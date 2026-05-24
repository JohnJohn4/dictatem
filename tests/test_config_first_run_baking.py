"""Tests for first-run Hardware Tier baking into the config (#36, ADR-0007).

On first run (no config file) the probe is consulted once, the tier resolved,
and CONCRETE values — including ``device``, which is otherwise never written —
are baked into the written config. On every later launch the existing file is
read unchanged and the probe is NOT consulted.
"""

from __future__ import annotations

import logging
from textwrap import dedent
from typing import TYPE_CHECKING

from dictatem.config import load_config
from dictatem.types import HardwareProfile
from tests.fakes import FakeHardwareProbe

if TYPE_CHECKING:
    from pathlib import Path

CPU_PROFILE = HardwareProfile(cuda_available=False, total_vram_mb=None)
GPU_HIGH_PROFILE = HardwareProfile(cuda_available=True, total_vram_mb=8192)
GPU_MID_PROFILE = HardwareProfile(cuda_available=True, total_vram_mb=4096)


class TestFirstRunBakesResolvedValues:
    """No config file -> probe once, resolve, write concrete values."""

    def test_cpu_machine_bakes_cpu_device(self, tmp_path: Path) -> None:
        probe = FakeHardwareProbe(CPU_PROFILE)
        cfg = load_config(tmp_path / "config.toml", probe=probe)
        assert cfg.model.name == "base"
        assert cfg.model.device == "cpu"
        assert cfg.model.compute_type == "int8"
        assert cfg.transform.model_name == "llama3.2:1b"

    def test_gpu_high_machine_bakes_high_tier(self, tmp_path: Path) -> None:
        probe = FakeHardwareProbe(GPU_HIGH_PROFILE)
        cfg = load_config(tmp_path / "config.toml", probe=probe)
        assert cfg.model.name == "large-v3-turbo"
        assert cfg.model.device == "cuda"
        assert cfg.model.compute_type == "float16"
        assert cfg.transform.model_name == "gemma4:e4b"

    def test_probe_consulted_exactly_once(self, tmp_path: Path) -> None:
        probe = FakeHardwareProbe(GPU_MID_PROFILE)
        load_config(tmp_path / "config.toml", probe=probe)
        assert probe.probe_count == 1

    def test_baked_device_is_persisted_to_disk(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        probe = FakeHardwareProbe(CPU_PROFILE)
        load_config(path, probe=probe)
        content = path.read_text()
        assert 'device = "cpu"' in content
        assert 'name = "base"' in content

    def test_baked_values_survive_reload_without_probe(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        probe = FakeHardwareProbe(GPU_MID_PROFILE)
        load_config(path, probe=probe)
        # Reload with no probe: the file drives everything now.
        cfg = load_config(path)
        assert cfg.model.name == "small"
        assert cfg.model.device == "cuda"
        assert cfg.model.compute_type == "int8_float16"
        assert cfg.transform.model_name == "llama3.2:1b"


class TestExistingFileNotReprobed:
    """An existing config is read unchanged; the probe is never consulted."""

    def test_probe_not_consulted_when_file_exists(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        path.write_text(dedent("""\
            [model]
            name = "large-v3-turbo"
            device = "cuda"
        """))
        probe = FakeHardwareProbe(CPU_PROFILE)
        cfg = load_config(path, probe=probe)
        assert probe.probe_count == 0
        # User's file wins — not re-resolved to the CPU profile's "base".
        assert cfg.model.name == "large-v3-turbo"
        assert cfg.model.device == "cuda"

    def test_existing_file_left_byte_identical(self, tmp_path: Path) -> None:
        path = tmp_path / "config.toml"
        original = dedent("""\
            [model]
            name = "small"
        """)
        path.write_text(original)
        load_config(path, probe=FakeHardwareProbe(GPU_HIGH_PROFILE))
        assert path.read_text() == original


class TestFirstRunLogsTier:
    """The resolved tier is logged for transparency (acceptance criterion)."""

    def test_logs_resolved_tier(
        self, tmp_path: Path, caplog: logging.LogCaptureFixture
    ) -> None:
        probe = FakeHardwareProbe(GPU_HIGH_PROFILE)
        with caplog.at_level(logging.INFO, logger="dictatem.config"):
            load_config(tmp_path / "config.toml", probe=probe)
        messages = " ".join(r.message for r in caplog.records)
        assert "GPU-high" in messages
        assert "large-v3-turbo" in messages


class TestFirstRunWithoutProbe:
    """Backward compatibility: no probe -> plain defaults, no device written."""

    def test_defaults_when_no_probe(self, tmp_path: Path) -> None:
        from dictatem.config import Config

        cfg = load_config(tmp_path / "config.toml")
        assert cfg == Config()
