#!/usr/bin/env python3
"""Closure guard for the WP900 -> WP510 consumer-boundary falsifier.

Success means the formerly reproduced counterexample is now rejected: a directly
constructed/non-factory GwtCausalPathSeal cannot contribute to a WholePersistentLoopSeal.

This script grants no runtime, GWT, J-Space, effect, completion, or whole-system credit.
"""
from __future__ import annotations

from dataclasses import replace

from test_whole_persistent_loop import fixture_components

from frankenstein2.whole_persistent_loop import (
    WholePersistentLoopError,
    seal_whole_persistent_loop,
)


def main() -> None:
    (
        checkpoint,
        frame,
        contract,
        plan,
        gwt,
        gwt_evidence,
        decision,
        outcome,
        next_checkpoint,
    ) = fixture_components()

    if getattr(gwt, "_factory_seal", None) is None:
        raise SystemExit("FALSIFIER_INVALID: canonical fixture lacks WP510 factory seal")
    forged = replace(gwt, _factory_seal=None)

    try:
        seal_whole_persistent_loop(
            seal_id="wp900-review-forged-gwt",
            generation=0,
            current_checkpoint=checkpoint,
            frame=frame,
            contract=contract,
            plan=plan,
            gwt_seal=forged,
            gwt_evidence=gwt_evidence,
            decision=decision,
            outcome=outcome,
            next_checkpoint=next_checkpoint,
            provenance_refs=("review:wp900:gwt-factory-boundary",),
        )
    except WholePersistentLoopError as exc:
        if "deterministic WP510 factory" not in str(exc):
            raise SystemExit(f"FALSIFIER_WRONG_REJECTION: {exc}") from exc
        print("FALSIFIER_CLOSED: WP900 rejected a non-WP510-factory GwtCausalPathSeal")
        print(f"rejection={exc}")
        return

    raise SystemExit(
        "FALSIFIER_STILL_OPEN: WP900 admitted a non-WP510-factory GwtCausalPathSeal"
    )


if __name__ == "__main__":
    main()
