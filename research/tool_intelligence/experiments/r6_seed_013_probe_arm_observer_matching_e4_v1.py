"""Trigger-6 E4 follow-up for R6-SEED-013.

Source-schema ablation for WP507 CausalProbeArm observer matching.
It tests three policies:
1) current: observer method is unbound/unmatched,
2) compare full ObserverBinding digest across intervention/control,
3) compare the nested ObserverMethod digest while keeping full per-run binding identity.

The goal is to reject measurement-method confounds without overbinding distinct
observer instances that implement the same exact method/config/evidence semantics.
This is not F2 target runtime.
"""
from __future__ import annotations

import hashlib
import json

SOURCE_BLOB_SHA = "f25c03d4e4e49c4fed44acd0c5c96edfb40f664e"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def serialized_bytes(value: object) -> int:
    return len(canonical_json(value).encode("utf-8"))


def method_descriptor(
    *,
    observer_type: str,
    artifact: str,
    config: str,
    method_class: str,
    evidence_class: str,
) -> dict[str, object]:
    return {
        "schema": "FRANKENSTEIN2_GWT_OBSERVER_METHOD/v1",
        "observer_type": observer_type,
        "observer_artifact_sha256": artifact,
        "observer_config_sha256": config,
        "method_class": method_class,
        "evidence_class": evidence_class,
    }


def binding(
    *,
    binding_id: str,
    generation: int,
    instance_id: str,
    method: dict[str, object],
) -> dict[str, object]:
    return {
        "schema": "FRANKENSTEIN2_GWT_OBSERVER_BINDING/v1",
        "binding_id": binding_id,
        "binding_generation": generation,
        "observer_instance_id": instance_id,
        "observer_method_sha256": digest(method),
        "provenance_refs": ["observer-binding-fixture"],
    }


def arm(
    *,
    arm_id: str,
    condition: str,
    output_sha256: str,
    observer_binding_sha256: str | None = None,
) -> dict[str, object]:
    intervention = condition == "INTERVENTION_BROADCAST"
    payload: dict[str, object] = {
        "schema": "FRANKENSTEIN2_GWT_CAUSAL_PROBE_ARM/v2",
        "classification": "DECLARED_MATCHED_PROBE_ARM_NOT_WORLD_TRUTH",
        "arm_id": arm_id,
        "probe_id": "probe-1",
        "condition": condition,
        "nonbroadcast_input_sha256": "a" * 64,
        "downstream_output_sha256": output_sha256,
        "broadcast_id": "b1" if intervention else None,
        "broadcast_sha256": "b" * 64 if intervention else None,
        "provenance_refs": [f"arm:{arm_id}"],
    }
    if observer_binding_sha256 is not None:
        payload["observer_binding_sha256"] = observer_binding_sha256
    return payload


def evaluate(
    *,
    intervention: dict[str, object],
    control: dict[str, object],
    intervention_binding: dict[str, object] | None,
    control_binding: dict[str, object] | None,
    policy: str,
) -> str:
    if intervention["probe_id"] != control["probe_id"]:
        return "UNKNOWN_UNMATCHED_CONTROL"
    if intervention["nonbroadcast_input_sha256"] != control["nonbroadcast_input_sha256"]:
        return "UNKNOWN_UNMATCHED_CONTROL"

    if policy == "FULL_BINDING_EQUAL":
        if intervention_binding is None or control_binding is None:
            return "UNKNOWN_UNMATCHED_OBSERVER"
        if digest(intervention_binding) != digest(control_binding):
            return "UNKNOWN_UNMATCHED_OBSERVER"
    elif policy == "METHOD_DIGEST_EQUAL":
        if intervention_binding is None or control_binding is None:
            return "UNKNOWN_UNMATCHED_OBSERVER"
        if intervention_binding["observer_method_sha256"] != control_binding["observer_method_sha256"]:
            return "UNKNOWN_UNMATCHED_OBSERVER"
    elif policy != "CURRENT_NO_OBSERVER_MATCH":
        raise ValueError(policy)

    if intervention["downstream_output_sha256"] == control["downstream_output_sha256"]:
        return "NO_CAUSAL_INFLUENCE_OBSERVED"
    return "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"


def main() -> None:
    direct_method = method_descriptor(
        observer_type="direct-inprocess-hook/v1",
        artifact="1" * 64,
        config="2" * 64,
        method_class="synchronous_direct",
        evidence_class="DIRECT_INPROCESS",
    )
    direct_method_same = dict(direct_method)
    async_method = method_descriptor(
        observer_type="async-log-scraper/v1",
        artifact="3" * 64,
        config="4" * 64,
        method_class="asynchronous_derived",
        evidence_class="DERIVED_ASYNC",
    )
    direct_instance_a = binding(
        binding_id="binding-direct-a",
        generation=1,
        instance_id="hook-instance-17",
        method=direct_method,
    )
    direct_instance_b = binding(
        binding_id="binding-direct-b",
        generation=1,
        instance_id="hook-instance-18",
        method=direct_method_same,
    )
    async_instance = binding(
        binding_id="binding-async-c",
        generation=1,
        instance_id="scraper-instance-9",
        method=async_method,
    )

    unbound_i = arm(
        arm_id="i",
        condition="INTERVENTION_BROADCAST",
        output_sha256="d" * 64,
    )
    unbound_c = arm(
        arm_id="c",
        condition="CONTROL_NO_BROADCAST",
        output_sha256="e" * 64,
    )
    bound_i = arm(
        arm_id="i",
        condition="INTERVENTION_BROADCAST",
        output_sha256="d" * 64,
        observer_binding_sha256=digest(direct_instance_a),
    )
    bound_c_same_method = arm(
        arm_id="c",
        condition="CONTROL_NO_BROADCAST",
        output_sha256="e" * 64,
        observer_binding_sha256=digest(direct_instance_b),
    )
    bound_c_different_method = arm(
        arm_id="c",
        condition="CONTROL_NO_BROADCAST",
        output_sha256="e" * 64,
        observer_binding_sha256=digest(async_instance),
    )

    same_method = {
        "full_binding_digests_equal": digest(direct_instance_a) == digest(direct_instance_b),
        "method_digests_equal": direct_instance_a["observer_method_sha256"]
        == direct_instance_b["observer_method_sha256"],
        "current_status": evaluate(
            intervention=unbound_i,
            control=unbound_c,
            intervention_binding=direct_instance_a,
            control_binding=direct_instance_b,
            policy="CURRENT_NO_OBSERVER_MATCH",
        ),
        "full_binding_match_policy_status": evaluate(
            intervention=bound_i,
            control=bound_c_same_method,
            intervention_binding=direct_instance_a,
            control_binding=direct_instance_b,
            policy="FULL_BINDING_EQUAL",
        ),
        "method_digest_match_policy_status": evaluate(
            intervention=bound_i,
            control=bound_c_same_method,
            intervention_binding=direct_instance_a,
            control_binding=direct_instance_b,
            policy="METHOD_DIGEST_EQUAL",
        ),
    }
    different_method = {
        "full_binding_digests_equal": digest(direct_instance_a) == digest(async_instance),
        "method_digests_equal": direct_instance_a["observer_method_sha256"]
        == async_instance["observer_method_sha256"],
        "current_status": evaluate(
            intervention=unbound_i,
            control=unbound_c,
            intervention_binding=direct_instance_a,
            control_binding=async_instance,
            policy="CURRENT_NO_OBSERVER_MATCH",
        ),
        "full_binding_match_policy_status": evaluate(
            intervention=bound_i,
            control=bound_c_different_method,
            intervention_binding=direct_instance_a,
            control_binding=async_instance,
            policy="FULL_BINDING_EQUAL",
        ),
        "method_digest_match_policy_status": evaluate(
            intervention=bound_i,
            control=bound_c_different_method,
            intervention_binding=direct_instance_a,
            control_binding=async_instance,
            policy="METHOD_DIGEST_EQUAL",
        ),
    }

    result = {
        "source_blob_sha": SOURCE_BLOB_SHA,
        "same_method_different_instance": same_method,
        "different_method": different_method,
        "identity_structure": {
            "direct_instance_a_binding_sha256": digest(direct_instance_a),
            "direct_instance_b_binding_sha256": digest(direct_instance_b),
            "direct_method_sha256": digest(direct_method),
            "async_method_sha256": digest(async_method),
        },
        "footprint": {
            "direct_method_descriptor_bytes": serialized_bytes(direct_method),
            "direct_binding_bytes": serialized_bytes(direct_instance_a),
            "arm_observer_binding_reference_increment_bytes": serialized_bytes(bound_i)
            - serialized_bytes(unbound_i),
        },
    }

    assert same_method["full_binding_digests_equal"] is False
    assert same_method["method_digests_equal"] is True
    assert same_method["current_status"] == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
    assert same_method["full_binding_match_policy_status"] == "UNKNOWN_UNMATCHED_OBSERVER"
    assert same_method["method_digest_match_policy_status"] == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"

    assert different_method["method_digests_equal"] is False
    assert different_method["current_status"] == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
    assert different_method["full_binding_match_policy_status"] == "UNKNOWN_UNMATCHED_OBSERVER"
    assert different_method["method_digest_match_policy_status"] == "UNKNOWN_UNMATCHED_OBSERVER"

    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
