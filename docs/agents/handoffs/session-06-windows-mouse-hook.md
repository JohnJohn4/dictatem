# Handoff — Session 6: Windows mouse hook

**You are the next agent in the roadmap.** This doc onboards you to one session.
It does not replace the issue or ADR — it tells you where you are, what to do, and
**how to hand off when you're done** (post-S6 sequencing at the bottom).

## How the roadmap works (read this first)

1. **`docs/agents/roadmap.md` is ground truth.** Read it now, top to bottom. Its
   **▶ Current Session Prompt** should already point you here.
2. The roadmap defines the **working principles**, the **session list (S1–S10)**,
   the **Definition of Done**, and the **handoff protocol**. Operate inside that
   frame — don't re-plan the backlog.
3. The backlog lives in GitHub Issues (`JohnJohn4/dictatem`, via `gh`). Read the
   issue (#120) and **ADR-0020** before coding.
4. When you finish, run the **handoff protocol**: append a ledger entry, rewrite
   the Current Session Prompt, and flag/export the manual QA.

## Your role this session

Autonomous AFK implementer **with a Windows manual-QA tail** (you can run it — you
are on Windows). The user reviews/merges the PR. Skills: `run`/`verify` and
`diagnose` for the live hook, `code-review` before the PR. Branch per issue; PR to
`main`.

## Where the project is (what landed before you)

- **S4 (CI + install hardening)** — PRs **#156** (#81 import-safety) and **#157**
  (#90 x64 CPython pin) may still be **open awaiting merge** when you start, or
  freshly merged. They're infra/install only and **file-disjoint from S6** — don't
  redo them. If still open, you can branch S6 off `main` regardless.
- **CI is real and green** (`windows-latest` + `macos-latest` × py3.11–3.13: ruff
  + pyright + pytest + import-safety). Your PR will be gated by it; keep it green.
- **S2 shipped the pure mouse classifier core (#118, merged in PR #133).** The
  `HotkeyClassifier` already knows the mouse identities and the conditional-
  suppression decision. **This session is the missing native adapter only.**

Nothing above is yours to redo. If you spot a contradiction with an ADR, surface
it (per `docs/agents/domain.md`) rather than silently overriding.

## Session 6 scope (1 issue) — read #120 + ADR-0020 first

**#120 — Windows `WH_MOUSE_LL` adapter feeding the S2 classifier.** A user sets
`[hotkey].modifiers = ["mouse4"]` (standalone) or `["ctrl", "mouse4"]` (combined)
and triggers dictation by pressing that button, with the button's normal OS action
suppressed **only** while it completes the combo.

| Piece | What | First look |
|---|---|---|
| **Pure keymap** | A native-code→`Key` map for the mouse buttons (Windows `WM_XBUTTONDOWN/UP` with X1/X2 in the high word of `mouseData`; middle = `WM_MBUTTONDOWN/UP`) → `MOUSE_4` / `MOUSE_5` / `MOUSE_MIDDLE`. **Pure + unit-tested**, sitting beside `hotkey/win32_keymap.py`. | `hotkey/win32_keymap.py`, `hotkey/classifier.py` (the `Key` enum + `_MODIFIER_MAP` already carry `MOUSE_4/5/MIDDLE` from #118 — confirm the exact names) |
| **Live hook** | A `WH_MOUSE_LL` adapter that mirrors the **keyboard** hook's shape: install `SetWindowsHookEx`, translate events via the pure keymap, feed the classifier on the hook thread, and **apply the classifier's per-event `HookDecision`** (`SUPPRESS` → return non-zero from the hook proc to swallow the event; `PASS_THROUGH` → `CallNextHookEx`). Manual-QA. | `hotkey/wh_keyboard_ll.py` (copy its threading + enqueue-to-main-thread + guard pattern), `daemon.py` (where the keyboard hook is installed/torn down — wire the mouse hook in alongside it) |

**Architecture seam (preserve it):** the native-code→`Key` decision and the
suppress/pass-through decision are **pure and unit-tested**; only the
`SetWindowsHookEx` plumbing is manual-QA. Don't put any Tap/Hold or suppression
*logic* in the hook — it already lives in the classifier (ADR-0020).

**Suggested order:** (1) pure keymap + tests; (2) the live hook mirroring
`wh_keyboard_ll.py`; (3) wire both hooks into the daemon so one classifier sees
keyboard + mouse events; (4) `/code-review`; (5) Windows QA.

## Definition of Done (this session)

- #120's acceptance criteria met: a configured mouse button (standalone or
  combined) triggers dictation with correct Tap/Hold; the button's normal action
  is suppressed **only** when the press completes the combo (bare presses pass
  through for combined combos); the native-code→`Key` map is pure + unit-tested;
  **no regression to the keyboard hotkey path**.
- `pytest` + `pyright` + `ruff` green locally **and CI green** on the PR.
- `/code-review` run on the diff.
- Docs: update the **Usage Guide** mouse-button section if behaviour wording
  changes; note the graceful degrade for click-only mice (ADR-0020 consequence).
- **Manual-QA (you can run it on this Windows box):** physically click
  **mouse4 / mouse5 / middle** — standalone arms dictation and the button's normal
  action is suppressed; combined (`["ctrl","mouse4"]`) only suppresses with the
  modifier held; a bare press still does browser-back. If you can't QA now, **export
  a QA handoff** (`docs/agents/qa-handoffs/<NN>-windows-mouse-hook.md`) — never
  claim QA passed without running it.
- Roadmap **ledger** appended + **Current Session Prompt** rewritten.

## Post-S6 sequencing — how to hand off when you're done

Run the roadmap's **Handoff protocol**. **Lead the next prompt with a
recommendation.** The strong candidates after S6:

1. **S7 — Cold-start latency design grill (#101).** Code-free, parallel-safe, the
   **deepest real-user complaint** (the long first-transcribe wait + paste
   misfiring as focus drifts during the load). Produces a short ADR + spun-out
   issues; decides #97's approach and frames #96 / #67. Use `grill-with-docs` /
   `prototype`. Unblocks **S8** (#96, #97). **Recommended next** if not already
   done in parallel.
2. **S8 — Overlay & focus UX (#96, #97).** Needs S7's decision first.

The **macOS track** (S9: #93/#94/#95/#121 incl. the macOS mouse hook #121, which
reuses this session's pure classifier path; S10 signing #91) waits for a real-Mac
QA day — export QA handoffs; **never claim Mac QA without the device.** **Parked**
(no build without a fresh go-ahead): #72, #80, #129, #130 (speech-helper spike —
use `prototype`), #131.

Carried-over QA to surface if it lands: **#126** vocabulary recognition-lift
(`docs/agents/qa-handoffs/02-vocabulary-recognition-qa.md`).
