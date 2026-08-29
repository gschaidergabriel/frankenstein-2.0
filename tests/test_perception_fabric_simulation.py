import unittest

from src.frankenstein2.perception_dashboard_policy import (
    capability_snapshot_from_dashboard,
    set_global_pause,
)
from src.frankenstein2.perception_fabric import PerceptionFabricError
from src.frankenstein2.perception_fabric_simulation import (
    _dashboard_and_snapshots,
    _intents_and_bridge,
    _sources,
    _world_and_visual_need,
    _claims,
    _capture_and_retina,
    run_four_source_perception_simulation,
)


class PerceptionFabricSimulationTests(unittest.TestCase):
    def test_four_source_end_to_end_contract_loop(self):
        report = run_four_source_perception_simulation()
        payload = report.as_dict()
        self.assertEqual(payload["source_count"], 4)
        self.assertEqual(payload["active_worker_count"], 4)
        self.assertEqual(report.generic_vlm_calls, 0)
        self.assertEqual(report.raw_payload_persist_count, 0)
        self.assertEqual(report.remote_raw_payload_send_count, 0)
        self.assertIn("ui.submit", report.disagreement_atom_ids)
        self.assertFalse(payload["physical_sensor_runtime"])
        self.assertFalse(payload["network_bridge_runtime"])
        self.assertFalse(payload["whole_system_acceptance"])
        self.assertEqual(payload["world_truth_authority"], "NONE")

    def test_dashboard_revocation_invalidates_preexisting_observe_intent(self):
        sources = _sources()
        dashboard, snapshots = _dashboard_and_snapshots(sources)
        _, assessments = _capture_and_retina(sources)
        claims = _claims(sources, assessments)
        _, _, visual_need = _world_and_visual_need(claims)
        intents, _, _, _ = _intents_and_bridge(
            sources=sources,
            snapshots=snapshots,
            visual_need=visual_need,
            claims=claims,
        )
        old_intent = intents[0]
        paused = set_global_pause(
            state=dashboard,
            paused=True,
            provenance_refs=("test:revocation",),
        )
        revoked_snapshot = capability_snapshot_from_dashboard(
            state=paused,
            source_id=sources[0].source_id,
            valid_from_monotonic_ns=301,
            expires_monotonic_ns=10_000,
            provenance_refs=("test:revocation",),
        )
        with self.assertRaisesRegex(PerceptionFabricError, "stale or mismatched"):
            old_intent.validate_against(revoked_snapshot, now_monotonic_ns=302)


if __name__ == "__main__":
    unittest.main()
