"""Fail-closed causal admission fence for F2-WP-900 generation 8.

The G8 observation-window receipt is intentionally a candidate surface.  Its
positive REENTRY path is recorder-origin bound, but its current negative trace
completeness metadata is supplied by the condition-aware caller.  Therefore a
structurally complete ``NO_REENTRY`` receipt MUST NOT be treated as causal
negative evidence until an independent complete-range event-source authority is
integrated.

This module makes that boundary executable: current negative absence always
admits as UNKNOWN.  There is deliberately no override/boolean/metadata argument
that can promote it.  A later successor may add an independent source-bound
range receipt as a new typed dependency; until then the only truthful result is
UNKNOWN.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from frankenstein2.gwt_reentry_observation_window import (
    NO_REENTRY_OBSERVED,
    REENTRY_OBSERVATION_UNKNOWN,
    REENTRY_OBSERVED,
    ReentryObservationWindowReceipt,
    validate_reentry_observation_window,
)

CAUSAL_REENTRY_ADMISSION_SCHEMA = "FRANKENSTEIN2_GWT_CAUSAL_REENTRY_ADMISSION/v1"
ADMITTED_POSITIVE_REENTRY = "ADMITTED_POSITIVE_REENTRY"
NEGATIVE_ABSENCE_UNPROVEN = "NEGATIVE_ABSENCE_UNPROVEN_SOURCE_AUTHORITY_MISSING"
OBSERVATION_UNKNOWN = "OBSERVATION_UNKNOWN"


@dataclass(frozen=True, slots=True, kw_only=True)
class CausalReentryAdmission:
    observation_sha256: str
    observation_status: str
    admission_status: str
    causal_positive_credit: int
    causal_negative_credit: int
    independent_negative_range_authority: bool
    blocker: str | None

    schema = CAUSAL_REENTRY_ADMISSION_SCHEMA
    semantic_gwt_runtime_credit = 0
    jspace_runtime_credit = 0
    physical_grid10_credit = 0
    effect_credit = 0
    training_credit = 0
    completion_credit = 0
    whole_system_acceptance = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "observation_sha256": self.observation_sha256,
            "observation_status": self.observation_status,
            "admission_status": self.admission_status,
            "causal_positive_credit": self.causal_positive_credit,
            "causal_negative_credit": self.causal_negative_credit,
            "independent_negative_range_authority": self.independent_negative_range_authority,
            "blocker": self.blocker,
            "semantic_gwt_runtime_credit": self.semantic_gwt_runtime_credit,
            "jspace_runtime_credit": self.jspace_runtime_credit,
            "physical_grid10_credit": self.physical_grid10_credit,
            "effect_credit": self.effect_credit,
            "training_credit": self.training_credit,
            "completion_credit": self.completion_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }


def admit_reentry_observation(
    observation: ReentryObservationWindowReceipt,
) -> CausalReentryAdmission:
    """Admit only what the current G8 evidence origin can actually establish.

    Positive reentry is admissible because G8's recorder can append REENTRY only
    from a validated factory-origin ``GwtRuntimeWitnessReceipt``.  Negative
    absence is *not* admissible: the current trace-completeness counters/ranges
    are caller supplied.  No argument exists here to waive that fence.
    """

    validate_reentry_observation_window(observation)

    if observation.status == REENTRY_OBSERVED:
        return CausalReentryAdmission(
            observation_sha256=observation.sha256(),
            observation_status=observation.status,
            admission_status=ADMITTED_POSITIVE_REENTRY,
            causal_positive_credit=1,
            causal_negative_credit=0,
            independent_negative_range_authority=False,
            blocker="INDEPENDENT_NEGATIVE_COMPLETE_RANGE_AUTHORITY_MISSING",
        )

    if observation.status == NO_REENTRY_OBSERVED:
        return CausalReentryAdmission(
            observation_sha256=observation.sha256(),
            observation_status=observation.status,
            admission_status=NEGATIVE_ABSENCE_UNPROVEN,
            causal_positive_credit=0,
            causal_negative_credit=0,
            independent_negative_range_authority=False,
            blocker="INDEPENDENT_NEGATIVE_COMPLETE_RANGE_AUTHORITY_MISSING",
        )

    if observation.status == REENTRY_OBSERVATION_UNKNOWN:
        return CausalReentryAdmission(
            observation_sha256=observation.sha256(),
            observation_status=observation.status,
            admission_status=OBSERVATION_UNKNOWN,
            causal_positive_credit=0,
            causal_negative_credit=0,
            independent_negative_range_authority=False,
            blocker="OBSERVATION_INCOMPLETE_OR_NEGATIVE_SOURCE_AUTHORITY_MISSING",
        )

    raise ValueError(f"unsupported G8 observation status: {observation.status}")


__all__ = [
    "ADMITTED_POSITIVE_REENTRY",
    "CAUSAL_REENTRY_ADMISSION_SCHEMA",
    "CausalReentryAdmission",
    "NEGATIVE_ABSENCE_UNPROVEN",
    "OBSERVATION_UNKNOWN",
    "admit_reentry_observation",
]
