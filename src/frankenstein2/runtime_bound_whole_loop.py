"""Bind accepted WP900 G4 causal runtime readback into the existing whole-loop seal.

F2-WP-900 generation 5 repository-integration scope.

The deterministic :mod:`whole_persistent_loop` seal intentionally proves typed causal
persistence without claiming that the same source/boot/runtime actually executed it.
WP900 G4 separately binds a factory-origin causal runtime readback to exact source,
boot and execution-context identity.  This module closes only the missing provenance
seam between those two already-existing evidence surfaces.

It does not execute a model, scheduler, effect or persistence operation and it does not
mint target-runtime, semantic GWT/J-Space, physical GRID10, effect, completion, training
or whole-system credit.  External execution/reconciliation remains required for any
promotion beyond repository integration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable

from .grid10_interface import Grid10Plan
from .gwt_causal_path import GwtCausalPathSeal
from .gwt_causal_runtime_readback import (
    CAUSAL_RUNTIME_READBACK_OBSERVED,
    GwtCausalRuntimeReadbackCandidate,
    GwtCausalRuntimeReadbackError,
    validate_causal_runtime_readback,
)
from .whole_persistent_loop import GwtCausalValidationEvidence, WholePersistentLoopSeal

RUNTIME_BOUND_WHOLE_LOOP_SCHEMA = "FRANKENSTEIN2_RUNTIME_BOUND_WHOLE_LOOP/v1"
RUNTIME_BOUND_WHOLE_LOOP_CLASSIFICATION = (
    "RUNTIME_IDENTITY_BOUND_WHOLE_LOOP_CANDIDATE_NOT_SEMANTIC_GWT_OR_COMPLETION_AUTHORITY"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_MAX_REFS = 4096
_BOUND = object()


class RuntimeBoundWholeLoopError(ValueError):
    """Fail closed on mismatched whole-loop/runtime evidence."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise RuntimeBoundWholeLoopError(f"{name} must be non-empty trimmed text")
    if len(value) > _MAX_TEXT or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise RuntimeBoundWholeLoopError(f"{name} is outside the bounded text domain")
    return value


def _sha(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise RuntimeBoundWholeLoopError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise RuntimeBoundWholeLoopError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance_ref", value) for value in values)
    if not refs:
        raise RuntimeBoundWholeLoopError("provenance_refs must not be empty")
    if len(refs) > _MAX_REFS or len(set(refs)) != len(refs):
        raise RuntimeBoundWholeLoopError("provenance_refs exceed bounds or contain duplicates")
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
        raise RuntimeBoundWholeLoopError("value is not canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeBoundWholeLoopCandidate:
    schema: str
    whole_loop_seal_id: str
    whole_loop_seal_sha256: str
    grid_plan_id: str
    grid_plan_sha256: str
    gwt_seal_id: str
    gwt_seal_sha256: str
    causal_runtime_readback_sha256: str
    exact_source_sha256: str
    boot_id_sha256: str
    execution_context_sha256: str
    broadcast_id: str
    broadcast_sha256: str
    uptake_receipt_sha256: str
    causal_result_sha256: str
    causal_result_status: str
    classification: str
    provenance_refs: tuple[str, ...]
    _factory_seal: object | None = field(default=None, repr=False, compare=False, hash=False)
    _factory_payload_sha256: str | None = field(default=None, repr=False, compare=False, hash=False)

    evidence_scope = "REPOSITORY_RUNTIME_IDENTITY_TO_WHOLE_LOOP_BINDING_CANDIDATE"
    repository_component_credit = 0
    target_environment_component_runtime_credit = 0
    runtime_bound_whole_loop_candidate_credit = 0
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
        if self.schema != RUNTIME_BOUND_WHOLE_LOOP_SCHEMA:
            raise RuntimeBoundWholeLoopError("runtime-bound whole-loop schema mismatch")
        if self.classification != RUNTIME_BOUND_WHOLE_LOOP_CLASSIFICATION:
            raise RuntimeBoundWholeLoopError("runtime-bound whole-loop classification mismatch")
        for name in (
            "whole_loop_seal_id",
            "grid_plan_id",
            "gwt_seal_id",
            "broadcast_id",
            "causal_result_status",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        for name in (
            "whole_loop_seal_sha256",
            "grid_plan_sha256",
            "gwt_seal_sha256",
            "causal_runtime_readback_sha256",
            "exact_source_sha256",
            "boot_id_sha256",
            "execution_context_sha256",
            "broadcast_sha256",
            "uptake_receipt_sha256",
            "causal_result_sha256",
        ):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        if self.causal_result_status != "CAUSAL_INFLUENCE_OBSERVED_AT_CONTRACT_SCOPE":
            raise RuntimeBoundWholeLoopError("causal runtime result is not positive at contract scope")
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "whole_loop_seal_id": self.whole_loop_seal_id,
            "whole_loop_seal_sha256": self.whole_loop_seal_sha256,
            "grid_plan_id": self.grid_plan_id,
            "grid_plan_sha256": self.grid_plan_sha256,
            "gwt_seal_id": self.gwt_seal_id,
            "gwt_seal_sha256": self.gwt_seal_sha256,
            "causal_runtime_readback_sha256": self.causal_runtime_readback_sha256,
            "exact_source_sha256": self.exact_source_sha256,
            "boot_id_sha256": self.boot_id_sha256,
            "execution_context_sha256": self.execution_context_sha256,
            "broadcast_id": self.broadcast_id,
            "broadcast_sha256": self.broadcast_sha256,
            "uptake_receipt_sha256": self.uptake_receipt_sha256,
            "causal_result_sha256": self.causal_result_sha256,
            "causal_result_status": self.causal_result_status,
            "classification": self.classification,
            "provenance_refs": list(self.provenance_refs),
            "evidence_scope": self.evidence_scope,
            "repository_component_credit": self.repository_component_credit,
            "target_environment_component_runtime_credit": self.target_environment_component_runtime_credit,
            "runtime_bound_whole_loop_candidate_credit": self.runtime_bound_whole_loop_candidate_credit,
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
        return _digest(self.as_dict())


def bind_runtime_bound_whole_loop(
    *,
    whole_loop_seal: WholePersistentLoopSeal,
    plan: Grid10Plan,
    gwt_seal: GwtCausalPathSeal,
    gwt_evidence: GwtCausalValidationEvidence,
    causal_runtime_readback: GwtCausalRuntimeReadbackCandidate,
    provenance_refs: Iterable[str],
) -> RuntimeBoundWholeLoopCandidate:
    """Bind exact G4 runtime identity to the deterministic whole-loop evidence subject."""

    if type(whole_loop_seal) is not WholePersistentLoopSeal:
        raise RuntimeBoundWholeLoopError("whole_loop_seal must be exact WholePersistentLoopSeal")
    if type(plan) is not Grid10Plan:
        raise RuntimeBoundWholeLoopError("plan must be exact Grid10Plan")
    if type(gwt_seal) is not GwtCausalPathSeal:
        raise RuntimeBoundWholeLoopError("gwt_seal must be exact GwtCausalPathSeal")
    if type(gwt_evidence) is not GwtCausalValidationEvidence:
        raise RuntimeBoundWholeLoopError("gwt_evidence must be exact GwtCausalValidationEvidence")
    if type(causal_runtime_readback) is not GwtCausalRuntimeReadbackCandidate:
        raise RuntimeBoundWholeLoopError(
            "causal_runtime_readback must be exact GwtCausalRuntimeReadbackCandidate"
        )
    try:
        validate_causal_runtime_readback(causal_runtime_readback)
    except (GwtCausalRuntimeReadbackError, ValueError) as exc:
        raise RuntimeBoundWholeLoopError(f"invalid causal runtime readback: {exc}") from exc

    if causal_runtime_readback.classification != CAUSAL_RUNTIME_READBACK_OBSERVED:
        raise RuntimeBoundWholeLoopError("causal runtime readback classification is not positive")
    if whole_loop_seal.grid_plan_id != plan.plan_id or whole_loop_seal.grid_plan_sha256 != plan.sha256():
        raise RuntimeBoundWholeLoopError("whole-loop GRID10 plan identity mismatch")
    if whole_loop_seal.gwt_seal_id != gwt_seal.seal_id or whole_loop_seal.gwt_seal_sha256 != gwt_seal.sha256():
        raise RuntimeBoundWholeLoopError("whole-loop GWT seal identity mismatch")

    try:
        gwt_evidence.validate(seal=gwt_seal, plan=plan)
    except ValueError as exc:
        raise RuntimeBoundWholeLoopError(f"GWT source evidence rejected: {exc}") from exc

    broadcast = gwt_evidence.broadcast
    if (
        causal_runtime_readback.broadcast_id != broadcast.broadcast_id
        or causal_runtime_readback.broadcast_sha256 != broadcast.sha256()
    ):
        raise RuntimeBoundWholeLoopError("causal runtime readback/broadcast identity mismatch")

    if not any(
        receipt.sha256() == causal_runtime_readback.uptake_receipt_sha256
        and receipt.receipt_id in {bundle.uptake_receipt.receipt_id for bundle in gwt_evidence.reentry_bundles}
        for receipt in gwt_evidence.receipts
    ):
        raise RuntimeBoundWholeLoopError(
            "causal runtime readback uptake receipt is outside the whole-loop GWT evidence"
        )

    candidate = RuntimeBoundWholeLoopCandidate(
        schema=RUNTIME_BOUND_WHOLE_LOOP_SCHEMA,
        whole_loop_seal_id=whole_loop_seal.seal_id,
        whole_loop_seal_sha256=whole_loop_seal.sha256(),
        grid_plan_id=plan.plan_id,
        grid_plan_sha256=plan.sha256(),
        gwt_seal_id=gwt_seal.seal_id,
        gwt_seal_sha256=gwt_seal.sha256(),
        causal_runtime_readback_sha256=causal_runtime_readback.sha256(),
        exact_source_sha256=causal_runtime_readback.exact_source_sha256,
        boot_id_sha256=causal_runtime_readback.boot_id_sha256,
        execution_context_sha256=causal_runtime_readback.execution_context_sha256,
        broadcast_id=causal_runtime_readback.broadcast_id,
        broadcast_sha256=causal_runtime_readback.broadcast_sha256,
        uptake_receipt_sha256=causal_runtime_readback.uptake_receipt_sha256,
        causal_result_sha256=causal_runtime_readback.causal_result_sha256,
        causal_result_status=causal_runtime_readback.causal_result_status,
        classification=RUNTIME_BOUND_WHOLE_LOOP_CLASSIFICATION,
        provenance_refs=_refs(provenance_refs),
        _factory_seal=_BOUND,
    )
    object.__setattr__(candidate, "_factory_payload_sha256", _digest(candidate.as_dict()))
    return candidate


def validate_runtime_bound_whole_loop(candidate: RuntimeBoundWholeLoopCandidate) -> None:
    """Require binder factory origin and immutable payload; never promote evidence scope."""

    if type(candidate) is not RuntimeBoundWholeLoopCandidate or candidate._factory_seal is not _BOUND:
        raise RuntimeBoundWholeLoopError("runtime-bound whole-loop candidate lacks binder factory origin")
    if candidate._factory_payload_sha256 != _digest(candidate.as_dict()):
        raise RuntimeBoundWholeLoopError("runtime-bound whole-loop candidate payload changed after bind")


__all__ = [
    "RUNTIME_BOUND_WHOLE_LOOP_CLASSIFICATION",
    "RUNTIME_BOUND_WHOLE_LOOP_SCHEMA",
    "RuntimeBoundWholeLoopCandidate",
    "RuntimeBoundWholeLoopError",
    "bind_runtime_bound_whole_loop",
    "validate_runtime_bound_whole_loop",
]
