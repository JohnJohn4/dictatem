"""Language selection: which language each clip is transcribed in (#273).

Pure. The backends only *gather* the inputs (Whisper's per-language
probabilities and the clip's post-VAD speech duration) and pass the chosen code
to the engine as ``language=``; every decision lives here so it is unit-tested
without an engine.

The config surface (``[model]``):

- no ``language`` key: English, no detection (the default);
- ``language = "<code>"``: pinned to that Whisper code, no detection;
- ``language = "auto"``: detect across every Whisper language;
- ``languages = ["en", "zh"]``: the Preferred Languages. When set it takes
  precedence over ``language`` and detection only chooses among them.

Detection is "sure or fall back": a clip with less than
:data:`MIN_DETECTION_SPEECH_S` of speech is never detected, and a detection
whose winner is below :data:`LANGUAGE_CONFIDENCE_THRESHOLD` (renormalised within
the Preferred Languages, when set) is not trusted. Either way the clip uses the
fallback: the last language confidently detected this session (if allowed),
else the first Preferred Language, else (for ``"auto"``) the OS UI language,
else English.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

logger = logging.getLogger(__name__)

# Every language code Whisper accepts (faster-whisper 1.2's
# ``tokenizer._LANGUAGE_CODES``; ``yue`` needs large-v3). Kept here so config
# validation never imports the engine; a test pins it to the installed engine.
WHISPER_LANGUAGE_CODES: frozenset[str] = frozenset({
    "af", "am", "ar", "as", "az", "ba", "be", "bg", "bn", "bo", "br", "bs", "ca",
    "cs", "cy", "da", "de", "el", "en", "es", "et", "eu", "fa", "fi", "fo", "fr",
    "gl", "gu", "ha", "haw", "he", "hi", "hr", "ht", "hu", "hy", "id", "is", "it",
    "ja", "jw", "ka", "kk", "km", "kn", "ko", "la", "lb", "ln", "lo", "lt", "lv",
    "mg", "mi", "mk", "ml", "mn", "mr", "ms", "mt", "my", "ne", "nl", "nn", "no",
    "oc", "pa", "pl", "ps", "pt", "ro", "ru", "sa", "sd", "si", "sk", "sl", "sn",
    "so", "sq", "sr", "su", "sv", "sw", "ta", "te", "tg", "th", "tk", "tl", "tr",
    "tt", "uk", "ur", "uz", "vi", "yi", "yo", "zh", "yue",
})

# The ``[model].language`` value meaning "detect across every language".
AUTO = "auto"

# The language used when nothing else applies, and the default with no key.
DEFAULT_LANGUAGE = "en"

# "Sure or fall back": a detected language is trusted only when its probability
# (renormalised within the Preferred Languages, when set) is at least this.
# Owner QA (#273): one-word "Summer." misdetected at fr 0.34 / el 0.57 / fr 0.28,
# while a full Mandarin sentence detected at zh 0.65 — 0.6 rejects the former.
LANGUAGE_CONFIDENCE_THRESHOLD = 0.6

# Clips with less post-VAD speech than this are never detected: Whisper's
# language ID is unreliable on a word or two, so they always use the fallback.
MIN_DETECTION_SPEECH_S = 1.5

# Locale primary subtags whose Whisper code differs (legacy ISO 639 codes and
# Whisper's own spellings).
_LOCALE_TO_WHISPER: dict[str, str] = {
    "iw": "he",  # legacy Hebrew
    "in": "id",  # legacy Indonesian
    "ji": "yi",  # legacy Yiddish
    "jv": "jw",  # Whisper spells Javanese "jw"
    "nb": "no",  # Norwegian Bokmal
    "fil": "tl",  # Filipino -> Tagalog
}


def normalise_language_code(value: str) -> str:
    """*value* trimmed and lower-cased, the form config validation compares."""
    return value.strip().lower()


def is_valid_language_setting(value: str) -> bool:
    """Whether *value* is a valid ``[model].language``: a Whisper code or ``"auto"``."""
    norm = normalise_language_code(value)
    return norm == AUTO or norm in WHISPER_LANGUAGE_CODES


def is_valid_language_code(value: str) -> bool:
    """Whether *value* is a Whisper language code (``"auto"`` is not one)."""
    return normalise_language_code(value) in WHISPER_LANGUAGE_CODES


def normalise_language_list(values: Iterable[str]) -> tuple[str, ...]:
    """Normalise each code and drop duplicates, keeping the first-seen order."""
    out: list[str] = []
    for value in values:
        norm = normalise_language_code(value)
        if norm and norm not in out:
            out.append(norm)
    return tuple(out)


def whisper_code_for_locale(tag: str | None) -> str | None:
    """The Whisper code for an OS locale / language tag, or ``None``.

    Accepts BCP-47 (``"zh-Hans-CN"``) and POSIX/Windows (``"en_US"``,
    ``"pt_BR.UTF-8"``) spellings; the primary subtag decides. ``None`` when the
    tag is empty or names a language Whisper doesn't know.
    """
    if not tag:
        return None
    primary = tag.split(".")[0].replace("_", "-").split("-")[0].strip().lower()
    code = _LOCALE_TO_WHISPER.get(primary, primary)
    return code if code in WHISPER_LANGUAGE_CODES else None


@dataclass(frozen=True)
class LanguagePolicy:
    """The session's language rule, built once from config.

    *pinned* set: every clip uses it, no detection. Otherwise detection runs:
    among *preferred* when non-empty, else across every language (``"auto"``),
    with *os_ui_language* as the last fallback before English.
    """

    pinned: str | None = DEFAULT_LANGUAGE
    preferred: tuple[str, ...] = ()
    os_ui_language: str | None = None

    @property
    def detects(self) -> bool:
        return self.pinned is None

    def allows(self, code: str) -> bool:
        """Whether a detection may choose *code* under this policy."""
        if self.preferred:
            return code in self.preferred
        return code in WHISPER_LANGUAGE_CODES

    @property
    def mode(self) -> str:
        """``"pinned"``, ``"preferred"`` or ``"auto"`` — for the startup log."""
        if self.pinned is not None:
            return "pinned"
        return "preferred" if self.preferred else AUTO


def language_policy(
    language: str | None,
    languages: Iterable[str] = (),
    *,
    os_ui_language: str | None = None,
) -> LanguagePolicy:
    """Build the :class:`LanguagePolicy` for validated ``[model]`` values.

    A non-empty *languages* wins over *language*. ``language`` ``None`` means
    the English default; ``"auto"`` detects. *os_ui_language* (a Whisper code,
    see :func:`whisper_code_for_locale`) only matters for ``"auto"``.
    """
    preferred = tuple(
        c for c in normalise_language_list(languages) if c in WHISPER_LANGUAGE_CODES
    )
    if preferred:
        return LanguagePolicy(pinned=None, preferred=preferred)
    if language is None:
        return LanguagePolicy(pinned=DEFAULT_LANGUAGE)
    norm = normalise_language_code(language)
    if norm == AUTO:
        ui = os_ui_language if os_ui_language in WHISPER_LANGUAGE_CODES else None
        return LanguagePolicy(pinned=None, os_ui_language=ui)
    if norm in WHISPER_LANGUAGE_CODES:
        return LanguagePolicy(pinned=norm)
    return LanguagePolicy(pinned=DEFAULT_LANGUAGE)


LanguageReason = Literal[
    "pinned", "detected", "short-clip", "unsure", "no-detection"
]
FallbackSource = Literal["session", "preferred-first", "os-ui", "default"]


@dataclass(frozen=True)
class LanguageChoice:
    """The language one clip is transcribed in, and why.

    *reason*: ``pinned`` (no detection by config), ``detected`` (a sure
    detection), ``short-clip`` (too little speech to detect), ``unsure`` (the
    winner was below the threshold) or ``no-detection`` (no probabilities were
    available, e.g. an English-only model). *fallback* names where a
    non-detected language came from. *probability* is the (renormalised)
    winner's probability when detection ran.
    """

    language: str
    reason: LanguageReason
    fallback: FallbackSource | None = None
    probability: float | None = None
    detected: str | None = None

    @property
    def confident(self) -> bool:
        return self.reason == "detected"

    def describe(self) -> str:
        """A log-safe one-liner: codes and numbers only, never text."""
        parts = [f"language={self.language}", f"reason={self.reason}"]
        if self.fallback is not None:
            parts.append(f"fallback={self.fallback}")
        if self.detected is not None and self.probability is not None:
            parts.append(f"top={self.detected} p={self.probability:.2f}")
        return " ".join(parts)


def needs_detection(policy: LanguagePolicy, speech_duration_s: float | None) -> bool:
    """Whether the backend should gather language probabilities for this clip.

    Never for a pinned policy; never for a clip shorter than
    :data:`MIN_DETECTION_SPEECH_S` (an unknown duration is treated as long
    enough — the threshold then decides).
    """
    if not policy.detects:
        return False
    return speech_duration_s is None or speech_duration_s >= MIN_DETECTION_SPEECH_S


def fallback_language(
    policy: LanguagePolicy, last_confident: str | None
) -> tuple[str, FallbackSource]:
    """The language (and its source) used when a clip isn't confidently detected."""
    if last_confident is not None and policy.allows(last_confident):
        return last_confident, "session"
    if policy.preferred:
        return policy.preferred[0], "preferred-first"
    if policy.os_ui_language is not None:
        return policy.os_ui_language, "os-ui"
    return DEFAULT_LANGUAGE, "default"


def choose_language(
    policy: LanguagePolicy,
    *,
    probabilities: Mapping[str, float] | None,
    speech_duration_s: float | None,
    last_confident: str | None,
) -> LanguageChoice:
    """Decide the language for one clip. Pure.

    *probabilities* maps Whisper codes to probabilities (``None`` when the
    backend did not or could not detect). With Preferred Languages they are
    restricted to the set and renormalised; the most likely wins (ties go to the
    earlier Preferred Language). The winner is trusted only at or above
    :data:`LANGUAGE_CONFIDENCE_THRESHOLD`; otherwise the fallback applies.
    """
    if policy.pinned is not None:
        return LanguageChoice(policy.pinned, "pinned")

    def _fallback(
        reason: LanguageReason, *, detected: str | None = None, p: float | None = None
    ) -> LanguageChoice:
        lang, source = fallback_language(policy, last_confident)
        return LanguageChoice(lang, reason, fallback=source, probability=p, detected=detected)

    if not needs_detection(policy, speech_duration_s):
        return _fallback("short-clip")
    if not probabilities:
        return _fallback("no-detection")

    if policy.preferred:
        candidates = {c: max(0.0, float(probabilities.get(c, 0.0))) for c in policy.preferred}
    else:
        candidates = {
            c: max(0.0, float(p))
            for c, p in probabilities.items()
            if c in WHISPER_LANGUAGE_CODES
        }
    total = sum(candidates.values())
    if total <= 0.0:
        return _fallback("no-detection")

    # max() keeps the first of equal values: dicts keep insertion order, so a
    # tie goes to the earlier Preferred Language.
    winner = max(candidates, key=lambda c: candidates[c])
    p = candidates[winner] / total if policy.preferred else candidates[winner]
    if p < LANGUAGE_CONFIDENCE_THRESHOLD:
        return _fallback("unsure", detected=winner, p=p)
    return LanguageChoice(winner, "detected", probability=p, detected=winner)


class LanguageSelector:
    """The session's language state around the pure :func:`choose_language`.

    One instance is shared by every backend of a session (the MLX engine and
    its CPU fallback), so "last confidently detected" survives an engine
    switch. It also remembers the last clip's choice, which the confirm pass
    (#249, a re-transcription of that same audio) reuses.
    """

    def __init__(self, policy: LanguagePolicy | None = None) -> None:
        self.policy = policy if policy is not None else LanguagePolicy()
        self._lock = threading.Lock()
        self._last_confident: str | None = None
        self._last_choice: LanguageChoice | None = None

    @property
    def last_confident(self) -> str | None:
        return self._last_confident

    def needs_detection(self, speech_duration_s: float | None) -> bool:
        return needs_detection(self.policy, speech_duration_s)

    def choose(
        self,
        probabilities: Mapping[str, float] | None,
        speech_duration_s: float | None,
    ) -> LanguageChoice:
        """Decide this clip's language, remember it, and log it (codes only)."""
        with self._lock:
            choice = choose_language(
                self.policy,
                probabilities=probabilities,
                speech_duration_s=speech_duration_s,
                last_confident=self._last_confident,
            )
            if choice.confident:
                self._last_confident = choice.language
            self._last_choice = choice
        if choice.reason == "pinned":
            logger.debug("Transcription %s", choice.describe())
        else:
            logger.info("Transcription %s", choice.describe())
        return choice

    def confirm_pass_language(self) -> str:
        """The language for the confirm pass: the last clip's, else the fallback."""
        with self._lock:
            if self.policy.pinned is not None:
                return self.policy.pinned
            if self._last_choice is not None:
                return self._last_choice.language
            return fallback_language(self.policy, self._last_confident)[0]
