"""Five-layer entity/installation/host/state-root/runtime-epoch identity model.

F2-WP-1207. Isolated, tested proposal module. NOT imported by, wired into, or
activated against any live module (`state_migration.py`, `stern.py`,
`witness_v3.py`, ...). No `UnifiedDB` write path exists here beyond the
in-memory JSON round-trip demonstrated by the tests -- "UnifiedDB-Persistenz"
per the directive means "provably stable under save/reload", not a live DB
integration in this round.

Design doc (v2, precise, this module's contract): see
`workpackages/evidence_inbox/F2-WP-1207/self_integration/ENTITY_IDENTITY_LAYERING_20260903.md`.
That document's v1 sketched the five layers and left four questions open.
Gabriel's follow-up directive (2026-09-03) answers all four; this module is
the resulting minimal, tested schema -- not an activation of it.

Gabriel's directive, verbatim (paraphrase-free extraction, see design doc v2
history section for full quote):

    1. StateRootIdentity is NOT hard-bound to HostIdentity. It belongs
       primarily to InstallationIdentity. The current host is a BINDING/
       ATTESTATION (HostBinding), not the identity itself -- HostBinding
       replaces HostIdentity as the parent-facing concept in this schema.
    2. RuntimeEpoch is defined by a CONTINUOUS runtime lifecycle, not by a
       session id -- a session id is evidence of continuity, not the
       definition of an epoch.
    3. Rechnerwechsel (host swap) = rebind of the SAME InstallationIdentity
       (a new HostBinding row). A new InstallationIdentity is minted only on
       a deliberate rebuild/clone/fork -- never inferred from an observed
       host change.
    4. A witness_v3 restart is always a NEW RuntimeEpoch (same StateRoot /
       Installation / Entity, new execution segment) -- a crash/reentry must
       stay visible in the epoch chain, never be smoothed over as one
       continuous runtime.
    5. EntityIdentity lives in the canonical persistent state (UnifiedDB),
       never in a plugin cache, never in `/etc/machine-id`, never in a model
       prompt: a once-minted immutable id plus an exportable recovery/
       bootstrap record. The physical storage location may change; the id
       itself does not.
    6. StateRootIdentity needs an `installation_id` field -- called out by
       Gabriel as "the most important next schema fix".

Exact target schema (field names verbatim from the directive):

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

Every dataclass here also carries a `schema` tag, matching the convention
already established in `state_migration.py` (`FRANKENSTEIN2_STATE_ROOT_IDENTITY/v1`
etc.) -- a version tag, not semantics; it does not violate directive point 5's
"no semantics" instruction for EntityIdentity, which is otherwise a bare
`entity_id`.

EntityIdentity is deliberately minimal per directive point 5: no name, no
description, no purpose field, nothing that could be read as "what the
entity is" -- only "which one it is". Creation evidence (timestamp, mechanism)
is intentionally kept OUT of the `EntityIdentity` dataclass itself (which
must match the bare `entity_id` schema above exactly) and lives instead in a
companion `EntityIdentityGenesisRecord`, produced once by
`generate_entity_identity()` alongside the identity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import re
import secrets
from typing import Any

ENTITY_IDENTITY_SCHEMA = "FRANKENSTEIN2_ENTITY_IDENTITY/v1"
ENTITY_IDENTITY_GENESIS_SCHEMA = "FRANKENSTEIN2_ENTITY_IDENTITY_GENESIS/v1"
INSTALLATION_IDENTITY_SCHEMA = "FRANKENSTEIN2_INSTALLATION_IDENTITY/v1"
STATE_ROOT_IDENTITY_SCHEMA = "FRANKENSTEIN2_ENTITY_STATE_ROOT_IDENTITY/v1"
HOST_BINDING_SCHEMA = "FRANKENSTEIN2_HOST_BINDING/v1"
RUNTIME_EPOCH_SCHEMA = "FRANKENSTEIN2_RUNTIME_EPOCH/v1"

# HostBinding.status -- exactly one HostBinding per installation should be
# ACTIVE at a time in the illustrative model; SUPERSEDED/REVOKED are terminal.
# Not enforced across instances here (this module has no registry/store) --
# only validated per-instance. Cross-instance invariants ("only one ACTIVE
# binding per installation_id") belong to whatever eventually persists these
# rows, matching the same discipline `state_migration.py` uses (it validates
# one migration request at a time, not a whole fleet).
BINDING_STATUS_ACTIVE = "ACTIVE"
BINDING_STATUS_SUPERSEDED = "SUPERSEDED"
BINDING_STATUS_REVOKED = "REVOKED"
_ALLOWED_BINDING_STATUSES = frozenset(
    {BINDING_STATUS_ACTIVE, BINDING_STATUS_SUPERSEDED, BINDING_STATUS_REVOKED}
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_FREEFORM_LEN = 4096
_MIN_ENTITY_ID_ENTROPY_BYTES = 16  # 128 bit, directive's stated floor
_MAX_ENTITY_ID_ENTROPY_BYTES = 32  # 256 bit, directive's stated ceiling


class EntityIdentityError(ValueError):
    """Fail-closed entity-identity-layer validation error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise EntityIdentityError(f"{name} must be a string")
    if not value or value != value.strip():
        raise EntityIdentityError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise EntityIdentityError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise EntityIdentityError(f"{name} contains control characters")
    return value


def _optional_identifier(name: str, value: Any) -> str | None:
    if value is None:
        return None
    return _identifier(name, value)


def _freeform(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise EntityIdentityError(f"{name} must be a string")
    if not value or value != value.strip():
        raise EntityIdentityError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_FREEFORM_LEN:
        raise EntityIdentityError(f"{name} exceeds {_MAX_FREEFORM_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value if ch != "\n"):
        raise EntityIdentityError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise EntityIdentityError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _hex_token(name: str, value: Any, *, min_bytes: int, max_bytes: int) -> str:
    if not isinstance(value, str):
        raise EntityIdentityError(f"{name} must be a string")
    lowered = value.lower()
    if lowered != value:
        raise EntityIdentityError(f"{name} must already be lowercase hex")
    if len(value) % 2 != 0 or re.fullmatch(r"[0-9a-f]+", value) is None:
        raise EntityIdentityError(f"{name} must be a hex string")
    nbytes = len(value) // 2
    if not (min_bytes <= nbytes <= max_bytes):
        raise EntityIdentityError(
            f"{name} must encode between {min_bytes} and {max_bytes} bytes "
            f"({min_bytes * 2}-{max_bytes * 2} hex chars), got {nbytes} bytes"
        )
    return value


def _rfc3339_utc(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise EntityIdentityError(f"{name} must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EntityIdentityError(f"{name} must be a valid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(None):
        raise EntityIdentityError(f"{name} must be an explicit UTC timestamp (+00:00 or Z)")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Layer 1: EntityIdentity -- "which entity is this, across everything"
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EntityIdentity:
    """Bare, minimal entity identity. Deliberately no name/description/purpose
    field -- directive point 5, "KEINE Semantik hineinpacken". The ONLY thing
    this dataclass claims is "which entity this is", matching the directive's
    exact schema (`entity_id` alone, plus the module's standard `schema` tag).
    """

    schema: str
    entity_id: str

    def __post_init__(self) -> None:
        if self.schema != ENTITY_IDENTITY_SCHEMA:
            raise EntityIdentityError("entity identity schema mismatch")
        object.__setattr__(
            self,
            "entity_id",
            _hex_token(
                "entity_id",
                self.entity_id,
                min_bytes=_MIN_ENTITY_ID_ENTROPY_BYTES,
                max_bytes=_MAX_ENTITY_ID_ENTROPY_BYTES,
            ),
        )

    @classmethod
    def create(cls, *, entity_id: str) -> "EntityIdentity":
        return cls(schema=ENTITY_IDENTITY_SCHEMA, entity_id=entity_id)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class EntityIdentityGenesisRecord:
    """Erzeugungsbeleg (creation evidence) for one EntityIdentity: timestamp
    plus how/where it was generated. Kept separate from `EntityIdentity`
    itself so the identity dataclass stays exactly the bare schema the
    directive specifies. This record is what "einmalig erzeugte
    unveraenderliche ID + exportierbares Recovery/Bootstrap-Metadatum" means
    in code: it is the exportable bootstrap metadatum.
    """

    schema: str
    entity_id: str
    created_at: str
    generated_by: str
    entropy_bytes: int

    def __post_init__(self) -> None:
        if self.schema != ENTITY_IDENTITY_GENESIS_SCHEMA:
            raise EntityIdentityError("entity identity genesis schema mismatch")
        object.__setattr__(
            self,
            "entity_id",
            _hex_token(
                "entity_id",
                self.entity_id,
                min_bytes=_MIN_ENTITY_ID_ENTROPY_BYTES,
                max_bytes=_MAX_ENTITY_ID_ENTROPY_BYTES,
            ),
        )
        object.__setattr__(self, "created_at", _rfc3339_utc("created_at", self.created_at))
        object.__setattr__(self, "generated_by", _freeform("generated_by", self.generated_by))
        if type(self.entropy_bytes) is not int or not (
            _MIN_ENTITY_ID_ENTROPY_BYTES <= self.entropy_bytes <= _MAX_ENTITY_ID_ENTROPY_BYTES
        ):
            raise EntityIdentityError(
                "entropy_bytes must be an int in "
                f"[{_MIN_ENTITY_ID_ENTROPY_BYTES}, {_MAX_ENTITY_ID_ENTROPY_BYTES}]"
            )

    def identity(self) -> EntityIdentity:
        return EntityIdentity.create(entity_id=self.entity_id)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntityIdentityGenesisRecord":
        if type(data) is not dict:
            raise EntityIdentityError("genesis record payload must be a dict")
        try:
            return cls(
                schema=data["schema"],
                entity_id=data["entity_id"],
                created_at=data["created_at"],
                generated_by=data["generated_by"],
                entropy_bytes=data["entropy_bytes"],
            )
        except KeyError as exc:
            raise EntityIdentityError(f"genesis record missing field: {exc}") from exc


def generate_entity_identity(
    *,
    entropy_bytes: int = 16,
    generated_by: str = "frankenstein2.entity_identity.generate_entity_identity",
    now: str | None = None,
) -> EntityIdentityGenesisRecord:
    """Mint a new EntityIdentity exactly once, with its Erzeugungsbeleg.

    `entropy_bytes` defaults to 16 (128 bit), the directive's stated floor;
    callers may raise it up to 32 (256 bit, the stated ceiling). Uses
    `secrets.token_hex`, matching the directive verbatim ("secrets.token_hex
    (16-32) oder UUID"). This function does not persist anything -- callers
    decide where the resulting `EntityIdentityGenesisRecord` is stored
    (UnifiedDB row, exported bootstrap file, ...); see
    `tests/test_entity_identity.py` for a save/reload simulation proving the
    resulting id is stable under that round trip.
    """
    if not (_MIN_ENTITY_ID_ENTROPY_BYTES <= entropy_bytes <= _MAX_ENTITY_ID_ENTROPY_BYTES):
        raise EntityIdentityError(
            "entropy_bytes must be in "
            f"[{_MIN_ENTITY_ID_ENTROPY_BYTES}, {_MAX_ENTITY_ID_ENTROPY_BYTES}]"
        )
    entity_id = secrets.token_hex(entropy_bytes)
    return EntityIdentityGenesisRecord(
        schema=ENTITY_IDENTITY_GENESIS_SCHEMA,
        entity_id=entity_id,
        created_at=now if now is not None else _utc_now_rfc3339(),
        generated_by=generated_by,
        entropy_bytes=entropy_bytes,
    )


# ---------------------------------------------------------------------------
# Layer 2: InstallationIdentity -- "which concrete deployment of that entity"
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InstallationIdentity:
    schema: str
    installation_id: str
    entity_id: str

    def __post_init__(self) -> None:
        if self.schema != INSTALLATION_IDENTITY_SCHEMA:
            raise EntityIdentityError("installation identity schema mismatch")
        object.__setattr__(
            self, "installation_id", _identifier("installation_id", self.installation_id)
        )
        object.__setattr__(
            self,
            "entity_id",
            _hex_token(
                "entity_id",
                self.entity_id,
                min_bytes=_MIN_ENTITY_ID_ENTROPY_BYTES,
                max_bytes=_MAX_ENTITY_ID_ENTROPY_BYTES,
            ),
        )

    @classmethod
    def create(cls, *, installation_id: str, entity_id: str) -> "InstallationIdentity":
        return cls(
            schema=INSTALLATION_IDENTITY_SCHEMA,
            installation_id=installation_id,
            entity_id=entity_id,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


# ---------------------------------------------------------------------------
# Layer 3: StateRootIdentity -- "which canonical durable-storage root, scoped
# to an INSTALLATION, not a host" -- directive point 1 + point 6.
#
# Note: this is a deliberately separate, parallel dataclass from
# `state_migration.py`'s own `StateRootIdentity` (which is shipped, live,
# host-bound v2 code and is NOT touched by this work package). This module's
# `StateRootIdentity` is the "what would an installation_id field look like"
# proposal the directive asked for, kept out of the live class entirely.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StateRootIdentity:
    """Directive point 6: "StateRootIdentity braucht ein installation_id-Feld
    -- der wichtigste naechste Schema-Fix." This is that field, proposed in
    isolation. `state_digest_sha256` stands in for the schema block's
    "state_digest / root metadata" line -- a single concrete sha256 digest of
    whatever root metadata a real implementation would define; kept generic
    on purpose (no path/storage_class/etc. re-litigated here, that remains
    `state_migration.py`'s live concern).
    """

    schema: str
    state_root_id: str
    installation_id: str
    state_digest_sha256: str

    def __post_init__(self) -> None:
        if self.schema != STATE_ROOT_IDENTITY_SCHEMA:
            raise EntityIdentityError("state root identity schema mismatch")
        object.__setattr__(self, "state_root_id", _identifier("state_root_id", self.state_root_id))
        object.__setattr__(
            self, "installation_id", _identifier("installation_id", self.installation_id)
        )
        object.__setattr__(
            self, "state_digest_sha256", _sha256("state_digest_sha256", self.state_digest_sha256)
        )

    @classmethod
    def create(
        cls, *, state_root_id: str, installation_id: str, state_digest_sha256: str
    ) -> "StateRootIdentity":
        return cls(
            schema=STATE_ROOT_IDENTITY_SCHEMA,
            state_root_id=state_root_id,
            installation_id=installation_id,
            state_digest_sha256=state_digest_sha256,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


# ---------------------------------------------------------------------------
# Layer 4: HostBinding -- "attestation that an installation currently runs on
# a host" -- directive point 1 replaces HostIdentity-as-parent with this.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HostBinding:
    schema: str
    installation_id: str
    host_id: str
    bound_at: str
    attestation: str
    status: str

    def __post_init__(self) -> None:
        if self.schema != HOST_BINDING_SCHEMA:
            raise EntityIdentityError("host binding schema mismatch")
        object.__setattr__(
            self, "installation_id", _identifier("installation_id", self.installation_id)
        )
        object.__setattr__(self, "host_id", _identifier("host_id", self.host_id))
        object.__setattr__(self, "bound_at", _rfc3339_utc("bound_at", self.bound_at))
        object.__setattr__(self, "attestation", _freeform("attestation", self.attestation))
        if self.status not in _ALLOWED_BINDING_STATUSES:
            raise EntityIdentityError(f"unsupported host binding status: {self.status!r}")

    @classmethod
    def create(
        cls,
        *,
        installation_id: str,
        host_id: str,
        bound_at: str,
        attestation: str,
        status: str = BINDING_STATUS_ACTIVE,
    ) -> "HostBinding":
        return cls(
            schema=HOST_BINDING_SCHEMA,
            installation_id=installation_id,
            host_id=host_id,
            bound_at=bound_at,
            attestation=attestation,
            status=status,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def superseded(self) -> "HostBinding":
        """Return a new record with status=SUPERSEDED. Frozen dataclass, so
        "ending" a binding means minting a new terminal record -- the same
        discipline `RuntimeEpoch.termination_reason` uses below, not an
        in-place mutation (there is nothing to mutate; these are values, not
        rows in a store yet).
        """
        return replace(self, status=BINDING_STATUS_SUPERSEDED)

    def revoked(self) -> "HostBinding":
        return replace(self, status=BINDING_STATUS_REVOKED)


# ---------------------------------------------------------------------------
# Layer 5: RuntimeEpoch -- "which concrete continuous runtime lifecycle" --
# directive point 2: defined by the lifecycle, session id is evidence only
# (no session_id field here at all -- deliberately; a caller wanting to
# record session-id-as-evidence can put it in `termination_reason`-adjacent
# out-of-band evidence/log, not in this identity schema, matching directive
# point 2's "Session-ID ist nur Evidenz, nicht die Definition").
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RuntimeEpoch:
    schema: str
    runtime_epoch_id: str
    state_root_id: str
    installation_id: str
    host_id: str
    started_at: str
    predecessor_epoch_id: str | None
    termination_reason: str | None

    def __post_init__(self) -> None:
        if self.schema != RUNTIME_EPOCH_SCHEMA:
            raise EntityIdentityError("runtime epoch schema mismatch")
        object.__setattr__(
            self, "runtime_epoch_id", _identifier("runtime_epoch_id", self.runtime_epoch_id)
        )
        object.__setattr__(self, "state_root_id", _identifier("state_root_id", self.state_root_id))
        object.__setattr__(
            self, "installation_id", _identifier("installation_id", self.installation_id)
        )
        object.__setattr__(self, "host_id", _identifier("host_id", self.host_id))
        object.__setattr__(self, "started_at", _rfc3339_utc("started_at", self.started_at))
        object.__setattr__(
            self,
            "predecessor_epoch_id",
            _optional_identifier("predecessor_epoch_id", self.predecessor_epoch_id),
        )
        if self.predecessor_epoch_id == self.runtime_epoch_id:
            raise EntityIdentityError("runtime epoch cannot be its own predecessor")
        object.__setattr__(
            self,
            "termination_reason",
            None if self.termination_reason is None else _freeform(
                "termination_reason", self.termination_reason
            ),
        )

    @classmethod
    def create(
        cls,
        *,
        runtime_epoch_id: str,
        state_root_id: str,
        installation_id: str,
        host_id: str,
        started_at: str,
        predecessor_epoch_id: str | None = None,
        termination_reason: str | None = None,
    ) -> "RuntimeEpoch":
        return cls(
            schema=RUNTIME_EPOCH_SCHEMA,
            runtime_epoch_id=runtime_epoch_id,
            state_root_id=state_root_id,
            installation_id=installation_id,
            host_id=host_id,
            started_at=started_at,
            predecessor_epoch_id=predecessor_epoch_id,
            termination_reason=termination_reason,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def terminated(self, *, reason: str) -> "RuntimeEpoch":
        """Return a new record with `termination_reason` set. Directive
        point 4: a witness_v3 restart is always a NEW epoch -- this method
        only closes out the OLD one; the caller mints a fresh `RuntimeEpoch`
        for the new segment with `predecessor_epoch_id=self.runtime_epoch_id`,
        it does not extend this one.
        """
        return replace(self, termination_reason=reason)

    def next_epoch(
        self,
        *,
        runtime_epoch_id: str,
        started_at: str,
        state_root_id: str | None = None,
        installation_id: str | None = None,
        host_id: str | None = None,
    ) -> "RuntimeEpoch":
        """Convenience constructor for the successor epoch in a chain, per
        directive point 4 -- carries state_root_id/installation_id/host_id
        forward by default (the common "same everything, new execution
        segment" case) but lets a caller override any of them (e.g. a
        HostBinding rebind happened between epochs).
        """
        return RuntimeEpoch.create(
            runtime_epoch_id=runtime_epoch_id,
            state_root_id=state_root_id if state_root_id is not None else self.state_root_id,
            installation_id=(
                installation_id if installation_id is not None else self.installation_id
            ),
            host_id=host_id if host_id is not None else self.host_id,
            started_at=started_at,
            predecessor_epoch_id=self.runtime_epoch_id,
            termination_reason=None,
        )
