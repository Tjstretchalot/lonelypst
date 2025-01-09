"""Intended as a script target; starts broadcasters locally and runs the
simple tests against them as if by `tarcluster`
"""

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
import secrets
import shutil
import sys
from typing import Any, AsyncIterator, Dict, Literal, cast

import uvicorn
from fastapi import FastAPI
from lonelypss.bknd.sweep_missed import sweep_missed
from lonelypsp.util.cancel_and_check import cancel_and_check
from lonelypss.config.config import (
    DBConfig,
    ConfigFromParts,
    GenericConfigFromValues,
    MissedRetryStandard,
    CompressionConfigFromParts,
)
from lonelypss.config.auth_config import (
    AuthConfigFromParts,
    IncomingAuthConfig,
    OutgoingAuthConfig,
)

from lonelypss.middleware.config import ConfigMiddleware
from lonelypss.middleware.ws_receiver import WSReceiverMiddleware
from lonelypss.router import router as HttpPubSubRouter
from lonelypss.config.lifespan import setup_config, teardown_config
from lonelypss.util.ws_receiver import SimpleFanoutWSReceiver
from lonelypss.config.helpers.hmac_auth_config import (
    IncomingHmacAuth,
    IncomingHmacAuthSqliteDBConfig,
    OutgoingHmacAuth,
)
from lonelypss.config.helpers.none_auth_config import IncomingNoneAuth, OutgoingNoneAuth
from lonelypss.config.helpers.token_auth_config import (
    IncomingTokenAuth,
    OutgoingTokenAuth,
)
from lonelypss.config.helpers.sqlite_db_config import SqliteDBConfig

import lonelypst.tests.tarcluster

if sys.version_info < (3, 11):
    from typing import NoReturn

    def assert_never(value: NoReturn) -> NoReturn:
        raise AssertionError(f"Unhandled value: {value!r}")

else:
    from typing import assert_never


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        default="sqlite",
        choices=["sqlite"],
        help="Database to use",
    )
    parser.add_argument(
        "--s2b-auth",
        default="hmac",
        choices=["hmac", "token", "none"],
        help="Authentication for subscriber->broadcaster messages",
    )
    parser.add_argument(
        "--b2s-auth",
        default="hmac",
        choices=["hmac", "token", "none"],
        help="Authentication for broadcaster->subscriber messages",
    )
    args = parser.parse_args()

    await main(args.db, args.s2b_auth, args.b2s_auth)


async def main(
    db_strategy: Literal["sqlite"],
    s2b_auth_strategy: Literal["hmac", "token", "none"],
    b2s_auth_strategy: Literal["hmac", "token", "none"],
) -> None:
    working_folder = "tmp"
    print(f"Selected working folder: {working_folder=}")

    if os.path.exists(working_folder):
        print("Working folder already exists! Delete it first")
        return

    try:
        os.mkdir(working_folder)

        db: DBConfig
        if db_strategy == "sqlite":
            db = SqliteDBConfig(database=":memory:")
        else:
            assert_never(db_strategy)

        subscriber_secrets: Dict[str, Any] = {"version": "1"}

        s2b_secret = secrets.token_urlsafe(64)
        b2s_secret = secrets.token_urlsafe(64)

        incoming_auth: IncomingAuthConfig
        if s2b_auth_strategy == "hmac":
            subscriber_secrets["outgoing"] = {"type": "hmac", "secret": s2b_secret}

            incoming_auth = IncomingHmacAuth(
                subscriber_secret=s2b_secret,
                broadcaster_secret=b2s_secret,
                db_config=IncomingHmacAuthSqliteDBConfig(":memory:"),
            )
        elif s2b_auth_strategy == "token":
            subscriber_secrets["outgoing"] = {"type": "token", "secret": s2b_secret}

            incoming_auth = IncomingTokenAuth(
                subscriber_token=s2b_secret, broadcaster_token=b2s_secret
            )
        elif s2b_auth_strategy == "none":
            incoming_auth = IncomingNoneAuth()
        else:
            assert_never(s2b_auth_strategy)

        outgoing_auth: OutgoingAuthConfig
        if b2s_auth_strategy == "hmac":
            subscriber_secrets["incoming"] = {"type": "hmac", "secret": b2s_secret}

            outgoing_auth = OutgoingHmacAuth(secret=b2s_secret)
        elif b2s_auth_strategy == "token":
            subscriber_secrets["incoming"] = {"type": "token", "secret": b2s_secret}

            outgoing_auth = OutgoingTokenAuth(token=b2s_secret)
        elif b2s_auth_strategy == "none":
            outgoing_auth = OutgoingNoneAuth()
        else:
            assert_never(b2s_auth_strategy)

        with open(os.path.join(working_folder, "subscriber-secrets.json"), "w") as f:
            json.dump(subscriber_secrets, f)

        config = ConfigFromParts(
            auth=AuthConfigFromParts(incoming=incoming_auth, outgoing=outgoing_auth),
            db=db,
            generic=GenericConfigFromValues(
                message_body_spool_size=1024 * 1024 * 10,
                outgoing_http_timeout_total=30,
                outgoing_http_timeout_connect=None,
                outgoing_http_timeout_sock_read=5,
                outgoing_http_timeout_sock_connect=5,
                websocket_accept_timeout=2,
                websocket_max_pending_sends=255,
                websocket_max_unprocessed_receives=255,
                websocket_large_direct_send_timeout=0.3,
                websocket_send_max_unacknowledged=3,
                websocket_minimal_headers=True,
                sweep_missed_interval=10,
            ),
            missed=MissedRetryStandard(
                expo_factor=1,
                expo_base=2,
                expo_max=10,
                max_retries=20,
                constant=1,
                jitter=2,
            ),
            compression=CompressionConfigFromParts(
                compression_allowed=True,
                compression_dictionary_by_id=dict(),
                outgoing_max_ws_message_size=16 * 1024 * 1024,
                allow_training=True,
                compression_min_size=32,
                compression_trained_max_size=16 * 1024,
                compression_training_low_watermark=100 * 1024,
                compression_training_high_watermark=10 * 1024 * 1024,
                compression_retrain_interval_seconds=60 * 60 * 60,
                decompression_max_window_size=8 * 1024 * 1024,
            ),
        )
        fanout = SimpleFanoutWSReceiver(
            receiver_url="http://127.0.0.1:3003/v1/receive_for_websockets",
            recovery="http://127.0.0.1:3003/v1/missed_for_websockets",
            db=config,
        )

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
            await setup_config(config)
            try:
                async with fanout, sweep_missed(config):
                    yield
            finally:
                await teardown_config(config)

        app = FastAPI(lifespan=lifespan)
        app.add_middleware(ConfigMiddleware, config=config)
        app.add_middleware(WSReceiverMiddleware, ws_receiver=fanout)
        app.include_router(HttpPubSubRouter)
        app.router.redirect_slashes = False

        server = uvicorn.Server(uvicorn.Config(app, port=3003))

        print("Starting broadcaster...")
        uvicorn_task = asyncio.create_task(server.serve())
        try:
            print("Running tests...")
            await lonelypst.tests.tarcluster.main(
                ips=["127.0.0.1:3003"],
                auth_file_path=os.path.join(working_folder, "subscriber-secrets.json"),
            )
        finally:
            print("Shutting down broadcaster...")
            server.should_exit = True
            await uvicorn_task
    finally:
        print("Cleaning up working folder...")
        shutil.rmtree(working_folder)

    print("All done!")


if __name__ == "__main__":
    asyncio.run(_main(), debug=True)
