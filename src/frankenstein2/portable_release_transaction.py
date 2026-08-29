"""Deterministic portable-release transaction primitives for hostile target twins.

F2-WP-1207 generation 1 preparatory component.

This module does NOT install a ZIP, invoke a package manager, mutate a host/twin, attach
VPS infrastructure, or grant T1-T4/runtime/effect/completion credit. It provides a strict
canonical transaction/state-lineage model for later binding to exact installer/twin evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

RELEASE_SCHEMA = "FRANKENSTEIN2_RELEASE_IDENTITY/v1"
STATE_SCHEMA = "FRANKENSTEIN2_DURABLE_STATE_LINEAGE/v1"
REQUEST_SCHEMA = "FRANKENSTEIN2_PORTABLE_RELEASE_TRANSACTION_REQUEST/v1"
PLAN_SCHEMA = "FRANKENSTEIN2_PORTABLE_RELEASE_TRANSACTION_PLAN/v1"
RECEIPT_SCHEMA = "FRANKENSTEIN2_PORTABLE_RELEASE_TRANSACTION_RECEIPT/v1"

INSTALL = "INSTALL"
UPDATE = "UPDATE"
ROLLBACK = "ROLLBACK"
OPERATIONS = frozenset({INSTALL, UPDATE, ROLLBACK})
FAILURE_STAGES = frozenset({"PREFLIGHT", "STAGE", "MIGRATE", "ACTIVATE", "VERIFY"})
APPLIED = "APPLIED"
FAILED = "FAILED"
ROLLED_BACK = "ROLLED_BACK"
EVIDENCE_SCOPE = "HOSTILE_TWIN_TRANSACTION_COMPONENT_ONLY_NO_TARGET_OR_COMPLETION_CREDIT"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_MAX_GENERATION = 2**63 - 1


class PortableReleaseTransactionError(ValueError):
    """Fail-closed validation error for this noncanonical component."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise PortableReleaseTransactionError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_TEXT or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PortableReleaseTransactionError(f"{name} is not an admissible identifier")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise PortableReleaseTransactionError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_GENERATION:
        raise PortableReleaseTransactionError(f"{name} must be a bounded nonnegative integer")
    return value


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PortableReleaseTransactionError("value is not canonical JSON-safe data") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ReleaseIdentity:
    schema: str
    release_id: str
    zip_sha256: str

    def __post_init__(self) -> None:
        if self.schema != RELEASE_SCHEMA:
            raise PortableReleaseTransactionError("release schema mismatch")
        object.__setattr__(self, "release_id", _text("release_id", self.release_id))
        object.__setattr__(self, "zip_sha256", _sha("zip_sha256", self.zip_sha256))

    @classmethod
    def create(cls, *, release_id: str, zip_sha256: str) -> "ReleaseIdentity":
        return cls(RELEASE_SCHEMA, release_id, zip_sha256)

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "release_id": self.release_id, "zip_sha256": self.zip_sha256}


@dataclass(frozen=True, slots=True)
class StateLineage:
    schema: str
    lineage_id: str
    generation: int
    state_digest: str

    def __post_init__(self) -> None:
        if self.schema != STATE_SCHEMA:
            raise PortableReleaseTransactionError("state schema mismatch")
        object.__setattr__(self, "lineage_id", _text("lineage_id", self.lineage_id))
        object.__setattr__(self, "generation", _generation("generation", self.generation))
        object.__setattr__(self, "state_digest", _sha("state_digest", self.state_digest))

    @classmethod
    def create(cls, *, lineage_id: str, generation: int, state_digest: str) -> "StateLineage":
        return cls(STATE_SCHEMA, lineage_id, generation, state_digest)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "lineage_id": self.lineage_id,
            "generation": self.generation,
            "state_digest": self.state_digest,
        }


def _release(value: ReleaseIdentity | None) -> dict[str, Any] | None:
    return None if value is None else value.as_dict()


def _state(value: StateLineage | None) -> dict[str, Any] | None:
    return None if value is None else value.as_dict()


@dataclass(frozen=True, slots=True)
class TransactionRequest:
    schema: str
    operation: str
    target_release: ReleaseIdentity
    expected_result_state: StateLineage
    current_release: ReleaseIdentity | None = None
    current_state: StateLineage | None = None
    rollback_source_release: ReleaseIdentity | None = None
    rollback_source_state: StateLineage | None = None
    failure_stage: str | None = None

    def __post_init__(self) -> None:
        if self.schema != REQUEST_SCHEMA or self.operation not in OPERATIONS:
            raise PortableReleaseTransactionError("request schema or operation mismatch")
        if not isinstance(self.target_release, ReleaseIdentity) or not isinstance(self.expected_result_state, StateLineage):
            raise PortableReleaseTransactionError("target release/result state must be typed identities")
        if self.failure_stage is not None and self.failure_stage not in FAILURE_STAGES:
            raise PortableReleaseTransactionError("unsupported failure stage")
        if (self.current_release is None) != (self.current_state is None):
            raise PortableReleaseTransactionError("current release/state must be supplied together")
        if (self.rollback_source_release is None) != (self.rollback_source_state is None):
            raise PortableReleaseTransactionError("rollback source release/state must be supplied together")
        self._validate_semantics()

    @classmethod
    def create(cls, **kwargs: Any) -> "TransactionRequest":
        return cls(schema=REQUEST_SCHEMA, **kwargs)

    def _validate_semantics(self) -> None:
        if self.operation == INSTALL:
            if self.current_release is not None or self.rollback_source_release is not None:
                raise PortableReleaseTransactionError("fresh INSTALL cannot carry prior state")
            if self.expected_result_state.generation != 0:
                raise PortableReleaseTransactionError("fresh INSTALL result generation must be zero")
            return

        if self.current_release is None or self.current_state is None:
            raise PortableReleaseTransactionError(f"{self.operation} requires exact current release/state")
        if self.expected_result_state.lineage_id != self.current_state.lineage_id:
            raise PortableReleaseTransactionError("transaction cannot change durable lineage_id")
        if self.current_state.generation == _MAX_GENERATION:
            raise PortableReleaseTransactionError("state generation exhausted")
        if self.expected_result_state.generation != self.current_state.generation + 1:
            raise PortableReleaseTransactionError("result generation must advance exactly once")

        if self.operation == UPDATE:
            if self.target_release == self.current_release:
                raise PortableReleaseTransactionError("UPDATE target must differ from current release")
            if self.rollback_source_release is not None:
                raise PortableReleaseTransactionError("UPDATE cannot predeclare rollback source")
            return

        if self.rollback_source_release is None or self.rollback_source_state is None:
            raise PortableReleaseTransactionError("ROLLBACK requires exact rollback source")
        if self.target_release != self.rollback_source_release:
            raise PortableReleaseTransactionError("ROLLBACK target must equal rollback source release")
        if self.rollback_source_state.lineage_id != self.current_state.lineage_id:
            raise PortableReleaseTransactionError("ROLLBACK source must share durable lineage")
        if self.rollback_source_state.generation >= self.current_state.generation:
            raise PortableReleaseTransactionError("ROLLBACK source must be an older generation")
        if self.expected_result_state.state_digest != self.rollback_source_state.state_digest:
            raise PortableReleaseTransactionError("ROLLBACK must restore exact source state digest")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "operation": self.operation,
            "target_release": self.target_release.as_dict(),
            "expected_result_state": self.expected_result_state.as_dict(),
            "current_release": _release(self.current_release),
            "current_state": _state(self.current_state),
            "rollback_source_release": _release(self.rollback_source_release),
            "rollback_source_state": _state(self.rollback_source_state),
            "failure_stage": self.failure_stage,
        }


@dataclass(frozen=True, slots=True)
class TransactionPlan:
    schema: str
    transaction_id: str
    request_digest: str
    request: TransactionRequest
    evidence_scope: str = EVIDENCE_SCOPE

    def __post_init__(self) -> None:
        if self.schema != PLAN_SCHEMA or self.evidence_scope != EVIDENCE_SCOPE:
            raise PortableReleaseTransactionError("plan schema/evidence scope mismatch")
        _text("transaction_id", self.transaction_id)
        _sha("request_digest", self.request_digest)
        if not isinstance(self.request, TransactionRequest):
            raise PortableReleaseTransactionError("plan request must be TransactionRequest")
        expected = _digest(self.request.as_dict())
        if self.request_digest != expected or self.transaction_id != f"portable-txn:{expected}":
            raise PortableReleaseTransactionError("plan identity binding mismatch")


def compile_transaction(request: TransactionRequest) -> TransactionPlan:
    if not isinstance(request, TransactionRequest):
        raise PortableReleaseTransactionError("request must be TransactionRequest")
    request_digest = _digest(request.as_dict())
    return TransactionPlan(PLAN_SCHEMA, f"portable-txn:{request_digest}", request_digest, request)


@dataclass(frozen=True, slots=True)
class TransactionReceipt:
    schema: str
    transaction_id: str
    outcome: str
    failure_stage: str | None
    final_release: ReleaseIdentity | None
    final_state: StateLineage | None
    receipt_digest: str
    evidence_scope: str = EVIDENCE_SCOPE
    physical_target_credit: int = 0
    runtime_credit: int = 0
    completion_credit: int = 0

    def __post_init__(self) -> None:
        if self.schema != RECEIPT_SCHEMA or self.outcome not in {APPLIED, FAILED, ROLLED_BACK}:
            raise PortableReleaseTransactionError("receipt schema/outcome mismatch")
        if self.evidence_scope != EVIDENCE_SCOPE:
            raise PortableReleaseTransactionError("receipt evidence scope mismatch")
        if any(v != 0 for v in (self.physical_target_credit, self.runtime_credit, self.completion_credit)):
            raise PortableReleaseTransactionError("component receipt cannot mint higher-scope credit")
        _sha("receipt_digest", self.receipt_digest)
        if self.receipt_digest != _digest(self.identity_payload()):
            raise PortableReleaseTransactionError("receipt identity binding mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "outcome": self.outcome,
            "failure_stage": self.failure_stage,
            "final_release": _release(self.final_release),
            "final_state": _state(self.final_state),
            "evidence_scope": self.evidence_scope,
            "physical_target_credit": self.physical_target_credit,
            "runtime_credit": self.runtime_credit,
            "completion_credit": self.completion_credit,
        }


def _receipt(plan: TransactionPlan, outcome: str, failure_stage: str | None,
             final_release: ReleaseIdentity | None, final_state: StateLineage | None) -> TransactionReceipt:
    payload = {
        "transaction_id": plan.transaction_id,
        "outcome": outcome,
        "failure_stage": failure_stage,
        "final_release": _release(final_release),
        "final_state": _state(final_state),
        "evidence_scope": EVIDENCE_SCOPE,
        "physical_target_credit": 0,
        "runtime_credit": 0,
        "completion_credit": 0,
    }
    return TransactionReceipt(RECEIPT_SCHEMA, plan.transaction_id, outcome, failure_stage,
                              final_release, final_state, _digest(payload))


def simulate_hostile_twin_transaction(plan: TransactionPlan) -> TransactionReceipt:
    """Project a transaction deterministically without performing any real effect."""
    if not isinstance(plan, TransactionPlan):
        raise PortableReleaseTransactionError("plan must be TransactionPlan")
    plan = TransactionPlan(plan.schema, plan.transaction_id, plan.request_digest, plan.request, plan.evidence_scope)
    request = plan.request
    if request.failure_stage is None:
        return _receipt(plan, APPLIED, None, request.target_release, request.expected_result_state)
    if request.failure_stage in {"PREFLIGHT", "STAGE", "MIGRATE"}:
        return _receipt(plan, FAILED, request.failure_stage, request.current_release, request.current_state)
    if request.current_release is None or request.current_state is None:
        return _receipt(plan, FAILED, request.failure_stage, None, None)
    return _receipt(plan, ROLLED_BACK, request.failure_stage, request.current_release, request.current_state)
