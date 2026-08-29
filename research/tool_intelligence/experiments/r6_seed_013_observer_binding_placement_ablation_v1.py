"""Trigger-6 E4 placement ablation for R6-SEED-013.

This is a deterministic source-schema experiment, not F2 target runtime.
It reproduces the exact serialized field boundary of current WP507
CellUptakeReceipt/UptakeSummary/CausalInfluenceResult and asks where a typed
ObserverBinding digest must be inserted to prevent observer-method identity
aliasing while preserving per-receipt attribution.
"""
from __future__ import annotations

import hashlib
import json

SOURCE_BLOB_SHA = "f25c03d4e4e49c4fed44acd0c5c96edfb40f664e"


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def serialized_bytes(value: object) -> int:
    return len(canonical_json(value).encode("utf-8"))


def receipt_payload(receipt_id: str = "r-G1", cell_id: str = "G1") -> dict[str, object]:
    return {
        "schema": "FRANKENSTEIN2_GWT_CELL_UPTAKE_RECEIPT/v2",
        "classification": "OBSERVED_UPTAKE_EVIDENCE_NOT_HIDDEN_STATE_OR_TRUTH_AUTHORITY",
        "receipt_id": receipt_id,
        "broadcast_id": "b1",
        "broadcast_sha256": "a" * 64,
        "cycle_id": "cycle-1",
        "broadcast_generation": 3,
        "selection_id": "sel-1",
        "selection_generation": 2,
        "selection_sha256": "b" * 64,
        "plan_id": "plan-1",
        "plan_generation": 4,
        "plan_sha256": "c" * 64,
        "cell_id": cell_id,
        "delivery_status": "DELIVERED",
        "uptake_status": "UPTAKEN",
        "downstream_ref": f"d:{cell_id}",
        "downstream_sha256": "d" * 64,
        "provenance_refs": [f"sensor:{cell_id}"],
    }


def summary_payload(
    receipts: list[dict[str, object]],
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "FRANKENSTEIN2_GWT_UPTAKE_SUMMARY/v2",
        "classification": "GWT_UPTAKE_MEASUREMENT_NOT_CAUSAL_PROOF_OR_RUNTIME_ACCEPTANCE",
        "summary_id": "s1",
        "broadcast_id": "b1",
        "broadcast_sha256": "a" * 64,
        "cycle_id": "cycle-1",
        "broadcast_generation": 3,
        "selection_id": "sel-1",
        "selection_generation": 2,
        "selection_sha256": "b" * 64,
        "plan_id": "plan-1",
        "plan_generation": 4,
        "plan_sha256": "c" * 64,
        "receipt_ids": sorted(str(item["receipt_id"]) for item in receipts),
        "delivered_cell_ids": sorted(str(item["cell_id"]) for item in receipts),
        "uptaken_cell_ids": sorted(str(item["cell_id"]) for item in receipts),
        "unknown_cell_ids": [],
        "status": "UPTAKE_OBSERVED",
        "provenance_refs": ["summary-src"],
        "source_receipt_sha256s": [digest(item) for item in receipts],
    }
    if extra:
        payload.update(extra)
    return payload


def arm_payload(condition: str, downstream_output_sha256: str) -> dict[str, object]:
    intervention = condition == "INTERVENTION_BROADCAST"
    return {
        "schema": "FRANKENSTEIN2_GWT_CAUSAL_PROBE_ARM/v2",
        "classification": "DECLARED_MATCHED_PROBE_ARM_NOT_WORLD_TRUTH",
        "arm_id": "i" if intervention else "c",
        "probe_id": "probe-1",
        "condition": condition,
        "nonbroadcast_input_sha256": "e" * 64,
        "downstream_output_sha256": downstream_output_sha256,
        "broadcast_id": "b1" if intervention else None,
        "broadcast_sha256": "a" * 64 if intervention else None,
        "provenance_refs": ["arm-src"],
    }


def result_payload(
    summary: dict[str, object],
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    intervention = arm_payload("INTERVENTION_BROADCAST", "f" * 64)
    control = arm_payload("CONTROL_NO_BROADCAST", "0" * 64)
    payload: dict[str, object] = {
        "schema": "FRANKENSTEIN2_GWT_CAUSAL_INFLUENCE_RESULT/v2",
        "classification": "MATCHED_CONTRACT_SCOPE_CAUSAL_EVIDENCE_NOT_HIDDEN_STATE_OR_WHOLE_SYSTEM_PROOF",
        "result_id": "res",
        "broadcast_id": "b1",
        "broadcast_sha256": "a" * 64,
        "uptake_summary_id": "s1",
        "uptake_summary_sha256": digest(summary),
        "intervention_arm_id": "i",
        "intervention_arm_sha256": digest(intervention),
        "control_arm_id": "c",
        "control_arm_sha256": digest(control),
        "status": "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE",
        "provenance_refs": ["result-src"],
        "runtime_credit": 0,
        "truth_authority": "NONE",
        "effect_authority": "NONE",
    }
    if extra:
        payload.update(extra)
    return payload


def main() -> None:
    observer_a = {
        "schema": "FRANKENSTEIN2_OBSERVER_BINDING/v1",
        "observer_type": "direct-inprocess-hook/v1",
        "observer_instance_id": "hook-17",
        "observer_artifact_sha256": "1" * 64,
        "observer_config_sha256": "2" * 64,
        "method_class": "synchronous_direct",
        "evidence_class": "DIRECT_INPROCESS",
    }
    observer_b = {
        "schema": "FRANKENSTEIN2_OBSERVER_BINDING/v1",
        "observer_type": "async-log-scraper/v1",
        "observer_instance_id": "scraper-9",
        "observer_artifact_sha256": "3" * 64,
        "observer_config_sha256": "4" * 64,
        "method_class": "asynchronous_derived",
        "evidence_class": "DERIVED_ASYNC",
    }
    observer_a_sha256 = digest(observer_a)
    observer_b_sha256 = digest(observer_b)

    base = receipt_payload()
    current_summary_a = summary_payload([base])
    current_summary_b = summary_payload([base])
    current_result_a = result_payload(current_summary_a)
    current_result_b = result_payload(current_summary_b)

    receipt_a = dict(base, observer_binding_sha256=observer_a_sha256)
    receipt_b = dict(base, observer_binding_sha256=observer_b_sha256)
    receipt_summary_a = summary_payload([receipt_a])
    receipt_summary_b = summary_payload([receipt_b])
    receipt_result_a = result_payload(receipt_summary_a)
    receipt_result_b = result_payload(receipt_summary_b)

    summary_only_a = summary_payload([base], {"observer_binding_sha256": observer_a_sha256})
    summary_only_b = summary_payload([base], {"observer_binding_sha256": observer_b_sha256})
    summary_result_a = result_payload(summary_only_a)
    summary_result_b = result_payload(summary_only_b)

    result_only_a = result_payload(current_summary_a, {"observer_binding_sha256": observer_a_sha256})
    result_only_b = result_payload(current_summary_b, {"observer_binding_sha256": observer_b_sha256})

    g1 = receipt_payload("r-G1", "G1")
    g2 = receipt_payload("r-G2", "G2")
    assignment_x = [
        dict(g1, observer_binding_sha256=observer_a_sha256),
        dict(g2, observer_binding_sha256=observer_b_sha256),
    ]
    assignment_y = [
        dict(g1, observer_binding_sha256=observer_b_sha256),
        dict(g2, observer_binding_sha256=observer_a_sha256),
    ]
    receipt_assignment_summary_x = summary_payload(assignment_x)
    receipt_assignment_summary_y = summary_payload(assignment_y)
    summary_set_x = summary_payload(
        [g1, g2],
        {"observer_binding_sha256s": sorted([observer_a_sha256, observer_b_sha256])},
    )
    summary_set_y = summary_payload(
        [g1, g2],
        {"observer_binding_sha256s": sorted([observer_a_sha256, observer_b_sha256])},
    )

    result = {
        "source_blob_sha": SOURCE_BLOB_SHA,
        "observer_binding_digests_distinct": observer_a_sha256 != observer_b_sha256,
        "single_receipt_placement": {
            "CURRENT_UNBOUND": {
                "receipt_collision": digest(base) == digest(base),
                "summary_collision": digest(current_summary_a) == digest(current_summary_b),
                "result_collision": digest(current_result_a) == digest(current_result_b),
            },
            "RECEIPT_LEVEL": {
                "receipt_collision": digest(receipt_a) == digest(receipt_b),
                "summary_collision": digest(receipt_summary_a) == digest(receipt_summary_b),
                "result_collision": digest(receipt_result_a) == digest(receipt_result_b),
                "added_receipt_bytes": serialized_bytes(receipt_a) - serialized_bytes(base),
            },
            "SUMMARY_ONLY": {
                "receipt_collision": True,
                "summary_collision": digest(summary_only_a) == digest(summary_only_b),
                "result_collision": digest(summary_result_a) == digest(summary_result_b),
                "added_summary_bytes": serialized_bytes(summary_only_a)
                - serialized_bytes(current_summary_a),
            },
            "RESULT_ONLY": {
                "receipt_collision": True,
                "summary_collision": True,
                "result_collision": digest(result_only_a) == digest(result_only_b),
                "added_result_bytes": serialized_bytes(result_only_a)
                - serialized_bytes(current_result_a),
            },
        },
        "multi_receipt_assignment_swap": {
            "scenario": "same two observer digests and same two cell receipts, but observer-to-cell assignment is swapped",
            "current_summary_collision": digest(summary_payload([g1, g2]))
            == digest(summary_payload([g1, g2])),
            "summary_only_unmapped_observer_set_collision": digest(summary_set_x)
            == digest(summary_set_y),
            "receipt_level_assignment_collision": digest(receipt_assignment_summary_x)
            == digest(receipt_assignment_summary_y),
            "assignment_x_summary_sha256": digest(receipt_assignment_summary_x),
            "assignment_y_summary_sha256": digest(receipt_assignment_summary_y),
        },
        "footprint": {
            "typed_observer_binding_example_bytes": serialized_bytes(observer_a),
            "leaf_reference_field_increment_bytes": serialized_bytes(receipt_a)
            - serialized_bytes(base),
        },
    }

    assert result["observer_binding_digests_distinct"] is True
    assert result["single_receipt_placement"]["CURRENT_UNBOUND"]["result_collision"] is True
    assert result["single_receipt_placement"]["RECEIPT_LEVEL"]["receipt_collision"] is False
    assert result["single_receipt_placement"]["RECEIPT_LEVEL"]["summary_collision"] is False
    assert result["single_receipt_placement"]["RECEIPT_LEVEL"]["result_collision"] is False
    assert result["single_receipt_placement"]["SUMMARY_ONLY"]["receipt_collision"] is True
    assert result["single_receipt_placement"]["RESULT_ONLY"]["summary_collision"] is True
    assert result["multi_receipt_assignment_swap"]["summary_only_unmapped_observer_set_collision"] is True
    assert result["multi_receipt_assignment_swap"]["receipt_level_assignment_collision"] is False

    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
