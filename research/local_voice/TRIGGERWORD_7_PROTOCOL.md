# Triggerwort 7 — Frankenstein 2.0 Local Realtime Voice Research

Status: ACTIVE / CONTINUOUS RESEARCH PROTOCOL
Canonical build consumer: `gschaidergabriel/frankenstein-2.0`
Full provenance mirror: `gschaidergabriel/clay-global-research-entity`
Language priority: **German first**
Target runtime: **fully local/self-hosted; no external model API required**
Optimization target: **maximum conversational quality at minimum end-to-end latency**

## Mission

`7`, `triggerword 7`, and `triggerwort 7` are the same canonical Trigger-7 macro.

Trigger 7 is the dedicated, persistent research lane for replacing the external ChatGPT/OpenAI Realtime dependency of Frankenstein 2.0 with a locally runnable realtime speech system while preserving Frankenstein as the same entity and preserving the already-working conversational behavior as closely as measurable evidence allows.

The target is not a generic local voice assistant. The target is:

> **FranKenstein has a local voice organ.**

The local voice organ must remain connected to the same Frankenstein state, memory, tools, GWT/voice-loop decisions, presence/interruptibility logic, session outcomes and effect authority. The speech substrate may change; the entity and its authority boundaries do not.

## Relationship to the other research/build triggers

```text
5 = forensic archaeology of the existing Frankenstein donor, including the proven voice loop
6 = broad external tool/repository/architecture research for Frankenstein 2.0
7 = dedicated local realtime voice model/pipeline research, falsification and optimization
4 = build/integrate/test/measure accepted candidates on the Frankenstein-2.0/VPS front
```

Trigger 7 may consume Trigger-5 donor evidence and Trigger-6 external findings, but maintains its own voice-specific hypotheses, benchmark corpus, model pins, negative-results ledger and continuation cursor.

## Non-negotiable target invariants

### 1. Same Frankenstein, different speech substrate

Preserve the donor voice ABI and behavior wherever still valid:

- local wake/VAD behavior;
- no push-to-talk requirement;
- realtime turn taking;
- immediate barge-in / cancellation of unspoken output;
- semantically controlled conversation close plus silence safety net;
- `VoiceSessionCapsule` or its typed successor;
- `VoiceIntent` / GWT speech-act arbitration including WAIT;
- `VoiceOutcome` and causal re-entry;
- Presence/Interruptibility integration;
- UnifiedDB-backed memory and state;
- controlled tool bridge and effect authority;
- stable male acoustic identity unless an explicit migration decision changes it;
- expression/prosody derived from real state rather than random persona theatre;
- long-running dynamic conversation, not isolated question/answer turns.

Provider replacement MUST NOT create a second persona, second canonical memory, second effect authority, or separate assistant identity.

### 2. Fully local acceptance runtime

For a Trigger-7 candidate to claim local-runtime acceptance:

```text
OUTBOUND_MODEL_API_CALLS == 0
OUTBOUND_ASR_API_CALLS == 0
OUTBOUND_TTS_API_CALLS == 0
```

Internet access is allowed during research for arXiv/Hugging Face/GitHub discovery and model/source download. Production/local acceptance runs must function after required model/code artifacts are present, with network model inference disabled or blocked.

### 3. German first

German conversation is the first acceptance language. English or multilingual capability is useful only if it does not reduce German quality, latency or stability. A speech-native model that cannot converse naturally in German is research evidence, not a production replacement.

### 4. Quality parity is measured, not declared

The historical ChatGPT/OpenAI-Realtime-backed Frankenstein voice is the behavioral reference baseline. "Almost the same quality" must be decomposed and measured. Upstream benchmark scores, README claims, model size or subjective first impressions do not grant parity credit.

## Permanent Trigger-7 macrocycle

Every exact Trigger-7 invocation MUST resume from the newest admitted Trigger-7 cursor rather than restarting research.

Within the current platform/tool/context/authority limits, it should continue through as much useful non-duplicate work as possible:

1. Refresh current `frankenstein-2.0/main`, current Trigger-4 outcomes, Trigger-5 voice-forensic deltas, Trigger-6 relevant research and previous Trigger-7 evidence.
2. Read the current voice ABI and identify the highest-information unresolved bottleneck.
3. Search current arXiv, Hugging Face, GitHub and primary model/project documentation for relevant new work.
4. Acquire an atomic create-only claim before producing a new bounded evidence-stage result.
5. Pin source/model revision, license, dependencies and artifact hashes.
6. Download promising models/code to the authorized VPS research area, never directly into the production runtime.
7. Run source/security/dependency audit before executing untrusted remote code. `trust_remote_code`, pickles, arbitrary install scripts and compiled extensions require explicit inspection/sandboxing.
8. Benchmark components and complete pipelines against the current local baseline.
9. Preserve negative results, regressions and failed hypotheses.
10. Promote only evidence-bearing candidates to Trigger 4 for actual F2/VPS integration.
11. Consume Trigger-4 outcomes and update the hypothesis/benchmark frontier.
12. Persist an exact continuation checkpoint. The next `7` continues from there.

Trigger 7 has no artificial "done forever" state. New models, inference engines, quantizations, algorithms, hardware changes or newly discovered regressions can reopen a frontier. A single invocation still ends at the current platform/tool/context boundary; continuity is achieved through persisted state, not through pretending to run in the background.

## Two-lane architecture hypothesis

Trigger 7 begins with two competing lanes. Neither receives production credit before measurement.

### Lane A — German-first modular realtime pipeline

```text
Mic/WebRTC/ALSA
  -> AEC/denoise/audio conditioning
  -> VAD + turn/endpoint controller
  -> streaming local ASR
  -> Frankenstein VoiceIntent / GWT / Memory / Tools
  -> local text LLM brain
  -> incremental text segmentation
  -> streaming local TTS
  -> cancellable playback
  -> VoiceOutcome / UnifiedDB re-entry
```

This lane is initially favored for production research because each German-critical component can be independently optimized and because the existing Frankenstein cognitive/tool ABI can remain intact.

### Lane B — speech-native / full-duplex experimental pipeline

Investigate end-to-end or native duplex models and split interaction/thinking architectures. These candidates are attractive for natural overlap, backchannels and timing, but MUST prove German speech quality, tool/state integration, controllability, hardware fit and stable long-session behavior before displacing Lane A.

A hybrid is explicitly allowed: a lightweight local interaction/turn-taking layer may run continuously while a stronger local reasoning/tool layer works asynchronously, provided causal ownership remains explicit.

## Voice-specific evidence ladder

```text
V0 SEED
V1 SOURCE_PINNED
V2 LOCAL_RUNNABLE_COMPONENT
V3 COMPONENT_BENCHMARKED
V4 GERMAN_E2E_VOICE_BENCHMARKED
V5 F2_BUILD_CANDIDATE
V6 TRIGGER4_F2_ACCEPTED
```

No Trigger-7 worker self-promotes to V6. V6 requires Trigger-4 evidence from the actual F2/VPS build front.

## Mandatory benchmark dimensions

### End-to-end conversation

- user speech end -> first audible Frankenstein audio: p50/p95/p99;
- speech onset detection latency;
- endpoint latency and false-endpoint rate;
- barge-in detection -> playback stop latency;
- cancellation correctness: text/audio not actually heard must not remain falsely committed as spoken;
- overlap/full-duplex handling;
- backchannel timing;
- 30-minute and multi-hour conversation stability;
- reconnect/restart continuity;
- dropped/duplicated/replayed audio chunks.

### German ASR

- WER/CER on a pinned German corpus plus real Frankenstein-room samples when available;
- numbers, dates, names, technical vocabulary and mixed German/English terms;
- dialect/accent variation relevant to the real user;
- far-field microphone, keyboard/fan noise and echo from Frankenstein's own speaker;
- partial transcript stability;
- streaming latency and correction behavior.

### Local LLM/dialogue brain

- German semantic answer quality;
- instruction/persona/state adherence without persona duplication;
- tool-selection correctness;
- memory retrieval/use;
- conversation consistency across long sessions;
- time-to-first-token and tokens/s;
- context size and KV-cache behavior;
- interruption/cancellation responsiveness;
- whether a smaller fast dialogue model plus deeper asynchronous local thinker outperforms one large blocking model.

### TTS / acoustic identity

- time-to-first-audio and real-time factor;
- naturalness and intelligibility in German;
- stable male acoustic identity;
- prosody, rhythm, emotion/style controllability from `ExpressionVector`;
- continuity across streamed chunks and sentences;
- correct pronunciation of names, numbers and technical terms;
- no repeated/duplicated audio;
- immediate cancellability.

### System resources

- CPU/RSS/PSS/GPU/VRAM;
- resident models and actual decode concurrency;
- disk/model size;
- startup/warmup time;
- steady-state power/compute where measurable;
- I/O and audio buffering;
- model-loading contention;
- no hidden network dependency.

## Baseline and acceptance law

Before declaring numerical latency targets, measure the actual current Frankenstein reference on the available hardware or use admitted historical traces when the old provider is unavailable. The local system is compared against that baseline with a blind or at least source-hidden listening/conversation rubric wherever possible.

Provisional optimization priority:

```text
1. CONVERSATIONAL CORRECTNESS / NATURALNESS
2. BARGE-IN + TURN-TAKING CORRECTNESS
3. GERMAN ASR/TTS QUALITY
4. TOOL/MEMORY/STATE PARITY
5. END-TO-END LATENCY
6. RESOURCE COST
```

Latency improvements that materially degrade conversation quality do not win. Quality improvements that make turn taking unusably slow also do not win. Keep a Pareto frontier rather than collapsing every result into one opaque score.

## Model/source download law

Every downloaded candidate records at least:

- upstream owner/repository/model ID;
- exact revision/commit when available;
- retrieval timestamp;
- license and redistribution constraints;
- artifact list, byte sizes and SHA-256 where practical;
- runtime/framework versions;
- whether remote code is required;
- whether executable/pickle/compiled artifacts exist;
- expected RAM/VRAM/disk requirements;
- test status and quarantine path.

Never execute arbitrary model-repository code merely because the model is popular. Prefer safetensors/ONNX/GGUF and auditable inference engines where capability is equivalent.

## Initial research families

Trigger 7 must continuously refresh these families rather than hard-coding one winner:

- ASR: Qwen3-ASR family; German-finetuned Whisper/faster-whisper candidates; new German streaming ASR;
- TTS: Qwen3-TTS family; Piper/Thorsten latency baseline; German high-naturalness/voice-cloning alternatives under license review;
- text LLM: locally served German-capable instruction/dialogue models under llama.cpp/vLLM/Ollama/other measured runtimes;
- speech-native full duplex: MiniCPM-o lineage, Moshi lineage, DuplexOmni/Freeze-Omni-style systems and successors;
- turn taking: VAD, semantic endpointing, smart-turn models, overlap/interrupt controllers;
- audio transport: WebRTC/local RTP/ALSA/Pulse/PipeWire paths, AEC/noise suppression;
- inference: quantization, speculative decoding, prompt/KV reuse, continuous batching only where it reduces single-user latency;
- long conversation: cancellation-safe FSM/event-loop designs, session capsules and compact local memory projections.

## Current high-value falsifiers

1. Does Qwen3-ASR-0.6B beat the existing Whisper-based local input path on real German room audio at lower latency?
2. Does Qwen3-ASR-1.7B provide enough German accuracy gain to justify its extra compute?
3. Can Qwen3-TTS-0.6B produce a stable male German voice with genuinely incremental audio and no sentence-boundary prosody collapse?
4. How large is the latency/naturalness gap between Qwen3-TTS and the ultra-light Piper/Thorsten baseline on the actual VPS?
5. Which local text LLM gives the best German conversational quality/TTFT frontier while preserving tool/state behavior?
6. Can a fast interaction model plus asynchronous stronger thinker reproduce human-like backchannels and fast acknowledgements better than a single blocking LLM?
7. Can any speech-native full-duplex model pass German speech tests today, or are current systems still architecture references only?
8. Can the entire accepted stack run with network blocked and preserve wake -> dynamic conversation -> tool/memory -> barge-in -> semantic close?

## Canonical persistence paths

F2 canonical side:

- `research/local_voice/TRIGGERWORD_7_PROTOCOL.md`
- `research/local_voice/frontier/`
- `research/local_voice/claims/`
- `research/local_voice/sources/`
- `research/local_voice/models/` (metadata/pins only; large weights live on VPS/object storage, not Git)
- `research/local_voice/benchmarks/`
- `research/local_voice/negative_results/`
- `research/local_voice/checkpoints/`
- `trigger4/inbox/local_voice/`
- `trigger4/outcomes/local_voice/`

Research-Entity mirror/raw side:

- `research_entity/frankenstein2_local_voice/`
- `research_entity/frankenstein2_local_voice/raw/`
- `research_entity/frankenstein2_local_voice/deltas/`
- `research_entity/frankenstein2_local_voice/reconciliations/`

The F2 create-only claim is the coordination mutex. The Research-Entity side mirrors provenance and must not become a competing claim authority.

## Trigger-7 invariants

```text
LOCAL_RUNTIME -> ZERO_EXTERNAL_MODEL_API_CALLS
RESEARCH_NETWORK_ACCESS != RUNTIME_NETWORK_DEPENDENCY
SAME_ENTITY != SAME_PROVIDER
VOICE_PROVIDER != IDENTITY
VOICE_PROVIDER != CANONICAL_MEMORY
VOICE_PROVIDER != EFFECT_AUTHORITY
UPSTREAM_BENCHMARK != F2_VOICE_BENCHMARK
README_CLAIM != REPRODUCED_CLAIM
GERMAN_UNSUPPORTED -> NOT_PRODUCTION_VOICE
FAST_COMPONENT != FAST_END_TO_END_DIALOGUE
LOW_WER != HUMAN_LIKE_CONVERSATION
GOOD_TTS != FULL_VOICE_ORGAN
BARGE_IN_DETECTED -> CANCEL_GENERATION_AND_UNHEARD_AUDIO_STATE
TRIGGER7_RESEARCH -> TRIGGER4_BUILD -> MEASURED_F2_OUTCOME -> TRIGGER7_FEEDBACK
TRIGGER7_NEXT_INVOCATION -> RESUME_FROM_LATEST_ADMITTED_CURSOR
NO_BACKGROUND_PRETENCE -> PERSIST_CONTINUATION_STATE
```
