from lonelypsc.http_client import HttpPubSubClient

from lonelypst.util.config_gen import ConfigGen
from lonelypst.util.try_notify import try_notify


async def test_http_notify_0(cgen: ConfigGen) -> None:
    """Verifies no errors and a clean exit to create a http client
    and notify a topic with no subscribers
    """
    async with HttpPubSubClient(cgen.http(3002)) as client:
        await try_notify(client, b"foo/bar", 0)
