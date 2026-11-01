"""Self-diagnosing paste log line (#269) — pure snapshot + formatter.

The Windows keystroke adapter gathers an :class:`InjectionSnapshot` at every
regular paste and Trigger Fire; :func:`format_injection_diagnostics` turns it
into ONE log line. It carries window/input state only — never dictated text,
never clipboard contents (privacy: #194).

Fields that could not be read are ``None`` and print as ``?``, so a partially
failed gather still yields a useful line.
"""

from __future__ import annotations

from dataclasses import dataclass

# Keys whose state the line reports, in print order (Windows virtual-key codes).
DIAGNOSTIC_VKS: tuple[tuple[str, int], ...] = (
    ("alt", 0x12),  # VK_MENU
    ("lwin", 0x5B),  # VK_LWIN
    ("rwin", 0x5C),  # VK_RWIN
    ("ctrl", 0x11),  # VK_CONTROL
    ("shift", 0x10),  # VK_SHIFT
    ("v", 0x56),  # VK_V
)

# GUITHREADINFO.flags bits (winuser.h).
_GUI_FLAG_NAMES: tuple[tuple[int, str], ...] = (
    (0x01, "caretblinking"),
    (0x02, "inmovesize"),
    (0x04, "inmenumode"),
    (0x08, "systemmenumode"),
    (0x10, "popupmenumode"),
)


def keys_down(is_down: dict[int, bool]) -> tuple[str, ...]:
    """Names of the :data:`DIAGNOSTIC_VKS` reported down, in print order."""
    return tuple(name for name, vk in DIAGNOSTIC_VKS if is_down.get(vk, False))


@dataclass(frozen=True)
class InjectionSnapshot:
    """Window and input state around one injection. No dictated text."""

    kind: str  # "paste" (clipboard + Ctrl+V) or "trigger-fire" (typed)
    target_hwnd: int
    foreground_after_hwnd: int | None  # GetForegroundWindow right after SendInput
    gui_flags: int | None  # target GUI thread's GetGUIThreadInfo flags
    focus_class: str | None  # class of that thread's focus window ("" = none)
    thread_keys: tuple[str, ...] | None  # target thread key state (down keys)
    thread_keys_delay_ms: int  # how long after SendInput the thread state was read
    async_keys: tuple[str, ...] | None  # GetAsyncKeyState (down keys)
    since_modifier_up_ms: int | None  # last modifier (combo) key-up -> now
    replay_within_1s: bool  # hook swallowed + replayed a key-up in the last 1 s
    sends: tuple[tuple[int, int], ...]  # (dispatched, requested) per SendInput
    settle_ms: int = 0  # pre-injection settle wait (0 = none needed)


def _hwnd(value: int) -> str:
    return f"0x{value:X}"


def _keys(keys: tuple[str, ...] | None) -> str:
    if keys is None:
        return "?"
    return "+".join(keys) if keys else "none"


def _gui_flags(flags: int | None) -> str:
    if flags is None:
        return "?"
    names = [name for bit, name in _GUI_FLAG_NAMES if flags & bit]
    return f"0x{flags:X}" + (f"[{','.join(names)}]" if names else "")


def _foreground(snap: InjectionSnapshot) -> str:
    fg = snap.foreground_after_hwnd
    if fg is None:
        return "?"
    if fg == snap.target_hwnd:
        return "yes"
    return f"no({_hwnd(fg)})"


def _sends(sends: tuple[tuple[int, int], ...]) -> str:
    if not sends:
        return "none"
    return ",".join(f"{sent}/{wanted}" for sent, wanted in sends)


def format_injection_diagnostics(snap: InjectionSnapshot) -> str:
    """One ``key=value`` line describing *snap* (stable field order)."""
    focus = "?" if snap.focus_class is None else (snap.focus_class or "none")
    since = "?" if snap.since_modifier_up_ms is None else str(snap.since_modifier_up_ms)
    return (
        f"Paste diag [{snap.kind}]: target={_hwnd(snap.target_hwnd)}"
        f" fg_after={_foreground(snap)}"
        f" gui_flags={_gui_flags(snap.gui_flags)}"
        f" focus={focus}"
        f" thread_keys(+{snap.thread_keys_delay_ms}ms)={_keys(snap.thread_keys)}"
        f" async_keys={_keys(snap.async_keys)}"
        f" since_mod_up_ms={since}"
        f" replay_1s={'yes' if snap.replay_within_1s else 'no'}"
        f" settle_ms={snap.settle_ms}"
        f" sendinput={_sends(snap.sends)}"
    )
