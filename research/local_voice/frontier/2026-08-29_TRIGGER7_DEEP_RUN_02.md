# Trigger 7 — Deep Run 02 — Local target residency + benchmarkable German voice

Date: 2026-08-29
Worker: GPT-5.6-Sol-TRIGGER7
Status: SOURCE/ARCHITECTURE/HARNESS FRONTIER ADVANCED; TARGET/VPS RUNTIME STILL NOT OBSERVED
Predecessor: `2026-08-29_TRIGGER7_DEEP_RUN_01.md`

## 0. Evidence boundary

This run resumed the admitted cursor rather than restarting. Current F2 product law was re-read before research.

Observed project truth:

- Frankenstein 2.0's finished baseline product is the **local installed host runtime**.
- GRID10/GWT/J-Space/HCU control semantics, UnifiedDB/state/memory, local core cognition, Voice, Perception/Retina where admitted, and Effects belong to the same local product body.
- A VPS/remote HCU/Claude provider may extend or accelerate the installed entity, but may not be required for baseline local boot/state/basic cognition/local voice.
- Trigger 7 therefore may not optimize voice as an isolated appliance that consumes all target RAM/VRAM and stops the rest of Frankenstein.

No target/VPS shell became available in this worker environment. Therefore this run claims **zero V2/V3/V4 runtime credit**. No target model download, model load, German runtime benchmark, or quality-parity run was observed.

## 1. Deepest architecture correction: benchmark the whole resident body

Run 01 correctly moved the voice path toward speculative, cancellation-safe duplex operation. Run 02 adds a missing systems constraint:

```text
VOICE_CANDIDATE_FITS_ALONE != FRANKENSTEIN_FITS_INSTALLED
```

The target selection problem is not:

> Which ASR + LLM + TTS can run on the machine?

It is:

> Which permanently/strategically resident model set can coexist with GRID10/GWT/J-Space/HCU control, UnifiedDB/memory, pulse/background services, admitted Retina/Perception services, audio conditioning, turn control and host adapters while keeping realtime tails stable?

Consequences:

1. measure **resident-set peak and steady memory**, not model file size only;
2. measure cold/warm model transitions and contention;
3. reserve headroom for the cognitive body before awarding a voice configuration;
4. prefer a smaller model that keeps p95/p99 stable over a larger model that causes swap/eviction or serial loading;
5. make model profile selection capability-adaptive at install/first-run rather than hardcoding one universal stack.

The hardware inventory tool was expanded in this run to detect NVIDIA, AMD/ROCm, Vulkan/OpenCL, Apple hardware probes and real audio/device surfaces rather than treating `nvidia-smi` as the definition of a target.

## 2. Benchmark infrastructure created

New predeclared benchmark:

`research/local_voice/benchmarks/T7_GERMAN_REALTIME_VOICE_BENCHMARK_V1.md`

New machine-readable summarizer:

`research/local_voice/tools/t7_voice_receipt.py`

It records/derives:

- speech-end -> first audible audio;
- endpoint -> ASR final;
- inference TTFT;
- inference -> first speakable clause;
- TTS request -> first audio ready;
- audio-ready -> actual playback;
- barge-in -> actual playback stop;
- hidden outbound model/ASR/TTS counters;
- barge-in without generation cancellation;
- false durable commit of unheard output;
- duplicate/replayed audio.

The tool refuses causal timestamp inversions and does not self-award V4/V5/V6. Four local unit tests passed before persistence in this worker environment.

## 3. ASR frontier after fresh research

### A1 — NVIDIA Nemotron 3.5 ASR Streaming 0.6B remains the first streaming falsifier

Primary source:
- `nvidia/nemotron-3.5-asr-streaming-0.6b`

Current upstream evidence:
- German `de-DE` is in the transcription-ready tier.
- The model exposes right-context settings from 80 ms through 1.12 s, creating a direct latency/accuracy sweep rather than one fixed streaming mode.
- Current card reports German WER with explicit language input of approximately 9.81 / 9.21 / 8.83 / 8.42 / 8.31 across 80 / 160 / 320 / 560 / 1120 ms right-context respectively; auto-detect is similar. These are upstream results, not F2 results.

Decision:
- benchmark **at least 80, 160, 320 and 560 ms** on the same real German F2 audio;
- do not choose 1.12 s merely for WER if it destroys turn timing;
- report partial stability and finalization latency, not WER alone.

### A2 — Qwen3-ASR 0.6B / 1.7B remain mandatory challengers

They stay on the frontier because German and streaming/offline operation are explicit and the size ladder lets us test quality gain per resident byte. No replacement decision is justified from source evidence.

### A3 — German Whisper Turbo remains the continuity baseline

Its value is not novelty; it anchors comparison to the donor implementation family and gives a fallback if newer streaming stacks have fragile dependencies or worse room robustness.

## 4. Turn-taking frontier: two-channel causal endpointing is now a first-class candidate

### DualTurn Endpointing

Primary source:
- `anyreach-ai/dualturn-endpointing`

Source facts observed:
- small causal audio-only endpointing layer over Mimi features;
- user + agent channels are listened to concurrently;
- outputs user EOT plus VAD/FVAD every 80 ms;
- ONNX streaming path is published, so the runtime can avoid `trust_remote_code` if the shipped graph/helpers are separately audited/pinned;
- upstream reports roughly 52 ms per 80 ms tick on its four-thread CPU setup; a 240 ms graph trades slower reaction for lower compute duty.

Important limitation:
- current model metadata is English-oriented. Its **architecture** is highly relevant; German pause/EOT quality is unproven.

Decision:
- add a German-specific falsifier with mid-sentence pauses, self-corrections, backchannels and own-output overlap;
- compare 80 ms vs 240 ms cadence in whole-system CPU contention, not endpoint model isolation.

### Endpoint Anticipation

The 2026 Endpoint Anticipation paper predicts turn endings before reactive EOT and reports about 505 ms average latency reduction in the upstream Unmute integration with additional speculative compute.

F2 decision remains:

```text
endpoint predictor proposes early branch
-> provider/TTS may begin speculative work
-> deterministic generation id owns validity
-> later user speech can invalidate branch
-> unheard/unplayed material never becomes durable spoken outcome
```

This is a latency-hiding technique, not permission for speculative state/effect commit.

## 5. TTS frontier expanded substantially

### T1 — Qwen3-TTS 12Hz 0.6B remains the first compact quality candidate

Primary source:
- `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`
- source repository `QwenLM/Qwen3-TTS`, observed GitHub main `022e286b98fbec7e1e916cb940cdf532cd9f488e`

Current source facts:
- Apache-2.0;
- German among 10 languages;
- natural-language tone/rhythm/emotion control;
- official card advertises end-to-end synthesis latency as low as 97 ms under its setup;
- current HF tree is safetensors-based and the main model file is ~1.81 GB.

Reason it remains first: size/control/German/streaming combination maps cleanly to `ExpressionVector` and portable deployment research.

### T2 — dots.tts is promoted to the **high-quality local challenger tier**

Primary sources:
- `studio-dots-ai/dots.tts`
- observed GitHub main `32407a55228630475c48ecdb2c4e2c0f9c09e030`
- `dots-studio/dots.tts-base` and MF/SOAR checkpoints

Source facts:
- Apache-2.0;
- 2B fully continuous autoregressive TTS;
- multilingual evaluation includes German;
- MF/SOAR and SGLang-Omni streaming paths exist;
- current project documents CPU/CUDA/Vulkan/Metal third-party ports as well as Apple MLX ports.

Interpretation:
- significantly heavier than Qwen3-TTS 0.6B, but important because quality may justify the cost on stronger target profiles;
- H100/H800-class latency numbers are not portable to the actual F2 target and grant no runtime credit.

### T3 — MOSS-TTS-Realtime 1.7B is promoted, but its latency claim gets a reproducibility warning

Primary source:
- `OpenMOSS-Team/MOSS-TTS-Realtime`
- source repo `OpenMOSS/MOSS-TTS`, observed GitHub main `58b20a0d5fcc6766658d50967a90a9d890009a46`

Source facts:
- German among 20 declared languages;
- context-aware multi-turn streaming architecture;
- upstream reports 180 ms TTFB after warmup and RTF 0.51 on one L20 GPU.

Negative evidence:
- public issue #203 states evaluators could not reproduce the published number exactly because fixture, sample count, aggregation and benchmark script were not supplied with sufficient precision.

Decision:
- retain as candidate;
- treat 180 ms / 0.51 as an upstream hypothesis only;
- require our common receipt before any comparison.

### T4 — NVIDIA MagpieTTS Multilingual 357M becomes a compact stable-voice challenger

Primary source:
- `nvidia/magpie_tts_multilingual_357m` v2607

Source facts:
- 364M parameters;
- German supported;
- current v2607 card reports German CER 0.80 and speaker-similarity 0.742 on its held-out evaluation;
- NVIDIA Open Model License;
- zero-shot voice-cloning was removed in v2607.

Interpretation:
- attractive footprint;
- cannot assume it can clone the old Frank voice;
- must audition fixed male voices/adaptation route and license implications.

### T5 — MOSS-TTS-Nano 100M is a latency/degraded-mode falsifier, not a quality winner yet

Source facts:
- Apache-2.0;
- 100M parameters;
- German declared among 20 languages;
- streaming and CPU-local operation are explicit.

However, tiny size and declared language support do not imply natural German Frank-quality. It belongs in the low-resource floor experiment until pronunciation/naturalness pass.

### T6 — Fun-CosyVoice3 / Chatterbox remain on frontier

No evidence in Run 02 demoted them. They continue to cover voice cloning/expression and portability trade-offs.

## 6. Local dialogue LLM: execution order corrected

Run 01 predeclared a pinned abliterated Qwen3.5-4B Q4 as the first server candidate. That is operationally simple, but the research objective is **German realtime conversational quality**, not refusal removal.

Run 02 changes the benchmark order:

1. **official `Qwen/Qwen3.5-4B` local reference/quantization first**;
2. same-size abliterated Qwen3.5-4B under identical settings;
3. Claude-reasoning-distilled/abliterated challenger later;
4. fast 0.8B–2B shell only for tightly bounded interaction acts if evidence supports it.

Why:
- abliteration is an intervention and may change useful behavior as well as refusals;
- without the official baseline we cannot attribute quality/latency/state differences;
- the provider remains candidate cognition, never state/effect authority.

The official Qwen3.5-4B source remains Apache-2.0 and is directly usable through current local inference ecosystems. Exact model revision/quantization must be re-resolved and immutably pinned immediately before target quarantine download.

### Fast-shell rule

A small model may emit only bounded interaction primitives such as:

```text
WAIT
BACKCHANNEL
ACKNOWLEDGE_NONFACTUAL
REQUEST_CLARIFICATION
INTERRUPTION_REPAIR
```

unless it independently passes factual/tool/state gates. A fast shell must never fabricate facts, tool completion or memory merely to reduce perceived latency.

## 7. Proposed installed local voice topology

```text
LOCAL TARGET

Audio/AEC owner
  +-- mic channel ------------------------------+
  +-- exact Frank playback reference ----------+----> causal VAD/EOT/FVAD
                                                  |      + semantic partials
                                                  |      + endpoint anticipation
                                                  |      + deterministic turn FSM
                                                  v
                                         streaming local ASR
                                                  |
                                                  v
                                     VoiceSessionCapsule projection
                                                  |
                   +------------------------------+---------------------+
                   |                                                    |
             LOCAL CORE PROVIDER                                  optional provider
          official Qwen-class local                            Claude augmentation
                   |                                                    |
                   +----------- candidate chunks only ------------------+
                                      |
                                      v
                          GWT/GRID10/effect/state boundary
                                      |
                                      v
                               incremental local TTS
                                      |
                                      v
                           cancellable PCM ring buffer
                                      |
                                      v
                               actual playback tap
                                      |
                                      v
                       heard-text/audio causal receipt
                                      |
                                      v
                             VoiceOutcome -> UnifiedDB
```

Critical design point: the playback tap, not generated text, defines the spoken causal frontier.

## 8. Capability-adaptive local profiles

Do not hardcode model names into product identity. Installer/first-run profiling should select from measured bundles after the exact machine is known.

### Profile L — constrained local floor

Goal: preserve complete local operation under scarce compute.

Likely research shape:
- Whisper/Qwen/Nemotron candidate chosen by CPU fit;
- tiny endpoint/VAD path;
- 0.8B–2B dialogue or measured 4B quant if resident headroom permits;
- Piper/Magpie/MOSS-Nano-class TTS fallback.

No quality claim yet.

### Profile M — mainstream accelerated local

Goal: current primary target for near-Realtime quality.

Likely research shape:
- Nemotron/Qwen streaming ASR;
- official Qwen3.5-4B Q4-class core;
- Qwen3-TTS/Cosy/Chatterbox measured winner;
- two-channel turn controller;
- all kept resident if whole-system budget permits.

### Profile H — strong GPU/high-memory local

Goal: use extra compute for voice quality, not architectural dependency.

Potential additions:
- dots.tts or MOSS-Realtime quality tier;
- stronger asynchronous local thinker;
- richer speech-native experiments.

Every H feature must degrade cleanly to a lower local profile without creating a new identity/state authority.

These are research profiles, not accepted minimum hardware specifications.

## 9. Native full-duplex research result

DuplexSLA remains unusually relevant because it places speech and a structured action stream on one synchronized timeline, which resembles Frankenstein's need to speak while planning/tooling. JoyAI-Talker reinforces the Thinker/Talker separation and state-driven expressive speech direction.

But current production recommendation does not change: the modular German stack remains favored until a speech-native candidate proves all of:

- natural German;
- target hardware fit;
- tool/state integration;
- deterministic effect boundaries;
- interruption/commit correctness;
- long-session stability.

## 10. Exact next executable sequence

When an authorized target/VPS shell exists:

1. run the expanded `t7_hardware_inventory.py` and persist exact receipt;
2. calculate whole-Frankenstein resident headroom before model download/load;
3. resolve immutable revisions for official Qwen3.5-4B quantization plus ASR/TTS candidates;
4. quarantine-download **official Qwen3.5-4B first**, then the already-pinned abliterated Q4 controlled variant;
5. run identical German `VoiceSessionCapsule` dialogue tests through both;
6. benchmark Nemotron ASR at multiple right-context settings vs Qwen3-ASR and Whisper on identical audio;
7. benchmark Qwen3-TTS first; then the strongest footprint-compatible Cosy/Chatterbox/dots/MOSS/Magpie challengers;
8. integrate two-channel endpointing only after source/artifact audit, then run German false-cutoff/backchannel tests;
9. feed all runtime event logs through `t7_voice_receipt.py`;
10. route a candidate to Trigger 4 only when real E3 evidence exists.

## 11. Current conclusion

Deep Run 02 strengthens rather than replaces Run 01:

```text
PRODUCTION RESEARCH FAVORITE
= modular German local voice organ
+ two-channel/semantic turn intelligence
+ speculative but cancellation-safe latency hiding
+ official local 4B baseline before alignment variants
+ streaming expressive local TTS
+ whole-Frankenstein resident resource budgeting
+ machine-readable causal receipts

NATIVE FULL DUPLEX
= parallel high-upside architecture lane, not yet German production winner
```

Most important unresolved blocker is now sharply defined: **real executable target/VPS access plus a hardware receipt**. More source browsing can improve the frontier, but it cannot answer the decisive resident-memory, p95/p99, German room-audio and conversational-quality questions.
