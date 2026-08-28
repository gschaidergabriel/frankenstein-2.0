from __future__ import annotations

import hashlib
import unittest

from frankenstein2.context_compiler import (
    CHANNEL_EVIDENCE,
    ContextCompilerError,
    ContextItem,
    ContextNeed,
    compile_context,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _item(source_generation: int) -> ContextItem:
    return ContextItem.create(
        item_id="item:generation-boundary",
        channel=CHANNEL_EVIDENCE,
        payload_ref="payload:ref",
        payload_sha256=_sha("payload"),
        source_ref="epistemic:r0",
        source_sha256=_sha("wp207-record-identity"),
        source_generation=source_generation,
        source_classification="UNKNOWN_NOT_FILLED_BY_INFERENCE_OR_RETRIEVAL",
        priority_bp=5000,
        cost_units=1,
        required=False,
        provenance_refs=("prov:wp207",),
        evidence_refs=("evidence:wp207-record",),
    )


def _need() -> ContextNeed:
    return ContextNeed.create(
        context_id="context:generation-boundary",
        task_id="task:generation-boundary",
        task_generation=1,
        allowed_channels=(CHANNEL_EVIDENCE,),
        required_channels=(CHANNEL_EVIDENCE,),
        max_items=1,
        max_cost_units=1,
        evidence_refs=("policy:generation-boundary",),
    )


class ContextCompilerGenerationZeroTests(unittest.TestCase):
    def test_source_generation_zero_is_admitted_and_preserved(self) -> None:
        item = _item(0)
        self.assertEqual(item.source_generation, 0)

        view = compile_context(_need(), (item,))

        self.assertEqual(view.selected_count, 1)
        self.assertEqual(view.selected[0].source_generation, 0)
        self.assertEqual(view.selected[0].source_sha256, item.source_sha256)
        self.assertEqual(view.selected[0].source_classification, item.source_classification)

    def test_negative_source_generation_still_fails_closed(self) -> None:
        with self.assertRaisesRegex(ContextCompilerError, r"source_generation must be an integer in \[0,"):
            _item(-1)

    def test_boolean_source_generation_still_fails_closed(self) -> None:
        with self.assertRaisesRegex(ContextCompilerError, r"source_generation must be an integer in \[0,"):
            _item(True)

    def test_maximum_source_generation_boundary_remains_admitted(self) -> None:
        item = _item(2_147_483_647)
        self.assertEqual(item.source_generation, 2_147_483_647)

    def test_source_generation_overflow_still_fails_closed(self) -> None:
        with self.assertRaisesRegex(ContextCompilerError, r"source_generation must be an integer in \[0,"):
            _item(2_147_483_648)


if __name__ == "__main__":
    unittest.main()
