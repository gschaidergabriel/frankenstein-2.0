"""Fail-closed release-activation readback fence for Frankenstein 2.0.

F2-WP-1207 generation 2.

This module intentionally leaves the accepted generation-1 transaction ABI byte-identical.
It composes that validator and adds the missing discriminator needed before a transaction
receipt can be considered evidence that the *planned release identity* is the release
actually observed active.

It is still preparatory evidence only: no host/twin mutation, installer execution, package
or network I/O, target-runtime credit, physical credit, effect authority, or completion
credit is performed or granted here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping

from frankenstein2.portable_release_transaction import (
    PortableReleaseTransactionError,
    TransactionRequest,
    build_transaction_plan,
    record_attempt,
)

READBACK_SCHEMA = "FRANKENSTEIN2_PORTABLE_RELEASE_READBACK_RECEIPT/v1"
READBACK_EVIDENCE_SCOPE = (
    "HOSTILE_TWIN_RELEASE_READBACK_PREPARATORY_ONLY_NO_TARGET_RUNTIME_EFFECT_OR_COMPLETION_CREDIT"
)


class PortableReleaseReadbackError(ValueError):
    """Fail-closed release readback validation error."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _optional_digest(name: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PortableReleaseReadbackError(f"{name} must be a string or null")
    if value != value.strip() or len(value) != 64:
        raise PortableReleaseReadbackError(
            f"{name} must be lowercase 64-hex SHA-256 or null"
        )
    if any(ch not in "0123456789abcdef" for ch in value):
        raise PortableReleaseReadbackError(
            f"{name} must be lowercase 64-hex SHA-256 or null"
        )
    return value


@dataclass(frozen=True, slots=True)
class ReleaseReadbackReceipt:
    schema: str
    attempt_id: str
    operation: str
    request_digest: str
    plan_digest: str
    base_attempt_receipt_digest: str
    outcome: str
    observed_generation: int | None
    observed_state_sha256: str | None
    expected_active_release_digest: str | None
    observed_active_release_digest: str | None
    failure_code: str | None
    evidence_scope: str = READBACK_EVIDENCE_SCOPE

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def digest(self) -> str:
        return _sha256(self.as_dict())


def record_release_readback(
    raw_request: Mapping[str, Any],
    *,
    outcome: str,
    observed_generation: int | None,
    observed_state_sha256: str | None,
    observed_active_release_digest: str | None,
    failure_code: str | None = None,
) -> ReleaseReadbackReceipt:
    """Validate G1 attempt evidence plus exact active-release readback.

    The original request is first normalized through the accepted G1 TransactionRequest,
    then the G1 plan and G1 attempt receipt are rebuilt from that normalized value. This
    prevents the readback fence from weakening generation/state/failure semantics while
    adding the release-identity discriminator.
    """

    try:
        request = TransactionRequest.from_mapping(raw_request)
        normalized_request = request.as_dict()
        plan = build_transaction_plan(normalized_request)
        base_receipt = record_attempt(
            plan,
            outcome=outcome,
            observed_generation=observed_generation,
            observed_state_sha256=observed_state_sha256,
            failure_code=failure_code,
        )
    except PortableReleaseTransactionError:
        raise

    observed_release = _optional_digest(
        "observed_active_release_digest", observed_active_release_digest
    )

    if base_receipt.outcome == "SUCCEEDED":
        expected_release = plan.target_release_digest
        if observed_release != expected_release:
            raise PortableReleaseReadbackError(
                "SUCCEEDED requires observed active release to match planned target release"
            )
    elif request.current_lineage is None:
        expected_release = None
        if observed_release is not None:
            raise PortableReleaseReadbackError(
                "failed first install must not invent an active release identity"
            )
    else:
        expected_release = request.current_lineage.active_release_digest
        if observed_release != expected_release:
            raise PortableReleaseReadbackError(
                f"{base_receipt.outcome} requires observed active release to match exact pre-attempt release"
            )

    return ReleaseReadbackReceipt(
        schema=READBACK_SCHEMA,
        attempt_id=plan.attempt_id,
        operation=plan.operation,
        request_digest=plan.request_digest,
        plan_digest=plan.digest(),
        base_attempt_receipt_digest=base_receipt.digest(),
        outcome=base_receipt.outcome,
        observed_generation=base_receipt.observed_generation,
        observed_state_sha256=base_receipt.observed_state_sha256,
        expected_active_release_digest=expected_release,
        observed_active_release_digest=observed_release,
        failure_code=base_receipt.failure_code,
    )
