#!/usr/bin/env python3
"""Deterministic falsification suite for F2-WP-502 Hyperposition."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from frankenstein2.hyperposition import (
    Alternative,
    EpistemicStatus,
    HyperpositionError,
    create_discriminator_candidate,
    create_hyperposition,
    verify_hyperposition_binding,
)


def alt(
    alternative_id: str,
    proposition_ref: str,
    *,
    status: EpistemicStatus = EpistemicStatus.INFERRED,
    generation: int = 3,
    support_refs: tuple[str, ...] = ("evidence:support",),
    counterevidence_refs: tuple[str, ...] = (),
    score_micros: int | None = 500_000,
    uncertainty_micros: int | None = 500_000,
    recurrence_count: int = 0,
    peer_support_count: int = 0,
) -> Alternative:
    return Alternative(
        alternative_id=alternative_id,
        proposition_ref=proposition_ref,
        generation=generation,
        epistemic_status=status,
        provenance_refs=("source:test",),
        support_refs=support_refs,
        counterevidence_refs=counterevidence_refs,
        score_micros=score_micros,
        uncertainty_micros=uncertainty_micros,
        recurrence_count=recurrence_count,
        peer_support_count=peer_support_count,
    )


def state() -> object:
    return create_hyperposition(
        hyperposition_id="hyper:1",
        generation=3,
        alternatives=(
            alt("alt:b", "hypothesis:b"),
            alt("alt:a", "hypothesis:a"),
        ),
        provenance_refs=("source:z", "source:a"),
        situation_frame_ref="situation:42",
        situation_frame_generation=4,
        situation_frame_sha256="a" * 64,
        policy_ref="policy:bounded",
    )


class HyperpositionTests(unittest.TestCase):
    def test_multiple_alternatives_are_preserved_without_winner(self):
        hp = state()
        self.assertEqual(
            tuple(item.alternative_id for item in hp.alternatives),
            ("alt:a", "alt:b"),
        )
        self.assertEqual(hp.as_dict()["selection_authority"], "NONE")
        self.assertNotIn("winner", hp.as_dict())
        self.assertIn("NOT_WORLD_TRUTH", hp.classification)

    def test_digest_is_canonical_under_alternative_and_ref_order(self):
        left = state()
        right = create_hyperposition(
            hyperposition_id="hyper:1",
            generation=3,
            alternatives=(
                alt("alt:a", "hypothesis:a", support_refs=("evidence:z", "evidence:a")),
                alt("alt:b", "hypothesis:b", support_refs=("evidence:y", "evidence:b")),
            ),
            provenance_refs=("source:a", "source:z"),
            situation_frame_ref="situation:42",
        situation_frame_generation=4,
        situation_frame_sha256="a" * 64,
            policy_ref="policy:bounded",
        )
        comparable = create_hyperposition(
            hyperposition_id="hyper:1",
            generation=3,
            alternatives=(
                alt("alt:b", "hypothesis:b", support_refs=("evidence:b", "evidence:y")),
                alt("alt:a", "hypothesis:a", support_refs=("evidence:a", "evidence:z")),
            ),
            provenance_refs=("source:z", "source:a"),
            situation_frame_ref="situation:42",
        situation_frame_generation=4,
        situation_frame_sha256="a" * 64,
            policy_ref="policy:bounded",
        )
        self.assertEqual(right.canonical_json(), comparable.canonical_json())
        self.assertEqual(right.sha256(), comparable.sha256())
        self.assertNotEqual(left.sha256(), right.sha256())

    def test_recurrence_peer_support_and_score_do_not_promote_truth(self):
        candidate = alt(
            "alt:a",
            "hypothesis:a",
            recurrence_count=1_000_000,
            peer_support_count=1_000_000,
            score_micros=1_000_000,
        )
        self.assertIs(candidate.epistemic_status, EpistemicStatus.INFERRED)
        self.assertIn("DO_NOT_MINT_TRUTH", candidate.as_dict()["authority_boundary"])

    def test_unknown_conflict_and_not_computed_are_distinct(self):
        unknown = alt(
            "alt:u",
            "hypothesis:u",
            status=EpistemicStatus.UNKNOWN,
            support_refs=(),
            score_micros=None,
        )
        conflict = alt(
            "alt:c",
            "hypothesis:c",
            status=EpistemicStatus.CONFLICT,
            support_refs=("evidence:yes",),
            counterevidence_refs=("evidence:no",),
        )
        not_computed = alt(
            "alt:n",
            "hypothesis:n",
            status=EpistemicStatus.NOT_COMPUTED,
            support_refs=(),
            score_micros=None,
            uncertainty_micros=None,
        )
        self.assertEqual(
            {unknown.epistemic_status, conflict.epistemic_status, not_computed.epistemic_status},
            {
                EpistemicStatus.UNKNOWN,
                EpistemicStatus.CONFLICT,
                EpistemicStatus.NOT_COMPUTED,
            },
        )

    def test_known_string_is_not_an_epistemic_status(self):
        with self.assertRaises(ValueError):
            EpistemicStatus("KNOWN")

    def test_not_computed_cannot_smuggle_computed_evidence_or_score(self):
        with self.assertRaisesRegex(HyperpositionError, "NOT_COMPUTED"):
            alt(
                "alt:n",
                "hypothesis:n",
                status=EpistemicStatus.NOT_COMPUTED,
                support_refs=("evidence:smuggled",),
                score_micros=None,
                uncertainty_micros=None,
            )
        with self.assertRaisesRegex(HyperpositionError, "NOT_COMPUTED"):
            alt(
                "alt:n",
                "hypothesis:n",
                status=EpistemicStatus.NOT_COMPUTED,
                support_refs=(),
                score_micros=1,
                uncertainty_micros=None,
            )

    def test_conflict_requires_both_support_and_counterevidence(self):
        with self.assertRaisesRegex(HyperpositionError, "CONFLICT"):
            alt(
                "alt:c",
                "hypothesis:c",
                status=EpistemicStatus.CONFLICT,
                support_refs=("evidence:yes",),
                counterevidence_refs=(),
            )

    def test_duplicate_alternative_or_proposition_identity_fails_closed(self):
        a = alt("alt:a", "hypothesis:a")
        with self.assertRaisesRegex(HyperpositionError, "duplicate alternative_id"):
            create_hyperposition(
                hyperposition_id="hyper:dup",
                generation=3,
                alternatives=(a, alt("alt:a", "hypothesis:b")),
                provenance_refs=("source:test",),
            )
        with self.assertRaisesRegex(HyperpositionError, "duplicate proposition_ref"):
            create_hyperposition(
                hyperposition_id="hyper:dup-prop",
                generation=3,
                alternatives=(a, alt("alt:b", "hypothesis:a")),
                provenance_refs=("source:test",),
            )

    def test_support_and_counterevidence_overlap_fails_closed(self):
        with self.assertRaisesRegex(HyperpositionError, "must not overlap"):
            alt(
                "alt:c",
                "hypothesis:c",
                status=EpistemicStatus.CONFLICT,
                support_refs=("evidence:same",),
                counterevidence_refs=("evidence:same",),
            )

    def test_alternative_generation_mismatch_fails_closed(self):
        with self.assertRaisesRegex(HyperpositionError, "generation mismatch"):
            create_hyperposition(
                hyperposition_id="hyper:stale",
                generation=3,
                alternatives=(
                    alt("alt:a", "hypothesis:a", generation=3),
                    alt("alt:b", "hypothesis:b", generation=2),
                ),
                provenance_refs=("source:test",),
            )

    def test_exact_binding_rejects_stale_generation_or_digest(self):
        hp = state()
        verify_hyperposition_binding(
            hp,
            expected_generation=3,
            expected_state_sha256=hp.sha256(),
        )
        with self.assertRaisesRegex(HyperpositionError, "generation mismatch"):
            verify_hyperposition_binding(
                hp,
                expected_generation=2,
                expected_state_sha256=hp.sha256(),
            )
        with self.assertRaisesRegex(HyperpositionError, "digest mismatch"):
            verify_hyperposition_binding(
                hp,
                expected_generation=3,
                expected_state_sha256="0" * 64,
            )

    def test_discriminator_is_exactly_bound_and_targets_are_canonical(self):
        hp = state()
        discriminator = create_discriminator_candidate(
            state=hp,
            expected_generation=3,
            expected_state_sha256=hp.sha256(),
            discriminator_id="disc:1",
            target_alternative_ids=("alt:b", "alt:a"),
            evidence_need_ref="need:measurement",
            expected_information_gain_micros=800_000,
            estimated_cost_micros=100_000,
            provenance_refs=("source:test",),
        )
        self.assertEqual(discriminator.hyperposition_sha256, hp.sha256())
        self.assertEqual(discriminator.target_alternative_ids, ("alt:a", "alt:b"))
        self.assertIn("NOT_ACTION_OR_EFFECT_AUTHORITY", discriminator.classification)
        self.assertEqual(discriminator.as_dict()["effect_authority"], "NONE")

    def test_discriminator_cannot_target_unknown_alternative(self):
        hp = state()
        with self.assertRaisesRegex(HyperpositionError, "unknown alternatives"):
            create_discriminator_candidate(
                state=hp,
                expected_generation=3,
                expected_state_sha256=hp.sha256(),
                discriminator_id="disc:bad",
                target_alternative_ids=("alt:a", "alt:missing"),
                evidence_need_ref="need:measurement",
                expected_information_gain_micros=800_000,
                estimated_cost_micros=100_000,
                provenance_refs=("source:test",),
            )

    def test_situation_frame_binding_requires_exact_version_triple(self):
        with self.assertRaisesRegex(HyperpositionError, "ref, generation, and digest"):
            create_hyperposition(
                hyperposition_id="hyper:partial-frame",
                generation=3,
                alternatives=(alt("alt:a", "hypothesis:a"), alt("alt:b", "hypothesis:b")),
                provenance_refs=("source:test",),
                situation_frame_ref="situation:42",
            )

    def test_situation_frame_version_changes_hyperposition_digest(self):
        current = state()
        stale = create_hyperposition(
            hyperposition_id="hyper:1",
            generation=3,
            alternatives=(alt("alt:b", "hypothesis:b"), alt("alt:a", "hypothesis:a")),
            provenance_refs=("source:z", "source:a"),
            situation_frame_ref="situation:42",
            situation_frame_generation=3,
            situation_frame_sha256="b" * 64,
            policy_ref="policy:bounded",
        )
        self.assertNotEqual(current.sha256(), stale.sha256())
        self.assertEqual(current.as_dict()["situation_frame_generation"], 4)
        self.assertEqual(current.as_dict()["situation_frame_sha256"], "a" * 64)

    def test_hyperposition_is_frozen(self):
        hp = state()
        with self.assertRaises(FrozenInstanceError):
            hp.generation = 4


if __name__ == "__main__":
    unittest.main()
