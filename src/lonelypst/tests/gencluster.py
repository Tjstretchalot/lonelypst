"""Intended as a script target; starts broadcasters locally and runs the
simple tests against them as if by `tarcluster`
"""

import argparse
import asyncio
import json
import os
import secrets
import shutil
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Literal, Optional

import aiohttp
import aiohttp.abc
import uvicorn
from fastapi import FastAPI
from lonelypsp.auth.config import (
    AuthConfigFromParts,
    ToBroadcasterAuthConfig,
    ToSubscriberAuthConfig,
)
from lonelypsp.auth.helpers.hmac_auth_config import (
    IncomingHmacAuthDBConfig,
    IncomingHmacAuthDBReentrantConfig,
    IncomingHmacAuthSqliteDBConfig,
    ToBroadcasterHmacAuth,
    ToSubscriberHmacAuth,
)
from lonelypsp.auth.helpers.none_auth_config import (
    ToBroadcasterNoneAuth,
    ToSubscriberNoneAuth,
)
from lonelypsp.auth.helpers.token_auth_config import (
    ToBroadcasterTokenAuth,
    ToSubscriberTokenAuth,
)
from lonelypss.bknd.sweep_missed import sweep_missed
from lonelypss.config.config import (
    CompressionConfigFromParts,
    ConfigFromParts,
    DBConfig,
    GenericConfigFromValues,
    MissedRetryStandard,
    NotifySessionStandard,
)
from lonelypss.config.helpers.sqlite_db_config import SqliteDBConfig
from lonelypss.config.lifespan import setup_config, teardown_config
from lonelypss.middleware.config import ConfigMiddleware
from lonelypss.middleware.ws_receiver import WSReceiverMiddleware
from lonelypss.router import router as HttpPubSubRouter
from lonelypss.util.ws_receiver import SimpleFanoutWSReceiver

import lonelypst.tests.tarcluster
from lonelypst.util.constants import WEBSOCKET_MAX_COMPAT_SIZE

if sys.version_info < (3, 11):
    from typing import NoReturn

    def assert_never(value: NoReturn) -> NoReturn:
        raise AssertionError(f"Unhandled value: {value!r}")

else:
    from typing import assert_never


async def monkey_patch_IOBasePayload_write(
    self: aiohttp.payload.IOBasePayload, writer: aiohttp.abc.AbstractStreamWriter
) -> None:
    try:
        chunk = self._value.read(2**16)
        while chunk:
            await writer.write(chunk)
            chunk = self._value.read(2**16)
    finally:
        self._value.close()


aiohttp.payload.IOBasePayload.write = monkey_patch_IOBasePayload_write  # type: ignore


async def _main() -> None:

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        action="append",
        choices=["sqlite"],
        help="Database to use, unset for all",
    )
    parser.add_argument(
        "--s2b-auth",
        action="append",
        choices=["hmac", "token", "none"],
        help="Authentication for subscriber->broadcaster messages, unset for all",
    )
    parser.add_argument(
        "--b2s-auth",
        action="append",
        choices=["hmac", "token", "none"],
        help="Authentication for broadcaster->subscriber messages, unset for all",
    )
    args = parser.parse_args()

    db: List[Literal["sqlite"]] = args.db
    if not db:
        db = ["sqlite"]

    s2b_auth: List[Literal["hmac", "token", "none"]] = args.s2b_auth
    if not s2b_auth:
        s2b_auth = ["hmac", "token", "none"]

    b2s_auth: List[Literal["hmac", "token", "none"]] = args.b2s_auth
    if not b2s_auth:
        b2s_auth = ["hmac", "token", "none"]

    for db_item in db:
        for s2b_auth_item in s2b_auth:
            for b2s_auth_item in b2s_auth:
                print(
                    f"Running using db={db_item}, s2b_auth={s2b_auth_item}, b2s_auth={b2s_auth_item}"
                )
                await main(db_item, s2b_auth_item, b2s_auth_item)


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

        serd_secrets: Dict[str, Any] = {"version": "2"}
        hmac_db: Optional[IncomingHmacAuthDBConfig] = None

        s2b_secret = secrets.token_urlsafe(64)
        b2s_secret = secrets.token_urlsafe(64)

        to_broadcaster_auth: ToBroadcasterAuthConfig
        if s2b_auth_strategy == "hmac":
            serd_secrets["to-broadcaster"] = {"type": "hmac", "secret": s2b_secret}
            hmac_db = IncomingHmacAuthDBReentrantConfig(
                IncomingHmacAuthSqliteDBConfig(":memory:")
            )

            to_broadcaster_auth = ToBroadcasterHmacAuth(
                secret=s2b_secret,
                db_config=hmac_db,
            )
        elif s2b_auth_strategy == "token":
            serd_secrets["to-broadcaster"] = {"type": "token", "secret": s2b_secret}

            to_broadcaster_auth = ToBroadcasterTokenAuth(token=s2b_secret)
        elif s2b_auth_strategy == "none":
            to_broadcaster_auth = ToBroadcasterNoneAuth()
        else:
            assert_never(s2b_auth_strategy)

        to_subscriber_auth: ToSubscriberAuthConfig
        if b2s_auth_strategy == "hmac":
            serd_secrets["to-subscriber"] = {"type": "hmac", "secret": b2s_secret}

            if hmac_db is None:
                hmac_db = IncomingHmacAuthSqliteDBConfig(":memory:")

            to_subscriber_auth = ToSubscriberHmacAuth(
                secret=b2s_secret, db_config=hmac_db
            )
        elif b2s_auth_strategy == "token":
            serd_secrets["incoming"] = {"type": "token", "secret": b2s_secret}

            to_subscriber_auth = ToSubscriberTokenAuth(token=b2s_secret)
        elif b2s_auth_strategy == "none":
            to_subscriber_auth = ToSubscriberNoneAuth()
        else:
            assert_never(b2s_auth_strategy)

        with open(os.path.join(working_folder, "subscriber-secrets.json"), "w") as f:
            json.dump(serd_secrets, f)

        config = ConfigFromParts(
            auth=AuthConfigFromParts(
                to_broadcaster=to_broadcaster_auth, to_subscriber=to_subscriber_auth
            ),
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
                outgoing_max_ws_message_size=WEBSOCKET_MAX_COMPAT_SIZE,
                allow_training=True,
                compression_min_size=32,
                compression_trained_max_size=16 * 1024,
                compression_training_low_watermark=100 * 1024,
                compression_training_high_watermark=10 * 1024 * 1024,
                compression_retrain_interval_seconds=60 * 60 * 60,
                decompression_max_window_size=8 * 1024 * 1024,
            ),
            notify_session=NotifySessionStandard(),
        )
        config.message_body_spool_size
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
            # print("waiting 1m seconds for debugging")
            # await asyncio.sleep(1_000_000)
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
    asyncio.run(_main(), debug=False)
