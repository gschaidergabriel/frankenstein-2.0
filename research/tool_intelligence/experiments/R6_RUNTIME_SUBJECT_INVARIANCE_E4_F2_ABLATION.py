#!/usr/bin/env python3
import json

BOUNDARIES = {
    "F2-WP-510@G3": {
        "status": "FROZEN_ACCEPTED_REPOSITORY_COMPONENT",
        "closure": {
            "src/frankenstein2/gwt_causal_path.py",
            "tests/test_gwt_causal_path.py",
            "tests/test_wp510_g3_not_computed_status.py",
            ".github/workflows/wp510-gwt-causal-path-ci.yml",
        },
    },
    "F2-WP-900@G1": {
        "status": "FROZEN_ACCEPTED_REPOSITORY_COMPONENT",
        "closure": {
            "src/frankenstein2/whole_persistent_loop.py",
            "tests/test_whole_persistent_loop.py",
            "tests/falsifier_wp900_unvalidated_gwt_seal.py",
            ".github/workflows/review-wp900-gwt-factory-seal-falsifier.yml",
        },
    },
    "F2-WP-206@G6": {"status": "ACTIVE_MOVING_BOUNDARY", "closure": set()},
    "F2-WP-901@G5": {"status": "ACTIVE_MOVING_BOUNDARY", "closure": set()},
}

CASES = [
    {
        "name": "wp510_real_g3_fusion_change",
        "boundary": "F2-WP-510@G3",
        "changes": {
            "src/frankenstein2/gwt_causal_path.py",
            "tests/test_wp510_g3_not_computed_status.py",
            ".github/workflows/wp510-gwt-causal-path-ci.yml",
        },
        "expected": "INVALIDATE_OR_DEFER",
    },
    {
        "name": "wp900_real_g1_fusion_change",
        "boundary": "F2-WP-900@G1",
        "changes": {
            "src/frankenstein2/whole_persistent_loop.py",
            ".github/workflows/review-wp900-gwt-factory-seal-falsifier.yml",
        },
        "expected": "INVALIDATE_OR_DEFER",
    },
    {
        "name": "research_only_successor_change_wp510",
        "boundary": "F2-WP-510@G3",
        "changes": {"research/tool_intelligence/claims/R6-20260830-RUNTIME-SUBJECT-INVARIANCE-GPT56SOL-01/E4_F2_ABLATION_FROZEN_BOUNDARY_FIXTURES.json"},
        "expected": "CERTIFY_NONINTERFERENCE",
    },
    {
        "name": "research_only_successor_change_wp900",
        "boundary": "F2-WP-900@G1",
        "changes": {"research/tool_intelligence/claims/R6-20260830-RUNTIME-SUBJECT-INVARIANCE-GPT56SOL-01/E4_F2_ABLATION_FROZEN_BOUNDARY_FIXTURES.json"},
        "expected": "CERTIFY_NONINTERFERENCE",
    },
    {
        "name": "active_wp206_boundary",
        "boundary": "F2-WP-206@G6",
        "changes": set(),
        "expected": "DEFER_ACTIVE_BOUNDARY",
    },
    {
        "name": "active_wp901_boundary",
        "boundary": "F2-WP-901@G5",
        "changes": set(),
        "expected": "DEFER_ACTIVE_BOUNDARY",
    },
]

def evaluate(case):
    boundary = BOUNDARIES[case["boundary"]]
    if boundary["status"] != "FROZEN_ACCEPTED_REPOSITORY_COMPONENT":
        return "DEFER_ACTIVE_BOUNDARY"
    return "INVALIDATE_OR_DEFER" if boundary["closure"] & case["changes"] else "CERTIFY_NONINTERFERENCE"

rows = []
for case in CASES:
    observed = evaluate(case)
    rows.append({
        "name": case["name"],
        "boundary": case["boundary"],
        "expected": case["expected"],
        "observed": observed,
        "pass": observed == case["expected"],
    })

print(json.dumps({
    "schema": "RUNTIME_SUBJECT_INVARIANCE_F2_ABLATION/v1",
    "rows": rows,
    "passed": sum(r["pass"] for r in rows),
    "total": len(rows),
    "acceptance": all(r["pass"] for r in rows),
}, sort_keys=True, indent=2))
