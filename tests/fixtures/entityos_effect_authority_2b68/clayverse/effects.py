from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from .effect_journal import EffectJournal
from .entityos_bridge import EntityOSBridge
from .store import Lease, StaleGeneration, UnifiedDB


@dataclass(frozen=True)
class EffectRequest:
    user_id: str
    session_id: str
    capability: str
    target: str
    argv: list[str] | None = None
    expected_generation: int | None = None


class EffectGate:
    ALLOWED = {"entityos.exec", "process.exec", "state.noop"}
    AUTO_LEASE_TTL = 300.0
    ENTITYOS_EFFECT_RESOURCE = "effect:entityos.exec"
    AUTONOMY_SOURCE = "clayverse-autonomy:goal-step"

    def __init__(
        self,
        db: UnifiedDB,
        allow_process: bool = False,
        entityos_bridge: EntityOSBridge | None = None,
    ):
        self.db = db
        self.allow_process = allow_process
        self.entityos_bridge = entityos_bridge
        self.journal = EffectJournal(db)

    def available_capabilities(self):
        capabilities = {"state.noop"}
        if self.entityos_bridge is not None:
            capabilities.add("entityos.exec")
        return tuple(sorted(capabilities))

    def causal_for_effect(self, effect_id):
        return self.journal.causal_for(effect_id)

    @classmethod
    def _lease_resource(cls, req: EffectRequest):
        if req.capability != "entityos.exec":
            raise ValueError("automatic lease only defined for entityos.exec")
        return cls.ENTITYOS_EFFECT_RESOURCE

    def _release_exact_lease(self, lease: Lease):
        with self.db.tx() as db:
            db.execute(
                "DELETE FROM leases WHERE resource=? AND holder=? AND generation=? AND nonce=?",
                (lease.resource, lease.holder, lease.generation, lease.nonce),
            )

    @staticmethod
    def _decode_provenance(raw) -> dict | None:
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _autonomy_identity_for_episode(
        self, episode_id: str | None, session_id: str
    ) -> tuple[str, str] | None:
        """Return exact autonomous goal/step identity for a canonical workspace episode.

        Non-workspace/direct EffectGate callers and ordinary human episodes remain outside
        this autonomy-specific replay fence. A canonical autonomy episode with malformed
        provenance fails closed.
        """
        if episode_id is None:
            return None
        row = self.db.db.execute(
            "SELECT t.provenance "
            "FROM workspace_episodes w JOIN turns t ON t.turn_id=w.observation_turn_id "
            "WHERE w.episode_id=? AND w.session_id=?",
            (episode_id, session_id),
        ).fetchone()
        if row is None:
            return None
        provenance = self._decode_provenance(row["provenance"])
        if provenance is None:
            raise RuntimeError("effect episode provenance malformed")
        if provenance.get("source") != self.AUTONOMY_SOURCE:
            return None
        goal_id = provenance.get("goal_id")
        step_id = provenance.get("autonomy_step_id")
        if not isinstance(goal_id, str) or not goal_id:
            raise RuntimeError("autonomous effect episode lacks goal identity")
        if not isinstance(step_id, str) or not step_id:
            raise RuntimeError("autonomous effect episode lacks step identity")
        return goal_id, step_id

    def _deny_cross_attempt_autonomy_replay(
        self, episode_id: str | None, req: EffectRequest
    ) -> None:
        """Never execute a second effect for the same durable autonomy goal/step.

        EffectJournal request identity is intentionally episode-scoped. This additional
        gate covers the crash/lost-handoff case where the controller retries the same
        logical autonomous step in a new episode after an earlier effect was already
        journaled. Existing evidence must be reconciled; it is never silently replayed.
        """
        identity = self._autonomy_identity_for_episode(episode_id, req.session_id)
        if identity is None:
            return
        rows = self.db.db.execute(
            "SELECT e.effect_id,e.status,t.provenance "
            "FROM effects e "
            "JOIN workspace_episodes w ON w.episode_id=e.episode_id "
            "JOIN turns t ON t.turn_id=w.observation_turn_id "
            "WHERE w.session_id=? AND e.episode_id<>? AND t.provenance LIKE ? "
            "ORDER BY e.ts,e.effect_id",
            (req.session_id, episode_id, f"%{self.AUTONOMY_SOURCE}%"),
        ).fetchall()
        for row in rows:
            provenance = self._decode_provenance(row["provenance"])
            if provenance is None:
                raise RuntimeError(
                    "prior autonomous effect provenance malformed; retry denied"
                )
            if provenance.get("source") != self.AUTONOMY_SOURCE:
                continue
            if provenance.get("goal_id") != identity[0]:
                continue
            if provenance.get("autonomy_step_id") != identity[1]:
                continue
            if row["status"] == "PENDING":
                raise RuntimeError(
                    "prior autonomous effect pending; retry denied until recovery"
                )
            raise RuntimeError(
                "prior final autonomous effect requires controller reconciliation before retry"
            )

    def execute(
        self,
        req: EffectRequest,
        episode_id=None,
        lease: Lease | None = None,
    ):
        if req.capability not in self.ALLOWED:
            raise PermissionError("capability denied")
        row = self.db.db.execute(
            "SELECT generation FROM sessions WHERE session_id=? AND user_id=?",
            (req.session_id, req.user_id),
        ).fetchone()
        if not row:
            raise PermissionError("session owner mismatch")
        generation = int(row[0])
        self.db.assert_live_generation(req.session_id, generation)
        if req.expected_generation is not None and req.expected_generation != generation:
            raise StaleGeneration(req.session_id)

        # Must run before lease acquisition, EffectJournal.begin(), or any real action.
        self._deny_cross_attempt_autonomy_replay(episode_id, req)

        if req.capability == "entityos.exec" and lease is not None:
            raise ValueError("entityos.exec lease is managed by EffectGate")
        if lease:
            self.db.assert_lease(lease)
        if req.capability == "process.exec":
            raise PermissionError(
                "direct host process execution forbidden; no admitted generic EntityOS process contract"
            )
        auto_lease = False
        if req.capability == "entityos.exec":
            holder = f"{req.session_id}:{uuid.uuid4().hex}"
            lease = self.db.acquire_lease(
                self._lease_resource(req), holder, ttl=self.AUTO_LEASE_TTL
            )
            auto_lease = True
        try:
            effect_id = self.journal.begin(
                episode_id,
                req.session_id,
                req.user_id,
                req.capability,
                req.target,
                generation,
                req.argv,
                lease=lease,
            )
            if req.capability == "state.noop":
                outcome = {
                    "ok": True,
                    "target": req.target,
                    "boundary": "internal",
                }
                self.journal.complete_verified(
                    effect_id,
                    outcome,
                    req.session_id,
                    req.user_id,
                    generation,
                    lease,
                )
                return effect_id, outcome
            if not self.entityos_bridge:
                outcome = {
                    "ok": False,
                    "denied": True,
                    "reason": "entityos_unavailable",
                    "target": req.target,
                    "boundary": "EntityOS",
                }
                self.journal.complete(effect_id, outcome, "DENIED")
                return effect_id, outcome
            try:
                outcome = dict(self.entityos_bridge.run(req.argv))
                outcome["boundary"] = "EntityOS"
                outcome["entityos_sha256"] = self.entityos_bridge.sha256.lower()
            except Exception as exc:
                self.journal.complete(
                    effect_id,
                    {"ok": False, "error": type(exc).__name__, "boundary": "EntityOS"},
                    "FAILED",
                )
                raise
            self.journal.complete_verified(
                effect_id,
                outcome,
                req.session_id,
                req.user_id,
                generation,
                lease,
            )
            return effect_id, outcome
        finally:
            if auto_lease and lease is not None:
                self._release_exact_lease(lease)
