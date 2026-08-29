import hashlib
import unittest
from dataclasses import replace

from frankenstein2.generic_agent_route import (
    ASSESSMENT_EVIDENCE_SCHEMA,
    AssessedHostCapabilityEvidence,
    GenericAgentRouteError,
    NativeSupportEvidence,
    ReleaseBinding,
    StateRootClass,
    SupportEvidenceState,
    plan_generic_agent_route,
)
from frankenstein2.host_adapter_abi import (
    AdapterClass,
    CAPABILITY_REPORT_SCHEMA,
    CapabilityObservation,
    EvidenceState,
    HostCapabilityReport,
    LifecycleBinding,
    LifecycleVerification,
    TargetEnvironmentBinding,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def release() -> ReleaseBinding:
    return ReleaseBinding.create(
        release_id="f2-rc-20260829.1",
        release_manifest_digest=sha("manifest"),
        source_commit="a" * 40,
        state_migration_version="3",
    )


def environment() -> TargetEnvironmentBinding:
    return TargetEnvironmentBinding.create(
        profile_generation=4,
        profile_digest=sha("profile-g4"),
        host_identity="host:generic-test",
        state_lineage_id="f2-state:primary",
        adapter_id="generic-agent:semantic-adapter",
        adapter_version="1",
    )


def lifecycle(role: str, env_digest: str, *, native: bool) -> LifecycleBinding:
    fields = ("session_id", "agent_id", "task_id", "turn_id", "causal_id")
    if role in {"PRE_EFFECT", "POST_EFFECT", "TOOL_RESULT_RETURN"}:
        fields = fields + ("tool_use_id",)
    return LifecycleBinding(
        semantic_role=role,
        concrete_event=f"observed.{role.lower()}",
        source_surface="observed-host-surface",
        verification=LifecycleVerification.VERIFIED,
        evidence_ref=f"receipt:{role.lower()}",
        environment_digest=env_digest,
        occurrence_contract="MEASURED_MULTIPLICITY",
        timing_contract="MEASURED_ORDERING",
        payload_identity_fields=fields,
        native_surface=native,
    )


def capability(name: str, env_digest: str, *, native: bool) -> CapabilityObservation:
    return CapabilityObservation(
        name=name,
        state=EvidenceState.VERIFIED_NATIVE if native else EvidenceState.VERIFIED_ADAPTED,
        concrete_surface=f"surface:{name.lower()}",
        evidence_ref=f"receipt:{name.lower()}",
        environment_digest=env_digest,
    )


def assessment(
    *,
    native: bool = False,
    include_background_wake: bool = False,
    omit_role: str | None = None,
    omit_capability: str | None = None,
):
    env = environment()
    digest = env.binding_digest()
    roles = [
        "SESSION_START",
        "USER_TURN",
        "PRE_EFFECT",
        "POST_EFFECT",
        "SESSION_STOP",
        "PRE_COMPACT_OR_CHECKPOINT",
        "TOOL_RESULT_RETURN",
    ]
    if include_background_wake:
        roles.append("BACKGROUND_WAKE")
    if omit_role is not None:
        roles = [role for role in roles if role != omit_role]
    caps = [
        "DURABLE_STATE_PATH",
        "STATE_READBACK",
        "LIFECYCLE_EVENT_BINDING",
        "TOOL_RESULT_BINDING",
    ]
    if omit_capability is not None:
        caps = [name for name in caps if name != omit_capability]

    evidence = AssessedHostCapabilityEvidence.from_observations(
        environment=env,
        lifecycle_bindings=[lifecycle(role, digest, native=native) for role in roles],
        capabilities=[capability(name, digest, native=native) for name in caps],
        declared_mode=AdapterClass.NATIVE if native else AdapterClass.ADAPTED,
        optional_roles=("BACKGROUND_WAKE",) if include_background_wake else (),
    )
    return env, evidence.report, evidence


def plan_kwargs(env, capability_report, capability_evidence=None):
    return dict(
        host_family="other-coding-agent",
        host_version="9.4.1",
        release=release(),
        capability_report=capability_report,
        capability_evidence=capability_evidence,
        environment_binding_digest=env.binding_digest(),
        state_lineage_id=env.state_lineage_id,
        durable_state_root="/var/lib/frankenstein2/state",
        state_root_class=StateRootClass.DURABLE_USER_DATA,
    )


class GenericAgentRouteTests(unittest.TestCase):
    def test_verified_generic_semantics_classify_adapted_without_product_guessing(self):
        env, capability_report, evidence = assessment(native=False)
        route = plan_generic_agent_route(**plan_kwargs(env, capability_report, evidence))
        self.assertIs(route.classification, AdapterClass.ADAPTED)
        self.assertFalse(route.mutation_authority)
        self.assertFalse(route.completion_authority)
        self.assertFalse(route.physical_host_credit)
        self.assertFalse(route.installer_runtime_credit)
        self.assertFalse(route.baseline_local_boot_requires_vps)

    def test_native_capability_report_cannot_self_mint_generic_native_release_support(self):
        env, capability_report, evidence = assessment(native=True)
        route = plan_generic_agent_route(**plan_kwargs(env, capability_report, evidence))
        self.assertIs(route.classification, AdapterClass.ADAPTED)
        self.assertIn("GENERIC_NATIVE_SUPPORT_NOT_RELEASE_VERIFIED", route.limitations)
        self.assertIsNone(route.native_support_evidence_ref)

    def test_exact_verified_release_native_support_can_preserve_native_classification(self):
        env, capability_report, evidence = assessment(native=True)
        rel = release()
        support = NativeSupportEvidence.create(
            state=SupportEvidenceState.VERIFIED,
            release_binding_digest=rel.binding_digest(),
            environment_binding_digest=env.binding_digest(),
            host_family="other-coding-agent",
            evidence_ref="receipt:native-support:f2-rc-20260829.1",
        )
        kwargs = plan_kwargs(env, capability_report, evidence)
        kwargs["release"] = rel
        kwargs["native_support"] = support
        route = plan_generic_agent_route(**kwargs)
        self.assertIs(route.classification, AdapterClass.NATIVE)
        self.assertEqual(route.native_support_evidence_ref, support.evidence_ref)

    def test_declared_only_native_support_does_not_mint_native(self):
        env, capability_report, evidence = assessment(native=True)
        rel = release()
        support = NativeSupportEvidence.create(
            state=SupportEvidenceState.DECLARED_ONLY,
            release_binding_digest=rel.binding_digest(),
            environment_binding_digest=env.binding_digest(),
            host_family="other-coding-agent",
            evidence_ref="documentation-only",
        )
        kwargs = plan_kwargs(env, capability_report, evidence)
        kwargs["release"] = rel
        kwargs["native_support"] = support
        route = plan_generic_agent_route(**kwargs)
        self.assertIs(route.classification, AdapterClass.ADAPTED)
        self.assertIn("GENERIC_NATIVE_SUPPORT_NOT_RELEASE_VERIFIED", route.limitations)

    def test_wrong_environment_native_support_does_not_mint_native(self):
        env, capability_report, evidence = assessment(native=True)
        rel = release()
        support = NativeSupportEvidence.create(
            state=SupportEvidenceState.VERIFIED,
            release_binding_digest=rel.binding_digest(),
            environment_binding_digest=sha("other-environment"),
            host_family="other-coding-agent",
            evidence_ref="receipt:native-support:other-environment",
        )
        kwargs = plan_kwargs(env, capability_report, evidence)
        kwargs["release"] = rel
        kwargs["native_support"] = support
        route = plan_generic_agent_route(**kwargs)
        self.assertIs(route.classification, AdapterClass.ADAPTED)

    def test_real_missing_required_capability_stays_blocked_without_positive_credit(self):
        env, capability_report, evidence = assessment(
            native=False,
            omit_capability="DURABLE_STATE_PATH",
        )
        self.assertIs(capability_report.classification, AdapterClass.BLOCKED)
        route = plan_generic_agent_route(**plan_kwargs(env, capability_report, evidence))
        self.assertIs(route.classification, AdapterClass.BLOCKED)
        self.assertFalse(route.physical_host_credit)
        self.assertFalse(route.completion_authority)

    def test_missing_required_capability_cannot_arrive_as_adapted(self):
        env, capability_report, evidence = assessment(native=False)
        forged = replace(
            capability_report,
            classification=AdapterClass.ADAPTED,
            missing_required_capabilities=("DURABLE_STATE_PATH",),
        )
        with self.assertRaisesRegex(
            GenericAgentRouteError,
            "CAPABILITY_REPORT_REQUIRED_DEFICIT_CLASSIFICATION_MISMATCH",
        ):
            plan_generic_agent_route(**plan_kwargs(env, forged, evidence))

    def test_unverified_required_lifecycle_role_cannot_arrive_as_adapted(self):
        env, capability_report, evidence = assessment(native=False)
        forged = replace(
            capability_report,
            classification=AdapterClass.ADAPTED,
            unverified_required_roles=("PRE_EFFECT",),
        )
        with self.assertRaisesRegex(
            GenericAgentRouteError,
            "CAPABILITY_REPORT_REQUIRED_DEFICIT_CLASSIFICATION_MISMATCH",
        ):
            plan_generic_agent_route(**plan_kwargs(env, forged, evidence))

    def test_pr495_direct_report_constructor_bypass_now_fails_closed(self):
        env_digest = "a" * 64
        forged = HostCapabilityReport(
            schema=CAPABILITY_REPORT_SCHEMA,
            classification=AdapterClass.ADAPTED,
            environment_binding_digest=env_digest,
            state_lineage_id="lineage-1",
            required_roles=(),
            required_capabilities=(),
            optional_roles=(),
            optional_capabilities=(),
            missing_required_roles=(),
            unverified_required_roles=(),
            missing_optional_roles=(),
            missing_required_capabilities=(),
            unverified_required_capabilities=(),
            missing_optional_capabilities=(),
            conflicts=(),
            limitations=(),
            native_surface_complete=False,
            completion_authority=False,
            physical_host_credit=False,
        )
        rel = ReleaseBinding.create(
            release_id="f2-review-release",
            release_manifest_digest="b" * 64,
            source_commit="c" * 40,
            state_migration_version="v1",
        )
        with self.assertRaisesRegex(
            GenericAgentRouteError,
            "CAPABILITY_REPORT_PRODUCER_LINEAGE_REQUIRED",
        ):
            plan_generic_agent_route(
                host_family="unknown-generic-agent",
                host_version="0",
                release=rel,
                capability_report=forged,
                environment_binding_digest=env_digest,
                state_lineage_id="lineage-1",
                durable_state_root="/var/lib/frankenstein2",
                state_root_class=StateRootClass.DURABLE_USER_DATA,
            )

    def test_direct_assessment_envelope_constructor_cannot_mint_producer_origin(self):
        env, capability_report, evidence = assessment(native=False)
        with self.assertRaisesRegex(
            GenericAgentRouteError,
            "ASSESSMENT_EVIDENCE_PRODUCER_ORIGIN_REQUIRED",
        ):
            AssessedHostCapabilityEvidence(
                schema=ASSESSMENT_EVIDENCE_SCHEMA,
                environment=env,
                lifecycle_bindings=evidence.lifecycle_bindings,
                capabilities=evidence.capabilities,
                declared_mode=evidence.declared_mode,
                optional_roles=evidence.optional_roles,
                optional_capabilities=evidence.optional_capabilities,
                report=capability_report,
                _origin=object(),
            )

    def test_report_tampering_after_real_assessment_fails_recompute_match(self):
        env, capability_report, evidence = assessment(native=False)
        forged = replace(capability_report, limitations=("SELF_ASSERTED",))
        with self.assertRaisesRegex(
            GenericAgentRouteError,
            "CAPABILITY_REPORT_PRODUCER_LINEAGE_MISMATCH",
        ):
            plan_generic_agent_route(**plan_kwargs(env, forged, evidence))

    def test_disposable_or_unknown_state_root_fails_closed(self):
        env, capability_report, evidence = assessment(native=False)
        for state_root_class in (
            StateRootClass.HOST_PLUGIN_CACHE,
            StateRootClass.HOST_CACHE,
            StateRootClass.TEMPORARY,
            StateRootClass.UNKNOWN,
        ):
            kwargs = plan_kwargs(env, capability_report, evidence)
            kwargs["state_root_class"] = state_root_class
            with self.assertRaisesRegex(
                GenericAgentRouteError,
                "CANONICAL_STATE_ROOT_NOT_DURABLE_USER_DATA",
            ):
                plan_generic_agent_route(**kwargs)

    def test_state_lineage_mismatch_fails_closed(self):
        env, capability_report, evidence = assessment(native=False)
        kwargs = plan_kwargs(env, capability_report, evidence)
        kwargs["state_lineage_id"] = "f2-state:other"
        with self.assertRaisesRegex(
            GenericAgentRouteError,
            "CAPABILITY_REPORT_STATE_LINEAGE_MISMATCH",
        ):
            plan_generic_agent_route(**kwargs)

    def test_environment_mismatch_fails_closed(self):
        env, capability_report, evidence = assessment(native=False)
        kwargs = plan_kwargs(env, capability_report, evidence)
        kwargs["environment_binding_digest"] = sha("different-environment")
        with self.assertRaisesRegex(
            GenericAgentRouteError,
            "CAPABILITY_REPORT_ENVIRONMENT_MISMATCH",
        ):
            plan_generic_agent_route(**kwargs)

    def test_upstream_report_cannot_arrive_with_completion_or_physical_credit(self):
        env, capability_report, evidence = assessment(native=False)
        for field_name, error in (
            ("completion_authority", "CAPABILITY_REPORT_MUST_NOT_HAVE_COMPLETION_AUTHORITY"),
            ("physical_host_credit", "CAPABILITY_REPORT_MUST_NOT_HAVE_PHYSICAL_HOST_CREDIT"),
        ):
            poisoned = replace(capability_report, **{field_name: True})
            with self.assertRaisesRegex(GenericAgentRouteError, error):
                plan_generic_agent_route(**plan_kwargs(env, poisoned, evidence))

    def test_route_digest_is_deterministic(self):
        env, capability_report, evidence = assessment(native=False)
        a = plan_generic_agent_route(**plan_kwargs(env, capability_report, evidence))
        b = plan_generic_agent_route(**plan_kwargs(env, capability_report, evidence))
        self.assertEqual(a.canonical_json(), b.canonical_json())
        self.assertEqual(a.route_digest(), b.route_digest())


if __name__ == "__main__":
    unittest.main()
