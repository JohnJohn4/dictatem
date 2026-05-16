"""Configuration defaults and TOML loading for Dictatem."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field, fields
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

VALID_OVERLAY_POSITIONS = frozenset({
    "top-left", "top-right", "bottom-left", "bottom-right",
})

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
    "behaviour": {"silence_timeout_s", "max_recording_seconds"},
    "transform": {"timeout_s", "last_paste_ttl_s"},
}


@dataclass
class HotkeyConfig:
    modifiers: tuple[str, ...] = ("win", "alt")
    tap_threshold_ms: int = 200


@dataclass
class ModelConfig:
    name: str = "large-v3-turbo"
    compute_type: str = "float16"
    language: str | None = None
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
    silence_timeout_s: int = 60
    max_recording_seconds: int = 300


@dataclass
class TransformConfig:
    enabled: bool = True
    model_name: str = "gemma4:e4b"
    base_url: str = "http://localhost:11434"
    timeout_s: int = 30
    last_paste_ttl_s: int = 300


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


def load_config(path: Path) -> Config:
    """Load configuration from *path*, falling back to defaults for missing/invalid values.

    If the file does not exist, a default config is written to *path* and returned.
    """
    if not path.exists():
        cfg = Config()
        write_config(cfg, path)
        return cfg

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        logger.warning("Failed to parse %s: %s — using defaults", path, exc)
        return Config()

    return _build_config(raw)


def write_config(cfg: Config, path: Path) -> None:
    """Serialize *cfg* to TOML and write it to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_serialize_toml(cfg), encoding="utf-8")


def _build_config(raw: dict[str, Any]) -> Config:
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
            value = section_data[f.name]
            if f.name == "modifiers" and isinstance(value, list):
                value = tuple(value)
            default_val = getattr(default_instance, f.name)
            section_kwargs[f.name] = _validate_field(
                section_name, f.name, value, default_val
            )

        kwargs[section_name] = cls(**section_kwargs)

    return Config(**kwargs)


def _validate_field(
    section: str, key: str, value: Any, default: Any
) -> Any:
    """Return *value* if valid, otherwise log a warning and return *default*."""
    positive_fields = _POSITIVE_INT_FIELDS.get(section, set())
    invalid = (
        (key in positive_fields and isinstance(value, int) and value <= 0)
        or (section == "overlay" and key == "position"
            and value not in VALID_OVERLAY_POSITIONS)
        or (section == "logging" and key == "level"
            and (not isinstance(value, str) or value.lower() not in VALID_LOG_LEVELS))
    )

    if invalid:
        logger.warning(
            "Invalid value for [%s].%s: %r — using default %r",
            section, key, value, default,
        )
        return default

    return value


def _serialize_toml(cfg: Config) -> str:
    """Produce a minimal TOML string from *cfg*."""
    lines: list[str] = []
    for section_name in _SECTION_CLASSES:
        section_obj = getattr(cfg, section_name)
        lines.append(f"[{section_name}]")
        for f in fields(type(section_obj)):
            value = getattr(section_obj, f.name)
            if value is None:
                continue
            lines.append(f"{f.name} = {_toml_value(value)}")
        lines.append("")
    return "\n".join(lines)


def _toml_value(value: Any) -> str:
    """Format a Python value as a TOML literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, (list, tuple)):
        inner = ", ".join(_toml_value(v) for v in value)
        return f"[{inner}]"
    msg = f"Unsupported TOML value type: {type(value)}"
    raise TypeError(msg)
