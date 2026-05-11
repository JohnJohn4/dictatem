"""Tests for the skeleton daemon module."""

from __future__ import annotations

import sys

import pytest

from dictatem.daemon import main
from dictatem.exceptions import PlatformNotSupportedError


class TestDaemonPlatformGate:
    def test_raises_on_linux(self) -> None:
        assert sys.platform != "win32", "This test must run on Linux"
        with pytest.raises(PlatformNotSupportedError, match="Windows-only"):
            main()

    def test_error_message_includes_platform(self) -> None:
        with pytest.raises(PlatformNotSupportedError, match=sys.platform):
            main()
