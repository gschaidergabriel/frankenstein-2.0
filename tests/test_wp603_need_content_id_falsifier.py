"""REVIEW_ONLY executable falsifier for the active F2-WP-603 generation-1 lane.

This file takes no WP603 mutation authority.  It checks whether a RecursionNeed whose
content-bound need_id was valid at construction can be mutated afterwards through
Python's object.__setattr__ escape hatch and then consumed without revalidating that
need_id against the exact current content.
"""
from __future__ import annotations

import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.direct_delegate_router import (
    DELEGATE_BUILD,
    RoutingPolicy,
    TaskRouteRequest,
    route_task,
)
from frankenstein2.native_child_abi import ABI_VERSION, ChildResourceBudget, NativeChildRequest
from frankenstein2.native_child_binding import NativeChildBinding
from frankenstein2.recursion_router import (
    RecursionNeed,
    RecursionPolicy,
    RecursionRouterError,
    route_recursion,
)
from frankenstein2.situation_frame import CycleContract, SituationFrame

TASK_DIGEST = "a" * 64


def _route():
    frame = SituationFrame.create(
        frame_id="frame-wp603-review",
        cycle_id="cycle-wp603-review",
        generation=1,
        situation_epoch=1,
        agency_state_ref="agency:wp603-review",
        agency_state_generation=1,
        agency_state_sha256="b" * 64,
        authority_scope_refs=("authority:review-only",),
        provenance_refs=("review:wp603-need-id",),
    )
    cycle = CycleContract.for_frame(
        frame,
        contract_id="cycle-contract-wp603-review",
        cycle_generation=1,
        max_grid_cells=10,
        allowed_exits=("ACT", "ASK", "WAIT", "HOLD"),
        continuation_refs=("checkpoint:review",),
        provenance_refs=("review:wp603-cycle",),
    )
    request = TaskRouteRequest.for_cycle(
        cycle,
        task_id="parent-task",
        task_generation=1,
        task_sha256=TASK_DIGEST,
        estimated_work_units=9,
        estimated_context_tokens=1024,
        requires_child_context_isolation=False,
        requires_parallelism=False,
        requires_long_horizon=False,
        provenance_refs=("review:wp603-task",),
    )
    policy = RoutingPolicy.create(
        policy_id="route-policy-wp603-review",
        generation=1,
        max_direct_work_units=8,
        max_direct_context_tokens=4096,
        allowed_routes=("DELEGATE_BUILD", "DIRECT_SMALL"),
        provenance_refs=("review:wp603-route-policy",),
    )
    candidate = route_task(cycle_contract=cycle, request=request, policy=policy)
    assert candidate.selected_route == DELEGATE_BUILD
    return candidate


def _child_request():
    parent = CausalIdentity(
        session_id="session-wp603-review",
        agent_id="parent-agent",
        task_id="parent-task",
        turn_id="turn-parent",
        causal_id="causal-parent-wp603-review",
        generation=1,
    )
    child = parent.derive(
        causal_id="causal-child-wp603-review",
        generation=2,
        agent_id="child-agent",
        task_id="child-task",
        turn_id="turn-child",
    )
    binding = NativeChildBinding(
        workpackage_id="F2-WP-603",
        workpackage_generation=1,
        claim_id="F2-WP-603-G1-GPT56SOL-RECURSION-ROUTER-20260829",
        parent=parent,
        invocation_id="invocation-wp603-review",
        tool_use_id="tool-use-wp603-review",
        delegation_id="delegation-wp603-review",
        child=child,
    )
    return NativeChildRequest(
        request_id="child-request-wp603-review",
        request_generation=1,
        abi_version=ABI_VERSION,
        binding=binding,
        binding_id=binding.binding_id(),
        binding_sha256=binding.sha256(),
        child_runtime_class="python-native-child",
        payload_ref="payload:parent-task",
        payload_sha256=TASK_DIGEST,
        input_refs=("input:review",),
        requested_capability_refs=(),
        resource_budget=ChildResourceBudget(
            max_work_units=32,
            max_duration_ms=5000,
            max_output_bytes=65536,
            max_nested_depth=3,
            max_tool_calls=4,
        ),
    )


class WP603NeedContentIdFalsifier(unittest.TestCase):
    def test_consumer_rejects_post_construction_need_content_mutation(self) -> None:
        route = _route()
        child = _child_request()
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_depth=1,
            generation=1,
            provenance_refs=("review:wp603-need",),
        )
        original_need_id = need.need_id

        # Frozen dataclasses are not an admission boundary: object.__setattr__ can mutate
        # them.  The consumer must therefore revalidate the content-bound identity.
        object.__setattr__(need, "requested_depth", 2)
        self.assertEqual(need.need_id, original_need_id)

        policy = RecursionPolicy.create(
            policy_id="recursion-policy-wp603-review",
            generation=1,
            max_recursion_depth=3,
            admitted_depths=(0, 1, 2, 3),
            provenance_refs=("review:wp603-policy",),
        )

        try:
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=policy,
            )
        except RecursionRouterError:
            return

        self.fail(
            "WP603 accepted a post-construction-mutated RecursionNeed whose need_id "
            "still binds the original R1 content while requested_depth now requests R2"
        )


if __name__ == "__main__":
    unittest.main()
