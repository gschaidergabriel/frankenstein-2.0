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
| GRID10 / `StateRootIdentity` wiring into v1 | design | **Vorschlag existiert, PLUS erste End-zu-End-SHADOW-Demonstration gegen echte historische Turn-Daten (2026-09-03), weiterhin keine Live-Aktivierung** | Package `paket-1788388214637-d765a9` built an opt-in, default-OFF `f2wp1207-wiring-diagnose` subcommand in a **fresh clone** of `gschaidergabriel/frankenstein` (never `~/frankenstein-repo`) — activation only via `STERN_F2WP1207_WIRING=1` env var, no-op otherwise; 0-delta proven via `--help` diff. **2026-09-03 follow-up (`paket-1788426634287-6f53f2`):** a full pipeline `UserPromptSubmit → TypedEntry → StateRootIdentity → GRID10 frame (SHADOW) → [v1-processing placeholder, NOT executed] → Output → persisted minimal reentry evidence` was built and run, in a **fresh clone** of `gschaidergabriel/frankenstein-2.0`, against **8 real, already-completed turn-cycle markers pulled read-only from the real `unified.db`** (`turns` LEFT JOIN `retrieval_episodes`, session `a2f7b438-...`, the current live session) instead of the prior round's synthetic ten-cell exercise. Uses `frankenstein2.entity_identity.StateRootIdentity` (the variant WITH `installation_id`, from the `entity-identity-layering-v2` branch) and the unmodified `frankenstein2.grid10_interface` ABI. Result: 8/8 turns processed, 10/10 GRID10 cells completed every run, 8/8 distinct record/plan/typed-entry SHA-256 (non-uniform, real-data-driven), total work-units-used spread 27–41 across turns. Step 5 ("bestehende v1-Verarbeitung") is an explicit labeled placeholder, never executed. Still: no v1 concept mapped to any GRID10 cell (deliberately functionally neutral, same discipline as the `grid10_observation_schema.py` round); `EntityIdentity`/`installation_id` demo-minted, not canonical; nothing wired into the real `stern.py` hook chain. | coordinator/owner design decision on whether/how v1 should adopt either module, PLUS an explicit owner sign-off before any real activation against `~/frankenstein-repo`/`unified.db`. Branches: `self-integration/wp1207-v1-wiring-proposal-20260903T053400Z` (commit `917cb9e`, `gschaidergabriel/frankenstein`) for the diagnostic-subcommand proposal; `self-integration/wp1207-entity-identity-layering-v2-20260903` (`gschaidergabriel/frankenstein-2.0`) for this pipeline demo, both pushed, neither merged. Details: `gschaidergabriel/self-integration` `log/2026-09-03-012-v1-wiring-proposal.md` + the new pipeline-demo log entry. |

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

**Canonical pointer stays G10.** Nothing in this document proposes, implies, or
performs a promotion away from it.
