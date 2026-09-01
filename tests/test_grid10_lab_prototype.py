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


def _setup(tmp_path):
    fabric = grid.Fabric(tmp_path / "grid10-lab.sqlite3")
    fabric.seed_scope("voice")
    fabric.seed_task("t1", "voice", "reason", {"q": "x"})
    fabric.runtime_join("n1", "reason", 101)
    fabric.runtime_join("n2", "reason", 102)
    elected = fabric.elect_coordinator("voice", ["n1", "n2"])
    assert elected is not None
    lease, token = elected
    return fabric, lease, token


def _redigest(packet):
    core = {k: packet[k] for k in packet if k not in ("packet_digest", "s1_write_intent")}
    packet["packet_digest"] = grid.digest(core)
    return packet


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
    committed = fabric.coordinator_commit(
        lease=lease,
        token=token,
        packet=packet,
        expected_epoch=snap2.epoch,
        expected_digest=snap2.state_digest,
    )
    assert committed["canonical_truth"] is False
    assert committed["effect_authority"] is False

    snap3 = fabric.snapshot()
    with pytest.raises(grid.FabricError, match="DUPLICATE_RESULT_REJECTED"):
        fabric.coordinator_commit(
            lease=lease,
            token=token,
            packet=packet,
            expected_epoch=snap3.epoch,
            expected_digest=snap3.state_digest,
        )

    fabric.revoke_lease(lease["lease_id"])
    snap4 = fabric.snapshot()
    with pytest.raises(grid.FabricError, match="COORDINATOR_LEASE_INVALID"):
        fabric.coordinator_commit(
            lease=lease,
            token=token,
            packet=grid.result_packet("n1", snap4, "voice", {"task_id": "t1", "answer": 43}),
            expected_epoch=snap4.epoch,
            expected_digest=snap4.state_digest,
        )


def test_rejects_state_digest_cas_mismatch(tmp_path):
    fabric, lease, token = _setup(tmp_path)
    snap = fabric.snapshot()
    packet = grid.result_packet("n1", snap, "voice", {"answer": 1})
    with pytest.raises(grid.FabricError, match="S1_COMPARE_AND_SWAP_DIGEST_FAILED"):
        fabric.coordinator_commit(
            lease=lease,
            token=token,
            packet=packet,
            expected_epoch=snap.epoch,
            expected_digest="0" * 64,
        )


def test_rejects_future_epoch_and_wrong_source_kind(tmp_path):
    fabric, lease, token = _setup(tmp_path)
    snap = fabric.snapshot()

    future = grid.result_packet("n1", snap, "voice", {"answer": 1})
    future["state_epoch"] = snap.epoch + 1
    _redigest(future)
    with pytest.raises(grid.FabricError, match="RESULT_FUTURE_EPOCH"):
        fabric.coordinator_commit(
            lease=lease,
            token=token,
            packet=future,
            expected_epoch=snap.epoch,
            expected_digest=snap.state_digest,
        )

    wrong_kind = grid.result_packet("n1", snap, "voice", {"answer": 2})
    wrong_kind["source_kind"] = "COORDINATOR"
    _redigest(wrong_kind)
    with pytest.raises(grid.FabricError, match="ORDINARY_RESULT_SOURCE_KIND_INVALID"):
        fabric.coordinator_commit(
            lease=lease,
            token=token,
            packet=wrong_kind,
            expected_epoch=snap.epoch,
            expected_digest=snap.state_digest,
        )


def test_rejects_stale_generation_lease_and_result(tmp_path):
    fabric, lease, token = _setup(tmp_path)

    con = grid.connect(fabric.path)
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("UPDATE meta SET v='2' WHERE k='generation'")
        con.execute("COMMIT")
    finally:
        con.close()

    snap = fabric.snapshot()
    current_generation_packet = grid.result_packet("n1", snap, "voice", {"answer": 3})
    with pytest.raises(grid.FabricError, match="COORDINATOR_LEASE_STALE_GENERATION"):
        fabric.coordinator_commit(
            lease=lease,
            token=token,
            packet=current_generation_packet,
            expected_epoch=snap.epoch,
            expected_digest=snap.state_digest,
        )

    # A packet may also be stale even while the lease generation is current.
    con = grid.connect(fabric.path)
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("UPDATE leases SET generation=2 WHERE lease_id=?", (lease["lease_id"],))
        con.execute("COMMIT")
    finally:
        con.close()

    snap2 = fabric.snapshot()
    stale_packet = grid.result_packet("n1", snap2, "voice", {"answer": 4})
    stale_packet["generation"] = 1
    _redigest(stale_packet)
    with pytest.raises(grid.FabricError, match="RESULT_STALE_GENERATION"):
        fabric.coordinator_commit(
            lease=lease,
            token=token,
            packet=stale_packet,
            expected_epoch=snap2.epoch,
            expected_digest=snap2.state_digest,
        )
