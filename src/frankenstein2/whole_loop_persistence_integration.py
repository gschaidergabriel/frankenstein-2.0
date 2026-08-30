"""WP900 -> WP206 canonical persistence/readback integration boundary.

This module is intentionally thin. It does not create a second store, scheduler, receipt
system, truth authority, or runtime authority. It connects an already-validated WP900
WholePersistentLoopSeal to the already-canonical WP206 CanonicalPersistentAgencyStore,
then performs exact typed readback from that same authority.

Repository-component execution of this adapter is not target-host or whole-system runtime
credit. Broader promotion still requires exact-source execution on an admitted runtime.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any

from .persistent_agency_kernel import (
    CanonicalPersistentAgencyStore,
    PersistentAgencyCheckpoint,
    PersistentAgencyError,
)
from .whole_persistent_loop import WholePersistentLoopSeal


PERSISTED_LOOP_READBACK_SCHEMA = "FRANKENSTEIN2_WHOLE_LOOP_PERSISTED_READBACK/v1"
PERSISTED_LOOP_READBACK_CLASSIFICATION = (
    "WP900_WP206_CANONICAL_PERSISTENCE_READBACK_EVIDENCE_NOT_RUNTIME_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"
)


class WholeLoopPersistenceIntegrationError(RuntimeError):
    """Fail closed when the WP900 seal and WP206 canonical store do not agree."""


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class PersistedWholeLoopReadbackEvidence:
    whole_loop_seal_id: str
    whole_loop_seal_sha256: str
    current_checkpoint_id: str
    current_checkpoint_sha256: str
    next_checkpoint_id: str
    next_checkpoint_sha256: str
    canonical_db_path: str
    db_device: int
    db_inode: int
    unifieddb_authority_receipt_sha256: str
    schema: str = PERSISTED_LOOP_READBACK_SCHEMA
    classification: str = PERSISTED_LOOP_READBACK_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "canonical_persistence_authority": "WP206_CANONICAL_PERSISTENT_AGENCY_STORE",
                "write_observed": True,
                "typed_readback_observed": True,
                "target_host_execution": "NOT_OBSERVED",
                "runtime_credit": 0,
                "effect_authority": "NONE",
                "truth_authority": "NONE",
                "completion_authority": "NONE",
                "whole_system_acceptance": False,
            }
        )
        return payload

    def sha256(self) -> str:
        return _digest(self.as_dict())


def persist_sealed_successor_and_readback(
    store: CanonicalPersistentAgencyStore,
    *,
    seal: WholePersistentLoopSeal,
    next_checkpoint: PersistentAgencyCheckpoint,
) -> PersistedWholeLoopReadbackEvidence:
    """Persist exactly the WP900-sealed successor through WP206 and read it back.

    The parent must already exist in the same canonical store. The adapter verifies the
    stored parent against the WP900 seal before any write, delegates the write to the
    existing WP206 authority, then reloads the successor through the accepted WP206 typed
    loader and compares exact identity/digest fields.
    """
    if type(store) is not CanonicalPersistentAgencyStore:
        raise WholeLoopPersistenceIntegrationError(
            "CANONICAL_PERSISTENT_AGENCY_STORE_REQUIRED"
        )
    if type(seal) is not WholePersistentLoopSeal:
        raise WholeLoopPersistenceIntegrationError("WHOLE_PERSISTENT_LOOP_SEAL_REQUIRED")
    if type(next_checkpoint) is not PersistentAgencyCheckpoint:
        raise WholeLoopPersistenceIntegrationError("PERSISTENT_AGENCY_CHECKPOINT_REQUIRED")
    if store.connection.in_transaction:
        raise WholeLoopPersistenceIntegrationError("CLEAN_STORE_TRANSACTION_REQUIRED")

    if next_checkpoint.checkpoint_id != seal.next_checkpoint_id:
        raise WholeLoopPersistenceIntegrationError("SEALED_SUCCESSOR_ID_MISMATCH")
    if next_checkpoint.sha256() != seal.next_checkpoint_sha256:
        raise WholeLoopPersistenceIntegrationError("SEALED_SUCCESSOR_DIGEST_MISMATCH")
    if next_checkpoint.previous_checkpoint_id != seal.current_checkpoint_id:
        raise WholeLoopPersistenceIntegrationError("SEALED_SUCCESSOR_PARENT_MISMATCH")

    try:
        persisted_parent = store.load_checkpoint(seal.current_checkpoint_id)
    except PersistentAgencyError as exc:
        raise WholeLoopPersistenceIntegrationError(
            f"SEALED_PARENT_READBACK_FAILED:{exc}"
        ) from exc
    if persisted_parent.sha256() != seal.current_checkpoint_sha256:
        raise WholeLoopPersistenceIntegrationError("SEALED_PARENT_DIGEST_MISMATCH")

    try:
        written_sha256 = store.write_checkpoint(next_checkpoint)
    except PersistentAgencyError as exc:
        raise WholeLoopPersistenceIntegrationError(
            f"SEALED_SUCCESSOR_WRITE_FAILED:{exc}"
        ) from exc
    if written_sha256 != seal.next_checkpoint_sha256:
        raise WholeLoopPersistenceIntegrationError("CANONICAL_WRITE_DIGEST_MISMATCH")

    try:
        readback = store.load_checkpoint(seal.next_checkpoint_id)
    except PersistentAgencyError as exc:
        raise WholeLoopPersistenceIntegrationError(
            f"SEALED_SUCCESSOR_READBACK_FAILED:{exc}"
        ) from exc
    if readback.checkpoint_id != seal.next_checkpoint_id:
        raise WholeLoopPersistenceIntegrationError("CANONICAL_READBACK_ID_MISMATCH")
    if readback.sha256() != seal.next_checkpoint_sha256:
        raise WholeLoopPersistenceIntegrationError("CANONICAL_READBACK_DIGEST_MISMATCH")
    if readback.previous_checkpoint_id != seal.current_checkpoint_id:
        raise WholeLoopPersistenceIntegrationError("CANONICAL_READBACK_PARENT_MISMATCH")

    return PersistedWholeLoopReadbackEvidence(
        whole_loop_seal_id=seal.seal_id,
        whole_loop_seal_sha256=seal.sha256(),
        current_checkpoint_id=seal.current_checkpoint_id,
        current_checkpoint_sha256=seal.current_checkpoint_sha256,
        next_checkpoint_id=seal.next_checkpoint_id,
        next_checkpoint_sha256=seal.next_checkpoint_sha256,
        canonical_db_path=store.canonical_db_path,
        db_device=store.db_device,
        db_inode=store.db_inode,
        unifieddb_authority_receipt_sha256=store.authority_receipt_sha256,
    )


__all__ = [
    "PERSISTED_LOOP_READBACK_CLASSIFICATION",
    "PERSISTED_LOOP_READBACK_SCHEMA",
    "PersistedWholeLoopReadbackEvidence",
    "WholeLoopPersistenceIntegrationError",
    "persist_sealed_successor_and_readback",
]
