# Trigger 7 — Full-Duplex System Evaluation Matrix G1

Date: 2026-09-02
Organ: GPT-5.6-Sol
Research ID: T7-20260902-FULL-DUPLEX-SYSTEM-EVAL-G1
Semantic key: `47fbda9348f75b462ef172fce955b3a49f5635965864f24bd9cddb080a7274f7`
Work class: CANDIDATE_FALSIFIER / RESEARCH_ONLY
Product mutation authority: NONE

## Purpose

Define a compact adversarial system-level benchmark for the **existing** Frankenstein 2.0 Voice-Slice:

`ASR -> Voice Packet Cortex -> Presence/Turn Policy -> Barge-in -> Output/TTS -> Recovery -> persistent state -> Reentry`

This benchmark exists to determine whether the already-present Voice authorities preserve one causal conversation/output lineage when boundaries interact. It is explicitly **not** permission to create new micro-components.

Current repository-executable composition evidence already covers the chain with ASR/TTS surrogates, checkpoint filesystem roundtrip, restart/reentry, heard-result handling and closed-restart idempotence. The next useful research move is therefore adversarial cross-boundary evaluation, followed by Trigger 4 runtime execution at the lowest faithful VPS sandbox tier.

## Evidence fence

This file mints **zero** runtime or product credit.

Even a complete pass of this matrix at repository/S1/S2 scope does not by itself prove:

- real acoustic ASR;
- real TTS model synthesis unless a bound model-runtime probe is executed;
- first audible playback or what a human physically heard;
- physical microphone/speaker behavior;
- native OS audio permissions/device enumeration/session rights;
- physical barge-in or acoustic echo cancellation;
- physical perception;
- host install/upgrade/reboot survival;
- semantic GWT/J-Space;
- effects;
- training;
- whole-product acceptance.

## Evaluation laws

Every executed case MUST preserve:

1. one causal conversation/turn lineage;
2. one authoritative policy decision per decision identity;
3. monotone output lifecycle (`proposed -> started -> heard/complete | interrupted/cancelled`) without resurrection;
4. interruption cannot later become a fully-heard/commit-eligible output;
5. late/stale packets and tool results cannot mutate a closed or superseded turn;
6. restart/reentry cannot duplicate already-closed output or effects;
7. persistence/reentry must bind exact IDs, not merely semantically similar text;
8. failure must be classified as PRODUCT_NEGATIVE, EVIDENCE_INVALID, INFRA_AUTH_TRANSPORT_QUOTA, CONCURRENCY_RETRY, or UNKNOWN_NONTERMINAL before repair;
9. no test may weaken an invariant just to become green.

## G1 adversarial scenario matrix

| ID | Scenario | Boundary stressed | Required observable / fail-closed invariant |
|---|---|---|---|
| FD01 | Clean sequential user turn, no overlap | ASR -> Packet Cortex -> policy -> output | Exactly one final input lineage, one policy decision, one output lineage; no duplicate packets or reentry events. |
| FD02 | User speech begins while output is in progress | Presence/turn -> barge-in -> output | Old output becomes interrupted/cancelled; its heard fraction stays `< 1`; it is not commit-eligible; no later chunk can resurrect it. |
| FD03 | Barge-in immediately after first output chunk | TTS/output cancellation timing | Cancellation is idempotent and bounded; post-cancel chunks are rejected at the producer/sink admission boundary. |
| FD04 | Duplicate barge-in/cancel signal | Barge-in idempotence | A second equivalent cancel does not create a second output terminal event, second policy transition, or duplicate reentry. |
| FD05 | Final ASR arrives after a provisional/HOLD state | ASR revision -> policy | Final evidence supersedes provisional state exactly once; stale HOLD cannot overwrite a later final decision. |
| FD06 | Duplicate final ASR packet | Packet Cortex dedupe -> policy | Same causal input identity cannot produce duplicate policy decisions or duplicate output. |
| FD07 | Out-of-order older ASR revision arrives after final | Packet ordering -> policy | Older revision is rejected/ignored as stale; accepted final state remains monotone. |
| FD08 | Late tool/result packet after user interruption | recovery/tool-result -> turn closure | Late result cannot commit into interrupted/superseded turn before or after restart. |
| FD09 | Late output/TTS packet after cancellation | output transport -> heard-result | Packet is rejected; interrupted output cannot regain heard/complete eligibility. |
| FD10 | Process crash after output start but before terminal heard-result | recovery -> persistence -> reentry | Restart reconstructs one open/interrupted-safe lineage; no duplicate playback/output commit is synthesized merely from restart. |
| FD11 | Process crash after terminal output completion persisted | persistence -> reentry | Restart does not replay or duplicate the terminal output; closed-restart replay is idempotent. |
| FD12 | Process crash after interruption persisted | persistence -> reentry | Interrupted terminal state survives; restart cannot convert it to complete/fully-heard/commit-eligible. |
| FD13 | Repeated restart/reentry N>=3 | persistent state -> reentry | Event/output cardinality is stable after first valid reentry; no restart-amplified duplicate events. |
| FD14 | Long silence then next user turn | presence/reentry -> new turn | New turn gets a new causal identity while preserving prior closed lineage; no stale prior HOLD/output leaks into it. |
| FD15 | Near-simultaneous user speech start and output completion | turn policy + heard-result race | Exactly one causally ordered terminal interpretation is admitted; contradictory complete+interrupted terminal states are impossible. |
| FD16 | Backchannel-like short overlap while output is active | presence/turn policy | Whatever current policy selects, exactly one decision is recorded and replay-stable; no duplicate independent policy authority is invoked. |
| FD17 | Output cancellation followed immediately by new response generation | barge-in -> next output | New output has a distinct output ID/turn binding; old cancelled chunks cannot enter the new sink/lineage. |
| FD18 | Stale packet from previous turn with otherwise valid schema | Packet Cortex -> policy | Causal parent/turn mismatch is rejected; schema validity alone is insufficient. |
| FD19 | Checkpoint write/readback with tampered/missing causal ID | persistence -> recovery | Fail closed as invalid evidence/state; do not reconstruct by text similarity or guessed identity. |
| FD20 | Restart during/after policy transition boundary | policy -> persistence -> reentry | Reentry yields one authoritative policy state; never two mutually inconsistent decisions for one decision identity. |

## Metrics to record on every executable run

Minimum machine-readable measurements:

- exact F2 source SHA and artifact/probe hashes;
- execution surface and sandbox tier;
- workflow/run/job identity where applicable;
- exact case IDs executed and counts;
- accepted/rejected packet counts by causal ID;
- policy-decision cardinality per decision ID;
- output lifecycle transitions per output ID;
- interruption/cancel timestamp and last accepted post-cancel chunk index;
- heard fraction / commit eligibility when represented by the current packet contract;
- persistence checkpoint identity/hash;
- restart/reentry event cardinality;
- duplicate/stale rejection counts;
- latency points that are faithfully measurable on the selected surface;
- stdout/stderr or trace hashes;
- explicit zero-credit fields.

## Tier plan

### Repository / S1

Run all deterministic packet-state scenarios possible without real audio hardware. Use synthetic/recorded packet timing, reorder, duplicate, cancellation, crash/checkpoint/restart and reentry. This tier may prove causal/state invariants only.

### S2

Add fuller Ubuntu service/user/filesystem lifecycle where needed: daemon/process restart, package/runtime dependencies, permission ownership, persistent paths, and headless local ASR/TTS model processes if the model-specific claim is independently bound. Still no physical audio credit.

### S3

Use only for a separate-kernel property not faithfully or safely representable in S1/S2, for example kernel/reboot/device-emulation behavior needed before S4. Do not move a dangerous kernel-level test to the owner's workstation merely for convenience.

### S4 — irreducibly physical only

Reserve for:

- real microphone capture;
- real speaker playback;
- native OS audio permissions;
- actual audio-device enumeration/hotplug/driver behavior;
- desktop/session rights;
- physical acoustic interruption/AEC/denoise behavior;
- install/upgrade/reboot persistence on the actual workstation;
- physical perception;
- final one-handoff installer/acceptance.

## Current transition decision

The architectural hypothesis is accepted **with evidence gates**:

- Do not open new small Voice components merely because the system-level matrix reveals an untested interaction.
- First map every failure to an existing authority and reproduce it there.
- A new component is legal only if an executed discriminator proves a named missing dependency that cannot be closed by existing machinery.
- WP715 repaired-subject runtime evidence is already reconciled at bounded scope; do not reopen it without executable counterevidence.
- WP903 remains terminal only at its exact bounded hostile-twin/S1 scope.
- WP720 remains subject-fenced/nonterminal until its current singleton VPS successor probe is terminally reconciled; do not duplicate or semantically churn that subject.
- The composed packet Voice-Slice G4 repository execution is useful readiness evidence but remains surrogate/non-acoustic and cannot be promoted into VPS/physical/whole-voice credit.

## Trigger 4 handoff condition

Trigger 4 should consume this benchmark only after refreshing current heads and overlap. It should run the **smallest existing-system composed discriminator** that increases evidence depth without duplicating WP720's bound runtime subject or the already-routed headless Qwen3-TTS claim.

Preferred order:

1. reconcile the current WP720 singleton runtime result when terminal;
2. consume the separately routed headless Qwen3-TTS 0.6B VPS model-runtime scope if no duplicate execution exists;
3. execute this G1 matrix against the composed Voice-Slice at the lowest faithful VPS sandbox tier, binding exact current source/artifact identities;
4. repair only reproducible PRODUCT_NEGATIVE failures at the owning existing boundary;
5. repeat the composed matrix after repair;
6. advance to S4 only for the explicitly irreducible physical gates above.

## External research falsifiers, not adopted architecture

Current full-duplex research candidates such as semantic streaming turn-state predictors and native duplex speech models should be treated as comparator/falsifier inputs. They do not justify replacing the current Packet Cortex / policy / output authorities without measured evidence that the present architecture cannot meet the required causal, latency or interruption invariants.

## Exact next research action

Keep Trigger 7 on system-level evaluation/research and model/runtime candidate falsification. Do **not** add another micro-component frontier. On every reentry, refresh WP720, the headless TTS runtime semantic key, and any Trigger-4 consumption of this G1 benchmark before creating further work.
