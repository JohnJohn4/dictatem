"""Configuration defaults for Dictatem."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    """All tunable values with sensible defaults matching the PRD."""

    # [hotkey]
    hotkey_modifiers: tuple[str, ...] = ("ctrl", "win")
    tap_threshold_ms: int = 200

    # [model]
    model_name: str = "large-v3-turbo"
    compute_type: str = "float16"
    language: str | None = None
    vad_filter: bool = True
    idle_unload_minutes: int = 30
    min_transcription_chars: int = 3

    # [paste]
    trailing_space: bool = True
    strip_newlines: bool = True
    clipboard_retry_attempts: int = 5
    clipboard_retry_delay_ms: int = 10

    # [overlay]
    overlay_position: str = "bottom-right"
    overlay_fade_in_ms: int = 100
    overlay_fade_out_ms: int = 400
    overlay_waveform_enabled: bool = True
    overlay_waveform_fps: int = 30

    # [audio]
    sample_rate: int = 16_000
    audio_device: str | None = None

    # [startup]
    autostart: bool = True

    # [logging]
    log_level: str = "info"
    log_rotation_days: int = 7

    # [behaviour]
    silence_timeout_s: int = 60
