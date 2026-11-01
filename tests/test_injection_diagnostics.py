"""Per-injection diagnostic line (#269) — pure formatter."""

from __future__ import annotations

import dataclasses

from dictatem.paste.injection_diagnostics import (
    InjectionSnapshot,
    format_injection_diagnostics,
    keys_down,
)

_SNAP = InjectionSnapshot(
    kind="paste",
    target_hwnd=0x1A2B3C,
    foreground_after_hwnd=0x1A2B3C,
    gui_flags=0,
    focus_class="Scintilla",
    thread_keys=(),
    thread_keys_delay_ms=250,
    async_keys=(),
    since_modifier_up_ms=412,
    replay_within_1s=True,
    sends=((6, 6, 1),),
)


def test_full_line() -> None:
    assert format_injection_diagnostics(_SNAP) == (
        "Paste diag [paste]: target=0x1A2B3C fg_after=yes gui_flags=0x0"
        " focus=Scintilla thread_keys(+250ms)=none async_keys=none"
        " since_mod_up_ms=412 replay_1s=yes settle_ms=0 sendinput=6/6"
    )


def test_foreground_moved_names_the_new_window() -> None:
    line = format_injection_diagnostics(
        dataclasses.replace(_SNAP, foreground_after_hwnd=0xBEEF)
    )
    assert " fg_after=no(0xBEEF) " in line


def test_gui_flags_are_decoded() -> None:
    line = format_injection_diagnostics(dataclasses.replace(_SNAP, gui_flags=0x5))
    assert " gui_flags=0x5[caretblinking,inmenumode] " in line


def test_down_keys_are_listed() -> None:
    line = format_injection_diagnostics(
        dataclasses.replace(_SNAP, thread_keys=("alt", "lwin"), async_keys=("ctrl",))
    )
    assert " thread_keys(+250ms)=alt+lwin " in line
    assert " async_keys=ctrl " in line


def test_unreadable_fields_print_as_question_marks() -> None:
    snap = dataclasses.replace(
        _SNAP,
        foreground_after_hwnd=None,
        gui_flags=None,
        focus_class=None,
        thread_keys=None,
        async_keys=None,
        since_modifier_up_ms=None,
        replay_within_1s=False,
        sends=(),
    )
    assert format_injection_diagnostics(snap) == (
        "Paste diag [paste]: target=0x1A2B3C fg_after=? gui_flags=?"
        " focus=? thread_keys(+250ms)=? async_keys=?"
        " since_mod_up_ms=? replay_1s=no settle_ms=0 sendinput=none"
    )


def test_no_focus_window_and_multiple_sends() -> None:
    snap = dataclasses.replace(
        _SNAP,
        kind="trigger-fire",
        focus_class="",
        sends=((364, 364, 23), (186, 186, 12)),
        settle_ms=37,
    )
    line = format_injection_diagnostics(snap)
    assert line.startswith("Paste diag [trigger-fire]: ")
    assert " focus=none " in line
    assert " settle_ms=37 " in line
    assert line.endswith(" sendinput=364/364 in 23 chunks,186/186 in 12 chunks")


def test_short_phase_shows_dispatched_of_requested() -> None:
    line = format_injection_diagnostics(dataclasses.replace(_SNAP, sends=((16, 364, 2),)))
    assert line.endswith(" sendinput=16/364 in 2 chunks")


def test_keys_down_keeps_print_order() -> None:
    assert keys_down({0x56: True, 0x12: True, 0x5C: False}) == ("alt", "v")
    assert keys_down({}) == ()
