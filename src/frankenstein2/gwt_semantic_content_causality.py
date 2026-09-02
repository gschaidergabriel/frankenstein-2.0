"""WP900 G9 fail-closed semantic-content causal crossover binder.

This module does not mint runtime or semantic GWT/J-Space credit. It binds four
same-mechanism broadcast trials into a content-causality *candidate*:

* exactly two content-addressed JSON payloads,
* ABBA/BAAB counterbalanced order,
* recorder-origin DELIVERY -> UPTAKE -> REENTRY evidence for every trial,
* one condition-blind task-outcome observation API,
* stable repeated outcomes for the same content,
* exact source/boot/context/task/pre-state/executor/plan/recipient mechanics.

Any missing mechanism path, mechanics mismatch, non-counterbalanced order,
semantically duplicate treatment payloads or unstable repeat becomes UNKNOWN.
A stable outcome difference across the two semantic payloads remains a zero-credit
candidate until the exact source executes on an admitted target and is separately
reconciled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Iterable

from frankenstein2.gwt_runtime_witness import (
    GwtRuntimeWitnessReceipt,
    LIVE_GWT_PATH_OBSERVED,
    validate_gwt_runtime_witness_receipt,
)
from frankenstein2.gwt_semantic_runtime_readback import (
    GwtSemanticRuntimeReadbackError,
    _canonical_json as _g6_canonical_json,
    _parse_json as _g6_parse_json,
)
from frankenstein2.gwt_workspace import BroadcastEnvelope

SEMANTIC_CONTENT_OUTCOME_SCHEMA = "FRANKENSTEIN2_GWT_CONDITION_BLIND_TASK_OUTCOME/v1"
SEMANTIC_CONTENT_TRIAL_SCHEMA = "FRANKENSTEIN2_GWT_SEMANTIC_CONTENT_TRIAL/v1"
SEMANTIC_CONTENT_CROSSOVER_SCHEMA = "FRANKENSTEIN2_GWT_SEMANTIC_CONTENT_CROSSOVER/v1"

SEMANTIC_CONTENT_CAUSAL_DIFFERENCE_CANDIDATE = (
    "SEMANTIC_CONTENT_CAUSAL_DIFFERENCE_CANDIDATE_REQUIRES_TARGET_EXECUTION_ADMISSION"
)
NO_SEMANTIC_CONTENT_CAUSAL_DIFFERENCE = "NO_SEMANTIC_CONTENT_CAUSAL_DIFFERENCE_OBSERVED"
SEMANTIC_CONTENT_CAUSALITY_UNKNOWN = "SEMANTIC_CONTENT_CAUSALITY_UNKNOWN_FAIL_CLOSED"

UNKNOWN_MECHANISM_PATH = "MECHANISM_PATH_MISMATCH_OR_INCOMPLETE"
UNKNOWN_MECHANICS_MISMATCH = "MATCHED_MECHANICS_MISMATCH"
UNKNOWN_ORDER = "COUNTERBALANCED_ORDER_NOT_PROVEN"
UNKNOWN_REPEAT_INSTABILITY = "SAME_CONTENT_REPEAT_UNSTABLE"
UNKNOWN_SEMANTIC_CONTENT = "DISTINCT_SEMANTIC_CONTENT_NOT_PROVEN"
CONTENT_CAUSALITY_READY = "COUNTERBALANCED_CONTENT_CAUSALITY_CANDIDATE"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTENT_REF_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
_MAX_TEXT = 512
_OUTCOME_FACTORY = object()
_TRIAL_FACTORY = object()
_CROSSOVER_FACTORY = object()


class GwtSemanticContentCausalityError(ValueError):
    """Fail-closed WP900 G9 content-causality validation error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise GwtSemanticContentCausalityError(f"{name} must be non-empty trimmed text")
    if len(value) > _MAX_TEXT:
        raise GwtSemanticContentCausalityError(f"{name} exceeds {_MAX_TEXT} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GwtSemanticContentCausalityError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise GwtSemanticContentCausalityError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 1:
        raise GwtSemanticContentCausalityError(f"{name} must be a positive integer")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GwtSemanticContentCausalityError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance_ref", value) for value in values)
    if not refs:
        raise GwtSemanticContentCausalityError("provenance_refs must not be empty")
    if len(set(refs)) != len(refs):
        raise GwtSemanticContentCausalityError("provenance_refs must not contain duplicates")
    return tuple(sorted(refs))


def _digest_json(value: Any) -> str:
    try:
        encoded = _g6_canonical_json(value).encode("utf-8")
    except GwtSemanticRuntimeReadbackError as exc:
        raise GwtSemanticContentCausalityError(str(exc)) from exc
    return hashlib.sha256(encoded).hexdigest()


def _canonical_semantic_json(raw_payload: bytes) -> tuple[str, str]:
    try:
        value = _g6_parse_json(raw_payload)
        canonical = _g6_canonical_json(value)
    except GwtSemanticRuntimeReadbackError as exc:
        raise GwtSemanticContentCausalityError(str(exc)) from exc
    return canonical, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class ConditionBlindTaskOutcomeReadback:
    """Factory-observed outcome; API deliberately has no arm/treatment/mechanism input."""

    task_id: str
    task_schema: str
    outcome_schema: str
    raw_outcome_sha256: str
    semantic_canonical_json: str
    semantic_sha256: str
    exact_source_sha256: str
    boot_id_sha256: str
    execution_context_sha256: str
    task_input_sha256: str
    pre_state_sha256: str
    task_executor_sha256: str
    observer_identity: str
    observed_monotonic_ns: int
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, init=False, repr=False, compare=False, hash=False)

    schema = SEMANTIC_CONTENT_OUTCOME_SCHEMA
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        for name in ("task_id", "task_schema", "outcome_schema", "observer_identity"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "raw_outcome_sha256", "semantic_sha256", "exact_source_sha256", "boot_id_sha256",
            "execution_context_sha256", "task_input_sha256", "pre_state_sha256", "task_executor_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        canonical, semantic_sha256 = _canonical_semantic_json(self.semantic_canonical_json.encode("utf-8"))
        if canonical != self.semantic_canonical_json:
            raise GwtSemanticContentCausalityError("semantic_canonical_json is not canonical")
        if semantic_sha256 != self.semantic_sha256:
            raise GwtSemanticContentCausalityError("semantic_sha256 does not bind canonical semantic JSON")
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @classmethod
    def observe_json(
        cls, *, task_id: str, task_schema: str, outcome_schema: str, raw_outcome: bytes,
        exact_source_sha256: str, boot_id_sha256: str, execution_context_sha256: str,
        task_input_sha256: str, pre_state_sha256: str, task_executor_sha256: str,
        observer_identity: str, observed_monotonic_ns: int, provenance_refs: Iterable[str],
    ) -> "ConditionBlindTaskOutcomeReadback":
        if type(raw_outcome) is not bytes or not raw_outcome:
            raise GwtSemanticContentCausalityError("raw_outcome must be non-empty exact bytes")
        observed = hashlib.sha256(raw_outcome).hexdigest()
        canonical, semantic_sha256 = _canonical_semantic_json(raw_outcome)
        value = cls(
            task_id=task_id, task_schema=task_schema, outcome_schema=outcome_schema,
            raw_outcome_sha256=observed, semantic_canonical_json=canonical,
            semantic_sha256=semantic_sha256, exact_source_sha256=exact_source_sha256,
            boot_id_sha256=boot_id_sha256, execution_context_sha256=execution_context_sha256,
            task_input_sha256=task_input_sha256, pre_state_sha256=pre_state_sha256,
            task_executor_sha256=task_executor_sha256, observer_identity=observer_identity,
            observed_monotonic_ns=observed_monotonic_ns, provenance_refs=tuple(provenance_refs),
        )
        object.__setattr__(value, "_factory_seal", _OUTCOME_FACTORY)
        object.__setattr__(value, "_factory_payload_sha256", _digest_json(value.as_dict()))
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema, "task_id": self.task_id, "task_schema": self.task_schema,
            "outcome_schema": self.outcome_schema, "raw_outcome_sha256": self.raw_outcome_sha256,
            "semantic_canonical_json": self.semantic_canonical_json, "semantic_sha256": self.semantic_sha256,
            "exact_source_sha256": self.exact_source_sha256, "boot_id_sha256": self.boot_id_sha256,
            "execution_context_sha256": self.execution_context_sha256, "task_input_sha256": self.task_input_sha256,
            "pre_state_sha256": self.pre_state_sha256, "task_executor_sha256": self.task_executor_sha256,
            "observer_identity": self.observer_identity, "observed_monotonic_ns": self.observed_monotonic_ns,
            "provenance_refs": list(self.provenance_refs),
            "credits": {"repository_ci": 0, "target_environment_component_runtime": 0,
                "semantic_gwt_runtime": 0, "jspace_runtime": 0, "effect": 0, "training": 0,
                "completion": 0, "whole_system_acceptance": False},
        }

    def sha256(self) -> str:
        return _digest_json(self.as_dict())


def validate_condition_blind_task_outcome(value: ConditionBlindTaskOutcomeReadback) -> None:
    if type(value) is not ConditionBlindTaskOutcomeReadback or value._factory_seal is not _OUTCOME_FACTORY:
        raise GwtSemanticContentCausalityError("task outcome lacks condition-blind observation-factory origin")
    if value._factory_payload_sha256 != _digest_json(value.as_dict()):
        raise GwtSemanticContentCausalityError("task outcome payload changed after observation")


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticContentTrial:
    trial_id: str
    order_position: int
    semantic_payload_ref: str
    semantic_payload_raw_sha256: str
    semantic_payload_canonical_json: str
    semantic_payload_sha256: str
    broadcast: BroadcastEnvelope
    runtime_witness: GwtRuntimeWitnessReceipt
    outcome: ConditionBlindTaskOutcomeReadback
    mechanics_sha256: str
    mechanism_path_complete: bool
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, init=False, repr=False, compare=False, hash=False)

    schema = SEMANTIC_CONTENT_TRIAL_SCHEMA
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "trial_id", _text("trial_id", self.trial_id))
        if type(self.order_position) is not int or not 1 <= self.order_position <= 4:
            raise GwtSemanticContentCausalityError("order_position must be one of 1..4")
        object.__setattr__(self, "semantic_payload_ref", _text("semantic_payload_ref", self.semantic_payload_ref))
        for name in ("semantic_payload_raw_sha256", "semantic_payload_sha256", "mechanics_sha256"):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        canonical, semantic_sha = _canonical_semantic_json(self.semantic_payload_canonical_json.encode("utf-8"))
        if canonical != self.semantic_payload_canonical_json:
            raise GwtSemanticContentCausalityError("semantic payload canonical JSON is not canonical")
        if semantic_sha != self.semantic_payload_sha256:
            raise GwtSemanticContentCausalityError("semantic payload SHA-256 does not bind canonical semantics")
        if type(self.broadcast) is not BroadcastEnvelope:
            raise GwtSemanticContentCausalityError("broadcast must be exact BroadcastEnvelope")
        if type(self.runtime_witness) is not GwtRuntimeWitnessReceipt:
            raise GwtSemanticContentCausalityError("runtime_witness must be exact GwtRuntimeWitnessReceipt")
        if type(self.outcome) is not ConditionBlindTaskOutcomeReadback:
            raise GwtSemanticContentCausalityError("outcome must be exact ConditionBlindTaskOutcomeReadback")
        if type(self.mechanism_path_complete) is not bool:
            raise GwtSemanticContentCausalityError("mechanism_path_complete must be bool")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @classmethod
    def observe(
        cls, *, trial_id: str, order_position: int, semantic_payload: bytes,
        broadcast: BroadcastEnvelope, runtime_witness: GwtRuntimeWitnessReceipt,
        outcome: ConditionBlindTaskOutcomeReadback, provenance_refs: Iterable[str],
    ) -> "SemanticContentTrial":
        if type(semantic_payload) is not bytes or not semantic_payload:
            raise GwtSemanticContentCausalityError("semantic_payload must be non-empty exact bytes")
        if type(broadcast) is not BroadcastEnvelope:
            raise GwtSemanticContentCausalityError("broadcast must be exact BroadcastEnvelope")
        validate_gwt_runtime_witness_receipt(runtime_witness)
        validate_condition_blind_task_outcome(outcome)
        raw_sha = hashlib.sha256(semantic_payload).hexdigest()
        canonical, semantic_sha = _canonical_semantic_json(semantic_payload)
        if len(broadcast.candidate_payload_refs) != 1:
            raise GwtSemanticContentCausalityError("semantic-content trial requires exactly one broadcast candidate payload")
        payload_ref = broadcast.candidate_payload_refs[0]
        match = _CONTENT_REF_RE.fullmatch(payload_ref)
        if match is None or match.group(1) != raw_sha:
            raise GwtSemanticContentCausalityError("broadcast candidate payload_ref is not exact sha256:<payload-bytes>")
        if runtime_witness.broadcast_id != broadcast.broadcast_id:
            raise GwtSemanticContentCausalityError("runtime witness broadcast_id mismatch")
        if runtime_witness.broadcast_sha256 != broadcast.sha256():
            raise GwtSemanticContentCausalityError("runtime witness broadcast SHA-256 mismatch")
        if runtime_witness.recipient_cell_id not in broadcast.recipient_cell_ids:
            raise GwtSemanticContentCausalityError("runtime witness recipient is not in broadcast recipient set")
        if outcome.exact_source_sha256 != runtime_witness.identity.exact_source_sha256:
            raise GwtSemanticContentCausalityError("outcome/source identity mismatch")
        if outcome.boot_id_sha256 != runtime_witness.identity.boot_id_sha256:
            raise GwtSemanticContentCausalityError("outcome/boot identity mismatch")
        if outcome.observed_monotonic_ns <= runtime_witness.events[-1].observed_monotonic_ns:
            raise GwtSemanticContentCausalityError("task outcome must be observed after runtime re-entry")
        mechanics = {
            "exact_source_sha256": outcome.exact_source_sha256, "boot_id_sha256": outcome.boot_id_sha256,
            "execution_context_sha256": outcome.execution_context_sha256, "task_id": outcome.task_id,
            "task_schema": outcome.task_schema, "outcome_schema": outcome.outcome_schema,
            "task_input_sha256": outcome.task_input_sha256, "pre_state_sha256": outcome.pre_state_sha256,
            "task_executor_sha256": outcome.task_executor_sha256, "observer_identity": outcome.observer_identity,
            "plan_id": broadcast.plan_id, "plan_generation": broadcast.plan_generation,
            "plan_sha256": broadcast.plan_sha256, "broadcast_generation": broadcast.generation,
            "selection_generation": broadcast.selection_generation, "recipient_cell_ids": list(broadcast.recipient_cell_ids),
            "observed_recipient_cell_id": runtime_witness.recipient_cell_id,
        }
        value = cls(
            trial_id=trial_id, order_position=order_position, semantic_payload_ref=payload_ref,
            semantic_payload_raw_sha256=raw_sha, semantic_payload_canonical_json=canonical,
            semantic_payload_sha256=semantic_sha, broadcast=broadcast, runtime_witness=runtime_witness,
            outcome=outcome, mechanics_sha256=_digest_json(mechanics),
            mechanism_path_complete=(runtime_witness.classification == LIVE_GWT_PATH_OBSERVED
                and runtime_witness.delivery_status == "DELIVERED" and runtime_witness.uptake_status == "UPTAKEN"
                and tuple(event.phase for event in runtime_witness.events) == ("DELIVERY", "UPTAKE", "REENTRY")),
            provenance_refs=tuple(provenance_refs),
        )
        object.__setattr__(value, "_factory_seal", _TRIAL_FACTORY)
        object.__setattr__(value, "_factory_payload_sha256", _digest_json(value.as_dict()))
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema, "trial_id": self.trial_id, "order_position": self.order_position,
            "semantic_payload_ref": self.semantic_payload_ref,
            "semantic_payload_raw_sha256": self.semantic_payload_raw_sha256,
            "semantic_payload_canonical_json": self.semantic_payload_canonical_json,
            "semantic_payload_sha256": self.semantic_payload_sha256,
            "broadcast_id": self.broadcast.broadcast_id, "broadcast_sha256": self.broadcast.sha256(),
            "runtime_witness_sha256": self.runtime_witness.sha256(), "outcome_sha256": self.outcome.sha256(),
            "outcome_semantic_sha256": self.outcome.semantic_sha256, "mechanics_sha256": self.mechanics_sha256,
            "mechanism_path_complete": self.mechanism_path_complete, "provenance_refs": list(self.provenance_refs),
            "credits": {"repository_ci": 0, "target_environment_component_runtime": 0,
                "semantic_gwt_runtime": 0, "jspace_runtime": 0, "effect": 0, "training": 0,
                "completion": 0, "whole_system_acceptance": False},
        }

    def sha256(self) -> str:
        return _digest_json(self.as_dict())


def validate_semantic_content_trial(value: SemanticContentTrial) -> None:
    if type(value) is not SemanticContentTrial or value._factory_seal is not _TRIAL_FACTORY:
        raise GwtSemanticContentCausalityError("semantic-content trial lacks observation-factory origin")
    validate_gwt_runtime_witness_receipt(value.runtime_witness)
    validate_condition_blind_task_outcome(value.outcome)
    if value.runtime_witness.broadcast_sha256 != value.broadcast.sha256():
        raise GwtSemanticContentCausalityError("semantic-content trial broadcast lineage changed")
    if value._factory_payload_sha256 != _digest_json(value.as_dict()):
        raise GwtSemanticContentCausalityError("semantic-content trial payload changed after observation")


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticContentCrossoverCandidate:
    trials: tuple[SemanticContentTrial, SemanticContentTrial, SemanticContentTrial, SemanticContentTrial]
    payload_semantic_sha256s: tuple[str, str]
    outcome_semantic_sha256s: tuple[str, str]
    classification: str
    reason: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, init=False, repr=False, compare=False, hash=False)

    schema = SEMANTIC_CONTENT_CROSSOVER_SCHEMA
    evidence_scope = "REPOSITORY_CANDIDATE_REQUIRES_EXACT_TARGET_EXECUTION_AND_RECONCILIATION"
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        if type(self.trials) is not tuple or len(self.trials) != 4 or not all(type(i) is SemanticContentTrial for i in self.trials):
            raise GwtSemanticContentCausalityError("crossover requires exactly four exact SemanticContentTrial values")
        if type(self.payload_semantic_sha256s) is not tuple or len(self.payload_semantic_sha256s) != 2:
            raise GwtSemanticContentCausalityError("payload_semantic_sha256s must contain exactly two digests")
        if type(self.outcome_semantic_sha256s) is not tuple or len(self.outcome_semantic_sha256s) != 2:
            raise GwtSemanticContentCausalityError("outcome_semantic_sha256s must contain exactly two digests")
        for value in self.payload_semantic_sha256s + self.outcome_semantic_sha256s:
            _sha256("crossover digest", value)
        if self.classification not in {SEMANTIC_CONTENT_CAUSAL_DIFFERENCE_CANDIDATE,
                NO_SEMANTIC_CONTENT_CAUSAL_DIFFERENCE, SEMANTIC_CONTENT_CAUSALITY_UNKNOWN}:
            raise GwtSemanticContentCausalityError("unsupported crossover classification")
        object.__setattr__(self, "reason", _text("reason", self.reason))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "evidence_scope": self.evidence_scope,
            "trial_sha256s": [item.sha256() for item in self.trials],
            "order_positions": [item.order_position for item in self.trials],
            "payload_semantic_sha256s": list(self.payload_semantic_sha256s),
            "outcome_semantic_sha256s": list(self.outcome_semantic_sha256s),
            "classification": self.classification, "reason": self.reason,
            "provenance_refs": list(self.provenance_refs),
            "credits": {"repository_ci": 0, "target_environment_component_runtime": 0,
                "semantic_gwt_runtime": 0, "jspace_runtime": 0, "effect": 0, "training": 0,
                "completion": 0, "whole_system_acceptance": False}}

    def sha256(self) -> str:
        return _digest_json(self.as_dict())


def _crossover_result(*, trials, payloads, outcomes, classification, reason, provenance_refs):
    value = SemanticContentCrossoverCandidate(
        trials=trials, payload_semantic_sha256s=payloads, outcome_semantic_sha256s=outcomes,
        classification=classification, reason=reason, provenance_refs=tuple(provenance_refs))
    object.__setattr__(value, "_factory_seal", _CROSSOVER_FACTORY)
    object.__setattr__(value, "_factory_payload_sha256", _digest_json(value.as_dict()))
    return value


def bind_semantic_content_crossover(*, trials, provenance_refs) -> SemanticContentCrossoverCandidate:
    """Bind four trials; return only a zero-credit semantic-content causal candidate."""
    if type(trials) is not tuple or len(trials) != 4:
        raise GwtSemanticContentCausalityError("crossover requires exactly four trials")
    for trial in trials:
        validate_semantic_content_trial(trial)
    ordered = tuple(sorted(trials, key=lambda item: item.order_position))
    if tuple(item.order_position for item in ordered) != (1, 2, 3, 4):
        raise GwtSemanticContentCausalityError("crossover trials must contain each order position 1..4 exactly once")
    payload_groups: dict[str, list[SemanticContentTrial]] = {}
    for trial in ordered:
        payload_groups.setdefault(trial.semantic_payload_sha256, []).append(trial)
    payload_keys = tuple(sorted(payload_groups))
    zero_outcomes = ("0" * 64, "0" * 64)
    if len(payload_groups) != 2 or any(len(group) != 2 for group in payload_groups.values()):
        padded = (payload_keys + ("0" * 64, "0" * 64))[:2]
        return _crossover_result(trials=ordered, payloads=padded, outcomes=zero_outcomes,
            classification=SEMANTIC_CONTENT_CAUSALITY_UNKNOWN, reason=UNKNOWN_SEMANTIC_CONTENT,
            provenance_refs=provenance_refs)
    if len({trial.semantic_payload_raw_sha256 for trial in ordered}) != 2:
        return _crossover_result(trials=ordered, payloads=payload_keys, outcomes=zero_outcomes,
            classification=SEMANTIC_CONTENT_CAUSALITY_UNKNOWN, reason=UNKNOWN_SEMANTIC_CONTENT,
            provenance_refs=provenance_refs)
    if len({trial.mechanics_sha256 for trial in ordered}) != 1:
        return _crossover_result(trials=ordered, payloads=payload_keys, outcomes=zero_outcomes,
            classification=SEMANTIC_CONTENT_CAUSALITY_UNKNOWN, reason=UNKNOWN_MECHANICS_MISMATCH,
            provenance_refs=provenance_refs)
    if not all(trial.mechanism_path_complete for trial in ordered):
        return _crossover_result(trials=ordered, payloads=payload_keys, outcomes=zero_outcomes,
            classification=SEMANTIC_CONTENT_CAUSALITY_UNKNOWN, reason=UNKNOWN_MECHANISM_PATH,
            provenance_refs=provenance_refs)
    order = tuple(trial.semantic_payload_sha256 for trial in ordered)
    if not (order[0] == order[3] and order[1] == order[2] and order[0] != order[1]):
        return _crossover_result(trials=ordered, payloads=payload_keys, outcomes=zero_outcomes,
            classification=SEMANTIC_CONTENT_CAUSALITY_UNKNOWN, reason=UNKNOWN_ORDER,
            provenance_refs=provenance_refs)
    stable_outcomes: dict[str, str] = {}
    for payload_sha, group in payload_groups.items():
        observed = {trial.outcome.semantic_sha256 for trial in group}
        if len(observed) != 1:
            return _crossover_result(trials=ordered, payloads=payload_keys, outcomes=zero_outcomes,
                classification=SEMANTIC_CONTENT_CAUSALITY_UNKNOWN, reason=UNKNOWN_REPEAT_INSTABILITY,
                provenance_refs=provenance_refs)
        stable_outcomes[payload_sha] = next(iter(observed))
    outcomes = tuple(stable_outcomes[key] for key in payload_keys)
    if outcomes[0] == outcomes[1]:
        return _crossover_result(trials=ordered, payloads=payload_keys, outcomes=outcomes,
            classification=NO_SEMANTIC_CONTENT_CAUSAL_DIFFERENCE,
            reason="MATCHED_MECHANISM_SEMANTIC_OUTCOMES_EQUIVALENT", provenance_refs=provenance_refs)
    return _crossover_result(trials=ordered, payloads=payload_keys, outcomes=outcomes,
        classification=SEMANTIC_CONTENT_CAUSAL_DIFFERENCE_CANDIDATE, reason=CONTENT_CAUSALITY_READY,
        provenance_refs=provenance_refs)


def validate_semantic_content_crossover(value: SemanticContentCrossoverCandidate) -> None:
    if type(value) is not SemanticContentCrossoverCandidate or value._factory_seal is not _CROSSOVER_FACTORY:
        raise GwtSemanticContentCausalityError("semantic-content crossover lacks binder factory origin")
    for trial in value.trials:
        validate_semantic_content_trial(trial)
    if value._factory_payload_sha256 != _digest_json(value.as_dict()):
        raise GwtSemanticContentCausalityError("semantic-content crossover payload changed after bind")


__all__ = [
    "CONTENT_CAUSALITY_READY", "ConditionBlindTaskOutcomeReadback", "GwtSemanticContentCausalityError",
    "NO_SEMANTIC_CONTENT_CAUSAL_DIFFERENCE", "SEMANTIC_CONTENT_CAUSALITY_UNKNOWN",
    "SEMANTIC_CONTENT_CAUSAL_DIFFERENCE_CANDIDATE", "SemanticContentCrossoverCandidate",
    "SemanticContentTrial", "UNKNOWN_MECHANICS_MISMATCH", "UNKNOWN_MECHANISM_PATH", "UNKNOWN_ORDER",
    "UNKNOWN_REPEAT_INSTABILITY", "UNKNOWN_SEMANTIC_CONTENT", "bind_semantic_content_crossover",
    "validate_condition_blind_task_outcome", "validate_semantic_content_crossover", "validate_semantic_content_trial",
]
