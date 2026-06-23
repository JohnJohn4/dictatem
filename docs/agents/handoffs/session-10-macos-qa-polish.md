# Handoff — Session 10: macOS QA & polish

**You are the next agent in the roadmap.** This doc onboards you to one session.
It does not replace the issues or ADRs — it tells you where you are, what your
**(unusual)** role is, what to do, and **how to hand off** when you're done.

## How the roadmap works (read this first)

1. **`docs/agents/roadmap.md` is ground truth.** Read it now, top to bottom. Its
   **▶ Current Session Prompt** should already point you here.
2. The roadmap defines the **working principles**, the **session list**, the
   **Definition of Done**, and the **handoff protocol**. Operate inside that frame
   — don't re-plan the backlog.
3. The backlog lives in GitHub Issues (`JohnJohn4/dictatem`, via `gh`). Read each
   issue and the named ADR before coding/QA: **#121** (ADR-0020), **#95**
   (ADR-0014, #57), **#94** (the v0.4.0 macOS runbook), **#93** (paste diagnose).
4. When you finish, run the **handoff protocol**: append a ledger entry, rewrite
   the Current Session Prompt, and update the QA handoff file with results.

## ⚠️ Your role this session — READ TWICE: REMOTE, PROXY macOS QA

This session is **not** a normal AFK session, and **not** a normal manual-QA
session. The macOS verification is done by a **third person on a real Mac who you
will never directly reach.** The wiring is:

```
  YOU (agent)              THE USER (on Windows)            THE MAC TESTER
  ───────────              ─────────────────────            ──────────────
  • write code on Windows  • runs you in this session       • physically holds
  • write EXACT, copy-      • relays your command blocks       the Mac
    pasteable command         to the tester                  • runs the relayed
    blocks for the Mac      • pastes the tester's output       commands verbatim
  • interpret the returned    + observations back to you     • reports what they
    logs + observations                                        SAW + pastes logs
```

**What this means for you, concretely:**

- **You are on Windows.** You **cannot** run, build, install, or observe the macOS
  app. The PyObjC native adapters (`mac_hook`, `mac_clipboard`, `mac_keystroke`,
  `mac_foreground`, `mac_tcc`, `macapp.activation`) **do not import on Windows** —
  do not try to run them. Your machine-checkable surface is **pure modules + their
  unit tests + `ruff` + `pyright`**, plus **CI's `macos-latest` legs** (which prove
  the PyObjC import + arch resolve). Lean on CI as your macOS smoke test.
- **Every macOS action goes through a relay.** When you need something done on the
  Mac, emit a **single self-contained, copy-pasteable command block** (no
  placeholders the tester has to guess) with a one-line "**what to look for**"
  caption. The user pastes it to the tester; the tester runs it and sends back the
  output. Keep blocks small and sequential — one observable step at a time — so a
  failure is localised.
- **Logs are necessary but NOT sufficient.** #93 is the cautionary tale: the
  pipeline logged a complete, clean `Paste: sent` on dictations whose text **never
  landed on screen**. So for any paste/landing/UI check, the **tester's eyes are
  the source of truth** — you must ask "did the text actually appear in the
  field?", not just read the log. **Never mark a macOS item PASS without the
  tester's explicit confirmation of the observable behaviour.** (Roadmap guardrail:
  *don't claim manual QA passed without a human running it on the device.*)
- **You drive the QA file, the tester ticks it.** The relay-ready checklist lives
  in [`docs/agents/qa-handoffs/08-s10-macos-qa.md`](../qa-handoffs/08-s10-macos-qa.md).
  Read it — it has the command blocks and the per-item "Expect". As results come
  back, record them there (PASS/FAIL + evidence) and on the issues.

## macOS launch quirks you MUST encode in every command block (do not regress)

These bite testers who treat the Mac like a normal app. Bake them into the blocks
you send:

- **Launch is via launchd ONLY.** Manual relaunch =
  `launchctl kickstart -k gui/$(id -u)/com.dictatem.daemon`.
  **Not** Spotlight / the `.app` (suppresses the tray icon) and **not** a bare
  terminal `dictatem` (kills hotkey/paste).
- **The TCC entry is labelled `python3.12`, not "Dictatem"** (the signed-bundle fix
  is the separate S11 / #91 grill). Tell the tester to look for `python3.12` in
  System Settings → Privacy & Security → Accessibility / Input Monitoring.
- **Grants take effect after a relaunch.** A freshly-granted permission needs the
  daemon kickstarted again.
- **Hotkey is ⌘+⌥ (Cmd+Opt)** on macOS; capture logs from the daemon's log file
  (the QA file's "Capture logs" block has the exact path/command).

## Where the project is (what landed before you)

- **S1–S9 done, all QA passed.** #126 vocabulary QA passed 2026-06-23 — **no
  carried-over QA remains** entering S10.
- **CI is real and green** (`windows-latest` + `macos-latest` × py3.11–3.13: ruff +
  pyright + pytest + native-import-safety). Your PRs are gated by it; keep it green.
  The `macos-latest` legs are your only automated macOS signal — watch them.
- **#118 (pure mouse classifier) shipped** (PR #133). The `HotkeyClassifier`
  already carries `Key.MOUSE_4 / MOUSE_5 / MOUSE_MIDDLE` + the conditional-
  suppression decision. **#121 is the missing macOS native tap only — reuse the
  classifier; do not re-implement Tap/Hold or suppression logic.**
- **S6 shipped the Windows mouse hook** (`hotkey/win32_mouse_keymap.py` pure +
  `hotkey/wh_mouse_ll.py` live). #121 is the **macOS mirror** of that shape.
- **macOS permission UX (#57) already shipped** (`permissions/mapper.py`,
  `qt_dialog.py`, `mac_tcc.py`) — #95 **extends** it, doesn't start it.

Nothing above is yours to redo. If you spot a contradiction with an ADR, surface
it (per `docs/agents/domain.md`) rather than silently overriding.

## Session 10 scope (4 issues) — heterogeneous; this is an **L** (may span sessions)

The four issues are very different shapes. **Spend the scarce Mac window on the
device-bound work that needs no new code first**, and write the code-first issues
in parallel on Windows so their Mac verification can follow.

| # | Issue | Shape | Code (Windows) | Needs Mac for | Label |
|---|---|---|---|---|---|
| **#94** | macOS QA runbook | **Pure manual QA, no code** | — | the whole checklist | `needs-triage` |
| **#93** | paste-not-landing | **Diagnose / characterize** | maybe a settle-delay/retry | repro right after relaunch | `needs-triage` |
| **#121** | macOS mouse hook | **Code + Mac-QA tail** | pure `mac_mouse_keymap.py` + tests; extend `mac_hook.py` | physical mouse-button click | `ready-for-agent` |
| **#95** | first-run onboarding | **Code + Mac-QA tail** | mapper logic, dialog copy, re-prompt throttle (pure-testable) | fresh-install behaviour, dialog copy | `needs-triage` |

> **Labels:** only #121 is `ready-for-agent`; #94/#95/#93 are `needs-triage` but
> are specced enough to action (read their bodies). Don't block on the label —
> treat **#94 as the QA spine** for the Mac session. If you want them re-labelled,
> ask the user.

### Recommended order for a Mac-session-tonight

1. **#94 runbook FIRST** — it needs zero new code, so it uses the Mac window
   immediately. Walk the tester through Checklist D–G + single-instance (see the QA
   file). This both closes #94 and **re-proves the platform** before you trust it
   for #121/#95.
2. **#93 watch in parallel** — have the tester do several dictations into a
   **browser web input right after a `kickstart -k`** and report whether the first
   few land; capture logs. If it reproduces, you have characterization for a fix
   (small settle-delay or read-back+retry before the first `CGEventPost`).
3. **#121** — write the pure `mac_mouse_keymap.py` (buttonNumber **2→MIDDLE,
   3→MOUSE_4, 4→MOUSE_5**, others→`None`) + unit tests on Windows, mirroring
   `win32_mouse_keymap.py`; extend `mac_hook.py`'s `CGEventTap` to also tap
   `otherMouseDown`/`otherMouseUp` and feed the classifier with suppression. Get CI
   green, then relay a physical-click QA block.
4. **#95** — simplify `qt_dialog.py` / `mapper.py` copy (action-first, one
   "takes effect after relaunch" line, keep the deep-link button); add
   **re-prompt-on-use** (hotkey fired without Input Monitoring, or paste without
   Accessibility → surface the guided dialog, **throttled** so it doesn't nag);
   the install.sh final message should say setup isn't done until the menu-bar icon
   + prompts appear. Keep the gating/throttle decision **pure + unit-tested**; thin
   Cocoa wiring. Mac-QA the fresh-install flow + copy.

**Architecture seam (preserve it):** native-code→`Key` maps, permission mappers,
re-prompt throttle gates are **pure + unit-tested**; only the `CGEventTap` /
Cocoa / TCC plumbing is manual-QA. Don't put decision logic in the adapters.

**Scope honesty:** four issues in one night with one remote Mac is a lot. It is
**fine** to land #94 (+ #93 characterization) tonight and carry #121/#95 (or just
their Mac-verification tail) as a follow-up — **export/keep their QA in the QA file
and never claim their Mac QA passed if the tester didn't run it.**

## Definition of Done (this session)

- For each issue worked: acceptance criteria met; pure logic unit-tested;
  `pytest` + `pyright` + `ruff` green locally **and CI green** (incl. `macos-latest`
  legs) on the PR; `/code-review` run on the diff.
- **macOS behavioural QA confirmed by the Mac tester** (observable result, not just
  logs) and recorded in `qa-handoffs/08-s10-macos-qa.md` + on the issue — or
  explicitly left **pending** with the QA file showing what's still owed. **Never
  silently skip or claim-pass.**
- Docs/ADRs/CONTEXT.md updated where behaviour/vocabulary changed.
- Branch per issue; PR to `main`. Roadmap **ledger** appended + **Current Session
  Prompt** rewritten for the next agent.

## Post-S10 sequencing — how to hand off when you're done

Run the roadmap's **Handoff protocol**. **Lead the next prompt with a
recommendation.** After S10 the only remaining numbered session is **S11 —
signing decision grill (#91)** (pay for Developer-ID + notarization vs. accept the
`python3.12` TCC label) — a **decisions-needed** grill that **needs the user's
spend call** ($99/yr). Confirm availability before picking. **Parked** (no build
without a fresh go-ahead): #72, #80, #129, #130 (speech-helper spike — use
`prototype`), #131.
