"""F2-WP-1102 deterministic Claude Code host-route candidate contract.

Plans/validates only. No host probing or mutation, no model/provider/tool calls,
no UnifiedDB/effect/completion authority, and no physical-host runtime credit.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json, re
from typing import Any

SCHEMA_REPORT = "FRANKENSTEIN2_CLAUDE_CODE_CAPABILITY_REPORT/v1"
SCHEMA_RELEASE = "FRANKENSTEIN2_RELEASE_IDENTITY/v1"
SCHEMA_STATE = "FRANKENSTEIN2_STATE_LINEAGE_IDENTITY/v1"
SCHEMA_ROUTE = "FRANKENSTEIN2_CLAUDE_CODE_ROUTE_CANDIDATE/v1"
CLASSIFICATION = "INSTALL_ROUTE_CANDIDATE_NOT_INSTALL_RUNTIME_EFFECT_OR_COMPLETION_PROOF"

SESSION_START="SESSION_START"; USER_TURN="USER_TURN"; PRE_EFFECT="PRE_EFFECT"
POST_EFFECT="POST_EFFECT"; SESSION_STOP="SESSION_STOP"
PRE_COMPACT="PRE_COMPACT_OR_CHECKPOINT"; TOOL_RESULT="TOOL_RESULT_RETURN"
BACKGROUND_WAKE="BACKGROUND_WAKE"
ALL_ROLES=(SESSION_START,USER_TURN,PRE_EFFECT,POST_EFFECT,SESSION_STOP,PRE_COMPACT,TOOL_RESULT,BACKGROUND_WAKE)
HARD=(SESSION_START,USER_TURN,PRE_EFFECT,POST_EFFECT,SESSION_STOP,TOOL_RESULT)
SOFT=(PRE_COMPACT,)
NATIVE="NATIVE"; ADAPTED="ADAPTED"; DEGRADED="DEGRADED"; BLOCKED="BLOCKED"
DURABLE="DURABLE_USER_STATE"; DISPOSABLE="DISPOSABLE_HOST_CACHE"
_SHA=re.compile(r"^[0-9a-f]{64}$")

class ClaudeCodeRouteError(ValueError): pass

def _txt(n,v):
    if type(v) is not str or not v or v != v.strip() or len(v)>1024 or any(ord(c)<32 or ord(c)==127 for c in v):
        raise ClaudeCodeRouteError(f"invalid {n}")
    return v

def _sha(n,v):
    if type(v) is not str or _SHA.fullmatch(v) is None: raise ClaudeCodeRouteError(f"invalid {n} SHA-256")
    return v

def _refs(n,v,empty=False):
    if type(v) is not tuple or (not empty and not v) or len(v)!=len(set(v)) or v!=tuple(sorted(v)):
        raise ClaudeCodeRouteError(f"invalid {n}")
    for x in v: _txt(n,x)
    return v

def _cj(v): return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
def _dg(v): return hashlib.sha256(_cj(v).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class HostRoleCapability:
    role:str; supported:bool; surface:str|None=None; mode:str|None=None
    firing_ref:str|None=None; payload_ref:str|None=None; timing_ref:str|None=None; multiplicity_ref:str|None=None
    def __post_init__(self):
        if self.role not in ALL_ROLES or type(self.supported) is not bool: raise ClaudeCodeRouteError("invalid role capability")
        extras=(self.surface,self.mode,self.firing_ref,self.payload_ref,self.timing_ref,self.multiplicity_ref)
        if not self.supported:
            if any(x is not None for x in extras): raise ClaudeCodeRouteError("unsupported role carries evidence")
            return
        _txt("surface",self.surface)
        if self.mode not in (NATIVE,ADAPTED): raise ClaudeCodeRouteError("invalid binding mode")
        for n,x in zip(("firing","payload","timing","multiplicity"),extras[2:]):
            if x is not None: _txt(n,x)
    @property
    def verified(self): return bool(self.supported and self.firing_ref and self.payload_ref and self.timing_ref and self.multiplicity_ref)
    def as_dict(self): return {"role":self.role,"supported":self.supported,"surface":self.surface,"mode":self.mode,"firing_ref":self.firing_ref,"payload_ref":self.payload_ref,"timing_ref":self.timing_ref,"multiplicity_ref":self.multiplicity_ref}

@dataclass(frozen=True,slots=True)
class ClaudeCapabilityReport:
    report_id:str; host_version:str; generation:int; capabilities:tuple[HostRoleCapability,...]; provenance_refs:tuple[str,...]
    baseline_vps_required:bool=False; schema:str=SCHEMA_REPORT; classification:str=CLASSIFICATION
    def __post_init__(self):
        if self.schema!=SCHEMA_REPORT or self.classification!=CLASSIFICATION: raise ClaudeCodeRouteError("report schema mismatch")
        _txt("host_version",self.host_version)
        if type(self.generation) is not int or self.generation<1: raise ClaudeCodeRouteError("invalid generation")
        if type(self.baseline_vps_required) is not bool or type(self.capabilities) is not tuple: raise ClaudeCodeRouteError("invalid report fields")
        if any(type(x) is not HostRoleCapability for x in self.capabilities): raise ClaudeCodeRouteError("non-exact capability")
        roles=tuple(x.role for x in self.capabilities)
        if len(roles)!=len(set(roles)) or roles!=tuple(sorted(roles)): raise ClaudeCodeRouteError("capability roles must be unique/canonical")
        _refs("provenance_refs",self.provenance_refs)
        if self.report_id!="claude-capability:"+_dg(self.payload()): raise ClaudeCodeRouteError("report_id mismatch")
    def payload(self): return {"schema":SCHEMA_REPORT,"host":"CLAUDE_CODE","host_version":self.host_version,"generation":self.generation,"capabilities":[x.as_dict() for x in self.capabilities],"provenance_refs":list(self.provenance_refs),"baseline_vps_required":self.baseline_vps_required,"classification":CLASSIFICATION}
    def sha256(self): return _dg({"report_id":self.report_id,**self.payload()})
    @classmethod
    def create(cls,*,host_version,generation,capabilities,provenance_refs,baseline_vps_required=False):
        if type(capabilities) is not tuple: raise ClaudeCodeRouteError("capabilities must be tuple")
        ordered=tuple(sorted(capabilities,key=lambda x:x.role)); payload={"schema":SCHEMA_REPORT,"host":"CLAUDE_CODE","host_version":host_version,"generation":generation,"capabilities":[x.as_dict() for x in ordered],"provenance_refs":list(provenance_refs),"baseline_vps_required":baseline_vps_required,"classification":CLASSIFICATION}
        return cls("claude-capability:"+_dg(payload),host_version,generation,ordered,provenance_refs,baseline_vps_required)

@dataclass(frozen=True,slots=True)
class ReleaseIdentity:
    release_id:str; version:str; manifest_sha256:str; source_tree_sha256:str; provenance_refs:tuple[str,...]; schema:str=SCHEMA_RELEASE
    def __post_init__(self):
        if self.schema!=SCHEMA_RELEASE: raise ClaudeCodeRouteError("release schema mismatch")
        _txt("version",self.version); _sha("manifest",self.manifest_sha256); _sha("source_tree",self.source_tree_sha256); _refs("provenance_refs",self.provenance_refs)
        if self.release_id!="release:"+_dg(self.payload()): raise ClaudeCodeRouteError("release_id mismatch")
    def payload(self): return {"schema":SCHEMA_RELEASE,"version":self.version,"manifest_sha256":self.manifest_sha256,"source_tree_sha256":self.source_tree_sha256,"provenance_refs":list(self.provenance_refs)}
    def sha256(self): return _dg({"release_id":self.release_id,**self.payload()})
    @classmethod
    def create(cls,*,version,manifest_sha256,source_tree_sha256,provenance_refs):
        payload={"schema":SCHEMA_RELEASE,"version":version,"manifest_sha256":manifest_sha256,"source_tree_sha256":source_tree_sha256,"provenance_refs":list(provenance_refs)}
        return cls("release:"+_dg(payload),version,manifest_sha256,source_tree_sha256,provenance_refs)

@dataclass(frozen=True,slots=True)
class StateLineageIdentity:
    lineage_id:str; generation:int; state_root:str; root_kind:str; state_digest:str; persistence_ref:str|None; cache_exclusion_ref:str|None; provenance_refs:tuple[str,...]; schema:str=SCHEMA_STATE
    def __post_init__(self):
        if self.schema!=SCHEMA_STATE or type(self.generation) is not int or self.generation<1: raise ClaudeCodeRouteError("state schema/generation mismatch")
        _txt("state_root",self.state_root); _sha("state_digest",self.state_digest); _refs("provenance_refs",self.provenance_refs)
        if self.root_kind not in (DURABLE,DISPOSABLE): raise ClaudeCodeRouteError("invalid root kind")
        if self.persistence_ref is not None: _txt("persistence_ref",self.persistence_ref)
        if self.cache_exclusion_ref is not None: _txt("cache_exclusion_ref",self.cache_exclusion_ref)
        if self.lineage_id!="state-lineage:"+_dg(self.payload()): raise ClaudeCodeRouteError("lineage_id mismatch")
    def payload(self): return {"schema":SCHEMA_STATE,"generation":self.generation,"state_root":self.state_root,"root_kind":self.root_kind,"state_digest":self.state_digest,"persistence_ref":self.persistence_ref,"cache_exclusion_ref":self.cache_exclusion_ref,"provenance_refs":list(self.provenance_refs)}
    def sha256(self): return _dg({"lineage_id":self.lineage_id,**self.payload()})
    @classmethod
    def create(cls,*,generation,state_root,root_kind,state_digest,persistence_ref,cache_exclusion_ref,provenance_refs):
        payload={"schema":SCHEMA_STATE,"generation":generation,"state_root":state_root,"root_kind":root_kind,"state_digest":state_digest,"persistence_ref":persistence_ref,"cache_exclusion_ref":cache_exclusion_ref,"provenance_refs":list(provenance_refs)}
        return cls("state-lineage:"+_dg(payload),generation,state_root,root_kind,state_digest,persistence_ref,cache_exclusion_ref,provenance_refs)

@dataclass(frozen=True,slots=True)
class ClaudeInstallRouteCandidate:
    route_id:str; capability_report_id:str; capability_report_sha256:str; release_id:str; release_sha256:str; state_lineage_id:str; state_lineage_sha256:str
    status:str; verified_roles:tuple[str,...]; adapted_roles:tuple[str,...]; limitations:tuple[str,...]
    vps_required_for_baseline:bool=False; effect_authority:str="NONE"; completion_authority:str="NONE"; install_runtime_credit:int=0; schema:str=SCHEMA_ROUTE; classification:str=CLASSIFICATION
    def __post_init__(self):
        if self.schema!=SCHEMA_ROUTE or self.classification!=CLASSIFICATION or self.status not in (NATIVE,ADAPTED,DEGRADED,BLOCKED): raise ClaudeCodeRouteError("route schema/status mismatch")
        for n,v in (("report",self.capability_report_sha256),("release",self.release_sha256),("state",self.state_lineage_sha256)): _sha(n,v)
        _refs("verified_roles",self.verified_roles,True); _refs("adapted_roles",self.adapted_roles,True); _refs("limitations",self.limitations,True)
        if self.vps_required_for_baseline or self.effect_authority!="NONE" or self.completion_authority!="NONE" or self.install_runtime_credit!=0: raise ClaudeCodeRouteError("route carries forbidden authority/runtime credit")
        if self.route_id!="claude-route:"+_dg(self.payload()): raise ClaudeCodeRouteError("route_id mismatch")
    def payload(self): return {"schema":SCHEMA_ROUTE,"capability_report_id":self.capability_report_id,"capability_report_sha256":self.capability_report_sha256,"release_id":self.release_id,"release_sha256":self.release_sha256,"state_lineage_id":self.state_lineage_id,"state_lineage_sha256":self.state_lineage_sha256,"status":self.status,"verified_roles":list(self.verified_roles),"adapted_roles":list(self.adapted_roles),"limitations":list(self.limitations),"vps_required_for_baseline":False,"effect_authority":"NONE","completion_authority":"NONE","install_runtime_credit":0,"classification":CLASSIFICATION}
    def sha256(self): return _dg({"route_id":self.route_id,**self.payload()})

def plan_claude_code_route(*,capability_report,release,state_lineage):
    if type(capability_report) is not ClaudeCapabilityReport or type(release) is not ReleaseIdentity or type(state_lineage) is not StateLineageIdentity: raise ClaudeCodeRouteError("exact canonical input types required")
    r=ClaudeCapabilityReport(capability_report.report_id,capability_report.host_version,capability_report.generation,capability_report.capabilities,capability_report.provenance_refs,capability_report.baseline_vps_required)
    rel=ReleaseIdentity(release.release_id,release.version,release.manifest_sha256,release.source_tree_sha256,release.provenance_refs)
    st=StateLineageIdentity(state_lineage.lineage_id,state_lineage.generation,state_lineage.state_root,state_lineage.root_kind,state_lineage.state_digest,state_lineage.persistence_ref,state_lineage.cache_exclusion_ref,state_lineage.provenance_refs)
    by={x.role:x for x in r.capabilities}; verified=[]; adapted=[]; limits=[]; hard=False; degraded=False
    if r.baseline_vps_required: hard=True; limits.append("VPS_REQUIRED_CONTRADICTS_LOCAL_BASELINE_PRODUCT")
    if st.root_kind!=DURABLE: hard=True; limits.append("STATE_ROOT_IS_DISPOSABLE_HOST_CACHE")
    if not st.persistence_ref: hard=True; limits.append("STATE_PERSISTENCE_EVIDENCE_MISSING")
    if not st.cache_exclusion_ref: hard=True; limits.append("STATE_CACHE_EXCLUSION_EVIDENCE_MISSING")
    for role in HARD:
        c=by.get(role)
        if c is None or not c.supported: hard=True; limits.append(f"REQUIRED_ROLE_UNAVAILABLE:{role}")
        elif not c.verified: hard=True; limits.append(f"REQUIRED_ROLE_FIRING_UNVERIFIED:{role}")
        else:
            verified.append(role)
            if c.mode==ADAPTED: adapted.append(role)
    c=by.get(PRE_COMPACT)
    if c is None or not c.supported: degraded=True; limits.append(f"CHECKPOINT_ROLE_UNAVAILABLE:{PRE_COMPACT}")
    elif not c.verified: degraded=True; limits.append(f"CHECKPOINT_ROLE_FIRING_UNVERIFIED:{PRE_COMPACT}")
    else:
        verified.append(PRE_COMPACT)
        if c.mode==ADAPTED: adapted.append(PRE_COMPACT)
    bg=by.get(BACKGROUND_WAKE)
    if bg is None or not bg.supported or not bg.verified: limits.append("BACKGROUND_WAKE_NOT_HOST_VERIFIED_OPTIONAL")
    elif bg.mode==ADAPTED: limits.append("BACKGROUND_WAKE_ADAPTED")
    status=BLOCKED if hard else DEGRADED if degraded else ADAPTED if adapted else NATIVE
    vr=tuple(sorted(verified)); ar=tuple(sorted(adapted)); lm=tuple(sorted(set(limits)))
    payload={"schema":SCHEMA_ROUTE,"capability_report_id":r.report_id,"capability_report_sha256":r.sha256(),"release_id":rel.release_id,"release_sha256":rel.sha256(),"state_lineage_id":st.lineage_id,"state_lineage_sha256":st.sha256(),"status":status,"verified_roles":list(vr),"adapted_roles":list(ar),"limitations":list(lm),"vps_required_for_baseline":False,"effect_authority":"NONE","completion_authority":"NONE","install_runtime_credit":0,"classification":CLASSIFICATION}
    return ClaudeInstallRouteCandidate("claude-route:"+_dg(payload),r.report_id,r.sha256(),rel.release_id,rel.sha256(),st.lineage_id,st.sha256(),status,vr,ar,lm)

def validate_claude_code_route(candidate,*,capability_report,release,state_lineage):
    if type(candidate) is not ClaudeInstallRouteCandidate: raise ClaudeCodeRouteError("exact route candidate required")
    expected=plan_claude_code_route(capability_report=capability_report,release=release,state_lineage=state_lineage)
    if candidate!=expected or candidate.sha256()!=expected.sha256(): raise ClaudeCodeRouteError("route candidate recomputation mismatch")
    return candidate
