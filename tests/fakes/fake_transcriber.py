"""Fake transcriber backend for testing lifecycle and transcription logic."""

from __future__ import annotations

from dictatem.types import AudioChunk, EmptyResult, TranscriptionResult


class FakeTranscriberBackend:
    def __init__(self, result: TranscriptionResult = "fake transcription") -> None:
        self._result = result
        self._loaded: bool = False
        self.load_count: int = 0
        self.unload_count: int = 0
        self.transcribe_calls: list[AudioChunk] = []

    def load_model(self) -> None:
        self._loaded = True
        self.load_count += 1

    def unload_model(self) -> None:
        self._loaded = False
        self.unload_count += 1

    def transcribe(self, audio: AudioChunk) -> TranscriptionResult:
        self.transcribe_calls.append(audio)
        if not self._loaded:
            return EmptyResult()
        return self._result

    @property
    def is_loaded(self) -> bool:
        return self._loaded
