#!/usr/bin/env python3
"""Trigger-6 E3 source-equivalent falsifier for PlanOut-derived WP507 assignment ideas.

This is research-fixture evidence only. It does not execute Frankenstein 2.0,
GRID10, GWT, providers, tools, effects, or target runtime.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter


def canonical_digest(obj):
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# Source-equivalent subset of facebookarchive/planout at
# eee764781054abb39f003133b00b88a73c8f8982.
def planout_hash(experiment_salt, salt, unit, appended_unit=None):
    units = unit if isinstance(unit, list) else [unit]
    units = list(units)
    if appended_unit is not None:
        units.append(appended_unit)
    hash_str = f"{experiment_salt}.{salt}." + ".".join(map(str, units))
    return int(hashlib.sha1(hash_str.encode("ascii")).hexdigest()[:15], 16)


def planout_random_int(experiment_salt, salt, unit, min_val, max_val):
    return min_val + planout_hash(experiment_salt, salt, unit) % (max_val - min_val + 1)


def planout_sample(experiment_salt, salt, unit, choices, draws):
    choices = list(choices)
    for i in range(len(choices) - 1, 0, -1):
        j = planout_hash(experiment_salt, salt, unit, appended_unit=i) % (i + 1)
        choices[i], choices[j] = choices[j], choices[i]
    return choices[:draws]


def planout_namespace_plan(namespace, num_segments, operations):
    available = set(range(num_segments))
    allocations = {}
    for operation in operations:
        if operation[0] == "add":
            _, name, count = operation
            sampled = planout_sample(
                namespace, "sampled_segments", name, list(available), count
            )
            for segment in sampled:
                allocations[segment] = name
                available.remove(segment)
        elif operation[0] == "remove":
            _, name = operation
            to_free = [s for s, n in allocations.items() if n == name]
            for segment in to_free:
                del allocations[segment]
                available.add(segment)
        else:
            raise ValueError(operation)
    return allocations


def planout_unit_experiment(namespace, num_segments, allocations, unit):
    segment = planout_random_int(namespace, "segment", unit, 0, num_segments - 1)
    return allocations.get(segment)


# Revised F2-native candidate: hash only schedules order of an explicitly declared
# intervention/control pair. It does NOT randomly choose which arms exist.
def f2_matched_pair_order(
    *,
    schema_version,
    probe_id,
    matched_pair_id,
    recipient_identity,
    assignment_domain_version,
    intervention_class,
    control_class,
    canonical_non_broadcast_input_digest,
):
    identity = {
        "assignment_schema_version": schema_version,
        "probe_id": probe_id,
        "matched_pair_id": matched_pair_id,
        "recipient_identity": recipient_identity,
        "assignment_domain_version": assignment_domain_version,
        "intervention_class": intervention_class,
        "control_class": control_class,
        "canonical_non_broadcast_input_digest": canonical_non_broadcast_input_digest,
    }
    input_digest = canonical_digest(identity)
    assignment_digest = hashlib.sha256(
        ("F2/WP507/MATCHED_PAIR_ORDER/v1\0" + input_digest).encode("utf-8")
    ).hexdigest()
    order_bit = int(assignment_digest[:16], 16) % 2
    run_order = (
        [intervention_class, control_class]
        if order_bit == 0
        else [control_class, intervention_class]
    )
    return {
        "assignment_id": f"mpo:{assignment_digest[:24]}",
        "assignment_digest": assignment_digest,
        "input_identity_digest": input_digest,
        "order_bit": order_bit,
        "run_order": run_order,
    }


# Deliberately naive alternative retained as a falsifier: hashing into N treatment
# classes does not guarantee every small matched set contains every arm.
def naive_hash_select_treatment(pair_id, treatments):
    treatments = tuple(sorted(set(treatments)))
    digest = hashlib.sha256(
        ("F2/WP507/NAIVE_TREATMENT_SELECT/v1\0" + pair_id).encode("utf-8")
    ).hexdigest()
    return treatments[int(digest[:16], 16) % len(treatments)]


def symmetric_difference_size(a, b, label):
    aa = {s for s, n in a.items() if n == label}
    bb = {s for s, n in b.items() if n == label}
    return len(aa ^ bb)


def main():
    # 1. Pinned PlanOut salt/unit determinism.
    replay_values = [
        planout_random_int("ns", "x", 42, 0, 100000) for _ in range(1000)
    ]
    planout_replay_stable = len(set(replay_values)) == 1

    salt_x = planout_random_int("assign_salt_a", "x", 20, 0, 100000)
    salt_y = planout_random_int("assign_salt_a", "y", 20, 0, 100000)
    planout_salt_separation_observed = salt_x != salt_y

    # 2. Reproduce SimpleNamespace history/order drift for one bounded fixture.
    base_ops = [("add", "A", 20), ("add", "B", 20), ("add", "C", 20)]
    inserted_ops = [
        ("add", "X", 10),
        ("add", "A", 20),
        ("add", "B", 20),
        ("add", "C", 20),
    ]
    reordered_ops = [("add", "B", 20), ("add", "A", 20), ("add", "C", 20)]

    base = planout_namespace_plan("wp507", 100, base_ops)
    inserted = planout_namespace_plan("wp507", 100, inserted_ops)
    reordered = planout_namespace_plan("wp507", 100, reordered_ops)

    base_units = [
        planout_unit_experiment("wp507", 100, base, unit) for unit in range(10000)
    ]
    inserted_units = [
        planout_unit_experiment("wp507", 100, inserted, unit)
        for unit in range(10000)
    ]
    reordered_units = [
        planout_unit_experiment("wp507", 100, reordered, unit)
        for unit in range(10000)
    ]

    inserted_drift = sum(
        a != b for a, b in zip(base_units, inserted_units)
    ) / len(base_units)
    reordered_drift = sum(
        a != b for a, b in zip(base_units, reordered_units)
    ) / len(base_units)

    segment_drift = {
        label: {
            "base_vs_inserted_symmetric_difference": symmetric_difference_size(
                base, inserted, label
            ),
            "base_vs_reordered_symmetric_difference": symmetric_difference_size(
                base, reordered, label
            ),
        }
        for label in ("A", "B", "C")
    }

    # 3. Revised F2-native pair-order proposal.
    pair_args = {
        "schema_version": "v1",
        "probe_id": "probe-17",
        "matched_pair_id": "pair-0042",
        "recipient_identity": "cell-7",
        "assignment_domain_version": "domain-v1",
        "intervention_class": "REAL_BROADCAST",
        "control_class": "WITHHELD_BROADCAST",
        "canonical_non_broadcast_input_digest": "nb:" + ("a" * 64),
    }
    f2_base = f2_matched_pair_order(**pair_args)
    f2_replays = [f2_matched_pair_order(**pair_args) for _ in range(1000)]
    f2_replay_stable = all(item == f2_base for item in f2_replays)
    both_arms_guaranteed = set(f2_base["run_order"]) == {
        pair_args["intervention_class"],
        pair_args["control_class"],
    } and len(f2_base["run_order"]) == 2

    v2_args = dict(pair_args)
    v2_args["assignment_domain_version"] = "domain-v2"
    f2_v2 = f2_matched_pair_order(**v2_args)
    explicit_version_change_changes_identity = (
        f2_v2["assignment_id"] != f2_base["assignment_id"]
    )

    historical_reentry = f2_matched_pair_order(**pair_args)
    historical_v1_reentry_stable = historical_reentry == f2_base

    # 4. Falsify naive four-way class selection as a guaranteed small-pair design.
    treatments = (
        "REAL_BROADCAST",
        "WITHHELD_BROADCAST",
        "SHUFFLED_RECIPIENT_BROADCAST",
        "SEMANTIC_PLACEBO_BROADCAST",
    )
    naive_first4 = Counter(
        naive_hash_select_treatment(f"pair-{i:04d}", treatments) for i in range(4)
    )
    naive_first4_has_all_arms = set(naive_first4) == set(treatments)

    # 5. The pair-order hash only counterbalances order. It must not be treated as
    # evidence of delivery, uptake or causal influence.
    order_counts = Counter()
    for i in range(1000):
        args = dict(pair_args)
        args["matched_pair_id"] = f"pair-{i:04d}"
        receipt = f2_matched_pair_order(**args)
        order_counts[str(receipt["order_bit"])] += 1

    assertions = {
        "planout_replay_stable": planout_replay_stable,
        "planout_salt_separation_observed": planout_salt_separation_observed,
        "planout_history_insertion_drift_observed": inserted_drift > 0,
        "planout_setup_reorder_drift_observed": reordered_drift > 0,
        "f2_pair_order_replay_stable": f2_replay_stable,
        "f2_both_declared_arms_guaranteed": both_arms_guaranteed,
        "f2_explicit_version_change_changes_identity": explicit_version_change_changes_identity,
        "f2_historical_v1_reentry_stable": historical_v1_reentry_stable,
        "naive_four_way_hash_selection_does_not_guarantee_all_arms_at_n4": not naive_first4_has_all_arms,
    }
    passed = all(assertions.values())

    result = {
        "schema": "FRANKENSTEIN2_TRIGGER6_PLANOUT_ASSIGNMENT_E3_FIXTURE_RESULT/v1",
        "source_equivalence_scope": {
            "upstream_repo": "facebookarchive/planout",
            "upstream_commit": "eee764781054abb39f003133b00b88a73c8f8982",
            "covered_mechanisms": [
                "SHA1 truncated salt/unit deterministic randomization",
                "Sample-style namespace segment allocation",
                "primary-unit-to-segment deterministic mapping",
            ],
            "not_claimed": [
                "full PlanOut runtime equivalence",
                "Frankenstein 2.0 runtime execution",
                "GWT causal influence",
            ],
        },
        "fixture": {
            "namespace_segments": 100,
            "base_operations": base_ops,
            "inserted_operations": inserted_ops,
            "reordered_operations": reordered_ops,
            "unit_probe_count": 10000,
            "replay_count": 1000,
        },
        "measurements": {
            "planout_replay_example_value": replay_values[0],
            "planout_base_vs_inserted_unit_assignment_changed_fraction": inserted_drift,
            "planout_base_vs_reordered_unit_assignment_changed_fraction": reordered_drift,
            "planout_segment_symmetric_difference": segment_drift,
            "f2_pair_order_example": f2_base,
            "f2_domain_v2_example": f2_v2,
            "naive_first4_treatment_counts": dict(sorted(naive_first4.items())),
            "f2_pair_order_bit_counts_over_1000_pair_ids": dict(sorted(order_counts.items())),
        },
        "assertions": assertions,
        "passed": passed,
        "adjudication": {
            "planout_namespace_state_model": "REPRODUCED_HISTORY_AND_ORDER_DRIFT_IN_BOUNDED_FIXTURE",
            "planout_runtime_dependency": "REJECT_FOR_WP507_GATE",
            "naive_hash_to_treatment_class": "REJECT_AS_MATCHED_PAIR_PRIMITIVE",
            "revised_distillation": "DETERMINISTIC_VERSIONED_RUN_ORDER_FOR_EXPLICIT_INTERVENTION_CONTROL_PAIR",
            "epistemic_fence": "ASSIGNMENT_OR_ORDER != OFFERED != DELIVERED != UPTAKEN != CAUSAL_INFLUENCE",
            "counterhypothesis_status": "DIRECT_EXPLICIT_FIXED_ORDER_REMAINS_VIABLE_AND_SIMPLER; HASH_ORDER_ONLY_ADDS_REPRODUCIBLE_ORDER_COUNTERBALANCING",
        },
        "credits": {
            "research_stage": "E3_CLAIM_REPRODUCED",
            "f2_runtime_credit": 0,
            "gwt_runtime_credit": 0,
            "jspace_runtime_credit": 0,
            "integration_credit": 0,
            "whole_system_credit": 0,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
