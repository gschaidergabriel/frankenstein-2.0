# Trigger 7 — System-Slice Transition / Queue Reentry Checkpoint

Status: **REENTRY SYNTHESIS PERSISTED / NO NEW PRODUCT MUTATION / NO NEW EXPERIMENT CLAIM**

## Trigger

- `7` / `triggerword 7` / `triggerwort 7`
- Protocol: `research/local_voice/TRIGGERWORD_7_PROTOCOL.md`
- Product invariant: `architecture/LOCAL_VOICE_RUNTIME_CONTRACT.md`
- Trigger-4 handoff commit: `00df70c057256341f31178c85226441a00ff798e`

## Owner hypothesis reviewed

After WP720 + WP715 + WP903 are cleanly closed, stop opening small Voice components and raise the focus to one composed Voice slice:

`ASR -> Packet Cortex -> Presence/Turn Policy -> Barge-in -> Output/TTS -> Recovery -> persistent state -> reentry`

Run all faithfully representable acceptance work in VPS S1/S2/S3 first. Reserve S4 for irreducible physical-machine properties.

## Assessment

**Directionally supported, but the transition precondition is not yet fully met.**

The current repository already contains the correct whole-voice acceptance shape. The productive next architecture move is composition/runtime-credit conversion, not another standalone Voice FSM/policy/state authority. However, two exact repaired component subjects are still nonterminal at the target/VPS execution boundary and must not be semantically churned or duplicate-dispatched while queued.

## Reentry evidence

### WP903

- accepted at exact-subject S1 restart/crash soak component-execution scope;
- exact subject: `731db925df96ab7e49c0e5b80cd7bc8f4d37a086`;
- 30 iterations / 60 cases;
- `EXECUTED_NO_COUNTEREXAMPLE`;
- broad target-runtime / physical / whole-voice credit remains zero.

### WP715 G3

- repaired current subject: `68b1db374c86027be987c1fdc5e88ff13f11f7b4`;
- repository CI accepted;
- latest Trigger-7 recovery-composition revalidation closes the six RCOMP probes with `NO_COUNTEREXAMPLE` at repository-executable scope;
- exact target run `33534368852` remains queued/nonterminal with zero executed steps and no assigned runner;
- previous target runtime is historical-only after required semantic repair;
- current target-environment component runtime credit remains zero.

### WP720 G1

- repaired current subject: `470f6c9509fb5ab32f706b2ee52896073b1180b6`;
- repository CI accepted with PFD6/PFD7 and authoritative Cortex regressions green;
- exact target run `33537350533` remains queued/nonterminal with zero executed steps and no assigned runner;
- duplicate dispatch is forbidden;
- current target-environment component runtime credit remains zero.

## Shared queue finding

The queued jobs do **not** justify an assumption that `clay-host` is globally offline.

A newer positive control exists:

- WP900 G5 run `33537844682` / job `99956441562`;
- runner `vps-clay-host`;
- target `clay-direct-dev`;
- result PASS at its bounded runtime-bound whole-persistent-loop scope.

Therefore current WP715/WP720 queue evidence is best classified as:

`UNKNOWN_NONTERMINAL_SHARED_QUEUE_OR_CAPACITY_PRESSURE`

not as product failure and not as proven runner outage.

The correct action is to preserve the existing exact queued runs, consume their first terminal evidence, and use the existing runner-evidence lane if control-plane starvation persists. Do not redispatch merely to test availability.

## System-slice transition law for next reentry

If both WP715 G3 and WP720 G1 become terminal with exact-subject execution and no new required semantic repair, immediately prefer one composition/runtime-credit boundary over any new small Voice component.

The first nonphysical VPS discriminator should reuse the existing local voice contract and prove, at the lowest safe faithful S1/S2/S3 tier:

1. outbound network blocked before session start;
2. no external model/API inference contributes;
3. German input traverses ASR into the existing Packet Cortex / cognition / tool / state surface;
4. Presence/Turn Policy remains single-authority and causal;
5. barge-in cancels generation plus unheard queued output without duplicate assistant turn;
6. TTS/output feeds correct heard/commit state;
7. tool result re-enters the same conversation lineage;
8. recovery and restart preserve the same durable canonical state lineage;
9. end-intent + bilateral-silence policy terminates correctly;
10. exact source/model/runtime identities plus latency/resource evidence are recorded.

This is the already-required product acceptance shape, not a new voice architecture.

## S4 fence

Do **not** move normal development to the local workstation. Defer only irreducibly physical evidence:

- real microphone/speaker;
- OS audio permissions;
- actual device enumeration;
- desktop/session permissions;
- real workstation install/upgrade/reboot persistence;
- physical perception;
- final one-handoff installer acceptance.

## Current source-watch result

The 2026 full-duplex literature does not justify a pivot before composition evidence. In particular, cascaded full-duplex/micro-turn work supports extracting more natural overlap/turn-taking from a modular streaming ASR-LLM-TTS architecture while retaining strong text cognition. Native speech-to-speech remains a useful counterhypothesis but would introduce a larger integration/authority change and must win on measured German/tool/state evidence before displacing the current path.

Decision: **NO ARCHITECTURE PIVOT / NO NEW SMALL VOICE COMPONENT.**

## Credit boundary

Still zero here for:

- WP715 current-subject target runtime;
- WP720 current-subject target runtime;
- whole Voice E2E;
- physical audio/device acceptance;
- semantic GWT/J-Space;
- effects;
- training;
- whole product.

## Next exact action

Re-enter exact runs `33534368852` and `33537350533`. On terminal results, bind executed steps/subject/receipt and classify them correctly. If both close without a required semantic successor, transition immediately to one network-off VPS system-slice discriminator using the existing Local Voice Runtime Contract; do not reopen adjacent Voice-component breadth.
