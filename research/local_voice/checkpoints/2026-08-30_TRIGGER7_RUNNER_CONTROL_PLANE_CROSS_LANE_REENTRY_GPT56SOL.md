# Trigger 7 — Runner Control-Plane Cross-Lane Reentry

Date: 2026-08-30
Organ: GPT-5.6 Sol / Trigger-7 research organ
Status: `CONTROL_PLANE_BLOCKED_NO_DUPLICATE_DISPATCH`

## Routing and authority

Exact user trigger `7` routes to the active Frankenstein 2.0 Local Realtime Voice Research lane.

Current execution authority permits owner-provisioned `clay-direct-dev`, self-hosted execution and local-model research. `FREE_ONLY` remains an external provider/token/spend boundary, not a VPS ban. Runtime credit still requires exact execution receipts.

## Reentry identities before this checkpoint

- Clay research main: `d39bac5391a0e8b783318281084c2cb58a426def`
- Frankenstein 2.0 main observed immediately before write: `0c0da64042780331b364ead198d9cec5b14fd367`
- Controller main: `6c77751435d980bf50f5e3b362e8d1fcffca87c1`
- Current parallel Trigger-7 delta at F2 head: Nemotron 3.5 ASR Streaming 0.6B target-runtime benchmark semantic claim, explicitly **without dispatch**, blocked on the same runner-assignment gate.

## Fresh execution observations

### Existing Qwen3-ASR target probe

- controller run: `33292903286`
- job: `99207535776`
- state: `queued`
- required labels: `self-hosted`, `Linux`, `X64`
- runner assignment: none (`runner_id=0`, empty runner name)
- executed steps: 0
- target load/inference credit: 0

### Existing Trigger-7 hardware roundtrip

- controller run: `33266856557`
- job: `99138324275`
- state: `queued`
- required labels: `self-hosted`, `Linux`, `X64`
- runner assignment: none (`runner_id=0`, empty runner name)
- executed steps: 0
- `clay-direct-dev` roundtrip receipt: not observed

### Newer Trigger-4 target-runtime workflow

- run: `33295805811`
- state observed: `pending`
- jobs exposed at observation: 0

This is pre-execution control-plane evidence only. It is not a Qwen, Nemotron, ASR, voice-stack or Frankenstein semantic failure.

## Cross-lane coordination

Trigger 4 independently converged on the same blocker and maintains controller issue `gschaidergabriel/Dr.-Unterweger#873`.

This Trigger-7 reentry appended fresh cross-lane evidence to that existing issue rather than creating a duplicate blocker:

- issue comment id: `5467623978`

No new Qwen/Nemotron/model benchmark dispatch was created.

## Hypothesis / counterhypothesis

Leading hypothesis:

`REPOSITORY_WIDE_SELF_HOSTED_RUNNER_LIFECYCLE_OR_AVAILABILITY_BLOCKER`

The repeated `queued + runner_id=0 + zero steps` pattern across independent self-hosted jobs makes a model-specific workflow defect materially less likely.

Counterhypothesis:

A narrower current registration/group/label eligibility or GitHub scheduler/admission condition could still produce the same queue pattern even if the target host itself is healthy.

Direct target-host observation is required to distinguish these cases. Do not mutate runner service policy from source/model consensus alone.

## Current-session surface boundary

The current chat transient container did not expose an installed SSH binary/config/identity. This is scoped absence on this session surface only. It does **not** establish that the configured Clay Git/SSH bridge, owner VPS or `clay-direct-dev` is globally absent.

## Evidence credits

- Qwen3-ASR target model load/inference: 0
- Nemotron target benchmark: 0
- German ASR quality: 0
- streaming ASR target-runtime: 0
- German end-to-end local voice: 0
- provider/model runtime: 0
- whole-system acceptance: false

## Next exact action

On an organ with the already-authorized target-host / `clay-direct-dev` bridge, inspect before mutation:

1. self-hosted runner service status and boot/start state;
2. `Runner.Listener` process presence;
3. diagnostic/connectivity logs;
4. exact installed runner version;
5. current registration/group/label eligibility;
6. then re-read the existing Qwen3-ASR, Trigger-7 hardware-roundtrip and Trigger-4 singleton jobs.

Only after the control-plane gate is resolved or an existing singleton becomes terminal should a successor target-runtime dispatch be considered. Preserve exact model/runtime/source identity and bounded evidence scope.
