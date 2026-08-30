# F2-WP-716 — Multimodal Empirical Lab + Local Device Acceptance

Status: OWNER_AUTHORIZED / ISOLATED_NEW_WORKPACKAGE

## Goal
Build one reproducible research/test surface for Retina + Voice + Cortex that can use (a) downloaded/public test media, (b) owner-supplied local media, (c) controlled generated dialogue/audio, and (d) explicitly permissioned local camera/microphone/speaker hardware. The two permanent owner channels (outdoor/nature-area monitoring and desk/webcam interaction) are hard acceptance scenarios, not the architectural limit; experiments must optimize general perceptual competence and OOD transfer.

## Hard evidence law
- FILE_REPLAY != LIVE_DEVICE.
- SYNTHETIC_AUDIO != PHYSICAL_SPEAKER_TO_MIC_LOOPBACK.
- COMPONENT_PASS != WHOLE_SYSTEM_ACCEPTANCE.
- Every run emits exact subject/source/timestamp/config/permission digest and measured outputs.
- Raw camera/audio persistence is OFF unless the run manifest explicitly enables it.
- Permission revocation invalidates queued work fail-closed.
- No test may silently convert similarity into real-person identity. Person tracking/speaker binding is allowed; named identity must come from explicit authenticated/contextual assertion, not face/voice biometrics.

## Test modes
1. `IMAGE_REPLAY`: image -> Retina -> typed percept/world-state receipt.
2. `VIDEO_REPLAY`: decoded frames + source timestamps -> CaptureOwner-compatible replay -> Retina/Cortex/world model.
3. `AUDIO_REPLAY`: WAV/FLAC/decoded audio -> VAD/ASR/Voice Packet Cortex -> cognition receipt.
4. `AV_REPLAY`: synchronized video+audio -> speaker/gesture/event binding and temporal-causality tests.
5. `PHYSICAL_LOOPBACK`: controlled TTS/test tone -> selected speaker sink -> room -> selected microphone source -> VAD/ASR/Voice -> response -> speaker, with measured latency chain.
6. `LIVE_CAMERA`: explicitly permissioned camera -> CaptureOwner/Broker -> Retina.
7. `LIVE_DUPLEX`: live camera + microphone + speaker -> Retina + Voice + Cortex under one causal run id.

## Required experiment families
- object permanence / re-identification within a running scene without named biometric identity
- partial/full occlusion and reappearance
- camera motion vs object motion
- depth/geometry/parallax
- support/contact/containment
- fall/roll/slide/impact/deformation/liquid/lighting/material hypotheses
- temporal ordering, reversed clips, dropped/reordered frames
- cause/effect candidates + counter-hypotheses + UNKNOWN
- prediction/re-entry: predict next state then score against observation
- mirrors, shadows, screens, reflections, insects near lens, weather/vegetation hard negatives
- audio-only, visual-only and deliberately contradictory AV cases
- speech/visible-speaker binding, gesture/object reference, interruption/barge-in, turn-taking
- day/night/low-light/noise/codec/resolution/OOD perturbations

## Permanent-channel acceptance
### Channel A — nature-area/outdoor
Long-horizon baseline, low false-alarm rate, persistent tracks, zones, weather/light/vegetation hard negatives, rare-event retention, day/night robustness, state consistency across hours/days.

### Channel B — desk/webcam
Low latency, hands/objects/pose, audio-video synchronization, visible-speaker binding, gesture/reference resolution, interruption and conversation re-entry.

These are regression gates. New research must also maintain held-out general media performance so the system does not overfit to either channel.

## Capability manifest
Grant only explicit, revocable capabilities:
- CAMERA_SEE
- CAMERA_ANALYZE
- MICROPHONE_CAPTURE
- SPEAKER_PLAYBACK
- MEDIA_FILE_READ
- MEDIA_FILE_DECODE
- TEST_MEDIA_DOWNLOAD_PUBLIC
- AUDIO_SYNTHESIS_TEST
- RAW_RETENTION (default false)
- REMOTE_FRAME (default false)
- EXTERNAL_VLM (default false; requires separate owner/provider policy)

Never imply OS permission from repository configuration. Host binding must verify actual `/dev/video*`, PipeWire sources/sinks and desktop/portal permission state at execution time.

## Physical-loopback latency receipt
Capture at minimum:
- `t_speaker_emit`
- `t_mic_detect`
- `t_vad_open`
- `t_asr_final`
- `t_voice_packet_commit`
- `t_cortex_response`
- `t_tts_first_audio`
- `t_speaker_response`
- loopback confidence / SNR / clipping / selected sink/source

## Corpus policy
Workers may acquire diverse public/redistributable images, videos and audio for testing and may generate controlled phrases/dialogues with language models. Every acquired asset must have provenance, URL/source, hash, media metadata and permitted use recorded. Owner-supplied media is tagged separately. Do not treat generated/synthetic media as real-device evidence.

## Dialogue generation
Generate scenario packs, not random chatter. Each pack contains:
- setup/world state
- test utterance(s)
- expected observable event(s)
- expected semantic response constraints
- allowed UNKNOWN/ABSTAIN conditions
- interruption variants
- noise/reverb/distance variants
- AV contradiction variants
- deterministic seed/model/provider metadata

Examples include commands, questions about visible objects/events, deictic references ("das dort"), correction, interruption, delayed response, background speech and non-speech sounds.

## Evaluation vector
Do not collapse into one fake percentage. Record:
- detection/segmentation quality where labels exist
- track continuity and ID switches
- temporal ordering correctness
- spatial/depth error where ground truth exists
- physical consistency
- causal calibration / counterfactual accuracy
- prediction error
- uncertainty calibration / abstention
- AV sync and visible-speaker binding
- ASR/VAD/turn-taking latency and errors
- false alarms / missed events
- RAM/CPU/GPU/token cost
- raw-retention and permission-law compliance

## Acceptance sequence
G1: replay harness + deterministic receipts.
G2: diverse public/owner media corpus + adversarial experiment generator.
G3: Retina/Voice/Cortex adapters consume replay without architecture fork.
G4: physical speaker->room->mic loopback on owner host.
G5: live camera permission/capture on owner host.
G6: full live duplex AV causal run.
G7: sustained permanent-channel soak + held-out OOD regression.

Only G4-G7 can mint corresponding physical/local evidence, and only exact observed execution can be promoted.
