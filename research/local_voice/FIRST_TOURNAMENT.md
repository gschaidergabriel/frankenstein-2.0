# Trigger 7 — First Local Voice Tournament

Status: READY FOR VPS EXECUTION
Research branch: `research/local-voice-continuous`

## Goal

Find the first credible fully-local German Frankenstein voice stack that preserves dynamic conversation and gives the best quality/latency Pareto point.

No candidate is a winner before measurement.

## Round 0 — host reality

Record exact VPS:

- CPU model/core count;
- RAM/free RAM;
- GPU/VRAM or `NO_GPU`;
- CUDA/ROCm/driver;
- free disk;
- OS/kernel;
- Python/compiler/runtime versions.

If the VPS has no suitable GPU, still run CPU-compatible latency floors and correctness tests, but label GPU-dependent candidates `BLOCKED_BY_HARDWARE` rather than drawing quality/latency conclusions from an unusable configuration.

## Round 1 — German ASR tournament

Challengers:

1. current Frankenstein/faster-whisper baseline;
2. Qwen3-ASR-0.6B;
3. whisper.cpp multilingual configuration;
4. Qwen3-ASR-1.7B only if Round 1 evidence shows enough remaining quality headroom and resources permit.

Primary metrics:

- German WER and semantic errors;
- names/numbers/technical vocabulary;
- hallucination after silence;
- partial stability;
- end-of-turn -> final transcript p50/p95;
- sustained RAM/VRAM;
- 30-minute streaming stability.

Winner selection: Pareto frontier, not one scalar score.

## Round 2 — German TTS tournament

Challengers:

1. current/local donor voice if reproducibly available;
2. Qwen3-TTS-12Hz-0.6B German-capable path;
3. Piper German latency control;
4. Qwen3-TTS 1.7B quality challenger only if resources permit.

Primary metrics:

- first-audio latency;
- streaming continuity/chunk gaps;
- German pronunciation;
- naturalness/prosody/rhythm;
- stable male Frank voice;
- state-dependent delivery without semantic distortion;
- barge-in cancellation latency;
- long-session voice drift.

Do not select Piper merely because it is fastest if it destroys the human-like voice target.

## Round 3 — dialogue model tournament

The dialogue model must be tested as a spoken conversation engine, not as a coding benchmark model.

Candidate discovery is dynamic at epoch start. First challengers should include the strongest locally runnable current small/medium instruction models with German and reliable structured/tool output, for example current Gemma 4 / Qwen-class checkpoints supported by the selected inference runtime.

Required tests:

- German spontaneous conversation;
- concise spoken phrasing;
- long technical explanation when asked;
- fast topic switching;
- ambiguity/clarification;
- state/personality projection;
- tool-call correctness;
- time to first token;
- tokens/sec after warmup;
- prompt/KV reuse in multi-turn sessions;
- cancellation behavior after barge-in.

Runtime/tool bugs are first-class evidence. A strong model with unreliable tool parsing or multi-turn cache behavior is not automatically suitable.

## Round 4 — pipeline tournament

Build at least three profiles:

### FAST

Fastest ASR Pareto candidate + smallest dialogue candidate that still passes German/tool quality + fastest acceptable TTS.

### BALANCED

Best quality/latency compromise.

### QUALITY

Highest conversational quality that still meets an explicit interactive latency bound.

For each measure:

- user-end -> first Frank audio;
- barge-in -> audio stop;
- tool round-trip -> resumed audio;
- 5+ minute dialogue naturalness;
- duplicate/stale response rate;
- resource contention between simultaneous ASR/LLM/TTS.

## Round 5 — duplex research challenger

Only after modular profiles are measured, test native/full-duplex approaches such as BayLing-Duplex/Moshi or newer open candidates.

Questions:

- Does native overlap/turn timing feel substantially more human?
- Does German quality survive?
- Can Frankenstein memory/tools/state remain authoritative?
- Can the model be interrupted without stale continuation?
- Is the compute cost justified by the gain?

A duplex model may contribute turn-taking/prosody without becoming the whole cognitive controller.

## Round 6 — no-network acceptance rehearsal

For current best modular/duplex profile:

1. preload all required local artifacts;
2. disable outbound network;
3. start Frankenstein voice runtime;
4. wake -> spontaneous German conversation;
5. perform read-tool round trip;
6. interrupt Frank mid-speech twice;
7. change topic abruptly;
8. reference prior state/memory;
9. end session via intended end policy;
10. restart and verify same durable state lineage.

Status can become `LOCAL_ACCEPTED_CANDIDATE` only if all inference is local.

## Round 7 — next research epoch

Regardless of result:

- update ledger;
- record champion and rejected candidates;
- search arXiv/Hugging Face/GitHub again for newer evidence;
- formulate next falsifier;
- continue.

Trigger 7 never closes.
