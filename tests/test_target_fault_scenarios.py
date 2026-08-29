from dataclasses import replace

import pytest

from frankenstein2.target_fault_scenarios import (
    BRIDGE_DISCONNECT,
    BRIDGE_RECONNECT,
    CLOCK_SKEW,
    DEVICE_EBUSY,
    DEVICE_LATE,
    DEVICE_REMOVE,
    DEVICE_READD,
    DNS_FAILURE,
    FAULT_REPLAY_CLASSIFICATION,
    LOW_SPACE,
    NETWORK_LATENCY,
    NETWORK_LOSS,
    PACKAGE_LOCK,
    PARTIAL_INSTALL,
    PERMISSION_DENY,
    PERMISSION_REVOKE,
    PIPEWIRE_RESTART,
    PORTAL_RESTART,
    PROCESS_KILL,
    READ_ONLY,
    REBOOT,
    STALE_GENERATION,
    SUSPEND_RESUME,
    USER_MANAGER_RESTART,
    WIREPLUMBER_RESTART,
    WRONG_OWNERSHIP,
    FaultSpec,
    TargetFaultScenarioError,
    compile_fault_scenario,
    replay_fault_scenario,
)


PROFILE = "a" * 64


def spec(action, target="target:primary", offset_ms=0, parameters=None):
    return FaultSpec.create(
        action=action,
        target=target,
        offset_ms=offset_ms,
        parameters=parameters,
    )


def compile_example(*, seed=17, profile=PROFILE, start_generation=4):
    return compile_fault_scenario(
        scenario_name="host-chaos-smoke",
        seed=seed,
        target_profile_digest=profile,
        start_generation=start_generation,
        specs=(
            spec(PERMISSION_DENY, "portal:screen", 0),
            spec(PERMISSION_REVOKE, "portal:screen", 10),
            spec(DEVICE_LATE, "audio:mic", 20, {"delay_ms": 250}),
            spec(DEVICE_EBUSY, "video:camera", 30),
            spec(PIPEWIRE_RESTART, "service:pipewire", 40),
            spec(NETWORK_LATENCY, "bridge:vps", 50, {"latency_ms": 900}),
            spec(NETWORK_LOSS, "bridge:vps", 60, {"loss_percent": 25}),
            spec(WRONG_OWNERSHIP, "path:state", 70),
            spec(PROCESS_KILL, "process:frankenstein", 80),
            spec(REBOOT, "host:target", 90),
        ),
    )


def test_same_exact_inputs_compile_to_same_timeline_and_digest():
    first = compile_example()
    second = compile_example()

    assert first == second
    assert first.scenario_id == second.scenario_id
    assert first.sha256() == second.sha256()
    assert [event.event_id for event in first.events] == [event.event_id for event in second.events]


def test_seed_is_identity_bearing_without_hidden_randomization():
    first = compile_example(seed=17)
    second = compile_example(seed=18)

    assert first.events == second.events
    assert first.scenario_id != second.scenario_id
    assert first.sha256() != second.sha256()


def test_unknown_target_profile_is_explicit_not_guessed():
    scenario = compile_example(profile="UNKNOWN")
    result = replay_fault_scenario(scenario)

    assert scenario.target_profile_digest == "UNKNOWN"
    assert result.target_profile_digest == "UNKNOWN"


def test_generation_invalidating_faults_advance_exact_chain():
    scenario = compile_fault_scenario(
        scenario_name="generation-chain",
        seed=1,
        target_profile_digest=PROFILE,
        start_generation=7,
        specs=(
            spec(PERMISSION_DENY, offset_ms=0),
            spec(PERMISSION_REVOKE, offset_ms=1),
            spec(DEVICE_REMOVE, offset_ms=2),
            spec(DEVICE_READD, offset_ms=3),
            spec(BRIDGE_DISCONNECT, offset_ms=4),
            spec(BRIDGE_RECONNECT, offset_ms=5),
            spec(SUSPEND_RESUME, offset_ms=6),
        ),
    )

    assert [(event.generation_before, event.generation_after) for event in scenario.events] == [
        (7, 7),
        (7, 8),
        (8, 9),
        (9, 10),
        (10, 11),
        (11, 12),
        (12, 13),
    ]
    assert replay_fault_scenario(scenario).final_generation == 13


def test_stale_generation_fault_requires_actual_staleness():
    good = compile_fault_scenario(
        scenario_name="stale-generation",
        seed=2,
        target_profile_digest=PROFILE,
        start_generation=3,
        specs=(spec(STALE_GENERATION, parameters={"claimed_generation": 2}),),
    )
    assert replay_fault_scenario(good).final_generation == 3

    with pytest.raises(TargetFaultScenarioError, match="lower than"):
        compile_fault_scenario(
            scenario_name="not-stale",
            seed=2,
            target_profile_digest=PROFILE,
            start_generation=3,
            specs=(spec(STALE_GENERATION, parameters={"claimed_generation": 3}),),
        )


def test_replay_is_noncanonical_and_mints_no_runtime_or_completion_credit():
    result = replay_fault_scenario(compile_example())

    assert result.classification == FAULT_REPLAY_CLASSIFICATION
    assert result.runtime_execution_observed is False
    assert result.physical_host_credit == 0
    assert result.completion_credit == 0
    assert len(result.applied_event_ids) == 10


def test_replay_counts_heterogeneous_fault_domains():
    result = replay_fault_scenario(compile_example())
    counts = dict(result.domain_counts)

    assert counts["PERMISSION"] == 2
    assert counts["DEVICE"] == 2
    assert counts["SESSION_SERVICE"] == 1
    assert counts["NETWORK_BRIDGE"] == 2
    assert counts["FILESYSTEM_PACKAGE"] == 1
    assert counts["PROCESS_LIFECYCLE"] == 2


def test_required_host_fault_families_are_representable():
    scenario = compile_fault_scenario(
        scenario_name="required-families",
        seed=3,
        target_profile_digest=PROFILE,
        start_generation=10,
        specs=(
            spec(PORTAL_RESTART, "service:portal", 0),
            spec(WIREPLUMBER_RESTART, "service:wireplumber", 1),
            spec(USER_MANAGER_RESTART, "service:systemd-user", 2),
            spec(DNS_FAILURE, "network:dns", 3),
            spec(READ_ONLY, "path:install", 4),
            spec(LOW_SPACE, "path:state", 5, {"remaining_bytes": 1024}),
            spec(PACKAGE_LOCK, "package:apt", 6),
            spec(PARTIAL_INSTALL, "install:f2", 7),
            spec(CLOCK_SKEW, "clock:host", 8, {"offset_ms": 30_000}),
        ),
    )

    actions = {event.action for event in scenario.events}
    assert actions == {
        PORTAL_RESTART,
        WIREPLUMBER_RESTART,
        USER_MANAGER_RESTART,
        DNS_FAILURE,
        READ_ONLY,
        LOW_SPACE,
        PACKAGE_LOCK,
        PARTIAL_INSTALL,
        CLOCK_SKEW,
    }


def test_action_parameter_bounds_fail_closed():
    with pytest.raises(TargetFaultScenarioError):
        spec(NETWORK_LATENCY, parameters={"latency_ms": -1})
    with pytest.raises(TargetFaultScenarioError):
        spec(NETWORK_LOSS, parameters={"loss_percent": 101})
    with pytest.raises(TargetFaultScenarioError):
        spec(LOW_SPACE, parameters={"remaining_bytes": -1})
    with pytest.raises(TargetFaultScenarioError):
        spec(DEVICE_LATE, parameters={"delay_ms": -1})
    with pytest.raises(TargetFaultScenarioError):
        spec(CLOCK_SKEW, parameters={"offset_ms": 100_000_000})


def test_non_json_and_nonfinite_parameters_fail_closed():
    with pytest.raises(TargetFaultScenarioError):
        spec(PERMISSION_DENY, parameters={"bad": object()})
    with pytest.raises(TargetFaultScenarioError):
        spec(PERMISSION_DENY, parameters={"bad": float("nan")})


def test_offsets_must_be_monotonic_in_declared_timeline():
    with pytest.raises(TargetFaultScenarioError, match="monotonic"):
        compile_fault_scenario(
            scenario_name="time-travel",
            seed=4,
            target_profile_digest=PROFILE,
            start_generation=1,
            specs=(
                spec(PROCESS_KILL, offset_ms=100),
                spec(REBOOT, offset_ms=99),
            ),
        )


def test_scenario_identity_detects_post_construction_event_mutation():
    scenario = compile_example()
    object.__setattr__(scenario.events[0], "target", "target:tampered")

    with pytest.raises(TargetFaultScenarioError):
        replay_fault_scenario(scenario)


def test_scenario_identity_detects_post_construction_seed_mutation():
    scenario = compile_example()
    object.__setattr__(scenario, "seed", 999)

    with pytest.raises(TargetFaultScenarioError, match="scenario_id"):
        replay_fault_scenario(scenario)


def test_event_generation_drift_fails_at_consumer_boundary():
    scenario = compile_example()
    object.__setattr__(scenario.events[1], "generation_after", 999)

    with pytest.raises(TargetFaultScenarioError, match="generation transition"):
        replay_fault_scenario(scenario)


def test_event_sequence_drift_fails_at_consumer_boundary():
    scenario = compile_example()
    object.__setattr__(scenario.events[2], "sequence", 99)

    with pytest.raises(TargetFaultScenarioError):
        replay_fault_scenario(scenario)


def test_invalid_profile_digest_fails_closed():
    with pytest.raises(TargetFaultScenarioError):
        compile_example(profile="not-a-digest")


def test_fault_spec_is_revalidated_when_consumed():
    mutable = spec(PERMISSION_DENY, offset_ms=0)
    object.__setattr__(mutable, "action", "UNSUPPORTED_FAULT")

    with pytest.raises(TargetFaultScenarioError, match="unsupported"):
        compile_fault_scenario(
            scenario_name="mutated-spec",
            seed=7,
            target_profile_digest=PROFILE,
            start_generation=2,
            specs=(mutable,),
        )


def test_replay_result_serialization_keeps_domain_counts_explicit():
    result = replay_fault_scenario(compile_example())
    payload = result.as_dict()

    assert payload["domain_counts"]["DEVICE"] == 2
    assert payload["classification"] == FAULT_REPLAY_CLASSIFICATION
    assert payload["physical_host_credit"] == 0
