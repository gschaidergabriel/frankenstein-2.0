# Triggerwort 6 — External Tool Intelligence / Architecture-Delta Research Unit

Status: ACTIVE RESEARCH PROTOCOL
Canonical build consumer: `gschaidergabriel/frankenstein-2.0`
Full provenance mirror: `gschaidergabriel/clay-global-research-entity`

## Mission

`6`, `triggerword 6`, and `triggerwort 6` are the same canonical Trigger-6 macro.

Trigger 6 is the dedicated external-repository/tool research arm for Frankenstein 2.0. It searches GitHub and relevant primary sources for mechanisms, tools, libraries, profilers, memory/index structures, agent observability systems, context-compression methods, testing practices and other components that may measurably improve Frankenstein 2.0.

It does **not** grant architecture credit from README claims, popularity or apparent fit. Every useful-looking tool starts as a hypothesis.

```text
TRIGGERWORT 5 = disassemble current Frankenstein donor
TRIGGERWORT 6 = maximum-depth external research/falsification + architecture-delta synthesis
TRIGGERWORT 4 = build/test/measure accepted build candidates on the F2/VPS front
```

## Trigger-6 maximum-research law

Trigger 6 is deliberately **not** a resource-conservation mode for the research worker.

On an exact Trigger-6 invocation:

1. Research as long and as deeply as the current platform, tool, context, safety and authority limits permit.
2. Use the largest useful reasoning, browsing, source-reading, comparison, experiment and visible-output budget available.
3. Do not stop early merely to save ChatGPT tokens, tool calls, browsing effort or research time.
4. Prefer broad triangulation plus deep source archaeology over a shallow shortlist when additional work can materially reduce uncertainty.
5. Continue through additional non-duplicate research objectives in the same invocation when the current objective reaches a useful terminal evidence state and meaningful research capacity remains.
6. Produce as many **useful, evidence-bearing** tokens as materially improve the research result. Do not pad with repetition or fabricated detail merely to increase raw token count.
7. Preserve hypotheses, counterhypotheses, negative results, exact source pins, measurements, contradictions and falsifiers rather than compressing them away for brevity.
8. If a hard platform/output/context limit ends the run, persist/restate a precise continuation checkpoint so the next Trigger-6 invocation resumes rather than restarts.

The optimization target for Trigger-6 research is therefore:

```text
MAXIMIZE VERIFIED RESEARCH DEPTH + BREADTH + INFORMATION GAIN
WITHIN CURRENT PLATFORM LIMITS
```

not:

```text
MINIMIZE RESEARCH TOKENS OR TOOL USE
```

### Research cost versus Frankenstein runtime cost

Do not confuse **research-resource usage** with the **resource-efficiency target of Frankenstein 2.0**.

- Trigger 6 may spend substantial research tokens/tool effort to find a better design.
- Frankenstein 2.0 itself should be aggressively measured and optimized for low token consumption and low unnecessary compute/resource use without sacrificing required capability, evidence quality or correctness.
- A research method is not rejected merely because investigating it is expensive; a runtime/build candidate is judged by its measured F2 value and operating cost.

In short:

```text
TRIGGER6_RESEARCH = MAXIMUM_USEFUL_DEPTH
FRANKENSTEIN2_RUNTIME = MINIMUM_NECESSARY_TOKENS_AND_RESOURCES_FOR_REQUIRED_QUALITY
```

## Mandatory live architecture fusion

Every Trigger-6 run MUST refresh the current architecture before choosing or evaluating work.

Inputs include at minimum:

- current `frankenstein-2.0/main` HEAD;
- `README.md`, `WORKPACKAGES.md`, donor/adoption matrix and current architecture files;
- current Trigger-4 checkpoints, receipts, measurements and accepted/failed workpackages;
- current Trigger-5 ingest/forensic deltas from the Research Entity;
- new Research-Entity architecture deltas since the previous Trigger-6 cursor;
- existing Trigger-6 hypotheses, experiments, negative results and Trigger-4 feedback.

The run emits a versioned `ArchitectureDeltaFusion` carrying exact source SHAs, affected modules, contradictions, supersessions and unresolved gaps.

### Architecture-delta production law

Trigger 6 is not limited to tool discovery. When research materially changes the best-supported understanding of Frankenstein 2.0, emit a versioned architecture delta in the same run when useful.

An architecture delta is warranted when evidence supports one or more of:

- a component should be added, removed, merged, split or replaced;
- control/data/state/effect authority boundaries should change;
- a cheaper token/context/runtime path can preserve required behavior;
- an existing mechanism is redundant, overbuilt, too expensive or causally weak;
- a new measurement/falsifier changes an architectural assumption;
- integration order or workpackage dependency should change;
- a previously attractive candidate should be retired or demoted.

Architecture deltas must include exact evidence refs, affected modules/workpackages, expected benefit, token/resource implications, counterhypotheses, falsifier/acceptance gates and evidence scope. Do not invent a delta when evidence does not justify one.

### Staleness law

Every hypothesis/build candidate is bound to an architecture snapshot. If a later architecture delta touches a relevant module or invalidates an assumption:

`ACTIVE -> STALE_REVIEW_REQUIRED`

It may not be handed to Trigger 4 until re-evaluated against the new architecture. Contradictions are preserved; they are not majority-voted away.

## Five-function emergent research cycle

The five roles below are complementary **coverage functions**, not a hard rule that one Trigger-6 invocation may perform only one small slot.

1. `ARCHITECTURE_DELTA_FUSER` — refresh F2/4/5 deltas, identify the most valuable unresolved capability/cost gap.
2. `DISCOVERY_SCOUT` — search GitHub/primary sources for candidate mechanisms and competing approaches; add them to Pending Research.
3. `SOURCE_ARCHAEOLOGIST` — pin/clone/download candidates, inspect source architecture, license, dependencies, tests, real integration surfaces and failure modes.
4. `EXPERIMENTAL_FALSIFIER` — reproduce relevant claims and compare against an F2 baseline/ablation with token, quality, latency, CPU/RAM/GPU/I/O and failure measurements.
5. `INTEGRATION_DISTILLER` — reconcile evidence/counterevidence and, only when warranted, produce complete Trigger-4 `BUILD_CANDIDATE` packets and architecture deltas.

One exact Trigger-6 invocation should pursue the highest-information non-duplicate objective first, then continue into additional roles/objectives whenever claims/authority permit and useful research capacity remains. Five successive invocations should still accumulate broad role coverage, but no artificial one-slot stopping rule may override the maximum-research law.

More text alone is not evidence; source pins, reproducible tests, measured deltas and explicit reasoning boundaries are. But brevity is also not a goal during Trigger 6 when more evidence-bearing detail materially improves the result.

## Atomic duplicate-work claim law

Before material work that could create a new Trigger-6 evidence-stage result, the worker MUST acquire one create-only objective claim in the canonical F2 repository.

Canonical coordination path:

`research/tool_intelligence/claims/<research_id>/<claim_target>.json`

Read `research/tool_intelligence/claims/README.md` before claiming.

Rules:

1. Refresh F2, Trigger-4, Trigger-5 and Research-Entity state first.
2. Choose one bounded objective. `claim_target` is normally the next evidence objective (`E1_SOURCE_READ`, `E2_ARCHITECTURE_MAPPED`, a claim-specific E3, an experiment-specific E4, or `E5_BUILD_CANDIDATE`).
3. Atomically CREATE the exact claim path before source archaeology, experiment execution or integration distillation.
4. Only the successful create owns that bounded objective. If the path already exists, or create-only semantics cannot be established, DO NOT duplicate the work; consume the existing claim/result and select another useful objective.
5. A later architecture change requiring re-review gets a new explicit objective such as `E2_REVIEW_<architecture_delta_id>`; never overwrite/recycle the original claim.
6. Claim existence grants zero evidence, architecture, runtime, integration, effect or completion credit.
7. The claim is coordination metadata only. `pending_research.sqlite` remains the canonical Trigger-6 research database and UnifiedDB remains canonical Frankenstein state authority.
8. Research-Entity may mirror an F2 claim after creation, but MUST NOT act as a competing claim authority. Cross-repo claim mirroring records source/target SHA and mirror epoch.
9. On completion, preserve the claim and persist a separate evidence/reconciliation receipt; synchronize claim/result into the research DB when the admitted DB path is available.
10. A blocked/already-owned objective does **not** end Trigger 6 while other high-value non-duplicate objectives are available; move to the next useful objective.

The 2026-08-29 concurrent `R6-SEED-005` AgentSight E2 audits are the motivating negative coordination result: same source + same objective + same architecture context is one research result with complementary receipts, not independent replication.

## Evidence ladder

- `E0 SEED` — link/idea only; zero architecture credit.
- `E1 SOURCE_READ` — source/README/API inspected and pinned.
- `E2 ARCHITECTURE_MAPPED` — actual integration surface, dependencies, overlap and counterhypothesis mapped.
- `E3 CLAIM_REPRODUCED` — relevant upstream claim independently reproduced or falsified.
- `E4 F2_ABLATION` — compared against current F2 baseline under equivalent workload.
- `E5 BUILD_CANDIDATE` — measured net benefit or strategically justified capability, exact source pin and executable integration/test plan.
- `E6 F2_ACCEPTED` — Trigger-4 VPS worker built/tested/measured it and F2 acceptance evidence exists.

README benchmark numbers are evidence about upstream claims only until reproduced.

## Required evaluation dimensions

For every serious candidate assess: quality/accuracy, exact-evidence preservation, **F2 runtime token consumption**, context/prompt size, model-call count, token savings/cost, p50/p95/p99 latency, CPU/RSS/PSS/GPU/VRAM/I/O/network where relevant, startup/steady-state overhead, cache/reuse behavior, failure modes, deterministic/replay behavior, dependency weight, license, maintenance risk, local/offline viability, overlap with existing F2 modules, causal/provenance compatibility, and whether a thinner structural distillation is better than importing the code.

Token/resource efficiency is a first-class Frankenstein-2.0 architecture criterion. Prefer, when quality/evidence are equivalent or better:

- fewer model calls and shorter prompts/contexts;
- typed compact state over repeated prose restatement;
- deterministic routing/gates over unnecessary LLM arbitration;
- retrieval of the smallest sufficient evidence slice over whole-history replay;
- caching/reuse of stable computations and embeddings;
- bounded resident-model/decode concurrency appropriate to actual workload;
- structural distillation over importing heavyweight frameworks;
- measured CPU/RAM/GPU/I/O reductions without hiding costs elsewhere.

Efficiency never grants correctness credit by itself and must not erase evidence, provenance, uncertainty, safety or required capabilities.

## Pending Research database

Canonical DB path:

`research/tool_intelligence/pending_research.sqlite`

It stores seeds, hypotheses/counterhypotheses, architecture snapshots/deltas, experiments, evidence, worker-cycle claims, build candidates and Trigger-4 feedback. A byte-identical or explicitly versioned mirror is maintained in the Research Entity; divergence is an error to reconcile, never silent last-writer-wins.

## Promoted repository archive

A repository reaches:

`research/tool_intelligence/promoted_repos/<candidate_id>/`

only after it becomes a real build hypothesis. The package must contain at least:

- `SOURCE_LOCK.json` with repo, commit/tree SHA and retrieval time;
- license/dependency assessment;
- source snapshot or reproducible fetch/bundle manifest when licensing/size permits;
- `EVALUATION.md`;
- `COUNTERHYPOTHESES.md`;
- `INTEGRATION_CONCEPT.md`;
- experiment/measurement refs;
- exact F2 architecture snapshot against which it was promoted.

## Trigger-4 handoff

An E5 candidate MUST emit:

`trigger4/inbox/tool_research/<candidate_id>.json`

containing exact source pin, F2 architecture snapshot, target workpackages/modules, proposed delta, baseline, acceptance/falsification tests, expected and measured resource/token/latency effects where available, known risks, counterhypotheses and evidence refs.

Trigger-4 VPS workers consume this packet, build/test/measure it, and return:

`trigger4/outcomes/tool_research/<candidate_id>.json`

The real build result is fed back into this research DB and into RCPD/MethodMemory. A Trigger-6 upstream success never marks an F2 integration complete by itself.

## Core invariants

```text
EXTERNAL_REPO_POPULARITY != F2_EVIDENCE
UPSTREAM_BENCHMARK != F2_BENCHMARK
README_CLAIM != REPRODUCED_CLAIM
DERIVED_INDEX != UNIFIEDDB_SOURCE_OF_TRUTH
TRANSPORT/OBSERVABILITY_TOOL != COGNITIVE_TRUTH
BUILD_CANDIDATE != INTEGRATED_COMPONENT
ARCHITECTURE_CHANGE -> RECHECK_AFFECTED_RESEARCH
CLAIM_EXISTS != RESEARCH_EVIDENCE
FAILED_CREATE_ONLY_CLAIM -> DO_NOT_DUPLICATE_OBJECTIVE
BLOCKED_OBJECTIVE != END_TRIGGER6_WHEN_OTHER_HIGH_VALUE_WORK_EXISTS
TRIGGER6_RESEARCH_BUDGET != F2_RUNTIME_RESOURCE_BUDGET
TRIGGER6_MAXIMIZES_USEFUL_RESEARCH_DEPTH
F2_RUNTIME_MINIMIZES_NECESSARY_TOKEN_AND_RESOURCE_COST_FOR_REQUIRED_QUALITY
TRIGGER6_EVIDENCE -> TRIGGER4_BUILD -> MEASURED_RESULT -> TRIGGER6/RCPD_FEEDBACK
```