# Trigger 7 checkpoint — JoyAI-Talker German/full-duplex source triage

Date: 2026-09-01
Research ID: `T7-20260901-JOYAI-TALKER-GERMAN-TRIAGE`
Semantic key: `aed6fa8704df1a177ce727a459efe23833427855a9356f48a2777bdf9b1ffc03`
Evidence: `research/local_voice/evidence/2026-09-01_TRIGGER7_JOYAI_TALKER_GERMAN_SOURCE_TRIAGE.json`

## Result

JoyAI-Talker is retained as a high-value **architecture/full-duplex turn-control donor**, not promoted as a Frankenstein local-runtime candidate.

Primary-source observations:

- arXiv `2608.01119` v1 was submitted 2026-08-02;
- architecture is decoupled Duplex-Thinker-Talker;
- Thinker uses JoyAI-LLM Flash, 48.9B total sparse MoE / about 3.28B active parameters per input token;
- Joy-Duplex is a separate 1.7B decoder-only streaming controller using 160 ms input chunks and explicit interaction-state tokens;
- the paper reports strong interruption/background-speech behavior on Full-Duplex-Bench v1.5;
- the paper describes multilingual Talker training, but this triage found no German-specific benchmark/result;
- current official-project/Hugging-Face search in this cycle did not surface a pin-able JoyAI-Talker/Joy-Duplex code+weights release for local audit/execution.

Therefore:

`SOURCE_PINNED_TRIAGE = PASS`

`GERMAN_FIRST_ACCEPTANCE = NOT_ESTABLISHED`

`LOCAL_SELF_HOSTED_RUNNABLE = NOT_ESTABLISHED`

`TARGET_HARDWARE_FIT = UNKNOWN`

`F2_BUILD_CANDIDATE = 0`

`TRIGGER4_ACCEPTED = 0`

## Architecture relevance

The valuable transferable idea is the small/decoupled state-driven duplex gate, not an immediate replacement of Frankenstein's cognition with the full JoyAI Thinker. The explicit `partial/complete/backchannel/accept/reject` interaction vocabulary is a useful donor for comparison with Frankenstein's VoiceIntent, presence/interruptibility and cancellation boundaries.

## Next exact gate

Only reopen this semantic objective for executable promotion when an official/author-linked code+weights revision can be pinned with license and hashes. Then run a network-blocked German interruption/background/backchannel falsifier and resource-envelope measurement before routing anything to Trigger 4.

If no reproducible release appears, retain this as architecture-donor evidence only and spend no F2/VPS integration capacity on it.

## Concurrency note

This cycle intentionally did not duplicate the active VoicePacketCortex recovery/import-bound Trigger-7 claims and did not mutate Trigger-4-owned product code.
