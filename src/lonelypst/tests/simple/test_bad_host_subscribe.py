import asyncio
from typing import Callable, Coroutine

from lonelypsc.http_client import HttpPubSubClient
from lonelypsp.util.cancel_and_check import cancel_and_check

from lonelypst.util.config_gen import ConfigGen
from lonelypst.util.timing import timing
from lonelypsc.client import PubSubRequestAmbiguousError
import sys


async def test_bad_host_subscribe(cgen: ConfigGen) -> None:
    """Verifies connecting to a bad host is finished within a reasonable amount of time"""
    with timing("_test_bad_host_subscribe_1", 30):
        await _test_with_runner(cgen, _test_bad_host_subscribe_1, 28)
    with timing("_test_bad_host_subscribe_2", 50):
        await _test_with_runner(cgen, _test_bad_host_subscribe_2, 48)


async def _test_with_runner(
    cgen: ConfigGen,
    runner: Callable[[ConfigGen], Coroutine[None, None, None]],
    seconds: int,
) -> None:
    """Verifies connecting to a bad host is finished within a reasonable amount of time"""
    task = asyncio.create_task(runner(cgen))
    await asyncio.wait([task], timeout=seconds)
    if not task.done():
        await cancel_and_check(task)
        raise Exception("Task did not finish in time")
    else:
        try:
            task.result()
        except PubSubRequestAmbiguousError:
            return
        except Exception as e:
            if sys.version_info >= (3, 11):
                if isinstance(e, ExceptionGroup) and all(
                    isinstance(e, PubSubRequestAmbiguousError) for e in e.exceptions
                ):
                    return
            raise


async def _test_bad_host_subscribe_1(cgen: ConfigGen) -> None:
    """Tries to connect to a bad host"""
    http_config = cgen.http(3002, override_ips=["192.168.0.72"])
    async with HttpPubSubClient(http_config) as client:
        async with client.subscribe_exact(b"topic") as subscription:
            async for _ in await subscription.messages():
                pass


async def _test_bad_host_subscribe_2(cgen: ConfigGen) -> None:
    """Tries to connect to a bad host"""
    http_config = cgen.http(3002, override_ips=["192.168.0.72", "192.168.0.73"])
    async with HttpPubSubClient(http_config) as client:
        async with client.subscribe_exact(b"topic") as subscription:
            async for _ in await subscription.messages():
                pass
    raise Exception("testing")
