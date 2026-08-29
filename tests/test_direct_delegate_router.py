from dataclasses import replace

import pytest

from frankenstein2.direct_delegate_router import (
    DELEGATE_BUILD,
    DIRECT_SMALL,
    ROUTE_CANDIDATE_CLASSIFICATION,
    DirectDelegateRouterError,
    RoutingPolicy,
    TaskRouteRequest,
    route_task,
)
from frankenstein2.situation_frame import CycleContract, SituationFrame


DIGEST_A = "a" * 64


def make_cycle(*, contract_id: str = "cycle-contract-1", cycle_generation: int = 3) -> CycleContract:
    frame = SituationFrame.create(
        frame_id="frame-1",
        cycle_id="cycle-1",
        generation=7,
        situation_epoch=11,
        agency_state_ref="agency:1",
        agency_state_generation=2,
        agency_state_sha256=DIGEST_A,
        authority_scope_refs=("authority:effectgate-external",),
        provenance_refs=("receipt:frame-source",),
    )
    return CycleContract.for_frame(
        frame,
        contract_id=contract_id,
        cycle_generation=cycle_generation,
        max_grid_cells=10,
        allowed_exits=("ACT", "ASK", "WAIT", "HOLD"),
        continuation_refs=("checkpoint:1",),
        provenance_refs=("receipt:cycle-source",),
    )


def make_policy(*, allowed_routes=(DIRECT_SMALL, DELEGATE_BUILD)) -> RoutingPolicy:
    return RoutingPolicy.create(
        policy_id="router-policy-1",
        generation=2,
        max_direct_work_units=8,
        max_direct_context_tokens=4096,
        allowed_routes=allowed_routes,
        provenance_refs=("policy-source:1",),
    )


def make_request(cycle: CycleContract, **overrides) -> TaskRouteRequest:
    values = {
        "task_id": "task-1",
        "task_generation": 4,
        "task_sha256": "b" * 64,
        "estimated_work_units": 4,
        "estimated_context_tokens": 1024,
        "requires_child_context_isolation": False,
        "requires_parallelism": False,
        "requires_long_horizon": False,
        "provenance_refs": ("task-source:1",),
    }
    values.update(overrides)
    return TaskRouteRequest.for_cycle(cycle, **values)


def test_small_explicit_task_routes_direct_without_minting_authority():
    cycle = make_cycle()
    candidate = route_task(cycle_contract=cycle, request=make_request(cycle), policy=make_policy())

    assert candidate.selected_route == DIRECT_SMALL
    assert candidate.reason_codes == ("DIRECT_BOUNDS_SATISFIED",)
    assert candidate.classification == ROUTE_CANDIDATE_CLASSIFICATION
    assert candidate.cycle_contract_sha256 == cycle.sha256()
    assert candidate.candidate_id.startswith("route:")


def test_work_units_over_explicit_bound_routes_to_delegate():
    cycle = make_cycle()
    request = make_request(cycle, estimated_work_units=9)
    candidate = route_task(cycle_contract=cycle, request=request, policy=make_policy())

    assert candidate.selected_route == DELEGATE_BUILD
    assert candidate.reason_codes == ("WORK_UNITS_EXCEED_DIRECT_BOUND",)


def test_any_explicit_structural_delegation_need_routes_to_delegate():
    cycle = make_cycle()
    request = make_request(
        cycle,
        requires_child_context_isolation=True,
        requires_parallelism=True,
        requires_long_horizon=True,
    )
    candidate = route_task(cycle_contract=cycle, request=request, policy=make_policy())

    assert candidate.selected_route == DELEGATE_BUILD
    assert candidate.reason_codes == (
        "CHILD_CONTEXT_ISOLATION_REQUIRED",
        "LONG_HORIZON_REQUIRED",
        "PARALLELISM_REQUIRED",
    )


def test_policy_can_disable_direct_but_output_remains_candidate_only():
    cycle = make_cycle()
    candidate = route_task(
        cycle_contract=cycle,
        request=make_request(cycle),
        policy=make_policy(allowed_routes=(DELEGATE_BUILD,)),
    )

    assert candidate.selected_route == DELEGATE_BUILD
    assert candidate.reason_codes == ("DIRECT_ROUTE_NOT_ALLOWED",)
    assert "AUTHORITY" in candidate.classification
    assert candidate.classification.startswith("ROUTE_CANDIDATE_NOT_")


def test_fail_closed_when_task_requires_delegation_but_policy_forbids_it():
    cycle = make_cycle()
    request = make_request(cycle, estimated_context_tokens=4097)

    with pytest.raises(DirectDelegateRouterError, match="requires delegation"):
        route_task(
            cycle_contract=cycle,
            request=request,
            policy=make_policy(allowed_routes=(DIRECT_SMALL,)),
        )


def test_request_is_bound_to_exact_cycle_contract_identity_generation_and_digest():
    cycle = make_cycle()
    request = make_request(cycle)
    other_cycle = make_cycle(contract_id="cycle-contract-2")

    with pytest.raises(DirectDelegateRouterError, match="cycle contract id mismatch"):
        route_task(cycle_contract=other_cycle, request=request, policy=make_policy())

    forged = replace(request, cycle_contract_sha256="f" * 64)
    with pytest.raises(DirectDelegateRouterError, match="cycle contract digest mismatch"):
        route_task(cycle_contract=cycle, request=forged, policy=make_policy())


def test_candidate_identity_is_deterministic_and_changes_with_policy_or_task_shape():
    cycle = make_cycle()
    request = make_request(cycle)
    policy = make_policy()

    first = route_task(cycle_contract=cycle, request=request, policy=policy)
    second = route_task(cycle_contract=cycle, request=request, policy=policy)
    changed_request = make_request(cycle, estimated_work_units=5)
    changed = route_task(cycle_contract=cycle, request=changed_request, policy=policy)

    assert first == second
    assert first.sha256() == second.sha256()
    assert first.candidate_id == second.candidate_id
    assert changed.candidate_id != first.candidate_id


def test_candidate_classification_cannot_be_rewritten_into_authority():
    cycle = make_cycle()
    candidate = route_task(cycle_contract=cycle, request=make_request(cycle), policy=make_policy())

    with pytest.raises(DirectDelegateRouterError, match="classification mismatch"):
        replace(candidate, classification="EFFECT_AUTHORITY")


def test_candidate_id_cannot_be_rewritten_away_from_candidate_content():
    cycle = make_cycle()
    candidate = route_task(cycle_contract=cycle, request=make_request(cycle), policy=make_policy())

    with pytest.raises(DirectDelegateRouterError, match="candidate id"):
        replace(candidate, candidate_id="route:" + "f" * 64)


def test_boolean_and_digest_fields_fail_closed_instead_of_accepting_python_coercions():
    cycle = make_cycle()

    with pytest.raises(DirectDelegateRouterError, match="requires_parallelism must be a boolean"):
        make_request(cycle, requires_parallelism=1)

    with pytest.raises(DirectDelegateRouterError, match="task_sha256"):
        make_request(cycle, task_sha256="ABC")


def test_policy_route_set_and_bounds_are_validated_deterministically():
    with pytest.raises(DirectDelegateRouterError, match="at least one route"):
        make_policy(allowed_routes=())

    with pytest.raises(DirectDelegateRouterError, match="allowed_routes must be a subset"):
        make_policy(allowed_routes=(DIRECT_SMALL, "EXECUTE_EFFECT"))

    with pytest.raises(DirectDelegateRouterError, match="max_direct_work_units"):
        RoutingPolicy.create(
            policy_id="router-policy-1",
            generation=1,
            max_direct_work_units=-1,
            max_direct_context_tokens=1,
            provenance_refs=("policy-source:1",),
        )
