# Trigger 7 — Local Dialogue LLM Frontier — 2026-08-29

Status: SOURCE-LEVEL SEED; no F2 dialogue-quality or latency credit

The local LLM is not allowed to become a second Frankenstein identity. It is a replaceable dialogue/reasoning substrate behind the same VoiceIntent/VoiceSessionCapsule/Memory/Tool boundaries.

## First Qwen3.5 size ladder

Primary upstream sources:

- https://huggingface.co/Qwen/Qwen3.5-0.8B
- https://huggingface.co/Qwen/Qwen3.5-2B
- https://huggingface.co/Qwen/Qwen3.5-4B
- https://github.com/ggml-org/llama.cpp

Source facts:

- Qwen3.5 checkpoints are Apache-2.0 and are post-trained conversational models;
- the family advertises broad multilingual coverage;
- official/current local runtimes include Transformers/vLLM-class paths, while llama.cpp currently exposes local GGUF serving for Qwen3.5-family models and an OpenAI-compatible local server;
- exact German conversational quality under quantization is not established by these source facts and must be measured by Trigger 7.

### LLM-Q35-08 — Qwen3.5-0.8B

Role hypothesis:
- ultra-fast interaction/appraisal/backchannel model;
- candidate for acknowledgement, turn-management, short clarifications and other latency-critical acts;
- may be too weak as the sole long-form Frankenstein dialogue brain.

Falsifier:
- German semantic/tool/state errors outweigh its latency advantage.

### LLM-Q35-2 — Qwen3.5-2B

Role hypothesis:
- middle interaction tier when 0.8B quality is insufficient but 4B is too slow for the target node.

Falsifier:
- no meaningful Pareto improvement over either 0.8B or 4B after quantization on actual hardware.

### LLM-Q35-4 — Qwen3.5-4B

Role hypothesis:
- first quality-oriented local dialogue candidate in this size ladder;
- benchmark as a single-model voice brain and as the deeper asynchronous thinker behind a smaller interaction shell.

Falsifier:
- TTFT/generation speed makes natural turn taking worse than a smaller model, or German/tool-state quality remains too far below the external-reference behavior.

## High-value architecture experiment: interaction shell + thinker

Inspired by the separation studied in current full-duplex research, Trigger 7 should compare:

```text
A) one blocking local LLM for every utterance
vs
B) fast local interaction shell + stronger asynchronous local thinker/tool layer
```

Example experimental shape only:

```text
Qwen3.5-0.8B or 2B
  -> immediate acknowledgement/backchannel/clarification candidates
  -> VoiceLoop arbitration

Qwen3.5-4B or stronger locally runnable model
  -> deeper answer / reasoning / tool planning in parallel where needed
```

The shell may never fabricate completion or facts merely to sound responsive. Fast backchannels are valid only when they do not claim an unverified result.

## Mandatory dialogue benchmark

Use the same pinned German prompt/session corpus for each model and quantization:

- ordinary open conversation;
- rapid short turns;
- interruptions and self-corrections;
- ambiguous speech requiring clarification;
- technical Frankenstein/project discussion;
- state-dependent questions requiring local memory/tool reads;
- conversational initiative versus WAIT;
- semantic close intent;
- long-session consistency;
- factual abstention when local state is unknown.

Record:

```text
TTFT p50/p95/p99
tokens_per_second
prompt_processing_time
KV/cache memory
resident RAM/VRAM
German dialogue quality rubric
tool selection correctness
memory/state grounding correctness
interrupt/cancel responsiveness
repetition/verbosity rate
30min+ drift
```

## Quantization law

Do not assume English benchmark retention implies German retention. Every promoted GGUF/other quantization must be benchmarked on the German voice-dialogue corpus against its higher-precision parent where hardware permits.

## Current recommendation

Start with a measured size ladder rather than naming one winner:

```text
0.8B -> latency floor / interaction shell
2B   -> middle tier
4B   -> first quality tier
```

If the actual VPS cannot run the quality tier with conversational latency, Trigger 7 records a hardware constraint rather than lowering the quality claim. Self-hosted execution on another owned/local node can be researched separately; external inference APIs remain disallowed for target-runtime acceptance.
