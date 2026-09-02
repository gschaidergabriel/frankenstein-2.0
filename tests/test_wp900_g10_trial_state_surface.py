from dataclasses import fields

from frankenstein2.gwt_independent_semantic_mediator import admit_mediated_semantic_state
from test_wp900_g10_independent_semantic_mediator import PAYLOADS, source_mediator


FORBIDDEN_PRE_CHILD_STATE_FIELDS = {
    "semantic_sha256",
    "wire_sha256",
    "trial_process_identity",
    "trial_position",
    "semantic_class",
    "raw_payload_sha256",
    "source_process_identity",
    "source_range_sha256",
    "source_event_sequence",
    "runtime_witness_sha256",
    "exact_source_sha256",
    "boot_id_sha256",
    "arm",
    "condition",
    "expected_outcome",
}


def test_behavior_capable_state_exposes_only_canonical_semantic_json():
    mediator = source_mediator(position=1, payload=PAYLOADS[0])
    state = admit_mediated_semantic_state(
        mediator=mediator,
        wire=mediator.to_wire(),
        trial_process_identity="trial-process:g10:1",
    )

    public_dataclass_fields = {item.name for item in fields(state) if not item.name.startswith("_")}
    assert public_dataclass_fields == {"canonical_semantic_json"}
    assert set(state.as_dict()) == {"schema", "canonical_semantic_json"}
    assert FORBIDDEN_PRE_CHILD_STATE_FIELDS.isdisjoint(public_dataclass_fields)
    for name in FORBIDDEN_PRE_CHILD_STATE_FIELDS:
        assert not hasattr(state, name)


def test_abba_position_is_not_recoverable_from_nonsemantic_state_metadata():
    states = []
    for position, payload in enumerate(PAYLOADS, 1):
        mediator = source_mediator(position=position, payload=payload)
        states.append(
            admit_mediated_semantic_state(
                mediator=mediator,
                wire=mediator.to_wire(),
                trial_process_identity=f"trial-process:g10:{position}",
            )
        )

    nonsemantic_views = []
    for state in states:
        visible = {
            name: getattr(state, name)
            for name in dir(state)
            if not name.startswith("_")
            and name != "canonical_semantic_json"
            and not callable(getattr(state, name))
        }
        nonsemantic_views.append(visible)

    # Public constants may exist, but no per-trial position/treatment selector may vary.
    assert all(view == nonsemantic_views[0] for view in nonsemantic_views[1:])
    assert all(FORBIDDEN_PRE_CHILD_STATE_FIELDS.isdisjoint(view) for view in nonsemantic_views)
