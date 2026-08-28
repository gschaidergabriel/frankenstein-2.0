from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from frankenstein2.persistent_agency_kernel import PersistentAgencyIntegrationError
from frankenstein2.persistent_agency_replay_policy import (
    CLASSIFICATION,
    POLICY_IDENTITY_CHANGED,
    POLICY_PROJECTION_CHANGED,
    REF_PREFIX,
    bind_checkpoint_replay_policy,
    build_replay_policy_binding,
    verify_checkpoint_replay_policy,
)
from test_persistent_agency_kernel import PersistentAgencyKernelTests


class PersistentAgencyReplayPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PersistentAgencyKernelTests()
        self.previous = self.fixture.checkpoint()
        self.current = self.fixture.checkpoint(
            integration_generation=1,
            parent=self.previous.sha256(),
        )

    def test_generation_only_transition_keeps_projection_and_identity_policies_distinct(self):
        projection = build_replay_policy_binding(
            self.previous,
            self.current,
            policy=POLICY_PROJECTION_CHANGED,
        )
        identity = build_replay_policy_binding(
            self.previous,
            self.current,
            policy=POLICY_IDENTITY_CHANGED,
        )
        self.assertFalse(projection.changed)
        self.assertTrue(identity.changed)
        self.assertEqual(projection.classification, CLASSIFICATION)
        self.assertNotEqual(projection.sha256(), identity.sha256())
        self.assertNotEqual(projection.provenance_ref(), identity.provenance_ref())

    def test_policy_flip_changes_checkpoint_replay_identity(self):
        projection_bound, projection = bind_checkpoint_replay_policy(
            self.previous,
            self.current,
            policy=POLICY_PROJECTION_CHANGED,
        )
        identity_bound, identity = bind_checkpoint_replay_policy(
            self.previous,
            self.current,
            policy=POLICY_IDENTITY_CHANGED,
        )
        self.assertNotEqual(projection_bound.sha256(), identity_bound.sha256())
        self.assertIn(projection.provenance_ref(), projection_bound.provenance_refs)
        self.assertIn(identity.provenance_ref(), identity_bound.provenance_refs)
        self.assertEqual(
            sum(ref.startswith(REF_PREFIX) for ref in projection_bound.provenance_refs),
            1,
        )
        self.assertTrue(
            verify_checkpoint_replay_policy(self.previous, projection_bound, projection)
        )
        self.assertTrue(verify_checkpoint_replay_policy(self.previous, identity_bound, identity))

    def test_missing_or_wrong_policy_binding_fails_closed(self):
        binding = build_replay_policy_binding(
            self.previous,
            self.current,
            policy=POLICY_PROJECTION_CHANGED,
        )
        with self.assertRaisesRegex(
            PersistentAgencyIntegrationError,
            "missing exact fingerprint replay policy binding",
        ):
            verify_checkpoint_replay_policy(self.previous, self.current, binding)

        identity_bound, _ = bind_checkpoint_replay_policy(
            self.previous,
            self.current,
            policy=POLICY_IDENTITY_CHANGED,
        )
        with self.assertRaisesRegex(
            PersistentAgencyIntegrationError,
            "missing exact fingerprint replay policy binding",
        ):
            verify_checkpoint_replay_policy(self.previous, identity_bound, binding)

    def test_bound_policy_survives_unifieddb_round_trip(self):
        bound, binding = bind_checkpoint_replay_policy(
            self.previous,
            self.current,
            policy=POLICY_PROJECTION_CHANGED,
        )
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "unified.db"
            store = self.fixture.store(db_path)
            self.assertEqual(store.persist(self.previous).status, "INSERTED")
            self.assertEqual(store.persist(bound).status, "INSERTED")
            replayed = store.load_latest("kernel-main")
            self.assertEqual(replayed.sha256(), bound.sha256())
            self.assertTrue(verify_checkpoint_replay_policy(self.previous, replayed, binding))

    def test_binding_has_no_action_effect_resume_or_completion_authority(self):
        bound, binding = bind_checkpoint_replay_policy(
            self.previous,
            self.current,
            policy=POLICY_IDENTITY_CHANGED,
        )
        payload = binding.as_dict()
        for forbidden in (
            "action",
            "selected_action",
            "effect",
            "resume",
            "completion",
            "provider",
            "tool",
        ):
            self.assertNotIn(forbidden, payload)
        self.assertNotIn("effect", bound.as_dict())
        self.assertNotIn("completion", bound.as_dict())


if __name__ == "__main__":
    unittest.main(verbosity=2)
