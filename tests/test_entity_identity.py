from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import tempfile
import unittest
from pathlib import Path

from frankenstein2.entity_identity import (
    BINDING_STATUS_ACTIVE,
    BINDING_STATUS_SUPERSEDED,
    ENTITY_IDENTITY_GENESIS_SCHEMA,
    ENTITY_IDENTITY_SCHEMA,
    HOST_BINDING_SCHEMA,
    INSTALLATION_IDENTITY_SCHEMA,
    RUNTIME_EPOCH_SCHEMA,
    STATE_ROOT_IDENTITY_SCHEMA,
    EntityIdentity,
    EntityIdentityError,
    EntityIdentityGenesisRecord,
    HostBinding,
    InstallationIdentity,
    RuntimeEpoch,
    StateRootIdentity,
    generate_entity_identity,
)


class EntityIdentityGenerationTests(unittest.TestCase):
    """Directive point 5 + build instruction 3: minimal, immutable, stable
    under save/reload."""

    def test_generate_default_128_bit(self) -> None:
        record = generate_entity_identity()
        self.assertEqual(record.schema, ENTITY_IDENTITY_GENESIS_SCHEMA)
        self.assertEqual(record.entropy_bytes, 16)
        self.assertEqual(len(record.entity_id), 32)  # 16 bytes -> 32 hex chars
        int(record.entity_id, 16)  # must be valid hex

    def test_generate_256_bit_ceiling(self) -> None:
        record = generate_entity_identity(entropy_bytes=32)
        self.assertEqual(len(record.entity_id), 64)

    def test_generate_rejects_below_floor_and_above_ceiling(self) -> None:
        with self.assertRaises(EntityIdentityError):
            generate_entity_identity(entropy_bytes=15)
        with self.assertRaises(EntityIdentityError):
            generate_entity_identity(entropy_bytes=33)

    def test_two_generations_are_different_entities(self) -> None:
        a = generate_entity_identity()
        b = generate_entity_identity()
        self.assertNotEqual(a.entity_id, b.entity_id)

    def test_genesis_record_carries_creation_evidence(self) -> None:
        record = generate_entity_identity(
            now="2026-09-03T08:00:00+00:00",
            generated_by="test-harness",
        )
        self.assertEqual(record.created_at, "2026-09-03T08:00:00+00:00")
        self.assertEqual(record.generated_by, "test-harness")

    def test_identity_extracted_from_record_matches_bare_schema(self) -> None:
        record = generate_entity_identity()
        identity = record.identity()
        self.assertIsInstance(identity, EntityIdentity)
        self.assertEqual(identity.schema, ENTITY_IDENTITY_SCHEMA)
        self.assertEqual(identity.entity_id, record.entity_id)
        # bare schema per directive: only entity_id (+ module schema tag)
        self.assertEqual(set(identity.as_dict().keys()), {"schema", "entity_id"})


class EntityIdentityImmutabilityTests(unittest.TestCase):
    def test_entity_identity_is_frozen(self) -> None:
        identity = EntityIdentity.create(entity_id="a" * 32)
        with self.assertRaises(FrozenInstanceError):
            identity.entity_id = "b" * 32  # type: ignore[misc]

    def test_entity_identity_rejects_bad_hex(self) -> None:
        with self.assertRaises(EntityIdentityError):
            EntityIdentity.create(entity_id="not-hex!!")

    def test_entity_identity_rejects_too_short(self) -> None:
        with self.assertRaises(EntityIdentityError):
            EntityIdentity.create(entity_id="ab" * 4)  # 8 bytes, below 16-byte floor

    def test_entity_identity_rejects_uppercase(self) -> None:
        with self.assertRaises(EntityIdentityError):
            EntityIdentity.create(entity_id="A" * 32)


class EntityIdentityPersistenceSimulationTests(unittest.TestCase):
    """Build instruction 3: prove the id is stable under a save/reload cycle
    -- stands in for "UnifiedDB-Persistenz" (physical location may change,
    the id does not) without wiring an actual DB in this isolated round."""

    def test_json_round_trip_via_tmp_file_is_identical(self) -> None:
        original = generate_entity_identity()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "entity_identity_genesis.json"
            path.write_text(json.dumps(original.as_dict()), encoding="utf-8")

            # simulate: process restarts, host changes, storage location
            # changes -- only the exported bootstrap file survives.
            reloaded_raw = json.loads(path.read_text(encoding="utf-8"))
            reloaded = EntityIdentityGenesisRecord.from_dict(reloaded_raw)

        self.assertEqual(reloaded.entity_id, original.entity_id)
        self.assertEqual(reloaded.created_at, original.created_at)
        self.assertEqual(reloaded.generated_by, original.generated_by)
        self.assertEqual(reloaded.sha256(), original.sha256())
        self.assertEqual(reloaded.identity().entity_id, original.identity().entity_id)

    def test_repeated_reload_is_idempotent(self) -> None:
        original = generate_entity_identity()
        payload = json.dumps(original.as_dict())
        first = EntityIdentityGenesisRecord.from_dict(json.loads(payload))
        second = EntityIdentityGenesisRecord.from_dict(json.loads(payload))
        third = EntityIdentityGenesisRecord.from_dict(json.loads(json.dumps(second.as_dict())))
        self.assertEqual(first.entity_id, second.entity_id)
        self.assertEqual(second.entity_id, third.entity_id)
        self.assertEqual(first.sha256(), third.sha256())

    def test_from_dict_rejects_missing_field(self) -> None:
        original = generate_entity_identity()
        incomplete = original.as_dict()
        del incomplete["created_at"]
        with self.assertRaises(EntityIdentityError):
            EntityIdentityGenesisRecord.from_dict(incomplete)


class InstallationIdentityTests(unittest.TestCase):
    def test_links_back_to_entity(self) -> None:
        entity = generate_entity_identity().identity()
        installation = InstallationIdentity.create(
            installation_id="i1-ai-core-node", entity_id=entity.entity_id
        )
        self.assertEqual(installation.schema, INSTALLATION_IDENTITY_SCHEMA)
        self.assertEqual(installation.entity_id, entity.entity_id)

    def test_one_entity_many_installations(self) -> None:
        entity = generate_entity_identity().identity()
        i1 = InstallationIdentity.create(installation_id="i1", entity_id=entity.entity_id)
        i2 = InstallationIdentity.create(installation_id="i2", entity_id=entity.entity_id)
        self.assertNotEqual(i1.installation_id, i2.installation_id)
        self.assertEqual(i1.entity_id, i2.entity_id)  # same entity, per directive

    def test_rejects_empty_entity_id(self) -> None:
        with self.assertRaises(EntityIdentityError):
            InstallationIdentity.create(installation_id="i1", entity_id="")


class StateRootIdentityTests(unittest.TestCase):
    """Directive point 6 -- the field this round exists to add."""

    def test_carries_installation_id(self) -> None:
        root = StateRootIdentity.create(
            state_root_id="s7",
            installation_id="i1",
            state_digest_sha256="a" * 64,
        )
        self.assertEqual(root.schema, STATE_ROOT_IDENTITY_SCHEMA)
        self.assertEqual(root.installation_id, "i1")

    def test_rejects_missing_installation_id(self) -> None:
        with self.assertRaises(EntityIdentityError):
            StateRootIdentity.create(
                state_root_id="s7", installation_id="", state_digest_sha256="a" * 64
            )

    def test_rejects_bad_digest(self) -> None:
        with self.assertRaises(EntityIdentityError):
            StateRootIdentity.create(
                state_root_id="s7", installation_id="i1", state_digest_sha256="not-a-digest"
            )


class HostBindingTests(unittest.TestCase):
    """Directive point 1: HostBinding replaces HostIdentity as the
    parent-facing concept; StateRootIdentity no longer hard-binds to a host."""

    def test_default_status_active(self) -> None:
        binding = HostBinding.create(
            installation_id="i1",
            host_id="h1",
            bound_at="2026-01-01T00:00:00+00:00",
            attestation="sha256:" + "a" * 64,
        )
        self.assertEqual(binding.schema, HOST_BINDING_SCHEMA)
        self.assertEqual(binding.status, BINDING_STATUS_ACTIVE)

    def test_rejects_unknown_status(self) -> None:
        with self.assertRaises(EntityIdentityError):
            HostBinding.create(
                installation_id="i1",
                host_id="h1",
                bound_at="2026-01-01T00:00:00+00:00",
                attestation="x",
                status="MAYBE",
            )

    def test_rejects_naive_timestamp(self) -> None:
        with self.assertRaises(EntityIdentityError):
            HostBinding.create(
                installation_id="i1",
                host_id="h1",
                bound_at="2026-01-01T00:00:00",  # no tz
                attestation="x",
            )

    def test_rebind_same_installation_new_host_is_two_bindings(self) -> None:
        """Directive point 3: a host swap rebinds the SAME installation --
        modeled here as h1 becoming SUPERSEDED and a new ACTIVE h2 binding
        appearing, both referencing installation_id i1."""
        h1 = HostBinding.create(
            installation_id="i1",
            host_id="h1",
            bound_at="2026-08-01T00:00:00+00:00",
            attestation="sha256:" + "1" * 64,
        )
        h1_ended = h1.superseded()
        h2 = HostBinding.create(
            installation_id="i1",
            host_id="h2",
            bound_at="2026-09-10T00:00:00+00:00",
            attestation="sha256:" + "2" * 64,
        )
        self.assertEqual(h1_ended.status, BINDING_STATUS_SUPERSEDED)
        self.assertEqual(h2.status, BINDING_STATUS_ACTIVE)
        # same installation throughout -- this is the "no new InstallationIdentity
        # on a mere host swap" invariant from directive point 3.
        self.assertEqual(h1_ended.installation_id, h2.installation_id)
        self.assertNotEqual(h1_ended.host_id, h2.host_id)
        # original h1 record is untouched (frozen); superseded() returned a copy
        self.assertEqual(h1.status, BINDING_STATUS_ACTIVE)


class RuntimeEpochTests(unittest.TestCase):
    """Directive point 2 + 4: continuous lifecycle, session id is evidence
    only (no session_id field on this dataclass at all); a witness restart is
    always a new epoch, chained via predecessor_epoch_id."""

    def test_first_epoch_has_no_predecessor(self) -> None:
        epoch = RuntimeEpoch.create(
            runtime_epoch_id="r81",
            state_root_id="s7",
            installation_id="i1",
            host_id="h2",
            started_at="2026-09-10T01:00:00+00:00",
        )
        self.assertEqual(epoch.schema, RUNTIME_EPOCH_SCHEMA)
        self.assertIsNone(epoch.predecessor_epoch_id)
        self.assertIsNone(epoch.termination_reason)

    def test_epoch_cannot_be_own_predecessor(self) -> None:
        with self.assertRaises(EntityIdentityError):
            RuntimeEpoch.create(
                runtime_epoch_id="r81",
                state_root_id="s7",
                installation_id="i1",
                host_id="h2",
                started_at="2026-09-10T01:00:00+00:00",
                predecessor_epoch_id="r81",
            )

    def test_terminated_returns_new_record_original_unchanged(self) -> None:
        r81 = RuntimeEpoch.create(
            runtime_epoch_id="r81",
            state_root_id="s7",
            installation_id="i1",
            host_id="h2",
            started_at="2026-09-10T01:00:00+00:00",
        )
        r81_closed = r81.terminated(reason="crash: witness_v3 target died, group SIGTERM")
        self.assertIsNone(r81.termination_reason)
        self.assertEqual(
            r81_closed.termination_reason, "crash: witness_v3 target died, group SIGTERM"
        )
        # closing does not fork identity -- same runtime_epoch_id
        self.assertEqual(r81.runtime_epoch_id, r81_closed.runtime_epoch_id)

    def test_next_epoch_chains_and_carries_context_forward(self) -> None:
        r81 = RuntimeEpoch.create(
            runtime_epoch_id="r81",
            state_root_id="s7",
            installation_id="i1",
            host_id="h2",
            started_at="2026-09-10T01:00:00+00:00",
        ).terminated(reason="witness_v3 detected target death, auto-relaunch")
        r82 = r81.next_epoch(runtime_epoch_id="r82", started_at="2026-09-10T01:00:05+00:00")

        self.assertEqual(r82.predecessor_epoch_id, "r81")
        # directive point 2: same state root / installation / host, new epoch
        self.assertEqual(r82.state_root_id, r81.state_root_id)
        self.assertEqual(r82.installation_id, r81.installation_id)
        self.assertEqual(r82.host_id, r81.host_id)
        self.assertIsNone(r82.termination_reason)  # r82 itself has not ended

    def test_three_epoch_chain_with_crash_reentry_stays_visible(self) -> None:
        """Reproduces Gabriel's R81 -> R82 (crash/reentry) -> R83 example."""
        r81 = RuntimeEpoch.create(
            runtime_epoch_id="r81",
            state_root_id="s7",
            installation_id="i1",
            host_id="h2",
            started_at="2026-09-10T01:00:00+00:00",
        ).terminated(reason="crash/reentry")
        r82 = r81.next_epoch(runtime_epoch_id="r82", started_at="2026-09-10T01:00:05+00:00")
        r83 = r82.next_epoch(runtime_epoch_id="r83", started_at="2026-09-10T02:00:00+00:00")

        chain = [r81, r82, r83]
        self.assertEqual([e.runtime_epoch_id for e in chain], ["r81", "r82", "r83"])
        self.assertEqual(r82.predecessor_epoch_id, r81.runtime_epoch_id)
        self.assertEqual(r83.predecessor_epoch_id, r82.runtime_epoch_id)
        # the crash is visible on r81, not smoothed away
        self.assertEqual(r81.termination_reason, "crash/reentry")
        self.assertIsNone(r82.termination_reason)
        self.assertIsNone(r83.termination_reason)
        # all three share one continuous state-root/installation/host context
        for epoch in chain:
            self.assertEqual(epoch.state_root_id, "s7")
            self.assertEqual(epoch.installation_id, "i1")
            self.assertEqual(epoch.host_id, "h2")


class GabrielExampleTreeTests(unittest.TestCase):
    """End-to-end reproduction of the ASCII tree in Gabriel's directive:

        ENTITY E1
         |- INSTALLATION I1
             |- HOST H1   [bis 2026-09-10]
             |- HOST H2   [ab 2026-09-10]
                 |- STATE ROOT S7
                     |- RUNTIME R81
                     |- RUNTIME R82  crash/reentry
                     |- RUNTIME R83

    Asserts E1==E1 and I1==I1 stay stable across the host swap and the
    runtime-epoch chain -- the whole point of the five-layer split.
    """

    def test_tree_relationships_hold(self) -> None:
        genesis = generate_entity_identity(now="2026-01-01T00:00:00+00:00")
        e1 = genesis.identity()

        i1 = InstallationIdentity.create(installation_id="i1", entity_id=e1.entity_id)

        h1 = HostBinding.create(
            installation_id=i1.installation_id,
            host_id="h1",
            bound_at="2026-01-01T00:00:00+00:00",
            attestation="sha256:" + "1" * 64,
        )
        h1_superseded = h1.superseded()
        h2 = HostBinding.create(
            installation_id=i1.installation_id,
            host_id="h2",
            bound_at="2026-09-10T00:00:00+00:00",
            attestation="sha256:" + "2" * 64,
        )

        s7 = StateRootIdentity.create(
            state_root_id="s7",
            installation_id=i1.installation_id,
            state_digest_sha256="d" * 64,
        )

        r81 = RuntimeEpoch.create(
            runtime_epoch_id="r81",
            state_root_id=s7.state_root_id,
            installation_id=i1.installation_id,
            host_id=h2.host_id,
            started_at="2026-09-10T01:00:00+00:00",
        ).terminated(reason="crash/reentry")
        r82 = r81.next_epoch(runtime_epoch_id="r82", started_at="2026-09-10T01:00:05+00:00")
        r83 = r82.next_epoch(runtime_epoch_id="r83", started_at="2026-09-10T02:00:00+00:00")

        # E1 == E1: the entity id used by the installation is exactly the one
        # the genesis record minted -- no drift across the whole tree build.
        self.assertEqual(i1.entity_id, e1.entity_id)

        # I1 == I1: same installation_id referenced by both host bindings,
        # the state root, and all three runtime epochs -- stable while H1/H2
        # and R81/R82/R83 change underneath it.
        installation_refs = {
            h1_superseded.installation_id,
            h2.installation_id,
            s7.installation_id,
            r81.installation_id,
            r82.installation_id,
            r83.installation_id,
        }
        self.assertEqual(installation_refs, {i1.installation_id})

        # host swap visible: h1 ended, h2 active, both under i1
        self.assertEqual(h1_superseded.status, BINDING_STATUS_SUPERSEDED)
        self.assertEqual(h2.status, BINDING_STATUS_ACTIVE)

        # state root sits under the installation, not under either host
        # binding directly (directive point 1) -- no host_id field on
        # StateRootIdentity at all in this schema.
        self.assertFalse(hasattr(s7, "host_id"))

        # runtime epochs sit under the state root and reference the CURRENT
        # host (h2) -- consistent with them all being minted after the swap.
        for epoch in (r81, r82, r83):
            self.assertEqual(epoch.state_root_id, s7.state_root_id)
            self.assertEqual(epoch.host_id, "h2")

        # crash/reentry stays visible, not smoothed into one continuous epoch
        self.assertEqual(r81.termination_reason, "crash/reentry")
        self.assertEqual(r82.predecessor_epoch_id, r81.runtime_epoch_id)
        self.assertEqual(r83.predecessor_epoch_id, r82.runtime_epoch_id)


if __name__ == "__main__":
    unittest.main()
