# `host_identity_sha256` real scheme — design proposal (not a decision)

Paket: `paket-1788424194135-8f29c3`. Auftrag: "start mit 1" von Gabriels
Sieben-Punkte-Liste offener Owner-Entscheidungen (F2-WP-1207 self-integration).
Punkt 1 = ein echtes `host_identity_sha256`-Schema. **Dieses Dokument ist ein
Vorschlag, keine Entscheidung, keine Aktivierung.**

## 1. Was der Code strukturell erwartet (v2, `state_migration.py`)

`StateRootIdentity.host_identity_sha256` (module
`src/frankenstein2/state_migration.py`, schema `FRANKENSTEIN2_STATE_ROOT_IDENTITY/v1`):

- **Format**: lowercase 64-hex string, enforced by `_sha256()` — a SHA-256 hex
  digest, nothing more specific validated (no schema-tagged payload required
  by the type system itself, unlike e.g. `StateLineage.state_sha256` which is
  paired with an explicit `generation`/`lineage_id`).
- **Semantics enforced by `StateMigrationRequest.__post_init__`**: line
  418-421 — `target.host_identity_sha256 != source.root.host_identity_sha256`
  is a hard `StateMigrationError`. **Source and target root must bind the
  exact same host identity.** Generation-1 migration plans structurally only
  support same-host migrations (e.g. moving canonical state between paths/
  storage classes on one machine) — cross-host migration is out of scope for
  this module as written, which is the single strongest structural clue for
  what "host" is supposed to mean: an OS/machine-level identity, not a
  per-DB-lineage or per-process one (those are already covered separately by
  `lineage_id`/`generation`/`state_sha256`).
- **No derivation logic exists in v2.** The dataclass only validates the
  *shape* of whatever the caller supplies. Every real derivation decision is
  explicitly out of scope for v2 and deferred to the caller/owner — confirmed
  by `local_iter2_autonomous_discovery.py`'s own "HOST IDENTITY NOTE"
  docstring and every prior round's non-claim (see `INTEGRATION_HYPOTHESES.md`
  Part 4/5, unchanged since F-ITER1 until this proposal).

## 2. What already exists in v1 (fresh clone, `gschaidergabriel/frankenstein`
   commit `a92a2f0`, NOT `~/frankenstein-repo`)

- **`unified.db` is explicitly per-machine by design.** `scripts/stern.py`
  comment at the `sprache_default`-Override (line ~7568): *"Instanz-lokal per
  Definition: jede Maschine hat ihre eigene unified.db/eigenes
  sprache_default"* — the codebase's own stated model is one DB per physical
  machine, not a DB that migrates or is shared across hosts as a matter of
  course.
- **No existing host/instance-identity concept anywhere in v1.** Checked:
  `USER_ID` is a hardcoded literal `"gabriel"` (line 92) — not host-derived.
  `session_id` (`CLAUDE_CODE_SESSION_ID` env var) is per Claude-Code-session,
  ephemeral, not host-stable. No `machine_id`/`instanz_id`/`host_id` column or
  config key exists in `star_konfig` or any other table referenced in
  `stern.py`.
- **`db_pfad_zeigen()` / `db-pfad-zeigen`** (line 12595) is the existing
  read-only DB-path resolver F-ITER2/local-iter2 already use to discover the
  real `unified.db` path without trusting a caller-supplied path. Any real
  `host_identity_sha256` derivation that touches v1 state would naturally live
  near this function, reusing the same resolved `DB_PATH`.
- **Two storage tiers exist for config/secrets**: plain `star_konfig`
  (comment near line 269: *"dauerhaft im Klartext in unified.db -- unabhaengig
  vom Tresor (PHASE 18)"*) vs. the PHASE 18 Tresor (vault) for actual secrets.
  This matters for where a pepper/seed for host identity should live (§3).

## 3. GRID10 / existing v2 sha256-accounting pattern — consistency or
   deliberate deviation?

Every existing sha256-identity field in `frankenstein2` (`object_sha256`,
`boot_id_sha256`, `exact_source_sha256`, `binding_sha256`, GRID10 cell
digests, `StateRootIdentity.sha256()` itself) follows one pattern:
`hashlib.sha256(canonical_json(value).encode()).hexdigest()` where `value` is
a **fully known, non-secret, schema-tagged dict** — anyone holding the same
inputs can independently recompute the same digest. That's the point: these
digests are meant to be *externally re-derivable* for verification.

`host_identity_sha256` cannot honestly follow that pattern if it is meant to
resist being reverse-engineered from a leaked/committed hash (see §5,
Privacy) — a bare `sha256(machine_id)` is independently recomputable by
anyone who also has (or can enumerate) the raw `machine_id`. Candidate A
below therefore **deliberately deviates**: it hashes a *secret* (a
locally-generated pepper) together with the raw local value, matching the
canonical-JSON/sha256-hex *shape* of every other digest in the codebase, but
not its "anyone can recompute" transparency property — the input is
partially secret by design, same category as the PHASE 18 Tresor already
existing for exactly this purpose in v1.

## 4. Candidates

### Candidate A — salted local machine identity (recommended)

```
pepper_hex      = 64 random hex chars, generated once, stored ONLY in v1
                  Tresor (PHASE 18 vault) or star_konfig if Tresor is judged
                  overkill for a non-authentication secret -- owner call
raw_local_id    = /etc/machine-id contents, stripped (fallback: a fixed
                  literal like today's test-scoped stand-in, if the file is
                  absent -- e.g. containers)
payload         = {"schema": "FRANKENSTEIN_HOST_IDENTITY/v1",
                    "salted_value": sha256(f"{pepper_hex}:{raw_local_id}").hexdigest()}
host_identity_sha256 = sha256(canonical_json(payload)).hexdigest()
```

- **Stability**: `/etc/machine-id` survives reboots and most updates by
  design (systemd guarantee). Survives OS *reinstall* only if explicitly
  preserved/restored — a fresh install normally gets a fresh machine-id,
  which would (correctly, arguably) look like a "new host" to
  `state_migration.py`.
- **Collision safety**: machine-id is itself designed to be globally unique
  (128-bit random, systemd-generated). Salting doesn't reduce uniqueness.
- **Privacy**: the raw hash is never exposed — only `sha256(pepper:raw)`
  wrapped in a second sha256. Without the pepper (host-local, never
  committed), a leaked `host_identity_sha256` cannot be reversed to the raw
  `machine-id`, and cannot even be correlated to *other* hosts' hashes by an
  outsider (unlike an unsalted hash, which anyone could brute-force against
  the small, guessable machine-id keyspace... note machine-id is NOT
  guessable in practice — 122 bits of entropy — so this is a defense-in-depth
  argument, not one against a plausible practical attack).
- **GRID10 consistency**: shape-consistent (canonical_json + sha256 hex,
  schema-tagged payload), deliberately deviates on re-derivability (§3) —
  necessary, not accidental.
- **Migration path**: every existing test-scoped `/etc/machine-id`-stand-in
  value in prior evidence files (`local_iter2_autonomous_discovery.py`,
  `LOCAL-ITER2-...-report.json`, GRID10-compat-check, the `9`*64 literal in
  `tests/test_state_migration.py`) is explicitly labeled non-canonical
  already — nothing needs migrating, they simply get superseded once/if this
  scheme is adopted and wired for real.

### Candidate B — random DB-scoped instance token

```
token_hex  = secrets.token_hex(32), generated ONCE at first real use,
             stored in unified.db star_konfig (key e.g. host_identity_token,
             or Tresor)
payload    = {"schema": "FRANKENSTEIN_HOST_IDENTITY/v1", "token": token_hex}
host_identity_sha256 = sha256(canonical_json(payload)).hexdigest()
```

- **Stability**: tied to the *DB lineage*, not the OS/machine. Survives OS
  reinstall as long as `unified.db` (or a backup of it) is restored;
  correctly changes identity if the DB is deleted and recreated from empty
  — which is a defensible reading of "new lineage" but a *different* concept
  from "same host", and overlaps with what `lineage_id`/`state_sha256`
  already track.
- **Collision safety**: 256-bit random, effectively zero collision risk,
  independent of any external namespace.
- **Privacy**: strictly better than A — pure random bytes, zero encoded
  hardware/OS information, nothing to reverse even in principle.
- **GRID10 consistency**: same shape, same non-re-derivability deviation as A.
- **Structural fit concern**: `state_migration.py`'s own invariant (source
  and target root must share `host_identity_sha256`) reads as an OS/host-level
  guarantee ("don't silently write across hosts"), not a DB-lineage guarantee
  (that's `lineage_id`). Using B here risks conflating two concepts the module
  already keeps separate elsewhere.
- **Migration path**: same as A — nothing to migrate, current values are all
  explicitly test-scoped placeholders.

### Candidate C — multi-factor OS/hardware composite (not recommended)

```
payload = {"schema": "FRANKENSTEIN_HOST_IDENTITY/v1",
           "hostname": socket.gethostname(),
           "machine_id_sha256": sha256(machine_id),
           "primary_mac_sha256": sha256(first non-loopback NIC MAC)}
host_identity_sha256 = sha256(canonical_json(payload)).hexdigest()
```

- **Stability**: worse than A or B — hostname and NIC/MAC both change more
  often than `/etc/machine-id` (renamed machines, USB/Wi-Fi adapter swaps,
  VMs re-provisioning virtual NICs, containers with ephemeral hostnames).
- **Collision safety**: fine in practice, but no better than A for the extra
  complexity.
- **Privacy**: **worse** — `hostname` is frequently human-chosen and
  identifying (e.g. a literal machine nickname), and this candidate hashes
  each factor separately then combines, which is more surface for accidental
  leakage of one factor if any intermediate value is ever logged unsalted by
  a future, less careful caller.
- **Verdict**: listed for completeness, not carried forward. More brittle,
  more privacy surface, no real advantage over A for this codebase's actual
  need (a stable per-migration-operation host guard, not a rich hardware
  inventory).

## 5. Privacy analysis (applies across candidates, only fields actually
   proposed to enter evidence files — which get committed to a **public**
   GitHub repo, `self-integration` and `frankenstein-2.0` both)

Only the final `host_identity_sha256` (a 64-hex digest) is ever meant to
appear in any evidence JSON/report/log. Under A or B, that digest alone
cannot be reversed to raw `machine-id`, hostname, or any other host fact
without also possessing the locally-stored, never-committed pepper/token.
Under C, `hostname` is a human-readable field that could itself be identifying
even before hashing, and if a future caller ever mistakenly logs the
intermediate per-factor dict, exposure is worse than A/B's flat digest. This
is the core reason C is not recommended even though it looks fine solely on
uniqueness. Independent of which candidate is chosen: the pepper/token itself
must NEVER be written to any evidence file, log, or committed report — only
the final digest.

## 6. Recommendation

**Candidate A (salted local machine identity)**, because it is the most
literal structural match for what `state_migration.py`'s own code already
enforces (same-host invariant across source/target roots — an OS/machine-level
guarantee, not a DB-lineage one), while still meeting the privacy bar via
salting. Candidate B is a legitimate, arguably-safer-on-privacy alternative
but tracks a different concept (DB lineage, already separately covered) and
would need the module's own comments/docstring updated to stop calling it
"host" identity if chosen instead. Candidate C is not recommended.

**This is a recommendation, not a decision.** Final choice among A/B/C (or
something else entirely) is Gabriel's/the owner's, per every prior round's
explicit non-invention discipline on this exact point.

## 7. Reference sketch (illustrative only — NOT wired, NOT imported anywhere,
   NOT activated, NOT tested against a live system; matches the default-OFF
   pattern of the 2026-09-03 wiring proposal)

```python
# ILLUSTRATIVE ONLY -- not part of any module, not imported, not tested.
# Candidate A, sketched for v1's stern.py (near db_pfad_zeigen()).

import hashlib
import json
import secrets
from pathlib import Path


def _canonical_json(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _host_identity_pepper_hex() -> str:
    """Read-or-create a 64-hex-char local pepper. Placement (star_konfig vs.
    Tresor) is an open implementation question, not decided here -- sketch
    uses star_konfig for illustration only."""
    existing = _konfig_dyn_get("host_identity_pepper_hex", "")
    if existing:
        return existing
    pepper = secrets.token_hex(32)
    _konfig_dyn_set("host_identity_pepper_hex", pepper, quelle="host_identity_bootstrap")
    return pepper


def host_identity_sha256_candidate_a() -> str:
    machine_id_path = Path("/etc/machine-id")
    raw_local_id = machine_id_path.read_text().strip() if machine_id_path.is_file() else "no-machine-id-fallback"
    pepper_hex = _host_identity_pepper_hex()
    salted = hashlib.sha256(f"{pepper_hex}:{raw_local_id}".encode()).hexdigest()
    payload = {"schema": "FRANKENSTEIN_HOST_IDENTITY/v1", "salted_value": salted}
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()
```

No caller in this proposal invokes `host_identity_sha256_candidate_a()`
against a real host. No pepper is generated by this round. No `unified.db`
row (real or test) exists for this anywhere yet.
