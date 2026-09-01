from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tools.telemetry_runtime import CausalContext, TelemetryRuntime  # noqa: E402
from frankenstein2.causal_authority_binding import (  # noqa: E402
    CausalAuthorityBindingError,
    UnifiedDBAuthorityRef,
    bind_causal_authority,
)
from frankenstein2.causal_identity import CausalIdentity  # noqa: E402

UDB = UnifiedDBAuthorityRef(
    receipt_ref="workpackages/receipts/F2-WP-100_G1_SOURCE_CI_ACCEPTANCE.json",
    canonical_source="src/state/unifieddb_identity.py",
    fingerprint_schema="FRANKENSTEIN2_UNIFIEDDB_FINGERPRINT/v2",
)


class TelemetryCausalAuthorityIntegrationTests(unittest.TestCase):
    def _emit_and_read(self) -> tuple[CausalIdentity, dict[str, object]]:
        context = CausalContext(
            run_id="run-integration-001",
            workpackage_id="F2-WP-005",
            generation=7,
            session_id="session-001",
            agent_id="agent-clay-organ",
            task_id="task-42",
            turn_id="turn-7",
            causal_id="cause-root",
        )
        identity = CausalIdentity(
            session_id=context.session_id,
            agent_id=context.agent_id,
            task_id=context.task_id,
            turn_id=context.turn_id,
            causal_id=context.causal_id,
            generation=context.generation,
        )

        with tempfile.TemporaryDirectory() as tmp:
            runtime = TelemetryRuntime(tmp, context)
            event_id = runtime.emit_system_event(
                component="integration-test",
                event_type="CAUSAL_AUTHORITY_DISCRIMINATOR",
                payload={"scope": "repository-hosted"},
                event_id="evt-integration-001",
            )
            self.assertEqual(event_id, "evt-integration-001")

            db = Path(tmp) / "system_telemetry.sqlite"
            with sqlite3.connect(db) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """SELECT event_id, run_id, session_id, agent_id, task_id,
                              turn_id, causal_id, generation
                       FROM system_events WHERE event_id = ?""",
                    (event_id,),
                ).fetchone()
            self.assertIsNotNone(row)
            telemetry = dict(row)

        return identity, telemetry

    def test_same_emitted_event_binds_exactly_to_existing_authorities(self) -> None:
        identity, telemetry = self._emit_and_read()
        bound = bind_causal_authority(identity, unifieddb=UDB, telemetry=telemetry)

        self.assertEqual(bound.telemetry_event_id, telemetry["event_id"])
        self.assertEqual(bound.telemetry_run_id, telemetry["run_id"])
        self.assertEqual(bound.identity.sha256(), identity.sha256())
        self.assertEqual(bound.unifieddb.receipt_ref, UDB.receipt_ref)

    def test_emitted_event_identity_substitution_fails_closed(self) -> None:
        identity, telemetry = self._emit_and_read()
        substituted = {**telemetry, "causal_id": "cause-substituted"}

        with self.assertRaises(CausalAuthorityBindingError):
            bind_causal_authority(identity, unifieddb=UDB, telemetry=substituted)


if __name__ == "__main__":
    unittest.main()
