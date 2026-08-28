#!/usr/bin/env python3
"""Materialize and maintain the Frankenstein 2.0 Trigger-6 research database.

Stdlib-only by design. The DB is a research/evidence index, not canonical world truth.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, pathlib, sqlite3

SCHEMA = r'''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS architecture_snapshots(
 snapshot_id TEXT PRIMARY KEY,created_at_utc TEXT NOT NULL,f2_sha TEXT NOT NULL,research_sha TEXT NOT NULL,
 trigger4_checkpoint_ref TEXT,trigger5_ingest_ref TEXT,delta_digest TEXT,status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS seeds(
 seed_id TEXT PRIMARY KEY,repo TEXT NOT NULL,url TEXT NOT NULL,user_hypothesis TEXT NOT NULL,
 counterhypothesis TEXT NOT NULL,initial_source_type TEXT,initial_source_sha TEXT,targets_json TEXT NOT NULL,
 priority INTEGER NOT NULL,status TEXT NOT NULL,last_snapshot_id TEXT,created_at_utc TEXT NOT NULL,updated_at_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS hypotheses(
 hypothesis_id TEXT PRIMARY KEY,seed_id TEXT,statement TEXT NOT NULL,counterhypothesis TEXT NOT NULL,
 affected_modules_json TEXT NOT NULL,architecture_snapshot_id TEXT NOT NULL,status TEXT NOT NULL,evidence_grade INTEGER NOT NULL DEFAULT 0,
 created_at_utc TEXT NOT NULL,updated_at_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS architecture_deltas(
 delta_id TEXT PRIMARY KEY,snapshot_id TEXT NOT NULL,source_stream TEXT NOT NULL,source_ref TEXT NOT NULL,
 affected_modules_json TEXT NOT NULL,delta_class TEXT NOT NULL,summary TEXT NOT NULL,impact_on_research TEXT NOT NULL,
 created_at_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS experiments(
 experiment_id TEXT PRIMARY KEY,hypothesis_id TEXT NOT NULL,worker_role TEXT NOT NULL,plan TEXT NOT NULL,
 baseline TEXT NOT NULL,required_measurements_json TEXT NOT NULL,acceptance_rule TEXT NOT NULL,status TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,updated_at_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence(
 evidence_id TEXT PRIMARY KEY,hypothesis_id TEXT,source_repo TEXT,source_sha TEXT,artifact_ref TEXT NOT NULL,
 evidence_type TEXT NOT NULL,direction TEXT NOT NULL,grade INTEGER NOT NULL,summary TEXT NOT NULL,created_at_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS worker_cycles(
 cycle_slot_id TEXT PRIMARY KEY,cycle_id TEXT NOT NULL,slot INTEGER NOT NULL,role TEXT NOT NULL,status TEXT NOT NULL,
 claimed_seed_id TEXT,claimed_hypothesis_id TEXT,architecture_snapshot_id TEXT NOT NULL,output_ref TEXT,created_at_utc TEXT NOT NULL,updated_at_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS build_candidates(
 candidate_id TEXT PRIMARY KEY,hypothesis_id TEXT NOT NULL,status TEXT NOT NULL,source_repo TEXT NOT NULL,source_sha TEXT,
 source_tree_sha TEXT,license TEXT,integration_class TEXT,target_workpackages_json TEXT NOT NULL,target_modules_json TEXT NOT NULL,
 package_ref TEXT,trigger4_inbox_ref TEXT,architecture_snapshot_id TEXT NOT NULL,net_benefit_summary TEXT,created_at_utc TEXT NOT NULL,updated_at_utc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trigger4_feedback(
 feedback_id TEXT PRIMARY KEY,candidate_id TEXT NOT NULL,workpackage_id TEXT,vps_run_id TEXT,result_status TEXT NOT NULL,
 result_ref TEXT NOT NULL,measurements_ref TEXT,root_cause_ref TEXT,created_at_utc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_hypothesis_status ON hypotheses(status);
CREATE INDEX IF NOT EXISTS idx_seed_status_priority ON seeds(status,priority DESC);
CREATE INDEX IF NOT EXISTS idx_delta_snapshot ON architecture_deltas(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_candidate_status ON build_candidates(status);
'''

ROLES = [
 "ARCHITECTURE_DELTA_FUSER","DISCOVERY_SCOUT","SOURCE_ARCHAEOLOGIST",
 "EXPERIMENTAL_FALSIFIER","INTEGRATION_DISTILLER"
]

def utcnow():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')

def stable_snapshot_id(f2_sha, research_sha, created):
    stamp = created.replace('-','').replace(':','').replace('Z','')[:15]
    return f"ADF-{stamp}-{f2_sha[:8]}-{research_sha[:8]}"

def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db=sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db

def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))

def bootstrap(db, manifest):
    created=manifest['created_at_utc']
    a=manifest['architecture_snapshot']
    sid=stable_snapshot_id(a['f2_sha_at_seed'],a['research_entity_sha_at_seed'],created)
    db.execute('INSERT OR IGNORE INTO architecture_snapshots VALUES(?,?,?,?,?,?,?,?)',(
        sid,created,a['f2_sha_at_seed'],a['research_entity_sha_at_seed'],
        'checkpoints/CURRENT.json','research_entity/frankenstein_architecture_ingest/INGEST_STATE.json',None,'BOOTSTRAP'))
    for s in manifest['seeds']:
        stmt=s['hypothesis']; counter=s['counterhypothesis']; targets=s.get('targets',[])
        src=s.get('initial_source',{})
        db.execute('''INSERT INTO seeds VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(seed_id) DO UPDATE SET repo=excluded.repo,url=excluded.url,user_hypothesis=excluded.user_hypothesis,
          counterhypothesis=excluded.counterhypothesis,initial_source_type=excluded.initial_source_type,
          initial_source_sha=excluded.initial_source_sha,targets_json=excluded.targets_json,priority=excluded.priority,
          updated_at_utc=excluded.updated_at_utc''',(
          s['seed_id'],s['repo'],s['url'],stmt,counter,src.get('type'),src.get('blob_sha'),json.dumps(targets),
          int(s.get('priority',50)),'PENDING_RESEARCH',sid,created,created))
        hid='R6-H-'+s['seed_id'].split('-')[-1]
        db.execute('''INSERT OR IGNORE INTO hypotheses VALUES(?,?,?,?,?,?,?,?,?,?)''',(
          hid,s['seed_id'],stmt,counter,json.dumps(targets),sid,'PENDING_FALSIFICATION',0,created,created))
    cycle='R6-CYCLE-0001'
    for slot,role in enumerate(ROLES,1):
        cid=f'{cycle}-SLOT-{slot}'
        db.execute('INSERT OR IGNORE INTO worker_cycles VALUES(?,?,?,?,?,?,?,?,?,?,?)',(
          cid,cycle,slot,role,'OPEN',None,None,sid,None,created,created))
    for k,v in {
      'schema':'FRANKENSTEIN2_TRIGGER6_PENDING_RESEARCH/v1',
      'canonical_repo':'gschaidergabriel/frankenstein-2.0',
      'mirror_repo':'gschaidergabriel/clay-global-research-entity',
      'architecture_fusion_required':'true','trigger4_handoff_required':'true','trigger5_live_ingest_required':'true'
    }.items(): db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(k,v))
    db.commit()
    return sid

def add_snapshot(db,args):
    created=args.timestamp or utcnow(); sid=args.snapshot_id or stable_snapshot_id(args.f2_sha,args.research_sha,created)
    db.execute('INSERT INTO architecture_snapshots VALUES(?,?,?,?,?,?,?,?)',(
      sid,created,args.f2_sha,args.research_sha,args.trigger4_ref,args.trigger5_ref,args.delta_digest,args.status))
    db.commit(); print(sid)

def add_delta(db,args):
    db.execute('INSERT INTO architecture_deltas VALUES(?,?,?,?,?,?,?,?,?)',(
      args.delta_id,args.snapshot_id,args.source_stream,args.source_ref,json.dumps(args.module),args.delta_class,args.summary,args.impact,args.timestamp or utcnow()))
    if args.mark_stale:
        for module in args.module:
            rows=db.execute("SELECT hypothesis_id,affected_modules_json FROM hypotheses WHERE status NOT IN ('REJECTED','F2_ACCEPTED')").fetchall()
            for hid,mods in rows:
                if module in json.loads(mods):
                    db.execute("UPDATE hypotheses SET status='STALE_REVIEW_REQUIRED',updated_at_utc=? WHERE hypothesis_id=?",(utcnow(),hid))
    db.commit()

def add_evidence(db,args):
    db.execute('INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?)',(
      args.evidence_id,args.hypothesis_id,args.source_repo,args.source_sha,args.artifact_ref,args.evidence_type,args.direction,args.grade,args.summary,args.timestamp or utcnow()))
    db.execute('UPDATE hypotheses SET evidence_grade=MAX(evidence_grade,?),updated_at_utc=? WHERE hypothesis_id=?',(args.grade,utcnow(),args.hypothesis_id))
    db.commit()

def claim(db,args):
    ts=utcnow()
    row=db.execute("SELECT cycle_slot_id,role FROM worker_cycles WHERE status='OPEN' ORDER BY slot LIMIT 1").fetchone()
    if not row: raise SystemExit('no OPEN Trigger-6 slot')
    cid,role=row
    db.execute("UPDATE worker_cycles SET status='CLAIMED',claimed_seed_id=?,claimed_hypothesis_id=?,architecture_snapshot_id=?,updated_at_utc=? WHERE cycle_slot_id=?",
      (args.seed_id,args.hypothesis_id,args.snapshot_id,ts,cid)); db.commit()
    print(json.dumps({'cycle_slot_id':cid,'role':role,'seed_id':args.seed_id,'hypothesis_id':args.hypothesis_id,'snapshot_id':args.snapshot_id}))

def verify(db):
    qc=db.execute('PRAGMA quick_check').fetchone()[0]
    bad=db.execute("SELECT COUNT(*) FROM build_candidates WHERE status='F2_ACCEPTED' AND trigger4_inbox_ref IS NULL").fetchone()[0]
    print(json.dumps({'quick_check':qc,'invalid_accepted_candidates':bad,'sha256':None}))
    if qc!='ok' or bad: raise SystemExit(2)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--db',default='research/tool_intelligence/pending_research.sqlite')
    sp=p.add_subparsers(dest='cmd',required=True)
    b=sp.add_parser('bootstrap'); b.add_argument('--manifest',default='research/tool_intelligence/SEED_MANIFEST_2026-08-29.json')
    s=sp.add_parser('snapshot'); s.add_argument('--snapshot-id'); s.add_argument('--f2-sha',required=True); s.add_argument('--research-sha',required=True); s.add_argument('--trigger4-ref'); s.add_argument('--trigger5-ref'); s.add_argument('--delta-digest'); s.add_argument('--status',default='CURRENT'); s.add_argument('--timestamp')
    d=sp.add_parser('delta'); d.add_argument('--delta-id',required=True); d.add_argument('--snapshot-id',required=True); d.add_argument('--source-stream',required=True); d.add_argument('--source-ref',required=True); d.add_argument('--module',action='append',required=True); d.add_argument('--delta-class',required=True); d.add_argument('--summary',required=True); d.add_argument('--impact',required=True); d.add_argument('--timestamp'); d.add_argument('--mark-stale',action='store_true')
    e=sp.add_parser('evidence'); e.add_argument('--evidence-id',required=True); e.add_argument('--hypothesis-id',required=True); e.add_argument('--source-repo'); e.add_argument('--source-sha'); e.add_argument('--artifact-ref',required=True); e.add_argument('--evidence-type',required=True); e.add_argument('--direction',choices=['SUPPORT','COUNTER','NEUTRAL'],required=True); e.add_argument('--grade',type=int,required=True); e.add_argument('--summary',required=True); e.add_argument('--timestamp')
    c=sp.add_parser('claim'); c.add_argument('--seed-id',required=True); c.add_argument('--hypothesis-id',required=True); c.add_argument('--snapshot-id',required=True)
    sp.add_parser('verify')
    args=p.parse_args(); db=connect(pathlib.Path(args.db))
    if args.cmd=='bootstrap': print(bootstrap(db,load_json(pathlib.Path(args.manifest))))
    elif args.cmd=='snapshot': add_snapshot(db,args)
    elif args.cmd=='delta': add_delta(db,args)
    elif args.cmd=='evidence': add_evidence(db,args)
    elif args.cmd=='claim': claim(db,args)
    elif args.cmd=='verify': verify(db)
    db.close()
if __name__=='__main__': main()
