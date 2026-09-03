# Entity identity layering — architecture design doc (not a decision, not an implementation)

Paket: `paket-1788425080890-0739e4`. Ordered by Gabriel, verbatim quote (see
`self-integration` blog for the German original and full context):

> "`host_identity_sha256` ist noch kein endgültiger Identitätsvertrag. [...] Die
> langfristige Identität sollte eher zusammengesetzt sein: Entity identity ≠ Host
> identity, sondern ungefähr: EntityIdentity → persistente Entity-ID.
> InstallationIdentity → konkrete Installation. HostIdentity → physischer/
> virtueller Rechner. StateRootIdentity → kanonischer Zustandsroot. RuntimeEpoch
> → konkreter Start/Reentry."

This document is a **design doc, not a decision, not an implementation**. No code is
activated, no schema is wired, no `INTEGRATION_HYPOTHESES.md` verdict is touched
(that file is being edited in parallel by a different work package,
`paket-1788424844685-d37b51`, implementing Candidate A from
`HOST_IDENTITY_PROPOSAL_20260903.md` as tested code — deliberately not touched here
to avoid collision). Final choices among any options sketched below remain
Gabriel's/the owner's, exactly as `HOST_IDENTITY_PROPOSAL_20260903.md` and every
prior F2-WP-1207 round already established as house discipline.

**Relationship to `HOST_IDENTITY_PROPOSAL_20260903.md`:** that document proposed a
concrete scheme for exactly one of the five layers below (HostIdentity, §3). Its
Candidate A recommendation stays valid and is *reused unmodified* here — this
document does not re-litigate it, only places it correctly inside the larger model
Gabriel asked for.

---

## 0. Why five layers, not one — the structural problem being solved

Every identity concept that exists in the codebase today (`host_identity_sha256` in
v2's `state_migration.py`, the DB-pointer file in v1's `stern.py`, the ephemeral
`CLAUDE_CODE_SESSION_ID`) answers a **different question**, but nothing currently
names or separates those questions. Collapsing them into one field (as
`host_identity_sha256` currently risks doing by name alone, even though its actual
enforced semantics — §3 below — are narrower and correct) produces two concrete
failure modes:

1. **Under-distinction**: treating "this machine" and "this installation" and "this
   entity" as the same fact makes a legitimate host swap (Gabriel's own example)
   structurally indistinguishable from a full identity loss — there would be no way
   to say "same entity, new host" without inventing a new field anyway, later, under
   pressure, probably worse-designed than doing it now.
2. **Over-distinction risk in the other direction**: inventing five *unrelated*
   identifiers with no defined containment/lifetime relationship between them would
   make every future migration/comparison ambiguous ("which of these five must
   match for state to be trusted?"). The point of this document is the
   **relationships**, not just the five names.

The five layers below are ordered from longest-lived (rarely changes, survives
almost everything) to shortest-lived (changes on every process start). Each section
gives: what question the layer answers, what currently exists (if anything) that is
already doing part of this job, a rough formation rule (illustrative only, no final
schema — that is explicitly out of scope, matching `HOST_IDENTITY_PROPOSAL_20260903.md`
§7's own "reference sketch, not wired" discipline), and its relationship to
neighboring layers.

---

## 1. EntityIdentity — "which entity is this, across everything"

**Question it answers:** is the thing running right now *the same Clay/Frankenstein/
EntityOS entity* as the thing that ran yesterday on a different machine, after a
reinstall, after a host migration — the identity a human would still call "it" even
if every other fact about the deployment changed?

**What exists today: nothing.** Checked in the fresh v1 clone
(`gschaidergabriel/frankenstein`, not `~/frankenstein-repo` — same safety discipline
as every prior round): `USER_ID` is a hardcoded literal `"gabriel"` (`stern.py` line
92, identifies the *human owner*, not the entity), there is no `entity_id`/
`clay_id`/similar column anywhere in `star_konfig` or any table `stern.py`
references, and v2's `state_migration.py` has no field above `StateRootIdentity` at
all — its highest-level object is the root, not anything entity-scoped. This is a
genuine gap, not an oversight to be blamed on either codebase: neither v1 nor v2 was
ever asked "can the same entity outlive its current host" before Gabriel's
directive that produced this work package.

**Lifetime / stability:** the longest-lived of all five layers by design. Should
survive: host migration, OS reinstall, DB recreation from backup, model
substitution (H14 already established that swapping the foundation model — Opus ↔
GLM — does not change "which entity" is running), and ordinary restarts/reentry
trivially. Should **not** survive a deliberate, explicit refounding — Gabriel's own
phrasing ("EntityIdentity ... alles außer vielleicht eine bewusste, explizite
Neugründung" was implicit in the framing of the directive) implies this is the one
layer that is meant to be *consciously* mutable, unlike the others which mutate as
a side effect of infrastructure events. A refounding is a decision, not a detected
fact — nothing in the system should ever infer "this must be a new entity" from
observed data (host change, DB loss, etc.) the way it currently infers "new host"
from a changed `machine-id`.

**Rough formation rule (illustrative, not final):** minted exactly once, at a
genesis event, as an opaque random identifier (structurally analogous to
`StateLineage.lineage_id` in v2, but one conceptual level above it — a lineage
already tracks state generations *within* one entity's life; `EntityIdentity` would
be the thing that could, in principle, span multiple lineages if a state root is
ever fully rebuilt from scratch under the same entity). The hard part is *where it
lives*: by definition it cannot live only inside any single Host's or Installation's
local storage, or a host swap would strand it exactly where it's supposed to
survive. Two non-exclusive placement strategies, neither decided here:
  - **Carried in version control** — committed as a literal value (or an
    encrypted/salted reference to one) in the entity's own source tree, so every
    `git clone` onto a new host/installation brings it along automatically, the same
    way this repository's own git history is what makes "the same project" provable
    across machines today.
  - **Carried explicitly on every migration** as a mandatory copy-forward field,
    the same discipline `state_migration.py` already applies to
    `lineage_id`/`state_sha256` (never regenerated by the migration planner, only
    ever validated for equality) — extended one layer up.

**Relationships:**
  - **To InstallationIdentity:** one EntityIdentity can have many
    InstallationIdentities over its life (Gabriel's example: v1 on ai-core-node vs.
    v1 on andreas-MACO) — but see §2's open question on whether today's v1 actually
    supports that claim yet, or only aspires to.
  - **To all layers below:** EntityIdentity is the only layer that does not derive
    from or bind to any Host/StateRoot/RuntimeEpoch fact. Every other layer answers
    "where/when", EntityIdentity alone answers "who".

---

## 2. InstallationIdentity — "which concrete deployment of that entity is this"

**Question it answers:** distinguishes "v1 running on ai-core-node" from "v1
running on andreas-MACO" even if (per Gabriel's model) both are meant to be the
*same* EntityIdentity — this is the layer that would let two installations
legitimately disagree (different local config, different in-flight state) while
still provably belonging to one entity.

**What exists today, partially:** v1's own `stern.py` comment (line ~7568, already
surfaced in `HOST_IDENTITY_PROPOSAL_20260903.md` §2) states the current model
explicitly: *"Instanz-lokal per Definition: jede Maschine hat ihre eigene
unified.db/eigenes sprache_default"* — today, one machine implicitly equals one
installation equals one DB, with no separate InstallationIdentity concept because
nothing has ever needed to distinguish "installation" from "host" before. The
closest existing scaffolding is the **DB-pointer file**,
`_db_zeiger_pfad()`/`~/.config/agentzero/db_pfad.txt` (`stern.py` lines 103-166): a
small file living *outside* `unified.db` itself, per-machine (via `XDG_CONFIG_HOME`),
that records where this machine's real DB currently lives. It is not an identity —
it carries no ID, only a path — but it already occupies the right conceptual slot
(a small, DB-external, per-machine marker of "this installation's" canonical
location) that an `installation_id` file could extend or sit beside.
`_db_pfad_aufloesen()`'s own four-stage resolution order (pointer → env var → XDG
target → legacy fallback → fresh-install target) is also exactly the kind of logic
an InstallationIdentity bootstrap would need to hook into: "is this a fresh
installation or an existing one" is a question v1 already answers today, just not
by minting an ID when it does.

**Lifetime / stability:** should survive process restarts, reentry, and DB
migrations *within* the same installation trivially. Whether it survives an OS
reinstall on the *same* physical host, or a state-root relocation to a *new* host
(state migrated, EntityIdentity carried forward, but is it "the same installation
that moved" or "a new installation that inherited the old one's state"?), is an
**open question this document deliberately does not resolve** — both readings are
internally consistent, and the choice has real consequences for how
`state_migration.py`'s host-identity invariant (§3 below) should be read once a
migration crosses hosts (out of scope for v2's generation-1 module today, but not
necessarily forever). Ends, by design, on a genuine uninstall — v1 already has a
real, working two-step confirmation flow for exactly this
(`deinstallation_anbieten()`/`deinstallation_bestaetigen()`, `stern.py` lines
~12799-12892) which is the natural place an InstallationIdentity's *end* would be
recorded, even though today it records only a confirmation flag per session, not an
identity retirement.

**Rough formation rule (illustrative):** minted once per genuinely fresh
installation (i.e. exactly at the point `_db_pfad_aufloesen()`'s stage-4
"echte Frischinstallation" branch fires and a new empty DB is created), stored
alongside the existing DB-pointer file or inside `star_konfig` itself, and required
to carry an explicit `entity_id` foreign-key-style field pointing back to §1 — so
the relationship between "this installation" and "the entity it belongs to" is a
provable link, not just filesystem proximity (two installations on two hosts should
be *checkable* as belonging to one entity, not merely assumed to).

**Relationships:**
  - **To EntityIdentity:** many InstallationIdentities per EntityIdentity, in
    principle — today's actual v1 has never had more than one real installation
    running against a shared `unified.db` at a time, so this is aspirational
    structure, not yet observed behavior (worth flagging honestly rather than
    implying it already works).
  - **To HostIdentity:** an installation runs on exactly one host *at a time*, but
    is not permanently bound to it the way §3 shows `state_migration.py`
    permanently binding a `StateRootIdentity` to one `host_identity_sha256` —
    InstallationIdentity is the layer where a host move would need to be an
    explicit, recorded rebind rather than a structural impossibility.
  - **To StateRootIdentity:** an installation owns (in the common case) exactly one
    canonical durable state root at a time — see §4.

---

## 3. HostIdentity — "which physical/virtual machine this is"

**Question it answers:** the narrowest of the five — a pure machine-level fact,
deliberately unaware of entity or installation. Already substantially specified by
`HOST_IDENTITY_PROPOSAL_20260903.md`; this section's job is only to place that
proposal correctly inside the five-layer model, not to redo it.

**What already exists — the concrete proposal (Candidate A, unchanged):** a salted
local `/etc/machine-id`, `sha256(pepper:raw_machine_id)` wrapped in a second sha256
with a schema-tagged payload, pepper stored locally (Tresor or `star_konfig`, owner
call, unresolved in the original proposal and still unresolved here). Full
rationale — GRID10 shape-consistency, deliberate non-re-derivability deviation,
privacy analysis, rejected Candidates B/C — is in
`HOST_IDENTITY_PROPOSAL_20260903.md` and not reproduced here; that document remains
the authority on HostIdentity's internal scheme.

**What this layering clarifies that the original proposal, scoped narrowly to "just
the host field," could not:** `host_identity_sha256` as currently named and coded in
`state_migration.py` binds **only** machine identity — it structurally cannot and
should not be asked to also stand in for InstallationIdentity or EntityIdentity, even
though today, with no other layer implemented, it is the *only* identity field that
exists near the state-migration boundary and could be mistaken for doing more work
than it does. Concretely:
  - `host_identity_sha256` changing (real OS reinstall without machine-id
    preservation) legitimately means "new host" — it says nothing about whether the
    entity or even the installation changed. Under Gabriel's model, an
    InstallationIdentity *could* survive this if a deliberate host-rebind is
    recorded (§2); `host_identity_sha256` alone cannot express that, nor should it
    be extended to try.
  - `host_identity_sha256` staying the same across two DBs on one machine
    (hypothetically, two separate installations sharing a host) would **not** imply
    those installations are the same entity — HostIdentity is orthogonal to, not a
    proxy for, EntityIdentity. v1's current one-DB-per-machine model has never
    exercised this case, so it is untested territory, not a contradiction of
    anything observed.

**Lifetime / stability:** survives reboots, most OS updates (systemd's own
`/etc/machine-id` guarantee, already documented in the source proposal). Does not
survive a fresh OS install unless the file is explicitly preserved/restored — this
is treated as *correct* behavior, not a bug, in the original proposal, and that
verdict is unchanged here.

**Relationships:**
  - **To StateRootIdentity:** this is the one relationship already **hard-enforced
    in shipped v2 code today**, not speculative — `StateMigrationRequest.__post_init__`
    (lines 418-421) raises `StateMigrationError` if
    `target.host_identity_sha256 != source.root.host_identity_sha256`. Generation-1
    migration plans are therefore structurally same-host-only by construction. See
    §4 for what this means once InstallationIdentity/EntityIdentity exist alongside
    it.
  - **To InstallationIdentity/EntityIdentity:** deliberately no relationship encoded
    — a host can carry any number of installations of any number of entities; none
    of that is HostIdentity's concern.

---

## 4. StateRootIdentity — "which canonical durable-storage root this is"

**Question it answers:** already a real, shipped, tested v2 concept
(`src/frankenstein2/state_migration.py`, `FRANKENSTEIN2_STATE_ROOT_IDENTITY/v1`,
frozen dataclass with `root_id`, `path`, `storage_class`,
`host_identity_sha256`, `observed_root_fingerprint_sha256`) — this section maps it
into the five-layer model rather than re-describing it.

**Is it a child of HostIdentity+InstallationIdentity, or independent?** Gabriel's
question, addressed directly: **child of both, but only one relationship is
currently enforced in code.**
  - **Child of HostIdentity — enforced today.** As shown in §3, source and target
    roots in any migration request must share the exact same `host_identity_sha256`
    (hard error otherwise). A `StateRootIdentity` cannot exist, as far as the code's
    own invariants are concerned, independent of a specific host.
  - **Child of InstallationIdentity — implied by design, not yet expressed as a
    field.** `StateRootIdentity` has no `installation_id` field at all today. In
    the current one-installation-per-host reality this is invisible (host and
    installation happen to coincide 1:1), but under Gabriel's model — multiple
    installations of one entity across hosts, or in principle multiple
    installations *on* one host — a root's ownership by a specific installation
    would need its own explicit field to stay provable rather than assumed. This is
    a genuine gap for whoever eventually wires InstallationIdentity for real, flagged
    here, not fixed here (no schema change proposed or implemented in this
    document).
  - **Grandchild of EntityIdentity, transitively.** Not directly bound at all today
    — `StateRootIdentity` has no notion of "entity" whatsoever. Its only path back
    to an entity would run through whatever InstallationIdentity eventually owns it.

**Lifetime / stability:** a `StateRootIdentity` is deliberately narrower-lived than
Host or Installation — `root_id`/`path`/`storage_class` describe *one specific
canonical storage location*, and `build_state_migration_plan()`'s entire purpose is
producing a new `StateRootIdentity` (new path, same or new storage class) while
carrying the *lineage* (not the root identity itself) forward via
`StateLineage.lineage_id`/`state_sha256`. In other words: **the root changes on
every migration by design; the lineage is what's meant to persist across root
changes.** This is already the correct shape for a "Kind"/child relationship — a
root is disposable infrastructure the module intentionally lets go stale
(`RETAIN_SOURCE_AS_ROLLBACK` keeps the *old* root only transiently, as a rollback
target, not as ongoing canonical truth).

**Relationships:**
  - **To HostIdentity:** hard 1:1-at-a-time binding, enforced in shipped code (§3).
  - **To InstallationIdentity:** implied 1:1-at-a-time ownership, not yet an
    explicit field — flagged gap, not proposed fix.
  - **To EntityIdentity:** no direct relationship; reachable only transitively
    through InstallationIdentity once that layer exists.
  - **To RuntimeEpoch:** a single StateRootIdentity persists across many
    RuntimeEpochs (many process starts read/write the same canonical root between
    migrations) — see §5.

---

## 5. RuntimeEpoch — "which concrete start/reentry this is"

**Question it answers:** the shortest-lived of the five — one running process's (or
one witness-covered subject-plus-relaunch-chain's) lifetime, from start to
termination or handoff to the next epoch.

**What already exists, partially, in two places:**
  - **v1's `session_id`** (`CLAUDE_CODE_SESSION_ID` env var) is already, by v1's
    own documented behavior (surfaced in `HOST_IDENTITY_PROPOSAL_20260903.md` §2,
    unchanged observation reused here), *"nur pro Sitzung stabil"* — per-session,
    not host-stable. That is exactly a RuntimeEpoch-shaped fact already present in
    the running system, just not named or schematized as one. `claude --resume
    <session_id>` (referenced directly in Phase 13/POSTREENTRY-20260901 evidence,
    `INTEGRATION_HYPOTHESES.md` H4/H7 rows) is the existing mechanism for
    *deliberately* continuing one RuntimeEpoch's conversational context across a
    process boundary — worth noting this already blurs "one epoch" vs. "one
    process": a `--resume` reentry is a new OS process but arguably the same
    RuntimeEpoch from the *witness*'s point of view, and a different one from the
    *OS process table*'s point of view. This document does not resolve which
    reading should be canonical — flagged as an open decision, same discipline as
    §2's host-migration ambiguity.
  - **`witness_v3.py`'s own event shape** (WITNESSFIX-20260903 evidence,
    `workpackages/evidence_inbox/F2-WP-1207/witness_detach_fix/WITNESSFIX-20260903/`)
    is, today, already producing exactly the data a RuntimeEpoch record would need —
    it just isn't named that yet: `target_died: true`, `waited_s`, `status`,
    `relaunched_pid`, `relaunch_ms`. Each of those fields describes the boundary
    between one epoch ending (the watched PID dying) and the next beginning (the
    new PID from relaunch). `daemonize()`'s own double-fork+`setsid` self-detach
    (run as the *first* thing in `main()`, before any target/kill/relaunch logic)
    is itself a RuntimeEpoch-boundary operation for the *witness process's own*
    epoch — it deliberately severs the witness's epoch from its launcher's
    process-group/session so that the launcher's epoch ending (real SIGTERM to the
    whole group, per the manual live-teardown test in the same evidence set) does
    not end the witness's epoch too.

**Lifetime / stability:** the only layer of the five that is expected to end and
begin routinely, many times per day, without that being noteworthy in itself — a
restart, a `--resume`, an auto-relaunch after crash, are all ordinary RuntimeEpoch
transitions. What *is* noteworthy (and already the subject of H4/H7/POSTREENTRY
evidence) is whether state/behavior stays continuous *across* a RuntimeEpoch
boundary — which is a claim about the layers *above* RuntimeEpoch (StateRoot,
Installation, Entity) being unaffected by the boundary, not a claim about
RuntimeEpoch itself changing.

**Rough formation rule (illustrative):** minted at process start (or, for a
witness-covered subject, at the moment `witness_v3.py` begins watching it), holding
at minimum `{pid, session_id_if_any, started_at, predecessor_epoch_id_if_relaunch}`
— the last field is what would let a chain of witness-mediated relaunches be
reconstructed as one continuous *supervision* history even while each individual
epoch is short. Ends at process death, explicit `--resume` into a fresh process
(new epoch, same conversational session per v1's existing model), or a clean
shutdown.

**Relationships:**
  - **To StateRootIdentity:** many RuntimeEpochs read/write one StateRootIdentity
    between migrations — a process restarting does not, by itself, imply the
    canonical root changed (and per H4/POSTREENTRY-20260901 evidence, verifiably
    does not, in every run measured so far).
  - **To InstallationIdentity/HostIdentity:** a RuntimeEpoch exists on exactly one
    Host, within exactly one Installation, for its entire (short) life — it cannot
    outlive either.
  - **To EntityIdentity:** no direct relationship — reachable only transitively,
    same as StateRootIdentity.

---

## 6. Hierarchy overview

Containment/duration, longest-lived to shortest-lived. "⊇" reads as "conceptually
contains/outlives, in the common case" — not all edges are enforced in code today;
enforced edges are marked explicitly.

```
EntityIdentity                (years; survives everything except deliberate refounding)
  │  1 : N  (aspirational — v1 has never run >1 installation of itself)
  ▼
InstallationIdentity          (installation lifetime; survives restarts, migrations,
  │                            possibly host moves — open question, §2)
  │  1 : 1-at-a-time, NOT enforced in code today (gap, §4)
  ▼
StateRootIdentity              (per-canonical-root; changes on every migration by
  │                            design — the LINEAGE persists across root changes,
  │                            not the root identity itself)
  │  many RuntimeEpochs read/write one root between migrations
  ▼
RuntimeEpoch                   (single process/witness-supervised-chain lifetime;
                               shortest-lived, changes routinely, many times/day)

HostIdentity                   (machine lifetime; ORTHOGONAL to the chain above —
                               does not contain or get contained by Entity/
                               Installation; referenced by StateRootIdentity via a
                               hard, ENFORCED-IN-CODE field, host_identity_sha256)
```

**Why HostIdentity sits outside the main chain:** every other layer is drawn from
the entity's own point of view (its identity, its installations, its storage, its
running moments). HostIdentity is drawn from the machine's point of view, and one
host can carry installations belonging to unrelated entities (as this very VPS
already does for two unrelated tenants — SeiMensch/`agentforge` and this research
entity/`claylab`, per `~/seimensch-redesign/CLAUDE.md`'s own documented two-tenant
warning, an independently-arrived-at example of exactly the same
host-is-not-entity principle this document argues for at the architecture level).
`StateRootIdentity` is the one place the two hierarchies are required, by shipped
code, to touch.

| Layer | Survives reboot | Survives process restart/reentry | Survives OS reinstall (same physical host) | Survives migration to a *new* host | Survives deliberate uninstall+reinstall | Survives deliberate refounding |
|---|---|---|---|---|---|---|
| EntityIdentity | yes | yes | yes | **yes (the whole point)** | open — depends whether reinstall is read as same-installation-restored or new-installation-of-same-entity | **no — by design, this is the one intentional reset** |
| InstallationIdentity | yes | yes | open question (§2) | open question (§2) | no (uninstall ends it; `deinstallation_*` flow in `stern.py` is the closest existing mechanism) | no (entity reset implies its installations are re-derived) |
| HostIdentity | yes | yes | no (new machine-id unless explicitly preserved) | n/a — HostIdentity by definition changes when the host changes | n/a — orthogonal to install/uninstall | n/a — orthogonal to entity |
| StateRootIdentity | yes | yes | no (bound to HostIdentity, §3/§4) | no (bound to HostIdentity; a cross-host migration would need a *new* root by construction) | no | no |
| RuntimeEpoch | no (new epoch on every boot) | no (that IS the boundary) | no | no | no | no |

---

## 7. Open questions this document deliberately leaves open

Consistent with `HOST_IDENTITY_PROPOSAL_20260903.md`'s own discipline (§6: "This is
a recommendation, not a decision") — the following are surfaced, not resolved, and
none of them are needed to be resolved for this document to be useful as a map:

1. Does a state-root migration that crosses hosts (out of scope for
   `state_migration.py` generation 1 today) end an InstallationIdentity and start a
   new one bound to the new host, or rebind the same InstallationIdentity to a new
   HostIdentity? (§2, §3)
2. Does a witness-mediated auto-relaunch (WITNESSFIX-20260903) count as the *same*
   RuntimeEpoch continuing under supervision, or a new RuntimeEpoch chained to its
   predecessor? (§5)
3. Where, concretely, should EntityIdentity be stored so it survives a host it has
   never touched yet (the genuinely hard part of §1) — version-controlled literal,
   explicit copy-forward-only field, or something else entirely?
4. Should `StateRootIdentity` gain an explicit `installation_id` field (§4's
   flagged gap), and if so, is that a v2 schema change (new dataclass field,
   backward-incompatible for `FRANKENSTEIN2_STATE_ROOT_IDENTITY/v1`) or a new
   schema version?

None of these are answered here. This document's job was mapping the five layers
Gabriel named and their relationships — not making the calls that belong to the
owner.

---

## 8. What was explicitly NOT done in this work package

- No code written, activated, imported, or tested.
- No `unified.db` row, `star_konfig` key, or Tresor entry created.
- `INTEGRATION_HYPOTHESES.md` was not opened, read for editing, or touched — that
  file belongs to the parallel work package (`paket-1788424844685-d37b51`)
  implementing Candidate A as tested code.
- `~/frankenstein-repo` (the live, actively-hooked checkout) was never read or
  written — all v1 research in this document reuses the fresh clone at
  `/tmp/frankenstein-v1-fresh-hostid` (`gschaidergabriel/frankenstein`, commit
  `a92a2f0`), the same clone `HOST_IDENTITY_PROPOSAL_20260903.md` used, confirmed
  still present and untouched by this work package (read-only `grep`/`Read` only,
  no `git` mutation).
- No pointer promotion, no canonicalization proposal, no claim of acceptance.
