#!/usr/bin/env python3
"""REVIEW_ONLY executable falsifier for F2-WP-1101.

Exit 42 means the preregistered gap is reproduced: a required lifecycle role can carry
semantically unverified free-form timing/multiplicity contract strings and still
participate in a NATIVE/ADAPTED HostCapabilityReport.

This file does not mutate production source and grants no runtime/host/product credit.
"""
from __future__ import annotations

import hashlib
import sys

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


env = TargetEnvironmentBinding.create(
    profile_generation=3,
    profile_digest=sha("review-wp1101-target-profile"),
    host_identity="host:review-only",
    state_lineage_id="state-lineage:review-only",
    adapter_id="review-only:semantic-adapter",
    adapter_version="1.0.0",
)
env_digest = env.binding_digest()

required_roles = (
    "SESSION_START",
    "USER_TURN",
    "PRE_EFFECT",
    "POST_EFFECT",
    "SESSION_STOP",
    "PRE_COMPACT_OR_CHECKPOINT",
    "TOOL_RESULT_RETURN",
)

bindings = []
for role in required_roles:
    fields = ("session_id", "agent_id", "task_id", "turn_id", "causal_id")
    if role in {"PRE_EFFECT", "POST_EFFECT", "TOOL_RESULT_RETURN"}:
        fields += ("tool_use_id",)
    bindings.append(
        LifecycleBinding(
            semantic_role=role,
            concrete_event=f"host.{role.lower()}",
            source_surface="review-only-host-hooks",
            verification=LifecycleVerification.VERIFIED,
            evidence_ref=f"review-only-receipt:{role.lower()}",
            environment_digest=env_digest,
            occurrence_contract="UNMEASURED" if role == "SESSION_START" else "MEASURED_MULTIPLICITY",
            timing_contract="UNKNOWN_ORDER" if role == "SESSION_START" else "MEASURED_ORDERING",
            payload_identity_fields=fields,
            native_surface=True,
        )
    )

capabilities = [
    CapabilityObservation(
        name=name,
        state=EvidenceState.VERIFIED_NATIVE,
        concrete_surface=f"review-only:{name.lower()}",
        evidence_ref=f"review-only-receipt:{name.lower()}",
        environment_digest=env_digest,
    )
    for name in (
        "DURABLE_STATE_PATH",
        "STATE_READBACK",
        "LIFECYCLE_EVENT_BINDING",
        "TOOL_RESULT_BINDING",
    )
]

report = assess_host_adapter(
    environment=env,
    lifecycle_bindings=bindings,
    capabilities=capabilities,
    declared_mode=AdapterClass.NATIVE,
    optional_roles=(),
)

print("classification=", report.classification.value)
print("native_surface_complete=", report.native_surface_complete)
print("conflicts=", report.conflicts)
print("limitations=", report.limitations)
print("preregistered_unknown_occurrence=UNMEASURED")
print("preregistered_unknown_timing=UNKNOWN_ORDER")

if report.classification in (AdapterClass.NATIVE, AdapterClass.ADAPTED):
    print("FALSIFIER_REPRODUCED: semantically unverified lifecycle contract metadata did not fail closed")
    sys.exit(42)

print("FALSIFIER_NOT_REPRODUCED: route failed closed")
sys.exit(0)
