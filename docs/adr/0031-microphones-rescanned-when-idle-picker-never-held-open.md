# Microphones are re-scanned when idle, picked in the tray, and never held open

> Windows (PortAudio/`sounddevice`) capture only. macOS captures natively
> ([ADR-0027](0027-macos-captures-audio-natively-via-avaudioengine.md)) and is
> unchanged. Shipped in v0.8.0 (#296).

Before this, PortAudio initialised at the **first hotkey press** of a session,
which froze its device list for the rest of the session:

- A headset plugged in mid-session wasn't seen until a restart.
- The first press paid PortAudio's start-up (~0.25–0.5 s) before the mic
  opened and the [Overlay Pill](../../CONTEXT.md#overlay-pill) could show.
- There was no way to choose a microphone except hand-editing `[audio] device`
  (a name substring or index).
- An unplugged configured device failed the dictation with a misleading
  "check mic permissions" message.

Measured on the work laptop, key press → pill took 1.0–1.9 s: ~0.6 s opening
the stream, ~0.3 s importing `sounddevice`. Opening the built-in Realtek array
alone takes 450–780 ms; a USB headset takes 47–62 ms.

## Decision

1. **Initialise PortAudio shortly after launch, and re-scan devices while
   idle.** Re-scans happen once after each dictation (on the daemon's idle
   tick, when no stream is open) and whenever the tray's Microphone menu
   opens. All PortAudio calls run on the GUI thread, so a re-scan can never
   race a stream opening. A re-scan never opens the microphone (the owner
   confirmed the mic-in-use indicator shows only while recording). It uses
   `sounddevice._terminate/_initialize`, a guarded private API.
2. **Tray Microphone menu.** It offers *System default* plus the default host
   API's inputs, with MME's 31-character-truncated names expanded to their
   full names and the "Sound Mapper" alias hidden. The choice is saved to
   `[audio] device`, the same way "Start at login" is saved (session-only when
   the config has problems).
3. **An unplugged choice falls back.** Dictation uses the system default
   (logged once), the menu hides the missing device and ticks *System
   default*, and the saved choice is kept, so replugging switches back
   automatically. Picking *System default* forgets it.
4. **The microphone is never held open between dictations (owner decision).**
   Pre-opening the stream would remove the ~0.5 s open time on slow devices,
   but it would keep the mic in use (privacy, and the in-use indicator) and
   could block apps that want the device. Don't reopen this.

## Consequences

- A new mic is used from the next dictation; a restart is no longer needed.
- The remaining record-start time is the device driver's open time. That's
  inherent on some built-in arrays, and WASAPI (#184) may help.
- The pill still appears only once the mic is live, so the start of speech is
  never lost.
