from __future__ import annotations

import unittest

from frankenstein2.cognitive_microworld import (
    INTERVENTION,
    FIXTURE_SCHEMA,
    ActionSpec,
    MicroWorldFixture,
    RunDescriptor,
    TransitionRule,
    WorldNode,
)


class WP803G2RunDescriptorOriginFalsifier(unittest.TestCase):
    """REVIEW_ONLY negative control for the F2-WP-803 generation-2 repair.

    Passing proves that ``RunDescriptor.assert_matches_fixture`` alone does not authenticate
    builder provenance. The G2 evaluator must separately require the builder-origin seal
    before accepting a descriptor as canonical evaluation provenance.
    """

    @staticmethod
    def _fixture() -> MicroWorldFixture:
        return MicroWorldFixture(
            FIXTURE_SCHEMA,
            "fixture/wp803-g2-run-origin-review",
            1,
            "holdout/wp803-g2-run-origin-review",
            "n0",
            1,
            (ActionSpec("advance", "action/advance", "a" * 64),),
            (
                WorldNode("n0", "public/a", "1" * 64, "hidden/a", "c" * 64, False, 0),
                WorldNode("n1", "public/b", "2" * 64, "hidden/b", "d" * 64, True, 1),
            ),
            (TransitionRule("n0", "advance", "n1", "transition/advance", "e" * 64),),
            "review-independent-source-family",
            ("review/source/wp803-g2-run-origin",),
            "review/donor-none",
            "review/run-origin-falsifier",
        )

    def test_assert_matches_fixture_does_not_by_itself_prove_factory_origin(self) -> None:
        fixture = self._fixture()
        canonical = RunDescriptor.for_fixture(
            fixture,
            run_id="run/wp803-g2-origin-canonical",
            condition=INTERVENTION,
            episode_family_id="family/wp803-g2-origin",
            system_under_test_ref="PUBLIC_PERSISTENCE_BASELINE",
            communication_before_result=False,
            independent_reproduction=True,
        )
        self.assertTrue(canonical._builder_verified)

        direct = RunDescriptor(**canonical.as_dict())
        self.assertFalse(direct._builder_verified)
        self.assertEqual(direct, canonical)
        self.assertEqual(direct.sha256(), canonical.sha256())

        # Current WP800 contract accepts the field-equivalent direct construction here.
        # Therefore G2 must check _builder_verified explicitly in addition to this method.
        direct.assert_matches_fixture(fixture)


if __name__ == "__main__":
    unittest.main()
