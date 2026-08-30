"""Fail-closed WP1113 release-bundle adapter for the accepted WP1207 hostile-twin loader.

F2-WP-1207 generation 6.

The accepted WP1207 generation-5 loader consumes the historical
``FRANKENSTEIN2_RELEASE_CANDIDATE_EVIDENCE_BUNDLE/v1`` outer format.  Current WP1113 emits
``FRANKENSTEIN2_RELEASE_CANDIDATE_BUNDLE/v1`` with ``release-bundle-index.json``.  This module
bridges that representation mismatch without creating a second release, archive, transaction,
state, effect, or completion authority.

For the current format it:

* binds every declared outer member by exact SHA-256 and byte count;
* reconstructs the already-declared WP1107 archive policy from exact archive metadata and
  verifies its digest against the WP1113 index;
* re-runs accepted WP1107 ``verify_release_archive`` against the exact inner release ZIP;
* cross-binds archive receipt, artifact subject, pre-handoff receipt-content subject and WP1112
  static-completeness subject;
* maps the exact source commit into the existing WP1207 ``ReleaseIdentity`` transaction ABI;
* returns the existing ``BoundReleaseCandidate`` data type used by the hostile-twin executor.

Repository/component success here is not clean-machine, target-host, physical-host, effect,
completion, GRID/GWT/J-Space, provider-model, training, or whole-system acceptance.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Mapping
import zipfile

from .hostile_twin_release_executor import BoundReleaseCandidate, HostileTwinExecutionError
from .portable_release_transaction import RELEASE_SCHEMA, ReleaseIdentity
from .release_archive import ReleaseArchivePolicy, ReleaseArchiveReceipt, verify_release_archive

LEGACY_INDEX_NAME = "RELEASE_CANDIDATE_BUNDLE.json"
CURRENT_INDEX_NAME = "release-bundle-index.json"
CURRENT_BUNDLE_SCHEMA = "FRANKENSTEIN2_RELEASE_CANDIDATE_BUNDLE/v1"
ARCHIVE_RECEIPT_NAME = "frankenstein-2.0-archive-receipt.json"
CONTENT_BOUND_NAME = "frankenstein-2.0-content-bound-prehandoff.json"
ARTIFACT_SUBJECT_SCHEMA = "FRANKENSTEIN2_RELEASE_ARTIFACT_SUBJECT/v1"
ARTIFACT_BOUND_PREHANDOFF_SCHEMA = "FRANKENSTEIN2_ARTIFACT_BOUND_PREHANDOFF_RECEIPT/v1"
CONTENT_BOUND_PREHANDOFF_SCHEMA = "FRANKENSTEIN2_CONTENT_BOUND_PREHANDOFF_RECEIPT/v1"
RECEIPT_CONTENT_SUBJECT_SCHEMA = "FRANKENSTEIN2_PREHANDOFF_RECEIPT_CONTENT_SUBJECT/v1"
STATIC_BOUND_SCHEMA = "FRANKENSTEIN2_ARTIFACT_BOUND_STATIC_COMPLETENESS/v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise HostileTwinExecutionError(f"{field} must be lowercase 64-hex SHA-256")
    return value


def _positive_size(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HostileTwinExecutionError(f"{field} must be a positive integer")
    return value


def _safe_member(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HostileTwinExecutionError(f"{field} must be a non-empty trimmed string")
    path = PurePosixPath(value)
    if path.is_absolute() or len(path.parts) != 1 or path.parts[0] in {".", ".."}:
        raise HostileTwinExecutionError(f"{field} must be one safe bundle member basename")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise HostileTwinExecutionError(f"{field} contains control characters")
    return value


def _json_object(raw: bytes, *, label: str, canonical: bool = True) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HostileTwinExecutionError(f"invalid {label} JSON") from exc
    if not isinstance(value, dict):
        raise HostileTwinExecutionError(f"{label} JSON must contain an object")
    if canonical and raw != _canonical_bytes(value):
        raise HostileTwinExecutionError(f"{label} JSON is not canonical byte form")
    return value


def _declared_files(zf: zipfile.ZipFile, index: Mapping[str, Any]) -> dict[str, bytes]:
    raw_files = index.get("files")
    if not isinstance(raw_files, dict) or not raw_files:
        raise HostileTwinExecutionError("current release bundle declared files missing")
    declared: dict[str, bytes] = {}
    for raw_name, raw_meta in raw_files.items():
        name = _safe_member(raw_name, field="declared bundle member")
        if not isinstance(raw_meta, dict):
            raise HostileTwinExecutionError(f"declared metadata missing for {name}")
        try:
            data = zf.read(name)
        except KeyError as exc:
            raise HostileTwinExecutionError(f"declared current bundle member missing: {name}") from exc
        expected_sha = _digest(raw_meta.get("sha256"), f"{name} sha256")
        expected_size = _positive_size(raw_meta.get("size_bytes"), f"{name} size_bytes")
        if _sha256(data) != expected_sha or len(data) != expected_size:
            raise HostileTwinExecutionError(f"declared current bundle member bytes mismatch: {name}")
        declared[name] = data
    expected_members = set(declared) | {CURRENT_INDEX_NAME}
    if set(zf.namelist()) != expected_members:
        raise HostileTwinExecutionError("current release bundle contains missing, renamed, or undeclared members")
    return declared


def _archive_policy_from_exact_bytes(
    archive_bytes: bytes,
    *,
    index: Mapping[str, Any],
    archive_meta: Mapping[str, Any],
) -> ReleaseArchivePolicy:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r", allowZip64=False) as inner:
            executable: list[str] = []
            for info in inner.infolist():
                mode = stat.S_IMODE(info.external_attr >> 16)
                if mode == 0o755:
                    executable.append(info.filename)
                elif mode != 0o644:
                    raise HostileTwinExecutionError(
                        f"current release archive has unsupported file mode {oct(mode)} for {info.filename}"
                    )
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise HostileTwinExecutionError("current release artifact is not a valid classic ZIP") from exc

    source_date_epoch = index.get("source_date_epoch")
    if isinstance(source_date_epoch, bool) or not isinstance(source_date_epoch, int):
        raise HostileTwinExecutionError("current bundle source_date_epoch must be an integer")
    policy_id = archive_meta.get("policy_id")
    if not isinstance(policy_id, str) or not policy_id:
        raise HostileTwinExecutionError("current bundle archive policy id missing")
    try:
        policy = ReleaseArchivePolicy(
            policy_id=policy_id,
            source_date_epoch=source_date_epoch,
            executable_paths=tuple(sorted(executable)),
        )
    except (TypeError, ValueError) as exc:
        raise HostileTwinExecutionError("current bundle archive policy reconstruction failed") from exc
    if policy.digest() != _digest(archive_meta.get("policy_sha256"), "archive policy_sha256"):
        raise HostileTwinExecutionError("current bundle archive policy digest disagrees with exact archive metadata")
    return policy


def _receipt_from_current(
    receipt_bytes: bytes,
    *,
    index: Mapping[str, Any],
    archive_meta: Mapping[str, Any],
) -> ReleaseArchiveReceipt:
    raw = _json_object(receipt_bytes, label="current archive receipt")
    keys = (
        "release_id",
        "source_commit",
        "source_tree",
        "build_id",
        "archive_policy_id",
        "archive_policy_sha256",
        "manifest_path",
        "manifest_sha256",
        "archive_sha256",
        "archive_size",
        "member_count",
    )
    try:
        receipt = ReleaseArchiveReceipt(**{key: raw[key] for key in keys})
    except (KeyError, TypeError, ValueError) as exc:
        raise HostileTwinExecutionError("current archive receipt is invalid") from exc
    if receipt.as_dict() != raw:
        raise HostileTwinExecutionError("current archive receipt mapping is noncanonical or incomplete")
    expected_pairs = {
        "release_id": index.get("release_id"),
        "source_commit": index.get("source_commit"),
        "source_tree": index.get("source_tree"),
        "build_id": index.get("build_id"),
        "archive_policy_id": archive_meta.get("policy_id"),
        "archive_policy_sha256": archive_meta.get("policy_sha256"),
        "manifest_sha256": archive_meta.get("manifest_sha256"),
        "archive_sha256": archive_meta.get("sha256"),
        "archive_size": archive_meta.get("size_bytes"),
        "member_count": archive_meta.get("member_count"),
    }
    for field, expected in expected_pairs.items():
        if getattr(receipt, field) != expected:
            raise HostileTwinExecutionError(f"current archive receipt disagrees with bundle index: {field}")
    if receipt.digest() != _digest(archive_meta.get("receipt_sha256"), "archive receipt_sha256"):
        raise HostileTwinExecutionError("current archive receipt digest disagrees with bundle index")
    tracked = index.get("tracked_regular_file_count")
    if isinstance(tracked, bool) or not isinstance(tracked, int) or tracked < 1:
        raise HostileTwinExecutionError("tracked_regular_file_count must be a positive integer")
    if receipt.member_count != tracked + 1:
        raise HostileTwinExecutionError("archive member count disagrees with tracked source file count plus manifest")
    return receipt


def _expected_artifact_subject(
    *, artifact_filename: str, receipt: ReleaseArchiveReceipt
) -> dict[str, Any]:
    return {
        "schema": ARTIFACT_SUBJECT_SCHEMA,
        "artifact_filename": artifact_filename,
        "artifact_sha256": receipt.archive_sha256,
        "artifact_size_bytes": receipt.archive_size,
        "release_manifest_sha256": receipt.manifest_sha256,
        "source_commit": receipt.source_commit,
        "source_tree": receipt.source_tree,
        "release_id": receipt.release_id,
        "build_id": receipt.build_id,
        "archive_policy_id": receipt.archive_policy_id,
        "archive_policy_sha256": receipt.archive_policy_sha256,
        "member_count": receipt.member_count,
    }


def _bind_current_subjects(
    *,
    index: Mapping[str, Any],
    declared: Mapping[str, bytes],
    artifact_filename: str,
    receipt: ReleaseArchiveReceipt,
) -> tuple[str, str]:
    subject_meta = index.get("artifact_subject")
    pre_meta = index.get("prehandoff_receipt")
    static_meta = index.get("artifact_bound_static_completeness")
    if not isinstance(subject_meta, dict) or not isinstance(pre_meta, dict) or not isinstance(static_meta, dict):
        raise HostileTwinExecutionError("current bundle subject metadata missing")

    pre_name = _safe_member(pre_meta.get("filename"), field="pre-handoff receipt filename")
    static_name = _safe_member(static_meta.get("filename"), field="static completeness filename")
    if pre_name not in declared or CONTENT_BOUND_NAME not in declared or static_name not in declared:
        raise HostileTwinExecutionError("current bundle subject receipt file missing")

    pre_bytes = declared[pre_name]
    content_bytes = declared[CONTENT_BOUND_NAME]
    static_bytes = declared[static_name]
    pre = _json_object(pre_bytes, label="artifact-bound pre-handoff receipt")
    content = _json_object(content_bytes, label="content-bound pre-handoff receipt")
    static = _json_object(static_bytes, label="artifact-bound static completeness receipt")

    expected_subject = _expected_artifact_subject(artifact_filename=artifact_filename, receipt=receipt)
    if pre.get("schema") != ARTIFACT_BOUND_PREHANDOFF_SCHEMA or pre.get("artifact_subject") != expected_subject:
        raise HostileTwinExecutionError("current artifact-bound pre-handoff subject disagrees with archive receipt")
    subject_sha = _sha256(_canonical_bytes(expected_subject))
    if subject_sha != _digest(subject_meta.get("sha256"), "artifact subject sha256"):
        raise HostileTwinExecutionError("current artifact subject digest disagrees with bundle index")
    pre_sha = _sha256(pre_bytes)
    if pre_sha != _digest(subject_meta.get("artifact_bound_prehandoff_sha256"), "artifact-bound pre-handoff sha256"):
        raise HostileTwinExecutionError("artifact-bound pre-handoff receipt digest disagrees with bundle index")
    if pre_sha != _digest(pre_meta.get("sha256"), "pre-handoff receipt sha256") or len(pre_bytes) != _positive_size(pre_meta.get("size_bytes"), "pre-handoff receipt size_bytes"):
        raise HostileTwinExecutionError("pre-handoff receipt bytes disagree with bundle index")
    if pre.get("prehandoff_receipt_ref") != pre_meta.get("declared_ref"):
        raise HostileTwinExecutionError("pre-handoff receipt reference disagrees with bundle index")
    for field in ("status", "static_status", "static_violations"):
        if pre.get(field) != subject_meta.get(field):
            raise HostileTwinExecutionError(f"artifact-bound pre-handoff {field} disagrees with bundle index")

    content_sha = _sha256(content_bytes)
    if content.get("schema") != CONTENT_BOUND_PREHANDOFF_SCHEMA:
        raise HostileTwinExecutionError("content-bound pre-handoff schema mismatch")
    if content_sha != _digest(pre_meta.get("content_bound_sha256"), "content-bound pre-handoff sha256"):
        raise HostileTwinExecutionError("content-bound pre-handoff digest disagrees with bundle index")
    if content.get("artifact_bound_prehandoff_sha256") != pre_sha:
        raise HostileTwinExecutionError("content-bound receipt disagrees with artifact-bound receipt digest")
    if content.get("artifact_subject_sha256") != subject_sha:
        raise HostileTwinExecutionError("content-bound receipt disagrees with artifact subject digest")
    if content.get("release_manifest_sha256") != receipt.manifest_sha256:
        raise HostileTwinExecutionError("content-bound receipt disagrees with release manifest digest")
    if content.get("status") != pre_meta.get("content_bound_status"):
        raise HostileTwinExecutionError("content-bound status disagrees with bundle index")
    content_subject = content.get("receipt_content_subject")
    if not isinstance(content_subject, dict) or content_subject.get("schema") != RECEIPT_CONTENT_SUBJECT_SCHEMA:
        raise HostileTwinExecutionError("receipt-content subject missing or invalid")
    expected_content_subject = {
        "schema": RECEIPT_CONTENT_SUBJECT_SCHEMA,
        "prehandoff_receipt_ref": pre_meta.get("declared_ref"),
        "prehandoff_receipt_sha256": pre_sha,
        "prehandoff_receipt_size_bytes": len(pre_bytes),
    }
    if content_subject != expected_content_subject:
        raise HostileTwinExecutionError("receipt-content subject disagrees with exact pre-handoff receipt bytes")

    if static.get("schema") != STATIC_BOUND_SCHEMA or static.get("artifact_subject") != expected_subject:
        raise HostileTwinExecutionError("WP1112 static-completeness subject disagrees with archive receipt")
    static_sha = _sha256(static_bytes)
    if static_sha != _digest(static_meta.get("sha256"), "static completeness file sha256"):
        raise HostileTwinExecutionError("WP1112 static-completeness file digest disagrees with bundle index")
    if static_sha != _digest(static_meta.get("receipt_sha256"), "static completeness receipt sha256"):
        raise HostileTwinExecutionError("WP1112 static-completeness receipt digest disagrees with bundle index")
    if static_meta.get("artifact_subject_sha256") != subject_sha:
        raise HostileTwinExecutionError("WP1112 static-completeness artifact subject digest disagrees with bundle index")
    if static_meta.get("artifact_sha256") != receipt.archive_sha256 or static_meta.get("release_manifest_sha256") != receipt.manifest_sha256:
        raise HostileTwinExecutionError("WP1112 static-completeness archive identity disagrees with archive receipt")
    for field in ("status", "static_status", "static_violations"):
        if static.get(field) != static_meta.get(field):
            raise HostileTwinExecutionError(f"WP1112 static-completeness {field} disagrees with bundle index")

    return pre_sha, content_sha


def _from_current_bundle(path: Path, outer: bytes) -> BoundReleaseCandidate:
    try:
        zf = zipfile.ZipFile(io.BytesIO(outer), "r")
    except zipfile.BadZipFile as exc:
        raise HostileTwinExecutionError("invalid current outer release bundle ZIP") from exc
    with zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            raise HostileTwinExecutionError("duplicate current outer bundle member")
        try:
            index_bytes = zf.read(CURRENT_INDEX_NAME)
        except KeyError as exc:
            raise HostileTwinExecutionError("current release bundle index missing") from exc
        index = _json_object(index_bytes, label="current release bundle index")
        if index.get("schema") != CURRENT_BUNDLE_SCHEMA:
            raise HostileTwinExecutionError("current release bundle schema mismatch")
        declared = _declared_files(zf, index)

    archive_meta = index.get("archive")
    if not isinstance(archive_meta, dict):
        raise HostileTwinExecutionError("current release archive metadata missing")
    artifact_filename = _safe_member(archive_meta.get("filename"), field="release artifact filename")
    if artifact_filename not in declared or ARCHIVE_RECEIPT_NAME not in declared:
        raise HostileTwinExecutionError("current release archive or archive receipt file missing")
    archive_bytes = declared[artifact_filename]
    if _sha256(archive_bytes) != _digest(archive_meta.get("sha256"), "archive sha256") or len(archive_bytes) != _positive_size(archive_meta.get("size_bytes"), "archive size_bytes"):
        raise HostileTwinExecutionError("current release archive bytes disagree with bundle index")

    policy = _archive_policy_from_exact_bytes(archive_bytes, index=index, archive_meta=archive_meta)
    expected_receipt = _receipt_from_current(
        declared[ARCHIVE_RECEIPT_NAME], index=index, archive_meta=archive_meta
    )
    try:
        observed_receipt = verify_release_archive(
            archive_bytes,
            policy=policy,
            expected_receipt=expected_receipt,
            manifest_path=expected_receipt.manifest_path,
        )
    except ValueError as exc:
        raise HostileTwinExecutionError("WP1107 rejected the exact current release archive") from exc
    if observed_receipt != expected_receipt:
        raise HostileTwinExecutionError("WP1107 observed receipt differs from current bundle receipt")

    artifact_bound_sha, content_bound_sha = _bind_current_subjects(
        index=index,
        declared=declared,
        artifact_filename=artifact_filename,
        receipt=observed_receipt,
    )

    source_commit = observed_receipt.source_commit
    release = ReleaseIdentity(
        schema=RELEASE_SCHEMA,
        release_id=observed_receipt.release_id,
        version=f"git-{source_commit}",
        artifact_sha256=observed_receipt.archive_sha256,
        manifest_sha256=observed_receipt.manifest_sha256,
    )
    return BoundReleaseCandidate(
        outer_sha256=_sha256(outer),
        artifact_filename=artifact_filename,
        archive_bytes=archive_bytes,
        archive_policy=policy,
        archive_receipt=observed_receipt,
        release_identity=release,
        portable_release_digest=release.digest(),
        artifact_bound_receipt_sha256=artifact_bound_sha,
        content_bound_receipt_sha256=content_bound_sha,
    )


def load_bound_release_candidate(
    bundle_path: str | Path,
    *,
    expected_outer_sha256: str | None = None,
) -> BoundReleaseCandidate:
    """Load legacy or current WP1113 bundle into the existing WP1207 candidate ABI.

    ``expected_outer_sha256`` should be supplied whenever a caller has an admitted exact
    artifact identity.  It is deliberately external to the bundle so a self-consistent
    tampered bundle cannot redefine its own expected outer identity.
    """

    path = Path(bundle_path)
    if path.is_symlink() or not path.is_file():
        raise HostileTwinExecutionError("bundle must be a regular non-symlink file")
    outer = path.read_bytes()
    outer_sha = _sha256(outer)
    if expected_outer_sha256 is not None:
        expected = expected_outer_sha256.removeprefix("sha256:")
        if outer_sha != _digest(expected, "expected_outer_sha256"):
            raise HostileTwinExecutionError("outer release bundle digest disagrees with admitted artifact identity")
    try:
        with zipfile.ZipFile(io.BytesIO(outer), "r") as zf:
            names = set(zf.namelist())
    except zipfile.BadZipFile as exc:
        raise HostileTwinExecutionError("invalid outer release bundle ZIP") from exc
    has_legacy = LEGACY_INDEX_NAME in names
    has_current = CURRENT_INDEX_NAME in names
    if has_legacy and has_current:
        raise HostileTwinExecutionError("ambiguous release bundle contains both legacy and current indexes")
    if has_legacy:
        candidate = BoundReleaseCandidate.from_bundle(path)
        if candidate.outer_sha256 != outer_sha:
            raise HostileTwinExecutionError("legacy loader outer identity disagrees with exact bytes")
        return candidate
    if has_current:
        return _from_current_bundle(path, outer)
    raise HostileTwinExecutionError("release bundle index missing")
