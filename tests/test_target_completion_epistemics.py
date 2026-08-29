from __future__ import annotations

import unittest

from frankenstein2.target_completion_epistemics import (
    CompletionEpistemicsError,
    CompletionStatus,
    CounterevidenceProbe,
    FidelityLevel,
    ObligationStatus,
    PositiveReadback,
    TargetCompletionReport,
    TargetObligation,
    TargetObligationManifest,
    TargetObligationRequirement,
)


def requirement(
    obligation_id: str,
    fidelity: FidelityLevel = FidelityLevel.T1_UBUNTU_USERSPACE,
) -> TargetObligationRequirement:
    return TargetObligationRequirement(
        obligation_id=obligation_id,
        required_fidelity=fidelity,
    )


def manifest(
    *requirements: TargetObligationRequirement,
    generation: int = 1,
    target_id: str = "host-a",
) -> TargetObligationManifest:
    return TargetObligationManifest(
        target_id=target_id,
        generation=generation,
        mandatory_obligations=tuple(requirements),
    )


def obligation(
    obligation_id: str,
    *,
    fidelity: FidelityLevel = FidelityLevel.T1_UBUNTU_USERSPACE,
    mandatory: bool = True,
    positive: PositiveReadback = PositiveReadback.UNKNOWN,
    counter: CounterevidenceProbe = CounterevidenceProbe.UNKNOWN,
) -> TargetObligation:
    return TargetObligation(
        obligation_id=obligation_id,
        target_id="host-a",
        required_fidelity=fidelity,
        mandatory=mandatory,
        positive_readback=positive,
        positive_evidence_refs=(f"readback:{obligation_id}",) if positive is not PositiveReadback.UNKNOWN else (),
        counterevidence_probe=counter,
        counterevidence_refs=(f"probe:{obligation_id}",) if counter is not CounterevidenceProbe.UNKNOWN else (),
    )


class TargetCompletionEpistemicsTests(unittest.TestCase):
    def test_missing_mandatory_evidence_is_unknown_not_pass(self) -> None:
        item = obligation("service-bound")
        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
            manifest=manifest(requirement("service-bound")),
            obligations=(item,),
        )
        self.assertIs(item.status, ObligationStatus.UNKNOWN)
        self.assertIs(report.status, CompletionStatus.UNKNOWN)
        self.assertEqual(report.unknown_obligation_ids, ("service-bound",))
        self.assertFalse(report.physical_credit)

    def test_positive_readback_without_counterevidence_probe_stays_unknown(self) -> None:
        self.assertIs(obligation("host-adapter", positive=PositiveReadback.PASS).status, ObligationStatus.UNKNOWN)

    def test_counterevidence_found_fails_even_with_positive_readback(self) -> None:
        item = obligation("wrong-owner-probe", positive=PositiveReadback.PASS, counter=CounterevidenceProbe.FOUND)
        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
            manifest=manifest(requirement("wrong-owner-probe")),
            obligations=(item,),
        )
        self.assertIs(item.status, ObligationStatus.FAIL)
        self.assertIs(report.status, CompletionStatus.FAILED)
        self.assertEqual(report.failed_obligation_ids, ("wrong-owner-probe",))

    def test_complete_requires_all_manifest_mandatory_in_scope_to_pass_both_paths(self) -> None:
        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T2_DEVICE_SESSION_FAULT_TWIN,
            manifest=manifest(
                requirement("install"),
                requirement("session", FidelityLevel.T2_DEVICE_SESSION_FAULT_TWIN),
            ),
            obligations=(
                obligation("install", positive=PositiveReadback.PASS, counter=CounterevidenceProbe.CLEAR),
                obligation("session", fidelity=FidelityLevel.T2_DEVICE_SESSION_FAULT_TWIN, positive=PositiveReadback.PASS, counter=CounterevidenceProbe.CLEAR),
                obligation("optional-debug", mandatory=False),
            ),
        )
        self.assertIs(report.status, CompletionStatus.COMPLETE)
        self.assertEqual(report.unknown_obligation_ids, ("optional-debug",))
        self.assertFalse(report.physical_credit)

    def test_future_fidelity_requirement_does_not_block_lower_scope(self) -> None:
        bound_manifest = manifest(
            requirement("userspace"),
            requirement("physical-camera", FidelityLevel.T4_PHYSICAL),
        )
        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
            manifest=bound_manifest,
            obligations=(
                obligation("userspace", positive=PositiveReadback.PASS, counter=CounterevidenceProbe.CLEAR),
                obligation("physical-camera", fidelity=FidelityLevel.T4_PHYSICAL),
            ),
        )
        self.assertIs(report.status, CompletionStatus.COMPLETE)
        self.assertEqual(tuple(item.obligation_id for item in report.required_manifest_in_scope), ("userspace",))
        self.assertFalse(report.physical_completion_candidate)
        self.assertFalse(report.physical_credit)
        self.assertIn("physical-camera", report.canonical_json())

    def test_t4_evidence_can_only_form_candidate_not_physical_credit(self) -> None:
        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T4_PHYSICAL,
            manifest=manifest(requirement("physical-readback", FidelityLevel.T4_PHYSICAL)),
            obligations=(
                obligation("physical-readback", fidelity=FidelityLevel.T4_PHYSICAL, positive=PositiveReadback.PASS, counter=CounterevidenceProbe.CLEAR),
            ),
        )
        self.assertIs(report.status, CompletionStatus.COMPLETE)
        self.assertTrue(report.physical_completion_candidate)
        self.assertFalse(report.physical_credit)

    def test_t4_scope_without_t4_requirement_cannot_form_physical_candidate(self) -> None:
        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T4_PHYSICAL,
            manifest=manifest(requirement("userspace")),
            obligations=(obligation("userspace", positive=PositiveReadback.PASS, counter=CounterevidenceProbe.CLEAR),),
        )
        self.assertIs(report.status, CompletionStatus.COMPLETE)
        self.assertFalse(report.physical_completion_candidate)
        self.assertFalse(report.physical_credit)

    def test_pr415_negative_space_omission_stays_unknown(self) -> None:
        bound_manifest = manifest(
            requirement("platform-contract", FidelityLevel.T0_CONTRACT),
            requirement("physical-camera", FidelityLevel.T4_PHYSICAL),
        )
        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T4_PHYSICAL,
            manifest=bound_manifest,
            obligations=(
                obligation(
                    "platform-contract",
                    fidelity=FidelityLevel.T0_CONTRACT,
                    positive=PositiveReadback.PASS,
                    counter=CounterevidenceProbe.CLEAR,
                ),
            ),
        )
        self.assertIs(report.status, CompletionStatus.UNKNOWN)
        self.assertEqual(report.missing_mandatory_obligation_ids, ("physical-camera",))
        self.assertIn("physical-camera", report.unknown_obligation_ids)
        self.assertFalse(report.physical_completion_candidate)
        self.assertFalse(report.physical_credit)

    def test_empty_evidence_against_manifest_is_unknown_not_vacuously_complete(self) -> None:
        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
            manifest=manifest(requirement("required-a"), requirement("required-b")),
            obligations=(),
        )
        self.assertIs(report.status, CompletionStatus.UNKNOWN)
        self.assertEqual(report.missing_mandatory_obligation_ids, ("required-a", "required-b"))
        self.assertEqual(report.unknown_obligation_ids, ("required-a", "required-b"))

    def test_manifest_declared_requirement_cannot_be_downgraded_or_retyped(self) -> None:
        bound_manifest = manifest(requirement("required", FidelityLevel.T2_DEVICE_SESSION_FAULT_TWIN))
        with self.assertRaises(CompletionEpistemicsError):
            TargetCompletionReport(
                target_id="host-a",
                evaluated_fidelity=FidelityLevel.T2_DEVICE_SESSION_FAULT_TWIN,
                manifest=bound_manifest,
                obligations=(obligation("required", fidelity=FidelityLevel.T2_DEVICE_SESSION_FAULT_TWIN, mandatory=False),),
            )
        with self.assertRaises(CompletionEpistemicsError):
            TargetCompletionReport(
                target_id="host-a",
                evaluated_fidelity=FidelityLevel.T2_DEVICE_SESSION_FAULT_TWIN,
                manifest=bound_manifest,
                obligations=(obligation("required", fidelity=FidelityLevel.T1_UBUNTU_USERSPACE),),
            )

    def test_undeclared_mandatory_obligation_fails_closed(self) -> None:
        with self.assertRaises(CompletionEpistemicsError):
            TargetCompletionReport(
                target_id="host-a",
                evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
                manifest=manifest(requirement("declared")),
                obligations=(obligation("invented"),),
            )

    def test_manifest_identity_is_generation_and_content_bound(self) -> None:
        first = manifest(requirement("a"), generation=1)
        next_generation = manifest(requirement("a"), generation=2)
        changed_universe = manifest(requirement("a"), requirement("b"), generation=1)
        self.assertNotEqual(first.sha256(), next_generation.sha256())
        self.assertNotEqual(first.sha256(), changed_universe.sha256())

        report = TargetCompletionReport(
            target_id="host-a",
            evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
            manifest=first,
            obligations=(obligation("a", positive=PositiveReadback.PASS, counter=CounterevidenceProbe.CLEAR),),
        )
        encoded = report.as_dict()
        self.assertEqual(encoded["manifest_generation"], 1)
        self.assertEqual(encoded["manifest_sha256"], first.sha256())

    def test_non_unknown_evidence_states_require_references(self) -> None:
        with self.assertRaises(CompletionEpistemicsError):
            TargetObligation(obligation_id="no-ref", target_id="host-a", required_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE, mandatory=True, positive_readback=PositiveReadback.PASS)
        with self.assertRaises(CompletionEpistemicsError):
            TargetObligation(obligation_id="no-probe-ref", target_id="host-a", required_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE, mandatory=True, counterevidence_probe=CounterevidenceProbe.CLEAR)

    def test_positive_and_counterevidence_refs_must_be_independent(self) -> None:
        shared_ref = "evidence:single-self-confirming-observation"
        with self.assertRaises(CompletionEpistemicsError):
            TargetObligation(
                obligation_id="independent-readback-and-probe",
                target_id="host-a",
                required_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
                mandatory=True,
                positive_readback=PositiveReadback.PASS,
                positive_evidence_refs=(shared_ref,),
                counterevidence_probe=CounterevidenceProbe.CLEAR,
                counterevidence_refs=(shared_ref,),
            )

        valid = TargetObligation(
            obligation_id="independent-readback-and-probe-valid",
            target_id="host-a",
            required_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
            mandatory=True,
            positive_readback=PositiveReadback.PASS,
            positive_evidence_refs=("evidence:readback",),
            counterevidence_probe=CounterevidenceProbe.CLEAR,
            counterevidence_refs=("evidence:counterprobe",),
        )
        self.assertIs(valid.status, ObligationStatus.PASS)

    def test_target_mismatch_and_duplicate_ids_fail_closed(self) -> None:
        good = obligation("a", positive=PositiveReadback.PASS, counter=CounterevidenceProbe.CLEAR)
        wrong_target = TargetObligation(obligation_id="b", target_id="host-b", required_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE, mandatory=True)
        bound_manifest = manifest(requirement("a"), requirement("b"))
        with self.assertRaises(CompletionEpistemicsError):
            TargetCompletionReport(
                target_id="host-a",
                evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
                manifest=bound_manifest,
                obligations=(good, wrong_target),
            )
        with self.assertRaises(CompletionEpistemicsError):
            TargetCompletionReport(
                target_id="host-a",
                evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
                manifest=manifest(requirement("a")),
                obligations=(good, good),
            )
        with self.assertRaises(CompletionEpistemicsError):
            TargetCompletionReport(
                target_id="host-a",
                evaluated_fidelity=FidelityLevel.T1_UBUNTU_USERSPACE,
                manifest=manifest(requirement("a"), target_id="host-b"),
                obligations=(good,),
            )

    def test_manifest_rejects_invalid_generation_duplicates_and_non_exact_members(self) -> None:
        with self.assertRaises(CompletionEpistemicsError):
            manifest(requirement("a"), generation=0)
        with self.assertRaises(CompletionEpistemicsError):
            manifest(requirement("a"), requirement("a"))
        with self.assertRaises(CompletionEpistemicsError):
            TargetObligationManifest(target_id="host-a", generation=1, mandatory_obligations=())
        with self.assertRaises(CompletionEpistemicsError):
            TargetObligationManifest(target_id="host-a", generation=1, mandatory_obligations=(object(),))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
