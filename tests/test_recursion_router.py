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
    RecursionRouterError,
    route_recursion,
)
from frankenstein2.situation_frame import CycleContract, SituationFrame


TASK_DIGEST = "a" * 64


def make_cycle() -> CycleContract:
    frame = SituationFrame.create(
        frame_id="frame-wp603",
        cycle_id="cycle-wp603",
        generation=7,
        situation_epoch=11,
        agency_state_ref="agency:wp603",
        agency_state_generation=2,
        agency_state_sha256="b" * 64,
        authority_scope_refs=("authority:effectgate-external",),
        provenance_refs=("receipt:frame-wp603",),
    )
    return CycleContract.for_frame(
        frame,
        contract_id="cycle-contract-wp603",
        cycle_generation=3,
        max_grid_cells=10,
        allowed_exits=("ACT", "ASK", "WAIT", "HOLD"),
        continuation_refs=("checkpoint:wp603",),
        provenance_refs=("receipt:cycle-wp603",),
    )


def make_route(*, selected: str) -> RouteCandidate:
    cycle = make_cycle()
    request = TaskRouteRequest.for_cycle(
        cycle,
        task_id="parent-task",
        task_generation=4,
        task_sha256=TASK_DIGEST,
        estimated_work_units=4 if selected == DIRECT_SMALL else 9,
        estimated_context_tokens=1024,
        requires_child_context_isolation=False,
        requires_parallelism=False,
        requires_long_horizon=False,
        provenance_refs=("task-source:wp603",),
    )
    policy = RoutingPolicy.create(
        policy_id="router-policy-wp603",
        generation=2,
        max_direct_work_units=8,
        max_direct_context_tokens=4096,
        allowed_routes=(DIRECT_SMALL, DELEGATE_BUILD),
        provenance_refs=("policy-source:wp600",),
    )
    candidate = route_task(cycle_contract=cycle, request=request, policy=policy)
    assert candidate.selected_route == selected
    return candidate


def make_child_request(
    *,
    max_nested_depth: int = 3,
    request_id: str = "child-request-wp603",
    parent_task_id: str = "parent-task",
    payload_sha256: str = TASK_DIGEST,
) -> NativeChildRequest:
    parent = CausalIdentity(
        session_id="session-wp603",
        agent_id="parent-agent",
        task_id=parent_task_id,
        turn_id="turn-parent",
        causal_id="causal-parent-wp603-" + request_id,
        generation=7,
    )
    child = parent.derive(
        causal_id="causal-child-wp603-" + request_id,
        generation=8,
        agent_id="child-agent",
        task_id="child-task-wp603",
        turn_id="turn-child",
    )
    binding = NativeChildBinding(
        workpackage_id="F2-WP-603",
        workpackage_generation=1,
        claim_id="F2-WP-603-G1-GPT56SOL-RECURSION-ROUTER-20260829",
        parent=parent,
        invocation_id="invocation-" + request_id,
        tool_use_id="tool-use-" + request_id,
        delegation_id="delegation-" + request_id,
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
        payload_ref="payload:parent-task",
        payload_sha256=payload_sha256,
        input_refs=("input:a", "input:b"),
        requested_capability_refs=("cap:read-memory",),
        resource_budget=budget,
    )


def make_policy(
    *,
    max_depth: int = 3,
    admitted_depths: tuple[int, ...] = (0, 1, 2, 3),
) -> RecursionPolicy:
    return RecursionPolicy.create(
        policy_id="recursion-policy-wp603",
        generation=1,
        max_recursion_depth=max_depth,
        admitted_depths=admitted_depths,
        provenance_refs=("policy-source:wp603",),
    )


class RecursionRouterTests(unittest.TestCase):
    def test_direct_small_is_exactly_r0_and_candidate_only(self) -> None:
        route = make_route(selected=DIRECT_SMALL)
        need = RecursionNeed.create(
            route_candidate=route,
            requested_depth=0,
            generation=1,
            provenance_refs=("need:direct-r0",),
        )
        candidate = route_recursion(route_candidate=route, need=need, policy=make_policy())

        self.assertEqual(candidate.selected_depth, 0)
        self.assertEqual(candidate.selected_level, R0)
        self.assertIsNone(candidate.child_request_id)
        self.assertIsNone(candidate.child_request_sha256)
        self.assertEqual(candidate.reason_codes, ("DIRECT_SMALL_REQUIRES_R0",))
        self.assertEqual(candidate.classification, RECURSION_ROUTE_CLASSIFICATION)
        self.assertTrue(candidate.candidate_id.startswith("recursion-route:"))

    def test_delegate_build_accepts_explicit_r1_r2_r3_without_inference(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=3)
        for depth, level in ((1, R1), (2, R2), (3, R3)):
            with self.subTest(depth=depth):
                need = RecursionNeed.create(
                    route_candidate=route,
                    child_request=child,
                    requested_depth=depth,
                    generation=1,
                    provenance_refs=(f"need:delegate-r{depth}",),
                )
                candidate = route_recursion(
                    route_candidate=route,
                    child_request=child,
                    need=need,
                    policy=make_policy(),
                )
                self.assertEqual(candidate.selected_depth, depth)
                self.assertEqual(candidate.selected_level, level)
                self.assertEqual(candidate.child_request_id, child.request_id)
                self.assertEqual(candidate.child_request_sha256, child.sha256())
                self.assertEqual(
                    candidate.reason_codes,
                    ("DELEGATE_BUILD_EXPLICIT_DEPTH_ADMITTED",),
                )

    def test_direct_small_with_nonzero_recursion_fails_closed(self) -> None:
        route = make_route(selected=DIRECT_SMALL)
        need = RecursionNeed.create(
            route_candidate=route,
            requested_depth=1,
            generation=1,
            provenance_refs=("need:invalid-direct",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "DIRECT_SMALL cannot be paired"):
            route_recursion(route_candidate=route, need=need, policy=make_policy())

    def test_direct_small_cannot_smuggle_a_child_request(self) -> None:
        route = make_route(selected=DIRECT_SMALL)
        child = make_child_request()
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_depth=0,
            generation=1,
            provenance_refs=("need:direct-with-child",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "DIRECT_SMALL R0 cannot be paired"):
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=make_policy(),
            )

    def test_delegate_build_requires_nonzero_admitted_child_depth(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        need = RecursionNeed.create(
            route_candidate=route,
            requested_depth=0,
            generation=1,
            provenance_refs=("need:delegate-r0",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "requires an admitted nonzero"):
            route_recursion(route_candidate=route, need=need, policy=make_policy())

    def test_delegate_build_requires_exact_native_child_request(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        need = RecursionNeed.create(
            route_candidate=route,
            requested_depth=1,
            generation=1,
            provenance_refs=("need:delegate-no-child",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "requires an exact NativeChildRequest"):
            route_recursion(route_candidate=route, need=need, policy=make_policy())

    def test_requested_level_above_policy_ceiling_fails_closed(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=3)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_depth=3,
            generation=1,
            provenance_refs=("need:over-ceiling",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "exceeds policy ceiling"):
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=make_policy(max_depth=2, admitted_depths=(0, 1, 2)),
            )

    def test_depth_must_be_explicitly_policy_admitted(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=3)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_depth=2,
            generation=1,
            provenance_refs=("need:not-admitted",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "not policy-admitted"):
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=make_policy(admitted_depths=(0, 1, 3)),
            )

    def test_native_child_budget_must_cover_selected_depth(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=1)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_depth=2,
            generation=1,
            provenance_refs=("need:budget-too-shallow",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "max_nested_depth cannot cover"):
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=make_policy(),
            )

    def test_need_binds_exact_route_identity_and_digest(self) -> None:
        route = make_route(selected=DIRECT_SMALL)
        need = RecursionNeed.create(
            route_candidate=route,
            requested_depth=0,
            generation=1,
            provenance_refs=("need:binding",),
        )
        other = make_route(selected=DELEGATE_BUILD)
        with self.assertRaises(RecursionRouterError):
            route_recursion(route_candidate=other, need=need, policy=make_policy())
        with self.assertRaisesRegex(RecursionRouterError, "need_id does not bind"):
            replace(need, route_candidate_sha256="f" * 64)

    def test_need_binds_exact_child_request_identity_generation_and_digest(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        first = make_child_request(request_id="child-request-a")
        second = make_child_request(request_id="child-request-b")
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=first,
            requested_depth=1,
            generation=1,
            provenance_refs=("need:child-binding",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "child request id mismatch"):
            route_recursion(
                route_candidate=route,
                child_request=second,
                need=need,
                policy=make_policy(),
            )

    def test_delegate_route_and_child_request_must_name_same_explicit_task(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(parent_task_id="other-task")
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_depth=1,
            generation=1,
            provenance_refs=("need:cross-task",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "task_id does not match"):
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=make_policy(),
            )

    def test_delegate_route_and_child_request_must_bind_same_payload_digest(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(payload_sha256="c" * 64)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_depth=1,
            generation=1,
            provenance_refs=("need:cross-payload",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "task digest does not match"):
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=make_policy(),
            )

    def test_exact_concrete_upstream_types_are_trust_boundaries(self) -> None:
        route = make_route(selected=DIRECT_SMALL)

        class ForgedRouteCandidate(RouteCandidate):
            pass

        forged_route = ForgedRouteCandidate(
            **{field.name: getattr(route, field.name) for field in fields(RouteCandidate)}
        )
        need = RecursionNeed.create(
            route_candidate=route,
            requested_depth=0,
            generation=1,
            provenance_refs=("need:exact-type",),
        )
        with self.assertRaisesRegex(RecursionRouterError, "exact concrete RouteCandidate"):
            route_recursion(route_candidate=forged_route, need=need, policy=make_policy())

    def test_bool_is_not_an_integer_recursion_depth(self) -> None:
        route = make_route(selected=DIRECT_SMALL)
        with self.assertRaisesRegex(RecursionRouterError, "exact integer"):
            RecursionNeed.create(
                route_candidate=route,
                requested_depth=False,
                generation=1,
                provenance_refs=("need:bool-depth",),
            )

    def test_policy_depths_must_be_unique_canonical_and_within_ceiling(self) -> None:
        with self.assertRaises(RecursionRouterError):
            make_policy(admitted_depths=(0, 2, 1))
        with self.assertRaises(RecursionRouterError):
            make_policy(admitted_depths=(0, 1, 1))
        with self.assertRaises(RecursionRouterError):
            make_policy(max_depth=1, admitted_depths=(0, 1, 2))

    def test_candidate_is_deterministic_and_tamper_evident(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=2)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_depth=2,
            generation=1,
            provenance_refs=("need:determinism",),
        )
        policy = make_policy(max_depth=2, admitted_depths=(0, 1, 2))
        first = route_recursion(
            route_candidate=route,
            child_request=child,
            need=need,
            policy=policy,
        )
        second = route_recursion(
            route_candidate=route,
            child_request=child,
            need=need,
            policy=policy,
        )
        self.assertEqual(first, second)
        self.assertEqual(first.sha256(), second.sha256())
        with self.assertRaisesRegex(RecursionRouterError, "candidate_id does not bind"):
            replace(first, candidate_id="recursion-route:" + "f" * 64)
        with self.assertRaisesRegex(RecursionRouterError, "classification mismatch"):
            replace(first, classification="EFFECT_AUTHORITY")


if __name__ == "__main__":
    unittest.main()
