# Trigger 7 — Deep Run 03 (GPT-5.6 Sol)

Date: 2026-08-30  
Trigger: exact user message `7`  
Mode: German-first LOCAL-SOLO voice research; provider augmentation remains optional/noncanonical.

## Authority / reentry

- The older project bootstrap did not define Trigger 7 and was treated only as a cache.
- Current canonical Trigger-7 sources in `clay-global-research-entity` and this repository resolve `7` to the Frankenstein 2.0 local realtime voice research/implementation lane.
- Current owner execution authority admits bounded exact-source work in owner-provisioned `clay-direct-dev` through the established Dr.-Unterweger self-hosted runner bridge.
- No external model API inference was used in this run.

## Runtime frontier observed

The canonical checkpoint already owns `T7-SYS-002/E3_VPS_HARDWARE_ROUNDTRIP` with GitHub Actions run `33265258658` / job `99134091520`. It remained `queued` when observed; therefore:

- target execution observed: **false**
- hardware receipt observed: **false**
- model download observed: **false**
- model runtime credit: **0**
- German E2E voice credit: **0**

A second parallel Trigger-7 bridge run (`33265385890`) was also observed queued. A duplicate probe workflow created during this session was removed again after the canonical/parallel lane was discovered. No duplicate runtime claim is retained from that probe.

No in-progress Dr.-Unterweger workflow run was observed at the final runner-status check. This establishes only that the queued Trigger-7 work had not been picked up at that observation point; it does **not** establish why (runner offline, unavailable, label mismatch, or another transport condition remains unresolved).

## Durable source research deltas

### 1. Qwen3-ASR-0.6B-hf exact local baseline pin

Added:

`research/local_voice/sources/T7_QWEN3_ASR_06B_HF_SOURCE_PIN_2026-08-30.json`

Observed official source facts:

- repository: `Qwen/Qwen3-ASR-0.6B-hf`
- observed revision: `7f1569a48a89f3e3f4dc3a5c9d28bddd903bc76c`
- model payload SHA-256: `d3f212dd20abecd315d830bc54ae3865e56ebfc3276484e57b771288ba27fd35`
- model payload size: `1564928088` bytes
- Apache-2.0
- German is supported by the official Qwen3-ASR family
- current HF path supports native Transformers >= 5.13.0, language forcing, and context/hotword prompting

This is source-only evidence. The artifact has not yet been downloaded or re-hashed inside `clay-direct-dev`.

### 2. Next-Turn duration-aware endpointing discriminator

Added:

`research/local_voice/sources/T7_NEXT_TURN_ENDPOINTING_SOURCE_AUDIT_2026-08-30.json`

Primary paper: arXiv `2606.18094`, *Next-Turn: Duration-Aware Streaming Endpoint Detection via Time-to-Next-Speech-Onset Prediction*.

High-value delta:

- predicts time-to-next-speech-onset instead of only a binary endpoint label;
- targets derive directly from speech timestamps;
- paper reports a 25.9 percentage-point absolute endpoint-accuracy gain within 320 ms over its strongest reported baseline;
- directly targets the within-turn hesitation/pause failure that fixed silence timers mishandle.

Architecture interpretation: Next-Turn is not equivalent to DualTurn. It is a narrower endpoint-duration mechanism and should be tested as a complement/falsifier against DualTurn's broader two-channel EOT/HOLD/BOT/BC/VAD/FVAD action-state vocabulary.

German behavior remains unproven until common-corpus target-runtime measurement.

## Parallel research incorporated, not duplicated

During this run the moving F2/global heads also gained independent Trigger-7 source work, including:

- exact Nemotron 3.5 ASR Streaming 0.6B German source pin and right-context sweep contract;
- Voxtral / X2-Turn German source audit;
- reconciliation of a duplicate VPS hardware claim.

These were treated as moving canonical/parallel work and were not reimplemented.

## Current hypothesis / counterhypothesis

**Hypothesis:** a modular LOCAL-SOLO German voice organ can outperform simple timeout-based interaction by combining a strong local ASR baseline/challenger set (Qwen3-ASR, Nemotron, donor Whisper/Voxtral where admitted) with learned turn/end-of-turn prediction and cancellation-safe generation.

**Counterhypothesis:** learned turn models trained/evaluated mostly on English/Chinese interaction patterns will not remain calibrated on German hesitation, backchannel and overlap behavior; the additional models may add latency/resource pressure without reducing real interruption errors.

## Next exact gate

Do not download or benchmark the pinned model bundle merely because source pins exist.

1. Observe canonical self-hosted run `33265258658` to a terminal state and fetch its persisted `clay-direct-dev` hardware/resource receipt if execution occurs.
2. Compute whole-Frankenstein resident RAM/VRAM/disk headroom from that receipt.
3. Only then quarantine-download the exact Qwen3-ASR and other selected baseline artifacts into `clay-direct-dev`, recompute hashes locally, and bind runtime identity.
4. Run the same real-German room-audio corpus through Qwen3-ASR, Nemotron and donor baselines.
5. Compare silence/VAD baseline vs DualTurn vs Next-Turn-style endpointing on mid-sentence pauses, overlap, backchannels and barge-in.
6. Preserve all results through the common Trigger-7 causal voice receipt path; source results never mint runtime or Trigger-4 acceptance credit.

## Evidence ceiling

`V1_SOURCE_PINNED_PLUS_RUNTIME_DISPATCH_QUEUED_NO_TARGET_EXECUTION`

No claim in this file establishes target runtime, model quality, German E2E voice acceptance, Trigger-4 acceptance, or whole-system acceptance.
