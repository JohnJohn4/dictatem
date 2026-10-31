"""Transcription backend selection — which engine runs the effective device (#229).

:func:`select_backend` is pure: it maps the session's effective
``[model].device`` to a backend kind. ``cuda`` and ``cpu`` run faster-whisper
(the behaviour before #224); ``mlx`` is reserved for the Apple-GPU MLX backend
(spec #224). Any other device string resolves to the whole ``CPU`` tier row with
a warning, because faster-whisper would raise at model load on a device it
doesn't know (the same reasoning as the ADR-0009 cuda guard).

:func:`build_transcriber` is the single place the daemon turns a selection into
a concrete :class:`~dictatem.interfaces.TranscriberBackend`, so a new engine is
added there and nowhere else. Engine modules are imported lazily inside it, so
importing this module never pulls in faster-whisper (or MLX).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from dictatem.hardware.resolver import tier_row

if TYPE_CHECKING:
    from dictatem.interfaces import TranscriberBackend

BackendKind = Literal["faster-whisper", "mlx"]

# Device value -> engine. Adding an engine is one row here plus one branch in
# build_transcriber.
_DEVICE_TO_KIND: dict[str, BackendKind] = {
    "cuda": "faster-whisper",
    "cpu": "faster-whisper",
    "mlx": "mlx",
}


@dataclass(frozen=True)
class BackendSelection:
    """The engine plus the transcription values it should be built with.

    ``warning`` is set (and the values are the ``CPU`` row) when the requested
    device was unknown; the caller logs it.
    """

    kind: BackendKind
    model: str
    device: str
    compute_type: str
    warning: str | None = None


def select_backend(*, device: str, model: str, compute_type: str) -> BackendSelection:
    """Pick the backend for the effective *device* / *model* / *compute_type*. Pure."""
    kind = _DEVICE_TO_KIND.get(device)
    if kind is not None:
        return BackendSelection(
            kind=kind, model=model, device=device, compute_type=compute_type
        )
    cpu = tier_row("CPU")
    return BackendSelection(
        kind=_DEVICE_TO_KIND[cpu.device],
        model=cpu.model,
        device=cpu.device,
        compute_type=cpu.compute_type,
        warning=(
            f"Unknown [model].device {device!r} (expected one of "
            f"{', '.join(sorted(_DEVICE_TO_KIND))}) — running on CPU "
            f"({cpu.model}/{cpu.device}/{cpu.compute_type}) for this session. "
            "The config file is unchanged."
        ),
    )


def build_transcriber(
    selection: BackendSelection,
    *,
    language: str | None,
    vad_filter: bool,
    vocabulary: list[str],
) -> TranscriberBackend:
    """Construct the (unloaded) backend for *selection*.

    The one place an engine is chosen by kind. ``mlx`` builds the Apple-GPU
    :class:`~dictatem.transcribe.mlx_backend.MlxBackend` (#231); constructing
    it never imports MLX, so a pin that reconcile let through is safe to build
    on any OS. The runtime fallback composite around it is #232.
    """
    if selection.kind == "mlx":
        from dictatem.transcribe.mlx_backend import MlxBackend

        return MlxBackend(
            model_name=selection.model,
            compute_type=selection.compute_type,
            language=language,
            vad_filter=vad_filter,
            vocabulary=vocabulary,
        )

    from dictatem.transcribe.faster_whisper_backend import FasterWhisperBackend

    return FasterWhisperBackend(
        model_name=selection.model,
        compute_type=selection.compute_type,
        device=selection.device,
        language=language,
        vad_filter=vad_filter,
        vocabulary=vocabulary,
    )
