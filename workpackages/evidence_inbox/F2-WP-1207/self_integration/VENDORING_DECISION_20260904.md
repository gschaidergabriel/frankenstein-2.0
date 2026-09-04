# P8 vendoring decision — the one confirmed instance (2026-09-04)

Origin: Claude Code coordinator session. Short audit round only, per
Gabriel's explicit instruction ("nicht refactoren, bevor klar ist, warum die
Byte-Kopie existiert... maximal eine kleine Audit-/Entscheidungsrunde, kein
neues Subprojekt"). No code changed by this doc.

## The instance

`frankenstein-repo/scripts/f2wp1207_grid10_p7_coordination.py` is a
byte-identical vendored copy of `frankenstein-2.0/src/frankenstein2/
grid10_p7_coordination.py` at commit `a9e5272` (sha256
`9e29f77598d59cbfc5faf266b59f7ee4fd9cc6d792cb2d84c21c13ed71fbb7ad`,
independently re-verified by the coordinator when the P7 live-bridge work
was reconciled — see `paket-1788515972573-d35ba2`).

## Why it's vendored instead of imported (audit finding)

`frankenstein-repo/scripts/stern.py` is invoked as a bare subprocess from
the LIVE hook (`~/.claude/star/stern.py`'s P7 bridge:
`subprocess.run([sys.executable, str(bruecke), "p7-bridge-turn"], ...)`,
timeout 4s, on every `Stop` event, for every session on this machine). A
subprocess entry point invoked this way has no reliable `sys.path` into a
SECOND, independently-versioned git repo (`frankenstein-2.0`) — that repo
could be on a different branch, mid-edit, temporarily broken, or simply not
present on a machine where only `frankenstein-repo` is deployed. Importing
across repos here would trade a small amount of duplication for a real
runtime dependency on another repository's working-tree state, at exactly
the point (`Stop`, every turn, fail-closed-critical) where the P7-bridge
work was built to be maximally isolated and reversible.

This matches Gabriel's own decision framework directly:
> "bleibt bewusst vendored, wenn Isolation/Fail-Closed/Version-Pinning
> wichtiger ist"

Both apply: isolation (no cross-repo import at a subprocess-invocation
boundary) and version-pinning (the vendored copy is frozen to the exact
commit that was tested and reconciled — `a9e5272` — not a moving target).

## Decision

**Keep vendored.** Not a bug, not accidental duplication — a deliberate
isolation boundary at a subprocess entry point, matching the same rationale
the P6d runner-reconstruction work already used for its own citation style
(avoid cross-repo live-import drift).

## What this is NOT a license for

This decision covers exactly this one instance. If a second module ever
gets vendored the same way, that's the point to revisit — repeated
vendoring of the same growing surface would tip the tradeoff back toward a
proper shared package. Not yet the case (P8 inventory found only this one
instance).

## Housekeeping note

If `grid10_p7_coordination.py` in `frankenstein-2.0` changes in the future
(e.g. bug fix, new formula term), the vendored copy in `frankenstein-repo`
will silently go stale — there is no automated re-sync. Whoever changes the
source should grep for `f2wp1207_grid10_p7_coordination.py` and re-vendor by
hand, or note in the source's commit message that the vendored copy needs
attention. Not automating this now (would be exactly the "neues Subprojekt"
Gabriel said to avoid) — just documenting the manual trip-wire.

Related: `STERN_DIFF_AUDIT_20260904.md` (the other P8 finding from today),
`f2wp1207-roadmap-p5-p13` (P8 definition).
