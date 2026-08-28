#!/usr/bin/env python3
"""Canonical UnifiedDB path resolution and exact file identity primitives.

F2-WP-100 generation 1 deliberately has no database-migration or schema-write
side effects.  It extracts the current donor's path precedence while making
file identity explicit enough for later causal/runtime receipts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import stat
from typing import Mapping, Optional


RESOLUTION_SCHEMA = "FRANKENSTEIN2_UNIFIEDDB_RESOLUTION/v1"
FINGERPRINT_SCHEMA = "FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v1"


class UnifiedDBIdentityError(RuntimeError):
    """Fail-closed identity error."""


@dataclass(frozen=True)
class UnifiedDBResolution:
    schema: str
    path: str
    source: str
    exists_at_resolution: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class UnifiedDBFingerprint:
    schema: str
    path: str
    real_path: str
    status: str
    exists: bool
    size: Optional[int]
    device: Optional[int]
    inode: Optional[int]
    mtime_ns: Optional[int]
    ctime_ns: Optional[int]
    sha256: Optional[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _absolute(path: Path | str) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _pointer_default(home: Path, env: Mapping[str, str]) -> Path:
    xdg_config = env.get("XDG_CONFIG_HOME")
    base = _absolute(xdg_config) if xdg_config else home / ".config"
    return base / "agentzero" / "db_pfad.txt"


def _xdg_target(home: Path, env: Mapping[str, str]) -> Path:
    xdg_data = env.get("XDG_DATA_HOME")
    base = _absolute(xdg_data) if xdg_data else home / ".local" / "share"
    return base / "agentzero" / "unified.db"


def resolve_unifieddb_path(
    *,
    env: Optional[Mapping[str, str]] = None,
    home: Optional[Path | str] = None,
    pointer_path: Optional[Path | str] = None,
    legacy_path: Optional[Path | str] = None,
) -> UnifiedDBResolution:
    """Resolve UnifiedDB location without creating, moving or opening the DB.

    Precedence is donor-compatible:
      1. pointer file, only if its target is an existing regular file;
      2. AGENTZERO_DB, then UDB_DB_PATH compatibility alias;
      3. existing XDG data target;
      4. explicitly supplied existing legacy path;
      5. XDG data target for a fresh installation.

    The legacy path is an explicit compatibility input. Frankenstein 2.0 never
    silently invents a source/plugin-tree fallback of its own.
    """
    env_map: Mapping[str, str] = os.environ if env is None else env
    home_path = _absolute(Path.home() if home is None else home)
    pointer = _absolute(pointer_path) if pointer_path is not None else _pointer_default(home_path, env_map)
    target = _xdg_target(home_path, env_map)

    try:
        pointed_text = pointer.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError, UnicodeError):
        pointed_text = ""
    if pointed_text:
        pointed = _absolute(pointed_text)
        if pointed.is_file():
            return UnifiedDBResolution(RESOLUTION_SCHEMA, str(pointed), "POINTER_EXISTING", True)

    for key in ("AGENTZERO_DB", "UDB_DB_PATH"):
        value = env_map.get(key)
        if value:
            selected = _absolute(value)
            return UnifiedDBResolution(RESOLUTION_SCHEMA, str(selected), f"ENV_{key}", selected.is_file())

    if target.is_file():
        return UnifiedDBResolution(RESOLUTION_SCHEMA, str(target), "XDG_EXISTING", True)

    if legacy_path is not None:
        legacy = _absolute(legacy_path)
        if legacy.is_file():
            return UnifiedDBResolution(RESOLUTION_SCHEMA, str(legacy), "LEGACY_EXISTING", True)

    return UnifiedDBResolution(RESOLUTION_SCHEMA, str(target), "XDG_FRESH_TARGET", False)


def _stat_signature(st: os.stat_result) -> tuple[int, int, int, int, int]:
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _sha256_fd(fd: int, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, chunk_size)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def fingerprint_unifieddb(path: Path | str) -> UnifiedDBFingerprint:
    """Fingerprint an exact regular DB file, detecting replacement/mutation.

    Missing files are represented explicitly because a fresh-install target can
    legitimately be unresolved before schema creation. Symlinks, directories,
    devices and files changing during hashing fail closed.
    """
    selected = _absolute(path)
    try:
        before_path = os.lstat(selected)
    except FileNotFoundError:
        return UnifiedDBFingerprint(
            FINGERPRINT_SCHEMA,
            str(selected),
            str(selected),
            "MISSING",
            False,
            None,
            None,
            None,
            None,
            None,
            None,
        )

    if not stat.S_ISREG(before_path.st_mode):
        raise UnifiedDBIdentityError("UNIFIEDDB_NOT_REGULAR_FILE")

    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        fd = os.open(selected, flags)
    except OSError as exc:
        raise UnifiedDBIdentityError(f"UNIFIEDDB_OPEN_FAILED:{exc.errno}") from exc

    try:
        before_fd = os.fstat(fd)
        if not stat.S_ISREG(before_fd.st_mode):
            raise UnifiedDBIdentityError("UNIFIEDDB_NOT_REGULAR_FILE")
        if (before_path.st_dev, before_path.st_ino) != (before_fd.st_dev, before_fd.st_ino):
            raise UnifiedDBIdentityError("UNIFIEDDB_REPLACED_BEFORE_FINGERPRINT")

        digest = _sha256_fd(fd)
        after_fd = os.fstat(fd)
        if _stat_signature(before_fd) != _stat_signature(after_fd):
            raise UnifiedDBIdentityError("UNIFIEDDB_MUTATED_DURING_FINGERPRINT")

        try:
            after_path = os.lstat(selected)
        except FileNotFoundError as exc:
            raise UnifiedDBIdentityError("UNIFIEDDB_REPLACED_DURING_FINGERPRINT") from exc
        if (after_path.st_dev, after_path.st_ino) != (after_fd.st_dev, after_fd.st_ino):
            raise UnifiedDBIdentityError("UNIFIEDDB_REPLACED_DURING_FINGERPRINT")

        return UnifiedDBFingerprint(
            FINGERPRINT_SCHEMA,
            str(selected),
            os.path.realpath(selected),
            "REGULAR_FILE",
            True,
            after_fd.st_size,
            after_fd.st_dev,
            after_fd.st_ino,
            after_fd.st_mtime_ns,
            after_fd.st_ctime_ns,
            digest,
        )
    finally:
        os.close(fd)
