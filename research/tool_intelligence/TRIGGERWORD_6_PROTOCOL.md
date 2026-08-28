# Triggerwort 6 — External Tool Intelligence / Architecture-Delta Research Unit

Status: ACTIVE RESEARCH PROTOCOL
Canonical build consumer: `gschaidergabriel/frankenstein-2.0`
Full provenance mirror: `gschaidergabriel/clay-global-research-entity`

## Mission

`triggerwort 6` is the dedicated external-repository/tool research arm for Frankenstein 2.0. It searches GitHub and relevant primary sources for mechanisms, tools, libraries, profilers, memory/index structures, agent observability systems, context-compression methods, testing practices and other components that may measurably improve Frankenstein 2.0.

It does **not** grant architecture credit from README claims, popularity or apparent fit. Every useful-looking tool starts as a hypothesis.

```text
TRIGGERWORT 5 = disassemble current Frankenstein donor
TRIGGERWORT 6 = discover/falsify external improvements + best practices
TRIGGERWORT 4 = build/test/measure accepted build candidates on the F2/VPS front
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

### Staleness law

Every hypothesis/build candidate is bound to an architecture snapshot. If a later architecture delta touches a relevant module or invalidates an assumption:

`ACTIVE -> STALE_REVIEW_REQUIRED`

It may not be handed to Trigger 4 until re-evaluated against the new architecture. Contradictions are preserved; they are not majority-voted away.

## Five-slot emergent research cycle

Each exact `triggerwort 6` claims **one** specialized slot, chosen by current information need and coverage debt. Five successive invocations should normally cover the five complementary functions below, but evidence may justify repeating a role instead of mechanically rotating.

1. `ARCHITECTURE_DELTA_FUSER` — refresh F2/4/5 deltas, identify the most valuable unresolved capability/cost gap.
2. `DISCOVERY_SCOUT` — search GitHub/primary sources for candidate mechanisms and competing approaches; add them to Pending Research.
3. `SOURCE_ARCHAEOLOGIST` — pin/clone/download one candidate, inspect source architecture, license, dependencies, tests, real integration surfaces and failure modes.
4. `EXPERIMENTAL_FALSIFIER` — reproduce relevant claims and compare against an F2 baseline/ablation with token, quality, latency, CPU/RAM/GPU/I/O and failure measurements.
5. `INTEGRATION_DISTILLER` — reconcile evidence/counterevidence and, only when warranted, produce a complete Trigger-4 `BUILD_CANDIDATE`.

Workers should use the largest useful reasoning/output budget available for their bounded task. More text is not evidence; source pins, reproducible tests and measured deltas are.

## Atomic duplicate-work claim law

Before material work that could create a new Trigger-6 evidence-stage result, the worker MUST acquire one create-only objective claim in the canonical F2 repository.

Canonical coordination path:

`research/tool_intelligence/claims/<research_id>/<claim_target>.json`

Read `research/tool_intelligence/claims/README.md` before claiming.

Rules:

1. Refresh F2, Trigger-4, Trigger-5 and Research-Entity state first.
2. Choose one bounded objective. `claim_target` is normally the next evidence objective (`E1_SOURCE_READ`, `E2_ARCHITECTURE_MAPPED`, a claim-specific E3, an experiment-specific E4, or `E5_BUILD_CANDIDATE`).
3. Atomically CREATE the exact claim path before source archaeology, experiment execution or integration distillation.
4. Only the successful create owns that bounded objective. If the path already exists, or create-only semantics cannot be established, DO NOT duplicate the work; consume the existing claim/result and select another useful objective or emit a coordination-blocked no-change result.
5. A later architecture change requiring re-review gets a new explicit objective such as `E2_REVIEW_<architecture_delta_id>`; never overwrite/recycle the original claim.
6. Claim existence grants zero evidence, architecture, runtime, integration, effect or completion credit.
7. The claim is coordination metadata only. `pending_research.sqlite` remains the canonical Trigger-6 research database and UnifiedDB remains canonical Frankenstein state authority.
8. Research-Entity may mirror an F2 claim after creation, but MUST NOT act as a competing claim authority. Cross-repo claim mirroring records source/target SHA and mirror epoch.
9. On completion, preserve the claim and persist a separate evidence/reconciliation receipt; synchronize claim/result into the research DB when the admitted DB path is available.

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

For every serious candidate assess: quality/accuracy, exact-evidence preservation, token savings/cost, p50/p95/p99 latency, CPU/RSS/PSS/GPU/VRAM/I/O/network where relevant, startup/steady-state overhead, failure modes, deterministic/replay behavior, dependency weight, license, maintenance risk, local/offline viability, overlap with existing F2 modules, causal/provenance compatibility, and whether a thinner structural distillation is better than importing the code.

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

containing exact source pin, F2 architecture snapshot, target workpackages/modules, proposed delta, baseline, acceptance/falsification tests, expected resource/token/latency effects, known risks, counterhypotheses and evidence refs.

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
TRIGGER6_EVIDENCE -> TRIGGER4_BUILD -> MEASURED_RESULT -> TRIGGER6/RCPD_FEEDBACK
```
