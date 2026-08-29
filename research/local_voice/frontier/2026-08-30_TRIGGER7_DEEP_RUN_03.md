# Trigger 7 — Deep Run 03

Date: 2026-08-30
Base: `frankenstein-2.0/main@2bc56f9909c1d71174e4cb686e6630e9e3b6686a`
Evidence scope: source/research only; runtime credit remains zero.

## Re-entry

The canonical Trigger-7 cursor is `V1_SOURCE_PINNED_EXTENDED_HARNESS_READY_NO_TARGET_RUNTIME`. The first unresolved gate remains real `clay-direct-dev` execution: bridge/runner re-entry, hardware/resource receipt, immutable local model download, then German component/E2E benchmarks. Missing direct chat SSH is not a global executor failure.

## New source delta

### Turn taking

FastTurn (arXiv:2604.01897, ASLP-lab/FastTurn) is now a high-value T7-TURN-001 discriminator because it combines acoustic information with streaming CTC semantic cues and publishes evaluation material that explicitly covers overlap, backchannels, pauses and noise. This maps closely onto Frankenstein's endpointing/interruptibility failure modes.

No German or Frankenstein runtime credit follows from the paper/repository. The serious counterhypothesis is that the semantic layer may cost more latency/complexity than it saves versus tuned acoustic VAD + simpler endpoint logic.

### TTS

Official Qwen3-TTS still supports German, streaming generation, 0.6B/1.7B families, voice design/clone and Apache-2.0 source. Current open issue traffic around streaming/runtime compatibility strengthens the existing rule: benchmark Qwen3-TTS first, but treat streaming as unverified until target-host TTFA/RTF/cancellation tests reproduce it.

Piper/Thorsten stays the tiny deterministic German latency/resource floor. It is not assumed to be the quality winner.

### ASR / local brain

Qwen3-ASR-0.6B remains a valid German candidate but receives no promotion without identical room-audio WER/CER/latency tests. Official Qwen3.5-4B remains the required control before the abliterated Q4 variant; source refresh did not produce an immutable official Q4 pin or runtime result.

## Highest-information next discriminator

On `clay-direct-dev`:

1. establish a fresh bridge/runner roundtrip receipt;
2. run `t7_hardware_inventory.py` and compute whole-Frankenstein headroom;
3. pin/download an official Qwen3.5-4B quantized reference before the abliterated control;
4. run the existing causal voice benchmark harness;
5. add a German pause/backchannel/overlap turn-taking replay comparing donor endpointing against an acoustic-semantic controller;
6. preserve all raw receipts and negative results;
7. send only E3/V4 evidence-bearing candidates to Trigger 4.

## Credit boundary

- Source refresh: observed.
- Harness repository CI: already observed before this run.
- Target VPS/hardware receipt: not observed in this run.
- Local model load/inference: not observed in this run.
- German E2E voice benchmark: not observed.
- Trigger 4 acceptance: not observed.
- Whole Frankenstein acceptance: not observed.
