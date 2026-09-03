# Entity identity layering v2 — Gabriel's precision pass, tested minimal schema

Paket: `paket-1788425913354-5072e0`. Supersedes
`ENTITY_IDENTITY_LAYERING_20260903.md` (kept verbatim as the historical
record — see the banner at its top). That v1 document mapped five layers and
left four questions open (§7) plus one structural ambiguity (§4: was
`StateRootIdentity` a child of `HostIdentity`, `InstallationIdentity`, or
both?). Gabriel read it and answered directly. This document is the
resulting precise model, plus the tested (not activated) code that
implements it.

## 0. Gabriel's directive, as given to this work package

1. **`StateRootIdentity` is NOT hard-bound to `HostIdentity`.** It belongs
   primarily to `InstallationIdentity`. The current host is a
   **binding/attestation** (`HostBinding`), not the identity itself. This
   replaces `HostIdentity` as the parent-facing concept in v1's model
   entirely — v1's §4 hard-enforced-in-code fact (`state_migration.py`
   pinning a root to one `host_identity_sha256`) is not disputed as *current
   shipped behavior*, but the *conceptual* parent of a state root, going
   forward, is the installation, not the host.
2. **`RuntimeEpoch` is defined by a continuous runtime lifecycle, not by a
   session id.** A session id (`CLAUDE_CODE_SESSION_ID`, `claude --resume
   <id>`) is **evidence** that an epoch continued — it is not what defines
   one. v1's §5 had already flagged this ambiguity ("this document does not
   resolve which reading should be canonical") without resolving it; this
   directive resolves it.
3. v1's four open questions (§7) are now decided — see §2 below.
4. **Exact target schema** — field names verbatim, reproduced in §3.

## 1. What changed from v1, precisely

| v1 (design doc, 2026-09-03 morning) | v2 (this document, same day) |
|---|---|
| `HostIdentity` is one of five peer-ish layers, "orthogonal" to the entity chain, referenced by `StateRootIdentity` via a hard field | `HostBinding` replaces it: a binding/attestation record, not an identity layer in its own right. `StateRootIdentity` no longer references a host at all. |
| §4 asked "child of Host+Installation, or independent?" and answered "child of both, only one enforced" | Resolved: `StateRootIdentity` is a child of `InstallationIdentity` only. The host relationship moves one level down, onto `HostBinding`, which itself hangs off `InstallationIdentity`. |
| RuntimeEpoch's relation to `session_id` left as an explicitly open question (§5, §7.2) | Resolved: RuntimeEpoch is the continuous-lifecycle fact; `session_id` (or any other correlation token) is evidence a caller may log *about* an epoch, never a field of the epoch's identity itself. This module's `RuntimeEpoch` dataclass has no `session_id` field at all, by design. |
| §7.1 open: does a cross-host migration end an `InstallationIdentity` or rebind it? | **Decided: rebind.** A host swap is a rebind of the *same* `InstallationIdentity` (a new `HostBinding` row). A new `InstallationIdentity` is minted only on a deliberate rebuild/clone/fork — never inferred from an observed host change. |
| §7.2 open: does a witness-mediated auto-relaunch count as the same RuntimeEpoch or a new one? | **Decided: always a new epoch.** A `witness_v3` restart is always a NEW `RuntimeEpoch` — same `StateRootIdentity`/`InstallationIdentity`/entity, but a new execution segment. A crash/reentry must stay visible in the epoch chain (via `predecessor_epoch_id` + `termination_reason` on the epoch that ended), never smoothed into one continuous runtime. |
| §7.3 open: where does `EntityIdentity` live? | **Decided: canonical persistent state (UnifiedDB), never a plugin cache, never `/etc/machine-id`, never a model prompt.** Once-minted immutable id + an exportable recovery/bootstrap record. Physical storage location may change; the id does not. |
| §7.4 open: should `StateRootIdentity` gain an `installation_id` field? | **Decided: yes — "der wichtigste nächste Schema-Fix" (Gabriel).** Built in this round, in the isolated proposal module (§4 below), not in the live `state_migration.py` class. |

## 2. The four v1 open questions, answered

1. **Cross-host migration → rebind, not a new installation.** Same
   `InstallationIdentity`, new `HostBinding` row (old one superseded/revoked,
   new one active). A new `InstallationIdentity` is reserved for a
   *conscious* rebuild/clone/fork — never inferred from infrastructure
   observation, matching the same discipline v1 §1 already established for
   `EntityIdentity` refounding ("a refounding is a decision, not a detected
   fact").
2. **`witness_v3` restart → always a new `RuntimeEpoch`.** The crash/reentry
   itself becomes visible as `termination_reason` on the epoch that ended,
   chained forward via `predecessor_epoch_id` on the new one. Nothing is
   allowed to present a crash+relaunch as one uninterrupted runtime.
3. **`EntityIdentity` storage location → canonical persistent state
   (UnifiedDB), not a cache, not `/etc/machine-id`, not a prompt.** A
   once-minted immutable id plus an exportable recovery/bootstrap record (the
   "Erzeugungsbeleg" — see §5). The record must be exportable *because* the
   physical machine it currently sits on is exactly the fact that is allowed
   to change without touching the id.
4. **`StateRootIdentity` gains `installation_id`.** Built as a proposal in an
   isolated module this round (§4), explicitly *not* touching the live,
   shipped `state_migration.py` class, per the same collision-avoidance
   discipline v1 already used for `INTEGRATION_HYPOTHESES.md`.

## 3. Exact target schema (verbatim field names, as given)

```
EntityIdentity
    entity_id

InstallationIdentity
    installation_id
    entity_id

StateRootIdentity
    state_root_id
    installation_id
    state_digest / root metadata

HostBinding
    installation_id
    host_id
    bound_at
    attestation
    status

RuntimeEpoch
    runtime_epoch_id
    state_root_id
    installation_id
    host_id
    started_at
    predecessor_epoch_id
    termination_reason
```

## 4. Where this is implemented

`src/frankenstein2/entity_identity.py` (this branch,
`self-integration/wp1207-entity-identity-layering-v2-20260903`), five frozen,
slotted dataclasses matching §3 exactly (plus a module-standard `schema`
version tag on each, not semantics), each with fail-closed `__post_init__`
validation in the same style as `state_migration.py`
(`_identifier`/`_sha256`/canonical-JSON digest helpers, all re-implemented
locally — this module does not import from or get imported by
`state_migration.py`, deliberately, so it stays a pure isolated proposal).

Deliberate scope limits, matching v1's "no code activated" discipline:

- **Not imported anywhere else.** No live module references this file.
- **`state_migration.py` is untouched.** Its own `StateRootIdentity` class
  (shipped, host-bound, hard-enforced) is not modified. This module's
  `StateRootIdentity` is a separate, parallel class showing what an
  `installation_id` field would look like, exactly per instruction: *"NICHT
  direkt verändern ... sondern das NEUE entity_identity.py-Modul als
  Ergänzung/Vorschlag daneben bauen."*
- **`INTEGRATION_HYPOTHESES.md` untouched** — same collision-avoidance as v1,
  that file belongs to the parallel HostIdentity-Kandidat-A work package.
- **`state_digest / root metadata`** (§3's slash notation) is implemented as
  one concrete field, `state_digest_sha256`, a sha256 hex digest — a single
  concrete choice standing in for "root metadata" in general, matching the
  rest of the codebase's existing digest conventions
  (`observed_root_fingerprint_sha256`, `state_sha256`).

## 5. EntityIdentity — minimal, per Gabriel's explicit floor

Directive: *"EntityIdentity JETZT NUR MINIMAL bauen: immutable UUID/128-256bit
random ID + Erzeugungsbeleg + UnifiedDB-Persistenz + KEINE Semantik
hineinpacken."* Implemented exactly to that floor:

- `EntityIdentity` dataclass: **only** `entity_id` (+ the module's standard
  `schema` tag) — no name, no description, no purpose field. Verified by a
  test asserting `set(identity.as_dict().keys()) == {"schema", "entity_id"}`.
- `generate_entity_identity()`: `secrets.token_hex(n)`, `n` in `[16, 32]`
  bytes (128–256 bit, the directive's stated floor and ceiling), called
  exactly once per entity.
- **Erzeugungsbeleg** (creation evidence — timestamp, mechanism) is kept in a
  *separate* companion dataclass, `EntityIdentityGenesisRecord`
  (`created_at`, `generated_by`, `entropy_bytes`), not inside
  `EntityIdentity` itself — so the identity dataclass matches §3's bare
  schema exactly, while the evidence the directive also asked for still
  exists as an exportable, serializable record (`as_dict()`/`from_dict()`).
- **"UnifiedDB-Persistenz" stand-in this round:** no live DB write path is
  wired (that would be activation, out of scope). Instead,
  `tests/test_entity_identity.py::EntityIdentityPersistenceSimulationTests`
  proves the id is stable under an actual save/reload cycle — generate once,
  serialize to JSON, write to a temp file, read it back into a fresh
  `EntityIdentityGenesisRecord`, assert `entity_id`/`created_at`/`sha256()`
  are byte-identical to the original, and that reloading twice more stays
  idempotent. This is the concrete evidence for "physischer Speicherort darf
  wechseln, die ID selbst bleibt" without touching a real database.

## 6. `HostBinding` and `RuntimeEpoch` — the two layers whose shape actually
changed from v1

`HostBinding` carries `status` (`ACTIVE` / `SUPERSEDED` / `REVOKED`) and
`bound_at`. Ending a binding does not mutate it (frozen dataclass) — it
mints a new record via `.superseded()`/`.revoked()`, the same discipline
`state_migration.py` already uses for state roots (a migration produces a
*new* root, it does not mutate the old one). A host swap is modeled as: old
`HostBinding` → `.superseded()`, new `HostBinding` → fresh record, both
referencing the *same* `installation_id` — exactly directive point 3's
"rebind, don't refound."

`RuntimeEpoch` has no `session_id` field — directive point 2, deliberately.
`.terminated(reason=...)` closes an epoch out (new record, `termination_reason`
set); `.next_epoch(...)` mints the successor with `predecessor_epoch_id`
pointing back, carrying `state_root_id`/`installation_id`/`host_id` forward
by default (overridable, for the case where a `HostBinding` rebind happened
between epochs). A three-epoch crash/reentry chain
(`test_three_epoch_chain_with_crash_reentry_stays_visible`) proves the crash
stays visible on the epoch that ended, never smoothed away.

## 7. Gabriel's example tree, reproduced as a passing test

```
ENTITY E1
 └─ INSTALLATION I1
     ├─ HOST H1   [bis 2026-09-10]
     └─ HOST H2   [ab 2026-09-10]
         └─ STATE ROOT S7
             ├─ RUNTIME R81
             ├─ RUNTIME R82  crash/reentry
             └─ RUNTIME R83
```

`tests/test_entity_identity.py::GabrielExampleTreeTests::test_tree_relationships_hold`
builds exactly this tree (genesis → `EntityIdentity` → `InstallationIdentity`
→ `HostBinding` H1 superseded, H2 active → `StateRootIdentity` S7 under I1
(not under either host) → `RuntimeEpoch` chain R81→R82→R83 under S7/H2) and
asserts:

- `E1 == E1`: the `entity_id` referenced by `InstallationIdentity` is exactly
  the one the genesis record minted — no drift across the tree build.
- `I1 == I1`: the same `installation_id` is referenced by both host
  bindings, the state root, and all three runtime epochs — stable while
  `H1`/`H2` and `R81`/`R82`/`R83` change underneath it. This is the concrete
  proof-by-test of the whole point of the five-layer split: host and runtime
  churn, entity and installation don't.
- `StateRootIdentity` has no `host_id` attribute at all (`hasattr(s7,
  "host_id")` is `False`) — the directive-point-1 "not hard-bound to host"
  claim is a structural fact of the schema, not just documentation.
- The crash on R81 is visible (`termination_reason == "crash/reentry"`),
  R82/R83 chain back via `predecessor_epoch_id`, none of the three lose
  their `state_root_id`/`installation_id`/`host_id` context.

## 8. Test results

`PYTHONPATH=src python3 -m pytest tests/test_entity_identity.py -v`: **29/29
PASS.** Full existing suite re-run alongside it (minus a baseline set of
pre-existing, pre-dating, unrelated collection errors present on `origin/main`
before this work package touched anything — package-relative imports in a
handful of `tests/test_wp9*`/`test_restart_recovery_*` files that fail when
`tests/` is collected as a package, confirmed present at commit `c5f956c`,
long before this round): 1994 passed, 22 pre-existing failures/3 pre-existing
errors, none of them in `test_entity_identity.py` or referencing
`entity_identity` at all — this work package changes nothing about that
baseline in either direction.

## 9. What was explicitly NOT done in this work package

- No code imported into, or wired against, any live module —
  `entity_identity.py` stands alone, matching v1's own "not wired" discipline
  one level further.
- `state_migration.py`'s shipped `StateRootIdentity` was not modified.
- `INTEGRATION_HYPOTHESES.md` was not opened.
- No `UnifiedDB` row was created — the persistence claim is demonstrated via
  a save/reload simulation (§5), not a live database write.
- No pointer promotion. No activation. No canonicalization proposal beyond
  what's written here as a design/test artifact.
- `~/frankenstein-repo` (the live, actively-hooked checkout) was never read
  or written.
