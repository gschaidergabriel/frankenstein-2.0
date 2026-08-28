from __future__ import annotations

import hashlib
import json

from frankenstein2.emergent_retrieval import (
    AXIS_GOAL,
    AXIS_SEMANTIC,
    RetrievalCandidate,
    RetrievalNeed,
    RetrievalSignal,
    build_retrieval_plan,
)
from frankenstein2.memory_lifecycle import create_memory


FALSIFIER_ID = "F2-WP-301-F1-CROSS-AXIS-EVIDENCE-ALIASING-20260829"
BASE_SHA = "0562d5adf0ea80dc9c2f6a4cf75f19583e929420"
SOURCE_BLOB_SHA = "8ca0c51bf88a79701ad188b9ccb0d7859feea944"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    memory = create_memory(
        memory_id="m:falsifier:cross-axis-alias",
        payload_ref="payload:m:falsifier:cross-axis-alias",
        payload_sha256=_sha256("payload:m:falsifier:cross-axis-alias"),
        provenance_refs=("memory:evidence:independent",),
    )

    # Counterexample: two nominally independent relevance axes reuse the exact same
    # evidence reference. If overlap_count is purely axis-count based, this single
    # evidence item can satisfy min_overlap_axes=2.
    aliased_evidence = ("evidence:single-source-reused-across-axes",)
    candidate = RetrievalCandidate.create(
        memory=memory,
        signals=(
            RetrievalSignal.create(
                axis=AXIS_GOAL,
                score_bp=8_000,
                evidence_refs=aliased_evidence,
            ),
            RetrievalSignal.create(
                axis=AXIS_SEMANTIC,
                score_bp=8_000,
                evidence_refs=aliased_evidence,
            ),
        ),
        candidate_evidence_refs=("candidate:evidence:falsifier",),
    )
    need = RetrievalNeed.create(
        need_id="need:falsifier:cross-axis-alias",
        axis_weights_bp={AXIS_GOAL: 10_000, AXIS_SEMANTIC: 10_000},
        min_overlap_axes=2,
        limit=4,
        evidence_refs=("need:evidence:falsifier",),
    )

    plan = build_retrieval_plan(need, (candidate,))
    reproduced = (
        len(plan.selected) == 1
        and plan.selected[0].memory_id == memory.memory_id
        and plan.selected[0].overlap_count == 2
        and tuple(refs for _, refs in plan.selected[0].signal_evidence_refs)
        == (aliased_evidence, aliased_evidence)
    )

    result = {
        "schema": "FRANKENSTEIN2_FALSIFIER_RESULT/v1",
        "falsifier_id": FALSIFIER_ID,
        "tested_base_sha": BASE_SHA,
        "tested_source_blob_sha": SOURCE_BLOB_SHA,
        "claim_scope": "REVIEW_ONLY_CANDIDATE_FALSIFIER",
        "hypothesis": "multi-axis overlap reflects independently evidenced relevance dimensions",
        "counterhypothesis": "the same evidence reference can be relabeled across axes and satisfy min_overlap_axes",
        "status": "NEGATIVE_RESULT_REPRODUCED" if reproduced else "FALSIFIER_NOT_REPRODUCED",
        "selected": [item.memory_id for item in plan.selected],
        "overlap_count": plan.selected[0].overlap_count if plan.selected else None,
        "signal_evidence_refs": (
            [[axis, list(refs)] for axis, refs in plan.selected[0].signal_evidence_refs]
            if plan.selected
            else []
        ),
        "authority_note": "This is review-only source/component evidence. It grants no runtime, truth, effect, completion, physical GRID10, VPS, or whole-system credit.",
        "next_discriminator": "Decide whether exact cross-axis evidence aliasing is admissible semantics. If not, open an explicit WP301 successor-generation hardening claim and reject/discount aliased positive-axis evidence with regression coverage.",
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())
