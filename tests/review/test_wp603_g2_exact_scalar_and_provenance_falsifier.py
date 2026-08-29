"""REVIEW_ONLY falsifiers for F2-WP-603 generation 2.

No WP603 implementation path is mutated here.  These tests check two exact-current
acceptance risks after the strategy/depth repair:

1. schema/classification trust fields must reject str subclasses, matching the exact
   scalar-boundary lesson already promoted in WP600 generation 2;
2. positive G2 child-harness fixtures must bind WP603 generation 2 / G2 claim identity,
   not silently keep proving the positive path with a generation-1 binding.

The probe follows the current v3 `requested_strategy` ABI. A red run caused only by
using a superseded review-probe field name is infrastructure/test staleness, not product
counterevidence.
"""
from dataclasses import replace
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_recursion_router import make_child_request, make_policy, make_route  # noqa: E402
from frankenstein2.direct_delegate_router import DELEGATE_BUILD, DIRECT_SMALL  # noqa: E402
from frankenstein2.recursion_router import (  # noqa: E402
    R0,
    RecursionNeed,
    RecursionRouterError,
    route_recursion,
)


class EqualityForgedStr(str):
    """Serializes as attacker text while ordinary equality claims any constant matches."""

    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    __hash__ = str.__hash__


class WP603G2ExactScalarAndProvenanceFalsifier(unittest.TestCase):
    def test_policy_schema_subclass_must_fail_closed(self) -> None:
        policy = make_policy()
        with self.assertRaises(RecursionRouterError):
            replace(policy, schema=EqualityForgedStr("WRONG_POLICY_SCHEMA"))

    def test_need_schema_subclass_must_fail_closed(self) -> None:
        route = make_route(selected=DIRECT_SMALL)
        need = RecursionNeed.create(
            route_candidate=route,
            requested_strategy=R0,
            generation=2,
            provenance_refs=("review:wp603-g2-need-schema",),
        )
        with self.assertRaises(RecursionRouterError):
            replace(need, schema=EqualityForgedStr("WRONG_NEED_SCHEMA"))

    def test_candidate_schema_and_classification_subclasses_must_fail_closed(self) -> None:
        route = make_route(selected=DIRECT_SMALL)
        need = RecursionNeed.create(
            route_candidate=route,
            requested_strategy=R0,
            generation=2,
            provenance_refs=("review:wp603-g2-candidate-schema",),
        )
        candidate = route_recursion(route_candidate=route, need=need, policy=make_policy())
        with self.assertRaises(RecursionRouterError):
            replace(candidate, schema=EqualityForgedStr("WRONG_CANDIDATE_SCHEMA"))
        with self.assertRaises(RecursionRouterError):
            replace(candidate, classification=EqualityForgedStr("EFFECT_AUTHORITY"))

    def test_positive_g2_child_fixture_must_bind_generation_two_claim(self) -> None:
        child = make_child_request(max_nested_depth=0)
        self.assertEqual(child.binding.workpackage_id, "F2-WP-603")
        self.assertEqual(child.binding.workpackage_generation, 2)
        self.assertEqual(
            child.binding.claim_id,
            "F2-WP-603-G2-GPT56SOL-STRATEGY-DEPTH-CONTRACT-20260829",
        )


if __name__ == "__main__":
    unittest.main()
