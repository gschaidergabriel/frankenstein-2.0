# Trigger 7 — PFD policy-conditioned packet benchmark precondition delta

Date: 2026-09-01
Trigger: 7
Producer: GPT-5.6-Sol
Research claim: `T7-20260901-INSTRUCT-FD-POLICY`
Claim mode: `ACTIVE_REVIEW_ONLY_SOURCE_RESEARCH`
Mutation authority: `false`
Authority: `research/local_voice/authority/2026-08-31_TRIGGER7_TEXT_PACKET_COMPLETION_AUTHORITY.md`
Protocol: `research/local_voice/TRIGGERWORD_7_PROTOCOL.md`
Observed F2 main before this delta: `a21c5a64d88288c449088f28397bb32411e20f98`

## Question

Can the proposed PFD1–PFD5 discriminator vary one authorized turn-management policy dimension while keeping the same causal conversation history and the same subsequent packet inputs, then prove that the local packet cortex changes its event/output trajectory for the expected reason?

## Current-source observations

Current `src/frankenstein2/voice_packet_cortex.py` exposes deterministic packet/event state with:

- input `endpoint_decision` in `HOLD|END|UNKNOWN`;
- input `overlap_state`;
- input `barge_in`;
- output/event intents including `WAIT`, `BACKCHANNEL`, `ANSWER`, `TOOL_USE`, `CLOSE`;
- deterministic cancellation when an accepted input packet sets `barge_in=True`;
- deterministic replay/order/monotonic-time validation.

The current `VoicePacketCortex` constructor accepts the session, presence state, and opening monotonic timestamp. It does **not** accept an explicit turn-policy object/configuration, and the current source contains no `PacketTurnPolicy` type.

Current `tests/test_voice_packet_cortex.py` proves important primitive behavior, including direct barge-in cancellation and shared event-fabric emission for WAIT/BACKCHANNEL/tool/GWT/memory references. Those tests do not establish a matched-history policy intervention where only an explicit policy binding differs.

## Result

`PFD_POLICY_INTERVENTION_PRECONDITION = ABSENT_AT_CURRENT_SOURCE`

Classification:

`RESEARCH_PRECONDITION_ABSENT / INTEGRATION_BLOCKER_CANDIDATE`

This is **not** a product-negative claim by itself. The current packet cortex has not been shown here to violate an admitted product invariant requiring instruction-conditioned turn policy. The narrower result is that the proposed causal PFD benchmark cannot currently isolate policy as the intervention variable without either:

1. binding an already-existing upstream policy surface to the packet-cortex consumer, if one exists elsewhere in the current product; or
2. adding the smallest explicit immutable policy input at the existing authoritative turn-control boundary.

It must not be faked by changing `barge_in`, `endpoint_decision`, `overlap_state`, transcript text, timing, or another packet field between arms and calling that a policy-only intervention. That would alter the observed input, not isolate policy conditioning.

## External-primary research synthesis

### Instruct-FD — arXiv:2607.20460

Useful architecture-agnostic donor: evaluate controllable turn management by changing the conversational instruction/policy while holding the scenario/history comparable. The paper reports substantial remaining instruction-adherence error and especially difficult proactive backchannel/interruption behavior. Trigger 7 imports the **evaluation structure**, not its model architecture or judge authority.

### Full-Duplex-Bench — arXiv:2503.04721

Useful behavior-axis donor: pause handling, backchanneling, turn-taking and interruption management are evaluated separately. This supports keeping PFD trajectory assertions behavior-specific rather than using one aggregate “naturalness” score.

### Synchronization and Turn-Taking in Full-Duplex Speech Dialogue Models — arXiv:2605.20356

Useful causal-method donor only: turn-taking claims become stronger when controlled interventions/readback establish that internal or policy state changes downstream behavior, rather than relying on correlation or model self-report.

No external source mints F2 evidence or runtime credit.

## Refined PFD discriminator

PFD0 — **binding precondition**

- Resolve the current single authoritative turn-control consumer and current mutation owner.
- Prove an explicit policy/config input already exists, or add only the smallest binding necessary through Trigger 4.
- Do not create a second turn FSM, cortex, state authority, output queue, cancellation path, or VoiceIntent authority.
- User barge-in immediate cancellation remains an invariant and must not become an optional policy knob.

PFD1 — **matched initial state**

- Same `VoiceSessionCapsule` construction semantics.
- Same presence state.
- Same deterministic conversation-history fixture.
- Same sensory/input packet sequence and timing after the intervention point.

PFD2 — **single policy intervention**

- Change exactly one admitted turn-management policy dimension.
- All non-policy inputs and state hashes before the intervention remain equal.

PFD3 — **same continuation**

- Feed identical subsequent packet inputs to both arms.
- No external model API/network dependency.

PFD4 — **behavioral readback**

- Require an expected event/output trajectory delta attributable to the policy intervention, for example an admitted WAIT-vs-BACKCHANNEL decision at the existing controller boundary.
- Do not use a dimension that weakens mandatory user-barge-in cancellation.
- Record exact event/output trajectory hashes and the first causal divergence point.

PFD5 — **deterministic controls**

- Repeat each arm and require stable hashes.
- Same-policy matched control must remain identical.
- Policy difference must be serialized/bound into provenance so a hidden metadata-only no-op cannot pass.

## Falsifiers

The benchmark fails closed if any of the following occurs:

- the two arms differ in packet input, timing, history, or causal identity before the intended policy intervention;
- policy metadata differs but event/output trajectory is identical where a behavioral delta is required;
- the implementation creates a competing turn/cancellation/state authority;
- the policy can suppress mandatory user-barge-in cancellation;
- an external model API is required for the deterministic packet discriminator;
- repeated same-policy runs produce different trajectory hashes without an explicitly admitted nondeterminism source.

## Credit fence

This delta grants:

- source-research credit: bounded donor/precondition finding only.

This delta grants **zero**:

- repository product acceptance credit;
- target runtime credit;
- acoustic/physical audio credit;
- GWT/J-Space semantic runtime credit;
- effect credit;
- training credit;
- completion credit;
- whole-system acceptance.

## Routing decision

Route one bounded Trigger-4 handoff: resolve the existing turn-control owner/binding first; if no explicit policy input exists at the authoritative boundary and the mutation slot is free, add only the smallest immutable policy binding needed for the matched-history PFD discriminator. Then execute deterministic repository tests. Trigger 7 consumes the result on re-entry.
