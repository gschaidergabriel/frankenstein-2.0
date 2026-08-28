# Frankenstein 2.0

**Status:** active assembly / evidence-first build

This repository is the canonical build, integration, measurement and evidence home for **Frankenstein 2.0**.

The research entity repository remains a research/provenance source. Frankenstein 2.0 itself is assembled, tested, measured and archived **here**.

Initial research source binding:

- source repository: `gschaidergabriel/clay-global-research-entity`
- source branch: `chatgpt/grid10-cognitive-envelope-control-20260828`
- source commit at repository initialization: `ff74dc52be6037b6d80f65ba3327e4b0ef7d03d5`
- current Frankenstein donor: `gschaidergabriel/frankenstein`

---

## 1. What Frankenstein 2.0 is intended to become

Frankenstein 2.0 is a persistent cognitive software system built from the strongest surviving mechanisms of the current Frankenstein donor, Agent-Zero lineage, Project-Frankenstein lineage, Clay/EntityOS/HCU research and the newer GRID10/GWT/Hyperposition architecture.

The target is **one coherent cognitive loop**, not a collection of independent personas:

```text
WORLD / USER / TASK
        ↓
RETINA / PERCEPTION / OBSERVATION
        ↓
PERSISTENT PULSE + AGENCY
        ↓
UNIFIEDDB / CAUSAL STATE
        ↓
EMERGENT RETRIEVAL + METHOD MEMORY
        ↓
OPTIONAL WORLD PROJECTIONS
        ├─ sparse generative world model
        ├─ QUBO projection
        ├─ NeRD / rudimentary physics
        └─ cognitive micro-lab experiments
        ↓
GRID10 + HYPERPOSITION
        ↓
GLOBAL WORKSPACE / GWT BROADCAST + UPTAKE
        ↓
ACT | ASK | SPEAK | OBSERVE | WAIT | HOLD | DELEGATE
        ↓
NATIVE CHILD / TOOL / VOICE / EXECUTOR
        ↓
REAL OR SIMULATED OUTCOME
        ↓
COMPLETION / PREDICTION RESIDUAL / CAUSAL CREDIT
        ↓
FACT + EPISODE + METHOD + PROCESS-POLICY UPDATE
        ↓
NEXT PULSE
```

### Intended capabilities

Frankenstein 2.0 should eventually be able to:

- remain persistently oriented across sessions/restarts without treating model context as canonical memory;
- maintain interests, open loops, goals and deferred intentions even when no user is currently speaking;
- perceive a user/task/world through a pre-cognitive Retina and distinguish observation from inference;
- generate competing hypotheses and counterhypotheses instead of collapsing uncertainty too early;
- choose targeted information-seeking actions when uncertainty is more important than immediate goal progress;
- build bounded internal world projections and compare multiple views of the same situation;
- use a reduced physical simulator / NeRD-style physics to estimate plausible physical consequences when useful;
- use a cognitive micro-lab to test mathematical, logical, causal and physical consistency before real action;
- learn reusable **methods of thinking**, not only facts, through Recursive Cognitive Process Distillation;
- adapt retrieval, decomposition, child-agent fanout, recursion depth and context size from measured outcomes;
- delegate real building/debugging work to native child agents while preserving exact workpackage → child → tool → result lineage;
- interact by voice as one identity, with Voice acting as an organ of the same GRID/GWT cognition;
- stop, wait or hold when further cognition has poor expected value;
- measure its own latency, resource use, critical paths, mistakes, hypotheses, bugs and recovery behavior;
- be tested on held-out interactive cognitive environments rather than optimized only for one benchmark or one public game set.

---

## 2. Core architecture laws

```text
MODEL_OUTPUT != WORLD_FACT
MEMORY != OBSERVATION
SIMULATION != OBSERVATION
WORLD_SLICE != CANONICAL_WORLD
GOAL_GENERATION != GOAL_ADOPTION
GOAL_ADOPTION != EFFECT_EXECUTION
EXECUTION != COMPLETION
UNKNOWN != FALSE
UNCERTAINTY -> TARGETED_EXPERIMENT when expected value is positive
MANY_SIGNAL_READERS -> ONE_AGGREGATED_CONTROL_DECISION -> ONE_POLICY_GATED_WRITER
ONE COGNITIVE CYCLE -> ONE LATCHED CONTROL SNAPSHOT
```

Security hardening is a later phase after the functional architecture is sufficiently complete to know what must be secured. Causal identity, provenance, completion evidence, sandbox isolation and reproducible measurement remain mandatory now because they are correctness requirements, not merely security features.

---

## 3. GRID10 — intended functional topology

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
| G9 | Delegation / native child / R0-R3 recursion routing |
| G10 | Critic / stopping / HOLD / overprocessing control |

The Global Workspace must have measurable selection, broadcast, uptake, causal influence and outcome re-entry. Merely writing a winner label is not sufficient.

---

## 4. Processing self-improvement

Frankenstein 2.0 should preserve four distinct learning products:

```text
Fact Memory     = what appears to be true
Episode Memory  = what happened
Method Memory   = which method worked under which conditions
Process Policy  = how cognition should be organized next time
```

Each meaningful cognitive/build episode should be able to produce a `MethodEpisode`. Repeated evidence may produce a `MethodHypothesis`, then shadow/ablation testing, then a promoted `MethodRule` only when held-out evidence supports it.

This is **online process/meta-learning without requiring model-weight updates**.

---

# 5. OPEN WORKPACKAGES

Status codes:

- `[ ]` NOT_STARTED
- `[-]` IN_PROGRESS / HOLD
- `[x]` ACCEPTED_AT_SCOPE with evidence in this repository

## Phase 0 — Repository and evidence spine

- [x] **F2-WP-000** Create canonical `gschaidergabriel/frankenstein-2.0` repository.
- [-] **F2-WP-001** Canonical architecture README and donor/adoption status views.
- [ ] **F2-WP-002** Machine-readable workpackage state, claims, generations and acceptance evidence.
- [ ] **F2-WP-003** Research-Entity → F2 provenance mirror with exact source SHA/tree receipts.
- [ ] **F2-WP-004** Immutable per-test run-package format and artifact index.
- [ ] **F2-WP-005** Project-wide telemetry databases and collectors.

## Phase 1 — UnifiedDB and causal coordination

- [ ] **F2-WP-100** Canonical UnifiedDB schema/resolver/fingerprint.
- [ ] **F2-WP-101** `session_id/agent_id/task_id/turn_id/causal_id/generation` identity spine.
- [ ] **F2-WP-102** Workpackage → native Agent tool-use → child `agent_id` → result binding.
- [ ] **F2-WP-103** Per-recipient delivery lifecycle `PENDING→OFFERED→ACKED`.
- [ ] **F2-WP-104** Deferred causal return envelope for retrieval/voice/tool results.
- [ ] **F2-WP-105** Typed effect/execution/completion outcome lineage for correctness.

## Phase 2 — Persistent pulse and agency

- [ ] **F2-WP-200** Persistent Pulse kernel.
- [ ] **F2-WP-201** StateFingerprint and cheap state-change detection.
- [ ] **F2-WP-202** PredictionContract / prediction residual.
- [ ] **F2-WP-203** AgencyState, interests, open loops and deferred intents.
- [ ] **F2-WP-204** GoalCandidate → TRIAL → ACTIVE → HOLD/COMPLETE lifecycle.
- [ ] **F2-WP-205** Wake conditions and valid no-op WAIT/HOLD behavior.

## Phase 3 — Memory, retrieval and process learning

- [ ] **F2-WP-300** Memory evolution / salience / degradation without destructive forgetting.
- [ ] **F2-WP-301** Emergent multi-view retrieval.
- [ ] **F2-WP-302** Familiarity and prediction-error binding.
- [ ] **F2-WP-303** Fact/Episode/Method/Process-Policy memory separation.
- [ ] **F2-WP-304** Recursive Cognitive Process Distillation (RCPD).
- [ ] **F2-WP-305** Processing-credit assignment and method ablation/shadow promotion.
- [ ] **F2-WP-306** ContextCompiler / bounded ContextViews / do-not-repeat memory.

## Phase 4 — World model and cognitive micro-lab

- [ ] **F2-WP-400** Sparse generative world basis + typed operators.
- [ ] **F2-WP-401** Xeno-style assimilator/composer and gardener/falsifier/compressor.
- [ ] **F2-WP-402** QUBO world projection adapter.
- [ ] **F2-WP-403** NeRD / rudimentary physics projection.
- [ ] **F2-WP-404** Cognitive Micro-Lab for bounded consistency experiments.
- [ ] **F2-WP-405** Multi-view world projection overlay and disagreement analysis.
- [ ] **F2-WP-406** VisualNeed / active sensing / post-action re-look.

## Phase 5 — GRID10, Hyperposition and Global Workspace

- [-] **F2-WP-500** GRID10 SituationFrame and cycle contract.
- [-] **F2-WP-501** Cognitive Envelope / latched ControlSnapshot.
- [-] **F2-WP-502** Hyperposition branch representation and discriminator selection.
- [ ] **F2-WP-503** G1–G10 functional interfaces and budgets.
- [ ] **F2-WP-504** Epistemic Action Selection.
- [ ] **F2-WP-505** GRID adaptive compute allocation.
- [ ] **F2-WP-506** GWT selection + broadcast.
- [ ] **F2-WP-507** GWT uptake and causal-influence capture.
- [ ] **F2-WP-508** GWT re-entry / child provenance / no parent-misattribution tests.
- [ ] **F2-WP-509** HOLD/stop/rumination and expected-value controller.

## Phase 6 — Native child agents and recursive harness

- [ ] **F2-WP-600** `DIRECT_SMALL` vs `DELEGATE_BUILD` router.
- [ ] **F2-WP-601** Native Child ABI and stable WorkExecution identity.
- [ ] **F2-WP-602** Handoff/reconcile with mechanically valid evidence.
- [ ] **F2-WP-603** R0 deterministic / R1 model recursion / R2 child harness / R3 adaptive selection.
- [ ] **F2-WP-604** Child resume/replacement/nested-spawn and stale-generation handling.
- [ ] **F2-WP-605** Child latency, cost, result quality and method-credit telemetry.

## Phase 7 — Retina, presence and voice

- [ ] **F2-WP-700** Retina capture/quality/delta/temporal continuity pipeline.
- [ ] **F2-WP-701** ObservedEvidence vs InferredHypothesis vs RetrievalPrior typing.
- [ ] **F2-WP-702** `COMPUTE_OFF/OUTPUT_OFF/MEMORY_OFF` mechanical separation.
- [ ] **F2-WP-703** PresenceKernel and FreshPresenceSnapshot.
- [ ] **F2-WP-704** VoiceIntent / VoiceSessionCapsule / VoiceOutcome loop.
- [ ] **F2-WP-705** Realtime conversation + barge-in + silence + tool-return re-entry.
- [ ] **F2-WP-706** Soft familiarity/identity evidence without hard-auth semantics.

## Phase 8 — Cognitive test suite

- [ ] **F2-WP-800** Held-out interactive micro-world harness.
- [ ] **F2-WP-801** Orientation tests.
- [ ] **F2-WP-802** Information-seeking / targeted experiment tests.
- [ ] **F2-WP-803** World-model prediction tests.
- [ ] **F2-WP-804** Goal inference tests.
- [ ] **F2-WP-805** Compositional transfer / recovery / efficient planning tests.
- [ ] **F2-WP-806** Cognitive lesion/rescue suite.
- [ ] **F2-WP-807** ARC-AGI-3-style general agentic-core falsifier with no public-game overfit credit.

## Phase 9 — Whole-system integration

- [ ] **F2-WP-900** Full persistent cognition loop.
- [ ] **F2-WP-901** Restart/recovery with unfinished-work continuation.
- [ ] **F2-WP-902** Whole-system latency/resource/quality characterization.
- [ ] **F2-WP-903** Long-running soak and degradation tests.
- [ ] **F2-WP-904** Cross-module failure injection and root-cause closure.

## Phase 10 — Security hardening after functional architecture freeze

- [ ] **F2-WP-1000** Attack-surface inventory from the finished architecture.
- [ ] **F2-WP-1001** Authentication/authorization/effect hardening.
- [ ] **F2-WP-1002** Secret handling and supply-chain hardening.
- [ ] **F2-WP-1003** Adversarial security acceptance suite.

---

# 6. COMPLETED / ACCEPTED IN THIS REPOSITORY

This section records only work that has become canonical in **this** repository.

| Workpackage | Status | Evidence |
|---|---|---|
| F2-WP-000 | ACCEPTED_AT_SCOPE | repository exists and is writable |
| F2-WP-001 | IN_PROGRESS | this README is the first canonical architecture snapshot |

No cognitive component is claimed as fully integrated merely because a donor implementation exists elsewhere.

---

# 7. DONOR MODULE / ARCHITECTURE ADOPTION MATRIX

Adoption classes:

```text
DIRECT_ADOPT       = source is close enough to move with minor packaging changes
ADAPT_TO_GRID      = substantial implementation exists but must be rebound to F2 state/GRID/causal ABI
CONCEPT_DISTILL    = valuable mechanism exists; implementation should not be copied wholesale
REIMPLEMENT        = F2 needs a new implementation using donor lessons
UNKNOWN            = source-level audit still required
```

| Area | Donor status | F2 adoption | Current judgement |
|---|---|---|---|
| UnifiedDB / durable memory substrate | substantial live donor code | ADAPT_TO_GRID | strong reusable base; coordination identity needs F2 successor |
| Handoff / reconcile workpackages | live donor mechanism | ADAPT_TO_GRID | useful evidence discipline; native child binding incomplete |
| Native Claude child tooling | runtime capability exists outside donor logic | ADAPT_TO_GRID | must bind `paket_id → tool_use_id → agent_id → result` |
| GRID10 cognitive envelope | active research/staging implementation | ADAPT_TO_GRID | meaningful source exists; latest runtime gates still nonterminal |
| Hyperposition | extensive research/tests | ADAPT_TO_GRID | mechanism survives; needs F2 cycle ABI |
| Current Frankenstein Voice / Realtime | substantial live donor implementation | ADAPT_TO_GRID | largely reusable organ; causal return semantics need repair |
| Visual Cortex / perception control | substantial donor + measured tests | ADAPT_TO_GRID | reuse pipeline ideas/source; bind to permanent Retina/Presence |
| Presence / familiarity | donor mechanisms + recent forensics | ADAPT_TO_GRID | preserve evidence softness; repair candidate-level attribution |
| Memory retrieval / MicroClay | substantial live donor implementation | ADAPT_TO_GRID | keep retrieval mechanisms; remove session/latest-entry credit shortcuts |
| Memory evolution / degradation | historical Project-Frankenstein lineage | CONCEPT_DISTILL | preserve non-destructive fading/salience idea; source-level extraction required |
| Consciousness/Pulse daemon | historical Project-Frankenstein lineage | CONCEPT_DISTILL | useful precursor for persistent pulse; F2 loop is substantially different |
| Agent-Zero cognition lineage | broad donor architecture | CONCEPT_DISTILL | keep autonomous cognition strengths, align through GRID10 rather than reuse wholesale |
| QUBO world model | donor/research lineage | ADAPT_TO_GRID | candidate second projection of world state; exact source migration audit required |
| NeRD physics | donor/research lineage | ADAPT_TO_GRID | promising bounded physics organ; exact source and performance audit required |
| Cognitive Micro-Lab | architecture synthesis + donor lab lineage | REIMPLEMENT | new reduced universal experiment environment required |
| Sparse generative world substrate | current research design | REIMPLEMENT | F2-native bounded WorldSlice architecture |
| Xeno assimilator/gardener concepts | current research design | CONCEPT_DISTILL | useful decomposition/compression roles, not separate identity |
| Effect/completion correctness | donor + EntityOS research | REIMPLEMENT | typed per-invocation causal successor required |
| RLM/RAH/context virtualization | external/research harness evidence | ADAPT_TO_GRID | adaptive R0/R1/R2/R3 router required |
| Recursive Cognitive Process Distillation | distilled from multi-worker research process | REIMPLEMENT | new intrinsic process-learning subsystem |
| ARC-AGI-3-style cognitive unit tests | benchmark-derived methodology | REIMPLEMENT | held-out internal worlds required; no public-game overfit |
| Complete telemetry/data spine | requirements synthesized for F2 | REIMPLEMENT | F2-native observability system |

This matrix is intentionally conservative: **donor availability is not the same as F2 completion**.

---

# 8. Mandatory experimental data spine

Every test series must produce an immutable package under:

```text
runs/<test_series>/<run_id>/
```

containing or referencing all instrumented system data for that run.

Project-wide databases are planned under `data/`:

```text
data/system_telemetry.sqlite
    all instrumented Frankenstein-2.0 component/system logs

data/communications.sqlite
    all Frankenstein-produced communication events + causal metadata

data/hypotheses.sqlite
    hypotheses, counterhypotheses, evidence and targeted tests

data/bugs.sqlite
    bugs, symptoms, root causes, fixes and regression evidence

data/grid10_telemetry.sqlite
    GRID cells, proposals, arbitration, broadcast, uptake, re-entry, budgets

data/performance.sqlite
    resource samples, state intervals, traces, latency spans and aggregates
```

A test is not considered fully instrumented unless every participating process/system declared in its test manifest has an active collector or an explicit `NOT_OBSERVABLE` record.

### Bug rule

```text
SYMPTOM_GONE != FIXED
PATCH_APPLIED != FIXED
FIXED = ROOT_CAUSE_CONFIRMED
        + ROOT_CAUSE_REMOVED
        + FIX_COMMIT
        + REGRESSION_TEST_PASS
        + REGRESSION_RECEIPT
```

The goal is not to hide bugs. The goal is to close **root causes**.

### Latency rule

All meaningful internal transitions should be traceable with:

```text
trace_id
span_id
parent_span_id
start/end wall clock
start/end monotonic clock
component/subsystem/operation
system state
workpackage/run/task/agent/invocation identity
queue_wait / compute / io_wait / network_wait / model_wait / db_wait / child_wait / unattributed
```

End-to-end latency is the **critical causal path**, not the sum of parallel work.

### Resource/performance states

At minimum characterize:

```text
BOOT_INITIALIZE
IDLE_HOLD
PULSE_ONLY
RETINA_IDLE
RETINA_ACTIVE
GRID_BURST
RETRIEVAL
WORLD_PROJECTION
QUBO
MICROLAB
NERD_PHYSICS
VOICE_SESSION
DIRECT_SMALL
CHILD_BUILD
MULTI_CHILD
RECURSIVE_HARNESS
COMPLETION_REENTRY
RECOVERY_RESTART
WHOLE_LOOP
STRESS_SATURATION
```

For each useful state/component collect CPU, memory, disk I/O, DB time, network, GPU/VRAM if present, model calls/tokens, latency, queueing and other available resource counters.

---

# 9. Triggerword-4 worker law for this repository

Once a Triggerword-4 worker is doing Frankenstein-2.0 build work, a coherent step is not finished until it has been made durable here.

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
+ CHECK_OFF_OR_RECORD_DEFICIT
+ CHECKPOINT
```

Workers must:

1. refresh current `main` before writing;
2. select/claim a workpackage and generation;
3. preserve exact source/donor ancestry;
4. commit coherent build steps rather than one giant opaque terminal dump;
5. archive tests, metrics, receipts and important negative results;
6. update workpackage status only when evidence supports it;
7. never overwrite a newer worker checkpoint with stale state;
8. leave `next_exact_action` for continuation;
9. keep the current `gschaidergabriel/frankenstein` donor read-only unless a separate explicit task says otherwise.

---

# 10. Repository target structure

```text
frankenstein-2.0/
├── README.md
├── WORKPACKAGES.md
├── DONOR_ADOPTION_MATRIX.md
├── WORKER_PROTOCOL.md
├── ARTIFACT_INDEX.md
├── architecture/
├── src/
├── tests/
├── research_mirror/
├── workpackages/
├── runs/
├── measurements/
├── receipts/
├── negative_results/
├── checkpoints/
├── data/
├── telemetry/
├── bugs/
├── hypotheses/
└── archive/
```

The end state is intentionally simple: after the build, a researcher should be able to clone **this one repository** and reconstruct what Frankenstein 2.0 is, how it was built, which experiments changed it, what remains uncertain, which root causes remain open and how much each cognitive organ costs in latency/resources.
