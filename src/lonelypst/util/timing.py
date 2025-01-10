import time
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def timing(name: str, eat: float) -> Iterator[None]:
    st = time.perf_counter()
    yield None
    et = time.perf_counter()
    time_taken = et - st
    print(f"{name} took {time_taken:.2f} seconds")
    if time_taken >= eat:
        raise Exception(f"{name} took too long! {time_taken=}")
