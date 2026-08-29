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
        profile_digest=sha("target-profile-g3"),
        host_identity="host:um790-test",
        state_lineage_id="state-lineage:primary",
        adapter_id="claude-code:semantic-adapter",
        adapter_version="1.2.3",
    )


def lifecycle(role: str, env_digest: str, *, native: bool = True, verification=LifecycleVerification.VERIFIED):
    fields = ("session_id", "agent_id", "task_id", "turn_id", "causal_id")
    if role in {"PRE_EFFECT", "POST_EFFECT", "TOOL_RESULT_RETURN"}:
        fields = fields + ("tool_use_id",)
    return LifecycleBinding(
        semantic_role=role,
        concrete_event=f"host.{role.lower()}",
        source_surface="host-hooks",
        verification=verification,
        evidence_ref=f"receipt:{role.lower()}",
        environment_digest=env_digest,
        occurrence_contract="MEASURED_MULTIPLICITY",
        timing_contract="MEASURED_ORDERING",
        payload_identity_fields=fields,
        native_surface=native,
    )


def capabilities(env_digest: str, *, native: bool = True):
    state = EvidenceState.VERIFIED_NATIVE if native else EvidenceState.VERIFIED_ADAPTED
    return [
        CapabilityObservation(
            name=name,
            state=state,
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


def required_lifecycle(env_digest: str, *, native: bool = True):
    return [
        lifecycle(role, env_digest, native=native)
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


class HostAdapterABITests(unittest.TestCase):
    def test_exact_verified_native_surface_classifies_native_when_optional_wake_not_requested(self):
        env = environment()
        digest = env.binding_digest()
        report = assess_host_adapter(
            environment=env,
            lifecycle_bindings=required_lifecycle(digest),
            capabilities=capabilities(digest),
            declared_mode=AdapterClass.NATIVE,
            optional_roles=(),
        )
        self.assertIs(report.classification, AdapterClass.NATIVE)
        self.assertTrue(report.native_surface_complete)
        self.assertFalse(report.completion_authority)
        self.assertFalse(report.physical_host_credit)

    def test_missing_background_wake_is_degraded_not_fake_native_by_default(self):
        env = environment()
        digest = env.binding_digest()
        report = assess_host_adapter(
            environment=env,
            lifecycle_bindings=required_lifecycle(digest),
            capabilities=capabilities(digest),
            declared_mode=AdapterClass.NATIVE,
        )
        self.assertIs(report.classification, AdapterClass.DEGRADED)
        self.assertEqual(report.missing_optional_roles, ("BACKGROUND_WAKE",))

    def test_declared_only_required_hook_blocks_route_even_if_name_matches(self):
        env = environment()
        digest = env.binding_digest()
        bindings = required_lifecycle(digest)
        bindings = [
            lifecycle("POST_EFFECT", digest, verification=LifecycleVerification.DECLARED_ONLY)
            if item.semantic_role == "POST_EFFECT"
            else item
            for item in bindings
        ]
        report = assess_host_adapter(
            environment=env,
            lifecycle_bindings=bindings,
            capabilities=capabilities(digest),
            declared_mode=AdapterClass.NATIVE,
            optional_roles=(),
        )
        self.assertIs(report.classification, AdapterClass.BLOCKED)
        self.assertEqual(report.unverified_required_roles, ("POST_EFFECT",))

    def test_unknown_required_capability_blocks_instead_of_absence_of_error_pass(self):
        env = environment()
        digest = env.binding_digest()
        caps = capabilities(digest)
        caps[-1] = CapabilityObservation(
            name="TOOL_RESULT_BINDING",
            state=EvidenceState.UNKNOWN,
            detail="host API not yet observed",
        )
        report = assess_host_adapter(
            environment=env,
            lifecycle_bindings=required_lifecycle(digest),
            capabilities=caps,
            declared_mode=AdapterClass.NATIVE,
            optional_roles=(),
        )
        self.assertIs(report.classification, AdapterClass.BLOCKED)
        self.assertEqual(report.unverified_required_capabilities, ("TOOL_RESULT_BINDING",))

    def test_environment_mismatch_invalidates_verified_surface(self):
        env = environment()
        digest = env.binding_digest()
        wrong = sha("different-env")
        bindings = required_lifecycle(digest)
        bindings[0] = lifecycle("SESSION_START", wrong)
        report = assess_host_adapter(
            environment=env,
            lifecycle_bindings=bindings,
            capabilities=capabilities(digest),
            declared_mode=AdapterClass.NATIVE,
            optional_roles=(),
        )
        self.assertIs(report.classification, AdapterClass.BLOCKED)
        self.assertIn("ROLE_ENVIRONMENT_MISMATCH:SESSION_START", report.conflicts)

    def test_verified_effect_binding_requires_causal_and_effect_or_tool_identity(self):
        env = environment()
        digest = env.binding_digest()
        with self.assertRaisesRegex(HostABIError, "PRE_EFFECT_MISSING_EFFECT_OR_TOOL_IDENTITY"):
            LifecycleBinding(
                semantic_role="PRE_EFFECT",
                concrete_event="before_tool",
                source_surface="host",
                verification=LifecycleVerification.VERIFIED,
                evidence_ref="r1",
                environment_digest=digest,
                occurrence_contract="ONCE",
                timing_contract="BEFORE",
                payload_identity_fields=("session_id", "causal_id"),
                native_surface=True,
            )

    def test_adapted_verified_surface_classifies_adapted(self):
        env = environment()
        digest = env.binding_digest()
        report = assess_host_adapter(
            environment=env,
            lifecycle_bindings=required_lifecycle(digest, native=False),
            capabilities=capabilities(digest, native=False),
            declared_mode=AdapterClass.ADAPTED,
            optional_roles=(),
        )
        self.assertIs(report.classification, AdapterClass.ADAPTED)
        self.assertFalse(report.native_surface_complete)

    def test_semantic_event_requires_full_worker_lineage_and_effect_identity(self):
        env = environment()
        digest = env.binding_digest()
        with self.assertRaisesRegex(HostABIError, "POST_EFFECT_EVENT_MISSING_EFFECT_OR_TOOL_ID"):
            SemanticLifecycleEvent.create(
                role="POST_EFFECT",
                environment_digest=digest,
                state_lineage_id=env.state_lineage_id,
                adapter_id=env.adapter_id,
                session_id="s",
                agent_id="a",
                task_id="t",
                turn_id="u",
                causal_id="c",
                generation=1,
                concrete_event="after_tool",
                occurrence_index=0,
                payload_digest=sha("payload"),
            )

    def test_semantic_event_verifies_only_against_exact_environment_and_adapter_binding(self):
        env = environment()
        digest = env.binding_digest()
        binding = lifecycle("TOOL_RESULT_RETURN", digest)
        event = SemanticLifecycleEvent.create(
            role="TOOL_RESULT_RETURN",
            environment_digest=digest,
            state_lineage_id=env.state_lineage_id,
            adapter_id=env.adapter_id,
            session_id="session-1",
            agent_id="agent-2",
            task_id="task-3",
            turn_id="turn-4",
            causal_id="causal-5",
            generation=7,
            concrete_event=binding.concrete_event,
            occurrence_index=0,
            payload_digest=sha("result-payload"),
            tool_use_id="tool-6",
        )
        self.assertTrue(verify_semantic_event_binding(event, environment=env, binding=binding))
        other_env = TargetEnvironmentBinding.create(
            profile_generation=4,
            profile_digest=sha("target-profile-g4"),
            host_identity=env.host_identity,
            state_lineage_id=env.state_lineage_id,
            adapter_id=env.adapter_id,
            adapter_version=env.adapter_version,
        )
        self.assertFalse(verify_semantic_event_binding(event, environment=other_env, binding=binding))

    def test_duplicate_semantic_role_mapping_is_rejected(self):
        env = environment()
        digest = env.binding_digest()
        item = lifecycle("SESSION_START", digest)
        with self.assertRaisesRegex(HostABIError, "DUPLICATE_SEMANTIC_ROLE_BINDING"):
            assess_host_adapter(
                environment=env,
                lifecycle_bindings=[item, item],
                capabilities=capabilities(digest),
                declared_mode=AdapterClass.NATIVE,
                optional_roles=(),
            )

    def test_report_digest_is_deterministic(self):
        env = environment()
        digest = env.binding_digest()
        kwargs = dict(
            environment=env,
            lifecycle_bindings=required_lifecycle(digest),
            capabilities=capabilities(digest),
            declared_mode=AdapterClass.NATIVE,
            optional_roles=(),
        )
        a = assess_host_adapter(**kwargs)
        b = assess_host_adapter(**kwargs)
        self.assertEqual(a.canonical_json(), b.canonical_json())
        self.assertEqual(a.report_digest(), b.report_digest())


if __name__ == "__main__":
    unittest.main()
