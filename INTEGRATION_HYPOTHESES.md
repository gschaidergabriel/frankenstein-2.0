# WP1207 Integration Hypotheses — Consolidated Status

**Written:** 2026-09-03, by a coordinator (Claude Code) session doing a consolidation
pass. **Why this file exists:** the original `INTEGRATION_HYPOTHESES.md` (the H1–H13
list) was never committed to this repository or to `gschaidergabriel/self-integration`
— it only ever lived in the local, un-versioned handoff bundle
`~/wp1207/FRANKENSTEIN_SELF_INTEGRATION_WP1207_2026-09-01/INTEGRATION_HYPOTHESES.md`
on `ai-core-node`. Two prior local-iteration rounds (2026-09-02/03) explicitly
searched both git repos for it, found nothing, and flagged that as an open problem.
This file is the fix: the original 13 hypotheses, reproduced verbatim below, plus
every subsequent evidence run's verdict on them, plus every additional
hypothesis/finding/gap that accumulated around WP1207 self-integration but was never
folded into one place. **Canonical status stays what the underlying evidence already
says — this file changes no verdicts, it only collects them.**

**Update 2026-09-03 (WITNESSFIX-20260903):** the `POSTREENTRY B` blocker row (Part 4)
and Part 5 item 9 were updated with a real fix + isolated-dummy-test verdict for the
post-reentry auto-relaunch tool. This is new evidence, not a reinterpretation of old
evidence — see `workpackages/evidence_inbox/F2-WP-1207/witness_detach_fix/
WITNESSFIX-20260903/`. Nothing else in this file changed; no hypothesis verdict
touched; no live subject was contacted; no pointer promotion.

**Update 2026-09-03 (SHADOW-PIPELINE-DEMO, paket-1788426634287-6f53f2):** the
`GRID10 / StateRootIdentity wiring into v1` row (Part 4) and Part 5 item 4 were
updated — the pipeline `UserPromptSubmit → TypedEntry → StateRootIdentity → GRID10
frame (SHADOW) → [v1-processing placeholder] → Output → persisted evidence` now runs
end-to-end against 8 real, already-completed turns pulled read-only from the real
`unified.db` (not synthetic scenarios). Still not a live activation — see
`workpackages/evidence_inbox/F2-WP-1207/self_integration/PIPELINE-DEMO-20260903T091657Z/`.
No hypothesis verdict elsewhere touched; no live subject contacted; no pointer
promotion; `~/frankenstein-repo` read-only (hook.log + `db-pfad-zeigen`), never
written.

**Update 2026-09-03 (PERSISTENCE-REBIND-REENTRY-20260903, paket-1788427516954-97461f):**
following Gabriel's assessment after the entity-identity-layering-v2 round ("Identity-
Schicht jetzt ca. 8/10 architektonische Reife, aber erst ~5/10 Runtime-Reife... Der
naechste Wert entsteht durch Persistenz, Rebind und Reentry-Beweis -- nicht durch
weitere Klassen"), this round did NOT add new dataclasses. It: (0) fixed
`RuntimeEpoch.host_id` -> `host_binding_id` (references `HostBinding.binding_id`,
prevents "runtime says H2, binding says H3" drift); (1) added `installation_id`
additively to the LIVE `state_migration.py::StateRootIdentity` (backward-compat
proven: 15 pre-existing tests + 3 new, zero edits to pre-existing tests); (2) built
`state_rebind.py::RebindEligibleMigrationRequest`, additive/parallel to the live
`StateMigrationRequest` (left completely unmodified, its hard host-equality check
still fires exactly as before) -- implements "same installation + valid HostBinding
transition -> Migration/Rebind erlaubt"; (3) proved real SQL INSERT/SELECT
persistence of one EntityIdentity + one InstallationIdentity in an isolated sandbox
sqlite db; (4) hung a `RuntimeEpoch` reentry chain off two genuinely different real
OS subprocesses (crash -> witness-style restart -> relaunch), persisted + verified
via SQL SELECT; (5) **GOLD TEST, passed**: `E1==E1, I1==I1, StateRootIdentity stays
bound to I1` proven by SQL SELECT across a real host rebind (H1 SUPERSEDED, H2
ACTIVE, same `installation_id`) *and* a real runtime change (two distinct real OS
processes, R81 -> R82 chained) happening simultaneously. See dedicated section
"Part 5a -- Schritt 5 Gold Test (2026-09-03)" below and
`gschaidergabriel/frankenstein-2.0`, branch
`self-integration/wp1207-persistence-rebind-reentry-20260903` (built off commit
`8432d6ed`), files `src/frankenstein2/entity_identity.py`,
`src/frankenstein2/state_migration.py`, `src/frankenstein2/state_rebind.py` (new),
`tests/test_step3_sandbox_persistence.py` (new),
`tests/test_step4_runtime_epoch_reentry.py` (new),
`tests/test_step5_gold_host_rebind.py` (new, the Gold Test). 64/64 tests green
across the whole round. Still: no UnifiedDB write path against the REAL
`~/.local/share/agentzero/unified.db`, no wiring into `stern.py`/`witness_v3.py`,
no live activation -- everything in this update is isolated/sandbox, per the same
discipline every prior round in this file has followed. No hypothesis verdict
elsewhere touched; no live subject contacted; no pointer promotion; branch pushed,
not merged to `main`.

**Update 2026-09-03 (LIVE-SHADOW-WIRING, paket-1788442476683-c1db4c):** the
`GRID10 / StateRootIdentity wiring into v1` row (Part 4) was updated again — this
is the first round in the entire series that actually modified
`~/frankenstein-repo` (the live checkout every running Claude-Code session on this
machine resolves `CLAUDE_PLUGIN_ROOT` to). New `_f2wp1207_shadow_beobachtung()` in
`stern.py`'s real `UserPromptSubmit` hook branch, three hard gates per Gabriel's
explicit protocol: feature flag default OFF (`STERN_F2WP1207_SHADOW_LIVE`), live
0-delta (proven via an OFF→ON→OFF bookend test against the real, moving `unified.db`
— see Part 5c for why a naive OFF-vs-ON diff alone is not valid proof against a live
system), and failure isolation (proven via an artificially injected exception, hook
still exits 0 with byte-identical output). First-ever `main` merge in this series
(`gschaidergabriel/frankenstein` commit `4f17e55`, justified by default-OFF), then
`~/frankenstein-repo` pulled to that commit with a noted rollback target and an
immediate post-pull hook-call verification. End state: code live, flag off. See
"Part 5c" below for full detail. No hypothesis verdict elsewhere touched; no pointer
promotion; `main` in `frankenstein-2.0` still untouched by this round (this file's
branch only).

**Placement decision:** committed here (`frankenstein-2.0` repo root) because every
`H*` ID and every evidence path below is meaningful only relative to this repo's
`workpackages/evidence_inbox/F2-WP-1207/...` tree — this is target-system
documentation, not blog narrative. A mirror copy lives in
`gschaidergabriel/self-integration` (repo root) for discoverability from the blog
side, marked there as a mirror with this file as source of truth. Both copies committed
on non-`main` branches / main-of-the-blog-repo per existing project discipline (see
`AUTHORITY_AND_SAFETY_RULES.md` — no canonical-chain mutation without explicit
owner authorization; this file is documentation, not a canonicalization proposal, and
touches no file under `workpackages/active|state_events|reconciliations|receipts`).

---

## Part 1 — The original H1–H13 (source: WP1207 2026-09-01 handoff bundle)

All items were hypotheses until measured. Reproduced verbatim from
`INTEGRATION_HYPOTHESES.md` in the handoff bundle:

- **H1** — The running Frankenstein has a single release/update boundary that can be wrapped by the portable transaction layer without rewriting its cognition loop.
- **H2** — The narrowest correct integration seam is the install/update handoff; cognition/agent semantics can remain untouched.
- **H3** — A failed in-place update can restore the exact predecessor state digest and then re-enter a healthy service.
- **H4** — Restart/re-entry after success and rollback preserves expected persisted identity/state and does not duplicate irreversible effects.
- **H5** — Hostile-twin or artifact/hash mismatch is rejected before mutation.
- **H6** — Transaction-layer overhead is bounded and measurable in latency, CPU, RSS, disk I/O and recovery time.
- **H7** — Primary Frankenstein behavior does not materially degrade relative to its measured pre-integration baseline.
- **H8** — Replaying the same transaction is idempotent and produces no state divergence or duplicate effects.
- **H9** — Concurrent/stale state updates provoke CAS/retry/fail-closed behavior instead of split-brain or double-apply.
- **H10** — Self-generated evidence can remain candidate evidence until independent review; the runtime need not self-accept its own claims.
- **H11** — Recovery latency can be decomposed into detection → rollback begin → rollback end → process re-entry → healthy readback.
- **H12** — External irreversible effects can be fenced or excluded from failure injection; local rollback must not be misrepresented as external-effect rollback.
- **H13** — G6 adapter/executor evidence guides wiring, while repaired G10 portable transaction source requires fresh runtime integration evidence rather than inherited G9 credit.

### Status matrix — H1–H13 across every evidence run

| ID | Status (current) | Evolution | Key evidence |
|---|---|---|---|
| H1 | **erledigt (PASS)** | PASS in `SELFINT-20260901-a1c9e2f4` (sandbox, P5). Not re-tested live — the live subject in Phase 13 was v1's actual `~/.local/bin/claude` symlink boundary, a different, narrower seam than v2's `self_update_transaction.py` over a curated `~/.claude` managed_dir. | `.../self_integration/SELFINT-20260901-a1c9e2f4/hypothesis_results.json#H1` |
| H2 | **erledigt (PASS)** | Same run, same caveat as H1. | `.../SELFINT-20260901-a1c9e2f4/hypothesis_results.json#H2` |
| H3 | **erledigt (PASS)** | PASS in sandbox (`SELFINT`, after a same-day PRODUCT_NEGATIVE fix — see blockers below), then re-confirmed **on the real running subject** in Phase 13 (`UPDATE + injected failure` → `ROLLED_BACK`, expected==observed digest, detection 0.30 ms, rollback 0.18 ms). | `.../SELFINT-20260901-a1c9e2f4/hypothesis_results.json#H3`; `.../self_integration/PHASE13-20260901/phase13_evidence.json`; `.../PHASE13-20260901/FINAL_REPORT.md` |
| H4 | **erledigt (PASS)** | Sandbox PASS with a disclosed asymmetry (explicit-rollback path only proven in-process, not cross-process). Phase 13 closes that asymmetry live: explicit `ROLLBACK → 2.1.240` SUCCEEDED, target==observed digest, live version confirmed; real SIGTERM → death (100 ms) → new PID (112 ms) → 20 s readback identical across the process boundary (`durable_memory`, `workspace_episodes`, `arbeitspaket` counts unchanged; GWT episode unchanged). Post-reentry run additionally confirms state continuity through `--resume`. | `.../PHASE13-20260901/phase13_evidence.json#steps.process_restart`; `.../post_reentry_validation/POSTREENTRY-20260901/hypothesis_results.json#H4-reentry` |
| H5 | **erledigt (PASS)** | Sandbox: forged `target_release` digest rejected before any write; on-disk digest and generation unchanged. Not separately re-run live (would require a live hostile-twin attempt against the real subject — correctly treated as adjacent to the flagged risky combination, not attempted). | `.../SELFINT-20260901-a1c9e2f4/hypothesis_results.json#H5` |
| H6 | **erledigt (PASS), aber schmal** | PASS with real (not fabricated) `resource.getrusage`/`/proc/self/io` numbers in the sandbox run (tens of ms). Phase 13 adds real live numbers for the same quantities (detection 0.30 ms, rollback 0.18 ms, reentry 112 ms, readback ~20.1 s incl. a 20 s deliberate wait). **Caveat carried forward explicitly, still true:** all measurements are against a 62 MB curated sandbox subset or a single narrow live boundary (a symlink + one small binary), never the full real `~/.claude` tree (~5 GB) or a broader live transaction. No extrapolation was ever performed — correctly left unmeasured rather than invented. | `.../SELFINT-20260901-a1c9e2f4/measurements.jsonl`; `.../PHASE13-20260901/phase13_measurements.jsonl` |
| H7 | **erledigt (PASS), single-run caveat** | INCONCLUSIVE in the sandbox run (no live subject to compare against — correctly declined rather than faked) and still INCONCLUSIVE after Phase 13 alone (Phase 13 proved state/pointer integrity, not behavioral equivalence). **Resolved to PASS** in the dedicated `POSTREENTRY-20260901` run: a fixed 32-test cognition suite scored identically pre/post reentry (Task 1.0→1.0, Tool 1.0→1.0, Memory/GWT 1.0→1.0, Abstention 2/2→2/2, 0 errors both sides, p95 ratio 1.245 ≤ the 2× tolerance, RSS −1.6%). **Explicitly flagged caveat, still open:** single run per phase, one model (`glm-5.3-flash[1m]` via router) — no repetition, no cross-model generality claim. | `.../post_reentry_validation/POSTREENTRY-20260901/hypothesis_results.json#H7-behavior`; `.../POSTREENTRY-20260901/cognition_comparison.json` |
| H8 | **erledigt (PASS)** | Sandbox: replaying an UPDATE whose target equals the already-active release is rejected (`rejected_no_double_apply=true`); CAS-stale-replay variant analogously rejected. Not separately re-run live. | `.../SELFINT-20260901-a1c9e2f4/hypothesis_results.json#H8` |
| H9 | **erledigt (PASS)** | Sandbox: stale-caller CAS race rejected fail-closed, final state is exactly the non-stale caller's (`no_split_brain=true`). Not separately re-run live. | `.../SELFINT-20260901-a1c9e2f4/hypothesis_results.json#H9` |
| H10 | **erledigt (PASS)** | Governance/process claim, true by construction in every run so far: every evidence artifact lives under `workpackages/evidence_inbox/...`, no run has mutated `workpackages/active|state_events|reconciliations|receipts`, every run's own `canonicalization_proposal.json` states `PROPOSAL_ONLY_ZERO_ACCEPTANCE_CREDIT` / `CANDIDATE_EVIDENCE_ONLY_NO_SELF_ACCEPTANCE`. | present in every run's `canonicalization_proposal.json` |
| H11 | **erledigt (PASS) — sandbox part only; live part weiter offen** | Sandbox part CLOSED 2026-09-03 (`H11FIVEPHASE-20260903-08d23eba`): a single continuous script run measured all 5 named phases back-to-back inside one process (plus one fresh child process for phases 4-5), no live process contact — detection_ms=0.3491 (real digest-mismatch compare, not the synthetic injected-flag path), rollback_begin_to_rollback_end_ms=1.1645 (timed strictly around `store._restore_snapshot()` alone, decoupled from detection and from receipt-mint for the first time), process_reentry_ms=10.166 (real subprocess spawn-to-alive), healthy_readback_ms=0.5675 (timed inside the fresh child around `independent_readback()`). All correctness checks passed (restored bytes match healthy state, lineage never advanced, fresh-process readback confirms healthy generation+digest). This is exactly the safe next step the document itself proposed ("a continuous 5-phase timing run entirely inside the existing disposable `self_update_transaction.py` sandbox, no live process contact at all"). **Still open:** the separately-scoped, riskier live-v1-harness variant of H11 (Part 3) — not attempted in this run, deliberately. | `.../SELFINT-20260901-a1c9e2f4/hypothesis_results.json#H11` (superseded for the sandbox case, not retracted); `.../PHASE13-20260901/FINAL_REPORT.md` §"Hypothesen-Neubewertung"; `.../H11FIVEPHASE-20260903-08d23eba/hypothesis_results.json#H11`; `.../H11FIVEPHASE-20260903-08d23eba/measurements.jsonl` |
| H12 | **erledigt (PASS)** | Sandbox and Phase 13 agree: the wrapped seam is pure local filesystem (sandbox) / a local symlink swap (Phase 13) with no network calls and no external side effects; nothing in any run claims local rollback as external-effect rollback. | `.../SELFINT-20260901-a1c9e2f4/hypothesis_results.json#H12`; `.../PHASE13-20260901/FINAL_REPORT.md` |
| H13 | **offen (INCONCLUSIVE) — Governance-Entscheidung nötig** | Explicitly a canonicalization/governance question, not something any sandboxed or live gate can adjudicate on its own. No run has changed this. Needs an independent reviewer / Gabriel decision referencing the G6/G9/G10 acceptance chain (see `CURRENT_CANONICAL_STATE.md`'s own warning against inheriting G9 credit onto G10). | `.../SELFINT-20260901-a1c9e2f4/hypothesis_results.json#H13` |

---

## Part 2 — Hypotheses/findings introduced after the original 13

These were never in the original `INTEGRATION_HYPOTHESES.md` file. Numbered/named
here for the first time so future rounds don't have to re-derive them from README
prose.

### H14 — Model substitution (Opus ↔ GLM-5.3-Flash)
**Status: riskant/unvollständig (PARTIAL)** — not PASS, not FAIL.
Hypothesis: "At unchanged Frankenstein system state, the foundation model Opus can be
swapped for GLM-5.3-Flash without material degradation of defined core functional
capabilities." On 26 valid state-controlled pairs: 0 functional flips, identical
tool/memory/planning scores. **Why not PASS:** the frozen abstention tolerance
("both arms 2/2") is violated (GLM 1/2, Opus side unmeasured) and 6/32 Opus tests are
unmeasured because the ~20 EUR subscription's 5-hour quota ran out mid-test — owner
decision was explicitly **not** to retest (cost/benefit negative). **Why not FAIL:**
no core capability measurably degraded; the two GLM "failures" are content-correct
answers hitting a known frozen-rubric regex blind spot. **Operationally relevant
side-finding:** Opus cost $0.43/test vs GLM $0.24/test and exhausted quota at test
27/32; GLM ran 32/32 with no quota event, at 1.69× the p95 latency (within the 2×
tolerance). Open blocker B1 (`INFRA_AUTH_TRANSPORT_QUOTA`, OPEN, owner decided not to
fix) — Opus-side abstention behavior stays permanently unmeasured for this run unless
someone chooses to pay for a retest.
Evidence: `workpackages/evidence_inbox/F2-WP-1207/model_substitution/MODELSUB-20260901/`.

### "H1v1/H2v1" — H1/H2 translated to the local v1 harness (`~/.claude/star/`)
**Status: FAIL.** This is a *different question* from canonical H1/H2 above (which
concerns v2's own `self_update_transaction.py` seam and passed). This one asks: does
the **actual locally-installed v1 harness** (`~/.claude/star/`) have a single
release/update boundary that could be wrapped? Answer: no currently-operating one.
`github-sync-*` (PHASE 20.2) exists in code but is uninitialized (`eingerichtet:
false`) and is push-only (star → private GitHub repo) with zero pull/deploy-back code
path. `stern.py` itself happens to be byte-identical to `origin/main` (verified via
independent shallow clone), but that is incidental — 29 of 30 local `.py` modules
aren't even tracked in the repo's real `scripts/` directory (only in an archival
mirror, `DEV_SOURCE_RESEARCH/repository/scripts/`, itself out of sync: 26/28 match,
2 are ahead by unpublished local fixes). The one real, working, documented boundary
(`HUMAN_READ_THIS/03_INSTALLING_IT.md` / `AI_START_HERE_DO_NOT_SCAN_REPO/
CLAUDE_CODE/00_DO_THIS.md`) is a one-shot **install**-from-scratch flow, not an
**update**-an-existing-install flow — it doesn't detect or apply drift.
**Implication:** building a portable transaction layer around v1 would mean first
*constructing* a real deploy/update mechanism, not wrapping an existing one — the
opposite of what H1's premise assumes for this specific subject.
Evidence: `gschaidergabriel/self-integration` `log/2026-09-03-005-h1h2-release-boundary.md`.

### Fusion-map track (v1 ↔ v2 compatibility, not part of H1–H14 numbering)
Three small, deliberately-scoped read-only checks run after the cyber-safety-filter
stop (see Part 3), each built to share none of the four flagged risk properties
(hostile-twin simulation + injected faults against a live process + process
termination/reentry + a transaction layer wrapped around an active agent):

- **F-ITER1 — `StateRootIdentity` discriminator vs. real v1 `unified.db`.**
  **Status: erledigt (PASS), schwaches Signal.** v2's
  `state_migration.py::StateRootIdentity.assert_eligible_canonical_root()` accepts the
  real v1 DB path as a structurally eligible `CANONICAL_DURABLE` root — but this is
  caller-supplied-claim validation (no existence check, no independent host
  discovery), and `host_identity_sha256` was an arbitrary test literal, not a real
  scheme. DB fingerprint unchanged before/after. First run used the **wrong** DB path
  (`~/.claude/star/unified.db`, pre-split-brain-fix) — see F-ITER2.
  Evidence: `workpackages/evidence_inbox/F2-WP-1207/self_integration/LOCAL-ITER0-20260902T163811Z/`.
- **F-ITER2 — Autonomous discovery, closes F-ITER1's gap.**
  **Status: erledigt (PASS), stärkeres Signal.** Rebuilds the same check but
  self-discovers the real v1 DB path via v1's own `stern.py db-pfad-zeigen`
  resolver (found: `~/.local/share/agentzero/unified.db`, the canonical post-split
  path — a live confirmation of the DB-split-brain fix documented elsewhere in the
  `self-integration` README), independently re-verifies existence, computes a real
  streaming SHA-256, and checks the real SQLite header before calling v2's
  (unmodified) `StateRootIdentity`. DB fingerprint unchanged before/after.
  `host_identity_sha256` still explicitly test-scoped, not a real scheme proposal.
  Evidence: `workpackages/evidence_inbox/F2-WP-1207/self_integration/LOCAL-ITER2-20260902T181450Z-report.json`.
- **F-ITER3 — GRID10 interface read-only compatibility check.**
  **Status: erledigt (PASS).** `src/frankenstein2/grid10_interface.py` (F2-WP-503)
  is a stdlib-only, dependency-free ABI for ten opaque "logical cell" budget slots.
  Static AST import scan: zero third-party dependencies. Dynamic pass: unmodified
  module imported, all ten cells driven through synthetic data, all budgets/digests
  compute cleanly. v1 has no competing "logical cell" concept (two literal "grid10"
  string hits in `stern.py` are unrelated FTS-guard boilerplate). No wiring into v1
  proposed or done. v1 DB fingerprint unchanged before/after.
  Evidence: `workpackages/evidence_inbox/F2-WP-1207/self_integration/LOCAL-ITER3-20260902T183203Z/`.

---

## Part 3 — Riskant-zurückgestellt (deliberately not attempted)

### The broad sandbox test catalog (stopped by Anthropic's cyber-safety filter, 2026-09-02)
**Status: riskant-zurückgestellt, offen für Gabriel.** A spawned build agent given the
full `ITERATION_PROTOCOL.md` phases 5–11 in one combined request (hostile-twin/hash-
mismatch simulation + injected faults against a live process + process
termination/reentry + a transaction layer wrapped around an active agent) was
terminated by Anthropic's automatic cyber-safety filter before execution (`status:
failed`, tag `[cyber]`) — a security stop, not a content error. **Why:** individually
normal reliability engineering; in combination, enough overlap with offensive
security-testing patterns to trigger the filter, even though the work is authorized
self-hosted research. **Explicit policy since then, followed by every subsequent
round including this one:** do not reformulate the request to route around an
automatic safety mechanism, regardless of how legitimate the underlying project is.
Package `paket-1788365306767-ff52ea` stayed open/unreconciled rather than being
silently dropped or falsely marked done.
Evidence: `gschaidergabriel/self-integration` `log/2026-09-02-001-...md` +
README section "Bau-Agent von Anthropics Cyber-Sicherheitsfilter gestoppt".

### H6 (further) / H11 (closing) on the **real, current v1 harness** specifically
**Status: riskant-zurückgestellt (H11-Sandbox-Teil jetzt PASS, Rest unverändert).**
H6 and H11 already have real measured numbers (Part 1) — but only for (a) a
disposable sandbox over a curated `~/.claude` subset and (b) one narrow real
boundary (a symlink pointing at a versioned Claude Code binary). Neither has been
measured against v1's actual `stern.py`/`unified.db`/hook chain under live load.
**2026-09-03 update:** the "safer, narrower read-only variant" flagged below as not
yet attempted — "a continuous 5-phase timing run entirely inside the existing
disposable `self_update_transaction.py` sandbox, no live process contact at all" —
was attempted and closed the **sandbox part** of H11 (`H11FIVEPHASE-20260903-08d23eba`,
see Part 1 table above). The live-harness part described in the rest of this note
remains fully deferred and unattempted; nothing below changed. **Why deferred rather
than attempted this round:** "transaction layer" + "overhead measurable" + "recovery
latency decomposition" sit in the same vocabulary/domain as the exact combination
that triggered the cyber-safety filter above, and any version of this that touches
the actually-running v1 harness process would reintroduce at least the "injected
faults against a live process" and likely the "process termination/reentry"
properties. Left as the explicit next candidate for a future, separately-scoped
round with its own owner sign-off naming the specific target instance.

---

## Part 4 — Open blockers (not hypothesis-specific)

| ID | Class | Status | Summary | Next discriminator |
|---|---|---|---|---|
| SELFINT `found_and_fixed_1` | PRODUCT_NEGATIVE | **FIXED** (same-day, 2026-09-01) | `apply_transaction` only recognized lowercase `pre_mutation`/`post_mutation`; any other truthy `injected_failure_stage` string fell through to a real mutating write, then re-raised without restoring → torn state (disk mutated, lineage still old generation). | closed — whitelist + normalize + restore-and-verify-before-reraise landed, 3 regression tests prove pre-fix-fails/post-fix-passes. |
| SELFINT `found_and_fixed_2` | EVIDENCE_INVALID | **FIXED** | `measurements.jsonl` schema v1 had no identity binding (no repo head SHA, no state digests per record) — required by `MEASUREMENT_PLAN.md`. | closed — schema v2, `run_gates.py` rewritten, cross-checked against `rollback_evidence.json`. |
| SELFINT (unnamed) | UNKNOWN_NONTERMINAL | **geschlossen 2026-09-03** | Explicit-ROLLBACK re-entry only proven in-process (unit test) inside the sandbox run, not as a fresh cross-process readback in the *same* run as the rollback. (Note: Phase 13 *does* prove this live, on the real subject — this specific sandbox-internal gap was narrower.) **Closed by `H11FIVEPHASE-20260903-08d23eba`:** install→corrupt-payload→detect(real digest mismatch)→rollback(`_restore_snapshot`)→fresh-subprocess-readback run as one continuous timed sequence entirely inside the sandbox, `healthy_readback_confirmed=true`. Uses the INSTALL/UPDATE ROLLED_BACK recovery path (not the separate explicit `apply_rollback` operation) — if a cross-process readback specifically after an *explicit* `apply_rollback` call is still wanted, that narrower variant remains open. | closed for the ROLLED_BACK-recovery path; an explicit-`apply_rollback`-specific cross-process readback variant would be a small follow-up, not yet done. |
| POSTREENTRY B (unnamed) | INFRA_AUTH_TRANSPORT_QUOTA | **teilweise behoben, jetzt live-erhärtet (WITNESSFIX-20260903 + manueller Live-Teardown-Test 2026-09-03)** | Root cause confirmed: `witness_v2.py` never detached *itself* from the session/process-group that launched it (only its post-death relaunch child got `start_new_session=True`); if that launching session/group is torn down together with the subject, an undetached witness goes down with it before it can act — exactly what `reentry2_evidence.json` shows (cut off right after the first `flush()`, before `died`/`status`/`new_pid`). Fix (`witness_v3.py`, double-fork+setsid self-daemonize as the first thing in `main()`) proven 5/5 PASS against an isolated dummy subject via the scripted harness (`test_detach_isolation.py`), **then owner-authorized (Gabriel: explicit "JA")** and re-run manually with real, unscripted signal delivery: a fresh isolated session (`setsid`) containing subject+witness, confirmed via `ps` that the witness had already moved itself to a new session/pgid *before* any signal, then a single group-wide `kill -TERM -<pgid>` on the *original* group only (reproducing real job-control/session teardown). Original group confirmed dead; witness's own evidence file (`target_died: true`, `waited_s: 26.2`, `status: "OK"`, `relaunched_pid`, `relaunch_ms: 0.361`) proves it was still alive and polling *after* the kill, detected the death, and completed the relaunch — the relaunched subject was independently confirmed alive afterward. | **Still open:** this run's subject was a self-created dummy process, not an actual live Frankenstein v1 / Claude Code CLI instance (deliberately — this round's safety instruction was "never touch a foreign running session"). A test against a real running harness instance (Phase-13-style, real subject PID, hardened against touching any other live session) remains undone and needs its own separately-scoped owner sign-off naming the specific target instance. Evidence: `workpackages/evidence_inbox/F2-WP-1207/witness_detach_fix/WITNESSFIX-20260903/` (`NOTES.md`, `witness_v3.py`, `test_detach_isolation.py`, `manifest.json`, `run_1..5.json`, `MANUAL_LIVE_TEARDOWN_ADDENDUM.md`, `manual_live_teardown_evidence.json`). |
| MODELSUB B1 | INFRA_AUTH_TRANSPORT_QUOTA | **offen — Owner hat Retest bewusst gestrichen** | Opus arm ran out of 5h subscription quota at test 27/32; 6/32 Opus responses (incl. both abstention-tolerance tests) permanently unmeasured for this run. | none planned — cost/benefit judged negative by owner. |
| H13 | governance | **offen** | Does repaired G10 portable-transaction source inherit G9's acceptance credit, or does it need wholly fresh runtime-integration evidence? | independent reviewer / Gabriel decision on `canonicalization_proposal.json`, referencing the G6/G9/G10 chain. |
| `host_identity_sha256` real scheme | design | **ENTSCHIEDEN: Kandidat A (Gabriel, 2026-09-03), implementiert + getestet in Isolation, NICHT aktiviert gegen Live-System** | Vorschlag (paket-1788424194135-8f29c3) hatte 3 Kandidaten und empfahl A. Gabriel wählte **Kandidat A** (gesalzene lokale `/etc/machine-id`) als kanonisches Schema. Nachfolgepaket `paket-1788424844685-d37b51` machte daraus echten, laufenden Code (nicht mehr nur Skizze): `scripts/host_identity_kandidat_a.py` in einem frischen `gschaidergabriel/frankenstein`-Klon (Branch `self-integration/wp1207-host-identity-kandidat-a-20260903`, commit `7ca5cce`) — Pepper via `secrets.token_hex(32)` einmalig erzeugt und wiederverwendet, `/etc/machine-id` mit sauberem Fallback, Salting + Doppel-SHA256, `canonical_json` wie jede andere sha256-Identität im Codebase. **Pepper-Speicherort: `star_konfig`**, nicht der PHASE-18-Tresor — Begründung: `vault_hinzufuegen()` verlangt Pflichtfeld `url` (Zugangsdaten-Schema, passt nicht auf einen reinen Pepper), GPG-Entschlüsselung wäre teuer bei jedem Aufruf, und der Pepper authentifiziert nirgendwo (reines Defense-in-depth-Salt, wie die Proposal selbst als zulässige Alternative nennt). **14/14 echte `unittest`-Fälle PASS** (`scripts/test_host_identity_kandidat_a.py`): Determinismus (gleicher Pepper+machine-id → gleicher Hash), Verschiedenheit (anderer Pepper bzw. andere machine-id → anderer Hash), Format (64 lowercase hex, auch im Fallback-Fall), Fallback bei fehlender/leerer `/etc/machine-id` (sauber, kein Absturz), Pepper-Persistenz real in `star_konfig` geprüft, kein Pepper-Leak in stdout/stderr oder im finalen Hash. Kein Aufrufer importiert das Modul, keine echte `unified.db` je berührt (jede Test-DB eine frische Temp-Datei), `~/frankenstein-repo` (Live-Checkout) nie angefasst. | **Aktivierung gegen den echten laufenden v1-Harness bleibt eine separate, spätere Owner-Entscheidung** — dieses Paket implementiert und testet nur in Isolation. Details: `workpackages/evidence_inbox/F2-WP-1207/self_integration/HOST_IDENTITY_PROPOSAL_20260903.md` (Vorschlag), `gschaidergabriel/self-integration` `log/2026-09-03-013-host-identity-proposal.md` (Vorschlag) + `log/2026-09-03-014-host-identity-kandidat-a-implementiert.md` (Umsetzung). |
| `StateLineage`/migration plan | design | **nicht begonnen, blockiert** | Constructing `StateLineage`/`StateMigrationRequest`/`StateMigrationPlan` requires a real `lineage_id`/`generation`/`state_sha256` scheme for `unified.db` and a real `target_root` — every round through F-ITER3 has explicitly declined to invent this without authorization. | same as above — owner decision on the identity/lineage scheme is the blocking prerequisite. |
| GRID10 / `StateRootIdentity` wiring into v1 | design | **Vorschlag+Demo existieren, PLUS ECHTES Live-Wiring in ~/frankenstein-repo (2026-09-03, Part 5c) mit 3 harten Gates bewiesen -- Code ist live, Feature-Flag default OFF, keine dauerhafte Aktivierung** | Package `paket-1788388214637-d765a9` built an opt-in, default-OFF `f2wp1207-wiring-diagnose` subcommand in a **fresh clone** of `gschaidergabriel/frankenstein` (never `~/frankenstein-repo`) — activation only via `STERN_F2WP1207_WIRING=1` env var, no-op otherwise; 0-delta proven via `--help` diff. **2026-09-03 follow-up (`paket-1788426634287-6f53f2`):** a full pipeline `UserPromptSubmit → TypedEntry → StateRootIdentity → GRID10 frame (SHADOW) → [v1-processing placeholder, NOT executed] → Output → persisted minimal reentry evidence` was built and run, in a **fresh clone** of `gschaidergabriel/frankenstein-2.0`, against **8 real, already-completed turn-cycle markers pulled read-only from the real `unified.db`** (`turns` LEFT JOIN `retrieval_episodes`, session `a2f7b438-...`, the current live session) instead of the prior round's synthetic ten-cell exercise. Uses `frankenstein2.entity_identity.StateRootIdentity` (the variant WITH `installation_id`, from the `entity-identity-layering-v2` branch) and the unmodified `frankenstein2.grid10_interface` ABI. Result: 8/8 turns processed, 10/10 GRID10 cells completed every run, 8/8 distinct record/plan/typed-entry SHA-256 (non-uniform, real-data-driven), total work-units-used spread 27–41 across turns. Step 5 ("bestehende v1-Verarbeitung") is an explicit labeled placeholder, never executed. Still: no v1 concept mapped to any GRID10 cell (deliberately functionally neutral, same discipline as the `grid10_observation_schema.py` round); `EntityIdentity`/`installation_id` demo-minted, not canonical; nothing wired into the real `stern.py` hook chain. | coordinator/owner design decision on whether/how v1 should adopt either module, PLUS an explicit owner sign-off before any real activation against `~/frankenstein-repo`/`unified.db`. Branches: `self-integration/wp1207-v1-wiring-proposal-20260903T053400Z` (commit `917cb9e`, `gschaidergabriel/frankenstein`) for the diagnostic-subcommand proposal; `self-integration/wp1207-entity-identity-layering-v2-20260903` (`gschaidergabriel/frankenstein-2.0`) for this pipeline demo, both pushed, neither merged. Details: `gschaidergabriel/self-integration` `log/2026-09-03-012-v1-wiring-proposal.md` + the new pipeline-demo log entry. |

---

## Part 5 — What's still missing before "a finished v2"

This is the honest completion checklist, built directly from the non-claims each run
made about itself plus the open items above — not a new invention:

1. **Whole-system / target / physical / effect / completion / training / GRID10 /
   GWT-J-Space / provider-model acceptance credit are all still zero**, per
   `CURRENT_CANONICAL_STATE.md`'s own frozen non-claims list. Every self-integration
   run since (SELFINT, Phase 13, post-reentry, model-substitution, all four local
   iterations) is explicitly candidate/non-canonical evidence — none has changed
   this, none has tried to.
2. **A real `host_identity_sha256` scheme** — **ENTSCHIEDEN: Kandidat A (Gabriel,
   2026-09-03), implementiert + getestet in Isolation, NICHT aktiviert gegen
   Live-System.** `scripts/host_identity_kandidat_a.py` +
   `scripts/test_host_identity_kandidat_a.py` (fresh `gschaidergabriel/frankenstein`
   clone, branch `self-integration/wp1207-host-identity-kandidat-a-20260903`, commit
   `7ca5cce`) turn the Part-4 sketch into real, running code — 14/14 unittest cases
   PASS. Pepper lives in `star_konfig` (not the Tresor; see Part 4 row for the
   rationale). Still zero code path *calls* this from anywhere in `stern.py`, and no
   `StateLineage` object has ever been constructed with a real (non-placeholder)
   value — activation against the real running v1 harness remains a separate,
   later owner decision.
3. **A real `lineage_id`/`generation`/`state_sha256` scheme for `unified.db` and a
   real `target_root`** — without these, no `StateLineage`/migration-plan work can
   start; every round has correctly declined to invent one.
4. **No wiring of any v2 self-integration primitive into v1's actual `stern.py`
   has been activated against a live system.** `StateRootIdentity` and GRID10 are
   both proven structurally safe to *approach* read-only against real v1 state
   (F-ITER1–3). **2026-09-03 update:** a default-OFF wiring *proposal* now exists
   (`f2wp1207-wiring-diagnose` subcommand, gated on `STERN_F2WP1207_WIRING=1`,
   built and pushed on a branch of a fresh clone — never touching the live
   `~/frankenstein-repo` checkout or `main`) — see the Part 4 table row above.
   **2026-09-03 follow-up (`SHADOW-PIPELINE-DEMO`):** the full
   `UserPromptSubmit → TypedEntry → StateRootIdentity → GRID10 frame (SHADOW) →
   [v1-processing placeholder] → Output → persisted evidence` pipeline was
   demonstrated end-to-end against 8 real historical turns (not synthetic
   scenarios) — still only inside a fresh `frankenstein-2.0` clone, still with
   step 5 an unexecuted labeled placeholder, still never touching
   `~/frankenstein-repo` or a live process. Neither this nor the
   `f2wp1207-wiring-diagnose` proposal has ever been activated against a real
   running v1 instance; that remains entirely an owner decision.
5. **v1's local harness (`~/.claude/star/`) has no real release/update boundary at
   all** (H1v1/H2v1 = FAIL) — before any transaction layer could wrap it, one would
   first need to be built (a genuine pull/deploy path with version pinning; today
   only a dormant push-only export scaffold and an ad-hoc hand-copy habit exist).
6. **H11 is not fully closed**: no single run has timed detection → rollback-begin →
   rollback-end → re-entry → readback as one continuous sequence; "rollback begin →
   end" is still reported as one combined figure everywhere it's been measured.
7. **H7's PASS rests on one run, one model** (`glm-5.3-flash[1m]`) — no repetition,
   no cross-model behavioral-equivalence claim beyond the one substitution tested
   under H14 (which itself only reached PARTIAL, not PASS, for a different reason:
   incomplete Opus-side data, not a behavioral failure).
8. **H13's governance question is unresolved**: whether G10 (repository-regression
   scope) inherits G9's (VPS clean-host) acceptance credit is explicitly flagged by
   the project's own frozen state doc as a distinction that must not be silently
   collapsed — no round has been authorized to decide this.
9. **The post-reentry auto-relaunch tool's detach bug is fixed and dummy-tested,
   not yet live-tested.** `witness_v3.py` (self-daemonizing, `WITNESSFIX-20260903`)
   fixes the root cause (witness never detached itself from the launching
   session/process-group) and passed 5/5 isolated dummy runs — but per the
   flagged cyber-safety-filter-adjacent-vocabulary caution (process termination/
   reentry against a live subject), it has deliberately **not** been run against
   a real instance yet. Any future live reentry test should use it, but still
   needs an owner-authorized live confirmation first (Phase-13-style sign-off).
10. **The originally-requested broad sandbox test catalog (Phase 6 hostile-twin +
    fault-injection + reentry + transaction-wrapper, all against a live subject in
    one combined run) has never been executed** — it was correctly stopped by
    Anthropic's cyber-safety filter and, per explicit project policy, was never
    retried in a reformulated way. Individual pieces of it *have* since been proven
    safely in isolation (Phase 13 did a real live update→fail→rollback→kill→reentry
    cycle on a narrow boundary; post-reentry did a real behavioral comparison) — but
    the full combined catalog against the broad `~/.claude` boundary remains
    unattempted and requires Gabriel's explicit sign-off on how to decompose it
    further before any future round should try again.
11. **`main` in `frankenstein-2.0` has never been touched by any self-integration
    evidence** — every run from `SELFINT-20260901-a1c9e2f4` through F-ITER3 lives on
    its own branch, pushed but unmerged, by design (no coordinator authorization
    requested or given). Promoting any of this to canonical status is explicitly out
    of scope for every round to date, including this one.

---

## Part 5a — Schritt 5 Gold Test (2026-09-03)

Gabriel's condition, verbatim: **"E1 bleibt E1, I1 bleibt I1, StateRoot bleibt
derselben Installation zugeordnet, obwohl Host UND Runtime wechseln."**

**Verdict: PASSED.** `tests/test_step5_gold_host_rebind.py::
Step5GoldHostRebindTests::test_gold_e1_stays_e1_i1_stays_i1_stateroot_stays_installation_despite_host_and_runtime_change`

What the test actually does (not a text claim — an executable, currently-green
`unittest` test, isolated sandbox sqlite db, no `unified.db`, no
`~/frankenstein-repo`):

1. Mints `E1` (via `generate_entity_identity()`), `I1` (`InstallationIdentity`,
   `installation_id="I1-gold"`), a first `HostBinding` `H1` (`ACTIVE`,
   `host_id="host-old-gold"`), and a `StateRootIdentity` `S7` bound to `I1`.
   All four rows are real `INSERT`s into the sandbox db.
2. Runs `RuntimeEpoch` `R81`, bound to `H1` via `RuntimeEpoch.from_binding()`,
   backed by an actual `subprocess.Popen` (real PID, real wall-clock
   `started_at`, waited-for exit). Persisted via real `INSERT`.
3. Checkpoints `S7.installation_id == I1.installation_id` via `SELECT`
   *before* touching anything else.
4. **The rebind:** `H1.superseded()` is applied via a real `UPDATE
   host_binding SET status=? WHERE binding_id=?` (not a Python-only
   transform); a new `HostBinding` `H2` (`ACTIVE`, `host_id="host-new-gold"`,
   **same `installation_id`**) is `INSERT`ed.
5. **Runtime changes too:** a second, genuinely different real OS subprocess
   is spawned (different PID, asserted `!=` the first); `R82 =
   r81.next_epoch(host_binding_id=h2.binding_id, ...)` chains it to `R81` via
   `predecessor_epoch_id`. Persisted via real `INSERT`.
6. **Every assertion below reads back via a fresh `sqlite3.connect()` +
   `SELECT`, not the in-memory Python objects:**
   - exactly one `entity_identity` row, still `E1`'s `entity_id`
   - exactly one `installation_identity` row, still `I1`, still pointing at `E1`
   - `S7`'s `installation_id` is `I1` both pre- and post-swap, unchanged
   - `H1` is `SUPERSEDED`, `H2` is `ACTIVE`, both under `I1`, different `host_id`
   - `R81` references `H1`/`pid1`, `R82` references `H2`/`pid2`/`predecessor=R81`,
     both under the same `installation_id` and the same `state_root_id`
   - one combined `assertTrue(...)` conjoining all of the above, labeled with
     the gold condition text itself

A second test in the same file
(`test_bonus_rebind_eligible_under_new_path_still_rejected_under_old_path`)
ties Schritt 2 into the same scenario: the identical source/target root pair
(differing only in `host_identity_sha256`) is accepted by the new
`RebindEligibleMigrationRequest` (same `installation_id` + `ACTIVE`
`HostBinding` for the new host) and **still rejected** by the completely
unmodified, live `StateMigrationRequest` — proving Schritt 2 added a path,
it did not weaken the existing one.

**What this does NOT prove (explicit DOUBTS, not overclaimed):**
- No cross-instance registry enforces "only one ACTIVE `HostBinding` per
  `installation_id`" — validated per-instance only, same caveat
  `entity_identity.py`'s own module docstring already states for
  `BINDING_STATUS_ACTIVE`.
- The sandbox sqlite schema is this round's own design, modeled on the
  dataclass fields — it was never diffed against the real production
  `unified.db` schema (that schema was not inspected, per the safety
  instruction to stay out of `~/frankenstein-repo`).
- `RuntimeEpoch`'s "real process" is a trivial `python -c "pass"` subprocess,
  not an actual Frankenstein/witness_v3 process — the reentry MECHANICS
  (real PID, real wait, real nonzero-exit-triggers-restart, real chaining)
  are proven; a live witness_v3 integration is not attempted here, by design.
- Nothing here is wired into `stern.py`, `witness_v3.py`, or any live
  UnifiedDB — activation against the real running system remains a fully
  separate, later, owner-authorized decision, same as every prior round.

**Canonical pointer stays G10.** Nothing in this document proposes, implies, or
performs a promotion away from it.

---

## Part 5b — Closing the two Schritt-5 gaps (2026-09-03, continuation)

Schritt 5's own "What this does NOT prove" listed two explicit gaps. Both closed
in this round, on the same branch, no promotion.

### Gap 1 closed: real `unified.db` schema abgleich

The sandbox schema was held against the actual production `unified.db`,
read-only, via `sqlite3 "file:<path>?mode=ro" -readonly`. Path resolved via
`stern.py db-pfad-zeigen` from a **fresh** `gschaidergabriel/frankenstein`
clone (`~/frankenstein-repo` never touched). Full method, raw evidence
(schema dump + SHA256, object list, targeted searches, the additive migration
proposal) in
`workpackages/evidence_inbox/F2-WP-1207/self_integration/UNIFIED_DB_SCHEMA_ABGLEICH_20260903/`.

**Finding:** none of the sandbox tables (`entity_identity`,
`installation_identity`, `host_binding`, `state_root_identity`,
`runtime_epoch`) or any `GRID10` concept exist anywhere in the real schema —
a valid result in itself, not a gap in the search. `entityos_wirte` is the
closest real analog to `HostBinding` (host sightings via heartbeat) but has
no status enum, no `installation_id`, no supersede/rebind concept, and no
cross-instance invariant. The proposed migration (`f2_`-prefixed tables,
`CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` only, zero FKs
into or out of existing tables, zero collision with any of the 260+ existing
objects) is a **document only** — not applied against `unified.db`, in this
round or any prior one.

### Gap 2 closed: cross-instance invariant enforced by the engine, not by Python

New module `src/frankenstein2/entity_identity_store.py` — a sandbox sqlite
persistence layer (still `tempfile`-scoped in its own tests, never
`unified.db`) that adds

```sql
CREATE UNIQUE INDEX ux_host_binding_one_active_per_installation
    ON host_binding (installation_id) WHERE status = 'ACTIVE';
```

a SQLite partial UNIQUE index (3.8.0+), so "at most one ACTIVE `HostBinding`
per `installation_id`" is now a real engine-level constraint, not caller
discipline. `tests/test_entity_identity_store.py` (18 tests, all green)
proves this is atomic and unbypassable:

- a **hand-written raw `INSERT`** that never calls any wrapper function is
  rejected with `sqlite3.IntegrityError: UNIQUE constraint failed` —
  the directive's core demand
  (`test_naive_raw_sql_insert_bypassing_all_wrappers_still_rejected`)
- a raw `UPDATE` flipping a dormant row to `ACTIVE` is equally rejected
  (`test_naive_raw_sql_update_flip_to_active_still_rejected`)
- a **second sqlite3 connection** (what a second process opening the same
  file would get) issuing the same raw SQL, both in autocommit and inside
  its own explicit transaction, is rejected the same way
  (`test_second_connection_raw_sql_still_rejected_in_and_out_of_tx`)
- causality (not correlation) is shown directly: the identical raw `INSERT`
  is rejected while the index exists, succeeds the moment the index is
  dropped, and is rejected again the moment the index is restored
  (`test_rejection_is_caused_by_the_partial_index_not_something_else`)
- the legitimate handover path, `bind_active_host()`, does the supersede +
  insert as one `BEGIN IMMEDIATE` transaction, so no other connection ever
  observes a zero- or two-ACTIVE intermediate state
  (`test_no_other_connection_ever_observes_zero_or_two_active_rows`)
- the exact Schritt-5 Gold-Test host-swap sequence still works unmodified
  under the new index (`test_step5_gold_rebind_flow_still_works_under_the_index`)
- the invariant is per-`installation_id`, not global — a second installation
  legitimately keeps its own ACTIVE binding
  (`test_two_installations_each_keep_their_own_active_binding`)
- an older Schritt-5-style sandbox db (no index) can be retro-fitted via
  `ensure_host_binding_atomicity()`, which itself refuses to create the index
  over already-violating data rather than silently hiding the violation
  (`test_ensure_host_binding_atomicity_refuses_index_over_violating_data`)

Bonus hardening that came with the same module: a `CHECK` constraint on
`host_binding.status` (engine-level backstop behind the dataclass's own
validation) and `PRAGMA foreign_keys = ON` actually enforced per-connection
(both proven rejecting raw-SQL bypass attempts, same file).

**Regression:** all 64 tests from Schritt 0-5 plus the 18 new store tests —
**82/82 green** (`tests/test_entity_identity.py`, `test_state_migration.py`,
`test_state_rebind.py`, `test_step3_sandbox_persistence.py`,
`test_step4_runtime_epoch_reentry.py`, `test_step5_gold_host_rebind.py`,
`test_entity_identity_store.py`).

**What this still does NOT prove:** the `f2_`-prefixed migration is a
proposal, not an applied schema change — the real `unified.db` today still
has zero rows and zero tables for any of this. Nothing in `entity_identity_
store.py` is wired into `stern.py`, `witness_v3.py`, or any live write path.
Same SHADOW/additive discipline as every prior round. **Canonical pointer
stays G10.** `main` in `frankenstein-2.0` untouched by this round (branch
only, verified after push).

## Part 5c — REAL live wiring into `~/frankenstein-repo`, three hard gates (2026-09-03)

Package `paket-1788442476683-c1db4c`. Gabriel's explicit protocol: "genau ein
Live-Shadow-Wiring, weiterhin ohne Wirkung: echter UserPromptSubmit →
bestehender Hook → F2 Shadow-Beobachtung → automatischer_abruf() →
bestehender Turn unverändert weiter", with three hard gates: (1) feature
flag default OFF with an immediate rollback path, (2) live 0-delta with
the same prompt classes OFF/ON, (3) failure isolation — an F2 failure must
never take the existing v1 hook down with it.

**This is the first round in the entire F2-WP-1207 series that actually
modified `~/frankenstein-repo`** — the live checkout every running
Claude-Code session on this machine resolves `CLAUDE_PLUGIN_ROOT` to, and
therefore executes on every single hook event. Every prior round stayed
strictly inside fresh clones or against self-created dummy processes.

**Build:** new `_f2wp1207_shadow_beobachtung()` in `scripts/stern.py`, right
next to the existing `_microclay_schatten()` shadow call in the
`UserPromptSubmit` branch of `cmd_hook()`. **Design finding made while
building, not planned beforehand:** calling `automatischer_abruf()` a
second time (as the prior round's isolated demo did) would NOT have been
shadow-safe against the real DB — that function writes `star_abruf_gezeigt`
on every call, so a second call would have altered the real future
retrieval decision for that session. Fix: the new function observes only
the `treffer` result the delivering call already computed this round — no
second retrieval call, no side effect. TypedEntry/StateRoot-reference/
GRID10-frame were deliberately rebuilt lightweight and self-contained
inside `stern.py` rather than importing the separate `frankenstein-2.0`
codebase live into the shared hook process (additional foreign-import/
version-drift risk exactly where Gate 3 is meant to minimize risk) — a
conscious simplification versus the full isolated demo pipeline on
`self-integration/wp1207-entity-identity-layering-v2-20260903`.

**Isolated tests, all PASS:** Test A (flag OFF) — no evidence file created
at all, Gate 1 confirmed. Test B (flag ON, same prompt/isolated DB) —
stdout byte-identical to Test A, evidence file populated. Test C (flag ON +
artificially injected exception inside the new logic) — hook still exits 0
with byte-identical stdout, error isolated to its own evidence-error line,
never touching `hook.log`. Gate 3 confirmed.

**First-ever `main` merge in this series:** branch
`self-integration/wp1207-live-shadow-wiring-20260903` (commit `2e2bc7a`) in
`gschaidergabriel/frankenstein`, then `--no-ff` merge to `main` (commit
`4f17e55`) — justified because the feature is default-OFF, so the merge
alone has zero effect on any running process.

**Then, with maximum care:** pre-pull state of `~/frankenstein-repo` verified
clean, `HEAD=a92a2f0` noted as the rollback target. `git pull origin main` →
fast-forward to `4f17e55`. Immediately after, before anything else: a real
hook invocation against the freshly-updated checkout (`exit=0`, no
traceback, plausible real output). Flag state re-verified OFF (no evidence
file without explicitly setting the env var). No rollback needed.

**Live 0-delta (Gate 2) — honest complication, not hidden:** a naive
OFF-vs-ON diff against the real hook showed visible differences — not
because of the flag, but because the real `unified.db` changes in real
time (concurrent sessions/agents writing new `thema_status` rows,
including about this very task). A bookend test OFF→ON→OFF with the same
prompt showed the answer: the diff between the two OFF calls (bracketing
the ON call) was the same size as the diff between OFF and ON — the
observed variance comes entirely from the live system moving under the
test, not from the flag. Combined with the structural proof from (a) (the
function provably never calls `automatischer_abruf()` a second time),
Gate 2 is satisfied both structurally and empirically.

**End state:** code is live in `~/frankenstein-repo` (`HEAD=4f17e55`);
`STERN_F2WP1207_SHADOW_LIVE` was never set globally/persistently, only as a
per-invocation prefix for two deliberate test calls — default behavior
after this round remains OFF. `git status` in `~/frankenstein-repo` clean
(evidence file gitignored). **Canonical pointer stays G10, no promotion.**

**What this does NOT prove / what a real, deliberate activation would still
need:** this round proves the wiring is *safe to have live*, not that it
*should be permanently active*. A conscious activation (e.g., setting the
flag persistently via `star_konfig` or a systemd unit) remains a separate,
later decision — not an automatic follow-on of this round. Details:
`gschaidergabriel/self-integration` `log/2026-09-03-021-live-shadow-wiring-drei-gates.md`.

## Part 5d — P0: shadow observation activated persistently (2026-09-03)

Package `paket-1788444680903-3dc2a1`. Gabriel gave a 7-item priority list
(P0–P6) right after the wiring round above landed. **P0**, verbatim: "Shadow
dauerhaft, aber weiterhin rein beobachtend aktivieren ... nicht sofort
systemweit blind, sondern bewusst für eine begrenzte Beobachtungsphase" —
target: 100–1000 real shadow turns, then re-evaluate P1 (binding the
evidence to the real identity chain).

The previous round's "what this does NOT prove" section named exactly this
as the next, separate, later decision. This round is that decision.

**Change:** `_f2wp1207_shadow_aktiv()` now checks the env-var override
first (unchanged, `0`/`1` wins), then falls back to a persistent
`star_konfig` key `f2wp1207.shadow_aktiv` (same pattern as
`modell_aktiv.gewaehlt` elsewhere in `stern.py`) instead of a hardcoded
`False`. That key was set to `"1"` via `_konfig_dyn_set()` for the
observation phase — no env var involved, so it survives across process
boundaries (every hook call is its own process).

**Verification order:** real hook call before the flip (flag still
effectively off) → `exit=0`, unchanged. Flip via `_konfig_dyn_set`. Real
hook call after, no env var set → `exit=0`, visible `additionalContext`
prefix byte-identical to the pre-flip call for the same prompt, evidence
file +1 line with a real `TypedEntry`+`GRID10` frame. `hook.log` still free
of `F2WP1207` lines (Gate 3 holds). Branch
`self-integration/wp1207-p0-shadow-persistent-20260903T141805Z` (`c97b4b7`)
in `gschaidergabriel/frankenstein`, then merged to `main`
(`c97b4b73953b359a3051bbd392bd5126c20d9e61`) — the **second** `main` merge
in this series. Final control call on the merged `main` state still clean.

**Not done in this round (unchanged from Part 5c):** binding observation
records to `EntityIdentity`/`InstallationIdentity`/`StateRootIdentity`/
`RuntimeEpoch` — those remain sandbox-only (`self-integration/wp1207-
persistence-rebind-reentry-20260903`), not written to the real
`unified.db`. That is Gabriel's P1, explicitly deferred until a meaningful
volume of real shadow turns has accumulated under P0. **Canonical pointer
stays G10.** Details: `gschaidergabriel/self-integration`
`log/2026-09-03-022-p0-shadow-persistent.md`.

## Part 5e — P1: shadow evidence bound to live identity chain (2026-09-03)

Gabriel corrected the sequencing right after Part 5d: the 100-1000-turn
target belongs to the later *statistical* GRID10 role analysis (P4/P5), not
to P1 — identity binding is a *structural* question, provable with a
handful of real turns plus one controlled reentry. So P1 ran immediately,
in parallel with P0's ongoing collection, not gated behind it.

`~/frankenstein-repo/scripts/stern.py` gained two new, deliberately
self-contained helpers (same no-cross-repo-import rationale as Part 5c):
`_f2wp1207_installation_id()` (deterministic proxy: sha256 of `DB_PATH` +
this file's checkout path) and `_f2wp1207_runtime_epoch(session_id,
force_new=False)` (file-based epoch assignment per `session_id`, stored in
newly-gitignored `f2wp1207_runtime_epochs.json`; `force_new=True` mints a
new epoch with `predecessor_epoch_id` chained to the old one — the reentry
mechanism). Every `F2WP1207_SHADOW_EVIDENCE` record now also carries
`installation_id`, `state_root_id` (renamed alias of the existing
`state_root_ref_sha256`), `runtime_epoch_id`, `predecessor_epoch_id`.

**Honestly scoped:** this proves the chaining mechanism is *correct* when
triggered — it does NOT implement automatic reentry detection. No hook-side
signal for "this call follows a real process restart" exists yet;
`force_new` must be set by a future, dedicated caller (a `witness_v3`
integration — that's P2).

**Proof, with real `python3 stern.py hook` calls (not simulated):**
1. Three real calls, same test `session_id` → identical `installation_id`,
   `state_root_id`, `runtime_epoch_id`, `predecessor_epoch_id=null`.
2. Simulated reentry (direct function call with `force_new=True`, since no
   automatic trigger exists): new epoch, `predecessor_epoch_id` points
   exactly at the old epoch; `installation_id` unchanged.
3. A further real hook call after the simulated reentry correctly picks up
   the new epoch and continues using it.
4. Gate 2 (0-delta) re-checked: a grep for `F2WP1207`/`installation_id`/
   `runtime_epoch` in visible `additionalContext` across all test calls hit
   once — verified to be a legitimate UnifiedDB memory-retrieval line *about*
   F2-WP-1207 itself, not a mechanism leak.
5. Gate 3 (failure isolation) re-checked: `f2wp1207_runtime_epochs.json`
   deliberately corrupted with invalid content, then a real hook call —
   still `exit=0`, plausible output; the internal fail-closed fallback in
   `_f2wp1207_runtime_epoch` returned a non-persisted fallback epoch instead
   of propagating.

Branch `self-integration/wp1207-p1-identity-binding-20260903T145600Z`
(commit `60b9bb2`) in `gschaidergabriel/frankenstein`, then merged to `main`
(fast-forward `c97b4b7`→`60b9bb2`) — the **third** `main` merge in this
series. Verified with a real hook call both before and after the merge; no
rollback needed.

**Not done in this round:** no automatic reentry trigger (P2, needs a real
`witness_v3` lifecycle binding); no production `f2_*` UnifiedDB tables (P3);
no binding to `EntityIdentity` itself, only the three fields Gabriel named.
**Canonical pointer stays G10.** Details: `gschaidergabriel/self-integration`
`log/2026-09-03-023-p1-identity-binding.md`.

### P2 — automatic reentry trigger, live Gold Test (2026-09-03, closes the P1 gap)

The exact gap P1 left open: `force_new` had to be set manually, no signal
existed for "this call follows a real process restart". P2 adds
`F2WP1207_REENTRY_MARKERS`, a small separate JSON file that `_f2wp1207_
runtime_epoch()` checks at the top of its existing try/except: if a marker
exists for the current `session_id`, `force_new` is set automatically and
the marker is consumed (single-use). The marker is written ONLY by a
dedicated witness process (`witness_v3` pattern: double-fork+setsid
self-daemonization) — never by the hook dispatch itself. For every real live
session without an involved witness, no marker ever exists — 0-delta holds
structurally, not just empirically.

**Gold Test run LIVE, not simulated:** a self-created test subject in its
own isolated session (`setsid`), PID-baseline checked (only the subject in
that group, no foreign session), a double-fork+setsid witness watching it,
a real group-wide `kill -TERM` on ONLY the subject's group (reproducing real
job-control/session teardown). R1: three real `python3 stern.py hook` calls
for the same test `session_id` → identical `runtime_epoch_id`, `predecessor_
epoch_id=null`. Witness confirms real death, writes the marker automatically.
R2: three further real hook calls, same `session_id`, **no manual `force_new`
this time** → new `runtime_epoch_id`, correctly chained via `predecessor_
epoch_id` to the R1 epoch, `installation_id`/`state_root_id` unchanged.
Marker file empty afterward (consumed once, no double-trigger).

**All 5 Gold Test properties proven:** same `installation_id` across reentry,
same `state_root_id`, new `runtime_epoch_id` with correct chaining, GRID10
frames from R1/R2 separable via `runtime_epoch_id` AND groupable via
`installation_id`/`state_root_id`. (Full `EntityIdentity` itself is still
sandbox-only, not imported live — see the Live-Shadow-Wiring Gate-3
simplification rationale; `installation_id`/`state_root_id` stability serves
as the live-available proxy here.)

Gate 2 (0-delta) and Gate 3 (failure isolation, corrupted marker file)
re-verified real. No foreign running process ever touched — PID baseline
checked before the signal, only the self-created test group was hit; the
actual process serving this very coordinating session ran unaffected
throughout.

Branch `self-integration/wp1207-p2-reentry-gold-test-live-20260903` was
never separately created for the code change — the change landed directly
on `gschaidergabriel/frankenstein` `main` (commit `a65e728`, the **fourth**
`main` merge in this series), verified with a real hook call before and
after. Details: `gschaidergabriel/self-integration`
`log/2026-09-03-024-p2-reentry-gold-test.md`.

**Not done in this round (deliberately, per Gabriel's ordering P3/P4/P5
come after):** no production `f2_*` UnifiedDB tables; no permanent
production witness monitoring a real session (only a self-created test
subject); `EntityIdentity` itself remains sandbox-only.
**Canonical pointer stays G10.**

## Part 5g — P3: additive Identity-Migration in the REAL UnifiedDB (2026-09-03)

Direct continuation after P2. Gabriel: "Mach direkt mit P3 weiter. Keine
Pause." — full 14-step protocol given verbatim, plus a coordinator-added
requirement: full rehearsal against a copy of the real DB before touching
the original.

**Pre-condition found and fixed:** the first P3 attempt correctly halted at
the baseline check — `PRAGMA integrity_check` on the real `unified.db`
returned `malformed inverted index for FTS5 table main.vp_alias_fts`, a
pre-existing corruption of a voice-mode speaker-alias search index,
unrelated to F2-WP-1207. The safety net worked exactly as designed: nothing
was written before this was caught. `vp_alias_fts` is an external-content
FTS5 table over `vp_alias` (`content='vp_alias', content_rowid='alias_id'`).
Repaired via `INSERT INTO vp_alias_fts(vp_alias_fts) VALUES('rebuild')` —
the FTS5-native rebuild path, which does not touch the content table.
Post-repair: `integrity_check=ok`, FTS5's own `integrity-check` pragma
passes, `vp_alias` row count/content-hash identical before/after (1162 rows,
`3d365dee...`), sample searches return plausible results.

**Migration:** fresh baseline after repair (new backup + SHA256 + schema
dump + row counts of all 197 pre-existing tables). Full rehearsal against a
plain file copy first (100% clean: `commit=ok`, `integrity_check=ok`, bypass
test — a raw second `ACTIVE` `f2_host_binding` insert for the same
`installation_id`, bypassing every Python wrapper — rejected by SQLite's own
partial unique index, not just application code; full readback chain proven
over a fresh connection). Only then the identical migration against the real
file: one transaction, `CREATE TABLE IF NOT EXISTS`/`CREATE INDEX IF NOT
EXISTS` only for `f2_entity_identity`, `f2_installation_identity`,
`f2_host_binding`, `f2_state_root_identity`, `f2_runtime_epoch` plus the
already-tested partial-unique cross-instance index — no existing object
altered.

**Genesis identity, for real:** one `EntityIdentity` (`secrets.token_hex(32)`,
never derived from host/session/prompt). One `InstallationIdentity` — reuses
the proxy value already live since P1 (`sha256(DB_PATH + checkout path)`,
`fb068ee8...`), not invented fresh, so the already-running shadow pipeline
was structurally aligned with this genesis from the start. One `HostBinding`
(`ACTIVE`) — Candidate A (salted local `/etc/machine-id`) instantiated for
real for the first time (a pepper was freshly generated; none existed live
before). One `StateRootIdentity` — reuses the P1/P2 live proxy
(`sha256("F2WP1207_STATE_ROOT_REF/v1:" + DB_PATH)`, `da592ade...`). One
`RuntimeEpoch` — the currently active epoch of this very coordinating
session's shadow chain, `predecessor=None`.

**Post-commit verification on the real file:** `integrity_check=ok`; all 197
pre-existing tables' row counts compared against baseline — five
(`causal_episodes`, `durable_memory`, `effects`, `gw_herkunft`, `leases`)
show higher counts, which is normal concurrent write activity from the live
system during the minutes this careful procedure took (the migration script
structurally only ever writes to `f2_*` tables) — `vp_alias`, the one
specifically fragile table, stayed byte-identical. Bypass test re-confirmed
on the real file. New tables each hold exactly one genesis row, otherwise
empty. 203 tables total (198+5). Fresh-connection readback chain
Entity→Installation→StateRoot→ActiveHostBinding→RuntimeEpoch proven, not
asserted. Regression: real `stern.py hook` call afterward, `exit=0`, no
traceback, plausible output; the shadow-evidence entry for that call already
carries the identical `installation_id`/`state_root_id` as the new genesis
rows — no code change to `stern.py` was needed this round, because P1's
derivation formula matched the genesis scheme by construction.

`~/frankenstein-repo` untouched this round (`HEAD` stayed `a65e728`, no new
commit needed). Details:
`gschaidergabriel/self-integration`
`log/2026-09-03-025-p3-unified-db-identity-migration.md`.
**Canonical pointer stays G10.**

**Deliberately still open (superseded by P4 below):** only one `RuntimeEpoch`
existed in the real DB so far (this session's) — no predecessor chain there
yet. The live shadow pipeline wrote only to the JSONL evidence file, not
directly into `f2_runtime_epoch`. GRID10 cells remain functionally neutral.

## Part 5g — P4: GRID10 as a full persistent runtime-bound measurement layer (2026-09-03)

Gabriel's directive after P3 (verbatim, condensed): "GRID10 technisch
vollständig in die reale Runtime/UnifiedDB integrieren. Keine Pause und kein
Warten auf 100-1000 Turns." Explicitly NOT the goal: naming G1-G10
semantically. The goal: a complete, persistent, identity-/runtime-bound
observation layer. Package `paket-1788449933872-77f078`.

**Closed the two gaps flagged open at the end of Part 5f:**

1. **RuntimeEpoch autosync.** New `_f2wp1207_runtime_epoch_db_sync()`: every
   call to `_f2wp1207_runtime_epoch()` (freshly minted OR already-known
   epoch) now performs an idempotent `INSERT OR IGNORE` into
   `f2_runtime_epoch`, resolving `host_binding_id` live from the `ACTIVE`
   `f2_host_binding` row. Fail-closed, same discipline as everything else in
   this pipeline.
2. **GRID10 schema in UnifiedDB.** Two new additive tables:
   `f2_grid10_frame` (frame-level: entity/installation/state-root/
   runtime-epoch/session/turn-event IDs, open/closed timestamps, `status`,
   `UNIQUE(runtime_epoch_id, turn_event_id)` as the replay/dedup guard) and
   `f2_grid10_cell_observation` (one row per frame × cell, `G1`..`G10` only —
   a `CHECK` constraint enforces this, no names possible even by accident —
   input/output digests, uptake, reentry/conflict flags, timing, real
   `resource.getrusage` numbers, `predecessor_observation_id`,
   `UNIQUE(frame_id, logical_cell_id)`). Rehearsed against a copy of the real
   DB first (schema apply + autosync simulation + two frames across two
   epochs + dedup-rejection test + fresh-connection readback + integrity
   check + full row-count diff against every other table — 100% clean), then
   the identical DDL applied to the real file (fresh backup
   `unified_db_backup_20260903T154057Z.db`, hash-verified, `integrity_check`
   `ok` before and after).

**Live frame wiring.** `_f2wp1207_shadow_beobachtung()` now calls
`_f2wp1207_grid10_frame_persist()` once per real turn, writing all ten cells
atomically in one short transaction. `entity_id` cannot be locally derived
(P3 genesis, cryptographically random) — read read-only from
`f2_entity_identity`. `installation_id`/`state_root_id` remain the P1 proxy
values, verified bit-identical to the P3 genesis rows (no bridging code
needed — they already matched by construction).

Two real hook calls in the same session: same `runtime_epoch_id` reused,
`turn_event_id` incremented, 10/10 cells per frame both times, second attempt
at the same (epoch, turn) key rejected by the database itself, not just
application code.

**Gate 2/3 re-verified for real:** flag OFF → the new code path is never
entered (unchanged). A deliberately invalid `entity_id` (FK violation, real
`IntegrityError`) injected directly into `_f2wp1207_grid10_frame_persist()`:
zero rows written, no exception propagated, `hook.log` still has zero
`F2WP1207`/`GRID10` lines.

**Real reentry test R1→R2.** A self-created test subject (`sleep 600`) and a
dedicated witness process (double-fork+setsid, its own independent
session/group) in an isolated process group — PID baseline checked before
any signal (only the test group's own subject was present). Two real hook
calls → R1 (`81c08346...`, `predecessor=NULL`, 2 frames × 10 cells). A real
group-wide `kill -TERM` on the test group only (the witness, in its own
separate group, was unaffected and kept polling). Witness detects the real
death, writes the reentry marker. Two more real hook calls → R2
(`edc78a70...`, `predecessor=81c08346...`, 2 more frames × 10 cells).

**Proof, via SQL over a fresh connection, not asserted:** all four frames
(R1: 2, R2: 2) share identical `entity_id`/`installation_id`/`state_root_id`
(`7a1bd3f5.../fb068ee8.../da592ade...`), differ only in `runtime_epoch_id`,
with the correct `predecessor_epoch_id` chain — exactly the property Gabriel
asked for: GRID10 frames before/after a real reentry belong to the same
Entity/Installation/StateRoot chain but to different RuntimeEpochs.

**Honestly noted, not a bug:** `turn_event_id` counts per-epoch (resets to
`:1` after each reentry) rather than being a single global counter across the
whole session — this does not weaken the uniqueness/dedup guarantee (the
composite key `runtime_epoch_id`+`turn_event_id` stays unique across the
whole table), but is a design choice worth naming explicitly rather than
leaving it to be assumed as a global monotonic counter.

Commit `95c438c` in `gschaidergabriel/frankenstein`, pushed to `main` — the
fifth `main` merge of the series. `~/frankenstein-repo` pulled to this commit
and re-verified with a real hook call afterward (`exit=0`, unchanged output
shape). `PRAGMA integrity_check=ok` after every step. **Canonical pointer
stays G10.** Details:
`gschaidergabriel/self-integration`
`log/2026-09-03-023-p4-grid10-runtime-persistence.md`.

**Deliberately still open:** no functional hypotheses about individual cells
(explicitly P5, not this round — needs a real data volume, per Gabriel's own
100-1000-turn guidance for *that* step specifically, not for infrastructure).
`installation_id`/`state_root_id` remain proxy values, not an independent
re-derivation scheme. Continuous collection now runs automatically — every
real turn produces a persisted frame, no further action needed until P5 has
enough data.

---

## P5 — observation audit + controlled probe campaign (2026-09-03)

Gabriel's correction: don't passively wait for 100-1000 organic turns before
starting P5 — that threshold is an evidence target for functional hypotheses
(the eventual P5b/P6 step), not a blocker for building the audit
infrastructure or for generating data via controlled probes through the real
runtime path.

**P5a early finding (before any probe campaign, from the 9-10 frames that
already existed):** `uptake`/`reentry_flag`/`conflict_flag` are hardcoded
constants in every cell of every frame — zero variance by construction.
`cpu_ru_utime_delta_s`/`rss_delta_kb` were **not deltas** — cumulative
per-process `getrusage()` snapshots read ten times in a tight loop, nearly
constant (rss) or monotonically increasing purely by loop order (cpu), not by
cell identity. **Fixed** (`gschaidergabriel/frankenstein` commit `1e31955`,
pushed to `main`, real hook call verified before/after: `exit=0`, output
shape unchanged): true per-cell before/after delta. Also added an additive
`cohort` column on `f2_grid10_frame` (`ORGANIC` default / `CONTROLLED_PROBE`)
— dry run against a DB copy first, then identical migration against the real
DB (backup `unified_db_backup_20260903T161531Z.db`,
`PRAGMA integrity_check=ok` before and after).

**Second finding (not fixed this round, out of scope):** the RuntimeEpoch-ID
formula (`session_id + timestamp + pid`, second resolution) can collide when
multiple `force_new=True` calls happen in the same process within the same
second — discovered via a same-process controlled-probe reentry test (all
three "epochs" got the identical hash). **Does not affect the real P2/P4 Gold
Test** (real, separate OS processes with distinct PIDs there). Repro script:
`workpackages/evidence_inbox/F2-WP-1207/self_integration/p5/f2wp1207_p5_probe_reentry_bug_repro.py`.
Flagged for a future round.

**Controlled probe campaign:** 30 `CONTROLLED_PROBE` frames across 10
stimulus families (short/long, retrieval hit/no-hit, known/unknown topic,
ambiguity, repetition, conflict-like) × 3 real, independent RuntimeEpochs —
deliberately stopped well short of the 100-300 target once the P5b result was
already clear (more volume would have only amplified the same artifact, not
produced new insight).

**P5b — permutation test (2000 permutations, null model: cell label carries
no information) against 56 total frames / 560 cell-observation rows:**
`uptake`/`reentry_flag`/`conflict_flag`/`cpu_ru_utime_delta_s`(post-fix)/
`rss_delta_kb`(post-fix) all p=1.0 (no signal beyond the null model).
`timing_ms` alone shows p=0.0 — **investigated, not taken at face value**: G1
and G2 are consistently the two slowest cells across *every single* epoch
tested, regardless of stimulus — but `G{i}` is *always* executed at loop
position `i` by construction, so this is classic first/second-iteration
`time.monotonic()`/`getrusage()` warm-up overhead, not a property of cell
identity. **Cell identity and execution order are perfectly confounded in
the current design — it is structurally impossible to separate them without
a redesign** (randomized execution order or an explicit position covariate).

**P6 deliberately NOT performed.** Gabriel's own precondition ("only if
reproducible differentiation exists, formulate exactly one hypothesis") is
not met — the one "significant" result is fully explained by an
instrumentation artifact, not by the cells themselves. Running an ablation
against a hypothesis whose only evidence is already explained away would be
scientifically dishonest — same discipline this project has held throughout
(correctly declined rather than faked).

**What's needed before a real P5/P6 attempt can succeed:** (1) break the
position/identity confound, (2) wire real, *differentiated* per-cell
processing (that's P7 — GRID10 currently does literally the same nothing for
all ten cells, so there is nothing to differentiate yet), (3) then re-run
P5 with a real chance at a clean signal, (4) fix the RuntimeEpoch-ID
collision gap noted above.

Evidence: `workpackages/evidence_inbox/F2-WP-1207/self_integration/p5/`
(`P5_FINDINGS_20260903.md`, `P5A_AUDIT_OUTPUT_20260903.txt`,
`f2wp1207_p5_audit.py`, `f2wp1207_p5_probe_runner.py`,
`f2wp1207_p5_probe_reentry_bug_repro.py`). Canonical pointer unchanged, G10.

---

## P5c / P6 (2026-09-03, Gabriel-Direktive) — Symmetry audit + role-neutral GRID10 dynamics

**Two bugs fixed** (both in `~/frankenstein-repo` `main`@`b8f246c`):
- RuntimeEpoch-ID collision gap closed: `epoche = uuid.uuid4().hex` replaces
  the old `sha256(session_id:iso_time:pid)` scheme, which could collide on
  two fast `force_new` calls in the same process/second. Time stays
  metadata (`started_at`), never part of identity.
- `logical_cell_id` decoupled from `execution_position`: G1..G10 now run in
  a per-frame, deterministically-seeded (`frame_id`) pseudo-random order;
  both fields are stored separately in `f2_grid10_cell_observation`.

**Symmetry audit (empirical, 750 pre-fix observations checked):** 0/750 had
`predecessor_observation_id` set; `uptake`/`reentry_flag`/`conflict_flag`
were constant across all 750 rows; no per-cell state table existed. All 7
of Gabriel's audit questions ("can G3 hold state G8 can't?", "can a cell
carry state across frames?", "is there Proposal/Competition/Broadcast/
Uptake?", "can a cell's output causally re-enter the next frame?") were
factually **no**. GRID10 was a 10-channel measurement instrument, not a
10-cell functional system — confirming Gabriel's structural diagnosis
before any more data was collected.

**Re-test after the position fix:** same 30-probe design re-run over 3 real
RuntimeEpochs (genuine kill/reentry cycle, self-created test subject).
Permutation test: p≈0.99 — still no cell-identity signal in the *old*
stateless slot model, this time with the position confound genuinely
removed rather than merely suspected.

**P6 (redefined — no ablation, there was no role to ablate):** built
minimal role-neutral dynamics, live in `f2_grid10_cell_state` (one
persistent scalar per cell, PK `(installation_id, logical_cell_id)`).
Identical algorithm for all ten cells, no per-cell special-casing:
`proposal = 0.5*state + 0.5*signal(turn,cell)` → `winner = argmax` →
`broadcast = proposal[winner]` → winner's new state = `broadcast`,
losers decay `0.9*state + 0.1*broadcast` → next frame reads the updated
state back (real reentry coupling via the DB, not just claimed). Still
zero semantic names.

Evidence: `~/frankenstein-repo` commit `b8f246c`; `self-integration` main
commit `13f3f81`. Canonical pointer unchanged, G10.

---

## P6b (2026-09-04, Gabriel-Direktive) — does state predict future win probability?

Controlled probe campaign against the new stateful GRID10: **353
CONTROLLED_PROBE frames across 14 RuntimeEpochs** total (140 newly added
this round across 5 epochs — 1 via a genuine external witness-triggered
reentry, double-fork/setsid pattern, real SIGTERM + real death detection
via proper parent `waitpid()`; 4 via direct `force_new=True`, a documented
simplification since the reentry-linkage mechanism itself was already
proven with real process kills in P2 and P4 — this round's actual target
was the state-dependency question, not re-validating reentry chaining).

**Self-correction worth recording:** a first analysis pass replayed frames
in an assumed cross-session chronological order and found a striking 64.5%
repeat-win rate (vs. ~10% chance) — but `f2_grid10_cell_state` is keyed by
`installation_id`, not by epoch, so state is genuinely shared across *all*
sessions on this installation, including real ORGANIC hook calls from the
coordinator's own concurrent session. The assumed cross-session ordering
could not be verified (42/308 replay predictions didn't match the recorded
winner under that ordering) and was discarded as unreliable.

**Reliable result: strictly within-epoch order** (no cross-session ordering
assumption needed — each epoch's own `turn_event_id` sequence is ground
truth): repeat-win rate = **28/298 transitions = 9.4%**, statistically
indistinguishable from the ~10% chance baseline for 10 cells. **No
significant evidence, at this sample size, that a cell's recent
win/broadcast state measurably increases its probability of winning the
next frame.**

Mechanistically this is plausible, not surprising: the state term
contributes at most `0.5 × (previous winner's broadcast value)` to the next
proposal, competing against a fresh `0.5 × signal` for every other cell —
a real but modest boost, easily swamped by signal noise at n≈30 frames per
epoch. The Proposal→Competition→Selection→Broadcast→Uptake→Reentry cycle is
mechanistically real and wired correctly (deterministic replay matched
100% of recorded winners in every isolated, non-interleaved test run) — but
it does not yet show a *detectable* self-reinforcing advantage at current
parameters/sample size.

**Per Gabriel's own precondition ("only formulate a hypothesis if
differentiation is reproducible"): no hypothesis formulated.** This is a
valid infrastructure-correctness result, not a differentiation result —
consistent with the project's discipline throughout (declined rather than
faked). Regression: real hook call after the full campaign, `exit=0`, no
traceback, `PRAGMA integrity_check=ok`.

**What would be needed for a fairer test:** either a much larger sample
(hundreds of transitions per epoch instead of ~30), or a stronger state
weight in the update rule (currently 0.5/0.5, cf. Gabriel's original
framing — this is a parameter choice, not yet explored), before concluding
the mechanism *can't* produce self-reinforcement vs. simply hasn't been
given enough of a signal-to-noise ratio to show it yet.

Evidence: analysis scripts and raw exports kept locally under
`/tmp/f2wp1207_p6b_probe.py` and `/tmp/p6b_analysis.py` on `ai-core-node`
(not committed — reproducible from the DB state and this description; can
be added to `workpackages/evidence_inbox/` on request). Canonical pointer
unchanged, G10.

---

## P6c — State-Weight Dosis-Wirkungs-Sweep (2026-09-04, vorregistriert)

Preregistration + Ergebnisse: `self-integration` Repo, `PREREG_P6C_20260904.md`
(Commit `0770475`) + `log/2026-09-04-023-p6c-state-weight-sweep.md` (Commit
`7ae3780`). Code: `workpackages/evidence_inbox/F2-WP-1207/p6c_state_weight_sweep/`
(dieser Branch).

**Ergebnis: uneindeutig nach eigener vorab festgelegter Regel.** Dosis-Wirkungs-
Kurve bestätigt (state_weight 0.0→0.75, Effekt wächst monoton, CI schließt Null
ab ~0.5 aus). Shuffle-Kontrolle bricht den Effekt (bestätigt: eigene Zellhistorie
zählt). Frozen-State-Kontrolle bricht den Effekt NICHT (widerspricht der
PASS-Bedingung, die beide Kontrollen verlangte). Mechanistische Einordnung: die
additive Proposal-Formel (`state_weight*state + (1-state_weight)*signal`) macht
den Dosis-Effekt mathematisch erwartbar -- kein Beweis fuer emergente rekurrente
Dynamik im engeren Sinn, nur Beleg dass die Formel wie gebaut funktioniert und
zellindividuelle Historie (nicht nur Zufallswerte) den Ausgang beeinflusst.

Offen fuer eine praezisere Frozen-Kontrolle (P6d, falls gewuenscht): Divergenz
ueber viele Frames zwischen "State darf sich anpassen" und "State bleibt fix"
bei driftender Signalverteilung wurde in dieser Runde NICHT getestet.

---

## P6d — Recurrent cell-state dynamics with decay (2026-09-04)

Follows P6c's ambiguous dose-response result (frozen-state control did NOT
collapse the effect there, diagnosed as a static formula artifact, not real
memory). Gabriel's redesigned dynamics: `state(t+1) = lambda*state(t) +
alpha*uptake(t) + beta*broadcast(t) - gamma*conflict(t)`, `proposal_score(t+1)
= signal(t+1) + kappa*tanh(state(t+1))`. Preregistered (`PREREG_P6D_20260904.md`
in `self-integration`, committed before any run) six-criterion test: impulse,
frozen, shuffle, reset, decay-sweep, counterfactual — all six required for a
strict PASS.

**Result: 4/6 criteria hold cleanly (counterfactual, frozen, shuffle,
impulse-response). Reset partial (boundary breaks, structure re-forms fast).
Decay-sweep monotonicity not shown at this sample size (single run/lambda,
likely underpowered).** Not a strict PASS under the preregistered all-six
rule, but qualitatively real evidence of a causally load-bearing recurrent
mechanism — distinct from P6c's static-bias diagnosis. Two implementation
bugs found and fixed en route (long-transaction lock starvation of
`stern.py`'s own epoch-sync helper; a counterfactual stimulus key that
accidentally embedded the condition name, invalidating the "identical
stimulus" precondition until corrected). Full writeup:
`self-integration` `log/2026-09-04-028-p6d-recurrent-dynamics-results.md`.

Isolated state persisted in new table `f2_grid10_p6d_state` (additive
migration to the real `unified.db`, backed up + generalprobed against a copy
first, `PRAGMA integrity_check=ok` before/after). `~/frankenstein-repo` HEAD
unchanged this round. No wiring into the live per-turn pipeline. No cell
role or semantic name. Canonical pointer unchanged, G10.

Open for a future round: decay-sweep needs multiple seeds/replicates per
lambda; reset's fast-remixing behavior deserves its own characterization
(a structure half-life measurement) rather than pass/fail framing.
