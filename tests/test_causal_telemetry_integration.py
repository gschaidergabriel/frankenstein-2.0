from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC))

from frankenstein2.causal_identity import CausalIdentity
from frankenstein2.telemetry import TelemetryWriteError, TelemetryWriter
from tools.init_telemetry_dbs import SCHEMAS, init_db


class CausalTelemetryIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        init_db(
            self.root / "system_telemetry.sqlite",
            SCHEMAS["system_telemetry.sqlite"],
        )
        self.writer = TelemetryWriter(self.root)
        self.identity = CausalIdentity(
            session_id="session-001",
            agent_id="agent-001",
            task_id="task-001",
            turn_id="turn-001",
            causal_id="causal-001",
            generation=7,
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _rows(self) -> list[tuple]:
        conn = sqlite3.connect(self.root / "system_telemetry.sqlite")
        try:
            return conn.execute(
                """
                SELECT event_id, run_id, workpackage_id, generation,
                       session_id, agent_id, task_id, turn_id, causal_id,
                       component, severity, event_type, payload_json
                FROM system_events ORDER BY event_id
                """
            ).fetchall()
        finally:
            conn.close()

    def test_identity_survives_exact_system_event_persistence(self) -> None:
        self.writer.emit_system_event(
            event_id="event-001",
            run_id="run-001",
            workpackage_id="F2-WP-101",
            identity=self.identity,
            recorded_at_utc="2026-08-28T14:56:00Z",
            monotonic_ns=123456,
            component="causal-telemetry-integration-test",
            severity="INFO",
            event_type="CAUSAL_IDENTITY_PERSISTENCE_PROBE",
            payload={"z": 2, "a": 1},
        )

        rows = self._rows()
        self.assertEqual(len(rows), 1)
        (
            event_id,
            run_id,
            workpackage_id,
            generation,
            session_id,
            agent_id,
            task_id,
            turn_id,
            causal_id,
            component,
            severity,
            event_type,
            payload_json,
        ) = rows[0]
        self.assertEqual(event_id, "event-001")
        self.assertEqual(run_id, "run-001")
        self.assertEqual(workpackage_id, "F2-WP-101")
        self.assertEqual(generation, self.identity.generation)
        self.assertEqual(session_id, self.identity.session_id)
        self.assertEqual(agent_id, self.identity.agent_id)
        self.assertEqual(task_id, self.identity.task_id)
        self.assertEqual(turn_id, self.identity.turn_id)
        self.assertEqual(causal_id, self.identity.causal_id)
        self.assertEqual(component, "causal-telemetry-integration-test")
        self.assertEqual(severity, "INFO")
        self.assertEqual(event_type, "CAUSAL_IDENTITY_PERSISTENCE_PROBE")
        self.assertEqual(payload_json, '{"a":1,"z":2}')
        self.assertEqual(json.loads(payload_json), {"a": 1, "z": 2})

    def test_derived_identity_is_rejected_before_lineage_can_be_dropped(self) -> None:
        derived = self.identity.derive(
            causal_id="causal-002",
            generation=8,
            turn_id="turn-002",
        )
        with self.assertRaisesRegex(
            TelemetryWriteError,
            "cannot preserve parent_causal_id",
        ):
            self.writer.emit_system_event(
                event_id="event-derived",
                run_id="run-001",
                workpackage_id="F2-WP-101",
                identity=derived,
                recorded_at_utc="2026-08-28T14:56:01Z",
                component="causal-telemetry-integration-test",
                severity="INFO",
                event_type="DERIVED_IDENTITY_MUST_FAIL_CLOSED",
                payload={},
            )
        self.assertEqual(self._rows(), [])

    def test_non_identity_input_fails_closed_without_persistence(self) -> None:
        with self.assertRaisesRegex(
            TelemetryWriteError,
            "explicit CausalIdentity",
        ):
            self.writer.emit_system_event(
                event_id="event-invalid",
                run_id="run-001",
                identity={"causal_id": "forged"},  # type: ignore[arg-type]
                recorded_at_utc="2026-08-28T14:56:02Z",
                component="causal-telemetry-integration-test",
                severity="INFO",
                event_type="INVALID_IDENTITY_MUST_FAIL_CLOSED",
                payload={},
            )
        self.assertEqual(self._rows(), [])


if __name__ == "__main__":
    unittest.main()
