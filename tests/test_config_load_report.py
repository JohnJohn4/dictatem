"""Config type validation and the Config Load Report (#238, F-11/F-12).

Every key is type-checked against its dataclass declaration; a wrong value
falls back to that key's default and lands in the report. A corrupt file runs
on the probe-resolved Hardware Tier defaults and is never written.
"""

from __future__ import annotations

import dataclasses
from textwrap import dedent
from typing import TYPE_CHECKING

from dictatem.config import (
    Config,
    ConfigLoadReport,
    ConfigProblem,
    config_problem_notification,
    load_config_with_report,
)
from dictatem.types import HardwareProfile
from tests.fakes import FakeHardwareProbe

if TYPE_CHECKING:
    from pathlib import Path


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(dedent(body), encoding="utf-8")
    return path


class TestTypeValidation:
    def test_string_for_int_falls_back_and_is_reported(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [hotkey]
            tap_threshold_ms = "fast"
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.hotkey.tap_threshold_ms == 200
        assert [p.key for p in report.problems] == ["[hotkey].tap_threshold_ms"]

    def test_bool_for_int_is_rejected(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [model]
            idle_unload_minutes = true
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.model.idle_unload_minutes == 30
        assert [p.key for p in report.problems] == ["[model].idle_unload_minutes"]

    def test_whole_number_for_float_is_accepted(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [behaviour]
            silence_timeout_s = 3
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.behaviour.silence_timeout_s == 3.0
        assert isinstance(cfg.behaviour.silence_timeout_s, float)
        assert report.is_empty

    def test_decimal_for_float_is_accepted(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [behaviour]
            silence_timeout_s = 2.5
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.behaviour.silence_timeout_s == 2.5
        assert report.is_empty

    def test_wrong_type_for_float_falls_back(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [behaviour]
            silence_timeout_s = "soon"
            max_recording_seconds = false
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.behaviour.silence_timeout_s == 60.0
        assert cfg.behaviour.max_recording_seconds == 300.0
        assert [p.key for p in report.problems] == [
            "[behaviour].silence_timeout_s",
            "[behaviour].max_recording_seconds",
        ]

    def test_wrong_type_for_bool_falls_back(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [startup]
            autostart = 1
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.startup.autostart is True
        assert [p.key for p in report.problems] == ["[startup].autostart"]

    def test_wrong_type_for_string_falls_back(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [model]
            name = 42
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.model.name == "large-v3-turbo"
        assert [p.key for p in report.problems] == ["[model].name"]

    def test_optional_string_accepts_string(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [model]
            language = "en"
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.model.language == "en"
        assert report.is_empty

    def test_wrong_type_for_optional_string_falls_back(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [audio]
            device = 3
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.audio.device is None
        assert [p.key for p in report.problems] == ["[audio].device"]

    def test_wrong_type_for_tuple_of_names_falls_back(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [hotkey]
            modifiers = "win+alt"
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.hotkey.modifiers == ("win", "alt")
        assert [p.key for p in report.problems] == ["[hotkey].modifiers"]

    def test_tuple_with_non_string_element_falls_back(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [hotkey]
            modifiers = ["ctrl", 4]
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.hotkey.modifiers == ("win", "alt")
        assert [p.key for p in report.problems] == ["[hotkey].modifiers"]

    def test_invalid_value_of_right_type_is_reported(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [overlay]
            position = "middle"
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.overlay.position == "bottom-right"
        assert [p.key for p in report.problems] == ["[overlay].position"]

    def test_valid_config_gives_empty_report(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [hotkey]
            modifiers = ["ctrl", "mouse4"]
            tap_threshold_ms = 150
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.hotkey.modifiers == ("ctrl", "mouse4")
        assert report.is_empty
        assert report.read_only is False

    def test_unknown_keys_and_sections_are_not_problems(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [hotkey]
            frobnicate = 1

            [mystery]
            x = 1
        """)
        _cfg, report = load_config_with_report(path)
        assert report.is_empty


CPU_PROFILE = HardwareProfile(cuda_available=False, total_vram_mb=None)

CORRUPT = '[hotkey]\ntap_threshold_ms = 150\n[model\nname = "small"\n'


class TestCorruptFile:
    def test_report_carries_parser_message_and_position(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(CORRUPT, encoding="utf-8")
        _cfg, report = load_config_with_report(path, probe=FakeHardwareProbe(CPU_PROFILE))
        assert report.read_only is True
        assert len(report.problems) == 1
        problem = report.problems[0]
        assert problem.key == ""
        assert "line 3" in problem.message

    def test_runs_on_probe_resolved_tier_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(CORRUPT, encoding="utf-8")
        probe = FakeHardwareProbe(CPU_PROFILE)
        cfg, _report = load_config_with_report(path, probe=probe)
        # The CPU tier, not the untiered large-v3-turbo/cuda/float16 defaults.
        assert (cfg.model.name, cfg.model.device, cfg.model.compute_type) == (
            "base", "cpu", "int8",
        )
        assert probe.probe_count == 1

    def test_file_bytes_unchanged_after_load(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        original = CORRUPT.encode("utf-8")
        path.write_bytes(original)
        load_config_with_report(path, probe=FakeHardwareProbe(CPU_PROFILE))
        assert path.read_bytes() == original

    def test_undecodable_file_is_read_only(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_bytes(b"\xff\xfe[hotkey]\x00")
        _cfg, report = load_config_with_report(path)
        assert report.read_only is True
        assert path.read_bytes() == b"\xff\xfe[hotkey]\x00"


class TestSampleRate:
    def test_non_16000_is_reported_and_ignored(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [audio]
            sample_rate = 44100
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.audio.sample_rate == 16_000
        assert [p.key for p in report.problems] == ["[audio].sample_rate"]

    def test_16000_is_fine(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [audio]
            sample_rate = 16000
        """)
        cfg, report = load_config_with_report(path)
        assert cfg.audio.sample_rate == 16_000
        assert report.is_empty


# A Windows toast shows roughly three lines of body text; the v0.7.0 message
# was cut off at ~165 characters (#280). Keep every variant well inside that.
_TOAST_BODY_MAX = 130

# The longest real key name, so the budget holds for the worst case.
_LONGEST_KEY = max(
    (
        f"[{section.name}].{f.name}"
        for section in dataclasses.fields(Config)
        for f in dataclasses.fields(section.default_factory())  # type: ignore[misc]
    ),
    key=len,
)


def _body(report: ConfigLoadReport) -> str:
    note = config_problem_notification(report)
    assert note is not None
    return note[1]


class TestNotification:
    """The one startup tray notification a non-empty report turns into."""

    def test_empty_report_gives_no_notification(self) -> None:
        assert config_problem_notification(ConfigLoadReport()) is None

    def test_one_bad_value_names_the_key_and_the_fix(self) -> None:
        report = ConfigLoadReport(problems=[
            ConfigProblem("[hotkey].tap_threshold_ms", "Wrong type ..."),
        ])
        note = config_problem_notification(report)
        assert note is not None
        title, body = note
        assert "config" in title.lower()
        assert body == (
            "Ignored bad setting [hotkey].tap_threshold_ms (using default). "
            "Fix it via Open config file…, then Restart."
        )

    def test_several_bad_values_name_the_first_and_count_the_rest(self) -> None:
        report = ConfigLoadReport(problems=[
            ConfigProblem("[hotkey].tap_threshold_ms", "Wrong type ..."),
            ConfigProblem("[audio].sample_rate", "Invalid value ..."),
            ConfigProblem("[overlay].position", "Invalid value ..."),
        ])
        assert _body(report) == (
            "Ignored bad settings [hotkey].tap_threshold_ms and 2 more "
            "(using defaults). Fix it via Open config file…, then Restart."
        )

    def test_unparseable_file_gives_the_position(self) -> None:
        report = ConfigLoadReport(
            problems=[ConfigProblem(
                "",
                "Expected ']' at the end of a table declaration "
                "(at line 3, column 7)",
            )],
            read_only=True,
        )
        note = config_problem_notification(report)
        assert note is not None
        title, body = note
        assert title == "Dictatem couldn't read config.toml"
        assert body == (
            "Syntax error at line 3, column 7 (using defaults). "
            "Fix it via Open config file…, then Restart."
        )

    def test_unreadable_file_without_a_position(self) -> None:
        report = ConfigLoadReport(
            problems=[ConfigProblem(
                "",
                "[Errno 13] Permission denied: "
                r"'C:\Users\someone\.dictatem\config.toml'",
            )],
            read_only=True,
        )
        assert _body(report) == (
            "The file couldn't be read (using defaults). "
            "Fix it via Open config file…, then Restart."
        )

    def test_wording_is_platform_neutral(self) -> None:
        # Windows says "tray menu", macOS "menu-bar menu"; the toast names
        # only the menu item, so one string is right on both.
        body = _body(ConfigLoadReport(problems=[ConfigProblem("[a].b", "x")]))
        assert "tray" not in body and "menu-bar" not in body

    def test_every_variant_fits_a_toast(self) -> None:
        reports = [
            ConfigLoadReport(problems=[ConfigProblem(_LONGEST_KEY, "x")]),
            ConfigLoadReport(
                problems=[ConfigProblem(_LONGEST_KEY, "x")] * 25
            ),
            ConfigLoadReport(
                problems=[ConfigProblem(
                    "",
                    "Expected ']' at the end of a table declaration "
                    "(at line 12345, column 678)",
                )],
                read_only=True,
            ),
            ConfigLoadReport(
                problems=[ConfigProblem("", "x" * 500)], read_only=True
            ),
        ]
        for report in reports:
            body = _body(report)
            assert len(body) <= _TOAST_BODY_MAX, body
            assert body.endswith("then Restart.")
