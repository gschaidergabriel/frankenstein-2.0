# Trigger 7 negative evidence — Nemotron 3.5 German risk

Date: 2026-08-30
Classification: UPSTREAM_NEGATIVE_EVIDENCE / NOT_F2_RUNTIME

## Observation

A public discussion on `nvidia/nemotron-3.5-asr-streaming-0.6b` reports substantial German transcription failures, including ordinary words, compounds and domain terminology, even with the largest discussed streaming context. NVIDIA's response does not dispute the failure class; it recommends three mitigation paths: request-time word boosting/context biasing, n-gram language-model fusion, and fine-tuning.

This is not a controlled Frankenstein benchmark and therefore does not establish that Nemotron fails on the actual F2 room corpus. It is nevertheless strong enough to invalidate a source-only assumption that published aggregate German WER makes Nemotron the presumptive production winner.

## Revised hypothesis

Nemotron remains a high-information streaming falsifier because it is compact, local, tunable and now has a native GGUF path through NeMo-Speech.cpp. It must earn German production credit against Qwen3-ASR and the donor Whisper baseline on the exact same audio.

## Required discriminator

1. Pin and locally hash the Q8_0 GGUF in `clay-direct-dev`.
2. Use the same real German room corpus for Nemotron, Qwen3-ASR and Whisper.
3. Sweep Nemotron right-context at 80/160/320/560 ms; reserve 1120 ms as a diagnostic upper point rather than a default realtime setting.
4. Run an unassisted baseline first.
5. Then run a separately labelled context-biasing/word-boosting condition using Frankenstein-specific names and technical vocabulary.
6. Measure WER/CER, terminology accuracy, partial stability, endpoint-to-final latency, CPU/GPU/RAM residency and end-to-end turn latency.
7. If context biasing repairs terminology without unacceptable latency/resource cost, retain as deployment candidate. If not, demote below Qwen3-ASR/Whisper or open a separate fine-tuning claim.

## Evidence boundary

`UPSTREAM_GERMAN_FAILURE_REPORT != F2_GERMAN_FAILURE`

`UPSTREAM_WER != F2_PRODUCTION_CREDIT`

`CONTEXT_BIASING_AVAILABLE != CONTEXT_BIASING_SOLVES_F2`

No VPS/model/runtime/benchmark/acceptance credit is granted by this record.
