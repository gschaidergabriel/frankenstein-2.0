# Trigger 7 — C++/GGUF runtime-consolidation audit

Date: 2026-08-30
Worker: GPT-5.6-Sol-TRIGGER7
Claim: `T7-SYS-003/E3_CXX_GGUF_CONSOLIDATED_RUNTIME_RESEARCH`
Status: SOURCE AUDIT COMPLETE; TARGET RUNTIME NOT OBSERVED

## Evidence boundary

This is a source-grounded Trigger-7 architecture/runtime audit. It grants **zero** component benchmark, German end-to-end, Trigger-4 acceptance, or whole-Frankenstein runtime credit.

The parallel `T7-SYS-002` claim remains the sole owner of the `clay-direct-dev` bridge roundtrip and hardware/resource inventory. This lane does not duplicate or alter that execution work.

## Exact upstream source pin

Candidate runtime:

- repository: `CrispStrobe/CrispASR`
- exact audited commit: `1edcc63c830523ec33bdedfe54f338ac56019207`
- observed upstream role: unified C++/ggml/GGUF speech engine with Qwen3-ASR and Qwen3-TTS backends, HTTP server/C ABI, CPU plus accelerator backends, and no Python/PyTorch requirement for the native CLI/runtime path.

Mutable `main` is **not** an evidence identity. Any target build must checkout this exact commit or a newly re-audited successor and record the source tree plus built-binary digest.

## Hypothesis H1

A shared C++/ggml/GGUF deployment substrate for the leading Qwen3 ASR/TTS candidates may improve Frankenstein 2.0 local voice by reducing:

- Python/PyTorch/vLLM package and ABI surface;
- duplicated installer/runtime plumbing;
- cold-process complexity;
- backend-specific observability glue;
- portability friction across CPU/CUDA/Vulkan-class profiles.

This could improve installed-body headroom and failure isolation even when the model weights themselves do not shrink.

## Counterhypothesis C1 — important correction

> One CrispASR server process can keep Qwen3-ASR and Qwen3-TTS simultaneously resident and share one model/runtime memory pool.

**NOT SUPPORTED by the audited source.**

The current server keeps one loaded model and mutex-serializes inference through that model. `--server-workers N` creates N independent model instances and explicitly costs approximately N× model memory. Runtime hot-swap changes the active loaded model; it is not simultaneous ASR+TTS residency.

Therefore the honest candidate is:

```text
COMMON C++/GGUF DEPLOYMENT SUBSTRATE
!= AUTOMATIC SINGLE-INSTANCE ASR+TTS MEMORY SHARING
```

For duplex Frankenstein voice, the baseline falsifier should use separate pinned ASR and TTS instances/processes (or another explicitly proven multi-session arrangement), then measure their combined RSS/VRAM and contention. A custom multi-model loader is justified only if measurements show that process/runtime duplication is a material bottleneck.

## Qwen3-ASR source findings relevant to F2

Audited CrispASR Qwen3-ASR 0.6B GGUF documentation declares German support and Apache-2.0 provenance from the official Qwen model.

Current community conversion/runtime claims include:

- F16 about 1.88 GB;
- Q8_0 about 961 MB;
- Q4_K about 631 MB;
- persistent KV-cache decode;
- native C++ mel/audio-encoder path without torch/librosa/scipy at inference;
- an EN+DE importance-matrix variant.

Most important negative/precision evidence: the project reports that sub-Q8 quantization of the **audio encoder** caused long-audio representation drift and repetition/empty-output failures. The rebaked sub-8-bit packages keep the 18-layer audio tower at Q8_0 while quantizing the LLM body more aggressively.

F2 consequence:

```text
DO NOT TEST "ALL-Q4" AS THE ONLY COMPACT QWEN3-ASR CONFIGURATION.
```

First conservative compact candidate:

- Q8_0 audio tower as packaged by the audited conversion;
- Q4_K or Q8_0 language-model body according to the exact published artifact;
- explicit German language path where supported;
- identical real German fixtures to the official/reference path.

The upstream speed/quality numbers are only upstream measurements and grant no F2 V2/V3/V4 credit.

## Qwen3-TTS source findings relevant to F2

CrispASR exposes a native Qwen3-TTS route within the same C++ speech-engine family. The parent Qwen3-TTS 0.6B family is already on the Trigger-7 German expressive-TTS frontier.

This is attractive primarily for dependency/runtime consolidation, not because source claims prove a latency win. Qwen3-TTS remains autoregressive and upstream CrispASR optimization notes still identify the talker autoregressive loop as an important bottleneck; published upstream RTF/latency must be reproduced on `clay-direct-dev` under the common Trigger-7 receipt.

For first target evidence, avoid model auto-download as the evidence identity. Quarantine and pin the exact talker/codec/voice assets, record SHA-256, and use an explicit German male-voice fixture plus deterministic seed where supported.

## Security / reproducibility rules for the candidate

First evidence-bearing run MUST:

1. build from an exact audited CrispASR git SHA;
2. record compiler/CMake/backend identity and binary SHA-256;
3. avoid `-m auto` or any mutable implicit model resolution;
4. quarantine-download exact GGUF/codec/voice artifacts and hash them;
5. record the converter/release provenance for community GGUF files;
6. keep network access blocked during the actual inference acceptance pass after artifacts are present;
7. record process RSS, system RAM, GPU/VRAM if present, CPU load and warm/cold behavior;
8. feed causal voice timestamps into the existing `t7_voice_receipt.py` contract;
9. preserve crashes, output corruption, repetition, German pronunciation defects and fallback/degradation as first-class negative evidence.

## Highest-information A/B after `T7-SYS-002`

After the hardware receipt exists, run the following sequence on the same machine and fixtures.

### A — ASR runtime A/B

Reference lane:
- current official/reference Qwen3-ASR 0.6B path already admitted by Trigger 7.

Candidate lane:
- pinned CrispASR exact source;
- pinned compact Qwen3-ASR GGUF with Q8 audio tower / declared body quantization.

Measure:
- German WER/CER and named entities/numbers/technical terms;
- endpoint-to-final latency;
- partial stability / false revisions if streaming mode is used;
- cold/warm startup;
- steady and peak RSS/VRAM;
- CPU/GPU utilization;
- 30-minute reliability;
- output identity/quality deltas on long utterances.

### B — TTS runtime A/B

Reference lane:
- current official Qwen3-TTS 0.6B reference path.

Candidate lane:
- pinned CrispASR Qwen3-TTS route with exact talker/codec/voice artifacts.

Measure:
- request-to-first-audio;
- RTF;
- German naturalness and pronunciation;
- stable male acoustic identity;
- prosody/ExpressionVector compatibility;
- cancellation granularity and duplicate-audio risk;
- peak/steady memory and accelerator utilization.

### C — whole resident speech pair

Run ASR and TTS as separate persistent instances and measure them **together**, not one at a time:

- combined RSS/VRAM;
- p50/p95/p99 under overlapping ASR + TTS load;
- barge-in -> actual playback stop;
- model contention and scheduler stalls;
- effect on resident Frankenstein control/state services;
- network-blocked inference.

Only after C can runtime consolidation receive an installed-body claim.

## Promotion rule

Promote CrispASR from source candidate toward Trigger 4 only if measured evidence shows one of the following without violating German quality or causal voice correctness:

1. materially lower resident memory / package footprint;
2. materially lower p95/p99 or better cancellation stability;
3. substantially simpler and more reliable local installation/runtime recovery;
4. better cross-hardware portability at comparable quality;
5. a combination large enough to justify replacing the current reference runtime.

Do **not** promote merely because it is one repository, one binary, GGUF-based, or has favorable README benchmarks.

## Current conclusion

CrispASR is a high-value **deployment-substrate challenger**, not yet a voice-stack winner.

The strongest new insight is architectural rather than benchmark-based:

```text
UNIFY RUNTIME/DEPENDENCIES FIRST
MEASURE MODEL RESIDENCY SEPARATELY
DO NOT ASSUME ONE-BINARY => ONE-MODEL-INSTANCE => LOWER TOTAL RAM
```

Its Qwen3-ASR mixed-precision evidence is useful enough to change the first compact ASR falsifier: preserve high precision in the audio tower rather than naively quantizing every tensor to Q4.

Next dependency remains the real `T7-SYS-002` hardware/bridge receipt. Once that lands, execute A/B/C above; until then runtime credit stays zero.
