"""The Windows-native tray menu plan: tidy separators, numbering, labels."""

from __future__ import annotations

from dictatem.tray.native_menu import NativeItem, native_label, number_actions, tidy

SEP = NativeItem("separator")


def _a(text: str) -> NativeItem:
    return NativeItem("action", text)


def test_tidy_drops_leading_trailing_and_doubled_separators() -> None:
    plan = tidy([SEP, _a("Copy"), SEP, SEP, _a("Unload"), SEP])
    assert [i.kind for i in plan] == ["action", "separator", "action"]


def test_tidy_applies_inside_submenus() -> None:
    sub = NativeItem("submenu", "Microphone", children=(SEP, _a("System default"), SEP))
    (tidied,) = tidy([sub])
    assert [i.text for i in tidied.children] == ["System default"]


def test_actions_are_numbered_from_one_depth_first_in_menu_order() -> None:
    mic = NativeItem("submenu", "Microphone", children=(_a("System default"), _a("Jabra")))
    plan = tidy([_a("Copy"), SEP, mic, _a("Quit")])
    ids = number_actions(plan)
    assert {k: v.text for k, v in ids.items()} == {
        1: "Copy",
        2: "System default",
        3: "Jabra",
        4: "Quit",
    }


def test_ampersands_are_escaped_for_windows() -> None:
    assert native_label("Headset (R&D mic)") == "Headset (R&&D mic)"
