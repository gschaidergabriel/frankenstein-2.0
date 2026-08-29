import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

P = Path(__file__).with_name("E3_EXECUTED_SOURCE.py")
spec = importlib.util.spec_from_file_location("w", P)
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


def test_parse_stat_handles_spaces_and_parentheses():
    real = Path(f"/proc/{os.getpid()}/stat").read_text()
    got = w._parse_stat(real)
    assert got["pid"] == os.getpid()
    assert got["starttime_ticks"] > 0


def test_self_witness_is_process_scoped_and_no_container_credit():
    got = w.witness(os.getpid(), 0.0)
    assert got["scope"] == "INIT_PROCESS_ONLY"
    assert got["container_total_credit"] is False
    assert got["cgroup_total_credit"] is False
    assert got["process_identity"]["starttime_ticks"] > 0
    assert len(got["witness_sha256"]) == 64


def test_invalid_pid_fails_closed():
    try:
        w.witness(-1, 0)
    except w.WitnessError as exc:
        assert "INVALID_PID" in str(exc)
    else:
        raise AssertionError("expected WitnessError")


def test_exited_process_fails_closed():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    pid = p.pid
    p.wait()
    time.sleep(0.01)
    try:
        w.witness(pid, 0)
    except w.WitnessError as exc:
        assert "PID_NOT_AVAILABLE" in str(exc)
    else:
        raise AssertionError("expected WitnessError")
