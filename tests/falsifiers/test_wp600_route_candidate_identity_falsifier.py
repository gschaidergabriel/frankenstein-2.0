from dataclasses import replace

import pytest

from frankenstein2.direct_delegate_router import (
    DELEGATE_BUILD,
    DIRECT_SMALL,
    DirectDelegateRouterError,
    RoutingPolicy,
    TaskRouteRequest,
    route_task,
)
from frankenstein2.situation_frame import CycleContract, SituationFrame


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def make_cycle() -> CycleContract:
    frame = SituationFrame.create(
        frame_id="frame:wp600-falsifier",
        cycle_id="cycle:wp600-falsifier",
        generation=7,
        situation_epoch=11,
        agency_state_ref="agency:wp600-falsifier",
        agency_state_generation=2,
        agency_state_sha256=DIGEST_A,
        authority_scope_refs=("authority:effectgate-external",),
        provenance_refs=("prov:wp600-falsifier-frame",),
    )
    return CycleContract.for_frame(
        frame,
        contract_id="cycle-contract:wp600-falsifier",
        cycle_generation=3,
        max_grid_cells=10,
        allowed_exits=("ACT", "ASK", "WAIT", "HOLD"),
        continuation_refs=("checkpoint:wp600-falsifier",),
        provenance_refs=("prov:wp600-falsifier-cycle",),
    )


def make_policy() -> RoutingPolicy:
    return RoutingPolicy.create(
        policy_id="router-policy:wp600-falsifier",
        generation=2,
        max_direct_work_units=8,
        max_direct_context_tokens=4096,
        allowed_routes=(DIRECT_SMALL, DELEGATE_BUILD),
        provenance_refs=("prov:wp600-falsifier-policy",),
    )


def test_route_candidate_rejects_selected_route_relabel_without_identity_rederivation():
    """A candidate_id must not survive a semantic route/reason rewrite.

    Start from a canonical DELEGATE_BUILD candidate whose identity was produced by route_task.
    dataclasses.replace() reruns RouteCandidate.__post_init__. If that validator does not bind
    candidate_id back to the current selected_route/reason_codes, a caller can manufacture a
    DIRECT_SMALL-looking RouteCandidate while retaining the exact identity of the delegated
    candidate. The immutable dataclass surface alone is therefore not an identity seal.
    """

    cycle = make_cycle()
    request = TaskRouteRequest.for_cycle(
        cycle,
        task_id="task:wp600-falsifier",
        task_generation=4,
        task_sha256=DIGEST_B,
        estimated_work_units=9,
        estimated_context_tokens=1024,
        requires_child_context_isolation=False,
        requires_parallelism=False,
        requires_long_horizon=False,
        provenance_refs=("prov:wp600-falsifier-task",),
    )
    candidate = route_task(cycle_contract=cycle, request=request, policy=make_policy())

    assert candidate.selected_route == DELEGATE_BUILD
    assert candidate.reason_codes == ("WORK_UNITS_EXCEED_DIRECT_BOUND",)

    with pytest.raises(DirectDelegateRouterError):
        replace(
            candidate,
            selected_route=DIRECT_SMALL,
            reason_codes=("DIRECT_BOUNDS_SATISFIED",),
        )
