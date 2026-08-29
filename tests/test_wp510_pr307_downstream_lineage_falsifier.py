"""REVIEW_ONLY executable falsifier for F2-WP-510 PR #307.

The current PR307 positive fixture seals a WP507 UPTAKEN receipt whose downstream
reference/digest are only caller-supplied strings. No typed downstream artifact is
present whose producer lineage closes back to the exact WP508 re-entry CellInput.

WP510 claims one coherent Stage-5 causal path, so positive admission must fail closed
until that downstream evidence is resolved through an exact typed artifact/lineage
boundary. This review intentionally changes no WP510-owned production path.
"""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_gwt_causal_path import make_fixture, seal  # noqa: E402

from frankenstein2.gwt_causal_path import GwtCausalPathError  # noqa: E402


def test_pr307_rejects_positive_uptake_without_typed_downstream_lineage_closure():
    fx = make_fixture()
    receipt = fx["receipts"][0]
    bundle = fx["reentry_bundles"][0]

    assert receipt.uptake_status == "UPTAKEN"
    assert receipt.downstream_ref == "downstream:wp510"
    assert bundle.binding.downstream_ref == receipt.downstream_ref
    assert not hasattr(bundle, "downstream_output")

    with pytest.raises(GwtCausalPathError, match="downstream"):
        seal(fx)
