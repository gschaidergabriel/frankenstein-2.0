import dataclasses
import unittest

from frankenstein2.grid10_interface import (
    CellBudget,
    CellInput,
    CellOutput,
    GRID10_CELL_IDS,
    Grid10InterfaceError,
    Grid10Plan,
    account_outputs,
)

HASH_A = "a" * 64
HASH_B = "b" * 64


def budgets(*, work=5, input_refs=3, output_refs=2):
    return tuple(
        CellBudget(
            cell_id=cell_id,
            role_label=f"opaque-role-{cell_id}",
            max_input_refs=input_refs,
            max_output_refs=output_refs,
            max_work_units=work,
            max_reentry_depth=1,
        )
        for cell_id in GRID10_CELL_IDS
    )


def make_plan(**overrides):
    values = dict(
        plan_id="grid-plan-1",
        cycle_id="cycle-1",
        generation=2,
        frame_id="frame-1",
        frame_generation=4,
        frame_sha256=HASH_A,
        policy_id="policy-1",
        policy_generation=3,
        policy_sha256=HASH_B,
        cells=budgets(),
        max_total_work_units=20,
        provenance_refs=("receipt:plan",),
    )
    values.update(overrides)
    return Grid10Plan.create(**values)


def make_input(plan, cell_id="G1", **overrides):
    values = dict(
        cell_id=cell_id,
        work_units_requested=3,
        reentry_depth=0,
        input_refs=("in:2", "in:1"),
        provenance_refs=("receipt:input",),
    )
    values.update(overrides)
    return CellInput.for_plan(plan, **values)


def make_output(plan, cell_input, **overrides):
    values = dict(
        status="PARTIAL",
        work_units_used=2,
        output_refs=("out:1",),
        evidence_refs=("evidence:1",),
        provenance_refs=("receipt:output",),
    )
    values.update(overrides)
    return CellOutput.for_input(plan, cell_input, **values)


class Grid10InterfaceTests(unittest.TestCase):
    def test_exact_ten_cells_are_canonicalized(self):
        a = make_plan()
        b = make_plan(cells=tuple(reversed(budgets())))
        self.assertEqual(tuple(cell.cell_id for cell in a.cells), GRID10_CELL_IDS)
        self.assertEqual(a.as_dict(), b.as_dict())
        self.assertEqual(a.sha256(), b.sha256())
        self.assertIn("NOT_TEN_RESIDENT_MODELS", a.classification)

    def test_missing_or_duplicate_cell_fails_closed(self):
        with self.assertRaises(Grid10InterfaceError):
            make_plan(cells=budgets()[:-1])
        duplicate = list(budgets())
        duplicate[-1] = duplicate[0]
        with self.assertRaises(Grid10InterfaceError):
            make_plan(cells=tuple(duplicate))

    def test_budget_booleans_and_negative_values_are_rejected(self):
        with self.assertRaises(Grid10InterfaceError):
            CellBudget("G1", "role", True, 1, 1, 0)
        with self.assertRaises(Grid10InterfaceError):
            CellBudget("G1", "role", 1, 1, -1, 0)

    def test_frame_binding_is_exact(self):
        plan = make_plan()
        plan.assert_frame_binding(frame_id="frame-1", generation=4, sha256=HASH_A)
        with self.assertRaisesRegex(Grid10InterfaceError, "frame generation mismatch"):
            plan.assert_frame_binding(frame_id="frame-1", generation=5, sha256=HASH_A)
        with self.assertRaisesRegex(Grid10InterfaceError, "frame digest mismatch"):
            plan.assert_frame_binding(frame_id="frame-1", generation=4, sha256="c" * 64)

    def test_policy_binding_is_exact(self):
        plan = make_plan()
        plan.assert_policy_binding(policy_id="policy-1", generation=3, sha256=HASH_B)
        with self.assertRaisesRegex(Grid10InterfaceError, "policy_id mismatch"):
            plan.assert_policy_binding(policy_id="policy-2", generation=3, sha256=HASH_B)

    def test_input_reference_budget_is_enforced(self):
        plan = make_plan(cells=budgets(input_refs=1))
        with self.assertRaisesRegex(Grid10InterfaceError, "input reference budget exceeded"):
            make_input(plan, input_refs=("a", "b"))

    def test_requested_work_and_reentry_budgets_are_enforced(self):
        plan = make_plan(cells=budgets(work=2))
        with self.assertRaisesRegex(Grid10InterfaceError, "requested work budget exceeded"):
            make_input(plan, work_units_requested=3)
        plan2 = make_plan()
        with self.assertRaisesRegex(Grid10InterfaceError, "reentry-depth budget exceeded"):
            make_input(plan2, reentry_depth=2)

    def test_output_reference_and_work_budgets_are_enforced(self):
        plan = make_plan(cells=budgets(output_refs=1, work=5))
        cell_input = make_input(plan, work_units_requested=3)
        with self.assertRaisesRegex(Grid10InterfaceError, "output reference budget exceeded"):
            make_output(plan, cell_input, output_refs=("a", "b"))
        with self.assertRaisesRegex(Grid10InterfaceError, "used more work than requested"):
            make_output(plan, cell_input, work_units_used=4)

    def test_plan_digest_mismatch_is_rejected(self):
        plan = make_plan()
        cell_input = make_input(plan)
        tampered = dataclasses.replace(cell_input, plan_sha256="c" * 64)
        with self.assertRaisesRegex(Grid10InterfaceError, "plan digest mismatch"):
            plan.validate_input(tampered)

    def test_input_digest_and_cell_identity_are_bound_to_output(self):
        plan = make_plan()
        cell_input = make_input(plan, "G1")
        output = make_output(plan, cell_input)
        tampered_digest = dataclasses.replace(output, input_sha256="c" * 64)
        with self.assertRaisesRegex(Grid10InterfaceError, "input digest mismatch"):
            plan.validate_output(tampered_digest, cell_input=cell_input)
        tampered_cell = dataclasses.replace(output, cell_id="G2")
        with self.assertRaisesRegex(Grid10InterfaceError, "identity mismatch"):
            plan.validate_output(tampered_cell, cell_input=cell_input)

    def test_unknown_status_is_rejected(self):
        plan = make_plan()
        cell_input = make_input(plan)
        with self.assertRaises(Grid10InterfaceError):
            make_output(plan, cell_input, status="SUCCESS_TRUTH")

    def test_global_work_budget_and_duplicate_outputs_fail_closed(self):
        plan = make_plan(max_total_work_units=3)
        i1 = make_input(plan, "G1", work_units_requested=2)
        i2 = make_input(plan, "G2", work_units_requested=2)
        o1 = make_output(plan, i1, work_units_used=2)
        o2 = make_output(plan, i2, work_units_used=2)
        with self.assertRaisesRegex(Grid10InterfaceError, "total work budget exceeded"):
            account_outputs(plan, ((i1, o1), (i2, o2)))
        duplicate_plan = make_plan()
        di1 = make_input(duplicate_plan, "G1")
        do1 = make_output(duplicate_plan, di1)
        with self.assertRaisesRegex(Grid10InterfaceError, "duplicate output"):
            account_outputs(duplicate_plan, ((di1, do1), (di1, do1)))

    def test_usage_receipt_preserves_missing_cells_without_success_inference(self):
        plan = make_plan(max_total_work_units=20)
        i1 = make_input(plan, "G1")
        o1 = make_output(plan, i1, status="UNKNOWN")
        receipt = account_outputs(plan, ((i1, o1),))
        self.assertEqual(receipt.completed_cell_ids, ("G1",))
        self.assertEqual(receipt.missing_cell_ids, GRID10_CELL_IDS[1:])
        self.assertIn("NOT_PHYSICAL_CONCURRENCY_EVIDENCE", receipt.classification)
        self.assertEqual(receipt.total_work_units_used, 2)
        self.assertEqual(receipt.remaining_work_units, 18)


if __name__ == "__main__":
    unittest.main()
