from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "t7_asr004_comparator_receipt_validator.py"
SPEC = importlib.util.spec_from_file_location("t7_asr004_validator", TOOL)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

GATE_SHA = "b" * 64


def valid_receipt() -> dict:
    doc = {
        "schema": validator.SCHEMA,
        "semantic_key": validator.SEMANTIC_KEY,
        "fixture": {
            "dataset": "google/fleurs",
            "config": "de_de",
            "revision": validator.FLEURS_REVISION,
            "split": "test",
            "rows": list(range(32)),
        },
        "evaluator": {
            "normalizer": "NFKC_CASEFOLD_PUNCT_SYMBOL_TO_SPACE_COLLAPSE_WS",
            "source_sha256": "c" * 64,
        },
        "external_gate": {"contract_sha256": GATE_SHA, "deterministic": True},
        "faster_whisper_baseline": {
            "package": "faster-whisper==1.2.1",
            "model_repo": "Systran/faster-whisper-large-v3",
            "model_revision": "resolved-revision",
            "artifact_sha256": ["d" * 64],
            "device": "cpu",
            "compute_type": "int8",
            "beam_size": 5,
            "language": "de",
            "condition_on_previous_text": False,
            "raw_vad_filter": False,
            "effective_cpu_threads": 2,
            "ctranslate2_version": "resolved",
            "runtime_version": "resolved",
            "package_source_sha256": "e" * 64,
        },
        "speech_records": [],
        "non_speech_records": [],
    }
    for row in range(32):
        audio_sha = f"{row:064x}"
        for variant in validator.VARIANTS:
            gated = variant in validator.GATED
            record = {
                "fixture_row": row,
                "variant": variant,
                "audio_sha256": audio_sha,
                "reference": "Hallo Welt",
                "dataset_raw_transcription": "Hallo Welt",
                "dataset_transcription": "Hallo Welt",
                "hypothesis": "Hallo Welt",
                "model_identity": "resolved-model",
                "runtime_identity": "resolved-runtime",
                "decoder_latency_ms": 1.0,
                "end_to_end_latency_ms": 2.0,
                "gate_decision": "SPEECH" if gated else "NOT_APPLICABLE",
            }
            if gated:
                record["external_gate_contract_sha256"] = GATE_SHA
            doc["speech_records"].append(record)
    hashes = {
        "digital_silence_1s": "1" * 64,
        "digital_silence_2s": "2" * 64,
        "digital_silence_5s": "3" * 64,
    }
    for fixture_id, audio_sha in hashes.items():
        for variant in validator.VARIANTS:
            gated = variant in validator.GATED
            record = {
                "fixture_id": fixture_id,
                "variant": variant,
                "audio_sha256": audio_sha,
                "hypothesis": "",
                "gate_decision": "NON_SPEECH" if gated else "NOT_APPLICABLE",
            }
            if gated:
                record["external_gate_contract_sha256"] = GATE_SHA
            doc["non_speech_records"].append(record)
    return doc


class ComparatorReceiptValidatorTest(unittest.TestCase):
    def test_valid_matrix_passes_without_minting_runtime_credit(self) -> None:
        report = validator.validate_receipt(valid_receipt())
        self.assertTrue(report["valid"])
        self.assertEqual(report["runtime_credit"], 0)
        self.assertEqual(report["trigger4_acceptance_credit"], 0)

    def test_arm_audio_mismatch_fails_closed(self) -> None:
        doc = valid_receipt()
        doc["speech_records"][1]["audio_sha256"] = "f" * 64
        with self.assertRaises(validator.ValidationError):
            validator.validate_receipt(doc)

    def test_missing_speech_arm_row_fails_closed(self) -> None:
        doc = valid_receipt()
        doc["speech_records"].pop()
        with self.assertRaises(validator.ValidationError):
            validator.validate_receipt(doc)

    def test_gated_arms_must_share_external_gate_identity(self) -> None:
        doc = valid_receipt()
        gated = next(r for r in doc["speech_records"] if r["variant"] in validator.GATED)
        gated["external_gate_contract_sha256"] = "f" * 64
        with self.assertRaises(validator.ValidationError):
            validator.validate_receipt(doc)

    def test_hidden_faster_whisper_internal_vad_fails_closed(self) -> None:
        doc = valid_receipt()
        doc["faster_whisper_baseline"]["raw_vad_filter"] = True
        with self.assertRaises(validator.ValidationError):
            validator.validate_receipt(doc)

    def test_rejected_speech_row_is_retained_with_empty_hypothesis(self) -> None:
        doc = valid_receipt()
        gated = next(r for r in doc["speech_records"] if r["variant"] in validator.GATED)
        gated["gate_decision"] = "NON_SPEECH"
        gated["hypothesis"] = "hallucination"
        with self.assertRaises(validator.ValidationError):
            validator.validate_receipt(doc)


if __name__ == "__main__":
    unittest.main()
