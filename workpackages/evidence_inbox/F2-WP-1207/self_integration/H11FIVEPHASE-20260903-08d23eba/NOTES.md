# H11FIVEPHASE-20260903-08d23eba — H11 five-phase decomposition, sandbox-only

F2-WP-1207 self-integration. Answers exactly the safe next step
`INTEGRATION_HYPOTHESES.md` names for H11 ("a continuous 5-phase timing run
entirely inside the existing disposable `self_update_transaction.py` sandbox,
no live process contact at all"). Nothing else.

## Why this run exists

Every prior run measured at most 2 of H11's 5 named phases as real numbers,
and even those 2 were not independent: `apply_transaction`'s injected
`post_mutation` path times `failure_detection_ms` from the same start clock
all the way through the rollback restore, the post-restore digest verify, and
the receipt mint — so it structurally *contains* `rollback_duration_ms`
rather than sitting beside it as a sibling phase. No run ever isolated
"mismatch noticed" from "bytes restored" from "fresh process saw healthy
state" from "that fresh readback itself completed" as 4 non-overlapping
intervals inside one continuous sequence.

## What this run does differently

`logs/run_five_phase.py`:
1. INSTALL (gen 1) + UPDATE (gen 2, "healthy") via the unmodified accepted
   `apply_transaction` — setup, not timed as a phase.
2. Writes a structurally-valid-but-doomed UPDATE payload to disk, then
   corrupts one file directly (outside the payload dict) so the on-disk
   bytes genuinely disagree with the expected manifest digest — the same
   real verify-mismatch condition `self_update_transaction.py`'s own
   non-injected-flag branch checks for, not the synthetic
   `injected_failure_stage` flag (whose "detection" would be a near-zero
   branch check, not real comparison work).
3. **Phase 1 (detection):** `compute_state_digest()` + compare, timed alone.
4. **Phase 2/3 (rollback begin → rollback end):** `store._restore_snapshot()`
   — the exact private method the accepted module itself calls — timed
   alone, nothing else inside the window.
5. Receipt mint (`record_attempt`, accepted primitive) timed but reported
   *outside* phases 1-2, disclosed separately (`receipt_mint_ms`), so it
   cannot silently inflate either the old way did.
6. **Phase 4 (process re-entry):** wall time from `subprocess.Popen(...)`
   for a genuinely fresh `python3` process to that child's first flushed
   stdout line — real OS spawn/exec/interpreter-startup cost.
7. **Phase 5 (healthy readback):** timed *inside* the child, strictly around
   `independent_readback()` (the same function P7 used), invoked from a
   genuinely separate process.

## Result (real numbers, single continuous run, exit 0)

| Phase | ms |
|---|---|
| 1. detection | 0.3491 |
| 2-3. rollback begin → rollback end | 1.1645 |
| 4. process re-entry | 10.166 |
| 5. healthy readback | 0.5675 |
| (disclosed, not one of the 5) receipt mint | 0.0557 |
| (disclosed, not one of the 5) mutation/setup | 0.573 |

All correctness checks passed: restored bytes match the pre-corruption
healthy state exactly; lineage never advanced off the healthy generation
(matches the accepted module's own ROLLED_BACK semantics); the fresh child
process's independent readback confirms the same healthy generation and
state digest. See `measurements.jsonl` for the full record including the raw
monotonic timeline.

## What this run does NOT claim

- Does not touch, signal, or spawn anything related to the real v1 harness
  or a real Claude Code CLI process. Only subprocess spawned is this
  script's own throwaway `python3 -c "..."` reader.
- Does not close the live-v1-harness variant of H11
  (`INTEGRATION_HYPOTHESES.md` Part 3, "H6 (further) / H11 (closing) on the
  real, current v1 harness specifically") — that stays explicitly deferred,
  separately-scoped, needing its own owner sign-off.
- Does not touch H1-H10, H12-H14 (unchanged).
- Does not promote the pointer away from G10.
- `PROPOSAL_ONLY_ZERO_ACCEPTANCE_CREDIT` per `canonicalization_proposal.json`
  — candidate evidence for independent review, not self-certified acceptance.

## Reproduce

```
python3 workpackages/evidence_inbox/F2-WP-1207/self_integration/H11FIVEPHASE-20260903-08d23eba/logs/run_five_phase.py
```
