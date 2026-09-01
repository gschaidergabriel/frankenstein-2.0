#!/usr/bin/env python3
"""REVIEW_ONLY discriminator for the WP1109 typed state-readback candidate.

This runs only after the exact-source-bound review transformer has been applied in a
disposable checkout. It proves the proposed boundary accepts a matching readback identity
and fails closed on untyped, lineage, generation, state-digest, binding-digest, and rollback
mismatches. Passing is candidate/component evidence only.
"""
from __future__ import annotations

from frankenstein2.host_transition import (
    CanonicalStateBinding,
    HostRouteEvidence,
    HostTransitionError,
    HostTransitionRequest,
    OP_REENABLE,
    OP_SWITCH_HOST,
    ROUTE_ADAPTED,
    ROUTE_NATIVE,
    plan_host_transition,
)

STATE_SHA = "a" * 64
OTHER_SHA = "b" * 64


def canonical_state() -> CanonicalStateBinding:
    return CanonicalStateBinding.create(
        lineage_id="lineage-A",
        generation=7,
        state_sha256=STATE_SHA,
        root_path="/home/user/.local/share/frankenstein2/state",
    )


def bound_route(
    state: CanonicalStateBinding,
    *,
    host_id: str = "codex",
    route_id: str = "codex-adapter",
    status: str = ROUTE_ADAPTED,
    lineage_id: str | None = None,
    generation: int | None = None,
    state_sha256: str | None = None,
    binding_sha256: str | None = None,
) -> HostRouteEvidence:
    return HostRouteEvidence.create(
        host_id=host_id,
        route_id=route_id,
        route_status=status,
        capability_evidence_ref="receipt:capabilities",
        lifecycle_firing_evidence_ref="receipt:lifecycle",
        state_readback_evidence_ref="receipt:readback",
        state_readback_lineage_id=state.lineage_id if lineage_id is None else lineage_id,
        state_readback_generation=state.generation if generation is None else generation,
        state_readback_state_sha256=state.state_sha256 if state_sha256 is None else state_sha256,
        state_readback_binding_sha256=state.sha256() if binding_sha256 is None else binding_sha256,
    )


def switch_request(state: CanonicalStateBinding, route: HostRouteEvidence) -> HostTransitionRequest:
    return HostTransitionRequest.create(
        transition_id="candidate-switch",
        operation=OP_SWITCH_HOST,
        source_host_id="claude",
        source_route_id="claude-native",
        state=state,
        permissions_before=("camera",),
        permissions_after=("camera",),
        successor_route=route,
    )


def expect_rejected(label: str, expected: str, fn) -> None:
    try:
        fn()
    except HostTransitionError as exc:
        if expected not in str(exc):
            raise AssertionError(f"{label}: wrong rejection: {exc}") from exc
    else:
        raise AssertionError(f"{label}: candidate accepted invalid state-readback evidence")


state = canonical_state()

# Positive control: exact typed readback identity is admitted at plan-only scope.
plan = plan_host_transition(switch_request(state, bound_route(state)))
assert plan.state_lineage_id == state.lineage_id
assert plan.state_generation == state.generation
assert plan.state_binding_sha256 == state.sha256()
assert plan.runtime_credit == 0
assert plan.physical_host_credit == 0
assert plan.whole_system_acceptance is False

# The original PR #457 counterexample must now fail closed even with a non-empty opaque ref.
untyped = HostRouteEvidence.create(
    host_id="codex",
    route_id="codex-adapter",
    route_status=ROUTE_ADAPTED,
    capability_evidence_ref="receipt:capabilities",
    lifecycle_firing_evidence_ref="receipt:lifecycle",
    state_readback_evidence_ref="receipt:readback-for-lineage-B-generation-99",
)
expect_rejected(
    "untyped-readback",
    "lacks typed durable state readback identity",
    lambda: switch_request(state, untyped),
)

expect_rejected(
    "lineage-mismatch",
    "lineage mismatch",
    lambda: switch_request(state, bound_route(state, lineage_id="lineage-B")),
)
expect_rejected(
    "generation-mismatch",
    "generation mismatch",
    lambda: switch_request(state, bound_route(state, generation=99)),
)
expect_rejected(
    "state-digest-mismatch",
    "state digest mismatch",
    lambda: switch_request(state, bound_route(state, state_sha256=OTHER_SHA)),
)
expect_rejected(
    "binding-digest-mismatch",
    "binding digest mismatch",
    lambda: switch_request(state, bound_route(state, binding_sha256=OTHER_SHA)),
)

# Rollback/re-enable must use the same state identity fence, not only host/route equality.
rollback = bound_route(
    state,
    host_id="claude",
    route_id="claude-native",
    status=ROUTE_NATIVE,
    generation=99,
)
expect_rejected(
    "rollback-generation-mismatch",
    "generation mismatch",
    lambda: HostTransitionRequest.create(
        transition_id="candidate-reenable",
        operation=OP_REENABLE,
        source_host_id="claude",
        source_route_id="claude-native",
        state=state,
        permissions_before=("camera",),
        permissions_after=("camera",),
        rollback_route=rollback,
    ),
)

print("WP1109_TYPED_STATE_READBACK_CANDIDATE_PASS")
