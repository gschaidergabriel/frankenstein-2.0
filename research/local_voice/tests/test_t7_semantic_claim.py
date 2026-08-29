import pathlib
import sys
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from t7_semantic_claim import SemanticObjective


class SemanticClaimTests(unittest.TestCase):
    def test_paraphrased_human_claims_share_key_when_semantics_match(self):
        a = SemanticObjective.from_inputs(
            family="VPS bridge hardware inventory",
            target_surface="clay_direct_dev",
            subject="whole Frankenstein resource envelope",
            evidence_scope="hardware receipt",
        )
        b = SemanticObjective.from_inputs(
            family="target runtime hardware inventory",
            target_surface="clay-direct-dev",
            subject="whole-frankenstein-resource-envelope",
            evidence_scope="target runtime hardware receipt",
        )
        self.assertEqual(a.semantic_key(), b.semantic_key())
        self.assertEqual(a.claim_path(), b.claim_path())

        pa = a.claim_payload(
            human_claim_path="claims/T7-SYS-002/foo.json",
            research_id="T7-SYS-002",
            objective="E3_VPS_BRIDGE_HARDWARE",
            description="probe runner then inspect resident memory",
        )
        pb = b.claim_payload(
            human_claim_path="claims/T7-SYS-099/bar.json",
            research_id="T7-SYS-099",
            objective="E3_TARGET_RESOURCE_RECEIPT",
            description="inventory VPS resource headroom",
        )
        self.assertEqual(pa["semantic_key"], pb["semantic_key"])
        self.assertNotEqual(pa["research_id"], pb["research_id"])

    def test_human_description_does_not_change_key(self):
        obj = SemanticObjective.from_inputs(
            family="official Qwen3.5-4B baseline",
            target_surface="source-only",
            subject="qwen3.5-4b",
            evidence_scope="source pin",
        )
        p1 = obj.claim_payload(
            human_claim_path="a.json",
            research_id="A",
            objective="ONE",
            description="baseline pin",
        )
        p2 = obj.claim_payload(
            human_claim_path="b.json",
            research_id="B",
            objective="TWO",
            description="resolve the untouched official model",
        )
        self.assertEqual(p1["semantic_key"], p2["semantic_key"])

    def test_material_semantic_change_changes_key(self):
        a = SemanticObjective.from_inputs(
            family="official Qwen3.5-4B baseline",
            target_surface="source-only",
            subject="qwen35-4b",
            evidence_scope="source pin",
        )
        b = SemanticObjective.from_inputs(
            family="official Qwen3.5-4B baseline",
            target_surface="clay-direct-dev",
            subject="qwen35-4b",
            evidence_scope="target-runtime-model-benchmark",
        )
        self.assertNotEqual(a.semantic_key(), b.semantic_key())

    def test_unknown_alias_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown family alias"):
            SemanticObjective.from_inputs(
                family="something vague and new",
                target_surface="source-only",
                subject="qwen3.5-4b",
                evidence_scope="source-pin",
            )

    def test_generation_changes_key_and_must_be_positive(self):
        a = SemanticObjective.from_inputs(
            family="german asr benchmark",
            target_surface="clay-direct-dev",
            subject="qwen3-asr",
            evidence_scope="component benchmark",
            generation=1,
        )
        b = SemanticObjective.from_inputs(
            family="german asr benchmark",
            target_surface="clay-direct-dev",
            subject="qwen3-asr",
            evidence_scope="component benchmark",
            generation=2,
        )
        self.assertNotEqual(a.semantic_key(), b.semantic_key())
        with self.assertRaisesRegex(ValueError, "generation"):
            SemanticObjective.from_inputs(
                family="german asr benchmark",
                target_surface="clay-direct-dev",
                subject="qwen3-asr",
                evidence_scope="component benchmark",
                generation=0,
            )

    def test_hardware_gate_key_is_stable(self):
        obj = SemanticObjective.from_inputs(
            family="target-runtime-hardware-inventory",
            target_surface="clay-direct-dev",
            subject="whole-frankenstein-resource-envelope",
            evidence_scope="target-runtime-hardware-receipt",
            generation=1,
        )
        self.assertEqual(
            obj.semantic_key(),
            "ba79dcf8960e1f02859a664103d5ba3f63fa8da95855d2b077b3e5aa2e0bf9e3",
        )

    def test_qwen3_tts_12hz_size_ab_alias_is_precise_and_stable(self):
        a = SemanticObjective.from_inputs(
            family="german tts benchmark",
            target_surface="clay-direct-dev",
            subject="qwen3-tts-12hz-0.6b-vs-1.7b",
            evidence_scope="component benchmark",
            generation=1,
        )
        b = SemanticObjective.from_inputs(
            family="german tts benchmark",
            target_surface="clay-direct-dev",
            subject="qwen3-tts-12hz-size-ab",
            evidence_scope="component benchmark",
            generation=1,
        )
        self.assertEqual(a.semantic_key(), b.semantic_key())
        self.assertEqual(a.claim_path(), b.claim_path())
        with self.assertRaisesRegex(ValueError, "unknown subject alias"):
            SemanticObjective.from_inputs(
                family="german tts benchmark",
                target_surface="clay-direct-dev",
                subject="qwen3-tts-25hz",
                evidence_scope="component benchmark",
                generation=1,
            )

    def test_magpietts_subject_alias_is_precise_and_stable(self):
        a = SemanticObjective.from_inputs(
            family="german tts benchmark",
            target_surface="source-only",
            subject="magpietts-multilingual-357m",
            evidence_scope="source-pin",
            generation=1,
        )
        b = SemanticObjective.from_inputs(
            family="german tts benchmark",
            target_surface="source-only",
            subject="nvidia-magpietts-multilingual-357m",
            evidence_scope="source-pin",
            generation=1,
        )
        self.assertEqual(a.semantic_key(), b.semantic_key())
        self.assertEqual(
            a.semantic_key(),
            "b276dc6794c8a85989a3dad568a2d7db7cc38a3a14f2349a31a22f35f81e3657",
        )

    def test_supertonic3_subject_alias_is_precise_and_stable(self):
        a = SemanticObjective.from_inputs(
            family="german tts benchmark",
            target_surface="source-only",
            subject="supertonic-3",
            evidence_scope="source-pin",
            generation=1,
        )
        b = SemanticObjective.from_inputs(
            family="german tts benchmark",
            target_surface="source-only",
            subject="supertone-supertonic-3",
            evidence_scope="source-pin",
            generation=1,
        )
        self.assertEqual(a.semantic_key(), b.semantic_key())
        self.assertEqual(
            a.semantic_key(),
            "140e6517287f351e96ba7571ff06bf7a8ffb44d0029b49ced88eaddb5ce6144c",
        )


if __name__ == "__main__":
    unittest.main()
