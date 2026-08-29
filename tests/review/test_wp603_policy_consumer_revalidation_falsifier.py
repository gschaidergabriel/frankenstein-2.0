from __future__ import annotations

import unittest

from frankenstein2.direct_delegate_router import DELEGATE_BUILD
from frankenstein2.recursion_router import RecursionNeed, RecursionRouterError, route_recursion
from test_recursion_router import make_child_request, make_policy, make_route


class WP603PolicyConsumerRevalidationFalsifier(unittest.TestCase):
    def test_post_init_policy_mutation_is_rejected_at_consumer_boundary(self) -> None:
        route = make_route(selected=DELEGATE_BUILD)
        child = make_child_request(max_nested_depth=3)
        need = RecursionNeed.create(
            route_candidate=route,
            child_request=child,
            requested_depth=2,
            generation=1,
            provenance_refs=("review:wp603-policy-post-init-mutation",),
        )
        policy = make_policy(max_depth=3, admitted_depths=(0, 1, 2, 3))

        # A frozen dataclass is not itself a trust boundary.  This bypasses
        # RecursionPolicy.__post_init__ while leaving the object concrete-typed.
        # A fail-closed consumer must reconstruct/revalidate before using fields.
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
