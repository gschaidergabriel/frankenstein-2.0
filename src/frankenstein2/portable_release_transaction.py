"""Deterministic hostile-twin release transaction planning for Frankenstein 2.0.

F2-WP-1207 generation 1.

This module is a fail-closed *preparatory* transaction/state-lineage primitive for
portable release install/update/rollback tests.  It never installs a release, mutates a
host, invokes a package manager, performs network I/O, or grants target/runtime/effect/
completion credit.

The core laws are:

    PLAN != EXECUTION
    TWIN_RECEIPT != PHYSICAL_TARGET_RECEIPT
    REQUESTED_SUCCESS != VERIFIED_SUCCESS

All release and lineage identities are exact SHA-256 values.  UPDATE and ROLLBACK require
caller-supplied predecessor continuity; missing continuity is rejected rather than inferred.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

RELEASE_SCHEMA = "FRANKENSTEIN2_PORTABLE_RELEASE_IDENTITY/v1"
LINEAGE_SCHEMA = "FRANKENSTEIN2_DURABLE_STATE_LINEAGE/v1"
REQUEST_SCHEMA = "FRANKENSTEIN2_PORTABLE_RELEASE_TRANSACTION_REQUEST/v1"
PLAN_SCHEMA = "FRANKENSTEIN2_PORTABLE_RELEASE_TRANSACTION_PLAN/v1"
RECEIPT_SCHEMA = "FRANKENSTEIN2_PORTABLE_RELEASE_TRANSACTION_RECEIPT/v1"
EVIDENCE_SCOPE = "HOSTILE_TWIN_PREPARATORY_ONLY_NO_TARGET_RUNTIME_EFFECT_OR_COMPLETION_CREDIT"

_OPERATIONS = {"INSTALL", "UPDATE", "ROLLBACK"}
_OUTCOMES = {"SUCCEEDED", "FAILED_NO_MUTATION", "ROLLED_BACK"}


class PortableReleaseTransactionError(ValueError):
    """Fail-closed release transaction validation error."""


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


def _string(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise PortableReleaseTransactionError(f"{name} must be a string")
    if value != value.strip() or not value:
        raise PortableReleaseTransactionError(f"{name} must be non-empty and already trimmed")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PortableReleaseTransactionError(f"{name} contains control characters")
    return value


def _digest(name: str, value: Any) -> str:
    text = _string(name, value)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise PortableReleaseTransactionError(f"{name} must be lowercase 64-hex SHA-256")
    return text


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PortableReleaseTransactionError(f"{name} must be a non-negative integer")
    return value


def _optional_digest(name: str, value: Any) -> str | None:
    if value is None:
        return None
    return _digest(name, value)


def _optional_generation(name: str, value: Any) -> int | None:
    if value is None:
        return None
    return _generation(name, value)


@dataclass(frozen=True, slots=True)
class ReleaseIdentity:
    schema: str
    release_id: str
    version: str
    artifact_sha256: str
    manifest_sha256: str

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ReleaseIdentity":
        if not isinstance(raw, Mapping):
            raise PortableReleaseTransactionError("release identity must be a mapping")
        if raw.get("schema", RELEASE_SCHEMA) != RELEASE_SCHEMA:
            raise PortableReleaseTransactionError("release identity schema mismatch")
        return cls(
            schema=RELEASE_SCHEMA,
            release_id=_string("release_id", raw.get("release_id")),
            version=_string("version", raw.get("version")),
            artifact_sha256=_digest("artifact_sha256", raw.get("artifact_sha256")),
            manifest_sha256=_digest("manifest_sha256", raw.get("manifest_sha256")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "release_id": self.release_id,
            "version": self.version,
            "artifact_sha256": self.artifact_sha256,
            "manifest_sha256": self.manifest_sha256,
        }

    def digest(self) -> str:
        return _sha256(self.as_dict())


@dataclass(frozen=True, slots=True)
class StateLineage:
    schema: str
    generation: int
    state_sha256: str
    active_release_digest: str
    predecessor_generation: int | None
    predecessor_state_sha256: str | None
    predecessor_release_digest: str | None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "StateLineage":
        if not isinstance(raw, Mapping):
            raise PortableReleaseTransactionError("state lineage must be a mapping")
        if raw.get("schema", LINEAGE_SCHEMA) != LINEAGE_SCHEMA:
            raise PortableReleaseTransactionError("state lineage schema mismatch")
        lineage = cls(
            schema=LINEAGE_SCHEMA,
            generation=_generation("generation", raw.get("generation")),
            state_sha256=_digest("state_sha256", raw.get("state_sha256")),
            active_release_digest=_digest("active_release_digest", raw.get("active_release_digest")),
            predecessor_generation=_optional_generation(
                "predecessor_generation", raw.get("predecessor_generation")
            ),
            predecessor_state_sha256=_optional_digest(
                "predecessor_state_sha256", raw.get("predecessor_state_sha256")
            ),
            predecessor_release_digest=_optional_digest(
                "predecessor_release_digest", raw.get("predecessor_release_digest")
            ),
        )
        predecessor_values = (
            lineage.predecessor_generation,
            lineage.predecessor_state_sha256,
            lineage.predecessor_release_digest,
        )
        if any(value is None for value in predecessor_values) and any(
            value is not None for value in predecessor_values
        ):
            raise PortableReleaseTransactionError(
                "predecessor lineage fields must be all present or all absent"
            )
        if (
            lineage.predecessor_generation is not None
            and lineage.predecessor_generation >= lineage.generation
        ):
            raise PortableReleaseTransactionError(
                "predecessor_generation must be lower than current generation"
            )
        return lineage

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "generation": self.generation,
            "state_sha256": self.state_sha256,
            "active_release_digest": self.active_release_digest,
            "predecessor_generation": self.predecessor_generation,
            "predecessor_state_sha256": self.predecessor_state_sha256,
            "predecessor_release_digest": self.predecessor_release_digest,
        }

    def digest(self) -> str:
        return _sha256(self.as_dict())


@dataclass(frozen=True, slots=True)
class TransactionRequest:
    schema: str
    attempt_id: str
    operation: str
    target_release: ReleaseIdentity
    current_lineage: StateLineage | None
    expected_generation: int | None
    expected_state_sha256: str | None
    rollback_release: ReleaseIdentity | None
    injected_failure_stage: str | None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "TransactionRequest":
        if not isinstance(raw, Mapping):
            raise PortableReleaseTransactionError("transaction request must be a mapping")
        if raw.get("schema", REQUEST_SCHEMA) != REQUEST_SCHEMA:
            raise PortableReleaseTransactionError("transaction request schema mismatch")
        operation = _string("operation", raw.get("operation")).upper()
        if operation not in _OPERATIONS:
            raise PortableReleaseTransactionError("operation must be INSTALL, UPDATE, or ROLLBACK")
        current_raw = raw.get("current_lineage")
        rollback_raw = raw.get("rollback_release")
        request = cls(
            schema=REQUEST_SCHEMA,
            attempt_id=_string("attempt_id", raw.get("attempt_id")),
            operation=operation,
            target_release=ReleaseIdentity.from_mapping(raw.get("target_release")),
            current_lineage=(
                None if current_raw is None else StateLineage.from_mapping(current_raw)
            ),
            expected_generation=_optional_generation(
                "expected_generation", raw.get("expected_generation")
            ),
            expected_state_sha256=_optional_digest(
                "expected_state_sha256", raw.get("expected_state_sha256")
            ),
            rollback_release=(
                None if rollback_raw is None else ReleaseIdentity.from_mapping(rollback_raw)
            ),
            injected_failure_stage=(
                None
                if raw.get("injected_failure_stage") is None
                else _string("injected_failure_stage", raw.get("injected_failure_stage"))
            ),
        )
        request._validate_semantics()
        return request

    def _validate_semantics(self) -> None:
        continuity_fields = (self.expected_generation, self.expected_state_sha256)
        if any(value is None for value in continuity_fields) and any(
            value is not None for value in continuity_fields
        ):
            raise PortableReleaseTransactionError(
                "expected_generation and expected_state_sha256 must be supplied together"
            )

        if self.operation == "INSTALL":
            if self.current_lineage is not None or any(
                value is not None for value in continuity_fields
            ):
                raise PortableReleaseTransactionError(
                    "INSTALL is only valid for an explicitly empty lineage"
                )
            if self.rollback_release is not None:
                raise PortableReleaseTransactionError(
                    "INSTALL must not carry rollback_release"
                )
            return

        if self.current_lineage is None:
            raise PortableReleaseTransactionError(
                f"{self.operation} requires current_lineage"
            )
        if self.expected_generation is None or self.expected_state_sha256 is None:
            raise PortableReleaseTransactionError(
                f"{self.operation} requires exact expected generation/state continuity"
            )
        if self.expected_generation != self.current_lineage.generation:
            raise PortableReleaseTransactionError("expected generation does not match current lineage")
        if self.expected_state_sha256 != self.current_lineage.state_sha256:
            raise PortableReleaseTransactionError("expected state digest does not match current lineage")

        if self.operation == "UPDATE":
            if self.rollback_release is not None:
                raise PortableReleaseTransactionError("UPDATE must not carry rollback_release")
            if self.target_release.digest() == self.current_lineage.active_release_digest:
                raise PortableReleaseTransactionError("UPDATE target must differ from active release")
            return

        # ROLLBACK
        if self.rollback_release is None:
            raise PortableReleaseTransactionError("ROLLBACK requires rollback_release")
        if (
            self.current_lineage.predecessor_generation is None
            or self.current_lineage.predecessor_state_sha256 is None
            or self.current_lineage.predecessor_release_digest is None
        ):
            raise PortableReleaseTransactionError(
                "ROLLBACK requires exact predecessor lineage in current state"
            )
        rollback_digest = self.rollback_release.digest()
        if rollback_digest != self.current_lineage.predecessor_release_digest:
            raise PortableReleaseTransactionError(
                "rollback release does not match exact predecessor release"
            )
        if self.target_release.digest() != rollback_digest:
            raise PortableReleaseTransactionError(
                "ROLLBACK target_release must equal rollback_release"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "attempt_id": self.attempt_id,
            "operation": self.operation,
            "target_release": self.target_release.as_dict(),
            "current_lineage": (
                None if self.current_lineage is None else self.current_lineage.as_dict()
            ),
            "expected_generation": self.expected_generation,
            "expected_state_sha256": self.expected_state_sha256,
            "rollback_release": (
                None if self.rollback_release is None else self.rollback_release.as_dict()
            ),
            "injected_failure_stage": self.injected_failure_stage,
        }


@dataclass(frozen=True, slots=True)
class TransactionPlan:
    schema: str
    attempt_id: str
    operation: str
    request_digest: str
    target_release_digest: str
    source_lineage_digest: str | None
    source_generation: int | None
    source_state_sha256: str | None
    source_active_release_digest: str | None
    next_generation: int
    rollback_target_generation: int | None
    rollback_target_state_sha256: str | None
    rollback_target_release_digest: str | None
    injected_failure_stage: str | None
    evidence_scope: str = EVIDENCE_SCOPE

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "attempt_id": self.attempt_id,
            "operation": self.operation,
            "request_digest": self.request_digest,
            "target_release_digest": self.target_release_digest,
            "source_lineage_digest": self.source_lineage_digest,
            "source_generation": self.source_generation,
            "source_state_sha256": self.source_state_sha256,
            "source_active_release_digest": self.source_active_release_digest,
            "next_generation": self.next_generation,
            "rollback_target_generation": self.rollback_target_generation,
            "rollback_target_state_sha256": self.rollback_target_state_sha256,
            "rollback_target_release_digest": self.rollback_target_release_digest,
            "injected_failure_stage": self.injected_failure_stage,
            "evidence_scope": self.evidence_scope,
        }

    def digest(self) -> str:
        return _sha256(self.as_dict())


@dataclass(frozen=True, slots=True)
class AttemptReceipt:
    schema: str
    attempt_id: str
    plan_digest: str
    operation: str
    outcome: str
    observed_generation: int | None
    observed_state_sha256: str | None
    observed_active_release_digest: str | None
    failure_code: str | None
    evidence_scope: str = EVIDENCE_SCOPE

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "attempt_id": self.attempt_id,
            "plan_digest": self.plan_digest,
            "operation": self.operation,
            "outcome": self.outcome,
            "observed_generation": self.observed_generation,
            "observed_state_sha256": self.observed_state_sha256,
            "observed_active_release_digest": self.observed_active_release_digest,
            "failure_code": self.failure_code,
            "evidence_scope": self.evidence_scope,
        }

    def digest(self) -> str:
        return _sha256(self.as_dict())


def build_transaction_plan(raw: Mapping[str, Any]) -> TransactionPlan:
    """Validate exact continuity and return a deterministic non-executing plan."""

    request = TransactionRequest.from_mapping(raw)
    lineage = request.current_lineage
    rollback_generation = None
    rollback_state = None
    rollback_release_digest = None
    if request.operation == "ROLLBACK":
        assert lineage is not None
        rollback_generation = lineage.predecessor_generation
        rollback_state = lineage.predecessor_state_sha256
        rollback_release_digest = lineage.predecessor_release_digest

    return TransactionPlan(
        schema=PLAN_SCHEMA,
        attempt_id=request.attempt_id,
        operation=request.operation,
        request_digest=_sha256(request.as_dict()),
        target_release_digest=request.target_release.digest(),
        source_lineage_digest=None if lineage is None else lineage.digest(),
        source_generation=None if lineage is None else lineage.generation,
        source_state_sha256=None if lineage is None else lineage.state_sha256,
        source_active_release_digest=(
            None if lineage is None else lineage.active_release_digest
        ),
        next_generation=0 if lineage is None else lineage.generation + 1,
        rollback_target_generation=rollback_generation,
        rollback_target_state_sha256=rollback_state,
        rollback_target_release_digest=rollback_release_digest,
        injected_failure_stage=request.injected_failure_stage,
    )


def record_attempt(
    plan: TransactionPlan,
    *,
    outcome: str,
    observed_generation: int | None,
    observed_state_sha256: str | None,
    observed_active_release_digest: str | None = None,
    failure_code: str | None = None,
) -> AttemptReceipt:
    """Create a deterministic attempt receipt without converting assertions into truth.

    SUCCEEDED requires an exact observed next generation, a state digest and an independently
    observed active-release digest matching the planned target. Failure/rollback outcomes must
    preserve the exact pre-attempt release/state lineage. Failure injection can never be
    normalized into success.
    """

    if not isinstance(plan, TransactionPlan):
        raise PortableReleaseTransactionError("plan must be TransactionPlan")
    normalized_outcome = _string("outcome", outcome).upper()
    if normalized_outcome not in _OUTCOMES:
        raise PortableReleaseTransactionError(
            "outcome must be SUCCEEDED, FAILED_NO_MUTATION, or ROLLED_BACK"
        )
    observed_generation_n = _optional_generation(
        "observed_generation", observed_generation
    )
    observed_state_n = _optional_digest(
        "observed_state_sha256", observed_state_sha256
    )
    observed_release_n = _optional_digest(
        "observed_active_release_digest", observed_active_release_digest
    )
    failure_code_n = None if failure_code is None else _string("failure_code", failure_code)

    if plan.injected_failure_stage is not None and normalized_outcome == "SUCCEEDED":
        raise PortableReleaseTransactionError(
            "injected failure cannot produce a synthetic SUCCEEDED receipt"
        )

    if normalized_outcome == "SUCCEEDED":
        if observed_generation_n != plan.next_generation or observed_state_n is None:
            raise PortableReleaseTransactionError(
                "SUCCEEDED requires exact next generation and observed state digest"
            )
        if observed_release_n != plan.target_release_digest:
            raise PortableReleaseTransactionError(
                "SUCCEEDED requires observed active release matching target release"
            )
        if failure_code_n is not None:
            raise PortableReleaseTransactionError("SUCCEEDED must not carry failure_code")

    elif normalized_outcome == "FAILED_NO_MUTATION":
        if plan.source_generation is None:
            if (
                observed_generation_n is not None
                or observed_state_n is not None
                or observed_release_n is not None
            ):
                raise PortableReleaseTransactionError(
                    "failed first install must not invent a durable lineage or active release"
                )
        else:
            if (
                observed_generation_n != plan.source_generation
                or observed_state_n != plan.source_state_sha256
                or observed_release_n != plan.source_active_release_digest
            ):
                raise PortableReleaseTransactionError(
                    "FAILED_NO_MUTATION must preserve exact source release/state lineage"
                )
        if failure_code_n is None:
            raise PortableReleaseTransactionError("failure outcome requires failure_code")

    else:  # ROLLED_BACK
        if (
            plan.source_generation is None
            or plan.source_state_sha256 is None
            or plan.source_active_release_digest is None
        ):
            raise PortableReleaseTransactionError("ROLLED_BACK requires a source lineage")
        if (
            observed_generation_n != plan.source_generation
            or observed_state_n != plan.source_state_sha256
            or observed_release_n != plan.source_active_release_digest
        ):
            raise PortableReleaseTransactionError(
                "ROLLED_BACK receipt must verify return to exact pre-attempt release/state lineage"
            )
        if failure_code_n is None:
            raise PortableReleaseTransactionError("rollback outcome requires failure_code")

    return AttemptReceipt(
        schema=RECEIPT_SCHEMA,
        attempt_id=plan.attempt_id,
        plan_digest=plan.digest(),
        operation=plan.operation,
        outcome=normalized_outcome,
        observed_generation=observed_generation_n,
        observed_state_sha256=observed_state_n,
        observed_active_release_digest=observed_release_n,
        failure_code=failure_code_n,
    )


def plan_from_json(text: str) -> str:
    """Pure JSON-in/JSON-out adapter for CI and hostile-twin tooling."""

    if not isinstance(text, str):
        raise PortableReleaseTransactionError("request JSON must be text")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PortableReleaseTransactionError("invalid transaction request JSON") from exc
    if not isinstance(raw, dict):
        raise PortableReleaseTransactionError("transaction request JSON must contain an object")
    return _canonical_json(build_transaction_plan(raw).as_dict()) + "\n"
