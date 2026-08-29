import unittest

from frankenstein2.target_host_profile import collect_target_host_profile
from frankenstein2.target_userspace_readback import collect_t1_userspace_runtime_readback


def _profile_runner(argv):
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
        generation=11,
        command_runner=_profile_runner,
        file_reader=_file_reader,
        environ={"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME"},
        collector_uid=1000,
    )


def _runtime_runner(argv):
    values = {
        ("systemctl", "--user", "is-system-running"): "running",
        ("busctl", "--user", "--no-pager", "--no-legend", "list"): "org.freedesktop.DBus",
        (
            "systemctl",
            "--user",
            "show",
            "frankenstein2-bootstrap.service",
            "--property=LoadState",
            "--property=ActiveState",
            "--property=SubState",
            "--no-pager",
        ): "LoadState=loaded\nActiveState=inactive\nSubState=dead",
        (
            "systemctl",
            "--user",
            "show",
            "frankenstein2-bootstrap.service",
            "--property=Result",
            "--property=ExecMainCode",
            "--property=ExecMainStatus",
            "--property=ExecMainExitTimestampMonotonic",
            "--no-pager",
        ): (
            "Result=success\nExecMainCode=exited\nExecMainStatus=0\n"
            "ExecMainExitTimestampMonotonic=123456"
        ),
    }
    key = tuple(argv)
    if key in values:
        return True, values[key], ""
    return False, "", "UNEXPECTED_COMMAND"


class CompletedOneshotReadbackTests(unittest.TestCase):
    def test_successfully_executed_oneshot_is_accepted_without_broader_credit(self):
        receipt = collect_t1_userspace_runtime_readback(
            _profile(),
            service_unit="frankenstein2-bootstrap.service",
            command_runner=_runtime_runner,
            stat_reader=lambda path: (True, 1000, ""),
            environ={
                "XDG_RUNTIME_DIR": "/run/user/1000",
                "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
                "XDG_SESSION_TYPE": "wayland",
            },
        )

        checks = {check.check_id: check for check in receipt.checks}
        self.assertTrue(receipt.t1_runtime_readback_pass)
        self.assertEqual(checks["service_state"].status, "PASS")
        self.assertEqual(checks["service_state"].reason, "COMPLETED_ONESHOT_PROVEN")
        self.assertIn("ExecMainExitTimestampMonotonic=123456", checks["service_state"].observed)
        self.assertEqual(receipt.runtime_credit, 0)
        self.assertEqual(receipt.physical_target_credit, 0)
        self.assertEqual(receipt.effect_credit, 0)
        self.assertEqual(receipt.completion_credit, 0)
        self.assertEqual(receipt.whole_system_credit, 0)


if __name__ == "__main__":
    unittest.main()
