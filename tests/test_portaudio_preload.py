"""The PortAudio preload targets the same bundled DLL sounddevice loads."""

from __future__ import annotations

import pytest

from dictatem.audio.sounddevice_capture import bundled_portaudio_dll_name


@pytest.mark.parametrize(
    ("platform_tag", "arch_bits", "asio", "expected"),
    [
        ("win-amd64", "64bit", False, "libportaudio64bit.dll"),
        ("win-amd64", "64bit", True, "libportaudio64bit-asio.dll"),
        ("win32", "32bit", False, "libportaudio32bit.dll"),
        ("win-arm64", "64bit", False, "libportaudioarm64.dll"),
    ],
)
def test_dll_name_mirrors_sounddevice(
    platform_tag: str, arch_bits: str, asio: bool, expected: str
) -> None:
    assert (
        bundled_portaudio_dll_name(platform_tag=platform_tag, arch_bits=arch_bits, asio=asio)
        == expected
    )


def test_preload_does_not_initialise_portaudio() -> None:
    # Importing sounddevice runs Pa_Initialize and freezes the device list; the
    # preload must leave that to the first press so hot-plugged mics still work.
    import inspect

    from dictatem.audio import sounddevice_capture

    source = inspect.getsource(sounddevice_capture.preload_portaudio_library)
    assert "import sounddevice" not in source
