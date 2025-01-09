"""Script target where there is an existing broadcaster cluster to
run tests against
"""

import asyncio
from typing import List
from lonelypsc.config.file_config import get_auth_config_from_file
from lonelypsc.config.auth_config import AuthConfigFromParts
from lonelypsc.config.http_config import make_http_pub_sub_config
from lonelypsc.config.ws_config import make_websocket_pub_sub_config
from lonelypsc.http_client import HttpPubSubClient
from lonelypsc.ws_client import WebsocketPubSubClient
from lonelypsc.client import PubSubClient
import psutil


async def _main() -> None:
    raise NotImplementedError


async def main(ips: List[str], auth_file_path: str) -> None:
    """Runs the standard tests against the broadcaster cluster at the given IPs"""
    print(f"Running tests against {ips=}")
    auth_config_gen = lambda: AuthConfigFromParts(
        *get_auth_config_from_file(auth_file_path)
    )
    http_config_gen = lambda port: make_http_pub_sub_config(
        bind={"type": "uvicorn", "host": "0.0.0.0", "port": port},
        host=f"http://127.0.0.1:{port}",
        broadcasters=[{"host": f"http://{ip}"} for ip in ips],
        outgoing_retries_per_broadcaster=2,
        message_body_spool_size=1024 * 1024 * 10,
        outgoing_http_timeout_total=30,
        outgoing_http_timeout_connect=None,
        outgoing_http_timeout_sock_read=None,
        outgoing_http_timeout_sock_connect=5,
        outgoing_retry_ambiguous=True,
        auth=auth_config_gen(),
    )
    ws_config_gen = lambda: make_websocket_pub_sub_config(
        broadcasters=[
            {"host": "ws://127.0.0.1:3003"},
        ],
        outgoing_initial_connect_retries=2,
        outgoing_min_reconnect_interval=1,
        max_websocket_message_size=1024 * 128,
        websocket_open_timeout=5,
        websocket_close_timeout=5,
        websocket_heartbeat_interval=10,
        websocket_minimal_headers=True,
        max_sent_notifications=None,
        max_unsent_notifications=None,
        max_expected_acks=None,
        max_received=None,
        max_unsent_acks=None,
        allow_compression=True,
        compression_dictionary_by_id=dict(),
        initial_compression_dict_id=None,
        allow_training_compression=True,
        decompression_max_window_size=0,
        auth=auth_config_gen(),
    )

    print("Notifying foo/bar via http")
    async with HttpPubSubClient(http_config_gen(3002)) as client:
        await _try_notify(client, b"foo/bar", 0)

    print("Verifying 3002 is not in use anymore")
    for conn in psutil.net_connections():
        if conn.laddr.port != 3002:
            continue

        print(f"Found connection: {conn}")
        if conn.status == "LISTEN" or conn.status == "ESTABLISHED":
            raise Exception(f"Port 3002 still in use!")

    print("Notifying foo/bar via ws")
    async with WebsocketPubSubClient(ws_config_gen()) as client:
        await _try_notify(client, b"foo/bar", 0)

    print("Notifying foo/bar via http (makes sure we can still bind to 3002)")
    async with HttpPubSubClient(http_config_gen(3002)) as client:
        await _try_notify(client, b"foo/bar", 0)

    print("Subscribing on http & notifying on http")
    async with HttpPubSubClient(http_config_gen(3002)) as subscriber, HttpPubSubClient(
        http_config_gen(3005)
    ) as notifier:  # , WebsocketPubSubClient(ws_config_gen()) as notifier:
        async with subscriber.subscribe_exact(b"foo/bar") as subscription:
            messages = await subscription.messages()
            next_msg = asyncio.create_task(messages.__anext__())
            await asyncio.sleep(0.1)  # give time for subscription to go through
            notify_task = asyncio.create_task(
                _try_notify(notifier, b"foo/bar", 1, data=b"hello")
            )
            # will get the message before notify task as we block confirming its
            # received until its cleaned up
            msg = await next_msg
            assert msg.data.read() == b"hello"
        # exiting subscription acks the message
        await notify_task

    print("Subscribing on ws & notifying on ws")
    async with WebsocketPubSubClient(
        ws_config_gen()
    ) as subscriber, WebsocketPubSubClient(
        ws_config_gen()
    ) as notifier:  # , WebsocketPubSubClient(ws_config_gen()) as notifier:
        async with subscriber.subscribe_exact(b"foo/bar") as subscription:
            messages = await subscription.messages()
            next_msg = asyncio.create_task(messages.__anext__())
            await asyncio.sleep(0.1)  # give time for subscription to go through
            notify_task = asyncio.create_task(
                _try_notify(notifier, b"foo/bar", 1, data=b"hello")
            )
            msg = await next_msg
            assert msg.data.read() == b"hello"
        await notify_task

    print("Subscribing on http & notifying on ws")
    async with HttpPubSubClient(
        http_config_gen(3002)
    ) as subscriber, WebsocketPubSubClient(
        ws_config_gen()
    ) as notifier:  # , WebsocketPubSubClient(ws_config_gen()) as notifier:
        async with subscriber.subscribe_exact(b"foo/bar") as subscription:
            messages = await subscription.messages()
            next_msg = asyncio.create_task(messages.__anext__())
            await asyncio.sleep(0.1)  # give time for subscription to go through
            notify_task = asyncio.create_task(
                _try_notify(notifier, b"foo/bar", 1, data=b"hello")
            )
            msg = await next_msg
            assert msg.data.read() == b"hello"
        await notify_task

    print("Subscribing on ws & notifying on http")
    async with WebsocketPubSubClient(ws_config_gen()) as subscriber, HttpPubSubClient(
        http_config_gen(3002)
    ) as notifier:  # , WebsocketPubSubClient(ws_config_gen()) as notifier:
        async with subscriber.subscribe_exact(b"foo/bar") as subscription:
            messages = await subscription.messages()
            next_msg = asyncio.create_task(messages.__anext__())
            await asyncio.sleep(0.1)  # give time for subscription to go through
            notify_task = asyncio.create_task(
                _try_notify(notifier, b"foo/bar", 1, data=b"hello")
            )
            msg = await next_msg
            assert msg.data.read() == b"hello"
        await notify_task


async def _try_notify(
    client: PubSubClient, topic: bytes, expect_subscribers: int, data=b""
) -> None:
    result = await client.notify(topic=topic, data=data)
    assert result.notified == expect_subscribers, f"{result=}, {expect_subscribers=}"


if __name__ == "__main__":
    asyncio.run(_main())
