import asyncio
from typing import Callable, Coroutine

from lonelypsc.http_client import HttpPubSubClient
from lonelypsp.util.cancel_and_check import cancel_and_check

from lonelypst.util.config_gen import ConfigGen
from lonelypst.util.timing import timing
from lonelypst.util.try_notify import try_notify
from lonelypsc.client import PubSubRequestAmbiguousError


async def test_bad_host_notify(cgen: ConfigGen) -> None:
    """Verifies connecting to a bad host is finished within a reasonable amount of time"""
    with timing("_test_bad_host_notify_1", 7):
        await _test_with_runner(cgen, _test_bad_host_notify_1, 5)
    with timing("_test_bad_host_notify_2", 20):
        await _test_with_runner(cgen, _test_bad_host_notify_2, 15)


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
            pass


async def _test_bad_host_notify_1(cgen: ConfigGen) -> None:
    """Tries to connect to a bad host"""
    http_config = cgen.http(3002, override_ips=["192.168.0.72"])
    async with HttpPubSubClient(http_config) as client:
        await try_notify(client, b"foo/bar", 0)


async def _test_bad_host_notify_2(cgen: ConfigGen) -> None:
    """Tries to connect to a bad host"""
    http_config = cgen.http(3002, override_ips=["192.168.0.72", "192.168.0.73"])
    print(f"{http_config.broadcasters=}")
    async with HttpPubSubClient(http_config) as client:
        await try_notify(client, b"foo/bar", 0)
    raise Exception("testing")
