"""Tests for TOML configuration loading with validation (Slice 8)."""

from __future__ import annotations

import logging
from textwrap import dedent
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from dictatem.config import (
    AudioConfig,
    BehaviourConfig,
    Config,
    HotkeyConfig,
    LoggingConfig,
    ModelConfig,
    OverlayConfig,
    PasteConfig,
    StartupConfig,
    TransformConfig,
    load_config,
    write_config,
)


class TestConfigSubDataclasses:
    """All Config sections from the PRD are represented as sub-dataclasses."""

    def test_hotkey_section(self) -> None:
        cfg = Config()
        assert isinstance(cfg.hotkey, HotkeyConfig)
        assert cfg.hotkey.modifiers == ("win", "alt")
        assert cfg.hotkey.tap_threshold_ms == 200

    def test_model_section(self) -> None:
        cfg = Config()
        assert isinstance(cfg.model, ModelConfig)
        assert cfg.model.name == "large-v3-turbo"
        assert cfg.model.compute_type == "float16"
        assert cfg.model.language is None
        assert cfg.model.vad_filter is True
        assert cfg.model.idle_unload_minutes == 30
        assert cfg.model.min_transcription_chars == 3

    def test_paste_section(self) -> None:
        cfg = Config()
        assert isinstance(cfg.paste, PasteConfig)
        assert cfg.paste.trailing_space is True
        assert cfg.paste.strip_newlines is True
        assert cfg.paste.clipboard_retry_attempts == 5
        assert cfg.paste.clipboard_retry_delay_ms == 10

    def test_overlay_section(self) -> None:
        cfg = Config()
        assert isinstance(cfg.overlay, OverlayConfig)
        assert cfg.overlay.position == "bottom-right"
        assert cfg.overlay.fade_in_ms == 100
        assert cfg.overlay.fade_out_ms == 400
        assert cfg.overlay.waveform_enabled is True
        assert cfg.overlay.waveform_fps == 30

    def test_audio_section(self) -> None:
        cfg = Config()
        assert isinstance(cfg.audio, AudioConfig)
        assert cfg.audio.sample_rate == 16_000
        assert cfg.audio.device is None

    def test_startup_section(self) -> None:
        cfg = Config()
        assert isinstance(cfg.startup, StartupConfig)
        assert cfg.startup.autostart is True

    def test_logging_section(self) -> None:
        cfg = Config()
        assert isinstance(cfg.logging, LoggingConfig)
        assert cfg.logging.level == "info"
        assert cfg.logging.rotation_days == 7

    def test_behaviour_section(self) -> None:
        cfg = Config()
        assert isinstance(cfg.behaviour, BehaviourConfig)
        assert cfg.behaviour.silence_timeout_s == 60

    def test_transform_section(self) -> None:
        cfg = Config()
        assert isinstance(cfg.transform, TransformConfig)
        assert cfg.transform.enabled is True
        assert cfg.transform.model_name == "gemma4:e4b"
        assert cfg.transform.base_url == "http://localhost:11434"
        assert cfg.transform.timeout_s == 30
        assert cfg.transform.last_paste_ttl_s == 300


class TestLoadConfigMissingFile:
    """load_config with no file present returns defaults and writes the file."""

    def test_returns_defaults_when_file_missing(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path / "config.toml")
        assert cfg == Config()

    def test_writes_defaults_file(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        load_config(path)
        assert path.exists()
        content = path.read_text()
        assert "[hotkey]" in content
        assert "[model]" in content
        assert "[paste]" in content
        assert "[overlay]" in content
        assert "[audio]" in content
        assert "[startup]" in content
        assert "[logging]" in content
        assert "[behaviour]" in content
        assert "[transform]" in content

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "subdir" / "nested" / "config.toml"
        load_config(path)
        assert path.exists()


class TestLoadConfigPartialFile:
    """Loading a partial TOML file fills the rest from defaults."""

    def test_partial_hotkey_only(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [hotkey]
            tap_threshold_ms = 300
        """))
        cfg = load_config(path)
        assert cfg.hotkey.tap_threshold_ms == 300
        assert cfg.hotkey.modifiers == ("win", "alt")
        # All other sections should be defaults
        assert cfg.model == ModelConfig()
        assert cfg.paste == PasteConfig()
        assert cfg.overlay == OverlayConfig()
        assert cfg.audio == AudioConfig()
        assert cfg.startup == StartupConfig()
        assert cfg.logging == LoggingConfig()
        assert cfg.behaviour == BehaviourConfig()
        assert cfg.transform == TransformConfig()

    def test_partial_section_with_some_keys(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [model]
            name = "small"
            [overlay]
            position = "top-left"
        """))
        cfg = load_config(path)
        assert cfg.model.name == "small"
        assert cfg.model.compute_type == "float16"  # default
        assert cfg.overlay.position == "top-left"
        assert cfg.overlay.fade_in_ms == 100  # default


class TestLoadConfigMalformedToml:
    """Loading malformed TOML returns defaults and logs at WARNING."""

    def test_returns_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text("this is [not valid toml = = =")
        cfg = load_config(path)
        assert cfg == Config()

    def test_logs_warning(self, tmp_path: Path, caplog: logging.LogCaptureFixture) -> None:
        path = tmp_path / "config.toml"
        path.write_text("this is [not valid toml = = =")
        with caplog.at_level(logging.WARNING, logger="dictatem.config"):
            load_config(path)
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_leaves_malformed_file_in_place(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        original = "this is [not valid toml = = ="
        path.write_text(original)
        load_config(path)
        assert path.read_text() == original


class TestLoadConfigRangeValidation:
    """Invalid values fall back to default with a WARNING log."""

    def test_negative_idle_unload_minutes(
        self, tmp_path: Path, caplog: logging.LogCaptureFixture
    ) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [model]
            idle_unload_minutes = -5
        """))
        with caplog.at_level(logging.WARNING, logger="dictatem.config"):
            cfg = load_config(path)
        assert cfg.model.idle_unload_minutes == 30  # default
        assert any(
            "idle_unload_minutes" in r.message and r.levelname == "WARNING"
            for r in caplog.records
        )

    def test_negative_tap_threshold(
        self, tmp_path: Path, caplog: logging.LogCaptureFixture
    ) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [hotkey]
            tap_threshold_ms = -1
        """))
        with caplog.at_level(logging.WARNING, logger="dictatem.config"):
            cfg = load_config(path)
        assert cfg.hotkey.tap_threshold_ms == 200  # default

    def test_zero_waveform_fps(
        self, tmp_path: Path, caplog: logging.LogCaptureFixture
    ) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [overlay]
            waveform_fps = 0
        """))
        with caplog.at_level(logging.WARNING, logger="dictatem.config"):
            cfg = load_config(path)
        assert cfg.overlay.waveform_fps == 30  # default

    def test_invalid_overlay_position(
        self, tmp_path: Path, caplog: logging.LogCaptureFixture
    ) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [overlay]
            position = "middle-center"
        """))
        with caplog.at_level(logging.WARNING, logger="dictatem.config"):
            cfg = load_config(path)
        assert cfg.overlay.position == "bottom-right"  # default

    def test_invalid_log_level(
        self, tmp_path: Path, caplog: logging.LogCaptureFixture
    ) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [logging]
            level = "megaverbose"
        """))
        with caplog.at_level(logging.WARNING, logger="dictatem.config"):
            cfg = load_config(path)
        assert cfg.logging.level == "info"  # default

    def test_valid_values_not_overridden(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [model]
            idle_unload_minutes = 60
        """))
        cfg = load_config(path)
        assert cfg.model.idle_unload_minutes == 60


class TestLoadConfigUnknownKeys:
    """Unknown keys under known sections are logged at INFO and ignored."""

    def test_unknown_key_ignored(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [hotkey]
            tap_threshold_ms = 300
            future_feature = true
        """))
        cfg = load_config(path)
        assert cfg.hotkey.tap_threshold_ms == 300
        assert not hasattr(cfg.hotkey, "future_feature")

    def test_unknown_key_logged_at_info(
        self, tmp_path: Path, caplog: logging.LogCaptureFixture
    ) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [model]
            unknown_setting = 42
        """))
        with caplog.at_level(logging.INFO, logger="dictatem.config"):
            load_config(path)
        assert any(
            "unknown_setting" in r.message and r.levelname == "INFO"
            for r in caplog.records
        )

    def test_unknown_section_logged_at_info(
        self, tmp_path: Path, caplog: logging.LogCaptureFixture
    ) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [future_section]
            key = "value"
        """))
        with caplog.at_level(logging.INFO, logger="dictatem.config"):
            load_config(path)
        assert any(
            "future_section" in r.message and r.levelname == "INFO"
            for r in caplog.records
        )


class TestRoundTrip:
    """Round-trip: load → modify → write → re-load → preserved."""

    def test_round_trip_preserves_modification(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        # First load creates defaults
        cfg = load_config(path)
        assert cfg.model.idle_unload_minutes == 30

        # Modify
        cfg.model.idle_unload_minutes = 60

        # Write back
        write_config(cfg, path)

        # Re-load
        cfg2 = load_config(path)
        assert cfg2.model.idle_unload_minutes == 60
        # Other values unchanged
        assert cfg2.model.name == "large-v3-turbo"
        assert cfg2.hotkey.modifiers == ("win", "alt")

    def test_round_trip_full_config(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        cfg = load_config(path)
        write_config(cfg, path)
        cfg2 = load_config(path)
        assert cfg2 == cfg

    def test_write_then_load_custom_values(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        cfg = Config(
            hotkey=HotkeyConfig(modifiers=("alt",), tap_threshold_ms=150),
            model=ModelConfig(name="tiny", language="en"),
            audio=AudioConfig(device="Yeti"),
        )
        write_config(cfg, path)
        cfg2 = load_config(path)
        assert cfg2.hotkey.modifiers == ("alt",)
        assert cfg2.hotkey.tap_threshold_ms == 150
        assert cfg2.model.name == "tiny"
        assert cfg2.model.language == "en"
        assert cfg2.audio.device == "Yeti"


class TestWriteConfig:
    """write_config produces valid TOML output."""

    def test_writes_all_sections(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        write_config(Config(), path)
        content = path.read_text()
        for section in ["hotkey", "model", "paste", "overlay", "audio",
                        "startup", "logging", "behaviour", "transform"]:
            assert f"[{section}]" in content

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "config.toml"
        write_config(Config(), path)
        assert path.exists()

    def test_none_values_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        write_config(Config(), path)
        cfg = load_config(path)
        assert cfg.model.language is None
        assert cfg.audio.device is None


class TestTransformKillSwitch:
    """[transform].enabled is the kill switch for the Trigger Words feature."""

    def test_enabled_defaults_to_true(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path / "config.toml")
        assert cfg.transform.enabled is True

    def test_can_be_disabled(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [transform]
            enabled = false
        """))
        cfg = load_config(path)
        assert cfg.transform.enabled is False

    def test_round_trip_disabled(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        cfg = Config(transform=TransformConfig(enabled=False))
        write_config(cfg, path)
        cfg2 = load_config(path)
        assert cfg2.transform.enabled is False


class TestTransformOllamaKnobs:
    """[transform] exposes model/url/timeout/ttl knobs (#22)."""

    def test_full_section_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [transform]
            enabled = true
            model_name = "llama3.2:3b"
            base_url = "http://remote:11434"
            timeout_s = 60
            last_paste_ttl_s = 120
        """))
        cfg = load_config(path)
        assert cfg.transform.enabled is True
        assert cfg.transform.model_name == "llama3.2:3b"
        assert cfg.transform.base_url == "http://remote:11434"
        assert cfg.transform.timeout_s == 60
        assert cfg.transform.last_paste_ttl_s == 120

    def test_first_write_emits_full_section(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        load_config(path)
        content = path.read_text()
        assert "[transform]" in content
        assert "enabled" in content
        assert "model_name" in content
        assert "base_url" in content
        assert "timeout_s" in content
        assert "last_paste_ttl_s" in content

    def test_zero_timeout_falls_back_to_default(
        self, tmp_path: Path, caplog: logging.LogCaptureFixture
    ) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [transform]
            timeout_s = 0
        """))
        with caplog.at_level(logging.WARNING, logger="dictatem.config"):
            cfg = load_config(path)
        assert cfg.transform.timeout_s == 30
        assert any(
            "timeout_s" in r.message and r.levelname == "WARNING"
            for r in caplog.records
        )

    def test_negative_timeout_falls_back_to_default(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [transform]
            timeout_s = -1
        """))
        cfg = load_config(path)
        assert cfg.transform.timeout_s == 30

    def test_zero_ttl_falls_back_to_default(
        self, tmp_path: Path, caplog: logging.LogCaptureFixture
    ) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [transform]
            last_paste_ttl_s = 0
        """))
        with caplog.at_level(logging.WARNING, logger="dictatem.config"):
            cfg = load_config(path)
        assert cfg.transform.last_paste_ttl_s == 300
        assert any(
            "last_paste_ttl_s" in r.message and r.levelname == "WARNING"
            for r in caplog.records
        )

    def test_round_trip_custom_values(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        cfg = Config(transform=TransformConfig(
            enabled=False,
            model_name="qwen2.5:7b",
            base_url="http://192.168.1.10:11434",
            timeout_s=45,
            last_paste_ttl_s=600,
        ))
        write_config(cfg, path)
        cfg2 = load_config(path)
        assert cfg2.transform == cfg.transform
