# Trigger 7 — Qwen3-ASR silence/noise + German comparator delta

Date: 2026-08-30
Trigger: `7`
Research ID: `T7-ASR-004`
Semantic key: `95bd53a469133dbfdf39da320f6daa049cec1361084e632dc915c4bc156e3715`
Status: `RESEARCH_DELTA / SAME_OPEN_SEMANTIC_OBJECTIVE`
Observed F2 main before this write: `d85271e8f4ac86ed63e5a7296553cfba38ff165e`
Evidence boundary: research/source design + previously admitted target-runtime component receipt; no new target execution or acceptance credit in this file.

## New observed constraint

The admitted target-runtime Qwen3-ASR CPU smoke receipt established exact artifact verification, local model load and local inference on `clay-direct-dev`, but one second of digital silence produced the German transcript `Ich.`.

That result is valuable negative evidence. It proves that the current bare decoder path must not be used as a speech-presence oracle. It does **not** by itself establish a general room-noise hallucination rate, German WER/CER, streaming quality, or end-to-end voice suitability.

Current semantic claim remains open at:

`research/local_voice/semantic_claims/95bd53a469133dbfdf39da320f6daa049cec1361084e632dc915c4bc156e3715.json`

Do not create a duplicate Qwen3-ASR German benchmark claim for the following quality/noise work.

## Hypotheses

### H1 — decoder-only false activation

The observed `Ich.` is a consequence of sending non-speech directly into the ASR decoder while forcing German, without an admitted external speech-presence gate. If so, a causal VAD/turn-controller gate should reject non-speech before text can enter VoiceIntent/GWT.

### H2 — synthetic-silence artifact

The result is specific to one second of exact zero samples plus the forced-language prompt and will not generalize materially to real room tone, fan/keyboard noise, echo, or the pinned German speech corpus.

### H3 — model-specific hallucination weakness

Qwen3-ASR has a materially worse non-speech false-text frontier than the admitted Whisper/faster-whisper baseline under matched target conditions, even with equivalent upstream gating.

The discriminator must distinguish H1/H2/H3 rather than treating any single silence output as a production verdict.

## Highest-information matched discriminator

Run the same pinned inputs on the same target under explicitly separated layers:

1. `RAW_DECODER`: no VAD; measure decoder susceptibility.
2. `GATED_PIPELINE`: admitted speech-presence/VAD gate before decoder; measure production-relevant false activation.
3. Matched Whisper/faster-whisper comparator with its VAD path enabled and decoder/no-speech fields recorded where exposed.

### Non-speech strata

At minimum:

- deterministic digital silence at 1 s, 2 s and 5 s;
- pinned real room tone;
- pinned fan/keyboard/background-noise samples;
- own-speaker playback/echo-only sample when an admitted donor/room fixture exists.

Measure:

- false activation rate per clip;
- non-empty decoded characters/tokens per second;
- gate speech/non-speech decision and latency;
- decoder latency;
- RSS/VRAM and warm/cold state;
- exact text emitted, never only a boolean PASS.

### German speech strata

Use a pinned transcript-bearing fixture set that contains:

- ordinary German sentences;
- numbers, dates and times;
- names and project vocabulary;
- German/English code-switching;
- hesitation/restart and short backchannels where transcript scoring remains well-defined.

Measure WER, CER, per-utterance latency, first stable partial latency when applicable, and exact failure transcripts. Keep room/dialect samples as a separately labeled robustness stratum when no gold transcript is available.

## Streaming scope correction

The currently admitted target smoke used the Transformers CPU backend and therefore has zero streaming credit.

Primary Qwen3-ASR source states that its official streaming API is vLLM-only, single-stream/no-batch, and does not return timestamps. The implementation buffers PCM, accumulates the stream, and re-feeds accumulated audio while using decoded-text prefix rollback. The official example uses a 2 s model chunk and exercises 0.5/1/2/4 s feed steps.

Consequences:

- `CPU_TRANSFORMERS_LOCAL_INFERENCE != VLLM_STREAMING`;
- do not mutate or reinterpret the successful CPU smoke receipt into streaming evidence;
- after resource-fit verification, official vLLM streaming should remain a distinct successor runtime gate as already routed in `trigger4/inbox/local_voice/T7_QWEN3_ASR_STREAMING_SCOPE_SUCCESSOR_2026-08-30_GPT56SOL.json`;
- German/noise quality characterization of the current Qwen subject remains part of the already-open T7-ASR-004 semantic benchmark.

## Comparator design note

The maintained `faster-whisper` baseline exposes Silero-VAD filtering and configurable silence handling. The comparison must therefore report both raw-decoder and gated-pipeline behavior; comparing ungated Qwen against gated Whisper would confound model quality with speech-presence control.

Production architecture consequence if H1 survives:

```text
AUDIO -> SPEECH_PRESENCE / TURN GATE -> ASR CANDIDATE -> VoiceIntent/GWT
```

not:

```text
AUDIO -> ASR TEXT EXISTS -> ASSUME USER SPOKE
```

The VAD/turn signal is perception evidence only. It must not become dialogue completion, canonical memory, or effect authority.

## Acceptance / falsification fences

```text
ONE SILENCE HALLUCINATION != GENERAL GERMAN_ASR_FAILURE
LOCAL_INFERENCE_PASS != GERMAN_QUALITY_PASS
RAW_DECODER_FALSE_TEXT != GATED_PIPELINE_FALSE_ACTIVATION
GATED_WHISPER != RAW_QWEN_FAIR_COMPARISON
LANGUAGE_FORCED_GERMAN != SPEECH_PRESENT
CPU_TRANSFORMERS != OFFICIAL_QWEN_STREAMING
STREAMING_API_EXISTS != REALTIME_LATENCY_PASS
TRIGGER7_RESEARCH != TRIGGER4_ACCEPTANCE
```

No arbitrary final quality threshold is minted here. First measure the pinned reference baseline and the current F2 requirements, then set promotion thresholds against the measured Pareto frontier.

## Source pins used for this delta

- F2 Qwen target probe: `research/local_voice/tools/t7_qwen3_asr_target_probe.py`
- admitted target checkpoint: `research/local_voice/checkpoints/2026-08-30_T7_ASR004_RUN33292903286_TRANSPORT_REPAIRED_CPU_SMOKE_PASS_GPT56SOL.json`
- current Qwen semantic claim: `research/local_voice/semantic_claims/95bd53a469133dbfdf39da320f6daa049cec1361084e632dc915c4bc156e3715.json`
- Qwen upstream implementation: `QwenLM/Qwen3-ASR`, `qwen_asr/inference/qwen3_asr.py`
- Qwen package version observed in current source audit: `qwen-asr==0.0.6`
- faster-whisper maintained baseline: `SYSTRAN/faster-whisper`

## Next exact gate

1. Trigger 4 or the already-authorized target executor runs the matched non-speech + pinned German fixture comparator on `clay-direct-dev` under the same T7-ASR-004 semantic objective, without creating a parallel duplicate ASR quality run.
2. Persist per-input transcripts, gate decisions, WER/CER, latency and memory/resource receipts.
3. Only after that result decide whether Qwen3-ASR remains the preferred German local ASR candidate, needs a mandatory upstream gate, or loses to the Whisper/faster-whisper baseline.
4. Keep official vLLM streaming as the already-routed successor gate; do not conflate it with this CPU quality discriminator.
