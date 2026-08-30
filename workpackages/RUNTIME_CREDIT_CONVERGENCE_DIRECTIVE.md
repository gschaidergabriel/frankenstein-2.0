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

## Architect interpretation

For coordination, treat lower-tier accepted components with zero higher-tier runtime credit as a **runtime-credit debt queue**. This queue is a prioritization view only; it is not a new canonical ledger or competing truth store. Exact workpackage claims, source, tests, receipts, reconciliation, and `PRODUCT_COMPLETION_LAW.md` remain authoritative for credit.

Primary optimization target:

```text
CONVERT EXISTING VERIFIED PARTS INTO VERIFIED INTEGRATED BEHAVIOR
BEFORE EXPANDING BREADTH
```
