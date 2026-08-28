from __future__ import annotations
import hashlib,json,time,uuid
from .store import UnifiedDB,StaleGeneration,Lease

class EffectJournal:
    """Transactional causal journal inside UnifiedDB; never a second state authority."""
    FINAL={'VERIFIED','DENIED','FAILED','STALE_OUTCOME','UNKNOWN_AFTER_RESTART'}
    SAFE_OUTCOME_FIELDS=('ok','exit','boundary','entityos_sha256','denied','reason','error','certainty')
    NON_REWARDING_CAPABILITIES={'state.noop'}
    def __init__(self,db:UnifiedDB):
        self.db=db
    @staticmethod
    def _payload(outcome): return json.dumps(outcome,sort_keys=True,separators=(',',':'))
    @classmethod
    def _credit(cls,status,outcome,capability):
        if capability in cls.NON_REWARDING_CAPABILITIES: return 0.0
        return 1.0 if status=='VERIFIED' and isinstance(outcome,dict) and outcome.get('ok') is True else 0.0
    @staticmethod
    def _target_receipt(target):
        raw=str(target).encode('utf-8')
        return {'audit':'redacted-target-v1','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    @classmethod
    def _argv_receipt(cls,argv):
        if not argv: return None
        raw=json.dumps(argv,ensure_ascii=False,separators=(',',':')).encode()
        return {'audit':'redacted-argv-v1','argc':len(argv),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
    @classmethod
    def _outcome_receipt(cls,outcome):
        payload=cls._payload(outcome).encode()
        receipt={'audit':'redacted-outcome-v1','sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)}
        if isinstance(outcome,dict):
            for key in cls.SAFE_OUTCOME_FIELDS:
                if key in outcome and isinstance(outcome[key],(str,int,float,bool,type(None))): receipt[key]=outcome[key]
        return receipt
    @staticmethod
    def _assert_lease_tx(db,lease:Lease):
        lr=db.execute('SELECT holder,generation,expires_at,nonce FROM leases WHERE resource=?',(lease.resource,)).fetchone()
        if not lr or lr['holder']!=lease.holder or int(lr['generation'])!=lease.generation or lr['nonce']!=lease.nonce or float(lr['expires_at'])<=time.time():
            raise StaleGeneration(lease.resource)
    @staticmethod
    def _assert_generation_tx(db,session_id,user_id,generation):
        row=db.execute('SELECT generation FROM sessions WHERE session_id=? AND user_id=?',(session_id,user_id)).fetchone()
        if not row: raise PermissionError('session owner mismatch')
        if int(row[0])!=int(generation): raise StaleGeneration(session_id)
        global_row=db.execute("SELECT value FROM meta WHERE key='entity_generation'").fetchone()
        entity_generation=int(global_row[0]) if global_row else 0
        if entity_generation>0 and entity_generation!=int(generation): raise StaleGeneration('entity_generation')
    @staticmethod
    def _assert_active_effect_intent_tx(db,episode_id,session_id,user_id,generation):
        active=db.execute(
            'SELECT workspace_selected,effect_id,causal_id FROM active_turns WHERE episode_id=? AND session_id=? AND user_id=? AND generation=?',
            (episode_id,session_id,user_id,int(generation)),
        ).fetchone()
        if not active: raise StaleGeneration('effect_active_turn')
        if not int(active['workspace_selected']): raise PermissionError('effect workspace intent not selected')
        if active['effect_id'] is not None: raise RuntimeError('active turn already bound to an effect')
        workspace=db.execute('SELECT state,selected FROM workspace_episodes WHERE episode_id=? AND session_id=?',(episode_id,session_id)).fetchone()
        if not workspace or workspace['state']!='SELECTED' or workspace['selected']!='request_effect':
            raise PermissionError('effect workspace selection mismatch')
        causal_rows=db.execute('SELECT causal_id FROM causal_episodes WHERE episode_id=? ORDER BY ts,causal_id',(episode_id,)).fetchall()
        if any(row['causal_id']!=active['causal_id'] for row in causal_rows):
            raise StaleGeneration('effect_causal_spine')
        return bool(causal_rows)
    def begin(self,episode_id,session_id,user_id,capability,target,generation,argv=None,lease:Lease|None=None):
        eid=str(uuid.uuid4())
        with self.db.tx() as db:
            self._assert_generation_tx(db,session_id,user_id,generation)
            if lease is not None: self._assert_lease_tx(db,lease)
            if episode_id is not None:
                causal_consumed=self._assert_active_effect_intent_tx(db,episode_id,session_id,user_id,generation)
                prior=db.execute('SELECT effect_id,status FROM effects WHERE episode_id=? ORDER BY ts,effect_id LIMIT 1',(episode_id,)).fetchone()
                if prior is not None:
                    raise RuntimeError('effect already persisted for episode; automatic replay denied')
                if causal_consumed:
                    raise RuntimeError('active causal identity already consumed before effect begin')
            audit_target=self._target_receipt(target)
            audit_argv=self._argv_receipt(argv)
            db.execute("INSERT INTO effects(effect_id,episode_id,user_id,capability,target,argv,requested_generation,status,outcome,ts,verified_at) VALUES(?,?,?,?,?,?,?,'PENDING',NULL,?,NULL)",(eid,episode_id,user_id,capability,self._payload(audit_target),json.dumps(audit_argv,sort_keys=True,separators=(',',':')) if audit_argv else None,generation,time.time()))
        return eid
    def _reenter_tx(self,db,effect_id,status,outcome):
        row=db.execute('SELECT causal_id FROM causal_episodes WHERE effect_id=? ORDER BY ts DESC LIMIT 1',(effect_id,)).fetchone()
        if row: return row[0]
        effect=db.execute('SELECT episode_id,capability FROM effects WHERE effect_id=?',(effect_id,)).fetchone()
        if not effect: raise KeyError(effect_id)
        episode_id=effect['episode_id']; observation_turn_id=None
        if episode_id:
            ws=db.execute('SELECT observation_turn_id FROM workspace_episodes WHERE episode_id=?',(episode_id,)).fetchone(); observation_turn_id=ws[0] if ws else None
        active=db.execute('SELECT causal_id FROM active_turns WHERE episode_id=?',(episode_id,)).fetchone() if episode_id else None
        cid=active['causal_id'] if active else str(uuid.uuid4())
        existing=db.execute('SELECT effect_id FROM causal_episodes WHERE causal_id=?',(cid,)).fetchone()
        if existing:
            raise RuntimeError('predeclared causal identity already consumed')
        payload=self._payload(outcome)
        db.execute('INSERT INTO causal_episodes(causal_id,episode_id,effect_id,observation_turn_id,outcome_hash,credit,reentered,ts) VALUES(?,?,?,?,?,?,1,?)',(cid,episode_id,effect_id,observation_turn_id,hashlib.sha256(payload.encode()).hexdigest(),self._credit(status,outcome,effect['capability']),time.time()))
        return cid
    def _finish_tx(self,db,effect_id,outcome,status):
        row=db.execute('SELECT status FROM effects WHERE effect_id=?',(effect_id,)).fetchone()
        if not row: raise KeyError(effect_id)
        if row['status']!='PENDING': raise RuntimeError(f"effect is not pending: {row['status']}")
        audit_outcome=self._outcome_receipt(outcome)
        db.execute('UPDATE effects SET status=?,outcome=?,verified_at=? WHERE effect_id=?',(status,self._payload(audit_outcome),time.time(),effect_id))
        return self._reenter_tx(db,effect_id,status,outcome)
    def complete(self,effect_id,outcome,status):
        if status not in self.FINAL-{'VERIFIED'}: raise ValueError(status)
        with self.db.tx() as db: return self._finish_tx(db,effect_id,outcome,status)
    def complete_verified(self,effect_id,outcome,session_id,user_id,generation,lease:Lease|None=None):
        stale=None
        with self.db.tx() as db:
            effect=db.execute('SELECT user_id,requested_generation FROM effects WHERE effect_id=?',(effect_id,)).fetchone()
            if not effect: raise KeyError(effect_id)
            if effect['user_id']!=user_id:
                raise PermissionError('effect owner mismatch')
            if int(effect['requested_generation'])!=int(generation):
                stale=StaleGeneration(effect_id)
            if stale is None:
                try: self._assert_generation_tx(db,session_id,user_id,generation)
                except (StaleGeneration,PermissionError) as exc: stale=exc
            if stale is None and lease is not None:
                try: self._assert_lease_tx(db,lease)
                except StaleGeneration as exc: stale=exc
            status='STALE_OUTCOME' if stale else 'VERIFIED'
            cid=self._finish_tx(db,effect_id,outcome,status)
        if stale: raise stale
        return cid
    def recover_pending(self):
        rows=self.db.db.execute("SELECT effect_id FROM effects WHERE status='PENDING' ORDER BY ts").fetchall()
        if not rows: return 0
        outcome={'ok':False,'certainty':'unknown','reason':'restart_before_verified_outcome'}
        with self.db.tx() as db:
            for row in rows:
                self._finish_tx(db,row['effect_id'],outcome,'UNKNOWN_AFTER_RESTART')
        return len(rows)
    def causal_for(self,effect_id):
        row=self.db.db.execute('SELECT causal_id FROM causal_episodes WHERE effect_id=? ORDER BY ts DESC LIMIT 1',(effect_id,)).fetchone(); return row[0] if row else None
