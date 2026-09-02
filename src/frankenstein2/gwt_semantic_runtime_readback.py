"""Fail-closed semantic readback above accepted WP900 G4/G5 evidence.

F2-WP-900 generation 6 comparator plus the generation 7 shared-outcome
integration and generation 8 independent-observation binder.

G4 deliberately proves only a matched intervention/control causal effect at a
contract/hash boundary. Executed REVIEW_ONLY counterevidence in PR #884 shows
that byte-distinct JSON serializations of the same parsed value can still make
that contract evaluator report downstream inequality. That is not a defect in
G4's accepted scope, but it blocks semantic GWT/J-Space promotion.

The G6 comparator therefore remains fail-closed:

* every arm is observed from exact raw downstream bytes;
* raw bytes must hash to the downstream SHA already bound by the accepted G4
  candidate;
* both arms bind exact source, boot and execution-context identities;
* both arms declare task and outcome schemas;
* JSON is parsed fail-closed (duplicate keys and non-finite constants reject),
  then canonicalized for one explicit structural-semantic representation;
* equal canonical semantic representations are semantic equivalence;
* incompatible task/outcome schemas return first-class UNKNOWN.

G7 does not weaken or replace that comparator. It adds one factory-sealed
matched-task outcome receipt. The receipt preserves each arm's distinct raw
schema and exact G4 downstream bytes, then projects only the predeclared
REENTRY_OBSERVED predicate already established by the validated G4 causal
candidate into one shared semantic outcome schema. A caller cannot obtain this
projection merely by relabeling arbitrary raw bytes or forging source/boot/
execution-context identities.

G8 closes the remaining circularity in G7. It does not accept a caller-selected
arm condition as semantic evidence. Instead it accepts only the exact
factory-sealed G4 runtime-witness and no-broadcast-control observation objects
whose hashes are already bound by the accepted G4 causal candidate. The positive
predicate is derived from the validated DELIVERY -> UPTAKE -> REENTRY event
sequence; the negative predicate is derived from the validated no-broadcast
control readback. Exact source, boot, execution context, probe, broadcast,
recipient, input and observation hashes are re-bound before the existing
semantic comparator is invoked.

All objects remain evidence candidates. They never mint semantic GWT/J-Space,
target-runtime, effect, training, completion or whole-system credit by
construction. Exact admitted execution and separate reconciliation remain
required for higher promotion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.gwt_causal_runtime_readback import (
    ControlNoBroadcastReadback,
    GwtCausalRuntimeReadbackCandidate,
    validate_causal_runtime_readback,
    validate_control_no_broadcast_readback,
)
from frankenstein2.gwt_runtime_witness import (
    GwtRuntimeWitnessReceipt,
    LIVE_GWT_PATH_OBSERVED,
    validate_gwt_runtime_witness_receipt,
)

SEMANTIC_ARM_READBACK_SCHEMA = "FRANKENSTEIN2_GWT_SEMANTIC_ARM_READBACK/v1"
SEMANTIC_CAUSAL_READBACK_SCHEMA = "FRANKENSTEIN2_GWT_SEMANTIC_CAUSAL_READBACK/v1"
SEMANTIC_EQUIVALENCE_OBSERVED = "SEMANTIC_EQUIVALENCE_OBSERVED"
SEMANTIC_DIFFERENCE_OBSERVED = "SEMANTIC_DIFFERENCE_OBSERVED_CANDIDATE"
SEMANTIC_COMPARISON_UNKNOWN = "SEMANTIC_COMPARISON_UNKNOWN"
NO_SEMANTIC_CAUSAL_DIFFERENCE = "NO_SEMANTIC_CAUSAL_DIFFERENCE_OBSERVED"
SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE = "SEMANTIC_CAUSAL_DIFFERENCE_CANDIDATE_REQUIRES_TARGET_EXECUTION_ADMISSION"
SEMANTIC_UNKNOWN_FAIL_CLOSED = "SEMANTIC_COMPARISON_UNKNOWN_FAIL_CLOSED"

MATCHED_TASK_OUTCOME_READBACK_SCHEMA = "FRANKENSTEIN2_GWT_MATCHED_TASK_OUTCOME_READBACK/v1"
MATCHED_TASK_OUTCOME_SCHEMA = "FRANKENSTEIN2_GWT_MATCHED_REENTRY_OUTCOME/v1"
MATCHED_TASK_OUTCOME_PREDICATE = "REENTRY_OBSERVED"
WP900_MATCHED_TASK_SCHEMA = "F2_WP900_G4_MATCHED_CAUSAL_TASK/v1"
WP900_INTERVENTION_RAW_OUTCOME_SCHEMA = "FRANKENSTEIN2_GRID10_CELL_OUTPUT/v1"
WP900_CONTROL_RAW_OUTCOME_SCHEMA = "F2_WP900_G4_CONTROL_NO_BROADCAST_DOWNSTREAM/v1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_MAX_RAW_BYTES = 1_048_576
_MAX_CANONICAL_JSON = 65_536
_ARM_FACTORY = object()
_BOUND_FACTORY = object()
_MATCHED_OUTCOME_FACTORY = object()


class GwtSemanticRuntimeReadbackError(ValueError):
    """Fail-closed WP900 semantic-readback error."""


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
class MatchedTaskOutcomeReadback:
    """Factory-sealed G7 bridge from exact raw G4 bytes to one outcome predicate.

    ``raw_outcome_schema`` records the original condition-specific schema and is
    deliberately not rewritten to the shared semantic schema. The only value
    projected into :class:`SemanticArmReadback` is the G4-predeclared
    REENTRY_OBSERVED predicate. Exact source/boot/context and downstream
    identities are copied from the already validated G4 candidate rather than
    accepted from caller-controlled text.
    """

    condition: str
    task_id: str
    task_schema: str
    raw_outcome_schema: str
    downstream_ref: str
    downstream_sha256: str
    reentry_observed: bool
    exact_source_sha256: str
    boot_id_sha256: str
    execution_context_sha256: str
    producer_identity: str
    runtime_instance_id: str
    observed_monotonic_ns: int
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, init=False, repr=False, compare=False, hash=False)

    schema = MATCHED_TASK_OUTCOME_READBACK_SCHEMA
    outcome_schema = MATCHED_TASK_OUTCOME_SCHEMA
    predicate = MATCHED_TASK_OUTCOME_PREDICATE
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        if self.condition not in {"INTERVENTION_BROADCAST", "CONTROL_NO_BROADCAST"}:
            raise GwtSemanticRuntimeReadbackError("matched outcome condition is invalid")
        for name in (
            "task_id",
            "task_schema",
            "raw_outcome_schema",
            "downstream_ref",
            "producer_identity",
            "runtime_instance_id",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "downstream_sha256",
            "exact_source_sha256",
            "boot_id_sha256",
            "execution_context_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if type(self.reentry_observed) is not bool:
            raise GwtSemanticRuntimeReadbackError("reentry_observed must be boolean")
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @classmethod
    def observe_from_g4(
        cls,
        *,
        contract_candidate: GwtCausalRuntimeReadbackCandidate,
        condition: str,
        task_id: str,
        task_schema: str,
        raw_outcome_schema: str,
        raw_payload: bytes,
        producer_identity: str,
        runtime_instance_id: str,
        observed_monotonic_ns: int,
        provenance_refs: Iterable[str],
    ) -> "MatchedTaskOutcomeReadback":
        if type(contract_candidate) is not GwtCausalRuntimeReadbackCandidate:
            raise GwtSemanticRuntimeReadbackError("contract_candidate must be exact GwtCausalRuntimeReadbackCandidate")
        try:
            validate_causal_runtime_readback(contract_candidate)
        except ValueError as exc:
            raise GwtSemanticRuntimeReadbackError(f"invalid G4 contract candidate: {exc}") from exc
        if condition == "INTERVENTION_BROADCAST":
            downstream_ref = contract_candidate.intervention_downstream_ref
            expected_sha256 = contract_candidate.intervention_downstream_sha256
            expected_raw_schema = WP900_INTERVENTION_RAW_OUTCOME_SCHEMA
            reentry_observed = True
        elif condition == "CONTROL_NO_BROADCAST":
            downstream_ref = contract_candidate.control_downstream_ref
            expected_sha256 = contract_candidate.control_downstream_sha256
            expected_raw_schema = WP900_CONTROL_RAW_OUTCOME_SCHEMA
            reentry_observed = False
        else:
            raise GwtSemanticRuntimeReadbackError("matched outcome condition is invalid")
        task_schema = _text("task_schema", task_schema)
        if task_schema != WP900_MATCHED_TASK_SCHEMA:
            raise GwtSemanticRuntimeReadbackError("matched task schema does not bind the admitted WP900 task")
        raw_outcome_schema = _text("raw_outcome_schema", raw_outcome_schema)
        if raw_outcome_schema != expected_raw_schema:
            raise GwtSemanticRuntimeReadbackError("raw outcome schema does not match the admitted condition-specific schema")
        _parse_json(raw_payload)
        raw_sha256 = hashlib.sha256(raw_payload).hexdigest()
        if raw_sha256 != expected_sha256:
            raise GwtSemanticRuntimeReadbackError("raw payload does not match accepted G4 downstream SHA-256")
        value = cls(
            condition=condition,
            task_id=task_id,
            task_schema=task_schema,
            raw_outcome_schema=raw_outcome_schema,
            downstream_ref=downstream_ref,
            downstream_sha256=raw_sha256,
            reentry_observed=reentry_observed,
            exact_source_sha256=contract_candidate.exact_source_sha256,
            boot_id_sha256=contract_candidate.boot_id_sha256,
            execution_context_sha256=contract_candidate.execution_context_sha256,
            producer_identity=producer_identity,
            runtime_instance_id=runtime_instance_id,
            observed_monotonic_ns=observed_monotonic_ns,
            provenance_refs=tuple(provenance_refs),
        )
        object.__setattr__(value, "_factory_seal", _MATCHED_OUTCOME_FACTORY)
        object.__setattr__(value, "_factory_payload_sha256", _digest_json(value.as_dict()))
        return value

    def semantic_value(self) -> dict[str, Any]:
        return {
            "predicate": self.predicate,
            "observed": self.reentry_observed,
        }

    def to_semantic_arm(self) -> SemanticArmReadback:
        validate_matched_task_outcome_readback(self)
        canonical = _canonical_json(self.semantic_value())
        value = SemanticArmReadback(
            condition=self.condition,
            task_id=self.task_id,
            task_schema=self.task_schema,
            outcome_schema=self.outcome_schema,
            downstream_ref=self.downstream_ref,
            downstream_sha256=self.downstream_sha256,
            semantic_canonical_json=canonical,
            semantic_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            exact_source_sha256=self.exact_source_sha256,
            boot_id_sha256=self.boot_id_sha256,
            execution_context_sha256=self.execution_context_sha256,
            producer_identity=self.producer_identity,
            runtime_instance_id=self.runtime_instance_id,
            observed_monotonic_ns=self.observed_monotonic_ns,
            provenance_refs=self.provenance_refs,
        )
        object.__setattr__(value, "_factory_seal", _ARM_FACTORY)
        object.__setattr__(value, "_factory_payload_sha256", _digest_json(value.as_dict()))
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "condition": self.condition,
            "task_id": self.task_id,
            "task_schema": self.task_schema,
            "raw_outcome_schema": self.raw_outcome_schema,
            "shared_outcome_schema": self.outcome_schema,
            "predicate": self.predicate,
            "downstream_ref": self.downstream_ref,
            "downstream_sha256": self.downstream_sha256,
            "reentry_observed": self.reentry_observed,
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "execution_context_sha256": self.execution_context_sha256,
            "producer_identity": self.producer_identity,
            "runtime_instance_id": self.runtime_instance_id,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "provenance_refs": list(self.provenance_refs),
            "repository_ci_credit": self.repository_ci_credit,
            "target_environment_component_runtime_credit": self.target_environment_component_runtime_credit,
            "semantic_gwt_runtime_credit": self.semantic_gwt_runtime_credit,
            "jspace_runtime_credit": self.jspace_runtime_credit,
            "effect_credit": self.effect_credit,
            "training_credit": self.training_credit,
            "completion_credit": self.completion_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }

    def sha256(self) -> str:
        return _digest_json(self.as_dict())


def validate_matched_task_outcome_readback(value: MatchedTaskOutcomeReadback) -> None:
    if type(value) is not MatchedTaskOutcomeReadback or value._factory_seal is not _MATCHED_OUTCOME_FACTORY:
        raise GwtSemanticRuntimeReadbackError("matched outcome lacks observation-factory origin")
    if value._factory_payload_sha256 != _digest_json(value.as_dict()):
        raise GwtSemanticRuntimeReadbackError("matched outcome payload changed after observation")


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


def _derived_reentry_semantic_arm(
    *,
    contract_candidate: GwtCausalRuntimeReadbackCandidate,
    condition: str,
    task_id: str,
    observed: bool,
    producer_identity: str,
    runtime_instance_id: str,
    observed_monotonic_ns: int,
    observation_ref: str,
    provenance_refs: tuple[str, ...],
) -> SemanticArmReadback:
    """Create one semantic arm only after G8 independently validates observation evidence."""

    if condition == "INTERVENTION_BROADCAST":
        downstream_ref = contract_candidate.intervention_downstream_ref
        downstream_sha256 = contract_candidate.intervention_downstream_sha256
    elif condition == "CONTROL_NO_BROADCAST":
        downstream_ref = contract_candidate.control_downstream_ref
        downstream_sha256 = contract_candidate.control_downstream_sha256
    else:
        raise GwtSemanticRuntimeReadbackError("independent observation condition is invalid")

    canonical = _canonical_json({
        "predicate": MATCHED_TASK_OUTCOME_PREDICATE,
        "observed": observed,
    })
    arm = SemanticArmReadback(
        condition=condition,
        task_id=task_id,
        task_schema=WP900_MATCHED_TASK_SCHEMA,
        outcome_schema=MATCHED_TASK_OUTCOME_SCHEMA,
        downstream_ref=downstream_ref,
        downstream_sha256=downstream_sha256,
        semantic_canonical_json=canonical,
        semantic_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        exact_source_sha256=contract_candidate.exact_source_sha256,
        boot_id_sha256=contract_candidate.boot_id_sha256,
        execution_context_sha256=contract_candidate.execution_context_sha256,
        producer_identity=producer_identity,
        runtime_instance_id=runtime_instance_id,
        observed_monotonic_ns=observed_monotonic_ns,
        provenance_refs=_refs((*provenance_refs, observation_ref)),
    )
    object.__setattr__(arm, "_factory_seal", _ARM_FACTORY)
    object.__setattr__(arm, "_factory_payload_sha256", _digest_json(arm.as_dict()))
    return arm


def bind_independent_reentry_evidence(
    *,
    contract_candidate: GwtCausalRuntimeReadbackCandidate,
    intervention_runtime_witness: GwtRuntimeWitnessReceipt,
    control_readback: ControlNoBroadcastReadback,
    task_id: str,
    provenance_refs: Iterable[str],
) -> SemanticCausalReadbackCandidate:
    """Bind non-circular G8 re-entry semantics from G4-bound observation objects.

    The caller supplies no semantic arm labels and no re-entry booleans. The
    positive value is derived from the recorder-origin runtime witness only
    after its exact hash and DELIVERY -> UPTAKE -> REENTRY lineage are checked.
    The negative value is derived from the factory-origin no-broadcast control
    readback only after its exact G4-bound hash and context identities are
    checked. The result remains a zero-credit semantic candidate.
    """

    if type(contract_candidate) is not GwtCausalRuntimeReadbackCandidate:
        raise GwtSemanticRuntimeReadbackError("contract_candidate must be exact GwtCausalRuntimeReadbackCandidate")
    try:
        validate_causal_runtime_readback(contract_candidate)
    except ValueError as exc:
        raise GwtSemanticRuntimeReadbackError(f"invalid G4 contract candidate: {exc}") from exc

    if type(intervention_runtime_witness) is not GwtRuntimeWitnessReceipt:
        raise GwtSemanticRuntimeReadbackError("intervention evidence must be exact GwtRuntimeWitnessReceipt")
    try:
        validate_gwt_runtime_witness_receipt(intervention_runtime_witness)
    except ValueError as exc:
        raise GwtSemanticRuntimeReadbackError(f"invalid intervention runtime witness: {exc}") from exc

    if type(control_readback) is not ControlNoBroadcastReadback:
        raise GwtSemanticRuntimeReadbackError("control evidence must be exact ControlNoBroadcastReadback")
    try:
        validate_control_no_broadcast_readback(control_readback)
    except ValueError as exc:
        raise GwtSemanticRuntimeReadbackError(f"invalid control readback: {exc}") from exc

    witness_sha256 = intervention_runtime_witness.sha256()
    control_sha256 = control_readback.sha256()
    if witness_sha256 != contract_candidate.runtime_witness_sha256:
        raise GwtSemanticRuntimeReadbackError("intervention runtime witness does not bind G4 runtime_witness_sha256")
    if control_sha256 != contract_candidate.control_readback_sha256:
        raise GwtSemanticRuntimeReadbackError("control readback does not bind G4 control_readback_sha256")

    witness_identity = intervention_runtime_witness.identity
    if witness_identity.exact_source_sha256 != contract_candidate.exact_source_sha256:
        raise GwtSemanticRuntimeReadbackError("intervention exact-source identity mismatch")
    if witness_identity.boot_id_sha256 != contract_candidate.boot_id_sha256:
        raise GwtSemanticRuntimeReadbackError("intervention boot identity mismatch")
    if intervention_runtime_witness.broadcast_id != contract_candidate.broadcast_id:
        raise GwtSemanticRuntimeReadbackError("intervention broadcast id does not bind G4 candidate")
    if intervention_runtime_witness.broadcast_sha256 != contract_candidate.broadcast_sha256:
        raise GwtSemanticRuntimeReadbackError("intervention broadcast SHA does not bind G4 candidate")
    if intervention_runtime_witness.recipient_cell_id != contract_candidate.recipient_cell_id:
        raise GwtSemanticRuntimeReadbackError("intervention recipient does not bind G4 candidate")
    if intervention_runtime_witness.uptake_receipt_sha256 != contract_candidate.uptake_receipt_sha256:
        raise GwtSemanticRuntimeReadbackError("intervention uptake receipt does not bind G4 candidate")

    if control_readback.exact_source_sha256 != contract_candidate.exact_source_sha256:
        raise GwtSemanticRuntimeReadbackError("control exact-source identity mismatch")
    if control_readback.boot_id_sha256 != contract_candidate.boot_id_sha256:
        raise GwtSemanticRuntimeReadbackError("control boot identity mismatch")
    if control_readback.execution_context_sha256 != contract_candidate.execution_context_sha256:
        raise GwtSemanticRuntimeReadbackError("control execution-context identity mismatch")
    if control_readback.probe_id != contract_candidate.probe_id:
        raise GwtSemanticRuntimeReadbackError("control probe id does not bind G4 candidate")
    if control_readback.nonbroadcast_input_sha256 != contract_candidate.nonbroadcast_input_sha256:
        raise GwtSemanticRuntimeReadbackError("control input does not bind G4 candidate")
    if control_readback.downstream_ref != contract_candidate.control_downstream_ref:
        raise GwtSemanticRuntimeReadbackError("control downstream ref does not bind G4 candidate")
    if control_readback.downstream_sha256 != contract_candidate.control_downstream_sha256:
        raise GwtSemanticRuntimeReadbackError("control downstream SHA does not bind G4 candidate")

    if intervention_runtime_witness.classification != LIVE_GWT_PATH_OBSERVED:
        raise GwtSemanticRuntimeReadbackError("intervention runtime witness did not observe live GWT path")
    delivery, uptake, reentry = intervention_runtime_witness.events
    if tuple(event.phase for event in intervention_runtime_witness.events) != ("DELIVERY", "UPTAKE", "REENTRY"):
        raise GwtSemanticRuntimeReadbackError("intervention event order is not DELIVERY -> UPTAKE -> REENTRY")
    if not (delivery.observed_monotonic_ns < uptake.observed_monotonic_ns < reentry.observed_monotonic_ns):
        raise GwtSemanticRuntimeReadbackError("intervention event order is not strictly monotonic")
    if delivery.object_id != intervention_runtime_witness.broadcast_id or delivery.object_sha256 != intervention_runtime_witness.broadcast_sha256:
        raise GwtSemanticRuntimeReadbackError("delivery event does not bind intervention broadcast")
    if uptake.object_id != intervention_runtime_witness.uptake_receipt_id or uptake.object_sha256 != intervention_runtime_witness.uptake_receipt_sha256:
        raise GwtSemanticRuntimeReadbackError("uptake event does not bind intervention uptake receipt")
    if reentry.object_id != intervention_runtime_witness.canonical_reentry_key or reentry.object_sha256 != intervention_runtime_witness.reentry_witness_sha256:
        raise GwtSemanticRuntimeReadbackError("re-entry event does not bind intervention re-entry witness")
    if control_readback.reentry_observed is not False:
        raise GwtSemanticRuntimeReadbackError("control observation did not preserve no-reentry result")

    task_id = _text("task_id", task_id)
    base_refs = _refs(provenance_refs)
    witness_ref = f"g4-runtime-witness-sha256:{witness_sha256}"
    control_ref = f"g4-control-readback-sha256:{control_sha256}"

    intervention_arm = _derived_reentry_semantic_arm(
        contract_candidate=contract_candidate,
        condition="INTERVENTION_BROADCAST",
        task_id=task_id,
        observed=True,
        producer_identity=witness_identity.process_identity,
        runtime_instance_id=witness_identity.runtime_instance_id,
        observed_monotonic_ns=reentry.observed_monotonic_ns,
        observation_ref=witness_ref,
        provenance_refs=base_refs,
    )
    control_arm = _derived_reentry_semantic_arm(
        contract_candidate=contract_candidate,
        condition="CONTROL_NO_BROADCAST",
        task_id=task_id,
        observed=False,
        producer_identity=control_readback.process_identity,
        runtime_instance_id=control_readback.runtime_instance_id,
        observed_monotonic_ns=control_readback.observed_monotonic_ns,
        observation_ref=control_ref,
        provenance_refs=base_refs,
    )

    return bind_semantic_causal_readback(
        contract_candidate=contract_candidate,
        intervention=intervention_arm,
        control=control_arm,
        provenance_refs=_refs((*base_refs, witness_ref, control_ref)),
    )


def validate_semantic_causal_readback(value: SemanticCausalReadbackCandidate) -> None:
    if type(value) is not SemanticCausalReadbackCandidate or value._factory_seal is not _BOUND_FACTORY:
        raise GwtSemanticRuntimeReadbackError("semantic causal candidate lacks binder-factory origin")
    if value._factory_payload_sha256 != _digest_json(value.as_dict()):
        raise GwtSemanticRuntimeReadbackError("semantic causal candidate payload changed after bind")


__all__ = [
    "GwtSemanticRuntimeReadbackError",
    "MATCHED_TASK_OUTCOME_PREDICATE",
    "MATCHED_TASK_OUTCOME_READBACK_SCHEMA",
    "MATCHED_TASK_OUTCOME_SCHEMA",
    "MatchedTaskOutcomeReadback",
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
    "WP900_CONTROL_RAW_OUTCOME_SCHEMA",
    "WP900_INTERVENTION_RAW_OUTCOME_SCHEMA",
    "WP900_MATCHED_TASK_SCHEMA",
    "bind_independent_reentry_evidence",
    "bind_semantic_causal_readback",
    "validate_matched_task_outcome_readback",
    "validate_semantic_arm_readback",
    "validate_semantic_causal_readback",
]