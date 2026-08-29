# Trigger 7 create-only research claims

This directory is the canonical duplicate-work mutex for bounded Trigger-7 evidence objectives.

Claim path convention:

`research/local_voice/claims/<research_id>/<objective>.json`

Examples:

- `T7-ASR-001/E2_SOURCE_AUDIT_QWEN3_ASR_06B.json`
- `T7-ASR-001/E3_VPS_GERMAN_ASR_BENCHMARK.json`
- `T7-TTS-001/E3_QWEN3_TTS_STREAMING_BENCHMARK.json`

Rules:

1. Refresh `frankenstein-2.0/main`, Trigger-4 outcomes, Trigger-5 voice deltas and current Trigger-7 frontier first.
2. Create the exact claim path atomically before material work on that bounded objective.
3. If creation fails because the path already exists, do not duplicate the objective. Read the owner/result and choose another non-duplicate objective.
4. Claim existence grants zero evidence, model, architecture, runtime, integration or acceptance credit.
5. Never overwrite/recycle a completed claim for a new experiment. Use a new objective ID.
6. Persist evidence/result separately under `benchmarks/`, `sources/`, `negative_results/` or `checkpoints/`.
7. The Research-Entity may mirror claims/provenance but is not a competing claim authority.
8. Trigger 4 owns F2 build acceptance; Trigger 7 cannot self-award V6.
