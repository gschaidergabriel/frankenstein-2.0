"""Typed EpistemicRecord -> ContextItem adapter for Frankenstein 2.0.

F2-WP-306 generation 3.

This module is a deterministic boundary adapter only. It binds already-typed
F2-WP-207 epistemic records into the reference-only F2-WP-306 ContextCompiler
surface without decoding payload semantics or minting truth, effect, completion,
retrieval or scheduling authority.
"""
from __future__ import annotations

import hashlib
from typing import Any

from frankenstein2.context_compiler import (
    CHANNEL_COUNTEREVIDENCE,
    CHANNEL_EVIDENCE,
    CHANNEL_HYPERPOSITION,
    CHANNEL_RETRIEVAL_REFERENCE,
    ContextItem,
)
from frankenstein2.epistemic_records import (
    InferredHypothesis,
    NegativeResult,
    ObservedEvidence,
    RetrievalPrior,
    UnknownEvidence,
)


class EpistemicContextAdapterError(ValueError):
    """Fail-closed boundary error for unsupported epistemic input."""


_CHANNEL_BY_EXACT_TYPE = {
    ObservedEvidence: CHANNEL_EVIDENCE,
    InferredHypothesis: CHANNEL_HYPERPOSITION,
    RetrievalPrior: CHANNEL_RETRIEVAL_REFERENCE,
    NegativeResult: CHANNEL_COUNTEREVIDENCE,
    # UNKNOWN remains visibly UNKNOWN in source_classification. HYPERPOSITION is
    # only the transport bucket for unresolved candidate state, never evidence.
    UnknownEvidence: CHANNEL_HYPERPOSITION,
}


def _payload_sha256(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _record_evidence_refs(record: Any) -> tuple[str, ...]:
    refs: list[str] = [f"epistemic-record-sha256:{record.identity_sha256}"]
    refs.extend(record.causal_refs)

    if type(record) is ObservedEvidence:
        refs.append(record.observation_ref)
    elif type(record) is InferredHypothesis:
        refs.extend(record.support_refs)
    elif type(record) is RetrievalPrior:
        refs.extend((record.retrieval_ref, f"query-sha256:{record.query_sha256}"))
    elif type(record) is NegativeResult:
        refs.extend((record.attempt_ref, record.falsifier_ref))
    elif type(record) is UnknownEvidence:
        # No semantic inference from reason text. The exact record digest remains
        # sufficient as a reference even when there are no causal refs.
        pass
    else:  # Defensive; the public adapter rejects before reaching this helper.
        raise EpistemicContextAdapterError("unsupported epistemic record type")

    return tuple(sorted(set(refs)))


def context_item_from_epistemic_record(
    record: Any,
    *,
    item_id: str,
    payload_ref: str,
    priority_bp: int,
    cost_units: int,
    required: bool = False,
) -> ContextItem:
    """Bind one exact typed epistemic record into one ContextItem.

    Channel selection is fixed by the concrete record type so callers cannot
    relabel a hypothesis, retrieval prior, negative result or UNKNOWN as observed
    evidence. Priority, cost and required-ness remain explicit caller inputs; the
    adapter does not infer relevance.
    """
    channel = _CHANNEL_BY_EXACT_TYPE.get(type(record))
    if channel is None:
        raise EpistemicContextAdapterError(
            "record must be one exact accepted F2-WP-207 epistemic record type"
        )

    return ContextItem.create(
        item_id=item_id,
        channel=channel,
        payload_ref=payload_ref,
        payload_sha256=_payload_sha256(record.payload_json),
        source_ref=record.record_id,
        source_sha256=record.identity_sha256,
        source_generation=record.generation,
        source_classification=record.classification,
        priority_bp=priority_bp,
        cost_units=cost_units,
        required=required,
        provenance_refs=(f"provenance-sha256:{record.provenance_sha256}",),
        evidence_refs=_record_evidence_refs(record),
    )


__all__ = [
    "EpistemicContextAdapterError",
    "context_item_from_epistemic_record",
]
