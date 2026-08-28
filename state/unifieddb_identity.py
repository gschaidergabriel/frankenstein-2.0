"""Frankenstein 2.0 UnifiedDB path resolution and read-only identity receipts.

F2-WP-100, Triggerword 4.

This module deliberately does *not* create, migrate, copy, repair, or mutate a database.
It answers two narrower questions:

1. Which path is allowed to denote the one durable UnifiedDB authority?
2. What inspectable identity metadata does an existing SQLite database expose right now?

Source-level implementation is not live-host acceptance. A receipt from this module is an
identity/observability receipt, not proof that all runtime participants use the same DB.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterable, Mapping, Sequence


SQLITE_HEADER = b"SQLite format 3\x00"
DEFAULT_ENV_NAMES = ("FRANKENSTEIN2_DB", "AGENTZERO_DB")


class UnifiedDBIdentityError(RuntimeError):
    """Base class for fail-closed UnifiedDB identity errors."""


class ExplicitAuthorityConflict(UnifiedDBIdentityError):
    """Two explicit authorities name different database paths."""


class InvalidAuthority(UnifiedDBIdentityError):
    """An explicit authority is malformed, relative, missing, or otherwise unsafe."""


class NotSQLiteDatabase(UnifiedDBIdentityError):
    """The selected path is not an existing SQLite 3 database file."""


@dataclass(frozen=True)
class UnifiedDBResolution:
    canonical_path: str
    authority: str
    exists: bool
    fresh_install_target: bool
    explicit_sources: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class UnifiedDBFingerprint:
    canonical_path: str
    filesystem_device: int
    filesystem_inode: int
    file_size_bytes: int
    mtime_ns: int
    sqlite_header: str
    sqlite_version: str
    page_size: int
    page_count: int
    schema_version: int
    user_version: int
    application_id: int
    schema_sha256: str
    journal_mode: str
    wal_present: bool
    shm_present: bool
    classification: str = "SQLITE_IDENTITY_NOT_STATE_SNAPSHOT"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def receipt_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _xdg_config_home(env: Mapping[str, str]) -> Path:
    raw = env.get("XDG_CONFIG_HOME")
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            raise InvalidAuthority("XDG_CONFIG_HOME must be absolute")
        return p
    return Path.home() / ".config"


def _xdg_data_home(env: Mapping[str, str]) -> Path:
    raw = env.get("XDG_DATA_HOME")
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            raise InvalidAuthority("XDG_DATA_HOME must be absolute")
        return p
    return Path.home() / ".local" / "share"


def default_pointer_file(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return _xdg_config_home(env) / "frankenstein-2.0" / "unifieddb.path"


def default_data_path(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    return _xdg_data_home(env) / "frankenstein-2.0" / "unified.db"


def _absolute_env_path(raw: str, source: str) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        raise InvalidAuthority(
            f"{source} must be an absolute path; relative DB paths are CWD-dependent"
        )
    return Path(os.path.realpath(os.fspath(p)))


def _pointer_target(pointer_file: Path) -> Path | None:
    if not pointer_file.exists():
        return None
    if not pointer_file.is_file():
        raise InvalidAuthority(f"DB pointer is not a regular file: {pointer_file}")
    raw = pointer_file.read_text(encoding="utf-8").strip()
    if not raw:
        raise InvalidAuthority(f"DB pointer is empty: {pointer_file}")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = pointer_file.parent / candidate
    candidate = Path(os.path.realpath(os.fspath(candidate)))
    if not candidate.is_file():
        raise InvalidAuthority(f"DB pointer target does not exist: {candidate}")
    return candidate


def _explicit_env_targets(
    env: Mapping[str, str], env_names: Sequence[str]
) -> list[tuple[str, Path]]:
    targets: list[tuple[str, Path]] = []
    for name in env_names:
        raw = env.get(name, "").strip()
        if raw:
            targets.append((name, _absolute_env_path(raw, name)))
    return targets


def _assert_one_explicit_target(
    pointer: Path | None, env_targets: Sequence[tuple[str, Path]]
) -> tuple[Path | None, tuple[str, ...]]:
    explicit: list[tuple[str, Path]] = []
    if pointer is not None:
        explicit.append(("pointer_file", pointer))
    explicit.extend(env_targets)
    if not explicit:
        return None, ()

    grouped: dict[str, list[str]] = {}
    paths: dict[str, Path] = {}
    for source, path in explicit:
        key = os.path.normcase(os.fspath(path))
        grouped.setdefault(key, []).append(source)
        paths[key] = path
    if len(grouped) != 1:
        detail = "; ".join(
            f"{','.join(sources)}={paths[key]}" for key, sources in sorted(grouped.items())
        )
        raise ExplicitAuthorityConflict(
            "conflicting explicit UnifiedDB authorities; refusing silent precedence: " + detail
        )
    only_key = next(iter(grouped))
    return paths[only_key], tuple(source for source, _ in explicit)


def resolve_unifieddb(
    *,
    env: Mapping[str, str] | None = None,
    pointer_file: str | os.PathLike[str] | None = None,
    legacy_candidates: Iterable[str | os.PathLike[str]] = (),
    env_names: Sequence[str] = DEFAULT_ENV_NAMES,
) -> UnifiedDBResolution:
    """Resolve the one allowed UnifiedDB path without touching or creating the DB.

    Precedence is donor-compatible but successor-stricter:
      explicit pointer / explicit environment (must agree if both are present)
      -> existing XDG data DB
      -> exactly one existing legacy DB
      -> fresh-install XDG data target.

    Relative environment paths are rejected so process CWD can never select durable state.
    A relative pointer target is interpreted relative to the pointer file itself, not CWD.
    """
    env = os.environ if env is None else env
    pointer_path = (
        default_pointer_file(env)
        if pointer_file is None
        else Path(pointer_file).expanduser()
    )
    if not pointer_path.is_absolute():
        raise InvalidAuthority("pointer_file must be absolute")

    pointer_target = _pointer_target(pointer_path)
    env_targets = _explicit_env_targets(env, env_names)
    explicit_target, explicit_sources = _assert_one_explicit_target(
        pointer_target, env_targets
    )
    if explicit_target is not None:
        return UnifiedDBResolution(
            canonical_path=os.fspath(explicit_target),
            authority="EXPLICIT",
            exists=explicit_target.is_file(),
            fresh_install_target=False,
            explicit_sources=explicit_sources,
        )

    data_path = Path(os.path.realpath(os.fspath(default_data_path(env))))
    if data_path.is_file():
        return UnifiedDBResolution(
            canonical_path=os.fspath(data_path),
            authority="XDG_EXISTING",
            exists=True,
            fresh_install_target=False,
            explicit_sources=(),
        )

    existing_legacy: list[Path] = []
    seen: set[str] = set()
    for raw in legacy_candidates:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            raise InvalidAuthority("legacy_candidates must be absolute")
        p = Path(os.path.realpath(os.fspath(p)))
        key = os.path.normcase(os.fspath(p))
        if p.is_file() and key not in seen:
            existing_legacy.append(p)
            seen.add(key)
    if len(existing_legacy) > 1:
        raise ExplicitAuthorityConflict(
            "multiple legacy UnifiedDB files exist; migration authority is ambiguous: "
            + ", ".join(map(os.fspath, existing_legacy))
        )
    if existing_legacy:
        return UnifiedDBResolution(
            canonical_path=os.fspath(existing_legacy[0]),
            authority="LEGACY_EXISTING",
            exists=True,
            fresh_install_target=False,
            explicit_sources=(),
        )

    return UnifiedDBResolution(
        canonical_path=os.fspath(data_path),
        authority="XDG_FRESH_TARGET",
        exists=False,
        fresh_install_target=True,
        explicit_sources=(),
    )


def _pragma_int(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute(f"PRAGMA {name}").fetchone()
    if row is None:
        raise NotSQLiteDatabase(f"PRAGMA {name} returned no value")
    return int(row[0])


def fingerprint_sqlite(path: str | os.PathLike[str]) -> UnifiedDBFingerprint:
    """Read an existing SQLite DB and return identity metadata without mutating it.

    The result deliberately says ``SQLITE_IDENTITY_NOT_STATE_SNAPSHOT``. SQLite WAL state,
    concurrent transactions, and runtime participant bindings require separate receipts.
    """
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise InvalidAuthority("fingerprint path must be absolute")
    try:
        canonical = p.resolve(strict=True)
    except FileNotFoundError as exc:
        raise NotSQLiteDatabase(f"database does not exist: {p}") from exc
    if not canonical.is_file():
        raise NotSQLiteDatabase(f"database is not a regular file: {canonical}")

    with canonical.open("rb") as fh:
        header = fh.read(len(SQLITE_HEADER))
    if header != SQLITE_HEADER:
        raise NotSQLiteDatabase(f"SQLite header missing: {canonical}")

    stat_before = canonical.stat()
    uri = canonical.as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise NotSQLiteDatabase(f"SQLite read-only open failed: {canonical}") from exc
    try:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute(
            "SELECT type, name, tbl_name, COALESCE(sql, '') "
            "FROM sqlite_master ORDER BY type, name, tbl_name, COALESCE(sql, '')"
        ).fetchall()
        schema_payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        schema_digest = sha256(schema_payload.encode("utf-8")).hexdigest()
        journal_row = conn.execute("PRAGMA journal_mode").fetchone()
        journal_mode = "UNKNOWN" if journal_row is None else str(journal_row[0]).upper()
        fingerprint = UnifiedDBFingerprint(
            canonical_path=os.fspath(canonical),
            filesystem_device=int(stat_before.st_dev),
            filesystem_inode=int(stat_before.st_ino),
            file_size_bytes=int(stat_before.st_size),
            mtime_ns=int(stat_before.st_mtime_ns),
            sqlite_header="SQLite format 3",
            sqlite_version=sqlite3.sqlite_version,
            page_size=_pragma_int(conn, "page_size"),
            page_count=_pragma_int(conn, "page_count"),
            schema_version=_pragma_int(conn, "schema_version"),
            user_version=_pragma_int(conn, "user_version"),
            application_id=_pragma_int(conn, "application_id"),
            schema_sha256=schema_digest,
            journal_mode=journal_mode,
            wal_present=Path(os.fspath(canonical) + "-wal").exists(),
            shm_present=Path(os.fspath(canonical) + "-shm").exists(),
        )
    except sqlite3.Error as exc:
        raise NotSQLiteDatabase(f"SQLite identity query failed: {canonical}") from exc
    finally:
        conn.close()

    stat_after = canonical.stat()
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(stat_before, field) != getattr(stat_after, field) for field in stable_fields):
        raise UnifiedDBIdentityError(
            "database file identity changed while fingerprinting; retry at a stable boundary"
        )
    return fingerprint


__all__ = [
    "DEFAULT_ENV_NAMES",
    "ExplicitAuthorityConflict",
    "InvalidAuthority",
    "NotSQLiteDatabase",
    "UnifiedDBFingerprint",
    "UnifiedDBIdentityError",
    "UnifiedDBResolution",
    "default_data_path",
    "default_pointer_file",
    "fingerprint_sqlite",
    "resolve_unifieddb",
]
