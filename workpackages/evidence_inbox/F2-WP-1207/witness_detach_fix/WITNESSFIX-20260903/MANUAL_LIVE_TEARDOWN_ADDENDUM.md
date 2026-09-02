# Manual live group-teardown test (2026-09-03, owner-authorized)

Not the same thing as the 5/5 `test_detach_isolation.py` dummy runs (those exist
already, unchanged). This is a separate, manually-driven real-signal test, run
after explicit owner sign-off ("JA" to the direct question whether to run the
live test), to reproduce the actual OS-level failure mode more faithfully than
the scripted dummy harness does.

## Setup
- `setsid python3 harness.py` created a fresh, isolated session (pid=pgid=sid=
  1884261) containing exactly two children: a dummy long-running subject
  (`python3 -c "import time; time.sleep(600)"`, pid 1884262) and the
  `witness_v3.py --arm --daemonize` process (pid 1884263 at spawn).
- Confirmed via `ps -eo pid,pgid,sid` immediately after daemonize that the
  witness had already moved itself to a brand-new session (pgid=sid=1884264,
  own_pid=1884265) — structurally separate from the original group 1884261
  *before* any signal was sent.
- Confirmed no other process on the machine shared pgid 1884261 or 1884264
  (isolation baseline, `ps -eo pid,pgid,sid,cmd`, filtered).

## Action
- `kill -TERM -1884261` — a single group-wide SIGTERM to the *original*
  session/group only. This reproduces exactly what job-control/session
  teardown does (terminal close, controlling-process exit cascading a
  SIGTERM/SIGHUP to its whole foreground group) — the real-world trigger for
  the `witness_v2.py` bug ("Zeuge starb mit dem Subjekt").

## Result
- Original group (1884261/1884262/1884263) confirmed dead immediately after.
- `manual_live_teardown_evidence.json` (own_pid 1884265, own_pgid/sid 1884264
  — never a member of the killed group): `target_died: true`,
  `waited_s: 26.2`, `status: "OK"`, `relaunched_pid: 1887604`,
  `relaunch_ms: 0.361`.
- Relaunch actually executed, not just spawned: `relaunch_marker` file present
  (created by the relaunch command itself), and the relaunched subject
  (`python3 -c "import time; time.sleep(600)"`, pid 1887605) confirmed alive
  and running independently after the fact, then cleanly terminated as test
  cleanup.
- Witness process itself was not found alive when checked ~1s after the kill —
  this is **not** evidence of the v2 bug recurring: `relaunch_ms: 0.361` and
  `waited_s: 26.2` in its own evidence file show it detected the death and
  completed its relaunch (its designed terminal state, `main()` returning 0)
  well inside that window, i.e. before the check — not because it was killed.
  Had it not survived the group-wide SIGTERM at all (the v2 bug), it could
  never have reached `target_died: true` / `status: "OK"` in the first place,
  since that requires still being alive and polling *after* the kill.

## What this does and does not close
- **Does close:** first test of the fix under a *real*, unscripted signal
  delivery reproducing the exact real-world teardown mechanism (session/group
  SIGTERM), not just the canned dummy-harness scenario. Genuine fork/exec/
  kill/relaunch, no mocking.
- **Does not close:** the blocker's own remedy text asks for a test "against a
  real running instance" — i.e. an actual live Frankenstein v1 / Claude Code
  CLI session, per the Phase 13 precedent (real subject PID, hardened against
  touching any other live session). This run's subject was still a
  self-created dummy process, not a real CLI instance — deliberately, per this
  round's own safety instruction ("never touch a foreign running session").
  Testing against an actual live harness instance remains open and would need
  its own explicit, separately-scoped owner sign-off naming the specific
  target instance, exactly as Phase 13 required.
