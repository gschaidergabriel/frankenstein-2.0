from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid


class RetryIdentityMismatch(RuntimeError):
    pass


class OperationFence:
    """Research-only fail-closed prototype for direct episode_id=None retry identity."""

    BLOCKING_STATES = {"PENDING", "DISPATCH_STARTED", "UNKNOWN"}
    TERMINAL_REUSE_STATES = {"VERIFIED_APPLIED"}

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS effect_operations (
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                operation_retry_id TEXT NOT NULL,
                operation_payload_sha256 TEXT NOT NULL,
                state TEXT NOT NULL,
                current_attempt_id TEXT,
                current_effect_id TEXT,
                verification_evidence_ref TEXT,
                PRIMARY KEY (user_id, session_id, operation_retry_id)
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS effect_attempts (
                attempt_id TEXT PRIMARY KEY,
                effect_id TEXT UNIQUE NOT NULL,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                operation_retry_id TEXT NOT NULL,
                dispatch_state TEXT NOT NULL,
                outcome_certainty TEXT NOT NULL,
                FOREIGN KEY (user_id, session_id, operation_retry_id)
                    REFERENCES effect_operations(user_id, session_id, operation_retry_id)
            )
            """
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    @staticmethod
    def payload_digest(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def begin_attempt(
        self,
        *,
        user_id: str,
        session_id: str,
        operation_retry_id: str,
        operation_payload_sha256: str,
    ) -> dict[str, str | bool]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                """
                SELECT * FROM effect_operations
                WHERE user_id=? AND session_id=? AND operation_retry_id=?
                """,
                (user_id, session_id, operation_retry_id),
            ).fetchone()
            if row is not None:
                if row["operation_payload_sha256"] != operation_payload_sha256:
                    raise RetryIdentityMismatch(
                        "same scoped operation_retry_id reused with changed payload"
                    )
                if row["state"] in self.BLOCKING_STATES:
                    self.db.commit()
                    return {
                        "dispatch_permitted": False,
                        "disposition": "BLOCK_UNRESOLVED",
                        "attempt_id": row["current_attempt_id"],
                        "effect_id": row["current_effect_id"],
                    }
                if row["state"] in self.TERMINAL_REUSE_STATES:
                    self.db.commit()
                    return {
                        "dispatch_permitted": False,
                        "disposition": "REUSE_VERIFIED_APPLIED",
                        "attempt_id": row["current_attempt_id"],
                        "effect_id": row["current_effect_id"],
                    }
                if row["state"] != "VERIFIED_NOT_APPLIED":
                    raise RuntimeError(f"unknown operation state: {row['state']}")

            attempt_id = f"attempt-{uuid.uuid4()}"
            effect_id = f"effect-{uuid.uuid4()}"
            if row is None:
                self.db.execute(
                    """
                    INSERT INTO effect_operations(
                        user_id, session_id, operation_retry_id,
                        operation_payload_sha256, state,
                        current_attempt_id, current_effect_id
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        user_id,
                        session_id,
                        operation_retry_id,
                        operation_payload_sha256,
                        "PENDING",
                        attempt_id,
                        effect_id,
                    ),
                )
            else:
                self.db.execute(
                    """
                    UPDATE effect_operations
                    SET state='PENDING', current_attempt_id=?, current_effect_id=?,
                        verification_evidence_ref=NULL
                    WHERE user_id=? AND session_id=? AND operation_retry_id=?
                    """,
                    (
                        attempt_id,
                        effect_id,
                        user_id,
                        session_id,
                        operation_retry_id,
                    ),
                )
            self.db.execute(
                """
                INSERT INTO effect_attempts(
                    attempt_id,effect_id,user_id,session_id,operation_retry_id,
                    dispatch_state,outcome_certainty
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    attempt_id,
                    effect_id,
                    user_id,
                    session_id,
                    operation_retry_id,
                    "NOT_STARTED",
                    "UNRESOLVED",
                ),
            )
            self.db.commit()
            return {
                "dispatch_permitted": True,
                "disposition": "ADMIT_NEW_ATTEMPT",
                "attempt_id": attempt_id,
                "effect_id": effect_id,
            }
        except Exception:
            self.db.rollback()
            raise

    def mark_dispatch_started(self, attempt_id: str) -> None:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT * FROM effect_attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if row is None:
                raise KeyError(attempt_id)
            self.db.execute(
                """
                UPDATE effect_attempts
                SET dispatch_state='STARTED', outcome_certainty='UNRESOLVED'
                WHERE attempt_id=?
                """,
                (attempt_id,),
            )
            self.db.execute(
                """
                UPDATE effect_operations
                SET state='DISPATCH_STARTED'
                WHERE user_id=? AND session_id=? AND operation_retry_id=?
                  AND current_attempt_id=?
                """,
                (
                    row["user_id"],
                    row["session_id"],
                    row["operation_retry_id"],
                    attempt_id,
                ),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def mark_unknown(self, attempt_id: str) -> None:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT * FROM effect_attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if row is None:
                raise KeyError(attempt_id)
            self.db.execute(
                """
                UPDATE effect_attempts
                SET outcome_certainty='UNKNOWN'
                WHERE attempt_id=?
                """,
                (attempt_id,),
            )
            self.db.execute(
                """
                UPDATE effect_operations
                SET state='UNKNOWN'
                WHERE user_id=? AND session_id=? AND operation_retry_id=?
                  AND current_attempt_id=?
                """,
                (
                    row["user_id"],
                    row["session_id"],
                    row["operation_retry_id"],
                    attempt_id,
                ),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def verify_not_applied(self, attempt_id: str, evidence_ref: str) -> None:
        if not evidence_ref:
            raise ValueError("authority-owned verification evidence is required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT * FROM effect_attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if row is None:
                raise KeyError(attempt_id)
            self.db.execute(
                """
                UPDATE effect_attempts
                SET outcome_certainty='VERIFIED_NOT_APPLIED'
                WHERE attempt_id=?
                """,
                (attempt_id,),
            )
            self.db.execute(
                """
                UPDATE effect_operations
                SET state='VERIFIED_NOT_APPLIED', verification_evidence_ref=?
                WHERE user_id=? AND session_id=? AND operation_retry_id=?
                  AND current_attempt_id=?
                """,
                (
                    evidence_ref,
                    row["user_id"],
                    row["session_id"],
                    row["operation_retry_id"],
                    attempt_id,
                ),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise


class DirectEpisodeNullRetryFencePrototypeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "unified.db"
        self.user = "user-A"
        self.session = "session-A"
        self.payload = OperationFence.payload_digest(
            b'{"capability":"state.noop","target":"x"}'
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_reopen_blocks_same_unresolved_operation_without_second_child_mutation(self) -> None:
        child_mutations = 0
        fence = OperationFence(self.path)
        first = fence.begin_attempt(
            user_id=self.user,
            session_id=self.session,
            operation_retry_id="op-A",
            operation_payload_sha256=self.payload,
        )
        self.assertTrue(first["dispatch_permitted"])
        child_mutations += 1
        fence.mark_dispatch_started(str(first["attempt_id"]))
        fence.mark_unknown(str(first["attempt_id"]))
        fence.close()

        reopened = OperationFence(self.path)
        second = reopened.begin_attempt(
            user_id=self.user,
            session_id=self.session,
            operation_retry_id="op-A",
            operation_payload_sha256=self.payload,
        )
        if second["dispatch_permitted"]:
            child_mutations += 1
        self.assertFalse(second["dispatch_permitted"])
        self.assertEqual(second["disposition"], "BLOCK_UNRESOLVED")
        self.assertEqual(second["attempt_id"], first["attempt_id"])
        self.assertEqual(second["effect_id"], first["effect_id"])
        self.assertEqual(child_mutations, 1)
        reopened.close()

    def test_changed_payload_same_operation_rejects_before_dispatch(self) -> None:
        fence = OperationFence(self.path)
        first = fence.begin_attempt(
            user_id=self.user,
            session_id=self.session,
            operation_retry_id="op-A",
            operation_payload_sha256=self.payload,
        )
        self.assertTrue(first["dispatch_permitted"])
        with self.assertRaises(RetryIdentityMismatch):
            fence.begin_attempt(
                user_id=self.user,
                session_id=self.session,
                operation_retry_id="op-A",
                operation_payload_sha256=OperationFence.payload_digest(b"different"),
            )
        attempts = fence.db.execute("SELECT count(*) FROM effect_attempts").fetchone()[0]
        self.assertEqual(attempts, 1)
        fence.close()

    def test_distinct_operation_id_keeps_identical_semantics_independently_admissible(self) -> None:
        fence = OperationFence(self.path)
        first = fence.begin_attempt(
            user_id=self.user,
            session_id=self.session,
            operation_retry_id="op-A",
            operation_payload_sha256=self.payload,
        )
        second = fence.begin_attempt(
            user_id=self.user,
            session_id=self.session,
            operation_retry_id="op-B",
            operation_payload_sha256=self.payload,
        )
        self.assertTrue(first["dispatch_permitted"])
        self.assertTrue(second["dispatch_permitted"])
        self.assertNotEqual(first["attempt_id"], second["attempt_id"])
        self.assertNotEqual(first["effect_id"], second["effect_id"])
        fence.close()

    def test_only_verified_not_applied_can_open_fresh_attempt_after_unknown(self) -> None:
        fence = OperationFence(self.path)
        first = fence.begin_attempt(
            user_id=self.user,
            session_id=self.session,
            operation_retry_id="op-A",
            operation_payload_sha256=self.payload,
        )
        fence.mark_dispatch_started(str(first["attempt_id"]))
        fence.mark_unknown(str(first["attempt_id"]))
        blocked = fence.begin_attempt(
            user_id=self.user,
            session_id=self.session,
            operation_retry_id="op-A",
            operation_payload_sha256=self.payload,
        )
        self.assertFalse(blocked["dispatch_permitted"])

        fence.verify_not_applied(
            str(first["attempt_id"]), "authority://verification/no-application/1"
        )
        retry = fence.begin_attempt(
            user_id=self.user,
            session_id=self.session,
            operation_retry_id="op-A",
            operation_payload_sha256=self.payload,
        )
        self.assertTrue(retry["dispatch_permitted"])
        self.assertNotEqual(retry["attempt_id"], first["attempt_id"])
        self.assertNotEqual(retry["effect_id"], first["effect_id"])
        attempts = fence.db.execute(
            """
            SELECT attempt_id,outcome_certainty FROM effect_attempts
            WHERE user_id=? AND session_id=? AND operation_retry_id=?
            ORDER BY rowid
            """,
            (self.user, self.session, "op-A"),
        ).fetchall()
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["outcome_certainty"], "VERIFIED_NOT_APPLIED")
        self.assertEqual(attempts[1]["outcome_certainty"], "UNRESOLVED")
        fence.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
