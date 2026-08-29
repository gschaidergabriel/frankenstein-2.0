# Frankenstein 2.0

**Status:** active assembly / evidence-first build / not yet whole-system accepted

This repository is the canonical build, integration, measurement and evidence home for **Frankenstein 2.0**.

Frankenstein 2.0 is being built as a persistent cognitive system around one durable entity/state lineage, one GRID10/GWT cognitive controller, typed world knowledge, active perception, persistent agency, bounded delegation and verified effects.

The target is not "an LLM with memory" and not "a VPS service". The final product is a **portable local host harness/runtime** that can be installed from a release ZIP by Claude Code, Codex CLI or another supported coding-agent host, while the authorized VPS/bridge lane is used to build, integrate, test and falsify the system as far as possible before final real-machine acceptance.

Research/provenance source:

- research repository: `gschaidergabriel/clay-global-research-entity`
- research branch: `chatgpt/grid10-cognitive-envelope-control-20260828`
- Frankenstein donor: `gschaidergabriel/frankenstein`

> Repository code, CI and VPS evidence are never promoted to physical/local acceptance unless the corresponding real environment was actually exercised.

---

## 1. Product law: VPS builds, local Claude Code/Opus accepts

The construction topology and the final installed topology are intentionally different.

```text
AUTHORIZED VPS / VERIFIED BRIDGE
        |
        | build almost-complete Frankenstein 2.0
        | integrate cognitive/state/perception/voice/effect subsystems
        | run deterministic + integration + failure + restart + soak tests
        | build installer routes, service templates, adapters and verifier
        | package a reproducible release candidate
        v
FRANKENSTEIN-2.0.zip
        |
        v
LOCAL CLAUDE CODE / CODEX / OTHER SUPPORTED HOST
        |
        | detect real host + OS + devices
        | bind local paths/services/hooks
        | request actual user-approved permissions
        | bind webcam/screens/browser/microphone/effects
        | run real-machine acceptance + restart/readback tests
        v
LOCAL LIVE FRANKENSTEIN 2.0
```

### Build-completeness rule

The VPS lane should finish **everything that does not inherently require the final user's physical machine or OS permission grant**.

That includes, before handoff:

- GRID10 / GWT / Hyperposition logic;
- persistent AgencyState, goals, HOLD/WAKE/RESUME and restart semantics;
- UnifiedDB/state authority and causal identity;
- retrieval, memory, world model and process-learning logic;
- Perception Fabric contracts, scheduling, bridge semantics, simulations and falsifiers;
- CaptureOwner/Broker ownership and bounded queue behavior;
- temporal fusion and MultiView disagreement handling;
- dashboard capability-policy backend and audit contracts;
- voice/session logic that can be tested without the final physical devices;
- EffectGate / CompletionGate boundaries;
- host semantic ABI and Claude Code / Codex / generic-agent installer routes;
- service templates, manifest, hashes, verifier, update/rollback and diagnostics;
- synthetic host/device fixtures, failure injection, restart, concurrency and soak tests;
- optional VPS bridge attach/detach semantics.

The intended local lane is deliberately thin:

```text
READ SMALL INSTALLER ENTRY
-> VERIFY PACKAGE
-> DETECT REAL HOST/CAPABILITIES
-> INSTALL PREBUILT PAYLOAD
-> BIND LOCAL ADAPTERS
-> REQUEST USER PERMISSIONS
-> START/RESTART SERVICES
-> RUN PHYSICAL ACCEPTANCE PROBES
-> READ BACK STATE/RECEIPTS
-> ACCEPT | NATIVE | ADAPTED | DEGRADED | BLOCKED
```

If local Claude Code/Opus must invent major cognitive, state, perception, scheduling, bridge or authority architecture, the release candidate is considered incomplete and the repair should normally return to canonical VPS engineering with a regression test.

Canonical contract: [`architecture/VPS_BUILD_TO_LOCAL_ACCEPTANCE_CONTRACT.md`](architecture/VPS_BUILD_TO_LOCAL_ACCEPTANCE_CONTRACT.md)

---

## 2. Final distribution: one-handoff portable host harness

The strongest distribution property of the Frankenstein 1.x donor is retained.

The intended release flow is:

```text
ZIP
-> AI_START_HERE_DO_NOT_SCAN_REPO
-> host/capability discovery
-> Claude Code | Codex CLI | supported other host route
-> install one canonical local runtime/state lineage
-> bind native/adapted hooks and services
-> verify by real readback
-> LIVE
```

The final installed product obeys:

```text
LOCAL_USER_MACHINE = BASELINE_INSTALLED_PRODUCT_RUNTIME
VPS/HCU/REMOTE_COMPUTE = OPTIONAL_EXTENSION_OR_ACCELERATOR
VPS_BRIDGE != CANONICAL_PRODUCT_LOCATION
HOST_ADAPTER != COGNITIVE_STATE_AUTHORITY
HOST_SWITCH != NEW_FRANKENSTEIN
```

Claude Code, Codex and other supported coding agents are host/executor surfaces around the **same** Frankenstein identity and durable state. Switching host adapters must not create competing memories, goals or world truths.

See:

- [`PRODUCT_COMPLETION_LAW.md`](PRODUCT_COMPLETION_LAW.md)
- [`architecture/PORTABLE_HOST_HARNESS_AND_DISTRIBUTION_CONTRACT.md`](architecture/PORTABLE_HOST_HARNESS_AND_DISTRIBUTION_CONTRACT.md)
- [`AI_START_HERE_DO_NOT_SCAN_REPO/`](AI_START_HERE_DO_NOT_SCAN_REPO/)

---

## 3. One coherent cognitive loop

Frankenstein 2.0 is designed as **one persistent cognitive system**, not a collection of independent personas or competing controllers.

```text
WORLD / USER / TASK
        |
        v
PERCEPTION FABRIC / RETINA / TYPED OBSERVATION
        |
        v
PERSISTENT PULSE + AGENCY
        |
        v
UNIFIEDDB / CAUSAL STATE
        |
        v
EMERGENT RETRIEVAL + METHOD MEMORY
        |
        v
WORLD MODEL / OPTIONAL BOUNDED PROJECTIONS
        |-- sparse generative world basis
        |-- QUBO projection
        |-- rudimentary physics / NeRD-style projection
        `-- cognitive micro-lab
        |
        v
GRID10 + HYPERPOSITION
        |
        v
GLOBAL WORKSPACE / GWT SELECTION + BROADCAST + UPTAKE + RE-ENTRY
        |
        v
ACT | ASK | SPEAK | OBSERVE | WAIT | HOLD | DELEGATE
        |
        v
HOST / NATIVE CHILD / TOOL / VOICE / EXECUTOR
        |
        v
REAL OR SIMULATED OUTCOME
        |
        v
COMPLETION / PREDICTION RESIDUAL / CAUSAL CREDIT
        |
        v
FACT + EPISODE + METHOD + PROCESS-POLICY UPDATE
        |
        v
CHECKPOINT -> NEXT PULSE | HOLD | WAKE/RESUME
```

### Core cognitive capabilities

The target system should be able to:

- remain persistently oriented across sessions and process restarts;
- preserve goals, interests, open loops and deferred intentions outside model context;
- keep observation, inference, retrieval and simulation epistemically distinct;
- maintain competing hypotheses instead of collapsing uncertainty too early;
- choose information-seeking/observation actions when new evidence has higher value than immediate action;
- maintain a typed world model with freshness, provenance and disagreement;
- use bounded world projections/micro-experiments before risky or expensive action;
- delegate work while preserving exact parent/child/tool/result lineage;
- use voice, perception and executors as organs of the same cognitive body;
- stop, wait or HOLD when further cognition has poor expected value;
- verify effects and completion from evidence rather than executor assertion;
- learn reusable methods/process policies from measured outcomes without requiring model-weight updates.

---

## 4. Hard architecture laws

```text
MODEL_OUTPUT != WORLD_FACT
MEMORY != OBSERVATION
INFERENCE != OBSERVATION
RETRIEVAL != OBSERVATION
SIMULATION != OBSERVATION
WORLD_SLICE != CANONICAL_WORLD
UNKNOWN != FALSE
STALE != CURRENT
ARRIVAL_ORDER != EVENT_TIME_ORDER
GOAL_GENERATION != GOAL_ADOPTION
GOAL_ADOPTION != EFFECT_AUTHORIZATION
EXECUTION != COMPLETION
GWT_BROADCAST != CAUSAL_UPTAKE
HOST_ADAPTER != STATE_AUTHORITY
PERCEPT_EVENT != WORLD_TRUTH
CI_SUCCESS != PHYSICAL_RUNTIME_ACCEPTANCE
```

The system must fail closed on stale authority, stale permission snapshots, ambiguous causal identity and unsupported claims.

---

## 5. GRID10 and Global Workspace

GRID10 is a variable functional topology, not ten personalities.

| Cell | Main function |
|---|---|
| G1 | Situation / orientation / state framing |
| G2 | Goal, value and success criterion |
| G3 | Epistemic gap / cheapest useful information gain |
| G4 | Hypothesis + counterhypothesis + Hyperposition |
| G5 | World projection / prediction / causal consequences |
| G6 | Planning / decomposition / action sequence |
| G7 | Retrieval / transfer / factual + method memory |
| G8 | Micro-lab / simulation / falsification |
| G9 | Delegation / native child / recursion routing |
| G10 | Critic / stopping / HOLD / overprocessing control |

The Global Workspace must show measurable **selection, broadcast, uptake, causal influence and outcome re-entry**. A winner label or log entry alone is not evidence that workspace information changed downstream cognition.

GRID10 is also the intended controller for active perception: it can decide that it does not know something, identify where that uncertainty can be observed, and issue a bounded `ObserveIntent` rather than forcing the main LLM to continuously inspect visual input.

---

# 6. Perception Fabric — persistent perception, selective attention

Perception is a **core cognitive substrate** in Frankenstein 2.0, not an occasional VLM tool call.

The governing idea is:

> **Always capable of perception on user-authorized sources; pay expensive attention only when it is useful.**

Canonical loop:

```text
USER-APPROVED SOURCE
        |
        v
SINGLE CAPTURE OWNER
        |
        v
RETINA L0
quality / delta / motion / staleness / cheap change detection
(no LLM/VLM tokens; bounded physical compute still applies)
        |
        v
SALIENCE / EVENT STREAM
        |
        v
GRID10 ATTENTION
        |
        v
OBSERVE INTENT
        |
        +-------------------------------+
        |                               |
        v                               v
CORTEX SLOT 1                     CORTEX SLOT 2..4
OCR / UI / CV / tracking / ROI / specialist heads
        |                               |
        +---------------+---------------+
                        |
                        v
              EPISTEMIC PERCEPT CLAIMS
                        |
                        v
                 TEMPORAL FUSION
                        |
                        v
                 MULTIVIEW OVERLAY
                        |
                        v
                    WORLD MODEL
                        |
                        v
                    GWT / GRID10
                        |
                        `---- targeted re-look when needed

unresolved + explicitly permitted only
                        |
                        v
                 optional generic VLM
```

### 6.1 Sources and workers are independent

- configured/permitted source count: **`0..N`**;
- initial active Cortex analysis ceiling: **`0..4`**;
- one source may have zero active Cortex workers while cheap Retina L0 monitoring continues;
- more sources than workers are handled by bounded scheduling/backpressure rather than unbounded fanout;
- workers are dynamically assigned to source/ROI/head requests according to cognition and compute policy.

Example simultaneous sources include:

- webcam/camera;
- display/screen 1;
- display/screen 2;
- rendered browser/webpage pixels;
- browser DOM/layout/accessibility structure;
- local user-activity summaries;
- future typed sensors through the same capability/epistemic boundary.

### 6.2 Permission-first capability plane

Each source is governed by an exact capability snapshot.

Minimum source capabilities:

| Capability | Meaning |
|---|---|
| `SEE` | acquire current permitted source data |
| `ANALYZE` | run allowed local Cortex/specialist heads |
| `MEMORY` | persist compact typed percept evidence |
| `RAW_RETENTION` | persist raw sample/frame payload |
| `REMOTE_FRAME` | send raw/ROI payload across the bridge |
| `EXTERNAL_VLM` | allow generic external vision escalation |

These compose with head-level `ON / COMPUTE_OFF / OUTPUT_OFF / MEMORY_OFF` controls.

Important rules:

- no source is sampled or analyzed without current permission;
- every `ObserveIntent` binds the exact permission-snapshot digest;
- revocation/staleness invalidates queued intents rather than allowing old authority to survive;
- raw frame persistence is **OFF by default**;
- remote frame/ROI transport is **OFF unless explicitly granted**;
- external VLM use is a separate explicit capability and late escalation;
- dashboard policy must be the same authority used by the runtime, not a cosmetic UI preference copy.

### 6.3 Single CaptureOwner / multiple readers

Each physical/logical capture source has one owner and bounded in-memory fan-out.

```text
SOURCE A -> CaptureOwner A -> bounded FrameRef ring -> Retina/Cortex consumers
SOURCE B -> CaptureOwner B -> bounded FrameRef ring -> Retina/Cortex consumers
```

Workers do not independently reopen the same webcam/display source. This prevents the duplicate-open / `Device or resource busy` failure class and gives one authoritative source-local sequence/continuity domain.

### 6.4 Temporal and MultiView truth discipline

A webcam observation at one time and a screen observation several minutes earlier must not silently become one "current" state.

Perception therefore preserves:

- source-local monotonic order;
- source/capture time;
- freshness horizon;
- clock-domain identity;
- bridge receive time when relevant;
- bounded/estimated clock skew for cross-host fusion;
- explicit `UNKNOWN` / `UNALIGNED` when simultaneity cannot be established.

Different views may corroborate each other, but disagreement is preserved. DOM/AX saying an element exists does not automatically override rendered pixels showing that it is occluded or unusable. Disagreement can itself generate a new targeted look.

### 6.5 World model receives typed state, not raw pixels by default

The persistent world model should receive compact, provenance-bound state such as:

```text
screen.1.active_app = Firefox              [OBSERVED]
page.checkout.button.enabled = true        [OBSERVED, structural]
person.presence = present                  [OBSERVED, camera]
terminal.job.state = running               [OBSERVED]
button.usable = maybe                      [INFERRED]
```

Each claim carries source, time/freshness, confidence/evidence and epistemic type. `OBSERVED`, `INFERRED` and `RETRIEVED` remain mechanically distinct. Memory cannot overwrite a contradictory current observation.

### 6.6 Browser dual-sense

Where available, browser perception should expose at least two independently typed views:

1. rendered visual pixels/ROI;
2. structural DOM/layout/accessibility view.

Neither is automatically authoritative over the other.

### 6.7 User-activity context, not baseline keylogging

Useful baseline activity context includes active application/window, browser tab/domain when permitted, idle/active state, interaction rate, focus changes and work-phase summaries.

Raw keystrokes, clipboard contents and password-field capture are **not baseline perception** and require a separately designed high-sensitivity capability if ever introduced.

Canonical Perception Fabric documentation:

- [`architecture/PERCEPTION_FABRIC.md`](architecture/PERCEPTION_FABRIC.md)
- [`architecture/PERCEPTION_FABRIC_HARDENING_20260829.md`](architecture/PERCEPTION_FABRIC_HARDENING_20260829.md)
- [`workpackages/PERCEPTION_FABRIC_PHASE.json`](workpackages/PERCEPTION_FABRIC_PHASE.json)

---

## 7. Local edge / VPS bridge split

The intended data path avoids continuously shipping raw video to the VPS.

```text
LOCAL MACHINE
Capture -> Retina L0 -> permitted local Cortex -> typed percept events
                                                   |
                                                   v
                                             VPS BRIDGE
                                                   |
VPS / OPTIONAL REMOTE ORGAN                        |
World Model <-> GRID10/GWT <-> cognition <---------+
                                                   |
                                              ObserveIntent
                                                   v
LOCAL MACHINE
source/ROI/head execution -> typed observation -> bridge/world-model re-entry
```

Typed percept events are the default bridge payload. Raw frames/ROIs require `REMOTE_FRAME`; generic external visual inference additionally requires `EXTERNAL_VLM`.

After installation, the VPS bridge is an optional remote organ/accelerator of the same entity. Loss of the bridge may degrade remote compute, but must not fabricate observations, corrupt local identity or destroy durable local state continuity.

---

## 8. Processing self-improvement

Frankenstein 2.0 separates four learning products:

```text
Fact Memory     = what appears to be true
Episode Memory  = what happened
Method Memory   = which method worked under which conditions
Process Policy  = how cognition should be organized next time
```

Meaningful cognitive/build episodes may produce method evidence. Repeated evidence can become a hypothesis, then shadow/ablation testing, and only then a promoted method/process rule when held-out evidence supports it.

This is online process/meta-learning without requiring model-weight updates.

---

## 9. Evidence-first acceptance

Frankenstein 2.0 is intentionally strict about evidence scope.

```text
SOURCE_PRESENT != EXECUTED
DONOR_CODE != MIGRATED_COMPONENT
UNIT_TEST_PASS != INTEGRATION_ACCEPTANCE
REPOSITORY_CI != VPS_RUNTIME
VPS_RUNTIME != PHYSICAL_LOCAL_RUNTIME
SIMULATED_SENSOR != REAL_CAMERA/SCREEN
CANDIDATE_OBSERVATION != WORLD_TRUTH
EXECUTOR_DONE != VERIFIED_COMPLETION
COMPONENT_ACCEPTED != WHOLE_SYSTEM_COMPLETE
```

A bug is not closed because the symptom disappeared:

```text
FIXED = ROOT_CAUSE_CONFIRMED
      + ROOT_CAUSE_REMOVED
      + FIX_COMMIT
      + REGRESSION_TEST_PASS
      + REGRESSION_RECEIPT
```

Final whole-product acceptance remains a **real local-machine event** after the VPS pre-handoff gates have passed.

---

## 10. Perception acceptance target

The Perception Fabric is not accepted merely because its contracts compile.

The intended sustained acceptance includes at least:

- `0` configured/permitted sources without fabricated observations;
- `1`-source capture/event/re-look path;
- `N > worker_count` scheduling/backpressure;
- four simultaneously represented permitted sources when available;
- dynamic `0..4` Cortex analysis workers;
- zero generic VLM calls in the normal baseline soak;
- zero raw-frame persistence under default policy;
- bounded RAM and queues under sustained source change;
- typed world-model updates with epistemic/source/time provenance;
- GRID10-triggered re-look from uncertainty/completion deficit/disagreement;
- source add/remove/rebind churn without stale authority;
- permission revocation invalidating queued observation work;
- clock-skew falsification preventing false contemporaneous fusion;
- `MEMORY_OFF` evidence not later resurrected from durable memory;
- bridge disconnect/reconnect not replaying stale visual authority;
- perception degrading/dropping work before starving cognition/control;
- final local repetition on the actually enabled physical devices and OS permission surfaces.

---

## 11. Current repository implementation surfaces

The repository already contains F2-native implementation surfaces for major parts of the architecture, including examples such as:

```text
src/frankenstein2/
    active_sensing_fabric.py
    adaptive_compute.py
    agency_state.py
    cognitive_envelope.py
    epistemic_perception.py
    grid10_interface.py
    gwt_workspace.py
    gwt_uptake.py
    hyperposition.py
    perception_bridge.py
    perception_capture_broker.py
    perception_compute_binding.py
    perception_control.py
    perception_dashboard_policy.py
    perception_fabric.py
    perception_fabric_simulation.py
    perception_host_permissions.py
    perception_temporal.py
    persistent_agency_kernel.py
    persistent_pulse.py
    retina_capture_broker.py
    retina_fanin.py
    retina_pipeline.py
    visual_need.py
    world_maintenance.py
    world_multiview.py
```

Presence of these files does **not** by itself mean whole-system or physical-runtime acceptance. Use current workpackage receipts/reconciliations and exact test identities for acceptance claims.

---

## 12. Workpackages and current state

The README intentionally does not maintain a giant hand-edited checklist of every workpackage because parallel workers can make that view stale within minutes.

Use the repository's machine-readable and evidence-backed state instead:

- [`WORKPACKAGES.md`](WORKPACKAGES.md)
- [`workpackages/`](workpackages/)
- [`receipts/`](receipts/)
- [`checkpoints/`](checkpoints/)
- [`negative_results/`](negative_results/)
- [`architecture/`](architecture/)

Perception Fabric currently has its own required phase contract covering F2-WP-707 through F2-WP-714 in [`workpackages/PERCEPTION_FABRIC_PHASE.json`](workpackages/PERCEPTION_FABRIC_PHASE.json).

---

## 13. Triggerword-4 engineering law

A Triggerword-4 engineering step is not complete until the result is durable and evidence-scoped.

```text
TRIGGERWORT_4
=
REFRESH
+ CLAIM
+ BUILD
+ TEST
+ MEASURE
+ TRACE
+ COMMIT
+ ARCHIVE
+ RECONCILE
+ CHECKPOINT
```

Workers must refresh the current head/authority before mutation, preserve exact ancestry, avoid overwriting concurrent work, test bounded changes, retain negative results, distinguish CI/VPS/local evidence and leave a precise next frontier.

The authorized VPS/bridge lane is a valid and intended build/test environment. Final product locality does **not** mean development must avoid the VPS.

---

## 14. Repository target structure

```text
frankenstein-2.0/
|-- README.md
|-- PRODUCT_COMPLETION_LAW.md
|-- WORKPACKAGES.md
|-- AI_START_HERE_DO_NOT_SCAN_REPO/
|-- architecture/
|-- src/
|-- tests/
|-- workpackages/
|-- runs/
|-- measurements/
|-- receipts/
|-- negative_results/
|-- checkpoints/
|-- data/
|-- telemetry/
|-- bugs/
|-- hypotheses/
|-- provenance/
`-- archive/
```

The release target is a reproducible package whose installer can reconstruct the supported local runtime and whose evidence allows a researcher or maintainer to determine what was built, what was actually tested, what remains uncertain and which claims are valid at which scope.

---

## 15. Definition of "Frankenstein 2.0 complete"

Frankenstein 2.0 is not complete merely because source code exists, CI is green, GRID10 runs, Perception Fabric simulations pass or the VPS can execute a partial runtime.

At minimum, final completion requires the integrated cognitive loop and portable release gates to converge, followed by real local acceptance of the enabled host/device surfaces:

```text
persistent state + pulse
-> goals / open loops / retrieval / world model
-> GRID10 + Hyperposition
-> GWT selection/broadcast/uptake/re-entry
-> ACT | ASK | SPEAK | OBSERVE | WAIT | HOLD | DELEGATE
-> verified effect/observation
-> CompletionGate + causal credit
-> checkpoint + restart continuity
-> Perception Fabric re-look loop
-> reproducible ZIP + one-handoff installer
-> local Claude Code/Opus real-machine integration
-> state/device/permission/restart readback
-> ACCEPTED at the exact proven scope
```

The desired final experience is simple:

> **The VPS engineering lane hands over an almost-complete Frankenstein 2.0 release ZIP. Claude Code/Opus locally should mostly install, bind the real machine, request the user's permissions, run the final acceptance probes and report the truth — not rebuild Frankenstein.**
