from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/frankenstein2/gwt_independent_semantic_mediator.py"
TEST = ROOT / "tests/test_wp900_g10_independent_semantic_mediator.py"
WORKFLOW = ROOT / ".github/workflows/trigger4-wp900-g10-independent-semantic-mediator-ci.yml"
ACTIVE = ROOT / "workpackages/active/F2-WP-900.json"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def patch_source() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'MEDIATED_SEMANTIC_STATE_SCHEMA = "FRANKENSTEIN2_G10_MEDIATED_SEMANTIC_STATE/v2"',
        'MEDIATED_SEMANTIC_STATE_SCHEMA = "FRANKENSTEIN2_G10_MEDIATED_SEMANTIC_STATE/v3"',
        "state schema",
    )
    old_state = '''@dataclass(frozen=True, slots=True, kw_only=True)\nclass MediatedSemanticState:\n    canonical_semantic_json: str\n    semantic_sha256: str\n    wire_sha256: str\n    trial_process_identity: str\n    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False)\n    _factory_sha256: str | None = field(default=None, init=False, repr=False, compare=False)\n\n    schema = MEDIATED_SEMANTIC_STATE_SCHEMA\n    repository_ci_credit = 0\n    target_environment_component_runtime_credit = 0\n    semantic_gwt_runtime_credit = 0\n    jspace_runtime_credit = 0\n    whole_system_acceptance = False\n\n    def __post_init__(self) -> None:\n        object.__setattr__(self, "semantic_sha256", _sha("semantic_sha256", self.semantic_sha256))\n        object.__setattr__(self, "wire_sha256", _sha("wire_sha256", self.wire_sha256))\n        object.__setattr__(\n            self,\n            "trial_process_identity",\n            _text("trial_process_identity", self.trial_process_identity),\n        )\n        semantic = _strict_json(self.canonical_semantic_json.encode("utf-8"))\n        canonical = _canonical_json(semantic)\n        if canonical != self.canonical_semantic_json:\n            raise G10MediatorError("semantic JSON is not canonical")\n        if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != self.semantic_sha256:\n            raise G10MediatorError("semantic_sha256 mismatch")\n\n    def as_dict(self) -> dict[str, Any]:\n        return {\n            "schema": self.schema,\n            "canonical_semantic_json": self.canonical_semantic_json,\n            "semantic_sha256": self.semantic_sha256,\n            "wire_sha256": self.wire_sha256,\n            "trial_process_identity": self.trial_process_identity,\n        }\n\n    def sha256(self) -> str:\n        return _digest(self.as_dict())\n\n\ndef admit_mediated_semantic_state(\n    *,\n    mediator: IndependentSemanticMediatorReceipt,\n    wire: bytes,\n    trial_process_identity: str,\n) -> MediatedSemanticState:\n    """Verifier-side admission. No public plan or attestation metadata crosses into the trial state."""\n    validate_semantic_mediator_receipt(mediator)\n    expected_wire = mediator.to_wire()\n    if wire != expected_wire:\n        raise G10MediatorError("trial wire was not emitted by the factory-valid semantic mediator")\n    value = _strict_json(wire)\n    if type(value) is not dict or set(value) != {"schema", "canonical_semantic_json"}:\n        raise G10MediatorError("invalid treatment-blind mediator wire envelope")\n    if value["schema"] != SEMANTIC_MEDIATOR_WIRE_SCHEMA:\n        raise G10MediatorError("invalid treatment-blind mediator wire schema")\n    canonical = _canonical_json(_strict_json(value["canonical_semantic_json"].encode("utf-8")))\n    if canonical != value["canonical_semantic_json"]:\n        raise G10MediatorError("wire semantic JSON is not canonical")\n    if canonical != mediator.canonical_semantic_json:\n        raise G10MediatorError("trial wire semantic state differs from source mediator")\n    trial_identity = _text("trial_process_identity", trial_process_identity)\n    if trial_identity == mediator.source_process_identity:\n        raise G10MediatorError("source and trial process identities must differ")\n    state = MediatedSemanticState(\n        canonical_semantic_json=canonical,\n        semantic_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),\n        wire_sha256=hashlib.sha256(wire).hexdigest(),\n        trial_process_identity=trial_identity,\n    )\n    return _seal(state, _STATE_FACTORY)\n'''
    new_state = '''@dataclass(frozen=True, slots=True, kw_only=True)\nclass MediatedSemanticState:\n    """The complete behavior-capable pre-child state surface.\n\n    Only canonical semantic content is admitted here. Source, trial, wire and\n    topology identities remain verifier/readback evidence and cannot be used as\n    treatment selectors by the behavior-capable wrapper.\n    """\n\n    canonical_semantic_json: str\n    _factory_seal: object | None = field(default=None, init=False, repr=False, compare=False)\n    _factory_sha256: str | None = field(default=None, init=False, repr=False, compare=False)\n\n    schema = MEDIATED_SEMANTIC_STATE_SCHEMA\n    repository_ci_credit = 0\n    target_environment_component_runtime_credit = 0\n    semantic_gwt_runtime_credit = 0\n    jspace_runtime_credit = 0\n    whole_system_acceptance = False\n\n    def __post_init__(self) -> None:\n        semantic = _strict_json(self.canonical_semantic_json.encode("utf-8"))\n        canonical = _canonical_json(semantic)\n        if canonical != self.canonical_semantic_json:\n            raise G10MediatorError("semantic JSON is not canonical")\n\n    def as_dict(self) -> dict[str, Any]:\n        return {\n            "schema": self.schema,\n            "canonical_semantic_json": self.canonical_semantic_json,\n        }\n\n    def sha256(self) -> str:\n        return _digest(self.as_dict())\n\n\ndef admit_mediated_semantic_state(\n    *,\n    mediator: IndependentSemanticMediatorReceipt,\n    wire: bytes,\n) -> MediatedSemanticState:\n    """Verifier-side admission into the minimal treatment-blind behavior state."""\n    validate_semantic_mediator_receipt(mediator)\n    expected_wire = mediator.to_wire()\n    if wire != expected_wire:\n        raise G10MediatorError("trial wire was not emitted by the factory-valid semantic mediator")\n    value = _strict_json(wire)\n    if type(value) is not dict or set(value) != {"schema", "canonical_semantic_json"}:\n        raise G10MediatorError("invalid treatment-blind mediator wire envelope")\n    if value["schema"] != SEMANTIC_MEDIATOR_WIRE_SCHEMA:\n        raise G10MediatorError("invalid treatment-blind mediator wire schema")\n    canonical = _canonical_json(_strict_json(value["canonical_semantic_json"].encode("utf-8")))\n    if canonical != value["canonical_semantic_json"]:\n        raise G10MediatorError("wire semantic JSON is not canonical")\n    if canonical != mediator.canonical_semantic_json:\n        raise G10MediatorError("trial wire semantic state differs from source mediator")\n    return _seal(MediatedSemanticState(canonical_semantic_json=canonical), _STATE_FACTORY)\n'''
    text = replace_once(text, old_state, new_state, "behavior state block")
    text = replace_once(
        text,
        '    trial_process_identities: tuple[str, str, str, str]\n',
        '',
        "candidate trial identity field",
    )
    old_candidate_identity_validation = '''        for name in ("source_process_identities", "trial_process_identities"):\n            values = tuple(_text(name, value) for value in getattr(self, name))\n            if len(values) != 4 or len(set(values)) != 4:\n                raise G10MediatorError(f"{name} must contain four distinct identities")\n            object.__setattr__(self, name, values)\n        if set(self.source_process_identities) & set(self.trial_process_identities):\n            raise G10MediatorError("source and trial process identity sets must be disjoint")\n'''
    new_candidate_identity_validation = '''        values = tuple(_text("source_process_identities", value) for value in self.source_process_identities)\n        if len(values) != 4 or len(set(values)) != 4:\n            raise G10MediatorError("source_process_identities must contain four distinct identities")\n        object.__setattr__(self, "source_process_identities", values)\n'''
    text = replace_once(
        text,
        old_candidate_identity_validation,
        new_candidate_identity_validation,
        "candidate identity validation",
    )
    text = replace_once(
        text,
        '            "trial_process_identities": list(self.trial_process_identities),\n',
        '',
        "candidate trial identity serialization",
    )
    old_bind_checks = '''        source_wire = mediator.to_wire()\n        if hashlib.sha256(source_wire).hexdigest() != state.wire_sha256:\n            raise G10MediatorError("mediated state does not bind exact source-authority trial wire")\n        if state.canonical_semantic_json != mediator.canonical_semantic_json:\n            raise G10MediatorError("mediated state semantic bytes differ from source authority")\n        if state.semantic_sha256 != mediator.semantic_sha256:\n            raise G10MediatorError("mediated state semantic digest differs from source authority")\n        if state.trial_process_identity == mediator.source_process_identity:\n            raise G10MediatorError("source and trial process identities must differ")\n'''
    new_bind_checks = '''        source_wire = mediator.to_wire()\n        if state.canonical_semantic_json != mediator.canonical_semantic_json:\n            raise G10MediatorError("mediated state semantic bytes differ from source authority")\n        state_semantic_sha256 = hashlib.sha256(state.canonical_semantic_json.encode("utf-8")).hexdigest()\n        if state_semantic_sha256 != mediator.semantic_sha256:\n            raise G10MediatorError("mediated state semantic digest differs from source authority")\n'''
    text = replace_once(text, old_bind_checks, new_bind_checks, "binder behavior-state checks")
    text = replace_once(
        text,
        '        wire_sha256s=tuple(state.wire_sha256 for state in states),  # type: ignore[arg-type]\n',
        '        wire_sha256s=tuple(hashlib.sha256(mediator.to_wire()).hexdigest() for mediator in mediators),  # type: ignore[arg-type]\n',
        "candidate wire digests",
    )
    text = replace_once(
        text,
        '        trial_process_identities=tuple(state.trial_process_identity for state in states),  # type: ignore[arg-type]\n',
        '',
        "candidate trial identities",
    )
    text = replace_once(
        text,
        '    schema = "FRANKENSTEIN2_G10_INDEPENDENT_SEMANTIC_MEDIATOR_CROSSOVER/v2"',
        '    schema = "FRANKENSTEIN2_G10_INDEPENDENT_SEMANTIC_MEDIATOR_CROSSOVER/v3"',
        "candidate schema",
    )
    SOURCE.write_text(text, encoding="utf-8")


def patch_tests() -> None:
    text = TEST.read_text(encoding="utf-8")
    text = text.replace(
        '''        admit_mediated_semantic_state(\n            mediator=mediator,\n            wire=mediator.to_wire(),\n            trial_process_identity=f"trial-process:g10:{position}",\n        )''',
        '''        admit_mediated_semantic_state(\n            mediator=mediator,\n            wire=mediator.to_wire(),\n        )''',
    )
    text = replace_once(
        text,
        '    assert len(set(candidate.trial_process_identities)) == 4\n    assert set(candidate.source_process_identities).isdisjoint(candidate.trial_process_identities)\n',
        '',
        "candidate trial identity assertions",
    )
    text = replace_once(
        text,
        '    assert "runtime_witness" not in params\n    assert behavioral_input_keys().isdisjoint(FORBIDDEN_BEHAVIORAL_INPUT_KEYS)\n',
        '    assert "runtime_witness" not in params\n    assert "trial_process_identity" not in params\n    public_state_fields = {\n        name for name in MediatedSemanticState.__dataclass_fields__ if not name.startswith("_")\n    }\n    assert public_state_fields == {"canonical_semantic_json"}\n    assert behavioral_input_keys().isdisjoint(FORBIDDEN_BEHAVIORAL_INPUT_KEYS)\n',
        "wire ABI assertion",
    )
    anchor = '''def test_mediator_requires_gwt_source_event_bound_to_exact_semantic_bytes():\n'''
    adversarial = '''def test_behavior_capable_state_surface_cannot_recover_abba_treatment_without_semantics():\n    mediators = tuple(\n        source_mediator(position=position, payload=payload)\n        for position, payload in enumerate(PAYLOADS, 1)\n    )\n    states = tuple(\n        admit_mediated_semantic_state(mediator=mediator, wire=mediator.to_wire())\n        for mediator in mediators\n    )\n    public_surfaces_without_semantics = []\n    for state in states:\n        surface = state.as_dict()\n        assert set(surface) == {"schema", "canonical_semantic_json"}\n        public_surfaces_without_semantics.append(\n            {key: value for key, value in surface.items() if key != "canonical_semantic_json"}\n        )\n    assert public_surfaces_without_semantics == [\n        {"schema": states[0].schema},\n        {"schema": states[0].schema},\n        {"schema": states[0].schema},\n        {"schema": states[0].schema},\n    ]\n    assert len({json.dumps(item, sort_keys=True) for item in public_surfaces_without_semantics}) == 1\n\n\n'''
    text = replace_once(text, anchor, adversarial + anchor, "adversarial wrapper-state regression")
    old_forged_call = '''        admit_mediated_semantic_state(\n            mediator=mediator,\n            wire=forged,\n            trial_process_identity="trial-process:g10:forged",\n        )'''
    new_forged_call = '''        admit_mediated_semantic_state(\n            mediator=mediator,\n            wire=forged,\n        )'''
    text = replace_once(text, old_forged_call, new_forged_call, "forged wire call")
    old_direct = '''    forged = MediatedSemanticState(\n        canonical_semantic_json=canonical,\n        semantic_sha256=hashlib.sha256(canonical.encode()).hexdigest(),\n        wire_sha256="f" * 64,\n        trial_process_identity="trial-process:g10:direct-forge",\n    )'''
    new_direct = '''    forged = MediatedSemanticState(canonical_semantic_json=canonical)'''
    text = replace_once(text, old_direct, new_direct, "direct state forge")
    old_identity_test = '''def test_source_and_trial_process_identity_must_differ():\n    mediator = source_mediator(position=1, payload=PAYLOADS[0])\n    with pytest.raises(G10MediatorError, match="must differ"):\n        admit_mediated_semantic_state(\n            mediator=mediator,\n            wire=mediator.to_wire(),\n            trial_process_identity=mediator.source_process_identity,\n        )\n\n\n'''
    new_identity_test = '''def test_behavior_state_admission_rejects_trial_identity_metadata_argument():\n    mediator = source_mediator(position=1, payload=PAYLOADS[0])\n    with pytest.raises(TypeError, match="trial_process_identity"):\n        admit_mediated_semantic_state(\n            mediator=mediator,\n            wire=mediator.to_wire(),\n            trial_process_identity="trial-process:g10:1",  # type: ignore[call-arg]\n        )\n\n\n'''
    text = replace_once(text, old_identity_test, new_identity_test, "identity API regression")
    old_hint_call = '''    state = admit_mediated_semantic_state(\n        mediator=mediator,\n        wire=mediator.to_wire(),\n        trial_process_identity="trial-process:g10:hints",\n    )'''
    new_hint_call = '''    state = admit_mediated_semantic_state(\n        mediator=mediator,\n        wire=mediator.to_wire(),\n    )'''
    text = replace_once(text, old_hint_call, new_hint_call, "external hint call")
    TEST.write_text(text, encoding="utf-8")


def patch_workflow() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '              "runtime_witness",\n          ):\n              assert forbidden not in params\n          assert g10.behavioral_input_keys().isdisjoint(g10.FORBIDDEN_BEHAVIORAL_INPUT_KEYS)\n',
        '              "runtime_witness",\n              "trial_process_identity",\n          ):\n              assert forbidden not in params\n          public_state_fields = {\n              name for name in g10.MediatedSemanticState.__dataclass_fields__\n              if not name.startswith("_")\n          }\n          assert public_state_fields == {"canonical_semantic_json"}\n          assert g10.behavioral_input_keys().isdisjoint(g10.FORBIDDEN_BEHAVIORAL_INPUT_KEYS)\n',
        "workflow behavior-state ABI fence",
    )
    WORKFLOW.write_text(text, encoding="utf-8")


def patch_active() -> None:
    data = json.loads(ACTIVE.read_text(encoding="utf-8"))
    if data.get("workpackage_id") != "F2-WP-900" or data.get("generation") != 10:
        raise SystemExit("active WP900 G10 authority moved; refuse stale repair")
    if data.get("claim_id") != "F2-WP-900-G10-GPT56SOL-INDEPENDENT-SEMANTIC-MEDIATOR-AUTHORITY-20260902":
        raise SystemExit("active WP900 claim moved; refuse stale repair")
    data["blocking_deficit"] = (
        "The exact accepted 93354ea repository subject is preserved as historical repository evidence but is invalid as a target subject after executed SIDECHANNEL_RECOVERY=4/4. This in-place G10 repair removes trial_process_identity plus verifier/readback-only wire/topology metadata from the behavior-capable MediatedSemanticState and adds an adversarial state-surface regression. The new source subject has repository_ci_credit=0 until exact targeted G8+G9+G10 CI and deterministic release CI re-execute it. Target/runtime/semantic-GWT/J-Space credits remain zero."
    )
    data["current_scope"] = "G10_BEHAVIOR_STATE_SIDECHANNEL_REPAIR_LANDED_REPOSITORY_GATES_PENDING"
    data["repository_ci_credit"] = 0
    data["runtime_execution_observed"] = False
    data["target_environment_component_runtime_credit"] = 0
    data["semantic_mediator_authority_candidate_credit"] = 0
    data["semantic_gwt_runtime_credit"] = 0
    data["gwt_runtime_credit"] = 0
    data["jspace_runtime_credit"] = 0
    data["runtime_credit"] = 0
    data["runtime_subject_churn_class"] = "REQUIRED_REPAIR_INVALIDATED_93354EA_NEW_REPOSITORY_SUBJECT_GATES_PENDING"
    data["new_component_necessity"] = (
        "NO NEW COMPONENT AND NO G11. G10 is repaired in place. The behavior-capable state now carries only canonical semantic JSON; topology and process-instance identity must be supplied later by external verifier/readback evidence, never by behavior-visible caller labels."
    )
    data["next_exact_action"] = (
        "Execute the targeted G10 workflow and deterministic release workflow on the exact new repair commit. Require the adversarial public-state regression, predecessor G8/G9 fences, source-forgery fences and zero-credit fence to pass. Repeat independent ABI review. Do not dispatch VPS until those exact repository gates are green; then freeze only that new exact subject for the external source->verifier/trial->executor process-topology discriminator."
    )
    ACTIVE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    expected_head = os.environ.get("EXPECTED_BASE_SHA")
    if expected_head:
        import subprocess
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if actual != expected_head:
            raise SystemExit(f"stale repair base: expected {expected_head}, got {actual}")
    patch_source()
    patch_tests()
    patch_workflow()
    patch_active()
    print("WP900 G10 trial-state sidechannel repair applied deterministically")


if __name__ == "__main__":
    main()
