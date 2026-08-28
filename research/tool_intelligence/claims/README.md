# Trigger-6 atomic work claims

This directory is the create-only coordination surface for Trigger-6 research work.
It is a mutex/audit surface, not a truth store and not research evidence.
`research/tool_intelligence/pending_research.sqlite` remains the canonical Trigger-6 research database; UnifiedDB remains the canonical Frankenstein state authority.

## Why this exists

On 2026-08-29 multiple workers independently performed the same `R6-SEED-005` / `SOURCE_ARCHAEOLOGIST` / E2 AgentSight task against the same source and architecture snapshot. Their receipts were later reconciled as one E2 result, not independent replication. A pre-work atomic claim is therefore required to prevent duplicate evidence work.

## Claim key

Use one create-only file per research objective:

`research/tool_intelligence/claims/<research_id>/<claim_target>.json`

`claim_target` is normally the next evidence objective, for example:

- `E1_SOURCE_READ`
- `E2_ARCHITECTURE_MAPPED`
- `E3_CLAIM_REPRODUCED_<claim_id>`
- `E4_F2_ABLATION_<experiment_id>`
- `E5_BUILD_CANDIDATE`

A stale re-review caused by a later architecture delta uses a new explicit objective such as `E2_REVIEW_<architecture_delta_id>`; it must not overwrite the original claim.

## Atomic law

1. Refresh current F2 + Trigger-4 + Trigger-5 + Research-Entity state first.
2. Choose one bounded research objective.
3. Create the exact claim path with create-only semantics BEFORE material source archaeology, experiment execution, or integration distillation.
4. If creation succeeds, that worker owns only that bounded objective.
5. If the path already exists or create-only semantics cannot be established, DO NOT duplicate the work. Read the existing claim/result and select a different useful objective, or emit a coordination-blocked no-change result.
6. A claim grants zero evidence, architecture, runtime, integration, effect, or completion credit.
7. On completion, preserve the original claim and write a separate evidence/reconciliation receipt; synchronize the claim/result into `pending_research.sqlite` when the admitted database path is available.
8. Never use the Research-Entity mirror as a competing claim authority. It may mirror the F2 claim after creation, with source/target SHAs and mirror epoch.

## Minimum claim fields

- schema
- research_id
- claim_target
- slot
- status
- claimed_at
- worker/provenance
- F2 main SHA
- Research-Entity main SHA
- Trigger-6 seed/protocol identity
- architecture-delta/fusion identity
- intended evidence ceiling
- explicit `research_credit: 0`

The claim file is append-only in meaning. Do not recycle or silently rewrite a claimed objective.
