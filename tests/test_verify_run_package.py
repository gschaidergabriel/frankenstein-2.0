#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runpackages"))

import verify_run_package as vrp  # noqa: E402


class RunPackageVerifierTests(unittest.TestCase):
    def _package(self, root: Path, *, paid_spend_usd: str = "0") -> Path:
        package = root / "package"
        package.mkdir()
        payload = package / "logs" / "result.txt"
        payload.parent.mkdir()
        payload.write_text("ok\n", encoding="utf-8")

        digest = hashlib.sha256(payload.read_bytes()).hexdigest()
        manifest = {
            "schema": vrp.SCHEMA,
            "package_id": "wp004-verifier-regression",
            "workpackage_id": "F2-WP-004",
            "generation": 2,
            "source_identity": {
                "repository": "gschaidergabriel/frankenstein-2.0",
                "ref": "main",
                "commit_sha": "a" * 40,
                "tree_sha": "b" * 40,
            },
            "claim_scope": "run-package verifier regression fixture",
            "runtime_credit_ceiling": "TEST_FIXTURE_ONLY",
            "command": ["python", "-m", "unittest", "tests.test_verify_run_package"],
            "outcome": "PASS",
            "started_at": "2026-08-28T14:42:00Z",
            "completed_at": "2026-08-28T14:42:01Z",
            "exit_code": 0,
            "provider_calls": 0,
            "paid_spend_usd": paid_spend_usd,
            "external_effects_executed": False,
            "files": {"logs/result.txt": digest},
        }
        manifest["package_digest"] = vrp._manifest_digest(manifest)
        (package / vrp.MANIFEST_NAME).write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return package

    def test_valid_package_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = vrp.verify_package(self._package(Path(td)))
            self.assertEqual(result["status"], "VERIFIED")
            self.assertEqual(result["payload_count"], 1)

    def test_payload_directory_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package = self._package(root)
            outside = root / "outside"
            outside.mkdir()
            (outside / "secret.txt").write_text("outside\n", encoding="utf-8")
            try:
                (package / "linked-dir").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks unavailable on this platform")

            with self.assertRaisesRegex(vrp.RunPackageError, "PAYLOAD_SYMLINK_FORBIDDEN"):
                vrp.verify_package(package)

    def test_package_directory_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package = self._package(root)
            alias = root / "package-alias"
            try:
                alias.symlink_to(package, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks unavailable on this platform")

            with self.assertRaisesRegex(vrp.RunPackageError, "PACKAGE_DIRECTORY_SYMLINK_FORBIDDEN"):
                vrp.verify_package(alias)

    def test_non_finite_paid_spend_is_rejected(self) -> None:
        for value in ("Infinity", "-Infinity", "NaN", "sNaN"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as td:
                package = self._package(Path(td), paid_spend_usd=value)
                with self.assertRaisesRegex(vrp.RunPackageError, "INVALID_PAID_SPEND"):
                    vrp.verify_package(package)

    def test_payload_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            package = self._package(Path(td))
            (package / "logs" / "result.txt").write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(vrp.RunPackageError, "PAYLOAD_DIGEST_MISMATCH"):
                vrp.verify_package(package)


if __name__ == "__main__":
    unittest.main()
