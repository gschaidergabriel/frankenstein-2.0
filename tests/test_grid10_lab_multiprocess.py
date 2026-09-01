import importlib.util
import json
import subprocess
import sys
from pathlib import Path

MODULE = Path(__file__).parents[1] / "research" / "grid10_lab" / "grid10_fabric_lab.py"
spec = importlib.util.spec_from_file_location("grid10_fabric_lab_mp_parent", MODULE)
grid = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = grid
spec.loader.exec_module(grid)

_CHILD = r'''
import importlib.util, inspect, json, sys
from pathlib import Path
module_path, db_path, action, payload_json = sys.argv[1:]
spec = importlib.util.spec_from_file_location("grid10_fabric_lab_child", module_path)
grid = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = grid
spec.loader.exec_module(grid)
fabric = grid.Fabric(Path(db_path))
payload = json.loads(payload_json)
sys.stdin.readline()
try:
    if action == "claim":
        fabric.runtime_claim_task(
            payload["task_id"], payload["node_id"], expected_epoch=payload["expected_epoch"]
        )
    elif action == "emit":
        fabric.emit_node_result(payload["packet"])
    elif action == "commit":
        kwargs = dict(
            lease=payload["lease"], token=payload["token"], packet=payload["packet"],
            expected_epoch=payload["expected_epoch"],
        )
        if "expected_digest" in inspect.signature(fabric.coordinator_commit).parameters:
            kwargs["expected_digest"] = payload["expected_digest"]
        fabric.coordinator_commit(**kwargs)
    else:
        raise AssertionError(action)
    print(json.dumps({"ok": True}, sort_keys=True))
except Exception as exc:
    print(json.dumps({"ok": False, "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
'''


def _race(db_path, action, payloads):
    procs = []
    for payload in payloads:
        p = subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(MODULE), str(db_path), action, json.dumps(payload, sort_keys=True)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        procs.append(p)
    for p in procs:
        assert p.stdin is not None
        p.stdin.write("go\n")
        p.stdin.flush()
    results = []
    for p in procs:
        out, err = p.communicate(timeout=15)
        assert p.returncode == 0, err
        results.append(json.loads(out.strip()))
    return results


def test_os_process_claim_collision_is_single_winner(tmp_path):
    db_path = tmp_path / "grid10-multiprocess.sqlite3"
    fabric = grid.Fabric(db_path)
    fabric.seed_scope("voice")
    fabric.seed_task("t1", "voice", "reason", {"q": "race"})
    fabric.runtime_join("n1", "reason", 101)
    fabric.runtime_join("n2", "reason", 102)
    snap = fabric.snapshot()

    results = _race(db_path, "claim", [
        {"task_id": "t1", "node_id": "n1", "expected_epoch": snap.epoch},
        {"task_id": "t1", "node_id": "n2", "expected_epoch": snap.epoch},
    ])
    assert sum(r["ok"] for r in results) == 1
    loser = next(r for r in results if not r["ok"])
    assert any(code in loser["error"] for code in ("TASK_CLAIM_CAS_FAILED", "TASK_NOT_CLAIMABLE"))

    con = grid.connect(db_path)
    try:
        row = con.execute("SELECT status,claimed_by FROM tasks WHERE task_id='t1'").fetchone()
        assert row["status"] == "CLAIMED"
        assert row["claimed_by"] in {"n1", "n2"}
    finally:
        con.close()


def test_os_process_duplicate_emit_and_commit_collision_are_single_admission(tmp_path):
    db_path = tmp_path / "grid10-multiprocess.sqlite3"
    fabric = grid.Fabric(db_path)
    fabric.seed_scope("voice")
    fabric.runtime_join("n1", "reason", 101)
    fabric.runtime_join("n2", "reason", 102)
    elected = fabric.elect_coordinator("voice", ["n1", "n2"])
    assert elected is not None
    lease, token = elected
    snap = fabric.snapshot()
    packet = grid.result_packet("n1", snap, "voice", {"answer": 42})

    emit_results = _race(db_path, "emit", [{"packet": packet}] * 4)
    assert all(r["ok"] for r in emit_results)
    con = grid.connect(db_path)
    try:
        outbox_count = con.execute(
            "SELECT COUNT(*) FROM outbox WHERE packet_digest=?", (packet["packet_digest"],)
        ).fetchone()[0]
        assert outbox_count == 1
    finally:
        con.close()

    commit_payload = {
        "lease": lease,
        "token": token,
        "packet": packet,
        "expected_epoch": snap.epoch,
        "expected_digest": snap.state_digest,
    }
    commit_results = _race(db_path, "commit", [commit_payload, commit_payload])
    assert sum(r["ok"] for r in commit_results) == 1
    loser = next(r for r in commit_results if not r["ok"])
    assert any(code in loser["error"] for code in (
        "S1_COMPARE_AND_SWAP_FAILED", "S1_COMPARE_AND_SWAP_DIGEST_FAILED", "DUPLICATE_RESULT_REJECTED"
    ))

    con = grid.connect(db_path)
    try:
        assert con.execute("SELECT COUNT(*) FROM admitted_results").fetchone()[0] == 1
        scope = con.execute("SELECT evidence_count,last_result_digest FROM scopes WHERE scope='voice'").fetchone()
        assert scope["evidence_count"] == 1
        assert scope["last_result_digest"] == packet["packet_digest"]
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()
