"""Pure-core sample-rate conversion — native-rate mono float32 -> 16 kHz mono.

No audio-stack import; depends only on numpy + stdlib, so it is unit-testable on
every CI platform (unlike an on-device AVAudioConverter). The native macOS
capture backend (``MacAudioCapture``, #161) resamples each AVAudioEngine tap
block through here before appending to the shared :class:`AudioBuffer`; the
Windows WASAPI switch (#184) reuses the identical "native rate -> 16 kHz" path.

Why a polyphase FIR and not the spike's linear interp: downsampling 44.1/48 kHz
to 16 kHz is a >2x decimation, so anything above the 8 kHz destination Nyquist
**aliases** back into the speech band unless it is low-pass filtered out first.
Linear interpolation is a poor anti-alias filter; a windowed-sinc polyphase
resampler filters and resamples in one rational ``L/M`` step with proper
stopband rejection (the quality the RESOLUTION.md §4D spike deferred to
production).

Two entry points over the same core:

* :class:`PolyphaseResampler` — **streaming**. ``process(block)`` carries filter
  state across calls, so feeding audio in arbitrary tap-sized blocks yields the
  *same* samples as one batch call (the ``streaming == batch`` invariant the
  tests pin). The backend needs this: it must append 16 kHz to the buffer *as
  each block arrives* so the daemon's live level/duration/idle reads work during
  recording — resampling only at flush would leave those dead against an empty
  buffer.
* :func:`resample` / :func:`resample_to_16k` — **stateless** convenience for a
  whole signal in one shot (one ``process`` call), used by the unit tests and by
  any caller that already has the full recording.
"""

from __future__ import annotations

from fractions import Fraction

import numpy as np

from dictatem.types import SAMPLE_RATE, AudioChunk

# Half-length of the anti-alias prototype filter, in destination-rate samples
# each side of centre. 16 gives ~40 dB stopband with a Hamming window — ample
# for speech, and cheap: the polyphase form only ever evaluates one phase per
# output sample regardless of the (possibly large) upsampling factor L.
_FILTER_HALF_LEN = 16


def _design_polyphase(upsample: int, downsample: int, half_len: int) -> np.ndarray:
    """Build the polyphase tap matrix for a rational ``upsample/downsample`` rate.

    Returns ``Hmat`` of shape ``(upsample, taps_per_phase)`` where
    ``Hmat[p, t]`` is prototype tap ``h[p + upsample * t]``. Output sample ``j``
    (phase ``p = (j*M) % L``, input index ``i = (j*M) // L``) is then simply
    ``sum_t Hmat[p, t] * x[i - t]`` — a single length-``taps_per_phase`` dot,
    which is what makes an ``L`` of a few hundred (44.1 kHz) affordable.
    """
    max_lm = max(upsample, downsample)
    # Cutoff at the lower of the two Nyquists, expressed in cycles/sample of the
    # (conceptual) upsampled rate: 0.5 / max(L, M).
    cutoff = 0.5 / max_lm
    num_taps = 2 * half_len * max_lm + 1  # odd -> exact linear-phase symmetry
    n = np.arange(num_taps, dtype=np.float64)
    centre = (num_taps - 1) / 2.0
    # Ideal low-pass impulse response (2*fc*sinc(2*fc*t)) times a Hamming window.
    h = 2 * cutoff * np.sinc(2 * cutoff * (n - centre)) * np.hamming(num_taps)
    # Normalise DC gain to L so the interpolation restores the amplitude lost to
    # the conceptual zero-stuffing (each of the L phases then sums to ~1).
    h *= upsample / h.sum()

    taps_per_phase = int(np.ceil(num_taps / upsample))
    pad = taps_per_phase * upsample - num_taps
    if pad:
        h = np.concatenate([h, np.zeros(pad, dtype=np.float64)])
    # h[t*L + p] laid out as [t, p]; transpose so phase p indexes the first axis.
    return h.reshape(taps_per_phase, upsample).T.astype(np.float32, copy=True)


class PolyphaseResampler:
    """Streaming rational resampler from ``src_rate`` to ``dst_rate``.

    Construct one per recording (the native input rate can differ run-to-run, so
    the backend reads it at ``start()`` and builds a fresh resampler — see #161
    §2). ``process`` may be called with any block length, including empty; the
    carried state guarantees the concatenation of per-block outputs equals a
    single whole-signal call.
    """

    def __init__(self, src_rate: float, dst_rate: int = SAMPLE_RATE) -> None:
        self._passthrough = int(round(src_rate)) == int(dst_rate)
        if self._passthrough:
            self._L = self._M = 1
            self._taps_per_phase = 1
            self._Hmat = np.ones((1, 1), dtype=np.float32)
        else:
            # limit_denominator bounds the filter size for any exotic reported
            # rate; standard 44.1/48 kHz reduce exactly (160/441, 1/3).
            ratio = Fraction(int(dst_rate), int(round(src_rate))).limit_denominator(2000)
            self._L = ratio.numerator
            self._M = ratio.denominator
            self._Hmat = _design_polyphase(self._L, self._M, _FILTER_HALF_LEN)
            self._taps_per_phase = self._Hmat.shape[1]
        # Filter history: the last (taps_per_phase - 1) input samples, so the
        # next block has the context the FIR needs. Zero-init == left zero-pad,
        # matching a batch call (keeps streaming == batch exact).
        self._hist = np.zeros(self._taps_per_phase - 1, dtype=np.float32)
        self._in_count = 0  # total input samples consumed (global index base)
        self._next_j = 0  # next output index to emit

    def process(self, block: AudioChunk) -> AudioChunk:
        """Resample one input block; return the 16 kHz samples it completes."""
        block = np.ascontiguousarray(block, dtype=np.float32)
        if self._passthrough:
            self._in_count += block.size
            return block.copy()
        if block.size == 0:
            return np.zeros(0, dtype=np.float32)

        L, M, q = self._L, self._M, self._taps_per_phase
        x_ext = np.concatenate([self._hist, block])
        ext_start = self._in_count - self._hist.size  # global index of x_ext[0]
        new_in_count = self._in_count + block.size

        # Largest output j whose newest needed input i(j) = (j*M)//L is available
        # (<= new_in_count - 1): j <= (new_in_count*L - 1) // M.
        j_max = (new_in_count * L - 1) // M
        js = np.arange(self._next_j, j_max + 1)

        if js.size:
            jm = js * M
            ii = jm // L  # newest input index each output reads
            pp = jm % L  # polyphase phase each output selects
            # window[n, t] = x_ext[(ii[n] - t) - ext_start]; taps run x[i], x[i-1]...
            local = (ii - ext_start)[:, None] - np.arange(q)[None, :]
            out = np.sum(x_ext[local] * self._Hmat[pp], axis=1, dtype=np.float32)
        else:
            out = np.zeros(0, dtype=np.float32)

        self._next_j = int(js[-1]) + 1 if js.size else self._next_j
        self._in_count = new_in_count
        # Retain the last (q - 1) inputs as history for the next block. Always
        # enough: by the maximality of j_max the next output's newest input index
        # i(next_j) is >= in_count, so its oldest tap (i - q + 1) never predates
        # in_count - (q - 1) — the window we keep. (Holds for up- and
        # down-sampling; in practice this backend only ever downsamples to 16k.)
        keep = q - 1
        self._hist = x_ext[-keep:].copy() if keep else np.zeros(0, dtype=np.float32)
        # asarray keeps the declared float32 return type: np.sum(axis=1) widens
        # to include a scalar in the type checker's view even though it is 1-D.
        return np.asarray(out, dtype=np.float32)


def resample(samples: AudioChunk, src_rate: float, dst_rate: int = SAMPLE_RATE) -> AudioChunk:
    """Resample a whole mono float32 signal from ``src_rate`` to ``dst_rate``.

    Stateless: one :class:`PolyphaseResampler` pass over the full signal. Empty
    in -> empty out; ``src_rate == dst_rate`` returns a float32 copy unfiltered.
    """
    return PolyphaseResampler(src_rate, dst_rate).process(samples)


def resample_to_16k(samples: AudioChunk, src_rate: float) -> AudioChunk:
    """Resample a whole mono float32 signal to Dictatem's 16 kHz contract."""
    return resample(samples, src_rate, SAMPLE_RATE)
