# Trigger 7 — Voice-Slice Convergence Reentry

Date: 2026-09-02
Worker: GPT-5.6-Sol
Class: REVIEW_ONLY / RESEARCH_SYNTHESIS / TRIGGER4_HANDOFF_PREPARATION
Product mutation authority: NONE
Runtime credit minted here: 0
Whole-voice E2E credit minted here: 0
Whole-product credit minted here: 0

## Purpose

Validate the Architect hypothesis that, after the current packet/policy/recovery promotion debt closes, Trigger 7 should stop opening adjacent small voice components and instead converge the existing voice surfaces into one executable VPS-sandbox Voice Slice before S4 physical-local acceptance.

This delta is deliberately not a new component and not a duplicate runtime dispatch. It records the current decision boundary and a smallest coherent system-level discriminator for Trigger 4 to execute when the already-bound runtime subjects become terminal/current.

## Current event-first observations

Observed F2 main during this reentry: `5f2348a1243023a630c19437fced0bf04a63800c` (`trigger7: revalidate repaired recovery composition matrix`). Main is moving concurrently; granular WP evidence and exact workflow subjects outrank this snapshot.

### WP903

Status: closed at its declared bounded scope.

- Generation 1 is terminal/accepted for the exact-subject S1 restart/crash soak.
- 30 iterations / 60 test cases executed with no counterexample.
- This is bounded component execution evidence only; it does not mint broad target-environment, physical, whole-voice, GWT/J-Space, effect or whole-product credit.

Decision: do not rerun WP903 merely to create activity.

### WP720

Status: NOT cleanly closed at current target-runtime scope.

- Current repaired exact runtime subject: `f93ef63bfbf2a22a39ac72c5f97e43f793960c16`.
- Existing singleton workflow run: `33537350533` (`WP720 Integrated Policy Exact-Subject VPS`).
- Live observation during this reentry: workflow/job remains `queued`, no executed steps, no conclusion.

Classification: `UNKNOWN_NONTERMINAL / CONTROL_PLANE_ONLY`.

Decision: preserve the exact bound subject; no semantic successor, no duplicate dispatch.

### WP715

Status: NOT cleanly closed for the repaired current subject.

- Current repaired source subject recorded by WP715 G3: `68b1db374c86027be987c1fdc5e88ff13f11f7b4`.
- Historical runtime on the older subject remains historical-only after required RCOMP repair.
- Existing current-subject falsifier workflow: `33534368852` (`T4 Packet Cortex Full Duplex Falsifier`).
- Live observation during this reentry: workflow/job remains `queued`, no executed steps, no conclusion.

Classification: `RUNTIME_PROBE_INVALIDATED_BY_REQUIRED_REPAIR` for the old subject plus `UNKNOWN_NONTERMINAL` for the current queued discriminator.

Decision: preserve the repaired current subject and singleton ownership; no duplicate dispatch or packet-cortex semantic mutation.

## Architect hypothesis verdict

`DIRECTIONALLY_CONFIRMED / PRECONDITION_NOT_YET_MET`.

The correct convergence direction is now system-level, not breadth-first component production. However the statement “after WP720 + WP715 + WP903 are cleanly closed” is not yet true: WP903 is bounded-terminal, while WP720 and WP715 still have exact-subject nonterminal runs with zero executed steps.

Therefore the legal Trigger-7 move is:

1. freeze same-boundary component churn;
2. prepare one composed Voice-Slice discriminator around existing accepted/source-ready parts;
3. do not execute a promotion-bearing current-subject replacement while the singleton WP720/WP715 probes are nonterminal;
4. once those probes terminate, Trigger 4 refreshes event heads and either repairs a real PRODUCT_NEGATIVE or executes the composed Voice Slice on the still-current accepted subjects.

## Existing product surfaces to compose, not replace

Observed existing surfaces include:

- `src/frankenstein2/voice_contract.py` — VoiceIntent / VoiceSessionCapsule / VoiceOutcome causal ABI;
- `src/frankenstein2/voice_packet_cortex.py` — ASR partial/final packet ingress, endpoint/overlap/barge-in fields, WAIT/BACKCHANNEL/ANSWER/TOOL_USE/CLOSE, output playback/heard/commit invariants;
- `src/frankenstein2/voice_packet_cortex_recovery.py` — checkpoint/restart/reconnect reconstruction and fail-closed projection validation;
- `src/frankenstein2/presence_kernel.py` — fresh/stale/unknown/conflict presence readout;
- `src/frankenstein2/voice_heard_result_reentry.py` — fully-heard durable result and interrupted heard-prefix/reentry bindings;
- existing typed memory / persistence / whole-loop infrastructure in `src/frankenstein2/`;
- Trigger-7 ASR/TTS/model research remains candidate input/output substrate and does not become a second identity/state/effect authority.

The packet cortex already encodes the critical system invariant that only fully heard completed output is commit-eligible. Recovery and heard-result reentry already provide the seams needed for a composed crash/barge-in/reentry test. This argues for composition rather than another micro-component.

## Proposed Voice-Slice execution subject

Target causal path:

```text
PINNED LOCAL AUDIO FIXTURE / LOCAL ASR
  -> ASR partial/final VoiceInputPacket
  -> VoicePacketCortex
  -> fresh Presence readout + turn policy
  -> overlap / barge-in decision
  -> local response / VoiceOutputPacket segments
  -> local TTS / cancellable output transport
  -> cancellation + heard/unheard accounting
  -> checkpoint / crash / reconnect recovery
  -> durable heard-result/state persistence
  -> process restart + readback
  -> causal reentry into the next turn
```

No new authority is introduced. The composed harness must bind the same VoiceSessionCapsule lineage end-to-end and preserve exact subject/artifact identities.

## Smallest high-information VPS discriminator

Use the lowest safe faithful tier.

### S1 — deterministic composition / fault matrix

Use pinned German WAV/PCM fixtures and two-channel interruption fixtures; no physical microphone claim.

Required cases:

1. normal German turn: ASR final -> ANSWER -> fully heard output -> durable heard-result -> restart -> readback -> next-turn reentry;
2. mid-output user interruption: playback stops; heard prefix may enter ephemeral next-turn context; unheard tail MUST NOT become durable spoken memory/outcome;
3. zero/near-zero buffer barge-in onset: interruption authority must not wait for semantic endpoint completion before cancelling output;
4. WAIT/BACKCHANNEL path: no accidental final-answer commitment while user turn remains open;
5. stale/UNKNOWN/CONFLICT presence: fail closed according to current policy, never fabricate `PRESENT_INTERRUPTIBLE`;
6. crash while output is queued/started/heard-partial: recovery must terminalize/cancel unsafe output and must not promote it as completed/heard;
7. crash with unresolved tool reference: recovery must not blindly replay an unknown external effect;
8. duplicate/reordered ASR chunks: packet replay/ordering protections must preserve one causal turn;
9. process restart after completed heard result: persisted state/readback must reconstruct the same durable result without duplicate commit;
10. offline/network-blocked execution where local ASR/TTS/models are present: outbound model/ASR/TTS inference calls remain zero.

Measure at least: speech-end/endpoint to first-output, barge-in detection-to-playback-stop, ASR partial/final timing, first TTS audio timing, recovery duration, duplicate/replay count, committed-vs-heard consistency, CPU/RSS and model residency. Record p50/p95/p99 only when the sample count and clock source are explicit.

### S2 — Ubuntu service/user/lifecycle fidelity

Promote the same exact composed subject to systemd-nspawn when service/user/session/package/filesystem semantics matter. Exercise service restart, permission withdrawal inside the sandbox, persistent-state mount/bind semantics and installer-facing lifecycle without claiming real desktop/audio devices.

### S3 — separate-kernel only where needed

Use only for reboot/kernel/virtual-device/network-boundary behavior that S1/S2 cannot faithfully or safely establish. Do not move such testing to the owner's workstation merely for convenience.

## S4 irreducible physical-local gate

Defer only properties that VPS S1/S2/S3 cannot prove:

- real microphone capture path;
- real speaker playback and acoustic echo coupling/AEC behavior;
- actual device enumeration and hotplug;
- OS audio permissions and native desktop/session rights;
- real PipeWire/Pulse/ALSA device behavior where virtual devices are insufficient;
- durable local state across actual install/upgrade/reboot on the target workstation;
- physical perception sources;
- final one-handoff installer/agent flow on a clean real machine.

`S1/S2/S3 PASS != S4 PASS` remains explicit.

## External research check — implications only, no donor adoption

Primary/current findings sampled during this reentry:

- HumDial / HumDial-FDBench (ICASSP 2026) evaluates full-duplex interaction on dual-channel human conversations with interruptions, overlap and dynamic turn negotiation. This supports evaluating the composed F2 voice path as a system interaction problem rather than isolated ASR/TTS scores.
  - https://arxiv.org/abs/2604.21406
  - https://arxiv.org/abs/2601.05564
- DuplexOmni separates a continuously responsive interaction layer from an asynchronous thinking/tool layer. This is useful architectural counterevidence against forcing every acknowledgement/backchannel to wait on the strongest reasoning path; it is not evidence to replace F2 with DuplexOmni.
  - https://arxiv.org/abs/2606.09186
- Pipecat's current turn-management documentation separates VAD speech detection from semantic turn completion, and its interruption path clears pending text/audio when a user turn starts. This independently matches F2's separation of raw speech/endpoint policy and its `unheard output must not be committed` invariant.
  - https://docs.pipecat.ai/pipecat/learn/speech-input

## Promotion/failure law for the composed run

Before any repair:

- exact executed invariant falsified -> `PRODUCT_NEGATIVE`;
- wrong/stale subject, fake/partial/unbound receipt -> `EVIDENCE_INVALID`;
- queued/no-step/runner/auth/transport failure -> `UNKNOWN_NONTERMINAL` or `INFRA_AUTH_TRANSPORT_QUOTA`;
- state/claim race -> `CONCURRENCY_RETRY`.

Only a real product negative or a validity defect needed to make the discriminator executable justifies same-boundary mutation.

## Immediate routing decision

NOW:

- no new small Voice component;
- no duplicate WP720/WP715 runtime dispatch;
- consume the newly repaired Trigger-7 recovery-composition revalidation as research evidence only;
- maintain the composed Voice-Slice plan as the next integration shape.

WHEN WP720 AND WP715 TERMINATE:

1. refresh current F2 main and both event chains;
2. if either run is a real product negative, repair only that exact boundary and re-prove current subject;
3. if both close at scope and WP903 remains valid/invariant, route one Trigger-4 integration claim for the composed Voice Slice;
4. execute S1 then S2 as needed, S3 only for separate-kernel properties;
5. keep S4 strictly for the irreducible physical gates above.

## Explicit zero-credit boundary

This research synthesis grants zero:

- target-runtime Voice-Slice acceptance;
- acoustic ASR/TTS runtime acceptance;
- physical microphone/speaker/device credit;
- GWT/J-Space semantic uptake credit;
- external effect credit;
- whole-loop completion;
- whole-product acceptance;
- training credit.

Next exact gate: terminal evidence for the already-bound WP720 run `33537350533` and WP715 run `33534368852`, followed by event-first reentry and one nonduplicate composed Voice-Slice integration subject if the repaired boundaries remain current.