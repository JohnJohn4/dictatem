"""NVML-first CUDA presence: skip the CTranslate2 import only when NVML is sure."""

from __future__ import annotations

import pytest

from dictatem.hardware.cuda_presence import (
    MIN_CUDA_DRIVER_VERSION,
    NvmlReport,
    decide_cuda_presence,
)

GOOD = NvmlReport(device_count=1, cuda_driver_version=13000, total_vram_mb=4094)


class _Ct2:
    def __init__(self, count: int) -> None:
        self.count = count
        self.calls = 0

    def __call__(self) -> int:
        self.calls += 1
        return self.count


def test_nvml_confirmed_gpu_skips_ctranslate2() -> None:
    ct2 = _Ct2(1)

    presence = decide_cuda_presence(GOOD, ctranslate2_device_count=ct2, env={})

    assert presence.available is True
    assert presence.total_vram_mb == 4094
    assert presence.decided_by == "nvml"
    assert ct2.calls == 0


@pytest.mark.parametrize(
    "nvml",
    [
        None,  # no NVIDIA driver / NVML broken
        NvmlReport(device_count=0, cuda_driver_version=13000, total_vram_mb=None),
        NvmlReport(device_count=1, cuda_driver_version=None, total_vram_mb=4094),
        NvmlReport(
            device_count=1,
            cuda_driver_version=MIN_CUDA_DRIVER_VERSION - 10,  # CUDA 11.x driver
            total_vram_mb=4094,
        ),
    ],
)
def test_anything_short_of_a_positive_nvml_answer_uses_ctranslate2(
    nvml: NvmlReport | None,
) -> None:
    ct2 = _Ct2(0)

    presence = decide_cuda_presence(nvml, ctranslate2_device_count=ct2, env={})

    assert ct2.calls == 1
    assert presence.available is False
    assert presence.total_vram_mb is None
    assert presence.decided_by == "ctranslate2"


def test_cuda_visible_devices_defers_to_ctranslate2() -> None:
    # CUDA honours CUDA_VISIBLE_DEVICES; NVML ignores it, so NVML can't decide.
    ct2 = _Ct2(0)

    presence = decide_cuda_presence(
        GOOD, ctranslate2_device_count=ct2, env={"CUDA_VISIBLE_DEVICES": ""}
    )

    assert ct2.calls == 1
    assert presence.available is False


def test_ctranslate2_path_still_reads_vram_from_nvml() -> None:
    # NVML saw the GPU but couldn't read the driver's CUDA version: CTranslate2
    # decides, and the VRAM NVML did read still sizes the tier (as before).
    nvml = NvmlReport(device_count=1, cuda_driver_version=None, total_vram_mb=4094)

    presence = decide_cuda_presence(nvml, ctranslate2_device_count=_Ct2(1), env={})

    assert presence.available is True
    assert presence.total_vram_mb == 4094
    assert presence.decided_by == "ctranslate2"
