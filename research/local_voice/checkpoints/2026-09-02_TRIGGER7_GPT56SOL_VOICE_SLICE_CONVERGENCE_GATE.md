# Trigger 7 — Voice-Slice Convergence Gate

Status: **PRECONDITION-GATED / SYSTEM-LEVEL NEXT / NO NEW SMALL VOICE COMPONENT**
Date: 2026-09-02
Trigger: `7` / `triggerword 7` / `triggerwort 7`
Role: Trigger-7 research/reentry/coordination checkpoint only. Trigger 4 retains F2 mutation and acceptance authority.

## Decision

The proposed Sandbox-First convergence direction is accepted **conditionally**:

> When the current exact WP720 and WP715 subjects have terminal executable evidence sufficient for their bounded scopes, do not reopen adjacent small Voice components by default. Promote the next work to one composed Voice-Slice discriminator on the VPS sandbox path.

WP903 is already terminal at its exact bounded S1 restart/crash-soak component-execution scope. WP720 and WP715 are not yet both terminal at the current repaired runtime subjects, so whole Voice-Slice acceptance must not be claimed prematurely.

This checkpoint does not create a new semantic experiment and does not steal the currently claimed Trigger-7 recovery-composition revalidation generation. It exists to prevent breadth-first component churn and to bind the next system-level gate.

## Live exact evidence observed during this Trigger-7 invocation

### WP903 — bounded soak closure exists

- accepted commit: `15775c386fcd6e64713d5a3246da5f0615e4a352`
- exact historical/runtime subject: `731db925df96ab7e49c0e5b80cd7bc8f4d37a086`
- S1 restart/crash soak: 30 iterations / 60 cases
- result: `EXECUTED_NO_COUNTEREXAMPLE`
- accepted only as exact-subject S1 component-execution evidence
- broad VPS/current-main invariance/physical/semantic/effect/training/completion/whole-system credit remains zero

Interpretation: sufficient as a bounded durability/soak dependency, not whole-voice proof.

### WP720 G1 — repaired integrated Presence/Turn policy, target runtime still nonterminal

Current repaired policy converged into the existing `VoicePacketCortex` authority rather than leaving a second standalone policy authority.

Repository evidence already recorded:

- repaired semantic subject: `470f6c9509fb5ab32f706b2ee52896073b1180b6`
- PFD6: PASS
- PFD7: PASS
- authoritative Cortex regressions: 24/24 PASS
- repository CI: PASS
- target-environment component runtime credit: 0
- singleton owner-VPS workflow run: `33537350533`
- job: `99954802244`
- observed state during this invocation: `QUEUED / NONTERMINAL`

Required fence: do not mutate policy semantics and do not redispatch while this exact promotion path remains nonterminal.

### WP715 G3 — recovery repair landed, prior runtime is historical-only

Current accepted repository-executable repair state:

- current source SHA: `68b1db374c86027be987c1fdc5e88ff13f11f7b4`
- repository CI run: `33534368751` PASS
- old runtime subject: `89414987f6eba3a38eaf69df87f1ae33b2f7ddf5`
- old runtime is valid only for its old exact subject
- classification: `RUNTIME_PROBE_INVALIDATED_BY_REQUIRED_REPAIR`
- current target-environment component runtime credit: 0
- full-duplex falsifier run: `33534368852`
- observed state during this invocation: `QUEUED / NONTERMINAL`

A new Trigger-7 semantic generation is already claimed for repaired recovery-composition revalidation:

- semantic key: `ec05977feabb70523bee9f6cf7cd99b0e83f80a4a34a6632f4ff8e2f9102f86f`
- objective: revalidate RCOMP1/RCOMP2 after Trigger-4 repair and classify Voice-Slice composition readiness

Required fence: do not duplicate that claim or its execution lane.

### WP900 G5 — system-level VPS evidence has already started to exist

A bounded owner-VPS `clay-direct-dev` runtime-bound whole-persistent-loop pass is reconciled:

- runtime subject: `6944ff1c9b0c99e29f5a6e38e62cb0824f60b481`
- controller run: `33537844682`
- job: `99956441562`
- runtime execution observed: true
- target: `clay-direct-dev`
- result: PASS

Scope remains bounded. Generic runtime, semantic GWT/J-Space, physical GRID10, effect, training, completion and whole-system credit remain zero.

Interpretation: system-level composition is no longer merely architectural prose; bounded whole-loop target-runtime evidence exists and should be reused rather than recreated.

## Trigger-7 source watch during this invocation

No source refresh justified reopening the architecture.

Relevant already-admitted measurement candidates remain:

1. `nvidia/nemotron-3.5-asr-streaming-0.6b`
   - 600M cache-aware streaming ASR
   - German `de-DE` is listed as transcription-ready
   - configurable streaming latency/chunking
   - use only as a measured ASR candidate; upstream claims grant no Frankenstein runtime credit

2. `Qwen/Qwen3-TTS-12Hz-0.6B-Base` / Qwen3-TTS family
   - German language support is explicit in current model configuration/source
   - upstream describes streaming TTS
   - remains a benchmark candidate; no upstream benchmark grants F2 runtime acceptance

3. `videosdk-live/NAMO-Turn-Detector-v1`
   - multilingual semantic turn-end detector with German support
   - already admitted/claimed in existing Trigger-7 history
   - therefore **no duplicate claim or new NAMO lane** is opened here

Source refresh reinforces measurement of the existing composition, not component proliferation.

## Next system-level Voice-Slice discriminator

Once WP720 and WP715 current exact-subject gates are terminal and nonnegative at their required bounded scopes, Trigger 4 should prefer **one** integration/runtime workpackage over new small Voice components.

Target composed path:

```text
pinned German audio / deterministic acoustic fixture
  -> local ASR
  -> Voice Packet Cortex
  -> Presence / Turn Policy
  -> Barge-in / cancellation
  -> Output / local TTS bytes
  -> Recovery
  -> durable persistent state
  -> process restart
  -> Reentry / causal readback
```

The VPS version intentionally substitutes deterministic prerecorded/fixture audio and an audio sink/file buffer for physical microphone/speaker hardware. That is valid S1/S2 evidence for all nonphysical semantics and timing that do not require real devices.

### Mandatory causal invariants

The composed discriminator should fail closed on at least:

1. **Turn identity preservation** — one causal turn/session identity survives ASR packetization, policy, output, recovery and reentry.
2. **Single policy decision** — one accepted HOLD/event cannot mint conflicting turn decisions.
3. **No stale HOLD** — a later final endpoint invalidates stale hold-policy projection.
4. **Barge-in correctness** — interruption cancels generation and unspoken/unheard output immediately enough to prevent false spoken-state commit.
5. **Output commit correctness** — `completed/heard` state cannot coexist with `commit_eligible=false` as an accepted projection.
6. **Tool/effect ownership continuity** — historical tool ownership cannot disappear in a way that permits duplicate issuance after restart.
7. **Recovery idempotence** — duplicate output/packet ids and corrupt queued heard-fraction states fail closed.
8. **Persistent-state continuity** — the exact durable state read after process restart causally descends from the pre-crash session state.
9. **Reentry causality** — resumed policy/voice behavior consumes the recovered state rather than merely loading a receipt-shaped file.
10. **Local-runtime boundary** — after required artifacts are staged, model inference runs with outbound ASR/TTS/model API calls blocked/zero.

### Fault-injection matrix

Prefer a compact high-information matrix over many new components:

- kill after ASR final before policy commit;
- kill after HOLD/FINAL decision before output scheduling;
- barge-in during queued TTS but before first audio byte;
- barge-in after partial audio/heard progress;
- kill after output completion before durable commit;
- kill after durable commit before acknowledgement/readback;
- remove active/cancelled tool projection while preserving history and verify replay rejection;
- duplicate packet/output ids across restart;
- stale HOLD followed by final endpoint across restart boundary;
- block network after local artifacts are staged and repeat the composed path.

### Metrics

Record from one trace clock/domain wherever possible:

- ASR final -> policy decision latency;
- endpoint -> first TTS byte latency;
- barge-in onset -> generation cancellation;
- barge-in onset -> output sink stop;
- restart -> recovered-session-ready latency;
- restart -> first causally valid reentry action;
- p50/p95/p99 where sample count is sufficient;
- exact CPU/RSS/GPU/VRAM and artifact identities when model execution is involved.

Do not collapse these to a fake scalar score.

## Promotion conditions

The system-slice build lane may open only after refreshing current event/claim heads and confirming:

- WP720 current repaired subject has terminal target/VPS evidence or an explicit new repair requirement;
- WP715 current repaired subject/revalidation is terminal enough to remove the known recovery blocker or identify the exact remaining repair;
- WP903 bounded soak closure remains valid for the reused exact dependency scope;
- no existing worker already owns the same semantic system-integration boundary;
- the composed discriminator reuses existing accepted source authorities rather than creating parallel Cortex/policy/recovery/state authorities.

If either WP720 or WP715 produces `PRODUCT_NEGATIVE`, repair that exact boundary first and invalidate only the affected runtime subject. If the blocker is `INFRA_AUTH_TRANSPORT_QUOTA` or queued/nonterminal execution, do not redesign the Voice architecture from that failure.

## Sandbox ladder for this Voice-Slice

### S1 — execute first

Use disposable Ubuntu OCI for:

- prerecorded German WAV / packet corpus;
- local ASR execution where dependencies fit;
- Packet Cortex + Presence/Turn policy;
- synthetic barge-in timing;
- local TTS byte generation / null or file sink;
- recovery/state corruption/crash/fuzz;
- process restart/reentry;
- outbound-network-blocked inference after artifact staging.

### S2 — use when service/session/filesystem fidelity matters

Use systemd-nspawn for:

- service lifecycle;
- users/groups/permissions that are representable without a real desktop device session;
- installer/service activation behavior;
- filesystem ownership and durable-state placement;
- user-service restart semantics.

### S3 — only for separate-kernel properties

Use VM/separate kernel for:

- true guest reboot tests;
- kernel/module behavior;
- virtual device or kernel-level audio stack conditions that cannot safely/fidelity-correctly run in S1/S2.

### S4 — defer only irreducible physical properties

Do not move to the physical local workstation merely because it is the eventual install target.

S4 remains required specifically for:

- real microphone capture;
- real loudspeaker playback/acoustic loop;
- native OS audio permissions;
- actual device enumeration/hotplug;
- real desktop/session rights;
- local persistence across real install/upgrade/reboot;
- physical perception/device interaction;
- final one-handoff installer acceptance.

A pass on S1/S2/S3 must never be relabeled as S4 evidence.

## Explicit zero-credit boundaries of this checkpoint

This checkpoint itself grants zero new credit for:

- WP720 target runtime
- WP715 current-subject target runtime
- acoustic microphone/speaker runtime
- ASR runtime
- TTS runtime
- semantic GWT/J-Space
- effects
- training
- composed Voice-Slice E2E
- physical host
- one-handoff completion
- whole-system acceptance

## Next exact action

1. Consume the already-owned Trigger-7 repaired RCOMP revalidation when it lands; do not duplicate it.
2. Consume terminal state of WP720 run `33537350533` and WP715 run `33534368852`; do not redispatch while nonterminal.
3. If both boundaries are nonnegative/current after reconciliation, route **one composed Voice-Slice S1/S2 discriminator** to Trigger 4 using the path and invariant matrix above.
4. If either produces executable counterevidence, repair only that exact boundary and then re-enter this convergence gate.
5. Keep S4 reserved for the exact irreducible physical acceptance list above.

This is the current highest-value convergence direction. More small Voice components are not the default next move.