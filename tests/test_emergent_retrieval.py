import hashlib

import pytest

from frankenstein2.emergent_retrieval import (
    AXIS_CAUSAL,
    AXIS_GOAL,
    AXIS_SEMANTIC,
    CLASSIFICATION_INSUFFICIENT,
    CLASSIFICATION_LIMIT,
    CLASSIFICATION_SUPERSEDED,
    EmergentRetrievalError,
    RetrievalCandidate,
    RetrievalNeed,
    RetrievalSignal,
    build_retrieval_plan,
)
from frankenstein2.memory_lifecycle import (
    STATUS_DEGRADED,
    MemoryTransition,
    TRANSITION_DEGRADE,
    TRANSITION_SUPERSEDE,
    apply_memory_transition,
    create_memory,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _memory(memory_id: str):
    return create_memory(
        memory_id=memory_id,
        payload_ref=f"payload:{memory_id}",
        payload_sha256=_sha(f"payload:{memory_id}"),
        provenance_refs=(f"evidence:{memory_id}",),
    )


def _signal(axis: str, score: int, suffix: str = "x") -> RetrievalSignal:
    return RetrievalSignal.create(
        axis=axis,
        score_bp=score,
        evidence_refs=(f"signal:{axis}:{suffix}",),
    )


def _candidate(memory, goal: int, semantic: int, causal: int, suffix: str = "x"):
    return RetrievalCandidate.create(
        memory=memory,
        signals=(
            _signal(AXIS_GOAL, goal, suffix),
            _signal(AXIS_SEMANTIC, semantic, suffix),
            _signal(AXIS_CAUSAL, causal, suffix),
        ),
        candidate_evidence_refs=(f"candidate:{memory.memory_id}:{suffix}",),
    )


def _need(limit: int = 8) -> RetrievalNeed:
    return RetrievalNeed.create(
        need_id="need:unit",
        axis_weights_bp={AXIS_GOAL: 10_000, AXIS_SEMANTIC: 10_000, AXIS_CAUSAL: 10_000},
        min_overlap_axes=2,
        limit=limit,
        evidence_refs=("need:evidence",),
    )


def test_multi_axis_overlap_beats_single_high_similarity():
    semantic_only = _candidate(_memory("m:semantic"), 0, 10_000, 0, "one")
    overlapping = _candidate(_memory("m:overlap"), 7_000, 7_000, 7_000, "many")

    plan = build_retrieval_plan(_need(), (semantic_only, overlapping))

    assert [result.memory_id for result in plan.selected] == ["m:overlap"]
    rejected = {result.memory_id: result for result in plan.not_selected}
    assert rejected["m:semantic"].classification == CLASSIFICATION_INSUFFICIENT
    assert rejected["m:semantic"].payload_ref is None
    assert rejected["m:semantic"].payload_sha256 is None


def test_rank_prefers_explicit_overlap_not_input_order():
    weaker = _candidate(_memory("m:weaker"), 7_000, 7_000, 7_000, "weak")
    stronger = _candidate(_memory("m:stronger"), 8_000, 8_000, 8_000, "strong")

    forward = build_retrieval_plan(_need(), (weaker, stronger))
    reverse = build_retrieval_plan(_need(), (stronger, weaker))

    assert [item.memory_id for item in forward.selected] == ["m:stronger", "m:weaker"]
    assert forward.as_dict() == reverse.as_dict()
    assert forward.sha256() == reverse.sha256()


def test_equal_score_tie_break_is_stable_memory_identity():
    a = _candidate(_memory("m:a"), 5_000, 5_000, 5_000, "a")
    b = _candidate(_memory("m:b"), 5_000, 5_000, 5_000, "b")

    plan = build_retrieval_plan(_need(), (b, a))

    assert [item.memory_id for item in plan.selected] == ["m:a", "m:b"]


def test_degraded_memory_is_not_deleted_or_silently_restored():
    original = _memory("m:degraded")
    transition = MemoryTransition.create(
        transition_id="transition:degrade",
        memory_id=original.memory_id,
        expected_generation=original.generation,
        expected_state_sha256=original.sha256(),
        kind=TRANSITION_DEGRADE,
        evidence_refs=("evidence:degrade",),
    )
    degraded, _ = apply_memory_transition(original, transition)
    assert degraded.status == STATUS_DEGRADED

    result = build_retrieval_plan(_need(), (_candidate(degraded, 6_000, 6_000, 6_000),)).selected[0]

    assert result.lifecycle_status == STATUS_DEGRADED
    assert result.payload_ref == degraded.payload_ref
    assert result.payload_sha256 == degraded.payload_sha256
    assert original.generation == 0
    assert degraded.generation == 1


def test_superseded_memory_returns_redirect_only_and_never_payload():
    original = _memory("m:old")
    transition = MemoryTransition.create(
        transition_id="transition:supersede",
        memory_id=original.memory_id,
        expected_generation=original.generation,
        expected_state_sha256=original.sha256(),
        kind=TRANSITION_SUPERSEDE,
        evidence_refs=("evidence:supersede",),
        successor_ref="m:new",
    )
    superseded, _ = apply_memory_transition(original, transition)

    plan = build_retrieval_plan(_need(), (_candidate(superseded, 10_000, 10_000, 10_000),))

    assert plan.selected == ()
    result = plan.not_selected[0]
    assert result.classification == CLASSIFICATION_SUPERSEDED
    assert result.successor_ref == "m:new"
    assert result.payload_ref is None
    assert result.payload_sha256 is None


def test_required_signal_axis_must_be_explicit_not_inferred():
    memory = _memory("m:missing")
    candidate = RetrievalCandidate.create(
        memory=memory,
        signals=(
            _signal(AXIS_GOAL, 9_000),
            _signal(AXIS_SEMANTIC, 9_000),
        ),
        candidate_evidence_refs=("candidate:missing",),
    )

    with pytest.raises(EmergentRetrievalError, match="missing required signal axes"):
        build_retrieval_plan(_need(), (candidate,))


def test_single_axis_need_is_forbidden():
    with pytest.raises(EmergentRetrievalError, match="at least 2"):
        RetrievalNeed.create(
            need_id="need:bad",
            axis_weights_bp={AXIS_SEMANTIC: 10_000},
            min_overlap_axes=1,
            evidence_refs=("need:bad:evidence",),
        )


def test_duplicate_memory_candidates_fail_closed():
    memory = _memory("m:duplicate")
    first = _candidate(memory, 5_000, 5_000, 5_000, "first")
    second = _candidate(memory, 8_000, 8_000, 8_000, "second")

    with pytest.raises(EmergentRetrievalError, match="duplicate memory_id"):
        build_retrieval_plan(_need(), (first, second))


def test_limit_does_not_leak_payload_reference_for_unselected_overflow():
    first = _candidate(_memory("m:first"), 9_000, 9_000, 9_000, "first")
    second = _candidate(_memory("m:second"), 8_000, 8_000, 8_000, "second")

    plan = build_retrieval_plan(_need(limit=1), (second, first))

    assert [result.memory_id for result in plan.selected] == ["m:first"]
    overflow = next(result for result in plan.not_selected if result.memory_id == "m:second")
    assert overflow.classification == CLASSIFICATION_LIMIT
    assert overflow.payload_ref is None
    assert overflow.payload_sha256 is None


def test_signal_scores_are_bounded_integer_evidence_not_floats():
    with pytest.raises(EmergentRetrievalError, match="integer basis-point"):
        RetrievalSignal.create(axis=AXIS_GOAL, score_bp=0.5, evidence_refs=("e",))
    with pytest.raises(EmergentRetrievalError, match="between"):
        RetrievalSignal.create(axis=AXIS_GOAL, score_bp=10_001, evidence_refs=("e",))


def test_plan_preserves_exact_memory_and_signal_provenance():
    memory = _memory("m:provenance")
    candidate = _candidate(memory, 7_000, 8_000, 9_000, "prov")

    result = build_retrieval_plan(_need(), (candidate,)).selected[0]

    assert result.memory_state_sha256 == memory.sha256()
    assert result.provenance_refs == memory.provenance_refs
    assert dict(result.signal_scores_bp) == {
        AXIS_CAUSAL: 9_000,
        AXIS_GOAL: 7_000,
        AXIS_SEMANTIC: 8_000,
    }
    evidence = dict(result.signal_evidence_refs)
    assert evidence[AXIS_CAUSAL] == ("signal:causal:prov",)
    assert result.candidate_sha256 == candidate.sha256()
