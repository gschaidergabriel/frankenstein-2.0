from __future__ import annotations

import hashlib
import unittest

from frankenstein2.context_compiler import (
    CHANNEL_AUTHORITY,
    CONTEXT_COST_WITNESS_SCHEMA,
    ContextCompilerError,
    ContextCostWitness,
    ContextItem,
    ContextNeed,
    compile_context,
)


SOURCE_BLOB = "a8cf88735e0ba6d01cdd3a1e9440a860f8e3eeea"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class WP306D14MemoryAuthorityFalsifier(unittest.TestCase):
    """REVIEW_ONLY candidate falsifier for VM-G10 / D14.

    Retrieved user/external memory must not gain AUTHORITY merely because a caller
    renders/reinjects it through the context compiler. The current compiler never
    reads payload bytes, so this fixture uses only inert reference metadata.
    """

    def test_retrieved_user_memory_cannot_self_promote_to_authority(self) -> None:
        payload_digest = sha256("inert retrieved user memory")
        source_digest = sha256("memory-record-1")

        item = ContextItem.create(
            item_id="memory-1",
            channel=CHANNEL_AUTHORITY,
            payload_ref="memory:retrieved:1",
            payload_sha256=payload_digest,
            source_ref="memory-record:1",
            source_sha256=source_digest,
            source_generation=7,
            source_classification="RETRIEVED_USER_MEMORY_UNTRUSTED_DATA",
            priority_bp=10_000,
            cost_units=1,
            required=True,
            provenance_refs=("provenance:memory-write:1",),
            evidence_refs=("retrieval-plan:1",),
        )
        need = ContextNeed.create(
            context_id="ctx-d14",
            task_id="task-d14",
            task_generation=1,
            allowed_channels=(CHANNEL_AUTHORITY,),
            required_channels=(CHANNEL_AUTHORITY,),
            max_items=1,
            max_cost_units=1,
            evidence_refs=("review:voicemem-vm-g10",),
        )
        witness = ContextCostWitness(
            schema=CONTEXT_COST_WITNESS_SCHEMA,
            payload_sha256=payload_digest,
            renderer_id="review-renderer",
            renderer_version="1",
            tokenizer_id="review-tokenizer",
            tokenizer_version="1",
            measured_cost_units=1,
            generation=1,
            measurement_ref="measurement:d14:1",
            provenance_refs=("review:cost-witness",),
        )

        try:
            view = compile_context(need, (item,), cost_witnesses=(witness,))
        except ContextCompilerError:
            return

        self.fail(
            "D14 reproduced: retrieved user/external memory was selected on the "
            f"AUTHORITY channel without an independent authority-admission witness; "
            f"source_blob={SOURCE_BLOB} selected={view.selected!r}"
        )


if __name__ == "__main__":
    unittest.main()
