# Trigger-6 → Trigger-4 Build Candidate Handoff

A Trigger-6 research result becomes actionable for VPS builders only as a versioned `BUILD_CANDIDATE` packet.

## Required packet path

`trigger4/inbox/tool_research/<candidate_id>.json`

## Required fields

```text
candidate_id
hypothesis_id
architecture_snapshot_id
research_entity_source_sha
frankenstein_2_source_sha
external_repo
external_repo_commit_sha
external_repo_tree_sha
license
integration_class = DIRECT_ADOPT | ADAPT_TO_GRID | CONCEPT_DISTILL | REIMPLEMENT
f2_target_workpackages[]
f2_target_modules[]
problem_or_gap
proposed_delta
counterhypotheses[]
evidence_refs[]
upstream_claims_reproduced[]
upstream_claims_not_reproduced[]
baseline_definition
required_tests[]
required_ablations[]
required_measurements[]
expected_token_delta
expected_latency_delta
expected_resource_delta
quality_success_metric
rollback_or_reject_rule
known_failure_modes[]
source_archive_ref
research_db_row_ids[]
```

## Trigger-4 consumption law

Trigger-4 must refresh F2 HEAD and reject/hold any packet whose `architecture_snapshot_id` is stale for affected modules. A 4er may adapt implementation detail, but it must preserve the research hypothesis, counterhypothesis, baseline and falsification tests so the build result is comparable to the research claim.

The VPS worker must produce:

`trigger4/outcomes/tool_research/<candidate_id>.json`

with exact build commit, run IDs, test receipts, measured token/latency/resource/quality deltas, negative results and root causes.

## Feedback loop

```text
Trigger6 research
 -> BUILD_CANDIDATE
 -> Trigger4 VPS build
 -> tests + measurements
 -> outcome packet
 -> Trigger6 evidence update
 -> hypothesis promote/downgrade/reject
 -> RCPD MethodEpisode
```

An upstream project may be excellent and still be rejected for F2 if marginal value is negative after integration cost. Conversely, a rejected wholesale dependency may still yield a useful structural distillation.
