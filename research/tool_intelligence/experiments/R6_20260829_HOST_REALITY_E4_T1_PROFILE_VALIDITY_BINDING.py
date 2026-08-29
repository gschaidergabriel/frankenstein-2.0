"""Trigger-6 E4 direct WP1201->WP1202 T1 validity-binding ablation.

This models the exact current dependency surface in target_userspace_twin.py:
_T1_FACT_BINDINGS consumes eight WP1201 facts while TargetProfileProjection also carries the
full WP1201 profile digest. The experiment asks whether unrelated WP1201 fact changes alter
T1 semantics and whether a separate semantic input-binding digest can preserve provenance
without forcing unrelated revalidation.

Evidence ceiling: deterministic repository-contract ablation only. Zero target/runtime credit.
"""
from __future__ import annotations

import copy
import hashlib
import json

PROFILE_SCHEMA = "FRANKENSTEIN2_TARGET_HOST_PROFILE/v1"
COLLECTOR_VERSION = "F2-WP-1201-G1"
BINDING_SCHEMA = "F2_T1_PROFILE_INPUT_BINDING_ABLATION/v1"

FIELDS = (
    "machine_model", "board_name", "bios_version", "bios_date", "os_release",
    "kernel_release", "architecture", "cpu_topology", "pci_inventory", "usb_inventory",
    "storage_inventory", "session_type", "desktop_name", "systemd_user_state",
    "pipewire_version", "wireplumber_version", "pipewire_topology", "camera_inventory",
    "firefox_version", "chromium_version", "chrome_version", "collector_uid",
    "xdg_runtime_dir_present", "xdg_runtime_dir_owned_by_collector_uid",
)

T1_BINDINGS = (
    ("os_release", "os_release"),
    ("kernel_release", "kernel_release"),
    ("architecture", "architecture"),
    ("uid", "collector_uid"),
    ("session_type", "session_type"),
    ("xdg_runtime_dir", None),
    ("session_dbus", None),
    ("systemd_user", "systemd_user_state"),
    ("pipewire_version", "pipewire_version"),
    ("wireplumber_version", "wireplumber_version"),
    ("portal_backend", None),
    ("browser_package_form", None),
)
T1_SOURCE_FACTS = frozenset(source for _, source in T1_BINDINGS if source is not None)


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def baseline() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for field in FIELDS:
        if field == "collector_uid":
            value: object = 1000
        elif field.startswith("xdg_runtime_dir_"):
            value = True
        else:
            value = f"BASE::{field}"
        result[field] = {"status": "OBSERVED", "source": f"synthetic:{field}", "value": value}
    return result


def profile_digest(facts: dict[str, dict[str, object]]) -> str:
    return digest({"schema": PROFILE_SCHEMA, "collector_version": COLLECTOR_VERSION, "generation": 1,
                   "facts": {key: facts[key] for key in sorted(facts)}})


def projection_fields(facts: dict[str, dict[str, object]]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for output, source in T1_BINDINGS:
        if source is None:
            fields[output] = "UNKNOWN"
            continue
        record = facts[source]
        if record["status"] == "UNKNOWN":
            fields[output] = "UNKNOWN"
        else:
            fields[output] = str(record["value"])
    return fields


def current_plan_identity(facts: dict[str, dict[str, object]]) -> str:
    # Current WP1202 plan identity includes source_profile_sha256 in its serialized plan.
    return digest({"source_profile_sha256": profile_digest(facts), "observed_shape": projection_fields(facts)})


def candidate_semantic_binding(facts: dict[str, dict[str, object]]) -> str:
    return digest({
        "binding_schema": BINDING_SCHEMA,
        "profile_schema": PROFILE_SCHEMA,
        "collector_version": COLLECTOR_VERSION,
        "source_fact_bindings": sorted(T1_SOURCE_FACTS),
        "facts": {key: facts[key] for key in sorted(T1_SOURCE_FACTS)},
    })


def mutate(facts: dict[str, dict[str, object]], field: str, kind: str) -> dict[str, dict[str, object]]:
    out = copy.deepcopy(facts)
    source = str(out[field]["source"])
    if kind == "TO_UNKNOWN":
        out[field] = {"status": "UNKNOWN", "source": source, "reason": "SYNTHETIC_UNKNOWN"}
        return out
    old = out[field]["value"]
    if isinstance(old, bool):
        new: object = not old
    elif isinstance(old, int):
        new = old + 1
    else:
        new = f"{old}::CHANGED"
    out[field] = {"status": "OBSERVED", "source": source, "value": new}
    return out


def run() -> dict[str, object]:
    base = baseline()
    base_profile = profile_digest(base)
    base_projection = projection_fields(base)
    base_plan = current_plan_identity(base)
    base_binding = candidate_semantic_binding(base)
    rows = []
    for field in FIELDS:
        for perturbation in ("VALUE_CHANGE", "TO_UNKNOWN"):
            changed = mutate(base, field, perturbation)
            rows.append({
                "field": field,
                "perturbation": perturbation,
                "t1_relevant": field in T1_SOURCE_FACTS,
                "profile_changed": profile_digest(changed) != base_profile,
                "projection_changed": projection_fields(changed) != base_projection,
                "current_plan_identity_changed": current_plan_identity(changed) != base_plan,
                "candidate_semantic_binding_changed": candidate_semantic_binding(changed) != base_binding,
            })
    relevant = [row for row in rows if row["t1_relevant"]]
    irrelevant = [row for row in rows if not row["t1_relevant"]]
    return {
        "schema": "FRANKENSTEIN2_TRIGGER6_E4_T1_BINDING_RESULT/v1",
        "t1_source_facts": sorted(T1_SOURCE_FACTS),
        "relevant_cases": len(relevant),
        "irrelevant_cases": len(irrelevant),
        "relevant_projection_changes": sum(row["projection_changed"] for row in relevant),
        "relevant_current_plan_identity_changes": sum(row["current_plan_identity_changed"] for row in relevant),
        "relevant_candidate_binding_changes": sum(row["candidate_semantic_binding_changed"] for row in relevant),
        "irrelevant_projection_changes": sum(row["projection_changed"] for row in irrelevant),
        "irrelevant_current_plan_identity_changes": sum(row["current_plan_identity_changed"] for row in irrelevant),
        "irrelevant_candidate_binding_changes": sum(row["candidate_semantic_binding_changed"] for row in irrelevant),
        "irrelevant_cases_where_full_profile_digest_alone_forces_current_plan_identity_change": sum(
            row["profile_changed"] and not row["projection_changed"] and row["current_plan_identity_changed"]
            for row in irrelevant
        ),
        "epistemic_limit": "This establishes an exact current contract coupling. It does not prove that the eight current T1 source facts are sufficient for real target fidelity.",
        "credits": {"runtime": 0, "physical_target": 0, "completion": 0, "whole_system": 0},
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
