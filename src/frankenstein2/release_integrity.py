from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

RELEASE_MANIFEST_SCHEMA = "FRANKENSTEIN2_RELEASE_MANIFEST/v1"
DEFAULT_MANIFEST_PATH = "manifest/release-manifest.json"


class ReleaseIntegrityError(ValueError):
    """Release payload or manifest violates a deterministic integrity invariant."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_relpath(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReleaseIntegrityError("release path must be a non-empty string")
    if "\x00" in value or "\\" in value:
        raise ReleaseIntegrityError(f"non-canonical release path: {value!r}")
    candidate = PurePosixPath(value)
    if candidate.is_absolute():
        raise ReleaseIntegrityError(f"absolute release path forbidden: {value!r}")
    parts = candidate.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ReleaseIntegrityError(
            f"path traversal/non-canonical segment forbidden: {value!r}"
        )
    normalized = candidate.as_posix()
    if normalized != value:
        raise ReleaseIntegrityError(
            f"path must already be canonical POSIX form: {value!r}"
        )
    return normalized


def _require_sha256(value: str, field_name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ReleaseIntegrityError(
            f"{field_name} must be a 64-character SHA-256 hex digest"
        )
    try:
        int(value, 16)
    except ValueError as exc:
        raise ReleaseIntegrityError(f"{field_name} must be hexadecimal") from exc
    return value.lower()


def _require_nonempty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseIntegrityError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True, order=True)
class ReleaseFileEntry:
    path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _canonical_relpath(self.path))
        object.__setattr__(self, "sha256", _require_sha256(self.sha256, "file sha256"))
        if isinstance(self.size, bool) or not isinstance(self.size, int) or self.size < 0:
            raise ReleaseIntegrityError("file size must be a non-negative integer")

    def as_dict(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True)
class ReleaseManifest:
    release_id: str
    source_commit: str
    source_tree: str
    build_id: str
    prehandoff_receipt_refs: tuple[str, ...]
    files: tuple[ReleaseFileEntry, ...]
    schema: str = RELEASE_MANIFEST_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != RELEASE_MANIFEST_SCHEMA:
            raise ReleaseIntegrityError(
                f"unsupported release manifest schema: {self.schema!r}"
            )
        _require_nonempty(self.release_id, "release_id")
        _require_nonempty(self.source_commit, "source_commit")
        _require_nonempty(self.source_tree, "source_tree")
        _require_nonempty(self.build_id, "build_id")
        refs = tuple(self.prehandoff_receipt_refs)
        if tuple(sorted(refs)) != refs or len(set(refs)) != len(refs):
            raise ReleaseIntegrityError(
                "pre-handoff receipt refs must be unique and sorted"
            )
        for ref in refs:
            _require_nonempty(ref, "pre-handoff receipt ref")
        entries = tuple(self.files)
        if tuple(sorted(entries, key=lambda item: item.path)) != entries:
            raise ReleaseIntegrityError("file entries must be sorted by canonical path")
        paths = [item.path for item in entries]
        if len(set(paths)) != len(paths):
            raise ReleaseIntegrityError("duplicate release file path")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "release_id": self.release_id,
            "source_commit": self.source_commit,
            "source_tree": self.source_tree,
            "build_id": self.build_id,
            "prehandoff_receipt_refs": list(self.prehandoff_receipt_refs),
            "files": [entry.as_dict() for entry in self.files],
        }

    def canonical_bytes(self) -> bytes:
        return (
            json.dumps(
                self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            + "\n"
        ).encode("utf-8")

    def sha256(self) -> str:
        return _sha256_bytes(self.canonical_bytes())

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "ReleaseManifest":
        allowed = {
            "schema",
            "release_id",
            "source_commit",
            "source_tree",
            "build_id",
            "prehandoff_receipt_refs",
            "files",
        }
        if set(raw) != allowed:
            missing = sorted(allowed - set(raw))
            extra = sorted(set(raw) - allowed)
            raise ReleaseIntegrityError(
                f"manifest keys mismatch; missing={missing}, extra={extra}"
            )
        raw_files = raw["files"]
        raw_refs = raw["prehandoff_receipt_refs"]
        if not isinstance(raw_files, list) or not isinstance(raw_refs, list):
            raise ReleaseIntegrityError(
                "files and prehandoff_receipt_refs must be arrays"
            )
        entries: list[ReleaseFileEntry] = []
        for item in raw_files:
            if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
                raise ReleaseIntegrityError(
                    "each file entry must contain exactly path, sha256, size"
                )
            entries.append(
                ReleaseFileEntry(
                    path=item["path"],
                    sha256=item["sha256"],
                    size=item["size"],
                )
            )
        return cls(
            schema=raw["schema"],
            release_id=raw["release_id"],
            source_commit=raw["source_commit"],
            source_tree=raw["source_tree"],
            build_id=raw["build_id"],
            prehandoff_receipt_refs=tuple(raw_refs),
            files=tuple(entries),
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "ReleaseManifest":
        try:
            raw = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReleaseIntegrityError(
                "release manifest is not valid UTF-8 JSON"
            ) from exc
        if not isinstance(raw, dict):
            raise ReleaseIntegrityError("release manifest root must be an object")
        return cls.from_mapping(raw)


def _iter_regular_files(
    package_root: Path, *, exclude_paths: frozenset[str]
) -> tuple[ReleaseFileEntry, ...]:
    root = package_root.resolve(strict=True)
    if not root.is_dir():
        raise ReleaseIntegrityError("package root must be a directory")

    entries: list[ReleaseFileEntry] = []
    seen_paths: set[str] = set()
    for current_root, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current = Path(current_root)

        for dirname in list(dirs):
            candidate = current / dirname
            if candidate.is_symlink():
                raise ReleaseIntegrityError(
                    f"symlink directory forbidden: {candidate.relative_to(root)}"
                )
        dirs.sort()
        files.sort()

        for filename in files:
            candidate = current / filename
            if candidate.is_symlink():
                raise ReleaseIntegrityError(
                    f"symlink file forbidden: {candidate.relative_to(root)}"
                )
            if not candidate.is_file():
                raise ReleaseIntegrityError(
                    f"non-regular release entry forbidden: {candidate.relative_to(root)}"
                )
            rel = _canonical_relpath(candidate.relative_to(root).as_posix())
            if rel in exclude_paths:
                continue
            if rel in seen_paths:
                raise ReleaseIntegrityError(f"duplicate release file path: {rel}")
            seen_paths.add(rel)
            data = candidate.read_bytes()
            entries.append(
                ReleaseFileEntry(path=rel, sha256=_sha256_bytes(data), size=len(data))
            )

    entries.sort(key=lambda entry: entry.path)
    return tuple(entries)


def build_release_manifest(
    package_root: str | Path,
    *,
    release_id: str,
    source_commit: str,
    source_tree: str,
    build_id: str,
    prehandoff_receipt_refs: Sequence[str] = (),
    manifest_path: str = DEFAULT_MANIFEST_PATH,
) -> ReleaseManifest:
    canonical_manifest_path = _canonical_relpath(manifest_path)
    raw_refs = tuple(prehandoff_receipt_refs)
    refs = tuple(sorted(set(raw_refs)))
    if len(refs) != len(raw_refs):
        raise ReleaseIntegrityError("duplicate pre-handoff receipt ref")
    return ReleaseManifest(
        release_id=release_id,
        source_commit=source_commit,
        source_tree=source_tree,
        build_id=build_id,
        prehandoff_receipt_refs=refs,
        files=_iter_regular_files(
            Path(package_root), exclude_paths=frozenset({canonical_manifest_path})
        ),
    )


def write_release_manifest(
    package_root: str | Path,
    manifest: ReleaseManifest,
    *,
    manifest_path: str = DEFAULT_MANIFEST_PATH,
) -> Path:
    root = Path(package_root).resolve(strict=True)
    rel = _canonical_relpath(manifest_path)
    destination = root.joinpath(*PurePosixPath(rel).parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(manifest.canonical_bytes())
    return destination


def verify_release_manifest(
    package_root: str | Path,
    manifest: ReleaseManifest,
    *,
    manifest_path: str = DEFAULT_MANIFEST_PATH,
) -> None:
    rel = _canonical_relpath(manifest_path)
    observed = _iter_regular_files(Path(package_root), exclude_paths=frozenset({rel}))
    expected_by_path = {entry.path: entry for entry in manifest.files}
    observed_by_path = {entry.path: entry for entry in observed}

    missing = sorted(set(expected_by_path) - set(observed_by_path))
    extra = sorted(set(observed_by_path) - set(expected_by_path))
    mismatched = sorted(
        path
        for path in set(expected_by_path) & set(observed_by_path)
        if expected_by_path[path] != observed_by_path[path]
    )
    if missing or extra or mismatched:
        raise ReleaseIntegrityError(
            "release payload mismatch; "
            f"missing={missing}, extra={extra}, mismatched={mismatched}"
        )


def load_and_verify_release_manifest(
    package_root: str | Path,
    *,
    manifest_path: str = DEFAULT_MANIFEST_PATH,
) -> ReleaseManifest:
    root = Path(package_root).resolve(strict=True)
    rel = _canonical_relpath(manifest_path)
    manifest_file = root.joinpath(*PurePosixPath(rel).parts)
    if manifest_file.is_symlink() or not manifest_file.is_file():
        raise ReleaseIntegrityError("manifest must be a regular non-symlink file")
    raw = manifest_file.read_bytes()
    manifest = ReleaseManifest.from_bytes(raw)
    if raw != manifest.canonical_bytes():
        raise ReleaseIntegrityError("manifest JSON is not in canonical byte form")
    verify_release_manifest(root, manifest, manifest_path=rel)
    return manifest
