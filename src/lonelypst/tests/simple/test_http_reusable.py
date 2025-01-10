import psutil
from lonelypsc.http_client import HttpPubSubClient

from lonelypst.util.config_gen import ConfigGen


async def test_http_reusable(cgen: ConfigGen) -> None:
    """Verifies we release the port and are able to rebind to it
    during the wait period
    """
    async with HttpPubSubClient(cgen.http(3002)):
        ...

    for conn in psutil.net_connections():
        if not conn.laddr:
            continue

        if conn.laddr.port != 3002:
            continue

        if conn.status == "LISTEN" or conn.status == "ESTABLISHED":
            raise Exception(f"Port 3002 still in use! {conn=}")

    async with HttpPubSubClient(cgen.http(3002)):
        ...
