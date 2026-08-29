from dataclasses import replace
import pytest
from frankenstein2.claude_code_route import *
A="a"*64; B="b"*64

def cap(role,supported=True,mode=NATIVE,verified=True):
    if not supported: return HostRoleCapability(role,False)
    e=f"e:{role}" if verified else None
    return HostRoleCapability(role,True,f"claude:{role}",mode,e,f"p:{role}" if verified else None,f"t:{role}" if verified else None,f"m:{role}" if verified else None)

def report(overrides=None,vps=False):
    o=overrides or {}; items=tuple(reversed(tuple(o.get(r,cap(r)) for r in ALL_ROLES)))
    return ClaudeCapabilityReport.create(host_version="1.2.3",generation=1,capabilities=items,provenance_refs=("probe:host",),baseline_vps_required=vps)

def rel(): return ReleaseIdentity.create(version="2.0-dev",manifest_sha256=A,source_tree_sha256=B,provenance_refs=("release:manifest",))
def state(kind=DURABLE,persist="probe:persist",exclude="probe:no-cache"): return StateLineageIdentity.create(generation=1,state_root="/home/u/.local/share/f2",root_kind=kind,state_digest=A,persistence_ref=persist,cache_exclusion_ref=exclude,provenance_refs=("state:lineage",))
def plan(r=None,s=None): return plan_claude_code_route(capability_report=r or report(),release=rel(),state_lineage=s or state())

def test_native_candidate_has_zero_authority_credit():
    x=plan(); assert x.status==NATIVE; assert set(x.verified_roles)==set(HARD+(PRE_COMPACT,)); assert x.effect_authority==x.completion_authority=="NONE"; assert x.install_runtime_credit==0

def test_adapted_required_binding_is_adapted(): assert plan(report({USER_TURN:cap(USER_TURN,mode=ADAPTED)})).status==ADAPTED
def test_missing_checkpoint_is_degraded(): assert plan(report({PRE_COMPACT:cap(PRE_COMPACT,False)})).status==DEGRADED
def test_missing_hard_role_blocks(): assert plan(report({POST_EFFECT:cap(POST_EFFECT,False)})).status==BLOCKED

def test_matching_name_without_firing_evidence_does_not_prove_capability():
    x=plan(report({SESSION_START:cap(SESSION_START,verified=False)})); assert x.status==BLOCKED; assert f"REQUIRED_ROLE_FIRING_UNVERIFIED:{SESSION_START}" in x.limitations

def test_disposable_state_blocks(): assert plan(s=state(DISPOSABLE)).status==BLOCKED
def test_missing_state_persistence_evidence_blocks(): assert plan(s=state(persist=None,exclude=None)).status==BLOCKED
def test_vps_cannot_be_baseline_prerequisite(): assert plan(report(vps=True)).status==BLOCKED

def test_background_wake_is_optional():
    x=plan(report({BACKGROUND_WAKE:cap(BACKGROUND_WAKE,False)})); assert x.status==NATIVE; assert "BACKGROUND_WAKE_NOT_HOST_VERIFIED_OPTIONAL" in x.limitations

def test_duplicate_role_rejected():
    with pytest.raises(ClaudeCodeRouteError,match="unique"):
        ClaudeCapabilityReport.create(host_version="1",generation=1,capabilities=tuple(cap(r) for r in ALL_ROLES)+(cap(USER_TURN),),provenance_refs=("p",))

def test_report_factory_order_deterministic():
    a=report(); b=ClaudeCapabilityReport.create(host_version="1.2.3",generation=1,capabilities=tuple(cap(r) for r in ALL_ROLES),provenance_refs=("probe:host",)); assert a.report_id==b.report_id and a.sha256()==b.sha256()

def test_status_tamper_fails_content_binding():
    x=plan(report({PRE_EFFECT:cap(PRE_EFFECT,False)})); assert x.status==BLOCKED
    with pytest.raises(ClaudeCodeRouteError,match="route_id"): replace(x,status=NATIVE)

def test_consumer_validation_recomputes_exact_candidate():
    r=report(); q=rel(); s=state(); x=plan_claude_code_route(capability_report=r,release=q,state_lineage=s); assert validate_claude_code_route(x,capability_report=r,release=q,state_lineage=s) is x

def test_bad_release_hash_fails_closed():
    with pytest.raises(ClaudeCodeRouteError,match="SHA-256"): ReleaseIdentity.create(version="2",manifest_sha256="BAD",source_tree_sha256=B,provenance_refs=("r",))
