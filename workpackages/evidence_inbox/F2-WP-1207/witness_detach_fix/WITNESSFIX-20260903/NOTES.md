# WITNESSFIX-20260903 — witness_v2.py auto-relaunch-tool detach fix

## What was broken

`witness_v2.py` (`workpackages/evidence_inbox/F2-WP-1207/post_reentry_validation/
POSTREENTRY-20260901/witness_v2.py`) is the "external witness/auto-relaunch tool"
referenced in `INTEGRATION_HYPOTHESES.md` Part 4, blocker `POSTREENTRY B`: during
the `POSTREENTRY-20260901` run it was supposed to SIGTERM the live subject
(claude PID 4179659), confirm death, and relaunch it via `--resume` in a fresh
terminal. It never got that far. `blockers.json` for that run:

> "Zeuge starb mit dem Subjekt (Detach nicht belastbar) — Auto-Relaunch kam nie
> zustande; Owner vollendete Reentry manuell (ohne
> `--dangerously-skip-permissions`)."

Confirmed directly from that run's own evidence: `reentry2_evidence.json` (the
witness's own evidence file for that attempt) stops right after the very first
`flush()` call — `pids_before` recorded, nothing else. No `died`, no `status`, no
`new_pid`. The witness process itself was cut off before it could even confirm
the target had died, let alone relaunch it.

## Root cause

Reading `witness_v2.py`: it calls `subprocess.Popen(["gnome-terminal", ...],
start_new_session=True, ...)` -- but that `start_new_session=True` only detaches
the process it *spawns for the relaunch*, i.e. after the target is already dead.
Nothing in the script detaches **the witness itself** from whatever session/
process-group launched it in the first place. If that launching session/group is
torn down together with the target -- terminal SIGHUP to the foreground process
group, shell job-control cleanup, or any other ordinary OS/harness mechanism that
tears down "everything belonging to this job" when its lead process dies -- an
un-detached witness goes down with it before it can do anything. The blocker's own
`next_discriminator` names the fix directly: "Neustart-Werkzeug AUSSERHALB der
Prozessgruppe des Subjekts erzeugen (echtes setsid + nohup + Auskoppeln VOR dem
Kill), und an Attrappe belasten, bevor es je wieder am echten Prozess läuft."

## Fix

`witness_v3.py` in this directory. Same core job as v2 (wait for target death,
relaunch), generalized (target pid / relaunch command / evidence path are CLI
args, not hardcoded) and, critically, adds a `daemonize()` step -- classic UNIX
double-fork (`fork` → parent exits → `setsid()` → `fork` again → parent exits →
`chdir("/")` + stdio redirected to `/dev/null`) run as the **first** thing in
`main()`, before any target/kill/relaunch logic. With `--daemonize` set, the
witness fully detaches into its own session before touching the target, exactly
as prescribed.

## Test (isolated, dummy-only — no live subject touched)

Per the task's safety instruction: this touches the exact vocabulary (process
termination/reentry against a subject, auto-relaunch) that overlaps the
combination that triggered Anthropic's cyber-safety filter on 2026-09-02
(hostile-twin + injected faults against a *live* process + reentry + transaction
layer around an *active agent*). This fix was therefore tested **only** against a
disposable dummy subject (`dummy_subject.py`, a trivial heartbeat loop — not
claude, not any real agent, no contact with the actually-running v1 harness or
any real Claude Code process at all), per the blocker's own
"an Attrappe belasten" instruction.

Methodology (`test_detach_isolation.py`):
1. A "harness leader" (`harness_leader.sh`) is started in its own fresh
   session/process-group (`start_new_session=True`), simulating a job that hosts
   a subject plus a witness spawned as an ordinary background child of that same
   session — the situation `witness_v2.py` was actually in.
2. Inside that harness: one dummy subject, one **naive** witness (same
   `witness_v3.py` code, `--daemonize` omitted — reproduces the v2 vulnerability),
   one **fixed** witness (`--daemonize` set).
3. A single `SIGTERM` is sent to the harness's whole process group — this takes
   the subject and the naive witness down in the *same* kernel action (no race
   against either witness's poll loop; this is a closer match to "died WITH the
   subject" than killing them separately with a timing gap).
4. Checked: did the naive witness die without ever reaching a completed state
   (reproduces the bug)? Did the fixed witness survive the same signal (different
   pgid/session by then) and go on to notice the subject's death and complete its
   relaunch (proves the fix)?

### Result: 5/5 runs PASS, deterministic, no stray processes left behind

Each run (`run_1.json` .. `run_5.json`, sha256 in `manifest.json`) shows:
- naive witness: `own_pgid == harness_pgid` at start (real member of that job,
  like v2 was); dead immediately after the single group `SIGTERM`; its evidence
  file never advances past the initial record (`"naive_witness_never_reached_
  status": true`) — it died before it could even confirm the subject's death, the
  same failure mode `reentry2_evidence.json` shows from the real run.
- fixed witness: `own_pgid != harness_pgid` at start (already detached); alive
  before the group kill; the group `SIGTERM` does not touch it (different
  session); shortly after, it independently notices the subject is gone (its own
  ordinary 0.1s poll loop) and completes its relaunch — `"status": "OK"`,
  relaunched dummy process confirmed alive.

Sample fixed-witness final record (`run_1.json`):
```json
{"daemonized": true, "status": "OK", "target_died": true,
 "relaunched_pid": 1780762, "relaunch_ms": 0.376, "waited_s": 0.6}
```

## What this does NOT prove yet

This proves the detachment mechanism itself is sound against the class of
"session/process-group teardown" events, using dummy processes. It does **not**
re-run the real `POSTREENTRY-20260901` scenario against an actual live claude
instance — doing that would mean sending a real `SIGTERM` to a real running agent
process and relaunching it, which is exactly the "process termination/reentry
against a live subject" property flagged as adjacent to the 2026-09-02
cyber-safety-filter stop. Per the task's explicit instruction, that live test is
**not attempted in this round**. It should be run by Gabriel (or with his
explicit sign-off, the way Phase 13's live SIGTERM/rollback/reentry test was
authorized) using `witness_v3.py --arm --daemonize --target-pid <real pid>
--relaunch-cmd '<real resume command>'` against an actual instance he's prepared
to have terminated and relaunched, before this is trusted for a real reentry run.

## What was explicitly NOT done

- No live process touched, no real claude/agent instance signaled, no contact
  with the actually-running v1 harness (`~/.claude/star/`).
- No canonical path written (`workpackages/active|state_events|reconciliations|
  receipts` untouched).
- No pointer promotion — G10 unchanged.
- `witness_v2.py` itself left untouched (historical evidence artifact of the
  original run; not modified).
