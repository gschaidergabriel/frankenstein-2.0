# Trigger 7 — Deep Run 03 — Native speech runtime convergence + German ASR risk gate

Date: 2026-08-30
Worker: GPT-5.6-Sol-TRIGGER7
Status: SOURCE FRONTIER ADVANCED; TARGET/VPS RUNTIME STILL NOT OBSERVED
Predecessor: `2026-08-29_TRIGGER7_DEEP_RUN_02.md`

## 0. Evidence boundary

This run resumed the canonical Trigger-7 cursor. It refreshed current F2 authority and execution authority before research. Owner VPS execution remains authorized through the established bridge/self-hosted runner, but this worker did not observe a successful new `clay-direct-dev` job, model download, hardware inventory, model load, German runtime benchmark or F2 end-to-end voice run.

The last preserved runner evidence available during this run was a pre-job transport/runner-assignment failure with zero jobs observed. That negative evidence is infrastructure evidence, not a model/product failure and is not assumed to describe the runner's current health without a new roundtrip.

Therefore:

```text
VPS_HARDWARE_RECEIPT = NOT_OBSERVED_THIS_RUN
MODEL_DOWNLOAD_RECEIPT = NOT_OBSERVED_THIS_RUN
GERMAN_RUNTIME_BENCHMARK = NOT_OBSERVED_THIS_RUN
F2_RUNTIME_CREDIT = 0
TRIGGER4_ACCEPTANCE_CREDIT = 0
```

## 1. New runtime-substrate candidate: NVIDIA NeMo-Speech.cpp

A new high-value systems option is now source-pinned: NVIDIA `NeMo-Speech.cpp` release v0.1.0 / main revision `4f9676226f667d14608487df744f375db87127f8`.

Upstream currently exposes one native C++ speech runtime family covering:

- Nemotron 3.5 / other ASR paths;
- VAD and endpointing;
- MagpieTTS/NanoCodec TTS;
- local HTTP APIs;
- realtime WebSocket transcription;
- a native C API;
- CPU, CUDA, Vulkan and Metal backends.

Trigger-7 interpretation:

```text
NEMO_SPEECH_CPP = SPEECH_RUNTIME_SUBSTRATE_CANDIDATE
NEMO_SPEECH_CPP != FRANKENSTEIN_IDENTITY
NEMO_SPEECH_CPP != VOICEINTENT_OR_GWT_AUTHORITY
NEMO_SPEECH_CPP != CANONICAL_MEMORY
NEMO_SPEECH_CPP != EFFECT_AUTHORITY
```

Why this matters: if target benchmarks hold, one native runtime can reduce Python/framework duplication and model-hosting fragmentation across parts of the local speech path while preserving Frankenstein's deterministic turn/state/effect boundary above it. That is a hypothesis until actual target residency and tail latency are measured.

## 2. Nemotron 3.5 German ranking revised downward pending target falsification

Deep Run 02 treated Nemotron 3.5 ASR Streaming 0.6B as the first German streaming falsifier based largely on upstream model support and benchmark data. Fresh negative evidence now changes the prior.

A public German-language report against `nvidia/nemotron-3.5-asr-streaming-0.6b` documents substantial errors in ordinary words, compounds and terminology even at the largest discussed streaming context. NVIDIA's response recommends:

1. word boosting / context biasing;
2. n-gram LM fusion;
3. fine-tuning as the durable fix.

This is not F2 evidence and does not demote Nemotron out of the benchmark. It does remove any source-only presumption that aggregate German WER predicts Frankenstein-room quality.

The local Q8_0 artifact is now source-pinned for a future clean target run:

```text
model: nvidia/nemotron-3.5-asr-streaming-0.6b
revision: 2e83bd1da4f3e470babc6711d6ce7f9436dced74
artifact: nemotron-3.5-asr-streaming-0.6b.q8_0.gguf
upstream_size_display: 742 MB
sha256: a5c435f294eea8f88ce68dd27b8c3bfea7f777cb2fbba04fcd30eaa555f429ae
```

No local hash verification has occurred yet.

### Revised ASR discriminator

Run the same pinned German room corpus through:

- Nemotron 3.5 Q8_0 through NeMo-Speech.cpp;
- Qwen3-ASR 0.6B;
- donor Whisper baseline.

For Nemotron:

- sweep 80/160/320/560 ms right context;
- keep 1120 ms as diagnostic upper point rather than default realtime mode;
- first measure without term assistance;
- then add a separately labelled context-biasing/word-boosting condition using the real Frankenstein names/technical vocabulary;
- compare WER/CER, terminology accuracy, partial stability, endpoint-to-final latency, whole-turn latency and resident resource cost.

Only if the assisted condition improves German terminology without destroying realtime tails does it remain a strong production candidate. Fine-tuning must be a separate bounded claim because it changes the model and attribution question.

## 3. DualTurn streaming identity must be fenced

Fresh source history shows a material streaming correction in `anyreach-ai/dualturn-endpointing`.

The earlier streaming ONNX path zero-initialized `audio_ctx`, which caused reported streaming/offline divergence around 0.17–0.66. A later rebuild changed the dynamic context behavior and reports approximately 0.019 residual. Documentation was also corrected from a stronger `bit-exact` wording to `strictly causal + decision-equivalent`, with approximately 0.02–0.03 floating-point residual versus batch.

Trigger-7 consequence:

```text
DUALTURN_BENCHMARK_REQUIRES_CORRECTED_STREAMING_GRAPH_IDENTITY
OLD_STREAMING_GRAPH != COMPARABLE_CURRENT_GRAPH
SOURCE_CLAIM_BIT_EXACT = RETIRED_FOR_BATCH_COMPARISON
```

Any German EOT/VAD/FVAD experiment must pin the corrected graph/helper identity before benchmarking. This is exactly the kind of source evolution that can otherwise create false before/after conclusions.

## 4. Architecture delta

The near-term production hypothesis becomes slightly more concrete:

```text
Audio/AEC
  -> deterministic channel ownership
  -> native speech runtime candidate (ASR + low-level VAD/endpoint primitives)
  -> Frankenstein semantic turn controller / VoiceIntent / GWT / WAIT
  -> provider-neutral local cognition
  -> deterministic state/effect boundary
  -> native or separately measured streaming TTS
  -> cancellable playback tap
  -> heard-output receipt
  -> VoiceOutcome / UnifiedDB
```

NeMo-Speech.cpp may host several low-level speech mechanisms in one process, but it must not swallow the semantic/causal authority that makes the voice organ part of the same Frankenstein.

## 5. Competing hypotheses after this run

### H1 — unified native speech runtime wins

A single native runtime reduces framework overhead, resident duplication and inter-process jitter enough to improve p95/p99 without harming German quality.

Falsifier: whole-system target measurements show no tail/residency advantage or lower German quality than the best modular alternatives.

### H2 — model quality dominates runtime consolidation

Separate best-of-breed ASR/TTS runtimes remain superior because German quality differences dominate any native-runtime simplification.

Falsifier: NeMo-Speech.cpp-hosted bundle reaches equal German quality while materially improving tails/resource residency.

### H3 — Nemotron's German issue is domain/context, not a general blocker

The observed German failures are substantially repaired by F2-specific context biasing and do not require full fine-tuning.

Falsifier: context biasing still loses to Qwen3-ASR/Whisper on the same F2 corpus or adds unacceptable latency/complexity.

## 6. Exact next executable sequence

1. Re-enter the existing bridge/self-hosted runner and obtain a fresh `clay-direct-dev` roundtrip receipt; classify concrete transport failure only if actually observed.
2. Run `t7_hardware_inventory.py` inside the sandbox and record whole-Frankenstein RAM/VRAM/storage/audio/backend headroom.
3. Quarantine-download and locally hash the pinned Nemotron Q8_0 artifact; verify hash against the source pin.
4. Pin/download the official Qwen3.5-4B reference plus clearly identified local conversion used for runtime comparison; do not label a third-party GGUF as an official quantization.
5. Run the three-way German ASR benchmark with Nemotron baseline + context-biasing condition.
6. Pin only the corrected DualTurn streaming graph/helper and run German mid-sentence-pause/backchannel/overlap tests.
7. Continue Qwen3-TTS-first TTS comparisons under whole-resident-body constraints.
8. Feed every executed voice run through `t7_voice_receipt.py`.
9. Route only real E3/V4 evidence to Trigger 4; Trigger 7 grants no V6 acceptance.

## 7. Conclusion

Deep Run 03 does not claim runtime progress. It does reduce the next-runtime search space and removes two sources of false confidence:

- aggregate German benchmark numbers are insufficient for Nemotron production ranking;
- stale DualTurn streaming artifacts are not comparable with the corrected current path.

The highest-value remaining gate is still real target execution, but the first target run is now better specified: hardware receipt -> exact artifact pins -> identical German corpus -> baseline/assisted Nemotron vs Qwen3-ASR vs Whisper -> causal voice receipts.
