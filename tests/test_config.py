"""Tests for Config defaults matching the PRD configuration sketch."""

from __future__ import annotations

from dictatem.config import Config


class TestConfigDefaults:
    """Every default must match the corresponding PRD entry."""

    def test_constructs_without_args(self) -> None:
        cfg = Config()
        assert cfg is not None

    # [hotkey]
    def test_hotkey_modifiers(self) -> None:
        assert Config().hotkey.modifiers == ("ctrl", "win")

    def test_tap_threshold_ms(self) -> None:
        assert Config().hotkey.tap_threshold_ms == 200

    # [model]
    def test_model_name(self) -> None:
        assert Config().model.name == "large-v3-turbo"

    def test_compute_type(self) -> None:
        assert Config().model.compute_type == "float16"

    def test_language_auto(self) -> None:
        assert Config().model.language is None

    def test_vad_filter(self) -> None:
        assert Config().model.vad_filter is True

    def test_idle_unload_minutes(self) -> None:
        assert Config().model.idle_unload_minutes == 30

    def test_min_transcription_chars(self) -> None:
        assert Config().model.min_transcription_chars == 3

    # [paste]
    def test_trailing_space(self) -> None:
        assert Config().paste.trailing_space is True

    def test_strip_newlines(self) -> None:
        assert Config().paste.strip_newlines is True

    def test_clipboard_retry_attempts(self) -> None:
        assert Config().paste.clipboard_retry_attempts == 5

    def test_clipboard_retry_delay_ms(self) -> None:
        assert Config().paste.clipboard_retry_delay_ms == 10

    # [overlay]
    def test_overlay_position(self) -> None:
        assert Config().overlay.position == "bottom-right"

    def test_overlay_fade_in_ms(self) -> None:
        assert Config().overlay.fade_in_ms == 100

    def test_overlay_fade_out_ms(self) -> None:
        assert Config().overlay.fade_out_ms == 400

    def test_overlay_waveform_enabled(self) -> None:
        assert Config().overlay.waveform_enabled is True

    def test_overlay_waveform_fps(self) -> None:
        assert Config().overlay.waveform_fps == 30

    # [audio]
    def test_sample_rate(self) -> None:
        assert Config().audio.sample_rate == 16_000

    def test_audio_device(self) -> None:
        assert Config().audio.device is None

    # [startup]
    def test_autostart(self) -> None:
        assert Config().startup.autostart is True

    # [logging]
    def test_log_level(self) -> None:
        assert Config().logging.level == "info"

    def test_log_rotation_days(self) -> None:
        assert Config().logging.rotation_days == 7

    # [behaviour]
    def test_silence_timeout_s(self) -> None:
        assert Config().behaviour.silence_timeout_s == 60
