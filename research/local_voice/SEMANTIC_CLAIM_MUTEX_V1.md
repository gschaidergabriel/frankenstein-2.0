# Trigger 7 Semantic Claim Mutex v1

Status: **SOURCE-IMPLEMENTED / STATICALLY TESTED / NOT TARGET-RUNTIME EVIDENCE**  
Date: 2026-08-30

## Problem

The legacy Trigger-7 duplicate-work rule used the human-readable claim path as the mutex:

`research/local_voice/claims/<research_id>/<objective>.json`

Concurrent workers can describe the same bounded experiment with different IDs or objective names, so distinct create-only paths can still schedule the same VPS/model experiment.

Therefore:

```text
CREATE_ONLY_HUMAN_PATH != SEMANTIC_OBJECTIVE_MUTEX
DISTINCT_NAMES MAY REPRESENT THE SAME EXPERIMENT
QUEUED_WORKFLOW != EXECUTION_EVIDENCE
```

The preserved negative result is:

`research/local_voice/negative_results/2026-08-30_T7_SEMANTIC_DUPLICATE_CLAIM_MUTEX_FAILURE.md`

## v1 canonical semantic object

Before creating a new material Trigger-7 claim or execution workflow, compile a bounded semantic object with exactly these key-bearing fields:

```json
{
  "schema": "T7_SEMANTIC_OBJECTIVE/v1",
  "family": "<admitted canonical family>",
  "target_surface": "<admitted canonical target>",
  "subject": "<admitted canonical subject>",
  "evidence_scope": "<admitted canonical evidence scope>",
  "generation": 1
}
```

Free-text descriptions, worker/model/session identity, research IDs, human objective names, timestamps, branch names and workflow filenames are **not** part of the semantic identity.

Canonical JSON serialization is UTF-8 JSON with sorted keys and separators `,` / `:`. The semantic key is:

```text
semantic_key = sha256(canonical_json)
```

The canonical create-only path is:

```text
research/local_voice/semantic_claims/<semantic_key>.json
```

Reference compiler:

`research/local_voice/tools/t7_semantic_claim.py`

## Required claim order

For every new bounded Trigger-7 objective:

1. Refresh F2 `main` and current Trigger-7 state.
2. Determine the smallest bounded semantic objective.
3. Compile it with `t7_semantic_claim.py`.
4. **Create the semantic claim path first, atomically and create-only.**
5. If that path already exists, lose the claim, read the existing owner/state, and route to another nonduplicate objective. Do not create a second human claim or second workflow.
6. Only after winning the semantic claim may a human-readable claim file be created under `claims/`.
7. Any workflow for the objective must bind the same semantic key and should use a concurrency group derived from it where the execution system supports that safely.
8. Terminal result/reconciliation updates semantic state; a new generation requires an explicit semantic or retry reason, not merely a new Trigger-7 invocation.

## Fail-closed alias law

The compiler accepts only admitted aliases mapped to canonical semantic values. Unknown families, targets, subjects or evidence scopes fail closed instead of silently minting a new key from arbitrary wording.

Adding a new semantic category is a versioned source change and should include a test.

## Current hardware-inventory gate

The canonical object for the current whole-Frankenstein `clay-direct-dev` hardware/resource inventory is:

```json
{"evidence_scope":"TARGET_RUNTIME_HARDWARE_RECEIPT","family":"TARGET_RUNTIME_HARDWARE_INVENTORY","generation":1,"schema":"T7_SEMANTIC_OBJECTIVE/v1","subject":"FRANKENSTEIN_2_0_RESOURCE_ENVELOPE","target_surface":"clay-direct-dev"}
```

Its v1 semantic key is:

```text
ba79dcf8960e1f02859a664103d5ba3f63fa8da95855d2b077b3e5aa2e0bf9e3
```

This stable key is locked by a regression test.

## Legacy duplicate reconciliation

Existing claims/workflows created before this protocol are historical evidence and are not deleted or rewritten. When several legacy paths map to one semantic key:

- record them as a duplicate set;
- create at most one semantic quarantine/winner record for future routing;
- do not mint extra runtime/replication credit merely because multiple queued/running jobs exist;
- preserve all terminal receipts and select causal/runtime credit by exact source, command, target identity and declared evidence scope;
- no new dispatch for the semantic key until the legacy set is reconciled or an explicit next generation is justified.

## Evidence boundary

Passing the semantic-key unit tests proves only deterministic coordination behavior of this source component. It does **not** prove GitHub create-only race behavior under live concurrent writers, does not cancel already queued workflows, and grants zero VPS/model/voice/Trigger-4 acceptance credit.

A stronger E3 coordination acceptance test requires two independent writers to attempt the same semantic key against the canonical repository and observe exactly one create-only winner before either schedules execution.
