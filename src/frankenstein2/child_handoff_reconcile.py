"""F2-WP-602 deterministic child handoff/reconcile evidence composition.

This component composes already-accepted repository contracts only:

    F2-WP-600 DELEGATE_BUILD RouteCandidate
      -> F2-WP-601 NativeChildRequest
      -> F2-WP-102 result-bound NativeChildBinding
      -> F2-WP-104 DeferredReturnEnvelope

It does not spawn a child, transport a payload, acknowledge delivery, inspect result
semantics, write UnifiedDB, decide execution/completion, authorize effects, or mint
runtime/GRID/GWT/J-Space/training/whole-system credit.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from .causal_identity import CausalIdentity
from .deferred_return import DeferredReturnEnvelope
from .direct_delegate_router import DELEGATE_BUILD, RouteCandidate
from .native_child_abi import NativeChildRequest, verify_native_child_request
from .native_child_binding import NativeChildBinding

HANDOFF_SCHEMA = "FRANKENSTEIN2_CHILD_HANDOFF_EVIDENCE/v1"
RECONCILE_SCHEMA = "FRANKENSTEIN2_CHILD_RECONCILE_EVIDENCE/v1"
HANDOFF_CLASSIFICATION = "EVIDENCE_ONLY_NOT_SPAWN_DELIVERY_EFFECT_OR_COMPLETION_AUTHORITY"
RECONCILE_CLASSIFICATION = "EVIDENCE_ONLY_NOT_RESULT_SUCCESS_EFFECT_OR_COMPLETION_AUTHORITY"
_MAX_IDENTIFIER_LENGTH = 512
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ChildHandoffReconcileError(ValueError):
    """Raised when Stage-6 child evidence is incomplete or contradictory."""


def _identifier(name: str, value: Any) -> str:
    if type(value) is not str:
        raise ChildHandoffReconcileError(f"{name} must be a string")
    if not value or value != value.strip():
        raise ChildHandoffReconcileError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise ChildHandoffReconcileError(f"{name} exceeds {_MAX_IDENTIFIER_LENGTH} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ChildHandoffReconcileError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ChildHandoffReconcileError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _handoff_identity_payload(
    route_candidate: RouteCandidate,
    route_candidate_sha256: str,
    child_request: NativeChildRequest,
    child_request_sha256: str,
) -> dict[str, Any]:
    return {
        "route_candidate_id": route_candidate.candidate_id,
        "route_candidate_sha256": route_candidate_sha256,
        "task_id": route_candidate.task_id,
        "task_generation": route_candidate.task_generation,
        "task_sha256": route_candidate.task_sha256,
        "child_request_id": child_request.request_id,
        "child_request_generation": child_request.request_generation,
        "child_request_sha256": child_request_sha256,
        "binding_id": child_request.binding_id,
        "binding_sha256": child_request.binding_sha256,
        "child_causal_id": child_request.binding.child.causal_id,
    }


def _handoff_id(
    route_candidate: RouteCandidate,
    route_candidate_sha256: str,
    child_request: NativeChildRequest,
    child_request_sha256: str,
) -> str:
    return "handoff:" + _digest(
        _handoff_identity_payload(
            route_candidate,
            route_candidate_sha256,
            child_request,
            child_request_sha256,
        )
    )


def _reconcile_identity_payload(
    handoff: "ChildHandoffEvidence",
    handoff_sha256: str,
    result_binding: NativeChildBinding,
    result_binding_sha256: str,
    deferred_return: DeferredReturnEnvelope,
    deferred_return_sha256: str,
) -> dict[str, Any]:
    return {
        "handoff_id": handoff.handoff_id,
        "handoff_sha256": handoff_sha256,
        "binding_id": result_binding.binding_id(),
        "result_binding_sha256": result_binding_sha256,
        "result_id": result_binding.result_id,
        "result_sha256": result_binding.result_sha256,
        "return_id": deferred_return.return_id,
        "deferred_return_sha256": deferred_return_sha256,
        "resume_causal_id": deferred_return.resume.causal_id,
        "resume_sha256": deferred_return.resume.sha256(),
    }


def _reconcile_id(
    handoff: "ChildHandoffEvidence",
    handoff_sha256: str,
    result_binding: NativeChildBinding,
    result_binding_sha256: str,
    deferred_return: DeferredReturnEnvelope,
    deferred_return_sha256: str,
) -> str:
    return "reconcile:" + _digest(
        _reconcile_identity_payload(
            handoff,
            handoff_sha256,
            result_binding,
            result_binding_sha256,
            deferred_return,
            deferred_return_sha256,
        )
    )


def _rebuild_route_candidate(value: Any) -> RouteCandidate:
    if not isinstance(value, Mapping):
        raise ChildHandoffReconcileError("route_candidate must be a mapping")
    expected = {
        "schema",
        "candidate_id",
        "task_id",
        "task_generation",
        "task_sha256",
        "request_sha256",
        "cycle_contract_id",
        "cycle_generation",
        "cycle_contract_sha256",
        "policy_id",
        "policy_generation",
        "policy_sha256",
        "selected_route",
        "reason_codes",
        "classification",
    }
    if set(value.keys()) != expected:
        raise ChildHandoffReconcileError("route_candidate fields are not exact")
    reason_codes = value["reason_codes"]
    if type(reason_codes) is list:
        reason_codes = tuple(reason_codes)
    if type(reason_codes) is not tuple:
        raise ChildHandoffReconcileError("route_candidate.reason_codes must be a canonical sequence")
    if reason_codes != tuple(sorted(set(reason_codes))):
        raise ChildHandoffReconcileError("route_candidate.reason_codes are not canonical")
    try:
        return RouteCandidate(**{**dict(value), "reason_codes": reason_codes})
    except (TypeError, ValueError) as exc:
        raise ChildHandoffReconcileError(f"invalid route_candidate: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ChildHandoffEvidence:
    """Evidence that one exact DELEGATE_BUILD route is bound to one child request."""

    schema: str
    handoff_id: str
    route_candidate: RouteCandidate
    route_candidate_sha256: str
    child_request: NativeChildRequest
    child_request_sha256: str
    classification: str = HANDOFF_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != HANDOFF_SCHEMA:
            raise ChildHandoffReconcileError("handoff schema mismatch")
        if self.classification != HANDOFF_CLASSIFICATION:
            raise ChildHandoffReconcileError("handoff classification mismatch")
        _identifier("handoff_id", self.handoff_id)

        if type(self.route_candidate) is not RouteCandidate:
            raise ChildHandoffReconcileError("route_candidate must be exact concrete RouteCandidate")
        rebuilt_route = _rebuild_route_candidate(self.route_candidate.as_dict())
        if rebuilt_route != self.route_candidate:
            raise ChildHandoffReconcileError("route_candidate canonical reconstruction mismatch")
        _sha256("route_candidate_sha256", self.route_candidate_sha256)
        if self.route_candidate.sha256() != self.route_candidate_sha256:
            raise ChildHandoffReconcileError("route_candidate digest mismatch")
        if self.route_candidate.selected_route != DELEGATE_BUILD:
            raise ChildHandoffReconcileError("handoff requires a DELEGATE_BUILD route candidate")

        if type(self.child_request) is not NativeChildRequest:
            raise ChildHandoffReconcileError("child_request must be exact concrete NativeChildRequest")
        _sha256("child_request_sha256", self.child_request_sha256)
        try:
            verify_native_child_request(
                self.child_request,
                expected_request_id=self.child_request.request_id,
                expected_request_generation=self.child_request.request_generation,
                expected_binding_id=self.child_request.binding_id,
                expected_binding_sha256=self.child_request.binding_sha256,
                expected_request_sha256=self.child_request_sha256,
            )
        except ValueError as exc:
            raise ChildHandoffReconcileError(f"invalid child_request: {exc}") from exc

        # Route task identity is a routing/work identity; causal generation is separate.
        # Bind only explicit common identity/content surfaces, never infer equivalence.
        if self.route_candidate.task_id != self.child_request.binding.parent.task_id:
            raise ChildHandoffReconcileError("routed task_id does not match child binding parent task_id")
        if self.route_candidate.task_sha256 != self.child_request.payload_sha256:
            raise ChildHandoffReconcileError("routed task digest does not match child payload digest")

        expected_id = _handoff_id(
            self.route_candidate,
            self.route_candidate_sha256,
            self.child_request,
            self.child_request_sha256,
        )
        if self.handoff_id != expected_id:
            raise ChildHandoffReconcileError("handoff_id does not bind exact handoff content")

    @classmethod
    def create(
        cls,
        *,
        route_candidate: RouteCandidate,
        child_request: NativeChildRequest,
    ) -> "ChildHandoffEvidence":
        if type(route_candidate) is not RouteCandidate:
            raise ChildHandoffReconcileError("route_candidate must be exact concrete RouteCandidate")
        if type(child_request) is not NativeChildRequest:
            raise ChildHandoffReconcileError("child_request must be exact concrete NativeChildRequest")
        route_digest = route_candidate.sha256()
        request_digest = child_request.sha256()
        return cls(
            schema=HANDOFF_SCHEMA,
            handoff_id=_handoff_id(route_candidate, route_digest, child_request, request_digest),
            route_candidate=route_candidate,
            route_candidate_sha256=route_digest,
            child_request=child_request,
            child_request_sha256=request_digest,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ChildHandoffEvidence":
        if not isinstance(value, Mapping):
            raise ChildHandoffReconcileError("handoff input must be a mapping")
        expected = {
            "schema",
            "handoff_id",
            "route_candidate",
            "route_candidate_sha256",
            "child_request",
            "child_request_sha256",
            "classification",
        }
        if set(value.keys()) != expected:
            raise ChildHandoffReconcileError("handoff fields are not exact")
        try:
            route_candidate = _rebuild_route_candidate(value["route_candidate"])
            child_request = NativeChildRequest.from_mapping(value["child_request"])
        except (TypeError, ValueError) as exc:
            raise ChildHandoffReconcileError(f"invalid nested handoff object: {exc}") from exc
        return cls(
            schema=value["schema"],
            handoff_id=value["handoff_id"],
            route_candidate=route_candidate,
            route_candidate_sha256=value["route_candidate_sha256"],
            child_request=child_request,
            child_request_sha256=value["child_request_sha256"],
            classification=value["classification"],
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "handoff_id": self.handoff_id,
            "route_candidate": self.route_candidate.as_dict(),
            "route_candidate_sha256": self.route_candidate_sha256,
            "child_request": self.child_request.as_dict(),
            "child_request_sha256": self.child_request_sha256,
            "classification": self.classification,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ChildReconcileEvidence:
    """Evidence that an exact child result is bound back to one exact handoff/return."""

    schema: str
    reconcile_id: str
    handoff: ChildHandoffEvidence
    handoff_sha256: str
    result_binding: NativeChildBinding
    result_binding_sha256: str
    deferred_return: DeferredReturnEnvelope
    deferred_return_sha256: str
    classification: str = RECONCILE_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != RECONCILE_SCHEMA:
            raise ChildHandoffReconcileError("reconcile schema mismatch")
        if self.classification != RECONCILE_CLASSIFICATION:
            raise ChildHandoffReconcileError("reconcile classification mismatch")
        _identifier("reconcile_id", self.reconcile_id)

        if type(self.handoff) is not ChildHandoffEvidence:
            raise ChildHandoffReconcileError("handoff must be exact concrete ChildHandoffEvidence")
        rebuilt_handoff = ChildHandoffEvidence.from_mapping(self.handoff.as_dict())
        if rebuilt_handoff != self.handoff:
            raise ChildHandoffReconcileError("handoff canonical reconstruction mismatch")
        _sha256("handoff_sha256", self.handoff_sha256)
        if self.handoff.sha256() != self.handoff_sha256:
            raise ChildHandoffReconcileError("handoff digest mismatch")

        if type(self.result_binding) is not NativeChildBinding:
            raise ChildHandoffReconcileError("result_binding must be exact concrete NativeChildBinding")
        if type(self.result_binding.parent) is not CausalIdentity or type(self.result_binding.child) is not CausalIdentity:
            raise ChildHandoffReconcileError("result_binding causal identities must be exact concrete CausalIdentity")
        rebuilt_binding = NativeChildBinding.from_mapping(self.result_binding.as_dict())
        if rebuilt_binding != self.result_binding:
            raise ChildHandoffReconcileError("result_binding canonical reconstruction mismatch")
        if not self.result_binding.has_result:
            raise ChildHandoffReconcileError("result_binding must contain an observed result identity/digest")
        _sha256("result_binding_sha256", self.result_binding_sha256)
        if self.result_binding.sha256() != self.result_binding_sha256:
            raise ChildHandoffReconcileError("result_binding digest mismatch")
        if self.result_binding.binding_id() != self.handoff.child_request.binding_id:
            raise ChildHandoffReconcileError("result binding does not preserve handoff binding identity")

        if type(self.deferred_return) is not DeferredReturnEnvelope:
            raise ChildHandoffReconcileError("deferred_return must be exact concrete DeferredReturnEnvelope")
        if type(self.deferred_return.binding) is not NativeChildBinding:
            raise ChildHandoffReconcileError("deferred_return binding must be exact concrete NativeChildBinding")
        if type(self.deferred_return.resume) is not CausalIdentity:
            raise ChildHandoffReconcileError("deferred_return resume must be exact concrete CausalIdentity")
        try:
            rebuilt_return = DeferredReturnEnvelope.from_mapping(self.deferred_return.as_dict())
        except (TypeError, ValueError) as exc:
            raise ChildHandoffReconcileError(f"invalid deferred_return: {exc}") from exc
        if rebuilt_return != self.deferred_return:
            raise ChildHandoffReconcileError("deferred_return canonical reconstruction mismatch")
        _sha256("deferred_return_sha256", self.deferred_return_sha256)
        if self.deferred_return.sha256() != self.deferred_return_sha256:
            raise ChildHandoffReconcileError("deferred_return digest mismatch")
        if self.deferred_return.binding.canonical_json() != self.result_binding.canonical_json():
            raise ChildHandoffReconcileError("deferred_return does not contain the exact result binding")
        if self.deferred_return.result_id != self.result_binding.result_id:
            raise ChildHandoffReconcileError("deferred_return result_id mismatch")
        if self.deferred_return.result_sha256 != self.result_binding.result_sha256:
            raise ChildHandoffReconcileError("deferred_return result digest mismatch")

        expected_id = _reconcile_id(
            self.handoff,
            self.handoff_sha256,
            self.result_binding,
            self.result_binding_sha256,
            self.deferred_return,
            self.deferred_return_sha256,
        )
        if self.reconcile_id != expected_id:
            raise ChildHandoffReconcileError("reconcile_id does not bind exact reconcile content")

    @classmethod
    def create(
        cls,
        *,
        handoff: ChildHandoffEvidence,
        result_binding: NativeChildBinding,
        deferred_return: DeferredReturnEnvelope,
    ) -> "ChildReconcileEvidence":
        if type(handoff) is not ChildHandoffEvidence:
            raise ChildHandoffReconcileError("handoff must be exact concrete ChildHandoffEvidence")
        if type(result_binding) is not NativeChildBinding:
            raise ChildHandoffReconcileError("result_binding must be exact concrete NativeChildBinding")
        if type(deferred_return) is not DeferredReturnEnvelope:
            raise ChildHandoffReconcileError("deferred_return must be exact concrete DeferredReturnEnvelope")
        handoff_digest = handoff.sha256()
        binding_digest = result_binding.sha256()
        return_digest = deferred_return.sha256()
        return cls(
            schema=RECONCILE_SCHEMA,
            reconcile_id=_reconcile_id(
                handoff,
                handoff_digest,
                result_binding,
                binding_digest,
                deferred_return,
                return_digest,
            ),
            handoff=handoff,
            handoff_sha256=handoff_digest,
            result_binding=result_binding,
            result_binding_sha256=binding_digest,
            deferred_return=deferred_return,
            deferred_return_sha256=return_digest,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ChildReconcileEvidence":
        if not isinstance(value, Mapping):
            raise ChildHandoffReconcileError("reconcile input must be a mapping")
        expected = {
            "schema",
            "reconcile_id",
            "handoff",
            "handoff_sha256",
            "result_binding",
            "result_binding_sha256",
            "deferred_return",
            "deferred_return_sha256",
            "classification",
        }
        if set(value.keys()) != expected:
            raise ChildHandoffReconcileError("reconcile fields are not exact")
        try:
            handoff = ChildHandoffEvidence.from_mapping(value["handoff"])
            result_binding = NativeChildBinding.from_mapping(value["result_binding"])
            deferred_return = DeferredReturnEnvelope.from_mapping(value["deferred_return"])
        except (TypeError, ValueError) as exc:
            raise ChildHandoffReconcileError(f"invalid nested reconcile object: {exc}") from exc
        return cls(
            schema=value["schema"],
            reconcile_id=value["reconcile_id"],
            handoff=handoff,
            handoff_sha256=value["handoff_sha256"],
            result_binding=result_binding,
            result_binding_sha256=value["result_binding_sha256"],
            deferred_return=deferred_return,
            deferred_return_sha256=value["deferred_return_sha256"],
            classification=value["classification"],
        )

    @property
    def result_id(self) -> str:
        assert self.result_binding.result_id is not None
        return self.result_binding.result_id

    @property
    def result_sha256(self) -> str:
        assert self.result_binding.result_sha256 is not None
        return self.result_binding.result_sha256

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "reconcile_id": self.reconcile_id,
            "handoff": self.handoff.as_dict(),
            "handoff_sha256": self.handoff_sha256,
            "result_binding": self.result_binding.as_dict(),
            "result_binding_sha256": self.result_binding_sha256,
            "deferred_return": self.deferred_return.as_dict(),
            "deferred_return_sha256": self.deferred_return_sha256,
            "classification": self.classification,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def verify_child_handoff(
    evidence: ChildHandoffEvidence,
    *,
    expected_handoff_id: str,
    expected_handoff_sha256: str,
) -> ChildHandoffEvidence:
    if type(evidence) is not ChildHandoffEvidence:
        raise ChildHandoffReconcileError("evidence must be exact concrete ChildHandoffEvidence")
    _identifier("expected_handoff_id", expected_handoff_id)
    _sha256("expected_handoff_sha256", expected_handoff_sha256)
    rebuilt = ChildHandoffEvidence.from_mapping(evidence.as_dict())
    if rebuilt != evidence:
        raise ChildHandoffReconcileError("handoff canonical reconstruction mismatch")
    if evidence.handoff_id != expected_handoff_id:
        raise ChildHandoffReconcileError("handoff id mismatch at consumer boundary")
    if evidence.sha256() != expected_handoff_sha256:
        raise ChildHandoffReconcileError("handoff digest mismatch at consumer boundary")
    return evidence


def verify_child_reconcile(
    evidence: ChildReconcileEvidence,
    *,
    expected_reconcile_id: str,
    expected_reconcile_sha256: str,
) -> ChildReconcileEvidence:
    if type(evidence) is not ChildReconcileEvidence:
        raise ChildHandoffReconcileError("evidence must be exact concrete ChildReconcileEvidence")
    _identifier("expected_reconcile_id", expected_reconcile_id)
    _sha256("expected_reconcile_sha256", expected_reconcile_sha256)
    rebuilt = ChildReconcileEvidence.from_mapping(evidence.as_dict())
    if rebuilt != evidence:
        raise ChildHandoffReconcileError("reconcile canonical reconstruction mismatch")
    if evidence.reconcile_id != expected_reconcile_id:
        raise ChildHandoffReconcileError("reconcile id mismatch at consumer boundary")
    if evidence.sha256() != expected_reconcile_sha256:
        raise ChildHandoffReconcileError("reconcile digest mismatch at consumer boundary")
    return evidence
