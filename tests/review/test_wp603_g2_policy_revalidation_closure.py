from __future__ import annotations

import unittest

from frankenstein2.direct_delegate_router import DELEGATE_BUILD
from frankenstein2.recursion_router import R0, R1, R2, R3, RecursionNeed, RecursionPolicy, RecursionRouterError, route_recursion
from test_recursion_router import make_child_request, make_route


class WP603G2PolicyRevalidationClosure(unittest.TestCase):
    def test_latest_g2_rejects_post_init_policy_mutation_before_consuming_fields(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=0)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_strategy=R2,
            remaining_nested_child_edges=0,
            generation=1,
            provenance_refs=("review:wp603-g2-policy-revalidation-closure",),
        )
        policy = RecursionPolicy.create(
            policy_id="recursion-policy-wp603-g2-review",
            generation=2,
            admitted_strategies=(R0, R1, R2, R3),
            max_nested_child_edges=3,
            provenance_refs=("policy-source:wp603-g2-review",),
        )

        # Bypass RecursionPolicy.__post_init__; canonical reconstruction at the
        # consumer boundary must detect the now noncanonical strategy order.
        object.__setattr__(policy, "admitted_strategies", (R0, R2, R1, R3))

        with self.assertRaises(RecursionRouterError):
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=policy,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
