# Frankenstein 2.0 Local Voice — Benchmark Protocol

Status: research protocol
Branch: `research/local-voice-continuous`
Trigger: `7`

## Benchmark philosophy

A voice stack is not good because one component has a low synthetic latency. Frankenstein 2.0 optimizes the complete human conversation loop.

The comparison unit is a pinned **voice stack profile**:

```text
VAD / endpointing revision
+ ASR model/runtime/revision/precision
+ dialogue model/runtime/revision/quantization/context
+ TTS model/runtime/revision/precision/voice profile
+ audio transport/buffering configuration
+ Frankenstein voice-controller revision
+ exact hardware/software environment
```

Every material result records this full identity.

## Benchmark groups

### B1 — German ASR accuracy

Corpus slices:

- clean spontaneous German;
- ordinary room noise;
- fast speech;
- quiet speech;
- names and surnames;
- dates, times, telephone-like number sequences and quantities;
- compounds and inflections;
- technical/computing vocabulary;
- English words/code-switching inside German;
- hesitation, self-correction and sentence restart.

Metrics:

- WER;
- semantic error count when WER over-penalizes harmless punctuation/inflection;
- hallucination-after-silence rate;
- omitted-clause rate;
- number/name exactness;
- partial-transcript stability.

### B2 — Endpointing and turn timing

Measure:

- user speech end -> endpoint decision;
- false early endpoint rate;
- late endpoint rate;
- hesitation tolerance;
- short acknowledgement handling;
- user restart after a pause;
- assistant starts while user is still continuing.

### B3 — Dialogue quality

Use multi-turn German sessions, not isolated prompts.

Score:

- relevance;
- reasoning/factual usefulness;
- natural spoken phrasing rather than essay-style output;
- adaptation to short/long conversational turns;
- context continuity;
- Frankenstein durable-state/memory adherence;
- stable identity/personality;
- clarification behavior under uncertainty;
- conversational repair after ASR errors.

### B4 — Tool integration

Measure:

- correct tool choice;
- correct argument extraction from speech;
- tool call latency;
- tool-result re-entry;
- spoken continuation after tool result;
- no duplicate tool call after barge-in/retry;
- effect authorization remains outside model assertion.

### B5 — German TTS quality

Test:

- ordinary conversational answers;
- very short replies;
- long explanatory answers;
- questions;
- numbers and dates;
- abbreviations;
- names;
- technical terms;
- English code-switching;
- emotional/state-dependent delivery;
- quiet/uncertain vs confident delivery without changing semantic content.

Score:

- intelligibility;
- naturalness;
- prosody;
- rhythm;
- pronunciation;
- voice consistency;
- audio artifacts;
- chunk boundary artifacts;
- long-session voice drift.

### B6 — Reactive human conversation

Required scenarios:

1. user asks a question, then interrupts Frank halfway through the first sentence;
2. user corrects themselves before finishing a turn;
3. user says only a short acknowledgement and immediately continues;
4. abrupt topic shift;
5. 5+ minute free conversation with no push-to-talk;
6. tool use followed immediately by unrelated conversation;
7. ambiguous request requiring clarification;
8. user begins speaking while TTS audio is active;
9. deliberate silence/hesitation;
10. session end phrase followed by configured bilateral silence.

Measure:

- barge-in detection -> audio stop;
- cancelled LLM/TTS work;
- duplicate output rate;
- post-interruption recovery;
- perceived timing naturalness;
- speaker echo/self-transcription failures.

### B7 — End-to-end latency

Record p50/p95/p99 where sample count supports it:

- mic frame -> speech-onset detection;
- speech -> first stable ASR partial;
- user end -> ASR final;
- ASR final -> LLM first token;
- user end -> tool call candidate;
- LLM first speakable chunk -> first TTS packet;
- user end -> first audible Frank response;
- barge-in onset -> speaker stop;
- tool result -> resumed first audio;
- latency drift over long session.

Do not report only mean latency.

## Resource metrics

Record throughout each run:

- CPU utilization;
- GPU utilization;
- RAM;
- VRAM;
- disk/model size;
- audio/model queue depths;
- real-time factor for ASR/TTS;
- load/warmup time;
- sustained thermal/throttling indicators where observable.

## Comparison law

A challenger and champion comparison is valid only when:

- hardware identity is the same or explicitly normalized;
- test corpus and ordering are the same;
- warm/cold state is recorded;
- model revision/quantization is pinned;
- configuration changes are explicit;
- raw results are retained.

Use Pareto comparison:

- quality improvement with acceptable latency regression may become `VOICE_LOCAL_QUALITY`;
- latency improvement with acceptable quality regression may become `VOICE_LOCAL_MIN` or `BALANCED`;
- a candidate dominated on both quality and latency is normally rejected.

## Human evaluation

Automatic metrics are necessary but insufficient for spoken interaction.

For champion promotion, retain blinded or randomized human comparison material where practical. The evaluator should compare audio without being told which model generated it.

Record preference separately for:

- voice naturalness;
- German pronunciation;
- conversational timing;
- overall willingness to continue talking to Frank.

## Offline gate

Before a stack can be marked `LOCAL_ACCEPTED`:

- outbound inference network is disabled;
- no external API key is read;
- all inference endpoints resolve locally;
- at least one full German conversation session with tool re-entry and barge-in passes;
- restart preserves Frankenstein state continuity;
- process/network trace shows zero external inference contribution.

## Near-parity gate

`NEAR_PARITY_TO_PREVIOUS_REMOTE_VOICE` is a separate, high bar.

It requires a frozen comparison set from the previously working Frankenstein voice experience and explicit thresholds for:

- perceived dialogue quality;
- naturalness;
- interruption handling;
- first-audio latency;
- recognition errors;
- tool correctness.

Do not infer parity from model reputation.
