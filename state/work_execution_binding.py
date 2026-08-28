"""Frankenstein 2.0 F2-WP-102 work-execution identity binding contract.

This module is intentionally a pure identity/validation layer. It does not spawn a child,
call a model/provider, execute a tool, mutate UnifiedDB, authorize an effect, or mint
completion. It binds an already-observed workpackage generation to an already-observed tool
invocation, child execution identity, and result identity so later persistence/effect layers
can reject cross-talk and stale-generation attribution.

Truth boundary:
    workpackage != invocation
    invocation != child execution
    child execution != result
    result outcome != completion
    UNKNOWN != SUCCESS
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re
from typing import Any, Mapping

SCHEMA = "FRANKENSTEIN2_WORK_EXECUTION_BINDING/v1"
RESULT_SCHEMA = "FRANKENSTEIN2_WORK_EXECUTION_RESULT_BINDING/v1"
OUTCOMES = frozenset({"SUCCESS", "FAILURE", "REJECTED", "UNKNOWN"})
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class WorkExecutionBindingError(ValueError):
    """Fail-closed identity/binding validation error."""


def _canon(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(_canon(value).encode("utf-8")).hexdigest()


def _id(name: str, value: object) -> str:
    text = str(value or "").strip()
    if not _ID_RE.fullmatch(text):
        raise WorkExecutionBindingError(f"INVALID_{name.upper()}")
    return text


def _generation(value: object) -> int:
    if isinstance(value, bool):
        raise WorkExecutionBindingError("INVALID_GENERATION")
    try:
        generation = int(value)
    except (TypeError, ValueError) as exc:
        raise WorkExecutionBindingError("INVALID_GENERATION") from exc
    if generation < 1 or str(generation) != str(value).strip():
        raise WorkExecutionBindingError("INVALID_GENERATION")
    return generation


def _sha256(name: str, value: object) -> str:
    text = str(value or "").strip().lower()
    if not _SHA256_RE.fullmatch(text):
        raise WorkExecutionBindingError(f"INVALID_{name.upper()}_SHA256")
    return text


@dataclass(frozen=True)
class WorkExecutionBinding:
    schema: str
    binding_id: str
    workpackage_id: str
    generation: int
    claim_id: str
    causal_id: str
    invocation_id: str
    tool_use_id: str
    child_agent_id: str
    child_execution_id: str
    identity_provenance: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canon(self.to_dict())


@dataclass(frozen=True)
class WorkExecutionResultBinding:
    schema: str
    result_binding_id: str
    binding_id: str
    workpackage_id: str
    generation: int
    claim_id: str
    causal_id: str
    invocation_id: str
    tool_use_id: str
    child_agent_id: str
    child_execution_id: str
    result_id: str
    outcome: str
    result_sha256: str
    result_provenance: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canon(self.to_dict())

    @property
    def is_success_result(self) -> bool:
        """SUCCESS is only a result classification; it is never completion authority here."""
        return self.outcome == "SUCCESS"


def make_binding(
    *,
    workpackage_id: object,
    generation: object,
    claim_id: object,
    causal_id: object,
    invocation_id: object,
    tool_use_id: object,
    child_agent_id: object,
    child_execution_id: object,
    identity_provenance: object,
) -> WorkExecutionBinding:
    """Build a deterministic binding from identities the caller actually observed.

    The deterministic binding id excludes timestamps and process-local state so replay of the
    same causal identity tuple yields the same identity. Any tool/child/generation change must
    yield a distinct binding id.
    """
    core = {
        "schema": SCHEMA,
        "workpackage_id": _id("workpackage_id", workpackage_id),
        "generation": _generation(generation),
        "claim_id": _id("claim_id", claim_id),
        "causal_id": _id("causal_id", causal_id),
        "invocation_id": _id("invocation_id", invocation_id),
        "tool_use_id": _id("tool_use_id", tool_use_id),
        "child_agent_id": _id("child_agent_id", child_agent_id),
        "child_execution_id": _id("child_execution_id", child_execution_id),
        "identity_provenance": _id("identity_provenance", identity_provenance),
    }
    binding_id = "wex:" + _digest(core)
    return WorkExecutionBinding(binding_id=binding_id, **core)


def bind_result(
    binding: WorkExecutionBinding,
    *,
    result_id: object,
    outcome: object,
    result_sha256: object,
    result_provenance: object,
    expected_workpackage_id: object | None = None,
    expected_generation: object | None = None,
    expected_claim_id: object | None = None,
    expected_causal_id: object | None = None,
    expected_invocation_id: object | None = None,
    expected_tool_use_id: object | None = None,
    expected_child_agent_id: object | None = None,
    expected_child_execution_id: object | None = None,
) -> WorkExecutionResultBinding:
    """Bind one observed result to the exact existing work-execution identity.

    Optional expected_* arguments are fail-closed guards for callers carrying a current
    WorkPackage/Causal context. A mismatch is rejected rather than re-attributed.
    """
    checks = {
        "workpackage_id": expected_workpackage_id,
        "generation": expected_generation,
        "claim_id": expected_claim_id,
        "causal_id": expected_causal_id,
        "invocation_id": expected_invocation_id,
        "tool_use_id": expected_tool_use_id,
        "child_agent_id": expected_child_agent_id,
        "child_execution_id": expected_child_execution_id,
    }
    for field, expected in checks.items():
        if expected is None:
            continue
        actual = getattr(binding, field)
        normalized = _generation(expected) if field == "generation" else _id(field, expected)
        if actual != normalized:
            raise WorkExecutionBindingError(f"{field.upper()}_MISMATCH")

    outcome_text = str(outcome or "").upper().strip()
    if outcome_text not in OUTCOMES:
        raise WorkExecutionBindingError("INVALID_OUTCOME")

    result_core = {
        "schema": RESULT_SCHEMA,
        "binding_id": binding.binding_id,
        "workpackage_id": binding.workpackage_id,
        "generation": binding.generation,
        "claim_id": binding.claim_id,
        "causal_id": binding.causal_id,
        "invocation_id": binding.invocation_id,
        "tool_use_id": binding.tool_use_id,
        "child_agent_id": binding.child_agent_id,
        "child_execution_id": binding.child_execution_id,
        "result_id": _id("result_id", result_id),
        "outcome": outcome_text,
        "result_sha256": _sha256("result", result_sha256),
        "result_provenance": _id("result_provenance", result_provenance),
    }
    result_binding_id = "wexr:" + _digest(result_core)
    return WorkExecutionResultBinding(result_binding_id=result_binding_id, **result_core)


def validate_binding_dict(payload: Mapping[str, Any]) -> WorkExecutionBinding:
    """Strictly parse a serialized binding; reject unknown/authority-like fields."""
    allowed = {
        "schema", "binding_id", "workpackage_id", "generation", "claim_id", "causal_id",
        "invocation_id", "tool_use_id", "child_agent_id", "child_execution_id",
        "identity_provenance",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise WorkExecutionBindingError("UNKNOWN_FIELDS:" + ",".join(unknown))
    if payload.get("schema") != SCHEMA:
        raise WorkExecutionBindingError("SCHEMA_MISMATCH")
    rebuilt = make_binding(
        workpackage_id=payload.get("workpackage_id"),
        generation=payload.get("generation"),
        claim_id=payload.get("claim_id"),
        causal_id=payload.get("causal_id"),
        invocation_id=payload.get("invocation_id"),
        tool_use_id=payload.get("tool_use_id"),
        child_agent_id=payload.get("child_agent_id"),
        child_execution_id=payload.get("child_execution_id"),
        identity_provenance=payload.get("identity_provenance"),
    )
    if payload.get("binding_id") != rebuilt.binding_id:
        raise WorkExecutionBindingError("BINDING_ID_MISMATCH")
    return rebuilt


__all__ = [
    "OUTCOMES",
    "RESULT_SCHEMA",
    "SCHEMA",
    "WorkExecutionBinding",
    "WorkExecutionBindingError",
    "WorkExecutionResultBinding",
    "bind_result",
    "make_binding",
    "validate_binding_dict",
]
