"""Script target where there is an existing broadcaster cluster to
run tests against
"""

import asyncio
from typing import List

from lonelypst.tests.simple.test_bad_host_notify import test_bad_host_notify
from lonelypst.tests.simple.test_bad_host_subscribe import test_bad_host_subscribe
from lonelypst.tests.simple.test_http_notify_0 import test_http_notify_0
from lonelypst.tests.simple.test_http_open_close import test_http_open_close
from lonelypst.tests.simple.test_http_reusable import test_http_reusable
from lonelypst.tests.simple.test_notify_1 import test_notify_1
from lonelypst.tests.simple.test_notify_large import test_notify_large
from lonelypst.tests.simple.test_notify_many import test_notify_many
from lonelypst.tests.simple.test_notify_trained_compression import (
    test_notify_trained_compression,
)
from lonelypst.tests.simple.test_ws_notify_0 import test_ws_notify_0
from lonelypst.util.config_gen import ConfigGen
from lonelypst.util.timing import timing


async def _main() -> None:
    raise NotImplementedError


async def main(ips: List[str], auth_file_path: str) -> None:
    """Runs the standard tests against the broadcaster cluster at the given IPs"""
    print(f"Running tests against {ips=}")

    async with ConfigGen(ips, auth_file_path) as cgen:

        with timing(
            "test_http_reusable", 1
        ):  # will use more strict timing on next part
            await test_http_reusable(cgen)
        with timing("test_http_open_close", 0.02):
            await test_http_open_close(cgen)

        with timing("test_bad_host_subscribe", 80):
            await test_bad_host_subscribe(cgen)

        with timing("test_bad_host_notify", 20):
            await test_bad_host_notify(cgen)

        with timing("test_http_notify_0", 50.5):
            await test_http_notify_0(cgen)
        with timing("test_ws_notify_0", 50.5):
            await test_ws_notify_0(cgen)
        with timing("test_notify_1", 2):
            await test_notify_1(cgen)
        with timing("test_notify_many", 24):
            await test_notify_many(cgen)
        with timing("test_notify_large", 32):
            await test_notify_large(cgen)
    with timing("test_notify_trained_compression", 480):
        await test_notify_trained_compression(ConfigGen(ips, auth_file_path))


if __name__ == "__main__":
    asyncio.run(_main())
