from __future__ import annotations

import unittest

from frankenstein2.direct_delegate_router import DELEGATE_BUILD
from frankenstein2.recursion_router import R0, R1, R2, R3, RecursionNeed, RecursionRouterError, route_recursion
from test_recursion_router import make_child_request, make_policy, make_route


class WP603G2PolicyRevalidationFalsifier(unittest.TestCase):
    def test_g2_rejects_post_init_policy_mutation_before_consuming_fields(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=0)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_mode=R2,
            remaining_nested_child_edges=0,
            generation=1,
            provenance_refs=("review:wp603-g2-policy-post-init-mutation",),
        )
        policy = make_policy(admitted_modes=(R0, R1, R2, R3))

        # Bypass RecursionPolicy.__post_init__.  Membership remains true for R2,
        # but the policy object is no longer in the canonical admitted-mode order.
        # The consumer must reconstruct/revalidate before using policy fields.
        object.__setattr__(policy, "admitted_modes", (R0, R2, R1, R3))

        with self.assertRaises(RecursionRouterError):
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=policy,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
