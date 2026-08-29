import unittest

from src.frankenstein2.perception_bridge import (
    AuditOutcome,
    BridgePayloadKind,
    PerceptionBridgeError,
    build_audit_receipt,
    build_bridge_envelope,
)
from src.frankenstein2.perception_fabric import (
    ObserveIntent,
    PerceptionCapability,
    PerceptionCapabilitySnapshot,
)


P = ("test:bridge",)
PAYLOAD_SHA = "a" * 64


def snapshot(capabilities):
    return PerceptionCapabilitySnapshot(
        snapshot_id="permission:screen:1:1",
        generation=1,
        source_id="screen:1",
        capabilities=capabilities,
        valid_from_monotonic_ns=10,
        expires_monotonic_ns=1_000,
        provenance_refs=P,
    )


def intent(s, *, remote=False, vlm=False):
    return ObserveIntent(
        intent_id="look:screen:1",
        cycle_id="cycle:1",
        generation=1,
        source_id="screen:1",
        permission_snapshot_sha256=s.sha256(),
        requested_head_ids=("ocr",),
        target_atom_ids=("ui.status",),
        roi_ref="roi:status",
        required_freshness_ns=100,
        expires_monotonic_ns=900,
        priority_micros=900_000,
        max_work_units=10,
        allow_remote_frame=remote,
        allow_external_vlm=vlm,
        provenance_refs=P,
    )


class PerceptionBridgeTests(unittest.TestCase):
    def test_typed_event_is_default_without_raw_capability(self):
        s = snapshot((PerceptionCapability.SEE, PerceptionCapability.ANALYZE))
        i = intent(s)
        envelope = build_bridge_envelope(
            intent=i,
            snapshot=s,
            payload_kind=BridgePayloadKind.TYPED_EVENT,
            payload_sha256=PAYLOAD_SHA,
            external_vlm_requested=False,
            now_monotonic_ns=100,
            provenance_refs=P,
        )
        self.assertEqual(envelope.payload_kind, BridgePayloadKind.TYPED_EVENT)
        self.assertFalse(envelope.external_vlm_requested)
        self.assertFalse(envelope.as_dict()["contains_payload_bytes"])

    def test_raw_roi_requires_remote_frame_permission_and_intent_flag(self):
        s = snapshot((PerceptionCapability.SEE, PerceptionCapability.ANALYZE))
        i = intent(s)
        with self.assertRaisesRegex(PerceptionBridgeError, "REMOTE_FRAME"):
            build_bridge_envelope(
                intent=i,
                snapshot=s,
                payload_kind=BridgePayloadKind.RAW_ROI,
                payload_sha256=PAYLOAD_SHA,
                external_vlm_requested=False,
                now_monotonic_ns=100,
                provenance_refs=P,
            )

    def test_external_vlm_requires_remote_frame_and_external_vlm_authorization(self):
        s = snapshot((
            PerceptionCapability.SEE,
            PerceptionCapability.ANALYZE,
            PerceptionCapability.REMOTE_FRAME,
            PerceptionCapability.EXTERNAL_VLM,
        ))
        i = intent(s, remote=True, vlm=True)
        envelope = build_bridge_envelope(
            intent=i,
            snapshot=s,
            payload_kind=BridgePayloadKind.RAW_ROI,
            payload_sha256=PAYLOAD_SHA,
            external_vlm_requested=True,
            now_monotonic_ns=100,
            provenance_refs=P,
        )
        self.assertTrue(envelope.external_vlm_requested)

    def test_external_vlm_cannot_use_typed_event_payload(self):
        s = snapshot((
            PerceptionCapability.SEE,
            PerceptionCapability.ANALYZE,
            PerceptionCapability.REMOTE_FRAME,
            PerceptionCapability.EXTERNAL_VLM,
        ))
        i = intent(s, remote=True, vlm=True)
        with self.assertRaisesRegex(PerceptionBridgeError, "RAW_ROI"):
            build_bridge_envelope(
                intent=i,
                snapshot=s,
                payload_kind=BridgePayloadKind.TYPED_EVENT,
                payload_sha256=PAYLOAD_SHA,
                external_vlm_requested=True,
                now_monotonic_ns=100,
                provenance_refs=P,
            )

    def test_stale_permission_hash_blocks_bridge(self):
        old = snapshot((PerceptionCapability.SEE, PerceptionCapability.ANALYZE))
        i = intent(old)
        newer = PerceptionCapabilitySnapshot(
            snapshot_id="permission:screen:1:2",
            generation=2,
            source_id="screen:1",
            capabilities=(PerceptionCapability.SEE, PerceptionCapability.ANALYZE),
            valid_from_monotonic_ns=10,
            expires_monotonic_ns=1_000,
            provenance_refs=P,
        )
        with self.assertRaisesRegex(PerceptionBridgeError, "stale or mismatched"):
            build_bridge_envelope(
                intent=i,
                snapshot=newer,
                payload_kind=BridgePayloadKind.TYPED_EVENT,
                payload_sha256=PAYLOAD_SHA,
                external_vlm_requested=False,
                now_monotonic_ns=100,
                provenance_refs=P,
            )

    def test_default_executed_receipt_proves_zero_raw_and_zero_vlm(self):
        s = snapshot((PerceptionCapability.SEE, PerceptionCapability.ANALYZE))
        i = intent(s)
        receipt = build_audit_receipt(
            intent=i,
            snapshot=s,
            outcome=AuditOutcome.EXECUTED,
            executed_head_ids=("ocr",),
            raw_payload_persisted=False,
            remote_raw_payload_sent=False,
            external_vlm_called=False,
            event_monotonic_ns=100,
            reason="typed-local-analysis-complete",
            provenance_refs=P,
        )
        self.assertFalse(receipt.raw_payload_persisted)
        self.assertFalse(receipt.remote_raw_payload_sent)
        self.assertFalse(receipt.external_vlm_called)
        self.assertEqual(receipt.as_dict()["world_truth_authority"], "NONE")

    def test_receipt_cannot_claim_raw_persistence_without_permission(self):
        s = snapshot((PerceptionCapability.SEE, PerceptionCapability.ANALYZE))
        i = intent(s)
        with self.assertRaisesRegex(PerceptionBridgeError, "RAW_RETENTION"):
            build_audit_receipt(
                intent=i,
                snapshot=s,
                outcome=AuditOutcome.EXECUTED,
                executed_head_ids=("ocr",),
                raw_payload_persisted=True,
                remote_raw_payload_sent=False,
                external_vlm_called=False,
                event_monotonic_ns=100,
                reason="bad-claim",
                provenance_refs=P,
            )

    def test_nonexecuted_receipt_cannot_claim_execution(self):
        s = snapshot((PerceptionCapability.SEE, PerceptionCapability.ANALYZE))
        i = intent(s)
        with self.assertRaisesRegex(PerceptionBridgeError, "non-executed"):
            build_audit_receipt(
                intent=i,
                snapshot=s,
                outcome=AuditOutcome.DROPPED_BACKPRESSURE,
                executed_head_ids=("ocr",),
                raw_payload_persisted=False,
                remote_raw_payload_sent=False,
                external_vlm_called=False,
                event_monotonic_ns=100,
                reason="queue-pressure",
                provenance_refs=P,
            )


if __name__ == "__main__":
    unittest.main()
