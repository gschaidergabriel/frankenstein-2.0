from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).parents[1] / "src"
sys.path.insert(0, str(SRC))

from frankenstein2.causal_authority_binding import (  # noqa: E402
    CausalAuthorityBindingError,
    UnifiedDBAuthorityRef,
    bind_causal_authority,
)
from frankenstein2.causal_identity import CausalIdentity  # noqa: E402


BASE = {
    "session_id": "session-001",
    "agent_id": "agent-clay-organ",
    "task_id": "task-42",
    "turn_id": "turn-7",
    "causal_id": "cause-root",
    "generation": 3,
}

UDB = UnifiedDBAuthorityRef(
    receipt_ref="workpackages/receipts/F2-WP-100_G1_SOURCE_CI_ACCEPTANCE.json",
    canonical_source="src/state/unifieddb_identity.py",
    fingerprint_schema="FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2",
)


class CausalAuthorityBindingTests(unittest.TestCase):
    def identity(self) -> CausalIdentity:
        return CausalIdentity.from_mapping(BASE)

    def telemetry(self) -> dict:
        return {
            "event_id": "evt-001",
            "run_id": "run-001",
            **BASE,
        }

    def test_valid_cross_plane_binding_roundtrips_exact_identity(self):
        bound = bind_causal_authority(self.identity(), unifieddb=UDB, telemetry=self.telemetry())
        self.assertEqual(bound.identity, self.identity())
        self.assertEqual(bound.telemetry_event_id, "evt-001")
        self.assertEqual(bound.telemetry_run_id, "run-001")
        self.assertEqual(bound.unifieddb.receipt_ref, UDB.receipt_ref)

    def test_wrong_agent_fails_closed(self):
        telemetry = {**self.telemetry(), "agent_id": "agent-other"}
        with self.assertRaises(CausalAuthorityBindingError):
            bind_causal_authority(self.identity(), unifieddb=UDB, telemetry=telemetry)

    def test_wrong_generation_fails_closed(self):
        telemetry = {**self.telemetry(), "generation": 4}
        with self.assertRaises(CausalAuthorityBindingError):
            bind_causal_authority(self.identity(), unifieddb=UDB, telemetry=telemetry)

    def test_missing_causal_id_fails_closed(self):
        telemetry = {k: v for k, v in self.telemetry().items() if k != "causal_id"}
        with self.assertRaises(CausalAuthorityBindingError):
            bind_causal_authority(self.identity(), unifieddb=UDB, telemetry=telemetry)

    def test_parent_lineage_mismatch_fails_closed(self):
        telemetry = {**self.telemetry(), "parent_causal_id": "wrong-parent"}
        with self.assertRaises(CausalAuthorityBindingError):
            bind_causal_authority(self.identity(), unifieddb=UDB, telemetry=telemetry)

    def test_parent_lineage_can_bind_when_exact(self):
        identity = self.identity().derive(causal_id="cause-child", generation=4)
        telemetry = {
            "event_id": "evt-child",
            "run_id": "run-001",
            **identity.as_dict(),
        }
        bound = bind_causal_authority(identity, unifieddb=UDB, telemetry=telemetry)
        self.assertEqual(bound.identity.parent_causal_id, "cause-root")

    def test_invalid_unifieddb_schema_fails_closed(self):
        with self.assertRaises(CausalAuthorityBindingError):
            UnifiedDBAuthorityRef(
                receipt_ref=UDB.receipt_ref,
                canonical_source=UDB.canonical_source,
                fingerprint_schema="FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v1",
            )

    def test_non_identity_input_fails_closed(self):
        with self.assertRaises(CausalAuthorityBindingError):
            bind_causal_authority(BASE, unifieddb=UDB, telemetry=self.telemetry())


if __name__ == "__main__":
    unittest.main()
