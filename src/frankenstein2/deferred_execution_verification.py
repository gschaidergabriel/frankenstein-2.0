"""Fail-closed F2-WP-104 -> F2-WP-105 verification correlation boundary.

This module does not execute a child, perform an effect, write UnifiedDB, infer a
world outcome, or mint completion. It preserves the already-authoritative WP-102
identity carried by the canonical WP-104 ``DeferredReturnEnvelope`` while a WP-105
verification transition is applied.

The purpose is narrow: a generic WP-105 ``ExecutionLineage`` intentionally carries a
small execution state-machine identity. Before a returned child observation may change
that state, this adapter requires the exact return/binding/invocation/tool-use/delegation/
result/child identity to match the target. Digest equality alone is not a correlation
key.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from state.execution_completion import (
    ExecutionLineage,
    ExecutionStage,
    VerifyExecution,
    apply_execution_transition,
)

from .deferred_return import DeferredReturnEnvelope


class DeferredExecutionVerificationError(ValueError):
    """Raised when deferred-return identity does not match a WP-105 target."""


@dataclass(frozen=True, slots=True)
class DeferredExecutionVerificationTarget:
    """One result-bound canonical WP-104 return paired with its WP-105 execution record."""

    returned: DeferredReturnEnvelope
    lineage: ExecutionLineage

    def __post_init__(self) -> None:
        if not isinstance(self.returned, DeferredReturnEnvelope):
            raise DeferredExecutionVerificationError("returned must be a DeferredReturnEnvelope")
        if not isinstance(self.lineage, ExecutionLineage):
            raise DeferredExecutionVerificationError("lineage must be an ExecutionLineage")
        binding = self.returned.binding
        child = binding.child
        if not binding.has_result:
            raise DeferredExecutionVerificationError("target requires a result-bound WP-102 binding")
        if self.lineage.causal_id != child.causal_id:
            raise DeferredExecutionVerificationError("lineage causal_id must equal bound child causal_id")
        if self.lineage.generation != child.generation:
            raise DeferredExecutionVerificationError("lineage generation must equal bound child generation")
        if self.lineage.stage not in (
            ExecutionStage.EXECUTION_RECORDED,
            ExecutionStage.VERIFIED_APPLIED,
            ExecutionStage.VERIFIED_NOT_APPLIED,
        ):
            raise DeferredExecutionVerificationError(
                "target lineage must be execution-recorded or verified"
            )


@dataclass(frozen=True, slots=True)
class CorrelatedVerification:
    """Explicit observation identity plus the generic WP-105 verification transition."""

    return_id: str
    binding_id: str
    invocation_id: str
    tool_use_id: str
    delegation_id: str
    child_identity_sha256: str
    result_id: str
    result_sha256: str
    transition: VerifyExecution

    @classmethod
    def for_target(
        cls,
        target: DeferredExecutionVerificationTarget,
        transition: VerifyExecution,
    ) -> "CorrelatedVerification":
        if not isinstance(target, DeferredExecutionVerificationTarget):
            raise DeferredExecutionVerificationError(
                "target must be a DeferredExecutionVerificationTarget"
            )
        if not isinstance(transition, VerifyExecution):
            raise DeferredExecutionVerificationError("transition must be VerifyExecution")
        binding = target.returned.binding
        assert binding.result_id is not None
        assert binding.result_sha256 is not None
        return cls(
            return_id=target.returned.return_id,
            binding_id=binding.binding_id(),
            invocation_id=binding.invocation_id,
            tool_use_id=binding.tool_use_id,
            delegation_id=binding.delegation_id,
            child_identity_sha256=binding.child.sha256(),
            result_id=binding.result_id,
            result_sha256=binding.result_sha256,
            transition=transition,
        )


def _require_equal(name: str, observed: str, expected: str) -> None:
    if observed != expected:
        raise DeferredExecutionVerificationError(f"{name}_MISMATCH")


def apply_correlated_verification(
    target: DeferredExecutionVerificationTarget,
    observed: CorrelatedVerification,
) -> DeferredExecutionVerificationTarget:
    """Apply a WP-105 verification only after exact WP-102/WP-104 identity match.

    All correlation checks happen before the generic WP-105 transition function is
    called. Because both layers are immutable, rejection leaves the target unchanged.
    Exact transition replay remains idempotent through WP-105's payload fingerprint.
    """
    if not isinstance(target, DeferredExecutionVerificationTarget):
        raise DeferredExecutionVerificationError(
            "target must be a DeferredExecutionVerificationTarget"
        )
    if not isinstance(observed, CorrelatedVerification):
        raise DeferredExecutionVerificationError("observed must be a CorrelatedVerification")

    binding = target.returned.binding
    if binding.result_id is None or binding.result_sha256 is None:
        raise DeferredExecutionVerificationError("target binding result identity is incomplete")

    _require_equal("RETURN_ID", observed.return_id, target.returned.return_id)
    _require_equal("BINDING_ID", observed.binding_id, binding.binding_id())
    _require_equal("INVOCATION_ID", observed.invocation_id, binding.invocation_id)
    _require_equal("TOOL_USE_ID", observed.tool_use_id, binding.tool_use_id)
    _require_equal("DELEGATION_ID", observed.delegation_id, binding.delegation_id)
    _require_equal("CHILD_IDENTITY_SHA256", observed.child_identity_sha256, binding.child.sha256())
    _require_equal("RESULT_ID", observed.result_id, binding.result_id)
    _require_equal("RESULT_SHA256", observed.result_sha256, binding.result_sha256)

    next_lineage = apply_execution_transition(target.lineage, observed.transition)
    return replace(target, lineage=next_lineage)


__all__ = [
    "CorrelatedVerification",
    "DeferredExecutionVerificationError",
    "DeferredExecutionVerificationTarget",
    "apply_correlated_verification",
]
