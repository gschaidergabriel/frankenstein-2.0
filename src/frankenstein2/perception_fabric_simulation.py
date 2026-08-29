"""Deterministic four-source Perception Fabric integration simulation.

This module is an executable repository/VPS-side integration harness, not physical sensor
runtime. It composes the real F2 contracts from source permission through capture references,
Retina, perception control, observed claims, temporal fusion, world multi-view disagreement,
VisualNeed, ObserveIntent, worker allocation and typed bridge/audit output.

No raw frame bytes, VLM/model/provider/network call, physical device access, canonical world
truth, effect, completion, VPS-runtime or whole-system credit is produced here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, ClassVar

from .active_sensing_fabric import compile_observe_intent
from .epistemic_perception import EpistemicPerceptClaim
from .perception_bridge import (
    AuditOutcome,
    BridgePayloadKind,
    PerceptionAuditReceipt,
    PerceptionBridgeEnvelope,
    build_audit_receipt,
    build_bridge_envelope,
)
from .perception_control import (
    PerceptionDependency,
    PerceptionHeadPolicy,
    PerceptionPolicyRegistry,
    evaluate_perception_head,
)
from .perception_dashboard_policy import (
    PerceptionDashboardState,
    capability_snapshot_from_dashboard,
    create_dashboard_state,
    set_source_policy,
)
from .perception_fabric import (
    ObserveIntent,
    PerceptionCapability,
    PerceptionCapabilitySnapshot,
    PerceptionSource,
    PerceptionWorkerAllocation,
    PerceptionWorkerPolicy,
    SourceKind,
    allocate_perception_workers,
)
from .perception_temporal import (
    ObservationWindow,
    bind_observed_claim,
    build_observation_window,
)
from .retina_capture_broker import (
    CaptureBrokerState,
    CaptureFrameRef,
    create_capture_broker,
    publish_frame_ref,
)
from .retina_pipeline import (
    RetinaAssessment,
    RetinaFrameSignal,
    RetinaPolicy,
    assess_retina_transition,
)
from .sparse_world_basis import (
    EpistemicOrigin,
    KnowledgeState,
    WorldAtom,
    WorldNeed,
    WorldSlice,
    materialize_world_slice,
)
from .visual_need import VisualNeed, plan_visual_need
from .world_multiview import (
    MultiViewOverlay,
    ViewAtomState,
    WorldView,
    compare_world_views,
)

SIMULATION_REPORT_SCHEMA = "FRANKENSTEIN2_PERCEPTION_FABRIC_SIMULATION_REPORT/v1"
PROVENANCE = ("simulation:perception-fabric-four-source-v1",)


class PerceptionFabricSimulationError(RuntimeError):
    """Raised only when the deterministic integration scenario violates its invariants."""


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionFabricSimulationReport:
    source_ids: tuple[str, ...]
    dashboard_state_sha256: str
    permission_snapshot_sha256s: tuple[str, ...]
    broker_state_sha256s: tuple[str, ...]
    retina_assessment_sha256s: tuple[str, ...]
    observed_claim_sha256s: tuple[str, ...]
    observation_window_sha256: str
    multiview_overlay_sha256: str
    disagreement_atom_ids: tuple[str, ...]
    visual_need_sha256: str
    observe_intent_sha256s: tuple[str, ...]
    worker_allocation_sha256: str
    selected_intent_ids: tuple[str, ...]
    bridge_envelope_sha256s: tuple[str, ...]
    audit_receipt_sha256s: tuple[str, ...]
    generic_vlm_calls: int
    raw_payload_persist_count: int
    remote_raw_payload_send_count: int

    schema: ClassVar[str] = SIMULATION_REPORT_SCHEMA
    classification: ClassVar[str] = (
        "SIMULATED_PERCEPTION_INTEGRATION_EVIDENCE_NOT_PHYSICAL_RUNTIME_WORLD_TRUTH_EFFECT_COMPLETION_OR_WHOLE_SYSTEM_ACCEPTANCE"
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "source_ids": list(self.source_ids),
            "source_count": len(self.source_ids),
            "dashboard_state_sha256": self.dashboard_state_sha256,
            "permission_snapshot_sha256s": list(self.permission_snapshot_sha256s),
            "broker_state_sha256s": list(self.broker_state_sha256s),
            "retina_assessment_sha256s": list(self.retina_assessment_sha256s),
            "observed_claim_sha256s": list(self.observed_claim_sha256s),
            "observation_window_sha256": self.observation_window_sha256,
            "multiview_overlay_sha256": self.multiview_overlay_sha256,
            "disagreement_atom_ids": list(self.disagreement_atom_ids),
            "visual_need_sha256": self.visual_need_sha256,
            "observe_intent_sha256s": list(self.observe_intent_sha256s),
            "worker_allocation_sha256": self.worker_allocation_sha256,
            "selected_intent_ids": list(self.selected_intent_ids),
            "active_worker_count": len(self.selected_intent_ids),
            "bridge_envelope_sha256s": list(self.bridge_envelope_sha256s),
            "audit_receipt_sha256s": list(self.audit_receipt_sha256s),
            "generic_vlm_calls": self.generic_vlm_calls,
            "raw_payload_persist_count": self.raw_payload_persist_count,
            "remote_raw_payload_send_count": self.remote_raw_payload_send_count,
            "physical_sensor_runtime": False,
            "network_bridge_runtime": False,
            "world_truth_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "whole_system_acceptance": False,
        }


def _sources() -> tuple[PerceptionSource, ...]:
    return (
        PerceptionSource(
            source_id="camera:front",
            kind=SourceKind.CAMERA,
            clock_domain="sim:local",
            capture_owner_id="capture-owner:camera:front",
            provenance_refs=PROVENANCE,
        ),
        PerceptionSource(
            source_id="display:1",
            kind=SourceKind.DISPLAY,
            clock_domain="sim:local",
            capture_owner_id="capture-owner:display:1",
            provenance_refs=PROVENANCE,
        ),
        PerceptionSource(
            source_id="browser:rendered",
            kind=SourceKind.BROWSER_RENDERED,
            clock_domain="sim:local",
            capture_owner_id="capture-owner:browser:rendered",
            provenance_refs=PROVENANCE,
        ),
        PerceptionSource(
            source_id="browser:structural",
            kind=SourceKind.BROWSER_STRUCTURAL,
            clock_domain="sim:local",
            capture_owner_id="capture-owner:browser:structural",
            provenance_refs=PROVENANCE,
        ),
    )


def _dashboard_and_snapshots(
    sources: tuple[PerceptionSource, ...],
) -> tuple[PerceptionDashboardState, tuple[PerceptionCapabilitySnapshot, ...]]:
    state = create_dashboard_state(
        state_id="dashboard:perception-fabric-sim",
        max_active_cortex_workers=4,
        provenance_refs=PROVENANCE,
    )
    caps = (
        PerceptionCapability.SEE,
        PerceptionCapability.ANALYZE,
        PerceptionCapability.MEMORY,
    )
    for source in sources:
        state = set_source_policy(
            state=state,
            source_id=source.source_id,
            enabled=True,
            capabilities=caps,
            provenance_refs=PROVENANCE,
        )
    snapshots = tuple(
        capability_snapshot_from_dashboard(
            state=state,
            source_id=source.source_id,
            valid_from_monotonic_ns=10,
            expires_monotonic_ns=10_000,
            provenance_refs=PROVENANCE,
        )
        for source in sources
    )
    return state, snapshots


def _capture_and_retina(
    sources: tuple[PerceptionSource, ...],
) -> tuple[tuple[CaptureBrokerState, ...], tuple[RetinaAssessment, ...]]:
    retina_policy = RetinaPolicy(
        policy_id="retina:sim-policy",
        generation=1,
        min_quality_micros=500_000,
        salient_delta_micros=100_000,
        max_interframe_gap_ns=1_000,
        provenance_refs=PROVENANCE,
    )
    brokers: list[CaptureBrokerState] = []
    assessments: list[RetinaAssessment] = []
    for index, source in enumerate(sources):
        baseline_payload = _sha(f"{source.source_id}:baseline")
        changed_payload = _sha(f"{source.source_id}:changed")
        broker = create_capture_broker(
            broker_id=f"broker:{source.source_id}",
            source_id=source.source_id,
            capture_owner_id=source.capture_owner_id,
            capacity=2,
            provenance_refs=PROVENANCE,
        )
        baseline_ref = CaptureFrameRef(
            frame_ref_id=f"{source.source_id}:frame:0",
            source_id=source.source_id,
            source_sequence=0,
            captured_monotonic_ns=100,
            payload_sha256=baseline_payload,
            provenance_refs=PROVENANCE,
        )
        current_ref = CaptureFrameRef(
            frame_ref_id=f"{source.source_id}:frame:1",
            source_id=source.source_id,
            source_sequence=1,
            captured_monotonic_ns=200,
            payload_sha256=changed_payload,
            provenance_refs=PROVENANCE,
        )
        broker = publish_frame_ref(
            state=broker,
            publisher_owner_id=source.capture_owner_id,
            frame_ref=baseline_ref,
        )
        broker = publish_frame_ref(
            state=broker,
            publisher_owner_id=source.capture_owner_id,
            frame_ref=current_ref,
        )
        brokers.append(broker)

        previous = RetinaFrameSignal(
            frame_id=baseline_ref.frame_ref_id,
            stream_id=source.source_id,
            generation=0,
            captured_monotonic_ns=baseline_ref.captured_monotonic_ns,
            frame_sha256=baseline_ref.payload_sha256,
            continuity_epoch="sim:epoch:1",
            quality_micros=900_000,
            delta_micros=None,
            delta_reference_frame_id=None,
            delta_reference_frame_sha256=None,
            provenance_refs=PROVENANCE,
        )
        current = RetinaFrameSignal(
            frame_id=current_ref.frame_ref_id,
            stream_id=source.source_id,
            generation=1,
            captured_monotonic_ns=current_ref.captured_monotonic_ns,
            frame_sha256=current_ref.payload_sha256,
            continuity_epoch="sim:epoch:1",
            quality_micros=900_000,
            delta_micros=300_000 + index,
            delta_reference_frame_id=baseline_ref.frame_ref_id,
            delta_reference_frame_sha256=baseline_ref.payload_sha256,
            provenance_refs=PROVENANCE,
        )
        assessments.append(
            assess_retina_transition(
                assessment_id=f"retina-assessment:{source.source_id}:1",
                current=current,
                expected_current_signal_sha256=current.sha256(),
                previous=previous,
                expected_previous_signal_sha256=previous.sha256(),
                policy=retina_policy,
                expected_policy_sha256=retina_policy.sha256(),
                provenance_refs=PROVENANCE,
            )
        )
    return tuple(brokers), tuple(assessments)


def _perception_registry() -> PerceptionPolicyRegistry:
    head = PerceptionHeadPolicy(
        head_id="local-semantic-head",
        generation=1,
        tier="ON",
        enabled=True,
        memory_allowed=True,
        provenance_refs=PROVENANCE,
    )
    dependency = PerceptionDependency(
        head_id="local-semantic-head",
        depends_on=(),
    )
    return PerceptionPolicyRegistry(
        registry_id="perception-registry:sim",
        generation=1,
        heads=(head,),
        dependencies=(dependency,),
        provenance_refs=PROVENANCE,
    )


def _claims(
    sources: tuple[PerceptionSource, ...],
    assessments: tuple[RetinaAssessment, ...],
) -> tuple[EpistemicPerceptClaim, ...]:
    registry = _perception_registry()
    values = (
        {"presence": "user_present"},
        {"active_app": "browser"},
        {"ui_submit": "occluded"},
        {"ui_submit": "present_in_structure"},
    )
    semantic_keys = (
        "person.presence",
        "screen.active_app",
        "ui.submit",
        "ui.submit",
    )
    modalities = ("visual", "visual", "visual-rendered", "browser-structural")
    claims: list[EpistemicPerceptClaim] = []
    for index, (source, assessment) in enumerate(zip(sources, assessments)):
        if not assessment.percept_event_candidate:
            raise PerceptionFabricSimulationError(
                f"expected salient Retina event for {source.source_id}"
            )
        result = evaluate_perception_head(
            evaluation_id=f"perception-eval:{source.source_id}:1",
            registry=registry,
            expected_registry_sha256=registry.sha256(),
            head_id="local-semantic-head",
            compute_fn=lambda value=values[index]: (value, 900_000),
            provenance_refs=(
                *PROVENANCE,
                f"retina-assessment-sha256:{assessment.sha256()}",
            ),
        )
        if result.status != "OK" or not result.egress_allowed:
            raise PerceptionFabricSimulationError(
                f"expected allowed perception result for {source.source_id}"
            )
        claims.append(
            EpistemicPerceptClaim(
                claim_id=f"observed:{source.source_id}:1",
                semantic_key=semantic_keys[index],
                modality=modalities[index],
                epistemic_type="OBSERVED",
                value=result.value,
                confidence_micros=result.confidence_micros or 0,
                source_generation=1,
                source_time_ns=200,
                upstream_retina_assessment_sha256=assessment.sha256(),
                provenance_refs=(
                    *PROVENANCE,
                    f"source:{source.source_id}",
                    f"retina-assessment-sha256:{assessment.sha256()}",
                    f"perception-control-result-sha256:{result.sha256()}",
                ),
            )
        )
    return tuple(claims)


def _temporal_window(
    sources: tuple[PerceptionSource, ...],
    claims: tuple[EpistemicPerceptClaim, ...],
) -> ObservationWindow:
    refs = tuple(
        bind_observed_claim(
            claim=claim,
            expected_claim_sha256=claim.sha256(),
            ref_id=f"temporal:{source.source_id}:1",
            source_id=source.source_id,
            source_sequence=1,
            clock_domain=source.clock_domain,
            reference_offset_ns=0,
            clock_uncertainty_ns=0,
            max_freshness_ns=500,
            provenance_refs=PROVENANCE,
        )
        for source, claim in zip(sources, claims)
    )
    return build_observation_window(
        refs=refs,
        reference_now_ns=250,
        max_join_skew_ns=20,
        max_clock_uncertainty_ns=10,
        provenance_refs=PROVENANCE,
    )


def _world_and_visual_need(
    claims: tuple[EpistemicPerceptClaim, ...],
) -> tuple[WorldSlice, MultiViewOverlay, VisualNeed]:
    rendered_claim = claims[2]
    structural_claim = claims[3]
    target = WorldAtom(
        atom_id="ui.actionable",
        generation=1,
        vector_space_version="perception-sim:v1",
        vector=(0, 1),
        epistemic_origin=EpistemicOrigin.INFERRED,
        knowledge_state=KnowledgeState.UNKNOWN,
        provenance_refs=PROVENANCE,
        evidence_refs=(),
        confidence_micros=None,
    )

    rendered_atom = WorldAtom(
        atom_id="ui.submit",
        generation=1,
        vector_space_version="perception-sim:v1",
        vector=(1, 0),
        epistemic_origin=EpistemicOrigin.OBSERVED,
        knowledge_state=KnowledgeState.UNKNOWN,
        provenance_refs=PROVENANCE,
        evidence_refs=(f"claim-sha256:{rendered_claim.sha256()}",),
        confidence_micros=None,
    )
    structural_atom = WorldAtom(
        atom_id="ui.submit",
        generation=1,
        vector_space_version="perception-sim:v1",
        vector=(1, 0),
        epistemic_origin=EpistemicOrigin.OBSERVED,
        knowledge_state=KnowledgeState.KNOWN,
        provenance_refs=PROVENANCE,
        evidence_refs=(f"claim-sha256:{structural_claim.sha256()}",),
        confidence_micros=structural_claim.confidence_micros,
    )
    rendered_need = WorldNeed(
        need_id="world-need:rendered",
        cycle_id="cycle:perception-sim",
        generation=1,
        vector_space_version="perception-sim:v1",
        start_atom_ids=("ui.submit",),
        target_atom_ids=("ui.actionable",),
        max_depth=0,
        max_atoms=2,
        provenance_refs=(
            *PROVENANCE,
            f"claim-sha256:{rendered_claim.sha256()}",
        ),
    )
    structural_need = WorldNeed(
        need_id="world-need:structural",
        cycle_id="cycle:perception-sim",
        generation=1,
        vector_space_version="perception-sim:v1",
        start_atom_ids=("ui.submit",),
        target_atom_ids=("ui.actionable",),
        max_depth=0,
        max_atoms=2,
        provenance_refs=(
            *PROVENANCE,
            f"claim-sha256:{structural_claim.sha256()}",
        ),
    )
    rendered_slice = materialize_world_slice(
        atoms=(rendered_atom, target),
        operators=(),
        activations=(),
        need=rendered_need,
    )
    structural_slice = materialize_world_slice(
        atoms=(structural_atom, target),
        operators=(),
        activations=(),
        need=structural_need,
    )
    rendered_view = WorldView(
        view_id="view:browser-rendered",
        world_slice=rendered_slice,
        atom_states=(
            ViewAtomState(
                atom_id="ui.submit",
                knowledge_state=KnowledgeState.UNKNOWN,
                provenance_refs=(f"claim-sha256:{rendered_claim.sha256()}",),
            ),
        ),
        provenance_refs=PROVENANCE,
    )
    structural_view = WorldView(
        view_id="view:browser-structural",
        world_slice=structural_slice,
        atom_states=(
            ViewAtomState(
                atom_id="ui.submit",
                knowledge_state=KnowledgeState.KNOWN,
                provenance_refs=(f"claim-sha256:{structural_claim.sha256()}",),
            ),
        ),
        provenance_refs=PROVENANCE,
    )
    overlay = compare_world_views(views=(rendered_view, structural_view))
    visual_need = plan_visual_need(
        world_slice=rendered_slice,
        visualizable_atom_ids=("ui.actionable", "ui.submit"),
        overlay=overlay,
        max_targets=4,
        provenance_refs=PROVENANCE,
    )
    if visual_need is None:
        raise PerceptionFabricSimulationError("expected VisualNeed from unresolved/disagreed world state")
    return rendered_slice, overlay, visual_need


def _intents_and_bridge(
    *,
    sources: tuple[PerceptionSource, ...],
    snapshots: tuple[PerceptionCapabilitySnapshot, ...],
    visual_need: VisualNeed,
    claims: tuple[EpistemicPerceptClaim, ...],
) -> tuple[
    tuple[ObserveIntent, ...],
    PerceptionWorkerAllocation,
    tuple[PerceptionBridgeEnvelope, ...],
    tuple[PerceptionAuditReceipt, ...],
]:
    intents = tuple(
        compile_observe_intent(
            visual_need=visual_need,
            source=source,
            permission_snapshot=snapshot,
            requested_head_ids=("local-semantic-head",),
            roi_ref="roi:disagreement-focus",
            required_freshness_ns=200,
            expires_monotonic_ns=1_000,
            priority_micros=900_000 - index,
            max_work_units=10,
            allow_remote_frame=False,
            allow_external_vlm=False,
            provenance_refs=PROVENANCE,
        )
        for index, (source, snapshot) in enumerate(zip(sources, snapshots))
    )
    worker_policy = PerceptionWorkerPolicy(
        policy_id="perception-workers:sim",
        generation=1,
        max_active_workers=4,
        max_total_work_units=40,
        provenance_refs=PROVENANCE,
    )
    allocation = allocate_perception_workers(
        intents=intents,
        policy=worker_policy,
        permission_snapshots=snapshots,
        now_monotonic_ns=300,
    )
    if len(allocation.selected_intent_ids) != 4:
        raise PerceptionFabricSimulationError("expected all four simulated intents to be selected")

    envelopes: list[PerceptionBridgeEnvelope] = []
    receipts: list[PerceptionAuditReceipt] = []
    for intent, snapshot, claim in zip(intents, snapshots, claims):
        envelopes.append(
            build_bridge_envelope(
                intent=intent,
                snapshot=snapshot,
                payload_kind=BridgePayloadKind.TYPED_EVENT,
                payload_sha256=claim.sha256(),
                external_vlm_requested=False,
                now_monotonic_ns=300,
                provenance_refs=PROVENANCE,
            )
        )
        receipts.append(
            build_audit_receipt(
                intent=intent,
                snapshot=snapshot,
                outcome=AuditOutcome.EXECUTED,
                executed_head_ids=("local-semantic-head",),
                raw_payload_persisted=False,
                remote_raw_payload_sent=False,
                external_vlm_called=False,
                event_monotonic_ns=310,
                reason="simulated-typed-local-perception-complete",
                provenance_refs=PROVENANCE,
            )
        )
    return intents, allocation, tuple(envelopes), tuple(receipts)


def run_four_source_perception_simulation() -> PerceptionFabricSimulationReport:
    """Execute the deterministic host-independent four-source Perception Fabric loop."""
    sources = _sources()
    dashboard, snapshots = _dashboard_and_snapshots(sources)
    brokers, assessments = _capture_and_retina(sources)
    claims = _claims(sources, assessments)
    window = _temporal_window(sources, claims)
    if len(window.current_ref_ids) != 4 or window.stale_ref_ids:
        raise PerceptionFabricSimulationError("expected four current and zero stale temporal refs")
    _, overlay, visual_need = _world_and_visual_need(claims)
    if "ui.submit" not in overlay.disagreement_atom_ids:
        raise PerceptionFabricSimulationError("expected rendered/structural disagreement on ui.submit")
    intents, allocation, envelopes, receipts = _intents_and_bridge(
        sources=sources,
        snapshots=snapshots,
        visual_need=visual_need,
        claims=claims,
    )
    generic_vlm_calls = sum(1 for receipt in receipts if receipt.external_vlm_called)
    raw_persist = sum(1 for receipt in receipts if receipt.raw_payload_persisted)
    raw_remote = sum(1 for receipt in receipts if receipt.remote_raw_payload_sent)
    if generic_vlm_calls or raw_persist or raw_remote:
        raise PerceptionFabricSimulationError("default simulation must remain typed/local with zero VLM/raw persistence/remote raw")
    return PerceptionFabricSimulationReport(
        source_ids=tuple(source.source_id for source in sources),
        dashboard_state_sha256=dashboard.sha256(),
        permission_snapshot_sha256s=tuple(snapshot.sha256() for snapshot in snapshots),
        broker_state_sha256s=tuple(broker.sha256() for broker in brokers),
        retina_assessment_sha256s=tuple(item.sha256() for item in assessments),
        observed_claim_sha256s=tuple(item.sha256() for item in claims),
        observation_window_sha256=window.sha256(),
        multiview_overlay_sha256=overlay.sha256(),
        disagreement_atom_ids=overlay.disagreement_atom_ids,
        visual_need_sha256=visual_need.sha256(),
        observe_intent_sha256s=tuple(item.sha256() for item in intents),
        worker_allocation_sha256=allocation.sha256(),
        selected_intent_ids=allocation.selected_intent_ids,
        bridge_envelope_sha256s=tuple(item.sha256() for item in envelopes),
        audit_receipt_sha256s=tuple(item.sha256() for item in receipts),
        generic_vlm_calls=generic_vlm_calls,
        raw_payload_persist_count=raw_persist,
        remote_raw_payload_send_count=raw_remote,
    )


__all__ = [
    "PerceptionFabricSimulationError",
    "PerceptionFabricSimulationReport",
    "SIMULATION_REPORT_SCHEMA",
    "run_four_source_perception_simulation",
]
