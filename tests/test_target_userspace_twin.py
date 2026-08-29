import copy
import json
import unittest

from frankenstein2.target_host_profile import collect_target_host_profile
from frankenstein2.target_userspace_twin import (
    FIDELITY,
    ONE_HANDOFF_ENTRY,
    PLAN_SCHEMA,
    PROFILE_SCHEMA,
    PROJECTION_SCHEMA,
    UNKNOWN,
    TargetUserspaceTwinError,
    build_t1_userspace_plan,
    plan_from_json,
)


def _command_runner(argv, *, overrides=None):
    values = {
        ("uname", "-r"): "6.8.0-target",
        ("uname", "-m"): "x86_64",
        ("systemctl", "--user", "is-system-running"): "running",
        ("pipewire", "--version"): "pipewire 1.0",
        ("wireplumber", "--version"): "wireplumber 0.5",
    }
    if overrides:
        values.update(overrides)
    key = tuple(argv)
    if key in values:
        return True, values[key], ""
    return False, "", "TEST_NOT_OBSERVED"


def _file_reader(path, *, os_release="Ubuntu 24.04.3 LTS"):
    if path == "/etc/os-release":
        return True, os_release, ""
    return False, "", "TEST_NOT_OBSERVED"


def _profile(*, fields=None):
    fields = {} if fields is None else dict(fields)
    command_overrides = {}
    command_bindings = {
        "kernel_release": ("uname", "-r"),
        "architecture": ("uname", "-m"),
        "systemd_user": ("systemctl", "--user", "is-system-running"),
        "pipewire_version": ("pipewire", "--version"),
        "wireplumber_version": ("wireplumber", "--version"),
    }
    for field, argv in command_bindings.items():
        if field in fields:
            command_overrides[argv] = fields[field]
    return collect_target_host_profile(
        generation=7,
        command_runner=lambda argv: _command_runner(
            argv, overrides=command_overrides
        ),
        file_reader=lambda path: _file_reader(
            path, os_release=fields.get("os_release", "Ubuntu 24.04.3 LTS")
        ),
        environ={
            "XDG_SESSION_TYPE": fields.get("session_type", "wayland"),
            "XDG_CURRENT_DESKTOP": "GNOME",
        },
        collector_uid=int(fields.get("uid", 1000)),
    )


class TargetUserspaceTwinTests(unittest.TestCase):
    def test_canonical_wp1201_object_produces_digest_bound_t1_projection(self):
        profile = _profile()
        plan = build_t1_userspace_plan(profile)
        observed = dict(plan.observed_shape)
        bindings = dict(plan.source_fact_bindings)

        self.assertEqual(plan.schema, PLAN_SCHEMA)
        self.assertEqual(plan.fidelity, FIDELITY)
        self.assertEqual(plan.projection_schema, PROJECTION_SCHEMA)
        self.assertEqual(plan.source_profile_generation, profile.generation)
        self.assertEqual(plan.source_profile_sha256, profile.profile_digest_sha256)
        self.assertEqual(observed["os_release"], "Ubuntu 24.04.3 LTS")
        self.assertEqual(observed["kernel_release"], "6.8.0-target")
        self.assertEqual(observed["architecture"], "x86_64")
        self.assertEqual(observed["uid"], "1000")
        self.assertEqual(observed["session_type"], "wayland")
        self.assertEqual(observed["systemd_user"], "running")
        self.assertEqual(observed["pipewire_version"], "pipewire 1.0")
        self.assertEqual(observed["wireplumber_version"], "wireplumber 0.5")
        self.assertEqual(bindings["uid"], "collector_uid")
        self.assertEqual(bindings["systemd_user"], "systemd_user_state")
        self.assertEqual(plan.one_handoff_installer_entry, ONE_HANDOFF_ENTRY)
        self.assertEqual(
            plan.classification,
            "T1_PREHANDOFF_PLAN_NO_PHYSICAL_OR_COMPLETION_CREDIT",
        )

    def test_real_wp1201_multiline_os_release_remains_consumable(self):
        realistic_os_release = (
            'PRETTY_NAME="Ubuntu 24.04.3 LTS"\n'
            'NAME="Ubuntu"\n'
            'VERSION_ID="24.04"'
        )
        profile = _profile(fields={"os_release": realistic_os_release})
        plan = build_t1_userspace_plan(profile)
        self.assertEqual(dict(plan.observed_shape)["os_release"], realistic_os_release)

    def test_uncollected_t1_facts_remain_unknown_instead_of_being_guessed(self):
        plan = build_t1_userspace_plan(_profile())
        observed = dict(plan.observed_shape)
        gap_fields = {gap.field for gap in plan.fidelity_gaps}

        for field in (
            "xdg_runtime_dir",
            "session_dbus",
            "portal_backend",
            "browser_package_form",
        ):
            self.assertEqual(observed[field], UNKNOWN)
            self.assertIn(field, gap_fields)
        self.assertEqual(
            dict(plan.source_fact_bindings)["portal_backend"],
            "NOT_COLLECTED_BY_CANONICAL_WP1201_G1",
        )

    def test_canonical_wp1201_as_dict_and_json_adapter_are_accepted(self):
        profile = _profile()
        object_plan = build_t1_userspace_plan(profile)
        mapping_plan = build_t1_userspace_plan(profile.as_dict())
        self.assertEqual(object_plan, mapping_plan)
        self.assertEqual(
            plan_from_json(profile.canonical_json()),
            json.dumps(
                object_plan.as_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n",
        )

    def test_old_parallel_profile_shape_is_rejected_even_with_valid_hex_digest(self):
        legacy = {
            "schema": PROFILE_SCHEMA,
            "profile_generation": 7,
            "profile_sha256": "a" * 64,
            "fields": {"os_release": "Ubuntu"},
        }
        with self.assertRaises(TargetUserspaceTwinError):
            build_t1_userspace_plan(legacy)

    def test_fact_mutation_with_stale_digest_fails_closed(self):
        raw = _profile().as_dict()
        raw["facts"]["session_type"]["value"] = "x11"
        with self.assertRaises(TargetUserspaceTwinError):
            build_t1_userspace_plan(raw)

    def test_two_different_fact_sets_cannot_share_one_attested_source_digest(self):
        first = _profile().as_dict()
        second = copy.deepcopy(first)
        second["facts"]["kernel_release"]["value"] = "6.9.0-forged"
        self.assertEqual(first["profile_digest_sha256"], second["profile_digest_sha256"])
        build_t1_userspace_plan(first)
        with self.assertRaises(TargetUserspaceTwinError):
            build_t1_userspace_plan(second)

    def test_derived_profile_metadata_is_revalidated(self):
        raw = _profile().as_dict()
        raw["observed_field_count"] += 1
        with self.assertRaises(TargetUserspaceTwinError):
            build_t1_userspace_plan(raw)

    def test_unrecognized_or_sensitive_fact_cannot_enter_projection(self):
        raw = _profile().as_dict()
        raw["facts"]["credential"] = {
            "status": "OBSERVED",
            "source": "forbidden",
            "value": "must-not-propagate",
        }
        with self.assertRaises(TargetUserspaceTwinError):
            build_t1_userspace_plan(raw)

    def test_plan_is_deterministic_across_canonical_mapping_order(self):
        raw = _profile().as_dict()
        reordered = dict(reversed(list(raw.items())))
        left = build_t1_userspace_plan(raw)
        right = build_t1_userspace_plan(reordered)
        self.assertEqual(left.as_dict(), right.as_dict())
        self.assertEqual(left.sha256(), right.sha256())

    def test_control_characters_in_observed_target_fields_fail_closed(self):
        profile = _profile(fields={"session_type": "wayland\nspoofed"})
        with self.assertRaises(TargetUserspaceTwinError):
            build_t1_userspace_plan(profile)

    def test_profile_json_must_be_an_object(self):
        with self.assertRaises(TargetUserspaceTwinError):
            plan_from_json("[]")


if __name__ == "__main__":
    unittest.main()
