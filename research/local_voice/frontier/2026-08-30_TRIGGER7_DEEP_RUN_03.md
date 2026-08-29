# Trigger 7 — Deep Run 03

Date: 2026-08-30
Reconciled base: `frankenstein-2.0/main@c860cfdcac509e6b741401b32938436e23677802`
Evidence scope: source/research only; runtime credit remains zero.

## Re-entry

Current Trigger-7 state has advanced beyond the previous no-executor blocker. The exact-source `clay-direct-dev` hardware roundtrip is already dispatched through the owner-authorized self-hosted runner as GitHub Actions run `33265258658`, job `99134091520`; at this checkpoint it is still queued, so execution/hardware/runtime credit remains zero.

Parallel work also pinned the official Qwen3.5-4B source and a community Q4_K_M control. Therefore source pinning is no longer the immediate LLM blocker; target quarantine/hash/load execution is.

## New source delta

### Turn taking

FastTurn (arXiv:2604.01897, ASLP-lab/FastTurn) is promoted to a high-value T7-TURN-001 discriminator because it combines acoustic information with streaming CTC semantic cues and publishes evaluation material covering overlap, backchannels, pauses and noise. This maps directly onto Frankenstein endpointing/interruptibility failure modes.

No German or Frankenstein runtime credit follows from paper/repository evidence. Counterhypothesis: the semantic layer may add ASR/model latency and complexity without enough gain over tuned acoustic VAD + simpler endpoint logic.

### TTS

Official Qwen3-TTS remains first in the expressive German TTS benchmark order: German, streaming generation, 0.6B/1.7B, voice design/clone, Apache-2.0. Current upstream runtime/streaming issue evidence makes target-host reproduction mandatory before any streaming credit. Piper/Thorsten remains the tiny deterministic German latency/resource floor, not a presumed quality winner.

### ASR / local brain

Qwen3-ASR-0.6B remains a German source candidate with no promotion without identical room-audio WER/CER/latency tests. The Qwen3.5-4B official-family Q4 control is now pinned in current main, but still `PINNED_SOURCE_ONLY_NOT_TARGET_VERIFIED`; the reported community-quant hash must be recomputed in `clay-direct-dev` quarantine before use.

## Highest-information next discriminator

1. Observe run `33265258658` to terminal state; queued is transport state, not runtime evidence.
2. If it executes, fetch/persist hardware receipt and compute whole-Frankenstein RAM/VRAM headroom.
3. Quarantine-download the pinned official-family Q4_K_M control, recompute SHA-256, and bind exact load identity.
4. Benchmark official-family Q4 versus pinned abliterated Q4 under identical German `VoiceSessionCapsule` prompts/tool schemas/context.
5. Add a pinned German pause/backchannel/overlap replay comparing donor endpointing against a FastTurn-derived or equivalent acoustic-semantic controller with fixed ASR/audio transport.
6. Preserve raw causal receipts and negative results; send only E3/V4 evidence-bearing candidates to Trigger 4.

## Credit boundary

- Source refresh: observed.
- Harness repository CI: previously observed.
- Runner dispatch: observed queued only.
- Target hardware execution/receipt: not observed.
- Local model load/inference: not observed.
- German E2E voice benchmark: not observed.
- Trigger 4 acceptance: not observed.
- Whole Frankenstein acceptance: not observed.
