# Native Windows on ARM: what it takes (research for #315)

*Researched 2026-11-07, the day before the v1.0 launch. Sources are PyPI JSON
listings, upstream GitHub repos, PRs, CI runs and artifacts, and official docs.
Each claim links to its source. Lines marked **estimate** are reasoning, not
measurement.*

## TL;DR

- **Only one thing blocks native ARM64: `ctranslate2`.** A dry-run resolve of the
  rest of the stack for `win_arm64` + CPython 3.12 (`uv pip compile
  --python-platform aarch64-pc-windows-msvc --python-version 3.12 --only-binary
  :all:`) succeeds. `faster-whisper` fails only because `ctranslate2` has no
  `win_arm64` wheel on any release, 4.0 through 4.8.5.
- **Upstream already builds a working wheel. It just isn't merged.**
  [CTranslate2 PR #2099](https://github.com/OpenNMT/CTranslate2/pull/2099) (open,
  no maintainer review since 2026-09-10) adds a `windows-11-arm` job. Its CI run
  built and tested `cp39`–`cp314` `win_arm64` wheels in about 23 minutes. That
  build uses **OpenBLAS, which has no `int8` path**, so our CPU tier
  (`base`/`cpu`/`int8`) would **throw** on it and must switch to `float32` on ARM.
- **None of the routes is weekend-sized in a way that is safe for v1.0.** The
  wheel build is a few hours of CI work. Nobody has an ARM device to check
  speed, the VC++ runtime and the float32 change before Sunday, and the gain is
  unmeasured. **Recommendation: ship v1.0 on x64 emulation as it is. Do route 1
  (OpenBLAS wheel, opt-in) in v1.1 and measure it on the reporter's Snapdragon.**
- **A free win:** `sounddevice` 0.5.6 (2026-08-17) now chooses its PortAudio DLL
  with `sysconfig.get_platform()`, not `platform.machine()`. Its `win_amd64`
  wheel now also bundles the ARM64 DLL. That removes the root cause of #181 and
  should unblock #182 (moving the ARM x64 pin from 3.11 to 3.12), separately
  from native ARM.

## Baseline today (ADR-0017)

ARM installs pin `cpython-3.11-windows-x86_64` and run the whole stack under
Prism, at about 1.5× real time on a Snapdragon X (about 5 s of compute for 3.5 s
of audio). See
[ADR-0017](../adr/0017-windows-on-arm-installs-under-x64-emulation.md) and its
two amendments. The CPU [Hardware Tier](../../src/dictatem/hardware/resolver.py)
is `base` / `cpu` / `int8`. The x64 `ctranslate2` wheel ships MKL/oneDNN with
Intel OpenMP (`libiomp5md.dll`) (checked: the 4.8.5 `cp312-win_amd64` wheel's
`ctranslate2.dll` imports `libiomp5md.dll`). Prism gained AVX/AVX2/FMA support
in a late-2025 update
([Neowin](https://www.neowin.net/amp/prism-update-unlocks-avx-avx2-support-for-windows-on-arm/),
secondary source). Microsoft publishes **no overhead figure** for emulated
compute-bound code, and no public benchmark of faster-whisper native versus
emulated on Snapdragon X turned up.

## (3) The rest of the stack: `win_arm64` cp312 wheels (all checked on PyPI)

| Package | Latest | `win_arm64` cp312 wheel? | Notes |
|---|---|---|---|
| [numpy](https://pypi.org/pypi/numpy/json) | 2.5.4 | yes | `win_arm64` since 2.3.0 |
| [PySide6-Essentials](https://pypi.org/pypi/PySide6-Essentials/json) / [shiboken6](https://pypi.org/pypi/shiboken6/json) | 6.12.0 | yes (`cp310-abi3-win_arm64`) | since 6.9.0; our floor `>=6.7` resolves to 6.12 |
| [sounddevice](https://pypi.org/pypi/sounddevice/json) | 0.5.6 | yes (`py3-none-win_arm64`) | see below |
| [pywin32](https://pypi.org/pypi/pywin32/json) | 312 | yes | since 307 |
| [onnxruntime](https://pypi.org/pypi/onnxruntime/json) (faster-whisper's VAD) | 1.31.1 | yes | since 1.24.2 |
| [av](https://pypi.org/pypi/av/json) | 19.0.2 | yes (`cp312-abi3-win_arm64`) | since 17.1.0 |
| [tokenizers](https://pypi.org/pypi/tokenizers/json) | 0.23.3 | yes (`abi3`) | |
| [huggingface-hub](https://pypi.org/pypi/huggingface-hub/json), [tqdm](https://pypi.org/pypi/tqdm/json) | 2.4.0 / 4.70.1 | pure Python | `hf-xet` 1.8.0 has `win_arm64` |
| [pyyaml](https://pypi.org/pypi/pyyaml/json) (ctranslate2 dep) | 6.0.3 | yes | |
| [nvidia-ml-py](https://pypi.org/pypi/nvidia-ml-py/json) | 13.615.71 | pure Python | no NVML on a Snapdragon, so the probe resolves to CPU (ADR-0017) |
| [faster-whisper](https://pypi.org/pypi/faster-whisper/json) | 1.2.1 | pure Python | depends on `ctranslate2>=4.0,<5` |
| **[ctranslate2](https://pypi.org/pypi/ctranslate2/json)** | **4.8.5** (2026-11-02) | **no; never, on any release** | wheel-only, no sdist; 45 files: win_amd64, macOS, manylinux x86_64/aarch64 |

A dry-run `uv pip compile` (uv 0.11.16, `aarch64-pc-windows-msvc`, py3.12,
binary-only) resolves numpy, sounddevice, PySide6-Essentials, nvidia-ml-py,
pywin32, onnxruntime, av, tokenizers, huggingface-hub, sherpa-onnx, onnx-asr and
onnxruntime-qnn to 38 packages with no errors. `faster-whisper>=1.1` alone fails
with *"ctranslate2==4.8.5 has no wheels with a matching platform tag (e.g.,
`win_arm64`)"*. uv offers a native `cpython-3.12.13-windows-aarch64-none` (and
3.11.15).

**sounddevice and the ARM64 PortAudio DLL.** I downloaded and parsed the wheels:

- 0.5.4 and 0.5.5 `win_arm64` wheels bundle `libportaudioarm64.dll`, a real
  ARM64 PE (machine `0xAA64`). Its imports are only system DLLs (WINMM, ole32,
  SETUPAPI, KERNEL32, USER32, ADVAPI32), with no VC++ runtime. Those versions
  chose the DLL with `platform.machine()`, and their `win_amd64` wheel had only
  `libportaudio64bit.dll`, which is the #181 failure.
- **0.5.6** (2026-08-17) chooses by `'arm64' in sysconfig.get_platform()`, which
  reports the *interpreter's* platform, not the silicon's. **Both** the
  `win_amd64` and `win_arm64` wheels now ship both the x64 and ARM64 DLLs, with
  byte-identical hashes to 0.5.5.
- So on a native ARM64 interpreter the bundled DLL should load. ADR-0017's
  original `0x7e` on native ARM cannot be explained from the wheel contents,
  because the DLL has no non-system imports. It needs a single check on the
  device, not engineering work.
- Under x64 emulation, 0.5.6 with Python 3.12 should pick `64bit`, because
  `sysconfig.get_platform()` returns `win-amd64` for an x64 build. If that holds
  on hardware, the 3.11 ARM pin from #181 can go (#182), with
  `sounddevice>=0.5.6`.

## (1) Build our own `ctranslate2` `win_arm64` wheel

### Current state upstream and in the community

- **[Issue #1756](https://github.com/OpenNMT/CTranslate2/issues/1756)**
  (2024-08, open): a user compiled it but found it "very slow". A maintainer
  said Ruy (old, no Windows ARM64) was the cause and suggested OpenBLAS.
- **[PR #2086](https://github.com/OpenNMT/CTranslate2/pull/2086)** (2026-08-21,
  draft, **closed unmerged** 2026-08-24): Ruy plus MSVC OpenMP. INT8 worked
  ("82 passed"). It depended on
  [google/ruy#377](https://github.com/google/ruy/pull/377), which disables
  cpuinfo on Windows ARM64. That PR is draft, closed, and its CLA was never
  signed. It also needed a Ruy TLS-teardown deadlock fix in CTranslate2.
- **[PR #2099](https://github.com/OpenNMT/CTranslate2/pull/2099)** (2026-09-10,
  **open**, unreviewed; a reviewer was pinged 2026-10-12): OpenBLAS 0.3.28 built
  with clang-cl, Ruy and MKL off, `OPENMP_RUNTIME=COMP`, adds `windows-11-arm`
  to the cibuildwheel matrix. It touches 5 files and +46/−5 lines. It **skips
  the int8 tests** because "the OpenBLAS build does not provide the int8 GEMM
  path". Int8 waits on
  [google/ruy#379](https://github.com/google/ruy/pull/379) (open since
  2026-08-26: MSVC NEON intrinsic kernels plus cpuinfo Windows ARM64 detection,
  benchmarked on a Snapdragon X Elite).
- **The PR #2099 CI run succeeded**
  ([run 34470959656](https://github.com/OpenNMT/CTranslate2/actions/runs/34470959656)).
  `build-python-wheels (windows-11-arm, ARM64)` took 23 minutes, and
  `test-python-wheels (windows-11-arm, …cp312…win_arm64.whl)` passed. I pulled
  the artifact (`ctranslate2-4.8.2-cp312-cp312-win_arm64.whl`, 2.0 MB) and
  parsed the PEs:
  - `_ext.pyd`, `ctranslate2.dll` and `openblas.dll` are all ARM64 (`0xAA64`).
  - `ctranslate2.dll` imports `openblas.dll` (bundled) plus **`MSVCP140.dll`,
    `VCRUNTIME140.dll` and `VCOMP140.DLL`, which are not bundled**.
- **Community builds:** [cgohlke/win_arm64-wheels](https://github.com/cgohlke/win_arm64-wheels)
  has had no new release since v2025.7.7. It is cp313-only and has no
  ctranslate2. The [WoA Python tracker](https://github.com/khmyznikov/PyEnv-WoA-State/issues/1)
  doesn't list ctranslate2 at all. Its onnxruntime row still says ❌, which is
  out of date: PyPI has had `win_arm64` wheels since 1.24.2.

### Build feasibility and BLAS choice

- **Feasible, and already shown to work.** Fork CTranslate2 at `v4.8.5` and
  apply PR #2099's 5-file diff. CI is free for this public repo on the
  `windows-11-arm` label
  ([GitHub changelog, GA 2025-08-07](https://github.blog/changelog/2025-08-07-arm64-hosted-runners-for-public-repositories-are-now-generally-available/)).
  CTranslate2's own publish step already triggers on a `v*` tag.
- **OpenBLAS (PR #2099): the choice for now.** It works today and needs no
  patched third-party code. The catch: CTranslate2 lists int8 on ARM64 only
  "with the Ruy backend"
  ([quantization docs](https://opennmt.net/CTranslate2/quantization.html)). And
  in `resolve_compute_type`, an explicit `int8` request on a backend without
  int8 **throws** `"Requested int8 compute type, but the target device or
  backend do not support efficient int8 computation."`
  ([src/types.cc](https://github.com/OpenNMT/CTranslate2/blob/master/src/types.cc)).
  So the ARM CPU tier must request `float32`. That means a new resolver row or
  arch override, plus tests. The weights are about 4× larger, which is fine for
  `base`.
- **Ruy (PR #2086 approach):** native int8 and faster, but we would carry an
  unmerged Ruy patch (cpuinfo off) and CTranslate2's TLS-teardown fix in our
  fork. That is more maintenance. Wait for ruy#379.
- **KleidiAI:** I found no CTranslate2 integration upstream. Not a near-term
  option.
- **Linux aarch64 reference:** upstream's Linux ARM wheels use
  `WITH_RUY=ON` plus `WITH_OPENBLAS=ON` (OpenBLAS 0.3.26)
  ([prepare_build_environment_linux.sh](https://github.com/OpenNMT/CTranslate2/blob/master/python/tools/prepare_build_environment_linux.sh)).
  The native Windows target is that configuration.

### Hosting and installing

- Attach the cp312 wheel to a GitHub Release in our repo, built in our CI with
  build provenance. In `install.ps1`'s ARM branch, replace the x64 pin with
  native `--python 3.12` and add `--with <wheel URL>`, which satisfies
  `faster-whisper`'s `ctranslate2` requirement.
- This bends ADR-0011's "wheels are already signed upstream" posture: we would
  ship one native binary. An ADR amendment is needed.
- **VC++ runtime:** the wheel needs the **ARM64** MSVCP140, VCRUNTIME140 and
  VCOMP140. The x64 wheel also imports MSVCP140 unbundled, so this is not a new
  class of dependency. But the ARM64 redistributable is less common on user
  machines, and a missing DLL gives exactly the `0x7e` failure class. Vendor
  the three DLLs into the wheel (for example with `delvewheel` and an explicit
  include), or have `install.ps1` check for the redistributable.

### Maintenance

- Rebuild when we bump `ctranslate2` or the Python minor version: one tag push
  and about 25 minutes of CI.
- Pin `ctranslate2==<our build>` on ARM only.
- If PR #2099 merges upstream, the wheel appears on PyPI. Our side then shrinks
  to the `install.ps1` change plus the float32 tier change, and we delete the
  fork.

### Effort and speed-up

- **Effort:** about 1–1.5 days of agent work: fork CI (2–3 h), runtime vendoring
  (1–2 h), `install.ps1` ARM branch (2 h), ARM float32 tier and tests (2–3 h),
  ADR-0017/0011 amendments (1 h). After that, **on-device QA** by the Snapdragon
  reporter, the real gate.
- **Speed-up (estimate, unmeasured):** about 1.5–3× faster than emulation, i.e.
  `base` at about 0.5–1× real time. Native NEON float32 GEMM has no
  translation overhead, but float32 gives up the int8 advantage the x64 MKL
  path has under emulation, so the gain may be smaller than "native" suggests.
  With Ruy int8 (later): an **estimated** 3–5×. This must be measured before it
  becomes the default.

## (2) A different engine behind the backend seam (ADR-0013)

The seam already carries a second engine
([`mlx_backend.py`](../../src/dictatem/transcribe/mlx_backend.py), 272 lines,
plus `mlx_models.py`, 146 lines), so adding one is a known shape. Dictatem relies
on `hotwords`/`initial_prompt` vocabulary biasing and VAD
(`faster_whisper_backend.py`). Each candidate is judged against that.

| Engine | `win_arm64` wheel | Fit | Effort | Speed-up vs emulation |
|---|---|---|---|---|
| **[sherpa-onnx](https://pypi.org/pypi/sherpa-onnx/json)** 2.0.1 | yes (`cp312-win_arm64`, 2.2 MB, plus `sherpa-onnx-core` `py3-none-win_arm64`, 16 MB) | Whisper (ONNX exports), Moonshine, NeMo transducers. `from_whisper` has **no prompt or hotwords** argument; hotwords only on transducers with `modified_beam_search` ([offline_recognizer.py](https://github.com/k2-fsa/sherpa-onnx/blob/master/sherpa-onnx/python/sherpa_onnx/offline_recognizer.py)) | 3–5 days: backend, a second model store and format, vocabulary loss on Whisper, QA | **estimate** 2–4× (ORT MLAS int8 on NEON) |
| **[onnx-asr](https://pypi.org/pypi/onnx-asr/json)** 0.12.0 | pure Python on `onnxruntime` (`win_arm64` OK) | Whisper, Parakeet v2/v3, Canary, with VAD. Parakeet RTFx 36 on a 9800X3D, 1.0 on a Cortex-A53 ([README](https://github.com/istupakov/onnx-asr)). No documented prompt or hotwords | 3–5 days, same shape as sherpa-onnx | **estimate** 2–5× (Parakeet is much cheaper per second than Whisper) |
| **Whisper on the NPU** via [onnxruntime-qnn](https://pypi.org/pypi/onnxruntime-qnn/json) 2.7.0 (`win_arm64`, 62 MB) | yes | [Qualcomm Whisper-Base](https://huggingface.co/qualcomm/Whisper-Base) on X Elite NPU: encoder 45.7 ms, decoder 3.7 ms per token (precompiled QNN ONNX); fixed 30 s input, 200-token decoder. We would write the mel front-end, tokenizer and decode loop ourselves. [`qai-hub-models`](https://pypi.org/pypi/qai-hub-models/json) needs torch, and torch has **no `win_arm64` wheel on PyPI**. Binaries are tied to QAIRT and driver versions | 1–2 weeks | **estimate** 10–30× (about 0.2 s for a 3.5 s clip) |
| **whisper.cpp** | [pywhispercpp](https://pypi.org/pypi/pywhispercpp/json) 1.5.1: **no `win_arm64`** (sdist only; open [#146](https://github.com/absadiki/pywhispercpp/issues/146)). Upstream [release b5454](https://github.com/ggml-org/whisper.cpp/releases) ships `whisper-bin-win-cpu-arm64.zip` | Would need our own wheel build (route 1's problem again) or ctypes over the release DLL. Has `initial_prompt`. ADR-0013 already rejected it for packaging cost | 3–5 days | **estimate** 2–4× |
| openai-whisper / transformers | torch has no `win_arm64` on PyPI ([tracker](https://github.com/khmyznikov/PyEnv-WoA-State/issues/1): torch is nightlies-only) | Out | n/a | n/a |

## Is any route weekend-sized for v1.0 (Sunday 8 Nov 2026)?

**No, not safely.** Route 1 with OpenBLAS is the closest. The code and CI are
about a day, and upstream has proven the build. But:

- nobody has ARM hardware to verify it before tomorrow (ADR-0017's amendments
  record that CI cannot catch ARM-only failures, and the #181 regression came in
  exactly that way);
- the forced `float32` tier change and the unbundled ARM64 VC++ runtime are new
  first-run failure modes;
- the speed-up is an estimate, and it could be modest.

Swapping a working, user-verified ARM install for an unverified one the day
before launch is a bad trade.

## Recommendation

1. **v1.0:** keep x64 emulation (ADR-0017) unchanged.
2. **v1.1:** route 1 with OpenBLAS, behind an opt-in such as
   `DICTATEM_ARM_NATIVE=1` in `install.ps1`. Build our cp312 wheel from
   CTranslate2 v4.8.5 plus PR #2099, vendor the VC++ ARM64 runtime, add a
   `float32` ARM CPU tier, and have the Snapdragon reporter measure native
   versus emulated real-time factor. Make it the default only if it is faster.
   Comment on PR #2099 to nudge the merge, because that removes our fork.
3. **Separately, cheap:** pin `sounddevice>=0.5.6` and re-test #182, which would
   lift the 3.11 ARM pin for the x64 path.
4. **Later:** the NPU (QNN) Whisper backend is the only route with an
   order-of-magnitude gain. It is a v1.x feature project, not a port.

## Open questions (need a device)

- The actual native-versus-emulated real-time factor for `base` float32
  (OpenBLAS) on Snapdragon X.
- Whether `libportaudioarm64.dll` from 0.5.6 loads on a native ARM64
  interpreter (the original ADR-0017 `0x7e` cause is unexplained).
- Whether the ARM64 VC++ redistributable is present on stock Snapdragon laptops.
