# Trigger 7 human-readable research claims

This directory preserves the human-readable claim/provenance layer for bounded Trigger-7 evidence objectives.

**It is no longer sufficient as the duplicate-work mutex.** Concurrent workers proved that distinct `<research_id>/<objective>` paths can encode the same semantic experiment. The preserved negative result is:

`research/local_voice/negative_results/2026-08-30_T7_SEMANTIC_DUPLICATE_CLAIM_MUTEX_FAILURE.md`

The canonical duplicate-work mutex for **new material Trigger-7 work** is now:

`research/local_voice/semantic_claims/<semantic_key>.json`

Protocol and compiler:

- `research/local_voice/SEMANTIC_CLAIM_MUTEX_V1.md`
- `research/local_voice/tools/t7_semantic_claim.py`

Human claim path convention remains:

`research/local_voice/claims/<research_id>/<objective>.json`

Examples:

- `T7-ASR-001/E2_SOURCE_AUDIT_QWEN3_ASR_06B.json`
- `T7-ASR-001/E3_VPS_GERMAN_ASR_BENCHMARK.json`
- `T7-TTS-001/E3_QWEN3_TTS_STREAMING_BENCHMARK.json`

Rules:

1. Refresh `frankenstein-2.0/main`, Trigger-4 outcomes, Trigger-5 voice deltas and current Trigger-7 frontier first.
2. Define the smallest bounded semantic objective and compile its canonical key with `t7_semantic_claim.py`.
3. Atomically/create-only create the exact semantic path under `research/local_voice/semantic_claims/` **before** creating a new human claim or execution workflow.
4. If the semantic path already exists, do not create a differently named human claim or workflow for the same objective. Read the existing semantic state and route to a nonduplicate objective, or justify an explicit next generation after terminal evidence.
5. Only the semantic-claim winner may create the corresponding human-readable claim and execution lane.
6. Human claim existence grants zero evidence, model, architecture, runtime, integration or acceptance credit.
7. Never overwrite/recycle a completed claim for a new experiment. Preserve history and use an explicit new semantic generation only when justified.
8. Persist evidence/results separately under `benchmarks/`, `sources/`, `negative_results/` or `checkpoints/`.
9. The Research-Entity may mirror claims/provenance but is not a competing claim authority.
10. Trigger 4 owns F2 build acceptance; Trigger 7 cannot self-award V6.

Legacy claims created before the semantic mutex remain historical evidence and are not deleted. Known semantic duplicate sets should be reconciled/quarantined under `semantic_claims/` so they cannot create additional dispatch fan-out.
