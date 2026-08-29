#!/usr/bin/env python3
"""Trigger-6 E3 source-equivalent falsifier for the current WP507 donor ABI.

This fixture does NOT execute Frankenstein runtime code. It reproduces only the
observable CausalProbeArm/evaluate_causal_influence condition/binding rules from
exact donor blob 381493eb916cd734341c1c64caf520085bde4ef1 and asks whether the
three DoWhy-derived negative-control classes can be represented without changing
that ABI.
"""
from __future__ import annotations

import hashlib
import json

DONOR_BLOB_SHA1 = "381493eb916cd734341c1c64caf520085bde4ef1"
DONOR_HEAD = "1c2037e97c9c6cf2c909764e142538028abc6e52"
ALLOWED_CONDITIONS = ("INTERVENTION_BROADCAST", "CONTROL_NO_BROADCAST")


def can_represent(*, class_name: str, carries_broadcast: bool, role: str) -> tuple[bool, str]:
    if role == "INTERVENTION":
        if not carries_broadcast:
            return False, "INTERVENTION_BROADCAST requires exact broadcast binding"
        return True, "Representable by CausalProbeArm.intervention"
    if role != "CONTROL":
        raise ValueError(role)
    if carries_broadcast:
        return False, "CONTROL_NO_BROADCAST rejects any broadcast_id/broadcast_sha256 binding"
    return True, "Representable by CausalProbeArm.control"


def main() -> None:
    classes = [
        ("REAL_BROADCAST", True, "INTERVENTION"),
        ("WITHHELD_BROADCAST", False, "CONTROL"),
        ("SHUFFLED_RECIPIENT_BROADCAST", True, "CONTROL"),
        ("SEMANTIC_PLACEBO_BROADCAST", True, "CONTROL"),
    ]
    matrix = {}
    for name, carries_broadcast, role in classes:
        ok, reason = can_represent(class_name=name, carries_broadcast=carries_broadcast, role=role)
        matrix[name] = {
            "role": role,
            "carries_broadcast": carries_broadcast,
            "representable_in_current_donor_abi": ok,
            "reason": reason,
        }

    assert matrix["REAL_BROADCAST"]["representable_in_current_donor_abi"] is True
    assert matrix["WITHHELD_BROADCAST"]["representable_in_current_donor_abi"] is True
    assert matrix["SHUFFLED_RECIPIENT_BROADCAST"]["representable_in_current_donor_abi"] is False
    assert matrix["SEMANTIC_PLACEBO_BROADCAST"]["representable_in_current_donor_abi"] is False

    result = {
        "schema": "FRANKENSTEIN2_TRIGGER6_WP507_DOWHY_NATIVE_PLACEBO_E3_FIXTURE_RESULT/v1",
        "source_scope": "SOURCE_EQUIVALENT_ABI_FIXTURE_ONLY",
        "donor_head": DONOR_HEAD,
        "donor_gwt_uptake_blob_sha1": DONOR_BLOB_SHA1,
        "observed_allowed_conditions": list(ALLOWED_CONDITIONS),
        "control_matrix": matrix,
        "measurements": {
            "declared_control_classes": 3,
            "representable_declared_controls": 1,
            "unrepresentable_declared_controls": 2,
            "coverage_fraction": 1 / 3,
            "all_assertions_passed": True,
        },
        "adjudication": {
            "withheld_broadcast": "REPRODUCIBLE_IN_CURRENT_DONOR_ABI",
            "shuffled_recipient_broadcast": "NOT_REPRESENTABLE_AS_CONTROL_IN_CURRENT_DONOR_ABI",
            "semantic_placebo_broadcast": "NOT_REPRESENTABLE_AS_CONTROL_IN_CURRENT_DONOR_ABI",
            "e2_three_control_native_fixture": "FALSIFIED_AS_DIRECT_CURRENT_ABI_IMPLEMENTATION",
            "dowhy_runtime_dependency": "NOT_JUSTIFIED_BY_THIS_RESULT",
            "minimal_next_design_question": "Whether a separate typed broadcast-bearing negative-control probe can add exact placebo/shuffle identity without weakening existing intervention/control lineage fences.",
        },
        "credits": {
            "runtime_credit": 0,
            "gwt_runtime_credit": 0,
            "jspace_runtime_credit": 0,
            "effect_credit": 0,
            "whole_system_credit": 0,
        },
    }
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    result["canonical_result_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
