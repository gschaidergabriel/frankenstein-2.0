import hashlib
import unittest

from frankenstein2.host_adapter_abi import (
    AdapterClass,
    CapabilityObservation,
    EvidenceState,
    HostABIError,
    LifecycleBinding,
    LifecycleVerification,
    SemanticLifecycleEvent,
    TargetEnvironmentBinding,
    assess_host_adapter,
    verify_semantic_event_binding,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def environment() -> TargetEnvironmentBinding:
    return TargetEnvironmentBinding.create(
        profile_generation=3,
        profile_digest=sha("wp1101-contract-fences"),
        host_identity="host:contract-fence-test",
        state_lineage_id="state-lineage:contract-fence-test",
        adapter_id="adapter:contract-fence-test",
        adapter_version="1.0.0",
    )


def binding(env_digest: str, role: str, *, required_identity: str | None = None) -> LifecycleBinding:
    fields = ("session_id", "agent_id", "task_id", "turn_id", "causal_id")
    if role in {"PRE_EFFECT", "POST_EFFECT", "TOOL_RESULT_RETURN"}:
        fields += (required_identity or "tool_use_id",)
    return LifecycleBinding(
        semantic_role=role,
        concrete_event=f"host.{role.lower()}",
        source_surface="host-hooks",
        verification=LifecycleVerification.VERIFIED,
        evidence_ref=f"receipt:{role.lower()}",
        environment_digest=env_digest,
        occurrence_contract="MEASURED_MULTIPLICITY",
        timing_contract="MEASURED_ORDERING",
        payload_identity_fields=fields,
        native_surface=True,
    )


def event(env: TargetEnvironmentBinding, *, effect_id=None, tool_use_id=None) -> SemanticLifecycleEvent:
    return SemanticLifecycleEvent.create(
        role="TOOL_RESULT_RETURN",
        environment_digest=env.binding_digest(),
        state_lineage_id=env.state_lineage_id,
        adapter_id=env.adapter_id,
        session_id="session-1",
        agent_id="agent-1",
        task_id="task-1",
        turn_id="turn-1",
        causal_id="causal-1",
        generation=1,
        concrete_event="host.tool_result_return",
        occurrence_index=0,
        payload_digest=sha("payload"),
        effect_id=effect_id,
        tool_use_id=tool_use_id,
    )


def capabilities(env_digest: str):
    return [
        CapabilityObservation(
            name=name,
            state=EvidenceState.VERIFIED_NATIVE,
            concrete_surface=f"surface:{name.lower()}",
            evidence_ref=f"receipt:{name.lower()}",
            environment_digest=env_digest,
        )
        for name in (
            "DURABLE_STATE_PATH",
            "STATE_READBACK",
            "LIFECYCLE_EVENT_BINDING",
            "TOOL_RESULT_BINDING",
        )
    ]


class HostAdapterABIContractFenceTests(unittest.TestCase):
    def test_tool_use_id_contract_rejects_effect_only_event(self):
        env = environment()
        lifecycle = binding(env.binding_digest(), "TOOL_RESULT_RETURN", required_identity="tool_use_id")
        self.assertFalse(
            verify_semantic_event_binding(
                event(env, effect_id="effect-1"), environment=env, binding=lifecycle
            )
        )

    def test_effect_id_contract_rejects_tool_only_event(self):
        env = environment()
        lifecycle = binding(env.binding_digest(), "TOOL_RESULT_RETURN", required_identity="effect_id")
        self.assertFalse(
            verify_semantic_event_binding(
                event(env, tool_use_id="tool-1"), environment=env, binding=lifecycle
            )
        )

    def test_declared_tool_identity_accepts_matching_event(self):
        env = environment()
        lifecycle = binding(env.binding_digest(), "TOOL_RESULT_RETURN", required_identity="tool_use_id")
        self.assertTrue(
            verify_semantic_event_binding(
                event(env, tool_use_id="tool-1"), environment=env, binding=lifecycle
            )
        )

    def test_verified_binding_rejects_unmeasured_occurrence_contract(self):
        env = environment()
        with self.assertRaisesRegex(HostABIError, "UNVERIFIED_OCCURRENCE_CONTRACT"):
            LifecycleBinding(
                semantic_role="SESSION_START",
                concrete_event="host.session_start",
                source_surface="host-hooks",
                verification=LifecycleVerification.VERIFIED,
                evidence_ref="receipt:session-start",
                environment_digest=env.binding_digest(),
                occurrence_contract="UNMEASURED",
                timing_contract="MEASURED_ORDERING",
                payload_identity_fields=("session_id", "causal_id"),
                native_surface=True,
            )

    def test_verified_binding_rejects_unknown_timing_contract(self):
        env = environment()
        with self.assertRaisesRegex(HostABIError, "UNVERIFIED_TIMING_CONTRACT"):
            LifecycleBinding(
                semantic_role="SESSION_START",
                concrete_event="host.session_start",
                source_surface="host-hooks",
                verification=LifecycleVerification.VERIFIED,
                evidence_ref="receipt:session-start",
                environment_digest=env.binding_digest(),
                occurrence_contract="MEASURED_MULTIPLICITY",
                timing_contract="UNKNOWN_ORDER",
                payload_identity_fields=("session_id", "causal_id"),
                native_surface=True,
            )

    def test_existing_once_before_contract_remains_valid(self):
        env = environment()
        observed = LifecycleBinding(
            semantic_role="PRE_EFFECT",
            concrete_event="host.pre_effect",
            source_surface="host-hooks",
            verification=LifecycleVerification.VERIFIED,
            evidence_ref="receipt:pre-effect",
            environment_digest=env.binding_digest(),
            occurrence_contract="ONCE",
            timing_contract="BEFORE",
            payload_identity_fields=("session_id", "causal_id", "tool_use_id"),
            native_surface=True,
        )
        self.assertTrue(observed.is_verified)

    def test_unknown_payload_identity_field_fails_closed(self):
        env = environment()
        with self.assertRaisesRegex(HostABIError, "UNKNOWN_PAYLOAD_IDENTITY_FIELD"):
            LifecycleBinding(
                semantic_role="SESSION_START",
                concrete_event="host.session_start",
                source_surface="host-hooks",
                verification=LifecycleVerification.VERIFIED,
                evidence_ref="receipt:session-start",
                environment_digest=env.binding_digest(),
                occurrence_contract="MEASURED_MULTIPLICITY",
                timing_contract="MEASURED_ORDERING",
                payload_identity_fields=("session_id", "invented_identity"),
                native_surface=True,
            )

    def test_post_init_contract_mutation_fails_at_verifier_boundary(self):
        env = environment()
        lifecycle = binding(env.binding_digest(), "TOOL_RESULT_RETURN")
        object.__setattr__(lifecycle, "timing_contract", "UNKNOWN_ORDER")
        self.assertFalse(
            verify_semantic_event_binding(
                event(env, tool_use_id="tool-1"), environment=env, binding=lifecycle
            )
        )

    def test_post_init_contract_mutation_fails_at_assessment_boundary(self):
        env = environment()
        bindings = [
            binding(env.binding_digest(), role)
            for role in (
                "SESSION_START",
                "USER_TURN",
                "PRE_EFFECT",
                "POST_EFFECT",
                "SESSION_STOP",
                "PRE_COMPACT_OR_CHECKPOINT",
                "TOOL_RESULT_RETURN",
            )
        ]
        object.__setattr__(bindings[0], "occurrence_contract", "UNMEASURED")
        with self.assertRaisesRegex(HostABIError, "UNVERIFIED_OCCURRENCE_CONTRACT"):
            assess_host_adapter(
                environment=env,
                lifecycle_bindings=bindings,
                capabilities=capabilities(env.binding_digest()),
                declared_mode=AdapterClass.NATIVE,
                optional_roles=(),
            )


if __name__ == "__main__":
    unittest.main()
