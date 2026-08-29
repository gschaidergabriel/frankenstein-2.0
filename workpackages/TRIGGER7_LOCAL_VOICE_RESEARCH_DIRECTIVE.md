# Trigger 7 — Frankenstein 2.0 Continuous Local Voice Research

Status: PROJECT-OWNER RESEARCH DIRECTIVE
Date: 2026-08-29
Activation: exact user trigger `7` (alias `triggerword 7` may be accepted by compatible workers)
Dedicated research branch: `research/local-voice-continuous`
Canonical product target: `architecture/LOCAL_VOICE_RUNTIME_CONTRACT.md`

## Mission

Trigger 7 exists only for the Frankenstein 2.0 local reactive conversation problem.

Its permanent objective is:

> **Maximize human-perceived German conversational quality while minimizing interactive latency, with the final runtime fully local and independent of ChatGPT/OpenAI/external inference APIs.**

The target experience is the already demonstrated Frankenstein conversational mode: a user should be able to speak naturally and dynamically about arbitrary topics, interrupt Frank, change direction mid-thought, receive fast context-aware responses, use Frankenstein memory/tools/state, and experience one coherent persistent entity rather than a push-to-talk chatbot.

This research lane has no terminal `DONE` state. A model or stack can be current champion, but research continues because new models, runtimes, quantizations, streaming methods and full-duplex architectures will appear.

## Trigger semantics

Every invocation of `7` starts or resumes a **Voice Research Epoch** from the latest research ledger. It must not restart from generic model lists if prior measurements exist.

Each epoch should perform the highest-information subset of:

1. inspect newest research evidence and unresolved hypotheses;
2. search current **arXiv**, **Hugging Face**, and **GitHub** for relevant new work;
3. inspect upstream model/runtime changelogs and releases;
4. acquire promising model/runtime candidates onto the authorized VPS research cache;
5. record exact source URL/repository, revision/commit, license, file hashes, model size and runtime dependencies;
6. run isolated microbenchmarks before whole-loop integration;
7. run German voice benchmarks against current champions;
8. falsify latency/quality/resource claims;
9. test streaming, interruption, turn-taking and tool round-trips;
10. retain negative results and rejected candidates so later workers do not repeat failed work;
11. promote only reproducibly superior candidates into a bounded Frankenstein integration branch/PR;
12. update the ledger, champion table, hypotheses and next experiments.

Research does not end because one stack works. It continues from the newest frontier.

## Source watch

At minimum every research epoch checks:

### arXiv

Search for:

- streaming / simultaneous ASR;
- German and multilingual ASR;
- speech-to-speech language models;
- full-duplex / duplex spoken dialogue;
- streaming neural TTS;
- low-frame-rate speech tokenizers/codecs;
- turn-taking, interruption and endpointing;
- inference acceleration, speculative decoding, quantization and KV-cache methods relevant to voice latency;
- human conversational evaluation and spoken dialogue benchmarks.

### Hugging Face

Search model cards and revisions for:

- German/multilingual STT;
- German expressive TTS;
- local speech-to-speech / audio-language models;
- strong small/medium instruct LLMs with German and reliable tool calling;
- quantized/optimized variants that preserve quality;
- license and redistribution constraints.

### GitHub

Search actively maintained implementations for:

- local voice agents with measured latency;
- streaming STT/TTS;
- duplex/barge-in state machines;
- `llama.cpp`/vLLM/other low-latency local inference;
- audio model runtimes and CUDA/CPU optimization;
- model-specific native runtimes;
- reproducible benchmark harnesses.

Popularity is not acceptance evidence. Prefer measured code paths, current commits, real hardware results and reproducible configurations.

## Dedicated branch law

`research/local-voice-continuous` is the persistent experimental branch/lane.

It may contain:

- research harnesses;
- model manifests and hashes;
- benchmark corpora metadata;
- scripts for model acquisition;
- experiment configs;
- latency traces;
- quality scorecards;
- rejected-candidate receipts;
- experimental adapters that are not yet product-authoritative.

It must not become a competing durable Frankenstein state authority. User memory/state is never copied into research fixtures.

Promotion path:

```text
research/local-voice-continuous
  -> reproducible candidate + evidence
  -> bounded integration branch / PR
  -> canonical Frankenstein tests
  -> offline whole-loop acceptance
  -> product profile/champion update
```

A research branch result alone never changes canonical runtime truth.

## VPS acquisition and experiment law

Promising open/local candidates should be downloaded to an **ephemeral/rebuildable research cache on the authorized VPS**, not to canonical user-state storage and not into git when model size makes that inappropriate.

Every acquired artifact requires a manifest entry containing at least:

- upstream project/model identifier;
- source URL;
- exact model revision or git commit;
- acquisition timestamp;
- license;
- expected and measured size;
- SHA-256 or upstream content identity;
- runtime/version used;
- quantization/precision;
- hardware used;
- status: `QUEUED | ACQUIRED | BENCHED | REJECTED | CHAMPION | PROMOTION_CANDIDATE`.

Deleteable model caches are not evidence; benchmark receipts and manifests are.

Never commit model binaries or secrets to the repository.

## Research candidate classes

Trigger 7 must research multiple architectures in parallel rather than locking prematurely to one stack.

### A. Cascaded local stack

```text
VAD/endpointing -> streaming ASR -> local dialogue LLM -> streaming TTS
```

Advantages to test: easiest preservation of Frankenstein memory/tools/state; independent component replacement; strong debugging and falsification.

### B. Native speech-to-speech / omni model

```text
audio -> speech-language model -> audio
```

Advantages to test: prosody, naturalness, lower semantic/audio boundary overhead, possible native conversational timing.

Constraint: it may not bypass Frankenstein state, tool/effect gates or persistent identity. If necessary use a typed control bridge around the speech model.

### C. Duplex / full-duplex speech model

Research models able to listen while speaking and learn turn-taking/interruption directly.

Constraint: native duplex behavior is useful only if it can be integrated without inventing an independent cognitive authority.

### D. Hybrid

Examples:

- fast local ASR + strong local LLM + neural streaming TTS;
- speech-language model for prosody/turn-taking with external Frankenstein cognitive state injected through a typed interface;
- dual-model fast-response/slow-refinement strategies;
- local fast conversational router plus stronger local model only when needed.

All remain hypotheses until measured.

## Optimization objective

Primary objective is not lowest latency at any quality. It is **maximum conversational quality subject to human-interaction latency**.

Maintain a Pareto frontier rather than one scalar benchmark.

Required latency measurements, all p50/p95/p99 where practical:

- speech onset detection;
- endpoint decision latency;
- partial transcript latency;
- final transcript latency;
- local LLM first-token latency;
- tool-call decision latency;
- TTS first-audio latency;
- mouth-to-ear time from user turn completion to first Frank audio;
- barge-in detection to speaker-stop latency;
- recovery latency after interruption;
- long-session latency drift.

Required quality measurements:

- German WER/semantic transcription accuracy;
- names, numbers, compound words, technical terms and code-switching;
- dialogue relevance and factual/semantic quality;
- Frankenstein memory/state adherence;
- tool-call correctness and argument fidelity;
- conversational naturalness;
- prosody, emotion, rhythm, pronunciation and voice consistency;
- interruption handling;
- false endpoint / premature turn-taking rate;
- repetition, stutter and duplicate-response rate;
- long-session coherence.

Required resource measurements:

- CPU/GPU/RAM/VRAM;
- real-time factor;
- model load/warmup time;
- sustained thermal/load stability;
- concurrent component contention.

## Human-like dynamic conversation target

The benchmark must include conversation rather than isolated utterances.

Test at least:

- fast back-and-forth questions;
- long reflective answers;
- user interruption while Frank speaks;
- user self-correction mid-sentence;
- short acknowledgements and follow-ups;
- abrupt topic shifts;
- ambiguous speech requiring clarification;
- memory references from earlier in the same and prior sessions;
- tool questions followed immediately by conversational continuation;
- silence, hesitation, filler words and restarts;
- speaking over the beginning of Frank's reply;
- several minutes of continuous natural dialogue without push-to-talk behavior.

Do not optimize benchmark phrasing so aggressively that spontaneous German conversation gets worse.

## Initial 2026 research seeds

These are **starting candidates only**, not locked architecture:

- Whisper-family local ASR plus newer streaming adaptations;
- Qwen3-ASR-class multilingual ASR candidates;
- `whisper.cpp`, `faster-whisper`, and other actively maintained streaming runtimes;
- Qwen3-TTS 0.6B/1.7B and newer Qwen speech synthesis releases for German streaming TTS;
- Piper as a latency floor/fallback, not presumed quality champion;
- current strong local German-capable instruct models through `llama.cpp`/vLLM-equivalent local runtimes;
- Hugging Face `speech-to-speech` reference implementations as integration/falsification material;
- BayLing-Duplex and subsequent open full-duplex SpeechLM research;
- new open native speech-to-speech/omni models when weights and local runtime are actually available.

## Promotion rule

A candidate is promoted only when it improves the measured Pareto frontier or closes a missing capability.

Promotion requires:

- exact model/runtime identity;
- reproducible command/config;
- benchmark corpus identity;
- raw metric receipt;
- comparison against the current champion on the same hardware and corpus;
- regression checks for memory/tools/session semantics;
- offline test showing no external inference contribution;
- explicit known regressions.

If quality improves while latency regresses, keep both profiles unless evidence shows one dominates the other.

## Never-ending rule

There is no terminal acceptance for Trigger 7 itself.

Possible epoch outcomes are:

- `NO_NEW_CHAMPION`;
- `NEW_PARETO_CANDIDATE`;
- `NEW_CHAMPION`;
- `FALSIFIED_CANDIDATE`;
- `NEW_RESEARCH_DIRECTION`;
- `BLOCKED_BY_HARDWARE`;
- `BLOCKED_BY_LICENSE_OR_RUNTIME`.

After any outcome, write the next highest-information experiment. Trigger 7 resumes there on its next activation.

Frankenstein 2.0 product voice may eventually be accepted; **voice research remains open indefinitely**.
