# Frankenstein 2.0 Local Voice — Continuous Research Ledger

Research branch: `research/local-voice-continuous`
Trigger: `7`
Initialized: 2026-08-29
Status: OPEN FOREVER

## Objective

Maximize German conversational quality while minimizing mouth-to-ear latency, interruption latency and resource cost. Preserve Frankenstein state, memory, tools, wake/end semantics and identity. Final accepted runtime must work without external inference APIs.

## Epoch 0001 — initial frontier scan

### Finding A — Qwen3-ASR is a serious German ASR candidate

Sources:

- arXiv: `2601.21337` — Qwen3-ASR Technical Report
- GitHub: `QwenLM/Qwen3-ASR`
- Hugging Face: `Qwen/Qwen3-ASR-0.6B-hf`, `Qwen/Qwen3-ASR-1.7B-hf`

Observed claims to falsify locally:

- 52 languages/dialects including German;
- official streaming CLI/runtime exists;
- 0.6B is positioned as accuracy/efficiency model;
- report gives very low TTFT under high-throughput server conditions, which does **not** directly imply single-user Frankenstein latency.

Experiments:

1. Qwen3-ASR-0.6B vs faster-whisper large-v3-turbo vs current Frankenstein STT on same German corpus.
2. Measure partial/final transcript latency, WER, names/numbers/technical words, hallucination after silence, memory growth in 30+ minute streaming session.
3. Test whether a smaller Qwen3-ASR context or quantized runtime wins the interactive Pareto frontier.

Status: `QUEUED_FOR_VPS_ACQUISITION`

### Finding B — Qwen3-TTS is a high-priority German streaming TTS candidate

Sources:

- arXiv: `2601.15621` — Qwen3-TTS Technical Report
- GitHub: `QwenLM/Qwen3-TTS`
- Hugging Face: `Qwen/Qwen3-TTS-12Hz-0.6B-Base`, `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`

Observed claims to falsify locally:

- German is explicitly supported;
- 0.6B and 1.7B model family;
- streaming generation;
- paper reports first-packet latency around 97 ms for the 12 Hz tokenizer path under its benchmark conditions;
- voice cloning and natural-language control may help preserve a stable Frank voice and emergent state-dependent prosody.

Experiments:

1. Qwen3-TTS 0.6B German vs current local donor TTS vs Piper German latency floor.
2. Streaming first-audio latency and chunk-gap test.
3. Human German naturalness/prosody comparison on short answers, long answers, emotional/state-modulated answers, numbers and technical terms.
4. Barge-in cancellation: verify no long uninterruptible synthesis queue.

Status: `QUEUED_FOR_VPS_ACQUISITION`

### Finding C — Whisper streaming remains a useful baseline, but should not be assumed champion

Sources:

- GitHub: `ggml-org/whisper.cpp`
- arXiv: `2506.12154` — Adapting Whisper for Streaming Speech Recognition via Two-Pass Decoding
- arXiv: `2604.25611` — WhisperPipe

Why retain:

- mature local runtimes, CPU/GPU portability and known German quality;
- useful control baseline against newer ASR models;
- WhisperPipe reports bounded-memory streaming and very low median latency, but claims must be reproduced on F2 hardware and German speech.

Status: `BASELINE_AND_RESEARCH`

### Finding D — modular fully local voice stacks already demonstrate the correct engineering pattern

Sources inspected:

- GitHub `shivu0070/local-voice-ai`: faster-whisper + Silero VAD + local LLM + Piper, streaming TTS and sub-second barge-in design;
- GitHub `aryeo0908/whisper-loop`: pluggable providers, streaming STT/LLM/TTS, immediate cancellation on barge-in, measured stage latencies;
- GitHub `huggingface/speech-to-speech`: fully local cascaded examples with local LLM server, realtime turn revisions and barge-in;
- GitHub `melnikaite/voice-assistant`: offline-first local assistant with streaming ASR/TTS, tools and memory.

Use:

- mine architecture/test ideas, cancellation semantics, buffering, WebRTC/echo-cancellation and benchmark methods;
- do not copy their state authority or product semantics into Frankenstein.

Status: `REFERENCE_IMPLEMENTATIONS`

### Finding E — BayLing-Duplex is a high-information full-duplex experiment

Sources:

- arXiv: `2606.14528` — BayLing-Duplex
- GitHub: `BayLing-Models/BayLing-Duplex`
- Hugging Face: `BayLing-Models/BayLing-Duplex`

Observed:

- public local inference repository and weights;
- model can listen and speak simultaneously and models turn-taking/interruption inside one autoregressive path;
- Hugging Face model repository is roughly 19 GB before associated speech tokenizer/decoder;
- derived from GLM-4-Voice lineage.

Research question:

Can its duplex timing/interruption behavior be reused or adapted while Frankenstein remains the cognitive/state/tool authority? It is **not** presumed suitable for German or final product quality.

Status: `HIGH_INFORMATION_EXPERIMENT`, hardware permitting

### Finding F — Moshi remains an important duplex reference

Source:

- GitHub: `kyutai-labs/moshi`

Observed:

- full-duplex streaming speech-text framework;
- PyTorch/MLX/Rust runtimes;
- GPU requirements can be substantial for PyTorch path; quantized MLX/Rust paths exist for supported environments.

Research value:

- turn-taking/duplex protocol and echo-cancellation lessons;
- compare learned full-duplex behavior against Frankenstein's modular VAD/barge-in loop.

Status: `REFERENCE_OR_EXPERIMENT`, hardware/language dependent

### Finding G — Qwen Audio 3.0 TTS should be watched, not assumed downloadable

Source:

- arXiv: `2607.23938` — Qwen-Audio-3.0-TTS

Observed paper claims:

- production-oriented TTS;
- 16-language support;
- low-frame-rate tokenizer and efficiency work;
- strong aggregate TTS results.

Before any experiment, verify that weights/license/runtime are actually available for local use. Paper existence is not model availability.

Status: `WATCH`

## Initial Pareto hypotheses

H1. **Best near-term Frankenstein integration:** modular pipeline with current VAD + Qwen3-ASR-0.6B or faster-whisper + strongest low-latency local German-capable dialogue model + Qwen3-TTS-0.6B streaming.

H2. **Latency floor:** Whisper/faster-whisper + small local LLM + Piper will probably be very fast but likely loses voice naturalness and dialogue quality; retain as `VOICE_LOCAL_MIN` control.

H3. **Quality profile:** larger local dialogue model + Qwen3-TTS-1.7B may win quality if first-token/first-audio latency can be hidden through streaming and speculative/pipelined generation.

H4. **Future human-likeness leap:** native/full-duplex SpeechLMs may produce more natural overlap and timing than cascaded systems, but current candidates may lose German quality, tool control, or Frankenstein cognitive integration.

H5. **Hybrid may dominate:** keep Frankenstein cognition/text/tool state modular while using an audio model only for timing/prosody/speech rendering.

All are hypotheses until measured.

## Mandatory next epoch

1. Detect exact VPS hardware/software capability and free disk.
2. Create research cache outside canonical Frankenstein state.
3. Acquire smallest high-information candidates first:
   - Qwen3-ASR-0.6B;
   - Qwen3-TTS-0.6B German-capable checkpoint;
   - current faster-whisper/whisper.cpp baseline runtimes.
4. Record exact revisions/hashes/licenses.
5. Run component benchmarks before downloading larger 1.7B/duplex candidates.
6. Build German corpus and conversational timing fixtures.
7. Do not promote any winner until same-hardware same-corpus comparison is complete.

## Ledger rule

Append new epochs. Never erase negative evidence. If an upstream version changes, record a new candidate revision rather than mutating old benchmark identity.
