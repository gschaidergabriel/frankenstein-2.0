import unittest

from research.local_voice.tools.t7_asr008_receipt_geometry_guard import (
    SCHEMA,
    evaluate,
)


class ASR008GeometryGuardTests(unittest.TestCase):
    def test_numeric_chunk_claim_fails_closed(self):
        receipt = {
            "schema": SCHEMA,
            "configs": [{
                "metrics": {
                    "language": "de-DE",
                    "chunk_ms": 320,
                    "rnnt_right_context": 3,
                }
            }],
            "streaming_geometry": [
                {"chunk_ms": 320, "rnnt_right_context": 3}
            ],
        }
        result = evaluate(receipt)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["classification"], "EVIDENCE_INVALID")
        self.assertIn(
            "EVIDENCE_INVALID_UNBOUND_CHUNK_DIMENSION",
            result["reasons"],
        )
        self.assertEqual(
            result["credit"]["target_runtime_promotion_allowed_by_this_guard"],
            0,
        )

    def test_right_context_only_receipt_can_pass_geometry_guard(self):
        receipt = {
            "schema": SCHEMA,
            "configs": [{
                "metrics": {
                    "language": "de-DE",
                    "rnnt_right_context": 3,
                }
            }],
            "streaming_geometry": [
                {"rnnt_right_context": 3}
            ],
        }
        result = evaluate(receipt)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["classification"], "ACCEPTED_GEOMETRY_SCOPE")
        self.assertEqual(result["numeric_chunk_claims"], [])

    def test_determinism_receipt_chunk_claim_is_also_rejected(self):
        receipt = {
            "schema": SCHEMA,
            "configs": [{"metrics": {"rnnt_right_context": 3}}],
            "deterministic_rerun": {
                "language": "de-DE",
                "chunk_ms": 320,
                "rnnt_right_context": 3,
            },
        }
        result = evaluate(receipt)
        self.assertFalse(result["accepted"])
        locations = {x["config_index"] for x in result["numeric_chunk_claims"]}
        self.assertIn("deterministic_rerun", locations)

    def test_schema_mismatch_fails_closed(self):
        result = evaluate({"schema": "wrong", "configs": [{"metrics": {}}]})
        self.assertFalse(result["accepted"])
        self.assertIn("RECEIPT_SCHEMA_MISMATCH", result["reasons"])


if __name__ == "__main__":
    unittest.main()
