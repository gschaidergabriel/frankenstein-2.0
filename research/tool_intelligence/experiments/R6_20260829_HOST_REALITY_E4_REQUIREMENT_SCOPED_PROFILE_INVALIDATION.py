"""Trigger-6 E4 deterministic contract ablation for F2-WP-1201.

Evidence ceiling: repository-contract experiment only. This does not execute on the target
host and grants zero runtime, physical-host, installation, completion, or whole-system credit.

The current WP1201 generation-1 contract hashes every allowed fact into one profile digest.
This experiment compares that invalidation behavior with a candidate requirement-scoped
binding digest over explicit field dependency sets. Dependency sets are hypotheses and MUST
be validated by downstream workload tests before architecture acceptance.
"""
from __future__ import annotations

import copy
import hashlib
import json

SCHEMA = "FRANKENSTEIN2_TARGET_HOST_PROFILE/v1"
COLLECTOR_VERSION = "F2-WP-1201-G1"
BINDING_SCHEMA = "F2_REQUIREMENT_BINDING_ABLATION/v1"

FIELDS = (
    "machine_model", "board_name", "bios_version", "bios_date", "os_release",
    "kernel_release", "architecture", "cpu_topology", "pci_inventory", "usb_inventory",
    "storage_inventory", "session_type", "desktop_name", "systemd_user_state",
    "pipewire_version", "wireplumber_version", "pipewire_topology", "camera_inventory",
    "firefox_version", "chromium_version", "chrome_version", "collector_uid",
    "xdg_runtime_dir_present", "xdg_runtime_dir_owned_by_collector_uid",
)

REQUIREMENTS = {
    "AUDIO_RUNTIME": {
        "pipewire_version", "wireplumber_version", "pipewire_topology", "session_type",
        "desktop_name", "systemd_user_state", "collector_uid", "xdg_runtime_dir_present",
        "xdg_runtime_dir_owned_by_collector_uid",
    },
    "BROWSER_FIREFOX_RUNTIME": {
        "firefox_version", "session_type", "desktop_name", "systemd_user_state",
        "collector_uid", "xdg_runtime_dir_present", "xdg_runtime_dir_owned_by_collector_uid",
    },
    "USB_ENUMERATION": {"usb_inventory"},
    "KERNEL_ABI": {"kernel_release", "architecture"},
    "PLATFORM_COMPAT": {
        "machine_model", "board_name", "bios_version", "bios_date", "os_release",
        "kernel_release", "architecture", "cpu_topology", "pci_inventory", "storage_inventory",
    },
    "CAMERA_RUNTIME": {
        "camera_inventory", "pipewire_version", "wireplumber_version", "pipewire_topology",
        "session_type", "desktop_name", "collector_uid", "xdg_runtime_dir_present",
        "xdg_runtime_dir_owned_by_collector_uid",
    },
}


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def baseline_facts() -> dict[str, dict[str, object]]:
    facts: dict[str, dict[str, object]] = {}
    for field in FIELDS:
        if field == "collector_uid":
            value: object = 1000
        elif field.startswith("xdg_runtime_dir_"):
            value = True
        else:
            value = f"BASE::{field}"
        facts[field] = {"status": "OBSERVED", "source": f"synthetic:{field}", "value": value}
    return facts


def monolithic_profile_digest(facts: dict[str, dict[str, object]]) -> str:
    return digest({
        "schema": SCHEMA,
        "collector_version": COLLECTOR_VERSION,
        "generation": 1,
        "facts": {key: facts[key] for key in sorted(facts)},
    })


def requirement_binding_digest(requirement: str, facts: dict[str, dict[str, object]]) -> str:
    required = REQUIREMENTS[requirement]
    return digest({
        "binding_schema": BINDING_SCHEMA,
        "target_profile_schema": SCHEMA,
        "collector_version": COLLECTOR_VERSION,
        "requirement_id": requirement,
        "facts": {key: facts[key] for key in sorted(required)},
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
    base = baseline_facts()
    base_monolithic = monolithic_profile_digest(base)
    base_scoped = {req: requirement_binding_digest(req, base) for req in REQUIREMENTS}
    rows: list[dict[str, object]] = []
    for field in FIELDS:
        for perturbation in ("VALUE_CHANGE", "TO_UNKNOWN"):
            changed = mutate(base, field, perturbation)
            mon_changed = monolithic_profile_digest(changed) != base_monolithic
            for requirement, required_fields in REQUIREMENTS.items():
                scoped_changed = requirement_binding_digest(requirement, changed) != base_scoped[requirement]
                rows.append({
                    "field": field,
                    "perturbation": perturbation,
                    "requirement": requirement,
                    "relevant": field in required_fields,
                    "monolithic_changed": mon_changed,
                    "scoped_changed": scoped_changed,
                })

    per_requirement = []
    for requirement, required_fields in REQUIREMENTS.items():
        selected = [row for row in rows if row["requirement"] == requirement]
        relevant = [row for row in selected if row["relevant"]]
        irrelevant = [row for row in selected if not row["relevant"]]
        per_requirement.append({
            "requirement": requirement,
            "required_fields": len(required_fields),
            "relevant_cases": len(relevant),
            "monolithic_false_preserve": sum(not row["monolithic_changed"] for row in relevant),
            "scoped_false_preserve": sum(not row["scoped_changed"] for row in relevant),
            "irrelevant_cases": len(irrelevant),
            "monolithic_irrelevant_invalidations": sum(row["monolithic_changed"] for row in irrelevant),
            "scoped_irrelevant_invalidations": sum(row["scoped_changed"] for row in irrelevant),
        })

    relevant_rows = [row for row in rows if row["relevant"]]
    irrelevant_rows = [row for row in rows if not row["relevant"]]
    return {
        "schema": "FRANKENSTEIN2_TRIGGER6_E4_ABLATION_RESULT/v1",
        "source_contract": "src/frankenstein2/target_host_profile.py blob f0b528956c5dab6cd58f93b1d3a6851c1adcb07a",
        "total_requirement_perturbation_pairs": len(rows),
        "relevant_pairs": len(relevant_rows),
        "irrelevant_pairs": len(irrelevant_rows),
        "monolithic_changed_pairs": sum(row["monolithic_changed"] for row in rows),
        "scoped_changed_pairs": sum(row["scoped_changed"] for row in rows),
        "monolithic_false_preserve_relevant": sum(not row["monolithic_changed"] for row in relevant_rows),
        "scoped_false_preserve_relevant": sum(not row["scoped_changed"] for row in relevant_rows),
        "monolithic_irrelevant_invalidations": sum(row["monolithic_changed"] for row in irrelevant_rows),
        "scoped_irrelevant_invalidations": sum(row["scoped_changed"] for row in irrelevant_rows),
        "per_requirement": per_requirement,
        "reboot_scope_probe": {
            "status": "UNREPRESENTABLE_IN_WP1201_G1_FACT_SCHEMA",
            "reason": "No boot-scope identity/fact exists; a reboot with otherwise identical collected facts produces no schema-level discriminator.",
        },
        "epistemic_limit": "Dependency sets are declared hypotheses. Zero false-preserve here proves only the deterministic digest mechanics under those declared sets, not semantic completeness of each set.",
        "credits": {"runtime": 0, "physical_host": 0, "completion": 0, "whole_system": 0},
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
