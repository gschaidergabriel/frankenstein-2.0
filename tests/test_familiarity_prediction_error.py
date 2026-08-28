from dataclasses import replace

import pytest

from frankenstein2.familiarity_prediction_error import (
    CLASS_BOUNDED_MISMATCH,
    CLASS_FAMILIAR_CONTRADICTION,
    CLASS_FAMILIAR_MATCH,
    CLASS_HIGH_ERROR_LOW_FAMILIARITY,
    CLASS_LOW_FAMILIARITY_MATCH,
    CLASS_UNKNOWN_FAMILIARITY,
    FAMILIARITY_KNOWN,
    FAMILIARITY_UNKNOWN,
    FamiliarityBindingPolicy,
    FamiliarityPredictionError,
    FamiliaritySignal,
    bind_familiarity_to_prediction_error,
)
from frankenstein2.prediction_contract import PredictionContract


BASIS = "a" * 64
OBS = "b" * 64


def _residual(expected, observed, *, target_id="target-1", generation=1):
    contract = PredictionContract.create(
        prediction_id="prediction-1",
        target_id=target_id,
        generation=generation,
        basis_fingerprint_sha256=BASIS,
        expected_projection=expected,
    )
    return contract.observe(
        observation_id="observation-1",
        observation_fingerprint_sha256=OBS,
        observed_projection=observed,
    )


def _known(score_bp=8000, *, target_id="target-1", generation=1):
    return FamiliaritySignal.known(
        signal_id="familiarity-1",
        target_id=target_id,
        generation=generation,
        score_bp=score_bp,
        evidence_refs=("memory:episode-7", "retrieval:axis-confidence"),
    )


def _bind(signal, residual, policy=None):
    if policy is None:
        policy = FamiliarityBindingPolicy.create()
    return bind_familiarity_to_prediction_error(
        binding_id="binding-1",
        signal=signal,
        residual=residual,
        expected_residual_sha256=residual.sha256(),
        residual_evidence_refs=("prediction:receipt-1", "observation:receipt-1"),
        policy=policy,
    )


def test_known_signal_is_explicit_and_evidence_order_is_canonical():
    signal = FamiliaritySignal.known(
        signal_id="familiarity-1",
        target_id="target-1",
        generation=2,
        score_bp=7000,
        evidence_refs=("z", "a"),
    )
    assert signal.state == FAMILIARITY_KNOWN
    assert signal.score_bp == 7000
    assert signal.evidence_refs == ("a", "z")
    assert signal.sha256() == signal.sha256()


def test_unknown_signal_preserves_unknown_without_fake_score():
    residual = _residual({"x": 1}, {"x": 1})
    signal = FamiliaritySignal.unknown(
        signal_id="familiarity-unknown",
        target_id="target-1",
        generation=1,
        evidence_refs=("sensor:insufficient-history",),
    )
    result = _bind(signal, residual)
    assert signal.state == FAMILIARITY_UNKNOWN
    assert signal.score_bp is None
    assert result.familiarity_score_bp is None
    assert result.calibration_class == CLASS_UNKNOWN_FAMILIARITY
    assert result.exact_match is True


def test_familiar_exact_match_is_candidate_not_truth():
    residual = _residual({"x": 1, "y": "ok"}, {"x": 1, "y": "ok"})
    result = _bind(_known(9000), residual)
    assert result.calibration_class == CLASS_FAMILIAR_MATCH
    assert result.mismatch_bp == 0
    assert result.contradiction_preserved is False
    assert "NOT_OBSERVATION_TRUTH" in result.classification


def test_low_familiarity_exact_match_stays_distinct():
    residual = _residual({"x": 1}, {"x": 1})
    result = _bind(_known(2000), residual)
    assert result.calibration_class == CLASS_LOW_FAMILIARITY_MATCH
    assert result.mismatch_bp == 0


def test_familiar_large_prediction_error_preserves_contradiction():
    residual = _residual(
        {"a": 1, "b": 2, "c": 3, "d": 4},
        {"a": 9, "b": 8, "c": 3, "d": 4},
    )
    result = _bind(_known(9000), residual)
    assert result.mismatch_bp == 5000
    assert result.calibration_class == CLASS_FAMILIAR_CONTRADICTION
    assert result.contradiction_preserved is True


def test_same_error_with_low_familiarity_does_not_claim_contradiction():
    residual = _residual(
        {"a": 1, "b": 2, "c": 3, "d": 4},
        {"a": 9, "b": 8, "c": 3, "d": 4},
    )
    result = _bind(_known(1000), residual)
    assert result.calibration_class == CLASS_HIGH_ERROR_LOW_FAMILIARITY
    assert result.contradiction_preserved is False


def test_small_mismatch_remains_bounded_mismatch():
    expected = {str(i): i for i in range(10)}
    observed = dict(expected)
    observed["0"] = 99
    result = _bind(_known(1000), _residual(expected, observed))
    assert result.mismatch_bp == 1000
    assert result.calibration_class == CLASS_BOUNDED_MISMATCH


def test_policy_thresholds_are_explicit_and_deterministic():
    residual = _residual({"a": 1, "b": 2}, {"a": 9, "b": 2})
    policy = FamiliarityBindingPolicy.create(
        familiar_threshold_bp=5000,
        high_prediction_error_threshold_bp=6000,
    )
    result = _bind(_known(8000), residual, policy)
    assert result.mismatch_bp == 5000
    assert result.calibration_class == CLASS_BOUNDED_MISMATCH


def test_target_mismatch_fails_closed():
    residual = _residual({"x": 1}, {"x": 2}, target_id="target-a")
    signal = _known(8000, target_id="target-b")
    with pytest.raises(FamiliarityPredictionError, match="target"):
        _bind(signal, residual)


def test_generation_mismatch_fails_closed():
    residual = _residual({"x": 1}, {"x": 2}, generation=3)
    signal = _known(8000, generation=2)
    with pytest.raises(FamiliarityPredictionError, match="generation"):
        _bind(signal, residual)


def test_stale_or_wrong_residual_digest_fails_closed():
    residual = _residual({"x": 1}, {"x": 2})
    with pytest.raises(FamiliarityPredictionError, match="digest mismatch"):
        bind_familiarity_to_prediction_error(
            binding_id="binding-1",
            signal=_known(),
            residual=residual,
            expected_residual_sha256="0" * 64,
            residual_evidence_refs=("prediction:receipt-1",),
            policy=FamiliarityBindingPolicy.create(),
        )


def test_internally_inconsistent_residual_is_rejected_even_if_dataclass_type_matches():
    residual = _residual({"x": 1}, {"x": 2})
    corrupted = replace(residual, exact_match=True)
    with pytest.raises(FamiliarityPredictionError, match="exact_match"):
        bind_familiarity_to_prediction_error(
            binding_id="binding-1",
            signal=_known(),
            residual=corrupted,
            expected_residual_sha256=corrupted.sha256(),
            residual_evidence_refs=("prediction:receipt-1",),
            policy=FamiliarityBindingPolicy.create(),
        )


def test_missing_or_duplicate_evidence_fails_closed():
    residual = _residual({"x": 1}, {"x": 1})
    with pytest.raises(FamiliarityPredictionError, match="at least one"):
        bind_familiarity_to_prediction_error(
            binding_id="binding-1",
            signal=_known(),
            residual=residual,
            expected_residual_sha256=residual.sha256(),
            residual_evidence_refs=(),
            policy=FamiliarityBindingPolicy.create(),
        )
    with pytest.raises(FamiliarityPredictionError, match="duplicate"):
        FamiliaritySignal.known(
            signal_id="familiarity-dup",
            target_id="target-1",
            generation=1,
            score_bp=5000,
            evidence_refs=("same", "same"),
        )


def test_unknown_signal_rejects_numeric_score():
    with pytest.raises(FamiliarityPredictionError, match="UNKNOWN"):
        FamiliaritySignal(
            schema="FRANKENSTEIN2_FAMILIARITY_SIGNAL/v1",
            signal_id="familiarity-unknown",
            target_id="target-1",
            generation=1,
            state=FAMILIARITY_UNKNOWN,
            score_bp=1,
            evidence_refs=("evidence:1",),
        )
