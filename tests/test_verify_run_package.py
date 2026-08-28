import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runpackages"))
import verify_run_package as vr


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest_digest(manifest: dict) -> str:
    unsigned = dict(manifest)
    unsigned.pop("package_digest", None)
    payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_manifest(package: Path, manifest: dict) -> None:
    manifest["package_digest"] = _manifest_digest(manifest)
    (package / vr.MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def build_package(root: Path) -> tuple[Path, dict]:
    package = root / "run-001"
    payload = package / "logs" / "result.txt"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b"PASS\n")
    manifest = {
        "schema": vr.SCHEMA,
        "package_id": "run-001",
        "workpackage_id": "F2-WP-004",
        "generation": 2,
        "source_identity": {
            "repository": "gschaidergabriel/frankenstein-2.0",
            "ref": "main",
            "commit_sha": "a" * 40,
            "tree_sha": "b" * 40,
        },
        "claim_scope": "RUN_PACKAGE_VERIFIER_COMPONENT_ONLY",
        "runtime_credit_ceiling": "COMPONENT_ONLY",
        "command": ["python", "tests/test_verify_run_package.py"],
        "outcome": "PASS",
        "provider_calls": 0,
        "paid_spend_usd": "0",
        "external_effects_executed": False,
        "started_at": "2026-08-28T14:00:00Z",
        "completed_at": "2026-08-28T14:00:01Z",
        "exit_code": 0,
        "files": {"logs/result.txt": _digest_bytes(payload.read_bytes())},
        "package_digest": "0" * 64,
    }
    _write_manifest(package, manifest)
    return package, manifest


class VerifyRunPackageTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.package, self.manifest = build_package(self.root)

    def tearDown(self):
        self.td.cleanup()

    def test_valid_package_verifies(self):
        result = vr.verify_package(self.package)
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["outcome"], "PASS")
        self.assertEqual(result["payload_count"], 1)

    def test_payload_tamper_is_rejected(self):
        (self.package / "logs" / "result.txt").write_bytes(b"TAMPERED\n")
        with self.assertRaisesRegex(vr.RunPackageError, "PAYLOAD_DIGEST_MISMATCH"):
            vr.verify_package(self.package)

    def test_unindexed_extra_payload_is_rejected(self):
        (self.package / "logs" / "extra.txt").write_text("extra", encoding="utf-8")
        with self.assertRaisesRegex(vr.RunPackageError, "PAYLOAD_SET_MISMATCH"):
            vr.verify_package(self.package)

    def test_path_traversal_index_is_rejected(self):
        self.manifest["files"] = {"../escape.txt": "c" * 64}
        _write_manifest(self.package, self.manifest)
        with self.assertRaisesRegex(vr.RunPackageError, "UNSAFE_PAYLOAD_PATH"):
            vr.verify_package(self.package)

    def test_payload_symlink_is_rejected(self):
        payload = self.package / "logs" / "result.txt"
        target = self.root / "outside.txt"
        target.write_text("outside", encoding="utf-8")
        payload.unlink()
        try:
            payload.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        with self.assertRaisesRegex(vr.RunPackageError, "PAYLOAD_SYMLINK_FORBIDDEN"):
            vr.verify_package(self.package)

    def test_manifest_symlink_is_rejected(self):
        manifest_path = self.package / vr.MANIFEST_NAME
        external = self.root / "external-manifest.json"
        external.write_bytes(manifest_path.read_bytes())
        manifest_path.unlink()
        try:
            manifest_path.symlink_to(external)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        with self.assertRaisesRegex(vr.RunPackageError, "MANIFEST_SYMLINK_FORBIDDEN"):
            vr.verify_package(self.package)

    def test_manifest_digest_tamper_is_rejected(self):
        data = json.loads((self.package / vr.MANIFEST_NAME).read_text(encoding="utf-8"))
        data["package_digest"] = "0" * 64
        (self.package / vr.MANIFEST_NAME).write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(vr.RunPackageError, "PACKAGE_DIGEST_MISMATCH"):
            vr.verify_package(self.package)

    def test_pass_requires_observed_zero_exit(self):
        self.manifest["exit_code"] = 1
        _write_manifest(self.package, self.manifest)
        with self.assertRaisesRegex(vr.RunPackageError, "PASS_REQUIRES_OBSERVED_ZERO_EXIT_EXECUTION"):
            vr.verify_package(self.package)

    def test_not_run_cannot_carry_execution_result(self):
        self.manifest["outcome"] = "NOT_RUN"
        _write_manifest(self.package, self.manifest)
        with self.assertRaisesRegex(vr.RunPackageError, "NOT_RUN_MUST_NOT_CONTAIN_EXECUTION_RESULT"):
            vr.verify_package(self.package)

    def test_invalid_source_commit_is_rejected(self):
        self.manifest["source_identity"]["commit_sha"] = "deadbeef"
        _write_manifest(self.package, self.manifest)
        with self.assertRaisesRegex(vr.RunPackageError, "INVALID_SOURCE_COMMIT_SHA"):
            vr.verify_package(self.package)

    def test_boolean_generation_is_rejected(self):
        self.manifest["generation"] = False
        _write_manifest(self.package, self.manifest)
        with self.assertRaisesRegex(vr.RunPackageError, "INVALID_GENERATION"):
            vr.verify_package(self.package)


if __name__ == "__main__":
    unittest.main()
