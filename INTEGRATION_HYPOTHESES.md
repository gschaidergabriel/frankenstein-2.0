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
| H11 | **offen (INCONCLUSIVE)** | Sandbox: only 2 of 5 phases had real, non-fabricated timings (`failure_detection_ms`, `rollback_duration_ms`); the rest would have required inventing numbers, correctly declined. Phase 13 closes most of the gap with real numbers for detection/rollback/reentry/readback on the live subject — but "rollback begin → rollback end" is still reported as one combined figure, not decomposed, and no single run has timed all five phases back-to-back as one continuous sequence. | `.../SELFINT-20260901-a1c9e2f4/hypothesis_results.json#H11`; `.../PHASE13-20260901/FINAL_REPORT.md` §"Hypothesen-Neubewertung" |
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
**Status: riskant-zurückgestellt.** H6 and H11 already have real measured numbers
(Part 1) — but only for (a) a disposable sandbox over a curated `~/.claude` subset and
(b) one narrow real boundary (a symlink pointing at a versioned Claude Code binary).
Neither has been measured against v1's actual `stern.py`/`unified.db`/hook chain
under live load. **Why deferred rather than attempted this round:** "transaction
layer" + "overhead measurable" + "recovery latency decomposition" sit in the same
vocabulary/domain as the exact combination that triggered the cyber-safety filter
above, and any version of this that touches the actually-running v1 harness process
would reintroduce at least the "injected faults against a live process" and likely
the "process termination/reentry" properties. A safer, narrower read-only variant may
exist (e.g., a continuous 5-phase timing run entirely inside the existing disposable
`self_update_transaction.py` sandbox, no live process contact at all) — this was
considered during this consolidation pass but **not attempted**, to keep this round's
scope to documentation as instructed. Left as the explicit next candidate for a
future, separately-scoped round.

---

## Part 4 — Open blockers (not hypothesis-specific)

| ID | Class | Status | Summary | Next discriminator |
|---|---|---|---|---|
| SELFINT `found_and_fixed_1` | PRODUCT_NEGATIVE | **FIXED** (same-day, 2026-09-01) | `apply_transaction` only recognized lowercase `pre_mutation`/`post_mutation`; any other truthy `injected_failure_stage` string fell through to a real mutating write, then re-raised without restoring → torn state (disk mutated, lineage still old generation). | closed — whitelist + normalize + restore-and-verify-before-reraise landed, 3 regression tests prove pre-fix-fails/post-fix-passes. |
| SELFINT `found_and_fixed_2` | EVIDENCE_INVALID | **FIXED** | `measurements.jsonl` schema v1 had no identity binding (no repo head SHA, no state digests per record) — required by `MEASUREMENT_PLAN.md`. | closed — schema v2, `run_gates.py` rewritten, cross-checked against `rollback_evidence.json`. |
| SELFINT (unnamed) | UNKNOWN_NONTERMINAL | **offen** | Explicit-ROLLBACK re-entry only proven in-process (unit test) inside the sandbox run, not as a fresh cross-process readback in the *same* run as the rollback. (Note: Phase 13 *does* prove this live, on the real subject — this specific sandbox-internal gap is narrower and still open.) | run install→inject-failure→rollback→fresh-subprocess-readback as one continuous timed sequence inside the sandbox. |
| POSTREENTRY B (unnamed) | INFRA_AUTH_TRANSPORT_QUOTA | **offen** | The external witness/auto-relaunch tool died together with the subject process during the Phase-13-adjacent post-reentry run — auto-relaunch never happened, owner completed reentry manually. | build the restart tool genuinely outside the subject's process group (real `setsid`+`nohup`+detach *before* the kill), and prove it first against a dummy process before ever running it against the real subject again. |
| MODELSUB B1 | INFRA_AUTH_TRANSPORT_QUOTA | **offen — Owner hat Retest bewusst gestrichen** | Opus arm ran out of 5h subscription quota at test 27/32; 6/32 Opus responses (incl. both abstention-tolerance tests) permanently unmeasured for this run. | none planned — cost/benefit judged negative by owner. |
| H13 | governance | **offen** | Does repaired G10 portable-transaction source inherit G9's acceptance credit, or does it need wholly fresh runtime-integration evidence? | independent reviewer / Gabriel decision on `canonicalization_proposal.json`, referencing the G6/G9/G10 chain. |
| `host_identity_sha256` real scheme | design | **offen, unverändert seit F-ITER1** | Every run to date uses `/etc/machine-id` as an explicitly test-scoped stand-in. No real scheme has ever been proposed by any agent — correctly left as an owner decision, not invented ad hoc. | Gabriel/coordinator decision needed before any `StateLineage` work can start. |
| `StateLineage`/migration plan | design | **nicht begonnen, blockiert** | Constructing `StateLineage`/`StateMigrationRequest`/`StateMigrationPlan` requires a real `lineage_id`/`generation`/`state_sha256` scheme for `unified.db` and a real `target_root` — every round through F-ITER3 has explicitly declined to invent this without authorization. | same as above — owner decision on the identity/lineage scheme is the blocking prerequisite. |
| GRID10 / `StateRootIdentity` wiring into v1 | design | **nicht begonnen** | F-ITER1–3 prove GRID10 and `StateRootIdentity` are structurally safe/portable to *look at* against real v1 state — nothing calls either from v1 `stern.py`, and no round has proposed which v1 concept (if any) should map onto GRID10's ten logical cells. | coordinator/owner design decision on whether/how v1 should adopt either module. |

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
2. **A real `host_identity_sha256` scheme** — currently only a test-scoped
   `/etc/machine-id` stand-in exists anywhere in either codebase.
3. **A real `lineage_id`/`generation`/`state_sha256` scheme for `unified.db` and a
   real `target_root`** — without these, no `StateLineage`/migration-plan work can
   start; every round has correctly declined to invent one.
4. **No wiring of any v2 self-integration primitive into v1's actual `stern.py`.**
   `StateRootIdentity` and GRID10 are both proven structurally safe to *approach*
   read-only against real v1 state (F-ITER1–3) — neither is called from v1 anywhere.
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
9. **The post-reentry auto-relaunch tool is broken** (dies with its subject,
   `INFRA_AUTH_TRANSPORT_QUOTA`, OPEN) — any future live reentry test needs a
   genuinely detached restart mechanism, proven against a dummy first.
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

**Canonical pointer stays G10.** Nothing in this document proposes, implies, or
performs a promotion away from it.
