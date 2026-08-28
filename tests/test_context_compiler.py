import hashlib
import json
import unittest

from frankenstein2.context_compiler import (
    CHANNEL_AUTHORITY,
    CHANNEL_COUNTEREVIDENCE,
    CHANNEL_EVIDENCE,
    CHANNEL_GOAL,
    CHANNEL_RETRIEVAL_REFERENCE,
    CHANNEL_STATE,
    ContextCompilerError,
    ContextItem,
    ContextNeed,
    VIEW_CLASSIFICATION,
    compile_context,
)


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def item(item_id, channel, priority, cost, *, required=False, classification="CALLER_LABEL"):
    return ContextItem.create(
        item_id=item_id,
        channel=channel,
        payload_ref=f"payload:{item_id}",
        payload_sha256=h(f"payload:{item_id}"),
        source_ref=f"source:{item_id}",
        source_sha256=h(f"source:{item_id}"),
        source_generation=3,
        source_classification=classification,
        priority_bp=priority,
        cost_units=cost,
        required=required,
        provenance_refs=[f"prov:{item_id}"],
        evidence_refs=[f"evidence:{item_id}"],
    )


def need(*, max_items=4, max_cost=10, allowed=None, required_channels=()):
    if allowed is None:
        allowed = [CHANNEL_STATE, CHANNEL_GOAL, CHANNEL_EVIDENCE, CHANNEL_COUNTEREVIDENCE]
    return ContextNeed.create(
        context_id="ctx-1",
        task_id="task-1",
        task_generation=7,
        allowed_channels=allowed,
        required_channels=required_channels,
        max_items=max_items,
        max_cost_units=max_cost,
        evidence_refs=["need:evidence"],
    )


class ContextCompilerTests(unittest.TestCase):
    def test_compilation_is_deterministic_and_input_order_independent(self):
        n = need(max_items=3, max_cost=7, required_channels=[CHANNEL_STATE])
        a = item("a", CHANNEL_STATE, 100, 2, required=True, classification="OBSERVED_EVIDENCE")
        b = item("b", CHANNEL_EVIDENCE, 9000, 3)
        c = item("c", CHANNEL_COUNTEREVIDENCE, 8000, 2)
        view1 = compile_context(n, [a, b, c])
        view2 = compile_context(n, [c, a, b])
        self.assertEqual(view1.sha256(), view2.sha256())
        self.assertEqual([x.item_id for x in view1.selected], ["a", "b", "c"])
        self.assertEqual(view1.classification, VIEW_CLASSIFICATION)

    def test_required_item_over_budget_fails_closed(self):
        n = need(max_cost=1)
        with self.assertRaisesRegex(ContextCompilerError, "required context items exceed"):
            compile_context(n, [item("must", CHANNEL_STATE, 100, 2, required=True)])

    def test_required_item_in_disallowed_channel_fails_closed(self):
        n = need(allowed=[CHANNEL_STATE])
        with self.assertRaisesRegex(ContextCompilerError, "disallowed channel"):
            compile_context(n, [item("must", CHANNEL_AUTHORITY, 100, 1, required=True)])

    def test_required_channel_is_reserved_before_optional_priority(self):
        n = need(max_items=1, max_cost=2, required_channels=[CHANNEL_EVIDENCE])
        view = compile_context(
            n,
            [
                item("state", CHANNEL_STATE, 9000, 1),
                item("evidence", CHANNEL_EVIDENCE, 100, 2),
            ],
        )
        self.assertEqual([x.item_id for x in view.selected], ["evidence"])
        self.assertEqual(view.selected[0].selection_reason, "REQUIRED_CHANNEL")

    def test_required_channel_without_candidate_fails_closed(self):
        n = need(required_channels=[CHANNEL_EVIDENCE])
        with self.assertRaisesRegex(ContextCompilerError, "required channel has no candidate"):
            compile_context(n, [item("state", CHANNEL_STATE, 9000, 1)])

    def test_optional_oversized_item_does_not_block_lower_priority_item_that_fits(self):
        n = need(max_items=2, max_cost=3)
        view = compile_context(
            n,
            [
                item("big", CHANNEL_EVIDENCE, 9000, 4),
                item("fit", CHANNEL_GOAL, 8000, 3),
            ],
        )
        self.assertEqual([x.item_id for x in view.selected], ["fit"])
        reasons = {x.item_id: x.omission_reason for x in view.omitted}
        self.assertEqual(reasons["big"], "COST_LIMIT")

    def test_caller_classification_is_preserved_not_relabelled(self):
        label = "RETRIEVAL_REFERENCE_CANDIDATE_NOT_TRUTH"
        n = need(allowed=[CHANNEL_RETRIEVAL_REFERENCE], max_cost=2)
        view = compile_context(
            n,
            [item("retrieved", CHANNEL_RETRIEVAL_REFERENCE, 5000, 1, classification=label)],
        )
        self.assertEqual(view.selected[0].source_classification, label)

    def test_disallowed_optional_item_is_omitted_without_payload_exposure(self):
        n = need(allowed=[CHANNEL_STATE], max_cost=2)
        hidden = item("hidden", CHANNEL_AUTHORITY, 9999, 1)
        view = compile_context(n, [item("state", CHANNEL_STATE, 1, 1), hidden])
        self.assertEqual([x.item_id for x in view.selected], ["state"])
        self.assertEqual(view.omitted[0].item_id, "hidden")
        rendered = view.canonical_json()
        self.assertNotIn("payload:hidden", rendered)

    def test_duplicate_item_identity_is_rejected(self):
        n = need()
        same = item("dup", CHANNEL_STATE, 10, 1)
        with self.assertRaisesRegex(ContextCompilerError, "duplicate context item_id"):
            compile_context(n, [same, same])

    def test_invalid_digest_and_non_boolean_required_are_rejected(self):
        with self.assertRaisesRegex(ContextCompilerError, "payload_sha256"):
            ContextItem.create(
                item_id="x",
                channel=CHANNEL_STATE,
                payload_ref="p",
                payload_sha256="ABC",
                source_ref="s",
                source_sha256=h("s"),
                source_generation=1,
                source_classification="UNKNOWN",
                priority_bp=1,
                cost_units=1,
                required=False,
                provenance_refs=["p1"],
                evidence_refs=["e1"],
            )
        with self.assertRaisesRegex(ContextCompilerError, "required must be a boolean"):
            ContextItem(
                schema="FRANKENSTEIN2_CONTEXT_ITEM/v1",
                item_id="x",
                channel=CHANNEL_STATE,
                payload_ref="p",
                payload_sha256=h("p"),
                source_ref="s",
                source_sha256=h("s"),
                source_generation=1,
                source_classification="UNKNOWN",
                priority_bp=1,
                cost_units=1,
                required=1,
                provenance_refs=("p1",),
                evidence_refs=("e1",),
            )

    def test_need_requires_required_channels_to_be_allowed(self):
        with self.assertRaisesRegex(ContextCompilerError, "subset"):
            need(allowed=[CHANNEL_STATE], required_channels=[CHANNEL_EVIDENCE])

    def test_view_is_reference_only_and_hash_stable(self):
        n = need(max_items=1, max_cost=1)
        source = item("x", CHANNEL_STATE, 1, 1, classification="UNKNOWN")
        view = compile_context(n, [source])
        data = json.loads(view.canonical_json())
        selected = data["selected"][0]
        self.assertEqual(selected["payload_ref"], "payload:x")
        self.assertEqual(selected["payload_sha256"], h("payload:x"))
        self.assertNotIn("payload", selected)
        self.assertEqual(view.sha256(), hashlib.sha256(view.canonical_json().encode()).hexdigest())


if __name__ == "__main__":
    unittest.main()
