import unittest

from src.frankenstein2.active_sensing_fabric import (
    ActiveSensingFabricError,
    compile_observe_intent,
)
from src.frankenstein2.perception_fabric import (
    PerceptionCapability,
    PerceptionCapabilitySnapshot,
    PerceptionSource,
    SourceKind,
)
from src.frankenstein2.perception_host_permissions import (
    HostPermissionGrant,
    resolve_effective_perception_snapshot,
)
from src.frankenstein2.visual_need import VisualNeed, VisualReason, VisualTarget


P = ("test:active-sensing",)


def need():
    return VisualNeed(
        visual_need_id="visual-need:test",
        cycle_id="cycle:1",
        generation=3,
        vector_space_version="space:v1",
        source_slice_id="world-slice:test",
        source_slice_sha256="a" * 64,
        source_slice_provenance_digest="b" * 64,
        source_overlay_id=None,
        source_overlay_sha256=None,
        targets=(VisualTarget(atom_id="ui.status", reasons=(VisualReason.UNRESOLVED_TARGET,)),),
        visualizable_atom_ids=("ui.status",),
        provenance_refs=P,
        provenance_digest="c" * 64,
    )


def source(source_id="screen:1"):
    return PerceptionSource(
        source_id=source_id,
        kind=SourceKind.DISPLAY,
        clock_domain="local-monotonic",
        capture_owner_id=f"capture-owner:{source_id}",
        provenance_refs=P,
    )


def requested_permissions(caps, source_id="screen:1"):
    return PerceptionCapabilitySnapshot(
        snapshot_id=f"requested:{source_id}:1",
        generation=1,
        source_id=source_id,
        capabilities=caps,
        valid_from_monotonic_ns=10,
        expires_monotonic_ns=1_000,
        provenance_refs=P,
    )


def permissions(caps, source_id="screen:1"):
    requested = requested_permissions(caps, source_id)
    grant = HostPermissionGrant(
        grant_id=f"host-grant:{source_id}:1",
        source_id=source_id,
        generation=1,
        granted_capabilities=caps,
        valid_from_monotonic_ns=10,
        expires_monotonic_ns=1_000,
        host_adapter_id="host-adapter:test",
        native_permission_ref=f"native-permission:{source_id}",
        provenance_refs=P,
    )
    return resolve_effective_perception_snapshot(
        requested_snapshot=requested,
        host_grant=grant,
        now_monotonic_ns=100,
        provenance_refs=P,
    )


class ActiveSensingFabricTests(unittest.TestCase):
    def test_visual_need_compiles_to_effective_permission_bound_observe_intent(self):
        s = source()
        p = permissions((PerceptionCapability.SEE, PerceptionCapability.ANALYZE))
        i = compile_observe_intent(
            visual_need=need(),
            source=s,
            permission_snapshot=p,
            requested_head_ids=("ocr", "ui-state"),
            roi_ref="roi:status",
            required_freshness_ns=100,
            expires_monotonic_ns=900,
            priority_micros=800_000,
            max_work_units=20,
            provenance_refs=P,
        )
        self.assertEqual(i.source_id, "screen:1")
        self.assertEqual(i.permission_snapshot_sha256, p.sha256())
        self.assertEqual(i.target_atom_ids, ("ui.status",))
        self.assertFalse(i.allow_external_vlm)
        self.assertEqual(i.as_dict()["perception_execution_authority"], "NONE")

    def test_dashboard_or_requested_policy_alone_cannot_compile_observe_intent(self):
        s = source()
        requested = requested_permissions((PerceptionCapability.SEE, PerceptionCapability.ANALYZE))
        with self.assertRaisesRegex(ActiveSensingFabricError, "dashboard policy alone"):
            compile_observe_intent(
                visual_need=need(), source=s, permission_snapshot=requested,
                requested_head_ids=("ocr",), roi_ref=None,
                required_freshness_ns=100, expires_monotonic_ns=900,
                priority_micros=100_000, max_work_units=5, provenance_refs=P,
            )

    def test_missing_see_permission_blocks_compilation(self):
        s = source()
        p = permissions(())
        with self.assertRaisesRegex(ActiveSensingFabricError, "SEE"):
            compile_observe_intent(
                visual_need=need(), source=s, permission_snapshot=p,
                requested_head_ids=("ocr",), roi_ref=None,
                required_freshness_ns=100, expires_monotonic_ns=900,
                priority_micros=100_000, max_work_units=5, provenance_refs=P,
            )

    def test_external_vlm_requires_explicit_remote_transport_and_both_capabilities(self):
        s = source()
        p = permissions((
            PerceptionCapability.SEE,
            PerceptionCapability.ANALYZE,
            PerceptionCapability.EXTERNAL_VLM,
        ))
        with self.assertRaisesRegex(ActiveSensingFabricError, "remote-frame"):
            compile_observe_intent(
                visual_need=need(), source=s, permission_snapshot=p,
                requested_head_ids=("generic-vlm",), roi_ref="roi:novel",
                required_freshness_ns=100, expires_monotonic_ns=900,
                priority_micros=900_000, max_work_units=100,
                allow_remote_frame=False, allow_external_vlm=True,
                provenance_refs=P,
            )

    def test_remote_frame_requires_remote_frame_capability(self):
        s = source()
        p = permissions((PerceptionCapability.SEE, PerceptionCapability.ANALYZE))
        with self.assertRaisesRegex(ActiveSensingFabricError, "REMOTE_FRAME"):
            compile_observe_intent(
                visual_need=need(), source=s, permission_snapshot=p,
                requested_head_ids=("ocr",), roi_ref="roi:1",
                required_freshness_ns=100, expires_monotonic_ns=900,
                priority_micros=500_000, max_work_units=10,
                allow_remote_frame=True, provenance_refs=P,
            )

    def test_source_permission_identity_mismatch_fails_closed(self):
        s = source("screen:1")
        p = permissions(
            (PerceptionCapability.SEE, PerceptionCapability.ANALYZE),
            source_id="camera:1",
        )
        with self.assertRaisesRegex(ActiveSensingFabricError, "source_id mismatch"):
            compile_observe_intent(
                visual_need=need(), source=s, permission_snapshot=p,
                requested_head_ids=("ocr",), roi_ref=None,
                required_freshness_ns=100, expires_monotonic_ns=900,
                priority_micros=500_000, max_work_units=10, provenance_refs=P,
            )


if __name__ == "__main__":
    unittest.main()
