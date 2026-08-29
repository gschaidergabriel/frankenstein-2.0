import hashlib
import unittest

from frankenstein2.host_adapter_abi import (
    LifecycleBinding,
    LifecycleVerification,
    SemanticLifecycleEvent,
    TargetEnvironmentBinding,
    verify_semantic_event_binding,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def environment() -> TargetEnvironmentBinding:
    return TargetEnvironmentBinding.create(
        profile_generation=1,
        profile_digest=sha("review-wp1101-payload-identity"),
        host_identity="host:review-only",
        state_lineage_id="state-lineage:review-only",
        adapter_id="adapter:review-only",
        adapter_version="1",
    )


def binding(env_digest: str, required_identity: str) -> LifecycleBinding:
    return LifecycleBinding(
        semantic_role="TOOL_RESULT_RETURN",
        concrete_event="host.tool_result_return",
        source_surface="host-hooks",
        verification=LifecycleVerification.VERIFIED,
        evidence_ref="receipt:review-only",
        environment_digest=env_digest,
        occurrence_contract="MEASURED_MULTIPLICITY",
        timing_contract="MEASURED_ORDERING",
        payload_identity_fields=(
            "session_id",
            "agent_id",
            "task_id",
            "turn_id",
            "causal_id",
            required_identity,
        ),
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


class WP1101PayloadIdentityBindingFalsifier(unittest.TestCase):
    """REVIEW_ONLY: verify_semantic_event_binding must honor the binding's declared identity fields."""

    def test_tool_use_id_contract_rejects_effect_only_event(self):
        env = environment()
        lifecycle = binding(env.binding_digest(), "tool_use_id")
        observed = event(env, effect_id="effect-1")
        self.assertFalse(
            verify_semantic_event_binding(observed, environment=env, binding=lifecycle),
            "effect_id alone must not satisfy a binding that explicitly requires tool_use_id",
        )

    def test_effect_id_contract_rejects_tool_only_event(self):
        env = environment()
        lifecycle = binding(env.binding_digest(), "effect_id")
        observed = event(env, tool_use_id="tool-1")
        self.assertFalse(
            verify_semantic_event_binding(observed, environment=env, binding=lifecycle),
            "tool_use_id alone must not satisfy a binding that explicitly requires effect_id",
        )


if __name__ == "__main__":
    unittest.main()
