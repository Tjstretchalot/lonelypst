"""Tests the various combinations of a websocket/http client notifying a
websocket/http subscriber
"""

import asyncio
import secrets

from lonelypsc.client import PubSubClient
from lonelypsc.http_client import HttpPubSubClient
from lonelypsc.ws_client import WebsocketPubSubClient

from lonelypst.util.config_gen import ConfigGen
from lonelypst.util.try_notify import try_notify


async def _test_notify_1(subscriber: PubSubClient, notifier: PubSubClient) -> None:
    topic = secrets.token_bytes(4)
    data = secrets.token_bytes(4)
    async with subscriber.subscribe_exact(topic) as subscription:
        messages = await subscription.messages()
        next_msg = asyncio.create_task(messages.__anext__())
        await asyncio.sleep(0.1)  # give time for subscription to go through
        notify_task = asyncio.create_task(try_notify(notifier, topic, 1, data=data))
        msg = await next_msg
        assert msg.data.read(-1) == data
    await notify_task


async def test_ws_http_notify_1(cgen: ConfigGen) -> None:
    """Verifies a websocket client can notify an http subscriber"""
    async with HttpPubSubClient(cgen.http(3002)) as subscriber, WebsocketPubSubClient(
        cgen.websocket()
    ) as notifier:
        await _test_notify_1(subscriber, notifier)


async def test_http_ws_notify_1(cgen: ConfigGen) -> None:
    """Verifies an http client can notify a websocket subscriber"""
    async with WebsocketPubSubClient(cgen.websocket()) as subscriber, HttpPubSubClient(
        cgen.http(3002)
    ) as notifier:
        await _test_notify_1(subscriber, notifier)


async def test_ws_ws_notify_1(cgen: ConfigGen) -> None:
    """Verifies a websocket client can notify a websocket subscriber"""
    async with WebsocketPubSubClient(
        cgen.websocket()
    ) as subscriber, WebsocketPubSubClient(cgen.websocket()) as notifier:
        await _test_notify_1(subscriber, notifier)


async def test_http_http_notify_1(cgen: ConfigGen) -> None:
    """Verifies an http client can notify an http subscriber"""
    async with HttpPubSubClient(cgen.http(3002)) as subscriber, HttpPubSubClient(
        cgen.http(3005)
    ) as notifier:
        await _test_notify_1(subscriber, notifier)


async def test_notify_1(cgen: ConfigGen) -> None:
    """Verifies all combinations of clients can notify subscribers"""
    await test_ws_http_notify_1(cgen)
    await test_http_ws_notify_1(cgen)
    await test_ws_ws_notify_1(cgen)
    await test_http_http_notify_1(cgen)
