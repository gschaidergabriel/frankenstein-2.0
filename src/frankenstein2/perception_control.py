"""Deterministic perception-control boundary for F2-WP-702.

This module enforces mechanically distinct COMPUTE_OFF, OUTPUT_OFF and
MEMORY_OFF semantics over caller-supplied compute functions. It does not
read pixels, open cameras, invoke models/providers/tools, persist state, or
mint world/effect/completion authority.

Generation 5 preserves the accepted OFF/taint/policy semantics while closing two
post-G4 counterexamples: ordinary result construction is factory-only, and a
consumer can revalidate exact current result content against an externally latched
result digest plus the exact current policy registry before authority-relevant
fields are consumed. This is an in-process correctness/provenance fence, not a
cryptographic claim against arbitrary hostile code in the same Python process.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Callable, ClassVar

POLICY_SCHEMA = "FRANKENSTEIN2_PERCEPTION_HEAD_POLICY/v1"
DEPENDENCY_SCHEMA = "FRANKENSTEIN2_PERCEPTION_DEPENDENCY/v1"
REGISTRY_SCHEMA = "FRANKENSTEIN2_PERCEPTION_POLICY_REGISTRY/v1"
RESULT_SCHEMA = "FRANKENSTEIN2_PERCEPTION_CONTROL_RESULT/v1"
TIERS = frozenset({"ON", "COMPUTE_OFF", "OUTPUT_OFF", "MEMORY_OFF"})
_STATUSES = frozenset({"OK", "NOT_COMPUTED", "OUTPUT_BLOCKED", "COMPUTE_ERROR"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PerceptionControlError(ValueError):
    """Fail-closed validation error for the WP702 control boundary."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise PerceptionControlError(f"{name} must be a trimmed non-empty string")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PerceptionControlError(f"{name} must not contain control characters")
    return value


def _nonnegative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PerceptionControlError(f"{name} must be an integer >= 0")
    return value


def _confidence(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
        raise PerceptionControlError("confidence_micros must be an integer in [0, 1000000]")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise PerceptionControlError(f"{name} must be lowercase sha256 hex")
    return value


def _refs(name: str, value: Any, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, tuple) or (not allow_empty and not value):
        suffix = "immutable tuple" if allow_empty else "non-empty immutable tuple"
        raise PerceptionControlError(f"{name} must be a {suffix}")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(refs) != len(set(refs)):
        raise PerceptionControlError(f"{name} must not contain duplicates")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PerceptionControlError("value must be canonical-JSON encodable") from exc


def _json_value(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionHeadPolicy:
    head_id: str
    generation: int
    tier: str
    enabled: bool
    memory_allowed: bool
    provenance_refs: tuple[str, ...]
    schema: ClassVar[str] = POLICY_SCHEMA
    classification: ClassVar[str] = "PERCEPTION_POLICY_NOT_WORLD_TRUTH_GWT_EFFECT_OR_COMPLETION_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "head_id", _text("head_id", self.head_id))
        _nonnegative_int("generation", self.generation)
        if self.tier not in TIERS:
            raise PerceptionControlError("tier must be ON, COMPUTE_OFF, OUTPUT_OFF or MEMORY_OFF")
        if not isinstance(self.enabled, bool) or not isinstance(self.memory_allowed, bool):
            raise PerceptionControlError("enabled and memory_allowed must be bool")
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    @property
    def compute_allowed(self) -> bool:
        return self.enabled and self.tier != "COMPUTE_OFF"

    @property
    def egress_allowed(self) -> bool:
        return self.compute_allowed and self.tier != "OUTPUT_OFF"

    @property
    def memory_match_allowed(self) -> bool:
        return self.compute_allowed and self.tier == "ON" and self.memory_allowed

    @property
    def persistence_allowed(self) -> bool:
        return self.memory_match_allowed

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "classification": self.classification, "head_id": self.head_id,
                "generation": self.generation, "tier": self.tier, "enabled": self.enabled,
                "memory_allowed": self.memory_allowed, "compute_allowed": self.compute_allowed,
                "egress_allowed": self.egress_allowed, "memory_match_allowed": self.memory_match_allowed,
                "persistence_allowed": self.persistence_allowed, "provenance_refs": list(self.provenance_refs)}

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionDependency:
    head_id: str
    depends_on: tuple[str, ...]
    schema: ClassVar[str] = DEPENDENCY_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "head_id", _text("head_id", self.head_id))
        object.__setattr__(self, "depends_on", _refs("depends_on", self.depends_on, allow_empty=True))
        if self.head_id in self.depends_on:
            raise PerceptionControlError("head cannot depend on itself")

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "head_id": self.head_id, "depends_on": list(self.depends_on)}


@dataclass(frozen=True, slots=True, kw_only=True)
class PerceptionPolicyRegistry:
    registry_id: str
    generation: int
    heads: tuple[PerceptionHeadPolicy, ...]
    dependencies: tuple[PerceptionDependency, ...]
    provenance_refs: tuple[str, ...]
    schema: ClassVar[str] = REGISTRY_SCHEMA
    classification: ClassVar[str] = "PERCEPTION_CONTROL_REGISTRY_NOT_CANONICAL_STATE_OR_EFFECT_AUTHORITY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "registry_id", _text("registry_id", self.registry_id))
        _nonnegative_int("generation", self.generation)
        if not isinstance(self.heads, tuple) or not self.heads:
            raise PerceptionControlError("heads must be a non-empty immutable tuple")
        if not isinstance(self.dependencies, tuple):
            raise PerceptionControlError("dependencies must be an immutable tuple")
        if any(type(head) is not PerceptionHeadPolicy for head in self.heads):
            raise PerceptionControlError("heads must contain concrete PerceptionHeadPolicy objects")
        if any(type(dep) is not PerceptionDependency for dep in self.dependencies):
            raise PerceptionControlError("dependencies must contain concrete PerceptionDependency objects")
        head_ids = [head.head_id for head in self.heads]
        if len(head_ids) != len(set(head_ids)):
            raise PerceptionControlError("head_id must be unique")
        dep_ids = [dep.head_id for dep in self.dependencies]
        if len(dep_ids) != len(set(dep_ids)):
            raise PerceptionControlError("dependency binding head_id must be unique")
        if set(dep_ids) != set(head_ids):
            raise PerceptionControlError("dependencies must define exactly one binding for every head")
        known = set(head_ids)
        for dep in self.dependencies:
            unknown = set(dep.depends_on) - known
            if unknown:
                raise PerceptionControlError(f"dependency graph references unknown heads: {sorted(unknown)}")
        graph = {dep.head_id: dep.depends_on for dep in self.dependencies}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise PerceptionControlError("dependency graph must be acyclic")
            if node in visited:
                return
            visiting.add(node)
            for upstream in graph[node]:
                visit(upstream)
            visiting.remove(node)
            visited.add(node)

        for head_id in sorted(known):
            visit(head_id)
        object.__setattr__(self, "heads", tuple(sorted(self.heads, key=lambda item: item.head_id)))
        object.__setattr__(self, "dependencies", tuple(sorted(self.dependencies, key=lambda item: item.head_id)))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "classification": self.classification, "registry_id": self.registry_id,
                "generation": self.generation, "heads": [head.as_dict() for head in self.heads],
                "dependencies": [dep.as_dict() for dep in self.dependencies],
                "provenance_refs": list(self.provenance_refs)}

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def head(self, head_id: str) -> PerceptionHeadPolicy | None:
        head_id = _text("head_id", head_id)
        return next((head for head in self.heads if head.head_id == head_id), None)

    def upstream(self, head_id: str) -> tuple[str, ...]:
        head_id = _text("head_id", head_id)
        binding = next((dep for dep in self.dependencies if dep.head_id == head_id), None)
        if binding is None:
            raise PerceptionControlError("head has no dependency binding")
        return binding.depends_on


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class PerceptionControlResult:
    """Factory-only deterministic control readout.

    The ordinary constructor fails closed so no caller-readable constructor token is used as
    authority. This remains a cooperative in-process provenance fence, not cryptographic
    hostile-same-process security. Consumers that use authority-relevant fields must call
    validate_perception_control_result() with an externally latched result digest and exact
    registry identity.
    """

    evaluation_id: str
    head_id: str
    registry_sha256: str
    policy_sha256: str | None
    status: str
    value: Any | None
    confidence_micros: int | None
    computed: bool
    internal_computed: bool
    egress_allowed: bool
    memory_match_allowed: bool
    persistence_allowed: bool
    blocked_by: str | None
    reason: str
    provenance_refs: tuple[str, ...]
    schema: ClassVar[str] = RESULT_SCHEMA
    classification: ClassVar[str] = "PERCEPTION_CONTROL_READOUT_NOT_WORLD_TRUTH_GWT_EFFECT_OR_COMPLETION_AUTHORITY"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise PerceptionControlError(
            "PerceptionControlResult is factory-only; use evaluate_perception_head()"
        )

    def _validate_produced(self) -> None:
        object.__setattr__(self, "evaluation_id", _text("evaluation_id", self.evaluation_id))
        object.__setattr__(self, "head_id", _text("head_id", self.head_id))
        _sha256("registry_sha256", self.registry_sha256)
        if self.status not in _STATUSES:
            raise PerceptionControlError("unsupported result status")
        if self.policy_sha256 is None:
            if self.status != "NOT_COMPUTED":
                raise PerceptionControlError("evidence-bearing result requires policy_sha256")
            if self.reason != "unknown_head_not_in_registry":
                raise PerceptionControlError("policy-less NOT_COMPUTED is reserved for unknown registry heads")
        else:
            _sha256("policy_sha256", self.policy_sha256)
        if not all(isinstance(item, bool) for item in (self.computed, self.internal_computed, self.egress_allowed,
                                                       self.memory_match_allowed, self.persistence_allowed)):
            raise PerceptionControlError("result control flags must be bool")
        if self.blocked_by is not None:
            object.__setattr__(self, "blocked_by", _text("blocked_by", self.blocked_by))
        object.__setattr__(self, "reason", _text("reason", self.reason))
        object.__setattr__(self, "provenance_refs", _refs("provenance_refs", self.provenance_refs))
        if self.status in {"NOT_COMPUTED", "OUTPUT_BLOCKED", "COMPUTE_ERROR"}:
            if self.value is not None or self.confidence_micros is not None:
                raise PerceptionControlError("non-OK result must not expose value/confidence")
        else:
            object.__setattr__(self, "value", _json_value(self.value))
            if self.confidence_micros is None:
                raise PerceptionControlError("OK result requires confidence_micros")
            _confidence(self.confidence_micros)
        if self.status == "NOT_COMPUTED":
            if self.computed or self.internal_computed or self.egress_allowed or self.memory_match_allowed or self.persistence_allowed:
                raise PerceptionControlError("NOT_COMPUTED cannot claim compute/egress/memory/persistence")
        elif self.status == "OUTPUT_BLOCKED":
            if not self.computed or not self.internal_computed or self.egress_allowed or self.memory_match_allowed or self.persistence_allowed:
                raise PerceptionControlError("OUTPUT_BLOCKED flag combination is invalid")
        elif self.status == "COMPUTE_ERROR":
            if not self.computed or self.internal_computed or self.egress_allowed or self.memory_match_allowed or self.persistence_allowed:
                raise PerceptionControlError("COMPUTE_ERROR flag combination is invalid")
        elif self.status == "OK":
            if not self.computed or not self.internal_computed or not self.egress_allowed:
                raise PerceptionControlError("OK requires completed compute and egress")
            if self.persistence_allowed and not self.memory_match_allowed:
                raise PerceptionControlError("persistence cannot exceed memory-match authority")

    def as_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "classification": self.classification, "evaluation_id": self.evaluation_id,
                "head_id": self.head_id, "registry_sha256": self.registry_sha256, "policy_sha256": self.policy_sha256,
                "status": self.status, "value": self.value, "confidence_micros": self.confidence_micros,
                "computed": self.computed, "internal_computed": self.internal_computed,
                "egress_allowed": self.egress_allowed, "memory_match_allowed": self.memory_match_allowed,
                "persistence_allowed": self.persistence_allowed, "blocked_by": self.blocked_by, "reason": self.reason,
                "not_computed_is_distinct_from_false": True, "world_truth_authority": "NONE",
                "gwt_authority": "NONE", "effect_authority": "NONE", "completion_authority": "NONE",
                "provenance_refs": list(self.provenance_refs)}

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _produce_perception_control_result(**fields: Any) -> PerceptionControlResult:
    """Module-private producer used only after deterministic evaluator decisions."""
    result = object.__new__(PerceptionControlResult)
    expected_fields = (
        "evaluation_id", "head_id", "registry_sha256", "policy_sha256", "status", "value",
        "confidence_micros", "computed", "internal_computed", "egress_allowed",
        "memory_match_allowed", "persistence_allowed", "blocked_by", "reason", "provenance_refs",
    )
    if tuple(fields.keys()) != expected_fields:
        raise PerceptionControlError("internal result producer field contract mismatch")
    for name, value in fields.items():
        object.__setattr__(result, name, value)
    result._validate_produced()
    return result


def _verify_registry(registry: PerceptionPolicyRegistry, expected_sha256: str) -> None:
    if type(registry) is not PerceptionPolicyRegistry:
        raise PerceptionControlError("registry must be a concrete PerceptionPolicyRegistry")
    _sha256("expected_registry_sha256", expected_sha256)
    if registry.sha256() != expected_sha256:
        raise PerceptionControlError("registry digest mismatch")


def _first_compute_blocker(registry: PerceptionPolicyRegistry, head_id: str) -> str | None:
    """Return the deterministic first transitive dependency that is compute-disabled."""
    seen: set[str] = set()

    def walk(node: str) -> str | None:
        for upstream in registry.upstream(node):
            if upstream in seen:
                continue
            seen.add(upstream)
            policy = registry.head(upstream)
            if policy is None:
                raise PerceptionControlError("validated registry lost an upstream head")
            if not policy.compute_allowed:
                return upstream
            nested = walk(upstream)
            if nested is not None:
                return nested
        return None

    return walk(head_id)


def _effective_memory_permissions(
    registry: PerceptionPolicyRegistry, head_id: str, policy: PerceptionHeadPolicy
) -> tuple[bool, bool]:
    """Propagate upstream memory/persistence denial through the acyclic dependency graph."""
    memory_match_allowed = policy.memory_match_allowed
    persistence_allowed = policy.persistence_allowed
    seen: set[str] = set()

    def walk(node: str) -> None:
        nonlocal memory_match_allowed, persistence_allowed
        for upstream in registry.upstream(node):
            if upstream in seen:
                continue
            seen.add(upstream)
            upstream_policy = registry.head(upstream)
            if upstream_policy is None:
                raise PerceptionControlError("validated registry lost an upstream head")
            if not upstream_policy.memory_match_allowed:
                memory_match_allowed = False
            if not upstream_policy.persistence_allowed:
                persistence_allowed = False
            walk(upstream)

    walk(head_id)
    if not memory_match_allowed:
        persistence_allowed = False
    return memory_match_allowed, persistence_allowed


def validate_perception_control_result(*, result: PerceptionControlResult,
    expected_result_sha256: str, registry: PerceptionPolicyRegistry,
    expected_registry_sha256: str) -> PerceptionControlResult:
    """Admit one current result for downstream use without rerunning caller compute.

    The expected result digest must be latched outside the mutable result object. Registry and
    policy semantics are re-derived so a caller cannot make a drifted/self-constructed readout
    authoritative merely by recomputing its own digest. This function does not mint world/effect
    authority and does not prove hostile-same-process authenticity.
    """
    if type(result) is not PerceptionControlResult:
        raise PerceptionControlError("result must be a concrete PerceptionControlResult")
    _sha256("expected_result_sha256", expected_result_sha256)
    _verify_registry(registry, expected_registry_sha256)
    if result.sha256() != expected_result_sha256:
        raise PerceptionControlError("result digest mismatch at consumer boundary")
    result._validate_produced()
    registry_sha = registry.sha256()
    if result.registry_sha256 != registry_sha:
        raise PerceptionControlError("result registry identity mismatch")

    policy = registry.head(result.head_id)
    if policy is None:
        expected = (
            result.policy_sha256 is None
            and result.status == "NOT_COMPUTED"
            and not result.computed
            and not result.internal_computed
            and not result.egress_allowed
            and not result.memory_match_allowed
            and not result.persistence_allowed
            and result.blocked_by is None
            and result.reason == "unknown_head_not_in_registry"
        )
        if not expected:
            raise PerceptionControlError("unknown-head result mismatches current registry semantics")
        return result

    policy_sha = policy.sha256()
    if result.policy_sha256 != policy_sha:
        raise PerceptionControlError("result policy identity mismatch")
    if not policy.compute_allowed:
        expected = (
            result.status == "NOT_COMPUTED"
            and not result.computed
            and not result.internal_computed
            and not result.egress_allowed
            and not result.memory_match_allowed
            and not result.persistence_allowed
            and result.blocked_by == result.head_id
            and result.reason == "compute_off_or_disabled"
        )
        if not expected:
            raise PerceptionControlError("result mismatches current compute-off policy")
        return result

    blocked_by = _first_compute_blocker(registry, result.head_id)
    if blocked_by is not None:
        expected = (
            result.status == "NOT_COMPUTED"
            and not result.computed
            and not result.internal_computed
            and not result.egress_allowed
            and not result.memory_match_allowed
            and not result.persistence_allowed
            and result.blocked_by == blocked_by
            and result.reason == f"taint_blocked_by:{blocked_by}"
        )
        if not expected:
            raise PerceptionControlError("result mismatches current transitive compute taint")
        return result

    if result.status == "COMPUTE_ERROR":
        if not result.reason.startswith("compute_error:"):
            raise PerceptionControlError("compute error result has invalid reason")
        return result

    if policy.tier == "OUTPUT_OFF":
        expected = (
            result.status == "OUTPUT_BLOCKED"
            and result.computed
            and result.internal_computed
            and not result.egress_allowed
            and not result.memory_match_allowed
            and not result.persistence_allowed
            and result.blocked_by is None
            and result.reason == "output_off_transient_internal_only"
        )
        if not expected:
            raise PerceptionControlError("result mismatches current output-off policy")
        return result

    if result.status != "OK":
        raise PerceptionControlError("result status mismatches current executable policy")
    memory_match_allowed, persistence_allowed = _effective_memory_permissions(registry, result.head_id, policy)
    if policy.tier == "MEMORY_OFF":
        expected_reason = "memory_off_no_persistence"
    elif memory_match_allowed != policy.memory_match_allowed or persistence_allowed != policy.persistence_allowed:
        expected_reason = "upstream_memory_or_persistence_taint"
    else:
        expected_reason = "policy_allows_egress"
    if result.memory_match_allowed != memory_match_allowed or result.persistence_allowed != persistence_allowed:
        raise PerceptionControlError("result memory/persistence authority mismatches current policy graph")
    if result.reason != expected_reason:
        raise PerceptionControlError("result reason mismatches current policy graph")
    return result


def evaluate_perception_head(*, evaluation_id: str, registry: PerceptionPolicyRegistry,
    expected_registry_sha256: str, head_id: str, compute_fn: Callable[[], tuple[Any, int]],
    provenance_refs: tuple[str, ...]) -> PerceptionControlResult:
    """Apply immutable perception policy before and after one caller compute operation."""
    _verify_registry(registry, expected_registry_sha256)
    head_id = _text("head_id", head_id)
    if not callable(compute_fn):
        raise PerceptionControlError("compute_fn must be callable")
    provenance_refs = _refs("provenance_refs", provenance_refs)
    registry_sha = registry.sha256()
    policy = registry.head(head_id)
    if policy is None:
        return _produce_perception_control_result(
            evaluation_id=evaluation_id, head_id=head_id, registry_sha256=registry_sha,
            policy_sha256=None, status="NOT_COMPUTED", value=None, confidence_micros=None, computed=False,
            internal_computed=False, egress_allowed=False, memory_match_allowed=False, persistence_allowed=False,
            blocked_by=None, reason="unknown_head_not_in_registry", provenance_refs=provenance_refs)
    policy_sha = policy.sha256()
    if not policy.compute_allowed:
        return _produce_perception_control_result(
            evaluation_id=evaluation_id, head_id=head_id, registry_sha256=registry_sha,
            policy_sha256=policy_sha, status="NOT_COMPUTED", value=None, confidence_micros=None, computed=False,
            internal_computed=False, egress_allowed=False, memory_match_allowed=False, persistence_allowed=False,
            blocked_by=head_id, reason="compute_off_or_disabled", provenance_refs=provenance_refs)
    blocked_by = _first_compute_blocker(registry, head_id)
    if blocked_by is not None:
        return _produce_perception_control_result(
            evaluation_id=evaluation_id, head_id=head_id, registry_sha256=registry_sha,
            policy_sha256=policy_sha, status="NOT_COMPUTED", value=None, confidence_micros=None, computed=False,
            internal_computed=False, egress_allowed=False, memory_match_allowed=False, persistence_allowed=False,
            blocked_by=blocked_by, reason=f"taint_blocked_by:{blocked_by}", provenance_refs=provenance_refs)
    try:
        raw = compute_fn()
    except Exception as exc:
        return _produce_perception_control_result(
            evaluation_id=evaluation_id, head_id=head_id, registry_sha256=registry_sha,
            policy_sha256=policy_sha, status="COMPUTE_ERROR", value=None, confidence_micros=None, computed=True,
            internal_computed=False, egress_allowed=False, memory_match_allowed=False, persistence_allowed=False,
            blocked_by=None, reason=f"compute_error:{type(exc).__name__}", provenance_refs=provenance_refs)
    if not isinstance(raw, tuple) or len(raw) != 2:
        raise PerceptionControlError("compute_fn must return exactly (value, confidence_micros)")
    value, confidence_micros = raw
    value = _json_value(value)
    _confidence(confidence_micros)
    if policy.tier == "OUTPUT_OFF":
        return _produce_perception_control_result(
            evaluation_id=evaluation_id, head_id=head_id, registry_sha256=registry_sha,
            policy_sha256=policy_sha, status="OUTPUT_BLOCKED", value=None, confidence_micros=None, computed=True,
            internal_computed=True, egress_allowed=False, memory_match_allowed=False, persistence_allowed=False,
            blocked_by=None, reason="output_off_transient_internal_only", provenance_refs=provenance_refs)
    memory_match_allowed, persistence_allowed = _effective_memory_permissions(registry, head_id, policy)
    if policy.tier == "MEMORY_OFF":
        reason = "memory_off_no_persistence"
    elif memory_match_allowed != policy.memory_match_allowed or persistence_allowed != policy.persistence_allowed:
        reason = "upstream_memory_or_persistence_taint"
    else:
        reason = "policy_allows_egress"
    return _produce_perception_control_result(
        evaluation_id=evaluation_id, head_id=head_id, registry_sha256=registry_sha,
        policy_sha256=policy_sha, status="OK", value=value, confidence_micros=confidence_micros, computed=True,
        internal_computed=True, egress_allowed=True, memory_match_allowed=memory_match_allowed,
        persistence_allowed=persistence_allowed, blocked_by=None, reason=reason,
        provenance_refs=provenance_refs)
