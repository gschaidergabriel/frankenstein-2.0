"""Non-canonical WP900 G9 candidate discriminator.

This research artifact is an owner handoff only. It deliberately lives outside
the active WP900 G9 mutation paths and mints ZERO Frankenstein/Clay credit.

Purpose:
- reject byte-level "semantic" claims without representation variants,
- require a matched sham/control,
- reject order/carry-over confounds,
- require an externally fixed oracle identity,
- keep the outcome observer blind to treatment/mechanism labels.

A PASS means only that the supplied experiment rows satisfy these structural
fences. It is NOT runtime evidence and cannot promote semantic GWT/J-Space.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Mapping, Sequence

SCHEMA = "F2_WP900_G9_SEMANTIC_CONTENT_CANDIDATE_DISCRIMINATOR/v1"
PASS = "CANDIDATE_DISCRIMINATOR_PASS"
FAIL = "CANDIDATE_DISCRIMINATOR_FAIL"
AMBIGUOUS = "CANDIDATE_DISCRIMINATOR_AMBIGUOUS"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_OBSERVER_FIELDS = frozenset(
    {
        "treatment",
        "treatment_label",
        "condition",
        "condition_label",
        "semantic_class",
        "representation_id",
        "payload_sha256",
        "mechanism_label",
        "expected_outcome_id",
        "oracle_expected",
    }
)


class CandidateDiscriminatorError(ValueError):
    """Malformed candidate experiment."""


def _text(name: str, value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise CandidateDiscriminatorError(f"{name} must be non-empty trimmed text")
    return value


def _sha(name: str, value: object) -> str:
    text = _text(name, value)
    if _SHA256.fullmatch(text) is None:
        raise CandidateDiscriminatorError(f"{name} must be lowercase SHA-256")
    return text


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CandidateDiscriminatorError("value is not canonical-JSON encodable") from exc


def digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class TrialSpec:
    trial_id: str
    semantic_class: str
    representation_id: str
    payload_sha256: str
    expected_outcome_id: str
    order_position: int
    reset_epoch: str
    counterbalance_block: str
    is_sham: bool = False

    def __post_init__(self) -> None:
        for name in (
            "trial_id",
            "semantic_class",
            "representation_id",
            "expected_outcome_id",
            "reset_epoch",
            "counterbalance_block",
        ):
            _text(name, getattr(self, name))
        _sha("payload_sha256", self.payload_sha256)
        if type(self.order_position) is not int or self.order_position < 1:
            raise CandidateDiscriminatorError("order_position must be a positive integer")
        if type(self.is_sham) is not bool:
            raise CandidateDiscriminatorError("is_sham must be bool")


@dataclass(frozen=True, slots=True)
class TrialObservation:
    trial_id: str
    pre_state_sha256: str
    post_state_sha256: str
    observed_outcome_id: str
    observer_received_fields: tuple[str, ...]
    source_binding_sha256: str
    runtime_subject_sha256: str

    def __post_init__(self) -> None:
        _text("trial_id", self.trial_id)
        _text("observed_outcome_id", self.observed_outcome_id)
        for name in (
            "pre_state_sha256",
            "post_state_sha256",
            "source_binding_sha256",
            "runtime_subject_sha256",
        ):
            _sha(name, getattr(self, name))
        if type(self.observer_received_fields) is not tuple:
            raise CandidateDiscriminatorError("observer_received_fields must be tuple[str, ...]")
        normalized = tuple(_text("observer field", item) for item in self.observer_received_fields)
        if len(set(normalized)) != len(normalized):
            raise CandidateDiscriminatorError("observer_received_fields contains duplicates")


@dataclass(frozen=True, slots=True)
class Evaluation:
    schema: str
    classification: str
    reasons: tuple[str, ...]
    manifest_sha256: str
    oracle_source_sha256: str
    runtime_subject_sha256: str | None
    representation_invariance: bool
    semantic_selectivity: bool
    sham_exclusion: bool
    carryover_exclusion: bool
    order_counterbalance: bool
    observer_blinding: bool
    oracle_identity_bound: bool

    # Explicitly zero: this candidate artifact is not canonical execution evidence.
    repository_ci_credit: int = 0
    target_environment_component_runtime_credit: int = 0
    runtime_credit: int = 0
    gwt_runtime_credit: int = 0
    semantic_gwt_runtime_credit: int = 0
    jspace_runtime_credit: int = 0
    physical_grid10_credit: int = 0
    effect_credit: int = 0
    training_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False

    def as_dict(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


def evaluate(
    *,
    trials: Sequence[TrialSpec],
    observations: Sequence[TrialObservation],
    oracle_source_sha256: str,
    oracle: Mapping[str, str],
) -> Evaluation:
    """Evaluate structural causality fences without minting project credit.

    The oracle is keyed by ``trial_id`` and must have an externally supplied
    immutable ``oracle_source_sha256``. This function never derives expected
    outcomes from payload bytes or observed outputs.
    """
    oracle_source_sha256 = _sha("oracle_source_sha256", oracle_source_sha256)
    if not trials:
        raise CandidateDiscriminatorError("trials must not be empty")
    if len({t.trial_id for t in trials}) != len(trials):
        raise CandidateDiscriminatorError("trial_id must be unique")
    if sorted(t.order_position for t in trials) != list(range(1, len(trials) + 1)):
        raise CandidateDiscriminatorError("order_position must form exactly 1..N")
    if set(oracle) != {t.trial_id for t in trials}:
        raise CandidateDiscriminatorError("oracle must cover exactly the trial IDs")
    for trial_id, expected in oracle.items():
        _text("oracle trial_id", trial_id)
        _text("oracle expected outcome", expected)

    by_trial = {o.trial_id: o for o in observations}
    if set(by_trial) != {t.trial_id for t in trials} or len(by_trial) != len(observations):
        raise CandidateDiscriminatorError("observations must cover each trial exactly once")

    manifest_payload = [
        {
            "trial_id": t.trial_id,
            "semantic_class": t.semantic_class,
            "representation_id": t.representation_id,
            "payload_sha256": t.payload_sha256,
            "expected_outcome_id": t.expected_outcome_id,
            "order_position": t.order_position,
            "reset_epoch": t.reset_epoch,
            "counterbalance_block": t.counterbalance_block,
            "is_sham": t.is_sham,
        }
        for t in trials
    ]
    manifest_sha256 = digest({"schema": SCHEMA, "trials": manifest_payload})

    reasons: list[str] = []

    # 1) Oracle must agree with predeclared IDs, but is not derived here.
    oracle_identity_bound = all(oracle[t.trial_id] == t.expected_outcome_id for t in trials)
    if not oracle_identity_bound:
        reasons.append("oracle disagrees with predeclared expected_outcome_id")

    # 2) Observer cannot receive treatment/mechanism metadata.
    observer_blinding = True
    for obs in observations:
        leaked = FORBIDDEN_OBSERVER_FIELDS.intersection(obs.observer_received_fields)
        if leaked:
            observer_blinding = False
            reasons.append(f"{obs.trial_id}: observer metadata leak: {sorted(leaked)!r}")

    # 3) Runtime subject and reset pre-state must be stable enough to reject carry-over.
    subjects = {o.runtime_subject_sha256 for o in observations}
    runtime_subject_sha256 = next(iter(subjects)) if len(subjects) == 1 else None
    if runtime_subject_sha256 is None:
        reasons.append("trials do not share one runtime subject")

    reset_pre_states: dict[str, set[str]] = {}
    for trial in trials:
        reset_pre_states.setdefault(trial.reset_epoch, set()).add(
            by_trial[trial.trial_id].pre_state_sha256
        )
    carryover_exclusion = all(len(states) == 1 for states in reset_pre_states.values())
    if not carryover_exclusion:
        reasons.append("same reset_epoch produced different pre-state hashes")

    # 4) Counterbalance must vary semantic-class order across otherwise matched blocks.
    non_sham_classes = sorted({t.semantic_class for t in trials if not t.is_sham})
    block_orders: dict[str, tuple[str, ...]] = {}
    for block in sorted({t.counterbalance_block for t in trials if not t.is_sham}):
        members = sorted(
            (t for t in trials if not t.is_sham and t.counterbalance_block == block),
            key=lambda t: t.order_position,
        )
        block_orders[block] = tuple(t.semantic_class for t in members)
    expected_class_set = set(non_sham_classes)
    blocks_cover_once = bool(block_orders) and all(
        len(order) == len(expected_class_set) and set(order) == expected_class_set
        for order in block_orders.values()
    )
    positions_by_class: dict[str, set[int]] = {
        semantic_class: set() for semantic_class in non_sham_classes
    }
    for order in block_orders.values():
        for position, semantic_class in enumerate(order, start=1):
            positions_by_class.setdefault(semantic_class, set()).add(position)
    order_counterbalance = (
        len(block_orders) >= 2
        and blocks_cover_once
        and len(set(block_orders.values())) >= 2
        and all(len(positions) >= 2 for positions in positions_by_class.values())
    )
    if not order_counterbalance:
        reasons.append(
            "counterbalance blocks must contain each non-sham class once and vary every class position"
        )

    # 5) 'Semantic' requires >=2 byte-distinct representations per non-sham semantic class.
    if len(non_sham_classes) < 2:
        reasons.append("need at least two non-sham semantic classes")
    representation_invariance = bool(non_sham_classes)
    class_outcomes: dict[str, set[str]] = {}
    for semantic_class in non_sham_classes:
        members = [t for t in trials if not t.is_sham and t.semantic_class == semantic_class]
        reps = {t.representation_id for t in members}
        payloads = {t.payload_sha256 for t in members}
        outcomes = {by_trial[t.trial_id].observed_outcome_id for t in members}
        class_outcomes[semantic_class] = outcomes
        if len(reps) < 2 or len(payloads) < 2:
            representation_invariance = False
            reasons.append(f"{semantic_class}: requires >=2 byte-distinct representations")
        if len(outcomes) != 1:
            representation_invariance = False
            reasons.append(f"{semantic_class}: observed outcome is representation-sensitive")

    # 6) Distinct semantic classes must produce distinct stable outcomes and match oracle.
    semantic_selectivity = (
        len(non_sham_classes) >= 2
        and representation_invariance
        and len({next(iter(v)) for v in class_outcomes.values() if len(v) == 1})
        == len(non_sham_classes)
    )
    if not semantic_selectivity:
        reasons.append("semantic classes are not selectively distinguishable")

    outcome_matches_oracle = all(
        by_trial[t.trial_id].observed_outcome_id == oracle[t.trial_id] for t in trials
    )
    if not outcome_matches_oracle:
        reasons.append("one or more observed outcomes disagree with external oracle")

    # 7) At least two byte-distinct sham representations must converge on one no-effect outcome.
    sham = [t for t in trials if t.is_sham]
    sham_exclusion = False
    if sham:
        sham_reps = {t.representation_id for t in sham}
        sham_payloads = {t.payload_sha256 for t in sham}
        sham_outcomes = {by_trial[t.trial_id].observed_outcome_id for t in sham}
        sham_expected = {oracle[t.trial_id] for t in sham}
        sham_exclusion = (
            len(sham_reps) >= 2
            and len(sham_payloads) >= 2
            and len(sham_outcomes) == 1
            and sham_outcomes == sham_expected
            and all(
                by_trial[t.trial_id].pre_state_sha256
                == by_trial[t.trial_id].post_state_sha256
                for t in sham
            )
        )
    if not sham_exclusion:
        reasons.append("matched byte-distinct sham/no-effect control did not close")

    gates = (
        oracle_identity_bound,
        observer_blinding,
        runtime_subject_sha256 is not None,
        carryover_exclusion,
        order_counterbalance,
        representation_invariance,
        semantic_selectivity,
        outcome_matches_oracle,
        sham_exclusion,
    )
    classification = PASS if all(gates) else FAIL

    # Structural PASS cannot prove the oracle producer or recorder is operationally
    # independent. Leave room for an explicit ambiguous caller decision.
    if classification == PASS and oracle_source_sha256 == runtime_subject_sha256:
        classification = AMBIGUOUS
        reasons.append("oracle source identity equals runtime subject identity")

    return Evaluation(
        schema=SCHEMA,
        classification=classification,
        reasons=tuple(reasons),
        manifest_sha256=manifest_sha256,
        oracle_source_sha256=oracle_source_sha256,
        runtime_subject_sha256=runtime_subject_sha256,
        representation_invariance=representation_invariance,
        semantic_selectivity=semantic_selectivity,
        sham_exclusion=sham_exclusion,
        carryover_exclusion=carryover_exclusion,
        order_counterbalance=order_counterbalance,
        observer_blinding=observer_blinding,
        oracle_identity_bound=oracle_identity_bound,
    )
