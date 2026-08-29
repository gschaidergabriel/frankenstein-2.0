"""Deterministic bounded context compilation for Frankenstein 2.0.

F2-WP-306 generation 4.

The compiler operates on caller-supplied references and metadata only. It never reads
payload bytes, infers relevance or truth, mutates upstream state, or authorizes effects.

Generation 4 closes one bounded accounting gap: a selectable ContextItem must have an
exact typed cost witness for its payload digest, and the witness's measured cost must
match the item's declared cost_units before budget accounting can use that value.
The witness is measurement/admission evidence only; it is not world-truth authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

CONTEXT_ITEM_SCHEMA = "FRANKENSTEIN2_CONTEXT_ITEM/v1"
CONTEXT_NEED_SCHEMA = "FRANKENSTEIN2_CONTEXT_NEED/v1"
CONTEXT_VIEW_SCHEMA = "FRANKENSTEIN2_CONTEXT_VIEW/v1"
CONTEXT_COST_WITNESS_SCHEMA = "FRANKENSTEIN2_CONTEXT_COST_WITNESS/v1"

CHANNEL_STATE = "STATE"
CHANNEL_GOAL = "GOAL"
CHANNEL_EVIDENCE = "EVIDENCE"
CHANNEL_COUNTEREVIDENCE = "COUNTEREVIDENCE"
CHANNEL_HYPERPOSITION = "HYPERPOSITION"
CHANNEL_COMPLETION_DEFICIT = "COMPLETION_DEFICIT"
CHANNEL_AUTHORITY = "AUTHORITY"
CHANNEL_DO_NOT_REPEAT = "DO_NOT_REPEAT"
CHANNEL_METHOD = "METHOD"
CHANNEL_RETRIEVAL_REFERENCE = "RETRIEVAL_REFERENCE"

ALLOWED_CHANNELS = (
    CHANNEL_AUTHORITY,
    CHANNEL_COMPLETION_DEFICIT,
    CHANNEL_COUNTEREVIDENCE,
    CHANNEL_DO_NOT_REPEAT,
    CHANNEL_EVIDENCE,
    CHANNEL_GOAL,
    CHANNEL_HYPERPOSITION,
    CHANNEL_METHOD,
    CHANNEL_RETRIEVAL_REFERENCE,
    CHANNEL_STATE,
)
_ALLOWED_CHANNEL_SET = frozenset(ALLOWED_CHANNELS)

VIEW_CLASSIFICATION = "BOUNDED_CONTEXT_REFERENCE_VIEW_NOT_TRUTH_OR_EFFECT_AUTHORITY"
_MAX_ID_LENGTH = 512
_MAX_ITEMS = 4096
_MAX_COST_UNITS = 10_000_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContextCompilerError(ValueError):
    """Fail-closed context compiler contract error."""


def _identifier(name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ContextCompilerError(f"{name} must be a string")
    if not value or value != value.strip():
        raise ContextCompilerError(f"{name} must be non-empty and already trimmed")
    if len(value) > _MAX_ID_LENGTH:
        raise ContextCompilerError(f"{name} exceeds {_MAX_ID_LENGTH} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise ContextCompilerError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ContextCompilerError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _positive_int(name: str, value: Any, *, maximum: int) -> int:
    if type(value) is not int or value < 1 or value > maximum:
        raise ContextCompilerError(f"{name} must be an integer in [1, {maximum}]")
    return value


def _nonnegative_int(name: str, value: Any, *, maximum: int) -> int:
    if type(value) is not int or value < 0 or value > maximum:
        raise ContextCompilerError(f"{name} must be an integer in [0, {maximum}]")
    return value


def _basis_points(name: str, value: Any) -> int:
    if type(value) is not int or value < 0 or value > 10_000:
        raise ContextCompilerError(f"{name} must be an integer in [0, 10000]")
    return value


def _refs(name: str, values: Iterable[str], *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ContextCompilerError(f"{name} must be an iterable of references")
    refs = tuple(_identifier(name, value) for value in values)
    if not refs and not allow_empty:
        raise ContextCompilerError(f"{name} must contain at least one reference")
    if len(set(refs)) != len(refs):
        raise ContextCompilerError(f"{name} contains duplicate references")
    return tuple(sorted(refs))


def _channels(name: str, values: Iterable[str], *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ContextCompilerError(f"{name} must be an iterable of channels")
    channels = tuple(values)
    if not channels and not allow_empty:
        raise ContextCompilerError(f"{name} must contain at least one channel")
    for channel in channels:
        if channel not in _ALLOWED_CHANNEL_SET:
            raise ContextCompilerError(f"unsupported context channel: {channel!r}")
    if len(set(channels)) != len(channels):
        raise ContextCompilerError(f"{name} contains duplicate channels")
    return tuple(sorted(channels))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ContextCostWitness:
    """Typed measurement witness consumed by ContextCompiler budget admission.

    The compiler deliberately does not create this witness because it never reads
    payload bytes and therefore cannot itself render/tokenize the payload. Upstream
    measurement code must produce the witness. This type binds the exact payload digest
    to explicit renderer/tokenizer identities, an exact measured cost, generation,
    measurement reference and provenance. It does not by itself assert that the
    measurement source is truthful beyond those bound inputs.
    """

    schema: str
    payload_sha256: str
    renderer_id: str
    renderer_version: str
    tokenizer_id: str
    tokenizer_version: str
    measured_cost_units: int
    generation: int
    measurement_ref: str
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != CONTEXT_COST_WITNESS_SCHEMA:
            raise ContextCompilerError("context cost witness schema mismatch")
        _sha256("cost witness payload_sha256", self.payload_sha256)
        _identifier("renderer_id", self.renderer_id)
        _identifier("renderer_version", self.renderer_version)
        _identifier("tokenizer_id", self.tokenizer_id)
        _identifier("tokenizer_version", self.tokenizer_version)
        _positive_int(
            "measured_cost_units",
            self.measured_cost_units,
            maximum=_MAX_COST_UNITS,
        )
        _nonnegative_int("cost witness generation", self.generation, maximum=2_147_483_647)
        _identifier("measurement_ref", self.measurement_ref)
        object.__setattr__(
            self,
            "provenance_refs",
            _refs("cost witness provenance_ref", self.provenance_refs),
        )

    @classmethod
    def create(
        cls,
        *,
        payload_sha256: str,
        renderer_id: str,
        renderer_version: str,
        tokenizer_id: str,
        tokenizer_version: str,
        measured_cost_units: int,
        generation: int,
        measurement_ref: str,
        provenance_refs: Iterable[str],
    ) -> "ContextCostWitness":
        return cls(
            schema=CONTEXT_COST_WITNESS_SCHEMA,
            payload_sha256=payload_sha256,
            renderer_id=renderer_id,
            renderer_version=renderer_version,
            tokenizer_id=tokenizer_id,
            tokenizer_version=tokenizer_version,
            measured_cost_units=measured_cost_units,
            generation=generation,
            measurement_ref=measurement_ref,
            provenance_refs=tuple(provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ContextItem:
    schema: str
    item_id: str
    channel: str
    payload_ref: str
    payload_sha256: str
    source_ref: str
    source_sha256: str
    source_generation: int
    source_classification: str
    priority_bp: int
    cost_units: int
    required: bool
    provenance_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != CONTEXT_ITEM_SCHEMA:
            raise ContextCompilerError("context item schema mismatch")
        _identifier("item_id", self.item_id)
        if self.channel not in _ALLOWED_CHANNEL_SET:
            raise ContextCompilerError(f"unsupported context channel: {self.channel!r}")
        _identifier("payload_ref", self.payload_ref)
        _sha256("payload_sha256", self.payload_sha256)
        _identifier("source_ref", self.source_ref)
        _sha256("source_sha256", self.source_sha256)
        _nonnegative_int("source_generation", self.source_generation, maximum=2_147_483_647)
        _identifier("source_classification", self.source_classification)
        _basis_points("priority_bp", self.priority_bp)
        _positive_int("cost_units", self.cost_units, maximum=_MAX_COST_UNITS)
        if type(self.required) is not bool:
            raise ContextCompilerError("required must be a boolean")
        object.__setattr__(self, "provenance_refs", _refs("provenance_ref", self.provenance_refs))
        object.__setattr__(self, "evidence_refs", _refs("evidence_ref", self.evidence_refs))

    @classmethod
    def create(
        cls,
        *,
        item_id: str,
        channel: str,
        payload_ref: str,
        payload_sha256: str,
        source_ref: str,
        source_sha256: str,
        source_generation: int,
        source_classification: str,
        priority_bp: int,
        cost_units: int,
        required: bool,
        provenance_refs: Iterable[str],
        evidence_refs: Iterable[str],
    ) -> "ContextItem":
        return cls(
            schema=CONTEXT_ITEM_SCHEMA,
            item_id=item_id,
            channel=channel,
            payload_ref=payload_ref,
            payload_sha256=payload_sha256,
            source_ref=source_ref,
            source_sha256=source_sha256,
            source_generation=source_generation,
            source_classification=source_classification,
            priority_bp=priority_bp,
            cost_units=cost_units,
            required=required,
            provenance_refs=tuple(provenance_refs),
            evidence_refs=tuple(evidence_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ContextNeed:
    schema: str
    context_id: str
    task_id: str
    task_generation: int
    allowed_channels: tuple[str, ...]
    required_channels: tuple[str, ...]
    max_items: int
    max_cost_units: int
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != CONTEXT_NEED_SCHEMA:
            raise ContextCompilerError("context need schema mismatch")
        _identifier("context_id", self.context_id)
        _identifier("task_id", self.task_id)
        _positive_int("task_generation", self.task_generation, maximum=2_147_483_647)
        allowed = _channels("allowed_channels", self.allowed_channels)
        required = _channels("required_channels", self.required_channels, allow_empty=True)
        if not set(required).issubset(set(allowed)):
            raise ContextCompilerError("required_channels must be a subset of allowed_channels")
        object.__setattr__(self, "allowed_channels", allowed)
        object.__setattr__(self, "required_channels", required)
        object.__setattr__(self, "max_items", _positive_int("max_items", self.max_items, maximum=_MAX_ITEMS))
        object.__setattr__(self, "max_cost_units", _positive_int("max_cost_units", self.max_cost_units, maximum=_MAX_COST_UNITS))
        object.__setattr__(self, "evidence_refs", _refs("need evidence_ref", self.evidence_refs))

    @classmethod
    def create(
        cls,
        *,
        context_id: str,
        task_id: str,
        task_generation: int,
        allowed_channels: Iterable[str],
        required_channels: Iterable[str] = (),
        max_items: int,
        max_cost_units: int,
        evidence_refs: Iterable[str],
    ) -> "ContextNeed":
        return cls(
            schema=CONTEXT_NEED_SCHEMA,
            context_id=context_id,
            task_id=task_id,
            task_generation=task_generation,
            allowed_channels=tuple(allowed_channels),
            required_channels=tuple(required_channels),
            max_items=max_items,
            max_cost_units=max_cost_units,
            evidence_refs=tuple(evidence_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class SelectedContextItem:
    item_id: str
    item_sha256: str
    channel: str
    payload_ref: str
    payload_sha256: str
    source_ref: str
    source_sha256: str
    source_generation: int
    source_classification: str
    priority_bp: int
    cost_units: int
    required: bool
    provenance_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    cost_witness_sha256: str
    cost_renderer_id: str
    cost_renderer_version: str
    cost_tokenizer_id: str
    cost_tokenizer_version: str
    cost_witness_generation: int
    cost_measurement_ref: str
    cost_witness_provenance_refs: tuple[str, ...]
    selection_reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OmittedContextItem:
    item_id: str
    item_sha256: str
    channel: str
    priority_bp: int
    cost_units: int
    required: bool
    omission_reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ContextView:
    schema: str
    context_id: str
    task_id: str
    task_generation: int
    need_sha256: str
    selected: tuple[SelectedContextItem, ...]
    omitted: tuple[OmittedContextItem, ...]
    selected_count: int
    selected_cost_units: int
    classification: str = VIEW_CLASSIFICATION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _selected(
    item: ContextItem,
    reason: str,
    cost_witness: ContextCostWitness,
) -> SelectedContextItem:
    return SelectedContextItem(
        item_id=item.item_id,
        item_sha256=item.sha256(),
        channel=item.channel,
        payload_ref=item.payload_ref,
        payload_sha256=item.payload_sha256,
        source_ref=item.source_ref,
        source_sha256=item.source_sha256,
        source_generation=item.source_generation,
        source_classification=item.source_classification,
        priority_bp=item.priority_bp,
        cost_units=cost_witness.measured_cost_units,
        required=item.required,
        provenance_refs=item.provenance_refs,
        evidence_refs=item.evidence_refs,
        cost_witness_sha256=cost_witness.sha256(),
        cost_renderer_id=cost_witness.renderer_id,
        cost_renderer_version=cost_witness.renderer_version,
        cost_tokenizer_id=cost_witness.tokenizer_id,
        cost_tokenizer_version=cost_witness.tokenizer_version,
        cost_witness_generation=cost_witness.generation,
        cost_measurement_ref=cost_witness.measurement_ref,
        cost_witness_provenance_refs=cost_witness.provenance_refs,
        selection_reason=reason,
    )


def _omitted(item: ContextItem, reason: str) -> OmittedContextItem:
    return OmittedContextItem(
        item_id=item.item_id,
        item_sha256=item.sha256(),
        channel=item.channel,
        priority_bp=item.priority_bp,
        cost_units=item.cost_units,
        required=item.required,
        omission_reason=reason,
    )


def _bind_cost_witnesses(
    selectable: tuple[ContextItem, ...],
    cost_witnesses: Iterable[ContextCostWitness],
) -> dict[str, ContextCostWitness]:
    if isinstance(cost_witnesses, (str, bytes)):
        raise ContextCompilerError("cost_witnesses must be an iterable of ContextCostWitness values")
    witnesses = tuple(cost_witnesses)
    if any(type(witness) is not ContextCostWitness for witness in witnesses):
        raise ContextCompilerError("cost_witnesses must contain only exact ContextCostWitness values")

    selectable_payloads = {item.payload_sha256 for item in selectable}
    by_payload: dict[str, ContextCostWitness] = {}
    for witness in witnesses:
        if witness.payload_sha256 not in selectable_payloads:
            raise ContextCompilerError("unbound context cost witness payload_sha256")
        if witness.payload_sha256 in by_payload:
            raise ContextCompilerError("duplicate context cost witness for payload_sha256")
        by_payload[witness.payload_sha256] = witness

    bound: dict[str, ContextCostWitness] = {}
    for item in selectable:
        witness = by_payload.get(item.payload_sha256)
        if witness is None:
            raise ContextCompilerError(f"missing cost witness for context item {item.item_id!r}")
        if witness.measured_cost_units != item.cost_units:
            raise ContextCompilerError(
                f"cost witness does not match declared cost_units for context item {item.item_id!r}"
            )
        bound[item.item_id] = witness
    return bound


def compile_context(
    need: ContextNeed,
    items: Iterable[ContextItem],
    *,
    cost_witnesses: Iterable[ContextCostWitness] = (),
) -> ContextView:
    """Compile one deterministic bounded reference-only context view.

    Every selectable item must have one exact typed cost witness bound to its
    payload digest. Budget accounting uses the measured cost only after proving
    it equals the item's declared cost_units. The compiler still never reads or
    renders payload bytes.
    """
    if not isinstance(need, ContextNeed):
        raise ContextCompilerError("need must be a ContextNeed")
    candidates = tuple(items)
    if not candidates:
        raise ContextCompilerError("items must contain at least one ContextItem")
    if any(not isinstance(item, ContextItem) for item in candidates):
        raise ContextCompilerError("items must contain only ContextItem values")
    ids = [item.item_id for item in candidates]
    if len(set(ids)) != len(ids):
        raise ContextCompilerError("duplicate context item_id")

    allowed = set(need.allowed_channels)
    required_channels = set(need.required_channels)
    selected: list[SelectedContextItem] = []
    omitted: list[OmittedContextItem] = []
    selected_ids: set[str] = set()
    used_cost = 0

    disallowed = [item for item in candidates if item.channel not in allowed]
    for item in disallowed:
        if item.required:
            raise ContextCompilerError(
                f"required item {item.item_id!r} uses disallowed channel {item.channel!r}"
            )
        omitted.append(_omitted(item, "CHANNEL_NOT_ALLOWED"))

    selectable = tuple(item for item in candidates if item.channel in allowed)
    cost_by_item = _bind_cost_witnesses(selectable, cost_witnesses)

    explicit_required = sorted(
        (item for item in selectable if item.required),
        key=lambda item: (-item.priority_bp, item.item_id),
    )
    for item in explicit_required:
        measured_cost = cost_by_item[item.item_id].measured_cost_units
        if len(selected) + 1 > need.max_items:
            raise ContextCompilerError("required context items exceed max_items")
        if used_cost + measured_cost > need.max_cost_units:
            raise ContextCompilerError("required context items exceed max_cost_units")
        selected.append(_selected(item, "EXPLICIT_REQUIRED", cost_by_item[item.item_id]))
        selected_ids.add(item.item_id)
        used_cost += measured_cost

    # Satisfy declared channel requirements before spending remaining budget on
    # ordinary optional items. This is a structural requirement, not inferred relevance.
    for channel in sorted(required_channels):
        if channel in {entry.channel for entry in selected}:
            continue
        channel_candidates = sorted(
            (
                item
                for item in selectable
                if not item.required and item.channel == channel and item.item_id not in selected_ids
            ),
            key=lambda item: (-item.priority_bp, item.item_id),
        )
        if not channel_candidates:
            raise ContextCompilerError(f"required channel has no candidate: {channel!r}")
        chosen = channel_candidates[0]
        measured_cost = cost_by_item[chosen.item_id].measured_cost_units
        if len(selected) + 1 > need.max_items:
            raise ContextCompilerError("required channels exceed max_items")
        if used_cost + measured_cost > need.max_cost_units:
            raise ContextCompilerError("required channels exceed max_cost_units")
        selected.append(_selected(chosen, "REQUIRED_CHANNEL", cost_by_item[chosen.item_id]))
        selected_ids.add(chosen.item_id)
        used_cost += measured_cost

    optional = sorted(
        (item for item in selectable if not item.required and item.item_id not in selected_ids),
        key=lambda item: (-item.priority_bp, item.item_id),
    )
    for item in optional:
        measured_cost = cost_by_item[item.item_id].measured_cost_units
        if len(selected) >= need.max_items:
            omitted.append(_omitted(item, "ITEM_LIMIT"))
            continue
        if used_cost + measured_cost > need.max_cost_units:
            omitted.append(_omitted(item, "COST_LIMIT"))
            continue
        selected.append(
            _selected(item, "EXPLICIT_PRIORITY_WITHIN_BUDGET", cost_by_item[item.item_id])
        )
        selected_ids.add(item.item_id)
        used_cost += measured_cost

    selected_channels = {item.channel for item in selected}
    missing_required_channels = tuple(sorted(required_channels - selected_channels))
    if missing_required_channels:
        raise ContextCompilerError(
            f"required channels missing from selected context: {missing_required_channels!r}"
        )

    omitted.sort(key=lambda item: (item.omission_reason, item.item_id))
    return ContextView(
        schema=CONTEXT_VIEW_SCHEMA,
        context_id=need.context_id,
        task_id=need.task_id,
        task_generation=need.task_generation,
        need_sha256=need.sha256(),
        selected=tuple(selected),
        omitted=tuple(omitted),
        selected_count=len(selected),
        selected_cost_units=used_cost,
    )


__all__ = [
    "ALLOWED_CHANNELS",
    "CHANNEL_AUTHORITY",
    "CHANNEL_COMPLETION_DEFICIT",
    "CHANNEL_COUNTEREVIDENCE",
    "CHANNEL_DO_NOT_REPEAT",
    "CHANNEL_EVIDENCE",
    "CHANNEL_GOAL",
    "CHANNEL_HYPERPOSITION",
    "CHANNEL_METHOD",
    "CHANNEL_RETRIEVAL_REFERENCE",
    "CHANNEL_STATE",
    "CONTEXT_COST_WITNESS_SCHEMA",
    "CONTEXT_ITEM_SCHEMA",
    "CONTEXT_NEED_SCHEMA",
    "CONTEXT_VIEW_SCHEMA",
    "ContextCompilerError",
    "ContextCostWitness",
    "ContextItem",
    "ContextNeed",
    "ContextView",
    "OmittedContextItem",
    "SelectedContextItem",
    "VIEW_CLASSIFICATION",
    "compile_context",
]
