#!/usr/bin/env python3
"""One-shot deterministic source transformer for the PR207 frame-version repair.

This file exists only on the repair branch long enough to apply a strictly matched patch.
It must be removed before merge.  Every replacement is cardinality checked so moving source
fails closed instead of producing a best-effort mutation.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def replace_exact(path: Path, old: str, new: str, *, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    observed = text.count(old)
    if observed != count:
        raise SystemExit(f"{path}: expected {count} exact matches, observed {observed}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def regex_exact(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{path}: regex replacement count={count}, expected 1")
    path.write_text(updated, encoding="utf-8")


hyper = ROOT / "src/frankenstein2/hyperposition.py"
gwt = ROOT / "src/frankenstein2/gwt_workspace.py"
test_hyper = ROOT / "tests/test_hyperposition.py"
test_gwt = ROOT / "tests/test_gwt_workspace.py"
review_test = ROOT / "tests/test_wp506_hyperposition_frame_version_falsifier.py"

# WP502: make SituationFrame version identity part of canonical Hyperposition identity.
replace_exact(
    hyper,
    'HYPERPOSITION_SCHEMA = "FRANKENSTEIN2_HYPERPOSITION/v1"',
    'HYPERPOSITION_SCHEMA = "FRANKENSTEIN2_HYPERPOSITION/v2"',
)
replace_exact(
    hyper,
    '''    situation_frame_ref: str | None = None\n    policy_ref: str | None = None\n''',
    '''    situation_frame_ref: str | None = None\n    situation_frame_generation: int | None = None\n    situation_frame_sha256: str | None = None\n    policy_ref: str | None = None\n''',
)
replace_exact(
    hyper,
    '''        object.__setattr__(\n            self,\n            "situation_frame_ref",\n            _optional_text("situation_frame_ref", self.situation_frame_ref),\n        )\n        object.__setattr__(self, "policy_ref", _optional_text("policy_ref", self.policy_ref))\n''',
    '''        object.__setattr__(\n            self,\n            "situation_frame_ref",\n            _optional_text("situation_frame_ref", self.situation_frame_ref),\n        )\n        frame_binding = (\n            self.situation_frame_ref,\n            self.situation_frame_generation,\n            self.situation_frame_sha256,\n        )\n        if any(value is not None for value in frame_binding) and not all(\n            value is not None for value in frame_binding\n        ):\n            raise HyperpositionError(\n                "situation frame binding must include ref, generation, and digest together"\n            )\n        if self.situation_frame_ref is not None:\n            _require_generation(self.situation_frame_generation)\n            object.__setattr__(\n                self,\n                "situation_frame_sha256",\n                _require_sha256("situation_frame_sha256", self.situation_frame_sha256),\n            )\n        object.__setattr__(self, "policy_ref", _optional_text("policy_ref", self.policy_ref))\n''',
)
replace_exact(
    hyper,
    '''            "situation_frame_ref": self.situation_frame_ref,\n            "policy_ref": self.policy_ref,\n''',
    '''            "situation_frame_ref": self.situation_frame_ref,\n            "situation_frame_generation": self.situation_frame_generation,\n            "situation_frame_sha256": self.situation_frame_sha256,\n            "policy_ref": self.policy_ref,\n''',
)
replace_exact(
    hyper,
    '''    situation_frame_ref: str | None = None,\n    policy_ref: str | None = None,\n) -> Hyperposition:\n''',
    '''    situation_frame_ref: str | None = None,\n    situation_frame_generation: int | None = None,\n    situation_frame_sha256: str | None = None,\n    policy_ref: str | None = None,\n) -> Hyperposition:\n''',
)
replace_exact(
    hyper,
    '''        situation_frame_ref=situation_frame_ref,\n        policy_ref=policy_ref,\n''',
    '''        situation_frame_ref=situation_frame_ref,\n        situation_frame_generation=situation_frame_generation,\n        situation_frame_sha256=situation_frame_sha256,\n        policy_ref=policy_ref,\n''',
)

# WP502 tests: existing bound fixtures now carry explicit frame version identity.
replace_exact(
    test_hyper,
    '''        situation_frame_ref="situation:42",\n        policy_ref="policy:bounded",\n''',
    '''        situation_frame_ref="situation:42",\n        situation_frame_generation=4,\n        situation_frame_sha256="a" * 64,\n        policy_ref="policy:bounded",\n''',
    count=3,
)
replace_exact(
    test_hyper,
    '''    def test_hyperposition_is_frozen(self):\n''',
    '''    def test_situation_frame_binding_requires_exact_version_triple(self):\n        with self.assertRaisesRegex(HyperpositionError, "ref, generation, and digest"):\n            create_hyperposition(\n                hyperposition_id="hyper:partial-frame",\n                generation=3,\n                alternatives=(alt("alt:a", "hypothesis:a"), alt("alt:b", "hypothesis:b")),\n                provenance_refs=("source:test",),\n                situation_frame_ref="situation:42",\n            )\n\n    def test_situation_frame_version_changes_hyperposition_digest(self):\n        current = state()\n        stale = create_hyperposition(\n            hyperposition_id="hyper:1",\n            generation=3,\n            alternatives=(alt("alt:b", "hypothesis:b"), alt("alt:a", "hypothesis:a")),\n            provenance_refs=("source:z", "source:a"),\n            situation_frame_ref="situation:42",\n            situation_frame_generation=3,\n            situation_frame_sha256="b" * 64,\n            policy_ref="policy:bounded",\n        )\n        self.assertNotEqual(current.sha256(), stale.sha256())\n        self.assertEqual(current.as_dict()["situation_frame_generation"], 4)\n        self.assertEqual(current.as_dict()["situation_frame_sha256"], "a" * 64)\n\n    def test_hyperposition_is_frozen(self):\n''',
)

# WP506: consume the exact WP502 SituationFrame version binding, not frame id alone.
regex_exact(
    gwt,
    r'''def _resolve_hyperposition_binding\(\n    \*,\n    frame_id: str,\n    hyperposition: Hyperposition \| None,\n    hyperposition_id: str \| None,\n    hyperposition_generation: int \| None,\n    hyperposition_sha256: str \| None,\n\) -> tuple\[str \| None, int \| None, str \| None\]:\n.*?    return expected\n''',
    '''def _resolve_hyperposition_binding(\n    *,\n    frame_id: str,\n    frame_generation: int,\n    frame_sha256: str,\n    hyperposition: Hyperposition | None,\n    hyperposition_id: str | None,\n    hyperposition_generation: int | None,\n    hyperposition_sha256: str | None,\n) -> tuple[str | None, int | None, str | None]:\n    fields = (hyperposition_id, hyperposition_generation, hyperposition_sha256)\n    if hyperposition is None:\n        if any(value is not None for value in fields):\n            raise GwtWorkspaceError(\n                "hyperposition object required to verify situation frame binding"\n            )\n        return None, None, None\n    if type(hyperposition) is not Hyperposition:\n        raise GwtWorkspaceError("hyperposition must be concrete Hyperposition or None")\n    normalized_frame_id = _text("frame_id", frame_id)\n    normalized_frame_generation = _generation("frame_generation", frame_generation)\n    normalized_frame_sha256 = _sha256("frame_sha256", frame_sha256)\n    if hyperposition.situation_frame_ref != normalized_frame_id:\n        raise GwtWorkspaceError("hyperposition situation frame binding mismatch")\n    if (\n        hyperposition.situation_frame_generation != normalized_frame_generation\n        or hyperposition.situation_frame_sha256 != normalized_frame_sha256\n    ):\n        raise GwtWorkspaceError("hyperposition situation frame version binding mismatch")\n    expected = (\n        hyperposition.hyperposition_id,\n        hyperposition.generation,\n        hyperposition.sha256(),\n    )\n    if any(value is not None for value in fields):\n        if not all(value is not None for value in fields):\n            raise GwtWorkspaceError("hyperposition binding must be all-present or all-absent")\n        normalized = (\n            _text("hyperposition_id", hyperposition_id),\n            _generation("hyperposition_generation", hyperposition_generation),\n            _sha256("hyperposition_sha256", hyperposition_sha256),\n        )\n        if normalized != expected:\n            raise GwtWorkspaceError("hyperposition identity binding mismatch")\n    return expected\n''',
)
replace_exact(
    gwt,
    '''                frame_id=self.frame_id,\n                hyperposition=self.hyperposition,\n''',
    '''                frame_id=self.frame_id,\n                frame_generation=self.frame_generation,\n                frame_sha256=self.frame_sha256,\n                hyperposition=self.hyperposition,\n''',
)
replace_exact(
    gwt,
    '''        frame_id=selection.frame_id,\n        hyperposition=selection.hyperposition,\n''',
    '''        frame_id=selection.frame_id,\n        frame_generation=selection.frame_generation,\n        frame_sha256=selection.frame_sha256,\n        hyperposition=selection.hyperposition,\n''',
)

# WP506 tests: bind the matching helper to the exact outer frame version and add stale-version cases.
replace_exact(
    test_gwt,
    '''def make_hyperposition(*, frame_ref="frame-1"):\n''',
    '''def make_hyperposition(*, frame_ref="frame-1", frame_generation=4, frame_sha256=D):\n''',
)
replace_exact(
    test_gwt,
    '''        provenance_refs=("prov:hp",),\n        situation_frame_ref=frame_ref,\n    )\n''',
    '''        provenance_refs=("prov:hp",),\n        situation_frame_ref=frame_ref,\n        situation_frame_generation=frame_generation,\n        situation_frame_sha256=frame_sha256,\n    )\n''',
)
replace_exact(
    test_gwt,
    '''def test_matching_hyperposition_object_binds_exact_frame_and_digest():\n''',
    '''@pytest.mark.parametrize(\n    ("kwargs", "message"),\n    (\n        ({"frame_generation": 3}, "version binding mismatch"),\n        ({"frame_sha256": "b" * 64}, "version binding mismatch"),\n    ),\n)\ndef test_same_id_stale_hyperposition_frame_version_fails_closed(kwargs, message):\n    stale = make_hyperposition(frame_ref="frame-1", **kwargs)\n    with pytest.raises(GwtWorkspaceError, match=message):\n        build_workspace_selection(\n            selection_id="sel-hp-stale-version",\n            cycle_id="cycle-1",\n            generation=7,\n            frame_id="frame-1",\n            frame_generation=4,\n            frame_sha256=D,\n            grid_plan_id=GRID_PLAN.plan_id,\n            grid_plan_generation=GRID_PLAN.generation,\n            grid_plan_sha256=GRID_PLAN.sha256(),\n            hyperposition=stale,\n            policy=policy(),\n            candidates=(candidate("hp-stale-version"),),\n        )\n\n\ndef test_matching_hyperposition_object_binds_exact_frame_and_digest():\n''',
)
replace_exact(
    test_gwt,
    '''    assert value.as_dict()["hyperposition"]["situation_frame_ref"] == "frame-1"\n''',
    '''    assert value.as_dict()["hyperposition"]["situation_frame_ref"] == "frame-1"\n    assert value.as_dict()["hyperposition"]["situation_frame_generation"] == 4\n    assert value.as_dict()["hyperposition"]["situation_frame_sha256"] == D\n''',
)

# Preserve PR207 as a durable regression but make the formerly external frame-version witness
# explicit at the repaired API boundary.  The scientific condition is unchanged: the canonical
# Hyperposition identity must carry the exact same-id stale generation/digest.
review_test.write_text(
    '''"""Regression for exact Hyperposition -> SituationFrame version binding.\n\nDerived from review-only PR #207. The pre-repair executable result showed that a reused\nframe_id collapsed distinct SituationFrame generations/digests. The repaired ABI requires\nthe external witness to be supplied explicitly and carries it in canonical identity.\n"""\n\nfrom frankenstein2.hyperposition import Alternative, EpistemicStatus, create_hyperposition\n\n\nSTALE_FRAME_SHA256 = "b" * 64\nSTALE_FRAME_GENERATION = 3\n\n\ndef _hyperposition_from_stale_same_id_frame():\n    return create_hyperposition(\n        hyperposition_id="hyper-stale-same-frame-id",\n        generation=2,\n        alternatives=(\n            Alternative(\n                alternative_id="alt-a",\n                proposition_ref="prop:a",\n                generation=2,\n                epistemic_status=EpistemicStatus.UNKNOWN,\n                provenance_refs=("prov:hp:a",),\n            ),\n            Alternative(\n                alternative_id="alt-b",\n                proposition_ref="prop:b",\n                generation=2,\n                epistemic_status=EpistemicStatus.UNKNOWN,\n                provenance_refs=("prov:hp:b",),\n            ),\n        ),\n        provenance_refs=("prov:hp:stale-frame-generation-3",),\n        situation_frame_ref="frame-1",\n        situation_frame_generation=STALE_FRAME_GENERATION,\n        situation_frame_sha256=STALE_FRAME_SHA256,\n    )\n\n\ndef test_hyperposition_carries_exact_situation_frame_generation_and_digest():\n    hyperposition = _hyperposition_from_stale_same_id_frame()\n    payload = hyperposition.as_dict()\n    assert payload.get("situation_frame_ref") == "frame-1"\n    assert payload.get("situation_frame_generation") == STALE_FRAME_GENERATION\n    assert payload.get("situation_frame_sha256") == STALE_FRAME_SHA256\n''',
    encoding="utf-8",
)

# Last guard: the consuming resolver must now receive all three outer-frame identity fields.
patched_gwt = gwt.read_text(encoding="utf-8")
if patched_gwt.count("_resolve_hyperposition_binding(") != 3:
    raise SystemExit("unexpected _resolve_hyperposition_binding call count after repair")
if "hyperposition situation frame version binding mismatch" not in patched_gwt:
    raise SystemExit("version-binding rejection missing after repair")

print("trigger4 frame-version patch applied deterministically")
