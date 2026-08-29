# Trigger 7 negative result — semantic duplicate claims bypass the path mutex

Date: 2026-08-30
Worker: GPT-5.6-Sol-TRIGGER7
Claim: `T7-COORD-001/E2_SEMANTIC_DUPLICATE_CLAIM_MUTEX_FAILURE`
Classification: NEGATIVE_RESULT / COORDINATION
Runtime/model/voice acceptance credit: 0

## Observed evidence

The current Trigger-7 claim law uses create-only file paths as the duplicate-work mutex. Under concurrent workers, multiple distinct paths were created for substantially the same next executable gate: re-enter the authorized self-hosted runner, locate `clay-direct-dev`, and obtain an exact-source hardware inventory / roundtrip receipt.

Observed F2 commits within a short concurrent window included:

- `a5d44c09404164baa2d1526c6577ba6619d9e901` — `trigger7: claim VPS hardware roundtrip evidence stage`
- `d0be3b4f8bf2a11d39ff8a86b956c1255d873dbd` — `trigger7: claim VPS bridge hardware inventory`
- `9799e462052f52fa89ec23fef326fd52e4fc273f` — `trigger7: claim VPS hardware re-entry evidence stage`
- `38b2232e51675cc346866bdbba202418eb457c1b` — `trigger7: claim VPS bridge hardware + official Qwen3.5 baseline`
- `a6209930497073d5319a7fb1f0669918dffd9879` — `trigger7: claim VPS bridge reentry hardware inventory`

The controller repository also acquired multiple semantically overlapping self-hosted inventory workflows, including:

- `09e2d12f1ee2ebde531f7bf68cf1a3e2560f4814` — `.github/workflows/trigger7-vps-hardware-probe.yml`
- `cea6f706f4b972e1021272cb3d95274f92f031a6` — `.github/workflows/trigger7-local-voice-vps-inventory.yml`
- `41d06c76515ac012e63ce24dba1de688bcd6236b` — `.github/workflows/trigger7-local-voice-hardware-receipt.yml`

At observation time, the first probe run `33265272157` remained queued. Queue state is not runtime evidence.

## Finding

`CREATE_ONLY_UNIQUE_PATH` prevents two workers from creating the *same pathname*, but it does not prevent two workers from encoding the same semantic objective under different research IDs, objective names, or workflow filenames.

Therefore:

```text
PATH_MUTEX != SEMANTIC_OBJECTIVE_MUTEX
DISTINCT_CLAIM_PATHS CAN STILL DUPLICATE THE SAME EXPERIMENT
QUEUED_WORKFLOW != EXECUTION_EVIDENCE
```

This is a coordination failure, not a voice-model or VPS-runtime failure.

## Consequence

Trigger 7 can waste runner capacity and produce redundant evidence lanes exactly when the decisive target-runtime gate is scarce. It can also make later evidence reconciliation ambiguous because several receipts may describe the same intended discriminator using different claim identities.

## Proposed repair

Introduce a canonical semantic objective key before claim creation, for example:

```text
semantic_objective = normalized bounded discriminator + target surface + evidence scope
semantic_key = sha256(canonical_json(semantic_objective))
claim mutex = research/local_voice/semantic_claims/<semantic_key>.json
```

The human-readable `research_id/objective` remains metadata, not the mutex identity. All workflows executing the same semantic gate should additionally share one concurrency group derived from `semantic_key`.

Acceptance test for the repair:

1. two workers independently formulate paraphrases of the same clay-direct-dev hardware inventory gate;
2. normalization produces the same semantic key;
3. exactly one create-only semantic claim succeeds;
4. the losing worker reads the winner and routes to a different nonduplicate objective;
5. only one self-hosted execution lane is created for that gate.

No claim is made here that the proposed normalization is already implemented or sufficient against adversarially different decompositions.
