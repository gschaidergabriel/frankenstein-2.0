from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.child_handoff_reconcile import (
    HANDOFF_CLASSIFICATION,
    RECONCILE_CLASSIFICATION,
    ChildHandoffEvidence,
    ChildHandoffReconcileError,
    ChildReconcileEvidence,
    verify_child_handoff,
    verify_child_reconcile,
)
from frankenstein2.deferred_return import DeferredReturnEnvelope
from frankenstein2.direct_delegate_router import (
    DELEGATE_BUILD,
    DIRECT_SMALL,
    RouteCandidate,
    RoutingPolicy,
    TaskRouteRequest,
    route_task,
)
from frankenstein2.native_child_abi import ABI_VERSION, ChildResourceBudget, NativeChildRequest
from frankenstein2.native_child_binding import NativeChildBinding
from frankenstein2.situation_frame import CycleContract, SituationFrame


class ChildHandoffReconcileTests(unittest.TestCase):
    def make_cycle(self) -> CycleContract:
        frame = SituationFrame.create(
            frame_id="frame-602",
            cycle_id="cycle-602",
            generation=7,
            situation_epoch=11,
            agency_state_ref="agency:602",
            agency_state_generation=2,
            agency_state_sha256="a" * 64,
            authority_scope_refs=("authority:effectgate-external",),
            provenance_refs=("receipt:frame-602",),
        )
        return CycleContract.for_frame(
            frame,
            contract_id="cycle-contract-602",
            cycle_generation=3,
            max_grid_cells=10,
            allowed_exits=("ACT", "ASK", "HOLD", "WAIT"),
            continuation_refs=("checkpoint:602",),
            provenance_refs=("receipt:cycle-602",),
        )

    def make_route(self, *, delegated: bool = True, task_sha256: str = "b" * 64) -> RouteCandidate:
        cycle = self.make_cycle()
        request = TaskRouteRequest.for_cycle(
            cycle,
            task_id="task-602",
            task_generation=4,
            task_sha256=task_sha256,
            estimated_work_units=9 if delegated else 4,
            estimated_context_tokens=1024,
            provenance_refs=("task-source:602",),
        )
        policy = RoutingPolicy.create(
            policy_id="router-policy-602",
            generation=2,
            max_direct_work_units=8,
            max_direct_context_tokens=4096,
            allowed_routes=(DIRECT_SMALL, DELEGATE_BUILD),
            provenance_refs=("policy-source:602",),
        )
        return route_task(cycle_contract=cycle, request=request, policy=policy)

    def make_pending_binding(self, *, task_id: str = "task-602") -> NativeChildBinding:
        parent = CausalIdentity(
            session_id="session-602",
            agent_id="parent-agent",
            task_id=task_id,
            turn_id="turn-parent",
            causal_id="causal-parent-602",
            generation=7,
        )
        child = parent.derive(
            causal_id="causal-child-602",
            generation=8,
            agent_id="child-agent",
            task_id="child-task-602",
            turn_id="turn-child",
        )
        return NativeChildBinding(
            workpackage_id="F2-WP-602",
            workpackage_generation=1,
            claim_id="F2-WP-602-G1-GPT56SOL-HANDOFF-RECONCILE-EVIDENCE-20260829",
            parent=parent,
            invocation_id="invocation-602",
            tool_use_id="tool-use-602",
            delegation_id="delegation-602",
            child=child,
        )

    def make_child_request(
        self,
        binding: NativeChildBinding,
        *,
        payload_sha256: str = "b" * 64,
    ) -> NativeChildRequest:
        budget = ChildResourceBudget(
            max_work_units=64,
            max_duration_ms=5000,
            max_output_bytes=65536,
            max_nested_depth=2,
            max_tool_calls=4,
        )
        return NativeChildRequest(
            request_id="child-request-602",
            request_generation=1,
            abi_version=ABI_VERSION,
            binding=binding,
            binding_id=binding.binding_id(),
            binding_sha256=binding.sha256(),
            child_runtime_class="python-native-child",
            payload_ref="payload:task-602",
            payload_sha256=payload_sha256,
            input_refs=("input:602:a", "input:602:b"),
            requested_capability_refs=("cap:memory-read", "cap:tool-visible"),
            resource_budget=budget,
        )

    def make_handoff(self) -> tuple[ChildHandoffEvidence, NativeChildBinding]:
        route = self.make_route(delegated=True)
        pending = self.make_pending_binding()
        request = self.make_child_request(pending)
        return ChildHandoffEvidence.create(route_candidate=route, child_request=request), pending

    def make_result_binding(self, pending: NativeChildBinding, *, result_id: str = "result-602", digest: str = "d" * 64) -> NativeChildBinding:
        return pending.bind_result(
            invocation_id=pending.invocation_id,
            delegation_id=pending.delegation_id,
            child_causal_id=pending.child.causal_id,
            result_id=result_id,
            result_sha256=digest,
        )

    def make_return(self, result_binding: NativeChildBinding, *, return_id: str = "return-602") -> DeferredReturnEnvelope:
        parent = result_binding.parent
        child = result_binding.child
        resume = child.derive(
            causal_id="causal-resume-602",
            generation=child.generation + 1,
            session_id=parent.session_id,
            agent_id=parent.agent_id,
            task_id=parent.task_id,
            turn_id="turn-resume",
        )
        return DeferredReturnEnvelope(return_id=return_id, binding=result_binding, resume=resume)

    def test_handoff_happy_path_roundtrip_and_consumer_verification(self) -> None:
        handoff, _ = self.make_handoff()
        rebuilt = ChildHandoffEvidence.from_mapping(handoff.as_dict())
        self.assertEqual(rebuilt, handoff)
        self.assertEqual(rebuilt.sha256(), handoff.sha256())
        self.assertIs(
            verify_child_handoff(
                handoff,
                expected_handoff_id=handoff.handoff_id,
                expected_handoff_sha256=handoff.sha256(),
            ),
            handoff,
        )
        self.assertTrue(handoff.handoff_id.startswith("handoff:"))

    def test_direct_small_route_cannot_be_mislabeled_as_child_handoff(self) -> None:
        route = self.make_route(delegated=False)
        pending = self.make_pending_binding()
        request = self.make_child_request(pending)
        self.assertEqual(route.selected_route, DIRECT_SMALL)
        with self.assertRaises(ChildHandoffReconcileError):
            ChildHandoffEvidence.create(route_candidate=route, child_request=request)

    def test_handoff_requires_exact_routed_task_identity(self) -> None:
        route = self.make_route(delegated=True)
        pending = self.make_pending_binding(task_id="other-task")
        request = self.make_child_request(pending)
        with self.assertRaises(ChildHandoffReconcileError):
            ChildHandoffEvidence.create(route_candidate=route, child_request=request)

    def test_handoff_requires_routed_task_digest_to_equal_payload_digest(self) -> None:
        route = self.make_route(delegated=True)
        pending = self.make_pending_binding()
        request = self.make_child_request(pending, payload_sha256="e" * 64)
        with self.assertRaises(ChildHandoffReconcileError):
            ChildHandoffEvidence.create(route_candidate=route, child_request=request)

    def test_handoff_identity_and_nested_digests_are_content_bound(self) -> None:
        handoff, _ = self.make_handoff()
        for replacement in (
            {"handoff_id": "handoff:" + "0" * 64},
            {"route_candidate_sha256": "e" * 64},
            {"child_request_sha256": "f" * 64},
        ):
            with self.subTest(replacement=replacement):
                with self.assertRaises(ChildHandoffReconcileError):
                    replace(handoff, **replacement)

    def test_handoff_requires_exact_concrete_dependency_types(self) -> None:
        handoff, _ = self.make_handoff()

        class RouteSubclass(RouteCandidate):
            pass

        forged_route = RouteSubclass(**handoff.route_candidate.as_dict())
        with self.assertRaises(ChildHandoffReconcileError):
            ChildHandoffEvidence.create(route_candidate=forged_route, child_request=handoff.child_request)

        class RequestSubclass(NativeChildRequest):
            pass

        forged_request = RequestSubclass(**{
            **handoff.child_request.__dict__
        }) if hasattr(handoff.child_request, "__dict__") else None
        if forged_request is not None:
            with self.assertRaises(ChildHandoffReconcileError):
                ChildHandoffEvidence.create(route_candidate=handoff.route_candidate, child_request=forged_request)

    def test_handoff_mapping_rejects_unknown_and_noncanonical_route_reasons(self) -> None:
        handoff, _ = self.make_handoff()
        raw = handoff.as_dict()
        raw["authority"] = "forged"
        with self.assertRaises(ChildHandoffReconcileError):
            ChildHandoffEvidence.from_mapping(raw)

        raw = handoff.as_dict()
        raw["route_candidate"]["reason_codes"] = [
            "WORK_UNITS_EXCEED_DIRECT_BOUND",
            "WORK_UNITS_EXCEED_DIRECT_BOUND",
        ]
        with self.assertRaises(ChildHandoffReconcileError):
            ChildHandoffEvidence.from_mapping(raw)

    def test_reconcile_happy_path_roundtrip_and_consumer_verification(self) -> None:
        handoff, pending = self.make_handoff()
        result_binding = self.make_result_binding(pending)
        deferred = self.make_return(result_binding)
        reconcile = ChildReconcileEvidence.create(
            handoff=handoff,
            result_binding=result_binding,
            deferred_return=deferred,
        )
        rebuilt = ChildReconcileEvidence.from_mapping(reconcile.as_dict())
        self.assertEqual(rebuilt, reconcile)
        self.assertEqual(reconcile.result_id, "result-602")
        self.assertEqual(reconcile.result_sha256, "d" * 64)
        self.assertTrue(reconcile.reconcile_id.startswith("reconcile:"))
        self.assertIs(
            verify_child_reconcile(
                reconcile,
                expected_reconcile_id=reconcile.reconcile_id,
                expected_reconcile_sha256=reconcile.sha256(),
            ),
            reconcile,
        )

    def test_reconcile_requires_result_bound_binding(self) -> None:
        handoff, pending = self.make_handoff()
        # DeferredReturnEnvelope itself correctly refuses a pending binding, so exercise
        # the reconcile boundary using a valid return but the pending binding argument.
        result_binding = self.make_result_binding(pending)
        deferred = self.make_return(result_binding)
        with self.assertRaises(ChildHandoffReconcileError):
            ChildReconcileEvidence.create(
                handoff=handoff,
                result_binding=pending,
                deferred_return=deferred,
            )

    def test_reconcile_preserves_stable_wp102_binding_identity(self) -> None:
        handoff, pending = self.make_handoff()
        result_binding = self.make_result_binding(pending)
        deferred = self.make_return(result_binding)
        reconcile = ChildReconcileEvidence.create(
            handoff=handoff,
            result_binding=result_binding,
            deferred_return=deferred,
        )
        self.assertEqual(result_binding.binding_id(), handoff.child_request.binding_id)
        self.assertNotEqual(result_binding.sha256(), handoff.child_request.binding_sha256)
        self.assertEqual(reconcile.result_binding.binding_id(), handoff.child_request.binding_id)

    def test_reconcile_rejects_different_result_for_same_stable_binding(self) -> None:
        handoff, pending = self.make_handoff()
        first = self.make_result_binding(pending, result_id="result-first", digest="d" * 64)
        second = self.make_result_binding(pending, result_id="result-second", digest="e" * 64)
        deferred = self.make_return(first)
        self.assertEqual(first.binding_id(), second.binding_id())
        with self.assertRaises(ChildHandoffReconcileError):
            ChildReconcileEvidence.create(
                handoff=handoff,
                result_binding=second,
                deferred_return=deferred,
            )

    def test_reconcile_rejects_return_from_different_binding_lineage(self) -> None:
        handoff, pending = self.make_handoff()
        result_binding = self.make_result_binding(pending)
        other_parent = CausalIdentity(
            session_id="session-other",
            agent_id="parent-agent",
            task_id="task-602",
            turn_id="turn-parent",
            causal_id="causal-parent-other",
            generation=7,
        )
        other_child = other_parent.derive(
            causal_id="causal-child-other",
            generation=8,
            agent_id="child-agent",
            task_id="child-task-602",
            turn_id="turn-child",
        )
        other_pending = NativeChildBinding(
            workpackage_id="F2-WP-602",
            workpackage_generation=1,
            claim_id="F2-WP-602-G1-GPT56SOL-HANDOFF-RECONCILE-EVIDENCE-20260829",
            parent=other_parent,
            invocation_id="invocation-other",
            tool_use_id="tool-use-other",
            delegation_id="delegation-other",
            child=other_child,
        )
        other_result = self.make_result_binding(other_pending)
        other_return = self.make_return(other_result, return_id="return-other")
        with self.assertRaises(ChildHandoffReconcileError):
            ChildReconcileEvidence.create(
                handoff=handoff,
                result_binding=result_binding,
                deferred_return=other_return,
            )

    def test_reconcile_id_and_all_nested_digests_fail_closed_on_tamper(self) -> None:
        handoff, pending = self.make_handoff()
        result_binding = self.make_result_binding(pending)
        deferred = self.make_return(result_binding)
        reconcile = ChildReconcileEvidence.create(
            handoff=handoff,
            result_binding=result_binding,
            deferred_return=deferred,
        )
        for replacement in (
            {"reconcile_id": "reconcile:" + "0" * 64},
            {"handoff_sha256": "a" * 64},
            {"result_binding_sha256": "b" * 64},
            {"deferred_return_sha256": "c" * 64},
        ):
            with self.subTest(replacement=replacement):
                with self.assertRaises(ChildHandoffReconcileError):
                    replace(reconcile, **replacement)

    def test_reconcile_mapping_rejects_unknown_fields(self) -> None:
        handoff, pending = self.make_handoff()
        result_binding = self.make_result_binding(pending)
        deferred = self.make_return(result_binding)
        reconcile = ChildReconcileEvidence.create(
            handoff=handoff,
            result_binding=result_binding,
            deferred_return=deferred,
        )
        raw = reconcile.as_dict()
        raw["completion"] = True
        with self.assertRaises(ChildHandoffReconcileError):
            ChildReconcileEvidence.from_mapping(raw)

    def test_evidence_classifications_do_not_mint_runtime_authority(self) -> None:
        handoff, pending = self.make_handoff()
        result_binding = self.make_result_binding(pending)
        reconcile = ChildReconcileEvidence.create(
            handoff=handoff,
            result_binding=result_binding,
            deferred_return=self.make_return(result_binding),
        )
        self.assertEqual(handoff.classification, HANDOFF_CLASSIFICATION)
        self.assertEqual(reconcile.classification, RECONCILE_CLASSIFICATION)
        for fields in (handoff.as_dict(), reconcile.as_dict()):
            for forbidden in (
                "delivery_ack",
                "execution_success",
                "effect_authority",
                "completion_authority",
                "world_fact",
                "unifieddb_write",
            ):
                self.assertNotIn(forbidden, fields)


if __name__ == "__main__":
    unittest.main()
