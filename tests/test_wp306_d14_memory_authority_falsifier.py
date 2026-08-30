from __future__ import annotations

import hashlib
import unittest

from frankenstein2.context_compiler import (
    CHANNEL_AUTHORITY,
    CONTEXT_COST_WITNESS_SCHEMA,
    ContextAuthorityWitness,
    ContextCompilerError,
    ContextCostWitness,
    ContextItem,
    ContextNeed,
    compile_context,
)


SOURCE_BLOB = "a8cf88735e0ba6d01cdd3a1e9440a860f8e3eeea"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def authority_item(*, item_id: str, classification: str) -> ContextItem:
    return ContextItem.create(
        item_id=item_id,
        channel=CHANNEL_AUTHORITY,
        payload_ref=f"payload:{item_id}",
        payload_sha256=sha256(f"payload:{item_id}"),
        source_ref=f"source:{item_id}",
        source_sha256=sha256(f"source:{item_id}"),
        source_generation=7,
        source_classification=classification,
        priority_bp=10_000,
        cost_units=1,
        required=True,
        provenance_refs=(f"provenance:{item_id}",),
        evidence_refs=(f"evidence:{item_id}",),
    )


def need() -> ContextNeed:
    return ContextNeed.create(
        context_id="ctx-d14",
        task_id="task-d14",
        task_generation=1,
        allowed_channels=(CHANNEL_AUTHORITY,),
        required_channels=(CHANNEL_AUTHORITY,),
        max_items=1,
        max_cost_units=1,
        evidence_refs=("review:voicemem-vm-g10",),
    )


def cost_witness(item: ContextItem) -> ContextCostWitness:
    return ContextCostWitness(
        schema=CONTEXT_COST_WITNESS_SCHEMA,
        payload_sha256=item.payload_sha256,
        renderer_id="review-renderer",
        renderer_version="1",
        tokenizer_id="review-tokenizer",
        tokenizer_version="1",
        measured_cost_units=1,
        generation=1,
        measurement_ref=f"measurement:{item.item_id}:1",
        provenance_refs=("review:cost-witness",),
    )


class WP306D14MemoryAuthorityFalsifier(unittest.TestCase):
    """REVIEW_ONLY candidate falsifier and repair characterization for VM-G10 / D14."""

    def test_retrieved_user_memory_cannot_self_promote_to_authority(self) -> None:
        item = authority_item(
            item_id="memory-1",
            classification="RETRIEVED_USER_MEMORY_UNTRUSTED_DATA",
        )

        with self.assertRaisesRegex(ContextCompilerError, "missing authority witness"):
            compile_context(need(), (item,), cost_witnesses=(cost_witness(item),))

    def test_separate_exact_authority_witness_preserves_legitimate_channel(self) -> None:
        item = authority_item(
            item_id="policy-1",
            classification="CANONICAL_POLICY_REFERENCE",
        )
        authority = ContextAuthorityWitness.create(
            item=item,
            authority_class="POLICY",
            authority_ref="authority-registry:policy-1",
            scope_ref="scope:context-construction",
            issuer_ref="deterministic-authority-resolver:v1",
            generation=4,
            provenance_refs=("canonical-authority:receipt-1",),
        )

        view = compile_context(
            need(),
            (item,),
            cost_witnesses=(cost_witness(item),),
            authority_witnesses=(authority,),
        )

        self.assertEqual(view.selected_count, 1)
        selected = view.selected[0]
        self.assertEqual(selected.channel, CHANNEL_AUTHORITY)
        self.assertEqual(selected.authority_witness_sha256, authority.sha256())
        self.assertEqual(selected.authority_class, "POLICY")
        self.assertEqual(selected.authority_issuer_ref, "deterministic-authority-resolver:v1")

    def test_authority_witness_cannot_be_reused_for_different_item(self) -> None:
        admitted = authority_item(
            item_id="policy-1",
            classification="CANONICAL_POLICY_REFERENCE",
        )
        forged_target = authority_item(
            item_id="memory-2",
            classification="RETRIEVED_USER_MEMORY_UNTRUSTED_DATA",
        )
        witness = ContextAuthorityWitness.create(
            item=admitted,
            authority_class="POLICY",
            authority_ref="authority-registry:policy-1",
            scope_ref="scope:context-construction",
            issuer_ref="deterministic-authority-resolver:v1",
            generation=4,
            provenance_refs=("canonical-authority:receipt-1",),
        )

        with self.assertRaisesRegex(ContextCompilerError, "unbound context authority witness"):
            compile_context(
                need(),
                (forged_target,),
                cost_witnesses=(cost_witness(forged_target),),
                authority_witnesses=(witness,),
            )


if __name__ == "__main__":
    unittest.main()
