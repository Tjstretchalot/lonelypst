"""Tests the various combinations of a websocket/http client notifying a
websocket/http subscriber
"""

import asyncio
import secrets

from lonelypsc.client import PubSubClient
from lonelypsc.http_client import HttpPubSubClient
from lonelypsc.ws_client import WebsocketPubSubClient

from lonelypst.util.config_gen import ConfigGen
from lonelypst.util.timing import timing
from lonelypst.util.try_notify import try_notify


async def _test_notify_large(subscriber: PubSubClient, notifier: PubSubClient) -> None:
    ready = asyncio.Event()

    async def on_receiving() -> None:
        ready.set()

    data = secrets.token_bytes(24 * 1024 * 1024)
    topic = secrets.token_bytes(4)
    async with subscriber.subscribe_exact(
        topic, on_receiving=on_receiving
    ) as subscription:
        messages = await subscription.messages()
        next_msg = asyncio.create_task(messages.__anext__())
        with timing("test_notify_large on_receiving", 1):
            await ready.wait()
        notify_task = asyncio.create_task(try_notify(notifier, topic, 1, data=data))
        await asyncio.wait([notify_task, next_msg], return_when=asyncio.FIRST_COMPLETED)
        if notify_task.done() and notify_task.exception() is not None:
            await notify_task

        msg = await next_msg
        assert msg.data.read(-1) == data
    await notify_task


async def test_ws_http_notify_large(cgen: ConfigGen) -> None:
    """Verifies a websocket client can notify an http subscriber"""
    async with HttpPubSubClient(cgen.http(3002)) as subscriber, WebsocketPubSubClient(
        cgen.websocket()
    ) as notifier:
        await _test_notify_large(subscriber, notifier)


async def test_http_ws_notify_large(cgen: ConfigGen) -> None:
    """Verifies an http client can notify a websocket subscriber"""
    async with WebsocketPubSubClient(cgen.websocket()) as subscriber, HttpPubSubClient(
        cgen.http(3002)
    ) as notifier:
        await _test_notify_large(subscriber, notifier)


async def test_ws_ws_notify_large(cgen: ConfigGen) -> None:
    """Verifies a websocket client can notify a websocket subscriber"""
    async with WebsocketPubSubClient(
        cgen.websocket()
    ) as subscriber, WebsocketPubSubClient(cgen.websocket()) as notifier:
        await _test_notify_large(subscriber, notifier)


async def test_http_http_notify_large(cgen: ConfigGen) -> None:
    """Verifies an http client can notify an http subscriber"""
    async with HttpPubSubClient(cgen.http(3002)) as subscriber, HttpPubSubClient(
        cgen.http(3005)
    ) as notifier:
        await _test_notify_large(subscriber, notifier)


async def test_notify_large(cgen: ConfigGen) -> None:
    """Verifies all combinations of clients can notify subscribers with a large
    (24mb) message"""
    with timing("test_ws_ws_notify_large", 8):
        await test_ws_ws_notify_large(cgen)
    with timing("test_http_ws_notify_large", 8):
        await test_http_ws_notify_large(cgen)
    with timing("test_ws_http_notify_large", 8):
        await test_ws_http_notify_large(cgen)
    with timing("test_http_http_notify_large", 8):
        await test_http_http_notify_large(cgen)
