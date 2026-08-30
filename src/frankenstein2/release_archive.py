"""Deterministic release-candidate ZIP construction and verification.

F2-WP-1107 generation 3 preserves the generation-2 deterministic archive contract and
closes the exact archive-byte perimeter around the classic ZIP end-of-central-directory
(EOCD). Ambient filesystem metadata is excluded from archive identity: member order,
timestamp, POSIX mode, ZIP version, compression, comments and extra fields are explicit
policy. V1 forbids ZIP64 and non-ASCII member names so the builder cannot emit a container
that its verifier rejects or whose filename flags depend on runtime encoding paths.
The embedded accepted WP1107 manifest remains the payload-integrity authority.

REPRODUCIBLE_ARCHIVE_COMPONENT != INSTALLATION != TARGET_RUNTIME != COMPLETION
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Mapping, Sequence
import zipfile

from .release_integrity import DEFAULT_MANIFEST_PATH, ReleaseIntegrityError, ReleaseManifest, build_release_manifest

ARCHIVE_POLICY_SCHEMA = "FRANKENSTEIN2_RELEASE_ARCHIVE_POLICY/v1"
ARCHIVE_RECEIPT_SCHEMA = "FRANKENSTEIN2_RELEASE_ARCHIVE_RECEIPT/v1"
ARCHIVE_COMPONENT_SCOPE = "DETERMINISTIC_RELEASE_ZIP_REPOSITORY_COMPONENT_ONLY_NO_INSTALL_RUNTIME_OR_COMPLETION_CREDIT"
DEFAULT_POLICY_ID = "f2-release-zip-stored-posix-v1"
_MIN_ZIP_EPOCH = 315532800
_MAX_ZIP_EPOCH = 4354819198
_REGULAR_TYPE = stat.S_IFREG
_ZIP20 = 20
_MAX_CLASSIC_ZIP_MEMBERS = 65535
_EOCD_SIGNATURE = b"PK\x05\x06"
_EOCD_FIXED_SIZE = 22


class ReleaseArchiveError(ValueError):
    """Deterministic release-archive invariant violation."""


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ReleaseArchiveError(f"{name} must be a non-empty already-trimmed string")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ReleaseArchiveError(f"{name} contains control characters")
    return value


def _digest(value: Any, name: str) -> str:
    value = _text(value, name)
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ReleaseArchiveError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _relpath(value: Any) -> str:
    value = _text(value, "archive path")
    if "\\" in value or "\x00" in value:
        raise ReleaseArchiveError(f"non-canonical archive path: {value!r}")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ReleaseArchiveError("generation-2 archive paths must be ASCII") from exc
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(p in {"", ".", ".."} for p in path.parts):
        raise ReleaseArchiveError(f"unsafe archive path: {value!r}")
    if path.as_posix() != value:
        raise ReleaseArchiveError(f"archive path must already be canonical POSIX: {value!r}")
    return value


def _zip_datetime(epoch: int) -> tuple[int, int, int, int, int, int]:
    if isinstance(epoch, bool) or not isinstance(epoch, int):
        raise ReleaseArchiveError("source_date_epoch must be an integer")
    epoch = max(_MIN_ZIP_EPOCH, min(_MAX_ZIP_EPOCH, epoch))
    epoch -= epoch % 2
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)


@dataclass(frozen=True, slots=True)
class ReleaseArchivePolicy:
    policy_id: str
    source_date_epoch: int
    executable_paths: tuple[str, ...] = ()
    regular_mode: int = 0o644
    executable_mode: int = 0o755
    create_system: int = 3
    create_version: int = _ZIP20
    extract_version: int = _ZIP20
    compression: int = zipfile.ZIP_STORED
    schema: str = ARCHIVE_POLICY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != ARCHIVE_POLICY_SCHEMA:
            raise ReleaseArchiveError("archive policy schema mismatch")
        _text(self.policy_id, "policy_id")
        _zip_datetime(self.source_date_epoch)
        paths = tuple(_relpath(path) for path in self.executable_paths)
        if tuple(sorted(paths)) != paths or len(set(paths)) != len(paths):
            raise ReleaseArchiveError("executable_paths must be unique and sorted")
        object.__setattr__(self, "executable_paths", paths)
        for name, mode in (("regular_mode", self.regular_mode), ("executable_mode", self.executable_mode)):
            if isinstance(mode, bool) or not isinstance(mode, int) or not 0 <= mode <= 0o777:
                raise ReleaseArchiveError(f"{name} must be a permission mode in 000..777")
        if self.create_system != 3:
            raise ReleaseArchiveError("generation-2 policy requires POSIX create_system=3")
        if self.create_version != _ZIP20 or self.extract_version != _ZIP20:
            raise ReleaseArchiveError("generation-2 policy requires explicit classic ZIP version 2.0")
        if self.compression != zipfile.ZIP_STORED:
            raise ReleaseArchiveError("generation-2 policy requires ZIP_STORED")

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "policy_id": self.policy_id, "source_date_epoch": self.source_date_epoch, "zip_datetime": list(_zip_datetime(self.source_date_epoch)), "executable_paths": list(self.executable_paths), "regular_mode": self.regular_mode, "executable_mode": self.executable_mode, "create_system": self.create_system, "create_version": self.create_version, "extract_version": self.extract_version, "compression": self.compression, "filename_encoding": "ASCII_ONLY", "zip64": False, "member_comment": "", "member_extra": "", "archive_comment": "", "directory_entries": False}

    def digest(self) -> str:
        return _sha256(_json_bytes(self.as_dict()))


@dataclass(frozen=True, slots=True)
class ReleaseArchiveReceipt:
    release_id: str
    source_commit: str
    source_tree: str
    build_id: str
    archive_policy_id: str
    archive_policy_sha256: str
    manifest_path: str
    manifest_sha256: str
    archive_sha256: str
    archive_size: int
    member_count: int
    evidence_scope: str = ARCHIVE_COMPONENT_SCOPE
    schema: str = ARCHIVE_RECEIPT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != ARCHIVE_RECEIPT_SCHEMA:
            raise ReleaseArchiveError("archive receipt schema mismatch")
        for name in ("release_id", "source_commit", "source_tree", "build_id", "archive_policy_id"):
            _text(getattr(self, name), name)
        _relpath(self.manifest_path)
        _digest(self.archive_policy_sha256, "archive_policy_sha256")
        _digest(self.manifest_sha256, "manifest_sha256")
        _digest(self.archive_sha256, "archive_sha256")
        if isinstance(self.archive_size, bool) or not isinstance(self.archive_size, int) or self.archive_size < 0:
            raise ReleaseArchiveError("archive_size must be a non-negative integer")
        if isinstance(self.member_count, bool) or not isinstance(self.member_count, int) or self.member_count < 1:
            raise ReleaseArchiveError("member_count must be a positive integer")
        if self.evidence_scope != ARCHIVE_COMPONENT_SCOPE:
            raise ReleaseArchiveError("archive receipt evidence scope mismatch")

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "release_id": self.release_id, "source_commit": self.source_commit, "source_tree": self.source_tree, "build_id": self.build_id, "archive_policy_id": self.archive_policy_id, "archive_policy_sha256": self.archive_policy_sha256, "manifest_path": self.manifest_path, "manifest_sha256": self.manifest_sha256, "archive_sha256": self.archive_sha256, "archive_size": self.archive_size, "member_count": self.member_count, "evidence_scope": self.evidence_scope}

    def canonical_bytes(self) -> bytes:
        return _json_bytes(self.as_dict())

    def digest(self) -> str:
        return _sha256(self.canonical_bytes())


@dataclass(frozen=True, slots=True)
class ReleaseArchiveBuild:
    archive_bytes: bytes
    manifest: ReleaseManifest
    receipt: ReleaseArchiveReceipt


def _mode(path: str, policy: ReleaseArchivePolicy) -> int:
    return policy.executable_mode if path in policy.executable_paths else policy.regular_mode


def _zip_info(path: str, policy: ReleaseArchivePolicy) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, date_time=_zip_datetime(policy.source_date_epoch))
    info.create_system = policy.create_system
    info.create_version = policy.create_version
    info.extract_version = policy.extract_version
    info.compress_type = policy.compression
    info.flag_bits = 0
    info.internal_attr = 0
    info.external_attr = ((_REGULAR_TYPE | _mode(path, policy)) & 0xFFFF) << 16
    info.extra = b""
    info.comment = b""
    return info


def _read_bound_payload(root: Path, manifest: ReleaseManifest) -> dict[str, bytes]:
    payload: dict[str, bytes] = {}
    for entry in manifest.files:
        path = _relpath(entry.path)
        candidate = root.joinpath(*PurePosixPath(path).parts)
        if candidate.is_symlink() or not candidate.is_file():
            raise ReleaseArchiveError(f"manifest member is not regular non-symlink: {path}")
        data = candidate.read_bytes()
        if len(data) != entry.size or _sha256(data) != entry.sha256:
            raise ReleaseArchiveError(f"payload mutated after manifest construction: {path}")
        payload[path] = data
    return payload


def build_release_archive(package_root: str | Path, *, release_id: str, source_commit: str, source_tree: str, build_id: str, policy: ReleaseArchivePolicy, prehandoff_receipt_refs: Sequence[str] = (), manifest_path: str = DEFAULT_MANIFEST_PATH) -> ReleaseArchiveBuild:
    root = Path(package_root).resolve(strict=True)
    manifest_path = _relpath(manifest_path)
    if manifest_path in policy.executable_paths:
        raise ReleaseArchiveError("embedded manifest cannot be executable")
    manifest = build_release_manifest(root, release_id=release_id, source_commit=source_commit, source_tree=source_tree, build_id=build_id, prehandoff_receipt_refs=prehandoff_receipt_refs, manifest_path=manifest_path)
    payload = _read_bound_payload(root, manifest)
    unknown_exec = sorted(set(policy.executable_paths) - set(payload))
    if unknown_exec:
        raise ReleaseArchiveError(f"executable policy references absent payload: {unknown_exec}")
    members = dict(payload)
    members[manifest_path] = manifest.canonical_bytes()
    if len(members) > _MAX_CLASSIC_ZIP_MEMBERS:
        raise ReleaseArchiveError("archive member count requires forbidden ZIP64")
    stream = io.BytesIO()
    try:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
            archive.comment = b""
            for path in sorted(members):
                archive.writestr(_zip_info(path, policy), members[path])
    except zipfile.LargeZipFile as exc:
        raise ReleaseArchiveError("archive size/offset requires forbidden ZIP64") from exc
    archive_bytes = stream.getvalue()
    receipt = ReleaseArchiveReceipt(release_id=manifest.release_id, source_commit=manifest.source_commit, source_tree=manifest.source_tree, build_id=manifest.build_id, archive_policy_id=policy.policy_id, archive_policy_sha256=policy.digest(), manifest_path=manifest_path, manifest_sha256=manifest.sha256(), archive_sha256=_sha256(archive_bytes), archive_size=len(archive_bytes), member_count=len(members))
    return ReleaseArchiveBuild(archive_bytes, manifest, receipt)


def write_release_archive(destination: str | Path, build: ReleaseArchiveBuild) -> Path:
    if not isinstance(build, ReleaseArchiveBuild):
        raise ReleaseArchiveError("build must be ReleaseArchiveBuild")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(build.archive_bytes)
    return destination


def _expected_attr(path: str, policy: ReleaseArchivePolicy) -> int:
    return ((_REGULAR_TYPE | _mode(path, policy)) & 0xFFFF) << 16


def _require_exact_classic_eocd_tail(archive_bytes: bytes) -> None:
    """Reject bytes outside the canonical classic-ZIP EOCD perimeter.

    Generation 2 already forbids archive comments, ZIP64 and multi-disk archives. Under that
    policy the EOCD is exactly the final 22 bytes, and the central directory must terminate
    immediately before it. Python's ``zipfile`` intentionally tolerates concatenated/trailing
    bytes, so this boundary must be checked explicitly before ordinary ZIP parsing.
    """
    if len(archive_bytes) < _EOCD_FIXED_SIZE:
        raise ReleaseArchiveError("invalid release ZIP: missing canonical EOCD")
    eocd_offset = len(archive_bytes) - _EOCD_FIXED_SIZE
    eocd = archive_bytes[eocd_offset:]
    if eocd[:4] != _EOCD_SIGNATURE:
        raise ReleaseArchiveError("invalid release ZIP: trailing/unbound bytes after canonical EOCD")

    disk_number = int.from_bytes(eocd[4:6], "little")
    central_directory_disk = int.from_bytes(eocd[6:8], "little")
    entries_on_disk = int.from_bytes(eocd[8:10], "little")
    entries_total = int.from_bytes(eocd[10:12], "little")
    central_directory_size = int.from_bytes(eocd[12:16], "little")
    central_directory_offset = int.from_bytes(eocd[16:20], "little")
    comment_length = int.from_bytes(eocd[20:22], "little")

    if comment_length != 0:
        raise ReleaseArchiveError("archive comment must be empty")
    if disk_number != 0 or central_directory_disk != 0 or entries_on_disk != entries_total:
        raise ReleaseArchiveError("multi-disk release ZIP is forbidden")
    if entries_total > _MAX_CLASSIC_ZIP_MEMBERS:
        raise ReleaseArchiveError("archive member count requires forbidden ZIP64")
    if central_directory_offset + central_directory_size != eocd_offset:
        raise ReleaseArchiveError("invalid release ZIP: central directory does not terminate at canonical EOCD")


def verify_release_archive(archive_bytes: bytes, *, policy: ReleaseArchivePolicy, expected_receipt: ReleaseArchiveReceipt | None = None, manifest_path: str = DEFAULT_MANIFEST_PATH) -> ReleaseArchiveReceipt:
    if not isinstance(archive_bytes, bytes) or not archive_bytes:
        raise ReleaseArchiveError("archive_bytes must be non-empty bytes")
    _require_exact_classic_eocd_tail(archive_bytes)
    manifest_path = _relpath(manifest_path)
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes), "r", allowZip64=False)
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ReleaseArchiveError("invalid release ZIP or forbidden ZIP64") from exc
    with archive:
        if archive.comment:
            raise ReleaseArchiveError("archive comment must be empty")
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(infos) > _MAX_CLASSIC_ZIP_MEMBERS:
            raise ReleaseArchiveError("archive member count requires forbidden ZIP64")
        if len(set(names)) != len(names):
            raise ReleaseArchiveError("duplicate archive member")
        if names != sorted(names) or [_relpath(name) for name in names] != names:
            raise ReleaseArchiveError("archive members must be canonical sorted ASCII POSIX paths")
        if manifest_path not in names:
            raise ReleaseArchiveError("embedded canonical release manifest missing")
        expected_dt = _zip_datetime(policy.source_date_epoch)
        for info in infos:
            if info.is_dir() or info.filename.endswith("/"):
                raise ReleaseArchiveError("directory entries are forbidden")
            if info.compress_type != policy.compression:
                raise ReleaseArchiveError(f"unexpected compression for {info.filename}")
            if info.date_time != expected_dt:
                raise ReleaseArchiveError(f"unexpected timestamp for {info.filename}")
            if info.create_system != policy.create_system or info.create_version != policy.create_version or info.extract_version != policy.extract_version:
                raise ReleaseArchiveError(f"unexpected ZIP system/version fields for {info.filename}")
            if info.flag_bits != 0:
                raise ReleaseArchiveError(f"unexpected ZIP flag bits for {info.filename}")
            if info.external_attr != _expected_attr(info.filename, policy):
                raise ReleaseArchiveError(f"unexpected file mode for {info.filename}")
            if info.comment or info.extra:
                raise ReleaseArchiveError(f"comment/extra metadata forbidden for {info.filename}")
        manifest_raw = archive.read(manifest_path)
        try:
            manifest = ReleaseManifest.from_bytes(manifest_raw)
        except ReleaseIntegrityError as exc:
            raise ReleaseArchiveError("embedded manifest is invalid") from exc
        if manifest_raw != manifest.canonical_bytes():
            raise ReleaseArchiveError("embedded manifest is not canonical byte form")
        expected_names = sorted([_relpath(entry.path) for entry in manifest.files] + [manifest_path])
        if names != expected_names:
            missing = sorted(set(expected_names) - set(names))
            extra = sorted(set(names) - set(expected_names))
            raise ReleaseArchiveError(f"archive member mismatch; missing={missing}, extra={extra}")
        for entry in manifest.files:
            data = archive.read(entry.path)
            if len(data) != entry.size or _sha256(data) != entry.sha256:
                raise ReleaseArchiveError(f"archive payload mismatch: {entry.path}")
    unknown_exec = sorted(set(policy.executable_paths) - {entry.path for entry in manifest.files})
    if unknown_exec:
        raise ReleaseArchiveError(f"executable policy references absent payload: {unknown_exec}")
    observed = ReleaseArchiveReceipt(release_id=manifest.release_id, source_commit=manifest.source_commit, source_tree=manifest.source_tree, build_id=manifest.build_id, archive_policy_id=policy.policy_id, archive_policy_sha256=policy.digest(), manifest_path=manifest_path, manifest_sha256=manifest.sha256(), archive_sha256=_sha256(archive_bytes), archive_size=len(archive_bytes), member_count=len(names))
    if expected_receipt is not None and observed != expected_receipt:
        raise ReleaseArchiveError("archive receipt identity mismatch")
    return observed
