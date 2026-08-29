import hashlib
import unittest
from dataclasses import replace

from frankenstein2.generic_agent_route import (
    GenericAgentRouteError,
    ReleaseBinding,
    StateRootClass,
    plan_generic_agent_route,
)
from frankenstein2.host_adapter_abi import (
    AdapterClass,
    CapabilityObservation,
    EvidenceState,
    LifecycleBinding,
    LifecycleVerification,
    TargetEnvironmentBinding,
    assess_host_adapter,
)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def environment() -> TargetEnvironmentBinding:
    return TargetEnvironmentBinding.create(
        profile_generation=4,
        profile_digest=sha("review-wp1104-profile"),
        host_identity="host:review-wp1104",
        state_lineage_id="f2-state:primary",
        adapter_id="generic-agent:semantic-adapter",
        adapter_version="1",
    )


def lifecycle(role: str, env_digest: str) -> LifecycleBinding:
    fields = ("session_id", "agent_id", "task_id", "turn_id", "causal_id")
    if role in {"PRE_EFFECT", "POST_EFFECT", "TOOL_RESULT_RETURN"}:
        fields = fields + ("tool_use_id",)
    return LifecycleBinding(
        semantic_role=role,
        concrete_event=f"observed.{role.lower()}",
        source_surface="review-observed-host-surface",
        verification=LifecycleVerification.VERIFIED,
        evidence_ref=f"receipt:review:{role.lower()}",
        environment_digest=env_digest,
        occurrence_contract="MEASURED_MULTIPLICITY",
        timing_contract="MEASURED_ORDERING",
        payload_identity_fields=fields,
        native_surface=False,
    )


def capability(name: str, env_digest: str) -> CapabilityObservation:
    return CapabilityObservation(
        name=name,
        state=EvidenceState.VERIFIED_ADAPTED,
        concrete_surface=f"surface:{name.lower()}",
        evidence_ref=f"receipt:review:{name.lower()}",
        environment_digest=env_digest,
    )


def valid_report():
    env = environment()
    digest = env.binding_digest()
    roles = (
        "SESSION_START",
        "USER_TURN",
        "PRE_EFFECT",
        "POST_EFFECT",
        "SESSION_STOP",
        "PRE_COMPACT_OR_CHECKPOINT",
        "TOOL_RESULT_RETURN",
    )
    caps = (
        "DURABLE_STATE_PATH",
        "STATE_READBACK",
        "LIFECYCLE_EVENT_BINDING",
        "TOOL_RESULT_BINDING",
    )
    report = assess_host_adapter(
        environment=env,
        lifecycle_bindings=[lifecycle(role, digest) for role in roles],
        capabilities=[capability(name, digest) for name in caps],
        declared_mode=AdapterClass.ADAPTED,
        optional_roles=(),
    )
    return env, report


def route_kwargs(env, capability_report):
    return dict(
        host_family="review-generic-agent",
        host_version="1.0",
        release=ReleaseBinding.create(
            release_id="f2-review-rc",
            release_manifest_digest=sha("review-manifest"),
            source_commit="a" * 40,
            state_migration_version="1",
        ),
        capability_report=capability_report,
        environment_binding_digest=env.binding_digest(),
        state_lineage_id=env.state_lineage_id,
        durable_state_root="/var/lib/frankenstein2/state",
        state_root_class=StateRootClass.DURABLE_USER_DATA,
    )


class WP1104CapabilityReportConsistencyFalsifier(unittest.TestCase):
    """REVIEW_ONLY: caller-supplied report inconsistency must fail closed.

    The active WP1104 contract says missing mandatory lifecycle/capability evidence is
    DEGRADED/BLOCKED and that the route consumes explicit caller-supplied evidence. A
    caller can currently mutate a valid HostCapabilityReport into an internally
    contradictory report whose classification remains ADAPTED while required evidence
    is marked missing/unverified. The route trusts classification and accepts it.

    These tests intentionally fail on the vulnerable implementation. They do not claim
    mutation authority over WP1104.
    """

    def test_missing_required_capability_cannot_arrive_as_adapted(self):
        env, report = valid_report()
        forged = replace(
            report,
            classification=AdapterClass.ADAPTED,
            missing_required_capabilities=("DURABLE_STATE_PATH",),
        )
        with self.assertRaises(GenericAgentRouteError):
            plan_generic_agent_route(**route_kwargs(env, forged))

    def test_unverified_required_lifecycle_role_cannot_arrive_as_adapted(self):
        env, report = valid_report()
        forged = replace(
            report,
            classification=AdapterClass.ADAPTED,
            unverified_required_roles=("PRE_EFFECT",),
        )
        with self.assertRaises(GenericAgentRouteError):
            plan_generic_agent_route(**route_kwargs(env, forged))


if __name__ == "__main__":
    unittest.main()
