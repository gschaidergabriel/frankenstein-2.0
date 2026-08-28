"""Deterministic read-only cognitive-envelope evaluation for Frankenstein 2.0.

F2-WP-501 generation 2 authority-fence repair.

This module consumes explicit bounded signal readouts plus an explicit envelope policy and
emits an immutable ControlSnapshot. It is measurement/control-candidate metadata only:
no hidden-state inference, persistence, model/provider/tool call, GRID mutation, effect,
completion, scheduler or policy-writer authority is present here.

Generation 2 preserves the generation-1 evaluation semantics while closing the public
output-object construction boundary: SignalResult and ControlSnapshot can only be minted
by the validated internal evaluation path, and every emitted field is fail-closed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable

POLICY_SCHEMA = "FRANKENSTEIN2_COGNITIVE_ENVELOPE_POLICY/v1"
BAND_SCHEMA = "FRANKENSTEIN2_COGNITIVE_ENVELOPE_BAND/v1"
READOUT_SCHEMA = "FRANKENSTEIN2_COGNITIVE_SIGNAL_READOUT/v1"
RESULT_SCHEMA = "FRANKENSTEIN2_COGNITIVE_SIGNAL_RESULT/v1"
SNAPSHOT_SCHEMA = "FRANKENSTEIN2_CONTROL_SNAPSHOT/v1"

STATUS_WITHIN = "WITHIN_ENVELOPE"
STATUS_DEGRADED_LOW = "DEGRADED_LOW"
STATUS_DEGRADED_HIGH = "DEGRADED_HIGH"
STATUS_HARD_LOW = "HARD_LIMIT_LOW"
STATUS_HARD_HIGH = "HARD_LIMIT_HIGH"
STATUS_UNKNOWN_REQUIRED = "UNKNOWN_MISSING_REQUIRED"
STATUS_OPTIONAL_MISSING = "OPTIONAL_MISSING"

DISPOSITION_WITHIN = "WITHIN_ENVELOPE"
DISPOSITION_DEGRADED = "DEGRADED"
DISPOSITION_HARD_LIMIT = "HARD_LIMIT_BREACH"
DISPOSITION_UNKNOWN = "UNKNOWN_REQUIRED_EVIDENCE"

CANDIDATE_NONE = "NO_REGULATION_CHANGE_CANDIDATE"
CANDIDATE_REDUCE = "BOUNDED_REGULATION_REVIEW_CANDIDATE"
CANDIDATE_CONTAIN = "CONTAIN_OR_HOLD_REVIEW_CANDIDATE"
CANDIDATE_UNKNOWN = "HOLD_FOR_REQUIRED_EVIDENCE_CANDIDATE"

SNAPSHOT_CLASSIFICATION = (
    "READ_ONLY_CONTROL_SNAPSHOT_AND_REGULATION_CANDIDATE_NOT_CONTROL_WRITER_OR_EFFECT_AUTHORITY"
)

_MAX_ID_LEN = 512
_MAX_ABS_VALUE = 1_000_000_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MEASURED_STATUSES = frozenset(
    {
        STATUS_WITHIN,
        STATUS_DEGRADED_LOW,
        STATUS_DEGRADED_HIGH,
        STATUS_HARD_LOW,
        STATUS_HARD_HIGH,
    }
)
_MISSING_STATUSES = frozenset({STATUS_UNKNOWN_REQUIRED, STATUS_OPTIONAL_MISSING})
_ALL_STATUSES = _MEASURED_STATUSES | _MISSING_STATUSES
_ALLOWED_DISPOSITIONS = frozenset(
    {
        DISPOSITION_WITHIN,
        DISPOSITION_DEGRADED,
        DISPOSITION_HARD_LIMIT,
        DISPOSITION_UNKNOWN,
    }
)
_ALLOWED_CANDIDATES = frozenset(
    {
        CANDIDATE_NONE,
        CANDIDATE_REDUCE,
        CANDIDATE_CONTAIN,
        CANDIDATE_UNKNOWN,
    }
)
_RESULT_TOKEN = object()
_SNAPSHOT_TOKEN = object()


class CognitiveEnvelopeError(ValueError):
    """Fail-closed CognitiveEnvelope contract error."""


def _text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CognitiveEnvelopeError(f"{name} must be a non-empty already-trimmed string")
    if len(value) > _MAX_ID_LEN:
        raise CognitiveEnvelopeError(f"{name} exceeds {_MAX_ID_LEN} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise CognitiveEnvelopeError(f"{name} contains control characters")
    return value


def _generation(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise CognitiveEnvelopeError(f"{name} must be a non-negative integer")
    return value


def _bounded_int(name: str, value: Any) -> int:
    if type(value) is not int or abs(value) > _MAX_ABS_VALUE:
        raise CognitiveEnvelopeError(
            f"{name} must be an integer within +/-{_MAX_ABS_VALUE}"
        )
    return value


def _sha256(name: str, value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise CognitiveEnvelopeError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(name: str, values: Iterable[str], *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise CognitiveEnvelopeError(f"{name} must be an iterable of references")
    refs = tuple(_text(name, item) for item in values)
    if not allow_empty and not refs:
        raise CognitiveEnvelopeError(f"{name} must contain at least one reference")
    if len(set(refs)) != len(refs):
        raise CognitiveEnvelopeError(f"{name} contains duplicate references")
    return tuple(sorted(refs))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EnvelopeBand:
    schema: str
    signal_id: str
    expected_generation: int
    hard_min: int
    soft_min: int
    soft_max: int
    hard_max: int
    required: bool
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != BAND_SCHEMA:
            raise CognitiveEnvelopeError("envelope band schema mismatch")
        object.__setattr__(self, "signal_id", _text("signal_id", self.signal_id))
        object.__setattr__(
            self, "expected_generation", _generation("expected_generation", self.expected_generation)
        )
        for field in ("hard_min", "soft_min", "soft_max", "hard_max"):
            object.__setattr__(self, field, _bounded_int(field, getattr(self, field)))
        if not self.hard_min <= self.soft_min <= self.soft_max <= self.hard_max:
            raise CognitiveEnvelopeError(
                "band limits must satisfy hard_min <= soft_min <= soft_max <= hard_max"
            )
        if type(self.required) is not bool:
            raise CognitiveEnvelopeError("required must be boolean")
        object.__setattr__(self, "evidence_refs", _refs("band evidence_ref", self.evidence_refs))

    @classmethod
    def create(
        cls,
        *,
        signal_id: str,
        expected_generation: int,
        hard_min: int,
        soft_min: int,
        soft_max: int,
        hard_max: int,
        required: bool,
        evidence_refs: Iterable[str],
    ) -> "EnvelopeBand":
        return cls(
            schema=BAND_SCHEMA,
            signal_id=signal_id,
            expected_generation=expected_generation,
            hard_min=hard_min,
            soft_min=soft_min,
            soft_max=soft_max,
            hard_max=hard_max,
            required=required,
            evidence_refs=tuple(evidence_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, init=False)
class CognitiveEnvelopePolicy:
    schema: str
    policy_id: str
    generation: int
    bands: tuple[EnvelopeBand, ...]
    evidence_refs: tuple[str, ...]

    def __init__(
        self,
        *,
        schema: str,
        policy_id: str,
        generation: int,
        bands: Iterable[EnvelopeBand],
        evidence_refs: Iterable[str],
    ) -> None:
        if schema != POLICY_SCHEMA:
            raise CognitiveEnvelopeError("policy schema mismatch")
        policy_id = _text("policy_id", policy_id)
        generation = _generation("policy generation", generation)
        raw_bands = tuple(bands)
        if not raw_bands:
            raise CognitiveEnvelopeError("policy requires at least one envelope band")
        if any(not isinstance(band, EnvelopeBand) for band in raw_bands):
            raise CognitiveEnvelopeError("bands must contain EnvelopeBand values")
        signal_ids = [band.signal_id for band in raw_bands]
        if len(set(signal_ids)) != len(signal_ids):
            raise CognitiveEnvelopeError("policy contains duplicate signal_id values")
        refs = _refs("policy evidence_ref", evidence_refs)
        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "generation", generation)
        object.__setattr__(self, "bands", tuple(sorted(raw_bands, key=lambda band: band.signal_id)))
        object.__setattr__(self, "evidence_refs", refs)

    @classmethod
    def create(
        cls,
        *,
        policy_id: str,
        generation: int,
        bands: Iterable[EnvelopeBand],
        evidence_refs: Iterable[str],
    ) -> "CognitiveEnvelopePolicy":
        return cls(
            schema=POLICY_SCHEMA,
            policy_id=policy_id,
            generation=generation,
            bands=bands,
            evidence_refs=evidence_refs,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "policy_id": self.policy_id,
            "generation": self.generation,
            "bands": [band.as_dict() for band in self.bands],
            "evidence_refs": list(self.evidence_refs),
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class SignalReadout:
    schema: str
    signal_id: str
    generation: int
    value: int
    evidence_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema != READOUT_SCHEMA:
            raise CognitiveEnvelopeError("signal readout schema mismatch")
        object.__setattr__(self, "signal_id", _text("signal_id", self.signal_id))
        object.__setattr__(self, "generation", _generation("readout generation", self.generation))
        object.__setattr__(self, "value", _bounded_int("readout value", self.value))
        object.__setattr__(self, "evidence_refs", _refs("readout evidence_ref", self.evidence_refs))
        object.__setattr__(
            self, "provenance_refs", _refs("readout provenance_ref", self.provenance_refs)
        )

    @classmethod
    def create(
        cls,
        *,
        signal_id: str,
        generation: int,
        value: int,
        evidence_refs: Iterable[str],
        provenance_refs: Iterable[str],
    ) -> "SignalReadout":
        return cls(
            schema=READOUT_SCHEMA,
            signal_id=signal_id,
            generation=generation,
            value=value,
            evidence_refs=tuple(evidence_refs),
            provenance_refs=tuple(provenance_refs),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, init=False)
class SignalResult:
    schema: str
    signal_id: str
    expected_generation: int
    observed_generation: int | None
    status: str
    observed_value: int | None
    band_sha256: str
    readout_sha256: str | None
    evidence_refs: tuple[str, ...]

    def __init__(
        self,
        *,
        schema: str,
        signal_id: str,
        expected_generation: int,
        observed_generation: int | None,
        status: str,
        observed_value: int | None,
        band_sha256: str,
        readout_sha256: str | None,
        evidence_refs: Iterable[str],
        _token: object | None = None,
    ) -> None:
        if _token is not _RESULT_TOKEN:
            raise CognitiveEnvelopeError(
                "SignalResult must be created by the validated envelope evaluation path"
            )
        if schema != RESULT_SCHEMA:
            raise CognitiveEnvelopeError("signal result schema mismatch")
        signal_id = _text("signal result signal_id", signal_id)
        expected_generation = _generation(
            "signal result expected_generation", expected_generation
        )
        if status not in _ALL_STATUSES:
            raise CognitiveEnvelopeError(f"unsupported signal result status: {status!r}")
        band_sha256 = _sha256("band_sha256", band_sha256)
        refs = _refs("signal result evidence_ref", evidence_refs)

        if status in _MISSING_STATUSES:
            if observed_generation is not None or observed_value is not None or readout_sha256 is not None:
                raise CognitiveEnvelopeError(
                    "missing signal result must not claim observed generation/value/readout digest"
                )
        else:
            observed_generation = _generation(
                "signal result observed_generation", observed_generation
            )
            if observed_generation != expected_generation:
                raise CognitiveEnvelopeError(
                    "signal result observed_generation must equal expected_generation"
                )
            observed_value = _bounded_int("signal result observed_value", observed_value)
            readout_sha256 = _sha256("readout_sha256", readout_sha256)

        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "signal_id", signal_id)
        object.__setattr__(self, "expected_generation", expected_generation)
        object.__setattr__(self, "observed_generation", observed_generation)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "observed_value", observed_value)
        object.__setattr__(self, "band_sha256", band_sha256)
        object.__setattr__(self, "readout_sha256", readout_sha256)
        object.__setattr__(self, "evidence_refs", refs)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _expected_control(statuses: set[str]) -> tuple[str, str]:
    hard = {STATUS_HARD_LOW, STATUS_HARD_HIGH}
    degraded = {STATUS_DEGRADED_LOW, STATUS_DEGRADED_HIGH}
    if statuses & hard:
        return DISPOSITION_HARD_LIMIT, CANDIDATE_CONTAIN
    if STATUS_UNKNOWN_REQUIRED in statuses:
        return DISPOSITION_UNKNOWN, CANDIDATE_UNKNOWN
    if statuses & degraded:
        return DISPOSITION_DEGRADED, CANDIDATE_REDUCE
    return DISPOSITION_WITHIN, CANDIDATE_NONE


@dataclass(frozen=True, slots=True, init=False)
class ControlSnapshot:
    schema: str
    policy_id: str
    policy_generation: int
    policy_sha256: str
    readout_set_sha256: str
    signal_results: tuple[SignalResult, ...]
    disposition: str
    regulation_candidate: str
    classification: str

    def __init__(
        self,
        *,
        schema: str,
        policy_id: str,
        policy_generation: int,
        policy_sha256: str,
        readout_set_sha256: str,
        signal_results: Iterable[SignalResult],
        disposition: str,
        regulation_candidate: str,
        classification: str = SNAPSHOT_CLASSIFICATION,
        _token: object | None = None,
    ) -> None:
        if _token is not _SNAPSHOT_TOKEN:
            raise CognitiveEnvelopeError(
                "ControlSnapshot must be created by the validated envelope evaluation path"
            )
        if schema != SNAPSHOT_SCHEMA:
            raise CognitiveEnvelopeError("control snapshot schema mismatch")
        policy_id = _text("snapshot policy_id", policy_id)
        policy_generation = _generation("snapshot policy_generation", policy_generation)
        policy_sha256 = _sha256("snapshot policy_sha256", policy_sha256)
        readout_set_sha256 = _sha256("snapshot readout_set_sha256", readout_set_sha256)

        raw_results = tuple(signal_results)
        if not raw_results:
            raise CognitiveEnvelopeError("control snapshot requires at least one SignalResult")
        if any(type(result) is not SignalResult for result in raw_results):
            raise CognitiveEnvelopeError("signal_results must contain concrete SignalResult values")
        ids = [result.signal_id for result in raw_results]
        if len(set(ids)) != len(ids):
            raise CognitiveEnvelopeError("control snapshot contains duplicate signal_id results")
        results = tuple(sorted(raw_results, key=lambda result: result.signal_id))

        if disposition not in _ALLOWED_DISPOSITIONS:
            raise CognitiveEnvelopeError(f"unsupported control disposition: {disposition!r}")
        if regulation_candidate not in _ALLOWED_CANDIDATES:
            raise CognitiveEnvelopeError(
                f"unsupported regulation_candidate: {regulation_candidate!r}"
            )
        expected_disposition, expected_candidate = _expected_control(
            {result.status for result in results}
        )
        if disposition != expected_disposition:
            raise CognitiveEnvelopeError(
                "control snapshot disposition does not match signal-result statuses"
            )
        if regulation_candidate != expected_candidate:
            raise CognitiveEnvelopeError(
                "control snapshot regulation_candidate does not match signal-result statuses"
            )
        if classification != SNAPSHOT_CLASSIFICATION:
            raise CognitiveEnvelopeError("control snapshot classification mismatch")

        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "policy_generation", policy_generation)
        object.__setattr__(self, "policy_sha256", policy_sha256)
        object.__setattr__(self, "readout_set_sha256", readout_set_sha256)
        object.__setattr__(self, "signal_results", results)
        object.__setattr__(self, "disposition", disposition)
        object.__setattr__(self, "regulation_candidate", regulation_candidate)
        object.__setattr__(self, "classification", classification)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _make_signal_result(
    *,
    band: EnvelopeBand,
    readout: SignalReadout | None,
    status: str,
    evidence_refs: Iterable[str],
) -> SignalResult:
    return SignalResult(
        schema=RESULT_SCHEMA,
        signal_id=band.signal_id,
        expected_generation=band.expected_generation,
        observed_generation=None if readout is None else readout.generation,
        status=status,
        observed_value=None if readout is None else readout.value,
        band_sha256=band.sha256(),
        readout_sha256=None if readout is None else readout.sha256(),
        evidence_refs=evidence_refs,
        _token=_RESULT_TOKEN,
    )


def _evaluate_band(band: EnvelopeBand, readout: SignalReadout | None) -> SignalResult:
    if readout is None:
        status = STATUS_UNKNOWN_REQUIRED if band.required else STATUS_OPTIONAL_MISSING
        return _make_signal_result(
            band=band,
            readout=None,
            status=status,
            evidence_refs=band.evidence_refs,
        )
    if readout.generation != band.expected_generation:
        raise CognitiveEnvelopeError(
            f"generation fence mismatch for signal {band.signal_id!r}: "
            f"expected {band.expected_generation}, observed {readout.generation}"
        )
    value = readout.value
    if value < band.hard_min:
        status = STATUS_HARD_LOW
    elif value > band.hard_max:
        status = STATUS_HARD_HIGH
    elif value < band.soft_min:
        status = STATUS_DEGRADED_LOW
    elif value > band.soft_max:
        status = STATUS_DEGRADED_HIGH
    else:
        status = STATUS_WITHIN
    return _make_signal_result(
        band=band,
        readout=readout,
        status=status,
        evidence_refs=tuple(
            sorted(set(band.evidence_refs + readout.evidence_refs + readout.provenance_refs))
        ),
    )


def evaluate_control_snapshot(
    policy: CognitiveEnvelopePolicy,
    readouts: Iterable[SignalReadout],
) -> ControlSnapshot:
    """Evaluate one explicit envelope snapshot without writing or regulating anything."""
    if not isinstance(policy, CognitiveEnvelopePolicy):
        raise CognitiveEnvelopeError("policy must be a CognitiveEnvelopePolicy")
    raw_readouts = tuple(readouts)
    if any(not isinstance(readout, SignalReadout) for readout in raw_readouts):
        raise CognitiveEnvelopeError("readouts must contain SignalReadout values")
    ids = [readout.signal_id for readout in raw_readouts]
    if len(set(ids)) != len(ids):
        raise CognitiveEnvelopeError("duplicate signal readout identity")
    allowed = {band.signal_id for band in policy.bands}
    unexpected = tuple(sorted(set(ids) - allowed))
    if unexpected:
        raise CognitiveEnvelopeError(f"unexpected signal readouts: {unexpected!r}")
    readout_map = {readout.signal_id: readout for readout in raw_readouts}
    ordered_readouts = tuple(sorted(raw_readouts, key=lambda item: item.signal_id))
    readout_set_sha = _digest([readout.as_dict() for readout in ordered_readouts])
    results = tuple(_evaluate_band(band, readout_map.get(band.signal_id)) for band in policy.bands)
    disposition, candidate = _expected_control({result.status for result in results})
    return ControlSnapshot(
        schema=SNAPSHOT_SCHEMA,
        policy_id=policy.policy_id,
        policy_generation=policy.generation,
        policy_sha256=policy.sha256(),
        readout_set_sha256=readout_set_sha,
        signal_results=results,
        disposition=disposition,
        regulation_candidate=candidate,
        classification=SNAPSHOT_CLASSIFICATION,
        _token=_SNAPSHOT_TOKEN,
    )


__all__ = [
    "BAND_SCHEMA",
    "CANDIDATE_CONTAIN",
    "CANDIDATE_NONE",
    "CANDIDATE_REDUCE",
    "CANDIDATE_UNKNOWN",
    "CognitiveEnvelopeError",
    "CognitiveEnvelopePolicy",
    "ControlSnapshot",
    "DISPOSITION_DEGRADED",
    "DISPOSITION_HARD_LIMIT",
    "DISPOSITION_UNKNOWN",
    "DISPOSITION_WITHIN",
    "EnvelopeBand",
    "SignalReadout",
    "SignalResult",
    "STATUS_DEGRADED_HIGH",
    "STATUS_DEGRADED_LOW",
    "STATUS_HARD_HIGH",
    "STATUS_HARD_LOW",
    "STATUS_OPTIONAL_MISSING",
    "STATUS_UNKNOWN_REQUIRED",
    "STATUS_WITHIN",
    "evaluate_control_snapshot",
]
