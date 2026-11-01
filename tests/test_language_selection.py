"""Language selection (#273): the pure decision, its config surface, and the adapters.

The decision (:func:`choose_language`) takes language probabilities, the clip's
speech duration, the policy and the last confident language, and returns the
chosen code plus a reason. The backends only gather those inputs.
"""

from __future__ import annotations

import logging
import sys
import tomllib
import types
from textwrap import dedent
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

from dictatem.config import Config, load_config_with_report, write_config
from dictatem.transcribe.language import (
    DEFAULT_LANGUAGE,
    LANGUAGE_CONFIDENCE_THRESHOLD,
    MIN_DETECTION_SPEECH_S,
    WHISPER_LANGUAGE_CODES,
    LanguagePolicy,
    LanguageSelector,
    choose_language,
    fallback_language,
    language_policy,
    needs_detection,
    whisper_code_for_locale,
)
from dictatem.transcribe.os_language import first_apple_language

if TYPE_CHECKING:
    from pathlib import Path

AUTO = language_policy("auto")
EN_ZH = language_policy(None, ["en", "zh"])
LONG = 3.0  # seconds of speech: long enough to detect
SHORT = 0.6  # a one-word clip


def _choose(
    policy: LanguagePolicy,
    probs: dict[str, float] | None,
    *,
    speech: float | None = LONG,
    last: str | None = None,
) -> tuple[str, str, str | None]:
    c = choose_language(
        policy, probabilities=probs, speech_duration_s=speech, last_confident=last
    )
    return c.language, c.reason, c.fallback


class TestConstants:
    def test_threshold_and_minimum_speech(self) -> None:
        assert LANGUAGE_CONFIDENCE_THRESHOLD == 0.6
        assert MIN_DETECTION_SPEECH_S == 1.5

    def test_codes_match_the_installed_engine(self) -> None:
        tokenizer = pytest.importorskip("faster_whisper.tokenizer")
        assert frozenset(tokenizer._LANGUAGE_CODES) == WHISPER_LANGUAGE_CODES


class TestPolicy:
    def test_no_language_key_is_english_pinned(self) -> None:
        policy = language_policy(None)
        assert policy.pinned == DEFAULT_LANGUAGE == "en"
        assert not policy.detects

    def test_a_code_pins_it(self) -> None:
        assert language_policy("ZH").pinned == "zh"

    def test_auto_detects_across_all_languages(self) -> None:
        policy = language_policy("auto", os_ui_language="de")
        assert policy.detects and policy.preferred == ()
        assert policy.os_ui_language == "de"
        assert policy.mode == "auto"

    def test_preferred_languages_win_over_language(self) -> None:
        policy = language_policy("fr", ["en", "zh", "en"])
        assert policy.pinned is None
        assert policy.preferred == ("en", "zh")
        assert policy.mode == "preferred"

    def test_an_empty_preferred_list_falls_through_to_language(self) -> None:
        assert language_policy("ja", []).pinned == "ja"


class TestChooseLanguage:
    def test_pinned_never_detects(self) -> None:
        assert _choose(language_policy("zh"), {"en": 0.99}) == ("zh", "pinned", None)
        assert not needs_detection(language_policy(None), LONG)

    @pytest.mark.parametrize(
        "probs",
        [
            {"fr": 0.34, "en": 0.30, "el": 0.10},  # "Summer." -> "Ça m'a."
            {"el": 0.57, "en": 0.20},  # "Summer." -> "ΣΑΜΑ"
            {"fr": 0.28, "en": 0.27},
        ],
    )
    def test_auto_unsure_winner_falls_back_to_english(self, probs: dict[str, float]) -> None:
        assert _choose(AUTO, probs) == ("en", "unsure", "default")

    def test_auto_sure_winner_is_used(self) -> None:
        assert _choose(AUTO, {"zh": 0.65, "en": 0.2}) == ("zh", "detected", None)

    def test_exactly_the_threshold_is_sure(self) -> None:
        assert _choose(AUTO, {"ja": 0.6, "en": 0.4})[1] == "detected"

    def test_short_clip_uses_the_fallback_without_detecting(self) -> None:
        assert not needs_detection(AUTO, SHORT)
        # Even an apparently sure detection is ignored on a short clip.
        assert _choose(AUTO, {"zh": 0.99}, speech=SHORT) == ("en", "short-clip", "default")

    def test_unknown_duration_still_detects(self) -> None:
        assert needs_detection(AUTO, None)
        assert _choose(AUTO, {"zh": 0.9}, speech=None)[0] == "zh"

    def test_no_probabilities_falls_back(self) -> None:
        assert _choose(AUTO, None) == ("en", "no-detection", "default")

    def test_preferred_set_restricts_and_renormalises(self) -> None:
        # Overall fr wins, but only en/zh are allowed: zh 0.3 / (0.3+0.1) = 0.75.
        c = choose_language(
            EN_ZH,
            probabilities={"fr": 0.5, "zh": 0.3, "en": 0.1},
            speech_duration_s=LONG,
            last_confident=None,
        )
        assert (c.language, c.reason) == ("zh", "detected")
        assert c.probability == pytest.approx(0.75)

    def test_preferred_set_unsure_uses_the_first_preferred(self) -> None:
        # en 0.25 / zh 0.20 -> 0.56 within the set: below the threshold.
        assert _choose(EN_ZH, {"en": 0.25, "zh": 0.20, "fr": 0.5}) == (
            "en", "unsure", "preferred-first",
        )

    def test_preferred_set_with_no_mass_in_the_set_falls_back(self) -> None:
        assert _choose(EN_ZH, {"fr": 1.0}) == ("en", "no-detection", "preferred-first")

    def test_ties_go_to_the_earlier_preferred_language(self) -> None:
        zh_en = language_policy(None, ["zh", "en"])
        # 0.5 / 0.5 is below the threshold, so check the reported winner.
        c = choose_language(
            zh_en,
            probabilities={"en": 0.4, "zh": 0.4},
            speech_duration_s=LONG,
            last_confident=None,
        )
        assert c.detected == "zh"


class TestFallbackChain:
    def test_last_confident_wins_when_allowed(self) -> None:
        assert fallback_language(EN_ZH, "zh") == ("zh", "session")
        assert fallback_language(AUTO, "ja") == ("ja", "session")

    def test_last_confident_outside_the_set_is_skipped(self) -> None:
        assert fallback_language(EN_ZH, "fr") == ("en", "preferred-first")

    def test_auto_uses_the_os_ui_language_then_english(self) -> None:
        assert fallback_language(language_policy("auto", os_ui_language="de"), None) == (
            "de", "os-ui",
        )
        assert fallback_language(AUTO, None) == ("en", "default")

    def test_an_unknown_os_ui_language_is_ignored(self) -> None:
        assert language_policy("auto", os_ui_language="xx").os_ui_language is None

    def test_short_clip_after_a_confident_one_reuses_it(self) -> None:
        assert _choose(EN_ZH, None, speech=SHORT, last="zh") == ("zh", "short-clip", "session")


class TestSelector:
    def test_remembers_the_last_confident_language(self) -> None:
        sel = LanguageSelector(EN_ZH)
        assert sel.choose({"zh": 0.9, "en": 0.1}, LONG).language == "zh"
        assert sel.last_confident == "zh"
        # An unsure clip then reuses zh, and does not overwrite it.
        assert sel.choose({"zh": 0.45, "en": 0.55}, LONG).language == "zh"
        assert sel.choose(None, SHORT).language == "zh"
        assert sel.last_confident == "zh"

    def test_confirm_pass_reuses_the_last_choice(self) -> None:
        sel = LanguageSelector(AUTO)
        assert sel.confirm_pass_language() == "en"  # nothing yet: the fallback
        sel.choose({"zh": 0.9}, LONG)
        assert sel.confirm_pass_language() == "zh"
        assert LanguageSelector(language_policy("ja")).confirm_pass_language() == "ja"

    def test_default_selector_is_english_pinned(self) -> None:
        assert LanguageSelector().choose(None, None).language == "en"

    def test_logs_codes_and_reason_only(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger="dictatem.transcribe.language")
        LanguageSelector(AUTO).choose({"fr": 0.34, "en": 0.3}, LONG)
        assert caplog.messages == [
            "Transcription language=en reason=unsure fallback=default top=fr p=0.34"
        ]


class TestLocaleMapping:
    @pytest.mark.parametrize(
        ("tag", "code"),
        [
            ("en_US", "en"),
            ("zh-Hans-CN", "zh"),
            ("pt_BR.UTF-8", "pt"),
            ("iw-IL", "he"),
            ("nb_NO", "no"),
            ("jv", "jw"),
            ("fil-PH", "tl"),
            ("xx-YY", None),
            ("", None),
            (None, None),
        ],
    )
    def test_whisper_code_for_locale(self, tag: str | None, code: str | None) -> None:
        assert whisper_code_for_locale(tag) == code

    def test_first_apple_language(self) -> None:
        assert first_apple_language('(\n    "zh-Hans-CN",\n    en\n)\n') == "zh-Hans-CN"
        assert first_apple_language("(\n    en\n)") == "en"
        assert first_apple_language("(\n)") is None


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(dedent(body), encoding="utf-8")
    return path


class TestConfig:
    def test_defaults(self) -> None:
        assert Config().model.language is None
        assert Config().model.languages == ()

    def test_valid_values_are_normalised(self, tmp_path: Path) -> None:
        cfg, report = load_config_with_report(_write(tmp_path, """
            [model]
            language = "AUTO"
            languages = ["EN", "zh", "en"]
        """))
        assert report.is_empty
        assert cfg.model.language == "auto"
        assert cfg.model.languages == ("en", "zh")

    def test_invalid_language_is_reported_and_defaults(self, tmp_path: Path) -> None:
        path = _write(tmp_path, """
            [model]
            language = "english"
        """)
        before = path.read_text(encoding="utf-8")
        cfg, report = load_config_with_report(path)
        assert cfg.model.language is None
        assert [p.key for p in report.problems] == ["[model].language"]
        assert report.write_protected
        assert path.read_text(encoding="utf-8") == before

    def test_invalid_preferred_entry_is_reported_and_defaults(self, tmp_path: Path) -> None:
        cfg, report = load_config_with_report(_write(tmp_path, """
            [model]
            languages = ["en", "auto"]
        """))
        assert cfg.model.languages == ()
        assert [p.key for p in report.problems] == ["[model].languages"]

    def test_written_config_shows_a_commented_languages_example(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        write_config(Config(), path)
        text = path.read_text(encoding="utf-8")
        assert '# languages = ["en", "zh"]' in text
        model = tomllib.loads(text)["model"]
        assert "languages" not in model and "language" not in model

    def test_set_preferred_languages_round_trip(self, tmp_path: Path) -> None:
        cfg = Config()
        cfg.model.languages = ("en", "zh")
        path = tmp_path / "config.toml"
        write_config(cfg, path)
        text = path.read_text(encoding="utf-8")
        assert "# languages =" not in text
        loaded, report = load_config_with_report(path)
        assert report.is_empty
        assert loaded.model.languages == ("en", "zh")


class TestDaemonSelector:
    def test_reads_the_os_ui_language_only_for_auto(self) -> None:
        from dictatem.daemon import _build_language_selector

        calls: list[int] = []

        def reader() -> str | None:
            calls.append(1)
            return "de"

        cfg = Config()
        assert _build_language_selector(cfg, reader).policy.pinned == "en"
        cfg.model.languages = ("en", "zh")
        assert _build_language_selector(cfg, reader).policy.preferred == ("en", "zh")
        assert calls == []
        cfg.model.languages = ()
        cfg.model.language = "auto"
        assert _build_language_selector(cfg, reader).policy.os_ui_language == "de"
        assert calls == [1]


# -- faster-whisper adapter, around a fake model (no engine load) ------------

AUDIO = np.ones(48_000, dtype=np.float32)  # 3 s at 16 kHz


class _Seg:
    text = " hello"
    start = 0.0
    end = 1.0
    avg_logprob = -0.2
    no_speech_prob = 0.01


class _FakeWhisperModel:
    def __init__(self, probs: list[tuple[str, float]]) -> None:
        self.model = types.SimpleNamespace(is_multilingual=True)
        self.probs = probs
        self.detect_calls: list[int] = []
        self.languages: list[str | None] = []

    def detect_language(self, audio: np.ndarray) -> tuple[str, float, list[tuple[str, float]]]:
        self.detect_calls.append(int(audio.size))
        return self.probs[0][0], self.probs[0][1], self.probs

    def transcribe(self, audio: Any, **kwargs: Any) -> tuple[list[_Seg], Any]:
        self.languages.append(kwargs["language"])
        return [_Seg()], types.SimpleNamespace(duration_after_vad=1.0)


@pytest.fixture
def speech(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, int]]:
    """Stub faster-whisper's Silero VAD; mutate the list to change the speech."""
    spans: list[dict[str, int]] = [{"start": 0, "end": 40_000}]  # 2.5 s
    vad = types.ModuleType("faster_whisper.vad")
    vad.get_speech_timestamps = lambda samples: spans  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper.vad", vad)
    return spans


def _fw(policy: LanguagePolicy, model: _FakeWhisperModel) -> Any:
    from dictatem.transcribe.faster_whisper_backend import FasterWhisperBackend

    backend = FasterWhisperBackend(
        model_name="tiny", device="cpu", language_selector=LanguageSelector(policy)
    )
    backend._model = model  # type: ignore[attr-defined]
    return backend


class TestFasterWhisperAdapter:
    def test_default_is_english_with_no_detection(self, speech: list[dict[str, int]]) -> None:
        model = _FakeWhisperModel([("fr", 0.9)])
        _fw(language_policy(None), model).transcribe(AUDIO)
        assert model.languages == ["en"]
        assert model.detect_calls == []

    def test_preferred_set_detects_on_the_speech_only(
        self, speech: list[dict[str, int]]
    ) -> None:
        model = _FakeWhisperModel([("fr", 0.5), ("zh", 0.4), ("en", 0.1)])
        _fw(EN_ZH, model).transcribe(AUDIO)
        assert model.detect_calls == [40_000]
        assert model.languages == ["zh"]

    def test_short_clip_skips_detection(self, speech: list[dict[str, int]]) -> None:
        speech[0]["end"] = 8_000  # 0.5 s
        model = _FakeWhisperModel([("zh", 0.99)])
        _fw(EN_ZH, model).transcribe(AUDIO)
        assert model.detect_calls == []
        assert model.languages == ["en"]

    def test_confirm_pass_reuses_the_regular_pass_language(
        self, speech: list[dict[str, int]]
    ) -> None:
        model = _FakeWhisperModel([("zh", 0.9), ("en", 0.1)])
        backend = _fw(AUTO, model)
        backend.transcribe(AUDIO)
        backend.transcribe_command(AUDIO, ["paste"])
        assert model.languages == ["zh", "zh"]
        assert len(model.detect_calls) == 1

    def test_english_only_model_is_not_detected(self, speech: list[dict[str, int]]) -> None:
        model = _FakeWhisperModel([("zh", 0.9)])
        model.model.is_multilingual = False
        _fw(AUTO, model).transcribe(AUDIO)
        assert model.detect_calls == []
        assert model.languages == ["en"]


# -- MLX adapter, around fake mlx / mlx_whisper modules ---------------------


class _FakeMlxModel:
    is_multilingual = True
    dims = types.SimpleNamespace(n_mels=128)

    def __init__(self, probs: dict[str, float]) -> None:
        self.probs = probs
        self.detect_calls = 0

    def detect_language(self, segment: Any) -> tuple[Any, dict[str, float]]:
        self.detect_calls += 1
        return None, self.probs


@pytest.fixture
def mlx_engine(
    monkeypatch: pytest.MonkeyPatch, speech: list[dict[str, int]]
) -> tuple[list[dict[str, Any]], _FakeMlxModel]:
    calls: list[dict[str, Any]] = []
    model = _FakeMlxModel({"fr": 0.5, "zh": 0.4, "en": 0.1})

    def transcribe(samples: np.ndarray, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"text": " hi", "segments": []}

    class _Arr:
        def astype(self, _dtype: Any) -> _Arr:
            return self

    mlx_whisper = types.ModuleType("mlx_whisper")
    mlx_whisper.transcribe = transcribe  # type: ignore[attr-defined]
    audio = types.ModuleType("mlx_whisper.audio")
    audio.N_FRAMES = 3000  # type: ignore[attr-defined]
    audio.N_SAMPLES = 480_000  # type: ignore[attr-defined]
    audio.log_mel_spectrogram = lambda *a, **k: _Arr()  # type: ignore[attr-defined]
    audio.pad_or_trim = lambda mel, *a, **k: mel  # type: ignore[attr-defined]
    mtrans = types.ModuleType("mlx_whisper.transcribe")
    mtrans.ModelHolder = types.SimpleNamespace(  # type: ignore[attr-defined]
        get_model=lambda path, dtype: model
    )
    mlx = types.ModuleType("mlx")
    core = types.ModuleType("mlx.core")
    core.float16 = "f16"  # type: ignore[attr-defined]
    core.float32 = "f32"  # type: ignore[attr-defined]
    mlx.core = core  # type: ignore[attr-defined]
    for name, mod in {
        "mlx_whisper": mlx_whisper,
        "mlx_whisper.audio": audio,
        "mlx_whisper.transcribe": mtrans,
        "mlx": mlx,
        "mlx.core": core,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)
    return calls, model


def _mlx(policy: LanguagePolicy) -> Any:
    from dictatem.transcribe.mlx_backend import MlxBackend

    backend = MlxBackend(model_name="tiny", language_selector=LanguageSelector(policy))
    backend._loaded = True  # type: ignore[attr-defined]
    backend._model_path = "/cache/whisper-tiny-mlx"  # type: ignore[attr-defined]
    return backend


class TestMlxAdapter:
    def test_default_sends_english(self, mlx_engine: tuple[list[dict[str, Any]], Any]) -> None:
        calls, model = mlx_engine
        _mlx(language_policy(None)).transcribe(AUDIO)
        assert calls[0]["language"] == "en"
        assert model.detect_calls == 0

    def test_preferred_set_restricts_detection(
        self, mlx_engine: tuple[list[dict[str, Any]], Any]
    ) -> None:
        calls, model = mlx_engine
        backend = _mlx(EN_ZH)
        backend.transcribe(AUDIO)
        backend.transcribe_command(AUDIO, ["paste"])
        assert [c["language"] for c in calls] == ["zh", "zh"]
        assert model.detect_calls == 1

    def test_short_clip_skips_detection(
        self, mlx_engine: tuple[list[dict[str, Any]], Any], speech: list[dict[str, int]]
    ) -> None:
        calls, model = mlx_engine
        speech[0]["end"] = 8_000
        _mlx(EN_ZH).transcribe(AUDIO)
        assert calls[0]["language"] == "en"
        assert model.detect_calls == 0
