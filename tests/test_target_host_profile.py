from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from frankenstein2.target_host_profile import (
    COLLECTOR_VERSION,
    DEFAULT_PROBES,
    OBSERVED,
    TARGET_HOST_PROFILE_SCHEMA,
    UNKNOWN,
    ProbeSpec,
    TargetHostProfileError,
    collect_target_host_profile,
)


class TargetHostProfileTests(unittest.TestCase):
    def make_collectors(self, *, variant: str = "A"):
        command_values = {
            tuple(spec.argv): f"{variant}:{spec.field_id}"
            for spec in DEFAULT_PROBES
            if spec.argv is not None
        }
        file_values = {
            spec.file_path: f"{variant}:{spec.field_id}"
            for spec in DEFAULT_PROBES
            if spec.file_path is not None
        }

        def run(argv):
            return True, command_values[tuple(argv)], ""

        def read(path):
            return True, file_values[path], ""

        return run, read

    def test_profile_is_deterministic_for_same_explicit_observations(self) -> None:
        run, read = self.make_collectors()
        with tempfile.TemporaryDirectory() as runtime_dir:
            env = {
                "XDG_SESSION_TYPE": "wayland",
                "XDG_CURRENT_DESKTOP": "GNOME",
                "XDG_RUNTIME_DIR": runtime_dir,
            }
            uid = Path(runtime_dir).stat().st_uid
            a = collect_target_host_profile(
                generation=1,
                command_runner=run,
                file_reader=read,
                environ=env,
                collector_uid=uid,
            )
            b = collect_target_host_profile(
                generation=1,
                command_runner=run,
                file_reader=read,
                environ=dict(reversed(tuple(env.items()))),
                collector_uid=uid,
            )
        self.assertEqual(a.schema, TARGET_HOST_PROFILE_SCHEMA)
        self.assertEqual(a.collector_version, COLLECTOR_VERSION)
        self.assertEqual(a.profile_digest_sha256, b.profile_digest_sha256)
        self.assertEqual(a.canonical_json(), b.canonical_json())
        self.assertTrue(a.complete_fingerprint)
        self.assertEqual(a.unknown_fields, ())

    def test_failed_or_absent_probe_is_unknown_not_defaulted(self) -> None:
        def run(argv):
            if tuple(argv) == ("uname", "-r"):
                return False, "", "NONZERO_EXIT"
            return False, "", "COMMAND_NOT_FOUND"

        def read(path):
            if path == "/etc/os-release":
                return True, 'NAME="Ubuntu"', ""
            return False, "", "FILE_NOT_FOUND"

        profile = collect_target_host_profile(
            generation=3,
            command_runner=run,
            file_reader=read,
            environ={},
            collector_uid=1000,
        )
        self.assertEqual(profile.facts["os_release"]["status"], OBSERVED)
        self.assertEqual(profile.facts["kernel_release"]["status"], UNKNOWN)
        self.assertEqual(profile.facts["kernel_release"]["reason"], "NONZERO_EXIT")
        self.assertNotIn("value", profile.facts["kernel_release"])
        self.assertEqual(profile.facts["session_type"]["status"], UNKNOWN)
        self.assertIn("session_type", profile.unknown_fields)
        self.assertFalse(profile.complete_fingerprint)

    def test_generation_and_observation_change_profile_digest(self) -> None:
        run_a, read_a = self.make_collectors(variant="A")
        run_b, read_b = self.make_collectors(variant="B")
        env = {
            "XDG_SESSION_TYPE": "wayland",
            "XDG_CURRENT_DESKTOP": "GNOME",
        }
        a = collect_target_host_profile(
            generation=1,
            command_runner=run_a,
            file_reader=read_a,
            environ=env,
            collector_uid=1000,
        )
        b = collect_target_host_profile(
            generation=2,
            command_runner=run_b,
            file_reader=read_b,
            environ=env,
            collector_uid=1000,
        )
        self.assertNotEqual(a.profile_digest_sha256, b.profile_digest_sha256)
        self.assertEqual(a.generation, 1)
        self.assertEqual(b.generation, 2)

    def test_custom_probe_set_is_rejected_to_preserve_privacy_allowlist(self) -> None:
        probes = DEFAULT_PROBES + (
            ProbeSpec(
                "secrets",
                "forbidden",
                argv=("cat", "/home/user/.ssh/id_ed25519"),
            ),
        )
        with self.assertRaisesRegex(TargetHostProfileError, "custom probe sets"):
            collect_target_host_profile(generation=1, probes=probes)

    def test_default_probe_surface_has_no_user_content_or_secret_collectors(self) -> None:
        serialized = " ".join(
            " ".join(spec.argv or ()) + " " + (spec.file_path or "") + " " + (spec.env_key or "")
            for spec in DEFAULT_PROBES
        ).lower()
        forbidden = (
            ".ssh",
            "clipboard",
            "xclip",
            "wl-paste",
            "cookies",
            "history",
            "camera frame",
            "microphone audio",
            "/home/",
            "printenv",
            "ps ",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, serialized)

    def test_missing_runtime_dir_does_not_guess_ownership(self) -> None:
        run, read = self.make_collectors()
        profile = collect_target_host_profile(
            generation=1,
            command_runner=run,
            file_reader=read,
            environ={
                "XDG_SESSION_TYPE": "wayland",
                "XDG_CURRENT_DESKTOP": "GNOME",
            },
            collector_uid=1000,
        )
        self.assertEqual(
            profile.facts["xdg_runtime_dir_present"],
            {"status": OBSERVED, "source": "runtime:XDG_RUNTIME_DIR", "value": False},
        )
        ownership = profile.facts["xdg_runtime_dir_owned_by_collector_uid"]
        self.assertEqual(ownership["status"], UNKNOWN)
        self.assertEqual(ownership["reason"], "RUNTIME_DIR_ABSENT")

    def test_invalid_generation_fails_closed(self) -> None:
        run, read = self.make_collectors()
        for generation in (0, -1, True):
            with self.subTest(generation=generation):
                with self.assertRaisesRegex(TargetHostProfileError, "positive integer"):
                    collect_target_host_profile(
                        generation=generation,
                        command_runner=run,
                        file_reader=read,
                        environ={},
                        collector_uid=1000,
                    )


if __name__ == "__main__":
    unittest.main()
