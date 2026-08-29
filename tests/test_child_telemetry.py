from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.child_handoff_reconcile import ChildHandoffEvidence, ChildReconcileEvidence
from frankenstein2.child_telemetry import (
    TELEMETRY_CLASSIFICATION,
    ChildTelemetryError,
    ChildTelemetrySample,
    verify_child_telemetry,
)
from frankenstein2.deferred_return import DeferredReturnEnvelope
from frankenstein2.direct_delegate_router import DELEGATE_BUILD, DIRECT_SMALL, RoutingPolicy, TaskRouteRequest, route_task
from frankenstein2.native_child_abi import ABI_VERSION, ChildResourceBudget, NativeChildRequest
from frankenstein2.native_child_binding import NativeChildBinding
from frankenstein2.situation_frame import CycleContract, SituationFrame


class ChildTelemetryTests(unittest.TestCase):
    def make_reconcile(self) -> ChildReconcileEvidence:
        frame = SituationFrame.create(
            frame_id="frame-605",
            cycle_id="cycle-605",
            generation=7,
            situation_epoch=11,
            agency_state_ref="agency:605",
            agency_state_generation=2,
            agency_state_sha256="a" * 64,
            authority_scope_refs=("authority:effectgate-external",),
            provenance_refs=("receipt:frame-605",),
        )
        cycle = CycleContract.for_frame(
            frame,
            contract_id="cycle-contract-605",
            cycle_generation=3,
            max_grid_cells=10,
            allowed_exits=("ACT", "ASK", "HOLD", "WAIT"),
            continuation_refs=("checkpoint:605",),
            provenance_refs=("receipt:cycle-605",),
        )
        request = TaskRouteRequest.for_cycle(
            cycle,
            task_id="task-605",
            task_generation=4,
            task_sha256="b" * 64,
            estimated_work_units=9,
            estimated_context_tokens=1024,
            provenance_refs=("task-source:605",),
        )
        policy = RoutingPolicy.create(
            policy_id="router-policy-605",
            generation=2,
            max_direct_work_units=8,
            max_direct_context_tokens=4096,
            allowed_routes=(DIRECT_SMALL, DELEGATE_BUILD),
            provenance_refs=("policy-source:605",),
        )
        route = route_task(cycle_contract=cycle, request=request, policy=policy)
        self.assertEqual(route.selected_route, DELEGATE_BUILD)

        parent = CausalIdentity(
            session_id="session-605",
            agent_id="parent-agent",
            task_id="task-605",
            turn_id="turn-parent",
            causal_id="causal-parent-605",
            generation=7,
        )
        child = parent.derive(
            causal_id="causal-child-605",
            generation=8,
            agent_id="child-agent",
            task_id="child-task-605",
            turn_id="turn-child",
        )
        pending = NativeChildBinding(
            workpackage_id="F2-WP-605",
            workpackage_generation=1,
            claim_id="F2-WP-605-G1-GPT56SOL-CHILD-TELEMETRY-20260829",
            parent=parent,
            invocation_id="invocation-605",
            tool_use_id="tool-use-605",
            delegation_id="delegation-605",
            child=child,
        )
        budget = ChildResourceBudget(
            max_work_units=64,
            max_duration_ms=5000,
            max_output_bytes=65536,
            max_nested_depth=2,
            max_tool_calls=4,
        )
        child_request = NativeChildRequest(
            request_id="child-request-605",
            request_generation=1,
            abi_version=ABI_VERSION,
            binding=pending,
            binding_id=pending.binding_id(),
            binding_sha256=pending.sha256(),
            child_runtime_class="python-native-child",
            payload_ref="payload:task-605",
            payload_sha256="b" * 64,
            input_refs=("input:605:a", "input:605:b"),
            requested_capability_refs=("cap:memory-read", "cap:tool-visible"),
            resource_budget=budget,
        )
        handoff = ChildHandoffEvidence.create(route_candidate=route, child_request=child_request)
        result_binding = pending.bind_result(
            invocation_id=pending.invocation_id,
            delegation_id=pending.delegation_id,
            child_causal_id=pending.child.causal_id,
            result_id="result-605",
            result_sha256="d" * 64,
        )
        resume = child.derive(
            causal_id="causal-resume-605",
            generation=child.generation + 1,
            session_id=parent.session_id,
            agent_id=parent.agent_id,
            task_id=parent.task_id,
            turn_id="turn-resume",
        )
        deferred = DeferredReturnEnvelope(return_id="return-605", binding=result_binding, resume=resume)
        return ChildReconcileEvidence.create(
            handoff=handoff,
            result_binding=result_binding,
            deferred_return=deferred,
        )

    def make_sample(self) -> ChildTelemetrySample:
        return ChildTelemetrySample.create(
            reconcile=self.make_reconcile(),
            started_monotonic_ns=1_000_000,
            finished_monotonic_ns=1_750_000,
            cpu_time_ns=500_000,
            peak_rss_bytes=8_388_608,
            input_tokens=321,
            output_tokens=87,
            tool_calls=2,
            work_units=9,
            quality_evidence_refs=("benchmark:child-quality-605", "receipt:heldout-605"),
            provenance_refs=("measurement:runner-605",),
        )

    def test_happy_path_roundtrip_and_consumer_verification(self) -> None:
        sample = self.make_sample()
        rebuilt = ChildTelemetrySample.from_mapping(sample.as_dict())
        self.assertEqual(rebuilt, sample)
        self.assertEqual(rebuilt.duration_ns, 750_000)
        self.assertEqual(rebuilt.result_id, "result-605")
        self.assertEqual(rebuilt.result_sha256, "d" * 64)
        self.assertEqual(rebuilt.classification, TELEMETRY_CLASSIFICATION)
        self.assertTrue(rebuilt.telemetry_id.startswith("child-telemetry:"))
        self.assertIs(
            verify_child_telemetry(
                sample,
                expected_telemetry_id=sample.telemetry_id,
                expected_telemetry_sha256=sample.sha256(),
                expected_reconcile_id=sample.reconcile.reconcile_id,
                expected_reconcile_sha256=sample.reconcile_sha256,
            ),
            sample,
        )

    def test_finish_before_start_fails_closed(self) -> None:
        with self.assertRaises(ChildTelemetryError):
            ChildTelemetrySample.create(
                reconcile=self.make_reconcile(),
                started_monotonic_ns=20,
                finished_monotonic_ns=19,
                provenance_refs=("measurement:runner-605",),
            )

    def test_negative_and_boolean_counters_fail_closed(self) -> None:
        for field, value in (("cpu_time_ns", -1), ("tool_calls", True), ("input_tokens", -5)):
            kwargs = dict(
                reconcile=self.make_reconcile(),
                started_monotonic_ns=1,
                finished_monotonic_ns=2,
                provenance_refs=("measurement:runner-605",),
            )
            kwargs[field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaises(ChildTelemetryError):
                    ChildTelemetrySample.create(**kwargs)

    def test_quality_refs_are_opaque_but_must_be_canonical(self) -> None:
        reconcile = self.make_reconcile()
        with self.assertRaises(ChildTelemetryError):
            ChildTelemetrySample.create(
                reconcile=reconcile,
                started_monotonic_ns=1,
                finished_monotonic_ns=2,
                quality_evidence_refs=("z", "a"),
                provenance_refs=("measurement:runner-605",),
            )
        with self.assertRaises(ChildTelemetryError):
            ChildTelemetrySample.create(
                reconcile=reconcile,
                started_monotonic_ns=1,
                finished_monotonic_ns=2,
                quality_evidence_refs=("a", "a"),
                provenance_refs=("measurement:runner-605",),
            )

    def test_provenance_is_required(self) -> None:
        with self.assertRaises(ChildTelemetryError):
            ChildTelemetrySample.create(
                reconcile=self.make_reconcile(),
                started_monotonic_ns=1,
                finished_monotonic_ns=2,
                provenance_refs=(),
            )

    def test_reconcile_digest_is_revalidated(self) -> None:
        sample = self.make_sample()
        with self.assertRaises(ChildTelemetryError):
            replace(sample, reconcile_sha256="e" * 64)

    def test_telemetry_identity_is_content_bound(self) -> None:
        sample = self.make_sample()
        with self.assertRaises(ChildTelemetryError):
            replace(sample, output_tokens=sample.output_tokens + 1)
        with self.assertRaises(ChildTelemetryError):
            replace(sample, telemetry_id="child-telemetry:" + "0" * 64)

    def test_mapping_rejects_unknown_fields(self) -> None:
        sample = self.make_sample()
        raw = sample.as_dict()
        raw["success"] = True
        with self.assertRaises(ChildTelemetryError):
            ChildTelemetrySample.from_mapping(raw)

    def test_consumer_verification_rejects_wrong_expected_identity(self) -> None:
        sample = self.make_sample()
        with self.assertRaises(ChildTelemetryError):
            verify_child_telemetry(
                sample,
                expected_telemetry_id="child-telemetry:" + "0" * 64,
                expected_telemetry_sha256=sample.sha256(),
                expected_reconcile_id=sample.reconcile.reconcile_id,
                expected_reconcile_sha256=sample.reconcile_sha256,
            )
        with self.assertRaises(ChildTelemetryError):
            verify_child_telemetry(
                sample,
                expected_telemetry_id=sample.telemetry_id,
                expected_telemetry_sha256=sample.sha256(),
                expected_reconcile_id=sample.reconcile.reconcile_id,
                expected_reconcile_sha256="f" * 64,
            )


if __name__ == "__main__":
    unittest.main()
