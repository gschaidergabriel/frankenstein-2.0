# Trigger 7 — FastTurn + TTS source addendum

Date: 2026-08-30
Scope: source/research delta only; no target-runtime credit.

This addendum is intentionally separate from the concurrently produced canonical Deep Run 03 frontier. It adds two non-duplicate discriminators.

## 1. FastTurn as a German turn-control falsifier

FastTurn (arXiv:2604.01897; ASLP-lab/FastTurn) combines acoustic cues with streaming CTC-derived semantic cues and evaluates overlap, backchannels, pauses, pitch variation and noise. That makes it a strong method/dataset donor for Frankenstein's false-endpoint, backchannel and interruption cases.

It receives no German or Frankenstein runtime credit from source evidence. The counterhypothesis is important: a semantic endpoint layer may add enough ASR/model latency and complexity that tuned acoustic VAD plus a simpler endpoint heuristic wins on the actual German workload.

Highest-information test after target hardware is available: hold audio transport and ASR constant and replay a pinned German pause/backchannel/overlap corpus through donor endpointing versus a FastTurn-derived or equivalent acoustic-semantic controller; compare false endpoints, late endpoints and barge-in cancellation latency.

## 2. Qwen3-TTS streaming claim remains target-gated

Official Qwen3-TTS remains a strong expressive German TTS candidate: German support, 0.6B/1.7B families, streaming generation, voice design/cloning and Apache-2.0 source. Current upstream runtime/streaming compatibility issue traffic means those capabilities must be reproduced on `clay-direct-dev` before TTFA/RTF/cancellation credit is granted.

Piper/Thorsten remains the tiny deterministic German latency/resource floor, not a presumed naturalness winner.

## 3. Reconciliation with concurrent Deep Run 03

Concurrent mainline work has already:

- added a NeMo-Speech.cpp substrate candidate;
- tightened Nemotron German-risk handling;
- fenced corrected DualTurn streaming graph identity;
- pinned the official Qwen3.5-4B source plus a community Q4_K_M control;
- dispatched exact-source VPS hardware run `33265258658`.

This addendum does not replace those results. It narrows the next turn-taking and TTS discriminators while preserving zero runtime credit until the queued target run actually executes and receipts are observed.
