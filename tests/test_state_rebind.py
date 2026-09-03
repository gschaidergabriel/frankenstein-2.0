from __future__ import annotations

import unittest

from frankenstein2.entity_identity import HostBinding
from frankenstein2.state_migration import (
    STORAGE_CANONICAL_DURABLE,
    TARGET_EMPTY_VERIFIED,
    StateLineage,
    StateMigrationError,
    StateRootIdentity,
    TargetRootObservation,
)
from frankenstein2.state_rebind import (
    REBIND_REQUEST_SCHEMA,
    RebindEligibleMigrationRequest,
    StateRebindError,
    assert_rebind_eligible,
)


class StateRebindTests(unittest.TestCase):
    HOST_OLD = "1" * 64
    HOST_NEW = "9" * 64
    FP_SOURCE = "2" * 64
    FP_TARGET = "3" * 64
    STATE = "4" * 64

    def source_root(self, installation_id: str | None = "i1") -> StateRootIdentity:
        return StateRootIdentity.create(
            root_id="old",
            path="/home/user/.local/share/frankenstein2/state",
            storage_class=STORAGE_CANONICAL_DURABLE,
            host_identity_sha256=self.HOST_OLD,
            observed_root_fingerprint_sha256=self.FP_SOURCE,
            installation_id=installation_id,
        )

    def target_root(
        self, installation_id: str | None = "i1", host_identity_sha256: str | None = None
    ) -> StateRootIdentity:
        return StateRootIdentity.create(
            root_id="new",
            path="/srv/frankenstein2/state",
            storage_class=STORAGE_CANONICAL_DURABLE,
            host_identity_sha256=host_identity_sha256 or self.HOST_NEW,
            observed_root_fingerprint_sha256=self.FP_TARGET,
            installation_id=installation_id,
        )

    def lineage(self, root: StateRootIdentity | None = None) -> StateLineage:
        return StateLineage.create(
            lineage_id="f2-user-lineage",
            generation=7,
            state_sha256=self.STATE,
            root=root or self.source_root(),
        )

    def active_binding(
        self, installation_id: str = "i1", binding_id: str = "hb2", host_id: str = "h2"
    ) -> HostBinding:
        return HostBinding.create(
            binding_id=binding_id,
            installation_id=installation_id,
            host_id=host_id,
            bound_at="2026-09-10T00:00:00+00:00",
            attestation="sha256:" + "a" * 64,
        )

    # -- assert_rebind_eligible() unit-level -------------------------------

    def test_eligible_when_same_installation_and_active_binding(self) -> None:
        assert_rebind_eligible(
            source_root=self.source_root(),
            target_root=self.target_root(),
            host_binding=self.active_binding(),
        )  # must not raise

    def test_rejects_missing_installation_id_on_source(self) -> None:
        with self.assertRaises(StateRebindError):
            assert_rebind_eligible(
                source_root=self.source_root(installation_id=None),
                target_root=self.target_root(),
                host_binding=self.active_binding(),
            )

    def test_rejects_missing_installation_id_on_target(self) -> None:
        with self.assertRaises(StateRebindError):
            assert_rebind_eligible(
                source_root=self.source_root(),
                target_root=self.target_root(installation_id=None),
                host_binding=self.active_binding(),
            )

    def test_rejects_different_installation_id(self) -> None:
        with self.assertRaises(StateRebindError):
            assert_rebind_eligible(
                source_root=self.source_root(installation_id="i1"),
                target_root=self.target_root(installation_id="i2"),
                host_binding=self.active_binding(installation_id="i2"),
            )

    def test_rejects_binding_for_different_installation(self) -> None:
        with self.assertRaises(StateRebindError):
            assert_rebind_eligible(
                source_root=self.source_root(),
                target_root=self.target_root(),
                host_binding=self.active_binding(installation_id="i-other"),
            )

    def test_rejects_superseded_binding(self) -> None:
        with self.assertRaises(StateRebindError):
            assert_rebind_eligible(
                source_root=self.source_root(),
                target_root=self.target_root(),
                host_binding=self.active_binding().superseded(),
            )

    def test_rejects_revoked_binding(self) -> None:
        with self.assertRaises(StateRebindError):
            assert_rebind_eligible(
                source_root=self.source_root(),
                target_root=self.target_root(),
                host_binding=self.active_binding().revoked(),
            )

    # -- full RebindEligibleMigrationRequest --------------------------------

    def request(self) -> RebindEligibleMigrationRequest:
        source = self.lineage()
        target = self.target_root()
        return RebindEligibleMigrationRequest.create(
            migration_id="rebind-1",
            source_lineage=source,
            target_root=target,
            target_observation=TargetRootObservation(
                status=TARGET_EMPTY_VERIFIED, evidence_ref="probe:target-empty"
            ),
            rollback_root=source.root,
            host_binding=self.active_binding(),
        )

    def test_request_succeeds_despite_host_identity_mismatch(self) -> None:
        """THE point of this module: HOST_OLD != HOST_NEW, and this does NOT
        raise -- unlike StateMigrationRequest, which would (see
        test_state_migration.py::test_wrong_host_identity_rejected, still
        green and unmodified)."""
        request = self.request()
        self.assertEqual(request.schema, REBIND_REQUEST_SCHEMA)
        self.assertNotEqual(
            request.source_lineage.root.host_identity_sha256,
            request.target_root.host_identity_sha256,
        )

    def test_request_still_rejects_non_canonical_target(self) -> None:
        from frankenstein2.state_migration import STORAGE_DISPOSABLE_HOST_CACHE

        source = self.lineage()
        bad_target = StateRootIdentity.create(
            root_id="cache",
            path="/home/user/plugin/cache",
            storage_class=STORAGE_DISPOSABLE_HOST_CACHE,
            host_identity_sha256=self.HOST_NEW,
            observed_root_fingerprint_sha256=self.FP_TARGET,
            installation_id="i1",
        )
        with self.assertRaises(StateMigrationError):
            RebindEligibleMigrationRequest.create(
                migration_id="rebind-bad",
                source_lineage=source,
                target_root=bad_target,
                target_observation=TargetRootObservation(
                    status=TARGET_EMPTY_VERIFIED, evidence_ref="probe:empty"
                ),
                rollback_root=source.root,
                host_binding=self.active_binding(),
            )

    def test_request_still_rejects_without_valid_binding(self) -> None:
        source = self.lineage()
        with self.assertRaises(StateRebindError):
            RebindEligibleMigrationRequest.create(
                migration_id="rebind-no-binding",
                source_lineage=source,
                target_root=self.target_root(),
                target_observation=TargetRootObservation(
                    status=TARGET_EMPTY_VERIFIED, evidence_ref="probe:empty"
                ),
                rollback_root=source.root,
                host_binding=self.active_binding().superseded(),
            )

    def test_request_digest_fences_still_hold(self) -> None:
        request = self.request()
        rebuilt_sha = request.sha256()
        self.assertEqual(request.sha256(), rebuilt_sha)


if __name__ == "__main__":
    unittest.main()
