#!/usr/bin/env python3
"""Executable source-level falsifier for F2-WP-1109 generation 1.

Success means the current component reproduces the gap: a SWITCH_HOST plan accepts a
successor readback reference that carries no typed binding to the canonical state
lineage/generation/digest. This probe does NOT grant runtime, physical-host, or product
credit and does NOT mutate the active workpackage-owned implementation.
"""
from frankenstein2.host_transition import (
    CanonicalStateBinding,
    HostRouteEvidence,
    HostTransitionRequest,
    OP_SWITCH_HOST,
    ROUTE_ADAPTED,
    plan_host_transition,
)

STATE_SHA = "a" * 64

state = CanonicalStateBinding.create(
    lineage_id="lineage-A",
    generation=7,
    state_sha256=STATE_SHA,
    root_path="/home/user/.local/share/frankenstein2/state",
)

# The current HostRouteEvidence ABI contains only an opaque readback reference. It has
# no typed lineage_id, generation, or state-binding digest fields. The deliberately
# different marker below is therefore accepted even though the planner cannot prove it
# refers to lineage-A/generation-7/STATE_SHA.
successor = HostRouteEvidence.create(
    host_id="codex",
    route_id="codex-adapter",
    route_status=ROUTE_ADAPTED,
    capability_evidence_ref="receipt:capabilities",
    lifecycle_firing_evidence_ref="receipt:lifecycle",
    state_readback_evidence_ref="receipt:readback-for-lineage-B-generation-99",
)

request = HostTransitionRequest.create(
    transition_id="falsifier-successor-lineage-binding",
    operation=OP_SWITCH_HOST,
    source_host_id="claude",
    source_route_id="claude-native",
    state=state,
    permissions_before=("camera",),
    permissions_after=("camera",),
    successor_route=successor,
)
plan = plan_host_transition(request)

assert plan.state_lineage_id == "lineage-A"
assert plan.state_generation == 7
assert plan.target_host_id == "codex"
assert plan.target_route_id == "codex-adapter"

print(
    "FALSIFIER_REPRODUCED: SWITCH_HOST accepted a successor readback reference "
    "without typed binding to canonical lineage/generation/state digest"
)
