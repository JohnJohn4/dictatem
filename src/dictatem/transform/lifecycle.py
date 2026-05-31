"""TransformLifecycle — thin wrapper around a TransformBackend.

Mirrors ``TranscribeLifecycle`` in spirit but without a load/unload
cycle: Ollama manages its own model lifecycle via ``keep_alive``.

Slice 1 of #19 keeps this layer intentionally thin. It exists so the
daemon can depend on a stable in-process interface while the actual
backend (and any future timeout / retry policy) can evolve without
touching ``DaemonCore``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dictatem.interfaces import TransformBackend

logger = logging.getLogger(__name__)


class TransformLifecycle:
    def __init__(self, *, backend: TransformBackend) -> None:
        self._backend = backend

    def transform(self, text: str, system_prompt: str) -> str:
        """Apply *system_prompt* to *text*.

        Lets ``TransformFailedError`` from the backend propagate unchanged
        so the daemon can map it to the existing ``EMPTY_RESULT`` /
        ``FLASH_ERROR`` path.
        """
        return self._backend.transform(text, system_prompt)

    def warm(self) -> bool:
        """Best-effort preload of the LLM into memory. Never raises; see
        ``TransformBackend.warm``."""
        return self._backend.warm()

    def is_model_available(self) -> bool:
        """Best-effort check that the configured model is pulled. Never raises;
        see ``TransformBackend.is_model_available``."""
        return self._backend.is_model_available()
