# Trigger 7 Target-Runtime Transport Re-entry v1

Status: ACTIVE SOURCE LAW / TARGET RECEIPT STILL REQUIRED
Date: 2026-08-30

## Problem

A Trigger-7 scientific objective can be correctly claimed while its GitHub Actions transport never reaches execution. The concrete discriminator is a job that remains queued with no assigned runner and no steps. That is transport/control-plane evidence only; it is not model evidence.

The canonical Qwen3-ASR case is run `33292903286`, job `99207535776`: the Actions path requested `[self-hosted, Linux, X64]` but did not reach step execution.

## Re-entry law

For an already-owned Trigger-7 semantic objective, an alternate target transport MAY be used without minting a second scientific objective when all of the following are true:

1. the original execution transport has produced no model/test steps and no target-runtime receipt;
2. the alternate transport reaches the same admitted target surface;
3. the same semantic key is preserved;
4. the exact intended source/probe commit, model revision and artifact-hash contract are preserved, except for an explicitly recorded repair commit when the first real execution exposes a source defect;
5. only one material target execution is active at a time;
6. the alternate transport emits a causally bound receipt with command identity/hash, target boundary, timestamps, exit state and stdout/stderr hashes;
7. queued/abandoned transport attempts mint zero model/runtime/quality/acceptance credit.

Current admitted alternate transport for `clay-direct-dev` is the existing Git control bridge:

```text
chatgpt-vps-control/vps_bridge/commands/<command>.json
  -> clay VPS bridge daemon
  -> rootless podman exec in clay-direct-dev
  -> chatgpt-vps-results/vps_bridge/results/receipts/<command>.json
```

A fresh `vps_bridge/results/LIVE.json` demonstrates bridge liveness only. Scientific credit still requires the command-specific terminal receipt and the inner probe result.

## Retry after source defect

If the first target execution exposes a deterministic source defect before model load/inference, a repaired source commit is a legitimate retry reason for the SAME semantic objective. The repair must be minimal, source-bound and regression-checked. It does not create runtime credit by itself.

For T7-ASR-004 the first bridge re-entry exposed an invalid Python keyword argument (`pass=False`) in `t7_qwen3_asr_target_probe.py`. The minimal syntax repair is F2 commit `48f0dbd96d5ab41b1f9b0bba568a65040b240afd`; the operational workflow is rebound to that commit and now runs `py_compile` before the probe.

## Anti-stampede rule

```text
QUEUED_ACTIONS_NO_STEPS + LIVE_BRIDGE
  -> REROUTE_EXISTING_SEMANTIC_OBJECTIVE
  != CREATE_NEW_SCIENTIFIC_CLAIM

ONE_ACTIVE_TARGET_EXECUTION_PER_SEMANTIC_KEY
TRANSPORT_SUCCESS != MODEL_SUCCESS
TRANSPORT_FAILURE != MODEL_FAILURE
```

Do not dispatch another Actions run merely because a previous one is queued. Do not run Actions and Git-Bridge target probes concurrently for the same semantic key. If the old Actions job later acquires a runner after a bridge result already exists, reconcile it as a stale transport attempt and do not grant duplicate scientific credit.
