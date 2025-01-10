"""Script target where there is an existing broadcaster cluster to
run tests against
"""

import asyncio
from typing import List

from lonelypst.tests.simple.test_http_notify_0 import test_http_notify_0
from lonelypst.tests.simple.test_http_reusable import test_http_reusable
from lonelypst.tests.simple.test_notify_1 import test_notify_1
from lonelypst.tests.simple.test_notify_many import test_notify_many
from lonelypst.tests.simple.test_ws_notify_0 import test_ws_notify_0
from lonelypst.util.config_gen import ConfigGen


async def _main() -> None:
    raise NotImplementedError


async def main(ips: List[str], auth_file_path: str) -> None:
    """Runs the standard tests against the broadcaster cluster at the given IPs"""
    print(f"Running tests against {ips=}")

    cgen = ConfigGen(ips, auth_file_path)
    await test_http_reusable(cgen)
    await test_http_notify_0(cgen)
    await test_ws_notify_0(cgen)
    await test_notify_1(cgen)
    await test_notify_many(cgen)


if __name__ == "__main__":
    asyncio.run(_main())
