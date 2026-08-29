import pytest

from frankenstein2.host_transition import (
    CanonicalStateBinding, HostRouteEvidence, HostTransitionError,
    HostTransitionRequest, OP_DISABLE, OP_REENABLE, OP_SWITCH_HOST,
    OP_UNINSTALL, OP_WITHDRAW_PERMISSIONS, ROUTE_ADAPTED, ROUTE_BLOCKED,
    ROUTE_NATIVE, STEP_BIND_SUCCESSOR, STEP_RETAIN_STATE, STEP_UNINSTALL,
    STEP_WITHDRAW, plan_host_transition,
)

H = "a" * 64


def state(root_path="/home/user/.local/share/frankenstein2/state"):
    return CanonicalStateBinding.create(lineage_id="lineage-1", generation=7, state_sha256=H, root_path=root_path)


def route(host_id="codex", route_id="codex-adapter", status=ROUTE_ADAPTED, lifecycle=True, readback=True):
    return HostRouteEvidence.create(host_id=host_id, route_id=route_id, route_status=status, capability_evidence_ref="evidence/capabilities.json", lifecycle_firing_evidence_ref="evidence/lifecycle.json" if lifecycle else None, state_readback_evidence_ref="evidence/readback.json" if readback else None)


def req(operation, **kwargs):
    s = kwargs.pop("state", state())
    return HostTransitionRequest.create(transition_id=f"transition-{operation.lower()}", operation=operation, source_host_id="claude", source_route_id="claude-native", state=s, permissions_before=kwargs.pop("permissions_before", ("camera", "microphone")), permissions_after=kwargs.pop("permissions_after", ("camera", "microphone")), **kwargs)


def test_disable_retains_canonical_state_and_zero_credit():
    plan = plan_host_transition(req(OP_DISABLE))
    assert STEP_RETAIN_STATE in plan.steps
    assert plan.state_lineage_id == "lineage-1"
    assert plan.runtime_credit == plan.physical_host_credit == 0
    assert plan.whole_system_acceptance is False


def test_uninstall_removes_adapter_not_state():
    plan = plan_host_transition(req(OP_UNINSTALL))
    assert STEP_UNINSTALL in plan.steps
    assert plan.steps.index(STEP_UNINSTALL) < plan.steps.index(STEP_RETAIN_STATE)


def test_permission_withdrawal_is_monotonic_and_explicit():
    plan = plan_host_transition(req(OP_WITHDRAW_PERMISSIONS, permissions_before=("camera", "microphone"), permissions_after=("camera",)))
    assert plan.withdrawn_permissions == ("microphone",)
    assert STEP_WITHDRAW in plan.steps


def test_permission_expansion_is_rejected():
    with pytest.raises(HostTransitionError, match="cannot expand permissions"):
        req(OP_WITHDRAW_PERMISSIONS, permissions_before=("camera",), permissions_after=("camera", "microphone"))


def test_permission_change_under_wrong_operation_is_rejected():
    with pytest.raises(HostTransitionError, match="explicit WITHDRAW_PERMISSIONS"):
        req(OP_DISABLE, permissions_before=("camera", "microphone"), permissions_after=("camera",))


def test_switch_requires_verified_successor_and_preserves_lineage():
    plan = plan_host_transition(req(OP_SWITCH_HOST, successor_route=route()))
    assert STEP_BIND_SUCCESSOR in plan.steps
    assert plan.target_host_id == "codex"
    assert plan.state_lineage_id == "lineage-1"


def test_switch_rejects_blocked_successor():
    with pytest.raises(HostTransitionError, match="NATIVE or ADAPTED"):
        req(OP_SWITCH_HOST, successor_route=route(status=ROUTE_BLOCKED))


def test_switch_rejects_missing_lifecycle_firing_evidence():
    with pytest.raises(HostTransitionError, match="lifecycle firing"):
        req(OP_SWITCH_HOST, successor_route=route(lifecycle=False))


def test_switch_rejects_missing_state_readback_evidence():
    with pytest.raises(HostTransitionError, match="state readback"):
        req(OP_SWITCH_HOST, successor_route=route(readback=False))


def test_switch_rejects_same_host_identity():
    with pytest.raises(HostTransitionError, match="must differ"):
        req(OP_SWITCH_HOST, successor_route=route(host_id="claude", route_id="other"))


def test_cache_state_root_cannot_be_canonical():
    with pytest.raises(HostTransitionError, match="transient or cache-like"):
        state("/home/user/.cache/frankenstein2/state")


def test_destructive_state_authority_is_out_of_scope():
    with pytest.raises(HostTransitionError, match="no authority to delete"):
        HostTransitionRequest.create(transition_id="delete", operation=OP_DISABLE, source_host_id="claude", source_route_id="claude-native", state=state(), permissions_before=("camera",), permissions_after=("camera",), destructive_state_authority_ref="owner/delete-state")


def test_reenable_requires_exact_verified_source_route():
    rollback = route(host_id="claude", route_id="claude-native", status=ROUTE_NATIVE)
    plan = plan_host_transition(req(OP_REENABLE, rollback_route=rollback))
    assert plan.rollback_host_id == "claude"
    assert plan.rollback_route_id == "claude-native"


def test_reenable_rejects_different_rollback_route():
    rollback = route(host_id="claude", route_id="other", status=ROUTE_NATIVE)
    with pytest.raises(HostTransitionError, match="source route identity"):
        req(OP_REENABLE, rollback_route=rollback)


def test_state_digest_fence_detects_tampering():
    s = state()
    with pytest.raises(HostTransitionError, match="digest fence"):
        HostTransitionRequest(schema="FRANKENSTEIN2_HOST_TRANSITION_REQUEST/v1", transition_id="tamper", operation=OP_DISABLE, source_host_id="claude", source_route_id="claude-native", state=s, expected_state_binding_sha256="b" * 64, permissions_before=("camera",), permissions_after=("camera",))


def test_plan_is_deterministic():
    r = req(OP_SWITCH_HOST, successor_route=route())
    a = plan_host_transition(r)
    b = plan_host_transition(r)
    assert a.as_dict() == b.as_dict()
    assert a.sha256() == b.sha256()
