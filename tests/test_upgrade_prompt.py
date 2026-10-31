"""Tests for the pure per-platform update path + prompt content (#193).

Phase 1 of #193: macOS surfaces an available update with a copyable, pinned
``install.sh`` one-liner — nothing auto-executes — while Windows keeps its
in-app ``install.ps1`` re-run. The platform decision and every string the
prompt shows are pure, so they are pinned here on any OS.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dictatem.upgrade.core import GITHUB_REPO, install_one_liner_url
from dictatem.upgrade.prompt import (
    COMMAND_COPIED_NOTIFICATION,
    UPDATING_DOCS_URL,
    UpdateMode,
    install_sh_command,
    install_sh_url,
    manual_update_prompt,
    update_mode_for,
)

_README = Path(__file__).resolve().parents[1] / "README.md"


class TestUpdateMode:
    def test_windows_keeps_the_in_app_upgrade(self) -> None:
        assert update_mode_for("win32") is UpdateMode.IN_APP

    def test_macos_is_manual(self) -> None:
        assert update_mode_for("darwin") is UpdateMode.MANUAL

    @pytest.mark.parametrize("platform", ["linux", "freebsd14", "cygwin", ""])
    def test_everything_else_is_unsupported(self, platform: str) -> None:
        assert update_mode_for(platform) is UpdateMode.UNSUPPORTED


class TestInstallShCommand:
    def test_url_is_pinned_to_the_tag(self) -> None:
        assert install_sh_url("v0.7.0") == (
            f"https://raw.githubusercontent.com/{GITHUB_REPO}/v0.7.0/install.sh"
        )

    def test_url_mirrors_the_windows_one_liner_shape(self) -> None:
        assert install_sh_url("v0.7.0") == install_one_liner_url("v0.7.0").replace(
            "install.ps1", "install.sh"
        )

    def test_command_is_the_readme_curl_pipe_sh_form(self) -> None:
        assert install_sh_command("v0.7.0") == (
            f"curl -fsSL https://raw.githubusercontent.com/{GITHUB_REPO}/v0.7.0/"
            "install.sh | sh"
        )

    def test_command_matches_the_readme_macos_one_liner(self) -> None:
        # The prompt must hand out exactly the documented command, just at the
        # newer tag — so derive the README's one-liner and compare shapes.
        readme = _README.read_text(encoding="utf-8")
        match = re.search(
            r"curl -fsSL https://raw\.githubusercontent\.com/\S+/(v[\d.]+)/install\.sh \| sh",
            readme,
        )
        assert match is not None, "README lost its macOS install one-liner"
        assert install_sh_command(match.group(1)) == match.group(0)


class TestManualUpdatePrompt:
    def test_title_names_the_new_version(self) -> None:
        assert manual_update_prompt("0.6.4", "v0.7.0").title == (
            "Dictatem v0.7.0 is available"
        )

    def test_text_names_the_installed_version(self) -> None:
        assert "You have v0.6.4." in manual_update_prompt("0.6.4", "v0.7.0").text

    def test_unreadable_current_version_is_not_rendered_as_v(self) -> None:
        text = manual_update_prompt("", "v0.7.0").text
        assert "You have this version." in text
        assert "You have v." not in text

    def test_carries_the_pinned_command_to_copy(self) -> None:
        prompt = manual_update_prompt("0.6.4", "v0.7.0")
        assert prompt.command == install_sh_command("v0.7.0")
        assert prompt.accept_label == "Copy Update Command"

    def test_tells_the_user_to_run_it_themselves(self) -> None:
        # Nothing auto-executes on macOS (#193 acceptance criterion) — the copy
        # must say the user runs it, in Terminal.
        text = manual_update_prompt("0.6.4", "v0.7.0").text
        assert "Terminal" in text
        assert "copy" in text.lower()

    def test_reassures_that_grants_carry_over(self) -> None:
        assert "permissions carry over" in manual_update_prompt("0.6.4", "v0.7.0").text

    def test_links_the_readme_updating_section(self) -> None:
        assert manual_update_prompt("0.6.4", "v0.7.0").docs_url == UPDATING_DOCS_URL
        assert f"https://github.com/{GITHUB_REPO}#updating" == UPDATING_DOCS_URL

    def test_readme_has_the_updating_anchor(self) -> None:
        assert "\n## Updating\n" in _README.read_text(encoding="utf-8").replace(
            "\r\n", "\n"
        )


class TestCopiedNotification:
    def test_points_at_terminal(self) -> None:
        title, body = COMMAND_COPIED_NOTIFICATION
        assert title
        assert "Terminal" in body
