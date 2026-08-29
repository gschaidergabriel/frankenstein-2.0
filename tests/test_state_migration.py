from __future__ import annotations

import unittest

from frankenstein2.state_migration import (
    STEP_COPY,
    STEP_FREEZE_SOURCE,
    STEP_READBACK,
    STEP_RETAIN_ROLLBACK,
    STEP_SWITCH,
    STEP_VERIFY,
    STORAGE_CANONICAL_DURABLE,
    STORAGE_DISPOSABLE_HOST_CACHE,
    TARGET_CONFLICTING_LINEAGE,
    TARGET_EMPTY_VERIFIED,
    TARGET_SAME_LINEAGE_VERIFIED,
    TARGET_UNKNOWN,
    StateLineage,
    StateMigrationError,
    StateMigrationRequest,
    StateRootIdentity,
    TargetRootObservation,
    build_state_migration_plan,
)


class StateMigrationTests(unittest.TestCase):
    HOST = "1" * 64
    ROOT_1 = "2" * 64
    ROOT_2 = "3" * 64
    STATE = "4" * 64

    def root(
        self,
        root_id: str = "old",
        path: str = "/home/user/.local/share/frankenstein2/state",
        fingerprint: str | None = None,
        storage_class: str = STORAGE_CANONICAL_DURABLE,
    ) -> StateRootIdentity:
        return StateRootIdentity.create(
            root_id=root_id,
            path=path,
            storage_class=storage_class,
            host_identity_sha256=self.HOST,
            observed_root_fingerprint_sha256=fingerprint or self.ROOT_1,
        )

    def lineage(
        self,
        generation: int = 7,
        state_sha256: str | None = None,
        root: StateRootIdentity | None = None,
    ) -> StateLineage:
        return StateLineage.create(
            lineage_id="f2-user-lineage",
            generation=generation,
            state_sha256=state_sha256 or self.STATE,
            root=root or self.root(),
        )

    def target(self) -> StateRootIdentity:
        return self.root(
            "new",
            "/srv/frankenstein2/state",
            self.ROOT_2,
        )

    def request(
        self, observation: TargetRootObservation | None = None
    ) -> StateMigrationRequest:
        source = self.lineage()
        target = self.target()
        target_observation = observation or TargetRootObservation(
            status=TARGET_EMPTY_VERIFIED,
            evidence_ref="probe:target-empty",
        )
        return StateMigrationRequest.create(
            migration_id="migration-1",
            source_lineage=source,
            target_root=target,
            target_observation=target_observation,
            rollback_root=source.root,
        )

    def test_happy_plan_is_deterministic_and_preserves_rollback(self) -> None:
        first = build_state_migration_plan(self.request())
        second = build_state_migration_plan(self.request())
        self.assertEqual(first.sha256(), second.sha256())
        self.assertEqual(
            first.steps,
            (
                STEP_FREEZE_SOURCE,
                STEP_COPY,
                STEP_VERIFY,
                STEP_SWITCH,
                STEP_READBACK,
                STEP_RETAIN_ROLLBACK,
            ),
        )
        self.assertEqual(first.source_root_sha256, first.rollback_root_sha256)

    def test_disposable_target_rejected(self) -> None:
        source = self.lineage()
        target = self.root(
            "cache",
            "/home/user/plugin/cache",
            self.ROOT_2,
            STORAGE_DISPOSABLE_HOST_CACHE,
        )
        with self.assertRaises(StateMigrationError):
            StateMigrationRequest.create(
                migration_id="m",
                source_lineage=source,
                target_root=target,
                target_observation=TargetRootObservation(
                    status=TARGET_EMPTY_VERIFIED,
                    evidence_ref="probe:empty",
                ),
                rollback_root=source.root,
            )

    def test_obvious_transient_target_rejected_even_if_labeled_durable(self) -> None:
        source = self.lineage()
        target = self.root(
            "tmp",
            "/tmp/frankenstein2",
            self.ROOT_2,
            STORAGE_CANONICAL_DURABLE,
        )
        with self.assertRaises(StateMigrationError):
            StateMigrationRequest.create(
                migration_id="m",
                source_lineage=source,
                target_root=target,
                target_observation=TargetRootObservation(
                    status=TARGET_EMPTY_VERIFIED,
                    evidence_ref="probe:empty",
                ),
                rollback_root=source.root,
            )

    def test_unknown_target_refuses_silent_second_lineage(self) -> None:
        with self.assertRaises(StateMigrationError):
            self.request(TargetRootObservation(status=TARGET_UNKNOWN))

    def test_conflicting_lineage_rejected(self) -> None:
        observation = TargetRootObservation(
            status=TARGET_CONFLICTING_LINEAGE,
            observed_lineage_id="other-lineage",
            observed_generation=1,
            observed_state_sha256="5" * 64,
            evidence_ref="probe:conflict",
        )
        with self.assertRaises(StateMigrationError):
            self.request(observation)

    def test_same_lineage_older_generation_is_migratable(self) -> None:
        observation = TargetRootObservation(
            status=TARGET_SAME_LINEAGE_VERIFIED,
            observed_lineage_id="f2-user-lineage",
            observed_generation=6,
            observed_state_sha256="5" * 64,
            evidence_ref="probe:old-target",
        )
        plan = build_state_migration_plan(self.request(observation))
        self.assertEqual(plan.generation, 7)

    def test_same_generation_digest_conflict_rejected(self) -> None:
        observation = TargetRootObservation(
            status=TARGET_SAME_LINEAGE_VERIFIED,
            observed_lineage_id="f2-user-lineage",
            observed_generation=7,
            observed_state_sha256="5" * 64,
            evidence_ref="probe:conflict",
        )
        with self.assertRaises(StateMigrationError):
            self.request(observation)

    def test_newer_target_generation_rejected(self) -> None:
        observation = TargetRootObservation(
            status=TARGET_SAME_LINEAGE_VERIFIED,
            observed_lineage_id="f2-user-lineage",
            observed_generation=8,
            observed_state_sha256="5" * 64,
            evidence_ref="probe:ahead",
        )
        with self.assertRaises(StateMigrationError):
            self.request(observation)

    def test_wrong_host_identity_rejected(self) -> None:
        source = self.lineage()
        target = StateRootIdentity.create(
            root_id="new",
            path="/srv/frankenstein2/state",
            storage_class=STORAGE_CANONICAL_DURABLE,
            host_identity_sha256="9" * 64,
            observed_root_fingerprint_sha256=self.ROOT_2,
        )
        with self.assertRaises(StateMigrationError):
            StateMigrationRequest.create(
                migration_id="m",
                source_lineage=source,
                target_root=target,
                target_observation=TargetRootObservation(
                    status=TARGET_EMPTY_VERIFIED,
                    evidence_ref="probe:empty",
                ),
                rollback_root=source.root,
            )

    def test_rollback_must_be_exact_source_root(self) -> None:
        source = self.lineage()
        rollback = self.root("rollback", "/srv/rollback", "8" * 64)
        with self.assertRaises(StateMigrationError):
            StateMigrationRequest.create(
                migration_id="m",
                source_lineage=source,
                target_root=self.target(),
                target_observation=TargetRootObservation(
                    status=TARGET_EMPTY_VERIFIED,
                    evidence_ref="probe:empty",
                ),
                rollback_root=rollback,
            )

    def test_source_digest_fence_mismatch_rejected(self) -> None:
        request = self.request()
        with self.assertRaises(StateMigrationError):
            StateMigrationRequest(
                schema=request.schema,
                migration_id=request.migration_id,
                source_lineage=request.source_lineage,
                target_root=request.target_root,
                target_observation=request.target_observation,
                rollback_root=request.rollback_root,
                expected_source_lineage_sha256="0" * 64,
                expected_source_root_sha256=request.expected_source_root_sha256,
                expected_target_root_sha256=request.expected_target_root_sha256,
                expected_rollback_root_sha256=request.expected_rollback_root_sha256,
            )

    def test_post_init_nested_mutation_detected_at_consumer_boundary(self) -> None:
        request = self.request()
        object.__setattr__(request.target_root, "path", "/tmp/forged")
        with self.assertRaises(StateMigrationError):
            build_state_migration_plan(request)

    def test_bool_generation_rejected(self) -> None:
        with self.assertRaises(StateMigrationError):
            StateLineage.create(
                lineage_id="x",
                generation=True,
                state_sha256=self.STATE,
                root=self.root(),
            )

    def test_target_equal_source_rejected(self) -> None:
        source = self.lineage()
        with self.assertRaises(StateMigrationError):
            StateMigrationRequest.create(
                migration_id="m",
                source_lineage=source,
                target_root=source.root,
                target_observation=TargetRootObservation(
                    status=TARGET_EMPTY_VERIFIED,
                    evidence_ref="probe:empty",
                ),
                rollback_root=source.root,
            )

    def test_plan_is_not_filesystem_or_completion_authority(self) -> None:
        plan = build_state_migration_plan(self.request())
        self.assertIn("NOT_FILESYSTEM", plan.classification)
        self.assertIn("COMPLETION_AUTHORITY", plan.classification)
        self.assertIn(
            "FILES_COPIED_OR_ZERO_EXIT_CODE_NEVER_EQUALS_COMPLETION",
            plan.acceptance_requirements,
        )


if __name__ == "__main__":
    unittest.main()
