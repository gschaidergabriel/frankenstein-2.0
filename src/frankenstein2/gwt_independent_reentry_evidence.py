"""Condition-blind re-entry evidence adapter for F2-WP-900 generation 8.

G7 produced a target-executed semantic-difference *candidate*, but its
``reentry_observed`` value was projected from the caller-selected arm condition.
That is useful as bounded G7 evidence and must remain historical, but it is not
an independent semantic observation.

G8 adds the smallest missing observation boundary.  A raw bounded event stream is
observed and sealed *before* an intervention/control label is supplied.  The
observer derives only one predicate:

    REENTRY_OBSERVED

A qualifying REENTRY event makes the predicate true.  A complete observation
window with no REENTRY event makes it false.  An incomplete tail with no REENTRY
remains explicit UNKNOWN.  Later arm binding cannot change that result.

This module deliberately does not attempt to reconstruct the historical G4 raw
runtime-witness/control-readback payloads from their digests.  A digest identifies
bytes already possessed; it cannot recover missing historical evidence.  Target
promotion therefore requires a fresh matched execution that persists the full
canonical G8 observation streams and their hashes.

All objects here are evidence candidates.  Repository construction/tests mint no
target-runtime, semantic-GWT, J-Space, effect, training, completion or whole-
system credit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable

import frankenstein2.gwt_semantic_runtime_readback as semantic
from frankenstein2.gwt_causal_runtime_readback import (
    GwtCausalRuntimeReadbackCandidate,
    validate_causal_runtime_readback,
)

CONDITION_BLIND_REENTRY_OBSERVATION_SCHEMA = (
    "FRANKENSTEIN2_GWT_CONDITION_BLIND_REENTRY_OBSERVATION/v1"
)
INDEPENDENT_REENTRY_OUTCOME_SCHEMA = (
    "FRANKENSTEIN2_GWT_INDEPENDENT_REENTRY_OUTCOME_READBACK/v1"
)

WINDOW_OPEN = "WINDOW_OPEN"
REENTRY = "REENTRY"
WINDOW_CLOSE = "WINDOW_CLOSE"

REENTRY_OBSERVED = "REENTRY_OBSERVED"
REENTRY_NOT_OBSERVED = "REENTRY_NOT_OBSERVED"
REENTRY_OBSERVATION_UNKNOWN = "REENTRY_OBSERVATION_UNKNOWN"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_MAX_STREAM_BYTES = 1_048_576
_MAX_EVENTS = 10_000
_OBSERVATION_FACTORY = object()
_OUTCOME_FACTORY = object()


class GwtIndependentReentryEvidenceError(ValueError):
    """Fail-closed WP900 G8 independent-reentry evidence error."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise GwtIndependentReentryEvidenceError(
            f"{name} must be non-empty trimmed text"
        )
    if len(value) > _MAX_TEXT:
        raise GwtIndependentReentryEvidenceError(
            f"{name} exceeds {_MAX_TEXT} characters"
        )
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise GwtIndependentReentryEvidenceError(
            f"{name} contains control characters"
        )
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise GwtIndependentReentryEvidenceError(
            f"{name} must be lowercase 64-hex SHA-256"
        )
    return value


def _positive_int(name: str, value: Any) -> int:
    if type(value) is not int or value < 1:
        raise GwtIndependentReentryEvidenceError(
            f"{name} must be a positive integer"
        )
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GwtIndependentReentryEvidenceError(
            "provenance_refs must be an iterable of strings"
        )
    refs = tuple(_text("provenance_ref", value) for value in values)
    if not refs:
        raise GwtIndependentReentryEvidenceError(
            "provenance_refs must not be empty"
        )
    if len(set(refs)) != len(refs):
        raise GwtIndependentReentryEvidenceError(
            "provenance_refs must not contain duplicates"
        )
    return tuple(sorted(refs))


def _reject_constant(value: str) -> None:
    raise GwtIndependentReentryEvidenceError(
        f"non-finite JSON constant is not admissible: {value}"
    )


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GwtIndependentReentryEvidenceError(
                f"duplicate JSON key is not admissible: {key}"
            )
        result[key] = value
    return result


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
        raise GwtIndependentReentryEvidenceError(
            "value is not canonical-JSON encodable"
        ) from exc


def _digest_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_canonical_event_stream(raw_event_stream: bytes) -> tuple[dict[str, Any], ...]:
    """Parse the arm-agnostic observer stream and require canonical exact bytes."""

    if type(raw_event_stream) is not bytes or not raw_event_stream:
        raise GwtIndependentReentryEvidenceError(
            "raw_event_stream must be non-empty exact bytes"
        )
    if len(raw_event_stream) > _MAX_STREAM_BYTES:
        raise GwtIndependentReentryEvidenceError(
            "raw_event_stream exceeds size bound"
        )
    try:
        text = raw_event_stream.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GwtIndependentReentryEvidenceError(
            "raw_event_stream must be UTF-8 JSON"
        ) from exc
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_pairs_without_duplicates,
            parse_constant=_reject_constant,
        )
    except GwtIndependentReentryEvidenceError:
        raise
    except json.JSONDecodeError as exc:
        raise GwtIndependentReentryEvidenceError(
            "raw_event_stream is not valid JSON"
        ) from exc

    if type(parsed) is not list or not parsed:
        raise GwtIndependentReentryEvidenceError(
            "raw_event_stream must be a non-empty JSON event array"
        )
    if len(parsed) > _MAX_EVENTS:
        raise GwtIndependentReentryEvidenceError(
            "raw_event_stream exceeds event-count bound"
        )
    if _canonical_json(parsed) != text:
        raise GwtIndependentReentryEvidenceError(
            "raw_event_stream bytes must already be canonical JSON"
        )

    required_keys = {"kind", "observed_monotonic_ns", "event_sha256"}
    events: list[dict[str, Any]] = []
    last_ns = 0
    close_seen = False
    for index, event in enumerate(parsed):
        if type(event) is not dict or set(event) != required_keys:
            raise GwtIndependentReentryEvidenceError(
                "each observer event must contain exactly kind, observed_monotonic_ns and event_sha256"
            )
        kind = _text("kind", event["kind"])
        if kind not in {WINDOW_OPEN, REENTRY, WINDOW_CLOSE}:
            raise GwtIndependentReentryEvidenceError(
                f"unsupported observer event kind: {kind}"
            )
        observed_ns = _positive_int(
            "observed_monotonic_ns", event["observed_monotonic_ns"]
        )
        _sha256("event_sha256", event["event_sha256"])
        if observed_ns <= last_ns:
            raise GwtIndependentReentryEvidenceError(
                "observer event times must be strictly increasing"
            )
        last_ns = observed_ns

        if index == 0 and kind != WINDOW_OPEN:
            raise GwtIndependentReentryEvidenceError(
                "first observer event must be WINDOW_OPEN"
            )
        if index > 0 and kind == WINDOW_OPEN:
            raise GwtIndependentReentryEvidenceError(
                "observer stream must contain exactly one leading WINDOW_OPEN"
            )
        if close_seen:
            raise GwtIndependentReentryEvidenceError(
                "WINDOW_CLOSE must be the final observer event"
            )
        if kind == WINDOW_CLOSE:
            close_seen = True
        events.append(event)

    return tuple(events)


@dataclass(frozen=True, slots=True, kw_only=True)
class ConditionBlindReentryObservation:
    """Factory-sealed result derived before any arm label is accepted."""

    observer_identity: str
    observer_source_sha256: str
    runtime_instance_id: str
    exact_source_sha256: str
    boot_id_sha256: str
    execution_context_sha256: str
    raw_event_stream_sha256: str
    event_count: int
    window_start_monotonic_ns: int
    window_end_monotonic_ns: int | None
    reentry_event_sha256s: tuple[str, ...]
    status: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(
        default=None, init=False, repr=False, compare=False, hash=False
    )
    _factory_payload_sha256: str | None = field(
        default=None, init=False, repr=False, compare=False, hash=False
    )

    schema = CONDITION_BLIND_REENTRY_OBSERVATION_SCHEMA
    predicate = semantic.MATCHED_TASK_OUTCOME_PREDICATE
    evidence_scope = "CONDITION_BLIND_REENTRY_OBSERVATION_CANDIDATE"
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        for name in ("observer_identity", "runtime_instance_id"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "observer_source_sha256",
            "exact_source_sha256",
            "boot_id_sha256",
            "execution_context_sha256",
            "raw_event_stream_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        _positive_int("event_count", self.event_count)
        _positive_int("window_start_monotonic_ns", self.window_start_monotonic_ns)
        if self.window_end_monotonic_ns is not None:
            _positive_int("window_end_monotonic_ns", self.window_end_monotonic_ns)
            if self.window_end_monotonic_ns <= self.window_start_monotonic_ns:
                raise GwtIndependentReentryEvidenceError(
                    "window end must be after window start"
                )
        if type(self.reentry_event_sha256s) is not tuple:
            raise GwtIndependentReentryEvidenceError(
                "reentry_event_sha256s must be a tuple"
            )
        for digest in self.reentry_event_sha256s:
            _sha256("reentry_event_sha256", digest)
        if len(set(self.reentry_event_sha256s)) != len(self.reentry_event_sha256s):
            raise GwtIndependentReentryEvidenceError(
                "reentry event identities must not contain duplicates"
            )
        if self.status not in {
            REENTRY_OBSERVED,
            REENTRY_NOT_OBSERVED,
            REENTRY_OBSERVATION_UNKNOWN,
        }:
            raise GwtIndependentReentryEvidenceError(
                "unknown condition-blind re-entry status"
            )
        if self.status == REENTRY_OBSERVED and not self.reentry_event_sha256s:
            raise GwtIndependentReentryEvidenceError(
                "REENTRY_OBSERVED requires at least one re-entry event"
            )
        if self.status == REENTRY_NOT_OBSERVED:
            if self.reentry_event_sha256s:
                raise GwtIndependentReentryEvidenceError(
                    "REENTRY_NOT_OBSERVED cannot contain a re-entry event"
                )
            if self.window_end_monotonic_ns is None:
                raise GwtIndependentReentryEvidenceError(
                    "REENTRY_NOT_OBSERVED requires a complete observation window"
                )
        if self.status == REENTRY_OBSERVATION_UNKNOWN:
            if self.reentry_event_sha256s:
                raise GwtIndependentReentryEvidenceError(
                    "UNKNOWN cannot contain an observed re-entry event"
                )
            if self.window_end_monotonic_ns is not None:
                raise GwtIndependentReentryEvidenceError(
                    "UNKNOWN is reserved for incomplete no-reentry windows"
                )
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @classmethod
    def observe_event_stream(
        cls,
        *,
        raw_event_stream: bytes,
        observer_identity: str,
        observer_source_sha256: str,
        runtime_instance_id: str,
        exact_source_sha256: str,
        boot_id_sha256: str,
        execution_context_sha256: str,
        provenance_refs: Iterable[str],
    ) -> "ConditionBlindReentryObservation":
        """Derive the predicate without receiving intervention/control condition."""

        events = _parse_canonical_event_stream(raw_event_stream)
        reentry_digests = tuple(
            event["event_sha256"] for event in events if event["kind"] == REENTRY
        )
        window_end = (
            events[-1]["observed_monotonic_ns"]
            if events[-1]["kind"] == WINDOW_CLOSE
            else None
        )
        if reentry_digests:
            status = REENTRY_OBSERVED
        elif window_end is not None:
            status = REENTRY_NOT_OBSERVED
        else:
            status = REENTRY_OBSERVATION_UNKNOWN

        value = cls(
            observer_identity=observer_identity,
            observer_source_sha256=observer_source_sha256,
            runtime_instance_id=runtime_instance_id,
            exact_source_sha256=exact_source_sha256,
            boot_id_sha256=boot_id_sha256,
            execution_context_sha256=execution_context_sha256,
            raw_event_stream_sha256=hashlib.sha256(raw_event_stream).hexdigest(),
            event_count=len(events),
            window_start_monotonic_ns=events[0]["observed_monotonic_ns"],
            window_end_monotonic_ns=window_end,
            reentry_event_sha256s=reentry_digests,
            status=status,
            provenance_refs=tuple(provenance_refs),
        )
        object.__setattr__(value, "_factory_seal", _OBSERVATION_FACTORY)
        object.__setattr__(value, "_factory_payload_sha256", _digest_json(value.as_dict()))
        return value

    @property
    def derived_reentry_observed(self) -> bool | None:
        if self.status == REENTRY_OBSERVED:
            return True
        if self.status == REENTRY_NOT_OBSERVED:
            return False
        return None

    @property
    def last_observed_monotonic_ns(self) -> int:
        return self.window_end_monotonic_ns or self.window_start_monotonic_ns

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "predicate": self.predicate,
            "evidence_scope": self.evidence_scope,
            "observer_identity": self.observer_identity,
            "observer_source_sha256": self.observer_source_sha256,
            "runtime_instance_id": self.runtime_instance_id,
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "execution_context_sha256": self.execution_context_sha256,
            "raw_event_stream_sha256": self.raw_event_stream_sha256,
            "event_count": self.event_count,
            "window_start_monotonic_ns": self.window_start_monotonic_ns,
            "window_end_monotonic_ns": self.window_end_monotonic_ns,
            "reentry_event_sha256s": list(self.reentry_event_sha256s),
            "status": self.status,
            "derived_reentry_observed": self.derived_reentry_observed,
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


def validate_condition_blind_reentry_observation(
    value: ConditionBlindReentryObservation,
) -> None:
    if (
        type(value) is not ConditionBlindReentryObservation
        or value._factory_seal is not _OBSERVATION_FACTORY
    ):
        raise GwtIndependentReentryEvidenceError(
            "condition-blind observation lacks observer-factory origin"
        )
    if value._factory_payload_sha256 != _digest_json(value.as_dict()):
        raise GwtIndependentReentryEvidenceError(
            "condition-blind observation payload changed after observation"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class IndependentReentryOutcomeReadback:
    """Later arm binding of an already-derived condition-blind outcome."""

    condition: str
    task_id: str
    task_schema: str
    downstream_ref: str
    downstream_sha256: str
    observation_sha256: str
    reentry_observed: bool
    exact_source_sha256: str
    boot_id_sha256: str
    execution_context_sha256: str
    observer_identity: str
    observer_source_sha256: str
    runtime_instance_id: str
    observed_monotonic_ns: int
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(
        default=None, init=False, repr=False, compare=False, hash=False
    )
    _factory_payload_sha256: str | None = field(
        default=None, init=False, repr=False, compare=False, hash=False
    )

    schema = INDEPENDENT_REENTRY_OUTCOME_SCHEMA
    outcome_schema = semantic.MATCHED_TASK_OUTCOME_SCHEMA
    predicate = semantic.MATCHED_TASK_OUTCOME_PREDICATE
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
            raise GwtIndependentReentryEvidenceError(
                "outcome condition must be INTERVENTION_BROADCAST or CONTROL_NO_BROADCAST"
            )
        for name in (
            "task_id",
            "task_schema",
            "downstream_ref",
            "observer_identity",
            "runtime_instance_id",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if self.task_schema != semantic.WP900_MATCHED_TASK_SCHEMA:
            raise GwtIndependentReentryEvidenceError(
                "task schema does not bind the admitted WP900 matched task"
            )
        for name in (
            "downstream_sha256",
            "observation_sha256",
            "exact_source_sha256",
            "boot_id_sha256",
            "execution_context_sha256",
            "observer_source_sha256",
        ):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))
        if type(self.reentry_observed) is not bool:
            raise GwtIndependentReentryEvidenceError(
                "reentry_observed must be an already-derived boolean"
            )
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    @classmethod
    def bind_to_contract(
        cls,
        *,
        contract_candidate: GwtCausalRuntimeReadbackCandidate,
        observation: ConditionBlindReentryObservation,
        condition: str,
        task_id: str,
        task_schema: str,
        provenance_refs: Iterable[str],
    ) -> "IndependentReentryOutcomeReadback":
        """Apply an arm label only after the observation result is sealed."""

        if type(contract_candidate) is not GwtCausalRuntimeReadbackCandidate:
            raise GwtIndependentReentryEvidenceError(
                "contract_candidate must be exact GwtCausalRuntimeReadbackCandidate"
            )
        try:
            validate_causal_runtime_readback(contract_candidate)
        except ValueError as exc:
            raise GwtIndependentReentryEvidenceError(
                f"invalid causal runtime contract candidate: {exc}"
            ) from exc
        validate_condition_blind_reentry_observation(observation)

        if observation.status == REENTRY_OBSERVATION_UNKNOWN:
            raise GwtIndependentReentryEvidenceError(
                "condition-blind re-entry result is UNKNOWN because the observation window is incomplete"
            )
        if observation.exact_source_sha256 != contract_candidate.exact_source_sha256:
            raise GwtIndependentReentryEvidenceError(
                "observation exact-source identity does not bind causal contract"
            )
        if observation.boot_id_sha256 != contract_candidate.boot_id_sha256:
            raise GwtIndependentReentryEvidenceError(
                "observation boot identity does not bind causal contract"
            )
        if observation.execution_context_sha256 != contract_candidate.execution_context_sha256:
            raise GwtIndependentReentryEvidenceError(
                "observation execution-context identity does not bind causal contract"
            )

        if condition == "INTERVENTION_BROADCAST":
            downstream_ref = contract_candidate.intervention_downstream_ref
            downstream_sha256 = contract_candidate.intervention_downstream_sha256
        elif condition == "CONTROL_NO_BROADCAST":
            downstream_ref = contract_candidate.control_downstream_ref
            downstream_sha256 = contract_candidate.control_downstream_sha256
        else:
            raise GwtIndependentReentryEvidenceError("outcome condition is invalid")

        value = cls(
            condition=condition,
            task_id=task_id,
            task_schema=task_schema,
            downstream_ref=downstream_ref,
            downstream_sha256=downstream_sha256,
            observation_sha256=observation.sha256(),
            reentry_observed=bool(observation.derived_reentry_observed),
            exact_source_sha256=observation.exact_source_sha256,
            boot_id_sha256=observation.boot_id_sha256,
            execution_context_sha256=observation.execution_context_sha256,
            observer_identity=observation.observer_identity,
            observer_source_sha256=observation.observer_source_sha256,
            runtime_instance_id=observation.runtime_instance_id,
            observed_monotonic_ns=observation.last_observed_monotonic_ns,
            provenance_refs=tuple(provenance_refs),
        )
        object.__setattr__(value, "_factory_seal", _OUTCOME_FACTORY)
        object.__setattr__(value, "_factory_payload_sha256", _digest_json(value.as_dict()))
        return value

    def semantic_value(self) -> dict[str, Any]:
        return {
            "predicate": self.predicate,
            "observed": self.reentry_observed,
        }

    def to_semantic_arm(self) -> semantic.SemanticArmReadback:
        validate_independent_reentry_outcome(self)
        canonical = semantic._canonical_json(self.semantic_value())
        value = semantic.SemanticArmReadback(
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
            producer_identity=self.observer_identity,
            runtime_instance_id=self.runtime_instance_id,
            observed_monotonic_ns=self.observed_monotonic_ns,
            provenance_refs=self.provenance_refs,
        )
        object.__setattr__(value, "_factory_seal", semantic._ARM_FACTORY)
        object.__setattr__(
            value, "_factory_payload_sha256", semantic._digest_json(value.as_dict())
        )
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "condition": self.condition,
            "task_id": self.task_id,
            "task_schema": self.task_schema,
            "outcome_schema": self.outcome_schema,
            "predicate": self.predicate,
            "downstream_ref": self.downstream_ref,
            "downstream_sha256": self.downstream_sha256,
            "observation_sha256": self.observation_sha256,
            "reentry_observed": self.reentry_observed,
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "execution_context_sha256": self.execution_context_sha256,
            "observer_identity": self.observer_identity,
            "observer_source_sha256": self.observer_source_sha256,
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


def validate_independent_reentry_outcome(
    value: IndependentReentryOutcomeReadback,
) -> None:
    if (
        type(value) is not IndependentReentryOutcomeReadback
        or value._factory_seal is not _OUTCOME_FACTORY
    ):
        raise GwtIndependentReentryEvidenceError(
            "independent re-entry outcome lacks binder-factory origin"
        )
    if value._factory_payload_sha256 != _digest_json(value.as_dict()):
        raise GwtIndependentReentryEvidenceError(
            "independent re-entry outcome payload changed after bind"
        )


__all__ = [
    "CONDITION_BLIND_REENTRY_OBSERVATION_SCHEMA",
    "ConditionBlindReentryObservation",
    "GwtIndependentReentryEvidenceError",
    "INDEPENDENT_REENTRY_OUTCOME_SCHEMA",
    "IndependentReentryOutcomeReadback",
    "REENTRY",
    "REENTRY_NOT_OBSERVED",
    "REENTRY_OBSERVATION_UNKNOWN",
    "REENTRY_OBSERVED",
    "WINDOW_CLOSE",
    "WINDOW_OPEN",
    "validate_condition_blind_reentry_observation",
    "validate_independent_reentry_outcome",
]
