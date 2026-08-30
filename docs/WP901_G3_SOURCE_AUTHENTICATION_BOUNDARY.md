# F2-WP-901 G3 — Restart Source-Authentication Boundary

Status: generation-3 component contract; repository source/tests/CI only.

## Why G3 exists

WP901 G2 closed deterministic `RestartContinuationPlan` disposition/ref/flag/reason-code consistency at repository-CI scope. It intentionally left a separate question open: the G2 planner accepts checkpoint and whole-loop identities from `PersistedRestartEvidence` and compares them with caller-supplied `expected_*` values. REVIEW_ONLY PR #683 reproduced that mutually self-consistent values can name checkpoint/seal identities never authenticated from concrete WP206/WP900 sources. REVIEW_ONLY PR #669 separately reproduced mixed causal-lineage admission.

G3 does not reopen G2 semantics. It adds a source-binding adapter before G2.

## Canonical component path

```text
CausalIdentity
+ UnifiedDBAuthorityRef
+ concrete PersistentAgencyCheckpoint
+ concrete WholePersistentLoopSeal
+ concrete LoopOutcomeEvidence
+ PersistedRestartEvidence
        |
        v
bind_restart_sources()
        |
        | derives exact checkpoint/seal/outcome ids + digests
        | verifies direct-successor generation
        | verifies seal -> checkpoint and seal -> outcome
        | verifies exact causal identity provenance ref across all four evidence surfaces
        v
RestartSourceBinding
        |
        v
plan_restart_continuation_from_sources()
        |
        | passes only derived principal values
        v
accepted G2 plan_restart_continuation()
        |
        v
RestartContinuationPlan candidate
```

## Evidence boundary

`UnifiedDBAuthorityRef` is a reference to separately admitted canonical-state authority. It is **not** proof that a particular persisted row was loaded. `RestartSourceBinding` therefore explicitly emits `persisted_row_attestation = NOT_OBSERVED` and has no truth/effect/completion/persistence authority.

The G3 component claim is narrower:

- it eliminates the G2 API's mutually self-attested principal-string path from the canonical component ingress;
- it binds the planner to concrete typed WP206/WP900/outcome objects and exact causal provenance;
- it preserves the accepted G2 planner unchanged as the deterministic inner function;
- it does not claim UnifiedDB row loading, loader-consumption attestation, target runtime, VPS runtime, physical GRID10, semantic GWT/J-Space, effects, completion, training, or whole-system acceptance.

A later integration gate must bind these typed objects to actual persisted-row/load evidence before target-runtime source-authentication credit is granted.

## Fail-closed cases

G3 rejects:

- checkpoint generation != causal identity generation;
- checkpoint generation != whole-loop seal generation + 1;
- seal next-checkpoint id/digest != concrete checkpoint;
- seal outcome id/digest != concrete outcome;
- restart evidence principal ids/digests != concrete objects;
- restart evidence outcome status/digest != concrete outcome;
- missing exact causal identity provenance ref in checkpoint, whole-loop seal, outcome, or restart evidence;
- expected restart-evidence digest != the bound evidence digest.

## G2 preservation

The G3 CI runs all accepted WP901 G2 suites in the same job before/with the G3 regressions. G3 does not modify `restart_recovery_continuation.py`.
