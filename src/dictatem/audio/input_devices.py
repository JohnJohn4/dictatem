"""Pure microphone listing/matching for the PortAudio capture (no native imports).

PortAudio lists every physical device once per host API (MME, DirectSound,
WASAPI, WDM-KS on Windows). Capture opens streams on the *default* host API
(``device=None`` and the index we resolve both live there; MME on Windows,
which also resamples to our 16 kHz), so the Microphone menu lists only that
host API's inputs. Each device appears once, under the same name the config
stores.

The config value (``[audio] device``) is a case-insensitive name substring, an
integer index, or unset/``"default"`` for the system default. A named device
that isn't connected falls back to the system default instead of failing the
dictation; the caller logs that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def is_default_spec(spec: str | None) -> bool:
    return spec is None or spec.strip() == "" or spec.strip().lower() == "default"


# MME (Windows' default PortAudio host API) truncates device names to 31
# characters; other host APIs list the same device under its full name.
_MME_NAME_LIMIT = 31
# MME's virtual "default input" device, the same thing as our System default.
_SOUND_MAPPER_PREFIX = "microsoft sound mapper"


def _looks_truncated(name: str) -> bool:
    return len(name) >= _MME_NAME_LIMIT


def _full_name(name: str, devices: Sequence[Mapping[str, Any]]) -> str:
    """The untruncated name for an MME-truncated *name*, if another host API has it."""
    if not _looks_truncated(name):
        return name
    longer = [
        str(d.get("name", ""))
        for d in devices
        if d.get("max_input_channels", 0) > 0
        and str(d.get("name", "")).startswith(name)
        and len(str(d.get("name", ""))) > len(name)
    ]
    return max(longer, key=len) if longer else name


def input_device_names(devices: Sequence[Mapping[str, Any]], hostapi: int) -> list[str]:
    """Input-capable device names on *hostapi* for the Microphone menu.

    In PortAudio order, de-duplicated, without MME's Sound Mapper alias, and
    with MME's truncated names expanded to the full name where known.
    """
    names: list[str] = []
    for dev in devices:
        if dev.get("hostapi") != hostapi or dev.get("max_input_channels", 0) <= 0:
            continue
        name = str(dev.get("name", ""))
        if not name or name.lower().startswith(_SOUND_MAPPER_PREFIX):
            continue
        name = _full_name(name, devices)
        if name not in names:
            names.append(name)
    return names


def _name_matches(device_name: str, wanted: str) -> bool:
    """Case-insensitive substring match that also accepts an MME-truncated
    *device_name* when *wanted* is the full name it was cut from."""
    name = device_name.lower()
    return wanted in name or (_looks_truncated(name) and wanted.startswith(name))


@dataclass(frozen=True)
class DeviceChoice:
    """Which PortAudio device to open. ``index=None`` means the system default."""

    index: int | None
    # True when a specific device was configured but isn't connected, so the
    # system default is used instead.
    fell_back: bool = False


def choose_input_device(
    devices: Sequence[Mapping[str, Any]], spec: str | None, hostapi: int
) -> DeviceChoice:
    """Resolve the configured *spec* against the live device list."""
    if is_default_spec(spec):
        return DeviceChoice(None)
    assert spec is not None
    text = spec.strip()
    if text.isdigit():
        index = int(text)
        if 0 <= index < len(devices) and devices[index].get("max_input_channels", 0) > 0:
            return DeviceChoice(index)
        return DeviceChoice(None, fell_back=True)
    wanted = text.lower()
    # Prefer the default host API (where the menu's names come from), then any.
    ordered = sorted(range(len(devices)), key=lambda i: devices[i].get("hostapi") != hostapi)
    for i in ordered:
        dev = devices[i]
        name = str(dev.get("name", ""))
        if dev.get("max_input_channels", 0) > 0 and _name_matches(name, wanted):
            return DeviceChoice(i)
    return DeviceChoice(None, fell_back=True)


@dataclass(frozen=True)
class MicrophoneMenuEntry:
    label: str
    # The value to store in ``[audio] device``; None = system default.
    value: str | None
    checked: bool


def microphone_menu_entries(
    names: Sequence[str], selected: str | None
) -> list[MicrophoneMenuEntry]:
    """The tray's Microphone submenu: System default, then each connected input.

    The tick shows the microphone actually in use. When the chosen device is
    unplugged it isn't listed and System default is ticked, because that's what
    dictation falls back to. The choice itself stays saved, so plugging the
    device back in switches to it again; picking System default forgets it.
    """
    wanted = (selected or "").strip().lower()
    match: str | None = None
    if not is_default_spec(selected):
        exact = [n for n in names if n.lower() == wanted]
        partial = [n for n in names if wanted in n.lower()]
        match = (exact or partial or [None])[0]

    entries = [MicrophoneMenuEntry("System default", None, checked=match is None)]
    entries.extend(MicrophoneMenuEntry(n, n, checked=(n == match)) for n in names)
    return entries
