import importlib.util
import inspect
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

MODULE = Path(__file__).parents[1] / "research" / "grid10_lab" / "grid10_fabric_lab.py"
spec = importlib.util.spec_from_file_location("grid10_fabric_lab_restart_parent", MODULE)
grid = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = grid
spec.loader.exec_module(grid)

CHILD = r'''
import importlib.util, inspect, json, sys
from pathlib import Path
module_path, db_path, action, payload_json = sys.argv[1:]
spec = importlib.util.spec_from_file_location("grid10_fabric_lab_restart_child", module_path)
grid = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = grid
spec.loader.exec_module(grid)
fabric = grid.Fabric(Path(db_path))
p = json.loads(payload_json)
if action == "join_claim":
    fabric.runtime_join(p["node_id"], p["capability"], p["pid"])
    snap = fabric.snapshot()
    fabric.runtime_claim_task(p["task_id"], p["node_id"], expected_epoch=snap.epoch)
elif action == "join":
    fabric.runtime_join(p["node_id"], p["capability"], p["pid"])
elif action == "commit":
    kwargs = dict(lease=p["lease"], token=p["token"], packet=p["packet"], expected_epoch=p["expected_epoch"])
    if "expected_digest" in inspect.signature(fabric.coordinator_commit).parameters:
        kwargs["expected_digest"] = p["expected_digest"]
    fabric.coordinator_commit(**kwargs)
else:
    raise AssertionError(action)
print(json.dumps({"ok": True}, sort_keys=True))
'''


def _child(db_path, action, payload):
    cp = subprocess.run(
        [sys.executable, "-c", CHILD, str(MODULE), str(db_path), action, json.dumps(payload, sort_keys=True)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert cp.returncode == 0, cp.stderr
    assert json.loads(cp.stdout)["ok"] is True


def test_process_exit_stale_claim_reclaims_then_same_node_rejoins(tmp_path):
    db = tmp_path / "restart.sqlite3"
    fabric = grid.Fabric(db)
    fabric.seed_scope("voice")
    fabric.seed_task("t1", "voice", "reason", {"q": "restart"})

    _child(db, "join_claim", {"node_id": "n1", "capability": "reason", "pid": 1001, "task_id": "t1"})
    time.sleep(0.04)
    assert fabric.reclaim_stale_claims(stale_after_seconds=0.01) == ["t1"]

    _child(db, "join", {"node_id": "n1", "capability": "reason", "pid": 2002})
    snap = fabric.snapshot()
    fabric.runtime_claim_task("t1", "n1", expected_epoch=snap.epoch)

    con = grid.connect(db)
    try:
        node = con.execute("SELECT healthy,pid FROM nodes WHERE node_id='n1'").fetchone()
        task = con.execute("SELECT status,claimed_by FROM tasks WHERE task_id='t1'").fetchone()
        assert node["healthy"] == 1
        assert node["pid"] == 2002
        assert task["status"] == "CLAIMED"
        assert task["claimed_by"] == "n1"
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()


def test_pending_result_blocks_stale_claim_reclaim(tmp_path):
    db = tmp_path / "pending.sqlite3"
    fabric = grid.Fabric(db)
    fabric.seed_scope("voice")
    fabric.seed_task("t2", "voice", "reason", {"q": "pending"})
    fabric.runtime_join("n1", "reason", 1001)
    snap = fabric.snapshot()
    fabric.runtime_claim_task("t2", "n1", expected_epoch=snap.epoch)
    packet_snap = fabric.snapshot()
    packet = grid.result_packet("n1", packet_snap, "voice", {"task_id": "t2", "answer": 7})
    fabric.emit_node_result(packet)

    time.sleep(0.04)
    assert fabric.reclaim_stale_claims(stale_after_seconds=0.01) == []
    con = grid.connect(db)
    try:
        task = con.execute("SELECT status,claimed_by FROM tasks WHERE task_id='t2'").fetchone()
        assert task["status"] == "CLAIMED"
        assert task["claimed_by"] == "n1"
        assert con.execute("SELECT COUNT(*) FROM outbox WHERE consumed=0").fetchone()[0] == 1
    finally:
        con.close()


def test_committed_result_survives_process_exit_and_duplicate_is_rejected(tmp_path):
    db = tmp_path / "commit-restart.sqlite3"
    fabric = grid.Fabric(db)
    fabric.seed_scope("voice")
    fabric.runtime_join("n1", "reason", 1001)
    fabric.runtime_join("n2", "reason", 1002)
    elected = fabric.elect_coordinator("voice", ["n1", "n2"])
    assert elected is not None
    lease, token = elected
    snap = fabric.snapshot()
    packet = grid.result_packet("n1", snap, "voice", {"answer": 42})

    _child(db, "commit", {
        "lease": lease,
        "token": token,
        "packet": packet,
        "expected_epoch": snap.epoch,
        "expected_digest": snap.state_digest,
    })

    restarted = grid.Fabric(db)
    snap2 = restarted.snapshot()
    with pytest.raises(grid.FabricError, match="DUPLICATE_RESULT_REJECTED"):
        kwargs = dict(lease=lease, token=token, packet=packet, expected_epoch=snap2.epoch)
        if "expected_digest" in inspect.signature(restarted.coordinator_commit).parameters:
            kwargs["expected_digest"] = snap2.state_digest
        restarted.coordinator_commit(**kwargs)

    con = grid.connect(db)
    try:
        assert con.execute("SELECT COUNT(*) FROM admitted_results").fetchone()[0] == 1
        scope = con.execute("SELECT evidence_count,last_result_digest FROM scopes WHERE scope='voice'").fetchone()
        assert scope["evidence_count"] == 1
        assert scope["last_result_digest"] == packet["packet_digest"]
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()
