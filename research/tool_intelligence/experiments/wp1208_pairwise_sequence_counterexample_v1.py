#!/usr/bin/env python3
"""Deterministic Trigger-6 E3 counterexample for F2-WP-1208 coverage semantics.

Research-only fixture. It does not execute faults, mutate a host/twin, or grant
runtime / architecture / completion credit.
"""
from __future__ import annotations

from itertools import combinations, permutations
import json

FACTORS = (
    "MULTIMEDIA_SESSION",
    "PERMISSION",
    "LIFECYCLE",
    "NETWORK",
    "RESOURCE_PRESSURE",
)

ACTION_VARIANTS = {
    "MULTIMEDIA_SESSION": ("PIPEWIRE_RESTART", "DEVICE_REMOVE"),
    "PERMISSION": ("PERMISSION_DENY", "PERMISSION_REVOKE"),
    "LIFECYCLE": ("PROCESS_KILL", "REBOOT"),
    "NETWORK": ("NETWORK_LOSS", "NETWORK_RESET"),
    "RESOURCE_PRESSURE": ("LOW_SPACE", "PACKAGE_LOCK"),
}

# Every row contains exactly one action from every required WP1208 family.
# A/B/C/D are a deliberately broad but correlated baseline.
# E/F are additional valid family-complete candidates.
CANDIDATE_ROWS = {
    "A": (0, 0, 0, 0, 0),
    "B": (1, 1, 1, 1, 1),
    "C": (0, 0, 0, 0, 1),
    "D": (1, 1, 1, 1, 0),
    "E": (0, 0, 1, 1, 1),
    "F": (1, 1, 0, 0, 1),
}
BASELINE_CASES = ("A", "B", "C", "D")
CASE_BUDGET = len(BASELINE_CASES)

PAIRWISE_UNIVERSE = {
    (i, j, a, b)
    for i, j in combinations(range(len(FACTORS)), 2)
    for a in (0, 1)
    for b in (0, 1)
}

def pairwise_coverage(case_ids):
    covered = set()
    for case_id in case_ids:
        row = CANDIDATE_ROWS[case_id]
        for i, j in combinations(range(len(FACTORS)), 2):
            covered.add((i, j, row[i], row[j]))
    return covered

def best_equal_budget_selection():
    best = None
    best_coverage = set()
    for selection in combinations(sorted(CANDIDATE_ROWS), CASE_BUDGET):
        covered = pairwise_coverage(selection)
        key = (len(covered), tuple(selection))
        if best is None or key[0] > len(best_coverage) or (
            key[0] == len(best_coverage) and tuple(selection) < tuple(best)
        ):
            best = selection
            best_coverage = covered
    return best, best_coverage

# Sequence counterexample: family presence and concurrent membership do not say
# whether the causal order around authority invalidation/rebind has been tested.
SEQUENCE_EVENTS = (
    "INVALIDATE_G_TO_GPLUS1",
    "STALE_G_OPERATION",
    "REOBSERVE_AND_REBIND_GPLUS1",
    "VALID_GPLUS1_OPERATION",
)
FORWARD = SEQUENCE_EVENTS
REVERSE = tuple(reversed(SEQUENCE_EVENTS))
BASELINE_SEQUENCES = (FORWARD, FORWARD)
SEQUENCE_AWARE = (FORWARD, REVERSE)

ORDER_UNIVERSE = set(permutations(SEQUENCE_EVENTS, 2))

def order_coverage(sequence):
    position = {event: idx for idx, event in enumerate(sequence)}
    return {(a, b) for a, b in ORDER_UNIVERSE if position[a] < position[b]}

def multi_sequence_coverage(sequences):
    covered = set()
    for sequence in sequences:
        covered |= order_coverage(sequence)
    return covered

def action_rows(case_ids):
    return {
        case_id: {
            factor: ACTION_VARIANTS[factor][CANDIDATE_ROWS[case_id][idx]]
            for idx, factor in enumerate(FACTORS)
        }
        for case_id in case_ids
    }

def main():
    baseline_cov = pairwise_coverage(BASELINE_CASES)
    best_cases, best_cov = best_equal_budget_selection()
    baseline_seq_cov = multi_sequence_coverage(BASELINE_SEQUENCES)
    sequence_aware_cov = multi_sequence_coverage(SEQUENCE_AWARE)

    assert all(len(CANDIDATE_ROWS[c]) == len(FACTORS) for c in CANDIDATE_ROWS)
    assert len(baseline_cov) < len(PAIRWISE_UNIVERSE)
    assert len(best_cov) > len(baseline_cov)
    assert len(best_cases) == CASE_BUDGET
    assert len(baseline_seq_cov) < len(ORDER_UNIVERSE)
    assert len(sequence_aware_cov) == len(ORDER_UNIVERSE)

    result = {
        "schema": "FRANKENSTEIN2_TRIGGER6_WP1208_E3_COUNTEREXAMPLE/v1",
        "classification": "DETERMINISTIC_RESEARCH_FIXTURE_NO_RUNTIME_OR_ARCHITECTURE_CREDIT",
        "factors": list(FACTORS),
        "action_variants": {k: list(v) for k, v in ACTION_VARIANTS.items()},
        "candidate_rows": action_rows(sorted(CANDIDATE_ROWS)),
        "pairwise": {
            "case_budget": CASE_BUDGET,
            "universe": len(PAIRWISE_UNIVERSE),
            "baseline_cases": list(BASELINE_CASES),
            "baseline_covered": len(baseline_cov),
            "baseline_fraction": len(baseline_cov) / len(PAIRWISE_UNIVERSE),
            "best_equal_budget_cases": list(best_cases),
            "best_equal_budget_covered": len(best_cov),
            "best_equal_budget_fraction": len(best_cov) / len(PAIRWISE_UNIVERSE),
            "absolute_interactions_gained": len(best_cov) - len(baseline_cov),
            "relative_coverage_gain": (len(best_cov) - len(baseline_cov)) / len(baseline_cov),
            "baseline_missing": [
                {
                    "factor_a": FACTORS[i],
                    "factor_b": FACTORS[j],
                    "level_a": a,
                    "level_b": b,
                }
                for i, j, a, b in sorted(PAIRWISE_UNIVERSE - baseline_cov)
            ],
        },
        "sequence": {
            "events": list(SEQUENCE_EVENTS),
            "ordered_pair_universe": len(ORDER_UNIVERSE),
            "baseline_sequence_count": len(BASELINE_SEQUENCES),
            "baseline_unique_order_pairs": len(baseline_seq_cov),
            "baseline_fraction": len(baseline_seq_cov) / len(ORDER_UNIVERSE),
            "sequence_aware_count": len(SEQUENCE_AWARE),
            "sequence_aware_unique_order_pairs": len(sequence_aware_cov),
            "sequence_aware_fraction": len(sequence_aware_cov) / len(ORDER_UNIVERSE),
            "same_sequence_budget": len(BASELINE_SEQUENCES) == len(SEQUENCE_AWARE),
        },
        "claim_reproduced": (
            "Required-family presence plus concurrency/fence invariants do not imply "
            "pairwise action-level or order-sensitive coverage."
        ),
        "credit": {
            "research_e3": 1,
            "repository_ci": 0,
            "target_twin_runtime": 0,
            "physical_host": 0,
            "architecture_acceptance": 0,
            "completion": 0,
            "whole_system": 0,
        },
    }
    print(json.dumps(result, sort_keys=True, indent=2))

if __name__ == "__main__":
    main()
