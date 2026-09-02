from dataclasses import fields

from frankenstein2.gwt_independent_semantic_mediator import admit_mediated_semantic_state
from test_wp900_g10_independent_semantic_mediator import PAYLOADS, source_mediator


def test_behavior_capable_state_exposes_only_canonical_semantics():
    """Verifier-only topology/identity metadata must never enter behavior-capable state."""
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

    public_state_fields = {
        item.name for item in fields(states[0]) if not item.name.startswith("_")
    }
    assert public_state_fields == {"canonical_semantic_json"}

    # The wrapper may inspect every admitted public field except semantic content.
    # There must be no remaining per-trial selector from which ABBA position/class
    # can be recovered without reading canonical_semantic_json itself.
    for state in states:
        nonsemantic_public_state = {
            item.name: getattr(state, item.name)
            for item in fields(state)
            if not item.name.startswith("_") and item.name != "canonical_semantic_json"
        }
        assert nonsemantic_public_state == {}
