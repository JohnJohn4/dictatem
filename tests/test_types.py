"""Tests for shared types module."""

from __future__ import annotations

import numpy as np

from dictatem.types import (
    SAMPLE_RATE,
    AudioChunk,
    EmptyResult,
    RecordingMode,
)


class TestSampleRate:
    def test_value(self) -> None:
        assert SAMPLE_RATE == 16_000


class TestAudioChunk:
    def test_alias_accepts_float32_array(self) -> None:
        chunk: AudioChunk = np.zeros(SAMPLE_RATE, dtype=np.float32)
        assert chunk.dtype == np.float32
        assert chunk.shape == (SAMPLE_RATE,)


class TestRecordingMode:
    def test_ptt(self) -> None:
        assert RecordingMode.PTT.value == "ptt"

    def test_toggle(self) -> None:
        assert RecordingMode.TOGGLE.value == "toggle"

    def test_members(self) -> None:
        assert set(RecordingMode.__members__) == {"PTT", "TOGGLE"}


class TestEmptyResult:
    def test_equality(self) -> None:
        assert EmptyResult() == EmptyResult()

    def test_not_equal_to_string(self) -> None:
        assert EmptyResult() != "some text"

    def test_repr(self) -> None:
        assert repr(EmptyResult()) == "EmptyResult()"

    def test_hashable(self) -> None:
        s = {EmptyResult(), EmptyResult()}
        assert len(s) == 1
