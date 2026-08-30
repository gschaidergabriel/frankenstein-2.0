from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from frankenstein2.artifact_bound_static_completeness import (
    EVIDENCE_SCOPE,
    bind_release_artifact_static_completeness,
)
from frankenstein2.portable_release_static_completeness import BLOCKED, STATIC_COMPLETE
from frankenstein2.release_archive import (
    ReleaseArchiveError,
    ReleaseArchivePolicy,
    build_release_archive,
    write_release_archive,
)
from frankenstein2.release_integrity import DEFAULT_MANIFEST_PATH
from tests.test_portable_release_static_completeness import (
    RECEIPT_REF,
    PortableReleaseStaticCompletenessTests,
)

EPOCH = 1_700_000_000


class ArtifactBoundStaticCompletenessTests(unittest.TestCase):
    def _policy(self) -> ReleaseArchivePolicy:
        return ReleaseArchivePolicy(
            policy_id="f2-release-zip-stored-posix-v1",
            source_date_epoch=EPOCH,
        )

    def _build(self, root: Path, *, drift_perception: bool = False):
        fixture = PortableReleaseStaticCompletenessTests()
        fixture._package(root)

        # The WP1111 fixture writes a standalone manifest so it can exercise the directory
        # gate directly. WP1107 is the authority for the exact archive manifest, so remove
        # that fixture-only copy before constructing the release candidate.
        fixture_manifest = root / DEFAULT_MANIFEST_PATH
        if fixture_manifest.exists():
            fixture_manifest.unlink()

        if drift_perception:
            contract_path = root / "AI_START_HERE_DO_NOT_SCAN_REPO/02_RELEASE_CONTRACT.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["perception_defaults"]["raw_frame_persistence"] = True
            contract_path.write_text(json.dumps(contract), encoding="utf-8")

        return build_release_archive(
            root,
            release_id="frankenstein-2.0-wp1112-test",
            source_commit="d" * 40,
            source_tree="e" * 40,
            build_id="wp1112-artifact-static-test",
            policy=self._policy(),
            prehandoff_receipt_refs=(RECEIPT_REF,),
        )

    def test_exact_release_zip_runs_wp1111_on_verified_materialized_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            payload = tmp_root / "payload"
            payload.mkdir()
            build = self._build(payload)
            artifact = write_release_archive(tmp_root / "frankenstein-2.0.zip", build)

            first = bind_release_artifact_static_completeness(
                artifact,
                policy=self._policy(),
                prehandoff_receipt_ref=RECEIPT_REF,
                expected_archive_receipt=build.receipt,
            )
            second = bind_release_artifact_static_completeness(
                artifact,
                policy=self._policy(),
                prehandoff_receipt_ref=RECEIPT_REF,
                expected_archive_receipt=build.receipt,
            )

            self.assertEqual(first.status, STATIC_COMPLETE)
            self.assertEqual(first.static_status, STATIC_COMPLETE)
            self.assertEqual(first.static_violations, ())
            self.assertEqual(first.artifact_sha256, build.receipt.archive_sha256)
            self.assertEqual(first.release_manifest_sha256, build.receipt.manifest_sha256)
            self.assertEqual(first.artifact_subject.source_commit, "d" * 40)
            self.assertEqual(first.artifact_subject.source_tree, "e" * 40)
            self.assertEqual(first.artifact_subject.build_id, "wp1112-artifact-static-test")
            self.assertEqual(first.evidence_scope, EVIDENCE_SCOPE)
            self.assertEqual(first.runtime_credit, 0)
            self.assertEqual(first.physical_host_credit, 0)
            self.assertEqual(first.effect_credit, 0)
            self.assertEqual(first.completion_credit, 0)
            self.assertFalse(first.whole_system_acceptance)
            self.assertEqual(first.canonical_bytes(), second.canonical_bytes())
            self.assertEqual(first.sha256(), second.sha256())

    def test_exact_archive_with_wp1111_contract_drift_is_bound_but_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            payload = tmp_root / "payload"
            payload.mkdir()
            build = self._build(payload, drift_perception=True)
            artifact = write_release_archive(tmp_root / "frankenstein-2.0.zip", build)

            result = bind_release_artifact_static_completeness(
                artifact,
                policy=self._policy(),
                prehandoff_receipt_ref=RECEIPT_REF,
                expected_archive_receipt=build.receipt,
            )

            self.assertEqual(result.status, BLOCKED)
            self.assertEqual(result.static_status, BLOCKED)
            self.assertIn(
                "perception_defaults:raw_frame_persistence_must_be_false",
                result.static_violations,
            )
            self.assertEqual(result.artifact_sha256, build.receipt.archive_sha256)
            self.assertEqual(result.runtime_credit, 0)

    def test_mutated_outer_artifact_fails_before_wp1111_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            payload = tmp_root / "payload"
            payload.mkdir()
            build = self._build(payload)
            artifact = write_release_archive(tmp_root / "frankenstein-2.0.zip", build)
            artifact.write_bytes(build.archive_bytes + b"trailing-tamper")

            with self.assertRaises(ReleaseArchiveError):
                bind_release_artifact_static_completeness(
                    artifact,
                    policy=self._policy(),
                    prehandoff_receipt_ref=RECEIPT_REF,
                    expected_archive_receipt=build.receipt,
                )

    def test_wrong_expected_archive_subject_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            payload = tmp_root / "payload"
            payload.mkdir()
            build = self._build(payload)
            artifact = write_release_archive(tmp_root / "frankenstein-2.0.zip", build)
            wrong = replace(build.receipt, manifest_sha256="0" * 64)

            with self.assertRaisesRegex(ReleaseArchiveError, "receipt identity mismatch"):
                bind_release_artifact_static_completeness(
                    artifact,
                    policy=self._policy(),
                    prehandoff_receipt_ref=RECEIPT_REF,
                    expected_archive_receipt=wrong,
                )


if __name__ == "__main__":
    unittest.main()
