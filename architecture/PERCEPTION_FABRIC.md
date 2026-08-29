# Frankenstein 2.0 — Perception Fabric

Status: PROJECT-OWNER CORE ARCHITECTURE INVARIANT
Date: 2026-08-29
Hardening: `architecture/PERCEPTION_FABRIC_HARDENING_20260829.md`

## Product intent

Frankenstein 2.0 treats perception as a persistent, permission-governed cognitive substrate rather than an occasional VLM prompt.

The canonical loop is:

`PERMISSIONED SOURCE -> CAPTURE OWNER -> RETINA L0 -> SALIENCE -> GRID10 ATTENTION -> OBSERVE INTENT -> 0..4 CORTEX ANALYSIS WORKERS (initial ceiling) -> EPISTEMIC PERCEPTS -> TEMPORAL/MULTIVIEW FUSION -> WORLD MODEL -> GWT/GRID10 -> RELOOK WHEN NEEDED`

Source cardinality is independently `0..N`; the initial Cortex analysis concurrency ceiling is `0..4`.

Generic VLM inference is an explicit late escalation, not the default visual path.

## Build/deployment split

The development target is the authorized VPS/bridge lane. The goal of VPS-side assembly is to finish contracts, deterministic control, world-model integration, scheduling, bridge protocol, tests, replay fixtures, simulators and release artifacts so that final local integration in Claude Code/Opus is primarily host/hardware wiring plus real acceptance.

The local machine remains the final sensor/effect boundary because actual webcam/display/browser/OS permissions exist there. The VPS may run GRID10, world-model and other compute through the same entity lineage, but local hardware bindings must not be re-designed during final acceptance.

## Hard invariants

1. **Permission first.** No source may be sampled, analyzed, persisted, bridged or VLM-escalated unless the exact current capability snapshot permits it.
2. **Stale permission fails closed.** Every ObserveIntent binds an exact permission snapshot digest. Execution against a newer/different snapshot requires re-authorization/replanning.
3. **Single capture owner per source.** A camera/display/browser-render stream has one capture owner and bounded in-memory fan-out. Multiple analysis workers must not contend for the underlying device.
4. **Retina L0 is token-free.** Quality/delta/motion/staleness and similar cheap local signals do not consume LLM/VLM tokens. They still consume bounded physical compute and must be budgeted.
5. **Perception cannot starve cognition.** Capture queues and worker queues are bounded. Backpressure drops/coalesces stale low-value work rather than unbounded buffering.
6. **Dynamic workers.** The reference worker pool is `0..4` active Cortex analysis slots, policy-bounded and load-adaptive. Four is a starting ceiling, not an assumption that four sources always exist.
7. **Epistemic separation.** OBSERVED, INFERRED and RETRIEVED remain distinct. Memory cannot overwrite current observation. Unknown and stale remain first-class states.
8. **Temporal binding.** Every observation carries source time, monotonic sequence, freshness bounds and clock/skew metadata where cross-host fusion occurs.
9. **Multi-view preserves disagreement.** Webcam, screen, DOM/AX and other views do not vote a contradiction into truth. Disagreement may trigger targeted re-look.
10. **World model stores typed state, not raw pixels by default.** Raw frames/dense features are RAM/local-only unless explicit capability permits retention/bridge egress.
11. **VLM is late escalation.** Preferred ladder: cached current state -> wait -> ROI re-look -> quality/exposure -> deterministic/local specialist head -> OCR/pose/UI/CV specialist -> generic VLM when still needed and allowed.
12. **User remains in control.** Dashboard policy can revoke SEE/ANALYZE/MEMORY/RAW_RETENTION/REMOTE_FRAME/EXTERNAL_VLM per source. Revocation must stop new work promptly and invalidate stale intents.
13. **No keylogger-by-default.** User-activity context should prefer active app/window/tab/domain, idle/activity rate, focus changes and interaction summaries. Raw keystrokes, clipboard and password fields require separate high-sensitivity capability and are not part of baseline perception.

## Source model

A `PerceptionSource` represents a permission-addressable sensory origin, for example:

- webcam/camera;
- display/screen;
- browser rendered pixels;
- browser DOM/layout/accessibility tree;
- local user-activity summary;
- future microphone/non-visual structured sensors through equivalent typed adapters.

Source count is `0..N`. Worker count is independent of source count.

## Capability plane

Minimum capabilities:

- `SEE` — acquire current source samples/metadata;
- `ANALYZE` — run allowed local heads over acquired data;
- `MEMORY` — persist compact typed percept evidence;
- `RAW_RETENTION` — persist raw frame/sample payload;
- `REMOTE_FRAME` — send raw/ROI payload across the VPS bridge;
- `EXTERNAL_VLM` — invoke generic external vision inference.

These capabilities compose with the existing perception-head `ON / COMPUTE_OFF / OUTPUT_OFF / MEMORY_OFF` control plane. Source permission answers *whether this source/path is allowed*. Head control answers *which computation/egress/memory behavior is allowed once a source is admitted*.

## ObserveIntent

A top-down look request must bind at least:

- intent id / cycle / generation;
- `source_id`;
- exact `permission_snapshot_sha256`;
- optional ROI/region selector;
- requested head ids;
- target world-model atom ids / reasons;
- freshness requirement;
- deadline/expiry;
- priority;
- bounded compute estimate/budget;
- whether raw payload, bridge egress and VLM escalation are allowed;
- provenance back to VisualNeed / WorldSlice / MultiView disagreement when applicable.

ObserveIntent is a candidate sensing request, not execution authority and not world truth.

## Capture and worker topology

```text
Source A ---- CaptureOwner A ---- bounded FrameRef ring ----+--> Cortex slot 1
                                                            +--> Cortex slot 2
Source B ---- CaptureOwner B ---- bounded FrameRef ring --------> Cortex slot 3
Source C ---- CaptureOwner C ---- bounded FrameRef ring --------> Cortex slot 4

Retina L0 runs continuously/cheaply per admitted source.
Cortex slots are assigned dynamically by GRID10 attention and scheduler policy.
```

A source may have no active Cortex worker while Retina L0 still measures cheap change/staleness. A worker may move between sources/ROIs across observation windows.

Reference scheduling score may combine relevance, uncertainty, staleness, salience, expected information gain and compute cost, but the exact formula remains replaceable and must be measured rather than treated as truth.

## Browser dual-sense rule

Browser perception should expose at least two separately typed views where available:

1. rendered visual view (pixels/ROI);
2. structural view (DOM/layout/accessibility).

They may corroborate but neither dominates by type. If structural state says an element exists while rendered view shows it occluded/unusable, preserve disagreement and request re-look/interaction-specific evidence.

## Edge/VPS bridge contract

Default data flow:

```text
LOCAL EDGE: Capture -> Retina L0 -> permitted local Cortex -> typed percept events
                                                   |
                                                   v
                                             VPS BRIDGE
                                                   |
VPS: World Model <-> GRID10/GWT <-> cognition -----+
                                                   |
                                            ObserveIntent
                                                   v
LOCAL EDGE: targeted source/ROI/head execution -> typed observation
```

Typed events are the default bridge payload. Raw frames/ROIs require explicit `REMOTE_FRAME` capability. External VLM additionally requires `EXTERNAL_VLM` capability.

## Temporal fusion law

Cross-source fusion must never use arrival order as event time. Contracts must preserve:

- source-local monotonic sequence;
- source capture time;
- bridge receive time where applicable;
- declared freshness horizon;
- clock-domain identity;
- estimated/allowed skew for cross-host joins.

Observations outside their freshness/skew window cannot silently contribute to a current-world snapshot.

## Acceptance target

The Perception Fabric is not accepted merely because contracts compile. A target integration run must eventually prove:

- source cardinality `0..N` without fixed-source assumptions;
- four simultaneously permissioned sources can be represented when four real or synthetic sources are available;
- `0..4` Cortex workers allocate dynamically;
- normal run invokes zero generic VLM calls;
- raw-frame persistence remains zero under default policy;
- RAM/queues remain bounded under sustained change;
- typed percepts update the world model with epistemic/source/time provenance;
- GRID10 can issue a re-look from uncertainty or multi-view disagreement;
- stale permission hashes block execution;
- permission revocation stops new source work and invalidates outstanding intents;
- contradictory views remain contradictory until new evidence resolves them;
- perception load obeys cognitive compute ceilings and cannot starve the main loop;
- optional VPS bridge loss degrades remote cognition/compute without fabricating local observation or corrupting entity state.

The complete cardinality/time/revocation/resource falsifier matrix is defined in `architecture/PERCEPTION_FABRIC_HARDENING_20260829.md` and `workpackages/PERCEPTION_FABRIC_PHASE.json`.

## Local final integration responsibility

Final Claude Code/Opus integration should primarily bind already-defined adapters to actual OS primitives (camera, PipeWire/portal/display, browser CDP/DOM/AX, local activity APIs), connect the dashboard to the capability store, and run the hardware acceptance suite. If local integration must invent new epistemic, CaptureOwner/Broker, scheduling, permission, world-model or bridge semantics, VPS-side assembly is incomplete.
