import copy
import unittest

from frankenstein2.target_host_profile import collect_target_host_profile
from frankenstein2.target_userspace_readback import (
    READBACK_CLASSIFICATION,
    READBACK_SCHEMA,
    TargetUserspaceReadbackError,
    collect_t1_userspace_runtime_readback,
)


def _profile_command_runner(argv):
    values = {
        ("uname", "-r"): "6.8.0-target",
        ("uname", "-m"): "x86_64",
        ("systemctl", "--user", "is-system-running"): "running",
        ("pipewire", "--version"): "pipewire 1.0",
        ("wireplumber", "--version"): "wireplumber 0.5",
    }
    key = tuple(argv)
    if key in values:
        return True, values[key], ""
    return False, "", "TEST_NOT_OBSERVED"


def _file_reader(path):
    if path == "/etc/os-release":
        return True, 'PRETTY_NAME="Ubuntu 24.04.3 LTS"', ""
    return False, "", "TEST_NOT_OBSERVED"


def _profile():
    return collect_target_host_profile(
        generation=7,
        command_runner=_profile_command_runner,
        file_reader=_file_reader,
        environ={
            "XDG_SESSION_TYPE": "wayland",
            "XDG_CURRENT_DESKTOP": "GNOME",
        },
        collector_uid=1000,
    )


def _runtime_runner(argv, *, service_state=None, calls=None):
    if calls is not None:
        calls.append(tuple(argv))
    values = {
        ("systemctl", "--user", "is-system-running"): "running",
        ("busctl", "--user", "--no-pager", "--no-legend", "list"): "org.freedesktop.DBus",
        (
            "systemctl",
            "--user",
            "show",
            "frankenstein2.service",
            "--property=LoadState",
            "--property=ActiveState",
            "--property=SubState",
            "--no-pager",
        ): service_state
        or "LoadState=loaded\nActiveState=active\nSubState=running",
    }
    key = tuple(argv)
    if key in values:
        return True, values[key], ""
    return False, "", "UNEXPECTED_COMMAND"


def _env(**overrides):
    values = {
        "XDG_RUNTIME_DIR": "/run/user/1000",
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
        "XDG_SESSION_TYPE": "wayland",
    }
    values.update(overrides)
    return values


def _stat_reader(path):
    if path == "/run/user/1000":
        return True, 1000, ""
    return False, None, "PATH_NOT_FOUND"


class TargetUserspaceReadbackTests(unittest.TestCase):
    def test_happy_path_binds_profile_plan_and_readbacks_without_broader_credit(self):
        receipt = collect_t1_userspace_runtime_readback(
            _profile(),
            service_unit="frankenstein2.service",
            command_runner=_runtime_runner,
            stat_reader=_stat_reader,
            environ=_env(),
        )

        self.assertEqual(receipt.schema, READBACK_SCHEMA)
        self.assertEqual(receipt.classification, READBACK_CLASSIFICATION)
        self.assertEqual(receipt.source_profile_generation, 7)
        self.assertEqual(receipt.source_profile_sha256, _profile().profile_digest_sha256)
        self.assertEqual(len(receipt.source_plan_sha256), 64)
        self.assertTrue(receipt.t1_runtime_readback_pass)
        self.assertNotIn("xdg_runtime_dir", receipt.remaining_fidelity_gaps)
        self.assertNotIn("session_dbus", receipt.remaining_fidelity_gaps)
        self.assertEqual(receipt.runtime_credit, 0)
        self.assertEqual(receipt.physical_target_credit, 0)
        self.assertEqual(receipt.effect_credit, 0)
        self.assertEqual(receipt.completion_credit, 0)
        self.assertEqual(receipt.whole_system_credit, 0)
        self.assertEqual(len(receipt.sha256()), 64)

    def test_dbus_address_must_bind_to_observed_xdg_runtime_bus_shape(self):
        receipt = collect_t1_userspace_runtime_readback(
            _profile(),
            service_unit="frankenstein2.service",
            command_runner=_runtime_runner,
            stat_reader=_stat_reader,
            environ=_env(DBUS_SESSION_BUS_ADDRESS="unix:path=/tmp/other-bus"),
        )

        checks = {check.check_id: check for check in receipt.checks}
        self.assertEqual(checks["session_dbus_address"].status, "FAIL")
        self.assertFalse(receipt.t1_runtime_readback_pass)
        self.assertIn("xdg_runtime_dir", receipt.remaining_fidelity_gaps)
        self.assertIn("session_dbus", receipt.remaining_fidelity_gaps)

    def test_xdg_runtime_owner_mismatch_fails_closed(self):
        receipt = collect_t1_userspace_runtime_readback(
            _profile(),
            service_unit="frankenstein2.service",
            command_runner=_runtime_runner,
            stat_reader=lambda path: (True, 2000, ""),
            environ=_env(),
        )

        checks = {check.check_id: check for check in receipt.checks}
        self.assertEqual(checks["xdg_runtime_dir_owner"].status, "FAIL")
        self.assertFalse(receipt.t1_runtime_readback_pass)

    def test_session_type_must_match_digest_bound_wp1201_observation(self):
        receipt = collect_t1_userspace_runtime_readback(
            _profile(),
            service_unit="frankenstein2.service",
            command_runner=_runtime_runner,
            stat_reader=_stat_reader,
            environ=_env(XDG_SESSION_TYPE="x11"),
        )

        checks = {check.check_id: check for check in receipt.checks}
        self.assertEqual(checks["xdg_session_type"].status, "FAIL")
        self.assertEqual(checks["xdg_session_type"].expected, "wayland")
        self.assertFalse(receipt.t1_runtime_readback_pass)

    def test_inactive_service_fails_runtime_readback_without_effecting_it(self):
        receipt = collect_t1_userspace_runtime_readback(
            _profile(),
            service_unit="frankenstein2.service",
            command_runner=lambda argv: _runtime_runner(
                argv,
                service_state="LoadState=loaded\nActiveState=inactive\nSubState=dead",
            ),
            stat_reader=_stat_reader,
            environ=_env(),
        )

        checks = {check.check_id: check for check in receipt.checks}
        self.assertEqual(checks["service_state"].status, "FAIL")
        self.assertFalse(receipt.t1_runtime_readback_pass)
        self.assertEqual(receipt.effect_credit, 0)

    def test_tampered_canonical_profile_is_rejected_before_readback(self):
        raw = copy.deepcopy(_profile().as_dict())
        raw["facts"]["session_type"]["value"] = "x11"
        with self.assertRaises(Exception):
            collect_t1_userspace_runtime_readback(
                raw,
                service_unit="frankenstein2.service",
                command_runner=_runtime_runner,
                stat_reader=_stat_reader,
                environ=_env(),
            )

    def test_unsafe_service_unit_is_rejected(self):
        with self.assertRaises(TargetUserspaceReadbackError):
            collect_t1_userspace_runtime_readback(
                _profile(),
                service_unit="frankenstein2.service;systemctl --user stop x",
                command_runner=_runtime_runner,
                stat_reader=_stat_reader,
                environ=_env(),
            )

    def test_collector_emits_only_allowlisted_read_only_commands(self):
        calls = []
        receipt = collect_t1_userspace_runtime_readback(
            _profile(),
            service_unit="frankenstein2.service",
            command_runner=lambda argv: _runtime_runner(argv, calls=calls),
            stat_reader=_stat_reader,
            environ=_env(),
        )
        self.assertTrue(receipt.t1_runtime_readback_pass)
        self.assertEqual(
            calls,
            [
                ("systemctl", "--user", "is-system-running"),
                ("busctl", "--user", "--no-pager", "--no-legend", "list"),
                (
                    "systemctl",
                    "--user",
                    "show",
                    "frankenstein2.service",
                    "--property=LoadState",
                    "--property=ActiveState",
                    "--property=SubState",
                    "--no-pager",
                ),
            ],
        )
        forbidden = {"start", "stop", "restart", "enable", "disable", "daemon-reload"}
        self.assertFalse(any(forbidden.intersection(call) for call in calls))

    def test_one_handoff_entry_mismatch_is_rejected(self):
        with self.assertRaises(TargetUserspaceReadbackError):
            collect_t1_userspace_runtime_readback(
                _profile(),
                service_unit="frankenstein2.service",
                command_runner=_runtime_runner,
                stat_reader=_stat_reader,
                environ=_env(),
                handoff_entry="some-other-entry",
            )


if __name__ == "__main__":
    unittest.main()
