"""Configuration defaults and TOML loading for Dictatem."""

from __future__ import annotations

import ipaddress
import logging
import re
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from dictatem.transcribe.language import (
    is_valid_language_code,
    is_valid_language_setting,
    normalise_language_code,
    normalise_language_list,
)
from dictatem.transform.alias import normalise_alias

if TYPE_CHECKING:
    from collections.abc import Callable

    from dictatem.interfaces import HardwareProbe
    from dictatem.types import HardwareProfile

logger = logging.getLogger(__name__)

VALID_OVERLAY_POSITIONS = frozenset({
    "top-left", "top-right", "bottom-left", "bottom-right",
})

# Curated allow-list of trigger-input names for [hotkey].modifiers. "meta" is
# the canonical cross-platform name for the OS key (Windows key on Windows,
# Command on macOS); "win" is a permanent alias for it. "mouse4"/"mouse5" are the
# side buttons and "middle" the wheel click — first-class trigger inputs in the
# same combo as modifiers (left/right click are never accepted). See ADR-0010,
# ADR-0018, ADR-0020, and CONTEXT.md#hotkey-combo.
VALID_MODIFIER_NAMES = frozenset({
    "meta", "win", "alt", "ctrl", "shift", "mouse4", "mouse5", "middle",
})

# The only supported [audio].sample_rate (#238 / F-12).
SAMPLE_RATE_HZ = 16_000

VALID_LOG_LEVELS = frozenset({
    "debug", "info", "warning", "error", "critical",
})

# Fields where the value must be strictly positive (> 0).
_POSITIVE_INT_FIELDS: dict[str, set[str]] = {
    "hotkey": {"tap_threshold_ms"},
    "model": {"idle_unload_minutes", "min_transcription_chars"},
    "paste": {"clipboard_retry_attempts", "clipboard_retry_delay_ms"},
    "overlay": {"fade_in_ms", "fade_out_ms", "waveform_fps"},
    "audio": {"sample_rate"},
    "logging": {"rotation_days"},
    "behaviour": {"silence_timeout_s", "max_recording_seconds", "model_timeout_s"},
    "transform": {"last_paste_ttl_s"},
}


def _normalise_aliases(aliases: tuple[str, ...]) -> tuple[str, ...]:
    """Normalise like Prompt File aliases; drop blanks and duplicates (#250)."""
    out: list[str] = []
    for alias in aliases:
        norm = normalise_alias(alias)
        if norm and norm not in out:
            out.append(norm)
    return tuple(out)


# Fields whose valid value is normalised before use: section -> key -> normaliser.
_FIELD_NORMALISERS: dict[str, dict[str, Callable[[Any], Any]]] = {
    "trigger_words": {"paste_aliases": _normalise_aliases},
    "model": {
        "language": normalise_language_code,
        "languages": normalise_language_list,
    },
}


@dataclass
class HotkeyConfig:
    modifiers: tuple[str, ...] = ("win", "alt")
    tap_threshold_ms: int = 200


@dataclass
class ModelConfig:
    name: str = "large-v3-turbo"
    compute_type: str = "float16"
    device: str = "cuda"
    # Transcription language (#273). Unset = English, no detection; a Whisper
    # code pins it; "auto" detects any language. A non-empty ``languages`` (the
    # Preferred Languages) wins and detects only among them. The
    # sure-or-fall-back rule lives in dictatem.transcribe.language.
    language: str | None = None
    languages: tuple[str, ...] = ()
    vad_filter: bool = True
    idle_unload_minutes: int = 30
    min_transcription_chars: int = 3


@dataclass
class PasteConfig:
    trailing_space: bool = True
    strip_newlines: bool = True
    clipboard_retry_attempts: int = 5
    clipboard_retry_delay_ms: int = 10


@dataclass
class OverlayConfig:
    position: str = "bottom-right"
    fade_in_ms: int = 100
    fade_out_ms: int = 400
    waveform_enabled: bool = True
    waveform_fps: int = 30


@dataclass
class AudioConfig:
    sample_rate: int = 16_000
    device: str | None = None


@dataclass
class StartupConfig:
    autostart: bool = True
    preload_model: bool = False


@dataclass
class LoggingConfig:
    level: str = "info"
    rotation_days: int = 7


@dataclass
class BehaviourConfig:
    # Decimal settings: a whole number (``= 3``) is accepted as well as ``3.0``.
    silence_timeout_s: float = 60.0
    max_recording_seconds: float = 300.0
    # One shared patience for model readiness (#74): the hard timeout for the
    # Ollama Transform request AND the threshold past which transcription shows
    # the "Model Loading" pill. A single knob keeps transcription and the LLM
    # consistent. Replaces the old [transform].timeout_s (default 30 -> 120).
    model_timeout_s: float = 120.0


@dataclass
class TransformConfig:
    enabled: bool = True
    model_name: str = "gemma4:e2b"
    base_url: str = "http://localhost:11434"
    last_paste_ttl_s: int = 300


@dataclass
class TriggerWordsConfig:
    # Hand-edited (ADR-0022): written commented-out while it holds the
    # defaults, so it is discoverable but never pinned by the app.
    # False restores exact-only Trigger Word matching (#247 / ADR-0028).
    fuzzy_matching: bool = True
    # User aliases for the built-in `paste` action (#250): map a mishearing
    # your voice consistently produces straight to `paste`. Normalised like
    # Prompt File aliases on load.
    paste_aliases: tuple[str, ...] = ()


# Sections shown commented-out in a written config while they equal their
# defaults; written live once the user changes them, so an app rewrite (e.g.
# the Start-at-login toggle) never reverts a hand edit.
_COMMENTED_WHEN_DEFAULT: dict[str, str] = {
    "trigger_words": (
        "# Trigger Words tolerate small mishearings of a short command\n"
        '# ("haste" -> paste). Uncomment and set fuzzy_matching = false for\n'
        "# exact-only matching, or list words to treat as `paste` in paste_aliases\n"
        '# (e.g. paste_aliases = ["haste"]).'
    ),
}


# Empty list settings left out of a written config (so the default stays
# "unset"); _SECTION_EXAMPLES shows them commented-out instead.
_OMITTED_WHEN_EMPTY: frozenset[tuple[str, str]] = frozenset({("model", "languages")})


# Commented examples appended to a written section while *predicate(section)*
# holds: discoverable settings the app never pins.
_SECTION_EXAMPLES: dict[str, tuple[Callable[[Any], bool], str]] = {
    "model": (
        lambda model: model.language is None and not model.languages,
        "# Transcription language: English unless set. Pin another Whisper code\n"
        '# (language = "zh"), detect any language (language = "auto"), or detect\n'
        "# only among your Preferred Languages (this wins over `language`):\n"
        '# languages = ["en", "zh"]',
    ),
}


_SECTION_CLASSES: dict[str, type[Any]] = {
    "hotkey": HotkeyConfig,
    "model": ModelConfig,
    "paste": PasteConfig,
    "overlay": OverlayConfig,
    "audio": AudioConfig,
    "startup": StartupConfig,
    "logging": LoggingConfig,
    "behaviour": BehaviourConfig,
    "transform": TransformConfig,
    "trigger_words": TriggerWordsConfig,
}


@dataclass
class Config:
    """All tunable values with sensible defaults matching the PRD."""

    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    paste: PasteConfig = field(default_factory=PasteConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    startup: StartupConfig = field(default_factory=StartupConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    behaviour: BehaviourConfig = field(default_factory=BehaviourConfig)
    transform: TransformConfig = field(default_factory=TransformConfig)
    trigger_words: TriggerWordsConfig = field(default_factory=TriggerWordsConfig)


def default_config_path() -> Path:
    """The canonical config.toml location — ``~/.dictatem/config.toml``.

    One spelling shared by the daemon (which loads it on startup) and the tray
    "Open config file…" item (ADR-0022), so the two cannot drift. Not
    platform-varying: ``~/.dictatem`` is the config home on both Windows and
    macOS.
    """
    return Path.home() / ".dictatem" / "config.toml"


@dataclass(frozen=True)
class ConfigProblem:
    """One problem found while loading config.toml (see Config Load Report).

    *key* names the offending setting as ``[section].key`` (or ``[section]`` for
    a whole section), or is empty for a file-level problem such as a TOML
    syntax error. *message* is the human-readable detail that goes to the log.
    """

    key: str
    message: str


@dataclass
class ConfigLoadReport:
    """Everything that went wrong in one config load (CONTEXT.md).

    Pure data: :func:`load_config_with_report` fills it and the daemon turns a
    non-empty report into exactly one startup tray notification. *read_only*
    marks a file that could not be read or parsed (the session runs on the
    Hardware Tier defaults). Unknown keys and sections are deliberately NOT
    problems — they stay info-only in the log.
    """

    problems: list[ConfigProblem] = field(default_factory=list)
    read_only: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.problems

    @property
    def write_protected(self) -> bool:
        """True when nothing may write config.toml this session.

        Any problem — unreadable file or a per-key one — protects the file:
        the startup notice promises it was not changed, so even the
        Start-at-login toggle applies for this session only.
        """
        return not self.is_empty


# Names only the menu item, not the menu, so one string is right on Windows
# ("tray menu") and macOS ("menu-bar menu").
_OPEN_CONFIG_HINT = "Fix it via Open config file…, then Restart."

# tomllib appends "(at line N, column M)" to every TOMLDecodeError message.
_TOML_POSITION = re.compile(r"\(at (line \d+, column \d+)\)")


def config_problem_notification(report: ConfigLoadReport) -> tuple[str, str] | None:
    """The ``(title, body)`` of the one startup notification for *report*.

    ``None`` for an empty report — a valid config shows nothing. The body is
    kept to about three toast lines so Windows never truncates it (#280): it
    names the first bad key (or the syntax-error position) and the fix. The
    full per-problem detail, and the promise that config.toml was not
    changed, go to the log (see ``DaemonCore.notify_config_problems``).
    """
    if report.is_empty:
        return None
    if report.read_only:
        match = _TOML_POSITION.search(report.problems[0].message)
        what = (
            f"Syntax error at {match.group(1)}"
            if match
            else "The file couldn't be read"
        )
        return (
            "Dictatem couldn't read config.toml",
            f"{what} (using defaults). {_OPEN_CONFIG_HINT}",
        )
    keys = [p.key for p in report.problems]
    if len(keys) == 1:
        what = f"Ignored bad setting {keys[0]} (using default)."
    else:
        what = (
            f"Ignored bad settings {keys[0]} and {len(keys) - 1} more "
            "(using defaults)."
        )
    return ("Dictatem config problem", f"{what} {_OPEN_CONFIG_HINT}")


def config_problem_log_summary(report: ConfigLoadReport) -> str:
    """The full one-line log summary behind the (short) startup notification."""
    if report.read_only:
        return (
            f"config.toml could not be read ({report.problems[0].message}); "
            "running on this machine's defaults this session. "
            "config.toml was not changed."
        )
    keys = ", ".join(p.key for p in report.problems)
    return (
        f"Ignored {len(report.problems)} invalid config setting(s), using "
        f"the defaults instead: {keys}. config.toml was not changed."
    )


def load_config(path: Path, probe: HardwareProbe | None = None) -> Config:
    """Load configuration from *path*; see :func:`load_config_with_report`."""
    cfg, _report = load_config_with_report(path, probe=probe)
    return cfg


def load_config_with_report(
    path: Path, probe: HardwareProbe | None = None
) -> tuple[Config, ConfigLoadReport]:
    """Load configuration from *path*, falling back to defaults for missing/invalid values.

    If the file does not exist this is a *first run*: when a *probe* is given,
    the machine is probed once, the Hardware Tier resolved, and concrete values
    (including ``device``) are baked into the written config (see ADR-0007).
    Without a probe, a plain default config is written. An existing file is
    read unchanged and the probe is never consulted — except when it cannot be
    read or parsed: then the session runs on the Hardware Tier defaults this
    machine would get on a first run (probe and resolve), the file is never
    written, and the report is marked read-only (#238).

    Every problem (unreadable file, wrong-type or invalid value) is logged and
    collected in the returned :class:`ConfigLoadReport`.
    """
    report = ConfigLoadReport()
    if not path.exists():
        cfg = _bake_first_run_config(probe) if probe is not None else Config()
        write_config(cfg, path)
        return cfg, report

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
        logger.warning(
            "Could not read %s: %s — running on this machine's Hardware Tier "
            "defaults for this session; the file was not changed",
            path,
            exc,
        )
        report.problems.append(ConfigProblem(key="", message=str(exc)))
        report.read_only = True
        cfg = _bake_first_run_config(probe) if probe is not None else Config()
        return cfg, report

    cfg = _build_config(raw, report)
    _warn_if_transform_not_local(cfg.transform)
    return cfg, report


def is_loopback_url(url: object) -> bool:
    """True when *url* points at this machine (``localhost``, 127.0.0.0/8, ``::1``).

    Pure. Anything unparseable, host-less, or non-string is *not* loopback, so
    a malformed ``base_url`` errs on the side of a warning.
    """
    if not isinstance(url, str):
        return False
    try:
        host = urlsplit(url.strip()).hostname
    except ValueError:
        return False
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _warn_if_transform_not_local(transform: TransformConfig) -> None:
    """Warn when Trigger Words would send dictated text off this machine.

    Firing a Trigger Word POSTs the Last Paste text to ``[transform].base_url``
    (pre-launch review S-3 / #202). Warn only — never block or rewrite: a user
    may deliberately run Ollama on another box they own.
    """
    if transform.enabled and not is_loopback_url(transform.base_url):
        logger.warning(
            "[transform].base_url %r is not a local (loopback) address — "
            "Trigger Words will send your dictated text to that host. Keep it "
            "local (e.g. http://localhost:11434) unless you trust that machine.",
            transform.base_url,
        )


def _detected_as_mac(profile: HardwareProfile) -> bool:
    """Whether the first-run log should describe *profile* as a Mac.

    A Mac (Apple Silicon, or unified memory known) with no CUDA: its tier is
    decided by MLX and unified memory, not CUDA and VRAM (#233).
    """
    return not profile.cuda_available and (
        profile.apple_silicon or profile.unified_memory_mb is not None
    )


def _bake_first_run_config(probe: HardwareProbe) -> Config:
    """Probe the machine once, resolve the tier, and bake concrete values.

    Imported lazily so ``config`` stays free of hardware-package import cost
    on the common (existing-file) path. The resolver is pure logic.
    """
    from dictatem.hardware.resolver import HardwareTierResolver

    profile = probe.probe()
    resolved = HardwareTierResolver().resolve(profile)

    if _detected_as_mac(profile):
        # Name MLX and unified memory, which decide the Apple tiers.
        memory = (
            "unknown unified memory"
            if profile.unified_memory_mb is None
            else f"{profile.unified_memory_mb} MB unified memory"
        )
        detected = ("MLX usable" if profile.mlx_available else "no MLX", memory)
    else:
        vram = (
            "unknown VRAM" if profile.total_vram_mb is None else f"{profile.total_vram_mb} MB"
        )
        detected = ("CUDA" if profile.cuda_available else "no CUDA", vram)
    logger.info(
        "Detected %s, %s -> tier %s: %s/%s/%s, transform %s",
        *detected,
        resolved.tier,
        resolved.model,
        resolved.device,
        resolved.compute_type,
        resolved.transform_model,
    )

    cfg = Config()
    cfg.model.name = resolved.model
    cfg.model.device = resolved.device
    cfg.model.compute_type = resolved.compute_type
    cfg.transform.model_name = resolved.transform_model
    return cfg


def write_config(cfg: Config, path: Path) -> None:
    """Serialize *cfg* to TOML and write it to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_serialize_toml(cfg), encoding="utf-8")


def _build_config(raw: dict[str, Any], report: ConfigLoadReport) -> Config:
    """Construct a Config from a parsed TOML dict, validating as we go."""
    kwargs: dict[str, Any] = {}

    for section_name, section_data in raw.items():
        if section_name not in _SECTION_CLASSES:
            logger.info("Ignoring unknown config section: [%s]", section_name)
            continue

        if not isinstance(section_data, dict):
            logger.warning(
                "Section [%s] is not a table — using defaults", section_name
            )
            report.problems.append(ConfigProblem(
                key=f"[{section_name}]",
                message=f"[{section_name}] is not a table — using defaults",
            ))
            continue

        cls = _SECTION_CLASSES[section_name]
        default_instance = cls()
        known_fields = {f.name for f in fields(cls)}

        for key in section_data:
            if key not in known_fields:
                logger.info("Ignoring unknown key [%s].%s", section_name, key)

        section_kwargs: dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in section_data:
                continue
            default_val = getattr(default_instance, f.name)
            value, problem = _check_field(
                section_name, f.name, f.type, section_data[f.name], default_val
            )
            if problem is not None:
                logger.warning("%s", problem.message)
                report.problems.append(problem)
            section_kwargs[f.name] = value

        kwargs[section_name] = cls(**section_kwargs)

    return Config(**kwargs)


def _coerce_type(annotation: object, value: Any) -> tuple[bool, Any]:
    """Check *value* against a dataclass field's declared type.

    Returns ``(ok, coerced)``. *annotation* is the field's annotation string
    (``from __future__ import annotations``). ``bool`` is rejected where an
    ``int`` belongs even though Python treats it as one; an ``int`` is accepted
    (as a float) where a ``float`` belongs; a tuple field takes a TOML array of
    its element type.
    """
    if annotation == "bool":
        return isinstance(value, bool), value
    if annotation == "int":
        return isinstance(value, int) and not isinstance(value, bool), value
    if annotation == "float":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return True, float(value)
        return False, value
    if annotation in ("str", "str | None"):
        return isinstance(value, str), value
    if annotation == "tuple[str, ...]":
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            return True, tuple(value)
        return False, value
    msg = f"No config type check for annotation {annotation!r}"
    raise TypeError(msg)


def _check_field(
    section: str, key: str, annotation: object, value: Any, default: Any
) -> tuple[Any, ConfigProblem | None]:
    """Return ``(value, None)`` if valid, else ``(default, problem)``."""
    name = f"[{section}].{key}"
    ok, value = _coerce_type(annotation, value)
    if not ok:
        return default, ConfigProblem(
            key=name,
            message=(
                f"Wrong type for {name}: {value!r} (expected {annotation}) — "
                f"using default {default!r}"
            ),
        )
    if not _value_is_valid(section, key, value):
        return default, ConfigProblem(
            key=name,
            message=f"Invalid value for {name}: {value!r} — using default {default!r}",
        )
    normalise = _FIELD_NORMALISERS.get(section, {}).get(key)
    if normalise is not None:
        value = normalise(value)
    return value, None


def _value_is_valid(section: str, key: str, value: Any) -> bool:
    """Range/enum checks on a value already known to have the right type."""
    if key in _POSITIVE_INT_FIELDS.get(section, set()) and value <= 0:
        return False
    if section == "audio" and key == "sample_rate":
        # Fixed (F-12): the transcriber and the duration maths assume 16 kHz,
        # so any other rate would silently produce garbage.
        return value == SAMPLE_RATE_HZ
    if section == "hotkey" and key == "modifiers":
        return bool(value) and all(n in VALID_MODIFIER_NAMES for n in value)
    if section == "overlay" and key == "position":
        return value in VALID_OVERLAY_POSITIONS
    if section == "logging" and key == "level":
        return value.lower() in VALID_LOG_LEVELS
    if section == "model" and key == "language":
        return is_valid_language_setting(value)
    if section == "model" and key == "languages":
        return all(is_valid_language_code(v) for v in value)
    return True


def _serialize_toml(cfg: Config) -> str:
    """Produce a minimal TOML string from *cfg*."""
    lines: list[str] = []
    for section_name in _SECTION_CLASSES:
        section_obj = getattr(cfg, section_name)
        note = _COMMENTED_WHEN_DEFAULT.get(section_name)
        commented = note is not None and section_obj == type(section_obj)()
        prefix = "# " if commented else ""
        if note is not None:
            lines.append(note)
        lines.append(f"{prefix}[{section_name}]")
        for f in fields(type(section_obj)):
            value = getattr(section_obj, f.name)
            if value is None:
                continue
            if (section_name, f.name) in _OMITTED_WHEN_EMPTY and not value:
                continue
            lines.append(f"{prefix}{f.name} = {_toml_value(value)}")
        example = _SECTION_EXAMPLES.get(section_name)
        if example is not None and example[0](section_obj):
            lines.append(example[1])
        lines.append("")
    return "\n".join(lines)


def _toml_value(value: Any) -> str:
    """Format a Python value as a TOML literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        # Whole-number floats are written as integers ("60", not "60.0") so a
        # fresh config reads as it always has; float fields accept ints on read.
        return str(int(value))
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, (list, tuple)):
        inner = ", ".join(_toml_value(v) for v in value)
        return f"[{inner}]"
    msg = f"Unsupported TOML value type: {type(value)}"
    raise TypeError(msg)
