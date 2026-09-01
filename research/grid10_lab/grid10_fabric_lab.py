#!/usr/bin/env python3
"""GRID10 first laboratory prototype for Frankenstein 2.0.

This is a deliberately bounded adaptation of the canonical Clay GRID10 fabric donor.
It exercises the central control invariants with independent OS/process-capable SQLite/WAL
connections while remaining a sandbox-owned laboratory store.

It is NOT the canonical Clay/EntityOS S1 database, NOT effect authority, and NOT physical
GRID10 product credit. See README.md and PROVENANCE.json beside this file.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = "FRANKENSTEIN_GRID10_LAB_FABRIC/v1"
RESULT_SCHEMA = "NODE_RESULT/v1"
SUMMARY_SCHEMA = "COORDINATOR_SUMMARY/v1"
LEASE_SCHEMA = "GRID_COORDINATOR_LEASE/v2"
LEASE_TTL_SECONDS = 8.0


class FabricError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


@dataclass(frozen=True)
class Snapshot:
    epoch: int
    generation: int
    state_digest: str


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path), isolation_level=None, timeout=10.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=10000")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS nodes(
          node_id TEXT PRIMARY KEY,
          capability TEXT NOT NULL,
          healthy INTEGER NOT NULL,
          pid INTEGER NOT NULL,
          last_seen_ts REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks(
          task_id TEXT PRIMARY KEY,
          scope TEXT NOT NULL,
          capability TEXT NOT NULL,
          status TEXT NOT NULL,
          claimed_by TEXT,
          payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scopes(
          scope TEXT PRIMARY KEY,
          summary_json TEXT NOT NULL,
          evidence_count INTEGER NOT NULL,
          last_writer_lease_id TEXT,
          last_result_digest TEXT,
          state_epoch INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS leases(
          lease_id TEXT PRIMARY KEY,
          node_id TEXT NOT NULL,
          scope TEXT NOT NULL,
          generation INTEGER NOT NULL,
          token_digest TEXT NOT NULL,
          granted_ts REAL NOT NULL,
          valid INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS admitted_results(
          result_digest TEXT PRIMARY KEY,
          source_node_id TEXT NOT NULL,
          coordinator_lease_id TEXT NOT NULL,
          scope TEXT NOT NULL,
          admitted_epoch INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS outbox(
          packet_digest TEXT PRIMARY KEY,
          scope TEXT NOT NULL,
          packet_json TEXT NOT NULL,
          consumed INTEGER NOT NULL DEFAULT 0,
          submitted_ts REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rejected_writes(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          actor TEXT NOT NULL,
          reason TEXT NOT NULL,
          ts REAL NOT NULL
        );
        """
    )
    con.execute("INSERT OR IGNORE INTO meta VALUES('epoch','1')")
    con.execute("INSERT OR IGNORE INTO meta VALUES('generation','1')")


class Fabric:
    def __init__(self, path: Path):
        self.path = Path(path)
        con = connect(self.path)
        try:
            init_schema(con)
        finally:
            con.close()

    @staticmethod
    def _meta_int(con: sqlite3.Connection, key: str) -> int:
        row = con.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        if row is None:
            raise FabricError(f"MISSING_META:{key}")
        return int(row["v"])

    def _bump_epoch(self, con: sqlite3.Connection) -> int:
        epoch = self._meta_int(con, "epoch") + 1
        con.execute("UPDATE meta SET v=? WHERE k='epoch'", (str(epoch),))
        return epoch

    @staticmethod
    def _state_digest(con: sqlite3.Connection, epoch: int, generation: int) -> str:
        tasks = [dict(r) for r in con.execute("SELECT * FROM tasks ORDER BY task_id")]
        scopes = [dict(r) for r in con.execute("SELECT * FROM scopes ORDER BY scope")]
        leases = [dict(r) for r in con.execute(
            "SELECT lease_id,node_id,scope,generation,valid FROM leases ORDER BY lease_id"
        )]
        return digest({
            "epoch": epoch,
            "generation": generation,
            "tasks": tasks,
            "scopes": scopes,
            "leases": leases,
        })

    def snapshot(self) -> Snapshot:
        con = connect(self.path)
        try:
            epoch = self._meta_int(con, "epoch")
            generation = self._meta_int(con, "generation")
            return Snapshot(epoch, generation, self._state_digest(con, epoch, generation))
        finally:
            con.close()

    def runtime_join(self, node_id: str, capability: str, pid: int) -> None:
        con = connect(self.path)
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                "INSERT OR REPLACE INTO nodes VALUES(?,?,?,?,?)",
                (node_id, capability, 1, pid, time.time()),
            )
            self._bump_epoch(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def runtime_heartbeat(self, node_id: str, healthy: bool = True) -> None:
        con = connect(self.path)
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                "UPDATE nodes SET healthy=?,last_seen_ts=? WHERE node_id=?",
                (1 if healthy else 0, time.time(), node_id),
            )
            self._bump_epoch(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def seed_scope(self, scope: str) -> None:
        con = connect(self.path)
        try:
            con.execute("BEGIN IMMEDIATE")
            epoch = self._meta_int(con, "epoch")
            con.execute(
                "INSERT OR REPLACE INTO scopes VALUES(?,?,?,?,?,?)",
                (scope, canonical_json({"status": "open"}), 0, None, None, epoch),
            )
            self._bump_epoch(con)
            con.execute("COMMIT")
        finally:
            con.close()

    def seed_task(self, task_id: str, scope: str, capability: str, payload: Any) -> None:
        con = connect(self.path)
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                "INSERT OR REPLACE INTO tasks VALUES(?,?,?,?,?,?)",
                (task_id, scope, capability, "OPEN", None, canonical_json(payload)),
            )
            self._bump_epoch(con)
            con.execute("COMMIT")
        finally:
            con.close()

    def runtime_claim_task(self, task_id: str, node_id: str, *, expected_epoch: int) -> None:
        con = connect(self.path)
        try:
            con.execute("BEGIN IMMEDIATE")
            if self._meta_int(con, "epoch") != expected_epoch:
                raise FabricError("TASK_CLAIM_CAS_FAILED")
            row = con.execute("SELECT status,claimed_by FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if row is None or row["status"] != "OPEN" or row["claimed_by"] is not None:
                raise FabricError("TASK_NOT_CLAIMABLE")
            con.execute("UPDATE tasks SET status='CLAIMED',claimed_by=? WHERE task_id=?", (node_id, task_id))
            self._bump_epoch(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def reclaim_stale_claims(self, *, stale_after_seconds: float = 15.0) -> list[str]:
        con = connect(self.path)
        try:
            con.execute("BEGIN IMMEDIATE")
            now = time.time()
            pending = set()
            for row in con.execute("SELECT packet_json FROM outbox WHERE consumed=0"):
                try:
                    task_id = (json.loads(row["packet_json"]).get("payload") or {}).get("task_id")
                    if task_id:
                        pending.add(task_id)
                except (ValueError, TypeError):
                    continue
            reclaimed: list[str] = []
            for row in con.execute("SELECT task_id,claimed_by FROM tasks WHERE status='CLAIMED'"):
                if row["task_id"] in pending:
                    continue
                node = con.execute(
                    "SELECT healthy,last_seen_ts FROM nodes WHERE node_id=?", (row["claimed_by"],)
                ).fetchone()
                stale = node is None or not int(node["healthy"]) or now - float(node["last_seen_ts"]) > stale_after_seconds
                if stale:
                    reclaimed.append(row["task_id"])
            for task_id in reclaimed:
                con.execute("UPDATE tasks SET status='OPEN',claimed_by=NULL WHERE task_id=?", (task_id,))
            if reclaimed:
                self._bump_epoch(con)
            con.execute("COMMIT")
            return reclaimed
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def ordinary_write_attempt(self, actor: str) -> None:
        con = connect(self.path)
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute("INSERT INTO rejected_writes(actor,reason,ts) VALUES(?,?,?)", (
                actor, "ORDINARY_NODE_S1_WRITE_FORBIDDEN", time.time()
            ))
            con.execute("COMMIT")
        finally:
            con.close()
        raise FabricError("ORDINARY_NODE_S1_WRITE_FORBIDDEN")

    def elect_coordinator(self, scope: str, candidate_node_ids: list[str]) -> tuple[dict[str, Any], str] | None:
        con = connect(self.path)
        try:
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute(
                "SELECT lease_id,granted_ts FROM leases WHERE scope=? AND valid=1", (scope,)
            ).fetchone()
            if existing is not None:
                if time.time() - float(existing["granted_ts"]) <= LEASE_TTL_SECONDS:
                    con.execute("ROLLBACK")
                    return None
                con.execute("UPDATE leases SET valid=0 WHERE lease_id=?", (existing["lease_id"],))
            generation = self._meta_int(con, "generation")
            healthy = []
            for node_id in candidate_node_ids:
                row = con.execute("SELECT healthy FROM nodes WHERE node_id=?", (node_id,)).fetchone()
                if row is not None and int(row["healthy"]) == 1:
                    healthy.append(node_id)
            if not healthy:
                raise FabricError("NO_HEALTHY_COORDINATOR_CANDIDATE")
            node_id = sorted(healthy, key=lambda n: digest({"scope": scope, "generation": generation, "node": n}))[0]
            token = digest({"scope": scope, "generation": generation, "node": node_id, "ts": time.time_ns()})
            lease_id = "lease-" + digest(token)[:24]
            con.execute(
                "INSERT INTO leases VALUES(?,?,?,?,?,?,1)",
                (lease_id, node_id, scope, generation, digest(token), time.time()),
            )
            self._bump_epoch(con)
            con.execute("COMMIT")
            return ({"schema": LEASE_SCHEMA, "lease_id": lease_id, "node_id": node_id,
                     "scope": scope, "generation": generation}, token)
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def revoke_lease(self, lease_id: str) -> None:
        con = connect(self.path)
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute("UPDATE leases SET valid=0 WHERE lease_id=?", (lease_id,))
            self._bump_epoch(con)
            con.execute("COMMIT")
        finally:
            con.close()

    def emit_node_result(self, packet: dict[str, Any]) -> None:
        con = connect(self.path)
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                "INSERT OR IGNORE INTO outbox VALUES(?,?,?,0,?)",
                (packet["packet_digest"], packet["scope"], canonical_json(packet), time.time()),
            )
            con.execute("COMMIT")
        finally:
            con.close()

    def coordinator_commit(
        self,
        *,
        lease: dict[str, Any],
        token: str,
        packet: dict[str, Any],
        expected_epoch: int,
        expected_digest: str,
    ) -> dict[str, Any]:
        con = connect(self.path)
        try:
            con.execute("BEGIN IMMEDIATE")
            lrow = con.execute("SELECT * FROM leases WHERE lease_id=?", (lease["lease_id"],)).fetchone()
            if lrow is None or int(lrow["valid"]) != 1:
                raise FabricError("COORDINATOR_LEASE_INVALID")
            if lrow["node_id"] != lease["node_id"] or lrow["token_digest"] != digest(token):
                raise FabricError("COORDINATOR_LEASE_BINDING_INVALID")
            if lrow["scope"] != packet.get("scope"):
                raise FabricError("COORDINATOR_SCOPE_VIOLATION")
            current_epoch = self._meta_int(con, "epoch")
            generation = self._meta_int(con, "generation")
            if int(lrow["generation"]) != generation:
                raise FabricError("COORDINATOR_LEASE_STALE_GENERATION")
            if time.time() - float(lrow["granted_ts"]) > LEASE_TTL_SECONDS:
                raise FabricError("COORDINATOR_LEASE_EXPIRED")
            if expected_epoch != current_epoch:
                raise FabricError("S1_COMPARE_AND_SWAP_FAILED")
            if expected_digest != self._state_digest(con, current_epoch, generation):
                raise FabricError("S1_COMPARE_AND_SWAP_DIGEST_FAILED")
            if packet.get("generation") != generation:
                raise FabricError("RESULT_STALE_GENERATION")
            if packet.get("state_epoch", -1) > current_epoch:
                raise FabricError("RESULT_FUTURE_EPOCH")
            schema = packet.get("schema")
            if schema not in (RESULT_SCHEMA, SUMMARY_SCHEMA):
                raise FabricError("PACKET_SCHEMA_INVALID")
            if schema == RESULT_SCHEMA and packet.get("source_kind") != "ORDINARY_NODE":
                raise FabricError("ORDINARY_RESULT_SOURCE_KIND_INVALID")
            if schema == SUMMARY_SCHEMA and packet.get("source_kind") != "COORDINATOR":
                raise FabricError("COORDINATOR_SUMMARY_SOURCE_KIND_INVALID")
            core = {k: packet[k] for k in packet if k not in ("packet_digest", "s1_write_intent")}
            if packet.get("packet_digest") != digest(core):
                raise FabricError("PACKET_DIGEST_MISMATCH")
            if packet.get("s1_write_intent") is not False:
                raise FabricError("SOURCE_PACKET_MUST_NOT_SELF_WRITE")
            if con.execute("SELECT 1 FROM admitted_results WHERE result_digest=?", (packet["packet_digest"],)).fetchone():
                raise FabricError("DUPLICATE_RESULT_REJECTED")
            scope = packet["scope"]
            row = con.execute("SELECT summary_json FROM scopes WHERE scope=?", (scope,)).fetchone()
            if row is None:
                raise FabricError("UNKNOWN_SCOPE")
            new_epoch = current_epoch + 1
            summary = {"previous": json.loads(row["summary_json"]), "latest": packet["payload"], "source_schema": schema}
            con.execute(
                "UPDATE scopes SET summary_json=?,evidence_count=evidence_count+1,last_writer_lease_id=?,last_result_digest=?,state_epoch=? WHERE scope=?",
                (canonical_json(summary), lease["lease_id"], packet["packet_digest"], new_epoch, scope),
            )
            con.execute("INSERT INTO admitted_results VALUES(?,?,?,?,?)", (
                packet["packet_digest"], packet["source_node_id"], lease["lease_id"], scope, new_epoch
            ))
            con.execute("UPDATE meta SET v=? WHERE k='epoch'", (str(new_epoch),))
            con.execute("COMMIT")
            return {"scope": scope, "new_epoch": new_epoch, "canonical_truth": False, "effect_authority": False}
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()


def result_packet(node_id: str, snap: Snapshot, scope: str, payload: Any) -> dict[str, Any]:
    core = {
        "schema": RESULT_SCHEMA,
        "source_kind": "ORDINARY_NODE",
        "source_node_id": node_id,
        "scope": scope,
        "generation": snap.generation,
        "state_epoch": snap.epoch,
        "state_digest": snap.state_digest,
        "payload": payload,
    }
    return {**core, "packet_digest": digest(core), "s1_write_intent": False}
