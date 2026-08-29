import hashlib
import unittest

from frankenstein2.context_compiler import (
    CHANNEL_EVIDENCE,
    ContextItem,
    ContextNeed,
    compile_context,
)


RENDERER_ID = "FIXTURE_IDENTITY_UTF8_RENDERER/v1"
TOKENIZER_ID = "FIXTURE_WHITESPACE_TOKENIZER/v1"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def render_fixture(payload: str) -> bytes:
    """Deterministic stand-in renderer used only by this negative-control test."""
    return payload.encode("utf-8")


def tokenize_fixture(rendered: bytes) -> tuple[str, ...]:
    """Deterministic stand-in tokenizer used only to create an independent cost witness."""
    return tuple(rendered.decode("utf-8").split())


class Wp306RendererTokenizerCostBindingFalsifier(unittest.TestCase):
    def test_selected_context_cannot_exceed_independently_measured_token_budget(self):
        """Preregistered desired invariant expected to FAIL against current WP306.

        The exact payload digest is known, and an independent deterministic renderer/tokenizer
        witnesses its concrete token cost. Current WP306 accepts a caller-supplied cost_units
        value without any renderer/tokenizer identity or measured-cost witness, so the item can
        be selected even when the independently measured payload cost exceeds max_cost_units.

        This is a REVIEW_ONLY discriminator. Failure demonstrates missing cost-witness binding;
        it does not imply that this fixture tokenizer is the production tokenizer or that
        repository component evidence is target-runtime evidence.
        """
        payload = " ".join(f"token-{index}" for index in range(64))
        rendered = render_fixture(payload)
        measured_token_count = len(tokenize_fixture(rendered))
        self.assertEqual(measured_token_count, 64)

        candidate = ContextItem.create(
            item_id="underdeclared-rendered-cost",
            channel=CHANNEL_EVIDENCE,
            payload_ref="fixture:wp306:underdeclared-rendered-cost",
            payload_sha256=sha256_text(payload),
            source_ref="fixture:wp306:source",
            source_sha256=sha256_text("fixture:wp306:source"),
            source_generation=1,
            source_classification="REVIEW_ONLY_COST_BINDING_FIXTURE",
            priority_bp=10_000,
            cost_units=1,
            required=True,
            provenance_refs=[f"renderer:{RENDERER_ID}", f"tokenizer:{TOKENIZER_ID}"],
            evidence_refs=["review:wp306:renderer-tokenizer-cost-binding"],
        )
        need = ContextNeed.create(
            context_id="ctx-wp306-cost-binding",
            task_id="task-wp306-cost-binding",
            task_generation=1,
            allowed_channels=[CHANNEL_EVIDENCE],
            required_channels=[CHANNEL_EVIDENCE],
            max_items=1,
            max_cost_units=1,
            evidence_refs=["review:wp306:budget-1"],
        )

        view = compile_context(need, [candidate])
        self.assertEqual(view.selected_count, 1)
        self.assertEqual(view.selected[0].item_id, candidate.item_id)
        self.assertEqual(view.selected_cost_units, 1)
        self.assertEqual(view.selected[0].payload_sha256, sha256_text(payload))

        # Desired fail-closed invariant: once concrete rendered/tokenized cost is independently
        # witnessed for this exact payload, a selected view must not exceed the declared budget.
        # Current WP306 cannot enforce this because no such witness participates in admission.
        self.assertLessEqual(
            measured_token_count,
            need.max_cost_units,
            (
                "WP306 selected an exact payload whose independently measured renderer/tokenizer "
                "cost exceeds max_cost_units because cost_units is caller-supplied and is not "
                "bound to a renderer/tokenizer cost witness"
            ),
        )


if __name__ == "__main__":
    unittest.main()
