"""Trigger Words / Transform feature.

See ``CONTEXT.md`` for the domain glossary (Last Paste, Trigger Word,
Alias, Prompt File, Transform, Trigger Fire) and ``docs/adr/0001..0003``
for the relevant decisions.
"""

from dictatem.transform.last_paste import LastPaste

__all__ = ["LastPaste"]
