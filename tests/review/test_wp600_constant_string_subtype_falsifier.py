from dataclasses import replace

import pytest

from frankenstein2.direct_delegate_router import (
    DELEGATE_BUILD,
    DIRECT_SMALL,
    ROUTE_CANDIDATE_CLASSIFICATION,
    TASK_ROUTE_REQUEST_SCHEMA,
    DirectDelegateRouterError,
    RoutingPolicy,
    TaskRouteRequest,
    route_task,
)
from frankenstein2.situation_frame import CycleContract, SituationFrame


DIGEST_A = "a" * 64


class EqualityAlias(str):
    """A string whose serialized bytes disagree with its claimed equality target."""

    def __new__(cls, serialized_value: str, equality_target: str):
        instance = super().__new__(cls, serialized_value)
        instance._equality_target = equality_target
        return instance

    def __eq__(self, other):
        return other == self._equality_target or super().__eq__(other)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self._equality_target)


def make_cycle() -> CycleContract:
    frame = SituationFrame.create(
        frame_id="frame-wp600-review",
        cycle_id="cycle-wp600-review",
        generation=1,
        situation_epoch=1,
        agency_state_ref="agency:wp600-review",
        agency_state_generation=1,
        agency_state_sha256=DIGEST_A,
        authority_scope_refs=("authority:effectgate-external",),
        provenance_refs=("receipt:wp600-review-frame",),
    )
    return CycleContract.for_frame(
        frame,
        contract_id="cycle-contract-wp600-review",
        cycle_generation=1,
        max_grid_cells=10,
        allowed_exits=("ACT", "ASK", "WAIT", "HOLD"),
        continuation_refs=("checkpoint:wp600-review",),
        provenance_refs=("receipt:wp600-review-cycle",),
    )


def make_policy() -> RoutingPolicy:
    return RoutingPolicy.create(
        policy_id="router-policy-wp600-review",
        generation=1,
        max_direct_work_units=8,
        max_direct_context_tokens=4096,
        allowed_routes=(DIRECT_SMALL, DELEGATE_BUILD),
        provenance_refs=("policy-source:wp600-review",),
    )


def make_request(cycle: CycleContract) -> TaskRouteRequest:
    return TaskRouteRequest.for_cycle(
        cycle,
        task_id="task-wp600-review",
        task_generation=1,
        task_sha256="b" * 64,
        estimated_work_units=1,
        estimated_context_tokens=256,
        provenance_refs=("task-source:wp600-review",),
    )


def test_route_candidate_classification_rejects_equality_alias_before_authority_label_can_drift():
    cycle = make_cycle()
    candidate = route_task(cycle_contract=cycle, request=make_request(cycle), policy=make_policy())
    forged = EqualityAlias("EFFECT_AUTHORITY", ROUTE_CANDIDATE_CLASSIFICATION)

    assert str(forged) == "EFFECT_AUTHORITY"
    assert forged == ROUTE_CANDIDATE_CLASSIFICATION

    with pytest.raises(DirectDelegateRouterError, match="classification"):
        replace(candidate, classification=forged)


def test_task_route_request_schema_rejects_equality_alias_with_different_canonical_payload():
    cycle = make_cycle()
    request = make_request(cycle)
    forged = EqualityAlias("FORGED_TASK_ROUTE_SCHEMA", TASK_ROUTE_REQUEST_SCHEMA)

    assert str(forged) == "FORGED_TASK_ROUTE_SCHEMA"
    assert forged == TASK_ROUTE_REQUEST_SCHEMA

    with pytest.raises(DirectDelegateRouterError, match="schema"):
        replace(request, schema=forged)
