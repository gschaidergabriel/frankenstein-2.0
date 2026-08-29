import json

import pytest

from frankenstein2.target_fault_scenarios import (
    DEVICE_READD,
    DEVICE_REMOVE,
    LOW_SPACE,
    NETWORK_LOSS,
    PERMISSION_REVOKE,
    PIPEWIRE_RESTART,
    PROCESS_KILL,
    FaultSpec,
)
from frankenstein2.target_hostile_chaos_matrix import (
    AUTHORITY_REBIND_POLICY,
    CHAOS_CLASSIFICATION,
    COMPLETION_EXPECTATION,
    DEGRADATION_ORDER,
    FAMILY_LIFECYCLE,
    FAMILY_MULTIMEDIA_SESSION,
    FAMILY_NETWORK,
    FAMILY_PERMISSION,
    FAMILY_RESOURCE_PRESSURE,
    MAX_EVENTS_PER_CASE,
    PROTECTED_STATE_EXPECTATION,
    TargetHostileChaosMatrixError,
    compile_hostile_chaos_case,
    compile_hostile_chaos_matrix,
)

PROFILE = "b" * 64


def fault(action, target, offset_ms, parameters=None):
    return FaultSpec.create(
        action=action,
        target=target,
        offset_ms=offset_ms,
        parameters=parameters,
    )


def canonical_specs():
    return (
        fault(PERMISSION_REVOKE, "permission:camera", 0),
        fault(PIPEWIRE_RESTART, "service:pipewire", 0),
        fault(NETWORK_LOSS, "network:uplink", 0, {"loss_percent": 30}),
        fault(LOW_SPACE, "path:state", 10, {"remaining_bytes": 4096}),
        fault(PROCESS_KILL, "process:voice", 10),
        fault(DEVICE_REMOVE, "device:camera", 20),
        fault(DEVICE_READD, "device:camera", 30),
    )


def build_case(*, name="mixed-pressure", profile=PROFILE, specs=None):
    return compile_hostile_chaos_case(
        case_name=name,
        seed=41,
        target_profile_digest=profile,
        start_generation=5,
        specs=canonical_specs() if specs is None else specs,
    )


def test_same_inputs_compile_to_same_case_and_matrix_identity():
    first = build_case()
    second = build_case()
    assert first == second
    assert first.case_id == second.case_id

    matrix_a = compile_hostile_chaos_matrix(matrix_name="release-hostile-smoke", cases=(first,))
    matrix_b = compile_hostile_chaos_matrix(matrix_name="release-hostile-smoke", cases=(second,))
    assert matrix_a == matrix_b
    assert matrix_a.matrix_id == matrix_b.matrix_id
    assert matrix_a.sha256() == matrix_b.sha256()


def test_required_fault_families_and_cross_family_concurrency_are_bound():
    case = build_case()
    counts = dict(case.family_counts)
    assert counts[FAMILY_MULTIMEDIA_SESSION] == 3
    assert counts[FAMILY_PERMISSION] == 1
    assert counts[FAMILY_LIFECYCLE] == 1
    assert counts[FAMILY_NETWORK] == 1
    assert counts[FAMILY_RESOURCE_PRESSURE] == 1
    assert case.concurrent_offsets_ms == (0, 10)


def test_missing_required_fault_family_fails_closed():
    specs = tuple(spec for spec in canonical_specs() if spec.action != NETWORK_LOSS)
    with pytest.raises(TargetHostileChaosMatrixError, match="missing required fault families"):
        build_case(specs=specs)


def test_no_cross_family_concurrency_fails_closed():
    specs = tuple(
        fault(spec.action, spec.target, index * 10, json.loads(spec.parameters_json))
        for index, spec in enumerate(canonical_specs())
    )
    with pytest.raises(TargetHostileChaosMatrixError, match="cross-family concurrency"):
        build_case(specs=specs)


def test_protected_cognition_or_canonical_state_target_fails_closed():
    specs = list(canonical_specs())
    specs[3] = fault(LOW_SPACE, "canonical_state:unifieddb", 10, {"remaining_bytes": 4096})
    with pytest.raises(TargetHostileChaosMatrixError, match="protected cognition/state authority"):
        build_case(specs=tuple(specs))


def test_generation_changes_create_explicit_stale_authority_fences():
    case = build_case()
    expected = tuple(
        event.event_id
        for event in case.scenario.events
        if event.generation_after > event.generation_before
    )
    assert case.authority_fence_event_ids == expected
    assert len(expected) >= 4
    assert case.authority_rebind_policy == AUTHORITY_REBIND_POLICY


def test_degradation_and_completion_expectations_are_fail_closed():
    case = build_case()
    assert case.degradation_order == DEGRADATION_ORDER
    assert case.degradation_order[:2] == ("PERCEPTION", "VOICE")
    assert case.degradation_order[-2:] == ("COGNITION", "CANONICAL_STATE")
    assert case.protected_state_expectation == PROTECTED_STATE_EXPECTATION
    assert case.completion_expectation == COMPLETION_EXPECTATION
    assert case.classification == CHAOS_CLASSIFICATION
    assert case.runtime_execution_observed is False
    assert case.physical_host_credit == 0
    assert case.completion_credit == 0


def test_unknown_target_profile_remains_unknown():
    case = build_case(profile="UNKNOWN")
    assert case.scenario.target_profile_digest == "UNKNOWN"


def test_case_event_budget_is_bounded_before_compilation():
    repeated = tuple(
        fault(PERMISSION_REVOKE, f"permission:item-{idx}", idx, None)
        for idx in range(MAX_EVENTS_PER_CASE + 1)
    )
    with pytest.raises(TargetHostileChaosMatrixError, match="exceeds"):
        build_case(specs=repeated)


def test_case_tampering_is_detected_at_matrix_consumer_boundary():
    case = build_case()
    object.__setattr__(case, "concurrent_offsets_ms", (999,))
    with pytest.raises(TargetHostileChaosMatrixError, match="concurrent_offsets_ms"):
        compile_hostile_chaos_matrix(matrix_name="tamper-check", cases=(case,))


def test_duplicate_case_names_fail_closed():
    first = build_case(name="same")
    second = build_case(name="same")
    with pytest.raises(TargetHostileChaosMatrixError, match="case names must be unique"):
        compile_hostile_chaos_matrix(matrix_name="duplicates", cases=(first, second))


def test_matrix_never_promotes_repository_plan_to_runtime_or_completion():
    first = build_case(name="mixed-a")
    second = build_case(name="mixed-b")
    matrix = compile_hostile_chaos_matrix(matrix_name="bounded-hostile", cases=(first, second))
    assert matrix.total_events == 14
    assert matrix.classification == CHAOS_CLASSIFICATION
    assert matrix.runtime_execution_observed is False
    assert matrix.physical_host_credit == 0
    assert matrix.completion_credit == 0
    payload = matrix.as_dict()
    assert payload["limits"]["max_events_per_case"] == MAX_EVENTS_PER_CASE
