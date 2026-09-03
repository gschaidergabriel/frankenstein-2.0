"""F2-WP-1207 Schritt 2: installation-aware, host-rebind-eligible migration
request -- ADDITIVE and PARALLEL to `state_migration.py`'s live
`StateMigrationRequest`, which is left completely untouched (its hard
"source and target roots must bind the same explicit host identity" check
still fires exactly as before -- see `tests/test_state_migration.py::
StateMigrationTests::test_wrong_host_identity_rejected`, still green,
unmodified).

Gabriel's directive, verbatim: "same installation + valid HostBinding
transition -> Migration/Rebind erlaubt" instead of "different host ->
grundsaetzlich verboten".

This module does NOT relax the check by loosening
`StateMigrationRequest` itself. Loosening a fail-closed identity check
in place, for every existing caller, on the strength of one work package's
say-so would be exactly the kind of silent authority-widening this
codebase's other modules (`state_migration.py`'s own docstring: "It does
not ... authorize effects") explicitly refuse to do. Instead:

    StateMigrationRequest         (state_migration.py, UNCHANGED)
        host_identity_sha256 mismatch -> unconditional StateMigrationError.
        This remains the DEFAULT, fail-closed path.

    RebindEligibleMigrationRequest (this module, NEW, opt-in)
        host_identity_sha256 mismatch is tolerated ONLY IF:
          1. both source.root.installation_id and target.installation_id
             are set and IDENTICAL (the "same installation" half), AND
          2. a caller-supplied `entity_identity.HostBinding` is ACTIVE and
             its installation_id matches that same installation_id (the
             "valid HostBinding transition" half) -- i.e. there is a live,
             attested, non-superseded/non-revoked binding vouching for the
             new host on behalf of that installation.
        Every OTHER check (canonical-root eligibility, target != source,
        rollback == source, digest fences, target prestate) is byte-identical
        to `StateMigrationRequest`, reusing `state_migration.py`'s own
        validators via `validate_target_prestate()` and the private
        `_revalidate_*` helpers -- this is not a looser twin, it is the same
        request with exactly one check swapped for a stricter-in-a-different-
        dimension one (installation+binding proof instead of raw host
        equality).

Still plan-only: this module does not touch a filesystem, execute a
migration, or authorize any effect -- same classification discipline as
`state_migration.py`'s `StateMigrationPlan.classification`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from frankenstein2.entity_identity import BINDING_STATUS_ACTIVE, HostBinding
from frankenstein2.state_migration import (
    StateLineage,
    StateMigrationError,
    StateRootIdentity,
    TargetRootObservation,
    _digest,
    _identifier,
    _revalidate_lineage,
    _revalidate_root,
    _revalidate_target_observation,
    validate_target_prestate,
)

REBIND_REQUEST_SCHEMA = "FRANKENSTEIN2_STATE_MIGRATION_REBIND_REQUEST/v1"


class StateRebindError(StateMigrationError):
    """Fail-closed rebind-eligibility error. Subclasses StateMigrationError
    so a caller that only catches the base class still catches this -- but
    is a distinct type so a caller can tell "ordinary migration validation
    failure" apart from "rebind eligibility specifically was not proven"."""


def _revalidate_binding(value: Any) -> HostBinding:
    if type(value) is not HostBinding:
        raise StateRebindError("host_binding must be exact entity_identity.HostBinding")
    return HostBinding(
        schema=value.schema,
        binding_id=value.binding_id,
        installation_id=value.installation_id,
        host_id=value.host_id,
        bound_at=value.bound_at,
        attestation=value.attestation,
        status=value.status,
    )


def assert_rebind_eligible(
    *,
    source_root: StateRootIdentity,
    target_root: StateRootIdentity,
    host_binding: HostBinding,
) -> None:
    """The core new rule, isolated as its own assertable function so it can
    be unit-tested independent of the full request dataclass below, and so
    `RebindEligibleMigrationRequest.__post_init__` and any future caller
    share exactly one implementation of "same installation + valid
    HostBinding transition"."""
    if source_root.installation_id is None or target_root.installation_id is None:
        raise StateRebindError(
            "rebind path requires installation_id set on BOTH source and target roots "
            "(host_identity_sha256 alone is not sufficient evidence for a rebind)"
        )
    if source_root.installation_id != target_root.installation_id:
        raise StateRebindError(
            "rebind path requires source and target roots to share the SAME "
            "installation_id -- a different installation_id is a genuine "
            "different-lineage-owner case, not a host rebind"
        )
    if host_binding.installation_id != target_root.installation_id:
        raise StateRebindError(
            "host_binding.installation_id does not match target_root.installation_id "
            "-- the binding does not vouch for this installation"
        )
    if host_binding.status != BINDING_STATUS_ACTIVE:
        raise StateRebindError(
            f"host_binding must be ACTIVE to authorize a rebind, got {host_binding.status!r}"
        )
    # Deliberately NOT checking host_identity_sha256 equality here -- tolerating
    # that mismatch, under the three conditions above, is the entire point of
    # this code path. A real host_identity_sha256 CHANGE across the rebind is
    # expected and fine; what must NOT change is the installation_id, and what
    # must be true is that a currently-ACTIVE HostBinding attests to the swap.


@dataclass(frozen=True, slots=True)
class RebindEligibleMigrationRequest:
    schema: str
    migration_id: str
    source_lineage: StateLineage
    target_root: StateRootIdentity
    target_observation: TargetRootObservation
    rollback_root: StateRootIdentity
    host_binding: HostBinding
    expected_source_lineage_sha256: str
    expected_source_root_sha256: str
    expected_target_root_sha256: str
    expected_rollback_root_sha256: str

    def __post_init__(self) -> None:
        if self.schema != REBIND_REQUEST_SCHEMA:
            raise StateRebindError("rebind request schema mismatch")
        object.__setattr__(
            self, "migration_id", _identifier("migration_id", self.migration_id)
        )

        source = _revalidate_lineage(self.source_lineage)
        target = _revalidate_root(self.target_root, role="target root")
        rollback = _revalidate_root(self.rollback_root, role="rollback root")
        observation = _revalidate_target_observation(self.target_observation)
        binding = _revalidate_binding(self.host_binding)

        # Identical eligibility/law checks to StateMigrationRequest -- the
        # canonical-durable / not-transient / ONE_CANONICAL_STATE_LINEAGE law
        # is NOT part of what this module relaxes.
        source.root.assert_eligible_canonical_root(role="source root")
        target.assert_eligible_canonical_root(role="target root")
        rollback.assert_eligible_canonical_root(role="rollback root")

        if target.sha256() == source.root.sha256():
            raise StateRebindError("target root must differ from source root")
        if rollback.sha256() != source.root.sha256():
            raise StateRebindError(
                "generation-1 plan requires rollback_root to be the exact source root"
            )

        # THE relaxed check -- replaces StateMigrationRequest's unconditional
        # host_identity_sha256 equality with the installation+binding proof.
        assert_rebind_eligible(
            source_root=source.root, target_root=target, host_binding=binding
        )

        object.__setattr__(self, "source_lineage", source)
        object.__setattr__(self, "target_root", target)
        object.__setattr__(self, "rollback_root", rollback)
        object.__setattr__(self, "target_observation", observation)
        object.__setattr__(self, "host_binding", binding)

        expected_source_lineage = self.expected_source_lineage_sha256
        expected_source_root = self.expected_source_root_sha256
        expected_target_root = self.expected_target_root_sha256
        expected_rollback_root = self.expected_rollback_root_sha256

        if expected_source_lineage != source.sha256():
            raise StateRebindError("source lineage digest fence mismatch")
        if expected_source_root != source.root.sha256():
            raise StateRebindError("source root digest fence mismatch")
        if expected_target_root != target.sha256():
            raise StateRebindError("target root digest fence mismatch")
        if expected_rollback_root != rollback.sha256():
            raise StateRebindError("rollback root digest fence mismatch")

        validate_target_prestate(self.target_observation, self.source_lineage)

    @classmethod
    def create(
        cls,
        *,
        migration_id: str,
        source_lineage: StateLineage,
        target_root: StateRootIdentity,
        target_observation: TargetRootObservation,
        rollback_root: StateRootIdentity,
        host_binding: HostBinding,
    ) -> "RebindEligibleMigrationRequest":
        source = _revalidate_lineage(source_lineage)
        target = _revalidate_root(target_root, role="target root")
        rollback = _revalidate_root(rollback_root, role="rollback root")
        return cls(
            schema=REBIND_REQUEST_SCHEMA,
            migration_id=migration_id,
            source_lineage=source,
            target_root=target,
            target_observation=_revalidate_target_observation(target_observation),
            rollback_root=rollback,
            host_binding=host_binding,
            expected_source_lineage_sha256=source.sha256(),
            expected_source_root_sha256=source.root.sha256(),
            expected_target_root_sha256=target.sha256(),
            expected_rollback_root_sha256=rollback.sha256(),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "migration_id": self.migration_id,
            "source_lineage": self.source_lineage.as_dict(),
            "target_root": self.target_root.as_dict(),
            "target_observation": self.target_observation.as_dict(),
            "rollback_root": self.rollback_root.as_dict(),
            "host_binding": asdict(self.host_binding),
            "expected_source_lineage_sha256": self.expected_source_lineage_sha256,
            "expected_source_root_sha256": self.expected_source_root_sha256,
            "expected_target_root_sha256": self.expected_target_root_sha256,
            "expected_rollback_root_sha256": self.expected_rollback_root_sha256,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())
