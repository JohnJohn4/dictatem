"""Pure focus-drift decision for the regular-dictation paste rail (ADR-0026 / #97).

The daemon anchors the foreground identity (``target_id``) at **record-start** and
compares it to the live foreground at **paste time**. If focus drifted to a
different window/app during the wait (e.g. a long cold model load), the dictation
must NOT be pasted into the wrong window — it is held in the
[Most-recent dictation](../../CONTEXT.md#most-recent-dictation) buffer for recovery
instead. This module is the pure comparison; the capture is the thin
``ForegroundTracker`` adapter (see ``CONTEXT.md#trigger-fire`` for the same
``target_id`` rail the Trigger Fire path already compares).
"""

from __future__ import annotations


def focus_drifted(anchor_target_id: int | None, current_target_id: int) -> bool:
    """Return whether the foreground changed since record-start (ADR-0026 / #97).

    ``anchor_target_id`` is the foreground captured at record-start;
    ``current_target_id`` is the live foreground at paste time. Returns ``True``
    only when there *is* an anchor and it differs from the live foreground — so a
    missing anchor (no ``ForegroundTracker`` on the platform, or capture skipped)
    never holds a dictation, preserving the paste-as-before behaviour. The
    comparison is window-granular on Windows (HWND) and app-granular on macOS
    (PID), identical to the Last Paste / Trigger Fire rail.
    """
    if anchor_target_id is None:
        return False
    return anchor_target_id != current_target_id
