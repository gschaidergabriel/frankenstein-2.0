import json
from dataclasses import dataclass


@dataclass
class SourceDerivedStore:
    """Minimal executable model of the exact CCR store semantics cited in result.json.

    This does NOT execute upstream Rust and must never be presented as upstream runtime credit.
    """

    rows: dict
    fail_put: bool = False

    def put(self, key, payload):
        if self.fail_put:
            return False
        self.rows[key] = payload  # source contract upserts/replaces by hash key
        return True

    def get(self, key):
        return self.rows.get(key)

    def expire(self, key):
        self.rows.pop(key, None)


def marker_for(key):
    return f"<<ccr:{key}>>"


def main():
    key = "0123456789abcdef01234567"
    marker = marker_for(key)
    cases = []

    store = SourceDerivedStore({}, fail_put=True)
    put_ok = store.put(key, "ORIGINAL_EVIDENCE")
    cases.append({
        "case": "PUT_FAILURE_AFTER_MARKER",
        "marker_emitted": bool(marker),
        "put_ok": put_ok,
        "retrievable": store.get(key) is not None,
        "f2_fail_closed_required": bool(marker) and not put_ok and store.get(key) is None,
    })

    store = SourceDerivedStore({key: "ORIGINAL_EVIDENCE"})
    pre = store.get(key)
    store.expire(key)
    post = store.get(key)
    cases.append({
        "case": "RECOVERY_TTL_EXPIRY",
        "marker_still_exists": bool(marker),
        "pre_expiry_retrievable": pre == "ORIGINAL_EVIDENCE",
        "post_expiry_retrievable": post is not None,
        "f2_long_horizon_reversibility_falsified": bool(marker) and pre is not None and post is None,
    })

    store = SourceDerivedStore({})
    store.put(key, "PAYLOAD_A")
    store.put(key, "PAYLOAD_B")
    cases.append({
        "case": "SAME_KEY_OVERWRITE",
        "retrieved": store.get(key),
        "original_a_preserved": store.get(key) == "PAYLOAD_A",
        "f2_requires_digest_and_provenance_revalidation": store.get(key) != "PAYLOAD_A",
    })

    out = {
        "schema": "R6_HEADROOM_SOURCE_DERIVED_CONTRACT_FALSIFIER/v1",
        "basis": {
            "upstream_commit": "213b37158fb9fa7287d7d5884c7df43800821995",
            "source_files": [
                "crates/headroom-core/src/ccr/mod.rs",
                "crates/headroom-core/src/ccr/backends/sqlite.rs",
            ],
            "execution_note": "Deterministic source-derived semantic fixture, not execution of upstream Rust code.",
        },
        "cases": cases,
        "acceptance": {
            "source_claim_reversibility_is_conditional": all([
                cases[0]["f2_fail_closed_required"],
                cases[1]["f2_long_horizon_reversibility_falsified"],
                cases[2]["f2_requires_digest_and_provenance_revalidation"],
            ]),
            "upstream_runtime_reproduced": False,
            "e3_runtime_credit": False,
            "recommended_f2_admission": "ADAPT_ONLY_WITH_FAIL_CLOSED_RECOVERY_COMMIT_AND_DIGEST_PROVENANCE_FENCE",
        },
    }
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
