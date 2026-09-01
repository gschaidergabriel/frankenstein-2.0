from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_gwt_causal_path import make_fixture, seal  # noqa: E402
from frankenstein2.gwt_causal_path import GwtCausalPathError  # noqa: E402
from frankenstein2.gwt_workspace import BroadcastEnvelope  # noqa: E402


def test_detached_direct_envelope_cannot_survive_positive_wp510_seal():
    fx = make_fixture()
    canonical = fx["broadcast"]
    detached = BroadcastEnvelope(
        broadcast_id=canonical.broadcast_id,
        cycle_id=canonical.cycle_id,
        generation=canonical.generation,
        selection_id=canonical.selection_id,
        selection_generation=canonical.selection_generation,
        selection_sha256=canonical.selection_sha256,
        plan_id=canonical.plan_id,
        plan_generation=canonical.plan_generation,
        plan_sha256=canonical.plan_sha256,
        recipient_cell_ids=canonical.recipient_cell_ids,
        candidate_ids=canonical.candidate_ids,
        candidate_payload_refs=canonical.candidate_payload_refs,
    )
    assert detached.as_dict() == canonical.as_dict()
    assert detached is not canonical

    with pytest.raises(
        GwtCausalPathError,
        match=r"broadcast.*(builder|lineage)|detached",
    ):
        seal(fx, broadcast=detached)
