"""Dictation Session — the per-dictation state, with an epoch (#234).

Pure logic, stdlib only. One session spans a single dictation: from
record-start, through transcription (and any Transform), to the paste — or to
a cancel/recovery. Daemon-lifetime state (Last Paste, the Most-recent
dictation, model warm/preload flags) deliberately does NOT live here; Last
Paste must survive across dictations.

The **epoch** is a monotonically increasing integer. ``begin()`` (starting a
recording) and ``end()`` (cancel or recover-to-idle) both bump it and clear
the per-dictation fields, so any epoch captured before the latest bump is
stale — the hook later work uses to drop results from an abandoned dictation.
"""

from __future__ import annotations


class DictationSession:
    """The current dictation's state; mutate the fields, bump via begin/end."""

    def __init__(self) -> None:
        self._epoch = 0
        # A transcription worker's result is still awaited for this dictation.
        self.transcription_outstanding: bool = False
        # A Transform (Trigger Fire) worker's result is still awaited.
        self.transform_outstanding: bool = False
        # Characters the paste must first backspace over (Trigger Fire); 0 for
        # a regular dictation.
        self.pending_replace_chars: int = 0
        # Foreground identity captured at record-start — the focus-drift
        # anchor (ADR-0026 / #97). A comparison token only, never refocused.
        self.record_start_target_id: int | None = None
        # The text waiting to be pasted once the state machine says PASTE.
        self.text_to_paste: str | None = None

    @property
    def epoch(self) -> int:
        return self._epoch

    def begin(self) -> None:
        """Start a new dictation: bump the epoch and clear every field."""
        self._advance()

    def end(self) -> None:
        """End the current dictation (cancel/recover): bump and clear."""
        self._advance()

    def _advance(self) -> None:
        self._epoch += 1
        self.transcription_outstanding = False
        self.transform_outstanding = False
        self.pending_replace_chars = 0
        self.record_start_target_id = None
        self.text_to_paste = None
