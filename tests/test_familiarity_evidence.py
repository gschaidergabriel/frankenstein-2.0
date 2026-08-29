import pytest

from frankenstein2.familiarity_evidence import (
    FamiliarityEvidence,
    FamiliarityEvidenceError,
    FamiliarityPromotionPolicy,
    evaluate_familiarity,
)

OBS = "a" * 64


def ev(eid, kind, *, at=100, confidence=700_000, proto="desk-1", generation=1,
       key="scene.desk_state", observed=None, independent=None):
    return FamiliarityEvidence(
        evidence_id=eid,
        prototype_id=proto,
        prototype_generation=generation,
        semantic_key=key,
        evidence_kind=kind,
        evidence_time_ns=at,
        confidence_micros=confidence,
        provenance_refs=(f"source:{eid}",),
        observed_claim_sha256=observed,
        independence_key=independent,
    )


def pair(e):
    return (e, e.sha256())


def decide(*events, policy=None):
    kwargs = {}
    if policy is not None:
        kwargs["policy"] = policy
    return evaluate_familiarity(
        prototype_id="desk-1",
        prototype_generation=1,
        semantic_key="scene.desk_state",
        evidence=tuple(pair(event) for event in events),
        **kwargs,
    )


def fresh(eid, at, independent):
    return ev(eid, "FRESH_EXPENSIVE_CONFIRMATION", at=at, observed=OBS, independent=independent)


def cheap(eid, at=100):
    return ev(eid, "CHEAP_MATCH", at=at)


def prior(eid, at=100):
    return ev(eid, "RETRIEVED_PRIOR", at=at)


def test_three_independent_fresh_confirmations_over_span_become_promotion_eligible():
    result = decide(
        fresh("f1", 0, "camera:round-1"),
        fresh("f2", 15_000_000_000, "camera:round-2"),
        fresh("f3", 31_000_000_000, "camera:round-3"),
    )
    assert result.status == "FAMILIAR_CURRENT_CONFIRMED"
    assert result.current_observation_present is True
    assert result.independent_fresh_confirmation_count == 3
    assert result.fresh_confirmation_span_ns == 31_000_000_000
    assert result.latest_fresh_confirmation_time_ns == 31_000_000_000
    assert result.promotion_eligible is True


def test_many_cheap_hits_never_promote_refresh_anchor_or_masquerade_as_observation():
    events = tuple(cheap(f"c{i}", at=i * 10**12) for i in range(20))
    result = decide(*events)
    assert result.status == "FAMILIAR_CANDIDATE_CHEAP"
    assert result.current_observation_present is False
    assert result.independent_fresh_confirmation_count == 0
    assert result.fresh_confirmation_span_ns == 0
    assert result.latest_fresh_confirmation_time_ns is None
    assert result.promotion_eligible is False
    assert len(result.cheap_match_sha256s) == 20


def test_retrieved_prior_only_remains_open_set_unknown():
    result = decide(prior("r1"), prior("r2"))
    assert result.status == "UNKNOWN_OPEN_SET"
    assert result.current_observation_present is False
    assert result.promotion_eligible is False


def test_cheap_and_retrieved_evidence_do_not_change_fresh_promotion_math():
    f1 = fresh("f1", 0, "a")
    f2 = fresh("f2", 40_000_000_000, "b")
    policy = FamiliarityPromotionPolicy(min_independent_fresh_confirmations=2, min_fresh_span_ns=30_000_000_000)
    base = decide(f1, f2, policy=policy)
    mixed = decide(f1, f2, cheap("c1", at=999_000_000_000), prior("r1", at=999_000_000_001), policy=policy)
    assert base.promotion_eligible is True
    assert mixed.promotion_eligible is True
    assert mixed.independent_fresh_confirmation_count == base.independent_fresh_confirmation_count
    assert mixed.fresh_confirmation_span_ns == base.fresh_confirmation_span_ns
    assert mixed.latest_fresh_confirmation_time_ns == base.latest_fresh_confirmation_time_ns


def test_repeated_same_independence_key_cannot_fake_independent_confirmation_count():
    policy = FamiliarityPromotionPolicy(min_independent_fresh_confirmations=2, min_fresh_span_ns=1)
    result = decide(
        fresh("f1", 0, "same-capture-lineage"),
        fresh("f2", 100_000_000_000, "same-capture-lineage"),
        policy=policy,
    )
    assert result.independent_fresh_confirmation_count == 1
    assert result.promotion_eligible is False


def test_minimum_span_is_required_even_with_enough_independent_confirmations():
    result = decide(fresh("f1", 0, "a"), fresh("f2", 1, "b"), fresh("f3", 2, "c"))
    assert result.independent_fresh_confirmation_count == 3
    assert result.promotion_eligible is False


@pytest.mark.parametrize("scope", ["person.identity", "person.face_presence", "scene.biometric_match", "FACE"])
def test_person_face_identity_biometric_scopes_are_rejected(scope):
    with pytest.raises(FamiliarityEvidenceError, match="must not target"):
        ev("bad", "CHEAP_MATCH", key=scope)


def test_cheap_or_retrieved_evidence_cannot_carry_observed_claim_or_independence_key():
    with pytest.raises(FamiliarityEvidenceError, match="cannot masquerade"):
        ev("c1", "CHEAP_MATCH", observed=OBS)
    with pytest.raises(FamiliarityEvidenceError, match="cannot claim independent"):
        ev("r1", "RETRIEVED_PRIOR", independent="fake")


def test_fresh_confirmation_requires_exact_observed_identity_and_independence_key():
    with pytest.raises(FamiliarityEvidenceError, match="requires observed"):
        ev("f1", "FRESH_EXPENSIVE_CONFIRMATION", independent="a")
    with pytest.raises(FamiliarityEvidenceError, match="requires independence"):
        ev("f1", "FRESH_EXPENSIVE_CONFIRMATION", observed=OBS)


def test_digest_mismatch_fails_closed():
    event = cheap("c1")
    with pytest.raises(FamiliarityEvidenceError, match="digest mismatch"):
        evaluate_familiarity(
            prototype_id="desk-1",
            prototype_generation=1,
            semantic_key="scene.desk_state",
            evidence=((event, "b" * 64),),
        )


def test_cross_prototype_generation_or_semantic_scope_fails_closed():
    for event in (
        ev("wrong-proto", "CHEAP_MATCH", proto="other"),
        ev("wrong-gen", "CHEAP_MATCH", generation=2),
        ev("wrong-key", "CHEAP_MATCH", key="scene.other_state"),
    ):
        with pytest.raises(FamiliarityEvidenceError, match="scope mismatch"):
            evaluate_familiarity(
                prototype_id="desk-1",
                prototype_generation=1,
                semantic_key="scene.desk_state",
                evidence=(pair(event),),
            )


def test_output_is_canonical_order_independent_and_has_no_authority():
    a = fresh("f1", 0, "a")
    b = cheap("c1")
    first = decide(a, b)
    second = decide(b, a)
    assert first.sha256() == second.sha256()
    payload = first.as_dict()
    assert payload["cheap_match_can_promote"] is False
    assert payload["retrieval_can_become_current_observation"] is False
    assert payload["person_identity_scope_allowed"] is False
    assert payload["world_truth_authority"] == "NONE"
    assert payload["identity_authority"] == "NONE"
    assert payload["gwt_authority"] == "NONE"
    assert payload["effect_authority"] == "NONE"
    assert payload["completion_authority"] == "NONE"


def test_policy_is_bounded_and_fail_closed():
    with pytest.raises(FamiliarityEvidenceError, match="cannot exceed"):
        FamiliarityPromotionPolicy(min_independent_fresh_confirmations=4, max_independent_fresh_confirmations=3)
    with pytest.raises(FamiliarityEvidenceError, match="hard safety cap"):
        FamiliarityPromotionPolicy(max_independent_fresh_confirmations=65)
