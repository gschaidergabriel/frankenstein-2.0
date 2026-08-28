"""Deterministic Fact/Episode/Method/Process memory typing for Frankenstein 2.0.

F2-WP-303 generation 1.

This module binds explicit caller-declared memory kinds and typed reference metadata to an
exact F2-WP-300 MemoryLifecycleState.  It never inspects payload contents, infers a kind,
validates world truth, ranks retrieval, reads/writes UnifiedDB, invokes a model/provider/tool,
authorizes effects, or mints completion.

The split is intentionally mechanical: metadata that belongs to Method Memory cannot be
attached to FACT records, process checkpoints cannot silently become FACT records, and episode
lineage remains distinct from factual evidence.  The kind is caller-supplied metadata, not a
truth claim.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from frankenstein2.memory_lifecycle import MemoryLifecycleState

TYPED_MEMORY_SCHEMA = "FRANKENSTEIN2_TYPED_MEMORY_RECORD/v1"
TYPED_REFSET_SCHEMA = "FRANKENSTEIN2_TYPED_MEMORY_REFSET/v1"

KIND_FACT = "FACT"
KIND_EPISODE = "EPISODE"
KIND_METHOD = "METHOD"
KIND_PROCESS = "PROCESS"

_ALLOWED_KINDS = frozenset({KIND_FACT, KIND_EPISODE, KIND_METHOD, KIND_PROCESS})
_ALLOWED_TAGS: dict[str, frozenset[str]] = {
    KIND_FACT: frozenset({"evidence", "counterevidence"}),
    KIND_EPISODE: frozenset({"event", "causal", "observation"}),
    KIND_METHOD: frozenset(
        {
            "method",
            "support",
            "discriminator",
            "falsifier",
            "failure_signature",
            "transfer_condition",
            "anti_pattern",
        }
    ),
    KIND_PROCESS: frozenset({"process", "checkpoint", "next_action", "dependency"}),
}
_REQUIRED_TAGS: dict[str, frozenset[str]] = {
    KIND_FACT: frozenset({"evidence"}),
    KIND_EPISODE: frozenset({"event"}),
    KIND_METHOD: frozenset({"method"}),
    KIND_PROCESS: frozenset({"process", "checkpoint"}),
}
_CLASSIFICATIONS = {
    KIND_FACT: "FACT_MEMORY_RECORD_NOT_WORLD_TRUTH_AUTHORITY",
    KIND_EPISODE: "EPISODE_MEMORY_RECORD_NOT_CAUSAL_TRUTH_AUTHORITY",
    KIND_METHOD: "METHOD_MEMORY_RECORD_NOT_FACT_OR_TRANSFER_AUTHORITY",
    KIND_PROCESS: "PROCESS_MEMORY_RECORD_NOT_COMPLETION_OR_EFFECT_AUTHORITY",
}
_AUTHORITY_BOUNDARY = "CALLER_DECLARED_MEMORY_KIND_NOT_INFERRED_TRUTH_OR_AUTHORITY"
_MAX_REF_LEN = 512
_RECORD_TOKEN = object()


class TypedMemoryError(ValueError):
    """Fail-closed typed-memory contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise TypedMemoryError(f"{name} must be a string")
    if not value or value != value.strip():
        raise TypedMemoryError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_REF_LEN:
        raise TypedMemoryError(f"{name} exceeds {_MAX_REF_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise TypedMemoryError(f"{name} contains control characters")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _kind(value: Any) -> str:
    if not isinstance(value, str) or value not in _ALLOWED_KINDS:
        raise TypedMemoryError(f"unsupported memory_kind: {value!r}")
    return value


def _refs(tag: str, values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypedMemoryError(f"refs[{tag!r}] must be an iterable of reference strings")
    normalized = tuple(_identifier(f"refs[{tag!r}]", item) for item in values)
    if not normalized:
        raise TypedMemoryError(f"refs[{tag!r}] must contain at least one reference")
    if len(set(normalized)) != len(normalized):
        raise TypedMemoryError(f"refs[{tag!r}] contains duplicate references")
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class TypedRefSet:
    schema: str
    tag: str
    refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != TYPED_REFSET_SCHEMA:
            raise TypedMemoryError("typed ref-set schema mismatch")
        object.__setattr__(self, "tag", _identifier("tag", self.tag))
        object.__setattr__(self, "refs", _refs(self.tag, self.refs))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True, init=False)
class TypedMemoryRecord:
    schema: str
    memory_kind: str
    memory_id: str
    lifecycle_generation: int
    lifecycle_status: str
    lifecycle_state_sha256: str
    payload_ref: str
    payload_sha256: str
    provenance_refs: tuple[str, ...]
    typed_refs: tuple[TypedRefSet, ...]
    classification: str
    authority_boundary: str

    def __init__(
        self,
        *,
        schema: str,
        memory_kind: str,
        memory_id: str,
        lifecycle_generation: int,
        lifecycle_status: str,
        lifecycle_state_sha256: str,
        payload_ref: str,
        payload_sha256: str,
        provenance_refs: Iterable[str],
        typed_refs: Iterable[TypedRefSet],
        classification: str,
        authority_boundary: str,
        _token: object | None = None,
    ) -> None:
        if _token is not _RECORD_TOKEN:
            raise TypedMemoryError("TypedMemoryRecord must be created through create_typed_memory")
        if schema != TYPED_MEMORY_SCHEMA:
            raise TypedMemoryError("typed-memory schema mismatch")
        memory_kind = _kind(memory_kind)
        memory_id = _identifier("memory_id", memory_id)
        if type(lifecycle_generation) is not int or lifecycle_generation < 0:
            raise TypedMemoryError("lifecycle_generation must be a non-negative integer")
        lifecycle_status = _identifier("lifecycle_status", lifecycle_status)
        lifecycle_state_sha256 = _identifier("lifecycle_state_sha256", lifecycle_state_sha256)
        if len(lifecycle_state_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in lifecycle_state_sha256):
            raise TypedMemoryError("lifecycle_state_sha256 must be lowercase 64-hex SHA-256")
        payload_ref = _identifier("payload_ref", payload_ref)
        payload_sha256 = _identifier("payload_sha256", payload_sha256)
        if len(payload_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in payload_sha256):
            raise TypedMemoryError("payload_sha256 must be lowercase 64-hex SHA-256")

        provenance = tuple(_identifier("provenance_ref", value) for value in provenance_refs)
        if not provenance or len(set(provenance)) != len(provenance):
            raise TypedMemoryError("provenance_refs must be non-empty and unique")
        provenance = tuple(sorted(provenance))

        refsets = tuple(typed_refs)
        if not refsets or not all(isinstance(item, TypedRefSet) for item in refsets):
            raise TypedMemoryError("typed_refs must contain TypedRefSet values")
        tags = tuple(item.tag for item in refsets)
        if len(tags) != len(set(tags)):
            raise TypedMemoryError("typed_refs contains duplicate tags")
        if tags != tuple(sorted(tags)):
            raise TypedMemoryError("typed_refs must be canonically sorted by tag")
        allowed = _ALLOWED_TAGS[memory_kind]
        supplied = frozenset(tags)
        forbidden = supplied - allowed
        if forbidden:
            raise TypedMemoryError(
                f"{memory_kind} record carries forbidden typed ref tags: {sorted(forbidden)!r}"
            )
        missing = _REQUIRED_TAGS[memory_kind] - supplied
        if missing:
            raise TypedMemoryError(
                f"{memory_kind} record is missing required typed ref tags: {sorted(missing)!r}"
            )
        if classification != _CLASSIFICATIONS[memory_kind]:
            raise TypedMemoryError("typed-memory classification mismatch")
        if authority_boundary != _AUTHORITY_BOUNDARY:
            raise TypedMemoryError("typed-memory authority boundary mismatch")

        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "memory_kind", memory_kind)
        object.__setattr__(self, "memory_id", memory_id)
        object.__setattr__(self, "lifecycle_generation", lifecycle_generation)
        object.__setattr__(self, "lifecycle_status", lifecycle_status)
        object.__setattr__(self, "lifecycle_state_sha256", lifecycle_state_sha256)
        object.__setattr__(self, "payload_ref", payload_ref)
        object.__setattr__(self, "payload_sha256", payload_sha256)
        object.__setattr__(self, "provenance_refs", provenance)
        object.__setattr__(self, "typed_refs", refsets)
        object.__setattr__(self, "classification", classification)
        object.__setattr__(self, "authority_boundary", authority_boundary)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())

    def refs_for(self, tag: str) -> tuple[str, ...]:
        tag = _identifier("tag", tag)
        for refset in self.typed_refs:
            if refset.tag == tag:
                return refset.refs
        return ()


def create_typed_memory(
    *,
    state: MemoryLifecycleState,
    memory_kind: str,
    refs: Mapping[str, Iterable[str]],
) -> TypedMemoryRecord:
    """Bind caller-declared typed metadata to one exact lifecycle-state identity."""
    if not isinstance(state, MemoryLifecycleState):
        raise TypedMemoryError("state must be a MemoryLifecycleState")
    memory_kind = _kind(memory_kind)
    if not isinstance(refs, Mapping):
        raise TypedMemoryError("refs must be a mapping of typed tag to reference iterable")

    allowed = _ALLOWED_TAGS[memory_kind]
    normalized_items: list[TypedRefSet] = []
    seen_tags: set[str] = set()
    for raw_tag, raw_refs in refs.items():
        tag = _identifier("ref tag", raw_tag)
        if tag in seen_tags:
            raise TypedMemoryError(f"duplicate ref tag: {tag!r}")
        seen_tags.add(tag)
        if tag not in allowed:
            raise TypedMemoryError(f"{memory_kind} record cannot carry ref tag {tag!r}")
        normalized_items.append(
            TypedRefSet(schema=TYPED_REFSET_SCHEMA, tag=tag, refs=_refs(tag, raw_refs))
        )

    normalized_items.sort(key=lambda item: item.tag)
    supplied = frozenset(item.tag for item in normalized_items)
    missing = _REQUIRED_TAGS[memory_kind] - supplied
    if missing:
        raise TypedMemoryError(
            f"{memory_kind} record is missing required typed ref tags: {sorted(missing)!r}"
        )

    return TypedMemoryRecord(
        schema=TYPED_MEMORY_SCHEMA,
        memory_kind=memory_kind,
        memory_id=state.memory_id,
        lifecycle_generation=state.generation,
        lifecycle_status=state.status,
        lifecycle_state_sha256=state.sha256(),
        payload_ref=state.payload_ref,
        payload_sha256=state.payload_sha256,
        provenance_refs=state.provenance_refs,
        typed_refs=tuple(normalized_items),
        classification=_CLASSIFICATIONS[memory_kind],
        authority_boundary=_AUTHORITY_BOUNDARY,
        _token=_RECORD_TOKEN,
    )


def verify_typed_memory_binding(record: TypedMemoryRecord, state: MemoryLifecycleState) -> None:
    """Fail closed unless a typed record still binds to the exact supplied lifecycle state."""
    if not isinstance(record, TypedMemoryRecord):
        raise TypedMemoryError("record must be a TypedMemoryRecord")
    if not isinstance(state, MemoryLifecycleState):
        raise TypedMemoryError("state must be a MemoryLifecycleState")
    checks = {
        "memory_id": (record.memory_id, state.memory_id),
        "lifecycle_generation": (record.lifecycle_generation, state.generation),
        "lifecycle_status": (record.lifecycle_status, state.status),
        "lifecycle_state_sha256": (record.lifecycle_state_sha256, state.sha256()),
        "payload_ref": (record.payload_ref, state.payload_ref),
        "payload_sha256": (record.payload_sha256, state.payload_sha256),
        "provenance_refs": (record.provenance_refs, state.provenance_refs),
    }
    mismatches = [name for name, (actual, expected) in checks.items() if actual != expected]
    if mismatches:
        raise TypedMemoryError(f"typed-memory lifecycle binding mismatch: {mismatches!r}")


__all__ = [
    "KIND_EPISODE",
    "KIND_FACT",
    "KIND_METHOD",
    "KIND_PROCESS",
    "TYPED_MEMORY_SCHEMA",
    "TYPED_REFSET_SCHEMA",
    "TypedMemoryError",
    "TypedMemoryRecord",
    "TypedRefSet",
    "create_typed_memory",
    "verify_typed_memory_binding",
]
