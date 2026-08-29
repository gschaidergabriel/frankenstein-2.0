from __future__ import annotations

import sys
import unittest

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.native_child_binding import NativeChildBinding
from frankenstein2.native_child_abi import (
    ABI_VERSION,
    ChildResourceBudget,
    NativeChildRequest,
)


class WP601BudgetCanonicalizationFalsifier(unittest.TestCase):
    """REVIEW ONLY: probe whether WP601's admitted domain is always hashable."""

    def test_accepted_budget_can_exceed_python_json_integer_digit_limit(self) -> None:
        # CPython 3.12 normally protects int->decimal conversion with a finite
        # max_str_digits limit.  WP601 accepts arbitrary positive ints, so choose a
        # value just outside the current admitted interpreter serialization domain.
        max_digits = sys.get_int_max_str_digits()
        self.assertGreater(
            max_digits,
            0,
            "review discriminator requires the standard finite CPython int digit limit",
        )
        huge_work_units = 10 ** (max_digits + 1)

        parent = CausalIdentity(
            session_id="review-session",
            agent_id="review-parent",
            task_id="review-parent-task",
            turn_id="review-turn-1",
            causal_id="review-causal-parent",
            generation=1,
        )
        child = parent.derive(
            causal_id="review-causal-child",
            generation=2,
            agent_id="review-child",
            task_id="review-child-task",
            turn_id="review-turn-2",
        )
        binding = NativeChildBinding(
            workpackage_id="F2-WP-601",
            workpackage_generation=1,
            claim_id="F2-WP-601-G1-GPT56SOL-NATIVE-CHILD-ABI-20260829",
            parent=parent,
            invocation_id="review-invocation",
            tool_use_id="review-tool-use",
            delegation_id="review-delegation",
            child=child,
        )

        # Both constructors accept this object as valid WP601 state.
        budget = ChildResourceBudget(
            max_work_units=huge_work_units,
            max_duration_ms=1,
            max_output_bytes=0,
            max_nested_depth=0,
            max_tool_calls=0,
        )
        request = NativeChildRequest(
            request_id="review-child-request",
            request_generation=1,
            abi_version=ABI_VERSION,
            binding=binding,
            binding_id=binding.binding_id(),
            binding_sha256=binding.sha256(),
            child_runtime_class="review-runtime",
            payload_ref="payload:review",
            payload_sha256="a" * 64,
            input_refs=("input:review",),
            requested_capability_refs=(),
            resource_budget=budget,
        )

        # But the accepted request cannot fulfill its own canonical hash ABI on the
        # same admitted Python runtime: json.dumps must decimal-serialize the huge int.
        with self.assertRaisesRegex(ValueError, "Exceeds the limit"):
            request.sha256()


if __name__ == "__main__":
    unittest.main()
