# V1 <-> V2 Fusion Map — LOCAL ITERATION 0 + 1 (read-only)

RUN_ID: `LOCAL-ITER0-20260902T163811Z`
Timestamp: 2026-09-02T16:38:11Z
Branch (local only, not pushed): `self-integration/wp1207-local-iter0-20260902T163811Z`
Scope: read-only discovery of the real v1 call chain + fingerprint, plus one read-only
StateRootIdentity discriminator against the real `unified.db` path. **Zero writes** to
`unified.db`, zero writes to v1 or v2 canonical state, zero process start/stop/restart.

## Role model (as given, checked plausible against the evidence found here)

- Claude Code host = organ/coordinator, not the artifact under replacement.
- Frankenstein v1.0 = the architecture already running AROUND the Claude Code host:
  `~/.claude/star/stern.py` + `~/.claude/star/unified.db` + Claude Code hooks. Repo
  `gschaidergabriel/frankenstein` confirmed byte-identical at `scripts/stern.py`.
- Frankenstein 2.0 (`~/frankenstein-2.0`) = evidence-based successor, not wired in,
  source of validated mechanisms for one-boundary-at-a-time integration into v1.
- Goal: v1 stays live donor/fallback; v2 mechanisms adopted only after a passed
  discriminator; never two parallel canonical truths (e.g. two UnifiedDBs).

Nothing found in this scan contradicts that framing.

## V1 baseline fingerprint

| Item | Value |
|---|---|
| `stern.py` SHA-256 (live) | `f96a597f88c14f54e8bd6071c471958ae153782536ea750b71bb89dce6c7a7d8` |
| `stern.py` size | 908270 bytes |
| Matching v1 repo | `gschaidergabriel/frankenstein`, local clone `~/frankenstein-repo` |
| Repo file | `scripts/stern.py`, content SHA-256 identical to live file |
| Last commit touching file | `7681c62` ("v1.0: Retrieval-Reparatur ...") |
| Repo HEAD at scan time | `61f9efb1a5751ba130f74e36df796cc019e9b439` (content unchanged since `7681c62`) |
| Repo caveat | local clone was mid-rebase (`(no branch, rebasing main)`) at scan time — pre-existing, not caused/touched by this run, out of scope to fix |
| `unified.db` realpath | `/home/ai-core-node/.claude/star/unified.db` |
| Device / Inode | `259,2` / `656188` |
| Size | 63401984 bytes |
| Birth | 2026-08-25T16:51:51+07:00 |
| SHA-256 (before Iteration 1) | `aeaf5304f70242bf385c7dd9af21c7c96b94735810daad172e7b7ce465c35308` |
| Table count | 200 (names only recorded, see JSON — no row data read) |

## Real v1 hook chain (not just "look for a daemon")

- `~/.claude/star/settings.json` registers **one** command,
  `python3 /home/ai-core-node/.claude/star/stern.py hook`, on **seven** Claude Code
  lifecycle events: `UserPromptSubmit`, `SessionStart`, `PreToolUse`, `PreCompact`,
  `PostToolUse`, `Stop`, `SessionEnd`.
- `stern.py`'s `cmd_hook()` (stern.py:8874) reads one JSON payload from stdin and
  branches internally on `hook_event_name` (stern.py:8888). So there is exactly
  **one** v1 entrypoint subcommand fed by 7 distinct events — not 7 separate code
  paths, not a background daemon.
- `~/.claude/settings.json` (global, outside `star/`) additionally wires:
  `PostToolUse` -> heartbeat.sh + `clay-room-heartbeat` + `stern.py raum-puls-global`
  (a *separate*, explicit subcommand, not the generic `hook` dispatcher).
  `UserPromptSubmit` -> `clay-chatgpt-usage-hook`.
- `UDB_DB_PATH` (pointing at `unified.db`) is set only in `~/.claude/star/settings.json`,
  not in the global settings file.

## Prior same-day F2 discovery reused, not repeated

Commit `f99a8a1` (run `WP1207-DISCOVERY-20260902T162531Z`, already on this branch's
history) already established, read-only: F2 has **no local always-on daemon**, is
repo+CI driven, and its narrowest internal release/update seam candidate is
`portable_release_transaction.py` + `current_release_bundle_adapter.py`. That finding
is carried forward unchanged; this run does not re-derive it.

## Candidate v1 <-> v2 seam map (hypotheses only, nothing wired)

1. **stern.py hook dispatcher <-> `state_migration.py` (`StateRootIdentity` /
   `StateLineage` / `StateMigrationRequest` / `StateMigrationPlan`, F2-WP-1105).**
   v2's module is plan-only: it can *describe* `unified.db` as a
   `StateRootIdentity(storage_class=CANONICAL_DURABLE)` and reason about
   lineage/generation, but it does not itself read/write `unified.db` and has no
   dispatcher of its own. It is a validation/planning primitive, not a runtime
   replacement for stern.py.
2. **unified.db (single canonical SQLite file) <-> v2's `ONE_CANONICAL_STATE_LINEAGE`
   / `DISPOSABLE_CACHE != CANONICAL_STATE_ROOT` law.** This is exactly the invariant
   the coordinator already enforces by hand for `unified.db` (no second DB, no schema
   change without explicit authorization) — v2 formalizes it as machine-checkable
   dataclass validation.
3. **F2-WP-1207 `portable_release_transaction.py`** — v2's own internal release seam,
   not yet evaluated as a mechanism for migrating v1 state. Carried forward from prior
   discovery, not re-examined here.

None of these are wired. All three are candidate hypotheses for a *future*, separately
authorized iteration.

## Iteration 1 — StateRootIdentity discriminator (see receipt for full detail)

**Result: PASS** (with scope caveat — see receipt). `StateRootIdentity.create()` +
`assert_eligible_canonical_root()` accepted the exact real path
`/home/ai-core-node/.claude/star/unified.db`, tagged `CANONICAL_DURABLE`, as an
eligible canonical root — purely in-memory, zero filesystem/DB I/O inside the module
(confirmed by reading `state_migration.py` line by line: no `open()`, no `os.*` calls).
DB fingerprint (size + mtime + SHA-256) identical before and after. See
`iteration1_discriminator_receipt.json` for exact evidence and the important caveat
that this is caller-supplied-claim validation, not autonomous path discovery.

## What was NOT done (by design, per operator instruction)

- No seam wiring, no dry-run, no disposable-sandbox test, no hostile-twin, no rollback
  test, no process kill/restart.
- No mutation/migration/schema-change/second-DB proposal executed against `unified.db`.
- No CausalIdentity / Runtime-State / Reentry / GWT / J-Space / Effects /
  Perception-Voice / Handoff iterations — explicitly deferred to the coordinator.
- Nothing pushed; `main` untouched in both `~/frankenstein-2.0` and `~/frankenstein-repo`.
