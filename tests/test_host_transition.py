import unittest

from frankenstein2.host_transition import (
    CanonicalStateBinding,
    HostRouteEvidence,
    HostTransitionError,
    HostTransitionRequest,
    OP_DISABLE,
    OP_REENABLE,
    OP_SWITCH_HOST,
    OP_UNINSTALL,
    OP_WITHDRAW_PERMISSIONS,
    ROUTE_ADAPTED,
    ROUTE_BLOCKED,
    ROUTE_NATIVE,
    STEP_BIND_SUCCESSOR,
    STEP_RETAIN_STATE,
    STEP_UNINSTALL,
    STEP_WITHDRAW,
    plan_host_transition,
)

H = "a" * 64


def state(root_path="/home/user/.local/share/frankenstein2/state"):
    return CanonicalStateBinding.create(
        lineage_id="lineage-1", generation=7, state_sha256=H, root_path=root_path
    )


def route(
    host_id="codex",
    route_id="codex-adapter",
    status=ROUTE_ADAPTED,
    lifecycle=True,
    readback=True,
    typed_readback=True,
    bound_state=None,
    lineage_id=None,
    generation=None,
    state_sha256=None,
    binding_sha256=None,
):
    bound_state = state() if bound_state is None else bound_state
    typed = readback and typed_readback
    return HostRouteEvidence.create(
        host_id=host_id,
        route_id=route_id,
        route_status=status,
        capability_evidence_ref="evidence/capabilities.json",
        lifecycle_firing_evidence_ref="evidence/lifecycle.json" if lifecycle else None,
        state_readback_evidence_ref="evidence/readback.json" if readback else None,
        state_readback_lineage_id=(
            bound_state.lineage_id if typed and lineage_id is None else lineage_id
        ),
        state_readback_generation=(
            bound_state.generation if typed and generation is None else generation
        ),
        state_readback_state_sha256=(
            bound_state.state_sha256 if typed and state_sha256 is None else state_sha256
        ),
        state_readback_binding_sha256=(
            bound_state.sha256() if typed and binding_sha256 is None else binding_sha256
        ),
    )


def req(operation, **kwargs):
    s = kwargs.pop("state", state())
    return HostTransitionRequest.create(
        transition_id=f"transition-{operation.lower()}",
        operation=operation,
        source_host_id="claude",
        source_route_id="claude-native",
        state=s,
        permissions_before=kwargs.pop("permissions_before", ("camera", "microphone")),
        permissions_after=kwargs.pop("permissions_after", ("camera", "microphone")),
        **kwargs,
    )


class HostTransitionTests(unittest.TestCase):
    def test_disable_retains_canonical_state_and_zero_credit(self):
        plan = plan_host_transition(req(OP_DISABLE))
        self.assertIn(STEP_RETAIN_STATE, plan.steps)
        self.assertEqual(plan.state_lineage_id, "lineage-1")
        self.assertEqual(plan.runtime_credit, 0)
        self.assertEqual(plan.physical_host_credit, 0)
        self.assertFalse(plan.whole_system_acceptance)

    def test_uninstall_removes_adapter_not_state(self):
        plan = plan_host_transition(req(OP_UNINSTALL))
        self.assertIn(STEP_UNINSTALL, plan.steps)
        self.assertLess(plan.steps.index(STEP_UNINSTALL), plan.steps.index(STEP_RETAIN_STATE))

    def test_permission_withdrawal_is_monotonic_and_explicit(self):
        plan = plan_host_transition(
            req(
                OP_WITHDRAW_PERMISSIONS,
                permissions_before=("camera", "microphone"),
                permissions_after=("camera",),
            )
        )
        self.assertEqual(plan.withdrawn_permissions, ("microphone",))
        self.assertIn(STEP_WITHDRAW, plan.steps)

    def test_permission_expansion_is_rejected(self):
        with self.assertRaisesRegex(HostTransitionError, "cannot expand permissions"):
            req(
                OP_WITHDRAW_PERMISSIONS,
                permissions_before=("camera",),
                permissions_after=("camera", "microphone"),
            )

    def test_permission_change_under_wrong_operation_is_rejected(self):
        with self.assertRaisesRegex(HostTransitionError, "explicit WITHDRAW_PERMISSIONS"):
            req(
                OP_DISABLE,
                permissions_before=("camera", "microphone"),
                permissions_after=("camera",),
            )

    def test_switch_requires_verified_successor_and_preserves_lineage(self):
        plan = plan_host_transition(req(OP_SWITCH_HOST, successor_route=route()))
        self.assertIn(STEP_BIND_SUCCESSOR, plan.steps)
        self.assertEqual(plan.target_host_id, "codex")
        self.assertEqual(plan.state_lineage_id, "lineage-1")

    def test_switch_rejects_blocked_successor(self):
        with self.assertRaisesRegex(HostTransitionError, "NATIVE or ADAPTED"):
            req(OP_SWITCH_HOST, successor_route=route(status=ROUTE_BLOCKED))

    def test_switch_rejects_missing_lifecycle_firing_evidence(self):
        with self.assertRaisesRegex(HostTransitionError, "lifecycle firing"):
            req(OP_SWITCH_HOST, successor_route=route(lifecycle=False))

    def test_switch_rejects_missing_state_readback_evidence(self):
        with self.assertRaisesRegex(HostTransitionError, "state readback"):
            req(OP_SWITCH_HOST, successor_route=route(readback=False))

    def test_switch_rejects_untyped_state_readback_identity(self):
        with self.assertRaisesRegex(HostTransitionError, "typed durable state readback identity"):
            req(
                OP_SWITCH_HOST,
                successor_route=route(typed_readback=False),
            )

    def test_switch_rejects_state_readback_lineage_mismatch(self):
        with self.assertRaisesRegex(HostTransitionError, "readback lineage mismatch"):
            req(
                OP_SWITCH_HOST,
                successor_route=route(lineage_id="lineage-other"),
            )

    def test_switch_rejects_state_readback_generation_mismatch(self):
        with self.assertRaisesRegex(HostTransitionError, "readback generation mismatch"):
            req(OP_SWITCH_HOST, successor_route=route(generation=8))

    def test_switch_rejects_state_readback_state_digest_mismatch(self):
        with self.assertRaisesRegex(HostTransitionError, "readback state digest mismatch"):
            req(OP_SWITCH_HOST, successor_route=route(state_sha256="b" * 64))

    def test_switch_rejects_state_readback_binding_digest_mismatch(self):
        with self.assertRaisesRegex(HostTransitionError, "readback binding digest mismatch"):
            req(OP_SWITCH_HOST, successor_route=route(binding_sha256="c" * 64))

    def test_partial_typed_readback_identity_is_rejected(self):
        with self.assertRaisesRegex(HostTransitionError, "state readback identity must be complete"):
            HostRouteEvidence.create(
                host_id="codex",
                route_id="codex-adapter",
                route_status=ROUTE_ADAPTED,
                capability_evidence_ref="evidence/capabilities.json",
                lifecycle_firing_evidence_ref="evidence/lifecycle.json",
                state_readback_evidence_ref="evidence/readback.json",
                state_readback_lineage_id="lineage-1",
            )

    def test_switch_rejects_same_host_identity(self):
        with self.assertRaisesRegex(HostTransitionError, "must differ"):
            req(OP_SWITCH_HOST, successor_route=route(host_id="claude", route_id="other"))

    def test_cache_state_root_cannot_be_canonical(self):
        with self.assertRaisesRegex(HostTransitionError, "transient or cache-like"):
            state("/home/user/.cache/frankenstein2/state")

    def test_destructive_state_authority_is_out_of_scope(self):
        with self.assertRaisesRegex(HostTransitionError, "no authority to delete"):
            HostTransitionRequest.create(
                transition_id="delete",
                operation=OP_DISABLE,
                source_host_id="claude",
                source_route_id="claude-native",
                state=state(),
                permissions_before=("camera",),
                permissions_after=("camera",),
                destructive_state_authority_ref="owner/delete-state",
            )

    def test_reenable_requires_exact_verified_source_route(self):
        rollback = route(
            host_id="claude", route_id="claude-native", status=ROUTE_NATIVE
        )
        plan = plan_host_transition(req(OP_REENABLE, rollback_route=rollback))
        self.assertEqual(plan.rollback_host_id, "claude")
        self.assertEqual(plan.rollback_route_id, "claude-native")

    def test_reenable_rejects_different_rollback_route(self):
        rollback = route(host_id="claude", route_id="other", status=ROUTE_NATIVE)
        with self.assertRaisesRegex(HostTransitionError, "source route identity"):
            req(OP_REENABLE, rollback_route=rollback)

    def test_reenable_rejects_mismatched_state_readback_binding(self):
        rollback = route(
            host_id="claude",
            route_id="claude-native",
            status=ROUTE_NATIVE,
            binding_sha256="d" * 64,
        )
        with self.assertRaisesRegex(HostTransitionError, "readback binding digest mismatch"):
            req(OP_REENABLE, rollback_route=rollback)

    def test_state_digest_fence_detects_tampering(self):
        s = state()
        with self.assertRaisesRegex(HostTransitionError, "digest fence"):
            HostTransitionRequest(
                schema="FRANKENSTEIN2_HOST_TRANSITION_REQUEST/v1",
                transition_id="tamper",
                operation=OP_DISABLE,
                source_host_id="claude",
                source_route_id="claude-native",
                state=s,
                expected_state_binding_sha256="b" * 64,
                permissions_before=("camera",),
                permissions_after=("camera",),
            )

    def test_plan_is_deterministic(self):
        r = req(OP_SWITCH_HOST, successor_route=route())
        a = plan_host_transition(r)
        b = plan_host_transition(r)
        self.assertEqual(a.as_dict(), b.as_dict())
        self.assertEqual(a.sha256(), b.sha256())


if __name__ == "__main__":
    unittest.main()
