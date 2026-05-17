# Hotkey pipeline uses `time.monotonic` end-to-end

Every timestamp that flows through the hotkey pipeline — the low-level
keyboard hook, the bridge queue, the [Tap](../../CONTEXT.md#tap) /
[Hold](../../CONTEXT.md#hold) discrimination in
`HotkeyClassifier`, and the Qt 50 ms tick that drives `HOLD_START`
detection — is `int(time.monotonic() * 1000)`. The `KBDLLHOOKSTRUCT.time`
field provided by Windows is deliberately ignored.

## Considered Options

- **Use `kb.time` (GetTickCount-derived) at the hook, `time.monotonic` at
  the Qt tick** (the original implementation). Compares two clocks whose
  epochs are not guaranteed to align. On a machine where the offset
  exceeds the 200 ms tap threshold, `classifier.tick()` computes
  `monotonic_now - kb_time_of_press` and immediately fires a spurious
  `HOLD_START`. The state machine goes `PRESSED → PTT_REC`, the user's
  quick release transitions `PTT_REC → TRANSCRIBING`, and a short or
  empty audio buffer drops back to idle — visible to the user as "the
  pill appears for a frame and disappears." See
  [#28](https://github.com/JohnJohn4/dictatem/issues/28).
- **Translate `kb.time` to a monotonic equivalent inside the classifier.**
  Requires the classifier to carry an offset and recalibrate it after
  suspend/resume or NTP correction. Adds clock-aware state to a module
  whose only purpose is pure tap/hold logic.
- **Drop `HOLD_START` detection from the tick and only discriminate
  tap-vs-hold on key release.** Loses the ability to switch the overlay
  into PTT mode while the user is still holding the keys — the visual
  feedback that the press has "armed" the recording.

`time.monotonic` end-to-end was chosen because it is the only option
that removes the mismatch by construction: the hook callback runs in a
Python thread and is free to call `time.monotonic()` itself, so the
field on `KBDLLHOOKSTRUCT` is just unused.

## Consequences

- `WHKeyboardLLHook` sets `timestamp_ms = int(time.monotonic() * 1000)`
  at the bottom of its low-level callback. `kb.vkCode`, `kb.flags`, and
  `kb.scanCode` are still read; only `kb.time` is dropped.
- `HotkeyClassifier` and the state machine's `_key_down_at` are
  unchanged: they continue to compare timestamps with subtraction, but
  both sides of every subtraction are now monotonic.
- A small additional cost per key event (one `QueryPerformanceCounter`
  call). Negligible at human keystroke rates.
- The hook callback runs on its own thread; `time.monotonic` is
  documented as thread-safe, so no synchronisation is needed.
- The convention applies only to the hotkey pipeline. The model-load
  idle timer in `TranscribeLifecycle` and the `LastPaste` TTL use their
  own clocks injected at construction time and are unaffected.
