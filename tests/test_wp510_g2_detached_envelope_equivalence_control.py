from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from test_gwt_causal_path import make_fixture, seal  # noqa: E402
from frankenstein2.gwt_workspace import BroadcastEnvelope  # noqa: E402


def _detached_copy(canonical):
    return BroadcastEnvelope(
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


def test_field_identical_detached_envelope_is_observationally_equivalent_at_wp510_boundary():
    fx = make_fixture()
    canonical = fx["broadcast"]
    detached = _detached_copy(canonical)

    assert detached is not canonical
    assert detached.as_dict() == canonical.as_dict()
    assert detached.sha256() == canonical.sha256()

    canonical_seal = seal(fx)
    detached_seal = seal(fx, broadcast=detached)

    assert detached_seal.as_dict() == canonical_seal.as_dict()
    assert detached_seal.sha256() == canonical_seal.sha256()
    assert detached_seal.path_status == "CONTRACT_SCOPE_CAUSAL_PATH_SEALED"
