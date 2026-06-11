"""Vocabulary parser + recognition-hint selection — biases transcription (#126).

[Vocabulary](../../../CONTEXT.md) terms — names, jargon, acronyms — bias the
transcription model toward the user's spellings. Terms live one per line in
``~/.dictatem/vocabulary.md``; ``#`` comments and blank lines are ignored.

The terms are fed to faster-whisper as a recognition hint. The backend's
``hotwords`` kwarg (newer faster-whisper) is preferred; older versions that lack
it fall back to ``initial_prompt``. Capability is detected by inspecting the
backend's ``transcribe`` signature (:func:`backend_supports_hotwords`), and the
choice itself (:func:`select_recognition_hint`) is PURE so it can be unit-tested
without a real model. The parser (:func:`parse_vocabulary`) is PURE too;
:func:`load_vocabulary` is the thin file loader and :func:`bootstrap_vocabulary`
writes the commented-example default file.
"""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

# Commented example + the over-long-list caveat. No active term out of the box.
_DEFAULT_VOCABULARY_MD = """\
# Dictatem Vocabulary — bias transcription toward your spellings.
#
# Put one term per line: names, jargon, acronyms, product names, non-English
# words you dictate often. Lines starting with '#' are comments; blank lines are
# ignored. Terms are NOT pasted as text — they only nudge how audio is heard.
#
# Keep the list focused: an over-long list can DEGRADE recognition rather than
# help it. Add the handful of terms Dictatem keeps mis-hearing, not a dictionary.
#
# Example (remove the leading '# ' to enable):
# Dictatem
"""


def parse_vocabulary(content: str) -> list[str]:
    """Parse the contents of ``vocabulary.md`` into terms. PURE.

    One term per line; lines starting with ``#`` (after stripping) are
    comments and blank lines are ignored. Surrounding whitespace is trimmed;
    the term's internal casing and characters are otherwise preserved (an
    inline ``#``, e.g. ``C# language``, is part of the term, not a comment).
    """
    terms: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        terms.append(line)
    return terms


def backend_supports_hotwords(transcribe: Callable[..., object]) -> bool:
    """Whether *transcribe* accepts a ``hotwords`` keyword argument.

    Detected by inspecting the signature so it tracks whatever faster-whisper
    version is actually installed. A callable whose signature cannot be read
    (some C-implemented callables) degrades to ``False`` — the safe
    ``initial_prompt`` path — rather than raising.
    """
    try:
        sig = inspect.signature(transcribe)
    except (TypeError, ValueError):
        return False
    return "hotwords" in sig.parameters


def select_recognition_hint(
    terms: list[str], *, supports_hotwords: bool
) -> dict[str, str]:
    """Map Vocabulary *terms* to a faster-whisper transcribe kwarg dict. PURE.

    Returns ``{"hotwords": "..."}`` when the backend supports it, else
    ``{"initial_prompt": "..."}``. Empty *terms* yields ``{}`` so the backend
    is called exactly as before — no hint, no behaviour change.
    """
    if not terms:
        return {}
    joined = " ".join(terms)
    if supports_hotwords:
        return {"hotwords": joined}
    return {"initial_prompt": joined}


def load_vocabulary(path: Path) -> list[str]:
    """Read *path* (thin I/O) and return parsed terms; ``[]`` if absent/unreadable."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return parse_vocabulary(content)


def bootstrap_vocabulary(path: Path) -> None:
    """Create *path* with a commented example + caveat if it does not exist.

    Never overwrites an existing user file. Out of the box no term is active.
    """
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_DEFAULT_VOCABULARY_MD, encoding="utf-8")
    logger.info("Bootstrapped default vocabulary file %s", path)


def default_vocabulary_path() -> Path:
    """Path to the user's ``~/.dictatem/vocabulary.md``."""
    return Path.home() / ".dictatem" / "vocabulary.md"
