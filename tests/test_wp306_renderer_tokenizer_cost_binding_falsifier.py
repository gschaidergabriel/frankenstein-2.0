import hashlib
import unittest

from frankenstein2.context_compiler import (
    CHANNEL_EVIDENCE,
    ContextCompilerError,
    ContextCostWitness,
    ContextItem,
    ContextNeed,
    compile_context,
)


RENDERER_ID = "FIXTURE_IDENTITY_UTF8_RENDERER"
RENDERER_VERSION = "1"
TOKENIZER_ID = "FIXTURE_WHITESPACE_TOKENIZER"
TOKENIZER_VERSION = "1"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_item(payload: str, *, declared_cost: int = 1) -> ContextItem:
    return ContextItem.create(
        item_id="renderer-tokenizer-cost-binding",
        channel=CHANNEL_EVIDENCE,
        payload_ref="fixture:wp306:renderer-tokenizer-cost-binding",
        payload_sha256=sha256_text(payload),
        source_ref="fixture:wp306:source",
        source_sha256=sha256_text("fixture:wp306:source"),
        source_generation=1,
        source_classification="REVIEW_ONLY_COST_BINDING_FIXTURE",
        priority_bp=10_000,
        cost_units=declared_cost,
        required=True,
        provenance_refs=["fixture:wp306:item-provenance"],
        evidence_refs=["review:wp306:renderer-tokenizer-cost-binding"],
    )


def make_witness(item: ContextItem, *, measured_cost: int, generation: int = 1) -> ContextCostWitness:
    return ContextCostWitness.create(
        payload_sha256=item.payload_sha256,
        renderer_id=RENDERER_ID,
        renderer_version=RENDERER_VERSION,
        tokenizer_id=TOKENIZER_ID,
        tokenizer_version=TOKENIZER_VERSION,
        measured_cost_units=measured_cost,
        generation=generation,
        measurement_ref=f"fixture:wp306:measurement:g{generation}",
        provenance_refs=["fixture:wp306:measurement-provenance"],
    )


def need() -> ContextNeed:
    return ContextNeed.create(
        context_id="ctx-wp306-cost-binding",
        task_id="task-wp306-cost-binding",
        task_generation=1,
        allowed_channels=[CHANNEL_EVIDENCE],
        required_channels=[CHANNEL_EVIDENCE],
        max_items=1,
        max_cost_units=1,
        evidence_refs=["review:wp306:budget-1"],
    )


class Wp306RendererTokenizerCostBindingRegression(unittest.TestCase):
    def test_pr519_underdeclared_concrete_cost_now_fails_closed(self):
        payload = " ".join(f"token-{index}" for index in range(64))
        item = make_item(payload, declared_cost=1)
        measured_token_count = len(payload.encode("utf-8").decode("utf-8").split())
        self.assertEqual(measured_token_count, 64)
        cost_witness = make_witness(item, measured_cost=measured_token_count)

        with self.assertRaisesRegex(
            ContextCompilerError,
            "cost witness does not match declared cost_units",
        ):
            compile_context(need(), [item], cost_witnesses=[cost_witness])

    def test_missing_cost_witness_fails_closed(self):
        item = make_item("one", declared_cost=1)
        with self.assertRaisesRegex(ContextCompilerError, "missing cost witness"):
            compile_context(need(), [item])

    def test_wrong_payload_witness_fails_closed(self):
        item = make_item("one", declared_cost=1)
        other = make_item("different", declared_cost=1)
        wrong = make_witness(other, measured_cost=1)
        with self.assertRaisesRegex(ContextCompilerError, "unbound context cost witness"):
            compile_context(need(), [item], cost_witnesses=[wrong])

    def test_duplicate_payload_witnesses_fail_closed(self):
        item = make_item("one", declared_cost=1)
        first = make_witness(item, measured_cost=1, generation=1)
        second = make_witness(item, measured_cost=1, generation=2)
        with self.assertRaisesRegex(ContextCompilerError, "duplicate context cost witness"):
            compile_context(need(), [item], cost_witnesses=[first, second])

    def test_selected_view_carries_exact_cost_witness_identity(self):
        item = make_item("one", declared_cost=1)
        cost_witness = make_witness(item, measured_cost=1)
        view = compile_context(need(), [item], cost_witnesses=[cost_witness])
        self.assertEqual(view.selected_count, 1)
        selected = view.selected[0]
        self.assertEqual(selected.cost_units, 1)
        self.assertEqual(selected.cost_witness_sha256, cost_witness.sha256())
        self.assertEqual(selected.cost_renderer_id, RENDERER_ID)
        self.assertEqual(selected.cost_renderer_version, RENDERER_VERSION)
        self.assertEqual(selected.cost_tokenizer_id, TOKENIZER_ID)
        self.assertEqual(selected.cost_tokenizer_version, TOKENIZER_VERSION)
        self.assertEqual(selected.cost_measurement_ref, cost_witness.measurement_ref)
        self.assertEqual(selected.cost_witness_generation, 1)

    def test_cost_witness_subtype_is_rejected_at_public_boundary(self):
        item = make_item("one", declared_cost=1)

        class ForgedWitness(ContextCostWitness):
            pass

        canonical = make_witness(item, measured_cost=1)
        forged = ForgedWitness(**canonical.as_dict())
        with self.assertRaisesRegex(ContextCompilerError, "only exact ContextCostWitness"):
            compile_context(need(), [item], cost_witnesses=[forged])


if __name__ == "__main__":
    unittest.main()
