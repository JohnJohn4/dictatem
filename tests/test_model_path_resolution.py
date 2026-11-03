"""Cache-first model resolution: no Hub call when the weights are already cached.

``WhisperModel("small")`` used to ask the Hugging Face Hub for the latest
revision on every load. ``resolve_model_path`` tries the local cache first and
only falls back to the online lookup (the old behaviour) when that fails.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dictatem.transcribe.faster_whisper_backend import resolve_model_path

if TYPE_CHECKING:
    from pathlib import Path


class _Download:
    def __init__(self, *, cached: bool) -> None:
        self.cached = cached
        self.calls: list[dict[str, Any]] = []

    def __call__(self, name: str, **kwargs: Any) -> str:
        self.calls.append({"name": name, **kwargs})
        if kwargs.get("local_files_only") and not self.cached:
            raise FileNotFoundError("not in cache")
        return f"/cache/{name}"


def test_cached_model_resolves_without_going_online() -> None:
    download = _Download(cached=True)

    assert resolve_model_path("small", download) == "/cache/small"
    assert download.calls == [{"name": "small", "local_files_only": True}]


def test_cache_miss_falls_back_to_the_online_lookup() -> None:
    download = _Download(cached=False)

    assert resolve_model_path("small", download) == "/cache/small"
    assert download.calls == [
        {"name": "small", "local_files_only": True},
        {"name": "small"},
    ]


def test_local_directory_is_used_as_is(tmp_path: Path) -> None:
    download = _Download(cached=False)

    assert resolve_model_path(str(tmp_path), download) == str(tmp_path)
    assert download.calls == []
