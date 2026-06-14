# Dictation is never lost — clutter-proof clipboard + "paste" recovery

> Relates to [ADR-0004](0004-trigger-fire-types-via-sendinput-not-clipboard.md)
> (Trigger Fire types via `SendInput`; **regular dictation pastes via clipboard +
> Ctrl+V**) and the [Last Paste](../../CONTEXT.md#last-paste) safety rails.
>
> **Amended 2026-06-14.** The original draft of this ADR claimed *"regular
> dictation and Trigger Fire never touch the clipboard"* and planned a no-target
> auto-dump to the clipboard (#124) plus a deferred paste-last hotkey (#128).
> Both the premise and the plan were wrong or abandoned: regular dictation **does**
> paste via clipboard + Ctrl+V (see ADR-0004, which was always correct), and
> recovery is now delivered by an in-memory buffer + a built-in `paste` Trigger
> Word. This file records the corrected, shipped design.

Wispr Flow, when it cannot paste into a focused field, preserves the dictation
and offers a "Paste Last Transcript" recovery. The competitor scan surfaced the
underlying want: a dictation should **never be silently lost** when there is
nowhere to type it, and recovering it should **not pollute the clipboard**. This
ADR records how Dictatem honours both wants without per-app focus detection.

## Decision

Regular dictation pastes by placing the transcribed text on the **clipboard**
and sending **Ctrl+V** — the typed `SendInput` path is Trigger Fire only
(ADR-0004). Two properties make that clean and safe:

1. **Clutter-proof clipboard write.** Every clipboard write Dictatem makes on the
   dictation path — the transient dictation write *and* the save/restore of the
   user's original — carries the Windows exclusion markers
   `CanIncludeInClipboardHistory` and `CanUploadToCloudClipboard` (both DWORD `0`).
   Ctrl+V still pastes normally, but the transient write and the restore are
   invisible to Win+V **history** and never sync to the **cloud clipboard**.
   Without the markers both writes land in Win+V — the dictation text *plus* a
   duplicate of the original — which is the three-entry clutter this amendment
   fixes. The markers are set on `win32_clipboard.Win32ClipboardIO`'s `set_text`
   and `restore`, which do not set them today.

2. **Never lost via an in-memory buffer + voice recovery.** Dictatem retains the
   [Most-recent dictation](../../CONTEXT.md#most-recent-dictation) — the exact
   payload of the last regular dictation — in daemon memory, kept across pastes
   and even when the dictation landed nowhere. It is recoverable two ways,
   neither needing editable-focus detection:
   - the **`paste`** [Trigger Word](../../CONTEXT.md#trigger-word) — a built-in
     action word (not an LLM [Transform](../../CONTEXT.md#transform)) that
     re-pastes the Most-recent dictation into the current foreground. It works
     **regardless of whether the Transform feature is enabled**, and even when
     there is no [Last Paste](../../CONTEXT.md#last-paste) (recovery is exactly
     that case). Its re-paste lands in a real window and *does* then become the
     new Last Paste;
   - an on-demand **"Copy last dictation"** [Tray Icon](../../CONTEXT.md#tray-icon)
     item — the last-resort copy when saying "paste" isn't convenient.

Because the text is always in the buffer, a dictation that lands nowhere is never
lost: focus where it should have gone and say "paste" (or use the tray copy).
Dictatem deliberately does **not** detect whether the focused control is editable
— pasting blind is what lets it work in every app without per-app knowledge — so
there is **no** automatic "it didn't land" notice; the buffer + `paste` recovery
*is* the guarantee.

## Considered options

- **Detection-based auto-fallback.** Detect editable focus (e.g. UI Automation
  "is this a text control?") before pasting; auto-copy when it is not. Closest to
  Wispr's behaviour, but UI Automation is unreliable across Electron, games, and
  custom controls — it would reintroduce the per-app failure surface that blind
  paste exists to avoid, and silently mis-fire. Rejected.
- **No-target auto-dump to the clipboard + Overlay Pill notice (#124).** Detect
  the cheaply-known "no foreground window" case, dump the text to the clipboard,
  and flash a pill notice. Rejected (was previously planned): the Most-recent
  dictation buffer already guarantees never-lost *without* writing to the
  clipboard, the common failure ("focused, but not a text field") is undetectable
  anyway, and the dump replaces the user's active clipboard. Superseded by the
  buffer + `paste` word.
- **Paste-last hotkey (#128).** A second, focus-preserving binding
  (e.g. Shift+Alt+Z on Windows / Cmd+Ctrl+V on macOS) that re-pastes the buffer.
  Rejected after pricing it against the code: a chord with a letter key needs
  (a) letter identities the curated modifier+mouse combo vocabulary does not
  carry (ADR-0020), and (b) **synchronous keystroke suppression in the native
  hooks** — the Windows `WH_KEYBOARD_LL` adapter is enqueue-only and suppresses
  nothing today, so the bound key would leak into the focused app (Alt+Z is the
  Nvidia overlay shortcut). The `paste` Trigger Word delivers identical recovery
  with **zero** new binding and **no** native-suppression work, and a lone "paste"
  is never something a user would dictate. Rejected.
- **Always-also-copy every dictation** (save/restore to avoid clobbering). Never
  loses text and needs no detection. The original draft rejected this as
  "reversing ADR-0004's clipboard avoidance" — that reason is void, since regular
  dictation already uses the clipboard. The real reason to reject: it would
  replace the user's clipboard on the *success* path too, whereas the buffer
  recovers text without touching the clipboard except on the explicit `paste` /
  copy actions. Rejected.
- **A Scratchpad window** (editable, with a Copy button) for the no-target case.
  An editable surface fights Dictatem's thin/minimal philosophy and the read-only
  in-app stance (ADR-0019); the buffer + `paste` already deliver "your text is
  safe". Rejected.

## Consequences

- Regular dictation's clipboard juggling is clutter-proof (history- and
  cloud-excluded) on **both** the transient set and the restore — this is what
  makes "your clipboard stays put and stays clean" actually true. Win32 adapter
  change; Windows manual-QA. macOS has no Win+V/cloud-clipboard equivalent, so the
  markers are a Windows concern; the mac adapter is unaffected.
- The [Most-recent dictation](../../CONTEXT.md#most-recent-dictation) is a
  distinct notion from [Last Paste](../../CONTEXT.md#last-paste): it exists even
  when nothing landed and no `target_id` was captured, and it does not by itself
  arm [Trigger Words](../../CONTEXT.md#trigger-word). Implementations must hold it
  independently of a successful paste (today `_last_text` is cleared after every
  paste — it must not be the buffer).
- The `paste` Trigger Word is a **built-in action**, not a Transform: it has no
  Prompt File, runs regardless of `[transform].enabled` (so trigger detection
  must no longer be gated solely on the Transform feature), and is matched by the
  same normalisation as other Trigger Words — punctuation stripped, lowercased, so
  "Paste.", "paste?", "PASTE" all fire while multi-word "paste this" does not. A
  user Prompt File aliased `paste` is shadowed by the built-in (warn on load). An
  empty buffer makes "paste" a no-op with the existing error flash — it never
  falls back to typing the literal word.
- The explicit **"Copy last dictation"** tray item is a *normal* copy (it appears
  in Win+V), because the user deliberately asked for the text on their clipboard;
  clutter-proofing targets only the *automatic* dictation juggling. (Flagged: flip
  it to a clutter-proof write if that proves surprising.)
- There is no automatic no-target notice (the dropped #124). The
  [Usage Guide](../../CONTEXT.md#usage-guide) must frame "say 'paste' / Copy last
  dictation" as the recovery, rather than implying a failed paste is auto-detected.
