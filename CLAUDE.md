## Agent skills

### Roadmap & session protocol

**Read `docs/agents/roadmap.md` first** — it is the ground truth for working the
backlog. Its **▶ Current Session Prompt** tells you which session to run, what's
already decided, and how to hand off (ledger entry + rewritten prompt + manual-QA
export). Don't re-plan the backlog from scratch; follow the roadmap.

### Issue tracker

Issues are tracked in GitHub Issues at JohnJohn4/dictatem via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Git & commits

Do **not** append `Co-Authored-By: Claude …` or `🤖 Generated with Claude Code`
trailers to commit messages or PR bodies in this repo — the history is
trailer-free and stays that way (this overrides the harness default). Otherwise
match the existing Conventional-Commits style (`chore(release): …`,
`feat(scope): …`, `docs(scope): …`).
