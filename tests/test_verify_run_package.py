#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runpackages"))

import verify_run_package as vrp  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


class RunPackageVerifierTests(unittest.TestCase):
    def _package(
        self,
        root: Path,
        *,
        classification: str = "COMPONENT_RUNTIME",
        runtime_observed: bool = True,
        runtime_credit: int = 1,
        not_observable: bool = False,
    ) -> Path:
        package = root / "package"
        package.mkdir()
        receipt = package / "receipts" / "ci.json"
        receipt.parent.mkdir()
        receipt.write_text('{"conclusion":"success","run_id":33181650674}\n', encoding="utf-8")

        participant = {
            "participant_id": "github-actions-job",
            "component": "runpackage-verifier-ci",
            "observability": "NOT_OBSERVABLE" if not_observable else "OBSERVABLE",
            "telemetry_refs": [] if not_observable else ["receipts/ci.json"],
        }
        if not_observable:
            participant["not_observable_reason"] = "fixture intentionally omits runtime telemetry"

        manifest = {
            "schema": vrp.MANIFEST_SCHEMA,
            "run_id": "wp004-verifier-regression-1",
            "series": "wp004-verifier",
            "workpackage_id": "F2-WP-004",
            "generation": 2,
            "claim_id": "F2-WP-004-G2-VERIFIER-HARDENING",
            "worker_id": "GPT-5.6-Sol",
            "source_commit_before": "a" * 40,
            "source_commit_after": "b" * 40,
            "started_at_utc": "2026-08-28T14:44:06Z",
            "finished_at_utc": "2026-08-28T14:44:15Z",
            "commands": [
                {
                    "command_id": "regression",
                    "argv_or_description": "python tests/test_verify_run_package.py",
                    "status": "EXECUTED_PASS",
                    "exit_code": 0,
                    "receipt_ref": "receipts/ci.json",
                }
            ],
            "evidence_scope": {
                "classification": classification,
                "runtime_execution_observed": runtime_observed,
                "runtime_credit": runtime_credit,
                "acceptance_scope": "WP-004 verifier component only",
                "completion_deficit": "whole-system credit remains zero",
            },
            "participants": [participant],
            "artifacts_index": vrp.ARTIFACTS_NAME,
            "closure_receipt": vrp.CLOSED_NAME,
            "next_exact_action": "continue only at declared scope",
        }
        _write_json(package / vrp.MANIFEST_NAME, manifest)

        artifacts = {
            "schema": vrp.ARTIFACT_SCHEMA,
            "run_id": manifest["run_id"],
            "generated_at_utc": "2026-08-28T14:44:16Z",
            "artifacts": [],
        }
        for rel, role in ((vrp.MANIFEST_NAME, "MANIFEST"), ("receipts/ci.json", "RECEIPT")):
            path = package / rel
            artifacts["artifacts"].append(
                {
                    "path": rel,
                    "sha256": _sha(path),
                    "size_bytes": path.stat().st_size,
                    "role": role,
                    "provenance": {
                        "producer": "test_verify_run_package.py",
                        "source_kind": "TEST_HARNESS",
                        "source_ref": None,
                        "causal_id": None,
                        "trace_id": None,
                    },
                }
            )
        _write_json(package / vrp.ARTIFACTS_NAME, artifacts)

        sum_paths = [vrp.MANIFEST_NAME, "receipts/ci.json", vrp.ARTIFACTS_NAME]
        (package / vrp.SUMS_NAME).write_text(
            "".join(f"{_sha(package / rel)}  {rel}\n" for rel in sum_paths),
            encoding="utf-8",
        )

        if classification == "SOURCE_ONLY":
            closure_status = "CLOSED_SOURCE_ONLY"
        elif classification == "BLOCKED":
            closure_status = "CLOSED_BLOCKED"
        elif classification == "NEGATIVE_RESULT":
            closure_status = "CLOSED_FAIL"
        else:
            closure_status = "CLOSED_PASS_AT_SCOPE"

        closed = {
            "schema": vrp.CLOSED_SCHEMA,
            "run_id": manifest["run_id"],
            "closed_at_utc": "2026-08-28T14:44:17Z",
            "manifest_sha256": _sha(package / vrp.MANIFEST_NAME),
            "artifact_index_sha256": _sha(package / vrp.ARTIFACTS_NAME),
            "sha256sums_sha256": _sha(package / vrp.SUMS_NAME),
            "closure_status": closure_status,
            "evidence_classification": classification,
            "runtime_execution_observed": runtime_observed,
            "runtime_credit": runtime_credit,
            "acceptance_scope": "WP-004 verifier component only",
            "completion_deficit": "whole-system credit remains zero",
            "not_observable_participants": (
                [{"participant_id": "github-actions-job", "reason": participant["not_observable_reason"]}]
                if not_observable
                else []
            ),
            "source_commit_after": "b" * 40,
            "next_exact_action": "continue only at declared scope",
        }
        _write_json(package / vrp.CLOSED_NAME, closed)
        return package

    def test_valid_closed_component_package_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = vrp.verify_package(self._package(Path(td)))
            self.assertEqual(result["status"], "VERIFIED_CLOSED")
            self.assertEqual(result["evidence_classification"], "COMPONENT_RUNTIME")
            self.assertEqual(result["runtime_credit"], 1)

    def test_payload_directory_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            package = self._package(root)
            outside = root / "outside"
            outside.mkdir()
            try:
                (package / "linked-dir").symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("directory symlinks unavailable on this platform")
            with self.assertRaisesRegex(vrp.RunPackageError, "PACKAGE_SYMLINK_FORBIDDEN"):
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

    def test_payload_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            package = self._package(Path(td))
            (package / "receipts" / "ci.json").write_text('{"tampered":true}\n', encoding="utf-8")
            with self.assertRaisesRegex(vrp.RunPackageError, "ARTIFACT_DIGEST_MISMATCH"):
                vrp.verify_package(package)

    def test_missing_not_observable_reason_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            package = self._package(Path(td), not_observable=True)
            manifest_path = package / vrp.MANIFEST_NAME
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["participants"][0].pop("not_observable_reason")
            _write_json(manifest_path, manifest)
            with self.assertRaisesRegex(vrp.RunPackageError, "NOT_OBSERVABLE_REASON"):
                vrp.verify_package(package)

    def test_unobserved_runtime_credit_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            package = self._package(Path(td), runtime_observed=False, runtime_credit=1)
            with self.assertRaisesRegex(vrp.RunPackageError, "UNOBSERVED_RUNTIME_CANNOT_HAVE_CREDIT"):
                vrp.verify_package(package)

    def test_closed_digest_tamper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            package = self._package(Path(td))
            closed_path = package / vrp.CLOSED_NAME
            closed = json.loads(closed_path.read_text(encoding="utf-8"))
            closed["manifest_sha256"] = "0" * 64
            _write_json(closed_path, closed)
            with self.assertRaisesRegex(vrp.RunPackageError, "CLOSED_DIGEST_MISMATCH"):
                vrp.verify_package(package)

    def test_artifact_index_cannot_index_itself(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            package = self._package(Path(td))
            index_path = package / vrp.ARTIFACTS_NAME
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index["artifacts"].append(
                {
                    "path": vrp.ARTIFACTS_NAME,
                    "sha256": "0" * 64,
                    "size_bytes": 0,
                    "role": "OTHER",
                    "provenance": {"producer": "test", "source_kind": "TEST_HARNESS"},
                }
            )
            _write_json(index_path, index)
            with self.assertRaisesRegex(vrp.RunPackageError, "SELF_OR_CLOSURE_FILE_FORBIDDEN"):
                vrp.verify_package(package)


if __name__ == "__main__":
    unittest.main()
