from contextlib import contextmanager
import time
from typing import Iterable


@contextmanager
def timing(name: str, eat: float) -> Iterable[None]:
    st = time.perf_counter()
    yield
    et = time.perf_counter()
    time_taken = et - st
    print(f"{name} took {time_taken:.2f} seconds")
    if time_taken >= eat:
        raise Exception(f"{name} took too long! {time_taken=}")
