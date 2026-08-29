# Perception Fabric Hardening — Source Cardinality, Time, Permission and Local Boundary

Status: PROJECT-OWNER REQUIRED HARDENING
Date: 2026-08-29
Parent: `architecture/PERCEPTION_FABRIC.md`

This file tightens the Perception Fabric contract. Where wording is more specific than the parent contract, this hardening governs.

## 1. Source cardinality is 0..N, not four

The architecture must never assume four configured or active perception sources.

```text
CONFIGURED_SOURCES = 0..N
PERMITTED_SOURCES <= CONFIGURED_SOURCES
ACTIVE_CAPTURE_OWNERS <= PERMITTED_SOURCES
ACTIVE_ANALYSIS_WORKERS = 0..4 initially
```

The number four is only the initial concurrent **analysis-worker** ceiling and the preferred stress scenario when four independent sources can be synthesized or provided. It is not a source-count limit and not a minimum.

Required cases include zero sources, one source, sources appearing/disappearing at runtime, permission changes without source deletion, more configured sources than analysis slots, and multiple logical sources behind one physical transport where ownership remains unambiguous.

## 2. Time contract is a hard ABI requirement

Every observation/percept/event admitted for fusion must carry enough timing information to avoid accidental false simultaneity.

Required semantics should include the equivalent of:

- `source_time` when meaningful;
- `capture_monotonic_ns` from the capture owner;
- processing/observation monotonic time when relevant;
- source generation/epoch;
- freshness/max-age contract;
- transport/bridge receive time when remote;
- explicit clock-domain identity;
- `clock_uncertainty_ns` or equivalent bounded/UNKNOWN skew representation for cross-clock comparisons.

Fusion must use an explicit admissible temporal window. If claims cannot be proven contemporaneous inside the active window/skew bound, they must not be collapsed into one stronger `NOW` assertion.

`ARRIVAL_ORDER != EVENT_TIME_ORDER`

`SAME_GRID_CYCLE != SAME_REAL_WORLD_TIME`

Unknown or excessive skew yields UNKNOWN/UNALIGNED, not guessed ordering.

## 3. Permission snapshot is execution authority for perception

Every `ObserveIntent` binds the exact immutable permission/capability snapshot digest under which it was admitted.

At execution time the capture/analysis/bridge layer must verify that the snapshot remains admissible under current owner policy. A stale grant cannot be revived merely because an intent was valid when generated.

Fail closed when source permission, `REMOTE_FRAME`, or `EXTERNAL_VLM` has been revoked; when the source generation changed; when the intent expired; or when the permission digest is unknown/unverifiable.

A downstream component may narrow rights, never widen them.

## 4. CaptureOwner is mandatory architecture; concrete OS binding is local

The **CaptureOwner/Broker semantics and implementation** are built and tested on the VPS/repository side with synthetic/mock/available transports. Claude Code must not have to invent the ownership protocol locally.

The final local lane binds that prebuilt broker to the real machine: actual camera/display/browser handles, PipeWire/XDG portal or platform equivalents, user permission prompts/grants, and host-specific service/socket paths.

```text
VPS: CaptureOwner state machine + broker + fan-out + bounded queues + tests
LOCAL: real device/OS adapter plugged into the prebuilt CaptureOwner interface
```

The historical duplicate-device-open / `Device busy` class requires an explicit regression falsifier.

## 5. Local acceptance is wiring + real-device falsification

Local Claude Code/Opus should receive prebuilt source/capability contracts, immutable permission snapshots, `ObserveIntent`, CaptureOwner/Broker, the dynamic 0..4 analysis scheduler, epistemic claims, temporal fusion, MultiView disagreement handling, PerceptionWorldBridge, audit receipts, dashboard policy/API contract, and deterministic/synthetic acceptance tests.

Local work should primarily be real sensor bridge binding, real OS permissions, dashboard-to-capability-plane binding, installed browser/DOM/AX integration, device timing/skew characterization, actual end-to-end/performance soak, and host-specific edge repairs that are upstreamed when general.

If Claude Code must design these contracts from scratch, the VPS handoff failed.

## 6. Stress/acceptance matrix

The suite must cover:

1. `0 sources` — cognition remains healthy and no observation is fabricated;
2. `1 source` — basic capture/event/re-look path;
3. `N sources > workers` — scheduler queues/drops by value without fixed-source assumptions;
4. `4 simultaneous useful sources` — all four analysis slots can be used when justified;
5. source churn — add/remove/rebind while running;
6. permission revoke during queued `ObserveIntent` — fail closed;
7. clock skew/uncertainty — no false contemporaneous fusion;
8. stale transport delivery — no promotion to current truth;
9. bridge disconnect/reconnect — no replay of expired rights or stale visual requests;
10. VLM disabled — baseline perception and targeted local re-look continue without a general VLM;
11. `MEMORY_OFF` — no later resurrection from durable memory;
12. resource pressure — perception degrades/drops work before starving GRID/state/control latency.

The four-source no-VLM soak remains a strong gate when four sources can be synthesized or provided, while product source cardinality remains `0..N`.
