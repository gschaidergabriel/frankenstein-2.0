# Trigger 7 — OpenASR Qwen3-ASR 0.6B q8 packaging/runtime audit

Date: 2026-08-30
Research ID: `T7-ASR-002`
Objective: `E2_OPENASR_QWEN3_06B_Q8_PACKAGING_AUDIT`
State: SOURCE_AUDIT_COMPLETE / CONDITIONAL_VPS_CHALLENGER
Worker: GPT-5.6-Sol-TRIGGER7

## Evidence boundary

This is source/security/dependency/provenance evidence only. No `clay-direct-dev` execution was performed by this objective. No German WER, target RTF, target RAM/VRAM, streaming-latency, V2/V3/V4, Trigger-4, or acceptance credit is granted.

## Exact runtime pin inspected

- runtime repository: `QuintinShaw/openasr`
- inspected source commit: `b7b3f96accef024d9abda6206cefb5faa88fb104`
- OpenASR registry model file at that commit: `model-registry/models/qwen3-asr-0.6b.toml`
- registry model id: `qwen3-asr-0.6b`
- default published quantization: `q8_0`
- registry declares German (`de`) among supported languages
- registry declares Apache-2.0 for this pack family

The runtime is under rapid active development. The newest inspected commits include GPU residency, decode/KV evidence and resource-admission changes. Therefore any later benchmark MUST bind the exact OpenASR runtime commit/build and pack digest; `latest` is not an admissible benchmark identity.

## Pack source and published profile

OpenASR's Hugging Face card for `OpenASR/qwen3-asr-0.6b` states that its `.oasr` packs are converted from `Qwen/Qwen3-ASR-0.6B` and run natively without Python inference. The published q8_0 profile is:

- file: `qwen3-asr-0.6b-q8_0.oasr`
- approximate file size: 1.01 GB
- published isolated RAM peak: 2.86 GB
- published M1 CPU RTF: 0.55
- published M1 GPU RTF: 0.27
- published JFK quantization drift vs that pack family's fp16: 0.0% word-level WER

These are upstream OpenASR measurements, not Frankenstein measurements. The JFK comparison is explicitly quantization drift against the OpenASR fp16 conversion, not absolute German recognition accuracy.

## Critical identity finding — DO NOT call this a quantized copy of the current F2 `-hf` baseline

The current Frankenstein Trigger-7 candidate matrix names `Qwen/Qwen3-ASR-0.6B-hf` as the official Qwen3-ASR challenger. OpenASR instead states that its pack was converted from `Qwen/Qwen3-ASR-0.6B` (without `-hf`). These two current official Qwen repositories are not byte-identical artifacts:

- `Qwen/Qwen3-ASR-0.6B/model.safetensors`: approximately 1.88 GB; current surfaced SHA-256 `79d6cbd4c98c7bbffe9db2edac07f56cd6637d0d5944b27f6c2b8353840323ea`.
- `Qwen/Qwen3-ASR-0.6B-hf/model.safetensors`: approximately 1.56 GB; current surfaced SHA-256 `d3f212dd20abecd315d830bc54ae3865e56ebfc3276484e57b771288ba27fd35`.

Therefore:

`OPENASR_Q8 != PROVEN_QUANTIZATION_OF_F2_QWEN3_ASR_06B_HF_BASELINE`

Treat OpenASR q8 as a distinct Qwen-family runtime/checkpoint challenger unless an explicit conversion/equivalence receipt proves otherwise. A direct quality delta between the `-hf` baseline and OpenASR q8 would conflate runtime/packaging/quantization with checkpoint representation differences.

## Runtime architecture/security findings

Positive source findings at the inspected OpenASR commit:

- native Rust/ggml-class runtime; no Python required for `.oasr` inference;
- GGUF-backed pack path and mmap-oriented weight handling;
- embedded signed public catalog fallback is present in source;
- catalog/model metadata is typed and versioned;
- runtime source contains explicit resource/admission and backend-evidence machinery;
- current development includes cancellation, KV/decode, residency and GPU correctness work;
- no cloud inference is required for the local execution path after artifacts are present.

Packaging/operational policy for F2:

- prefer source build at an exact commit or an exact release artifact with digest;
- do not use a moving one-line installer as evidence identity;
- retrieve the model through Trigger-7 quarantine/download controls and preserve the final pack SHA-256;
- run pack/catalog verification before execution;
- disable/block outbound model inference during acceptance runs;
- preserve exact runtime binary hash, pack hash, backend, CPU/GPU driver/runtime identity and command line in the voice receipt.

## Backend evidence — major target gate

OpenASR's own Qwen family audit (inspected at runtime commit `b7b3f96...`) reports:

- CPU: supported/verified on its cited M1 evidence;
- Metal: supported/verified on its cited M1 evidence;
- CUDA: untested for the Qwen family in that audit;
- Vulkan: untested;
- HIP: untested.

The same audit explicitly says target/backend-bound correctness receipts are the unlock condition for the untested discrete-GPU paths.

Consequences for Frankenstein:

1. Do not import M1 Metal numbers into `clay-direct-dev`.
2. Wait for the exact Trigger-7 hardware receipt before selecting CPU/CUDA/Vulkan/HIP test mode.
3. If the target is CUDA/HIP/Vulkan, first run a bounded correctness/parity smoke before German performance comparison.
4. A CPU-only comparison remains useful if it fits the whole-Frankenstein resident envelope, but it must be measured on target hardware.

## Hypothesis / counterhypothesis

H1: OpenASR q8 can lower resident Qwen3-ASR memory and dependency overhead enough to improve the fully-local German voice Pareto frontier while preserving acceptable recognition quality.

Counterhypothesis: the apparent gain is M1-specific and/or the distinct non-`-hf` checkpoint plus runtime behavior produces no German target advantage; on the actual VPS backend it may be slower, unsupported, or less accurate than the official `-hf` path, Nemotron, or donor Whisper.

## Cheapest high-information discriminator after the hardware receipt

Only if backend support is compatible:

1. pin OpenASR runtime commit/build;
2. quarantine and hash q8_0 pack;
3. verify pack/catalog metadata;
4. run a short correctness smoke with outbound model networking blocked;
5. use the identical pinned German room-audio set already planned for Qwen/Nemotron/Whisper;
6. measure WER/CER, partial stability, finalization latency, RTF, RSS/PSS/VRAM, startup/warmup and cancellation;
7. compare whole-Frankenstein headroom, not ASR in isolation;
8. record via Trigger-7 causal receipts.

## Decision

`CONDITIONAL_PROMOTE_TO_LATER_VPS_CHALLENGER`

OpenASR q8 is worth retaining because its native local runtime, q8 footprint and cancellation/resource engineering could materially improve the local voice stack. It is NOT promoted as the official Qwen baseline and gets zero target/German benchmark credit now.

Promotion gate:

`VPS_HARDWARE_RECEIPT + BACKEND_COMPATIBILITY + EXACT_RUNTIME_PIN + PACK_DIGEST + GERMAN_TARGET_BENCHMARK`

If the target backend is one of the currently unverified Qwen GPU paths, add a target correctness/parity smoke before performance credit.

## Source references inspected

- `QuintinShaw/openasr@b7b3f96accef024d9abda6206cefb5faa88fb104`
- `model-registry/models/qwen3-asr-0.6b.toml`
- `docs/model-audits/qwen.md`
- `crates/openasr-core/src/registry.rs`
- `OpenASR/qwen3-asr-0.6b` model card/tree on Hugging Face
- `Qwen/Qwen3-ASR-0.6B` model artifact metadata on Hugging Face
- `Qwen/Qwen3-ASR-0.6B-hf` model artifact metadata on Hugging Face
