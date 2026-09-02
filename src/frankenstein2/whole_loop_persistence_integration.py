"""WP900 -> WP206 canonical persistence/readback integration boundary.

This module stays deliberately thin: it reuses the existing WP900 whole-loop evidence
and the canonical WP206 store.  The historical seal-only path remains available for its
accepted deterministic scope.  The runtime-bound path additionally preserves the exact
WP900 G5 runtime/source identity instead of collapsing distinct valid runtime subjects
onto one persisted-readback evidence object.

Repository-component execution of either path is not target-host or whole-system runtime
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
from .runtime_bound_whole_loop import (
    RuntimeBoundWholeLoopCandidate,
    RuntimeBoundWholeLoopError,
    validate_runtime_bound_whole_loop,
)
from .whole_persistent_loop import WholePersistentLoopSeal


PERSISTED_LOOP_READBACK_SCHEMA = "FRANKENSTEIN2_WHOLE_LOOP_PERSISTED_READBACK/v1"
PERSISTED_LOOP_READBACK_CLASSIFICATION = (
    "WP900_WP206_CANONICAL_PERSISTENCE_READBACK_EVIDENCE_NOT_RUNTIME_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"
)
RUNTIME_BOUND_PERSISTED_LOOP_READBACK_SCHEMA = (
    "FRANKENSTEIN2_RUNTIME_BOUND_WHOLE_LOOP_PERSISTED_READBACK/v1"
)
RUNTIME_BOUND_PERSISTED_LOOP_READBACK_CLASSIFICATION = (
    "WP900_G5_RUNTIME_IDENTITY_BOUND_WP206_PERSISTENCE_READBACK_CANDIDATE_NOT_RUNTIME_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"
)


class WholeLoopPersistenceIntegrationError(RuntimeError):
    """Fail closed when WP900 evidence and the WP206 canonical store do not agree."""


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


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeBoundPersistedWholeLoopReadbackEvidence:
    persisted_readback_sha256: str
    runtime_bound_whole_loop_sha256: str
    whole_loop_seal_id: str
    whole_loop_seal_sha256: str
    causal_runtime_readback_sha256: str
    exact_source_sha256: str
    boot_id_sha256: str
    execution_context_sha256: str
    broadcast_id: str
    broadcast_sha256: str
    uptake_receipt_sha256: str
    causal_result_sha256: str
    canonical_db_path: str
    db_device: int
    db_inode: int
    unifieddb_authority_receipt_sha256: str
    schema: str = RUNTIME_BOUND_PERSISTED_LOOP_READBACK_SCHEMA
    classification: str = RUNTIME_BOUND_PERSISTED_LOOP_READBACK_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "canonical_persistence_authority": "WP206_CANONICAL_PERSISTENT_AGENCY_STORE",
                "runtime_identity_authority": "WP900_G5_RUNTIME_BOUND_WHOLE_LOOP_CANDIDATE",
                "write_observed": True,
                "typed_readback_observed": True,
                "runtime_identity_preserved": True,
                "target_host_execution": "NOT_OBSERVED",
                "repository_component_credit": 0,
                "target_environment_component_runtime_credit": 0,
                "runtime_credit": 0,
                "gwt_runtime_credit": 0,
                "semantic_gwt_runtime_credit": 0,
                "jspace_runtime_credit": 0,
                "effect_authority": "NONE",
                "truth_authority": "NONE",
                "completion_authority": "NONE",
                "training_credit": 0,
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

    This is the historical deterministic seal-only boundary.  It intentionally does not
    claim that a specific G5 runtime subject executed the persistence operation.  Call
    :func:`persist_runtime_bound_successor_and_readback` when the already-admitted WP900
    G5 runtime identity must survive the persistence/readback evidence handoff.
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


def _validate_runtime_binding(
    *,
    runtime_binding: RuntimeBoundWholeLoopCandidate,
    seal: WholePersistentLoopSeal,
) -> None:
    if type(runtime_binding) is not RuntimeBoundWholeLoopCandidate:
        raise WholeLoopPersistenceIntegrationError(
            "RUNTIME_BOUND_WHOLE_LOOP_CANDIDATE_REQUIRED"
        )
    try:
        validate_runtime_bound_whole_loop(runtime_binding)
    except RuntimeBoundWholeLoopError as exc:
        raise WholeLoopPersistenceIntegrationError(
            f"INVALID_RUNTIME_BOUND_WHOLE_LOOP:{exc}"
        ) from exc
    if runtime_binding.whole_loop_seal_id != seal.seal_id:
        raise WholeLoopPersistenceIntegrationError("RUNTIME_BINDING_SEAL_ID_MISMATCH")
    if runtime_binding.whole_loop_seal_sha256 != seal.sha256():
        raise WholeLoopPersistenceIntegrationError("RUNTIME_BINDING_SEAL_DIGEST_MISMATCH")


def persist_runtime_bound_successor_and_readback(
    store: CanonicalPersistentAgencyStore,
    *,
    seal: WholePersistentLoopSeal,
    runtime_binding: RuntimeBoundWholeLoopCandidate,
    next_checkpoint: PersistentAgencyCheckpoint,
) -> RuntimeBoundPersistedWholeLoopReadbackEvidence:
    """Persist through WP206 while retaining the accepted WP900 G5 runtime identity.

    The factory-origin G5 candidate is validated and bound to the exact deterministic
    seal *before* any store write. Persistence remains delegated to the existing WP206
    adapter/store. The returned evidence then binds the deterministic persisted readback
    digest and every authority-bearing G5 runtime identity needed to distinguish valid
    runtime subjects that share the same deterministic whole-loop seal.
    """
    if type(seal) is not WholePersistentLoopSeal:
        raise WholeLoopPersistenceIntegrationError("WHOLE_PERSISTENT_LOOP_SEAL_REQUIRED")
    _validate_runtime_binding(runtime_binding=runtime_binding, seal=seal)

    persisted = persist_sealed_successor_and_readback(
        store,
        seal=seal,
        next_checkpoint=next_checkpoint,
    )
    return RuntimeBoundPersistedWholeLoopReadbackEvidence(
        persisted_readback_sha256=persisted.sha256(),
        runtime_bound_whole_loop_sha256=runtime_binding.sha256(),
        whole_loop_seal_id=runtime_binding.whole_loop_seal_id,
        whole_loop_seal_sha256=runtime_binding.whole_loop_seal_sha256,
        causal_runtime_readback_sha256=runtime_binding.causal_runtime_readback_sha256,
        exact_source_sha256=runtime_binding.exact_source_sha256,
        boot_id_sha256=runtime_binding.boot_id_sha256,
        execution_context_sha256=runtime_binding.execution_context_sha256,
        broadcast_id=runtime_binding.broadcast_id,
        broadcast_sha256=runtime_binding.broadcast_sha256,
        uptake_receipt_sha256=runtime_binding.uptake_receipt_sha256,
        causal_result_sha256=runtime_binding.causal_result_sha256,
        canonical_db_path=persisted.canonical_db_path,
        db_device=persisted.db_device,
        db_inode=persisted.db_inode,
        unifieddb_authority_receipt_sha256=persisted.unifieddb_authority_receipt_sha256,
    )


__all__ = [
    "PERSISTED_LOOP_READBACK_CLASSIFICATION",
    "PERSISTED_LOOP_READBACK_SCHEMA",
    "RUNTIME_BOUND_PERSISTED_LOOP_READBACK_CLASSIFICATION",
    "RUNTIME_BOUND_PERSISTED_LOOP_READBACK_SCHEMA",
    "PersistedWholeLoopReadbackEvidence",
    "RuntimeBoundPersistedWholeLoopReadbackEvidence",
    "WholeLoopPersistenceIntegrationError",
    "persist_runtime_bound_successor_and_readback",
    "persist_sealed_successor_and_readback",
]
