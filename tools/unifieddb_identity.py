#!/usr/bin/env python3
"""Deterministic UnifiedDB path resolution and fingerprinting for Frankenstein 2.0.

This module does not create or mutate the database. Resolution mirrors the donor's
persistence hierarchy while keeping donor-specific pointer/legacy locations explicit.
Fingerprinting opens SQLite read-only and separates filesystem instance identity from
logical schema identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

SQLITE_HEADER = b"SQLite format 3\x00"
DEFAULT_ENV_NAME = "AGENTZERO_DB"
DEFAULT_XDG_SUBPATH = Path("agentzero") / "unified.db"


class UnifiedDBIdentityError(RuntimeError):
    """Raised when canonical UnifiedDB identity cannot be established safely."""


@dataclass(frozen=True)
class ResolvedUnifiedDB:
    path: str
    source: str
    exists: bool
    pointer_file: str | None = None


@dataclass(frozen=True)
class UnifiedDBFingerprint:
    resolved_path: str
    source: str | None
    stat_device: int
    stat_inode: int
    stat_size: int
    stat_mtime_ns: int
    sqlite_user_version: int
    sqlite_application_id: int
    sqlite_page_size: int
    sqlite_encoding: str
    schema_object_count: int
    schema_sha256: str
    instance_sha256: str
    file_sha256: str | None


def _expand(value: str, *, home: Path) -> Path:
    if not value or not value.strip():
        raise UnifiedDBIdentityError("empty UnifiedDB path candidate")
    raw = value.strip()
    if raw == "~":
        return home
    if raw.startswith("~/"):
        return home / raw[2:]
    return Path(os.path.expandvars(raw))


def _pointer_target(pointer_file: Path, *, home: Path) -> Path | None:
    if not pointer_file.is_file():
        return None
    try:
        text = pointer_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise UnifiedDBIdentityError(f"cannot read pointer file: {pointer_file}") from exc
    if not text:
        return None
    if text.startswith("{"):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise UnifiedDBIdentityError(f"invalid JSON pointer file: {pointer_file}") from exc
        value = payload.get("path") or payload.get("db_path")
        if not isinstance(value, str) or not value.strip():
            raise UnifiedDBIdentityError(
                f"JSON pointer file must contain non-empty 'path' or 'db_path': {pointer_file}"
            )
        return _expand(value, home=home)
    return _expand(text, home=home)


def _canonicalize(path: Path, *, require_existing: bool) -> tuple[Path, bool]:
    try:
        if require_existing:
            resolved = path.resolve(strict=True)
        else:
            resolved = path.resolve(strict=False)
    except OSError as exc:
        raise UnifiedDBIdentityError(f"cannot resolve UnifiedDB path: {path}") from exc
    exists = resolved.is_file()
    if require_existing and not exists:
        raise UnifiedDBIdentityError(f"UnifiedDB does not exist as a regular file: {resolved}")
    if resolved.exists() and not exists:
        raise UnifiedDBIdentityError(f"UnifiedDB path is not a regular file: {resolved}")
    return resolved, exists


def resolve_unifieddb_path(
    *,
    pointer_file: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    env_name: str = DEFAULT_ENV_NAME,
    legacy_env_names: Sequence[str] = (),
    xdg_data_home: str | os.PathLike[str] | None = None,
    home: str | os.PathLike[str] | None = None,
    legacy_paths: Iterable[str | os.PathLike[str]] = (),
    require_existing: bool = True,
) -> ResolvedUnifiedDB:
    """Resolve UnifiedDB using donor-preserving precedence.

    Precedence: valid pointer -> environment -> XDG data path -> existing legacy path.
    For fresh installs (`require_existing=False`), the XDG path is selected before legacy
    probing so package-local state never becomes the default for a new installation.

    Donor-specific pointer filename and legacy locations are explicit inputs because the
    current donor prose specifies their role but not a stable cross-version filename ABI.
    """
    env_map = os.environ if env is None else env
    home_path = Path(home) if home is not None else Path.home()

    if pointer_file is not None:
        pointer = Path(pointer_file).expanduser()
        target = _pointer_target(pointer, home=home_path)
        if target is not None:
            resolved, exists = _canonicalize(target, require_existing=True)
            return ResolvedUnifiedDB(str(resolved), "POINTER", exists, str(pointer.resolve(strict=False)))

    for name in (env_name, *legacy_env_names):
        value = env_map.get(name)
        if value and value.strip():
            resolved, exists = _canonicalize(_expand(value, home=home_path), require_existing=require_existing)
            return ResolvedUnifiedDB(str(resolved), f"ENV:{name}", exists)

    if xdg_data_home is not None:
        xdg_root = Path(xdg_data_home)
    elif env_map.get("XDG_DATA_HOME", "").strip():
        xdg_root = _expand(env_map["XDG_DATA_HOME"], home=home_path)
    else:
        xdg_root = home_path / ".local" / "share"
    xdg_candidate = xdg_root / DEFAULT_XDG_SUBPATH

    if not require_existing:
        resolved, exists = _canonicalize(xdg_candidate, require_existing=False)
        return ResolvedUnifiedDB(str(resolved), "XDG_DEFAULT", exists)

    if xdg_candidate.is_file():
        resolved, exists = _canonicalize(xdg_candidate, require_existing=True)
        return ResolvedUnifiedDB(str(resolved), "XDG_EXISTING", exists)

    for legacy in legacy_paths:
        candidate = Path(legacy).expanduser()
        if candidate.is_file():
            resolved, exists = _canonicalize(candidate, require_existing=True)
            return ResolvedUnifiedDB(str(resolved), "LEGACY_EXISTING", exists)

    raise UnifiedDBIdentityError(
        "no existing UnifiedDB resolved via pointer, environment, XDG data path, or declared legacy paths"
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_unifieddb(
    db: ResolvedUnifiedDB | str | os.PathLike[str], *, include_file_sha256: bool = False
) -> UnifiedDBFingerprint:
    """Fingerprint an existing SQLite DB without creating or mutating it."""
    if isinstance(db, ResolvedUnifiedDB):
        path = Path(db.path)
        source = db.source
    else:
        path = Path(db).resolve(strict=True)
        source = None

    path = path.resolve(strict=True)
    if not path.is_file():
        raise UnifiedDBIdentityError(f"UnifiedDB is not a regular file: {path}")

    try:
        with path.open("rb") as handle:
            header = handle.read(len(SQLITE_HEADER))
    except OSError as exc:
        raise UnifiedDBIdentityError(f"cannot read UnifiedDB header: {path}") from exc
    if header != SQLITE_HEADER:
        raise UnifiedDBIdentityError(f"not a SQLite 3 database: {path}")

    stat = path.stat()
    uri = path.as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            conn.execute("PRAGMA query_only = ON")
            user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            application_id = int(conn.execute("PRAGMA application_id").fetchone()[0])
            page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
            encoding = str(conn.execute("PRAGMA encoding").fetchone()[0])
            rows = conn.execute(
                """
                SELECT type, name, tbl_name, COALESCE(sql, '')
                FROM sqlite_master
                WHERE type IN ('table','view','index','trigger')
                ORDER BY type, name, tbl_name, COALESCE(sql, '')
                """
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise UnifiedDBIdentityError(f"cannot inspect UnifiedDB read-only: {path}: {exc}") from exc

    schema_payload = {
        "application_id": application_id,
        "encoding": encoding,
        "objects": [list(row) for row in rows],
        "page_size": page_size,
        "user_version": user_version,
    }
    schema_bytes = json.dumps(
        schema_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    schema_sha = hashlib.sha256(schema_bytes).hexdigest()

    instance_payload = {
        "resolved_path": str(path),
        "schema_sha256": schema_sha,
        "stat_device": int(stat.st_dev),
        "stat_inode": int(stat.st_ino),
        "stat_size": int(stat.st_size),
        "stat_mtime_ns": int(stat.st_mtime_ns),
    }
    instance_sha = hashlib.sha256(
        json.dumps(instance_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    return UnifiedDBFingerprint(
        resolved_path=str(path),
        source=source,
        stat_device=int(stat.st_dev),
        stat_inode=int(stat.st_ino),
        stat_size=int(stat.st_size),
        stat_mtime_ns=int(stat.st_mtime_ns),
        sqlite_user_version=user_version,
        sqlite_application_id=application_id,
        sqlite_page_size=page_size,
        sqlite_encoding=encoding,
        schema_object_count=len(rows),
        schema_sha256=schema_sha,
        instance_sha256=instance_sha,
        file_sha256=_sha256_file(path) if include_file_sha256 else None,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pointer-file")
    parser.add_argument("--legacy-path", action="append", default=[])
    parser.add_argument("--legacy-env", action="append", default=[])
    parser.add_argument("--xdg-data-home")
    parser.add_argument("--home")
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--fingerprint", action="store_true")
    parser.add_argument("--file-sha256", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        resolved = resolve_unifieddb_path(
            pointer_file=args.pointer_file,
            legacy_env_names=tuple(args.legacy_env),
            xdg_data_home=args.xdg_data_home,
            home=args.home,
            legacy_paths=tuple(args.legacy_path),
            require_existing=not args.allow_missing,
        )
        payload: dict[str, object] = {"resolved": asdict(resolved)}
        if args.fingerprint:
            if not resolved.exists:
                raise UnifiedDBIdentityError("cannot fingerprint a missing fresh-install path")
            payload["fingerprint"] = asdict(
                fingerprint_unifieddb(resolved, include_file_sha256=args.file_sha256)
            )
        print(json.dumps(payload, sort_keys=True, indent=2))
        return 0
    except UnifiedDBIdentityError as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
