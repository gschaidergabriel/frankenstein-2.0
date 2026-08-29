from __future__ import annotations
import hashlib, json, random, sqlite3, statistics, time

EVENTS = [
    dict(event_id="E001", subject="service", predicate="mode", value="blue", cardinality="SINGLE", observed_at="2026-01-01T10:00:00Z", reference_time="2026-01-01T09:55:00Z", valid_from="2026-01-01T00:00:00Z", supersedes_event_id=None, epistemic="OBSERVED"),
    dict(event_id="E002", subject="service", predicate="mode", value="green", cardinality="SINGLE", observed_at="2026-02-01T10:00:00Z", reference_time="2026-02-01T09:55:00Z", valid_from="2026-02-01T00:00:00Z", supersedes_event_id="E001", epistemic="OBSERVED"),
    dict(event_id="E003", subject="auth", predicate="uses", value="JWT", cardinality="MULTI", observed_at="2026-01-05T10:00:00Z", reference_time="2026-01-05T09:55:00Z", valid_from="2026-01-05T00:00:00Z", supersedes_event_id=None, epistemic="OBSERVED"),
    dict(event_id="E004", subject="auth", predicate="uses", value="session_tokens", cardinality="MULTI", observed_at="2026-02-05T10:00:00Z", reference_time="2026-02-05T09:55:00Z", valid_from="2026-02-05T00:00:00Z", supersedes_event_id=None, epistemic="OBSERVED"),
    dict(event_id="E005", subject="deployment", predicate="region", value="us-east", cardinality="ALTERNATIVE", observed_at="2026-02-10T10:00:00Z", reference_time="2026-02-10T09:55:00Z", valid_from="2026-02-10T00:00:00Z", supersedes_event_id=None, epistemic="REPORTED"),
    dict(event_id="E006", subject="deployment", predicate="region", value="eu-west", cardinality="ALTERNATIVE", observed_at="2026-02-10T10:01:00Z", reference_time="2026-02-10T09:56:00Z", valid_from="2026-02-10T00:00:00Z", supersedes_event_id=None, epistemic="REPORTED"),
    dict(event_id="E007", subject="schema", predicate="version", value="v1", cardinality="SINGLE", observed_at="2026-03-01T10:00:00Z", reference_time="2025-12-15T00:00:00Z", valid_from="2025-12-15T00:00:00Z", supersedes_event_id=None, epistemic="OBSERVED"),
]

def canonical_payload(e):
    return json.dumps({k: e[k] for k in sorted(e)}, sort_keys=True, separators=(",", ":"))

def event_digest(e):
    return hashlib.sha256(canonical_payload(e).encode()).hexdigest()

def setup(events):
    db = sqlite3.connect(":memory:")
    db.executescript("""
      CREATE TABLE canonical_events (event_id TEXT PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL, value TEXT NOT NULL, cardinality TEXT NOT NULL, observed_at TEXT NOT NULL, reference_time TEXT NOT NULL, valid_from TEXT NOT NULL, supersedes_event_id TEXT, epistemic TEXT NOT NULL, source_digest TEXT NOT NULL);
      CREATE TABLE temporal_projection (source_event_id TEXT PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL, value TEXT NOT NULL, valid_from TEXT NOT NULL, valid_to TEXT, observed_at TEXT NOT NULL, reference_time TEXT NOT NULL, cardinality TEXT NOT NULL, epistemic TEXT NOT NULL, source_digest TEXT NOT NULL);
      CREATE INDEX projection_lookup ON temporal_projection(subject,predicate,valid_from,valid_to);
    """)
    for e in events:
        db.execute("INSERT INTO canonical_events VALUES (?,?,?,?,?,?,?,?,?,?,?)", (e["event_id"],e["subject"],e["predicate"],e["value"],e["cardinality"],e["observed_at"],e["reference_time"],e["valid_from"],e["supersedes_event_id"],e["epistemic"],event_digest(e)))
    rebuild(db)
    return db

def rebuild(db):
    db.execute("DELETE FROM temporal_projection")
    rows = db.execute("SELECT event_id,subject,predicate,value,cardinality,observed_at,reference_time,valid_from,supersedes_event_id,epistemic,source_digest FROM canonical_events ORDER BY event_id").fetchall()
    valid_to = {}
    for r in rows:
        if r[8] and db.execute("SELECT 1 FROM canonical_events WHERE event_id=?", (r[8],)).fetchone():
            valid_to[r[8]] = r[7]
    for r in rows:
        eid,subj,pred,val,card,obs,ref,vfrom,sup,epi,digest = r
        db.execute("INSERT INTO temporal_projection VALUES (?,?,?,?,?,?,?,?,?,?,?)", (eid,subj,pred,val,vfrom,valid_to.get(eid),obs,ref,card,epi,digest))
    db.commit()

def q_direct(db, subj, pred, at):
    rows=db.execute("SELECT event_id,value,valid_from,supersedes_event_id FROM canonical_events WHERE subject=? AND predicate=? AND valid_from<=? ORDER BY event_id", (subj,pred,at)).fetchall()
    ended={}
    for eid,vfrom,sup in db.execute("SELECT event_id,valid_from,supersedes_event_id FROM canonical_events"):
        if sup: ended[sup]=vfrom
    return [(eid,val) for eid,val,vfrom,sup in rows if ended.get(eid) is None or at < ended[eid]]

def q_proj(db, subj, pred, at):
    return db.execute("SELECT source_event_id,value FROM temporal_projection WHERE subject=? AND predicate=? AND valid_from<=? AND (valid_to IS NULL OR ?<valid_to) ORDER BY source_event_id", (subj,pred,at,at)).fetchall()

def normalized_projection_hash(db):
    rows=db.execute("SELECT source_event_id,subject,predicate,value,valid_from,valid_to,observed_at,reference_time,cardinality,epistemic,source_digest FROM temporal_projection ORDER BY source_event_id").fetchall()
    return hashlib.sha256(json.dumps(rows,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def run():
    db=setup(EVENTS)
    cases=[("service","mode","2026-01-15T00:00:00Z"),("service","mode","2026-02-15T00:00:00Z"),("auth","uses","2026-01-20T00:00:00Z"),("auth","uses","2026-02-20T00:00:00Z"),("deployment","region","2026-02-20T00:00:00Z"),("schema","version","2025-12-20T00:00:00Z")]
    query_results=[]
    for c in cases:
        d=q_direct(db,*c); p=q_proj(db,*c); assert d==p, (c,d,p); query_results.append(dict(query=c,direct=d,projection=p))
    assert q_proj(db,"auth","uses","2026-02-20T00:00:00Z")==[("E003","JWT"),("E004","session_tokens")]
    assert q_proj(db,"deployment","region","2026-02-20T00:00:00Z")==[("E005","us-east"),("E006","eu-west")]
    assert db.execute("SELECT observed_at,reference_time,valid_from FROM temporal_projection WHERE source_event_id='E007'").fetchone()==("2026-03-01T10:00:00Z","2025-12-15T00:00:00Z","2025-12-15T00:00:00Z")
    lineage_ok=all(db.execute("SELECT source_digest FROM canonical_events WHERE event_id=?", (eid,)).fetchone()[0]==digest for eid,digest in db.execute("SELECT source_event_id,source_digest FROM temporal_projection")); assert lineage_ok
    before=db.execute("SELECT count(*) FROM temporal_projection WHERE source_event_id='E006'").fetchone()[0]; db.execute("DELETE FROM canonical_events WHERE event_id='E006'"); db.commit(); rebuild(db); after=db.execute("SELECT count(*) FROM temporal_projection WHERE source_event_id='E006'").fetchone()[0]; assert (before,after)==(1,0)
    db1=setup(EVENTS); shuffled=list(EVENTS); random.Random(20260829).shuffle(shuffled); db2=setup(shuffled); h1=normalized_projection_hash(db1); h2=normalized_projection_hash(db2); assert h1==h2
    perf=[]
    for i in range(5000):
        g=i//5; prev=f"P{i-1:05d}" if i%5 else None
        perf.append(dict(event_id=f"P{i:05d}",subject=f"s{g}",predicate="state",value=str(i%5),cardinality="SINGLE",observed_at=f"2026-01-{1+(i%28):02d}T00:00:00Z",reference_time=f"2026-01-{1+(i%28):02d}T00:00:00Z",valid_from=f"2026-01-{1+(i%28):02d}T00:00:00Z",supersedes_event_id=prev,epistemic="OBSERVED"))
    pdb=setup(perf); queries=[(f"s{i%1000}","state","2026-01-29T00:00:00Z") for i in range(500)]; td=[]; tp=[]
    for q in queries:
        t=time.perf_counter_ns(); q_direct(pdb,*q); td.append((time.perf_counter_ns()-t)/1000); t=time.perf_counter_ns(); q_proj(pdb,*q); tp.append((time.perf_counter_ns()-t)/1000)
    def pct(xs,p): xs=sorted(xs); return xs[min(len(xs)-1,int((len(xs)-1)*p))]
    out={"schema":"TRIGGER6_GRAPHITI_TEMPORAL_PROJECTION_FIXTURE_RESULT/v1","tests":{"historical_current_query_equivalence":True,"false_supersession_prevented":True,"contradictions_preserved":True,"observed_reference_validity_times_distinct":True,"exact_lineage_roundtrip":lineage_ok,"projection_source_deletion_rebuild":{"before":before,"after":after},"deterministic_rebuild":{"hash_a":h1,"hash_b":h2,"equal":h1==h2}},"query_results":query_results,"microbenchmark_synthetic_only":{"rows":5000,"queries":500,"direct_us":{"median":statistics.median(td),"p95":pct(td,.95),"p99":pct(td,.99)},"projection_us":{"median":statistics.median(tp),"p95":pct(tp,.95),"p99":pct(tp,.99)},"projection_rows":pdb.execute("SELECT count(*) FROM temporal_projection").fetchone()[0],"canonical_rows":pdb.execute("SELECT count(*) FROM canonical_events").fetchone()[0]}}
    print(json.dumps(out,indent=2,sort_keys=True))
if __name__=="__main__": run()
