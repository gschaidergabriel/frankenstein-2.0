from __future__ import annotations

from dataclasses import fields, replace
import unittest

from frankenstein2.causal_identity import CausalIdentity
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
from frankenstein2.recursion_router import (
    R0,
    R1,
    R2,
    R3,
    RECURSION_ROUTE_CLASSIFICATION,
    RecursionNeed,
    RecursionPolicy,
    RecursionRouteCandidate,
    RecursionRouterError,
    route_recursion,
)
from frankenstein2.situation_frame import CycleContract, SituationFrame


TASK_DIGEST = "a" * 64
NESTED_DIGEST = "d" * 64
DECISION_DIGEST = "e" * 64


def make_cycle(*, suffix: str = "root") -> CycleContract:
    frame = SituationFrame.create(
        frame_id=f"frame-wp603-{suffix}",
        cycle_id=f"cycle-wp603-{suffix}",
        generation=7,
        situation_epoch=11,
        agency_state_ref=f"agency:wp603:{suffix}",
        agency_state_generation=2,
        agency_state_sha256="b" * 64,
        authority_scope_refs=("authority:effectgate-external",),
        provenance_refs=(f"receipt:frame-wp603:{suffix}",),
    )
    return CycleContract.for_frame(
        frame,
        contract_id=f"cycle-contract-wp603-{suffix}",
        cycle_generation=3,
        max_grid_cells=10,
        allowed_exits=("ACT", "ASK", "WAIT", "HOLD"),
        continuation_refs=(f"checkpoint:wp603:{suffix}",),
        provenance_refs=(f"receipt:cycle-wp603:{suffix}",),
    )


def make_route(
    *,
    selected: str,
    task_id: str = "parent-task",
    task_digest: str = TASK_DIGEST,
    suffix: str = "root",
) -> RouteCandidate:
    cycle = make_cycle(suffix=suffix)
    request = TaskRouteRequest.for_cycle(
        cycle,
        task_id=task_id,
        task_generation=4,
        task_sha256=task_digest,
        estimated_work_units=4 if selected == DIRECT_SMALL else 9,
        estimated_context_tokens=1024,
        requires_child_context_isolation=False,
        requires_parallelism=False,
        requires_long_horizon=False,
        provenance_refs=(f"task-source:wp603:{suffix}",),
    )
    policy = RoutingPolicy.create(
        policy_id=f"router-policy-wp603-{suffix}",
        generation=2,
        max_direct_work_units=8,
        max_direct_context_tokens=4096,
        allowed_routes=(DIRECT_SMALL, DELEGATE_BUILD),
        provenance_refs=(f"policy-source:wp600-g2:{suffix}",),
    )
    candidate = route_task(cycle_contract=cycle, request=request, policy=policy)
    assert candidate.selected_route == selected
    return candidate


def make_child_request(
    *,
    max_nested_depth: int = 0,
    request_id: str = "child-request-wp603",
    parent_task_id: str = "parent-task",
    payload_sha256: str = TASK_DIGEST,
) -> NativeChildRequest:
    safe_id = request_id.replace(":", "-")
    parent = CausalIdentity(
        session_id="session-wp603",
        agent_id="parent-agent",
        task_id=parent_task_id,
        turn_id=f"turn-parent-{safe_id}",
        causal_id=f"causal-parent-wp603-{safe_id}",
        generation=7,
    )
    child = parent.derive(
        causal_id=f"causal-child-wp603-{safe_id}",
        generation=8,
        agent_id="child-agent",
        task_id=f"child-task-{safe_id}",
        turn_id=f"turn-child-{safe_id}",
    )
    binding = NativeChildBinding(
        workpackage_id="F2-WP-603",
        workpackage_generation=2,
        claim_id="F2-WP-603-G2-GPT56SOL-STRATEGY-DEPTH-CONTRACT-20260829",
        parent=parent,
        invocation_id=f"invocation-{safe_id}",
        tool_use_id=f"tool-use-{safe_id}",
        delegation_id=f"delegation-{safe_id}",
        child=child,
    )
    budget = ChildResourceBudget(
        max_work_units=32,
        max_duration_ms=5000,
        max_output_bytes=65536,
        max_nested_depth=max_nested_depth,
        max_tool_calls=4,
    )
    return NativeChildRequest(
        request_id=request_id,
        request_generation=1,
        abi_version=ABI_VERSION,
        binding=binding,
        binding_id=binding.binding_id(),
        binding_sha256=binding.sha256(),
        child_runtime_class="python-native-child",
        payload_ref=f"payload:{parent_task_id}",
        payload_sha256=payload_sha256,
        input_refs=("input:a", "input:b"),
        requested_capability_refs=("cap:read-memory",),
        resource_budget=budget,
    )


def make_policy(
    *,
    admitted_strategies: tuple[str, ...] = (R0, R1, R2, R3),
    max_nested_child_edges: int = 3,
    generation: int = 2,
) -> RecursionPolicy:
    return RecursionPolicy.create(
        policy_id="recursion-policy-wp603-g2",
        generation=generation,
        admitted_strategies=admitted_strategies,
        max_nested_child_edges=max_nested_child_edges,
        provenance_refs=("policy-source:wp603-g2",),
    )


def make_r3_need(
    *,
    route: RouteCandidate,
    selected_strategy: str,
    available: tuple[str, ...],
    provenance: str,
    child: NativeChildRequest | None = None,
    remaining: int = 0,
    decision_sha: str = DECISION_DIGEST,
    parent_candidate: RecursionRouteCandidate | None = None,
) -> RecursionNeed:
    return RecursionNeed.create(
        route_candidate=route,
        requested_strategy=R3,
        r3_available_strategies=available,
        r3_selected_strategy=selected_strategy,
        r3_decision_id=f"decision:{provenance}",
        r3_decision_sha256=decision_sha,
        r3_decision_provenance_refs=(f"decision-source:{provenance}",),
        child_request=child,
        remaining_nested_child_edges=remaining,
        parent_candidate=parent_candidate,
        generation=2,
        provenance_refs=(f"need:{provenance}",),
    )


class RecursionRouterG2Tests(unittest.TestCase):
    def test_r0_is_deterministic_local_and_candidate_only(self) -> None:
        route = make_route(selected=DIRECT_SMALL)
        need = RecursionNeed.create(
            route_candidate=route,
            requested_strategy=R0,
            generation=2,
            provenance_refs=("need:r0",),
        )
        candidate = route_recursion(route_candidate=route, need=need, policy=make_policy())
        self.assertEqual(candidate.requested_strategy, R0)
        self.assertEqual(candidate.selected_strategy, R0)
        self.assertEqual(candidate.remaining_nested_child_edges, 0)
        self.assertIsNone(candidate.child_request_id)
        self.assertIsNone(candidate.child_remaining_nested_child_edges)
        self.assertEqual(candidate.reason_codes, ("R0_DETERMINISTIC_ADMITTED",))
        self.assertEqual(candidate.classification, RECURSION_ROUTE_CLASSIFICATION)

    def test_r1_model_recursion_requires_no_native_child_request(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        need = RecursionNeed.create(
            route_candidate=route,
            requested_strategy=R1,
            generation=2,
            provenance_refs=("need:r1-model",),
        )
        candidate = route_recursion(route_candidate=route, need=need, policy=make_policy())
        self.assertEqual(candidate.requested_strategy, R1)
        self.assertEqual(candidate.selected_strategy, R1)
        self.assertIsNone(candidate.child_request_id)
        self.assertEqual(candidate.reason_codes, ("R1_MODEL_RECURSION_CANDIDATE_ADMITTED",))

    def test_r2_immediate_child_is_valid_with_zero_descendant_budget(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=0)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_strategy=R2,
            remaining_nested_child_edges=0,
            generation=2,
            provenance_refs=("need:r2-immediate",),
        )
        candidate = route_recursion(
            route_candidate=route,
            child_request=child,
            need=need,
            policy=make_policy(),
        )
        self.assertEqual(candidate.selected_strategy, R2)
        self.assertEqual(candidate.child_request_id, child.request_id)
        self.assertEqual(candidate.child_remaining_nested_child_edges, 0)
        self.assertEqual(candidate.reason_codes, ("R2_NATIVE_CHILD_HARNESS_ADMITTED",))

    def test_r2_descendant_budget_is_orthogonal_and_enforced(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=0)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_strategy=R2,
            remaining_nested_child_edges=1,
            generation=2,
            provenance_refs=("need:r2-over-child-budget",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "exceed NativeChildRequest max_nested_depth"):
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=make_policy(),
            )

    def test_r3_is_explicit_adaptive_strategy_not_depth_three(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        need = make_r3_need(
            route=route,
            selected_strategy=R1,
            available=(R1, R2),
            provenance="r3-select-r1",
        )
        candidate = route_recursion(route_candidate=route, need=need, policy=make_policy())
        self.assertEqual(candidate.requested_strategy, R3)
        self.assertEqual(candidate.selected_strategy, R1)
        self.assertEqual(candidate.remaining_nested_child_edges, 0)
        self.assertEqual(candidate.r3_decision_id, "decision:r3-select-r1")
        self.assertEqual(candidate.r3_decision_sha256, DECISION_DIGEST)
        self.assertEqual(
            candidate.r3_decision_provenance_refs,
            ("decision-source:r3-select-r1",),
        )
        self.assertEqual(candidate.reason_codes, ("R3_ADAPTIVE_SELECTED_R1",))

    def test_r3_can_explicitly_select_r2_with_exact_child_evidence(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=1)
        need = make_r3_need(
            route=route,
            selected_strategy=R2,
            available=(R1, R2),
            provenance="r3-select-r2",
            child=child,
            remaining=1,
        )
        candidate = route_recursion(
            route_candidate=route,
            child_request=child,
            need=need,
            policy=make_policy(),
        )
        self.assertEqual(candidate.requested_strategy, R3)
        self.assertEqual(candidate.selected_strategy, R2)
        self.assertEqual(candidate.child_request_id, child.request_id)
        self.assertEqual(candidate.child_remaining_nested_child_edges, 1)
        self.assertEqual(candidate.reason_codes, ("R3_ADAPTIVE_SELECTED_R2",))

    def test_r3_on_direct_route_can_explicitly_select_only_r0(self) -> None:
        route = make_route(selected=DIRECT_SMALL)
        need = make_r3_need(
            route=route,
            selected_strategy=R0,
            available=(R0,),
            provenance="r3-direct-r0",
        )
        candidate = route_recursion(route_candidate=route, need=need, policy=make_policy())
        self.assertEqual(candidate.selected_strategy, R0)
        self.assertEqual(candidate.reason_codes, ("R3_ADAPTIVE_SELECTED_R0",))

    def test_r3_requires_selected_strategy_and_decision_evidence(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        with self.assertRaises(RecursionRouterError):
            RecursionNeed.create(
                route_candidate=route,
                requested_strategy=R3,
                r3_available_strategies=(R1,),
                generation=2,
                provenance_refs=("need:r3-missing-decision",),
            )
        with self.assertRaisesRegex(RecursionRouterError, "explicitly present"):
            make_r3_need(
                route=route,
                selected_strategy=R2,
                available=(R1,),
                provenance="r3-selected-not-available",
            )

    def test_r3_decision_digest_is_content_bound(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        first_need = make_r3_need(
            route=route,
            selected_strategy=R1,
            available=(R1,),
            provenance="r3-decision-a",
            decision_sha="e" * 64,
        )
        second_need = make_r3_need(
            route=route,
            selected_strategy=R1,
            available=(R1,),
            provenance="r3-decision-a",
            decision_sha="f" * 64,
        )
        policy = make_policy()
        first = route_recursion(route_candidate=route, need=first_need, policy=policy)
        second = route_recursion(route_candidate=route, need=second_need, policy=policy)
        self.assertNotEqual(first_need.need_id, second_need.need_id)
        self.assertNotEqual(first.candidate_id, second.candidate_id)

    def test_route_strategy_contradictions_fail_closed(self) -> None:
        direct = make_route(selected=DIRECT_SMALL)
        r1_need = RecursionNeed.create(
            route_candidate=direct,
            requested_strategy=R1,
            generation=2,
            provenance_refs=("need:bad-direct-r1",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "contradicts upstream route"):
            route_recursion(route_candidate=direct, need=r1_need, policy=make_policy())

        delegate = make_route(selected=DELEGATE_BUILD, suffix="delegate-r0")
        r0_need = RecursionNeed.create(
            route_candidate=delegate,
            requested_strategy=R0,
            generation=2,
            provenance_refs=("need:bad-delegate-r0",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "contradicts upstream route"):
            route_recursion(route_candidate=delegate, need=r0_need, policy=make_policy())

    def test_r3_rejects_available_strategy_incompatible_with_upstream_route(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        need = make_r3_need(
            route=route,
            selected_strategy=R1,
            available=(R0, R1),
            provenance="r3-incompatible-available",
        )
        with self.assertRaisesRegex(RecursionRouterError, "incompatible with upstream route"):
            route_recursion(route_candidate=route, need=need, policy=make_policy())

    def test_policy_must_admit_r3_and_its_selected_lower_strategy(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        need = make_r3_need(
            route=route,
            selected_strategy=R1,
            available=(R1,),
            provenance="r3-policy",
        )
        with self.assertRaisesRegex(RecursionRouterError, "R3 adaptive selection is not policy-admitted"):
            route_recursion(
                route_candidate=route,
                need=need,
                policy=make_policy(admitted_strategies=(R0, R1, R2)),
            )
        with self.assertRaisesRegex(RecursionRouterError, "selected lower strategy is not policy-admitted"):
            route_recursion(
                route_candidate=route,
                need=need,
                policy=make_policy(admitted_strategies=(R0, R2, R3)),
            )

    def test_policy_nested_depth_ceiling_is_independent_of_strategy(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=2)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_strategy=R2,
            remaining_nested_child_edges=2,
            generation=2,
            provenance_refs=("need:r2-policy-depth",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "exceed policy ceiling"):
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=make_policy(max_nested_child_edges=1),
            )

    def test_r2_crossproduct_child_with_wrong_parent_task_fails_closed(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(parent_task_id="other-task")
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_strategy=R2,
            generation=2,
            provenance_refs=("need:cross-task",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "task_id does not match"):
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=make_policy(),
            )

    def test_r2_crossproduct_child_with_wrong_payload_digest_fails_closed(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(payload_sha256="c" * 64)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_strategy=R2,
            generation=2,
            provenance_refs=("need:cross-payload",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "task digest does not match"):
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=make_policy(),
            )

    def test_need_binds_exact_child_request_identity_generation_and_digest(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        first = make_child_request(request_id="child-request-a")
        second = make_child_request(request_id="child-request-b")
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=first,
            requested_strategy=R2,
            generation=2,
            provenance_refs=("need:child-binding",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "child request id mismatch"):
            route_recursion(
                route_candidate=route,
                child_request=second,
                need=need,
                policy=make_policy(),
            )

    def test_nested_r2_consumes_remaining_edge_monotonically(self) -> None:
        root_route = make_route(selected=DELEGATE_BUILD, suffix="nested-root")
        root_child = make_child_request(max_nested_depth=2, request_id="root-child")
        root_need = RecursionNeed.create(
            route_candidate=root_route,
            child_request=root_child,
            requested_strategy=R2,
            remaining_nested_child_edges=2,
            generation=2,
            provenance_refs=("need:nested-root",),
        )
        root_candidate = route_recursion(
            route_candidate=root_route,
            child_request=root_child,
            need=root_need,
            policy=make_policy(),
        )

        nested_route = make_route(
            selected=DELEGATE_BUILD,
            task_id="nested-task",
            task_digest=NESTED_DIGEST,
            suffix="nested-child",
        )
        nested_child = make_child_request(
            max_nested_depth=1,
            request_id="nested-child",
            parent_task_id="nested-task",
            payload_sha256=NESTED_DIGEST,
        )
        nested_need = RecursionNeed.create(
            route_candidate=nested_route,
            child_request=nested_child,
            requested_strategy=R2,
            remaining_nested_child_edges=1,
            parent_candidate=root_candidate,
            generation=3,
            provenance_refs=("need:nested-child",),
        )
        nested_candidate = route_recursion(
            route_candidate=nested_route,
            child_request=nested_child,
            parent_candidate=root_candidate,
            need=nested_need,
            policy=make_policy(),
        )
        self.assertEqual(root_candidate.child_remaining_nested_child_edges, 2)
        self.assertEqual(nested_candidate.child_remaining_nested_child_edges, 1)

        with self.assertRaisesRegex(RecursionRouterError, "consume exactly one"):
            RecursionNeed.create(
                route_candidate=nested_route,
                child_request=nested_child,
                requested_strategy=R2,
                remaining_nested_child_edges=2,
                parent_candidate=root_candidate,
                generation=3,
                provenance_refs=("need:depth-reset",),
            )

    def test_zero_remaining_parent_cannot_reissue_r2(self) -> None:
        route = make_route(selected=DELEGATE_BUILD, suffix="zero-parent")
        child = make_child_request(max_nested_depth=0, request_id="zero-parent-child")
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_strategy=R2,
            remaining_nested_child_edges=0,
            generation=2,
            provenance_refs=("need:zero-parent",),
        )
        parent_candidate = route_recursion(
            route_candidate=route,
            child_request=child,
            need=need,
            policy=make_policy(),
        )
        nested_route = make_route(
            selected=DELEGATE_BUILD,
            task_id="nested-zero-task",
            task_digest=NESTED_DIGEST,
            suffix="nested-zero",
        )
        nested_child = make_child_request(
            max_nested_depth=0,
            request_id="nested-zero-child",
            parent_task_id="nested-zero-task",
            payload_sha256=NESTED_DIGEST,
        )
        with self.assertRaisesRegex(RecursionRouterError, "no remaining nested-child edge"):
            RecursionNeed.create(
                route_candidate=nested_route,
                child_request=nested_child,
                requested_strategy=R2,
                remaining_nested_child_edges=0,
                parent_candidate=parent_candidate,
                generation=3,
                provenance_refs=("need:nested-zero",),
            )

    def test_consumer_revalidates_post_construction_mutated_need(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        need = RecursionNeed.create(
            route_candidate=route,
            requested_strategy=R1,
            generation=2,
            provenance_refs=("need:content-id-falsifier",),
        )
        original_need_id = need.need_id
        object.__setattr__(need, "requested_strategy", R2)
        self.assertEqual(need.need_id, original_need_id)
        with self.assertRaises(RecursionRouterError):
            route_recursion(route_candidate=route, need=need, policy=make_policy())

    def test_consumer_revalidation_catches_stale_need_id_after_generation_mutation(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        need = RecursionNeed.create(
            route_candidate=route,
            requested_strategy=R1,
            generation=2,
            provenance_refs=("need:content-id-generation",),
        )
        object.__setattr__(need, "generation", 3)
        with self.assertRaisesRegex(RecursionRouterError, "need_id does not bind"):
            route_recursion(route_candidate=route, need=need, policy=make_policy())

    def test_consumer_revalidation_catches_mutated_r3_decision_digest(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        need = make_r3_need(
            route=route,
            selected_strategy=R1,
            available=(R1,),
            provenance="r3-mutation",
        )
        object.__setattr__(need, "r3_decision_sha256", "f" * 64)
        with self.assertRaisesRegex(RecursionRouterError, "need_id does not bind"):
            route_recursion(route_candidate=route, need=need, policy=make_policy())

    def test_policy_generation_outside_canonical_json_integer_domain_fails_closed(self) -> None:
        pathological_generation = 10 ** 5000
        with self.assertRaises(RecursionRouterError):
            make_policy(generation=pathological_generation)

    def test_need_generation_outside_canonical_json_integer_domain_fails_closed(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        pathological_generation = 10 ** 5000
        with self.assertRaises(RecursionRouterError):
            RecursionNeed.create(
                route_candidate=route,
                requested_strategy=R1,
                generation=pathological_generation,
                provenance_refs=("need:huge-generation",),
            )

    def test_candidate_mapping_roundtrip_and_display_tampering_fail_closed(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=0)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_strategy=R2,
            generation=2,
            provenance_refs=("need:mapping",),
        )
        candidate = route_recursion(
            route_candidate=route,
            child_request=child,
            need=need,
            policy=make_policy(),
        )
        rebuilt = RecursionRouteCandidate.from_mapping(candidate.as_dict())
        self.assertEqual(rebuilt, candidate)
        self.assertEqual(rebuilt.sha256(), candidate.sha256())

        forged = candidate.as_dict()
        forged["selected_strategy"] = R1
        with self.assertRaises(RecursionRouterError):
            RecursionRouteCandidate.from_mapping(forged)

    def test_candidate_identity_changes_with_strategy_or_depth_evidence(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        r1_need = RecursionNeed.create(
            route_candidate=route,
            requested_strategy=R1,
            generation=2,
            provenance_refs=("need:id-r1",),
        )
        r1 = route_recursion(route_candidate=route, need=r1_need, policy=make_policy())

        child = make_child_request(max_nested_depth=1)
        r2_zero_need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_strategy=R2,
            remaining_nested_child_edges=0,
            generation=2,
            provenance_refs=("need:id-r2-zero",),
        )
        r2_one_need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_strategy=R2,
            remaining_nested_child_edges=1,
            generation=2,
            provenance_refs=("need:id-r2-one",),
        )
        r2_zero = route_recursion(
            route_candidate=route,
            child_request=child,
            need=r2_zero_need,
            policy=make_policy(),
        )
        r2_one = route_recursion(
            route_candidate=route,
            child_request=child,
            need=r2_one_need,
            policy=make_policy(),
        )
        self.assertNotEqual(r1.candidate_id, r2_zero.candidate_id)
        self.assertNotEqual(r2_zero.candidate_id, r2_one.candidate_id)

    def test_candidate_is_deterministic_and_tamper_evident(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        need = RecursionNeed.create(
            route_candidate=route,
            requested_strategy=R1,
            generation=2,
            provenance_refs=("need:determinism",),
        )
        policy = make_policy()
        first = route_recursion(route_candidate=route, need=need, policy=policy)
        second = route_recursion(route_candidate=route, need=need, policy=policy)
        self.assertEqual(first, second)
        self.assertEqual(first.sha256(), second.sha256())
        with self.assertRaisesRegex(RecursionRouterError, "candidate_id does not bind"):
            replace(first, candidate_id="recursion-route:" + "f" * 64)
        with self.assertRaisesRegex(RecursionRouterError, "classification mismatch"):
            replace(first, classification="EFFECT_AUTHORITY")

    def test_exact_concrete_route_type_is_a_trust_boundary(self) -> None:
        route = make_route(selected=DIRECT_SMALL)

        class ForgedRouteCandidate(RouteCandidate):
            pass

        forged_route = ForgedRouteCandidate(
            **{field.name: getattr(route, field.name) for field in fields(RouteCandidate)}
        )
        need = RecursionNeed.create(
            route_candidate=route,
            requested_strategy=R0,
            generation=2,
            provenance_refs=("need:exact-type",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "exact concrete RouteCandidate"):
            route_recursion(route_candidate=forged_route, need=need, policy=make_policy())

    def test_non_r2_selected_strategy_cannot_smuggle_child_or_depth_evidence(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=1)
        with self.assertRaisesRegex(RecursionRouterError, "non-R2 selected strategy must not carry child"):
            RecursionNeed.create(
                route_candidate=route,
                child_request=child,
                requested_strategy=R1,
                generation=2,
                provenance_refs=("need:r1-smuggle-child",),
            )
        with self.assertRaisesRegex(RecursionRouterError, "zero nested-child edges"):
            RecursionNeed.create(
                route_candidate=route,
                requested_strategy=R1,
                remaining_nested_child_edges=1,
                generation=2,
                provenance_refs=("need:r1-smuggle-depth",),
            )

    def test_bool_is_not_an_integer_nested_edge_budget(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=0)
        with self.assertRaisesRegex(RecursionRouterError, "exact integer"):
            RecursionNeed.create(
                route_candidate=route,
                child_request=child,
                requested_strategy=R2,
                remaining_nested_child_edges=False,
                generation=2,
                provenance_refs=("need:bool-depth",),
            )

    def test_policy_strategies_must_be_canonical_and_exact_strings(self) -> None:
        with self.assertRaises(RecursionRouterError):
            make_policy(admitted_strategies=(R0, R2, R1, R3))
        with self.assertRaises(RecursionRouterError):
            make_policy(admitted_strategies=(R0, R1, R1, R3))

        class StringSubclass(str):
            pass

        with self.assertRaises(RecursionRouterError):
            RecursionPolicy.create(
                policy_id=StringSubclass("policy-subclass"),
                generation=2,
                admitted_strategies=(R0, R1),
                max_nested_child_edges=1,
                provenance_refs=("policy-source:subclass",),
            )


if __name__ == "__main__":
    unittest.main()
