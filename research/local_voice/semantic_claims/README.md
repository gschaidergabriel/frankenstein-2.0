# Trigger 7 semantic claims

This directory is the canonical **semantic-objective mutex** for new Trigger-7 material work.

Human-readable claims under `research/local_voice/claims/` remain provenance/UI metadata. They are no longer sufficient as the duplicate-work mutex because different names can encode the same experiment.

Protocol: `research/local_voice/SEMANTIC_CLAIM_MUTEX_V1.md`  
Compiler: `research/local_voice/tools/t7_semantic_claim.py`

Required order for new work:

1. compile the bounded semantic objective;
2. create `semantic_claims/<sha256>.json` atomically/create-only;
3. if it already exists, do not create another human claim or workflow for the same semantic objective;
4. only the winner may proceed to the human claim and execution lane;
5. preserve terminal evidence separately and do not infer runtime credit from claim existence.

Legacy duplicate sets may be represented here only as explicit `LEGACY_*` reconciliation/quarantine records. Such a record prevents new duplicate dispatch but does not retroactively make an old claim or queued run successful.
