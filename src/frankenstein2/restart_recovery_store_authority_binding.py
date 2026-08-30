"""Store-bound UnifiedDB authority bridge for WP901 restart/recovery.

F2-WP-901 generation 5 successor over accepted G4 persisted-row attestation.

G4 proves that a checkpoint was loaded from one exact CanonicalPersistentAgencyStore row,
but its canonical entry point still accepts a separately caller-supplied
``UnifiedDBAuthorityRef`` for the downstream G3 source binding.  Executable PR719 showed
that a foreign authority reference could therefore accompany a valid checkpoint from the
real store and still reach ``CONTINUE_UNFINISHED``.

G5 closes only that cross-boundary identity gap.  It deterministically derives the expected
G3 authority reference from the exact store authority receipt already consumed by G4 and
requires any caller-supplied reference to equal it before planning.  The accepted G4 row
snapshot, G3 typed-source checks and G2 continuation semantics remain unchanged.

This module creates no second persistence/truth/effect authority and grants no target-host,
runtime, completion, GWT/J-Space, model/provider or training credit.
"""
from __future__ import annotations

from .causal_authority_binding import UnifiedDBAuthorityRef
from .causal_identity import CausalIdentity
from .persistent_agency_kernel import CanonicalPersistentAgencyStore
from .restart_recovery_continuation import PersistedRestartEvidence
from .restart_recovery_persisted_row_attestation import (
    PersistedRowLoadAttestationError,
    PersistedRowRestartPlanResult,
    attest_persisted_checkpoint_load,
)
from .restart_recovery_source_authentication import plan_restart_continuation_from_sources
from .whole_persistent_loop import LoopOutcomeEvidence, WholePersistentLoopSeal
from state.unifieddb_identity import FINGERPRINT_SCHEMA as UNIFIEDDB_FINGERPRINT_SCHEMA


STORE_BOUND_AUTHORITY_REF_PREFIX = "f2:unifieddb-fingerprint:"
STORE_BOUND_AUTHORITY_SOURCE = "src/state/unifieddb_identity.py"


def store_bound_unifieddb_authority_ref(
    store: CanonicalPersistentAgencyStore,
) -> UnifiedDBAuthorityRef:
    """Derive the sole G3 authority ref admitted for this concrete WP206 store."""
    if type(store) is not CanonicalPersistentAgencyStore:
        raise PersistedRowLoadAttestationError(
            "CANONICAL_PERSISTENT_AGENCY_STORE_REQUIRED"
        )
    receipt = store.authority_receipt_sha256
    if not isinstance(receipt, str) or len(receipt) != 64 or any(
        ch not in "0123456789abcdef" for ch in receipt
    ):
        raise PersistedRowLoadAttestationError(
            "PERSISTED_ROW_STORE_AUTHORITY_RECEIPT_INVALID"
        )
    return UnifiedDBAuthorityRef(
        receipt_ref=STORE_BOUND_AUTHORITY_REF_PREFIX + receipt,
        canonical_source=STORE_BOUND_AUTHORITY_SOURCE,
        fingerprint_schema=UNIFIEDDB_FINGERPRINT_SCHEMA,
    )


def plan_restart_continuation_from_store_bound_persisted_row(
    store: CanonicalPersistentAgencyStore,
    *,
    checkpoint_id: str,
    evidence: PersistedRestartEvidence,
    plan_id: str,
    expected_evidence_sha256: str,
    causal_identity: CausalIdentity,
    unifieddb_authority: UnifiedDBAuthorityRef,
    whole_loop_seal: WholePersistentLoopSeal,
    outcome: LoopOutcomeEvidence,
) -> PersistedRowRestartPlanResult:
    """Canonical G5 ingress: exact store authority -> G4 row load -> G3 -> G2."""
    expected_authority = store_bound_unifieddb_authority_ref(store)
    if type(unifieddb_authority) is not UnifiedDBAuthorityRef:
        raise PersistedRowLoadAttestationError(
            "PERSISTED_ROW_G3_UNIFIEDDB_AUTHORITY_REF_REQUIRED"
        )
    if unifieddb_authority != expected_authority:
        raise PersistedRowLoadAttestationError(
            "PERSISTED_ROW_G3_UNIFIEDDB_AUTHORITY_REF_MISMATCH"
        )

    checkpoint, attestation = attest_persisted_checkpoint_load(
        store,
        checkpoint_id=checkpoint_id,
    )
    if (
        attestation.unifieddb_authority_receipt_sha256
        != store.authority_receipt_sha256
    ):
        raise PersistedRowLoadAttestationError(
            "PERSISTED_ROW_STORE_AUTHORITY_ATTESTATION_MISMATCH"
        )

    plan = plan_restart_continuation_from_sources(
        evidence,
        plan_id=plan_id,
        expected_evidence_sha256=expected_evidence_sha256,
        causal_identity=causal_identity,
        unifieddb_authority=expected_authority,
        source_checkpoint=checkpoint,
        whole_loop_seal=whole_loop_seal,
        outcome=outcome,
    )
    if plan.source_checkpoint_id != attestation.checkpoint_id:
        raise PersistedRowLoadAttestationError(
            "PERSISTED_ROW_PLAN_CHECKPOINT_ID_MISMATCH"
        )
    if plan.source_checkpoint_sha256 != attestation.checkpoint_sha256:
        raise PersistedRowLoadAttestationError(
            "PERSISTED_ROW_PLAN_CHECKPOINT_DIGEST_MISMATCH"
        )
    return PersistedRowRestartPlanResult(
        plan=plan,
        load_attestation=attestation,
    )


__all__ = [
    "STORE_BOUND_AUTHORITY_REF_PREFIX",
    "STORE_BOUND_AUTHORITY_SOURCE",
    "plan_restart_continuation_from_store_bound_persisted_row",
    "store_bound_unifieddb_authority_ref",
]
