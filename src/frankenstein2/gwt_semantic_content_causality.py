"""WP900 G9 fail-closed semantic-content crossover discriminator.

This module deliberately sits *above* the accepted GWT runtime-witness and
uptake factories. It does not create delivery/uptake/re-entry evidence. It
only binds four already-observed live-path trials into a counterbalanced
content intervention.

The design closes the semantic-equivalence confound identified during the G9
review: one payload per semantic class would make payload identity perfectly
correlated with the claimed semantic class. Therefore a positive candidate
requires two byte-distinct, content-addressed surface variants for each of two
declared semantic classes (A1/A2 and B1/B2), a condition-blind outcome
observer, within-class outcome stability, and between-class outcome
discrimination.

Even a positive repository candidate mints no target-runtime, semantic GWT,
J-Space, effect, training, completion, or whole-system credit. Exact admitted
target execution and separate reconciliation remain required.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable

from frankenstein2.gwt_runtime_witness import (
    GwtRuntimeWitnessReceipt,
    LIVE_GWT_PATH_OBSERVED,
    validate_gwt_runtime_witness_receipt,
)
from frankenstein2.gwt_uptake import CellUptakeReceipt, GWTUptakeError
from frankenstein2.gwt_workspace import BroadcastEnvelope

SEMANTIC_CONTENT_TRIAL_SCHEMA = "FRANKENSTEIN2_GWT_SEMANTIC_CONTENT_TRIAL/v1"
SEMANTIC_CONTENT_CROSSOVER_SCHEMA = "FRANKENSTEIN2_GWT_SEMANTIC_CONTENT_CROSSOVER/v1"
SEMANTIC_CONTENT_CAUSALITY_CANDIDATE = (
    "SEMANTIC_CONTENT_CAUSALITY_CANDIDATE_REQUIRES_TARGET_EXECUTION_ADMISSION"
)
SEMANTIC_CONTENT_FAIL_CLOSED = "SEMANTIC_CONTENT_CAUSALITY_NOT_ESTABLISHED"
CONTENT_REF_PREFIX = "sha256:"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_MAX_PAYLOAD_BYTES = 1_048_576
_MAX_OUTCOME_BYTES = 1_048_576
_MAX_CANONICAL_JSON = 65_536
_BLIND_OUTCOME_FACTORY = object()
_TRIAL_FACTORY = object()
_CROSSOVER_FACTORY = object()


class GwtSemanticContentCausalityError(ValueError):
    """Fail-closed WP900 G9 semantic-content crossover error."""


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
        raise GwtSemanticContentCausalityError(
            "value is not canonical-JSON encodable"
        ) from exc
    if len(encoded.encode("utf-8")) > _MAX_CANONICAL_JSON:
        raise GwtSemanticContentCausalityError("canonical JSON exceeds size bound")
    return encoded


def _reject_constant(value: str) -> None:
    raise GwtSemanticContentCausalityError(
        f"non-finite JSON constant is not admissible: {value}"
    )


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GwtSemanticContentCausalityError(
                f"duplicate JSON key is not admissible: {key}"
            )
        result[key] = value
    return result


def _canonical_json_bytes(name: str, raw: bytes, *, max_bytes: int) -> tuple[str, str]:
    if type(raw) is not bytes or not raw:
        raise GwtSemanticContentCausalityError(f"{name} must be non-empty exact bytes")
    if len(raw) > max_bytes:
        raise GwtSemanticContentCausalityError(f"{name} exceeds size bound")
    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs_without_duplicates,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise GwtSemanticContentCausalityError(f"{name} must be UTF-8 JSON") from exc
    except GwtSemanticContentCausalityError:
        raise
    except json.JSONDecodeError as exc:
        raise GwtSemanticContentCausalityError(f"{name} must be valid JSON") from exc
    canonical = _canonical_json(parsed)
    return canonical, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _refs(name: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise GwtSemanticContentCausalityError(f"{name} must be an iterable of strings")
    refs = tuple(_text(f"{name} item", value) for value in values)
    if not refs:
        raise GwtSemanticContentCausalityError(f"{name} must not be empty")
    if len(set(refs)) != len(refs):
        raise GwtSemanticContentCausalityError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


@dataclass(frozen=True, slots=True, kw_only=True)
class MatchedCrossoverMechanics:
    """Caller-observed mechanics that must remain identical across all four trials."""

    task_id: str
    task_schema: str
    context_sha256: str
    pre_state_sha256: str
    executor_identity: str
    execution_context_sha256: str

    def __post_init__(self) -> None:
        for name in ("task_id", "task_schema", "executor_identity"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in ("context_sha256", "pre_state_sha256", "execution_context_sha256"):
            object.__setattr__(self, name, _sha256(name, getattr(self, name)))

    def as_dict(self) -> dict[str, str]:
        return {
            "task_id": self.task_id,
            "task_schema": self.task_schema,
            "context_sha256": self.context_sha256,
            "pre_state_sha256": self.pre_state_sha256,
            "executor_identity": self.executor_identity,
            "execution_context_sha256": self.execution_context_sha256,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ContentAddressedSemanticPayload:
    """Exact treatment bytes plus a declared semantic class and surface variant."""

    semantic_class_id: str
    surface_variant_id: str
    payload_ref: str
    payload_sha256: str
    payload_size_bytes: int
    _payload_bytes: bytes = field(repr=False, compare=False, hash=False)

    @classmethod
    def from_bytes(
        cls,
        *,
        semantic_class_id: str,
        surface_variant_id: str,
        payload_bytes: bytes,
    ) -> "ContentAddressedSemanticPayload":
        if type(payload_bytes) is not bytes or not payload_bytes:
            raise GwtSemanticContentCausalityError(
                "payload_bytes must be non-empty exact bytes"
            )
        if len(payload_bytes) > _MAX_PAYLOAD_BYTES:
            raise GwtSemanticContentCausalityError("payload_bytes exceeds size bound")
        digest = hashlib.sha256(payload_bytes).hexdigest()
        return cls(
            semantic_class_id=semantic_class_id,
            surface_variant_id=surface_variant_id,
            payload_ref=f"{CONTENT_REF_PREFIX}{digest}",
            payload_sha256=digest,
            payload_size_bytes=len(payload_bytes),
            _payload_bytes=payload_bytes,
        )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "semantic_class_id", _text("semantic_class_id", self.semantic_class_id)
        )
        object.__setattr__(
            self, "surface_variant_id", _text("surface_variant_id", self.surface_variant_id)
        )
        object.__setattr__(self, "payload_sha256", _sha256("payload_sha256", self.payload_sha256))
        if self.payload_ref != f"{CONTENT_REF_PREFIX}{self.payload_sha256}":
            raise GwtSemanticContentCausalityError(
                "payload_ref must be exact sha256:<payload_sha256> content address"
            )
        if type(self._payload_bytes) is not bytes or not self._payload_bytes:
            raise GwtSemanticContentCausalityError("payload bytes are required")
        if len(self._payload_bytes) != self.payload_size_bytes:
            raise GwtSemanticContentCausalityError("payload_size_bytes mismatch")
        if hashlib.sha256(self._payload_bytes).hexdigest() != self.payload_sha256:
            raise GwtSemanticContentCausalityError("payload bytes do not match content address")

    def as_dict(self) -> dict[str, Any]:
        return {
            "semantic_class_id": self.semantic_class_id,
            "surface_variant_id": self.surface_variant_id,
            "payload_ref": self.payload_ref,
            "payload_sha256": self.payload_sha256,
            "payload_size_bytes": self.payload_size_bytes,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class BlindSemanticOutcome:
    """Outcome observation API intentionally has no treatment/class parameters."""

    downstream_ref: str
    downstream_sha256: str
    canonical_json: str
    semantic_sha256: str
    observer_identity: str
    observed_monotonic_ns: int
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(
        default=None, repr=False, compare=False, hash=False
    )

    @classmethod
    def observe_json(
        cls,
        *,
        uptake_receipt: CellUptakeReceipt,
        raw_downstream_bytes: bytes,
        observer_identity: str,
        observed_monotonic_ns: int,
        provenance_refs: Iterable[str],
    ) -> "BlindSemanticOutcome":
        if type(uptake_receipt) is not CellUptakeReceipt:
            raise GwtSemanticContentCausalityError(
                "uptake_receipt must be exact CellUptakeReceipt"
            )
        if uptake_receipt.uptake_status != "UPTAKEN":
            raise GwtSemanticContentCausalityError(
                "blind semantic outcome requires UPTAKEN receipt"
            )
        if uptake_receipt.downstream_ref is None or uptake_receipt.downstream_sha256 is None:
            raise GwtSemanticContentCausalityError(
                "uptake receipt lacks downstream readback binding"
            )
        if type(raw_downstream_bytes) is not bytes:
            raise GwtSemanticContentCausalityError(
                "raw_downstream_bytes must be exact bytes"
            )
        raw_sha = hashlib.sha256(raw_downstream_bytes).hexdigest()
        if raw_sha != uptake_receipt.downstream_sha256:
            raise GwtSemanticContentCausalityError(
                "raw downstream bytes do not match uptake receipt SHA-256"
            )
        canonical, semantic_sha = _canonical_json_bytes(
            "raw_downstream_bytes",
            raw_downstream_bytes,
            max_bytes=_MAX_OUTCOME_BYTES,
        )
        value = cls(
            downstream_ref=uptake_receipt.downstream_ref,
            downstream_sha256=raw_sha,
            canonical_json=canonical,
            semantic_sha256=semantic_sha,
            observer_identity=observer_identity,
            observed_monotonic_ns=observed_monotonic_ns,
            provenance_refs=tuple(provenance_refs),
            _factory_seal=_BLIND_OUTCOME_FACTORY,
        )
        object.__setattr__(value, "_factory_payload_sha256", _digest(value.as_dict()))
        return value

    def __post_init__(self) -> None:
        object.__setattr__(self, "downstream_ref", _text("downstream_ref", self.downstream_ref))
        object.__setattr__(
            self, "downstream_sha256", _sha256("downstream_sha256", self.downstream_sha256)
        )
        object.__setattr__(
            self, "semantic_sha256", _sha256("semantic_sha256", self.semantic_sha256)
        )
        object.__setattr__(
            self, "observer_identity", _text("observer_identity", self.observer_identity)
        )
        _positive_int("observed_monotonic_ns", self.observed_monotonic_ns)
        parsed_canonical, semantic_sha = _canonical_json_bytes(
            "canonical_json",
            self.canonical_json.encode("utf-8"),
            max_bytes=_MAX_OUTCOME_BYTES,
        )
        if parsed_canonical != self.canonical_json:
            raise GwtSemanticContentCausalityError("canonical_json is not canonical")
        if semantic_sha != self.semantic_sha256:
            raise GwtSemanticContentCausalityError(
                "semantic_sha256 does not bind canonical outcome"
            )
        object.__setattr__(
            self, "provenance_refs", _refs("provenance_refs", self.provenance_refs)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "downstream_ref": self.downstream_ref,
            "downstream_sha256": self.downstream_sha256,
            "canonical_json": self.canonical_json,
            "semantic_sha256": self.semantic_sha256,
            "observer_identity": self.observer_identity,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "provenance_refs": list(self.provenance_refs),
        }


def validate_blind_semantic_outcome(outcome: BlindSemanticOutcome) -> None:
    if (
        type(outcome) is not BlindSemanticOutcome
        or outcome._factory_seal is not _BLIND_OUTCOME_FACTORY
    ):
        raise GwtSemanticContentCausalityError(
            "blind semantic outcome lacks observation factory origin"
        )
    if outcome._factory_payload_sha256 != _digest(outcome.as_dict()):
        raise GwtSemanticContentCausalityError(
            "blind semantic outcome payload changed after observation"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticContentTrial:
    schema: str
    order_position: int
    mechanics: MatchedCrossoverMechanics
    payload: ContentAddressedSemanticPayload
    broadcast: BroadcastEnvelope
    uptake_receipt: CellUptakeReceipt
    runtime_witness: GwtRuntimeWitnessReceipt
    blind_outcome: BlindSemanticOutcome
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(
        default=None, repr=False, compare=False, hash=False
    )

    @classmethod
    def bind(
        cls,
        *,
        order_position: int,
        mechanics: MatchedCrossoverMechanics,
        payload: ContentAddressedSemanticPayload,
        broadcast: BroadcastEnvelope,
        uptake_receipt: CellUptakeReceipt,
        runtime_witness: GwtRuntimeWitnessReceipt,
        blind_outcome: BlindSemanticOutcome,
    ) -> "SemanticContentTrial":
        if type(mechanics) is not MatchedCrossoverMechanics:
            raise GwtSemanticContentCausalityError(
                "mechanics must be exact MatchedCrossoverMechanics"
            )
        if type(payload) is not ContentAddressedSemanticPayload:
            raise GwtSemanticContentCausalityError(
                "payload must be exact ContentAddressedSemanticPayload"
            )
        if type(broadcast) is not BroadcastEnvelope:
            raise GwtSemanticContentCausalityError("broadcast must be exact BroadcastEnvelope")
        if type(uptake_receipt) is not CellUptakeReceipt:
            raise GwtSemanticContentCausalityError(
                "uptake_receipt must be exact CellUptakeReceipt"
            )
        if type(runtime_witness) is not GwtRuntimeWitnessReceipt:
            raise GwtSemanticContentCausalityError(
                "runtime_witness must be exact GwtRuntimeWitnessReceipt"
            )
        if type(blind_outcome) is not BlindSemanticOutcome:
            raise GwtSemanticContentCausalityError(
                "blind_outcome must be exact BlindSemanticOutcome"
            )
        validate_blind_semantic_outcome(blind_outcome)
        validate_gwt_runtime_witness_receipt(runtime_witness)
        try:
            uptake_receipt.assert_broadcast_binding(broadcast)
        except GWTUptakeError as exc:
            raise GwtSemanticContentCausalityError(
                f"invalid uptake/broadcast binding: {exc}"
            ) from exc
        if runtime_witness.classification != LIVE_GWT_PATH_OBSERVED:
            raise GwtSemanticContentCausalityError(
                "trial requires validated live DELIVERY->UPTAKE->REENTRY witness"
            )
        if (
            runtime_witness.broadcast_id != broadcast.broadcast_id
            or runtime_witness.broadcast_sha256 != broadcast.sha256()
        ):
            raise GwtSemanticContentCausalityError(
                "runtime witness/broadcast identity mismatch"
            )
        if (
            runtime_witness.uptake_receipt_id != uptake_receipt.receipt_id
            or runtime_witness.uptake_receipt_sha256 != uptake_receipt.sha256()
        ):
            raise GwtSemanticContentCausalityError(
                "runtime witness/uptake receipt identity mismatch"
            )
        if runtime_witness.recipient_cell_id != uptake_receipt.cell_id:
            raise GwtSemanticContentCausalityError(
                "runtime witness/uptake recipient mismatch"
            )
        if (
            blind_outcome.downstream_ref != uptake_receipt.downstream_ref
            or blind_outcome.downstream_sha256 != uptake_receipt.downstream_sha256
        ):
            raise GwtSemanticContentCausalityError(
                "blind outcome/uptake downstream binding mismatch"
            )
        if blind_outcome.observed_monotonic_ns <= runtime_witness.events[-1].observed_monotonic_ns:
            raise GwtSemanticContentCausalityError(
                "blind downstream outcome must be observed after runtime re-entry"
            )
        if len(broadcast.candidate_payload_refs) != 1:
            raise GwtSemanticContentCausalityError(
                "semantic-content trial requires exactly one broadcast payload ref"
            )
        if broadcast.candidate_payload_refs[0] != payload.payload_ref:
            raise GwtSemanticContentCausalityError(
                "broadcast payload ref does not bind content-addressed treatment bytes"
            )
        value = cls(
            schema=SEMANTIC_CONTENT_TRIAL_SCHEMA,
            order_position=order_position,
            mechanics=mechanics,
            payload=payload,
            broadcast=broadcast,
            uptake_receipt=uptake_receipt,
            runtime_witness=runtime_witness,
            blind_outcome=blind_outcome,
            _factory_seal=_TRIAL_FACTORY,
        )
        object.__setattr__(value, "_factory_payload_sha256", _digest(value.as_dict()))
        return value

    def __post_init__(self) -> None:
        if self.schema != SEMANTIC_CONTENT_TRIAL_SCHEMA:
            raise GwtSemanticContentCausalityError("semantic content trial schema mismatch")
        _positive_int("order_position", self.order_position)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "order_position": self.order_position,
            "mechanics": self.mechanics.as_dict(),
            "payload": self.payload.as_dict(),
            "broadcast_id": self.broadcast.broadcast_id,
            "broadcast_sha256": self.broadcast.sha256(),
            "uptake_receipt_id": self.uptake_receipt.receipt_id,
            "uptake_receipt_sha256": self.uptake_receipt.sha256(),
            "runtime_witness_sha256": self.runtime_witness.sha256(),
            "runtime_identity": self.runtime_witness.identity.as_dict(),
            "recipient_cell_id": self.runtime_witness.recipient_cell_id,
            "blind_outcome": self.blind_outcome.as_dict(),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


def validate_semantic_content_trial(trial: SemanticContentTrial) -> None:
    if type(trial) is not SemanticContentTrial or trial._factory_seal is not _TRIAL_FACTORY:
        raise GwtSemanticContentCausalityError(
            "semantic content trial lacks binder factory origin"
        )
    if trial._factory_payload_sha256 != _digest(trial.as_dict()):
        raise GwtSemanticContentCausalityError(
            "semantic content trial payload changed after bind"
        )
    validate_gwt_runtime_witness_receipt(trial.runtime_witness)
    validate_blind_semantic_outcome(trial.blind_outcome)
    try:
        trial.uptake_receipt.assert_broadcast_binding(trial.broadcast)
    except GWTUptakeError as exc:
        raise GwtSemanticContentCausalityError(
            f"semantic content trial uptake/broadcast validation failed: {exc}"
        ) from exc
    if trial.runtime_witness.broadcast_sha256 != trial.broadcast.sha256():
        raise GwtSemanticContentCausalityError(
            "semantic content trial runtime/broadcast hash mismatch"
        )
    if trial.runtime_witness.uptake_receipt_sha256 != trial.uptake_receipt.sha256():
        raise GwtSemanticContentCausalityError(
            "semantic content trial runtime/uptake hash mismatch"
        )
    if trial.broadcast.candidate_payload_refs != (trial.payload.payload_ref,):
        raise GwtSemanticContentCausalityError(
            "semantic content trial broadcast treatment changed after bind"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class SemanticContentCrossoverCandidate:
    schema: str
    crossover_id: str
    trials: tuple[
        SemanticContentTrial,
        SemanticContentTrial,
        SemanticContentTrial,
        SemanticContentTrial,
    ]
    semantic_class_ids: tuple[str, str]
    class_outcome_sha256: tuple[str, str]
    exact_source_sha256: str
    boot_id_sha256: str
    process_identity: str
    runtime_instance_id: str
    classification: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(
        default=None, repr=False, compare=False, hash=False
    )

    evidence_scope = (
        "FOUR_TRIAL_ORTHOGONALIZED_SEMANTIC_CONTENT_CAUSALITY_CANDIDATE_ONLY"
    )
    semantic_equivalence_basis = (
        "TWO_DISTINCT_SURFACE_VARIANTS_PER_DECLARED_CLASS_WITH_BLIND_OUTCOME_STABILITY"
    )
    repository_ci_credit = 0
    target_environment_component_runtime_credit = 0
    semantic_content_causal_candidate_credit = 0
    gwt_runtime_credit = 0
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    physical_grid10_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def __post_init__(self) -> None:
        if self.schema != SEMANTIC_CONTENT_CROSSOVER_SCHEMA:
            raise GwtSemanticContentCausalityError("semantic content crossover schema mismatch")
        object.__setattr__(self, "crossover_id", _text("crossover_id", self.crossover_id))
        if self.classification not in {
            SEMANTIC_CONTENT_CAUSALITY_CANDIDATE,
            SEMANTIC_CONTENT_FAIL_CLOSED,
        }:
            raise GwtSemanticContentCausalityError("unsupported crossover classification")
        object.__setattr__(
            self, "exact_source_sha256", _sha256("exact_source_sha256", self.exact_source_sha256)
        )
        object.__setattr__(
            self, "boot_id_sha256", _sha256("boot_id_sha256", self.boot_id_sha256)
        )
        object.__setattr__(
            self, "process_identity", _text("process_identity", self.process_identity)
        )
        object.__setattr__(
            self, "runtime_instance_id", _text("runtime_instance_id", self.runtime_instance_id)
        )
        object.__setattr__(
            self, "provenance_refs", _refs("provenance_refs", self.provenance_refs)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "crossover_id": self.crossover_id,
            "trials": [trial.as_dict() for trial in self.trials],
            "semantic_class_ids": list(self.semantic_class_ids),
            "class_outcome_sha256": list(self.class_outcome_sha256),
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "process_identity": self.process_identity,
            "runtime_instance_id": self.runtime_instance_id,
            "classification": self.classification,
            "provenance_refs": list(self.provenance_refs),
            "evidence_scope": self.evidence_scope,
            "semantic_equivalence_basis": self.semantic_equivalence_basis,
            "repository_ci_credit": self.repository_ci_credit,
            "target_environment_component_runtime_credit": self.target_environment_component_runtime_credit,
            "semantic_content_causal_candidate_credit": self.semantic_content_causal_candidate_credit,
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
        return _digest(self.as_dict())


def build_semantic_content_crossover(
    *,
    crossover_id: str,
    trials: tuple[
        SemanticContentTrial,
        SemanticContentTrial,
        SemanticContentTrial,
        SemanticContentTrial,
    ],
    provenance_refs: Iterable[str],
) -> SemanticContentCrossoverCandidate:
    """Build the four-trial A/B/B/A or B/A/A/B orthogonalized candidate.

    Any violated causal discriminator raises and therefore cannot be accidentally
    promoted as a semantic-content causal candidate.
    """
    if type(trials) is not tuple or len(trials) != 4:
        raise GwtSemanticContentCausalityError(
            "crossover requires exactly four immutable trials"
        )
    for trial in trials:
        validate_semantic_content_trial(trial)
    if tuple(trial.order_position for trial in trials) != (1, 2, 3, 4):
        raise GwtSemanticContentCausalityError(
            "trials must be supplied in exact order positions 1,2,3,4"
        )

    mechanics = trials[0].mechanics
    if any(trial.mechanics != mechanics for trial in trials[1:]):
        raise GwtSemanticContentCausalityError(
            "task/context/pre-state/executor mechanics are not matched"
        )

    identities = tuple(trial.runtime_witness.identity for trial in trials)
    first_identity = identities[0]
    if any(identity != first_identity for identity in identities[1:]):
        raise GwtSemanticContentCausalityError(
            "source/boot/process/runtime identity is not matched across crossover"
        )

    recipient = trials[0].runtime_witness.recipient_cell_id
    if any(trial.runtime_witness.recipient_cell_id != recipient for trial in trials[1:]):
        raise GwtSemanticContentCausalityError(
            "recipient identity is not matched across crossover"
        )

    plan_binding = (
        trials[0].broadcast.plan_id,
        trials[0].broadcast.plan_generation,
        trials[0].broadcast.plan_sha256,
    )
    for trial in trials[1:]:
        if (
            trial.broadcast.plan_id,
            trial.broadcast.plan_generation,
            trial.broadcast.plan_sha256,
        ) != plan_binding:
            raise GwtSemanticContentCausalityError(
                "GRID10 plan mechanics are not matched across crossover"
            )

    observer = trials[0].blind_outcome.observer_identity
    if any(trial.blind_outcome.observer_identity != observer for trial in trials[1:]):
        raise GwtSemanticContentCausalityError(
            "condition-blind observer identity changed across crossover"
        )

    classes = tuple(trial.payload.semantic_class_id for trial in trials)
    class_ids = tuple(sorted(set(classes)))
    if len(class_ids) != 2:
        raise GwtSemanticContentCausalityError(
            "crossover requires exactly two declared semantic classes"
        )
    if classes not in (
        (class_ids[0], class_ids[1], class_ids[1], class_ids[0]),
        (class_ids[1], class_ids[0], class_ids[0], class_ids[1]),
    ):
        raise GwtSemanticContentCausalityError(
            "semantic classes must be counterbalanced A/B/B/A or B/A/A/B"
        )

    payload_hashes = tuple(trial.payload.payload_sha256 for trial in trials)
    if len(set(payload_hashes)) != 4:
        raise GwtSemanticContentCausalityError(
            "semantic-equivalence control requires four byte-distinct payload variants"
        )

    broadcast_hashes = tuple(trial.broadcast.sha256() for trial in trials)
    if len(set(broadcast_hashes)) != 4:
        raise GwtSemanticContentCausalityError(
            "each surface variant requires a distinct bound broadcast"
        )

    class_outcomes: list[str] = []
    for class_id in class_ids:
        members = [trial for trial in trials if trial.payload.semantic_class_id == class_id]
        if len(members) != 2:
            raise GwtSemanticContentCausalityError(
                "each semantic class requires exactly two trials"
            )
        variants = {trial.payload.surface_variant_id for trial in members}
        if len(variants) != 2:
            raise GwtSemanticContentCausalityError(
                "each semantic class requires two distinct surface_variant_id values"
            )
        outcomes = {trial.blind_outcome.semantic_sha256 for trial in members}
        if len(outcomes) != 1:
            raise GwtSemanticContentCausalityError(
                "blind downstream semantics are not stable across same-class surface variants"
            )
        class_outcomes.append(next(iter(outcomes)))

    if class_outcomes[0] == class_outcomes[1]:
        raise GwtSemanticContentCausalityError(
            "different semantic classes did not produce different blind downstream semantics"
        )

    value = SemanticContentCrossoverCandidate(
        schema=SEMANTIC_CONTENT_CROSSOVER_SCHEMA,
        crossover_id=crossover_id,
        trials=trials,
        semantic_class_ids=(class_ids[0], class_ids[1]),
        class_outcome_sha256=(class_outcomes[0], class_outcomes[1]),
        exact_source_sha256=first_identity.exact_source_sha256,
        boot_id_sha256=first_identity.boot_id_sha256,
        process_identity=first_identity.process_identity,
        runtime_instance_id=first_identity.runtime_instance_id,
        classification=SEMANTIC_CONTENT_CAUSALITY_CANDIDATE,
        provenance_refs=tuple(provenance_refs),
        _factory_seal=_CROSSOVER_FACTORY,
    )
    object.__setattr__(value, "_factory_payload_sha256", _digest(value.as_dict()))
    return value


def validate_semantic_content_crossover(
    candidate: SemanticContentCrossoverCandidate,
) -> None:
    if (
        type(candidate) is not SemanticContentCrossoverCandidate
        or candidate._factory_seal is not _CROSSOVER_FACTORY
    ):
        raise GwtSemanticContentCausalityError(
            "semantic content crossover lacks builder factory origin"
        )
    if candidate._factory_payload_sha256 != _digest(candidate.as_dict()):
        raise GwtSemanticContentCausalityError(
            "semantic content crossover payload changed after build"
        )
    rebuilt = build_semantic_content_crossover(
        crossover_id=candidate.crossover_id,
        trials=candidate.trials,
        provenance_refs=candidate.provenance_refs,
    )
    if rebuilt.as_dict() != candidate.as_dict():
        raise GwtSemanticContentCausalityError(
            "semantic content crossover no longer matches source trials"
        )


__all__ = [
    "BlindSemanticOutcome",
    "ContentAddressedSemanticPayload",
    "GwtSemanticContentCausalityError",
    "MatchedCrossoverMechanics",
    "SEMANTIC_CONTENT_CAUSALITY_CANDIDATE",
    "SEMANTIC_CONTENT_CROSSOVER_SCHEMA",
    "SEMANTIC_CONTENT_FAIL_CLOSED",
    "SEMANTIC_CONTENT_TRIAL_SCHEMA",
    "SemanticContentCrossoverCandidate",
    "SemanticContentTrial",
    "build_semantic_content_crossover",
    "validate_blind_semantic_outcome",
    "validate_semantic_content_crossover",
    "validate_semantic_content_trial",
]
