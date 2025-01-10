from lonelypsc.client import PubSubClient


async def try_notify(
    client: PubSubClient, topic: bytes, expect_subscribers: int, data: bytes = b""
) -> None:
    """Notifies the given topic on the given client with the given data and raises
    an exception if there aren't the expected number of subscribers
    """
    result = await client.notify(topic=topic, data=data)
    assert result.notified == expect_subscribers, f"{result=}, {expect_subscribers=}"
