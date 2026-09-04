# P8 stern.py diff-audit — findings (no code changed)

Origin: Claude Code coordinator session, 2026-09-04. Two-step read-only
investigation, done by forks of the coordinator, both independently spot-
verified by the coordinator itself before this writeup. No paket_id minted
(pure documentation + a reusable analysis script, no building/consolidation
happened).

## Background

P8 ("v1/v2-Doppelstrukturen abbauen") started with the observation that
`~/.claude/star/stern.py` (the file actually registered as the live hook in
`~/.claude/star/settings.json` — fires on every UserPromptSubmit/PreToolUse/
Stop/etc. for every Claude Code session on this machine) and
`~/frankenstein-repo/scripts/stern.py` (the file carrying all F2WP1207/
GRID10/RuntimeEpoch research code) share an identical filename but were
initially assumed to be two disconnected codebases.

An inventory pass (step 1) corrected that: `frankenstein-repo/scripts/
stern.py` is a **fork** of `star/stern.py`, forked at commit `4f55d68`
(2026-08-26), then diverged independently — 436(ish)/438 function names
shared, meaning most of the 900KB+ file is duplicated logic, not just a
naming coincidence. That inventory flagged the real open risk as: *the
prior audit only checked names, not bodies — silent behavioral drift under
identical names was unverified.*

## Step 2: body-level diff audit (this document's actual finding)

Method: `tools/stern_shared_function_diff_audit.py` (this repo, next to
this doc) parses both files with Python's `ast` module, extracts the full
source segment of every top-level and nested function/method by name, and
compares bodies for all shared names — byte-identical / whitespace-comment-
only-diff / substantively different.

**Result, run 2026-09-04:**

```
functions in star/stern.py:                470
functions in frankenstein-repo/stern.py:    477
shared names:                               468
  byte-identical:                           467
  whitespace/comment-only diff:               0
  substantively different:                    1
only in star/stern.py:                        2  (_f2wp1207_p7_bruecke_aktiv, _f2wp1207_p7_bruecke_versuchen)
only in frankenstein-repo/stern.py:           9  (_f2wp1207_runtime_epoch, _f2wp1207_runtime_epoch_db_sync,
                                                    _f2wp1207_installation_id, _f2wp1207_canonical_entity_id,
                                                    _f2wp1207_active_host_binding_id, _f2wp1207_next_turn_event_id,
                                                    _f2wp1207_grid10_frame_persist, _f2wp1207_shadow_aktiv,
                                                    _f2wp1207_shadow_beobachtung)
```

**The one substantive diff is `cmd_hook` itself, and it is exactly the two
known, deliberate F2WP1207 insertion points — nothing else:**

- `star/stern.py`'s `cmd_hook` has the P7-bridge call
  (`_f2wp1207_p7_bruecke_versuchen(session_id)`, in the `Stop` branch,
  wrapped in `try/except`) added 2026-09-04 (paket
  `paket-1788515972573-d35ba2`).
- `frankenstein-repo/scripts/stern.py`'s `cmd_hook` has the pre-existing P0
  shadow-observation call (`_f2wp1207_shadow_beobachtung(session_id,
  prompt_text, treffer)`, in the `UserPromptSubmit` branch) from an earlier
  P0 round.

Full text of both variants was read directly (not just diffed) by the
coordinator to confirm this — every other line of `cmd_hook` in both files
is byte-identical, including all the unrelated PHASE-N comments, the
SessionStart/PreToolUse/PostToolUse/SessionEnd/PreCompact branches, and the
UserPromptSubmit branch outside the single added line.

**P7-bridge collision check:** clean. No name collision, no near-duplicate
(`p7`/`bruecke`/`bridge` substring) between the new bridge function names
and anything already in `frankenstein-repo/scripts/stern.py`.

**A false-positive worth noting for future runs:** `_zeile` and
`_einen_lauf` each appear twice by bare name in *both* files — these are
locally-scoped nested helper functions reused inside two different
enclosing functions, a pre-existing pattern present identically in both
files (just offset by line number because of the F2WP1207 additions). The
bare-name-based matching in the script flags these as "ambiguous" (>1
definition for the same name in one file) but they are not a cross-file
drift risk — the script only compares `[0]` (first occurrence) per name,
so a future run should sanity-check these two names by hand if the
enclosing-function offsets ever change.

## Verdict

**No silent drift found.** The "436 shared, unverified bodies" risk that
motivated this audit does not materialize — the shared surface (467/468
functions) is byte-identical, and the sole exception is the one function
both sides were *supposed* to touch, touched in exactly the documented way.

## Decision (Gabriel, 2026-09-04)

Given the above: **no consolidation needed right now.** Leave both files as
they are. This document plus the reusable script in
`tools/stern_shared_function_diff_audit.py` are the durable record — re-run
the script any time future drift is suspected (e.g. before wiring more
F2WP1207 phases into the live bridge, or periodically as a standing check).
P8's `stern.py` sub-item is closed on this basis; the remaining P8 items
from the original inventory (8 duplicate git clones instead of 3 canonical,
the single vendoring-by-copy instance) remain open, not addressed here.

Related: `f2wp1207-roadmap-p5-p13` (P8 definition), the P7 live-bridge work
this audit grew out of (paket `paket-1788515972573-d35ba2`).
