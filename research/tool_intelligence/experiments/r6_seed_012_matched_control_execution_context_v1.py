"""Trigger-6 E3 source-level falsifier for R6-SEED-012.

Reproduces the exact decision boundary of WP507 generation 4 source blob
f25c03d4e4e49c4fed44acd0c5c96edfb40f664e for the matched-probe fields
relevant to execution-context confounding. It does not run a model/provider or
claim real GWT causality.
"""
from __future__ import annotations

import hashlib
import json

WP507_SOURCE_BLOB_SHA = "f25c03d4e4e49c4fed44acd0c5c96edfb40f664e"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def arm(*, arm_id: str, probe_id: str, condition: str, input_sha: str, output_sha: str,
        broadcast_id: str | None, broadcast_sha: str | None) -> dict[str, object]:
    return {
        "schema": "FRANKENSTEIN2_GWT_CAUSAL_PROBE_ARM/v2",
        "classification": "DECLARED_MATCHED_PROBE_ARM_NOT_WORLD_TRUTH",
        "arm_id": arm_id,
        "probe_id": probe_id,
        "condition": condition,
        "nonbroadcast_input_sha256": input_sha,
        "downstream_output_sha256": output_sha,
        "broadcast_id": broadcast_id,
        "broadcast_sha256": broadcast_sha,
        "provenance_refs": ["run:generic"],
    }


def current_wp507_status(intervention: dict[str, object], control: dict[str, object]) -> str:
    if intervention["probe_id"] != control["probe_id"]:
        return "UNKNOWN_UNMATCHED_CONTROL"
    if intervention["broadcast_id"] != "b1" or intervention["broadcast_sha256"] != "a" * 64:
        raise AssertionError("fixture intervention broadcast mismatch")
    if intervention["nonbroadcast_input_sha256"] != control["nonbroadcast_input_sha256"]:
        return "UNKNOWN_UNMATCHED_CONTROL"
    if intervention["downstream_output_sha256"] == control["downstream_output_sha256"]:
        return "NO_CAUSAL_INFLUENCE_OBSERVED"
    return "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"


def main() -> None:
    intervention = arm(
        arm_id="arm-i", probe_id="probe-1", condition="INTERVENTION_BROADCAST",
        input_sha="1" * 64, output_sha="2" * 64,
        broadcast_id="b1", broadcast_sha="a" * 64,
    )
    control = arm(
        arm_id="arm-c", probe_id="probe-1", condition="CONTROL_NO_BROADCAST",
        input_sha="1" * 64, output_sha="3" * 64,
        broadcast_id=None, broadcast_sha=None,
    )
    intervention_context = {
        "runner": "runner-v1", "code": "4" * 64, "model": "engine-A",
        "config_sha256": "5" * 64, "env_sha256": "6" * 64,
        "sample_case_id": "case-1", "attempt_policy": "single",
    }
    control_context = {
        "runner": "runner-v1", "code": "4" * 64, "model": "engine-B",
        "config_sha256": "7" * 64, "env_sha256": "6" * 64,
        "sample_case_id": "case-1", "attempt_policy": "single",
    }
    current_status = current_wp507_status(intervention, control)
    context_i = digest(intervention_context)
    context_c = digest(control_context)
    bound_status = "UNKNOWN_UNMATCHED_CONTROL" if context_i != context_c else current_status
    result = {
        "wp507_source_blob_sha": WP507_SOURCE_BLOB_SHA,
        "intervention_arm_sha256": digest(intervention),
        "control_arm_sha256": digest(control),
        "intervention_execution_context_sha256": context_i,
        "control_execution_context_sha256": context_c,
        "execution_contexts_match": context_i == context_c,
        "current_wp507_status": current_status,
        "status_with_context_match_gate": bound_status,
    }
    assert result["execution_contexts_match"] is False
    assert current_status == "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE"
    assert bound_status == "UNKNOWN_UNMATCHED_CONTROL"
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
