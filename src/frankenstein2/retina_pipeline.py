"""Deterministic Retina frame/quality/delta/continuity boundary for F2-WP-700 G2.

Consumes caller-supplied measurements and exact identities only. It never reads pixels,
opens a camera, invokes a model/provider/tool, persists raw frames, or asserts object/world
semantics. A positive result is only a PerceptEvent candidate.

Generation 2 closes executable post-acceptance counterevidence from PR #326: a
RetinaAssessment is now a factory-only output of assess_retina_transition(). Ordinary direct
construction or dataclasses.replace() cannot mint producer-looking outcome fields.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, ClassVar

FRAME_SIGNAL_SCHEMA = "FRANKENSTEIN2_RETINA_FRAME_SIGNAL/v1"
RETINA_POLICY_SCHEMA = "FRANKENSTEIN2_RETINA_POLICY/v1"
RETINA_ASSESSMENT_SCHEMA = "FRANKENSTEIN2_RETINA_ASSESSMENT/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RetinaPipelineError(ValueError):
    """Fail-closed validation error for the Retina boundary."""


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value.strip():
        raise RetinaPipelineError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise RetinaPipelineError(f"{name} must not contain leading/trailing whitespace")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise RetinaPipelineError(f"{name} must not contain control characters")
    return value


def _int_nonnegative(name: str, value: Any) -> int:
    if type(value) is not int or value < 0:
        raise RetinaPipelineError(f"{name} must be an integer >= 0")
    return value


def _micros(name: str, value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 1_000_000:
        raise RetinaPipelineError(f"{name} must be an integer in [0, 1000000]")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise RetinaPipelineError(f"{name} must be a lowercase sha256 hex digest")
    return value


def _refs(name: str, value: Any) -> tuple[str, ...]:
    if type(value) is not tuple or not value:
        raise RetinaPipelineError(f"{name} must be a non-empty immutable tuple")
    refs = tuple(_text(f"{name} item", item) for item in value)
    if len(set(refs)) != len(refs):
        raise RetinaPipelineError(f"{name} must not contain duplicates")
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
        raise RetinaPipelineError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class RetinaFrameSignal:
    """Exact identity plus cheap caller-measured frame signals; no raw pixels."""

    frame_id: str
    stream_id: str
    generation: int
    captured_monotonic_ns: int
    frame_sha256: str
    continuity_epoch: str
    quality_micros: int
    delta_micros: int | None
    delta_reference_frame_id: str | None
    delta_reference_frame_sha256: str | None
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = FRAME_SIGNAL_SCHEMA
    classification: ClassVar[str] = (
        "RETINA_CALLER_MEASUREMENT_NOT_OBJECT_WORLD_TRUTH_OR_EFFECT_AUTHORITY"
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "frame_id", _text("frame_id", self.frame_id))
        object.__setattr__(self, "stream_id", _text("stream_id", self.stream_id))
        _int_nonnegative("generation", self.generation)
        _int_nonnegative("captured_monotonic_ns", self.captured_monotonic_ns)
        _sha256("frame_sha256", self.frame_sha256)
        object.__setattr__(
            self, "continuity_epoch", _text("continuity_epoch", self.continuity_epoch)
        )
        _micros("quality_micros", self.quality_micros)
        delta_fields = (
            self.delta_micros,
            self.delta_reference_frame_id,
            self.delta_reference_frame_sha256,
        )
        if all(item is None for item in delta_fields):
            pass
        elif any(item is None for item in delta_fields):
            raise RetinaPipelineError(
                "delta measurement and reference identity must be all present or all absent"
            )
        else:
            _micros("delta_micros", self.delta_micros)
            object.__setattr__(
                self,
                "delta_reference_frame_id",
                _text("delta_reference_frame_id", self.delta_reference_frame_id),
            )
            _sha256(
                "delta_reference_frame_sha256", self.delta_reference_frame_sha256
            )
            if self.delta_reference_frame_id == self.frame_id:
                raise RetinaPipelineError(
                    "delta reference cannot point to the current frame"
                )
        object.__setattr__(
            self, "provenance_refs", _refs("provenance_refs", self.provenance_refs)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "frame_id": self.frame_id,
            "stream_id": self.stream_id,
            "generation": self.generation,
            "captured_monotonic_ns": self.captured_monotonic_ns,
            "frame_sha256": self.frame_sha256,
            "continuity_epoch": self.continuity_epoch,
            "quality_micros": self.quality_micros,
            "delta_micros": self.delta_micros,
            "delta_reference_frame_id": self.delta_reference_frame_id,
            "delta_reference_frame_sha256": self.delta_reference_frame_sha256,
            "raw_frame_present": False,
            "provenance_refs": list(self.provenance_refs),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class RetinaPolicy:
    policy_id: str
    generation: int
    min_quality_micros: int
    salient_delta_micros: int
    max_interframe_gap_ns: int
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = RETINA_POLICY_SCHEMA
    classification: ClassVar[str] = (
        "RETINA_THRESHOLD_POLICY_NOT_WORLD_TRUTH_EFFECT_OR_COMPLETION_AUTHORITY"
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        _int_nonnegative("generation", self.generation)
        _micros("min_quality_micros", self.min_quality_micros)
        _micros("salient_delta_micros", self.salient_delta_micros)
        if type(self.max_interframe_gap_ns) is not int or self.max_interframe_gap_ns <= 0:
            raise RetinaPipelineError(
                "max_interframe_gap_ns must be an integer > 0"
            )
        object.__setattr__(
            self, "provenance_refs", _refs("provenance_refs", self.provenance_refs)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "policy_id": self.policy_id,
            "generation": self.generation,
            "min_quality_micros": self.min_quality_micros,
            "salient_delta_micros": self.salient_delta_micros,
            "max_interframe_gap_ns": self.max_interframe_gap_ns,
            "provenance_refs": list(self.provenance_refs),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class RetinaAssessment:
    """Factory-only deterministic assessment output.

    The public constructor deliberately fails closed. This is a typed provenance fence, not
    a claim that Python objects are cryptographically unforgeable inside a hostile process.
    Consumers still receive candidate cognition only, never world/effect authority.
    """

    assessment_id: str
    current_frame_id: str
    current_frame_sha256: str
    current_signal_sha256: str
    previous_frame_id: str | None
    previous_frame_sha256: str | None
    previous_signal_sha256: str | None
    policy_id: str
    policy_generation: int
    policy_sha256: str
    quality_status: str
    delta_status: str
    continuity_status: str
    percept_event_candidate: bool
    event_reason: str
    provenance_refs: tuple[str, ...]

    schema: ClassVar[str] = RETINA_ASSESSMENT_SCHEMA
    classification: ClassVar[str] = (
        "RETINA_PERCEPT_EVENT_CANDIDATE_NOT_OBJECT_WORLD_TRUTH_GWT_EFFECT_OR_COMPLETION_AUTHORITY"
    )
    _QUALITY = frozenset({"QUALITY_PASS", "QUALITY_REJECTED"})
    _DELTA = frozenset({"BASELINE", "NO_SALIENT_DELTA", "SALIENT_DELTA"})
    _CONTINUITY = frozenset(
        {
            "BASELINE",
            "CONTINUOUS",
            "BREAK_STREAM",
            "BREAK_EPOCH",
            "BREAK_GENERATION_GAP",
            "BREAK_TIME_GAP",
        }
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise RetinaPipelineError(
            "assessment producer lineage is factory-only; direct/replacement output "
            "must equal assess_retina_transition()"
        )

    def _validate_produced(self) -> None:
        object.__setattr__(
            self, "assessment_id", _text("assessment_id", self.assessment_id)
        )
        object.__setattr__(
            self, "current_frame_id", _text("current_frame_id", self.current_frame_id)
        )
        _sha256("current_frame_sha256", self.current_frame_sha256)
        _sha256("current_signal_sha256", self.current_signal_sha256)
        prev = (
            self.previous_frame_id,
            self.previous_frame_sha256,
            self.previous_signal_sha256,
        )
        if all(item is None for item in prev):
            pass
        elif any(item is None for item in prev):
            raise RetinaPipelineError(
                "previous frame identity fields must be all set or all absent"
            )
        else:
            object.__setattr__(
                self,
                "previous_frame_id",
                _text("previous_frame_id", self.previous_frame_id),
            )
            _sha256("previous_frame_sha256", self.previous_frame_sha256)
            _sha256("previous_signal_sha256", self.previous_signal_sha256)

        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        _int_nonnegative("policy_generation", self.policy_generation)
        _sha256("policy_sha256", self.policy_sha256)
        if self.quality_status not in self._QUALITY:
            raise RetinaPipelineError("unsupported quality_status")
        if self.delta_status not in self._DELTA:
            raise RetinaPipelineError("unsupported delta_status")
        if self.continuity_status not in self._CONTINUITY:
            raise RetinaPipelineError("unsupported continuity_status")
        if type(self.percept_event_candidate) is not bool:
            raise RetinaPipelineError("percept_event_candidate must be bool")
        object.__setattr__(
            self, "event_reason", _text("event_reason", self.event_reason)
        )
        object.__setattr__(
            self, "provenance_refs", _refs("provenance_refs", self.provenance_refs)
        )
        eligible = (
            self.quality_status == "QUALITY_PASS"
            and self.delta_status == "SALIENT_DELTA"
            and self.continuity_status == "CONTINUOUS"
        )
        if self.percept_event_candidate != eligible:
            raise RetinaPipelineError(
                "percept_event_candidate must equal the explicit "
                "quality/delta/continuity conjunction"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "assessment_id": self.assessment_id,
            "current_frame_id": self.current_frame_id,
            "current_frame_sha256": self.current_frame_sha256,
            "current_signal_sha256": self.current_signal_sha256,
            "previous_frame_id": self.previous_frame_id,
            "previous_frame_sha256": self.previous_frame_sha256,
            "previous_signal_sha256": self.previous_signal_sha256,
            "policy_id": self.policy_id,
            "policy_generation": self.policy_generation,
            "policy_sha256": self.policy_sha256,
            "quality_status": self.quality_status,
            "delta_status": self.delta_status,
            "continuity_status": self.continuity_status,
            "percept_event_candidate": self.percept_event_candidate,
            "event_reason": self.event_reason,
            "observation_authority": "CALLER_MEASUREMENT_ONLY",
            "world_truth_authority": "NONE",
            "gwt_authority": "NONE",
            "effect_authority": "NONE",
            "completion_authority": "NONE",
            "raw_frame_present": False,
            "provenance_refs": list(self.provenance_refs),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())

    def sha256(self) -> str:
        return _digest(self.as_dict())


def _produce_retina_assessment(
    *,
    assessment_id: str,
    current_frame_id: str,
    current_frame_sha256: str,
    current_signal_sha256: str,
    previous_frame_id: str | None,
    previous_frame_sha256: str | None,
    previous_signal_sha256: str | None,
    policy_id: str,
    policy_generation: int,
    policy_sha256: str,
    quality_status: str,
    delta_status: str,
    continuity_status: str,
    percept_event_candidate: bool,
    event_reason: str,
    provenance_refs: tuple[str, ...],
) -> RetinaAssessment:
    """Module-private producer used only after deterministic transition evaluation."""

    assessment = object.__new__(RetinaAssessment)
    fields = {
        "assessment_id": assessment_id,
        "current_frame_id": current_frame_id,
        "current_frame_sha256": current_frame_sha256,
        "current_signal_sha256": current_signal_sha256,
        "previous_frame_id": previous_frame_id,
        "previous_frame_sha256": previous_frame_sha256,
        "previous_signal_sha256": previous_signal_sha256,
        "policy_id": policy_id,
        "policy_generation": policy_generation,
        "policy_sha256": policy_sha256,
        "quality_status": quality_status,
        "delta_status": delta_status,
        "continuity_status": continuity_status,
        "percept_event_candidate": percept_event_candidate,
        "event_reason": event_reason,
        "provenance_refs": provenance_refs,
    }
    for name, value in fields.items():
        object.__setattr__(assessment, name, value)
    assessment._validate_produced()
    return assessment


def _verify_signal(
    signal: RetinaFrameSignal, *, expected_sha256: str, name: str
) -> None:
    if type(signal) is not RetinaFrameSignal:
        raise RetinaPipelineError(f"{name} must be a concrete RetinaFrameSignal")
    _sha256(f"expected_{name}_sha256", expected_sha256)
    if signal.sha256() != expected_sha256:
        raise RetinaPipelineError(f"{name} signal digest mismatch")


def _verify_policy(policy: RetinaPolicy, *, expected_sha256: str) -> None:
    if type(policy) is not RetinaPolicy:
        raise RetinaPipelineError("policy must be a concrete RetinaPolicy")
    _sha256("expected_policy_sha256", expected_sha256)
    if policy.sha256() != expected_sha256:
        raise RetinaPipelineError("policy digest mismatch")


def assess_retina_transition(
    *,
    assessment_id: str,
    current: RetinaFrameSignal,
    expected_current_signal_sha256: str,
    policy: RetinaPolicy,
    expected_policy_sha256: str,
    previous: RetinaFrameSignal | None = None,
    expected_previous_signal_sha256: str | None = None,
    provenance_refs: tuple[str, ...],
) -> RetinaAssessment:
    """Classify cheap frame measurements without reading or interpreting pixels."""

    _verify_signal(
        current, expected_sha256=expected_current_signal_sha256, name="current"
    )
    _verify_policy(policy, expected_sha256=expected_policy_sha256)

    if previous is None:
        if expected_previous_signal_sha256 is not None:
            raise RetinaPipelineError(
                "expected_previous_signal_sha256 must be absent when previous is absent"
            )
        if current.delta_micros is not None:
            raise RetinaPipelineError(
                "baseline frame must not claim a delta without a previous frame"
            )
        continuity_status = "BASELINE"
        delta_status = "BASELINE"
        previous_frame_id = previous_frame_sha256 = previous_signal_sha256 = None
    else:
        if expected_previous_signal_sha256 is None:
            raise RetinaPipelineError(
                "expected_previous_signal_sha256 is required with previous"
            )
        _verify_signal(
            previous,
            expected_sha256=expected_previous_signal_sha256,
            name="previous",
        )
        if current.delta_micros is None:
            raise RetinaPipelineError(
                "non-baseline frame requires an explicit delta measurement"
            )
        if current.delta_reference_frame_id != previous.frame_id:
            raise RetinaPipelineError("delta reference frame id mismatch")
        if current.delta_reference_frame_sha256 != previous.frame_sha256:
            raise RetinaPipelineError("delta reference frame digest mismatch")
        if current.captured_monotonic_ns <= previous.captured_monotonic_ns:
            raise RetinaPipelineError(
                "current frame must be strictly newer by monotonic time"
            )
        if current.generation <= previous.generation:
            raise RetinaPipelineError("current frame generation must advance")

        if current.stream_id != previous.stream_id:
            continuity_status = "BREAK_STREAM"
        elif current.continuity_epoch != previous.continuity_epoch:
            continuity_status = "BREAK_EPOCH"
        elif current.generation != previous.generation + 1:
            continuity_status = "BREAK_GENERATION_GAP"
        elif (
            current.captured_monotonic_ns - previous.captured_monotonic_ns
            > policy.max_interframe_gap_ns
        ):
            continuity_status = "BREAK_TIME_GAP"
        else:
            continuity_status = "CONTINUOUS"

        delta_status = (
            "SALIENT_DELTA"
            if current.delta_micros >= policy.salient_delta_micros
            else "NO_SALIENT_DELTA"
        )
        previous_frame_id = previous.frame_id
        previous_frame_sha256 = previous.frame_sha256
        previous_signal_sha256 = previous.sha256()

    quality_status = (
        "QUALITY_PASS"
        if current.quality_micros >= policy.min_quality_micros
        else "QUALITY_REJECTED"
    )
    percept_event_candidate = (
        quality_status == "QUALITY_PASS"
        and delta_status == "SALIENT_DELTA"
        and continuity_status == "CONTINUOUS"
    )
    if percept_event_candidate:
        event_reason = "QUALITY_PASS_SALIENT_DELTA_CONTINUOUS"
    elif quality_status == "QUALITY_REJECTED":
        event_reason = "SUPPRESSED_LOW_QUALITY"
    elif delta_status == "BASELINE":
        event_reason = "BASELINE_ONLY"
    elif continuity_status != "CONTINUOUS":
        event_reason = f"SUPPRESSED_{continuity_status}"
    else:
        event_reason = "SUPPRESSED_NO_SALIENT_DELTA"

    return _produce_retina_assessment(
        assessment_id=assessment_id,
        current_frame_id=current.frame_id,
        current_frame_sha256=current.frame_sha256,
        current_signal_sha256=current.sha256(),
        previous_frame_id=previous_frame_id,
        previous_frame_sha256=previous_frame_sha256,
        previous_signal_sha256=previous_signal_sha256,
        policy_id=policy.policy_id,
        policy_generation=policy.generation,
        policy_sha256=policy.sha256(),
        quality_status=quality_status,
        delta_status=delta_status,
        continuity_status=continuity_status,
        percept_event_candidate=percept_event_candidate,
        event_reason=event_reason,
        provenance_refs=provenance_refs,
    )
