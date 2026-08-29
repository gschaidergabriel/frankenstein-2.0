#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).with_name('E3_EXECUTED_SOURCE.py')
spec = importlib.util.spec_from_file_location('witness', SOURCE)
w = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(w)

PARENT = '''import subprocess, sys, time
child = subprocess.Popen([sys.executable, '-c', "import time\\nend=time.monotonic()+4.0\\nx=0\\nwhile time.monotonic()<end: x=(x*1664525+1013904223)&0xffffffff\\nprint(x)"])
print(child.pid, flush=True)
time.sleep(3.5)
child.wait()
'''

def run() -> dict:
    parent = subprocess.Popen([sys.executable, '-c', PARENT], stdout=subprocess.PIPE, text=True)
    assert parent.stdout is not None
    child_pid = int(parent.stdout.readline().strip())
    parent_pid = parent.pid
    parent_obs = w.witness(parent_pid, 0.40)
    child_obs = w.witness(child_pid, 0.40)
    parent.wait(timeout=8)
    parent_cpu = parent_obs['delta']['cpu_seconds']
    child_cpu = child_obs['delta']['cpu_seconds']
    outcome = 'SUPPORTED_PROCFS_PARENT_UNDERCOUNTS_PROCESS_TREE' if child_cpu > parent_cpu + 0.10 else 'NOT_DISCRIMINATIVE'
    return {
        'schema': 'FRANKENSTEIN2_TRIGGER6_PROCFS_UNDERCOUNT_REPRODUCTION/v1',
        'research_id': 'R6-20260829-CGROUPLESS-CONTAINER-RESOURCE-WITNESS-GPT56SOL-01',
        'evidence_stage': 'E3_CLAIM_REPRODUCED_LOCAL_NON_F2',
        'parent_pid': parent_pid,
        'child_pid': child_pid,
        'parent_cpu_seconds': parent_cpu,
        'child_cpu_seconds': child_cpu,
        'parent_scope': parent_obs['scope'],
        'child_scope': child_obs['scope'],
        'parent_container_total_credit': parent_obs['container_total_credit'],
        'child_container_total_credit': child_obs['container_total_credit'],
        'falsifier_outcome': outcome,
        'evidence_boundary': 'LOCAL PROCESS-TREE REPRODUCTION ONLY; NOT CONTAINER, NOT F2, NOT VPS, NOT E4 F2 ABLATION',
        'credits': {'f2_runtime':0,'vps':0,'container_total':0,'whole_system':0},
    }

if __name__ == '__main__':
    result = run()
    print(json.dumps(result, sort_keys=True, indent=2))
    raise SystemExit(0 if result['falsifier_outcome'].startswith('SUPPORTED_') else 1)
