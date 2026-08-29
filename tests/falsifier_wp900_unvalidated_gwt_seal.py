#!/usr/bin/env python3
"""REVIEW_ONLY falsifier for the WP900 -> WP510 consumer boundary.

Success means the current WP900 implementation reproduced the counterexample:
a directly constructed (non-WP510-factory) GwtCausalPathSeal was admitted into a
WholePersistentLoopSeal. Failure means the counterexample did not reproduce or the
fixture itself was invalid.

This script grants no runtime, GWT, J-Space, effect, completion, or whole-system credit.
"""
from __future__ import annotations

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
        decision,
        outcome,
        next_checkpoint,
    ) = fixture_components()

    # fixture_components deliberately uses a directly constructed GwtCausalPathSeal;
    # current WP510 exposes validate_gwt_causal_path_seal() specifically so consumers
    # can reject values that were not produced/rebuilt from the deterministic WP510
    # source-evidence chain.
    if getattr(gwt, "_factory_seal", None) is not None:
        raise SystemExit("FALSIFIER_INVALID: fixture unexpectedly carries WP510 factory seal")

    try:
        sealed = seal_whole_persistent_loop(
            seal_id="wp900-review-forged-gwt",
            generation=0,
            current_checkpoint=checkpoint,
            frame=frame,
            contract=contract,
            plan=plan,
            gwt_seal=gwt,
            decision=decision,
            outcome=outcome,
            next_checkpoint=next_checkpoint,
            provenance_refs=("review:wp900:gwt-factory-boundary",),
        )
    except WholePersistentLoopError as exc:
        raise SystemExit(
            "FALSIFIER_NOT_REPRODUCED: WP900 rejected the non-factory GWT seal: "
            f"{exc}"
        ) from exc

    if sealed.gwt_seal_sha256 != gwt.sha256():
        raise SystemExit("FALSIFIER_INVALID: accepted seal did not bind supplied GWT digest")

    print("FALSIFIER_REPRODUCED: WP900 admitted a non-WP510-factory GwtCausalPathSeal")
    print(f"gwt_path_status={gwt.path_status}")
    print(f"gwt_causal_status={gwt.causal_status}")
    print(f"whole_loop_seal_sha256={sealed.sha256()}")


if __name__ == "__main__":
    main()
