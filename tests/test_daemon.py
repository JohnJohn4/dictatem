"""Tests for the skeleton daemon module."""

from __future__ import annotations

import sys

import pytest

from dictatem.daemon import main
from dictatem.exceptions import PlatformNotSupportedError

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="main() starts the Qt event loop on Windows and blocks; "
    "platform-gate behaviour is only meaningful to test on non-Windows.",
)


class TestDaemonPlatformGate:
    def test_raises_on_non_windows(self) -> None:
        with pytest.raises(PlatformNotSupportedError, match="Windows-only"):
            main(argv=[])

    def test_error_message_includes_platform(self) -> None:
        with pytest.raises(PlatformNotSupportedError, match=sys.platform):
            main(argv=[])

    def test_uninstall_flag_parses(self) -> None:
        # --uninstall is a recognized flag (argparse does not error); the
        # platform gate still fires first on non-Windows, before the registry.
        with pytest.raises(PlatformNotSupportedError, match="Windows-only"):
            main(argv=["--uninstall"])

    def test_unknown_flag_errors(self) -> None:
        # argparse exits (SystemExit) on an unrecognized flag.
        with pytest.raises(SystemExit):
            main(argv=["--bogus"])
