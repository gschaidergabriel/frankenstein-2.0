# Frankenstein 2.0 — Perception Fabric

Status: PROJECT-OWNER CORE ARCHITECTURE REQUIREMENT
Date: 2026-08-29

## 1. Purpose

Frankenstein 2.0 must have a persistent, permission-gated perception fabric that lets GRID10 inspect allowed parts of the user's environment without requiring a VLM or LLM-token round for ordinary continuous perception.

The architecture separates dense physical capture from sparse cognitive attention:

```text
USER DASHBOARD / CAPABILITY POLICY
             |
             v
PERCEPTION SOURCES
webcam | displays | browser pixels | DOM/AX | user-activity metadata
             |
             v
SINGLE CAPTURE OWNER PER SOURCE
             |
             v
RETINA L0
quality | delta | motion | freshness | continuity | cheap salience
             |
             v
SPARSE EVENT STREAM
             |
             v
GRID10 ATTENTION / OBSERVE INTENT
             |
       +-----+-----+-----+
       |     |     |     |
    worker worker worker worker      dynamic 0..4
       +-----+-----+-----+
             |
       CORTEX L1/L2
OCR | tracking | UI | ROI | local CV | structural inspection
             |
             v
EPISTEMIC PERCEPT CLAIMS
OBSERVED != INFERRED != RETRIEVED
             |
             v
TEMPORAL + MULTIVIEW FUSION
             |
             v
WORLD MODEL / GWT / GRID10
             |
             +---- unresolved/valuable ----> re-look
                                           |
                                           v
                                   OPTIONAL VLM L3
```

The intended property is not "the system knows everything." The correct property is:

> Frankenstein can inspect any currently permitted source when useful, while preserving UNKNOWN, staleness, disagreement and provenance as first-class states.

## 2. Perception source model

A `PerceptionSource` is a typed inspectable source with exact identity, source generation, transport/locality, capability policy and freshness state.

Initial source classes should include:

- `WEBCAM`;
- `DISPLAY` / individual monitor;
- `BROWSER_VISUAL`;
- `BROWSER_STRUCTURAL` (DOM/layout/accessibility where available);
- `USER_ACTIVITY` metadata;
- later explicitly admitted local sensors/feeds.

Each physical/logical source has exactly one capture owner for acquisition. Analysis may fan out behind that owner.

## 3. Capability plane and dashboard

Every source must be controlled by an explicit user-visible capability policy. Recommended independent grants:

- `SEE` — source acquisition may occur;
- `ANALYZE` — local Retina/Cortex processing may occur;
- `MEMORY` — compact typed events may be admitted to durable memory according to memory policy;
- `RAW_RETENTION` — raw frames/images may be persisted;
- `REMOTE_FRAME` — raw/ROI visual data may cross the VPS bridge;
- `EXTERNAL_VLM` — an external/general VLM may inspect an explicitly selected frame/ROI.

Default policy should be privacy-minimizing: raw frames and dense visual features remain RAM/local-only unless explicitly allowed.

The existing perception enforcement distinction remains mandatory:

- `COMPUTE_OFF` = do not compute the head; absence is not inferred;
- `OUTPUT_OFF` = computation may exist but result is not emitted downstream;
- `MEMORY_OFF` = current output may exist but must not be durably admitted/reintroduced through memory;
- `ON` = permitted inside all other current policy constraints.

A capability snapshot must be immutable for one admitted observation operation and referenced by digest from resulting percept evidence.

The dashboard must provide at least:

- per-source enable/disable;
- per-capability controls;
- global `PAUSE RETINA`;
- global `ALL SENSORS OFF`;
- current source/worker activity;
- reason for current attention (`unresolved_target`, `salient_change`, `completion_check`, etc.);
- audit trail of capture/analysis/remote/VLM decisions;
- immediate permission withdrawal behavior.

## 4. Single-owner capture and bounded RAM

Never let independent Retina/Cortex workers each open the same physical capture device.

Required pattern:

```text
ONE PHYSICAL/LOGICAL SOURCE
    -> ONE CaptureOwner
    -> bounded RAM ring / FrameRef stream
    -> MANY read-only analysis consumers
```

Each capture buffer must have hard size/age limits and explicit drop/leaky behavior. Backpressure must prefer dropping stale perception work over starving the cognitive/runtime control plane.

## 5. Retina L0: continuous cheap perception

Retina L0 is the always-available low-cost layer. It should normally run without a language model and without producing language tokens.

Suitable operations include:

- frame identity/digest;
- temporal continuity;
- quality/exposure/blur checks;
- frame/block deltas;
- pHash or equivalent cheap change detection;
- motion/optical-flow-like local signals when affordable;
- freeze/stale detection;
- source freshness;
- cheap salience estimates.

Dense streams should become sparse events. A static screen should not cause continuous GRID10/VLM work merely because frames continue to arrive.

Token cost may be zero while physical CPU/GPU/RAM/bandwidth cost is non-zero. Therefore Perception Fabric must have its own bounded resource budget.

## 6. GRID10 attention and `ObserveIntent`

GRID10 decides where additional perception is valuable. Attention may be bottom-up or top-down:

- bottom-up: a permitted source reports material change/salience;
- top-down: current uncertainty, disagreement, goal state or completion deficit requires new evidence.

A concrete `ObserveIntent` should bind at least:

- intent/cycle/generation identity;
- `source_id`;
- optional ROI/region/window/tab target;
- requested local heads;
- targeted world-model atom(s)/question(s);
- freshness requirement / maximum age;
- priority;
- estimated compute cost/work budget;
- deadline or expiry when relevant;
- exact permission/capability snapshot digest;
- whether remote ROI/VLM escalation is permitted;
- provenance from the `VisualNeed`, salient event or completion deficit that caused the request.

`ObserveIntent != OBSERVATION` and has no truth authority.

## 7. Dynamic Retina/Cortex worker pool

Use a dynamic analysis pool with:

```text
MAX_WORKERS = 4
ACTIVE_WORKERS = 0..4
```

Four is the initial product ceiling, not a requirement to keep four workers resident or busy.

Workers are gaze/analysis slots, not independent capture owners and not independent world-model authorities. The scheduler assigns work based on current value and resource constraints.

A useful scheduling concept is:

```text
AttentionValue ~ Relevance * Uncertainty * Staleness * Salience * ExpectedInformationGain / ComputeCost
```

The exact function is an implementation/measurement question. Hard requirements are bounded concurrency, measurable admission/backpressure and no cognitive starvation.

## 8. Cortex L1/L2 without general VLM

Ordinary semantic-enough inspection should prefer local deterministic/specialist mechanisms before a generic VLM, including where applicable:

- OCR;
- UI/window/control detection;
- DOM/accessibility inspection;
- object/presence tracking;
- motion trajectories;
- local classifiers/specialist heads;
- ROI re-look;
- familiarity evidence;
- quality correction and re-capture.

Required escalation ladder:

```text
existing current local state
-> short temporal wait when useful
-> ROI re-look
-> quality/exposure correction
-> targeted local head
-> OCR/DOM/AX/pose/specialist
-> generic VLM only when still needed AND explicitly allowed
```

Presence-only or simple completion checks must not automatically invoke a cloud/general VLM.

## 9. Browser dual-sense perception

Web content should be inspectable through two independent views when available:

1. `BROWSER_VISUAL` — what was actually rendered on screen;
2. `BROWSER_STRUCTURAL` — DOM/layout/accessibility state.

Neither view automatically overrides the other. For example, a DOM button may exist while a visual overlay blocks it. Such disagreement is preserved as `MULTIVIEW_DISAGREEMENT` and may trigger a targeted re-look.

## 10. User-activity source

The baseline user-activity source should prefer contextual metadata rather than raw surveillance content. Useful admitted signals may include:

- active application/window;
- focus changes;
- active browser tab/domain when explicitly permitted;
- idle/active state;
- coarse keyboard/mouse activity rate;
- workflow phase changes;
- foreground/background transitions.

Raw keylogging, clipboard capture, password-field capture or equivalent high-sensitivity content is not part of the baseline source and requires a separate explicit high-sensitivity capability if ever implemented.

## 11. Temporal fusion

Multi-source fusion must be time-aware. Every percept carries source-time/monotonic ordering, generation, freshness/age and provenance.

Do not fuse stale states into a single current-world assertion simply because they arrived in the same cognitive cycle.

When source clocks cross machines, preserve clock uncertainty and avoid stronger ordering claims than evidence supports.

## 12. World-model ingress

The world model should normally receive compact typed claims/state changes rather than raw frames.

Examples:

- `screen.1.foreground_app = Firefox`;
- `page.checkout.button.enabled = true`;
- `person.presence = OBSERVED_PRESENT`;
- `terminal.job.state = running`;
- `display.2.change = salient`.

Every claim must preserve source, timestamp/freshness, confidence/evidence quality, epistemic type and provenance.

`OBSERVED`, `INFERRED` and `RETRIEVED` remain mechanically distinct. Repeated inference or memory does not become a current observation. Multi-view disagreement remains representable rather than being collapsed to majority truth.

## 13. VPS PerceptionWorldBridge

The VPS bridge should carry compact typed perception/world events by default, not permanent raw video streams.

Preferred pattern:

```text
LOCAL SOURCE
-> Capture/Retina/Cortex
-> typed event
-> VPS bridge
-> World Model / GRID10

GRID10 needs detail
-> ObserveIntent
-> local source/ROI inspection
-> typed result
-> optional permitted ROI/frame transfer only when necessary
```

Remote raw/ROI transfer requires `REMOTE_FRAME`. Generic external VLM requires `EXTERNAL_VLM`. The permission digest accompanies the request and result.

Bridge disconnect must not destroy local identity or local sensor control. Stale remote perception requests expire rather than executing later with outdated authority.

## 14. Resource law

Perception must not starve cognition or the state/control plane.

Required controls include:

- bounded frame queues;
- bounded worker queues;
- per-source cadence limits;
- dynamic worker activation 0..4;
- CPU/GPU/RAM ceilings or measurable adaptive budgets;
- stale-work dropping;
- backpressure;
- VLM escalation budgets;
- ability to degrade to cheap Retina-only monitoring under load.

The correct claim is `NO REQUIRED LLM TOKEN COST FOR BASELINE CONTINUOUS PERCEPTION`, not `ZERO COMPUTE COST`.

## 15. Acceptance gate

Perception Fabric is not accepted merely because individual Retina/Cortex modules exist.

A release candidate must prove a sustained multi-source scenario, with physical acceptance finally repeated on the user's local machine:

- four permitted sources available concurrently where the environment can provide them;
- dynamic workers move between 0 and 4;
- general VLM invocations remain zero during the baseline soak;
- raw frame persistence remains zero under default policy;
- RAM/queues remain bounded;
- salient changes create sparse events;
- GRID10 can issue targeted `ObserveIntent` re-looks;
- browser visual/structural disagreement is preserved;
- stale observations do not become current truth;
- permission withdrawal stops new capture/analysis/remote use as specified;
- `MEMORY_OFF` evidence is not later reintroduced from memory;
- world-model updates retain exact epistemic/source/freshness provenance;
- VPS bridge loss/reconnect does not fork identity or replay stale visual authority;
- cognition/control latency remains within the admitted envelope under perception load.

The VPS lane should build and falsify this architecture using synthetic/mock/available sources before handoff. The local Claude Code/Opus lane performs the final real-device/OS-permission acceptance and should not need to invent the architecture itself.
