"""Tests the various combinations of a websocket/http client notifying a
websocket/http subscriber
"""

import asyncio
import json
import multiprocessing
import multiprocessing.synchronize
import secrets
import time
from typing import Callable, Iterator, List

from lonelypsc.ws_client import WebsocketPubSubClient

from lonelypst.util.config_gen import ConfigGen
from lonelypst.util.timing import timing


def _no_bytes() -> bytes:
    return b""


def _ultra_compressible() -> bytes:
    return b"\x00" * 1024


def _non_compressible() -> bytes:
    return secrets.token_bytes(1024)


def _partially_compressible() -> bytes:
    # about 191 bytes of data, which is compressible to about 42 bytes
    # Python 3.11.1 (tags/v3.11.1:a7a450f, Dec  6 2022, 19:58:39) [MSC v.1934 64 bit (AMD64)] on win32
    # Type "help", "copyright", "credits" or "license" for more information.
    # >>> import lonelypst.tests.simple.test_ws_trained_compression as t
    # >>> t._partially_compressible()
    # b'{"username": "U_YKPeC057k", "email": "U_YKPeC057k@example.com", "favorite_color": "green", "favorite_number": 8, "favorit: "green", "favorite_number": 8, "favorite_fruit": "apple", "updated_at_ms": 1736867963932, "is_admin": true}'
    # >>> len(t._partially_compressible())
    # 191
    # >>> examples = [t._partially_compressible() for _ in range(1024 * 8)]
    # >>> import zstandard
    # >>> zdict = zstandard.train_dictionary(65536, examples)
    # >>> zdict.precompute_compress(10)
    # >>> compressor = zstandard.ZstdCompressor(level=10,dict_data=zdict, write_checksum=False, write_content_size=False, write_dict_id=False)

    # >>> compressor.compress(t._partially_compressible())
    # b"(\xb5/\xfd\x00\x00%\x01\x00\x88B8evh5_OEXk149373\x07\xfc\x80\xe9\xee\t\xe0\xac\xce[\x17'5Qf\xf6\xe1\x05"
    # >>> len(compressor.compress(t._partially_compressible()))
    # 42
    # >>>
    uname = secrets.token_urlsafe(8)
    return json.dumps(
        {
            "username": uname,
            "email": f"{uname}@example.com",
            "favorite_color": secrets.choice(["red", "green", "blue"]),
            "favorite_number": secrets.randbelow(100),
            "favorite_fruit": secrets.choice(["apple", "banana", "cherry"]),
            "updated_at_ms": int(time.time() * 1000),
            "is_admin": secrets.choice([True, False]),
        }
    ).encode()


def timing_per_iteration(name: str, num_items: int, batch_size: int) -> Iterator[None]:
    print(f"{name=} {num_items=} {batch_size=} starting")
    started_at_mono = time.monotonic()
    last_batch_start_at = started_at_mono
    for i in range(num_items):
        yield

        if i > 0 and i % batch_size == 0:
            now = time.monotonic()
            num_finished = i + 1
            elapsed_total = now - started_at_mono
            elapsed_batch = now - last_batch_start_at
            est_messages_per_second_total = num_finished / elapsed_total
            total_time_based_on_total = num_items / est_messages_per_second_total
            est_messages_per_second_batch = batch_size / elapsed_batch
            total_time_based_on_batch = num_items / est_messages_per_second_batch

            print(
                f"  {i: >5}: @{elapsed_total:.3f}s ~{est_messages_per_second_total:.1f}m/s (T) | ~{est_messages_per_second_batch:.1f}m/s (B) (~fin: @{total_time_based_on_total:.1f}s (T) | @{total_time_based_on_batch:.1f}s (B))"
            )

            last_batch_start_at = now


async def _async_notifier_task(
    name: str, cgen: ConfigGen, topic: bytes, to_send: List[bytes]
) -> None:
    async with WebsocketPubSubClient(cgen.websocket()) as notifier:
        timing_iter = timing_per_iteration(name, len(to_send), 4096)
        for data in to_send:
            await notifier.notify(topic=topic, data=data)
            next(timing_iter)


def _notifier_process_target(
    name: str, cgen: ConfigGen, topic: bytes, to_send: List[bytes]
) -> None:
    asyncio.run(_async_notifier_task(name, cgen, topic, to_send))


async def _async_subscriber_task(
    cgen: ConfigGen,
    topic: bytes,
    to_receive: List[bytes],
    on_ready: multiprocessing.synchronize.Event,
) -> None:
    async with WebsocketPubSubClient(cgen.websocket()) as subscriber:
        ready = asyncio.Event()

        async def on_receiving() -> None:
            ready.set()
            on_ready.set()

        async with subscriber.subscribe_exact(
            topic, on_receiving=on_receiving
        ) as subscription:
            messages = await subscription.messages()
            next_msg = asyncio.create_task(messages.__anext__())
            await ready.wait()

            last_next_msg_idx_excl = len(to_receive) - 1
            for i, data in enumerate(to_receive):
                msg = await next_msg
                assert msg.data.read(-1) == data
                if i < last_next_msg_idx_excl:
                    next_msg = asyncio.create_task(messages.__anext__())


def _subscriber_process_target(
    cgen: ConfigGen,
    topic: bytes,
    to_receive: List[bytes],
    on_ready: multiprocessing.synchronize.Event,
) -> None:
    asyncio.run(_async_subscriber_task(cgen, topic, to_receive, on_ready))


async def _test_notify_repeatedly(
    name: str,
    cgen: ConfigGen,
    sampler: Callable[[], bytes],
    num_messages: int = 1024 * 16,
) -> None:
    topic = secrets.token_bytes(4)
    to_send = [sampler() for _ in range(num_messages)]

    subscriber_ready_event = multiprocessing.Event()
    subscriber_process = multiprocessing.Process(
        target=_subscriber_process_target,
        args=(
            cgen,
            topic,
            to_send,
            subscriber_ready_event,
        ),
        daemon=True,
    )
    subscriber_process.start()
    await asyncio.to_thread(subscriber_ready_event.wait)

    notifier_process = multiprocessing.Process(
        target=_notifier_process_target,
        args=(name, cgen, topic, to_send),
        daemon=True,
    )
    notifier_process.start()

    subscriber_wait = asyncio.create_task(asyncio.to_thread(subscriber_process.join))
    notifier_wait = asyncio.create_task(asyncio.to_thread(notifier_process.join))
    try:
        await asyncio.wait(
            [subscriber_wait, notifier_wait], return_when=asyncio.FIRST_COMPLETED
        )
    except BaseException:
        subscriber_process.terminate()
        notifier_process.terminate()
        raise
    try:
        await asyncio.wait(
            [subscriber_wait, notifier_wait],
            return_when=asyncio.ALL_COMPLETED,
            timeout=5,
        )
    except BaseException:
        subscriber_process.terminate()
        notifier_process.terminate()
        raise


async def test_notify_trained_compression(cgen: ConfigGen) -> None:
    """Various tests related to triggering trained compression on websockets"""
    with timing("test_notify_trained_compression: empty payload, 16384 messages", 120):
        await _test_notify_repeatedly("empty payload", cgen, _no_bytes)

    with timing(
        "test_notify_trained_compression: ultra compressible payload, 16384 messages",
        120,
    ):
        await _test_notify_repeatedly(
            "ultra compressible payload", cgen, _ultra_compressible
        )

    with timing(
        "test_notify_trained_compression: non compressible payload, 16384 messages", 120
    ):
        await _test_notify_repeatedly(
            "non compressible payload", cgen, _non_compressible
        )

    with timing(
        "test_notify_trained_compression: partially compressible payload, 16384 messages",
        120,
    ):
        await _test_notify_repeatedly(
            "partially compressible payload", cgen, _partially_compressible
        )
