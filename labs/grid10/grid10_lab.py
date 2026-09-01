#!/usr/bin/env python3
"""Isolated GRID10 laboratory fabric for Frankenstein 2.0.

Standard-library-only SQLite/WAL prototype. It never connects to production
state and never mints product/runtime/GWT/J-Space/effect/training credit.
"""
from __future__ import annotations
import hashlib, json, os, sqlite3, time, uuid
from pathlib import Path
from typing import Any

SCHEMA = "F2_GRID10_LAB/v1"
RESULT_SCHEMA = "F2_GRID10_NODE_RESULT/v1"

class Grid10Error(RuntimeError): pass

def _j(v: Any) -> str: return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def _dg(v: Any) -> str: return hashlib.sha256(_j(v).encode()).hexdigest()
def _con(path: Path) -> sqlite3.Connection:
    c=sqlite3.connect(str(path), isolation_level=None, timeout=10.0); c.row_factory=sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA busy_timeout=10000"); c.execute("PRAGMA synchronous=NORMAL")
    return c

class Grid10LabFabric:
    def __init__(self, db_path: str | Path):
        self.db=Path(db_path); self.db.parent.mkdir(parents=True, exist_ok=True); c=_con(self.db)
        try:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY,v TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS nodes(node_id TEXT PRIMARY KEY,pid INTEGER NOT NULL,healthy INTEGER NOT NULL,last_seen REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks(task_id TEXT PRIMARY KEY,scope TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,claimed_by TEXT,claim_generation INTEGER);
            CREATE TABLE IF NOT EXISTS leases(lease_id TEXT PRIMARY KEY,scope TEXT NOT NULL,node_id TEXT NOT NULL,generation INTEGER NOT NULL,token_digest TEXT NOT NULL,expires REAL NOT NULL,valid INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox(result_digest TEXT PRIMARY KEY,scope TEXT NOT NULL,task_id TEXT NOT NULL,node_id TEXT NOT NULL,result_json TEXT NOT NULL,consumed INTEGER NOT NULL DEFAULT 0,submitted REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS committed(result_digest TEXT PRIMARY KEY,task_id TEXT UNIQUE NOT NULL,scope TEXT NOT NULL,source_node_id TEXT NOT NULL,lease_id TEXT NOT NULL,result_json TEXT NOT NULL);
            """)
            c.execute("INSERT OR IGNORE INTO meta VALUES('epoch','1')"); c.execute("INSERT OR IGNORE INTO meta VALUES('generation','1')"); c.execute("INSERT OR IGNORE INTO meta VALUES('schema',?)",(SCHEMA,))
        finally: c.close()
    @staticmethod
    def _m(c,k):
        r=c.execute("SELECT v FROM meta WHERE k=?",(k,)).fetchone()
        if not r: raise Grid10Error(f"MISSING_META:{k}")
        return int(r["v"])
    @classmethod
    def _bump(cls,c):
        e=cls._m(c,"epoch")+1; c.execute("UPDATE meta SET v=? WHERE k='epoch'",(str(e),)); return e
    def _tx(self, fn):
        c=_con(self.db)
        try:
            c.execute("BEGIN IMMEDIATE"); out=fn(c); c.execute("COMMIT"); return out
        except Exception:
            if c.in_transaction: c.execute("ROLLBACK")
            raise
        finally: c.close()
    def join(self,node_id,pid=None):
        def f(c): c.execute("INSERT OR REPLACE INTO nodes VALUES(?,?,1,?)",(node_id,os.getpid() if pid is None else pid,time.time())); self._bump(c)
        self._tx(f)
    def heartbeat(self,node_id,healthy=True):
        def f(c):
            if c.execute("UPDATE nodes SET healthy=?,last_seen=? WHERE node_id=?",(int(healthy),time.time(),node_id)).rowcount!=1: raise Grid10Error("UNKNOWN_NODE")
            self._bump(c)
        self._tx(f)
    def seed(self,task_id,scope,payload):
        self._tx(lambda c:(c.execute("INSERT INTO tasks VALUES(?,?,?,'OPEN',NULL,NULL)",(task_id,scope,_j(payload))),self._bump(c)))
    def snapshot(self):
        c=_con(self.db)
        try:
            e=self._m(c,"epoch"); g=self._m(c,"generation")
            tasks=[dict(r) for r in c.execute("SELECT * FROM tasks ORDER BY task_id")]; nodes=[dict(r) for r in c.execute("SELECT * FROM nodes ORDER BY node_id")]
            committed=[dict(r) for r in c.execute("SELECT * FROM committed ORDER BY task_id")]
            return {"schema":SCHEMA,"epoch":e,"generation":g,"tasks":tasks,"nodes":nodes,"committed":committed,"state_digest":_dg({"epoch":e,"generation":g,"tasks":tasks,"committed":committed})}
        finally: c.close()
    def claim(self,task_id,node_id,expected_epoch):
        def f(c):
            if self._m(c,"epoch")!=expected_epoch: raise Grid10Error("TASK_CLAIM_CAS_FAILED")
            n=c.execute("SELECT healthy FROM nodes WHERE node_id=?",(node_id,)).fetchone(); t=c.execute("SELECT status,claimed_by FROM tasks WHERE task_id=?",(task_id,)).fetchone()
            if not n or not n["healthy"]: raise Grid10Error("NODE_NOT_HEALTHY")
            if not t or t["status"]!="OPEN" or t["claimed_by"] is not None: raise Grid10Error("TASK_NOT_CLAIMABLE")
            g=self._m(c,"generation"); c.execute("UPDATE tasks SET status='CLAIMED',claimed_by=?,claim_generation=? WHERE task_id=?",(node_id,g,task_id)); self._bump(c); return g
        return self._tx(f)
    def emit(self,task_id,node_id,value):
        def f(c):
            t=c.execute("SELECT scope,status,claimed_by,claim_generation FROM tasks WHERE task_id=?",(task_id,)).fetchone()
            if not t or t["status"]!="CLAIMED" or t["claimed_by"]!=node_id: raise Grid10Error("RESULT_WITHOUT_OWNED_CLAIM")
            p={"schema":RESULT_SCHEMA,"task_id":task_id,"scope":t["scope"],"node_id":node_id,"claim_generation":t["claim_generation"],"value":value}; d=_dg(p)
            c.execute("INSERT OR IGNORE INTO outbox VALUES(?,?,?,?,?,0,?)",(d,t["scope"],task_id,node_id,_j(p),time.time())); return d
        return self._tx(f)
    def lease(self,scope,node_id,ttl=5.0):
        if ttl<=0: raise Grid10Error("INVALID_LEASE_TTL")
        token=uuid.uuid4().hex; lid=uuid.uuid4().hex
        def f(c):
            n=c.execute("SELECT healthy FROM nodes WHERE node_id=?",(node_id,)).fetchone()
            if not n or not n["healthy"]: raise Grid10Error("COORDINATOR_NODE_NOT_HEALTHY")
            g=self._m(c,"generation"); c.execute("UPDATE leases SET valid=0 WHERE scope=? AND valid=1",(scope,)); exp=time.time()+ttl
            c.execute("INSERT INTO leases VALUES(?,?,?,?,?,?,1)",(lid,scope,node_id,g,_dg(token),exp)); self._bump(c); return {"lease_id":lid,"scope":scope,"node_id":node_id,"generation":g,"expires":exp}
        return self._tx(f),token
    def commit(self,scope,lease,token,expected_epoch):
        def f(c):
            if self._m(c,"epoch")!=expected_epoch: raise Grid10Error("COORDINATOR_COMMIT_CAS_FAILED")
            g=self._m(c,"generation"); l=c.execute("SELECT * FROM leases WHERE lease_id=?",(lease["lease_id"],)).fetchone()
            if not l or not l["valid"]: raise Grid10Error("LEASE_NOT_VALID")
            if l["scope"]!=scope or l["generation"]!=g: raise Grid10Error("LEASE_SCOPE_OR_GENERATION_MISMATCH")
            if l["expires"]<=time.time(): raise Grid10Error("LEASE_EXPIRED")
            if l["token_digest"]!=_dg(token): raise Grid10Error("LEASE_TOKEN_MISMATCH")
            done=[]
            for r in c.execute("SELECT * FROM outbox WHERE scope=? AND consumed=0 ORDER BY submitted,result_digest",(scope,)).fetchall():
                p=json.loads(r["result_json"])
                if p["claim_generation"]!=g: continue
                if c.execute("SELECT 1 FROM committed WHERE task_id=?",(r["task_id"],)).fetchone(): c.execute("UPDATE outbox SET consumed=1 WHERE result_digest=?",(r["result_digest"],)); continue
                c.execute("INSERT INTO committed VALUES(?,?,?,?,?,?)",(r["result_digest"],r["task_id"],scope,r["node_id"],lease["lease_id"],r["result_json"])); c.execute("UPDATE tasks SET status='DONE' WHERE task_id=?",(r["task_id"],)); c.execute("UPDATE outbox SET consumed=1 WHERE result_digest=?",(r["result_digest"],)); self._bump(c); done.append(r["result_digest"])
            return done
        return self._tx(f)
    def recover_stale(self,stale_after=15.0):
        if stale_after<0: raise Grid10Error("INVALID_STALE_THRESHOLD")
        def f(c):
            now=time.time(); pending={r["task_id"] for r in c.execute("SELECT task_id FROM outbox WHERE consumed=0")}; out=[]
            for t in c.execute("SELECT task_id,claimed_by FROM tasks WHERE status='CLAIMED'").fetchall():
                if t["task_id"] in pending: continue
                n=c.execute("SELECT healthy,last_seen FROM nodes WHERE node_id=?",(t["claimed_by"],)).fetchone(); stale=(not n or not n["healthy"] or now-n["last_seen"]>=stale_after)
                if stale: c.execute("UPDATE tasks SET status='OPEN',claimed_by=NULL,claim_generation=NULL WHERE task_id=?",(t["task_id"],)); out.append(t["task_id"])
            if out: self._bump(c)
            return out
        return self._tx(f)
    def restart_generation(self):
        def f(c):
            g=self._m(c,"generation")+1; c.execute("UPDATE meta SET v=? WHERE k='generation'",(str(g),)); c.execute("UPDATE leases SET valid=0 WHERE valid=1"); self._bump(c); return g
        return self._tx(f)
