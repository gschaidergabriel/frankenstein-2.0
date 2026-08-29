#!/usr/bin/env python3
"""Trigger-6 E4 falsifier for F2-WP-306 rendered-cost binding.

Research-only experiment. It does not modify product state and it does not grant runtime,
physical-host, effect, completion, training, or whole-system credit.

The experiment is intentionally bound to one exact context_compiler.py Git blob. It shows
that a caller can declare cost_units=1 for a payload that is much larger after dereference /
rendering, because the bounded ContextCompiler is reference-only by design. A separate
render/token witness can detect that mismatch without teaching the core compiler semantics.

The deterministic whitespace tokenizer below is a TEST TOKENIZER, not a production-model
tokenizer. Its purpose is to falsify the generic assumption that caller-declared cost_units
necessarily tracks a rendered token budget. Production admission must bind the exact model /
tokenizer / chat-template or renderer identity used for inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import frankenstein2.context_compiler as context_compiler
from frankenstein2.context_compiler import (
    CHANNEL_EVIDENCE,
    ContextItem,
    ContextNeed,
    compile_context,
)

SCHEMA = "F2_WP306_RENDERED_COST_WITNESS_E4_RESULT/v1"
EXPECTED_CONTEXT_COMPILER_GIT_BLOB_SHA1 = "edbfb96710376af01af88bf4453d660fdcf5d341"
RENDERER_ID = "F2_TEST_IDENTITY_CHAT_RENDERER/v1"
TOKENIZER_ID = "F2_TEST_WHITESPACE_TOKENIZER/v1_NOT_PRODUCTION"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def render_payload(payload: str) -> str:
    # Deliberately simple deterministic stand-in for a production chat renderer.
    # The renderer identity is part of the witness so this cannot be confused with
    # an actual model chat template.
    return f"<|evidence|>\n{payload}\n<|assistant|>\n"


def test_tokenize(rendered: str) -> tuple[str, ...]:
    # Deterministic TEST tokenizer only. Production integration must replace this
    # with the exact tokenizer used by the selected inference engine/model.
    return tuple(rendered.split())


def make_witness(*, selected: Any, payload: str) -> dict[str, Any]:
    payload_bytes = payload.encode("utf-8")
    observed_payload_sha = sha256_bytes(payload_bytes)
    if observed_payload_sha != selected.payload_sha256:
        raise AssertionError("payload digest changed after ContextView selection")

    rendered = render_payload(payload)
    rendered_bytes = rendered.encode("utf-8")
    tokens = test_tokenize(rendered)
    witness_core = {
        "payload_ref": selected.payload_ref,
        "payload_sha256": selected.payload_sha256,
        "renderer_id": RENDERER_ID,
        "renderer_identity_sha256": sha256_bytes(RENDERER_ID.encode("utf-8")),
        "tokenizer_id": TOKENIZER_ID,
        "tokenizer_identity_sha256": sha256_bytes(TOKENIZER_ID.encode("utf-8")),
        "rendered_sha256": sha256_bytes(rendered_bytes),
        "rendered_utf8_bytes": len(rendered_bytes),
        "rendered_test_tokens": len(tokens),
        "declared_cost_units": selected.cost_units,
    }
    return {
        **witness_core,
        "witness_sha256": sha256_bytes(canonical_json(witness_core).encode("utf-8")),
    }


def run() -> dict[str, Any]:
    source_path = Path(context_compiler.__file__).resolve()
    source_bytes = source_path.read_bytes()
    actual_blob_sha1 = git_blob_sha1(source_bytes)
    if actual_blob_sha1 != EXPECTED_CONTEXT_COMPILER_GIT_BLOB_SHA1:
        raise AssertionError(
            "exact-source fence failed: context_compiler.py blob changed "
            f"expected={EXPECTED_CONTEXT_COMPILER_GIT_BLOB_SHA1} actual={actual_blob_sha1}"
        )

    # 16,384 lexical units are intentionally hidden behind caller-declared cost_units=1.
    payload = ("alpha beta gamma delta " * 4096).rstrip()
    payload_ref = "fixture:wp306:large-rendered-payload"
    payload_sha256 = sha256_bytes(payload.encode("utf-8"))

    item = ContextItem.create(
        item_id="cheap-declared-large-rendered",
        channel=CHANNEL_EVIDENCE,
        payload_ref=payload_ref,
        payload_sha256=payload_sha256,
        source_ref="fixture:wp306:e4",
        source_sha256=sha256_bytes(b"fixture:wp306:e4"),
        source_generation=1,
        source_classification="E4_TEST_FIXTURE_NOT_WORLD_FACT",
        priority_bp=10_000,
        cost_units=1,
        required=True,
        provenance_refs=("trigger6:wp306:e4",),
        evidence_refs=("claim:E4_F2_ABLATION_RENDERED_COST_WITNESS_MISMATCH",),
    )
    need = ContextNeed.create(
        context_id="wp306-e4-rendered-cost",
        task_id="wp306-e4",
        task_generation=1,
        allowed_channels=(CHANNEL_EVIDENCE,),
        required_channels=(CHANNEL_EVIDENCE,),
        max_items=1,
        max_cost_units=1,
        evidence_refs=("trigger6:wp306:e4",),
    )

    view = compile_context(need, (item,))
    assert view.selected_count == 1
    assert view.selected_cost_units == 1
    selected = view.selected[0]
    witness = make_witness(selected=selected, payload=payload)

    mismatch = (
        witness["declared_cost_units"] <= need.max_cost_units
        and witness["rendered_utf8_bytes"] > need.max_cost_units
        and witness["rendered_test_tokens"] > need.max_cost_units
    )
    if not mismatch:
        raise AssertionError("falsifier failed to construct a rendered-cost mismatch")

    # Fail-closed digest control: changing dereferenced content after selection must be caught.
    mutation_rejected = False
    try:
        make_witness(selected=selected, payload=payload + " MUTATED")
    except AssertionError:
        mutation_rejected = True
    if not mutation_rejected:
        raise AssertionError("post-selection payload mutation was not rejected")

    result = {
        "schema": SCHEMA,
        "status": "FALSIFIER_REPRODUCED",
        "evidence_scope": "EXACT_SOURCE_REPOSITORY_HOSTED_E4_RESEARCH_ABLATION_NOT_PRODUCT_ACCEPTANCE",
        "github_sha": os.environ.get("GITHUB_SHA", "LOCAL_OR_UNSET"),
        "source_binding": {
            "context_compiler_path": str(source_path),
            "expected_git_blob_sha1": EXPECTED_CONTEXT_COMPILER_GIT_BLOB_SHA1,
            "observed_git_blob_sha1": actual_blob_sha1,
            "source_sha256": sha256_bytes(source_bytes),
        },
        "context_view": {
            "sha256": view.sha256(),
            "selected_count": view.selected_count,
            "selected_cost_units": view.selected_cost_units,
            "max_cost_units": need.max_cost_units,
            "selected_item_id": selected.item_id,
            "payload_ref": selected.payload_ref,
            "payload_sha256": selected.payload_sha256,
        },
        "rendered_cost_witness": witness,
        "falsified_assumption": "CALLER_DECLARED_COST_UNITS_IMPLY_RENDERED_BYTE_OR_TOKEN_BOUNDEDNESS",
        "mismatch_reproduced": mismatch,
        "post_selection_payload_mutation_rejected": mutation_rejected,
        "production_boundary": {
            "test_tokenizer_is_production_tokenizer": False,
            "required_next_binding": "EXACT_RENDERER_OR_CHAT_TEMPLATE_IDENTITY_PLUS_EXACT_PRODUCTION_TOKENIZER_MODEL_RUNTIME_IDENTITY",
            "runtime_credit": 0,
            "physical_host_credit": 0,
            "whole_system_credit": 0,
        },
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    result = run()
    text = json.dumps(result, sort_keys=True, indent=2)
    print(text)
    if args.json_out:
        args.json_out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
