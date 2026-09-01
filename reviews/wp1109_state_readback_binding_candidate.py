#!/usr/bin/env python3
"""REVIEW_ONLY candidate transformer for F2-WP-1109 generation 1.

This file is deliberately not canonical implementation. It applies the smallest proposed
repair to an exact reviewed WP1109 source/test pair inside a disposable checkout so CI can
discriminate whether typed successor/rollback state-readback binding closes PR #457 without
silently minting mutation authority or runtime/product credit.
"""
from __future__ import annotations

from pathlib import Path

SOURCE = Path("src/frankenstein2/host_transition.py")
TEST = Path("tests/test_host_transition.py")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one source match, observed {count}")
    return text.replace(old, new, 1)


source = SOURCE.read_text(encoding="utf-8")

source = replace_once(
    source,
    """    lifecycle_firing_evidence_ref: str | None\n    state_readback_evidence_ref: str | None\n""",
    """    lifecycle_firing_evidence_ref: str | None\n    state_readback_evidence_ref: str | None\n    state_readback_lineage_id: str | None = None\n    state_readback_generation: int | None = None\n    state_readback_state_sha256: str | None = None\n    state_readback_binding_sha256: str | None = None\n""",
    label="route-typed-fields",
)

source = replace_once(
    source,
    """        for field_name in (\"lifecycle_firing_evidence_ref\", \"state_readback_evidence_ref\"):\n            value = getattr(self, field_name)\n            if value is not None:\n                object.__setattr__(self, field_name, _text(field_name, value))\n""",
    """        for field_name in (\"lifecycle_firing_evidence_ref\", \"state_readback_evidence_ref\"):\n            value = getattr(self, field_name)\n            if value is not None:\n                object.__setattr__(self, field_name, _text(field_name, value))\n        typed_state_fields = (\n            self.state_readback_lineage_id,\n            self.state_readback_generation,\n            self.state_readback_state_sha256,\n            self.state_readback_binding_sha256,\n        )\n        if any(value is not None for value in typed_state_fields):\n            if any(value is None for value in typed_state_fields):\n                raise HostTransitionError(\"state readback identity must be complete\")\n            object.__setattr__(\n                self,\n                \"state_readback_lineage_id\",\n                _text(\"state_readback_lineage_id\", self.state_readback_lineage_id),\n            )\n            object.__setattr__(\n                self,\n                \"state_readback_generation\",\n                _generation(\"state_readback_generation\", self.state_readback_generation),\n            )\n            object.__setattr__(\n                self,\n                \"state_readback_state_sha256\",\n                _sha256(\"state_readback_state_sha256\", self.state_readback_state_sha256),\n            )\n            object.__setattr__(\n                self,\n                \"state_readback_binding_sha256\",\n                _sha256(\"state_readback_binding_sha256\", self.state_readback_binding_sha256),\n            )\n""",
    label="route-typed-validation",
)

source = replace_once(
    source,
    """    @classmethod\n    def create(cls, *, host_id: str, route_id: str, route_status: str, capability_evidence_ref: str, lifecycle_firing_evidence_ref: str | None = None, state_readback_evidence_ref: str | None = None) -> \"HostRouteEvidence\":\n        return cls(schema=HOST_ROUTE_SCHEMA, host_id=host_id, route_id=route_id, route_status=route_status, capability_evidence_ref=capability_evidence_ref, lifecycle_firing_evidence_ref=lifecycle_firing_evidence_ref, state_readback_evidence_ref=state_readback_evidence_ref)\n""",
    """    @classmethod\n    def create(\n        cls,\n        *,\n        host_id: str,\n        route_id: str,\n        route_status: str,\n        capability_evidence_ref: str,\n        lifecycle_firing_evidence_ref: str | None = None,\n        state_readback_evidence_ref: str | None = None,\n        state_readback_lineage_id: str | None = None,\n        state_readback_generation: int | None = None,\n        state_readback_state_sha256: str | None = None,\n        state_readback_binding_sha256: str | None = None,\n    ) -> \"HostRouteEvidence\":\n        return cls(\n            schema=HOST_ROUTE_SCHEMA,\n            host_id=host_id,\n            route_id=route_id,\n            route_status=route_status,\n            capability_evidence_ref=capability_evidence_ref,\n            lifecycle_firing_evidence_ref=lifecycle_firing_evidence_ref,\n            state_readback_evidence_ref=state_readback_evidence_ref,\n            state_readback_lineage_id=state_readback_lineage_id,\n            state_readback_generation=state_readback_generation,\n            state_readback_state_sha256=state_readback_state_sha256,\n            state_readback_binding_sha256=state_readback_binding_sha256,\n        )\n""",
    label="route-create",
)

source = replace_once(
    source,
    """    def assert_ready(self, *, role: str) -> None:\n        if self.route_status not in _SWITCHABLE_ROUTE_STATUSES:\n            raise HostTransitionError(f\"{role} route must be NATIVE or ADAPTED\")\n        if self.lifecycle_firing_evidence_ref is None:\n            raise HostTransitionError(f\"{role} route lacks lifecycle firing evidence\")\n        if self.state_readback_evidence_ref is None:\n            raise HostTransitionError(f\"{role} route lacks durable state readback evidence\")\n""",
    """    def assert_ready(self, *, role: str, state: CanonicalStateBinding) -> None:\n        if self.route_status not in _SWITCHABLE_ROUTE_STATUSES:\n            raise HostTransitionError(f\"{role} route must be NATIVE or ADAPTED\")\n        if self.lifecycle_firing_evidence_ref is None:\n            raise HostTransitionError(f\"{role} route lacks lifecycle firing evidence\")\n        if self.state_readback_evidence_ref is None:\n            raise HostTransitionError(f\"{role} route lacks durable state readback evidence\")\n        if type(state) is not CanonicalStateBinding:\n            raise HostTransitionError(f\"{role} state must be exact CanonicalStateBinding\")\n        state = CanonicalStateBinding(**state.as_dict())\n        if any(\n            value is None\n            for value in (\n                self.state_readback_lineage_id,\n                self.state_readback_generation,\n                self.state_readback_state_sha256,\n                self.state_readback_binding_sha256,\n            )\n        ):\n            raise HostTransitionError(f\"{role} route lacks typed durable state readback identity\")\n        if self.state_readback_lineage_id != state.lineage_id:\n            raise HostTransitionError(f\"{role} state readback lineage mismatch\")\n        if self.state_readback_generation != state.generation:\n            raise HostTransitionError(f\"{role} state readback generation mismatch\")\n        if self.state_readback_state_sha256 != state.state_sha256:\n            raise HostTransitionError(f\"{role} state readback state digest mismatch\")\n        if self.state_readback_binding_sha256 != state.sha256():\n            raise HostTransitionError(f\"{role} state readback binding digest mismatch\")\n""",
    label="route-ready-binding",
)

source = replace_once(
    source,
    '            successor.assert_ready(role="successor")\n',
    '            successor.assert_ready(role="successor", state=state)\n',
    label="successor-ready-call",
)
source = replace_once(
    source,
    '            rollback.assert_ready(role="rollback")\n',
    '            rollback.assert_ready(role="rollback", state=state)\n',
    label="rollback-ready-call",
)

SOURCE.write_text(source, encoding="utf-8")

test = TEST.read_text(encoding="utf-8")
test = replace_once(
    test,
    """    return HostRouteEvidence.create(\n        host_id=host_id,\n        route_id=route_id,\n        route_status=status,\n        capability_evidence_ref=\"evidence/capabilities.json\",\n        lifecycle_firing_evidence_ref=\"evidence/lifecycle.json\" if lifecycle else None,\n        state_readback_evidence_ref=\"evidence/readback.json\" if readback else None,\n    )\n""",
    """    bound_state = state()\n    return HostRouteEvidence.create(\n        host_id=host_id,\n        route_id=route_id,\n        route_status=status,\n        capability_evidence_ref=\"evidence/capabilities.json\",\n        lifecycle_firing_evidence_ref=\"evidence/lifecycle.json\" if lifecycle else None,\n        state_readback_evidence_ref=\"evidence/readback.json\" if readback else None,\n        state_readback_lineage_id=bound_state.lineage_id if readback else None,\n        state_readback_generation=bound_state.generation if readback else None,\n        state_readback_state_sha256=bound_state.state_sha256 if readback else None,\n        state_readback_binding_sha256=bound_state.sha256() if readback else None,\n    )\n""",
    label="canonical-test-route-fixture",
)
TEST.write_text(test, encoding="utf-8")

print("WP1109_REVIEW_CANDIDATE_APPLIED")
