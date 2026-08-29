# Trigger 7 — Initial Local Voice Frontier — 2026-08-29

Status: SEED / SOURCE-READ; **zero F2 runtime acceptance credit**
Architecture snapshot: `frankenstein-2.0@085119cd4417c8fee6e4c36b1e6aeebdeebb0940`
Donor voice evidence source: `gschaidergabriel/frankenstein@DEV_SOURCE_RESEARCH`

## User target distilled

German first. Frankenstein 2.0 should preserve the already-working realtime conversational system but remove the requirement for ChatGPT/OpenAI or another external inference API in the target runtime. Research may use the internet to discover and download models. Final runtime must be self-hosted/local and should optimize for the highest achievable conversational quality with the lowest achievable latency.

## Donor behavior that the replacement must preserve

The donor evidence describes more than STT + chatbot + TTS. It contains:

- local continuous wake/VAD;
- true realtime conversation without push-to-talk;
- streamed audio;
- barge-in with truncation/cancellation;
- semantic close plus bilateral-silence close;
- state/memory/tool access;
- `voice_loop_core` GWT speech acts including WAIT;
- `ExpressionVector` derived from live Frankenstein state;
- chatter-debt/reopen behavior;
- `VoiceSessionCapsule`, `VoiceIntent`, `VoiceOutcome` architecture;
- Presence/Interruptibility integration target;
- same-entity requirement: voice is an organ, not a second assistant.

Primary donor references:

- `repository/GESPRAECHSMODUS.md`
- `repository/scripts/realtime_gespraech.py`
- `repository/scripts/voice_loop_core.py`
- `repository/scripts/frank_voice_lite.py`
- `repository/phase43/dossier_2026-08-27/14_VOICE_CHATGPT_AS_FRANKENSTEIN_ORGAN.md`
- `repository/phase43/dossier_2026-08-27/15_UNIFIED_CORTEX_GWT_VOICE_ARCHITECTURE.md`

## Current model/source frontier

The facts below are upstream/source facts only until reproduced on the actual Frankenstein hardware and workload.

### ASR candidate A1 — Qwen3-ASR-0.6B

Sources:
- Technical report: https://arxiv.org/abs/2601.21337
- Hugging Face: https://huggingface.co/Qwen/Qwen3-ASR-0.6B-hf

Upstream facts:
- Apache-2.0;
- German is explicitly supported;
- unified streaming/offline inference;
- 0.6B model;
- technical report claims average TTFT as low as 92 ms under its reported setup and positions 0.6B as the accuracy/efficiency variant.

F2 hypothesis:
- likely first ASR candidate to benchmark because it may reduce recognition latency while retaining strong German accuracy.

Falsifier:
- if real German room WER, partial-transcript stability or endpoint interaction is worse than the existing local Whisper path at comparable compute, it does not replace the baseline.

### ASR candidate A2 — Qwen3-ASR-1.7B

Sources:
- Technical report: https://arxiv.org/abs/2601.21337
- Hugging Face: https://huggingface.co/Qwen/Qwen3-ASR-1.7B

Upstream facts:
- Apache-2.0;
- German supported;
- streaming/offline;
- upstream authors report stronger accuracy than the 0.6B variant.

F2 hypothesis:
- accuracy tier for difficult real-world German audio if extra compute is justified.

Falsifier:
- accuracy gain too small to offset added latency/RAM/VRAM on the actual deployment hardware.

### ASR candidate A3 — primeline Whisper Large-v3-Turbo German

Source:
- https://huggingface.co/primeline/whisper-large-v3-turbo-german

Upstream facts:
- Apache-2.0;
- approximately 0.8B parameters;
- German-finetuned Whisper Large-v3-Turbo;
- model card reports an aggregate WER of 2.628 on its published German evaluation mix; this is self-reported upstream evidence, not F2 evidence.

F2 role:
- strong German Whisper-family baseline, useful especially because the donor already has faster-whisper experience.

### TTS candidate T1 — Qwen3-TTS 12Hz 0.6B

Sources:
- Technical report: https://arxiv.org/abs/2601.15621
- CustomVoice model card: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
- vLLM-Omni recipe: https://github.com/vllm-project/vllm-omni/blob/main/recipes/Qwen/Qwen3-TTS.md

Upstream facts:
- Apache-2.0 model family;
- German supported among ten languages;
- 0.6B CustomVoice variant supports predefined voices and style control;
- technical report reports first-packet emission down to 97 ms for its 12Hz low-latency design;
- vLLM-Omni has a local serving path and streaming PCM recipe.

Known upstream risk:
- streaming implementations have had real bugs, including duplicated/replayed audio reports; therefore "streaming supported" is not enough.

F2 hypothesis:
- current quality-first German TTS candidate because it combines multilingual German support, controllable style and a streaming-oriented architecture.

Mandatory falsifiers:
- male voice stability;
- German pronunciation;
- clause/sentence boundary prosody;
- genuine incremental generation rather than buffered batch behavior;
- no duplicated/replayed chunks;
- cancellation latency under barge-in.

### TTS candidate T2 — Piper / Thorsten German

Sources:
- https://huggingface.co/Thorsten-Voice/Piper
- https://huggingface.co/rhasspy/piper-voices/blob/main/de/de_DE/thorsten/medium/MODEL_CARD

Upstream facts:
- German male Thorsten voices exist as compact ONNX models;
- medium voice is 22.05 kHz, one speaker; model artifacts are small enough to be a useful CPU latency floor;
- Piper repository/model packaging is auditable and simple relative to large neural speech stacks.

F2 role:
- **latency/resource baseline**, not assumed quality winner.
- compare normal Thorsten and emotional variants where licensing/artifact provenance passes audit.

### Native duplex candidate D1 — MiniCPM-o 4.5

Sources:
- https://github.com/OpenBMB/MiniCPM-o
- https://github.com/OpenBMB/MiniCPM-o-Demo/blob/main/docs/en/architecture/duplex.md

Upstream facts:
- 9B end-to-end omni model;
- simultaneous streaming audio/video input with text/speech output;
- official demo exposes audio full-duplex mode;
- Apache-2.0;
- current official speech-conversation description is bilingual **English + Chinese**, not German;
- upstream documents unstable speech output/mixed-language limitations in omni mode.

F2 classification now:
- **architecture/full-duplex research reference; not a German production replacement yet.**

Value:
- study interaction scheduling, listen/speak overlap, interruption and full-duplex control semantics.

### Native duplex candidate D2 — Moshi

Source:
- https://github.com/kyutai-labs/moshi

Upstream facts:
- speech-text full-duplex foundation model;
- official FAQ says it currently speaks English only;
- official FAQ also describes demanding hardware and degradation from aggressive quantization.

F2 classification now:
- **architecture research reference, not German production voice.**

### Architecture reference D3 — DuplexOmni

Source:
- https://arxiv.org/abs/2606.09186

Upstream fact of highest relevance:
- separates a realtime interaction layer from an asynchronous/pluggable thinking layer for reasoning and tool use.

F2 hypothesis:
- this split is highly aligned with Frankenstein: a low-latency local interaction shell can maintain natural timing while the canonical Frankenstein cognition/tool path remains separate and explicit.
- this is an architectural hypothesis, not a claim that DuplexOmni itself should be imported.

## Initial architecture decision: two competing lanes

### Lane A — production-oriented German cascade

First experimental stack family:

```text
Silero/existing VAD + turn controller
  -> Qwen3-ASR-0.6B | Qwen3-ASR-1.7B | German Whisper Turbo
  -> Frankenstein VoiceLoop/GWT + local LLM
  -> Qwen3-TTS-0.6B | Piper Thorsten
  -> cancellable playback
```

Why first:
- every component supports independent replacement/ablation;
- German can be optimized directly;
- existing Frankenstein memory/tools/GWT boundaries remain reusable;
- individual bottlenecks can be measured rather than hidden inside one omni model.

### Lane B — native duplex research

Continuously test new German-capable speech-native systems and study MiniCPM-o/Moshi/DuplexOmni mechanisms. Lane B can supersede Lane A only after it passes the same German, tool/state, long-session, barge-in and offline-runtime gates.

## First benchmark matrix

| Experiment | Compare | Primary decision |
|---|---|---|
| ASR-001 | donor faster-whisper vs Qwen3-ASR-0.6B vs Qwen3-ASR-1.7B vs primeline German Turbo | German WER/latency Pareto |
| TTS-001 | Piper Thorsten vs Qwen3-TTS-0.6B | TTFA, RTF, German naturalness, prosody, cancellation |
| TURN-001 | existing Silero/VAD endpointing vs semantic/smart-turn candidates | false cuts + response latency |
| LLM-001 | locally available German-capable instruction models under identical VoiceSessionCapsule | answer quality vs TTFT/tokens/s |
| E2E-001 | best modular combination | user-end -> first audio; 30min stability; tools/memory |
| DUPLEX-001 | native duplex research candidates | German support + overlap/backchannel quality |
| OFFLINE-001 | best candidate stack with outbound network blocked | prove zero external inference dependency |
| PARITY-001 | local stack vs admitted historic/current external Realtime baseline | blind/source-hidden conversation quality |

## Immediate hardware prerequisite

Before claiming that a model "runs on the VPS", record the actual target node's CPU, RAM, GPU/VRAM (if any), disk free space, OS, audio transport path and currently installed inference engines. Model selection without that inventory is only a hypothesis.

If the target VPS is CPU-only or has insufficient accelerator memory, near-proprietary realtime quality may require either smaller quantized components or self-hosted compute on another owned/local node. Trigger 7 must measure this constraint rather than hiding it.

## Continuation cursor

Next highest-information work after this seed:

1. refresh actual F2/VPS hardware inventory;
2. snapshot the existing local donor ASR/VAD path and benchmark harness requirements;
3. create the first atomic Trigger-7 claim for `ASR-001`;
4. pin/download **Qwen3-ASR-0.6B** and **primeline/whisper-large-v3-turbo-german** into a quarantined VPS model-cache/research location if hardware/storage gates pass;
5. benchmark German ASR accuracy + streaming latency against the existing path;
6. in parallel only when non-duplicating, source-audit Qwen3-TTS local streaming path and Piper Thorsten baseline;
7. hand an evidence-bearing integration candidate to Trigger 4 only after component measurements exist.
