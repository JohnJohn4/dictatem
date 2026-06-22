"""Shared test helpers (not fakes)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    """Block until *predicate* is true or *timeout* elapses (then raise).

    Load-on-arm (#161) runs the model load on a background thread, so tests
    that assert on its effects must wait for that thread rather than sleep a
    fixed amount.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition not met within timeout")
