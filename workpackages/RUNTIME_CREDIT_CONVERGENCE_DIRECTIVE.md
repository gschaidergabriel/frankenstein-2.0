# Frankenstein 2.0 — Runtime-Credit Convergence Directive

Status: **ACTIVE OWNER PRIORITY OVERLAY**

Scope: all current and future Frankenstein-2.0 build/research/test workers whose work can affect product convergence.

This directive changes **priority**, not evidence authority. `PRODUCT_COMPLETION_LAW.md`, claim/generation ownership, exact receipts, and fail-closed acceptance remain binding.

## Owner priority

The current failure mode to avoid is continued breadth-first component production while already accepted/source-ready components remain disconnected from higher-scope executable evidence.

Until superseded, select work in this order:

1. `RUNTIME_CREDIT_CLOSURE`
2. `INTEGRATION_BLOCKER`
3. `EVIDENCE_RECONCILIATION`
4. `NEW_COMPONENT`

`NEW_COMPONENT` is admissible only when the claimant identifies a concrete currently-open integration/runtime gate and shows that the smallest correct closure cannot be obtained by wiring, adapting, testing, or repairing existing components.

```text
MORE_COMPONENTS != MORE_PRODUCT
COMPONENT_ACCEPTANCE_WITH_RUNTIME_CREDIT_0 = INTEGRATION_DEBT_SIGNAL
INTEGRATION_DEBT != COMPONENT_FAILURE
SOURCE_OR_CI_PASS != TARGET_RUNTIME_CREDIT
TARGET_RUNTIME_CREDIT != WHOLE_PERSISTENT_LOOP_CREDIT
```

## Mandatory pre-claim classification

Before claiming material implementation work, classify it as one of the four classes above and record, in the claim or first durable claim-scoped delta:

- `target_completion_tier`: exact next tier from `PRODUCT_COMPLETION_LAW.md`;
- `integration_boundary`: exact upstream -> downstream boundary being closed;
- `existing_components`: accepted/source-ready mechanisms that will be fused or exercised;
- `blocking_deficit`: the smallest missing fact/code/config/test/runtime condition;
- `runtime_evidence_expected`: exact receipt/trace/result needed to promote credit;
- `duplicate_owner_check`: active claim/workpackage checked before mutation;
- `new_component_necessity`: required only for `NEW_COMPONENT`; explain why existing machinery cannot close the gate.

If these fields cannot be stated, default to `REVIEW_ONLY` until the integration target is resolved.

## Integration-first execution law

Prefer a bounded causal slice that connects existing parts and produces a higher-scope discriminator over another isolated feature.

Good work advances a real boundary such as:

```text
accepted component A
-> real adapter/route/state boundary
-> accepted component B
-> executable invocation
-> observed trace/result
-> exact scoped receipt
-> credit promotion only at the tier actually demonstrated
```

The worker should reuse existing accepted/source-ready components even when doing so exposes integration bugs. Those bugs are valuable convergence evidence and become higher priority than speculative adjacent features.

Do not create a second adapter, state authority, receipt format, scheduler, or abstraction merely to make integration locally convenient when the repository already has an intended mechanism.

## Runtime-credit closure

Runtime-credit work must bind evidence at the scope claimed. At minimum, preserve the identities required by the relevant acceptance contract, including exact source commit, artifact/config/runtime identity, invocation, observed result, and verification/trace references.

A queued job, deployable source tree, repository CI result, model output, or receipt-shaped file is not target-runtime execution by itself.

Never weaken a test, broaden an interpretation, or relabel component evidence merely to increase a progress metric.

## Worker routing under fan-out

When many workers are active:

1. refresh `main` and active pointers before choosing work;
2. prefer an unowned **integration boundary** over an unowned new feature;
3. if another worker already owns the same semantic boundary, do not fork it — contribute as `REVIEW_ONLY` / `CANDIDATE_FALSIFIER` or route to the next unowned dependency;
4. if a newer commit closes the selected boundary, re-enter and retarget immediately;
5. preserve useful duplicate tests/falsifiers as donor evidence, but retire duplicate mutation authority;
6. do not rewrite hot aggregate state merely to advertise activity.

One worker owning one component does not imply that no worker owns the cross-component boundary; inspect both workpackage claims and the actual target path.

### Terminal claim is not promotion-boundary ownership

A durable pointer under `workpackages/active/<workpackage_id>.json` may remain present after its recorded claim is terminal (`ACCEPTED`, `RECONCILED`, or an equivalent closed state). Its presence still governs mutation authority exactly as defined by `CLAIM_PROTOCOL.md`, but **it must not be interpreted as proof that the next higher-tier executable boundary is currently owned**.

For work selection, distinguish:

```text
CLOSED SOURCE/COMPONENT CLAIM
!=
LIVE OWNERSHIP OF ITS NEXT RUNTIME PROMOTION
```

Before declaring a runtime/integration boundary duplicated or blocked, inspect the pointer state, latest reconciliation/receipt, recent claim/dispatch evidence, and `next_exact_action`. If the underlying claim is terminal and its `next_exact_action` names a higher-tier runtime/host/integration discriminator, treat that discriminator as **unowned for scheduling purposes unless a separate live claim, singleton dispatch, or current mutation owner explicitly owns that semantic boundary**.

This clarification does not transfer mutation authority, authorize a new generation, or permit overwriting a terminal pointer. A worker that needs canonical source/state mutation must still follow `CLAIM_PROTOCOL.md`; an execution/review worker may instead run or route the already-admitted discriminator without inventing a new component or authority.

## Scheduler heuristic

When multiple safe tasks are available, maximize approximately:

```text
expected higher-tier credit gain * causal-path reuse * blocker reduction
-----------------------------------------------------------------------
duplicate risk + integration risk + execution cost + coordination cost
```

Prefer the smallest testable step that moves a boundary from a lower evidence tier toward `INTEGRATION`, `TARGET_RUNTIME`, `WHOLE_PERSISTENT_LOOP`, or later characterization tiers.

## Stop conditions for new breadth

Do not start a new component merely because:

- its workpackage is unclaimed;
- a runner is temporarily unavailable elsewhere;
- existing component tests are green;
- it is easy to implement in isolation;
- many workers are available.

Idle parallel capacity is not evidence that architectural breadth is the current bottleneck.

A new component remains appropriate when it is demonstrably the smallest missing dependency on a named high-priority integration/runtime path.

## Executable promotion-pressure rule

When an exact higher-tier discriminator is already executable on an authorized surface, source-only breadth must not consume the same decision slot merely because it is easier to merge.

Before selecting `INTEGRATION_BLOCKER`, `EVIDENCE_RECONCILIATION`, or `NEW_COMPONENT`, ask:

```text
IS THERE AN UNOWNED, EXECUTABLE, HIGHER-TIER PROBE
FOR AN ALREADY-INTEGRATED CRITICAL-PATH SUBJECT?
```

If **yes**, prefer that probe unless the candidate task is the demonstrably smallest missing dependency needed to make the probe valid. A worker blocked from invoking one execution surface may retarget to another independent named gate, but it must not reinterpret invocation inconvenience as evidence that more architecture is needed.

Examples of higher-information probes include:

- exact-source fresh-process persist -> terminate/crash -> reopen/readback;
- release artifact -> clean-host install -> semantic lifecycle/state readback;
- accepted component chain -> real target invocation -> trace-bound result;
- failure injection that can invalidate a claimed restart/recovery or whole-loop invariant.

This is a **work-selection throttle**, not a new acceptance mechanism. It never changes evidence tiers, claim authority, or receipt semantics.

For Architect/research review, evaluate recent activity by conversion rather than volume. Useful noncanonical diagnostic ratios include:

```text
higher_tier_promotions / material_merges
integration_or_falsifier_closures / material_merges
repository_only_closures / material_merges
blocked_executable_probes / executable_probes_attempted
```

These ratios are temporary observations for scheduling and retrospection only. They MUST NOT become a second progress ledger or mint credit.

Research rationale: current F2 history shows repeated repository-only closures while already-integrated restart/recovery and target-host subjects remain at zero higher-tier credit. Recent multi-agent software-engineering research likewise reports that coordination/specification gaps can dominate coding capability, and that adding agents without explicit shared interfaces or executable verification can reduce integration success. Treat stronger task specification and executable discriminators as scarce coordination resources.

## Runtime-subject churn throttle

Once an exact-source higher-tier runtime probe has been materially dispatched, queued, assigned, or otherwise bound to a concrete source subject, treat semantic mutation of that same integration boundary as **promotion-invalidating churn** unless the mutation is required to fix executable counterevidence or to make the already-bound probe valid.

This does not freeze the repository globally and does not grant the runtime probe mutation authority. It is a scheduling rule for the semantic boundary under test:

```text
BOUND RUNTIME SUBJECT + SEMANTIC SUCCESSOR BEFORE EXECUTION
= LIKELY HISTORICAL-ONLY PROMOTION + REPLAY DEBT
```

Before opening a successor generation on a boundary with a pending runtime probe, record one of:

- `RUNTIME_SUBJECT_INVARIANT`: the proposed delta is proven not to alter the executed semantic path, so the pending subject remains representative at the claimed scope;
- `RUNTIME_PROBE_INVALIDATED_BY_REQUIRED_REPAIR`: executable counterevidence requires the repair, so accept that the historical probe can only credit its exact subject and schedule at most one deduplicated successor replay after closure;
- `DEFER_UNTIL_RUNTIME_RESULT`: the delta is useful but not required for validity, so defer it until the pending discriminator resolves.

A later green historical runtime receipt plus newer repository CI is never composed into current-generation runtime credit without explicit semantic-invariance evidence. Prefer reducing **promotion staleness latency** — time from exact-source probe binding to terminal executed evidence — over producing additional same-boundary source generations.

For research/architect diagnosis, count a runtime probe as `staled_before_execution` when a newer accepted or active semantic generation touches its integration boundary before the probe executes. This is a noncanonical scheduling observation only; it is not a new ledger or acceptance field.

Rationale: recent F2 evidence shows an exact WP900/WP206/WP901 runtime subject becoming historical while the self-hosted execution remained queued and newer WP206/WP901 semantic generations landed. That converts scarce runtime capacity into historical-only evidence and creates mandatory replay debt. Multi-agent SWE research similarly favors dependency-aware central delegation, isolated mutation, structured integration, and executable verification over uncontrolled concurrent modification of interdependent artifacts.

## Architect interpretation

For coordination, treat lower-tier accepted components with zero higher-tier runtime credit as a **runtime-credit debt queue**. This queue is a prioritization view only; it is not a new canonical ledger or competing truth store. Exact workpackage claims, source, tests, receipts, reconciliation, and `PRODUCT_COMPLETION_LAW.md` remain authoritative for credit.

Primary optimization target:

```text
CONVERT EXISTING VERIFIED PARTS INTO VERIFIED INTEGRATED BEHAVIOR
BEFORE EXPANDING BREADTH
```
