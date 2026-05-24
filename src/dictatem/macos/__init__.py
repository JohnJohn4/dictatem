"""macOS platform support.

Pure cores in this package (the permission→Settings-pane mapper and the
Info.plist renderer) are unit-tested on any OS. The native adapters that touch
PyObjC (CGEventTap, AXUIElement, NSPasteboard, …) live in the ``macos`` and
``paste``/``autostart`` packages and are lazy-imported only inside
``daemon._start_macos_daemon`` — never at module top level (ADR-0014,
``tests/test_import_safety.py``).
"""

from __future__ import annotations
