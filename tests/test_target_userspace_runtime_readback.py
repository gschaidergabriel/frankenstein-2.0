import dataclasses
import unittest

from frankenstein2.target_host_profile import collect_target_host_profile
from frankenstein2.target_userspace_runtime_readback import (
    CommandResult,
    FAIL,
    HandoffEvidence,
    PASS,
    PathStatResult,
    TargetUserspaceRuntimeReadbackError,
    UNKNOWN,
    execute_t1_runtime_readbacks,
)


def _profile():
    command_values = {
        ("uname", "-r"): (True, "6.8.0-target", ""),
        ("uname", "-m"): (True, "x86_64", ""),
        ("systemctl", "--user", "is-system-running"): (True, "running", ""),
        ("pipewire", "--version"): (True, "pipewire 1.0", ""),
        ("wireplumber", "--version"): (True, "wireplumber 0.5", ""),
    }

    def command_runner(argv):
        return command_values.get(tuple(argv), (False, "", "TEST_NOT_OBSERVED"))

    def file_reader(path):
        if path == "/etc/os-release":
            return True, 'PRETTY_NAME="Ubuntu 24.04.3 LTS"\nNAME="Ubuntu"', ""
        return False, "", "TEST_NOT_OBSERVED"

    return collect_target_host_profile(
        generation=7,
        command_runner=command_runner,
        file_reader=file_reader,
        environ={"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME"},
        collector_uid=1000,
    )


def _runner(values):
    def run(argv):
        return values.get(tuple(argv), CommandResult(None))
    return run


class TargetUserspaceRuntimeReadbackTests(unittest.TestCase):
    def test_all_declared_t1_checks_can_pass_without_minting_runtime_or_t4_credit(self):
        values = {
            ("systemctl", "is-system-running"): CommandResult(0, "running\n"),
            ("id", "-u"): CommandResult(0, "1000\n"),
            ("systemctl", "--user", "is-system-running"): CommandResult(0, "running\n"),
            ("busctl", "--user", "--no-pager", "status"): CommandResult(0, "bus ok\n"),
            ("systemctl", "--user", "is-active", "pipewire.service"): CommandResult(0, "active\n"),
            ("systemctl", "--user", "is-active", "wireplumber.service"): CommandResult(0, "active\n"),
            ("systemctl", "--user", "is-active", "xdg-desktop-portal.service"): CommandResult(0, "active\n"),
        }
        receipt = execute_t1_runtime_readbacks(
            _profile(),
            command_runner=_runner(values),
            environ={
                "XDG_RUNTIME_DIR": "/run/user/1000",
                "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
                "XDG_SESSION_TYPE": "wayland",
            },
            path_stat_reader=lambda path: PathStatResult(True, 1000),
            handoff_evidence=HandoffEvidence(
                entry="AI_START_HERE_DO_NOT_SCAN_REPO",
                evidence_sha256="a" * 64,
            ),
        )

        self.assertEqual(receipt.pass_count, 10)
        self.assertEqual(receipt.fail_count, 0)
        self.assertEqual(receipt.unknown_count, 0)
        self.assertEqual(receipt.fidelity_gaps, ())
        self.assertEqual(
            receipt.classification,
            "T1_READBACK_ALL_DECLARED_CHECKS_PASS_NO_RUNTIME_CREDIT_MINTED",
        )
        self.assertEqual(receipt.runtime_credit, 0)
        self.assertEqual(receipt.target_twin_runtime_credit, 0)
        self.assertEqual(receipt.physical_target_credit, 0)
        self.assertFalse(receipt.whole_system_acceptance)
        self.assertEqual(len(receipt.sha256()), 64)

    def test_unavailable_observers_remain_unknown_and_are_explicit_gaps(self):
        receipt = execute_t1_runtime_readbacks(
            _profile(),
            command_runner=_runner({}),
            environ={},
            path_stat_reader=lambda path: PathStatResult(None),
        )

        statuses = {item.check: item.status for item in receipt.observations}
        self.assertEqual(statuses["systemd-system-manager-is-live"], UNKNOWN)
        self.assertEqual(statuses["non-root-target-user-exists"], UNKNOWN)
        self.assertEqual(statuses["session-dbus-is-reachable-from-target-user-context"], UNKNOWN)
        self.assertEqual(statuses["one-handoff-installer-entry-is-used"], UNKNOWN)
        self.assertEqual(statuses["twin-target-differences-are-recorded-not-masked"], PASS)
        self.assertEqual(receipt.fail_count, 0)
        self.assertGreater(receipt.unknown_count, 0)
        self.assertGreater(len(receipt.fidelity_gaps), 0)
        self.assertEqual(
            receipt.classification,
            "T1_READBACK_PARTIAL_WITH_EXPLICIT_GAPS_NO_RUNTIME_CREDIT_MINTED",
        )

    def test_mismatched_uid_xdg_owner_session_and_handoff_fail_closed(self):
        values = {
            ("systemctl", "is-system-running"): CommandResult(0, "running"),
            ("id", "-u"): CommandResult(0, "0"),
            ("systemctl", "--user", "is-system-running"): CommandResult(0, "running"),
            ("busctl", "--user", "--no-pager", "status"): CommandResult(0, "bus ok"),
            ("systemctl", "--user", "is-active", "pipewire.service"): CommandResult(0, "active"),
            ("systemctl", "--user", "is-active", "wireplumber.service"): CommandResult(0, "active"),
            ("systemctl", "--user", "is-active", "xdg-desktop-portal.service"): CommandResult(0, "active"),
        }
        receipt = execute_t1_runtime_readbacks(
            _profile(),
            command_runner=_runner(values),
            environ={
                "XDG_RUNTIME_DIR": "/run/user/0",
                "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/0/bus",
                "XDG_SESSION_TYPE": "x11",
            },
            path_stat_reader=lambda path: PathStatResult(True, 0),
            handoff_evidence=HandoffEvidence(entry="wrong-entry", evidence_sha256="b" * 64),
        )

        statuses = {item.check: item.status for item in receipt.observations}
        self.assertEqual(statuses["non-root-target-user-exists"], FAIL)
        self.assertEqual(statuses["xdg-runtime-dir-exists-and-owned-by-target-user"], FAIL)
        self.assertEqual(statuses["declared-session-type-is-observed-or-gap-recorded"], FAIL)
        self.assertEqual(statuses["one-handoff-installer-entry-is-used"], FAIL)
        self.assertGreaterEqual(receipt.fail_count, 4)
        self.assertEqual(
            receipt.classification,
            "T1_READBACK_OBSERVED_WITH_FAILURES_NO_RUNTIME_CREDIT_MINTED",
        )

    def test_runner_must_return_exact_bounded_command_result(self):
        with self.assertRaises(TargetUserspaceRuntimeReadbackError):
            execute_t1_runtime_readbacks(
                _profile(),
                command_runner=lambda argv: (True, "running", ""),
                environ={},
                path_stat_reader=lambda path: PathStatResult(None),
            )

    def test_handoff_evidence_requires_digest_and_exact_entry_for_pass(self):
        with self.assertRaises(TargetUserspaceRuntimeReadbackError):
            HandoffEvidence(entry="AI_START_HERE_DO_NOT_SCAN_REPO", evidence_sha256="not-a-digest")

        receipt = execute_t1_runtime_readbacks(
            _profile(),
            command_runner=_runner({}),
            environ={},
            path_stat_reader=lambda path: PathStatResult(None),
            handoff_evidence=HandoffEvidence(entry="other-entry", evidence_sha256="c" * 64),
        )
        handoff = next(
            item for item in receipt.observations
            if item.check == "one-handoff-installer-entry-is-used"
        )
        self.assertEqual(handoff.status, FAIL)

    def test_receipt_rejects_credit_inflation(self):
        receipt = execute_t1_runtime_readbacks(
            _profile(),
            command_runner=_runner({}),
            environ={},
            path_stat_reader=lambda path: PathStatResult(None),
        )
        with self.assertRaises(TargetUserspaceRuntimeReadbackError):
            dataclasses.replace(receipt, target_twin_runtime_credit=1)
        with self.assertRaises(TargetUserspaceRuntimeReadbackError):
            dataclasses.replace(receipt, physical_target_credit=1)
        with self.assertRaises(TargetUserspaceRuntimeReadbackError):
            dataclasses.replace(receipt, whole_system_acceptance=True)


if __name__ == "__main__":
    unittest.main()
