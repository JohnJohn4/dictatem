"""Microphone listing, matching and the tray's Microphone submenu (pure logic)."""

from __future__ import annotations

from typing import Any

from dictatem.audio.input_devices import (
    DeviceChoice,
    choose_input_device,
    input_device_names,
    microphone_menu_entries,
)

MME, WASAPI = 0, 1

# PortAudio-style list: each physical device appears once per host API.
DEVICES: list[dict[str, Any]] = [
    {"name": "Microsoft Sound Mapper - Input", "hostapi": MME, "max_input_channels": 2},
    {"name": "Microphone (Realtek(R) Audio)", "hostapi": MME, "max_input_channels": 2},
    {"name": "Headset (Jabra Evolve2 65)", "hostapi": MME, "max_input_channels": 1},
    {"name": "Speakers (Realtek(R) Audio)", "hostapi": MME, "max_input_channels": 0},
    {"name": "Microphone (Realtek(R) Audio)", "hostapi": WASAPI, "max_input_channels": 2},
    {"name": "Headset (Jabra Evolve2 65)", "hostapi": WASAPI, "max_input_channels": 1},
]


def test_lists_inputs_on_the_default_host_api_only() -> None:
    # The Sound Mapper alias is the System default entry, so it's hidden.
    assert input_device_names(DEVICES, MME) == [
        "Microphone (Realtek(R) Audio)",
        "Headset (Jabra Evolve2 65)",
    ]


TRUNCATED: list[dict[str, Any]] = [
    # MME cuts names at 31 characters; WASAPI has the full name.
    {"name": "Microphone Array (Realtek(R) Au", "hostapi": MME, "max_input_channels": 2},
    {"name": "Microphone Array (Realtek(R) Audio)", "hostapi": WASAPI, "max_input_channels": 2},
]


def test_menu_shows_the_full_name_for_an_mme_truncated_device() -> None:
    assert input_device_names(TRUNCATED, MME) == ["Microphone Array (Realtek(R) Audio)"]


def test_full_name_choice_opens_the_truncated_mme_device() -> None:
    choice = choose_input_device(TRUNCATED, "Microphone Array (Realtek(R) Audio)", MME)
    assert choice == DeviceChoice(0)


def test_default_spec_opens_the_system_default() -> None:
    for spec in (None, "", "default", "Default"):
        assert choose_input_device(DEVICES, spec, MME) == DeviceChoice(None)


def test_name_substring_prefers_the_default_host_api() -> None:
    assert choose_input_device(DEVICES, "jabra", MME) == DeviceChoice(2)


def test_unplugged_device_falls_back_to_the_system_default() -> None:
    # A saved choice that isn't connected must not fail the dictation.
    assert choose_input_device(DEVICES, "Blue Yeti", MME) == DeviceChoice(None, fell_back=True)


def test_index_spec() -> None:
    assert choose_input_device(DEVICES, "1", MME) == DeviceChoice(1)
    # An output-only or out-of-range index falls back.
    assert choose_input_device(DEVICES, "3", MME) == DeviceChoice(None, fell_back=True)
    assert choose_input_device(DEVICES, "99", MME) == DeviceChoice(None, fell_back=True)


def test_menu_checks_system_default_when_nothing_is_chosen() -> None:
    entries = microphone_menu_entries(["Mic A", "Headset B"], None)
    assert [(e.label, e.value, e.checked) for e in entries] == [
        ("System default", None, True),
        ("Mic A", "Mic A", False),
        ("Headset B", "Headset B", False),
    ]


def test_menu_checks_the_chosen_device_by_name_or_substring() -> None:
    assert [e.checked for e in microphone_menu_entries(["Mic A", "Headset B"], "headset")] == [
        False,
        False,
        True,
    ]


def test_menu_shows_a_disconnected_choice_greyed_out() -> None:
    entries = microphone_menu_entries(["Mic A"], "Headset B")
    last = entries[-1]
    assert last.label == "Headset B (not connected)"
    assert last.checked is True
    assert last.enabled is False
    assert not entries[0].checked
