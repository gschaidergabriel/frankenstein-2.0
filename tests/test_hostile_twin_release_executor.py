#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from frankenstein2.hostile_twin_release_executor import (
    FAIL_AFTER_EXTRACT,
    BoundReleaseCandidate,
    HostileTwinExecutionError,
    ScratchHostileTwin,
    request_for_install,
    request_for_rollback,
    request_for_update,
)
from frankenstein2.portable_release_transaction import RELEASE_SCHEMA, ReleaseIdentity
from frankenstein2.release_archive import ReleaseArchivePolicy, build_release_archive


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def build_bundle(root: Path, label: str, payload: bytes) -> Path:
    package = root / f"pkg-{label}"
    package.mkdir()
    (package / "app.txt").write_bytes(payload)
    policy = ReleaseArchivePolicy(
        policy_id=f"test-{label}-stored-posix-v1",
        source_date_epoch=1788065582,
        executable_paths=(),
    )
    build = build_release_archive(
        package,
        release_id=f"frankenstein-2.0-{label}",
        source_commit=(label[0] * 40),
        source_tree=(label[-1] * 40),
        build_id=f"test-{label}",
        policy=policy,
    )
    release = ReleaseIdentity(
        schema=RELEASE_SCHEMA,
        release_id=build.receipt.release_id,
        version=f"git-{label}",
        artifact_sha256=build.receipt.archive_sha256,
        manifest_sha256=build.receipt.manifest_sha256,
    )
    artifact_name = f"{label}.zip"
    artifact_receipt_name = f"external-receipts/{label}.artifact-bound.json"
    content_name = f"{label}.content-bound.json"
    content_ref = f"external-receipts/{content_name}"
    abr = canonical({"schema": "TEST_ARTIFACT_BOUND/v1", "status": "READY_FOR_REAL_HOST_HANDOFF", "release": release.as_dict()})
    cbr = canonical({"schema": "TEST_CONTENT_BOUND/v1", "status": "READY_FOR_REAL_HOST_HANDOFF", "artifact_receipt_sha256": sha(abr)})
    index = {
        "schema": "FRANKENSTEIN2_RELEASE_CANDIDATE_EVIDENCE_BUNDLE/v1",
        "archive_policy": policy.as_dict(),
        "artifact": {"filename": artifact_name, "sha256": sha(build.archive_bytes), "size_bytes": len(build.archive_bytes)},
        "release_archive_receipt": build.receipt.as_dict(),
        "portable_release_identity": release.as_dict(),
        "portable_release_digest": release.digest(),
        "artifact_bound_prehandoff": {"ref": artifact_receipt_name, "sha256": sha(abr), "size_bytes": len(abr), "status": "READY_FOR_REAL_HOST_HANDOFF"},
        "receipt_content_binding": {"content_bound_receipt_filename": content_name, "content_bound_receipt_sha256": sha(cbr), "content_bound_receipt_size_bytes": len(cbr), "status": "READY_FOR_REAL_HOST_HANDOFF"},
    }
    out = root / f"{label}-bundle.zip"
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as z:
        z.writestr("RELEASE_CANDIDATE_BUNDLE.json", canonical(index))
        z.writestr(artifact_name, build.archive_bytes)
        z.writestr(artifact_receipt_name, abr)
        z.writestr(content_ref, cbr)
    return out


class HostileTwinReleaseExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.b1 = build_bundle(self.root, "aaaaaaaaaaaa", b"release-one\n")
        self.b2 = build_bundle(self.root, "bbbbbbbbbbbb", b"release-two\n")
        self.r1 = BoundReleaseCandidate.from_bundle(self.b1)
        self.r2 = BoundReleaseCandidate.from_bundle(self.b2)
        self.state = b'{"durable":"state"}\n'

    def tearDown(self) -> None:
        self.td.cleanup()

    def twin(self) -> ScratchHostileTwin:
        return ScratchHostileTwin(self.root / "twin")

    def test_fresh_install_executes_exact_bundle_and_readback(self) -> None:
        twin = self.twin()
        receipt = twin.execute(
            request_for_install(attempt_id="install-r1", release=self.r1.release_identity),
            candidate=self.r1,
            canonical_state_bytes=self.state,
        )
        self.assertEqual(receipt.outcome, "SUCCEEDED")
        self.assertEqual(receipt.observed_generation, 0)
        self.assertEqual(receipt.observed_active_release_digest, self.r1.portable_release_digest)
        current = twin.readback()
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.state_sha256, sha(self.state))
        self.assertEqual(current.active_release_digest, self.r1.portable_release_digest)
        self.assertEqual((twin.releases / self.r1.portable_release_digest / "app.txt").read_bytes(), b"release-one\n")

    def test_injected_update_failure_rolls_back_without_lineage_mutation(self) -> None:
        twin = self.twin()
        twin.execute(request_for_install(attempt_id="install-r1", release=self.r1.release_identity), candidate=self.r1, canonical_state_bytes=self.state)
        before = twin.readback()
        assert before is not None
        receipt = twin.execute(
            request_for_update(attempt_id="update-r2-fail", release=self.r2.release_identity, current=before, injected_failure_stage=FAIL_AFTER_EXTRACT),
            candidate=self.r2,
            canonical_state_bytes=self.state,
        )
        self.assertEqual(receipt.outcome, "ROLLED_BACK")
        self.assertEqual(twin.readback(), before)
        self.assertFalse((twin.releases / self.r2.portable_release_digest).exists())

    def test_successful_update_then_explicit_rollback_preserves_state_lineage(self) -> None:
        twin = self.twin()
        twin.execute(request_for_install(attempt_id="install-r1", release=self.r1.release_identity), candidate=self.r1, canonical_state_bytes=self.state)
        g0 = twin.readback(); assert g0 is not None
        up = twin.execute(request_for_update(attempt_id="update-r2", release=self.r2.release_identity, current=g0), candidate=self.r2, canonical_state_bytes=self.state)
        self.assertEqual(up.outcome, "SUCCEEDED")
        g1 = twin.readback(); assert g1 is not None
        self.assertEqual(g1.generation, 1)
        self.assertEqual(g1.predecessor_generation, 0)
        self.assertEqual(g1.predecessor_release_digest, self.r1.portable_release_digest)
        rb = twin.execute(request_for_rollback(attempt_id="rollback-r1", release=self.r1.release_identity, current=g1), candidate=self.r1, canonical_state_bytes=self.state)
        self.assertEqual(rb.outcome, "SUCCEEDED")
        g2 = twin.readback(); assert g2 is not None
        self.assertEqual(g2.generation, 2)
        self.assertEqual(g2.state_sha256, g0.state_sha256)
        self.assertEqual(g2.active_release_digest, self.r1.portable_release_digest)

    def test_stale_cache_fails_closed(self) -> None:
        twin = self.twin()
        twin.execute(request_for_install(attempt_id="install-r1", release=self.r1.release_identity), candidate=self.r1, canonical_state_bytes=self.state)
        twin.cache_current_path.write_text('{"schema":"FRANKENSTEIN2_HOSTILE_TWIN_CURRENT_SNAPSHOT/v1","snapshot_id":"stale","snapshot_sha256":"' + '0'*64 + '"}\n')
        with self.assertRaisesRegex(HostileTwinExecutionError, "stale current-snapshot cache"):
            twin.readback()

    def test_wrong_permission_twin_root_fails_before_mutation(self) -> None:
        root = self.root / "readonly-twin"
        root.mkdir(mode=0o500)
        root.chmod(0o500)
        try:
            with self.assertRaisesRegex(HostileTwinExecutionError, "not owner-writable"):
                ScratchHostileTwin(root)
        finally:
            root.chmod(0o700)

    def test_partial_preexisting_release_destination_fails_closed(self) -> None:
        twin = self.twin()
        twin.execute(request_for_install(attempt_id="install-r1", release=self.r1.release_identity), candidate=self.r1, canonical_state_bytes=self.state)
        bad = twin.releases / self.r2.portable_release_digest
        bad.mkdir()
        (bad / "partial.txt").write_text("stale")
        current = twin.readback(); assert current is not None
        with self.assertRaisesRegex(HostileTwinExecutionError, "pre-existing/partial release destination"):
            twin.execute(request_for_update(attempt_id="update-r2", release=self.r2.release_identity, current=current), candidate=self.r2, canonical_state_bytes=self.state)
        self.assertEqual(twin.readback(), current)

    def test_tampered_outer_bundle_fails_before_twin_mutation(self) -> None:
        tampered = self.root / "tampered.zip"
        data = bytearray(self.b2.read_bytes())
        data[-20] ^= 1
        tampered.write_bytes(data)
        with self.assertRaises(HostileTwinExecutionError):
            BoundReleaseCandidate.from_bundle(tampered)


if __name__ == "__main__":
    unittest.main()
