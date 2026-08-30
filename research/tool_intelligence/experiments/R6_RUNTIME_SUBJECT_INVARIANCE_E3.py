#!/usr/bin/env python3
import json

STRATEGIES = {
    "declared_only": {"entry.py"},
    "observed_only": {"entry.py", "plugins/a.py"},
    "hybrid_fail_closed": {
        "entry.py", "plugins/a.py", "plugins/b.py", "selector.json",
        "ENV:PLUGIN", "RUNTIME:python", "DISCOVERY:plugins/*"
    },
}

CASES = [
    ("unrelated_docs", {"docs/readme.md"}, False),
    ("selected_plugin_changes", {"plugins/a.py"}, True),
    ("selector_a_to_b", {"selector.json"}, True),
    ("nonselected_plugin_b_changes", {"plugins/b.py"}, True),
    ("environment_selector_changes", {"ENV:PLUGIN"}, True),
    ("runtime_identity_changes", {"RUNTIME:python"}, True),
    ("plugin_discovery_rule_changes", {"DISCOVERY:plugins/*"}, True),
]

def decision(strategy, changes):
    closure = STRATEGIES[strategy]
    return "INVALIDATE_OR_DEFER" if closure & changes else "CERTIFY_NONINTERFERENCE"

rows = []
for case, changes, must_invalidate in CASES:
    for strategy in STRATEGIES:
        d = decision(strategy, changes)
        false_certify = must_invalidate and d == "CERTIFY_NONINTERFERENCE"
        rows.append({
            "case": case,
            "strategy": strategy,
            "changes": sorted(changes),
            "ground_truth_must_invalidate": must_invalidate,
            "decision": d,
            "false_certify": false_certify,
        })

summary = {}
for strategy in STRATEGIES:
    sr = [r for r in rows if r["strategy"] == strategy]
    summary[strategy] = {
        "false_certify_count": sum(r["false_certify"] for r in sr),
        "certifies_unrelated_docs": next(r["decision"] for r in sr if r["case"] == "unrelated_docs") == "CERTIFY_NONINTERFERENCE",
    }

acceptance = (
    summary["declared_only"]["false_certify_count"] >= 1
    and summary["observed_only"]["false_certify_count"] >= 1
    and summary["hybrid_fail_closed"]["false_certify_count"] == 0
    and summary["hybrid_fail_closed"]["certifies_unrelated_docs"]
)

print(json.dumps({
    "schema": "RUNTIME_SUBJECT_INVARIANCE_TOY/v1",
    "cases": rows,
    "summary": summary,
    "acceptance": acceptance,
}, sort_keys=True, indent=2))
