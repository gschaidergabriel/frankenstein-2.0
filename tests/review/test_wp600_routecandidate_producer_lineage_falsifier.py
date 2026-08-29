"""REVIEW_ONLY executable falsifier for F2-WP-600 generation 1.

This test takes no WP600 mutation authority. It probes whether a caller can directly
reconstruct a RouteCandidate with a changed route/reason while preserving the exact
candidate_id minted by route_task() for the original decision.
"""
from __future__ import annotations

from dataclasses import replace
import unittest

from frankenstein2.direct_delegate_router import (
    DELEGATE_BUILD,
    DIRECT_SMALL,
    RoutingPolicy,
    TaskRouteRequest,
    route_task,
)
from frankenstein2.situation_frame import CycleContract, SituationFrame

H64 = "a" * 64


def make_cycle() -> CycleContract:
    frame = SituationFrame.create(
        frame_id="frame-wp600-review",
        cycle_id="cycle-wp600-review",
        generation=7,
        situation_epoch=11,
        agency_state_ref="agency:wp600-review",
        agency_state_generation=2,
        agency_state_sha256=H64,
        authority_scope_refs=("authority:effectgate-external",),
        provenance_refs=("review:frame",),
    )
    return CycleContract.for_frame(
        frame,
        contract_id="cycle-contract-wp600-review",
        cycle_generation=3,
        max_grid_cells=10,
        allowed_exits=("ACT", "ASK", "WAIT", "HOLD"),
        continuation_refs=("checkpoint:wp600-review",),
        provenance_refs=("review:cycle",),
    )


def make_request(cycle: CycleContract) -> TaskRouteRequest:
    return TaskRouteRequest.for_cycle(
        cycle,
        task_id="task-wp600-review",
        task_generation=4,
        task_sha256="b" * 64,
        estimated_work_units=4,
        estimated_context_tokens=1024,
        requires_child_context_isolation=False,
        requires_parallelism=False,
        requires_long_horizon=False,
        provenance_refs=("review:task",),
    )


def make_policy() -> RoutingPolicy:
    return RoutingPolicy.create(
        policy_id="router-policy-wp600-review",
        generation=2,
        max_direct_work_units=8,
        max_direct_context_tokens=4096,
        allowed_routes=(DIRECT_SMALL, DELEGATE_BUILD),
        provenance_refs=("review:policy",),
    )


class WP600RouteCandidateProducerLineageFalsifier(unittest.TestCase):
    def test_changed_route_can_preserve_route_task_candidate_id(self) -> None:
        cycle = make_cycle()
        request = make_request(cycle)
        policy = make_policy()
        canonical = route_task(cycle_contract=cycle, request=request, policy=policy)

        self.assertEqual(canonical.selected_route, DIRECT_SMALL)
        self.assertEqual(canonical.reason_codes, ("DIRECT_BOUNDS_SATISFIED",))

        # REVIEW-ONLY reproduction: dataclasses.replace() re-enters RouteCandidate.__post_init__,
        # so successful construction proves that the public object boundary validates shape but
        # does not recompute candidate_id from route_task's identity payload.
        forged = replace(
            canonical,
            selected_route=DELEGATE_BUILD,
            reason_codes=("CALLER_FORGED_ROUTE",),
        )

        self.assertEqual(forged.selected_route, DELEGATE_BUILD)
        self.assertEqual(forged.reason_codes, ("CALLER_FORGED_ROUTE",))
        self.assertEqual(forged.candidate_id, canonical.candidate_id)
        self.assertEqual(forged.request_sha256, canonical.request_sha256)
        self.assertEqual(forged.cycle_contract_sha256, canonical.cycle_contract_sha256)
        self.assertEqual(forged.policy_sha256, canonical.policy_sha256)
        self.assertNotEqual(forged.sha256(), canonical.sha256())


if __name__ == "__main__":
    unittest.main(verbosity=2)
