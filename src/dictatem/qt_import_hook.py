"""Stop PySide6's import hook from re-reading the source of every imported module.

PySide6 wraps ``__import__`` for its optional ``__feature__`` switches
(``snake_case`` / ``true_property``). On first sight of each module imported
after Qt, ``shibokensupport.feature._mod_uses_pyside`` runs
``inspect.getsource(module)`` and searches it for the text "PySide6". That reads
every module's ``.py`` source a second time: faster-whisper, huggingface_hub,
httpx2, and so on.

On a machine whose endpoint scanner checks each file open, this was the bulk of
a slow first dictation after a gap. Work-laptop QA, 2026-11-03: about 5 s of a
6.9 s "resolve" step was this source scan. Warm, it still costs a little.

Dictatem never uses ``__feature__``, so for modules outside ``dictatem`` the
answer is "doesn't use PySide" without reading any source. Dictatem's own
modules still get the original check, so behaviour for them is unchanged.

This patches a private shiboken module. If its layout changes, the patch logs
at debug level and does nothing, and imports work exactly as before.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)

_FEATURE_MODULE = "shibokensupport.feature"
_OWN_PREFIX = "dictatem"


def limit_pyside_source_scan(modules: dict[str, Any] | None = None) -> bool:
    """Patch the hook in place; return True if it was patched.

    Call right after PySide6 is first imported. *modules* defaults to
    ``sys.modules`` (injectable for tests). Idempotent.
    """
    feature = (sys.modules if modules is None else modules).get(_FEATURE_MODULE)
    original = getattr(feature, "_mod_uses_pyside", None)
    if feature is None or not callable(original):
        logger.debug("PySide6 feature hook not found; leaving imports as they are")
        return False
    if getattr(original, "_dictatem_limited", False):
        return True

    def _mod_uses_pyside(module: Any) -> Any:
        name = getattr(module, "__name__", "")
        if isinstance(name, str) and (name == _OWN_PREFIX or name.startswith(_OWN_PREFIX + ".")):
            return original(module)
        return False

    _mod_uses_pyside._dictatem_limited = True  # type: ignore[attr-defined]
    setattr(feature, "_mod_uses_pyside", _mod_uses_pyside)  # noqa: B010 (private, untyped module)
    return True
