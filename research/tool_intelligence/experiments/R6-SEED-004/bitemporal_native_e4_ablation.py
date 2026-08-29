from __future__ import annotations
import json, time, sqlite3, tracemalloc, platform, sys, hashlib, math, random
from collections import defaultdict


def stable_json(v):
    return json.dumps(v, sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False)

def qtile(xs, q):
    xs=sorted(xs)
    idx=min(len(xs)-1, max(0, math.ceil(q*len(xs))-1))
    return xs[idx]

def active(row, system_t, valid_t):
    if row["observed_at"] > system_t:
        return False
    if row["expired_at"] is not None and not (system_t < row["expired_at"]):
        return False
    if row["valid_at"] is None or row["valid_at"] > valid_t:
        return False
    if row["invalid_at"] is not None and not (valid_t < row["invalid_at"]):
        return False
    return True

def scan_query(rows, relation_id, system_t, valid_t):
    matches=[r for r in rows if r["relation_id"]==relation_id and active(r,system_t,valid_t)]
    if len(matches)==1:
        return matches[0]["version_id"]
    if len(matches)==0:
        return None
    return "AMBIGUOUS"

def build_index(rows):
    out=defaultdict(list)
    for r in rows:
        out[r["relation_id"]].append(r)
    for rid in out:
        out[rid].sort(key=lambda r:(r["observed_at"],r["version_id"]))
    return dict(out)

def index_query(index, relation_id, system_t, valid_t):
    matches=[r for r in index.get(relation_id,()) if active(r,system_t,valid_t)]
    if len(matches)==1:
        return matches[0]["version_id"]
    if len(matches)==0:
        return None
    return "AMBIGUOUS"

def latest_only_query(index, relation_id, valid_t):
    versions=index.get(relation_id,())
    if not versions: return None
    r=versions[-1]
    if r["valid_at"] is None or r["valid_at"] > valid_t: return None
    if r["invalid_at"] is not None and not (valid_t < r["invalid_at"]): return None
    return r["version_id"]

N_REL=6000
rows=[]
for i in range(N_REL):
    rid=f"rel-{i:05d}"
    rows.append({
        "relation_id":rid,"version_id":f"{rid}-v0","fact_code":"STATE_ON",
        "observed_at":5+(i%7),"reference_time":3+(i%5),"valid_at":0,"invalid_at":None,
        "expired_at":50 if i%2==0 else None,"provenance_id":f"episode-{i:05d}-a",
        "canonical_sha256":hashlib.sha256(f"{rid}:v0".encode()).hexdigest(),
    })
    if i%2==0:
        rows.append({
            "relation_id":rid,"version_id":f"{rid}-v1","fact_code":"STATE_ON",
            "observed_at":50,"reference_time":45,"valid_at":0,"invalid_at":20+(i%5),
            "expired_at":None,"provenance_id":f"episode-{i:05d}-correction",
            "canonical_sha256":hashlib.sha256(f"{rid}:v1".encode()).hexdigest(),
        })

raw_digest=hashlib.sha256(stable_json(rows).encode()).hexdigest()
raw_bytes=len(stable_json(rows).encode())
tracemalloc.start(); t0=time.perf_counter_ns(); index=build_index(rows); build_ns=time.perf_counter_ns()-t0
cur,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
index_bytes=len(stable_json(index).encode())

con=sqlite3.connect(":memory:")
con.execute("PRAGMA journal_mode=OFF")
con.execute("PRAGMA synchronous=OFF")
con.execute("CREATE TABLE events (relation_id TEXT, version_id TEXT, observed_at INTEGER, valid_at INTEGER, invalid_at INTEGER, expired_at INTEGER)")
con.executemany("INSERT INTO events VALUES (?,?,?,?,?,?)",[(r['relation_id'],r['version_id'],r['observed_at'],r['valid_at'],r['invalid_at'],r['expired_at']) for r in rows])
con.execute("CREATE INDEX idx_events_rel_obs ON events(relation_id, observed_at)")

rng=random.Random(8675309)
queries=[]
for _ in range(900):
    i=rng.randrange(N_REL); rid=f"rel-{i:05d}"
    system_t=rng.choice([10,49,50,60])
    valid_t=rng.choice([10,19,20,21,24,25,30])
    queries.append((rid,system_t,valid_t))
# add exact discriminating historical/current pairs for corrected rows
for i in range(0,400,2):
    rid=f"rel-{i:05d}"; end=20+(i%5)
    queries.append((rid,49,end+1))
    queries.append((rid,60,end+1))

# Correctness equivalence
scan_results=[scan_query(rows,*q) for q in queries]
idx_results=[index_query(index,*q) for q in queries]
index_mismatches=sum(a!=b for a,b in zip(scan_results,idx_results))
ambiguous=sum(x=="AMBIGUOUS" for x in scan_results)

# SQLite correctness
def sqlite_query(q):
    rid,system_t,valid_t=q
    rs=con.execute("""
      SELECT version_id FROM events
      WHERE relation_id=? AND observed_at<=?
        AND (expired_at IS NULL OR ? < expired_at)
        AND valid_at<=?
        AND (invalid_at IS NULL OR ? < invalid_at)
      ORDER BY observed_at, version_id LIMIT 2
    """,(rid,system_t,system_t,valid_t,valid_t)).fetchall()
    if len(rs)==1: return rs[0][0]
    if len(rs)==0: return None
    return "AMBIGUOUS"
sql_results=[sqlite_query(q) for q in queries]
sql_mismatches=sum(a!=b for a,b in zip(scan_results,sql_results))

# Falsify collapse to latest-only current projection on historical-system queries
collapse_errors=0; collapse_cases=0
for q,truth in zip(queries,scan_results):
    rid,system_t,valid_t=q
    if system_t < 50 and int(rid.split('-')[1])%2==0:
        collapse_cases+=1
        if latest_only_query(index,rid,valid_t)!=truth:
            collapse_errors+=1

# Microbench: interleave rounds and collect per-query us
sample=queries[:800]
scan_us=[]; idx_us=[]; sql_us=[]
for q in sample:
    t=time.perf_counter_ns(); scan_query(rows,*q); scan_us.append((time.perf_counter_ns()-t)/1000)
    t=time.perf_counter_ns(); index_query(index,*q); idx_us.append((time.perf_counter_ns()-t)/1000)
    t=time.perf_counter_ns(); sqlite_query(q); sql_us.append((time.perf_counter_ns()-t)/1000)

# observer rebuild determinism
index_digest=hashlib.sha256(stable_json(index).encode()).hexdigest()
index2=build_index(list(rows))
index2_digest=hashlib.sha256(stable_json(index2).encode()).hexdigest()
source_unchanged=hashlib.sha256(stable_json(rows).encode()).hexdigest()==raw_digest

# explicit fail-closed ambiguity fixture: two simultaneously-active versions
base_rel_00001=next(r for r in rows if r["relation_id"]=="rel-00001")
amb_rows=list(rows)+[dict(base_rel_00001, version_id="rel-00001-conflict", canonical_sha256="f"*64)]
amb_index=build_index(amb_rows)
ambiguity_fail_closed=(index_query(amb_index,"rel-00001",60,10)=="AMBIGUOUS")

result={
 "schema":"FRANKENSTEIN2_TRIGGER6_GRAPHITI_DISTILLATION_E4_RESULT/v1",
 "research_id":"R6-SEED-004",
 "claim_target":"E4_F2_ABLATION_BITEMPORAL_NATIVE_V0",
 "scope":"LOCAL_DETERMINISTIC_PYTHON_SQLITE_COMPONENT_ABLATION_NOT_GRAPHITI_RUNTIME_NOT_F2_TARGET_RUNTIME",
 "source_pin":{"repo":"getzep/graphiti","commit":"c18d6778184c55e3be28f5ae3e5821930b361d47","tree":"b4f30e3764115dcb2ecbd846ee9f58f2453f5b57"},
 "graphiti_semantics_tested":["separate observed/system time","valid_at","invalid_at","expired_at/supersession","episode/provenance preservation"],
 "fixture":{"relations":N_REL,"canonical_rows":len(rows),"queries":len(queries),"bench_queries":len(sample),"raw_json_bytes":raw_bytes,"derived_index_json_bytes":index_bytes,"derived_to_raw_ratio":round(index_bytes/raw_bytes,6)},
 "correctness":{"index_vs_reference_mismatches":index_mismatches,"sqlite_vs_reference_mismatches":sql_mismatches,"reference_ambiguous_queries":ambiguous,"rebuild_digest_equal":index_digest==index2_digest,"source_unchanged":source_unchanged,"ambiguity_fail_closed":ambiguity_fail_closed},
 "two_axis_falsifier":{"historical_corrected_cases":collapse_cases,"latest_only_errors":collapse_errors,"error_rate":round(collapse_errors/collapse_cases,6) if collapse_cases else None,"interpretation":"collapsing system/observation time into latest validity state loses historical truth-as-known-then"},
 "build":{"derived_index_build_ms":round(build_ns/1e6,3),"python_tracemalloc_peak_bytes":peak},
 "latency_us":{
   "canonical_global_scan":{"p50":round(qtile(scan_us,.50),3),"p95":round(qtile(scan_us,.95),3),"p99":round(qtile(scan_us,.99),3)},
   "sqlite_indexed":{"p50":round(qtile(sql_us,.50),3),"p95":round(qtile(sql_us,.95),3),"p99":round(qtile(sql_us,.99),3)},
   "derived_in_memory":{"p50":round(qtile(idx_us,.50),3),"p95":round(qtile(idx_us,.95),3),"p99":round(qtile(idx_us,.99),3)},
 },
 "environment":{"python":sys.version.split()[0],"platform":platform.platform(),"sqlite":sqlite3.sqlite_version},
 "evidence_ceiling":"E4_LOCAL_COMPONENT_ABLATION_ONLY",
 "credits":{"architecture":0,"runtime":0,"integration":0,"effect":0,"whole_system":0},
 "limitations":[
   "No Graphiti server/driver/LLM/embedder executed; only source-derived temporal semantics were structurally distilled.",
   "The canonical global scan is a deliberately simple reference, not a claim about production UnifiedDB query performance.",
   "SQLite and in-memory measurements are local-container microbenchmarks; they are not VPS/target-runtime measurements.",
   "Serialized JSON size is a structural size proxy, not RSS/PSS or persistent SQLite page cost.",
   "E5 promotion requires an exact F2/UnifiedDB schema integration plan and benchmark against the actual future Phase-3/4 query workload."
 ],
}
print(stable_json(result))
