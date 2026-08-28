"""Deterministic AgencyState contract for Frankenstein 2.0.

F2-WP-203 generation 1.

AgencyState is an immutable, persistence-agnostic projection of explicitly supplied:
- interests,
- unresolved/open loops,
- deferred intents.

The component deliberately does not infer any of those items, evaluate revisit conditions,
select a Pulse action, read/write UnifiedDB, call a provider/tool, execute an effect, or
mint completion. State evolution is a pure function guarded by exact state identity,
generation and digest. Every accepted evolution returns a deterministic transition receipt
that a future canonical persistence layer may store.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

AGENCY_STATE_SCHEMA = "FRANKENSTEIN2_AGENCY_STATE/v1"
AGENCY_PATCH_SCHEMA = "FRANKENSTEIN2_AGENCY_STATE_PATCH/v1"
AGENCY_TRANSITION_SCHEMA = "FRANKENSTEIN2_AGENCY_STATE_TRANSITION/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_ID_LEN = 512
_MAX_TEXT_LEN = 4096
_LOOP_STATES = frozenset({"OPEN", "BLOCKED", "WAITING"})


class AgencyStateError(ValueError):
    """Fail-closed AgencyState contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise AgencyStateError(f"{name} must be a string")
    if not value or value != value.strip():
        raise AgencyStateError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LEN:
        raise AgencyStateError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise AgencyStateError(f"{name} contains control characters")
    return value


def _text(name: str, value: Any) -> str:
    value = _identifier(name, value)
    if len(value) > _MAX_TEXT_LEN:
        raise AgencyStateError(f"{name} exceeds {_MAX_TEXT_LEN} characters")
    return value


def _ppm(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise AgencyStateError(f"{name} must be an integer in [0, 1000000]")
    return value


def _generation(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise AgencyStateError("generation must be a non-negative integer")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise AgencyStateError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Iterable[str], *, require_nonempty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise AgencyStateError(f"{name} must be an iterable of reference strings")
    cleaned = tuple(sorted({_identifier(name, value) for value in values}))
    if require_nonempty and not cleaned:
        raise AgencyStateError(f"{name} must contain at least one explicit reference")
    return cleaned


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Interest:
    interest_id: str
    label: str
    salience_ppm: int
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "interest_id", _identifier("interest_id", self.interest_id))
        object.__setattr__(self, "label", _text("interest label", self.label))
        object.__setattr__(self, "salience_ppm", _ppm("salience_ppm", self.salience_ppm))
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("interest provenance_ref", self.provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OpenLoop:
    loop_id: str
    summary: str
    state: str
    priority_ppm: int
    provenance_refs: tuple[str, ...]
    blocked_on_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "loop_id", _identifier("loop_id", self.loop_id))
        object.__setattr__(self, "summary", _text("open-loop summary", self.summary))
        if self.state not in _LOOP_STATES:
            raise AgencyStateError(f"open-loop state must be one of {sorted(_LOOP_STATES)}")
        object.__setattr__(self, "priority_ppm", _ppm("priority_ppm", self.priority_ppm))
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("open-loop provenance_ref", self.provenance_refs),
        )
        blocked = _refs("blocked_on_ref", self.blocked_on_refs, require_nonempty=False)
        if self.state == "BLOCKED" and not blocked:
            raise AgencyStateError("BLOCKED open loop requires blocked_on_refs")
        if self.state != "BLOCKED" and blocked:
            raise AgencyStateError("blocked_on_refs are only valid for BLOCKED open loops")
        object.__setattr__(self, "blocked_on_refs", blocked)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DeferredIntent:
    intent_id: str
    summary: str
    priority_ppm: int
    revisit_condition_ref: str
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "intent_id", _identifier("intent_id", self.intent_id))
        object.__setattr__(self, "summary", _text("deferred-intent summary", self.summary))
        object.__setattr__(self, "priority_ppm", _ppm("priority_ppm", self.priority_ppm))
        object.__setattr__(
            self,
            "revisit_condition_ref",
            _identifier("revisit_condition_ref", self.revisit_condition_ref),
        )
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("deferred-intent provenance_ref", self.provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unique_by_id(items: Iterable[Any], id_attr: str, category: str) -> tuple[Any, ...]:
    mapping: dict[str, Any] = {}
    for item in items:
        item_id = getattr(item, id_attr, None)
        if item_id in mapping:
            raise AgencyStateError(f"duplicate {category} id: {item_id}")
        mapping[item_id] = item
    return tuple(mapping[key] for key in sorted(mapping))


def _assert_global_id_uniqueness(
    interests: tuple[Interest, ...],
    open_loops: tuple[OpenLoop, ...],
    deferred_intents: tuple[DeferredIntent, ...],
) -> None:
    seen: dict[str, str] = {}
    for category, pairs in (
        ("interest", ((item.interest_id, item) for item in interests)),
        ("open_loop", ((item.loop_id, item) for item in open_loops)),
        ("deferred_intent", ((item.intent_id, item) for item in deferred_intents)),
    ):
        for item_id, _ in pairs:
            prior = seen.get(item_id)
            if prior is not None:
                raise AgencyStateError(
                    f"agency item id {item_id!r} is ambiguous across {prior} and {category}"
                )
            seen[item_id] = category


@dataclass(frozen=True, slots=True)
class AgencyStatePatch:
    schema: str
    transition_id: str
    expected_state_id: str
    expected_generation: int
    expected_state_sha256: str
    next_generation: int
    transition_refs: tuple[str, ...]
    upsert_interests: tuple[Interest, ...] = ()
    remove_interest_ids: tuple[str, ...] = ()
    upsert_open_loops: tuple[OpenLoop, ...] = ()
    close_loop_ids: tuple[str, ...] = ()
    upsert_deferred_intents: tuple[DeferredIntent, ...] = ()
    cancel_intent_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.schema != AGENCY_PATCH_SCHEMA:
            raise AgencyStateError("agency patch schema mismatch")
        object.__setattr__(self, "transition_id", _identifier("transition_id", self.transition_id))
        object.__setattr__(
            self, "expected_state_id", _identifier("expected_state_id", self.expected_state_id)
        )
        object.__setattr__(self, "expected_generation", _generation(self.expected_generation))
        object.__setattr__(
            self,
            "expected_state_sha256",
            _sha256("expected_state_sha256", self.expected_state_sha256),
        )
        object.__setattr__(self, "next_generation", _generation(self.next_generation))
        if self.next_generation != self.expected_generation + 1:
            raise AgencyStateError("next_generation must equal expected_generation + 1")
        object.__setattr__(
            self, "transition_refs", _refs("transition_ref", self.transition_refs)
        )
        object.__setattr__(
            self,
            "upsert_interests",
            _unique_by_id(self.upsert_interests, "interest_id", "interest upsert"),
        )
        object.__setattr__(
            self,
            "upsert_open_loops",
            _unique_by_id(self.upsert_open_loops, "loop_id", "open-loop upsert"),
        )
        object.__setattr__(
            self,
            "upsert_deferred_intents",
            _unique_by_id(
                self.upsert_deferred_intents, "intent_id", "deferred-intent upsert"
            ),
        )
        object.__setattr__(
            self,
            "remove_interest_ids",
            _refs("remove_interest_id", self.remove_interest_ids, require_nonempty=False),
        )
        object.__setattr__(
            self,
            "close_loop_ids",
            _refs("close_loop_id", self.close_loop_ids, require_nonempty=False),
        )
        object.__setattr__(
            self,
            "cancel_intent_ids",
            _refs("cancel_intent_id", self.cancel_intent_ids, require_nonempty=False),
        )
        self._assert_no_operation_conflicts()
        if not self.has_changes:
            raise AgencyStateError("agency patch must contain at least one explicit change")

    @property
    def has_changes(self) -> bool:
        return any(
            (
                self.upsert_interests,
                self.remove_interest_ids,
                self.upsert_open_loops,
                self.close_loop_ids,
                self.upsert_deferred_intents,
                self.cancel_intent_ids,
            )
        )

    def _assert_no_operation_conflicts(self) -> None:
        if {item.interest_id for item in self.upsert_interests} & set(self.remove_interest_ids):
            raise AgencyStateError("interest cannot be upserted and removed in one patch")
        if {item.loop_id for item in self.upsert_open_loops} & set(self.close_loop_ids):
            raise AgencyStateError("open loop cannot be upserted and closed in one patch")
        if {item.intent_id for item in self.upsert_deferred_intents} & set(self.cancel_intent_ids):
            raise AgencyStateError("deferred intent cannot be upserted and cancelled in one patch")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "transition_id": self.transition_id,
            "expected_state_id": self.expected_state_id,
            "expected_generation": self.expected_generation,
            "expected_state_sha256": self.expected_state_sha256,
            "next_generation": self.next_generation,
            "transition_refs": list(self.transition_refs),
            "upsert_interests": [item.as_dict() for item in self.upsert_interests],
            "remove_interest_ids": list(self.remove_interest_ids),
            "upsert_open_loops": [item.as_dict() for item in self.upsert_open_loops],
            "close_loop_ids": list(self.close_loop_ids),
            "upsert_deferred_intents": [item.as_dict() for item in self.upsert_deferred_intents],
            "cancel_intent_ids": list(self.cancel_intent_ids),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class AgencyStateTransition:
    schema: str
    transition_id: str
    state_id: str
    before_generation: int
    after_generation: int
    before_state_sha256: str
    after_state_sha256: str
    patch_sha256: str
    transition_refs: tuple[str, ...]
    removed_interest_ids: tuple[str, ...]
    closed_loop_ids: tuple[str, ...]
    cancelled_intent_ids: tuple[str, ...]
    classification: str = "PURE_AGENCY_STATE_TRANSITION_NOT_WORLD_EFFECT"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AgencyState:
    schema: str
    state_id: str
    generation: int
    interests: tuple[Interest, ...]
    open_loops: tuple[OpenLoop, ...]
    deferred_intents: tuple[DeferredIntent, ...]
    classification: str = "EXPLICIT_AGENCY_PROJECTION_NOT_WORLD_TRUTH"

    def __post_init__(self) -> None:
        if self.schema != AGENCY_STATE_SCHEMA:
            raise AgencyStateError("agency state schema mismatch")
        object.__setattr__(self, "state_id", _identifier("state_id", self.state_id))
        object.__setattr__(self, "generation", _generation(self.generation))
        interests = _unique_by_id(self.interests, "interest_id", "interest")
        loops = _unique_by_id(self.open_loops, "loop_id", "open loop")
        intents = _unique_by_id(self.deferred_intents, "intent_id", "deferred intent")
        _assert_global_id_uniqueness(interests, loops, intents)
        object.__setattr__(self, "interests", interests)
        object.__setattr__(self, "open_loops", loops)
        object.__setattr__(self, "deferred_intents", intents)

    @classmethod
    def create(
        cls,
        *,
        state_id: str,
        generation: int = 0,
        interests: Iterable[Interest] = (),
        open_loops: Iterable[OpenLoop] = (),
        deferred_intents: Iterable[DeferredIntent] = (),
    ) -> "AgencyState":
        return cls(
            schema=AGENCY_STATE_SCHEMA,
            state_id=state_id,
            generation=generation,
            interests=tuple(interests),
            open_loops=tuple(open_loops),
            deferred_intents=tuple(deferred_intents),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "state_id": self.state_id,
            "generation": self.generation,
            "interests": [item.as_dict() for item in self.interests],
            "open_loops": [item.as_dict() for item in self.open_loops],
            "deferred_intents": [item.as_dict() for item in self.deferred_intents],
            "classification": self.classification,
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def apply(self, patch: AgencyStatePatch) -> tuple["AgencyState", AgencyStateTransition]:
        if not isinstance(patch, AgencyStatePatch):
            raise AgencyStateError("patch must be an AgencyStatePatch")
        if patch.expected_state_id != self.state_id:
            raise AgencyStateError("agency state_id mismatch")
        if patch.expected_generation != self.generation:
            raise AgencyStateError("stale agency-state generation")
        before_sha = self.sha256()
        if patch.expected_state_sha256 != before_sha:
            raise AgencyStateError("stale or mismatched agency-state digest")

        interests = {item.interest_id: item for item in self.interests}
        loops = {item.loop_id: item for item in self.open_loops}
        intents = {item.intent_id: item for item in self.deferred_intents}

        for item_id in patch.remove_interest_ids:
            if item_id not in interests:
                raise AgencyStateError(f"cannot remove unknown interest: {item_id}")
            del interests[item_id]
        for item_id in patch.close_loop_ids:
            if item_id not in loops:
                raise AgencyStateError(f"cannot close unknown open loop: {item_id}")
            del loops[item_id]
        for item_id in patch.cancel_intent_ids:
            if item_id not in intents:
                raise AgencyStateError(f"cannot cancel unknown deferred intent: {item_id}")
            del intents[item_id]

        interests.update({item.interest_id: item for item in patch.upsert_interests})
        loops.update({item.loop_id: item for item in patch.upsert_open_loops})
        intents.update({item.intent_id: item for item in patch.upsert_deferred_intents})

        next_state = AgencyState.create(
            state_id=self.state_id,
            generation=patch.next_generation,
            interests=interests.values(),
            open_loops=loops.values(),
            deferred_intents=intents.values(),
        )
        after_sha = next_state.sha256()
        if after_sha == before_sha:
            raise AgencyStateError("agency patch produced no state delta")

        receipt = AgencyStateTransition(
            schema=AGENCY_TRANSITION_SCHEMA,
            transition_id=patch.transition_id,
            state_id=self.state_id,
            before_generation=self.generation,
            after_generation=next_state.generation,
            before_state_sha256=before_sha,
            after_state_sha256=after_sha,
            patch_sha256=patch.sha256(),
            transition_refs=patch.transition_refs,
            removed_interest_ids=patch.remove_interest_ids,
            closed_loop_ids=patch.close_loop_ids,
            cancelled_intent_ids=patch.cancel_intent_ids,
        )
        return next_state, receipt


__all__ = [
    "AGENCY_PATCH_SCHEMA",
    "AGENCY_STATE_SCHEMA",
    "AGENCY_TRANSITION_SCHEMA",
    "AgencyState",
    "AgencyStateError",
    "AgencyStatePatch",
    "AgencyStateTransition",
    "DeferredIntent",
    "Interest",
    "OpenLoop",
]
