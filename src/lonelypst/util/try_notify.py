from typing import TypeVar

from lonelypsc.client import PubSubClient

NotifierT = TypeVar("NotifierT")


async def try_notify(
    client: PubSubClient[None, NotifierT],
    topic: bytes,
    expect_subscribers: int,
    data: bytes = b"",
) -> None:
    """Notifies the given topic on the given client with the given data and raises
    an exception if there aren't the expected number of subscribers
    """
    result = await client.notify(trace_initializer=None, topic=topic, data=data)
    assert result.notified == expect_subscribers, f"{result=}, {expect_subscribers=}"
