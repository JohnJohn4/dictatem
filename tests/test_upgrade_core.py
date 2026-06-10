"""Tests for the pure upgrade-decision core (#100).

The tray "Check for Updates" action resolves the latest GitHub release tag and
decides whether to upgrade. The version parse/compare, the release-JSON parse,
the decision, and the install-one-liner URL are all pure logic with no network
or process I/O, so they are fully unit-tested here. The GitHub fetch and the
detached upgrade spawn are thin adapters verified by manual QA on Windows.
"""

from __future__ import annotations

from dictatem.upgrade.core import (
    GITHUB_REPO,
    UpgradeKind,
    decide_upgrade,
    install_one_liner_url,
    is_newer,
    parse_latest_tag,
    parse_version,
)


class TestParseVersion:
    def test_strips_leading_v(self) -> None:
        assert parse_version("v0.4.0") == (0, 4, 0)

    def test_plain_dotted(self) -> None:
        assert parse_version("0.4.0") == (0, 4, 0)

    def test_two_component(self) -> None:
        assert parse_version("v1.2") == (1, 2)

    def test_non_numeric_is_none(self) -> None:
        assert parse_version("garbage") is None

    def test_prerelease_suffix_is_none(self) -> None:
        # Our releases are plain vX.Y.Z; an unexpected suffix reads as unknown
        # rather than silently comparing a partial version.
        assert parse_version("v0.4.0-rc1") is None

    def test_empty_is_none(self) -> None:
        assert parse_version("") is None

    def test_unicode_digit_is_none_not_a_crash(self) -> None:
        # str.isdigit() is True for '²' but int('²') raises — must stay None.
        assert parse_version("v1.²") is None


class TestIsNewer:
    def test_higher_minor_is_newer(self) -> None:
        assert is_newer("v0.5.0", "0.4.0") is True

    def test_equal_is_not_newer(self) -> None:
        assert is_newer("v0.4.0", "0.4.0") is False

    def test_lower_is_not_newer(self) -> None:
        assert is_newer("v0.3.0", "0.4.0") is False

    def test_higher_patch_is_newer(self) -> None:
        assert is_newer("v0.4.1", "0.4.0") is True

    def test_higher_major_beats_lower_minor(self) -> None:
        assert is_newer("v1.0.0", "0.9.9") is True

    def test_zero_pads_shorter_version(self) -> None:
        assert is_newer("v0.4", "0.4.0") is False

    def test_unknown_current_is_never_newer(self) -> None:
        # Never claim an upgrade when we can't read our own version.
        assert is_newer("v0.5.0", "") is False

    def test_unknown_candidate_is_never_newer(self) -> None:
        assert is_newer("nightly", "0.4.0") is False


class TestParseLatestTag:
    def test_extracts_tag_name(self) -> None:
        body = '{"tag_name": "v0.5.0", "name": "Release 0.5.0"}'
        assert parse_latest_tag(body) == "v0.5.0"

    def test_missing_tag_name_is_none(self) -> None:
        assert parse_latest_tag('{"name": "x"}') is None

    def test_invalid_json_is_none(self) -> None:
        assert parse_latest_tag("not json") is None

    def test_empty_is_none(self) -> None:
        assert parse_latest_tag("") is None

    def test_non_string_tag_is_none(self) -> None:
        assert parse_latest_tag('{"tag_name": 123}') is None


class TestDecideUpgrade:
    def test_newer_release_is_upgrade_available(self) -> None:
        decision = decide_upgrade("0.4.0", "v0.5.0")
        assert decision.kind is UpgradeKind.UPGRADE_AVAILABLE
        assert decision.tag == "v0.5.0"
        assert "v0.5.0" in decision.message

    def test_same_version_is_up_to_date(self) -> None:
        decision = decide_upgrade("0.4.0", "v0.4.0")
        assert decision.kind is UpgradeKind.UP_TO_DATE
        assert decision.tag is None
        assert "0.4.0" in decision.message

    def test_older_latest_is_up_to_date(self) -> None:
        # A dev build ahead of the latest release: nothing to do.
        decision = decide_upgrade("0.5.0", "v0.4.0")
        assert decision.kind is UpgradeKind.UP_TO_DATE

    def test_missing_latest_tag_is_unknown(self) -> None:
        decision = decide_upgrade("0.4.0", None)
        assert decision.kind is UpgradeKind.UNKNOWN
        assert decision.tag is None
        assert decision.message  # non-empty guidance

    def test_unparseable_latest_tag_is_unknown(self) -> None:
        decision = decide_upgrade("0.4.0", "nightly")
        assert decision.kind is UpgradeKind.UNKNOWN

    def test_unreadable_current_version_is_unknown_not_up_to_date(self) -> None:
        # Editable/dev checkout: version("dictatem") raises -> current is "".
        # Must not falsely report "up to date (v)" and swallow a real upgrade.
        decision = decide_upgrade("", "v0.5.0")
        assert decision.kind is UpgradeKind.UNKNOWN
        assert "(v)" not in decision.message


class TestInstallOneLinerUrl:
    def test_points_at_raw_github_install_ps1_for_tag(self) -> None:
        url = install_one_liner_url("v0.5.0")
        assert url == (
            "https://raw.githubusercontent.com/JohnJohn4/dictatem/v0.5.0/install.ps1"
        )

    def test_uses_the_repo_constant(self) -> None:
        assert GITHUB_REPO == "JohnJohn4/dictatem"
        assert GITHUB_REPO in install_one_liner_url("v9.9.9")
