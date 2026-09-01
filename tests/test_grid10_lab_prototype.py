import importlib.util
import sys
from pathlib import Path

import pytest

MODULE = Path(__file__).parents[1] / "research" / "grid10_lab" / "grid10_fabric_lab.py"
spec = importlib.util.spec_from_file_location("grid10_fabric_lab", MODULE)
grid = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = grid
spec.loader.exec_module(grid)


def test_core_authority_and_recovery_invariants(tmp_path):
    fabric = grid.Fabric(tmp_path / "grid10-lab.sqlite3")
    fabric.seed_scope("voice")
    fabric.seed_task("t1", "voice", "reason", {"q": "x"})
    fabric.runtime_join("n1", "reason", 101)
    fabric.runtime_join("n2", "reason", 102)

    snap = fabric.snapshot()
    fabric.runtime_claim_task("t1", "n1", expected_epoch=snap.epoch)
    with pytest.raises(grid.FabricError, match="ORDINARY_NODE_S1_WRITE_FORBIDDEN"):
        fabric.ordinary_write_attempt("n1")

    elected = fabric.elect_coordinator("voice", ["n1", "n2"])
    assert elected is not None
    lease, token = elected

    snap2 = fabric.snapshot()
    packet = grid.result_packet("n1", snap2, "voice", {"task_id": "t1", "answer": 42})
    fabric.emit_node_result(packet)
    committed = fabric.coordinator_commit(lease=lease, token=token, packet=packet, expected_epoch=snap2.epoch)
    assert committed["canonical_truth"] is False
    assert committed["effect_authority"] is False

    with pytest.raises(grid.FabricError, match="DUPLICATE_RESULT_REJECTED"):
        fabric.coordinator_commit(
            lease=lease,
            token=token,
            packet=packet,
            expected_epoch=fabric.snapshot().epoch,
        )

    fabric.revoke_lease(lease["lease_id"])
    with pytest.raises(grid.FabricError, match="COORDINATOR_LEASE_INVALID"):
        fabric.coordinator_commit(
            lease=lease,
            token=token,
            packet=grid.result_packet("n1", fabric.snapshot(), "voice", {"task_id": "t1", "answer": 43}),
            expected_epoch=fabric.snapshot().epoch,
        )
