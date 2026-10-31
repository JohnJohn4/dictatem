"""Startup Trigger Word collision warnings in daemon.log (#251).

``log_trigger_lexicon_warnings`` is what ``start_daemon`` calls after loading
the Prompt Files: one warning per collision and per exact-only Alias,
never raising (startup is not blocked).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from dictatem.daemon import log_trigger_lexicon_warnings

if TYPE_CHECKING:
    import pytest

PROMPTS_DIR = Path("prompts")
DEFAULTS = {"polish.md": ["polish", "cleanup"], "summarize.md": ["summarize", "summarise"]}


def _messages(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == "dictatem.daemon"]


def test_collision_logs_one_warning_naming_both_aliases_and_files(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="dictatem.daemon"):
        log_trigger_lexicon_warnings({**DEFAULTS, "grand.md": ["palace"]}, (), PROMPTS_DIR)
    messages = _messages(caplog)
    assert len(messages) == 1
    level, text = messages[0]
    assert level == logging.WARNING
    for part in ("polish", "polish.md", "palace", "grand.md"):
        assert part in text


def test_exact_only_alias_logs_one_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="dictatem.daemon"):
        log_trigger_lexicon_warnings(DEFAULTS, ("glue",), PROMPTS_DIR)
    messages = _messages(caplog)
    assert len(messages) == 1
    level, text = messages[0]
    assert level == logging.WARNING
    assert "glue" in text
    assert "paste_aliases" in text


def test_each_finding_gets_its_own_line(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="dictatem.daemon"):
        log_trigger_lexicon_warnings(
            {**DEFAULTS, "grand.md": ["palace"], "rush.md": ["haste", "fix"]}, (), PROMPTS_DIR
        )
    levels = [level for level, _ in _messages(caplog)]
    # polish/palace, paste/haste, and the exact-only "fix"
    assert levels == [logging.WARNING] * 3


def test_shipped_defaults_log_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="dictatem.daemon"):
        log_trigger_lexicon_warnings(DEFAULTS, (), PROMPTS_DIR)
    assert _messages(caplog) == []
