#!/usr/bin/env python3
"""Canonical UnifiedDB resolver and read-only identity primitives.

F2-WP-100 generation 1.

The donor's persistence hierarchy is preserved, but Frankenstein 2.0 fails closed
where two explicit authorities disagree or where a relative path would make process
CWD select durable truth. This module creates, migrates, repairs and mutates nothing.
Its fingerprint is an identity receipt, *not* a full SQLite state snapshot and not
proof that every runtime participant opened the same database.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Mapping, Optional, Sequence


RESOLUTION_SCHEMA = "FRANKENSTEIN2_UNIFIEDDB_RESOLUTION/v2"
FINGERPRINT_SCHEMA = "FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2"
SQLITE_HEADER = b"SQLite format 3\x00"
EXPLICIT_ENV_KEYS = ("FRANKENSTEIN2_DB", "AGENTZERO_DB", "UDB_DB_PATH")


class UnifiedDBIdentityError(RuntimeError):
    """Fail-closed identity error."""


class UnifiedDBAuthorityConflict(UnifiedDBIdentityError):
    """Multiple explicit authorities resolve to different durable-state paths."""


@dataclass(frozen=True)
class UnifiedDBResolution:
    schema: str
    path: str
    source: str
    exists_at_resolution: bool
    explicit_sources: tuple[str, ...] = ()

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
    sqlite_schema_sha256: Optional[str] = None
    sqlite_schema_version: Optional[int] = None
    sqlite_user_version: Optional[int] = None
    sqlite_application_id: Optional[int] = None
    sqlite_page_size: Optional[int] = None
    sqlite_page_count: Optional[int] = None
    sqlite_journal_mode: Optional[str] = None
    wal_present: Optional[bool] = None
    shm_present: Optional[bool] = None
    classification: str = "SQLITE_IDENTITY_NOT_STATE_SNAPSHOT"

    def to_dict(self) -> dict:
        return asdict(self)

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def receipt_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _expand_without_cwd(path: Path | str, *, label: str) -> Path:
    selected = Path(os.path.expanduser(os.fspath(path)))
    if not selected.is_absolute():
        raise UnifiedDBIdentityError(f"{label}_RELATIVE_PATH_FORBIDDEN")
    return Path(os.path.abspath(selected))


def _absolute_home(path: Path | str) -> Path:
    home = Path(os.path.expanduser(os.fspath(path)))
    if not home.is_absolute():
        raise UnifiedDBIdentityError("HOME_RELATIVE_PATH_FORBIDDEN")
    return Path(os.path.abspath(home))


def _pointer_default(home: Path, env: Mapping[str, str]) -> Path:
    xdg_config = env.get("XDG_CONFIG_HOME")
    if xdg_config:
        base = _expand_without_cwd(xdg_config, label="XDG_CONFIG_HOME")
    else:
        base = home / ".config"
    return base / "agentzero" / "db_pfad.txt"


def _xdg_target(home: Path, env: Mapping[str, str]) -> Path:
    xdg_data = env.get("XDG_DATA_HOME")
    if xdg_data:
        base = _expand_without_cwd(xdg_data, label="XDG_DATA_HOME")
    else:
        base = home / ".local" / "share"
    return base / "agentzero" / "unified.db"


def _canonical_intended_path(path: Path) -> Path:
    # realpath is deterministic for existing ancestors and does not require the target
    # to exist. It removes symlink/path spelling ambiguity without creating anything.
    return Path(os.path.realpath(os.fspath(path)))


def _read_pointer(pointer: Path) -> Path | None:
    try:
        raw = pointer.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as exc:
        raise UnifiedDBIdentityError("UNIFIEDDB_POINTER_UNREADABLE") from exc
    if not raw:
        raise UnifiedDBIdentityError("UNIFIEDDB_POINTER_EMPTY")

    candidate = Path(os.path.expanduser(raw))
    if not candidate.is_absolute():
        # Relative pointer text is anchored to the pointer file, never process CWD.
        candidate = pointer.parent / candidate
    candidate = _canonical_intended_path(candidate)
    if not candidate.is_file():
        raise UnifiedDBIdentityError("UNIFIEDDB_POINTER_TARGET_MISSING")
    return candidate


def _explicit_env_targets(
    env: Mapping[str, str], keys: Sequence[str] = EXPLICIT_ENV_KEYS
) -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    for key in keys:
        raw = env.get(key, "").strip()
        if not raw:
            continue
        selected = _expand_without_cwd(raw, label=key)
        result.append((key, _canonical_intended_path(selected)))
    return result


def _coalesce_explicit(
    pointer_target: Path | None, env_targets: Sequence[tuple[str, Path]]
) -> tuple[Path | None, tuple[str, ...]]:
    candidates: list[tuple[str, Path]] = []
    if pointer_target is not None:
        candidates.append(("POINTER", pointer_target))
    candidates.extend(env_targets)
    if not candidates:
        return None, ()

    by_path: dict[str, list[str]] = {}
    canonical: dict[str, Path] = {}
    for source, path in candidates:
        key = os.path.normcase(os.fspath(path))
        by_path.setdefault(key, []).append(source)
        canonical[key] = path
    if len(by_path) != 1:
        detail = ";".join(
            f"{','.join(by_path[key])}={canonical[key]}" for key in sorted(by_path)
        )
        raise UnifiedDBAuthorityConflict("UNIFIEDDB_EXPLICIT_AUTHORITY_CONFLICT:" + detail)
    key = next(iter(by_path))
    return canonical[key], tuple(source for source, _ in candidates)


def resolve_unifieddb_path(
    *,
    env: Optional[Mapping[str, str]] = None,
    home: Optional[Path | str] = None,
    pointer_path: Optional[Path | str] = None,
    legacy_path: Optional[Path | str] = None,
) -> UnifiedDBResolution:
    """Resolve the sole allowed UnifiedDB location without touching the DB.

    Successor-safe precedence:
      1. pointer and explicit environment authorities, if present, must agree;
      2. existing XDG data target;
      3. explicitly supplied existing legacy path;
      4. XDG data target for a fresh installation.

    The donor's persistence intent is preserved: replaceable source/plugin trees never
    become the fresh-install state default. Relative explicit paths fail closed.
    """
    env_map: Mapping[str, str] = os.environ if env is None else env
    home_path = _absolute_home(Path.home() if home is None else home)
    pointer = (
        _expand_without_cwd(pointer_path, label="POINTER_FILE")
        if pointer_path is not None
        else _pointer_default(home_path, env_map)
    )
    target = _canonical_intended_path(_xdg_target(home_path, env_map))

    pointed = _read_pointer(pointer)
    env_targets = _explicit_env_targets(env_map)
    explicit_target, explicit_sources = _coalesce_explicit(pointed, env_targets)
    if explicit_target is not None:
        source = "EXPLICIT_" + "+".join(explicit_sources)
        return UnifiedDBResolution(
            RESOLUTION_SCHEMA,
            str(explicit_target),
            source,
            explicit_target.is_file(),
            explicit_sources,
        )

    if target.is_file():
        return UnifiedDBResolution(
            RESOLUTION_SCHEMA, str(target), "XDG_EXISTING", True, ()
        )

    if legacy_path is not None:
        legacy = _canonical_intended_path(
            _expand_without_cwd(legacy_path, label="LEGACY_DB")
        )
        if legacy.is_file():
            return UnifiedDBResolution(
                RESOLUTION_SCHEMA, str(legacy), "LEGACY_EXISTING", True, ()
            )

    return UnifiedDBResolution(
        RESOLUTION_SCHEMA, str(target), "XDG_FRESH_TARGET", False, ()
    )


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


def _sqlite_schema_identity(path: Path) -> tuple[str, int, int, int, int, int, str]:
    uri = path.as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise UnifiedDBIdentityError("UNIFIEDDB_SQLITE_READONLY_OPEN_FAILED") from exc
    try:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute(
            "SELECT type,name,tbl_name,COALESCE(sql,'') FROM sqlite_master "
            "ORDER BY type,name,tbl_name,COALESCE(sql,'')"
        ).fetchall()
        payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        def pragma_int(name: str) -> int:
            row = conn.execute(f"PRAGMA {name}").fetchone()
            if row is None:
                raise UnifiedDBIdentityError(f"UNIFIEDDB_PRAGMA_MISSING:{name}")
            return int(row[0])

        mode_row = conn.execute("PRAGMA journal_mode").fetchone()
        mode = "UNKNOWN" if mode_row is None else str(mode_row[0]).upper()
        return (
            digest,
            pragma_int("schema_version"),
            pragma_int("user_version"),
            pragma_int("application_id"),
            pragma_int("page_size"),
            pragma_int("page_count"),
            mode,
        )
    except sqlite3.Error as exc:
        raise UnifiedDBIdentityError("UNIFIEDDB_SQLITE_IDENTITY_QUERY_FAILED") from exc
    finally:
        conn.close()


def fingerprint_unifieddb(path: Path | str) -> UnifiedDBFingerprint:
    """Fingerprint an exact SQLite file and detect replacement/mutation.

    Missing fresh-install targets are represented explicitly. Symlinks, non-regular
    files, non-SQLite content and files changing during the file-hash phase fail closed.
    The result is an identity receipt; WAL/runtime binding still needs separate evidence.
    """
    selected = _expand_without_cwd(path, label="UNIFIEDDB")
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

        os.lseek(fd, 0, os.SEEK_SET)
        if os.read(fd, len(SQLITE_HEADER)) != SQLITE_HEADER:
            raise UnifiedDBIdentityError("UNIFIEDDB_NOT_SQLITE3")

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

        real = Path(os.path.realpath(selected))
        (
            schema_digest,
            schema_version,
            user_version,
            application_id,
            page_size,
            page_count,
            journal_mode,
        ) = _sqlite_schema_identity(real)
        return UnifiedDBFingerprint(
            FINGERPRINT_SCHEMA,
            str(selected),
            str(real),
            "SQLITE3_REGULAR_FILE",
            True,
            after_fd.st_size,
            after_fd.st_dev,
            after_fd.st_ino,
            after_fd.st_mtime_ns,
            after_fd.st_ctime_ns,
            digest,
            schema_digest,
            schema_version,
            user_version,
            application_id,
            page_size,
            page_count,
            journal_mode,
            Path(str(real) + "-wal").exists(),
            Path(str(real) + "-shm").exists(),
        )
    finally:
        os.close(fd)


__all__ = [
    "EXPLICIT_ENV_KEYS",
    "FINGERPRINT_SCHEMA",
    "RESOLUTION_SCHEMA",
    "UnifiedDBAuthorityConflict",
    "UnifiedDBFingerprint",
    "UnifiedDBIdentityError",
    "UnifiedDBResolution",
    "fingerprint_unifieddb",
    "resolve_unifieddb_path",
]
