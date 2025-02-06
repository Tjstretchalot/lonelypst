"""Tests the various combinations of a websocket/http client notifying a
websocket/http subscriber
"""

import asyncio
import secrets
from typing import Any, Dict, List, Literal

from lonelypsc.client import PubSubClient, PubSubClientMessage, PubSubClientSubscription
from lonelypsc.http_client import HttpPubSubClient
from lonelypsc.ws_client import WebsocketPubSubClient

from lonelypst.util.config_gen import ConfigGen
from lonelypst.util.timing import timing
from lonelypst.util.try_notify import try_notify


async def _test_notify_many(
    subscribers: List[PubSubClient], notifier: PubSubClient, effective_subscribers: int
) -> None:
    topic = secrets.token_bytes(4)
    data = secrets.token_bytes(4)

    subscriptions: List[PubSubClientSubscription] = []
    message_tasks: List[asyncio.Task[PubSubClientMessage]] = []
    for subscriber in subscribers:
        is_receiving = asyncio.Event()

        async def _async_set() -> None:
            is_receiving.set()

        subscription = subscriber.subscribe_exact(topic, on_receiving=_async_set)
        await subscription.__aenter__()
        subscriptions.append(subscription)
        messages = await subscription.messages()
        message_tasks.append(asyncio.create_task(messages.__anext__()))
        await is_receiving.wait()

    notify_task = asyncio.create_task(
        try_notify(notifier, topic, len(subscribers), data=data)
    )

    for subscription, message_task in zip(subscriptions, message_tasks):
        msg = await message_task
        assert msg.data.read(-1) == data
        await subscription.__aexit__(None, None, None)

    await notify_task


async def _test_notify_many_of_type(
    cgen: ConfigGen,
    notifier_type: Literal["http", "ws"],
    subscriber_types: Dict[Literal["http", "ws"], int],
) -> None:
    notifier = (
        HttpPubSubClient(cgen.http(3002))
        if notifier_type == "http"
        else WebsocketPubSubClient(cgen.websocket())
    )
    await notifier.__aenter__()

    subscribers: List[PubSubClient] = []
    for i in range(subscriber_types.get("http", 0)):
        subscriber: PubSubClient[None, Any] = HttpPubSubClient(cgen.http(3005 + i))
        await subscriber.__aenter__()
        subscribers.append(subscriber)

    for i in range(subscriber_types.get("ws", 0)):
        subscriber = WebsocketPubSubClient(cgen.websocket())
        await subscriber.__aenter__()
        subscribers.append(subscriber)

    with timing(
        f"_test_notify_many_of_type: {notifier_type} notifies {subscriber_types}",
        0.2 + 0.2 * len(subscribers),
    ):
        await _test_notify_many(
            subscribers,
            notifier,
            subscriber_types.get("http", 0) + min(subscriber_types.get("ws", 0), 1),
        )

    await notifier.__aexit__(None, None, None)

    for subscriber in subscribers:
        await subscriber.__aexit__(None, None, None)


async def test_ws_http_notify_many(cgen: ConfigGen) -> None:
    """Verifies a websocket client can notify many http subscribers"""
    for count in (2, 3, 5):
        try:
            await _test_notify_many_of_type(cgen, "ws", {"http": count})
        except Exception as e:
            raise Exception(f"{count=}") from e


async def test_http_ws_notify_many(cgen: ConfigGen) -> None:
    """Verifies an http client can notify many websocket subscribers"""
    for count in (2, 3, 5):
        try:
            await _test_notify_many_of_type(cgen, "http", {"ws": count})
        except Exception as e:
            raise Exception(f"{count=}") from e


async def test_ws_ws_notify_many(cgen: ConfigGen) -> None:
    """Verifies a websocket client can notify many websocket subscribers"""
    for count in (2, 3, 5):
        try:
            await _test_notify_many_of_type(cgen, "ws", {"ws": count})
        except Exception as e:
            raise Exception(f"{count=}") from e


async def test_http_http_notify_many(cgen: ConfigGen) -> None:
    """Verifies an http client can notify many http subscribers"""
    for count in (2, 3, 5):
        try:
            await _test_notify_many_of_type(cgen, "http", {"http": count})
        except Exception as e:
            raise Exception(f"{count=}") from e


async def test_http_mixed_notify_many(cgen: ConfigGen) -> None:
    """Verifies an http client can notify many http and websocket subscribers"""
    for count in (1, 2, 3):
        try:
            await _test_notify_many_of_type(cgen, "http", {"http": count, "ws": count})
        except Exception as e:
            raise Exception(f"{count=}") from e


async def test_ws_mixed_notify_many(cgen: ConfigGen) -> None:
    """Verifies a websocket client can notify many http and websocket subscribers"""
    for count in (1, 2, 3):
        try:
            await _test_notify_many_of_type(cgen, "ws", {"http": count, "ws": count})
        except Exception as e:
            raise Exception(f"{count=}") from e


async def test_notify_many(cgen: ConfigGen) -> None:
    """Verifies all combinations of clients can notify subscribers"""
    with timing("test_ws_http_notify_many", 4):
        await test_ws_http_notify_many(cgen)
    with timing("test_http_ws_notify_many", 4):
        await test_http_ws_notify_many(cgen)
    with timing("test_ws_ws_notify_many", 4):
        await test_ws_ws_notify_many(cgen)
    with timing("test_http_http_notify_many", 4):
        await test_http_http_notify_many(cgen)
    with timing("test_http_mixed_notify_many", 4):
        await test_http_mixed_notify_many(cgen)
    with timing("test_ws_mixed_notify_many", 4):
        await test_ws_mixed_notify_many(cgen)
