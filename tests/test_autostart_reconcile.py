"""Tests for the pure autostart reconcile decision (#55 / ADR-0012).

The daemon owns autostart and reconciles the OS entry to
``config.startup.autostart`` on launch. The *decision* — given the desired flag
and whether the OS entry currently exists, what action to take — is pure logic
with no registry or I/O, mirroring ``HardwareTierResolver.reconcile``. Every one
of the four (desired × currently_enabled) combinations is covered.
"""

from __future__ import annotations

from pathlib import Path

from dictatem.autostart.reconcile import (
    AutostartAction,
    apply_autostart,
    reconcile_autostart,
    run_uninstall,
)
from tests.fakes import FakeAutostartRegistrar


class TestReconcileEnables:
    """Flag on, OS entry missing -> register it."""

    def test_desired_on_currently_off_enables(self) -> None:
        action = reconcile_autostart(desired=True, currently_enabled=False)
        assert action is AutostartAction.ENABLE


class TestReconcileDisables:
    """Flag off, OS entry present -> remove it."""

    def test_desired_off_currently_on_disables(self) -> None:
        action = reconcile_autostart(desired=False, currently_enabled=True)
        assert action is AutostartAction.DISABLE


class TestReconcileNoops:
    """Already in the desired state -> do nothing (idempotent)."""

    def test_desired_on_currently_on_noops(self) -> None:
        action = reconcile_autostart(desired=True, currently_enabled=True)
        assert action is AutostartAction.NOOP

    def test_desired_off_currently_off_noops(self) -> None:
        action = reconcile_autostart(desired=False, currently_enabled=False)
        assert action is AutostartAction.NOOP


class TestReconcileIsPure:
    """reconcile is a total function over the four boolean combinations."""

    def test_all_combinations_have_a_defined_action(self) -> None:
        expected = {
            (True, False): AutostartAction.ENABLE,
            (True, True): AutostartAction.NOOP,
            (False, True): AutostartAction.DISABLE,
            (False, False): AutostartAction.NOOP,
        }
        for (desired, currently_enabled), action in expected.items():
            assert (
                reconcile_autostart(
                    desired=desired, currently_enabled=currently_enabled
                )
                is action
            )


class TestApplyAutostart:
    """apply_autostart reads the registrar, runs the pure decision, applies it.

    This is the thin glue the daemon calls on launch (and the tray toggle calls
    after flipping the flag). It returns the action it took so callers can log.
    """

    def test_enables_when_flag_on_and_entry_missing(self) -> None:
        reg = FakeAutostartRegistrar(enabled=False)
        action = apply_autostart(desired=True, registrar=reg)
        assert action is AutostartAction.ENABLE
        assert reg.is_enabled() is True
        assert reg.enable_calls == 1

    def test_disables_when_flag_off_and_entry_present(self) -> None:
        reg = FakeAutostartRegistrar(enabled=True)
        action = apply_autostart(desired=False, registrar=reg)
        assert action is AutostartAction.DISABLE
        assert reg.is_enabled() is False
        assert reg.disable_calls == 1

    def test_noop_when_flag_on_and_entry_present(self) -> None:
        reg = FakeAutostartRegistrar(enabled=True)
        action = apply_autostart(desired=True, registrar=reg)
        assert action is AutostartAction.NOOP
        assert reg.enable_calls == 0
        assert reg.disable_calls == 0

    def test_noop_when_flag_off_and_entry_missing(self) -> None:
        reg = FakeAutostartRegistrar(enabled=False)
        action = apply_autostart(desired=False, registrar=reg)
        assert action is AutostartAction.NOOP
        assert reg.enable_calls == 0
        assert reg.disable_calls == 0


class TestRunUninstall:
    """`dictatem --uninstall` removes the autostart entry, then prints the
    final `uv tool uninstall dictatem` step for the user to run (ADR-0011).
    """

    def test_removes_autostart_entry(self) -> None:
        reg = FakeAutostartRegistrar(enabled=True)
        run_uninstall(registrar=reg, out=lambda _msg: None)
        assert reg.is_enabled() is False
        assert reg.disable_calls == 1

    def test_idempotent_when_entry_absent(self) -> None:
        reg = FakeAutostartRegistrar(enabled=False)
        run_uninstall(registrar=reg, out=lambda _msg: None)
        assert reg.is_enabled() is False
        # disable is always called; the registrar swallows the absent case.
        assert reg.disable_calls == 1

    def test_absent_entry_claims_nothing(self) -> None:
        # macOS builds the registrar unconditionally for uninstall, so with
        # no LaunchAgent on disk the output must not claim one was removed.
        reg = FakeAutostartRegistrar(enabled=False)
        lines: list[str] = []
        run_uninstall(registrar=reg, out=lines.append)
        joined = "\n".join(lines)
        assert "Removed" not in joined
        assert "uv tool uninstall dictatem" in joined

    def test_prints_uv_tool_uninstall_step(self) -> None:
        reg = FakeAutostartRegistrar(enabled=True)
        lines: list[str] = []
        run_uninstall(registrar=reg, out=lines.append)
        joined = "\n".join(lines)
        assert "uv tool uninstall dictatem" in joined

    def test_none_registrar_prints_guidance_only(self) -> None:
        # Platforms with no autostart registrar (a macOS install whose .app
        # was never generated): there is no entry to remove, so claiming
        # "Removed" would be false.
        lines: list[str] = []
        run_uninstall(registrar=None, out=lines.append)
        joined = "\n".join(lines)
        assert "Removed" not in joined
        assert "uv tool uninstall dictatem" in joined


class TestRunUninstallRemovesAppBundle:
    """The macOS extra step (#61): the .app goes away before the uv tool —
    after `uv tool uninstall` the .app's exec shim target no longer exists."""

    def test_reports_the_removed_bundle_before_the_final_step(self) -> None:
        reg = FakeAutostartRegistrar(enabled=True)
        bundle = Path("/Users/me/Applications/Dictatem.app")
        lines: list[str] = []
        run_uninstall(
            registrar=reg, out=lines.append, remove_app_bundle=lambda: bundle
        )
        joined = "\n".join(lines)
        assert joined.index(f"Removed {bundle}.") < joined.index(
            "uv tool uninstall dictatem"
        )

    def test_absent_bundle_claims_nothing(self) -> None:
        # remove_app_bundle returns None when the .app was already gone —
        # claiming "Removed" would be false.
        lines: list[str] = []
        run_uninstall(
            registrar=None, out=lines.append, remove_app_bundle=lambda: None
        )
        joined = "\n".join(lines)
        assert "Removed" not in joined
        assert "uv tool uninstall dictatem" in joined

    def test_default_is_no_bundle_step(self) -> None:
        # Windows passes no remover; output is exactly the two-step guidance.
        reg = FakeAutostartRegistrar(enabled=True)
        lines: list[str] = []
        run_uninstall(registrar=reg, out=lines.append)
        assert "Dictatem.app" not in "\n".join(lines)
