from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures/bound_entityos_effect_authority"
BINDING_PATH = FIXTURE_ROOT / "ENTITYOS_EFFECT_AUTHORITY_IMPLEMENTATION_BINDING_V1.json"
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(FIXTURE_ROOT))

# effects.py imports EntityOSBridge only for its runtime dependency.  Every test below
# supplies an in-process bridge double: no EntityOS executable and no external effect.
_bridge_module = types.ModuleType("clayverse.entityos_bridge")
_bridge_module.EntityOSBridge = object
sys.modules["clayverse.entityos_bridge"] = _bridge_module

from clayverse.effect_journal import EffectJournal
from clayverse.effects import EffectGate, EffectRequest
from clayverse.store import UnifiedDB
from frankenstein2.effect_invocation_correlation import (
    EffectCallBinding,
    EffectCorrelationStage,
    EffectInvocationCorrelationError,
    observe_effect_result,
)
from frankenstein2.effect_request_identity import EffectRequestIdentity

EXPECTED_BINDING_BLOB = "b4d91a0dd233c9dc15ff8218feea9248ac1c13c5"
EXPECTED_IMPL_COMMIT = "2b68aad14bf7824d513b52898904909256e3522d"


def git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def canonical_effect_request(identity: EffectRequestIdentity) -> EffectRequest:
    """Lossless candidate adapter mapping; it grants no authority by itself."""
    return EffectRequest(
        user_id=identity.user_id,
        session_id=identity.session_id,
        capability=identity.capability,
        target=identity.target,
        argv=list(identity.argv) if identity.argv is not None else None,
        expected_generation=identity.expected_generation,
    )


def result_sha(outcome: dict) -> str:
    return hashlib.sha256(
        json.dumps(outcome, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class FakeEntityOSBridge:
    def __init__(self, db: UnifiedDB, episode_id: str) -> None:
        self.db = db
        self.episode_id = episode_id
        self.sha256 = "f" * 64
        self.calls: list[list[str] | None] = []
        self.pending_effect_ids_seen: list[str] = []

    def run(self, argv):
        self.calls.append(list(argv) if argv is not None else None)
        rows = self.db.db.execute(
            "SELECT effect_id,status FROM effects WHERE episode_id=? ORDER BY ts,effect_id",
            (self.episode_id,),
        ).fetchall()
        if len(rows) != 1 or rows[0]["status"] != "PENDING":
            raise AssertionError("canonical EffectJournal PENDING must exist before bridge.run")
        leases = self.db.db.execute(
            "SELECT resource FROM leases WHERE resource=?",
            (EffectGate.ENTITYOS_EFFECT_RESOURCE,),
        ).fetchall()
        if len(leases) != 1:
            raise AssertionError("canonical entityos.exec lease must be live during bridge.run")
        self.pending_effect_ids_seen.append(rows[0]["effect_id"])
        return {"ok": True, "exit": 0}


class BoundEntityOSEffectTopologyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.binding = json.loads(BINDING_PATH.read_text(encoding="utf-8"))

    def new_db(self):
        td = tempfile.TemporaryDirectory()
        path = Path(td.name) / "unified.sqlite"
        db = UnifiedDB(path)
        user_id = "u:trigger4"
        db.ensure_user(user_id, "Trigger 4 Test")
        session_id = db.ensure_session(user_id, "trigger4-test")
        generation = db.session_generation(session_id)
        return td, path, db, user_id, session_id, generation

    def install_episode(
        self,
        db: UnifiedDB,
        user_id: str,
        session_id: str,
        generation: int,
        label: str,
        *,
        replace_active: bool = False,
    ) -> str:
        if replace_active:
            db.db.execute("DELETE FROM active_turns WHERE session_id=?", (session_id,))
        turn_id = db.append_turn(
            session_id, user_id, "user", f"no-real-effect topology test {label}"
        )
        episode_id = f"episode:trigger4:bound-effect-topology:{label}"
        causal_id = f"causal:trigger4:bound-effect-topology:{label}"
        now = time.time()
        db.db.execute(
            "INSERT INTO workspace_episodes(episode_id,session_id,ts,observation_turn_id,salience,alternatives,selected,state) VALUES(?,?,?,?,?,?,?,?)",
            (episode_id, session_id, now, turn_id, 1.0, "[]", "request_effect", "SELECTED"),
        )
        db.db.execute(
            "INSERT INTO active_turns(session_id,user_id,turn_id,episode_id,causal_id,generation,resource_refs,effect_id,outcome,workspace_selected,started_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (session_id, user_id, turn_id, episode_id, causal_id, generation, "[]", None, None, 1, now),
        )
        return episode_id

    def new_fixture(self):
        td, path, db, user_id, session_id, generation = self.new_db()
        episode_id = self.install_episode(
            db, user_id, session_id, generation, "single"
        )
        return td, path, db, user_id, session_id, generation, episode_id

    def test_binding_record_losslessly_pins_all_bound_source_bytes(self) -> None:
        self.assertEqual(git_blob_sha(BINDING_PATH), EXPECTED_BINDING_BLOB)
        self.assertEqual(self.binding["schema"], "ENTITYOS_EFFECT_AUTHORITY_IMPLEMENTATION_BINDING/v1")
        self.assertEqual(self.binding["status"], "CURRENT_EXACT_SOURCE_IDENTITY_BINDING_NO_NEW_AUTHORITY")
        identity = self.binding["implementation_identity"]
        self.assertEqual(identity["bound_commit"], EXPECTED_IMPL_COMMIT)
        self.assertEqual(self.binding["api_contract"]["version"], "ENTITYOS_EFFECT_AUTHORITY_PY_API/v1")

        fixture_paths = {
            "effect_gate": FIXTURE_ROOT / "clayverse/effects.py",
            "effect_journal": FIXTURE_ROOT / "clayverse/effect_journal.py",
            "canonical_state_schema": FIXTURE_ROOT / "clayverse/store.py",
        }
        for key, path in fixture_paths.items():
            item = identity[key]
            actual = git_blob_sha(path)
            self.assertEqual(actual, item["blob_sha"], f"bound blob mismatch for {key}")

    def test_bound_effectgate_owns_pending_dispatch_finalize_transaction_once(self) -> None:
        td, _path, db, user_id, session_id, generation, episode_id = self.new_fixture()
        self.addCleanup(td.cleanup)
        self.addCleanup(db.close)
        bridge = FakeEntityOSBridge(db, episode_id)
        gate = EffectGate(db, entityos_bridge=bridge)
        req = EffectRequest(
            user_id=user_id,
            session_id=session_id,
            capability="entityos.exec",
            target="fake://no-real-effect",
            argv=["noop"],
            expected_generation=generation,
        )

        effect_id, outcome = gate.execute(req, episode_id=episode_id)

        self.assertEqual(bridge.calls, [["noop"]])
        self.assertEqual(bridge.pending_effect_ids_seen, [effect_id])
        self.assertTrue(outcome["ok"])
        row = db.db.execute(
            "SELECT status FROM effects WHERE effect_id=?", (effect_id,)
        ).fetchone()
        self.assertEqual(row["status"], "VERIFIED")
        lease_count = db.db.execute(
            "SELECT COUNT(*) FROM leases WHERE resource=?",
            (EffectGate.ENTITYOS_EFFECT_RESOURCE,),
        ).fetchone()[0]
        self.assertEqual(lease_count, 0)

        with self.assertRaisesRegex(RuntimeError, "effect already persisted|causal identity already consumed"):
            gate.execute(req, episode_id=episode_id)
        self.assertEqual(bridge.calls, [["noop"]], "same episode must never dispatch twice")

    def test_pending_crash_recovery_becomes_unknown_and_cannot_replay(self) -> None:
        td, path, db, user_id, session_id, generation, episode_id = self.new_fixture()
        self.addCleanup(td.cleanup)
        effect_id = EffectJournal(db).begin(
            episode_id,
            session_id,
            user_id,
            "entityos.exec",
            "fake://crash-before-dispatch",
            generation,
            ["noop"],
        )
        db.close()

        reopened = UnifiedDB(path)
        self.addCleanup(reopened.close)
        self.assertEqual(EffectJournal(reopened).recover_pending(), 1)
        row = reopened.db.execute(
            "SELECT status FROM effects WHERE effect_id=?", (effect_id,)
        ).fetchone()
        self.assertEqual(row["status"], "UNKNOWN_AFTER_RESTART")

        bridge = FakeEntityOSBridge(reopened, episode_id)
        gate = EffectGate(reopened, entityos_bridge=bridge)
        req = EffectRequest(
            user_id=user_id,
            session_id=session_id,
            capability="entityos.exec",
            target="fake://crash-before-dispatch",
            argv=["noop"],
            expected_generation=generation,
        )
        with self.assertRaisesRegex(RuntimeError, "effect already persisted|causal identity already consumed"):
            gate.execute(req, episode_id=episode_id)
        self.assertEqual(bridge.calls, [], "UNKNOWN_AFTER_RESTART must not auto-replay")

    def test_same_session_ab_bijection_survives_reverse_observation_order(self) -> None:
        """Simulate overlapping observation: canonical calls serialize; F2 sees B then A."""
        td, _path, db, user_id, session_id, generation = self.new_db()
        self.addCleanup(td.cleanup)
        self.addCleanup(db.close)

        request_a = EffectRequestIdentity(
            user_id=user_id,
            session_id=session_id,
            capability="entityos.exec",
            target="fake://request-A",
            argv=("noop", "A"),
            expected_generation=generation,
        )
        request_b = EffectRequestIdentity(
            user_id=user_id,
            session_id=session_id,
            capability="entityos.exec",
            target="fake://request-B",
            argv=("noop", "B"),
            expected_generation=generation,
        )
        self.assertNotEqual(request_a.sha256(), request_b.sha256())

        episode_a = self.install_episode(db, user_id, session_id, generation, "A")
        bridge_a = FakeEntityOSBridge(db, episode_a)
        effect_a, outcome_a = EffectGate(db, entityos_bridge=bridge_a).execute(
            canonical_effect_request(request_a), episode_id=episode_a
        )

        # A completed canonically. Replace only the controller's single active-turn pointer
        # to represent the next same-session call; durable A effect/causal evidence remains.
        episode_b = self.install_episode(
            db, user_id, session_id, generation, "B", replace_active=True
        )
        bridge_b = FakeEntityOSBridge(db, episode_b)
        effect_b, outcome_b = EffectGate(db, entityos_bridge=bridge_b).execute(
            canonical_effect_request(request_b), episode_id=episode_b
        )
        self.assertNotEqual(effect_a, effect_b)
        self.assertEqual(bridge_a.calls, [["noop", "A"]])
        self.assertEqual(bridge_b.calls, [["noop", "B"]])

        prepared_a = EffectCallBinding(
            effect_id=effect_a,
            return_id=None,
            binding_id="binding-A",
            invocation_id="invocation-A",
            tool_use_id="tool-A",
            delegation_id="delegation-A",
            child_identity_sha256="a" * 64,
            stage=EffectCorrelationStage.PREPARED,
            request=request_a,
        )
        prepared_b = EffectCallBinding(
            effect_id=effect_b,
            return_id=None,
            binding_id="binding-B",
            invocation_id="invocation-B",
            tool_use_id="tool-B",
            delegation_id="delegation-B",
            child_identity_sha256="b" * 64,
            stage=EffectCorrelationStage.PREPARED,
            request=request_b,
        )

        # Reverse observer order deliberately: B is correlated before A even though A was
        # canonically executed first.  Identity, not completion proximity, must dominate.
        observed_b = observe_effect_result(
            prepared_b,
            effect_id=effect_b,
            observed_invocation_id="invocation-B",
            observed_tool_use_id="tool-B",
            observed_delegation_id="delegation-B",
            observed_binding_id="binding-B",
            observed_child_identity_sha256="b" * 64,
            result_id="result-B",
            result_sha256=result_sha(outcome_b),
            observed_request_sha256=request_b.sha256(),
        )
        observed_a = observe_effect_result(
            prepared_a,
            effect_id=effect_a,
            observed_invocation_id="invocation-A",
            observed_tool_use_id="tool-A",
            observed_delegation_id="delegation-A",
            observed_binding_id="binding-A",
            observed_child_identity_sha256="a" * 64,
            result_id="result-A",
            result_sha256=result_sha(outcome_a),
            observed_request_sha256=request_a.sha256(),
        )
        self.assertEqual(observed_b.stage, EffectCorrelationStage.RESULT_OBSERVED)
        self.assertEqual(observed_a.stage, EffectCorrelationStage.RESULT_OBSERVED)

        with self.assertRaisesRegex(EffectInvocationCorrelationError, "EFFECT_ID_MISMATCH"):
            observe_effect_result(
                prepared_a,
                effect_id=effect_b,
                observed_invocation_id="invocation-A",
                observed_tool_use_id="tool-A",
                observed_delegation_id="delegation-A",
                observed_binding_id="binding-A",
                observed_child_identity_sha256="a" * 64,
                result_id="result-cross-effect",
                result_sha256=result_sha(outcome_b),
                observed_request_sha256=request_a.sha256(),
            )
        with self.assertRaisesRegex(EffectInvocationCorrelationError, "REQUEST_SHA256_MISMATCH"):
            observe_effect_result(
                prepared_a,
                effect_id=effect_a,
                observed_invocation_id="invocation-A",
                observed_tool_use_id="tool-A",
                observed_delegation_id="delegation-A",
                observed_binding_id="binding-A",
                observed_child_identity_sha256="a" * 64,
                result_id="result-cross-request",
                result_sha256=result_sha(outcome_a),
                observed_request_sha256=request_b.sha256(),
            )

        # Correlation failures are pure observation failures: they cannot cause a second
        # canonical action invocation.
        self.assertEqual(bridge_a.calls, [["noop", "A"]])
        self.assertEqual(bridge_b.calls, [["noop", "B"]])
        rows = db.db.execute(
            "SELECT effect_id,status FROM effects WHERE effect_id IN (?,?) ORDER BY effect_id",
            (effect_a, effect_b),
        ).fetchall()
        self.assertEqual({row["effect_id"] for row in rows}, {effect_a, effect_b})
        self.assertEqual({row["status"] for row in rows}, {"VERIFIED"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
