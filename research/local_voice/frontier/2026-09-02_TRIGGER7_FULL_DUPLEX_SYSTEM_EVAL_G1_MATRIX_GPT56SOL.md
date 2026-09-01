# Trigger 7 — Full-Duplex System Evaluation Matrix G1

Date: 2026-09-02
Organ: GPT-5.6-Sol
Research ID: T7-20260902-FULL-DUPLEX-SYSTEM-EVAL-G1
Semantic key: `47fbda9348f75b462ef172fce955b3a49f5635965864f24bd9cddb080a7274f7`
Work class: CANDIDATE_FALSIFIER / RESEARCH_ONLY
Product mutation authority: NONE

## Current reentry decision

This benchmark was first written while WP720's repaired singleton VPS successor was still nonterminal. Before routing it, F2 main advanced and **WP720 G1 was terminally reconciled** through exact owner-VPS controller run `33537472310` / job `99955200635` at bounded packet-turn-policy target-component runtime scope. WP715's repaired-subject VPS runtime was already reconciled immediately before it, and WP903 is already terminal at its exact bounded S1/hostile-twin scope.

Therefore the architect hypothesis is now **ACCEPTED WITH EVIDENCE FENCES**:

- WP720 + WP715 + WP903 no longer block system-level Voice-Slice convergence at their accepted scopes.
- Do not open more small Voice components by default.
- Move the active frontier to the composed system path:
  `ASR -> Voice Packet Cortex -> Presence/Turn Policy -> Barge-in -> Output/TTS -> Recovery -> persistent state -> Reentry`.
- Maximize VPS S1/S2/S3 fidelity before S4.
- Preserve all physical/acoustic/whole-product zero-credit boundaries until actually executed.

WP720's reconciliation does **not** establish physical audio, real ASR/TTS, semantic GWT/J-Space, effects, whole-voice E2E or whole-system acceptance.

## Purpose

Define a compact adversarial system-level benchmark for the **existing** Frankenstein 2.0 Voice-Slice and determine whether existing authorities preserve one causal conversation/output lineage when their boundaries interact. It is explicitly not permission to create new micro-components.

Current repository-executable G4 composition evidence already exercised the chain with ASR/TTS surrogates, Packet Cortex, Presence/Turn Policy, barge-in cancellation, checkpoint filesystem roundtrip, restart/reentry, fully-heard result handling and closed-restart idempotence. That run executed 51 tests without a counterexample at repository-executable information-packet scope. The remaining move is higher-fidelity composed execution, not more component breadth.

A separate Trigger-7 handoff already splits Qwen3-TTS into a VPS-representable headless model-runtime scope, and a virtual-audio sandbox-fidelity addendum already specifies recorded PCM -> real local ASR -> existing packet/policy/barge path -> real local TTS -> file/null or sandbox virtual sink -> recovery/state/reentry. Those existing packets must be reused rather than duplicated.

## Evidence fence

This file mints **zero** runtime or product credit.

Even a complete pass of this matrix at repository/S1/S2 scope does not by itself prove:

- first audible playback or what a human physically heard;
- physical microphone/speaker behavior;
- native workstation OS audio permissions/device enumeration/session rights;
- physical acoustic barge-in, AEC or denoise quality;
- physical perception;
- real workstation install/upgrade/reboot survival;
- semantic GWT/J-Space;
- effects;
- training;
- whole-product acceptance.

Real local ASR/TTS software runtime may only receive its own bounded credit when exact model/runtime/fixture/source identities actually execute.

## Evaluation laws

Every executed case MUST preserve:

1. one causal conversation/turn lineage;
2. one authoritative policy decision per decision identity;
3. monotone output lifecycle (`proposed -> started -> complete/heard | interrupted/cancelled`) without resurrection;
4. interruption cannot later become fully-heard/commit-eligible output;
5. late/stale packets and tool results cannot mutate a closed or superseded turn;
6. restart/reentry cannot duplicate already-closed output or effects;
7. persistence/reentry must bind exact IDs, not semantically similar text;
8. failure must be classified as PRODUCT_NEGATIVE, EVIDENCE_INVALID, INFRA_AUTH_TRANSPORT_QUOTA, CONCURRENCY_RETRY, or UNKNOWN_NONTERMINAL before repair;
9. no invariant may be weakened merely to make a test green.

## G1 adversarial scenario matrix

| ID | Scenario | Boundary stressed | Required observable / fail-closed invariant |
|---|---|---|---|
| FD01 | Clean sequential user turn, no overlap | ASR -> Packet Cortex -> policy -> output | Exactly one final input lineage, one policy decision, one output lineage; no duplicate packets or reentry events. |
| FD02 | User speech begins while output is in progress | Presence/turn -> barge-in -> output | Old output becomes interrupted/cancelled; heard fraction stays `< 1`; it is not commit-eligible; no later chunk resurrects it. |
| FD03 | Barge-in immediately after first output chunk | TTS/output cancellation timing | Cancellation is idempotent and bounded; post-cancel chunks are rejected at producer/sink admission. |
| FD04 | Duplicate barge-in/cancel signal | Barge-in idempotence | No second terminal event, second policy transition or duplicate reentry. |
| FD05 | Final ASR arrives after provisional/HOLD | ASR revision -> policy | Final evidence supersedes provisional state exactly once; stale HOLD cannot overwrite later final decision. |
| FD06 | Duplicate final ASR packet | Packet Cortex dedupe -> policy | Same causal input identity cannot produce duplicate policy decisions/output. |
| FD07 | Older ASR revision arrives after final | Packet ordering -> policy | Older revision is stale/rejected; accepted final state stays monotone. |
| FD08 | Late tool/result packet after interruption | recovery/tool-result -> closure | Late result cannot commit into interrupted/superseded turn before or after restart. |
| FD09 | Late TTS/output packet after cancellation | output -> heard-result | Packet rejected; interrupted output cannot regain complete/heard eligibility. |
| FD10 | Crash after output start before terminal heard-result | recovery -> persistence -> reentry | Restart reconstructs one safe lineage; no duplicate playback/output commit is invented. |
| FD11 | Crash after completed output persisted | persistence -> reentry | Restart does not replay/duplicate terminal output; closed replay is idempotent. |
| FD12 | Crash after interruption persisted | persistence -> reentry | Interrupted terminal state survives; restart cannot convert it to complete/fully-heard. |
| FD13 | Repeated restart/reentry N>=3 | persistence -> reentry | Event/output cardinality stable after first valid reentry; no restart amplification. |
| FD14 | Long silence then next turn | presence/reentry -> new turn | New causal identity; no stale prior HOLD/output leakage. |
| FD15 | Near-simultaneous speech start and output completion | policy + heard-result race | Exactly one causally ordered terminal interpretation; contradictory complete+interrupted states impossible. |
| FD16 | Backchannel-like short overlap | presence/turn policy | Current policy may choose its allowed outcome, but exactly one decision is replay-stable and no second authority participates. |
| FD17 | Cancel then immediate new response | barge-in -> next output | New distinct output ID/turn binding; cancelled old chunks cannot enter new lineage. |
| FD18 | Valid-schema stale packet from previous turn | Packet Cortex -> policy | Causal parent/turn mismatch rejected; schema validity alone is insufficient. |
| FD19 | Tampered/missing causal ID in checkpoint/readback | persistence -> recovery | Fail closed; do not reconstruct by text similarity or guessed identity. |
| FD20 | Restart at policy-transition boundary | policy -> persistence -> reentry | One authoritative policy state after reentry; never two conflicting decisions for one identity. |

## Required observables

Every promotion-bearing execution must preserve at least:

- exact F2 source/tree SHA and probe/artifact hashes;
- execution surface and sandbox tier;
- workflow/run/job identity where applicable;
- exact case IDs and counts;
- exact ASR/TTS model + artifact identities when real model paths execute;
- input PCM/WAV hash, sample rate, channels and duration when acoustic input is represented;
- accepted/rejected packet counts by causal ID;
- policy-decision cardinality per decision ID;
- output lifecycle transitions per output ID;
- cancel/barge identity, producer/sink stop boundary and late-frame rejection;
- heard fraction / commit eligibility only when represented by the executed contract;
- persistence checkpoint identity/hash;
- restart/reentry cardinality;
- duplicate/stale rejection counts;
- faithfully measurable latency/resource points;
- outbound inference API counters for local-only evidence;
- stdout/stderr/trace hashes;
- explicit zero-credit fields.

## Sandbox-first execution ladder

### Repository / S1

Use pinned recorded German PCM for real local ASR when available, real local TTS generation into a file/null/in-memory sink, deterministic timing/reorder/duplicate/cancellation injection, checkpoint/restart and reentry. Repository G4 surrogate evidence remains useful but does not substitute for the real software model paths.

### S2

If the existing output adapter requires an OS audio service/device API, use sandbox-local PipeWire/PulseAudio/null-sink style virtual audio where faithful. Exercise service/user/session/filesystem permission and lifecycle behavior that does not require physical hardware. A virtual sink can prove adapter delivery/cancellation, never human-heard output.

### S3

Use a separate-kernel VM only for a property S1/S2 cannot faithfully or safely represent, such as kernel/device-emulation behavior. Do not move a kernel-risk test to the physical workstation for convenience.

### S4 — irreducibly physical only

Reserve for:

- real microphone capture;
- real speaker transduction;
- human-heard output truth;
- native workstation OS audio permissions;
- actual device enumeration/hotplug/driver behavior;
- desktop/session rights not faithfully virtualized;
- physical acoustic interruption/AEC/denoise behavior;
- actual workstation persistence over install/upgrade/reboot;
- physical perception;
- final one-handoff installer/acceptance.

## No-new-component rule

A failed G1 case first maps to an **existing owning authority** and is reproduced there. A new Voice component is legal only if an executed discriminator proves a named missing dependency that existing machinery cannot close. Test absence is not such proof.

## Trigger 4 handoff

Trigger 4 should refresh current heads and overlap, then consume the existing system-slice packets rather than creating parallel authorities.

Preferred sequence now that WP720 is closed:

1. consume/execute the already-routed headless Qwen3-TTS 0.6B VPS model-runtime scope if no material duplicate execution exists;
2. bind real local ASR input using pinned German PCM and exact model/source identities at S1 when current admitted ASR runtime is available;
3. execute G1 against the composed existing Voice-Slice at the lowest faithful VPS tier, starting with real local ASR + real local TTS -> file/null sink and escalating to S2 virtual audio only if the existing output adapter needs OS-audio fidelity;
4. repair only reproducible PRODUCT_NEGATIVE failures at the owning existing boundary;
5. rerun the composed matrix after repair;
6. use S3 only for proven separate-kernel need;
7. advance to S4 only for the explicitly irreducible physical gates above.

## External research falsifiers, not adopted architecture

Semantic streaming turn-state predictors and native duplex speech models remain comparator/falsifier inputs. They do not justify replacing Packet Cortex / policy / output authorities unless measured evidence shows the current architecture cannot meet causal, latency or interruption invariants.

## Exact next research action

Trigger 7 remains on **system-level evaluation, sandbox-fidelity and model/runtime falsification**. Do not add another micro-component frontier. Re-enter current main after each Trigger-4 consumption and only create a new research generation when the existing G1/model-runtime evidence exposes a genuinely new unresolved hypothesis.
