import pytest

from frankenstein2.epistemic_perception import (
    EpistemicPerceptClaim,
    EpistemicPerceptionError,
    build_epistemic_field,
)

RETINA = "a" * 64


def claim(cid, kind, value, confidence=700_000, *, generation=1, at=100, key="person.presence", modality="vision", retina=None):
    return EpistemicPerceptClaim(
        claim_id=cid,
        semantic_key=key,
        modality=modality,
        epistemic_type=kind,
        value=value,
        confidence_micros=confidence,
        source_generation=generation,
        source_time_ns=at,
        provenance_refs=(f"source:{kind.lower()}",),
        upstream_retina_assessment_sha256=retina,
    )


def pair(c):
    return (c, c.sha256())


def build(*, observed=None, inferred=(), retrieved=()):
    return build_epistemic_field(
        field_id="field-1",
        semantic_key="person.presence",
        modality="vision",
        observed=pair(observed) if observed else None,
        inferred=tuple(pair(c) for c in inferred),
        retrieved=tuple(pair(c) for c in retrieved),
        provenance_refs=("wp701:test",),
    )


def test_observation_defeats_conflicting_retrieval_prior_without_confidence_change():
    observed = claim("o1", "OBSERVED", True, 780_000, retina=RETINA)
    prior = claim("r1", "RETRIEVED", False, 999_999)
    field = build(observed=observed, retrieved=(prior,))
    assert field.current_status == "OBSERVED_PRESENT"
    assert field.effective_observed_value is True
    assert field.effective_observed_confidence_micros == 780_000
    assert field.contradiction_claim_sha256s == (prior.sha256(),)
    assert field.as_dict()["memory_can_override_observation"] is False


def test_reverse_conflict_also_preserves_observation():
    observed = claim("o1", "OBSERVED", False, 600_000, retina=RETINA)
    prior = claim("r1", "RETRIEVED", True, 950_000)
    field = build(observed=observed, retrieved=(prior,))
    assert field.effective_observed_value is False
    assert field.contradiction_claim_sha256s == (prior.sha256(),)


def test_conflicting_inference_cannot_replace_observation():
    observed = claim("o1", "OBSERVED", {"count": 1}, 550_000, retina=RETINA)
    inferred = claim("i1", "INFERRED", {"count": 2}, 1_000_000)
    field = build(observed=observed, inferred=(inferred,))
    assert field.effective_observed_value == {"count": 1}
    assert field.effective_observed_confidence_micros == 550_000
    assert inferred.sha256() in field.contradiction_claim_sha256s


def test_agreement_is_recorded_but_never_boosts_observed_confidence():
    observed = claim("o1", "OBSERVED", "open", 510_000, retina=RETINA)
    inferred = claim("i1", "INFERRED", "open", 990_000)
    prior = claim("r1", "RETRIEVED", "open", 990_000)
    field = build(observed=observed, inferred=(inferred,), retrieved=(prior,))
    assert field.effective_observed_confidence_micros == 510_000
    assert field.corroborating_claim_sha256s == tuple(sorted((inferred.sha256(), prior.sha256())))


def test_inference_only_remains_unknown_even_at_max_confidence_and_repetition():
    inferred = tuple(claim(f"i{idx}", "INFERRED", True, 1_000_000, generation=idx + 1) for idx in range(5))
    field = build(inferred=inferred)
    assert field.current_status == "UNKNOWN_NO_CURRENT_OBSERVATION"
    assert field.effective_observed_value is None
    assert field.effective_observed_confidence_micros is None
    assert field.as_dict()["unknown_is_first_class"] is True
    assert field.as_dict()["inference_can_upgrade_to_observation"] is False


def test_retrieval_only_remains_unknown():
    field = build(retrieved=(claim("r1", "RETRIEVED", "historical", 1_000_000),))
    assert field.current_status == "UNKNOWN_NO_CURRENT_OBSERVATION"
    assert field.observed_claim_sha256 is None


def test_retrieved_claim_cannot_carry_current_retina_assessment():
    with pytest.raises(EpistemicPerceptionError, match="must not masquerade"):
        claim("r1", "RETRIEVED", True, retina=RETINA)


def test_wrong_declared_type_in_slot_fails_closed():
    observed = claim("o1", "OBSERVED", True, retina=RETINA)
    with pytest.raises(EpistemicPerceptionError, match="not INFERRED"):
        build_epistemic_field(
            field_id="field-1", semantic_key="person.presence", modality="vision",
            inferred=(pair(observed),), provenance_refs=("test",))


def test_claim_digest_mismatch_fails_closed():
    observed = claim("o1", "OBSERVED", True, retina=RETINA)
    with pytest.raises(EpistemicPerceptionError, match="digest mismatch"):
        build_epistemic_field(
            field_id="field-1", semantic_key="person.presence", modality="vision",
            observed=(observed, "b" * 64), provenance_refs=("test",))


def test_semantic_key_or_modality_cross_contamination_fails_closed():
    observed = claim("o1", "OBSERVED", True, retina=RETINA)
    wrong = claim("i1", "INFERRED", True, key="object.motion")
    with pytest.raises(EpistemicPerceptionError, match="semantic_key/modality mismatch"):
        build(observed=observed, inferred=(wrong,))


def test_duplicate_claim_identity_across_groups_fails_closed():
    inferred = claim("same", "INFERRED", True)
    retrieved = claim("same", "RETRIEVED", False)
    with pytest.raises(EpistemicPerceptionError, match="claim_id must be unique"):
        build(inferred=(inferred,), retrieved=(retrieved,))


def test_output_exposes_no_truth_gwt_effect_or_completion_authority():
    observed = claim("o1", "OBSERVED", True, retina=RETINA)
    payload = build(observed=observed).as_dict()
    assert payload["world_truth_authority"] == "NONE"
    assert payload["gwt_authority"] == "NONE"
    assert payload["effect_authority"] == "NONE"
    assert payload["completion_authority"] == "NONE"
