"""REVIEW_ONLY / CANDIDATE_FALSIFIER for F2-WP-600.

Demonstrates whether a polymorphic scalar string can cross the TaskProfile public
boundary and alter equality semantics at exact CycleContract identity checks.  This
file does not modify WP600-owned implementation source.
"""
from dataclasses import replace
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_direct_delegate_router import make_cycle, make_policy, make_profile  # noqa: E402

from frankenstein2.direct_delegate_router import DIRECT_SMALL, route_task  # noqa: E402


class EqualityBypassStr(str):
    """String payload whose text is forged while equality claims every value matches."""

    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    __hash__ = str.__hash__


def test_wp600_scalar_string_subtype_can_bypass_cycle_identity_and_digest_checks():
    cycle = make_cycle()
    valid = make_profile(cycle)

    forged_cycle_id = EqualityBypassStr("cycle-contract:forged-not-current")
    forged_cycle_sha = EqualityBypassStr("0" * 64)
    forged = replace(
        valid,
        cycle_contract_id=forged_cycle_id,
        cycle_contract_sha256=forged_cycle_sha,
    )

    # Prove the serialized/profile evidence really contains forged values rather than
    # using the subtype's overloaded equality operator for the assertion.
    serialized = json.dumps(
        forged.as_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert '"cycle_contract_id":"cycle-contract:forged-not-current"' in serialized
    assert '"cycle_contract_sha256":"' + ("0" * 64) + '"' in serialized
    assert str(forged.cycle_contract_id) != cycle.contract_id
    assert str(forged.cycle_contract_sha256) != cycle.sha256()

    observed = route_task(
        decision_id="route-decision:wp600-scalar-falsifier",
        task_profile=forged,
        cycle_contract=cycle,
        policy=make_policy(),
    )

    # If reached, the router accepted a TaskProfile whose own serialized identity/digest
    # are not those of the CycleContract supplied to route_task().  The returned decision
    # then binds the real CycleContract while task_profile_sha256 binds the forged profile.
    assert observed.route == DIRECT_SMALL
    assert observed.cycle_contract_id == cycle.contract_id
    assert observed.cycle_contract_sha256 == cycle.sha256()
    assert observed.task_profile_sha256 == forged.sha256()
