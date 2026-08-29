from __future__ import annotations

import gc
import importlib.util
import json
import statistics
import time
import tracemalloc
from pathlib import Path

MODULE_PATH = Path('/mnt/data/r6_openinference_e3_falsifier.py')
spec = importlib.util.spec_from_file_location('r6_e3', MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)

source = {
    "schema": "FRANKENSTEIN2_GWT_REENTRY_UPTAKE_BINDING/v1",
    "classification": "DERIVED_BINDING_WP507_UPTAKE_AUTHORITY_ONLY_NOT_NEW_UPTAKE_OR_RUNTIME_EVIDENCE",
    "binding_id": "binding-001",
    "canonical_reentry_key": "1" * 64,
    "reentry_witness_sha256": "2" * 64,
    "uptake_receipt_id": "uptake-001",
    "uptake_receipt_sha256": "3" * 64,
    "broadcast_id": "broadcast-001",
    "broadcast_generation": 4,
    "broadcast_sha256": "4" * 64,
    "recipient_cell_id": "G7",
    "delivery_status": "DELIVERED",
    "uptake_status": "UPTAKEN",
    "downstream_ref": "receipt://downstream/001",
    "downstream_sha256": "5" * 64,
    "binding_status": "WP507_UPTAKEN_BOUND",
    "causal_influence_claim": "NOT_ESTABLISHED_BY_BINDING",
    "truth_authority": "NONE",
    "effect_authority": "NONE",
    "prompt": "TOP-SECRET PROMPT 9c8e9a",
    "output": "TOP-SECRET OUTPUT c4fb7d",
    "tool_definition": "dangerous-tool-schema-ff1190",
    "api_key": "sk-test-never-export-01",
    "secret": "secret-never-export-02",
    "freeform_metadata": {"private": "never-export-03"},
}
TRACE_ID = 'a' * 32
SPAN_ID = 'b' * 16


def native_encode():
    mod.validate_source(source)
    native_min = {key: source.get(key) for key in mod.CANONICAL_FIELDS if source.get(key) is not None}
    return mod.stable_json(native_min)


def projection_encode():
    p = mod.project_to_openinference(source, observer_enabled=True, target_trace_id=TRACE_ID, target_span_id=SPAN_ID)
    assert p is not None
    return mod.stable_json(p)


def percentile(sorted_values, q):
    idx = int(round((len(sorted_values) - 1) * q))
    return sorted_values[idx]


def latency_benchmark(iterations=30000, warmup=3000):
    for _ in range(warmup):
        native_encode(); projection_encode()
    native_ns, projection_ns = [], []
    gc_enabled = gc.isenabled(); gc.disable()
    try:
        for i in range(iterations):
            if i % 2 == 0:
                t0=time.perf_counter_ns(); native_encode(); t1=time.perf_counter_ns()
                t2=time.perf_counter_ns(); projection_encode(); t3=time.perf_counter_ns()
            else:
                t2=time.perf_counter_ns(); projection_encode(); t3=time.perf_counter_ns()
                t0=time.perf_counter_ns(); native_encode(); t1=time.perf_counter_ns()
            native_ns.append(t1-t0); projection_ns.append(t3-t2)
    finally:
        if gc_enabled: gc.enable()
    def stats(v):
        v=sorted(v)
        return {'p50_ns':percentile(v,.50),'p95_ns':percentile(v,.95),'p99_ns':percentile(v,.99),'mean_ns':round(statistics.fmean(v),3),'min_ns':v[0],'max_ns':v[-1]}
    return stats(native_ns), stats(projection_ns)


def memory_benchmark(func, iterations=5000):
    gc.collect(); tracemalloc.start(); baseline_current,_=tracemalloc.get_traced_memory(); checksum=0
    for _ in range(iterations): checksum ^= len(func())
    current,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
    return {'iterations':iterations,'peak_bytes_over_baseline':peak-baseline_current,'current_bytes_over_baseline':current-baseline_current,'checksum':checksum}


def main():
    native_payload=native_encode(); projection_payload=projection_encode()
    native_stats,projection_stats=latency_benchmark(); native_mem=memory_benchmark(native_encode); projection_mem=memory_benchmark(projection_encode)
    result={
      'schema':'FRANKENSTEIN2_TRIGGER6_OPENINFERENCE_E4_COST_ABLATION/v1','research_id':'R6-SEED-011','claim_target':'E4_F2_ABLATION_OPENINFERENCE_PROJECTION_COST_V0',
      'scope':'LOCAL_PYTHON_MICROBENCHMARK_NOT_OTLP_NOT_COLLECTOR_NOT_VPS_NOT_F2_TARGET_RUNTIME','python_clock':'time.perf_counter_ns','iterations':30000,'warmup':3000,
      'payload':{'native_json_bytes':len(native_payload.encode()),'projection_json_bytes':len(projection_payload.encode()),'byte_ratio':round(len(projection_payload.encode())/len(native_payload.encode()),6)},
      'latency':{'native':native_stats,'projection':projection_stats,'ratio':{'p50':round(projection_stats['p50_ns']/native_stats['p50_ns'],6),'p95':round(projection_stats['p95_ns']/native_stats['p95_ns'],6),'p99':round(projection_stats['p99_ns']/native_stats['p99_ns'],6),'mean':round(projection_stats['mean_ns']/native_stats['mean_ns'],6)}},
      'tracemalloc':{'native':native_mem,'projection':projection_mem,'peak_ratio':round(projection_mem['peak_bytes_over_baseline']/native_mem['peak_bytes_over_baseline'],6),'note':'Python tracemalloc peak in repeated local serialization loop; not process RSS/PSS and not runtime steady-state memory.'},
      'interpretation_gate':{'identity_privacy_semantics':'SUPPORTED_BY_E3_ONLY','runtime_efficiency':'NOT_ESTABLISHED','build_promotion':False,'reason':'E4 measures local Python/JSON overhead only. Full SDK, OTLP, collector, exporter and query-value benefit remain unmeasured.'},
      'architecture_credit':0,'runtime_credit':0,'gwt_causal_credit':0,'effect_credit':0,'whole_system_credit':0}
    print(json.dumps(result,sort_keys=True,indent=2))

if __name__=='__main__': main()
