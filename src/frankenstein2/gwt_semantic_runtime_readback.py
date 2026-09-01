"""Fail-closed semantic readback above accepted WP900 G4/G5 evidence.

F2-WP-900 generation 6.

G4 deliberately proves only a matched intervention/control causal effect at a
contract/hash boundary.  Executed REVIEW_ONLY counterevidence in PR #884 shows
that byte-distinct JSON serializations of the same parsed value can still make
that contract evaluator report downstream inequality.  That is not a defect in
G4's accepted scope, but it blocks semantic GWT/J-Space promotion.

This module adds the smallest successor ABI needed to remove that ambiguity:

* every arm is observed from the exact raw downstream bytes;
* raw bytes must hash to the downstream SHA already bound by the accepted G4
  candidate;
* both arms bind exact source, boot and execution-context identities;
* both arms declare task and outcome schemas;
* JSON is parsed fail-closed (duplicate keys and non-finite constants reject),
  then canonicalized for one explicit structural-semantic representation;
* equal canonical semantic representations are classified as semantic
  equivalence, never semantic causal difference;
* incompatible task/outcome schemas return first-class UNKNOWN rather than a
  positive semantic claim.

The object produced here is still only a repository/runtime evidence candidate.
It never mints semantic GWT/J-Space, target-runtime, effect, training,
completion or whole-system credit.  Exact admitted VPS execution and separate
reconciliation remain required for any higher promotion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.gwt_causal_runtime_readback import (
    GwtCausalRuntimeReadbackCandidate,
    validate_causal_runtime_readback,
)

SEMANTIC_ARM_READBACK_SCHEMA = "FRANKENSTEIN2_GWT_SEMANTIC_ARM_READBACK/v1"
SEMANTIC_CAUSAL_READBACK_SCHEMA = "FRANKENSTEIN2_GWT_SEMANTIC_CAUSAL_READBACK/v1"
SEMANTIC_EQUIVALENCE_OBSERVED = "SEMANTIC_EQUIVALENCE_OBSERVED"
SEMANTIC_DIFFERENCE_OBSERVED = "SEMANTIC_DIFFERENCE_OBSERVED_CANDIDATE"
SEMANTIC_COMPARISON_UNKNOWN = "SEMANTIC_COMPARISON_UNKNOWN"
NO_SEMANTIC_CAUSAL_DIFFERENCE = "NO_SEMANTIC_CAUSAL_DIFFERENCE_OBSERVED"
SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE = "SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE_REQUIRES_TARGET_EXECUTION_ADMISSION"
SEMANTIC_UNKNOWN_FAIL_CLOSED = "SEMANTIC_COMPARISON_UNKNOWN_FAIL_CLOSED"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_MAX_RAW_BYTES = 1_048_576
_MAX_CANONICAL_JSON = 65_536
_ARM_FACTORY = object()
_BOUND_FACTORY = object()


class GwtSemanticRuntimeReadbackError(ValueError):
    """Fail-closed WP900 G6 semantic-readback error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise GwtSemanticRuntimeReadbackError(f"{name} must be non-empty trimmed text")
    if len(value) > _MAX_TEXT:
        raise GwtSemanticRuntimeReadbackError(f"{name} exceeds {_MAX_TEXT} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GwtSemanticRuntimeReadbackError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise GwtSemanticRuntimeReadbackError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 1:
        raise GwtSemanticRuntimeReadbackError(f"{name} must be a positive integer")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GwtSemanticRuntimeReadbackError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance_ref", value) for value in values)
    if not refs:
        raise GwtSemanticRuntimeReadbackError("provenance_refs must not be empty")
    if len(set(refs)) != len(refs):
        raise GwtSemanticRuntimeReadbackError("provenance_refs must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise GwtSemanticRuntimeReadbackError("semantic value is not canonical-JSON encodable") from exc
    if len(encoded.encode("utf-8")) > _MAX_CANONICAL_JSON:
        raise GwtSemanticRuntimeReadbackError("canonical semantic JSON exceeds size bound")
    return encoded


def _digest_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reject_constant(value: str) -> None:
    raise GwtSemanticRuntimeReadbackError(f"non-finite JSON constant is not admissible: {value}")


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GwtSemanticRuntimeReadbackError(f"duplicate JSON key is not admissible: {key}")
        result[key] = value
    return result


def _parse_json(raw_payload: bytes) -> Any:
    if type(raw_payload) is not bytes or not raw_payload:
        raise GwtSemanticRuntimeReadbackError("raw_payload must be non-empty exact bytes")
    if len(raw_payload) > _MAX_RAW_BYTES:
        raise GwtSemanticRuntimeReadbackError("raw_payload exceeds size bound")
    try:
        text = raw_payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GwtSemanticRuntimeReadbackError("raw_payload must be UTF-8 JSON") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_without_duplicates,
            parse_constant=_reject_constant,
        )
    except GwtSemanticRuntimeReadbackError:
        raise
    except json.JSONDecodeError as exc:
        raise GwtSemanticRuntimeReadbackError("raw_payload is not valid JSON") from exc


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticArmReadback:
    """One factory-observed downstream payload with explicit structural semantics."""

    condition: str
    task_id: str
    task_schema: str
    outcome_schema: str
    downstream_ref: str
    downstream_sha256: str
    semantic_canonical_json: str
    semantic_sha256: str
    exact_source_sha256: str
    boot_id_sha256: str
    execution_context_sha256: str
    producer_identity: str
    runtime_instance_id: str
    observed_monotonic_ns: int
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, init=False, repr=False, compare=False, hash=False)

    schema = SEMANTIC_ARM_READBACK_SCHEMA
    semantic_scope = "CANONICAL_JSON_STRUCTURAL_SEMANTICS"

    def __post_init__(self) -> None:
        if self.condition not in {"INTERVENTION_BROADCAST", "CONTROL_NO_BROADCAST"}:
            raise GwtSemanticRuntimeReadbackError("condition must be INTERVENTION_BROADCAST or CONTROL_NO_BROADCAST")
        for name in (
            "task_id",
            "task_schema",
            "outcome_schema",
            "downstream_ref",
            "producer_identity",
            "runtime_instance_id",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "downstream_sha256",
            "semantic_sha256",
            "exact_source_sha256",
            "boot_id_sha256",
            "execution_context_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if type(self.semantic_canonical_json) is not str or not self.semantic_canonical_json:
            raise GwtSemanticRuntimeReadbackError("semantic_canonical_json must be non-empty text")
        parsed = _parse_json(self.semantic_canonical_json.encode("utf-8"))
        canonical = _canonical_json(parsed)
        if canonical != self.semantic_canonical_json:
            raise GwtSemanticRuntimeReadbackError("semantic_canonical_json is not canonical")
        if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != self.semantic_sha256:
            raise GwtSemanticRuntimeReadbackError("semantic_sha256 does not bind canonical semantic JSON")
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @classmethod
    def observe_json(
        cls,
        *,
        condition: str,
        task_id: str,
        task_schema: str,
        outcome_schema: str,
        downstream_ref: str,
        expected_downstream_sha256: str,
        raw_payload: bytes,
        exact_source_sha256: str,
        boot_id_sha256: str,
        execution_context_sha256: str,
        producer_identity: str,
        runtime_instance_id: str,
        observed_monotonic_ns: int,
        provenance_refs: Iterable[str],
    ) -> "SemanticArmReadback":
        expected_downstream_sha256 = _sha256("expected_downstream_sha256", expected_downstream_sha256)
        if type(raw_payload) is not bytes:
            raise GwtSemanticRuntimeReadbackError("raw_payload must be exact bytes")
        raw_sha256 = hashlib.sha256(raw_payload).hexdigest()
        if raw_sha256 != expected_downstream_sha256:
            raise GwtSemanticRuntimeReadbackError("raw payload does not match accepted downstream SHA-256")
        semantic_value = _parse_json(raw_payload)
        canonical = _canonical_json(semantic_value)
        value = cls(
            condition=condition,
            task_id=task_id,
            task_schema=task_schema,
            outcome_schema=outcome_schema,
            downstream_ref=downstream_ref,
            downstream_sha256=raw_sha256,
            semantic_canonical_json=canonical,
            semantic_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            exact_source_sha256=exact_source_sha256,
            boot_id_sha256=boot_id_sha256,
            execution_context_sha256=execution_context_sha256,
            producer_identity=producer_identity,
            runtime_instance_id=runtime_instance_id,
            observed_monotonic_ns=observed_monotonic_ns,
            provenance_refs=tuple(provenance_refs),
        )
        object.__setattr__(value, "_factory_seal", _ARM_FACTORY)
        object.__setattr__(value, "_factory_payload_sha256", _digest_json(value.as_dict()))
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "semantic_scope": self.semantic_scope,
            "condition": self.condition,
            "task_id": self.task_id,
            "task_schema": self.task_schema,
            "outcome_schema": self.outcome_schema,
            "downstream_ref": self.downstream_ref,
            "downstream_sha256": self.downstream_sha256,
            "semantic_canonical_json": self.semantic_canonical_json,
            "semantic_sha256": self.semantic_sha256,
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "execution_context_sha256": self.execution_context_sha256,
            "producer_identity": self.producer_identity,
            "runtime_instance_id": self.runtime_instance_id,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest_json(self.as_dict())


def validate_semantic_arm_readback(value: SemanticArmReadback) -> None:
    if type(value) is not SemanticArmReadback or value._factory_seal is not _ARM_FACTORY:
        raise GwtSemanticRuntimeReadbackError("semantic arm lacks observation-factory origin")
    if value._factory_payload_sha256 != _digest_json(value.as_dict()):
        raise GwtSemanticRuntimeReadbackError("semantic arm payload changed after observation")


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticCausalReadbackCandidate:
    """Semantic comparison candidate; never authority or promotion by construction."""

    contract_candidate_sha256: str
    exact_source_sha256: str
    boot_id_sha256: str
    execution_context_sha256: str
    intervention_arm_sha256: str
    control_arm_sha256: str
    task_id: str
    intervention_task_schema: str
    control_task_schema: str
    intervention_outcome_schema: str
    control_outcome_schema: str
    intervention_semantic_sha256: str
    control_semantic_sha256: str
    comparison_status: str
    classification: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, init=False, repr=False, compare=False, hash=False)

    schema = SEMANTIC_CAUSAL_READBACK_SCHEMA
    evidence_scope = "SEMANTIC_CAUSAL_READBACK_CANDIDATE_REQUIRES_EXACT_TARGET_EXECUTION_ADMISSION"
    semantic_scope = "CANONICAL_JSON_STRUCTURAL_SEMANTICS"
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    runtime_credit = 0
    gwt_runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    physical_grid10_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        for name in (
            "contract_candidate_sha256",
            "exact_source_sha256",
            "boot_id_sha256",
            "execution_context_sha256",
            "intervention_arm_sha256",
            "control_arm_sha256",
            "intervention_semantic_sha256",
            "control_semantic_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        for name in (
            "task_id",
            "intervention_task_schema",
            "control_task_schema",
            "intervention_outcome_schema",
            "control_outcome_schema",
            "comparison_status",
            "classification",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        allowed = {
            SEMANTIC_EQUIVALENCE_OBSERVED: NO_SEMANTIC_CAUSAL_DIFFERENCE,
            SEMANTIC_DIFFERENCE_OBSERVED: SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE,
            SEMANTIC_COMPARISON_UNKNOWN: SEMANTIC_UNKNOWN_FAIL_CLOSED,
        }
        if self.comparison_status not in allowed:
            raise GwtSemanticRuntimeReadbackError("unknown semantic comparison status")
        if self.classification != allowed[self.comparison_status]:
            raise GwtSemanticRuntimeReadbackError("semantic comparison classification/status mismatch")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "evidence_scope": self.evidence_scope,
            "semantic_scope": self.semantic_scope,
            "contract_candidate_sha256": self.contract_candidate_sha256,
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "execution_context_sha256": self.execution_context_sha256,
            "intervention_arm_sha256": self.intervention_arm_sha256,
            "control_arm_sha256": self.control_arm_sha256,
            "task_id": self.task_id,
            "intervention_task_schema": self.intervention_task_schema,
            "control_task_schema": self.control_task_schema,
            "intervention_outcome_schema": self.intervention_outcome_schema,
            "control_outcome_schema": self.control_outcome_schema,
            "intervention_semantic_sha256": self.intervention_semantic_sha256,
            "control_semantic_sha256": self.control_semantic_sha256,
            "comparison_status": self.comparison_status,
            "classification": self.classification,
            "provenance_refs": list(self.provenance_refs),
            "repository_ci_credit": self.repository_ci_credit,
            "target_environment_component_runtime_credit": self.target_environment_component_runtime_credit,
            "runtime_credit": self.runtime_credit,
            "gwt_runtime_credit": self.gwt_runtime_credit,
            "semantic_gwt_runtime_credit": self.semantic_gwt_runtime_credit,
            "jspace_runtime_credit": self.jspace_runtime_credit,
            "physical_grid10_credit": self.physical_grid10_credit,
            "effect_credit": self.effect_credit,
            "training_credit": self.training_credit,
            "completion_credit": self.completion_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }

    def sha256(self) -> str:
        return _digest_json(self.as_dict())


def bind_semantic_causal_readback(
    *,
    contract_candidate: GwtCausalRuntimeReadbackCandidate,
    intervention: SemanticArmReadback,
    control: SemanticArmReadback,
    provenance_refs: Iterable[str],
) -> SemanticCausalReadbackCandidate:
    """Bind exact G4 arm bytes to explicit task/outcome semantics, fail closed."""

    if type(contract_candidate) is not GwtCausalRuntimeReadbackCandidate:
        raise GwtSemanticRuntimeReadbackError("contract_candidate must be exact GwtCausalRuntimeReadbackCandidate")
    try:
        validate_causal_runtime_readback(contract_candidate)
    except ValueError as exc:
        raise GwtSemanticRuntimeReadbackError(f"invalid G4 contract candidate: {exc}") from exc
    validate_semantic_arm_readback(intervention)
    validate_semantic_arm_readback(control)

    if intervention.condition != "INTERVENTION_BROADCAST":
        raise GwtSemanticRuntimeReadbackError("intervention arm condition mismatch")
    if control.condition != "CONTROL_NO_BROADCAST":
        raise GwtSemanticRuntimeReadbackError("control arm condition mismatch")

    for arm_name, arm in (("intervention", intervention), ("control", control)):
        if arm.exact_source_sha256 != contract_candidate.exact_source_sha256:
            raise GwtSemanticRuntimeReadbackError(f"{arm_name} exact-source identity mismatch")
        if arm.boot_id_sha256 != contract_candidate.boot_id_sha256:
            raise GwtSemanticRuntimeReadbackError(f"{arm_name} boot identity mismatch")
        if arm.execution_context_sha256 != contract_candidate.execution_context_sha256:
            raise GwtSemanticRuntimeReadbackError(f"{arm_name} execution-context identity mismatch")

    if intervention.downstream_ref != contract_candidate.intervention_downstream_ref:
        raise GwtSemanticRuntimeReadbackError("intervention downstream ref does not bind G4 candidate")
    if intervention.downstream_sha256 != contract_candidate.intervention_downstream_sha256:
        raise GwtSemanticRuntimeReadbackError("intervention downstream SHA does not bind G4 candidate")
    if control.downstream_ref != contract_candidate.control_downstream_ref:
        raise GwtSemanticRuntimeReadbackError("control downstream ref does not bind G4 candidate")
    if control.downstream_sha256 != contract_candidate.control_downstream_sha256:
        raise GwtSemanticRuntimeReadbackError("control downstream SHA does not bind G4 candidate")

    comparable = (
        intervention.task_id == control.task_id
        and intervention.task_schema == control.task_schema
        and intervention.outcome_schema == control.outcome_schema
    )
    if not comparable:
        status = SEMANTIC_COMPARISON_UNKNOWN
        classification = SEMANTIC_UNKNOWN_FAIL_CLOSED
    elif intervention.semantic_sha256 == control.semantic_sha256:
        status = SEMANTIC_EQUIVALENCE_OBSERVED
        classification = NO_SEMANTIC_CAUSAL_DIFFERENCE
    else:
        status = SEMANTIC_DIFFERENCE_OBSERVED
        classification = SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE

    value = SemanticCausalReadbackCandidate(
        contract_candidate_sha256=contract_candidate.sha256(),
        exact_source_sha256=contract_candidate.exact_source_sha256,
        boot_id_sha256=contract_candidate.boot_id_sha256,
        execution_context_sha256=contract_candidate.execution_context_sha256,
        intervention_arm_sha256=intervention.sha256(),
        control_arm_sha256=control.sha256(),
        task_id=intervention.task_id if intervention.task_id == control.task_id else "UNKNOWN_MISMATCHED_TASK_ID",
        intervention_task_schema=intervention.task_schema,
        control_task_schema=control.task_schema,
        intervention_outcome_schema=intervention.outcome_schema,
        control_outcome_schema=control.outcome_schema,
        intervention_semantic_sha256=intervention.semantic_sha256,
        control_semantic_sha256=control.semantic_sha256,
        comparison_status=status,
        classification=classification,
        provenance_refs=_refs(provenance_refs),
    )
    object.__setattr__(value, "_factory_seal", _BOUND_FACTORY)
    object.__setattr__(value, "_factory_payload_sha256", _digest_json(value.as_dict()))
    return value


def validate_semantic_causal_readback(value: SemanticCausalReadbackCandidate) -> None:
    if type(value) is not SemanticCausalReadbackCandidate or value._factory_seal is not _BOUND_FACTORY:
        raise GwtSemanticRuntimeReadbackError("semantic causal candidate lacks binder-factory origin")
    if value._factory_payload_sha256 != _digest_json(value.as_dict()):
        raise GwtSemanticRuntimeReadbackError("semantic causal candidate payload changed after bind")


__all__ = [
    "GwtSemanticRuntimeReadbackError",
    "NO_SEMANTIC_CAUSAL_DIFFERENCE",
    "SEMANTIC_ARM_READBACK_SCHEMA",
    "SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE",
    "SEMANTIC_CAUSAL_READBACK_SCHEMA",
    "SEMANTIC_COMPARISON_UNKNOWN",
    "SEMANTIC_DIFFERENCE_OBSERVED",
    "SEMANTIC_EQUIVALENCE_OBSERVED",
    "SEMANTIC_UNKNOWN_FAIL_CLOSED",
    "SemanticArmReadback",
    "SemanticCausalReadbackCandidate",
    "bind_semantic_causal_readback",
    "validate_semantic_arm_readback",
    "validate_semantic_causal_readback",
]
