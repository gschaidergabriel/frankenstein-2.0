# F2-WP-1207 — first SHADOW pipeline run against real turn data

Paket: `paket-1788426634287-6f53f2` (2026-09-03). Gabriel's framing: every
prior F2-WP-1207 round ran v2 components ALONGSIDE v1 (isolated compat
checks, sandbox tests, synthetic-scenario harnesses). This is the first
round to show v2 building blocks sitting INSIDE the shape of a real v1 turn
— as observers, not actors — driven by real, already-completed turn data.

## What this proves

The pipeline `UserPromptSubmit → TypedEntry → StateRootIdentity → GRID10
frame (SHADOW) → [v1-processing placeholder] → Output → persisted minimal
reentry evidence` runs end-to-end, consistently, against 8 real,
already-completed turn-cycle markers pulled read-only from the real
`unified.db` (see `REAL_TURN_EXTRACTION_NOTES.md` for the exact extraction
query and an explicit honesty caveat about what these markers are/aren't).
Every stage uses real, unmodified code from this repo's own
`self-integration/wp1207-entity-identity-layering-v2-20260903` branch
(`frankenstein2.entity_identity.StateRootIdentity` — the one WITH
`installation_id` — and `frankenstein2.grid10_interface`, unmodified,
F2-WP-503).

## What this does NOT prove

- **Not a live activation.** Nothing here is wired into
  `~/frankenstein-repo/scripts/stern.py`'s actual hook chain. This is a
  demonstrated prototype run against historical data in a fresh clone, one
  Python process, invoked by hand.
- **Step 5 ("bestehende v1-Verarbeitung") is an explicit, labeled
  placeholder**, not real v1 logic — see
  `v1_processing_placeholder()`/`V1_PLACEHOLDER_SCHEMA` in
  `pipeline_demo.py`. It documents exactly which real v1 code path
  (`stern.py`'s existing SHADOW-mode retrieval, the same one that produced
  the real `retrieval_episodes` rows this run reads) would sit there on
  real activation, without calling it.
- **No v1 concept is assigned to any GRID10 cell.** `G1`..`G10` remain
  functionally neutral (same discipline as the prior
  `grid10_observation_schema.py` round) — this run only replaces that
  round's *index-formulaic synthetic* drive pattern with a *real-turn-
  derived* one; it does not decide what any cell "is".
- **`StateRootIdentity.installation_id`/`EntityIdentity` here are
  demo-minted**, not the project's canonical identity. Minting the real one
  remains a separate owner decision (`INTEGRATION_HYPOTHESES.md` Part 5).

## Results (`shadow_pipeline_report.json`)

- 8/8 real turns processed, all from the current live session
  (`a2f7b438-df52-4465-8786-b49905bbacaf`).
- **8/8 distinct `record_sha256`, 8/8 distinct GRID10 `plan_sha256`, 8/8
  distinct `typed_entry.sha256`** — not a uniform/fake output; every turn's
  real characteristics (marker kind, `chars_selected`, `entry_key_count`,
  `ts_unix`) genuinely drive different GRID10 work-unit/reentry-depth
  numbers per cell.
- GRID10: 10/10 logical cells (`G1..G10`) completed in every one of the 8
  runs (`missing_cell_ids: []` every time) — the real ABI's ten-cell
  accounting invariant holds under real-data drive, not just synthetic.
- Total work-units-used per turn ranges 27–41 across the 8 runs (real
  spread, not constant).
- 4/8 turns (the `t-mc-*` ones) carried a real linked `retrieval_episodes`
  row → GRID10 cell `status` observed as `COMPLETE`; the other 4 (`t-close-
  *`) had none → `status` observed as `NOT_COMPUTED`. This status split is
  itself real-data-derived, not scripted per-turn.
- Semantic-neutrality guard (`_assert_no_semantic_leakage`, reused verbatim
  from `grid10_observation_schema.py`'s denylist) ran against every GRID10
  frame and typed entry and passed with zero trips in the final run (two
  earlier drafts of this script DID trip it — see git history of this file
  for the honest record: the guard is written for GRID10-cell-naming
  leakage specifically, and two non-GRID10 records legitimately using the
  word "identity" needed the guard scoped away from them, not weakened).

## Verification run in this evidence dir

```
$ PYTHONPATH=../../../../../src python3 -m pytest \
    ../../../../../tests/test_entity_identity.py \
    ../../../../../tests/test_grid10_interface.py -q
42 passed in 0.09s
```

(29 `test_entity_identity.py` + 13 `test_grid10_interface.py`, both
untouched by this round — proves this round did not regress the modules it
reused.)

## No-effects attestation

- `unified.db` (real): read-only connection (`mode=ro`) + one whole-file
  SHA-256 read for the fingerprint. Zero `INSERT`/`UPDATE`/`DELETE`.
- `~/frankenstein-repo`: `scripts/hook.log` read via `grep`/`tail`/`wc`
  only. No file under `~/frankenstein-repo` was opened for writing, created,
  or deleted at any point in this round — see the coordinator's final
  `git status`/mtime comparison in the round's chat summary for the
  before/after proof.
- No hook registered, no `hooks.json` touched, no `stern.py` in the live
  checkout touched.
- All code/output for this round lives in a **fresh** clone of
  `gschaidergabriel/frankenstein-2.0` (`/tmp/frankenstein2-fresh` on the
  coordinator's machine), on branch
  `self-integration/wp1207-entity-identity-layering-v2-20260903`, pushed —
  never `main`, never `~/frankenstein-repo`.

## Files in this directory

- `pipeline_demo.py` — the pipeline itself (see its module docstring for
  full detail on every stage).
- `REAL_TURN_EXTRACTION_NOTES.md` — exact extraction query + honesty caveat.
- `real_turns_raw.json` — the 8 raw real rows the pipeline was driven by.
- `db_pfad_zeigen_output.json` — real, read-only `python3
  ~/.claude/star/stern.py db-pfad-zeigen` output (resolved `DB_PATH`).
- `unified_db_fingerprint_sha256.txt` — real, read-only whole-file SHA-256
  of `unified.db` at round start.
- `shadow_pipeline_report.json` — the full output: state-root-identity
  record + all 8 per-turn pipeline records + the distinctness check.
