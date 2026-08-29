import hashlib
import unittest

from src.frankenstein2.perception_world_bridge import (
    BridgeCapabilityView,
    BridgeObserveIntent,
    PerceptionWorldBridgeError,
    TypedPerceptEvent,
    validate_observe_intent_for_dispatch,
    validate_remote_percept_for_admission,
)

P = ("test:wp712",)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def capability(*, permission=None, remote=False, vlm=False, source_generation=3):
    return BridgeCapabilityView(
        snapshot_id="permissions:current",
        generation=9,
        source_id="camera:front",
        source_generation=source_generation,
        permission_snapshot_sha256=permission or digest("permission:g9"),
        remote_frame_allowed=remote,
        external_vlm_allowed=vlm,
        provenance_refs=P,
    )


def intent(*, permission=None, bridge_generation=4, payload="TYPED_PERCEPT", vlm=False, deadline=200, source_generation=3):
    return BridgeObserveIntent(
        intent_id="observe:1",
        source_id="camera:front",
        source_generation=source_generation,
        permission_snapshot_sha256=permission or digest("permission:g9"),
        bridge_generation=bridge_generation,
        created_monotonic_ns=100,
        deadline_monotonic_ns=deadline,
        requested_payload_kind=payload,
        external_vlm_requested=vlm,
        clock_domain="grid-monotonic",
        provenance_refs=P,
    )


def percept(*, permission=None, bridge_generation=4, payload="TYPED_PERCEPT", observed=150, freshness=50, source_generation=3):
    return TypedPerceptEvent(
        event_id="percept:1",
        source_id="camera:front",
        source_generation=source_generation,
        permission_snapshot_sha256=permission or digest("permission:g9"),
        bridge_generation=bridge_generation,
        epistemic_kind="OBSERVED",
        payload_kind=payload,
        payload_ref="percept-ref:1",
        source_sequence=7,
        capture_monotonic_ns=max(0, observed - 5),
        observed_monotonic_ns=observed,
        freshness_max_age_ns=freshness,
        clock_domain="edge-monotonic",
        clock_uncertainty_ns=1,
        provenance_refs=P,
    )


class PerceptionWorldBridgeTests(unittest.TestCase):
    def test_typed_percept_is_default_and_needs_no_remote_frame_capability(self):
        decision = validate_observe_intent_for_dispatch(
            decision_id="decision:typed",
            intent=intent(),
            current_capability=capability(),
            current_bridge_generation=4,
            now_monotonic_ns=150,
            now_clock_domain="grid-monotonic",
            provenance_refs=P,
        )
        self.assertEqual(decision.payload_kind, "TYPED_PERCEPT")
        self.assertFalse(decision.as_dict()["network_io_performed"])
        self.assertEqual(decision.as_dict()["effect_authority"], "NONE")

    def test_raw_or_roi_transfer_requires_remote_frame_revalidation(self):
        for kind in ("RAW_FRAME", "ROI_FRAME"):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(PerceptionWorldBridgeError, "REMOTE_FRAME"):
                    validate_observe_intent_for_dispatch(
                        decision_id=f"decision:{kind}",
                        intent=intent(payload=kind),
                        current_capability=capability(remote=False),
                        current_bridge_generation=4,
                        now_monotonic_ns=150,
                        now_clock_domain="grid-monotonic",
                        provenance_refs=P,
                    )
                decision = validate_observe_intent_for_dispatch(
                    decision_id=f"decision:{kind}:allowed",
                    intent=intent(payload=kind),
                    current_capability=capability(remote=True),
                    current_bridge_generation=4,
                    now_monotonic_ns=150,
                    now_clock_domain="grid-monotonic",
                    provenance_refs=P,
                )
                self.assertEqual(decision.payload_kind, kind)

    def test_external_vlm_requires_dispatch_time_capability(self):
        with self.assertRaisesRegex(PerceptionWorldBridgeError, "EXTERNAL_VLM"):
            validate_observe_intent_for_dispatch(
                decision_id="decision:vlm:deny",
                intent=intent(vlm=True),
                current_capability=capability(vlm=False),
                current_bridge_generation=4,
                now_monotonic_ns=150,
                now_clock_domain="grid-monotonic",
                provenance_refs=P,
            )
        decision = validate_observe_intent_for_dispatch(
            decision_id="decision:vlm:allow",
            intent=intent(vlm=True),
            current_capability=capability(vlm=True),
            current_bridge_generation=4,
            now_monotonic_ns=150,
            now_clock_domain="grid-monotonic",
            provenance_refs=P,
        )
        self.assertTrue(decision.external_vlm)
        self.assertFalse(decision.as_dict()["provider_or_vlm_invoked"])

    def test_permission_revocation_or_digest_change_fails_closed(self):
        with self.assertRaisesRegex(PerceptionWorldBridgeError, "permission snapshot"):
            validate_observe_intent_for_dispatch(
                decision_id="decision:revoked",
                intent=intent(permission=digest("old")),
                current_capability=capability(permission=digest("new")),
                current_bridge_generation=4,
                now_monotonic_ns=150,
                now_clock_domain="grid-monotonic",
                provenance_refs=P,
            )

    def test_expired_intent_is_non_replayable(self):
        with self.assertRaisesRegex(PerceptionWorldBridgeError, "expired"):
            validate_observe_intent_for_dispatch(
                decision_id="decision:expired",
                intent=intent(deadline=149),
                current_capability=capability(),
                current_bridge_generation=4,
                now_monotonic_ns=150,
                now_clock_domain="grid-monotonic",
                provenance_refs=P,
            )

    def test_reconnect_generation_invalidates_queued_old_intent(self):
        with self.assertRaisesRegex(PerceptionWorldBridgeError, "bridge generation"):
            validate_observe_intent_for_dispatch(
                decision_id="decision:reconnect",
                intent=intent(bridge_generation=3),
                current_capability=capability(),
                current_bridge_generation=4,
                now_monotonic_ns=150,
                now_clock_domain="grid-monotonic",
                provenance_refs=P,
            )

    def test_late_stale_remote_event_cannot_be_current(self):
        with self.assertRaisesRegex(PerceptionWorldBridgeError, "stale"):
            validate_remote_percept_for_admission(
                decision_id="decision:late",
                event=percept(observed=100, freshness=20),
                current_capability=capability(),
                current_bridge_generation=4,
                receive_monotonic_ns=121,
                receive_clock_domain="edge-monotonic",
                provenance_refs=P,
            )

    def test_remote_raw_event_rechecks_remote_frame_at_actual_admission(self):
        with self.assertRaisesRegex(PerceptionWorldBridgeError, "REMOTE_FRAME"):
            validate_remote_percept_for_admission(
                decision_id="decision:raw-deny",
                event=percept(payload="RAW_FRAME"),
                current_capability=capability(remote=False),
                current_bridge_generation=4,
                receive_monotonic_ns=160,
                receive_clock_domain="edge-monotonic",
                provenance_refs=P,
            )

    def test_source_rebind_generation_fails_closed(self):
        with self.assertRaisesRegex(PerceptionWorldBridgeError, "source generation"):
            validate_remote_percept_for_admission(
                decision_id="decision:old-source",
                event=percept(source_generation=2),
                current_capability=capability(source_generation=3),
                current_bridge_generation=4,
                receive_monotonic_ns=160,
                receive_clock_domain="edge-monotonic",
                provenance_refs=P,
            )

    def test_cross_clock_receive_is_unaligned_not_false_age_arithmetic(self):
        decision = validate_remote_percept_for_admission(
            decision_id="decision:unaligned",
            event=percept(observed=9_000_000_000, freshness=1),
            current_capability=capability(),
            current_bridge_generation=4,
            receive_monotonic_ns=1,
            receive_clock_domain="vps-monotonic",
            provenance_refs=P,
        )
        self.assertEqual(decision.temporal_status, "UNALIGNED_CANDIDATE")
        self.assertFalse(decision.as_dict()["canonical_world_mutation"])

    def test_admitted_percept_remains_candidate_not_world_truth(self):
        event = percept()
        decision = validate_remote_percept_for_admission(
            decision_id="decision:admit",
            event=event,
            current_capability=capability(),
            current_bridge_generation=4,
            receive_monotonic_ns=160,
            receive_clock_domain="edge-monotonic",
            provenance_refs=P,
        )
        self.assertEqual(decision.operation, "ADMIT_PERCEPT")
        self.assertFalse(decision.as_dict()["canonical_world_mutation"])
        self.assertEqual(event.as_dict()["world_truth_authority"], "NONE")
        self.assertIsNone(event.as_dict()["raw_payload"])


if __name__ == "__main__":
    unittest.main()
