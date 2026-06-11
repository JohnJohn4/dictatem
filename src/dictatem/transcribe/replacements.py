"""Replacement parser + apply — deterministic post-transcription substitution.

A [Replacement](../../../CONTEXT.md) rewrites a matched source string to a
target in regular dictation *before* it is pasted. Rules live one per line in
``~/.dictatem/replacements.md`` as ``source => target``; ``#`` comments and
blank lines are ignored, and malformed lines are skipped with a warning. An
**empty target deletes** the match and collapses the surrounding whitespace —
the literal-minded way to drop unambiguous fillers (``um``, ``uh``).

Matching is **case-insensitive on whole words**. No LLM is involved, which
distinguishes a Replacement from a Transform (see ADR-0024).

The parser (:func:`parse_replacements`) and the apply (:func:`apply_replacements`)
are PURE — string in, value out, no I/O. :func:`load_replacements` is the thin
file loader and :func:`bootstrap_replacements` writes the opt-in default file.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_ARROW = "=>"

# The first-run file ships with ONLY commented-out examples, so out of the box
# nothing is altered (ADR-0024: no silent autocorrect). Ambiguous fillers
# (`like`, `you know`, `actually`) are deliberately NOT offered — they are real
# words in context and a blind rule would shred meaning.
_DEFAULT_REPLACEMENTS_MD = """\
# Dictatem Replacements — deterministic find/replace on your dictation.
#
# Each active line is a rule:   source => target
# Matching is case-insensitive and on WHOLE words. An EMPTY target deletes the
# match and collapses the surrounding whitespace. Lines starting with '#' are
# comments; blank lines are ignored.
#
# Replacements are OPT-IN: nothing below is active. Uncomment a line (remove the
# leading '# ') to enable it. Dictatem never silently cleans up your speech.
#
# --- Unambiguous filler removal (uncomment to enable) ---
# um =>
# uh =>
# er =>
#
# --- Spelling / expansion examples ---
# teh => the
# btw => by the way
"""


@dataclass(frozen=True)
class Replacement:
    """One ``source => target`` rule. An empty *target* means delete."""

    source: str
    target: str


def parse_replacements(content: str) -> list[Replacement]:
    """Parse the contents of ``replacements.md`` into rules. PURE.

    ``source => target`` per line; ``#`` comments and blank lines are ignored.
    An empty target (``um =>``) is a delete rule. A line missing the ``=>``
    arrow, or with an empty source, is skipped with a warning.
    """
    rules: list[Replacement] = []
    for lineno, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        source, sep, target = line.partition(_ARROW)
        if not sep:
            logger.warning(
                "replacements.md line %d: no '=>' separator — skipping %r",
                lineno, raw_line,
            )
            continue
        source = source.strip()
        target = target.strip()
        if not source:
            logger.warning(
                "replacements.md line %d: empty source — skipping %r",
                lineno, raw_line,
            )
            continue
        rules.append(Replacement(source=source, target=target))
    return rules


def apply_replacements(text: str, rules: list[Replacement]) -> str:
    """Apply *rules* to *text* and return the result. PURE.

    Each rule matches its source case-insensitively on whole words. A
    non-empty target substitutes in place; an empty target deletes the match
    and collapses the surrounding whitespace so no double space is left behind.
    """
    for rule in rules:
        # \b alone won't bound sources whose ends aren't word characters (e.g.
        # "c++" — '+' is not a word char, so \b sits in the wrong place). Bound
        # instead on "not adjacent to a word character" via lookarounds: this
        # both handles punctuation-edged sources AND keeps standard whole-word
        # semantics (underscore counts as a word char, so "um" never matches
        # inside "um_var").
        pattern = re.compile(
            rf"(?<!\w)(?:{re.escape(rule.source)})(?!\w)",
            re.IGNORECASE,
        )
        if rule.target:
            text = pattern.sub(lambda _m, t=rule.target: t, text)
        else:
            text = _delete_collapsing_whitespace(text, pattern)
    return text


def _delete_collapsing_whitespace(text: str, pattern: re.Pattern[str]) -> str:
    """Delete every *pattern* match, collapsing the whitespace it leaves.

    A deleted word surrounded by spaces would otherwise leave a double space;
    a leading/trailing match would leave an edge space. We remove the match
    together with one adjacent run of whitespace, then tidy the edges.
    """
    # Consume surrounding whitespace with the match so "so um yeah" -> "so yeah",
    # not "so  yeah". Prefer eating the leading space; fall back to trailing.
    greedy = re.compile(
        rf"(?:\s+(?:{pattern.pattern})(?=\s|$)|(?<=^)(?:{pattern.pattern})\s+)",
        re.IGNORECASE,
    )
    result = greedy.sub("", text)
    # Any match the greedy pass missed (no adjacent whitespace at all) is a
    # lone token — drop it outright.
    result = pattern.sub("", result)
    return result.strip()


def load_replacements(path: Path) -> list[Replacement]:
    """Read *path* (thin I/O) and return parsed rules; ``[]`` if absent/unreadable."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return parse_replacements(content)


def bootstrap_replacements(path: Path) -> None:
    """Create *path* with commented-out opt-in examples if it does not exist.

    Never overwrites an existing user file. Out of the box the file activates
    no rules (ADR-0024 — no silent autocorrect).
    """
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_DEFAULT_REPLACEMENTS_MD, encoding="utf-8")
    logger.info("Bootstrapped default replacements file %s", path)


def default_replacements_path() -> Path:
    """Path to the user's ``~/.dictatem/replacements.md``."""
    return Path.home() / ".dictatem" / "replacements.md"
