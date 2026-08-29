import json

import pytest

from frankenstein2.target_userspace_twin import (
    FIDELITY,
    ONE_HANDOFF_ENTRY,
    PLAN_SCHEMA,
    PROFILE_SCHEMA,
    UNKNOWN,
    TargetUserspaceTwinError,
    build_t1_userspace_plan,
    plan_from_json,
)


DIGEST = "a" * 64


def _profile(**overrides):
    fields = {
        "os_release": "Ubuntu 24.04.3 LTS",
        "kernel_release": "6.8.0-test",
        "architecture": "x86_64",
        "uid": "1000",
        "session_type": "wayland",
        "xdg_runtime_dir": "/run/user/1000",
        "session_dbus": "reachable",
        "systemd_user": "running",
        "pipewire_version": "1.0-observed",
        "wireplumber_version": "0.5-observed",
        "portal_backend": "xdg-desktop-portal-gnome",
        "browser_package_form": "snap",
    }
    fields.update(overrides.pop("fields", {}))
    return {
        "schema": PROFILE_SCHEMA,
        "profile_generation": overrides.pop("profile_generation", 7),
        "profile_sha256": overrides.pop("profile_sha256", DIGEST),
        "fields": fields,
        **overrides,
    }


def test_complete_observed_profile_produces_t1_plan_without_gaps():
    plan = build_t1_userspace_plan(_profile())

    assert plan.schema == PLAN_SCHEMA
    assert plan.fidelity == FIDELITY
    assert plan.source_profile_generation == 7
    assert plan.source_profile_sha256 == DIGEST
    assert plan.fidelity_gaps == ()
    assert dict(plan.observed_shape)["session_type"] == "wayland"
    assert plan.one_handoff_installer_entry == ONE_HANDOFF_ENTRY
    assert "one-handoff-installer-entry-is-used" in plan.required_runtime_checks
    assert plan.classification == "T1_PREHANDOFF_PLAN_NO_PHYSICAL_OR_COMPLETION_CREDIT"


def test_missing_target_facts_remain_unknown_and_are_not_guessed():
    profile = _profile(fields={"os_release": None, "kernel_release": None, "session_type": None})
    plan = build_t1_userspace_plan(profile)
    observed = dict(plan.observed_shape)
    gap_fields = {gap.field for gap in plan.fidelity_gaps}

    assert observed["os_release"] == UNKNOWN
    assert observed["kernel_release"] == UNKNOWN
    assert observed["session_type"] == UNKNOWN
    assert {"os_release", "kernel_release", "session_type"}.issubset(gap_fields)
    serialized = json.dumps(plan.as_dict(), sort_keys=True)
    assert "24.04" not in serialized
    assert "6.8.0-test" not in serialized
    assert "wayland" not in serialized


def test_unrecognized_or_sensitive_profile_fields_are_not_forwarded():
    profile = _profile()
    profile["fields"]["clipboard"] = "must-not-propagate"
    profile["fields"]["credential"] = "must-not-propagate"
    plan = build_t1_userspace_plan(profile)
    output = json.dumps(plan.as_dict(), sort_keys=True)

    assert "clipboard" not in output
    assert "must-not-propagate" not in output
    assert "credential" not in output


def test_plan_is_deterministic_across_mapping_order_and_json_adapter():
    left = _profile()
    right = {
        "fields": dict(reversed(list(left["fields"].items()))),
        "profile_sha256": left["profile_sha256"],
        "profile_generation": left["profile_generation"],
        "schema": left["schema"],
    }

    left_plan = build_t1_userspace_plan(left)
    right_plan = build_t1_userspace_plan(right)
    assert left_plan.as_dict() == right_plan.as_dict()
    assert left_plan.sha256() == right_plan.sha256()
    assert plan_from_json(json.dumps(left)) == plan_from_json(json.dumps(right))


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema": "WRONG"},
        {"profile_generation": -1},
        {"profile_generation": True},
        {"profile_sha256": "A" * 64},
        {"profile_sha256": "abc"},
    ],
)
def test_invalid_identity_or_schema_fails_closed(mutation):
    profile = _profile()
    profile.update(mutation)
    with pytest.raises(TargetUserspaceTwinError):
        build_t1_userspace_plan(profile)


def test_profile_json_must_be_an_object():
    with pytest.raises(TargetUserspaceTwinError):
        plan_from_json("[]")
