"""Read the OS user-interface language as a Whisper code (#273).

A thin native adapter for the ``[model].language = "auto"`` fallback: the
mapping from a locale tag to a Whisper code is the pure
:func:`dictatem.transcribe.language.whisper_code_for_locale`.

- **Windows:** ``GetUserDefaultUILanguage()`` (the display language the user
  picked in Settings), turned into a locale name by ``locale.windows_locale``.
- **macOS:** the first of the user's preferred languages
  (``NSLocale.preferredLanguages``, via ``defaults read -g AppleLanguages`` so
  no PyObjC import is needed).
- **Anything else:** ``None`` (the caller falls back to English).

Never raises: any failure is logged at debug and returns ``None``.
"""

from __future__ import annotations

import logging
import subprocess
import sys

from dictatem.transcribe.language import whisper_code_for_locale

logger = logging.getLogger(__name__)


def _windows_ui_locale() -> str | None:
    import ctypes
    import locale

    langid = int(ctypes.windll.kernel32.GetUserDefaultUILanguage())  # type: ignore[attr-defined]
    return locale.windows_locale.get(langid)


def first_apple_language(defaults_output: str) -> str | None:
    """The first entry of ``defaults read -g AppleLanguages`` output. Pure.

    The output is a property-list array, e.g. ``(\\n    "zh-Hans-CN",\\n    en\\n)``.
    """
    for raw in defaults_output.splitlines():
        entry = raw.strip().strip(",").strip().strip('"')
        if entry and entry not in ("(", ")"):
            return entry
    return None


def _macos_ui_locale() -> str | None:
    out = subprocess.run(
        ["defaults", "read", "-g", "AppleLanguages"],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )
    if out.returncode != 0:
        return None
    return first_apple_language(out.stdout)


def read_os_ui_language() -> str | None:
    """The OS UI language as a Whisper code, or ``None`` if unknown/unsupported."""
    try:
        if sys.platform == "win32":
            tag = _windows_ui_locale()
        elif sys.platform == "darwin":
            tag = _macos_ui_locale()
        else:
            return None
    except Exception:
        logger.debug("Could not read the OS UI language", exc_info=True)
        return None
    return whisper_code_for_locale(tag)
