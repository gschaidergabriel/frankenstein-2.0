"""Bounded filesystem hostile-twin executor for Frankenstein 2.0 release handoff.

F2-WP-1207 generation 5 candidate.

This module closes the gap between deterministic release/transaction planning and an
*executable* install/update/failure/rollback/readback cycle inside an explicitly supplied
scratch twin root.  It composes existing authorities instead of replacing them:

- WP1107 ``verify_release_archive`` remains ZIP/container authority.
- WP1207 G1 ``build_transaction_plan`` / ``record_attempt`` remain transaction authority.
- WP1207 G2 ``record_release_readback`` remains active-release readback authority.
- The canonical application state remains caller-supplied bytes; this executor never invents
  semantic state or claims EffectGate/CompletionGate authority.

The executor performs real filesystem mutation only below ``twin_root``.  Repository/local
execution of this component is not target-host, physical-host, effect, completion, GRID/GWT,
J-Space, training, or whole-system acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
from typing import Any, Mapping
import zipfile

from .portable_release_readback import ReleaseReadbackReceipt, record_release_readback
from .portable_release_transaction import (
    LINEAGE_SCHEMA,
    RELEASE_SCHEMA,
    REQUEST_SCHEMA,
    ReleaseIdentity,
    StateLineage,
    TransactionRequest,
    build_transaction_plan,
)
from .release_archive import (
    ReleaseArchivePolicy,
    ReleaseArchiveReceipt,
    verify_release_archive,
)

BUNDLE_SCHEMA = "FRANKENSTEIN2_RELEASE_CANDIDATE_EVIDENCE_BUNDLE/v1"
EXECUTION_RECEIPT_SCHEMA = "FRANKENSTEIN2_HOSTILE_TWIN_FILESYSTEM_EXECUTION_RECEIPT/v1"
EXECUTION_SCOPE = (
    "BOUNDED_FILESYSTEM_HOSTILE_TWIN_EXECUTION_ONLY_"
    "NO_TARGET_PHYSICAL_EFFECT_COMPLETION_GRID_GWT_JSPACE_TRAINING_OR_WHOLE_SYSTEM_CREDIT"
)
ACTIVE_SCHEMA = "FRANKENSTEIN2_HOSTILE_TWIN_ACTIVE_RELEASE/v1"
FAIL_AFTER_EXTRACT = "AFTER_EXTRACT_BEFORE_ACTIVATE"


class HostileTwinExecutionError(ValueError):
    """Fail-closed hostile-twin executor error."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_name(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HostileTwinExecutionError(f"{field} must be a non-empty trimmed string")
    p = PurePosixPath(value)
    if p.is_absolute() or len(p.parts) != 1 or p.parts[0] in {".", ".."}:
        raise HostileTwinExecutionError(f"{field} must be one safe path component")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise HostileTwinExecutionError(f"{field} contains control characters")
    return value


def _ensure_plain_dir(path: Path, *, create: bool = False) -> None:
    if path.is_symlink():
        raise HostileTwinExecutionError(f"symlink directory forbidden: {path}")
    if create:
        path.mkdir(parents=False, exist_ok=True)
    if not path.is_dir():
        raise HostileTwinExecutionError(f"expected directory: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if not (mode & stat.S_IWUSR):
        raise HostileTwinExecutionError(f"directory is not owner-writable: {path}")


def _ensure_ancestry_plain(root: Path, path: Path) -> None:
    root = root.resolve(strict=True)
    try:
        rel = path.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise HostileTwinExecutionError("path escapes twin root") from exc
    cur = root
    for part in rel.parts[:-1]:
        cur = cur / part
        if cur.exists() or cur.is_symlink():
            if cur.is_symlink() or not cur.is_dir():
                raise HostileTwinExecutionError(f"unsafe output ancestor: {cur}")


def _write_atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _ensure_ancestry_plain(path.parents[1] if len(path.parents) > 1 else path.parent, path)
    data = _canonical_bytes(value)
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        raise HostileTwinExecutionError(f"stale temporary control file: {tmp}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(tmp, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        finally:
            raise


def _json_file(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise HostileTwinExecutionError(f"control file missing or unsafe: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HostileTwinExecutionError(f"invalid control JSON: {path}") from exc
    if not isinstance(value, dict):
        raise HostileTwinExecutionError(f"control JSON must contain an object: {path}")
    return value


@dataclass(frozen=True, slots=True)
class BoundReleaseCandidate:
    outer_sha256: str
    artifact_filename: str
    archive_bytes: bytes
    archive_policy: ReleaseArchivePolicy
    archive_receipt: ReleaseArchiveReceipt
    release_identity: ReleaseIdentity
    portable_release_digest: str
    artifact_bound_receipt_sha256: str
    content_bound_receipt_sha256: str

    @classmethod
    def from_bundle(cls, bundle_path: str | Path) -> "BoundReleaseCandidate":
        path = Path(bundle_path)
        if path.is_symlink() or not path.is_file():
            raise HostileTwinExecutionError("bundle must be a regular non-symlink file")
        outer = path.read_bytes()
        outer_sha = _sha256(outer)
        try:
            zf = zipfile.ZipFile(path, "r")
        except zipfile.BadZipFile as exc:
            raise HostileTwinExecutionError("invalid outer release evidence ZIP") from exc
        with zf:
            names = zf.namelist()
            if len(names) != len(set(names)):
                raise HostileTwinExecutionError("duplicate outer bundle member")
            if "RELEASE_CANDIDATE_BUNDLE.json" not in names:
                raise HostileTwinExecutionError("release bundle index missing")
            try:
                index = json.loads(zf.read("RELEASE_CANDIDATE_BUNDLE.json"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise HostileTwinExecutionError("invalid release bundle index") from exc
            if not isinstance(index, dict) or index.get("schema") != BUNDLE_SCHEMA:
                raise HostileTwinExecutionError("release bundle schema mismatch")

            artifact_meta = index.get("artifact")
            if not isinstance(artifact_meta, dict):
                raise HostileTwinExecutionError("artifact metadata missing")
            artifact_filename = _safe_name(artifact_meta.get("filename"), field="artifact filename")
            try:
                archive_bytes = zf.read(artifact_filename)
            except KeyError as exc:
                raise HostileTwinExecutionError("declared release artifact missing") from exc
            if _sha256(archive_bytes) != artifact_meta.get("sha256") or len(archive_bytes) != artifact_meta.get("size_bytes"):
                raise HostileTwinExecutionError("release artifact bytes do not match bundle index")

            policy_raw = index.get("archive_policy")
            if not isinstance(policy_raw, dict):
                raise HostileTwinExecutionError("archive policy missing")
            try:
                policy = ReleaseArchivePolicy(
                    policy_id=policy_raw["policy_id"],
                    source_date_epoch=policy_raw["source_date_epoch"],
                    executable_paths=tuple(policy_raw.get("executable_paths", ())),
                    regular_mode=policy_raw.get("regular_mode", 0o644),
                    executable_mode=policy_raw.get("executable_mode", 0o755),
                    create_system=policy_raw.get("create_system", 3),
                    create_version=policy_raw.get("create_version", 20),
                    extract_version=policy_raw.get("extract_version", 20),
                    compression=policy_raw.get("compression", zipfile.ZIP_STORED),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise HostileTwinExecutionError("invalid archive policy") from exc
            if policy.as_dict() != policy_raw:
                raise HostileTwinExecutionError("archive policy is not canonical")

            receipt_raw = index.get("release_archive_receipt")
            if not isinstance(receipt_raw, dict):
                raise HostileTwinExecutionError("release archive receipt missing")
            receipt_fields = {
                key: receipt_raw[key]
                for key in (
                    "release_id", "source_commit", "source_tree", "build_id",
                    "archive_policy_id", "archive_policy_sha256", "manifest_path",
                    "manifest_sha256", "archive_sha256", "archive_size", "member_count",
                )
            }
            expected_receipt = ReleaseArchiveReceipt(**receipt_fields)
            observed_receipt = verify_release_archive(
                archive_bytes,
                policy=policy,
                expected_receipt=expected_receipt,
                manifest_path=receipt_raw.get("manifest_path", "manifest/release-manifest.json"),
            )
            if observed_receipt.as_dict() != receipt_raw:
                raise HostileTwinExecutionError("release archive receipt mapping mismatch")

            release_raw = index.get("portable_release_identity")
            if not isinstance(release_raw, dict):
                raise HostileTwinExecutionError("portable release identity missing")
            release = ReleaseIdentity.from_mapping(release_raw)
            if release.release_id != observed_receipt.release_id:
                raise HostileTwinExecutionError("release id disagrees with archive receipt")
            if release.artifact_sha256 != observed_receipt.archive_sha256:
                raise HostileTwinExecutionError("release artifact digest disagrees with archive")
            if release.manifest_sha256 != observed_receipt.manifest_sha256:
                raise HostileTwinExecutionError("release manifest digest disagrees with archive")
            portable_digest = release.digest()
            if portable_digest != index.get("portable_release_digest"):
                raise HostileTwinExecutionError("portable release digest mismatch")

            artifact_bound = index.get("artifact_bound_prehandoff")
            content_bound = index.get("receipt_content_binding")
            if not isinstance(artifact_bound, dict) or not isinstance(content_bound, dict):
                raise HostileTwinExecutionError("bound pre-handoff receipt metadata missing")
            artifact_ref = artifact_bound.get("ref")
            content_name = content_bound.get("content_bound_receipt_filename")
            if not isinstance(artifact_ref, str) or not isinstance(content_name, str):
                raise HostileTwinExecutionError("bound receipt reference missing")
            content_ref = f"external-receipts/{content_name}"
            try:
                artifact_receipt_bytes = zf.read(artifact_ref)
                content_receipt_bytes = zf.read(content_ref)
            except KeyError as exc:
                raise HostileTwinExecutionError("declared bound receipt missing") from exc
            if _sha256(artifact_receipt_bytes) != artifact_bound.get("sha256") or len(artifact_receipt_bytes) != artifact_bound.get("size_bytes"):
                raise HostileTwinExecutionError("artifact-bound receipt bytes mismatch")
            if _sha256(content_receipt_bytes) != content_bound.get("content_bound_receipt_sha256") or len(content_receipt_bytes) != content_bound.get("content_bound_receipt_size_bytes"):
                raise HostileTwinExecutionError("content-bound receipt bytes mismatch")
            expected_members = {
                "RELEASE_CANDIDATE_BUNDLE.json",
                artifact_filename,
                artifact_ref,
                content_ref,
            }
            if set(names) != expected_members:
                raise HostileTwinExecutionError("outer release bundle contains undeclared members")

        return cls(
            outer_sha256=outer_sha,
            artifact_filename=artifact_filename,
            archive_bytes=archive_bytes,
            archive_policy=policy,
            archive_receipt=observed_receipt,
            release_identity=release,
            portable_release_digest=portable_digest,
            artifact_bound_receipt_sha256=_sha256(artifact_receipt_bytes),
            content_bound_receipt_sha256=_sha256(content_receipt_bytes),
        )


@dataclass(frozen=True, slots=True)
class HostileTwinExecutionReceipt:
    schema: str
    attempt_id: str
    operation: str
    outcome: str
    outer_bundle_sha256: str
    artifact_sha256: str
    manifest_sha256: str
    target_release_digest: str
    observed_generation: int | None
    observed_state_sha256: str | None
    observed_active_release_digest: str | None
    transaction_plan_digest: str
    release_readback_receipt_digest: str
    failure_code: str | None
    twin_root_fingerprint: str
    execution_scope: str = EXECUTION_SCOPE
    target_runtime_credit: int = 0
    physical_host_credit: int = 0
    effect_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def digest(self) -> str:
        return _sha256(_canonical_bytes(self.as_dict()))


class ScratchHostileTwin:
    """Real filesystem executor confined to one caller-chosen scratch root.

    Canonical twin state is a single atomic pointer to one immutable snapshot directory.
    An interrupted write may leave an orphan staging/snapshot directory, but cannot partially
    change the canonical state because ``control/current.json`` is the only activation point.
    """

    CURRENT_SCHEMA = "FRANKENSTEIN2_HOSTILE_TWIN_CURRENT_SNAPSHOT/v1"

    def __init__(self, twin_root: str | Path):
        raw = Path(twin_root)
        if raw.exists() or raw.is_symlink():
            if raw.is_symlink() or not raw.is_dir():
                raise HostileTwinExecutionError("twin root must be a plain directory")
        else:
            raw.mkdir(parents=True, mode=0o700)
        self.root = raw.resolve(strict=True)
        _ensure_plain_dir(self.root)
        self.releases = self.root / "releases"
        self.staging = self.root / "staging"
        self.control = self.root / "control"
        self.snapshots = self.root / "snapshots"
        self.cache = self.root / "cache"
        for path in (self.releases, self.staging, self.control, self.snapshots, self.cache):
            if not path.exists():
                path.mkdir(mode=0o700)
            _ensure_plain_dir(path)
        self.current_path = self.control / "current.json"
        self.cache_current_path = self.cache / "current.json"

    def _fingerprint(self) -> str:
        payload = {
            "root_name": self.root.name,
            "layout": ["cache", "control", "releases", "snapshots", "staging"],
        }
        return _sha256(_canonical_bytes(payload))

    def _load_current_pointer(self) -> dict[str, Any] | None:
        if not (self.current_path.exists() or self.current_path.is_symlink()):
            return None
        pointer = _json_file(self.current_path)
        if pointer.get("schema") != self.CURRENT_SCHEMA:
            raise HostileTwinExecutionError("current snapshot pointer schema mismatch")
        snapshot_id = _safe_name(pointer.get("snapshot_id"), field="snapshot_id")
        if pointer.get("snapshot_sha256") is None:
            raise HostileTwinExecutionError("current snapshot pointer digest missing")
        if self.cache_current_path.exists() or self.cache_current_path.is_symlink():
            cached = _json_file(self.cache_current_path)
            if cached != pointer:
                raise HostileTwinExecutionError("stale current-snapshot cache disagrees with canonical pointer")
        return pointer

    def _current(self) -> tuple[StateLineage | None, dict[str, Any] | None]:
        pointer = self._load_current_pointer()
        if pointer is None:
            return None, None
        snapshot_id = pointer["snapshot_id"]
        snapshot = self.snapshots / snapshot_id
        if snapshot.is_symlink() or not snapshot.is_dir():
            raise HostileTwinExecutionError("current snapshot directory missing or unsafe")
        lineage_raw = _json_file(snapshot / "lineage.json")
        active = _json_file(snapshot / "active-release.json")
        state_path = snapshot / "canonical-state.bin"
        if state_path.is_symlink() or not state_path.is_file():
            raise HostileTwinExecutionError("canonical state file missing or unsafe")
        snapshot_subject = {
            "lineage": lineage_raw,
            "active_release": active,
            "canonical_state_sha256": _sha256(state_path.read_bytes()),
        }
        if _sha256(_canonical_bytes(snapshot_subject)) != pointer.get("snapshot_sha256"):
            raise HostileTwinExecutionError("current snapshot digest mismatch")
        lineage = StateLineage.from_mapping(lineage_raw)
        if active.get("schema") != ACTIVE_SCHEMA:
            raise HostileTwinExecutionError("active release schema mismatch")
        release_raw = active.get("release")
        if not isinstance(release_raw, dict):
            raise HostileTwinExecutionError("active release identity missing")
        release = ReleaseIdentity.from_mapping(release_raw)
        if active.get("release_digest") != release.digest():
            raise HostileTwinExecutionError("active release digest mapping mismatch")
        if release.digest() != lineage.active_release_digest:
            raise HostileTwinExecutionError("active release and lineage disagree")
        if snapshot_subject["canonical_state_sha256"] != lineage.state_sha256:
            raise HostileTwinExecutionError("canonical state bytes disagree with lineage")
        release_dir = self.releases / release.digest()
        if release_dir.is_symlink() or not release_dir.is_dir():
            raise HostileTwinExecutionError("active release directory missing or unsafe")
        manifest = release_dir / "manifest" / "release-manifest.json"
        if manifest.is_symlink() or not manifest.is_file() or _sha256(manifest.read_bytes()) != release.manifest_sha256:
            raise HostileTwinExecutionError("active release manifest readback mismatch")
        return lineage, active

    def readback(self) -> StateLineage | None:
        lineage, _ = self._current()
        return lineage

    def _verify_request_current(self, request: TransactionRequest) -> StateLineage | None:
        current, _ = self._current()
        if request.current_lineage is None:
            if current is not None:
                raise HostileTwinExecutionError("request claims empty lineage but twin is already installed")
            return None
        if current is None or current.as_dict() != request.current_lineage.as_dict():
            raise HostileTwinExecutionError("request current lineage does not match exact twin readback")
        return current

    def _extract_candidate(self, candidate: BoundReleaseCandidate, attempt_id: str) -> Path:
        stage = self.staging / _safe_name(attempt_id, field="attempt_id")
        if stage.exists() or stage.is_symlink():
            raise HostileTwinExecutionError("stale attempt staging directory already exists")
        stage.mkdir(mode=0o700)
        try:
            import io
            with zipfile.ZipFile(io.BytesIO(candidate.archive_bytes), "r") as zf:
                for info in zf.infolist():
                    rel = PurePosixPath(info.filename)
                    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
                        raise HostileTwinExecutionError("unsafe archive member during extraction")
                    target = stage.joinpath(*rel.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    cur = stage
                    for part in rel.parts[:-1]:
                        cur = cur / part
                        if cur.is_symlink() or not cur.is_dir():
                            raise HostileTwinExecutionError("unsafe extraction ancestor")
                    if target.exists() or target.is_symlink():
                        raise HostileTwinExecutionError("duplicate extraction target")
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                    if hasattr(os, "O_NOFOLLOW"):
                        flags |= os.O_NOFOLLOW
                    mode = stat.S_IMODE(info.external_attr >> 16) & 0o777
                    fd = os.open(target, flags, mode)
                    with os.fdopen(fd, "wb") as f:
                        f.write(zf.read(info.filename))
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        manifest = stage / candidate.archive_receipt.manifest_path
        if manifest.is_symlink() or not manifest.is_file() or _sha256(manifest.read_bytes()) != candidate.release_identity.manifest_sha256:
            shutil.rmtree(stage, ignore_errors=True)
            raise HostileTwinExecutionError("extracted release manifest does not match bound candidate")
        return stage

    def _activate_release_payload(self, candidate: BoundReleaseCandidate, stage: Path | None) -> None:
        release_dir = self.releases / candidate.portable_release_digest
        if release_dir.exists() or release_dir.is_symlink():
            if release_dir.is_symlink() or not release_dir.is_dir():
                raise HostileTwinExecutionError("existing release destination is unsafe")
            manifest = release_dir / candidate.archive_receipt.manifest_path
            if manifest.is_symlink() or not manifest.is_file() or _sha256(manifest.read_bytes()) != candidate.release_identity.manifest_sha256:
                raise HostileTwinExecutionError("pre-existing/partial release destination conflicts with candidate")
            if stage is not None:
                shutil.rmtree(stage)
        else:
            if stage is None:
                raise HostileTwinExecutionError("rollback target release is not already installed")
            os.replace(stage, release_dir)

    def _write_snapshot(
        self,
        *,
        attempt_id: str,
        lineage: StateLineage,
        active: Mapping[str, Any],
        canonical_state_bytes: bytes,
    ) -> None:
        subject = {
            "lineage": lineage.as_dict(),
            "active_release": dict(active),
            "canonical_state_sha256": _sha256(canonical_state_bytes),
        }
        snapshot_sha = _sha256(_canonical_bytes(subject))
        snapshot_id = f"g{lineage.generation}-{snapshot_sha[:24]}"
        final = self.snapshots / snapshot_id
        tmp = self.snapshots / f"tmp-{_safe_name(attempt_id, field='attempt_id')}"
        if tmp.exists() or tmp.is_symlink():
            raise HostileTwinExecutionError("stale snapshot staging directory")
        if final.exists() or final.is_symlink():
            if final.is_symlink() or not final.is_dir():
                raise HostileTwinExecutionError("existing snapshot identity is unsafe")
            existing_subject = {
                "lineage": _json_file(final / "lineage.json"),
                "active_release": _json_file(final / "active-release.json"),
                "canonical_state_sha256": _sha256((final / "canonical-state.bin").read_bytes()),
            }
            if _sha256(_canonical_bytes(existing_subject)) != snapshot_sha:
                raise HostileTwinExecutionError("existing snapshot identity collision")
        else:
            tmp.mkdir(mode=0o700)
            try:
                (tmp / "lineage.json").write_bytes(_canonical_bytes(lineage.as_dict()))
                (tmp / "active-release.json").write_bytes(_canonical_bytes(active))
                (tmp / "canonical-state.bin").write_bytes(canonical_state_bytes)
                os.replace(tmp, final)
            except Exception:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
        pointer = {
            "schema": self.CURRENT_SCHEMA,
            "snapshot_id": snapshot_id,
            "snapshot_sha256": snapshot_sha,
        }
        _write_atomic_json(self.current_path, pointer)
        _write_atomic_json(self.cache_current_path, pointer)

    def execute(
        self,
        raw_request: Mapping[str, Any],
        *,
        candidate: BoundReleaseCandidate,
        canonical_state_bytes: bytes,
    ) -> HostileTwinExecutionReceipt:
        if not isinstance(canonical_state_bytes, bytes):
            raise HostileTwinExecutionError("canonical_state_bytes must be bytes")
        request = TransactionRequest.from_mapping(raw_request)
        if request.target_release.as_dict() != candidate.release_identity.as_dict():
            raise HostileTwinExecutionError("request target release is not the bound candidate")
        plan = build_transaction_plan(request.as_dict())
        current = self._verify_request_current(request)
        state_sha = _sha256(canonical_state_bytes)
        if current is not None and current.state_sha256 != state_sha:
            raise HostileTwinExecutionError("caller state bytes do not match current durable lineage")

        stage: Path | None = None
        existing_release = self.releases / candidate.portable_release_digest
        if request.operation != "ROLLBACK" or not existing_release.is_dir():
            stage = self._extract_candidate(candidate, request.attempt_id)

        if request.injected_failure_stage is not None:
            if request.injected_failure_stage != FAIL_AFTER_EXTRACT:
                if stage is not None:
                    shutil.rmtree(stage, ignore_errors=True)
                raise HostileTwinExecutionError("unsupported injected failure stage")
            if stage is not None:
                shutil.rmtree(stage, ignore_errors=True)
            if current is None:
                outcome = "FAILED_NO_MUTATION"
                observed_generation = None
                observed_state = None
                observed_release = None
            else:
                outcome = "ROLLED_BACK"
                observed_generation = current.generation
                observed_state = current.state_sha256
                observed_release = current.active_release_digest
            failure_code = "INJECTED_AFTER_EXTRACT_BEFORE_ACTIVATE"
            readback = record_release_readback(
                request.as_dict(),
                outcome=outcome,
                observed_generation=observed_generation,
                observed_state_sha256=observed_state,
                observed_active_release_digest=observed_release,
                failure_code=failure_code,
            )
            return self._receipt(candidate, plan.digest(), readback)

        try:
            self._activate_release_payload(candidate, stage)
            stage = None
        except Exception:
            if stage is not None:
                shutil.rmtree(stage, ignore_errors=True)
            raise

        next_lineage = StateLineage(
            schema=LINEAGE_SCHEMA,
            generation=plan.next_generation,
            state_sha256=state_sha,
            active_release_digest=candidate.portable_release_digest,
            predecessor_generation=None if current is None else current.generation,
            predecessor_state_sha256=None if current is None else current.state_sha256,
            predecessor_release_digest=None if current is None else current.active_release_digest,
        )
        active = {
            "schema": ACTIVE_SCHEMA,
            "release": candidate.release_identity.as_dict(),
            "release_digest": candidate.portable_release_digest,
            "outer_bundle_sha256": candidate.outer_sha256,
            "artifact_bound_receipt_sha256": candidate.artifact_bound_receipt_sha256,
            "content_bound_receipt_sha256": candidate.content_bound_receipt_sha256,
        }
        self._write_snapshot(
            attempt_id=request.attempt_id,
            lineage=next_lineage,
            active=active,
            canonical_state_bytes=canonical_state_bytes,
        )
        observed = self.readback()
        assert observed is not None
        readback = record_release_readback(
            request.as_dict(),
            outcome="SUCCEEDED",
            observed_generation=observed.generation,
            observed_state_sha256=observed.state_sha256,
            observed_active_release_digest=observed.active_release_digest,
        )
        return self._receipt(candidate, plan.digest(), readback)

    def _receipt(
        self,
        candidate: BoundReleaseCandidate,
        plan_digest: str,
        readback: ReleaseReadbackReceipt,
    ) -> HostileTwinExecutionReceipt:
        return HostileTwinExecutionReceipt(
            schema=EXECUTION_RECEIPT_SCHEMA,
            attempt_id=readback.attempt_id,
            operation=readback.operation,
            outcome=readback.outcome,
            outer_bundle_sha256=candidate.outer_sha256,
            artifact_sha256=candidate.release_identity.artifact_sha256,
            manifest_sha256=candidate.release_identity.manifest_sha256,
            target_release_digest=candidate.portable_release_digest,
            observed_generation=readback.observed_generation,
            observed_state_sha256=readback.observed_state_sha256,
            observed_active_release_digest=readback.observed_active_release_digest,
            transaction_plan_digest=plan_digest,
            release_readback_receipt_digest=readback.digest(),
            failure_code=readback.failure_code,
            twin_root_fingerprint=self._fingerprint(),
        )

def request_for_install(*, attempt_id: str, release: ReleaseIdentity) -> dict[str, Any]:
    return {
        "schema": REQUEST_SCHEMA,
        "attempt_id": attempt_id,
        "operation": "INSTALL",
        "target_release": release.as_dict(),
        "current_lineage": None,
        "expected_generation": None,
        "expected_state_sha256": None,
        "rollback_release": None,
        "injected_failure_stage": None,
    }


def request_for_update(
    *, attempt_id: str, release: ReleaseIdentity, current: StateLineage, injected_failure_stage: str | None = None
) -> dict[str, Any]:
    return {
        "schema": REQUEST_SCHEMA,
        "attempt_id": attempt_id,
        "operation": "UPDATE",
        "target_release": release.as_dict(),
        "current_lineage": current.as_dict(),
        "expected_generation": current.generation,
        "expected_state_sha256": current.state_sha256,
        "rollback_release": None,
        "injected_failure_stage": injected_failure_stage,
    }


def request_for_rollback(
    *, attempt_id: str, release: ReleaseIdentity, current: StateLineage
) -> dict[str, Any]:
    return {
        "schema": REQUEST_SCHEMA,
        "attempt_id": attempt_id,
        "operation": "ROLLBACK",
        "target_release": release.as_dict(),
        "current_lineage": current.as_dict(),
        "expected_generation": current.generation,
        "expected_state_sha256": current.state_sha256,
        "rollback_release": release.as_dict(),
        "injected_failure_stage": None,
    }
