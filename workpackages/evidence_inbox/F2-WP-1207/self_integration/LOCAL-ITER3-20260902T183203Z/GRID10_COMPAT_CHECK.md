# F2-WP-1207 LOCAL ITERATION 3 -- GRID10-Interface read-only compatibility check

Candidate picked up from `self-integration` README's queued next step after
LOCAL ITERATION 2 (`c3cf56b`): "GRID10-Interface read-only pruefen".

## What GRID10 actually is

`src/frankenstein2/grid10_interface.py` (from F2-WP-503) is **not** a live
cognitive/compute component. It is a pure, stdlib-only data/validation module:
a deterministic ABI for exactly ten opaque "logical cell" budget slots
(`G1`..`G10`) bound to one `SituationFrame`/policy identity, with bounded
input/output/work-unit budgets and sha256-based canonical accounting
(`Grid10Plan`, `CellBudget`, `CellInput`, `CellOutput`, `account_outputs`).
Its own docstring is explicit about what it deliberately does *not* do: "does
not assign cognitive semantics to cells, call models/tools/providers, mutate
state, authorize effects/completion, or imply any physical model/decode
concurrency." No model calls, no process spawning, no live-instance contact
anywhere in the module.

Note: v1's `stern.py` also contains the literal string `grid10` twice, but
both are unrelated -- leftover sandbox-guard boilerplate text that once
polluted FTS retrieval results (see `_KONFIG_DEFAULTS["abruf.gesperrte_paket_teilstrings"]`
and the `paket-1788112504899` comment in `stern.py`). v1 has **no** existing
concept of "logical cells" or a GRID10 ABI -- this is a v2-only construct.
Confirmed by grep across `~/.claude/star/stern.py`; no coincidental overlap.

## What this iteration checked (read-only, no wiring)

`grid10_compat_check.py` in this directory:

1. **Static import scan** (AST-based) of `grid10_interface.py`: confirms its
   only top-level imports are `__future__, dataclasses, hashlib, json, re,
   typing` -- all Python 3.12 stdlib. Zero third-party dependencies.
2. **Dynamic functional exercise**: imports the unmodified v2 module directly,
   builds a synthetic `Grid10Plan` (ten cells, one dummy frame/policy
   binding), runs `CellInput.for_plan` / `CellOutput.for_input` for all ten
   cells, then `account_outputs` to get a `Grid10UsageReceipt`. All ten cells
   complete, budgets validate, canonical sha256 digests compute successfully.
   No v1 file or DB row is read as part of this exercise -- purely synthetic
   data.
3. **v1 DB fingerprint before/after**: resolved v1's real `unified.db` path
   via v1's own `stern.py db-pfad-zeigen` (same discovery pattern as
   LOCAL-ITER2), took an independent streaming sha256 before and after the
   exercise. Identical (size/mtime/sha256) -- proves this check, despite
   having no reason to go near v1 state, in fact touched none.

**Result: PASS.** See `report.json` for the full machine-readable output.

## Conclusion / what this does and does not establish

GRID10 is a portable, dependency-free ABI. If a coordinator later decides to
wire GRID10 into v1 (e.g. to give a future v1 subsystem a bounded, ten-slot
work-budget contract), the import itself carries no new dependency and no
environment risk -- confirmed empirically, not assumed.

This iteration does **not**:
- wire GRID10 into `stern.py` or any v1 code path,
- propose what v1 concept (if any) should map onto the ten logical cells,
- touch `main` in either repo,
- claim GRID10 is *useful* for v1 today -- only that it is *safe and cheap to
  import* if a future decision calls for it.

Whether GRID10 is actually worth wiring into v1 is an open design question,
not something this read-only check answers or should answer.

## Next candidate

No further "read-only interface prove-out" candidates of this shape were
identified as queued in this iteration. Next cron cycle should re-check
`self-integration` README + `INTEGRATION_HYPOTHESES.md`-equivalent notes (the
exact filename named in the task brief does not exist in this repo under that
name; the closest analog is the running list of local-iteration conclusions
inside `self-integration/README.md` itself) for the next small, non-invasive,
non-live-process candidate.
