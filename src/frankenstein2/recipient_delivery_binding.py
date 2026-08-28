"""Bind F2 recipient delivery to the single canonical UnifiedDB authority.

This adapter composes F2-WP-100 path/fingerprint authority with F2-WP-103 delivery.
It refuses missing or ambiguous durable-state targets and proves that schema admission
happened on the same SQLite inode that was resolved/fingerprinted before mutation.

The receipt is an integration identity receipt only. It is not a full DB snapshot,
whole-system runtime acceptance, or effect authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3
from typing import Mapping, Optional

from state.unifieddb_identity import (
    UnifiedDBFingerprint,
    UnifiedDBIdentityError,
    UnifiedDBResolution,
    fingerprint_unifieddb,
    resolve_unifieddb_path,
)

from .recipient_delivery import RecipientDeliveryStore


_BINDING_SCHEMA = "F2_RECIPIENT_DELIVERY_UNIFIEDDB_BINDING/v1"
_REQUIRED_TABLES = frozenset({"coordination_events", "coordination_deliveries"})


class RecipientDeliveryBindingError(RuntimeError):
    """Fail-closed canonical UnifiedDB binding error."""


@dataclass(frozen=True, slots=True)
class RecipientDeliveryUnifiedDBBinding:
    schema: str
    resolution: dict
    before_fingerprint: dict
    after_fingerprint: dict
    same_real_path: bool
    same_device: bool
    same_inode: bool
    required_tables_present: bool
    quick_check: str
    classification: str = "CANONICAL_UNIFIEDDB_COORDINATION_COMPONENT_BINDING_ONLY"

    def to_dict(self) -> dict:
        return asdict(self)

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class BoundRecipientDeliveryStore:
    store: RecipientDeliveryStore
    binding: RecipientDeliveryUnifiedDBBinding


def _identity_tuple(fp: UnifiedDBFingerprint) -> tuple[str, Optional[int], Optional[int]]:
    return (fp.real_path, fp.device, fp.inode)


def _verify_delivery_schema(path: str) -> tuple[bool, str]:
    try:
        con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise RecipientDeliveryBindingError("UNIFIEDDB_READONLY_REOPEN_FAILED") from exc
    try:
        names = {
            str(row[0])
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        quick_row = con.execute("PRAGMA quick_check").fetchone()
        quick = "MISSING" if quick_row is None else str(quick_row[0])
        return _REQUIRED_TABLES <= names, quick
    except sqlite3.Error as exc:
        raise RecipientDeliveryBindingError("UNIFIEDDB_POST_ADMISSION_VERIFY_FAILED") from exc
    finally:
        con.close()


def bind_recipient_delivery_to_canonical_unifieddb(
    *,
    env: Optional[Mapping[str, str]] = None,
    home: Optional[Path | str] = None,
    pointer_path: Optional[Path | str] = None,
    legacy_path: Optional[Path | str] = None,
) -> BoundRecipientDeliveryStore:
    """Resolve, attest, admit and reopen recipient delivery on canonical UnifiedDB.

    Acceptance rules:
    - WP-100 must resolve exactly one authority;
    - target must already exist and fingerprint as SQLite before WP-103 mutation;
    - RecipientDeliveryStore may add only its tables to that exact file;
    - post-admission fingerprint must retain real path + device + inode;
    - required tables and PRAGMA quick_check=ok must be observed afterward.

    Requiring an existing DB is deliberate: WP-103 may extend canonical durable state,
    but this adapter does not get authority to mint a new canonical UnifiedDB itself.
    """
    try:
        resolution: UnifiedDBResolution = resolve_unifieddb_path(
            env=env,
            home=home,
            pointer_path=pointer_path,
            legacy_path=legacy_path,
        )
        before = fingerprint_unifieddb(resolution.path)
    except UnifiedDBIdentityError as exc:
        raise RecipientDeliveryBindingError(f"UNIFIEDDB_AUTHORITY_REJECTED:{exc}") from exc

    if not resolution.exists_at_resolution or not before.exists:
        raise RecipientDeliveryBindingError("CANONICAL_UNIFIEDDB_MUST_EXIST_BEFORE_WP103_ADMISSION")
    if before.status != "SQLITE3_REGULAR_FILE":
        raise RecipientDeliveryBindingError("CANONICAL_UNIFIEDDB_NOT_SQLITE3_REGULAR_FILE")

    expected_identity = _identity_tuple(before)
    store = RecipientDeliveryStore(resolution.path)

    try:
        after = fingerprint_unifieddb(resolution.path)
    except UnifiedDBIdentityError as exc:
        raise RecipientDeliveryBindingError(f"POST_ADMISSION_FINGERPRINT_REJECTED:{exc}") from exc

    same_real_path = before.real_path == after.real_path
    same_device = before.device == after.device
    same_inode = before.inode == after.inode
    if _identity_tuple(after) != expected_identity:
        raise RecipientDeliveryBindingError("UNIFIEDDB_REPLACED_DURING_WP103_SCHEMA_ADMISSION")

    tables_present, quick_check = _verify_delivery_schema(after.real_path)
    if not tables_present:
        raise RecipientDeliveryBindingError("WP103_REQUIRED_TABLES_MISSING_AFTER_ADMISSION")
    if quick_check.lower() != "ok":
        raise RecipientDeliveryBindingError(f"UNIFIEDDB_QUICK_CHECK_FAILED:{quick_check}")

    binding = RecipientDeliveryUnifiedDBBinding(
        schema=_BINDING_SCHEMA,
        resolution=resolution.to_dict(),
        before_fingerprint=before.to_dict(),
        after_fingerprint=after.to_dict(),
        same_real_path=same_real_path,
        same_device=same_device,
        same_inode=same_inode,
        required_tables_present=tables_present,
        quick_check=quick_check,
    )
    return BoundRecipientDeliveryStore(store=store, binding=binding)


__all__ = [
    "BoundRecipientDeliveryStore",
    "RecipientDeliveryBindingError",
    "RecipientDeliveryUnifiedDBBinding",
    "bind_recipient_delivery_to_canonical_unifieddb",
]
