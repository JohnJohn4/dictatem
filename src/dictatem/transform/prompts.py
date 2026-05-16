"""Prompt-file parser, folder loader, and first-run bootstrap.

See ADR-0003 (`docs/adr/0003-prompts-as-frontmatter-md-files.md`) for
the file-format rationale.

A Prompt File is a ``.md`` document with YAML-style frontmatter declaring
its Aliases, followed by the prompt body sent verbatim to Ollama as the
system prompt::

    ---
    aliases: [summarize, summarise]
    ---
    You are a text condenser...

The filename is informational only — Aliases in frontmatter are the
single source of truth.
"""

from __future__ import annotations

import logging
import shutil
import string
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedPromptFile:
    aliases: list[str]
    body: str


def parse_prompt_file(content: str, *, source: str = "<string>") -> ParsedPromptFile | None:
    """Parse the contents of a single prompt ``.md`` file.

    Returns ``None`` (and logs a warning identifying *source*) on every
    malformed case: missing/unterminated frontmatter, missing ``aliases``
    key, non-list ``aliases``, empty alias list.
    """
    if not content.startswith("---"):
        logger.warning("Prompt file %s: missing opening '---' — skipping", source)
        return None

    # Strip the opening fence and find the closing one.
    after_open = content.split("\n", 1)
    if len(after_open) < 2:
        logger.warning("Prompt file %s: no content after opening '---' — skipping", source)
        return None
    rest = after_open[1]

    close_idx = rest.find("\n---")
    if close_idx == -1:
        logger.warning("Prompt file %s: missing closing '---' — skipping", source)
        return None

    fm_block = rest[:close_idx]
    body_start = close_idx + len("\n---")
    body = rest[body_start:].lstrip("\n").rstrip()
    if rest[body_start:body_start + 1] not in ("", "\n"):
        # The closing fence must be at the start of its own line.
        logger.warning("Prompt file %s: closing '---' is not on its own line — skipping", source)
        return None

    aliases = _parse_aliases(fm_block)
    if aliases is None:
        logger.warning(
            "Prompt file %s: frontmatter has no valid 'aliases' list — skipping", source
        )
        return None
    if not aliases:
        logger.warning("Prompt file %s: 'aliases' list is empty — skipping", source)
        return None

    return ParsedPromptFile(aliases=aliases, body=body)


def _parse_aliases(fm_block: str) -> list[str] | None:
    """Extract ``aliases: [a, b, ...]`` from a frontmatter block.

    Only the inline ``[..]`` flow style is supported — that is the schema
    documented in ADR-0003. Returns ``None`` if the key is missing or
    the value is not a bracketed list. Returned aliases are stripped of
    surrounding whitespace and surrounding quotes but otherwise verbatim
    (normalisation is the loader's job).
    """
    for raw_line in fm_block.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        if key.strip() != "aliases":
            continue
        value = value.strip()
        if not (value.startswith("[") and value.endswith("]")):
            return None
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_strip_quotes(item.strip()) for item in inner.split(",") if item.strip()]
    return None


def _strip_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    return token


def _normalise_alias(alias: str) -> str:
    return alias.strip().strip(string.punctuation).lower()


def load_prompts_dir(directory: Path) -> dict[str, str]:
    """Load every ``*.md`` in *directory* into a flat alias → body map.

    Files that fail to parse are skipped (the parser already logged).
    Alias normalisation matches ``TriggerDetector``'s match rule. On a
    collision across files the first occurrence wins (deterministic by
    sorted filename) and a warning is logged.
    """
    result: dict[str, str] = {}
    if not directory.is_dir():
        return result

    for path in sorted(directory.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Prompt file %s: read failed (%s) — skipping", path, exc)
            continue

        parsed = parse_prompt_file(content, source=str(path))
        if parsed is None:
            continue

        for alias in parsed.aliases:
            key = _normalise_alias(alias)
            if not key:
                logger.warning(
                    "Prompt file %s: alias %r normalises to empty — skipping that alias",
                    path, alias,
                )
                continue
            if key in result:
                logger.warning(
                    "Prompt file %s: alias %r already registered — keeping first occurrence",
                    path, alias,
                )
                continue
            result[key] = parsed.body

    return result


def bootstrap_prompts(target: Path, source: Path) -> None:
    """Copy any default ``*.md`` from *source* into *target* if missing.

    Creates *target* if absent. Never overwrites an existing user file.
    If *source* does not exist (e.g. running from an oddly-laid-out
    checkout), this is a no-op.
    """
    target.mkdir(parents=True, exist_ok=True)
    if not source.is_dir():
        logger.warning("Default prompts directory %s not found — skipping bootstrap", source)
        return

    for default_path in sorted(source.glob("*.md")):
        dest = target / default_path.name
        if dest.exists():
            continue
        shutil.copy2(default_path, dest)
        logger.info("Bootstrapped default prompt %s → %s", default_path.name, dest)


def default_prompts_dir() -> Path:
    """Path to the prompts directory bundled with the installed package."""
    return Path(__file__).resolve().parent.parent / "default_prompts"
