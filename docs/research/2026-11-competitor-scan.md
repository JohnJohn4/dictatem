# Competitor scan: dictation apps, late 2025 to Nov 2026

*Researched 2026-11-01. Sources are vendor changelogs, docs and pricing pages
where available. Third-party reviews are used only for user sentiment and are
labelled **[sentiment]**. "Accessed" dates are given for undated doc pages.
Where sources disagreed, the primary source is used and the conflict is noted.*

**The short version:** in 2026 every leading app converged on the same four
additions: **voice-editing selected text**, **saying "send" to submit**,
**searchable history**, and **mic hygiene** (no-audio warnings, faster mic start,
skipping virtual mics). The cloud apps (Wispr Flow, Aqua, Willow) also moved into
meetings, teams and MCP. The OS vendors now ship on-device LLM-cleaned dictation,
but it is gated to new hardware. Dictatem's local, private, voice-first position
is still clear of all of them. The best next moves extend the Trigger Word system
rather than adding new surfaces.

---

## 1. Top 5 build recommendations

| # | Build | Effort | Related issue |
|---|---|---|---|
| 1 | Trigger Words act on the **current selection** | M | #131 (parked: "Transform the current selection") |
| 2 | Built-in **`send`** Trigger Word | S | #131 (parked: "Auto-send") |
| 3 | **Silent-mic warning** plus a faster WASAPI mic start | S–M | #184 |
| 4 | **Static Prompt Files** (voice snippets) | S | #131 (parked: "Voice snippets") |
| 5 | **Opt-in local dictation history**, text only, with retention | M | #131 (parked: "Local dictation history"), #119 |

### 1. Trigger Words act on the current selection
**What:** if text is selected in the focused window when a Trigger Word fires,
the Transform rewrites the selection in place instead of the Last Paste. So
"polish" or "summarize" would work on any text, not only text Dictatem just pasted.
**Who:** Wispr Flow Command Mode: highlight text, hold a shortcut, speak an
instruction. Mac and Windows, Pro only, off by default under Experimental
([docs](https://docs.wisprflow.ai/articles/4816967992-how-to-use-command-mode),
accessed 2026-11-01). Aqua Voice Edit Mode (v0.17.0, 2026-07-20,
[changelog](https://aquavoice.com/changelog)). Superwhisper: selected text used as
context in all apps (v2.6.0, 2025-10-15,
[changelog](https://superwhisper.com/changelog)).
**Why it fits:** competitors send the selection to a cloud LLM. Dictatem would
send it to local Ollama, with the same privacy guarantee as today. It stays
voice-first: no extra shortcut, just the same one-word Trigger Words. On Windows
the selection can be read with a synthetic Ctrl+C wrapped in the existing
Clipboard Snapshot/restore machinery. The replace path already exists in Trigger
Fire (typed SendInput, ADR-0004).
**Watch:** a new Last Paste/selection precedence rule needs an ADR. Per #278,
Trigger Fire replacement is mangled in Windows 11 Notepad, so typing over a
selection must be QA'd there too.

### 2. Built-in `send` Trigger Word
**What:** a second built-in action next to `paste`. Saying "send" right after a
dictation presses Enter in the same window, guarded by the same same-target rail
as Trigger Fire. Config chooses the key (Enter or Ctrl+Enter).
**Who:** Aqua "Send It" (v0.18.0, 2026-07-26) and a choice of submit key (v0.18.5,
2026-07-29) ([changelog](https://aquavoice.com/changelog)). VoiceInk global Auto
Send (v2.21, 28 Sep, [releases](https://github.com/Beingpax/VoiceInk/releases)).
Wispr Flow rebindable Enter (v1.4.661, 2026-03-31,
[what's new](https://wisprflow.ai/whats-new)).
**Why it fits:** this is the chat and AI-prompt workflow, and it needs no LLM, no
network and no new UI. It reuses the built-in-action, fuzzy-match and alias code
(`paste_aliases` → `send_aliases`).
**Watch:** "send" is a common word. Like `paste`, it must fire only as a
standalone single-word utterance (ADR-0028 already enforces this).

### 3. Silent-mic warning plus a faster WASAPI mic start
**What:** (a) if a recording's RMS stays at the digital floor for its first
couple of seconds (muted mic, wrong device, privacy switch), flash a distinct
pill colour and fire one toast naming the device, instead of producing an empty
transcript. (b) Ship #184 (WASAPI shared mode plus resample), which cuts the mic
start time on Windows.
**Who:** Wispr Flow no-sound warning (2026-10-19). Superwhisper no-audio mic
warning (v2.15.0, 2026-05-29), favourite/exclude devices (v2.16.4, 2026-07-13) and
faster mic start (v2.19.0, 2026-10-02). Aqua cut Windows mic start from 298 ms to
122 ms (v0.19.14, 2026-09-14) and lets users blacklist virtual mics (v0.19.12,
2026-09-04).
**Why it fits:** this is Windows-first reliability work, with no privacy cost.
It targets the "I spoke and nothing happened" class of failure (compare #269).
`audio/buffer.py` already computes normalised RMS, so (a) is small.

### 4. Static Prompt Files (voice snippets)
**What:** a Prompt File whose frontmatter declares `kind: snippet`. Its body is
pasted verbatim when its Trigger Word is spoken, with no LLM call. Examples:
"signature", "address", a canned support reply.
**Who:** Wispr Flow Snippets, with rich text since v1.6.288 (2026-07-29). Aqua
Replacements that expand to saved text (v0.10.8, 2025-11-13).
**Why it fits:** it reuses the existing `prompts/*.md` format (ADR-0003),
aliases and fuzzy matching. It works with Ollama off, like `paste`. It is fully
local and adds no UI.
**Watch:** a snippet pastes new text at the cursor and does not replace the Last
Paste. That makes it different from a Transform, so define it in CONTEXT.md.

### 5. Opt-in local dictation history, text only
**What:** off by default. When enabled, dictated text (never audio) is appended to
a local file with a retention limit (for example 7 days or N entries). A tray
item, "Recent dictations…", re-copies an entry.
**Who:** Superwhisper rebuilt History with full-text search (v2.8.0, 2026-01-02)
and added a retention setting (v2.11.0, 2026-03-12). Wispr Flow added local
storage choices (keep, 24-hour auto-delete, never) (2026-04-24) and 14-day audio
playback (2026-08-05). VoiceInk added Quick History (v2.20, 19 Sep).
**Why it fits:** "dictation is never lost" currently covers only the
Most-recent dictation (ADR-0023). History extends that promise. Keeping it
text-only, local, opt-in and retention-capped keeps the README's privacy claims
true.
**Watch:** the README Privacy section and ADR-0023 would need amending, because
text would now persist on disk when the user opts in. Do not store audio.

**Next tier (evidence present, weaker fit right now):**
- **Opt-in auto-cleanup (#129).** Wispr Auto Cleanup levels (2026-04-24) then
  needed an accuracy fix and rollback testing (2026-06-04, 2026-07-09).
  Microsoft made Fluid Dictation **off by default for new users**
  ([KB5101684](https://support.microsoft.com/help/5101684), 2026-07-28). That
  supports keeping #129 opt-in and parked.
- **App-aware Trigger Words** (a Prompt File limited to certain apps). See
  VoiceInk Modes/Power Mode (v2.0, 16 Jul;
  [docs](https://tryvoiceink.com/docs/power-mode)) and Spokenly voice-triggered
  mode switching (Windows 1.0.13, 2026-10-14). Per-app modes are parked in #131.

---

## 2. Competitor profiles

### Wispr Flow (in depth)
- **Platforms:** Mac, Windows, iOS (2025-06-03), Android (2026-02-23)
  ([Wikipedia](https://en.wikipedia.org/wiki/Wispr_Flow)).
- **Local or cloud:** cloud. Turning off model training "does not stop cloud
  processing". "Dictation cloud storage" and "Improve the model" both "default to
  on unless restricted"
  ([docs](https://docs.wisprflow.ai/articles/4709791908-understanding-privacy-mode-and-cloud-sync),
  accessed 2026-11-01). Metadata (app, URL, word count) is uploaded even with
  training off.
- **Pricing** ([pricing](https://wisprflow.ai/pricing), accessed 2026-11-01):
  Free has a weekly word limit. Pro is $15/mo ($12 annual). Growth is $23/mo
  ($18 annual) and adds SSO and HIPAA. Enterprise is custom.
- **2026 features** ([what's new](https://wisprflow.ai/whats-new)):
  - 2026-03-31: Flow Bar language picker, 20-minute sessions, **Mouse Flow**
    (side mouse buttons), rebindable Esc/Enter, inline retry from History.
  - 2026-04-24: Insights/leaderboard, **Auto Cleanup levels**, local transcript
    storage options.
  - 2026-05-01: Scratchpad beta, **Transforms beta** ("Polish", "Prompt
    Engineer", custom), dictation recovery after quit.
  - 2026-07-29: rich-text Snippets.
  - 2026-08-05: Notetaker (Mac), 14-day audio playback.
  - 2026-08-21: virtual mics selectable.
  - 2026-09-04: org-shared dictionary.
  - 2026-09-15: Notetaker on Windows, with MCP.
  - 2026-09-17: **Canto**, its in-house speech model.
  - 2026-10-19: dark mode, no-sound mic warning, "add a spoken language" prompt.
  - Command Mode (voice edit of the selection, Pro, Experimental; see #1).
- **Late 2025 context:** $25M Series A extension (2025-11-20). A $280M Series B
  followed (2026-08-17, per Wikipedia).
- **Complaints [sentiment]:** the app can read keystrokes (Wikipedia, citing
  Wispr's privacy page). It requires an internet connection (Android Police,
  2026-02-25, via Wikipedia). High resource use and startup delays (How-To Geek,
  2026-04-26, via Wikipedia). Windows Electron RAM/CPU complaints
  ([Spokenly review](https://spokenly.app/blog/wispr-flow-review); a competitor,
  so low trust). The vendor's own reliability posts (2026-06-04, 2026-06-10)
  acknowledge outages.

### Superwhisper (in depth)
- **Platforms:** macOS (14+ since v2.16.2, 2026-07-06), Windows 10/11 x64 and ARM64
  (launched about 2025-12-02,
  [AlternativeTo](https://alternativeto.net/news/2025/12/ai-powered-transcription-tool-superwhisper-has-officially-launched-a-windows-version)),
  iOS, Android. One license covers all of them.
- **Local or cloud:** hybrid. Local Whisper models are free. Parakeet, Cohere
  Transcribe, the S1 models, cloud models and BYOK LLMs are Pro
  ([plans](https://superwhisper.com/docs/billing/plans.md)). "Super Mode" reads
  the screen for context ([Windows page](https://superwhisper.com/windows)).
- **Pricing:** Free. Pro is $8.49/mo, $84.99/yr or $249.99 lifetime. The new-user
  trial is 3,000 words ([plans](https://superwhisper.com/docs/billing/plans.md)).
- **Features** ([changelog](https://superwhisper.com/changelog)):
  - Late 2025: selected-text context in all apps (2.6.0, 2025-10-15), Stats and
    mode-selector shortcuts (2.7.0, 2025-11-26).
  - 2.8.0 (2026-01-02): searchable History, Model Library.
  - 2.9.0 (2026-01-23): Parakeet Realtime offline.
  - 2.10–2.11 (Feb–Mar 2026): realtime streaming UI, filler-word removal,
    retention setting.
  - 2.13.0 (2026-04-24): Claude Code/OpenCode agents, Vocabulary and Replacements
    redesign.
  - 2.16.x (Jun–Jul 2026): themes, ~300 ms faster paste, vocabulary for offline
    Whisper, deep links.
  - 2.18.0 (2026-08-19): **S1-mini on-device model with tone control**.
  - 2.18.2 (2026-08-26): all local Whisper models free on macOS.
  - 2.18.3 (2026-09-03): **clipboard preserved by default**.
  - 2.19.0 (2026-10-02): faster mic start, "Muffle" for other apps' audio.
  - **3.0.0 (2026-10-15): Meetings tab.**
  - 3.1.0 (2026-10-28): FaceTime recording, "Modes" renamed "Transcribe".
- **Complaints [sentiment]:** the Windows build is less polished than the Mac
  build, and the agent integrations are Mac-only
  ([Spokenly](https://spokenly.app/blog/superwhisper-for-windows);
  [Voibe](https://www.getvoibe.com/resources/superwhisper-platform-support/)).
  Both are competitor sites. The changelog shows a steady stream of crash fixes.

### MacWhisper
macOS only. File and meeting transcription is its core, with dictation
secondary. Local and cloud engines (ElevenLabs, AssemblyAI, Cohere, OpenAI and
others). v15 requires macOS 15 and adds folders, live meeting transcription
(Pro), Siri/Shortcuts and six UI languages. 15.8 types text in Chromium instead of
pasting. 15.9 fixes "stuck busy" dictation
([Releasebot](https://releasebot.io/updates/macwhisper); entries first seen
Oct 2026, exact release dates not given). Pro is about €59 lifetime
([Voibe](https://www.getvoibe.com/resources/macwhisper-pricing/), secondary).

### Aqua Voice
Mac, Windows, iOS, and Android (2026-10-06). Cloud, using its own "Avalon"
model (v1.5 on 2026-04-13). Pro is about $8–10/mo (secondary sources). From the
[changelog](https://aquavoice.com/changelog):
- 2025-10-04: paste-last shortcut.
- 2025-11-13: Replacements and text expansion.
- 2026-01-23: Windows mutes background audio while recording.
- 2026-06-01: Business tier with SSO.
- 2026-07-20: Edit Mode.
- 2026-07-26: "Send It".
- 2026-07-30: mouse-button bindings.
- 2026-09: mic blacklist, Windows mic start 122 ms.
- 2026-10-15: "Aqua Pet" (gamification).

### Willow Voice
Mac, iOS and Windows (reported January 2026, secondary). Cloud. Pro is about
$15/mo. Offline mode is reported as Mac/iOS only, not Windows
([Voibe review](https://www.getvoibe.com/resources/willow-voice-review/),
secondary). The official changelog shows auto language switching (2025-09-27) and
Esc to reset a hung pipeline (2025-10-07). It has no 2026 entries
([featurebase](https://willowvoice.featurebase.app/changelog)). Product Hunt lists
Willow for Developers (2026-02-11) and Frontier Pro (2026-07-08).

### VoiceInk
macOS only. Open source (GPL v3 per a
[secondary source](https://www.getvoibe.com/resources/voiceink-pricing/)), with
paid notarized builds. Local and cloud models. From
[GitHub releases](https://github.com/Beingpax/VoiceInk/releases) (the page omits
years; 2026 is inferred):
- v2.0 (16 Jul): app- and site-specific Modes, plus trigger words for modes and
  prompts in the betas.
- v2.11 (12 Aug): on-device "Refine".
- v2.20 (19 Sep): Dictionary Auto Learn, Quick History, mouse shortcuts.
- v2.21 (28 Sep): Auto Send, double-tap shortcuts.

### Spokenly
Mac, Windows, Linux, iOS. Local Whisper and Parakeet are free and uncapped.
Local+ costs $29 once. Pro is $12/mo, with cloud models and AI cleanup
([pricing](https://spokenly.app/pricing)). Windows timeline
([releases](https://spokenly.app/releases/windows)):
- 0.1.0 (2026-05-03): first Windows release.
- 0.2.1 (2026-06-16): local-only mode.
- 0.3.18 (2026-08-20): GPU Parakeet.
- 1.0.9 (2026-10-11): local-only mode enforced by Group Policy or Intune.
- 1.0.13 (2026-10-14): voice-triggered mode switching.
- 1.1.0 (2026-10-19): new on-device models.

It is the closest Windows-local competitor.

### Windows 11 voice access and voice typing (Win+H)
- **Fluid Dictation:** on-device, fixes grammar, punctuation and fillers.
  **Copilot+ PCs only.** Release Preview on 2025-10-21
  ([Windows blog](https://blogs.windows.com/blog/2025/12/03/2025-a-year-in-recap-windows-accessibility/)).
  English locales, with Spanish and French in Insider builds. Not available in
  the EEA or China (secondary).
- **KB5101684 (2026-07-28):** Fluid Dictation is now **off by default for new
  users**. Voice Isolation and Korean were added to voice access
  ([KB](https://support.microsoft.com/help/5101684)).
- **Voice typing:** standard voice typing uses online speech recognition (Azure),
  per Microsoft support (via secondary summary).

### macOS built-in dictation
WWDC (2026-06-08) announced LLM-based systemwide dictation
([TechCrunch](https://techcrunch.com/2026/06/08/apple-introduces-systemwide-dictation)).
"Advanced Dictation Preview" is opt-in, runs fully on-device ("AFM Core
Advanced"), and requires a Mac with **M3 or later and at least 12 GB RAM**
([9to5Mac](https://9to5mac.com/2026/06/12/ai-advanced-dictation-preview-ios-27-beta/),
2026-06-12). The coverage described accuracy, punctuation and capitalization
gains. Filler removal and edit commands were not mentioned.

### Also notable
- **Handy:** free, MIT, Windows/macOS/Linux, offline Whisper and Parakeet,
  push-to-talk, about 36k GitHub stars ([repo](https://github.com/cjpais/Handy),
  accessed 2026-11-01). It is the most visible free local alternative.
- **OpenWhispr:** MIT, cross-platform, local models plus optional cloud, and AI
  cleanup ([site](https://openwhispr.com)).

---

## 3. Feature matrix

✅ = shipped · ◐ = partial, paid-only, or hardware-gated · ❌ = no · ? = unverified

| Feature | Dictatem | Wispr Flow | Superwhisper | MacWhisper | Aqua | Willow | VoiceInk | Spokenly | Win 11 | macOS |
|---|---|---|---|---|---|---|---|---|---|---|
| Windows app | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ |
| Fully offline transcription | ✅ | ❌ | ✅ | ✅ | ❌ | ◐ Mac/iOS | ✅ | ✅ | ◐ | ◐ M3+ |
| No account required | ✅ | ❌ | ? | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| Free, no word cap | ✅ | ❌ | ◐ local Whisper | ◐ | ❌ | ❌ | ✅ source | ✅ local | ✅ | ✅ |
| LLM rewrite, local | ✅ Ollama | ❌ | ◐ S1-mini (Pro) | ◐ Apple model | ❌ | ❌ | ✅ | ◐ BYO | ◐ Copilot+ | ◐ |
| Voice-edit selection | ❌ (#1) | ◐ Pro | ✅ context | ? | ✅ | ? | ? | ? | ❌ | ❌ |
| Spoken "send" | ❌ (#2) | ◐ key | ? | ❌ | ✅ | ? | ✅ | ? | ❌ | ❌ |
| Snippets/text expansion | ◐ Replacements | ✅ | ✅ Replacements | ? | ✅ | ? | ? | ? | ❌ | ❌ |
| Custom vocabulary | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ voice access | ❌ |
| Searchable history | ❌ (#5) | ✅ | ✅ | ✅ | ? | ? | ✅ | ? | ❌ | ❌ |
| Mouse-button trigger | ✅ Win | ✅ | ? | ? | ✅ | ? | ✅ | ? | ❌ | ❌ |
| No-audio mic warning | ❌ (#3) | ✅ | ✅ | ? | ? | ? | ? | ? | ? | ❌ |
| Whole-clipboard preserve | ✅ Win | ? | ✅ default | ? | ? | ? | ? | ? | n/a | n/a |
| Restrict language detection | ✅ | ◐ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Meetings/notetaker | ❌ by design | ✅ | ✅ 3.0 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Team/SSO | ❌ by design | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ◐ GPO | n/a | n/a |

---

## 4. Gaps where Dictatem already wins (pitch ammunition)

Every claim below can be checked in this repo (README.md, CONTEXT.md, docs/adr/).

- **"Your voice never leaves your PC, and it never touches your disk."** No
  telemetry, no account. Audio is transcribed in memory and never written to
  disk, and the logs record character counts only (README, Privacy). Wispr's
  cloud storage and model-improvement switches default to on.
- **"Local AI rewriting, on any Windows 11 PC, for free."** Trigger Words run on
  your own Ollama (ADR-0008), with no subscription and no Copilot+ NPU. Wispr's
  Command Mode is Pro-only cloud. Windows Fluid Dictation needs a Copilot+ PC.
  Apple's version needs an M3 with 12 GB.
- **"Edit by voice with one word, not a shortcut chord."** You say "polish" or
  "summarize" after dictating. Fuzzy matching handles mishearings, and an
  uncertain match flashes "say again" instead of guessing (ADR-0028).
- **"A dictation is never lost."** Focus drift holds the text instead of
  mispasting it. "paste" or the tray recovers it (ADR-0023, ADR-0026).
- **"Your clipboard survives, images and files included."** On Windows the whole
  clipboard is restored after every paste and is kept out of clipboard history
  (README, Features). Superwhisper only made clipboard preservation the default
  on 2026-09-03.
- **"Bind dictation to a mouse button."** Shipped on Windows 2026-06-22
  (PR #159, ADR-0020), alongside Wispr (2026-03-31) and ahead of Aqua
  (2026-07-30) and VoiceInk (Sep).
- **"It won't turn 'Summer.' into French."** English by default, with Preferred
  Languages that limit detection to the languages you use. A sure-or-fallback
  rule covers short clips (README, Language). Wispr was still adding
  "add a spoken language" prompts in Sep and Oct 2026.
- **"Transparent by construction."** It is a public repo under the MIT licence
  (README). You can read the installer before running it. Config and prompts are
  plain files you can version (ADR-0003, ADR-0022). Windows on ARM is supported
  (ADR-0017).

---

## 5. Ideas explicitly rejected

| Idea (who does it) | Why not |
|---|---|
| Cloud or in-house speech models (Wispr Canto, Aqua Avalon, Superwhisper S1-Voice) | Breaks the core promise. Optional BYO endpoints stay parked in #165 and are never the default. |
| Screen-reading "context awareness" (Superwhisper Super Mode, Aqua Deep Context, Wispr app/URL metadata) | Captures screen content: the most privacy-hostile feature in the category, and a common complaint. The selection-only design in #1 is the bounded alternative. |
| Meetings and notetaker (Wispr 2026-08/09, Superwhisper 3.0, MacWhisper 15) | Already rejected (#131, "Meeting/File-transcription suites"). It would mean a different product, recording other people, and storing audio. |
| Audio playback in history (Wispr 2026-08-05) | Audio is never written to disk (README). History (#5) stays text-only. |
| Realtime streaming UI (Superwhisper 2.10, Spokenly) | Already rejected in #131. Batch transcription is what keeps the push-to-talk model simple. |
| Insights, leaderboards, pets, "Wrapped" (Wispr, Aqua, Superwhisper Stats) | Already rejected as gamification in #131. It would also need usage logging, which the logs deliberately avoid. |
| Teams, SSO, shared dictionaries, admin audit logs | Already rejected in #131. There is no server to share with. |
| MCP and coding-agent integrations (Wispr Notetaker MCP, Superwhisper agents) | Mac-centric and server-adjacent, and needs a history/notes store first. Revisit only after #5. |
| Scratchpad / notes app (Wispr 2026-05-01) | Already rejected in #131. Dictatem pastes into your apps and is not one itself. |
| Settings window (everyone) | ADR-0022: the config is a discoverable file. The in-app Usage Guide (ADR-0019) covers discoverability. |
| Keyboard-shortcut Command Mode (Wispr) | Conflicts with voice-first Trigger Words (#131). Recommendation #1 delivers the same outcome by voice. |
| Auto-translate (Superwhisper, Wispr Notetaker) | Parked in #272, not rejected. Not a 2026 differentiator. |
