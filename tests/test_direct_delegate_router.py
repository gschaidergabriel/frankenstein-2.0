from dataclasses import replace

import pytest

from frankenstein2.direct_delegate_router import (
    DELEGATE_BUILD,
    DIRECT_SMALL,
    DirectDelegateRouterError,
    RouteDecision,
    RoutingPolicy,
    TaskProfile,
    route_task,
)
from frankenstein2.situation_frame import CycleContract, EpistemicRef, SituationFrame

D = "a" * 64
T = "b" * 64


def make_frame(*, frame_id="frame-wp600", cycle_id="cycle-wp600", generation=3):
    return SituationFrame.create(
        frame_id=frame_id,
        cycle_id=cycle_id,
        generation=generation,
        situation_epoch=7,
        agency_state_ref="agency:wp600",
        agency_state_generation=2,
        agency_state_sha256=D,
        epistemic_refs=(EpistemicRef(kind="UNKNOWN", ref="evidence:pending"),),
        authority_scope_refs=("authority:component-only",),
        provenance_refs=("prov:frame",),
    )


def make_cycle(*, contract_id="cycle-contract-wp600", cycle_generation=5, frame=None):
    frame = frame or make_frame()
    return CycleContract.for_frame(
        frame,
        contract_id=contract_id,
        cycle_generation=cycle_generation,
        max_grid_cells=10,
        allowed_exits=("ACT", "ASK", "WAIT", "HOLD"),
        continuation_refs=("continue:stage6",),
        provenance_refs=("prov:cycle-contract",),
    )


def make_policy(**overrides):
    values = dict(
        policy_id="router-policy-wp600",
        generation=1,
        max_direct_work_units=4,
        max_direct_artifacts=2,
        max_direct_dependencies=3,
        max_recursion_depth=2,
        direct_route_enabled=True,
        provenance_refs=("prov:policy",),
    )
    values.update(overrides)
    return RoutingPolicy.create(**values)


def make_profile(cycle, **overrides):
    values = dict(
        task_id="task:wp600",
        generation=4,
        task_sha256=T,
        declared_work_units=3,
        declared_artifact_count=1,
        declared_dependency_count=2,
        recursion_depth=1,
        direct_capability_admitted=True,
        provenance_refs=("prov:task-profile",),
    )
    values.update(overrides)
    return TaskProfile.for_cycle(cycle, **values)


def route(profile, cycle, policy=None):
    return route_task(
        decision_id="route-decision:wp600",
        task_profile=profile,
        cycle_contract=cycle,
        policy=policy or make_policy(),
    )


def test_all_explicit_direct_bounds_admitted_routes_direct_small():
    cycle = make_cycle()
    result = route(make_profile(cycle), cycle)
    assert isinstance(result, RouteDecision)
    assert result.route == DIRECT_SMALL
    assert result.reason_codes == ("ALL_DIRECT_BOUNDS_ADMITTED",)


def test_exceeding_any_direct_bound_routes_delegate_build_with_auditable_reasons():
    cycle = make_cycle()
    profile = make_profile(
        cycle,
        declared_work_units=5,
        declared_artifact_count=3,
        declared_dependency_count=4,
    )
    result = route(profile, cycle)
    assert result.route == DELEGATE_BUILD
    assert result.reason_codes == (
        "DIRECT_ARTIFACT_BOUND_EXCEEDED",
        "DIRECT_DEPENDENCY_BOUND_EXCEEDED",
        "DIRECT_WORK_BOUND_EXCEEDED",
    )


def test_missing_direct_capability_routes_delegate_without_inventing_authority():
    cycle = make_cycle()
    result = route(make_profile(cycle, direct_capability_admitted=False), cycle)
    assert result.route == DELEGATE_BUILD
    assert result.reason_codes == ("DIRECT_CAPABILITY_NOT_ADMITTED",)


def test_policy_can_disable_direct_route_without_changing_task_profile():
    cycle = make_cycle()
    result = route(make_profile(cycle), cycle, make_policy(direct_route_enabled=False))
    assert result.route == DELEGATE_BUILD
    assert result.reason_codes == ("DIRECT_ROUTE_DISABLED",)


def test_recursion_beyond_declared_policy_limit_fails_closed_not_delegate():
    cycle = make_cycle()
    with pytest.raises(DirectDelegateRouterError, match="recursion depth exceeds policy limit"):
        route(make_profile(cycle, recursion_depth=3), cycle)


def test_cycle_contract_id_generation_and_digest_are_exact_bindings():
    cycle = make_cycle()
    profile = make_profile(cycle)

    other_id = make_cycle(contract_id="cycle-contract-other")
    with pytest.raises(DirectDelegateRouterError, match="cycle contract id mismatch"):
        route(profile, other_id)

    other_generation = make_cycle(cycle_generation=6)
    with pytest.raises(DirectDelegateRouterError, match="cycle contract generation mismatch"):
        route(profile, other_generation)

    changed_frame = make_frame(frame_id="frame-changed")
    other_digest = make_cycle(frame=changed_frame)
    with pytest.raises(DirectDelegateRouterError, match="cycle contract digest mismatch"):
        route(profile, other_digest)


def test_task_profile_requires_concrete_boolean_capability():
    cycle = make_cycle()
    with pytest.raises(DirectDelegateRouterError, match="concrete bool"):
        make_profile(cycle, direct_capability_admitted=1)


def test_negative_and_overflow_task_bounds_fail_closed():
    cycle = make_cycle()
    with pytest.raises(DirectDelegateRouterError, match="declared_work_units"):
        make_profile(cycle, declared_work_units=-1)
    with pytest.raises(DirectDelegateRouterError, match="declared_artifact_count"):
        make_profile(cycle, declared_artifact_count=2**31)


def test_classification_authority_cannot_be_rewritten_with_dataclasses_replace():
    cycle = make_cycle()
    profile = make_profile(cycle)
    policy = make_policy()
    result = route(profile, cycle, policy)

    with pytest.raises(DirectDelegateRouterError, match="task profile classification mismatch"):
        replace(profile, classification="WORLD_FACT")
    with pytest.raises(DirectDelegateRouterError, match="routing policy classification mismatch"):
        replace(policy, classification="EXECUTION_AUTHORITY")
    with pytest.raises(DirectDelegateRouterError, match="route decision classification mismatch"):
        replace(result, classification="COMPLETION_AUTHORITY")


def test_router_rejects_polymorphic_task_policy_and_cycle_boundaries():
    cycle = make_cycle()
    profile = make_profile(cycle)
    policy = make_policy()

    class TaskProfileSubtype(TaskProfile):
        pass

    class RoutingPolicySubtype(RoutingPolicy):
        pass

    class CycleContractSubtype(CycleContract):
        pass

    profile_subtype = TaskProfileSubtype(**profile.__dict__) if hasattr(profile, "__dict__") else TaskProfileSubtype(
        schema=profile.schema,
        task_id=profile.task_id,
        generation=profile.generation,
        task_sha256=profile.task_sha256,
        cycle_contract_id=profile.cycle_contract_id,
        cycle_generation=profile.cycle_generation,
        cycle_contract_sha256=profile.cycle_contract_sha256,
        declared_work_units=profile.declared_work_units,
        declared_artifact_count=profile.declared_artifact_count,
        declared_dependency_count=profile.declared_dependency_count,
        recursion_depth=profile.recursion_depth,
        direct_capability_admitted=profile.direct_capability_admitted,
        provenance_refs=profile.provenance_refs,
        classification=profile.classification,
    )
    policy_subtype = RoutingPolicySubtype(
        schema=policy.schema,
        policy_id=policy.policy_id,
        generation=policy.generation,
        max_direct_work_units=policy.max_direct_work_units,
        max_direct_artifacts=policy.max_direct_artifacts,
        max_direct_dependencies=policy.max_direct_dependencies,
        max_recursion_depth=policy.max_recursion_depth,
        direct_route_enabled=policy.direct_route_enabled,
        provenance_refs=policy.provenance_refs,
        classification=policy.classification,
    )
    cycle_subtype = CycleContractSubtype(
        schema=cycle.schema,
        contract_id=cycle.contract_id,
        cycle_id=cycle.cycle_id,
        cycle_generation=cycle.cycle_generation,
        expected_frame_id=cycle.expected_frame_id,
        expected_frame_generation=cycle.expected_frame_generation,
        expected_frame_sha256=cycle.expected_frame_sha256,
        max_grid_cells=cycle.max_grid_cells,
        allowed_exits=cycle.allowed_exits,
        continuation_refs=cycle.continuation_refs,
        provenance_refs=cycle.provenance_refs,
        classification=cycle.classification,
    )

    with pytest.raises(DirectDelegateRouterError, match="concrete TaskProfile"):
        route_task(
            decision_id="route:subtype-task",
            task_profile=profile_subtype,
            cycle_contract=cycle,
            policy=policy,
        )
    with pytest.raises(DirectDelegateRouterError, match="concrete RoutingPolicy"):
        route_task(
            decision_id="route:subtype-policy",
            task_profile=profile,
            cycle_contract=cycle,
            policy=policy_subtype,
        )
    with pytest.raises(DirectDelegateRouterError, match="concrete CycleContract"):
        route_task(
            decision_id="route:subtype-cycle",
            task_profile=profile,
            cycle_contract=cycle_subtype,
            policy=policy,
        )


def test_decision_is_deterministic_and_bound_to_exact_profile_and_policy():
    cycle = make_cycle()
    profile = make_profile(cycle)
    policy = make_policy()
    first = route(profile, cycle, policy)
    second = route(profile, cycle, policy)
    assert first == second
    assert first.sha256() == second.sha256()
    assert first.task_profile_sha256 == profile.sha256()
    assert first.policy_sha256 == policy.sha256()
    assert first.cycle_contract_sha256 == cycle.sha256()


def test_route_decision_explicitly_denies_child_execution_effect_and_completion_credit():
    cycle = make_cycle()
    payload = route(make_profile(cycle), cycle).as_dict()
    assert payload["child_identity_minted"] is False
    assert payload["execution_observed"] is False
    assert payload["effect_authority"] == "NONE"
    assert payload["completion_authority"] == "NONE"
