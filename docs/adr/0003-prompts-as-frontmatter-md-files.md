# Transforms are declared as frontmatter-prefixed `.md` files

Each [Transform](../../CONTEXT.md#transform) is declared by a single
[Prompt File](../../CONTEXT.md#prompt-file) under `~/.dictatem/prompts/`.
The file has a YAML-style frontmatter block declaring its
[Aliases](../../CONTEXT.md#alias) and a body that is sent verbatim as the
system prompt to Ollama.

The daemon globs `~/.dictatem/prompts/*.md` at startup, parses each file,
and builds a flat `alias → prompt_body` map. Adding a new Transform =
dropping a new `.md` file into the folder.

## Considered Options

- **Single `prompts.toml` file with all aliases and bodies inline.** Less
  portable (TOML escaping for multi-line markdown is awkward) and forces
  every prompt edit through one file.
- **Plain `.md` bodies plus a Python registry mapping aliases to filenames.**
  Splits the declaration in two — aliases in Python, prompt in markdown.
  More boilerplate per transform, more to keep in sync.
- **Frontmatter holds metadata (name, description) only; filename is the
  trigger word.** Doesn't handle multi-alias cases (UK `summarise` vs US
  `summarize`, plus Whisper's punctuation noise) without forcing duplicate
  files.

Frontmatter-with-aliases was chosen because it makes the prompt file
self-describing and portable to other tools, keeps aliases co-located with
their prompt, and lets users refine prompts without editing source.

## Consequences

- A minimal inline frontmatter parser is sufficient — the schema is fixed
  to flow-style `aliases: [list]`, so we don't add a `pyyaml` dependency.
- The package ships its default prompts at
  `src/dictatem/default_prompts/` (inside the installable package so the
  files survive `pip install`). On first daemon start we copy any missing
  defaults into `~/.dictatem/prompts/`, mirroring the `config.toml`
  bootstrap pattern, so user edits survive upgrades.
- The filename has no runtime meaning. Aliases declared in frontmatter are
  the single source of truth. A file with no aliases — or with malformed
  frontmatter — is skipped with a warning at startup.
- Aliases are normalised (lowercase, strip ASCII punctuation, strip
  whitespace) at load time so they line up with `TriggerDetector`'s
  match-time normalisation. On a collision across files the first
  occurrence wins (deterministic by sorted filename) and a warning is
  logged.
