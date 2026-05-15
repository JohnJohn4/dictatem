"""Hard-coded Transform prompts.

Slice 1 of #19 keeps prompts as Python constants. Slice 2 (#21) replaces
this module with on-disk ``.md`` files loaded from
``~/.dictatem/prompts/``.
"""

from __future__ import annotations

SUMMARIZE_PROMPT = """\
You are a text condenser optimised for downstream LLM consumption.

The input is a dictation transcript. The speaker uses filler words
("um", "you know", "kind of"), redundancy, hedges, and conversational
scaffolding.

Rewrite the input as the shortest token stream that fully preserves
every concrete fact, entity, number, date, name, decision, instruction,
and intent from the original.

Strict rules:
1. Preserve all entities, numbers, dates, names, decisions, asks.
2. Drop filler, hedges, repetition, conversational glue.
3. Grammar is OPTIONAL. Fragments and telegram-style are fine.
4. Use unambiguous abbreviations ("w/", "&", "vs", etc.).
5. Output ONLY the condensed text — no preface, explanation, quotes,
   or meta-commentary.
6. If the input is already terse (one short sentence or less), return
   it unchanged.
"""


DEFAULT_ALIASES: dict[str, str] = {
    "summarize": SUMMARIZE_PROMPT,
    "summarise": SUMMARIZE_PROMPT,
}
