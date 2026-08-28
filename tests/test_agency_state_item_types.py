from __future__ import annotations

import unittest

from frankenstein2.agency_state import (
    AGENCY_PATCH_SCHEMA,
    AgencyState,
    AgencyStateError,
    AgencyStatePatch,
)


class AgencyStateItemTypeRegressionTests(unittest.TestCase):
    class ForgedInterest:
        interest_id = "forged-interest"

        def as_dict(self):
            return {
                "interest_id": self.interest_id,
                "label": "forged without validated provenance",
                "salience_ppm": 1,
                "provenance_refs": [],
            }

    def test_state_rejects_duck_typed_interest(self):
        with self.assertRaisesRegex(AgencyStateError, "Interest"):
            AgencyState.create(
                state_id="agency-main",
                generation=0,
                interests=(self.ForgedInterest(),),
            )

    def test_patch_rejects_duck_typed_interest(self):
        state = AgencyState.create(state_id="agency-main", generation=0)
        with self.assertRaisesRegex(AgencyStateError, "Interest"):
            AgencyStatePatch(
                schema=AGENCY_PATCH_SCHEMA,
                transition_id="transition-type-fence",
                expected_state_id=state.state_id,
                expected_generation=state.generation,
                expected_state_sha256=state.sha256(),
                next_generation=state.generation + 1,
                transition_refs=("event:type-fence",),
                upsert_interests=(self.ForgedInterest(),),
            )

    def test_state_rejects_cross_category_concrete_type(self):
        from frankenstein2.agency_state import OpenLoop

        loop = OpenLoop(
            loop_id="loop-as-interest",
            summary="wrong category",
            state="OPEN",
            priority_ppm=1,
            provenance_refs=("event:typed",),
        )
        with self.assertRaisesRegex(AgencyStateError, "Interest"):
            AgencyState.create(
                state_id="agency-main",
                generation=0,
                interests=(loop,),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
