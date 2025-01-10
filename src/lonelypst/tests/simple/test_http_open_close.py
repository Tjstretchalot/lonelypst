import time

from lonelypst.util.config_gen import ConfigGen
from lonelypst.util.timing import timing
from lonelypsc.http_client import HttpPubSubClient


async def test_http_open_close(cgen: ConfigGen) -> None:
    """Verifies we can open and close a http client without error, quickly"""

    with timing("build config", 0.01):
        config = cgen.http(3002)

    with timing("build client", 0.01):
        client = HttpPubSubClient(config)

    with timing("enter client", 0.01):
        await client.__aenter__()

    with timing("exit client", 0.01):
        await client.__aexit__(None, None, None)
