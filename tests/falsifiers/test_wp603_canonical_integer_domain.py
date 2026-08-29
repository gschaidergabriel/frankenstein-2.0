from __future__ import annotations

import unittest

from frankenstein2.recursion_router import RecursionPolicy, RecursionRouterError


class WP603CanonicalIntegerDomainFalsifier(unittest.TestCase):
    """Candidate falsifier: constructor-valid WP603 integers must remain hashable/fail-closed."""

    def test_policy_generation_outside_json_integer_string_domain_is_rejected_by_wp603_boundary(self) -> None:
        # Python 3.12 normally limits decimal int conversion to 4300 digits. WP601 G2
        # already hardened the equivalent canonical-JSON boundary. WP603 currently
        # accepts this value in _generation(), so RecursionPolicy construction succeeds
        # but sha256()/canonical_json can leak a raw ValueError instead of rejecting the
        # object at the WP603 boundary.
        pathological_generation = 10 ** 5000

        try:
            policy = RecursionPolicy.create(
                policy_id="wp603-falsifier-policy",
                generation=pathological_generation,
                max_recursion_depth=1,
                admitted_depths=(0, 1),
                provenance_refs=("falsifier:wp603-canonical-int-domain",),
            )
        except RecursionRouterError:
            return

        with self.assertRaises(
            RecursionRouterError,
            msg=(
                "WP603 admitted a RecursionPolicy that cannot cross its own canonical JSON/hash boundary; "
                "generation should be rejected with RecursionRouterError before a raw serializer ValueError leaks"
            ),
        ):
            policy.sha256()


if __name__ == "__main__":
    unittest.main()
