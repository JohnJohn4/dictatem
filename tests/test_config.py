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
        assert Config().hotkey_modifiers == ("ctrl", "win")

    def test_tap_threshold_ms(self) -> None:
        assert Config().tap_threshold_ms == 200

    # [model]
    def test_model_name(self) -> None:
        assert Config().model_name == "large-v3-turbo"

    def test_compute_type(self) -> None:
        assert Config().compute_type == "float16"

    def test_language_auto(self) -> None:
        assert Config().language is None

    def test_vad_filter(self) -> None:
        assert Config().vad_filter is True

    def test_idle_unload_minutes(self) -> None:
        assert Config().idle_unload_minutes == 30

    def test_min_transcription_chars(self) -> None:
        assert Config().min_transcription_chars == 3

    # [paste]
    def test_trailing_space(self) -> None:
        assert Config().trailing_space is True

    def test_strip_newlines(self) -> None:
        assert Config().strip_newlines is True

    def test_clipboard_retry_attempts(self) -> None:
        assert Config().clipboard_retry_attempts == 5

    def test_clipboard_retry_delay_ms(self) -> None:
        assert Config().clipboard_retry_delay_ms == 10

    # [overlay]
    def test_overlay_position(self) -> None:
        assert Config().overlay_position == "bottom-right"

    def test_overlay_fade_in_ms(self) -> None:
        assert Config().overlay_fade_in_ms == 100

    def test_overlay_fade_out_ms(self) -> None:
        assert Config().overlay_fade_out_ms == 400

    def test_overlay_waveform_enabled(self) -> None:
        assert Config().overlay_waveform_enabled is True

    def test_overlay_waveform_fps(self) -> None:
        assert Config().overlay_waveform_fps == 30

    # [audio]
    def test_sample_rate(self) -> None:
        assert Config().sample_rate == 16_000

    def test_audio_device(self) -> None:
        assert Config().audio_device is None

    # [startup]
    def test_autostart(self) -> None:
        assert Config().autostart is True

    # [logging]
    def test_log_level(self) -> None:
        assert Config().log_level == "info"

    def test_log_rotation_days(self) -> None:
        assert Config().log_rotation_days == 7

    # [behaviour]
    def test_silence_timeout_s(self) -> None:
        assert Config().silence_timeout_s == 60
