from lonelypsc.ws_client import WebsocketPubSubClient

from lonelypst.util.config_gen import ConfigGen
from lonelypst.util.try_notify import try_notify


async def test_ws_notify_0(cgen: ConfigGen) -> None:
    """Verifies no errors and a clean exit to create a websocket client
    and notify a topic with no subscribers
    """
    async with WebsocketPubSubClient(cgen.websocket()) as client:
        await try_notify(client, b"foo/bar", 0)
