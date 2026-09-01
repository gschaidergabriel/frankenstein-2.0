# F2-WP-1207 Self-Integration Final Report

- **RUN_ID:** `SELFINT-20260901-a1c9e2f4`
- **Branch:** `self-integration/wp1207-SELFINT-20260901-a1c9e2f4` (no push to main)
- **Base commit (repo HEAD before this run's commit):** `2f7437b12423688533e35301e947ac0e282e6362`
- **Status:** `CANDIDATE_SELF_INTEGRATION_NON_CANONICAL` -- evidence only, zero self-certification, zero acceptance credit claimed.

## What was built

`src/frankenstein2/self_update_transaction.py` wraps (imports/calls only, never
forks or edits) the ACCEPTED G10 canonical primitives in
`portable_release_transaction.py` (`build_transaction_plan`, `record_attempt`,
`ReleaseIdentity`, `StateLineage`) to add real filesystem
install/update/rollback/independent-readback plumbing over a managed directory.
`tests/test_self_update_transaction.py` (11/11 passing) covers install+update,
injected pre/post-mutation failure with exact-digest rollback, in-process
readback correctness, hostile-twin rejection, replay rejection, CAS/stale-state
rejection, and a control/managed-dir nesting guard.

The canonical baseline (`tests/test_portable_release_transaction.py`) remains
**12/12 passing, exit 0** -- confirming `portable_release_transaction.py` itself
was never modified.

## Sandbox

All gates ran against a disposable, curated, bounded, faithful representative
subset of `~/.claude` (54 files, 62M) copied to `/tmp/selfint-SELFINT-20260901-a1c9e2f4/`.
The real `~/.claude/` was never mutated (verified: settings.json mtime/permissions
unchanged after the copy; `star/unified.db` sha256 confirmed byte-identical
between source and copy). This is **not** a full byte-identical mirror -- large
reproducible/derived/archival material (venv, snapshots, historical db backups,
skill packs, conversation history: roughly 4.9G of the real 5G tree) was excluded
as irrelevant to the release/update transaction boundary. Full exclusion list and
rationale: `integration_map.json#fidelity_limitation`.

## Gates executed (P5-P11)

All 7 gates behaved exactly as required; see `logs/gate_summary.json` and
`measurements.jsonl` for full detail.

| Gate | What it proves | Result |
|---|---|---|
| P5 | INSTALL then UPDATE succeed, generation advances | SUCCEEDED / SUCCEEDED |
| P6 | Injected post-mutation failure -> exact rollback | ROLLED_BACK, predecessor/observed/fresh digest all identical |
| P7 | Independent readback from a genuinely fresh subprocess | `lineage_matches_observed=true` |
| P8 | Hostile-twin declared release rejected before mutation | RAISED pre-mutation, state unchanged |
| P9 | Replay/idempotency (same target as active) | RAISED, no double-apply |
| P10 | Concurrent/stale-state CAS | caller B SUCCEEDED, caller A RAISED fail-closed, no split-brain |
| P11 | Real (non-fabricated) CPU/wall/RSS/disk measurements | recorded in `measurements.jsonl`, sub-second, `rollback_duration_ms=25.69`, `failure_detection_ms=62.00` |

## Rollback evidence (P6)

Predecessor state digest, observed post-recovery digest, and a fresh
on-disk recompute all equal
`68513b5bcff37c9d120033d8084e7855fafd98c69590df25011f8a917c840a61`.
Full detail, including the honest gap (cross-process re-entry proven for the
success path via P7, not yet proven for the explicit-rollback path in this
run): `rollback_evidence.json`.

## Hypotheses (H1-H13)

**PASS: 10** (H1, H2, H3, H4, H5, H6, H8, H9, H10, H12)
**INCONCLUSIVE: 3** (H7, H11, H13)
**FAIL: 0**

Full per-hypothesis evidence and reasoning: `hypothesis_results.json`.

- H7 is INCONCLUSIVE because it requires comparing against the real, live
  Frankenstein runtime, which is Phase 13 and explicitly out of scope here.
- H11 is INCONCLUSIVE because only 2 of the 5 named latency phases
  (`failure_detection_ms`, `rollback_duration_ms`) have real measured numbers
  in a single continuous run; a full 5-phase chained timing was not produced.
- H13 is INCONCLUSIVE because it is a canonicalization/governance decision
  about G9/G10 credit inheritance, not something these gates can adjudicate.

## Blockers

3 non-terminal blockers recorded in `blockers.json` (the H4/H11 cross-process
rollback-readback gap, the H7 live-baseline gap, the H13 governance gap). Zero
`PRODUCT_NEGATIVE` gate failures; zero `EVIDENCE_INVALID` findings.

## Security / redaction

Secret scan (see exact command in `security_audit.json#secret_scan_detail`) run
against the full evidence directory including `patch.diff`: **no matches** of
the two sensitive settings.json keys. Detail: `security_audit.json`.

## Safety constraints observed

- Real `~/.claude/` never touched/moved/deleted.
- `portable_release_transaction.py` never modified (confirmed via `git status`
  and the passing baseline suite).
- No push to `main`; all work stays on
  `self-integration/wp1207-SELFINT-20260901-a1c9e2f4`.
- No canonical `workpackages/` path written; all new evidence lives under
  `workpackages/evidence_inbox/F2-WP-1207/self_integration/SELFINT-20260901-a1c9e2f4/`.
- No self-certification: `canonicalization_proposal.json` is marked
  `PROPOSAL_ONLY_ZERO_ACCEPTANCE_CREDIT` with `requested_independent_review: true`.
- Cognition/GWT/J-Space/model semantics untouched (excluded from the sandbox
  by construction).
- No host reboot, no state deletion, Phase 13 not attempted.

## What Phase 13 (or a follow-up run) would need

1. Close the H4/H11 gap: one continuously-timed gate chaining injected
   failure -> rollback -> fresh-subprocess readback, all 5 phases timed.
2. A live-runtime behavioral baseline to resolve H7 (must go through its own
   independent-review/authorization path -- explicitly not attempted here).
3. Independent review of `canonicalization_proposal.json` and a governance
   decision on H13 (G9/G10 credit inheritance) before any canonical
   `workpackages/` write is considered.
4. If H4/H11/H7 close out clean, a scoped, explicitly-authorized live
   integration trial against the real `~/.claude` -- never attempted or implied
   by this run.

## Proof line

`test:0:PYTHONPATH=src python3 -m pytest tests/test_portable_release_transaction.py tests/test_self_update_transaction.py -q -- 23 passed, exit 0`
