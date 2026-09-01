"""Model-specific semantic causal readback gate for the accepted F2 GWT path.

F2-WP-900 generation 5 repository/integration scope.

WP900 G4 established a bounded target-environment contract-level causal
observation: a matched broadcast intervention and no-broadcast control produced
different downstream readbacks under one exact execution context. That result
is intentionally insufficient for semantic GWT/J-Space credit because a hash
difference does not establish that a downstream cognitive organ used the
broadcast *semantically*.

This module adds only the missing fail-closed semantic discriminator contract.
It consumes the accepted G4 candidate and binds a model-specific matched pair
against an evaluator-only task oracle. The intervention must produce the
expected semantic label while the matched no-broadcast control must not. Both
arms must share the exact source/boot, model artifact, decoder configuration,
non-broadcast input, and model-input context identity. The control arm may not
carry broadcast identity.

Construction or repository CI remains candidate evidence only. This module does
not execute a model, provider, physical GRID10, effect, or J-Space runtime, and
all promotion fields remain zero. Any future semantic GWT/J-Space promotion
requires an admitted external execution receipt proving that the recorded model
and oracle-isolation identities were actually exercised.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.gwt_causal_runtime_readback import (
    CAUSAL_RUNTIME_READBACK_OBSERVED,
    GwtCausalRuntimeReadbackCandidate,
    ProbeExecutionContext,
    validate_causal_runtime_readback,
)

SEMANTIC_TASK_SCHEMA = "FRANKENSTEIN2_GWT_SEMANTIC_TASK/v1"
SEMANTIC_EXECUTION_CONTEXT_SCHEMA = "FRANKENSTEIN2_GWT_SEMANTIC_EXECUTION_CONTEXT/v1"
SEMANTIC_DOWNSTREAM_READBACK_SCHEMA = "FRANKENSTEIN2_GWT_SEMANTIC_DOWNSTREAM_READBACK/v1"
SEMANTIC_CAUSAL_READBACK_SCHEMA = "FRANKENSTEIN2_GWT_SEMANTIC_CAUSAL_READBACK/v1"

SEMANTIC_CAUSAL_INFLUENCE_CANDIDATE = "SEMANTIC_CAUSAL_INFLUENCE_CANDIDATE_REQUIRES_EXTERNAL_ADMISSION"
INTERVENTION_BROADCAST = "INTERVENTION_BROADCAST"
CONTROL_NO_BROADCAST = "CONTROL_NO_BROADCAST"
UNKNOWN_SEMANTIC_LABEL = "__UNKNOWN__"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_TASK_FACTORY = object()
_CONTEXT_FACTORY = object()
_READBACK_FACTORY = object()
_BIND_FACTORY = object()


class GwtSemanticCausalReadbackError(ValueError):
    """Fail-closed WP900 G5 semantic causal-readback error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise GwtSemanticCausalReadbackError(f"{name} must be non-empty trimmed text")
    if len(value) > _MAX_TEXT:
        raise GwtSemanticCausalReadbackError(f"{name} exceeds {_MAX_TEXT} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GwtSemanticCausalReadbackError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise GwtSemanticCausalReadbackError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 1:
        raise GwtSemanticCausalReadbackError(f"{name} must be a positive integer")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GwtSemanticCausalReadbackError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance_ref", value) for value in values)
    if not refs:
        raise GwtSemanticCausalReadbackError("provenance_refs must not be empty")
    if len(set(refs)) != len(refs):
        raise GwtSemanticCausalReadbackError("provenance_refs must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise GwtSemanticCausalReadbackError("value is not canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _label_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticTaskSpec:
    """Evaluator-side semantic task and oracle identity.

    The expected label belongs to the evaluator-side oracle. A runtime harness
    must prove that oracle material was not inserted into the model input.
    """

    task_id: str
    task_family: str
    nonbroadcast_input_sha256: str
    oracle_ref: str
    oracle_sha256: str
    expected_label: str
    expected_label_sha256: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = SEMANTIC_TASK_SCHEMA

    def __post_init__(self) -> None:
        for name in ("task_id", "task_family", "oracle_ref", "expected_label"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if self.expected_label == UNKNOWN_SEMANTIC_LABEL:
            raise GwtSemanticCausalReadbackError("expected_label may not be UNKNOWN")
        for name in ("nonbroadcast_input_sha256", "oracle_sha256", "expected_label_sha256"):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if self.expected_label_sha256 != _label_digest(self.expected_label):
            raise GwtSemanticCausalReadbackError("expected_label_sha256 does not match expected_label")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @classmethod
    def define(
        cls,
        *,
        task_id: str,
        task_family: str,
        nonbroadcast_input_sha256: str,
        oracle_ref: str,
        oracle_sha256: str,
        expected_label: str,
        provenance_refs: Iterable[str],
    ) -> "SemanticTaskSpec":
        value = cls(
            task_id=task_id,
            task_family=task_family,
            nonbroadcast_input_sha256=nonbroadcast_input_sha256,
            oracle_ref=oracle_ref,
            oracle_sha256=oracle_sha256,
            expected_label=expected_label,
            expected_label_sha256=_label_digest(_text("expected_label", expected_label)),
            provenance_refs=tuple(provenance_refs),
            _factory_seal=_TASK_FACTORY,
        )
        object.__setattr__(value, "_factory_payload_sha256", _digest(value.as_dict()))
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "task_id": self.task_id,
            "task_family": self.task_family,
            "nonbroadcast_input_sha256": self.nonbroadcast_input_sha256,
            "oracle_ref": self.oracle_ref,
            "oracle_sha256": self.oracle_sha256,
            "expected_label": self.expected_label,
            "expected_label_sha256": self.expected_label_sha256,
            "oracle_visibility": "EVALUATOR_ONLY_REQUIRES_RUNTIME_ADMISSION",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def validate_semantic_task(value: SemanticTaskSpec) -> None:
    if type(value) is not SemanticTaskSpec or value._factory_seal is not _TASK_FACTORY:
        raise GwtSemanticCausalReadbackError("semantic task lacks definition factory origin")
    if value._factory_payload_sha256 != _digest(value.as_dict()):
        raise GwtSemanticCausalReadbackError("semantic task payload changed after definition")


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticExecutionContext:
    """Model-specific context layered over the accepted G4 execution context."""

    execution_context_sha256: str
    exact_source_sha256: str
    boot_id_sha256: str
    model_runtime_identity: str
    model_artifact_sha256: str
    decoder_config_sha256: str
    model_input_context_sha256: str
    evaluator_oracle_context_sha256: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = SEMANTIC_EXECUTION_CONTEXT_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_runtime_identity", _text("model_runtime_identity", self.model_runtime_identity))
        for name in (
            "execution_context_sha256",
            "exact_source_sha256",
            "boot_id_sha256",
            "model_artifact_sha256",
            "decoder_config_sha256",
            "model_input_context_sha256",
            "evaluator_oracle_context_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if self.model_input_context_sha256 == self.evaluator_oracle_context_sha256:
            raise GwtSemanticCausalReadbackError(
                "model input context and evaluator oracle context must be distinct"
            )
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @classmethod
    def bind(
        cls,
        *,
        execution_context: ProbeExecutionContext,
        model_runtime_identity: str,
        model_artifact_sha256: str,
        decoder_config_sha256: str,
        model_input_context_sha256: str,
        evaluator_oracle_context_sha256: str,
        provenance_refs: Iterable[str],
    ) -> "SemanticExecutionContext":
        if type(execution_context) is not ProbeExecutionContext:
            raise GwtSemanticCausalReadbackError("execution_context must be exact ProbeExecutionContext")
        value = cls(
            execution_context_sha256=execution_context.sha256(),
            exact_source_sha256=execution_context.exact_source_sha256,
            boot_id_sha256=execution_context.boot_id_sha256,
            model_runtime_identity=model_runtime_identity,
            model_artifact_sha256=model_artifact_sha256,
            decoder_config_sha256=decoder_config_sha256,
            model_input_context_sha256=model_input_context_sha256,
            evaluator_oracle_context_sha256=evaluator_oracle_context_sha256,
            provenance_refs=tuple(provenance_refs),
            _factory_seal=_CONTEXT_FACTORY,
        )
        object.__setattr__(value, "_factory_payload_sha256", _digest(value.as_dict()))
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "execution_context_sha256": self.execution_context_sha256,
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "model_runtime_identity": self.model_runtime_identity,
            "model_artifact_sha256": self.model_artifact_sha256,
            "decoder_config_sha256": self.decoder_config_sha256,
            "model_input_context_sha256": self.model_input_context_sha256,
            "evaluator_oracle_context_sha256": self.evaluator_oracle_context_sha256,
            "oracle_isolation_claim": "MUST_BE_PROVEN_BY_EXTERNAL_RUNTIME_RECEIPT",
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def validate_semantic_execution_context(
    value: SemanticExecutionContext,
    *,
    execution_context: ProbeExecutionContext,
) -> None:
    if type(value) is not SemanticExecutionContext or value._factory_seal is not _CONTEXT_FACTORY:
        raise GwtSemanticCausalReadbackError("semantic execution context lacks factory origin")
    if value._factory_payload_sha256 != _digest(value.as_dict()):
        raise GwtSemanticCausalReadbackError("semantic execution context changed after bind")
    if type(execution_context) is not ProbeExecutionContext:
        raise GwtSemanticCausalReadbackError("execution_context must be exact ProbeExecutionContext")
    if value.execution_context_sha256 != execution_context.sha256():
        raise GwtSemanticCausalReadbackError("semantic/base execution context mismatch")
    if value.exact_source_sha256 != execution_context.exact_source_sha256:
        raise GwtSemanticCausalReadbackError("semantic/base exact-source mismatch")
    if value.boot_id_sha256 != execution_context.boot_id_sha256:
        raise GwtSemanticCausalReadbackError("semantic/base boot mismatch")


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticDownstreamReadback:
    """Observed semantic label for one matched intervention/control arm."""

    condition: str
    task_sha256: str
    semantic_execution_context_sha256: str
    runtime_instance_id: str
    process_identity: str
    model_artifact_sha256: str
    decoder_config_sha256: str
    nonbroadcast_input_sha256: str
    broadcast_id: str | None
    broadcast_sha256: str | None
    output_ref: str
    output_sha256: str
    semantic_label: str
    semantic_label_sha256: str
    observed_monotonic_ns: int
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = SEMANTIC_DOWNSTREAM_READBACK_SCHEMA

    def __post_init__(self) -> None:
        if self.condition not in {INTERVENTION_BROADCAST, CONTROL_NO_BROADCAST}:
            raise GwtSemanticCausalReadbackError("unsupported semantic readback condition")
        for name in ("runtime_instance_id", "process_identity", "output_ref", "semantic_label"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "task_sha256",
            "semantic_execution_context_sha256",
            "model_artifact_sha256",
            "decoder_config_sha256",
            "nonbroadcast_input_sha256",
            "output_sha256",
            "semantic_label_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if self.semantic_label_sha256 != _label_digest(self.semantic_label):
            raise GwtSemanticCausalReadbackError("semantic_label_sha256 does not match semantic_label")
        if self.condition == INTERVENTION_BROADCAST:
            if self.broadcast_id is None or self.broadcast_sha256 is None:
                raise GwtSemanticCausalReadbackError("intervention readback requires broadcast identity")
            object.__setattr__(self, "broadcast_id", _text("broadcast_id", self.broadcast_id))
            object.__setattr__(self, "broadcast_sha256", _sha256("broadcast_sha256", self.broadcast_sha256))
        else:
            if self.broadcast_id is not None or self.broadcast_sha256 is not None:
                raise GwtSemanticCausalReadbackError("control readback must not carry broadcast identity")
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @classmethod
    def observe(
        cls,
        *,
        condition: str,
        task: SemanticTaskSpec,
        semantic_execution_context: SemanticExecutionContext,
        runtime_instance_id: str,
        process_identity: str,
        nonbroadcast_input_sha256: str,
        output_ref: str,
        output_sha256: str,
        semantic_label: str,
        observed_monotonic_ns: int,
        provenance_refs: Iterable[str],
        broadcast_id: str | None = None,
        broadcast_sha256: str | None = None,
    ) -> "SemanticDownstreamReadback":
        validate_semantic_task(task)
        if type(semantic_execution_context) is not SemanticExecutionContext:
            raise GwtSemanticCausalReadbackError(
                "semantic_execution_context must be exact SemanticExecutionContext"
            )
        value = cls(
            condition=condition,
            task_sha256=task.sha256(),
            semantic_execution_context_sha256=semantic_execution_context.sha256(),
            runtime_instance_id=runtime_instance_id,
            process_identity=process_identity,
            model_artifact_sha256=semantic_execution_context.model_artifact_sha256,
            decoder_config_sha256=semantic_execution_context.decoder_config_sha256,
            nonbroadcast_input_sha256=nonbroadcast_input_sha256,
            broadcast_id=broadcast_id,
            broadcast_sha256=broadcast_sha256,
            output_ref=output_ref,
            output_sha256=output_sha256,
            semantic_label=semantic_label,
            semantic_label_sha256=_label_digest(_text("semantic_label", semantic_label)),
            observed_monotonic_ns=observed_monotonic_ns,
            provenance_refs=tuple(provenance_refs),
            _factory_seal=_READBACK_FACTORY,
        )
        object.__setattr__(value, "_factory_payload_sha256", _digest(value.as_dict()))
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "condition": self.condition,
            "task_sha256": self.task_sha256,
            "semantic_execution_context_sha256": self.semantic_execution_context_sha256,
            "runtime_instance_id": self.runtime_instance_id,
            "process_identity": self.process_identity,
            "model_artifact_sha256": self.model_artifact_sha256,
            "decoder_config_sha256": self.decoder_config_sha256,
            "nonbroadcast_input_sha256": self.nonbroadcast_input_sha256,
            "broadcast_id": self.broadcast_id,
            "broadcast_sha256": self.broadcast_sha256,
            "output_ref": self.output_ref,
            "output_sha256": self.output_sha256,
            "semantic_label": self.semantic_label,
            "semantic_label_sha256": self.semantic_label_sha256,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def validate_semantic_downstream_readback(value: SemanticDownstreamReadback) -> None:
    if type(value) is not SemanticDownstreamReadback or value._factory_seal is not _READBACK_FACTORY:
        raise GwtSemanticCausalReadbackError("semantic readback lacks observation factory origin")
    if value._factory_payload_sha256 != _digest(value.as_dict()):
        raise GwtSemanticCausalReadbackError("semantic readback payload changed after observation")


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticGwtCausalReadbackCandidate:
    probe_id: str
    g4_causal_candidate_sha256: str
    task_sha256: str
    semantic_execution_context_sha256: str
    exact_source_sha256: str
    boot_id_sha256: str
    model_runtime_identity: str
    model_artifact_sha256: str
    decoder_config_sha256: str
    nonbroadcast_input_sha256: str
    broadcast_id: str
    broadcast_sha256: str
    intervention_readback_sha256: str
    control_readback_sha256: str
    intervention_semantic_label: str
    control_semantic_label: str
    expected_semantic_label: str
    classification: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    schema = SEMANTIC_CAUSAL_READBACK_SCHEMA
    evidence_scope = "MODEL_SPECIFIC_SEMANTIC_CAUSAL_CANDIDATE_REQUIRES_EXTERNAL_EXECUTION_ADMISSION"
    repository_ci_credit = 0
    runtime_credit = 0
    target_environment_component_runtime_credit = 0
    gwt_contract_causal_runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    physical_grid10_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        for name in (
            "probe_id",
            "model_runtime_identity",
            "broadcast_id",
            "intervention_semantic_label",
            "control_semantic_label",
            "expected_semantic_label",
            "classification",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "g4_causal_candidate_sha256",
            "task_sha256",
            "semantic_execution_context_sha256",
            "exact_source_sha256",
            "boot_id_sha256",
            "model_artifact_sha256",
            "decoder_config_sha256",
            "nonbroadcast_input_sha256",
            "broadcast_sha256",
            "intervention_readback_sha256",
            "control_readback_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if self.classification != SEMANTIC_CAUSAL_INFLUENCE_CANDIDATE:
            raise GwtSemanticCausalReadbackError("unexpected semantic causal classification")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "probe_id": self.probe_id,
            "g4_causal_candidate_sha256": self.g4_causal_candidate_sha256,
            "task_sha256": self.task_sha256,
            "semantic_execution_context_sha256": self.semantic_execution_context_sha256,
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "model_runtime_identity": self.model_runtime_identity,
            "model_artifact_sha256": self.model_artifact_sha256,
            "decoder_config_sha256": self.decoder_config_sha256,
            "nonbroadcast_input_sha256": self.nonbroadcast_input_sha256,
            "broadcast_id": self.broadcast_id,
            "broadcast_sha256": self.broadcast_sha256,
            "intervention_readback_sha256": self.intervention_readback_sha256,
            "control_readback_sha256": self.control_readback_sha256,
            "intervention_semantic_label": self.intervention_semantic_label,
            "control_semantic_label": self.control_semantic_label,
            "expected_semantic_label": self.expected_semantic_label,
            "classification": self.classification,
            "evidence_scope": self.evidence_scope,
            "repository_ci_credit": self.repository_ci_credit,
            "runtime_credit": self.runtime_credit,
            "target_environment_component_runtime_credit": self.target_environment_component_runtime_credit,
            "gwt_contract_causal_runtime_credit": self.gwt_contract_causal_runtime_credit,
            "semantic_gwt_runtime_credit": self.semantic_gwt_runtime_credit,
            "jspace_runtime_credit": self.jspace_runtime_credit,
            "physical_grid10_credit": self.physical_grid10_credit,
            "effect_credit": self.effect_credit,
            "training_credit": self.training_credit,
            "completion_credit": self.completion_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
            "provenance_refs": list(self.provenance_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def bind_semantic_causal_readback(
    *,
    g4_candidate: GwtCausalRuntimeReadbackCandidate,
    execution_context: ProbeExecutionContext,
    semantic_execution_context: SemanticExecutionContext,
    task: SemanticTaskSpec,
    intervention_readback: SemanticDownstreamReadback,
    control_readback: SemanticDownstreamReadback,
    provenance_refs: Iterable[str],
) -> SemanticGwtCausalReadbackCandidate:
    """Bind a model-specific semantic intervention/control candidate.

    No execution occurs here. The function only verifies already-observed,
    factory-bound records and deliberately leaves every runtime promotion field
    at zero pending an admitted external execution receipt.
    """

    if type(g4_candidate) is not GwtCausalRuntimeReadbackCandidate:
        raise GwtSemanticCausalReadbackError("g4_candidate must be exact GwtCausalRuntimeReadbackCandidate")
    try:
        validate_causal_runtime_readback(g4_candidate)
    except ValueError as exc:
        raise GwtSemanticCausalReadbackError(f"invalid G4 causal candidate: {exc}") from exc
    if g4_candidate.classification != CAUSAL_RUNTIME_READBACK_OBSERVED:
        raise GwtSemanticCausalReadbackError("G4 causal candidate is not contract-scope positive")

    validate_semantic_execution_context(
        semantic_execution_context,
        execution_context=execution_context,
    )
    validate_semantic_task(task)
    validate_semantic_downstream_readback(intervention_readback)
    validate_semantic_downstream_readback(control_readback)

    if g4_candidate.exact_source_sha256 != execution_context.exact_source_sha256:
        raise GwtSemanticCausalReadbackError("G4/base exact-source mismatch")
    if g4_candidate.boot_id_sha256 != execution_context.boot_id_sha256:
        raise GwtSemanticCausalReadbackError("G4/base boot mismatch")
    if semantic_execution_context.exact_source_sha256 != g4_candidate.exact_source_sha256:
        raise GwtSemanticCausalReadbackError("semantic/G4 exact-source mismatch")
    if semantic_execution_context.boot_id_sha256 != g4_candidate.boot_id_sha256:
        raise GwtSemanticCausalReadbackError("semantic/G4 boot mismatch")

    if task.nonbroadcast_input_sha256 != g4_candidate.nonbroadcast_input_sha256:
        raise GwtSemanticCausalReadbackError("semantic task input does not match G4 non-broadcast input")

    expected_context_sha = semantic_execution_context.sha256()
    for name, readback in (
        ("intervention", intervention_readback),
        ("control", control_readback),
    ):
        if readback.task_sha256 != task.sha256():
            raise GwtSemanticCausalReadbackError(f"{name} task binding mismatch")
        if readback.semantic_execution_context_sha256 != expected_context_sha:
            raise GwtSemanticCausalReadbackError(f"{name} semantic execution-context mismatch")
        if readback.model_artifact_sha256 != semantic_execution_context.model_artifact_sha256:
            raise GwtSemanticCausalReadbackError(f"{name} model artifact mismatch")
        if readback.decoder_config_sha256 != semantic_execution_context.decoder_config_sha256:
            raise GwtSemanticCausalReadbackError(f"{name} decoder configuration mismatch")
        if readback.nonbroadcast_input_sha256 != task.nonbroadcast_input_sha256:
            raise GwtSemanticCausalReadbackError(f"{name} non-broadcast input mismatch")

    if intervention_readback.condition != INTERVENTION_BROADCAST:
        raise GwtSemanticCausalReadbackError("intervention arm condition mismatch")
    if control_readback.condition != CONTROL_NO_BROADCAST:
        raise GwtSemanticCausalReadbackError("control arm condition mismatch")
    if intervention_readback.broadcast_id != g4_candidate.broadcast_id:
        raise GwtSemanticCausalReadbackError("intervention/G4 broadcast id mismatch")
    if intervention_readback.broadcast_sha256 != g4_candidate.broadcast_sha256:
        raise GwtSemanticCausalReadbackError("intervention/G4 broadcast digest mismatch")
    if control_readback.broadcast_id is not None or control_readback.broadcast_sha256 is not None:
        raise GwtSemanticCausalReadbackError("control arm unexpectedly carries broadcast identity")

    if intervention_readback.semantic_label != task.expected_label:
        raise GwtSemanticCausalReadbackError("intervention did not produce expected semantic label")
    if control_readback.semantic_label == task.expected_label:
        raise GwtSemanticCausalReadbackError("control also produced expected label; no semantic causal influence")
    if intervention_readback.output_sha256 == control_readback.output_sha256:
        raise GwtSemanticCausalReadbackError("matched arms have identical downstream output digest")

    candidate = SemanticGwtCausalReadbackCandidate(
        probe_id=g4_candidate.probe_id,
        g4_causal_candidate_sha256=g4_candidate.sha256(),
        task_sha256=task.sha256(),
        semantic_execution_context_sha256=expected_context_sha,
        exact_source_sha256=g4_candidate.exact_source_sha256,
        boot_id_sha256=g4_candidate.boot_id_sha256,
        model_runtime_identity=semantic_execution_context.model_runtime_identity,
        model_artifact_sha256=semantic_execution_context.model_artifact_sha256,
        decoder_config_sha256=semantic_execution_context.decoder_config_sha256,
        nonbroadcast_input_sha256=task.nonbroadcast_input_sha256,
        broadcast_id=g4_candidate.broadcast_id,
        broadcast_sha256=g4_candidate.broadcast_sha256,
        intervention_readback_sha256=intervention_readback.sha256(),
        control_readback_sha256=control_readback.sha256(),
        intervention_semantic_label=intervention_readback.semantic_label,
        control_semantic_label=control_readback.semantic_label,
        expected_semantic_label=task.expected_label,
        classification=SEMANTIC_CAUSAL_INFLUENCE_CANDIDATE,
        provenance_refs=_refs(provenance_refs),
        _factory_seal=_BIND_FACTORY,
    )
    object.__setattr__(candidate, "_factory_payload_sha256", _digest(candidate.as_dict()))
    return candidate


def validate_semantic_causal_readback(candidate: SemanticGwtCausalReadbackCandidate) -> None:
    if type(candidate) is not SemanticGwtCausalReadbackCandidate or candidate._factory_seal is not _BIND_FACTORY:
        raise GwtSemanticCausalReadbackError("semantic causal candidate lacks binder factory origin")
    if candidate._factory_payload_sha256 != _digest(candidate.as_dict()):
        raise GwtSemanticCausalReadbackError("semantic causal candidate changed after bind")


__all__ = [
    "CONTROL_NO_BROADCAST",
    "INTERVENTION_BROADCAST",
    "SEMANTIC_CAUSAL_INFLUENCE_CANDIDATE",
    "SEMANTIC_CAUSAL_READBACK_SCHEMA",
    "SEMANTIC_DOWNSTREAM_READBACK_SCHEMA",
    "SEMANTIC_EXECUTION_CONTEXT_SCHEMA",
    "SEMANTIC_TASK_SCHEMA",
    "UNKNOWN_SEMANTIC_LABEL",
    "GwtSemanticCausalReadbackError",
    "SemanticDownstreamReadback",
    "SemanticExecutionContext",
    "SemanticGwtCausalReadbackCandidate",
    "SemanticTaskSpec",
    "bind_semantic_causal_readback",
    "validate_semantic_causal_readback",
    "validate_semantic_downstream_readback",
    "validate_semantic_execution_context",
    "validate_semantic_task",
]
