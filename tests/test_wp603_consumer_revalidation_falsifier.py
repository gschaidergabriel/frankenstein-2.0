from __future__ import annotations

import unittest

from frankenstein2.direct_delegate_router import DELEGATE_BUILD
from frankenstein2.recursion_router import RecursionNeed, RecursionRouterError, route_recursion
from test_recursion_router import make_child_request, make_policy, make_route


class WP603ConsumerRevalidationFalsifiers(unittest.TestCase):
    def test_post_init_need_mutation_cannot_change_admitted_depth(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=3)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_depth=1,
            generation=1,
            provenance_refs=("review:need-post-init-mutation",),
        )

        # frozen=True is not a trust boundary: object.__setattr__ can bypass __post_init__.
        # The stored need_id still binds R1, while the directly consumed field now says R3.
        object.__setattr__(need, "requested_depth", 3)

        with self.assertRaises(RecursionRouterError):
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=make_policy(),
            )

    def test_post_init_policy_mutation_cannot_bypass_canonical_policy_invariants(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=3)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_depth=2,
            generation=1,
            provenance_refs=("review:policy-post-init-mutation",),
        )
        policy = make_policy(max_depth=3, admitted_depths=(0, 1, 2, 3))

        # Constructor rejects this order, but direct consumption currently does not
        # reconstruct/revalidate policy content at the consumer boundary.
        object.__setattr__(policy, "admitted_depths", (0, 2, 1, 3))

        with self.assertRaises(RecursionRouterError):
            route_recursion(
                route_candidate=route,
                child_request=child,
                need=need,
                policy=policy,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
