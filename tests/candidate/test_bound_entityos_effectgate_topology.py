from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

BOUND_ROOT = Path(os.environ["BOUND_ENTITYOS_ROOT"]).resolve()
sys.path.insert(0, str(BOUND_ROOT / "the artefact"))

from clayverse.effects import EffectGate, EffectRequest  # type: ignore[import-not-found]  # noqa: E402
from clayverse.store import UnifiedDB  # type: ignore[import-not-found]  # noqa: E402

from frankenstein2.canonical_effect_authority_bridge import (  # noqa: E402
    CanonicalEffectAuthorityEvidence,
    CanonicalEffectAuthorityIdentity,
    CanonicalEffectAuthorityIdentityError,
)
from frankenstein2.effect_executor_interlock import ExternalGateDecision  # noqa: E402


BOUND_AUTHORITY = CanonicalEffectAuthorityIdentity(
    repository="gschaidergabriel/clay-global-research-entity",
    commit_sha="2b68aad14bf7824d513b52898904909256e3522d",
    module_path="the artefact/clayverse/effects.py",
    source_blob_sha="4a6413b3f3c752c6327e67233bdd8097f3cf0ba4",
    state_schema="ENTITYOS_EFFECT_AUTHORITY_IMPLEMENTATION_BINDING/v1",
    api_version="ENTITYOS_EFFECT_AUTHORITY_PY_API/v1",
)


class BoundEffectGateTopologyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = UnifiedDB(Path(self._tmp.name) / "unified.sqlite")
        self.addCleanup(self.db.close)
        self.user_id = "f2-topology-user"
        self.db.ensure_user(self.user_id, "F2 topology probe")
        self.session_id = self.db.ensure_session(self.user_id, "f2-topology-terminal")
        self.generation = self.db.session_generation(self.session_id)
        self.gate = EffectGate(self.db)

    def _noop_request(self) -> EffectRequest:
        return EffectRequest(
            user_id=self.user_id,
            session_id=self.session_id,
            capability="state.noop",
            target="f2-bound-effectgate-topology-probe",
            expected_generation=self.generation,
        )

    def test_bound_effectgate_owns_begin_action_and_finalize_in_one_call(self) -> None:
        begin_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        original_begin = self.gate.journal.begin

        def counted_begin(*args: object, **kwargs: object) -> str:
            begin_calls.append((args, kwargs))
            return original_begin(*args, **kwargs)

        self.gate.journal.begin = counted_begin  # type: ignore[method-assign]
        effect_id, outcome = self.gate.execute(self._noop_request())

        rows = self.db.db.execute(
            "SELECT effect_id,status,capability FROM effects ORDER BY ts,effect_id"
        ).fetchall()
        self.assertEqual(len(begin_calls), 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["effect_id"], effect_id)
        self.assertEqual(rows[0]["status"], "VERIFIED")
        self.assertEqual(rows[0]["capability"], "state.noop")
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["boundary"], "internal")

    def test_truthful_two_stage_allow_cannot_be_synthesized_after_execute_returns(self) -> None:
        effect_id, _outcome = self.gate.execute(self._noop_request())
        row = self.db.db.execute(
            "SELECT status FROM effects WHERE effect_id=?", (effect_id,)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "VERIFIED")

        with self.assertRaisesRegex(
            CanonicalEffectAuthorityIdentityError,
            "CANONICAL_ALLOW_REQUIRES_PENDING_JOURNAL",
        ):
            CanonicalEffectAuthorityEvidence(
                authority=BOUND_AUTHORITY,
                decision_id="bound-gate-call-1",
                decision=ExternalGateDecision.ALLOW,
                journal_state=row["status"],
                effect_id=effect_id,
                return_id="return-1",
                binding_id="binding-1",
                invocation_id="invocation-1",
                tool_use_id="tool-1",
                delegation_id="delegation-1",
                child_identity_sha256="a" * 64,
            )

    def test_recovery_marks_pending_unknown_without_replaying(self) -> None:
        effect_id = self.gate.journal.begin(
            None,
            self.session_id,
            self.user_id,
            "state.noop",
            "f2-restart-topology-probe",
            self.generation,
        )
        pending = self.db.db.execute(
            "SELECT status FROM effects WHERE effect_id=?", (effect_id,)
        ).fetchone()
        self.assertEqual(pending["status"], "PENDING")

        self.assertEqual(self.gate.journal.recover_pending(), 1)
        recovered = self.db.db.execute(
            "SELECT status FROM effects WHERE effect_id=?", (effect_id,)
        ).fetchone()
        self.assertEqual(recovered["status"], "UNKNOWN_AFTER_RESTART")
        self.assertEqual(self.gate.journal.recover_pending(), 0)
        self.assertEqual(
            self.db.db.execute("SELECT COUNT(*) FROM effects").fetchone()[0],
            1,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
