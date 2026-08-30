# F2-WP-716 — VPS Multimodal Empirical Lab Policy

Status: OWNER-DIRECTED SUPPORTING WORKPACKAGE

This document narrows the owner request for the multimodal research lab. It does **not** replace `PERCEPTION_FABRIC_PHASE.json`, WP715 ownership, or the final physical-host acceptance law.

## Authority / location

The empirical media-research loop runs on the **VPS first**. The local owner machine is not required for file-based image/video/audio research. Local camera/microphone/speaker binding remains a later physical-host acceptance step.

## Owner-authorized VPS capabilities

Workers may, for the purpose of Retina/Perception/Voice/Cortex empirical testing:

- download public image, video, and audio media over HTTP(S);
- resolve supported public media pages to a direct media URL with `yt-dlp` when available;
- generate synthetic images, videos, tones, speech and dialogue fixtures locally;
- use already-authorized model/provider routes to create test prompts, dialogue phrases, answers, scene descriptions, media-generation prompts, adversarial variants and annotations;
- decode/transcode/sample media with local tools such as ffmpeg/ffprobe/sox;
- replay the resulting media into the accepted Retina/Perception/Voice test interfaces;
- derive frames, ROIs, clips, spectrograms, transcripts, optical-flow/depth/tracking/event/causal fixtures and other bounded research derivatives;
- delete/recreate disposable media as needed.

Together remains forbidden. Existing provider admission rules remain authoritative. This workpackage grants no new secret, canonical-truth, effect, training, or whole-system authority.

## Storage law — HARD

All disposable research media MUST live under the shared media-lab store implemented by:

`src/frankenstein2/media_lab_store.py`

Default root:

`~/.cache/frankenstein2/media_lab`

Hard rules:

1. Aggregate media + in-flight temp media MUST NOT exceed **10 GiB**.
2. Default hard cap is exactly `10 * 1024^3` bytes and code refuses configuration above it.
3. At >95% occupancy the store evicts least-recently-used unleased media toward an 8 GiB low-water mark.
4. Unleased media older than 72 hours is deleted by age GC by default.
5. A periodic janitor SHOULD run every 15 minutes.
6. Workers must acquire a short lease for media that must survive a running experiment; leases expire automatically.
7. Binaries/media MUST NOT be committed to Git merely to preserve a test. Persist hashes, provenance, manifests, metrics and receipts instead.
8. Duplicate content is content-addressed by SHA-256 and reused instead of stored twice.
9. If active leases leave insufficient space, new acquisition fails closed rather than crossing the cap.
10. Download redirects are revalidated and non-public/private/loopback/link-local targets are rejected. This media route is not an SSRF/internal-network fetch capability.

Environment knobs may reduce storage or age, never increase the hard maximum beyond 10 GiB:

```bash
export F2_MEDIA_LAB_ROOT="$HOME/.cache/frankenstein2/media_lab"
export F2_MEDIA_LAB_MAX_BYTES=10737418240
export F2_MEDIA_LAB_LOW_WATER_BYTES=8589934592
export F2_MEDIA_LAB_MAX_AGE_HOURS=72
```

## Worker CLI

```bash
export PYTHONPATH="$PWD/src"

python3 -m frankenstein2.media_lab_store status
python3 -m frankenstein2.media_lab_store gc --aggressive

# Direct public media URL
python3 -m frankenstein2.media_lab_store fetch 'https://example.org/example.webm'

# Public page supported by yt-dlp: resolve to one direct combined A/V URL,
# then stream it through the same hard-capped downloader.
python3 -m frankenstein2.media_lab_store fetch-ytdlp 'https://…'

# Existing/generated local media
python3 -m frankenstein2.media_lab_store ingest /tmp/generated_scene.mp4

# Deterministic local fixtures
python3 -m frankenstein2.media_lab_store tone --frequency 997 --seconds 1
python3 -m frankenstein2.media_lab_store speech 'Frankenstein, was siehst du gerade?' --voice de
python3 -m frankenstein2.media_lab_store generate image --size 1280x720
python3 -m frankenstein2.media_lab_store generate video --seconds 5 --size 1280x720 --fps 24
```

Every accepted asset returns at least a stable SHA-256, path, size, media kind, source/provenance class and timestamps. Acquisition/ingest/deletion receipts are written separately from disposable media.

## Empirical research use

The lab is not limited to the two permanent real-world channels. Those channels are mandatory acceptance domains, while the VPS lab should maximize general visual/auditory competence through broad and adversarial experiments.

Recommended experiment families include:

- object detection, segmentation, tracking and re-identification within a continuous observation/session;
- partial/full occlusion and object permanence;
- camera motion vs object motion;
- depth, geometry, support, containment, contact and topology;
- rigid/deformable/liquid/smoke/cloth/rope dynamics;
- temporal order, missing frames, reversed clips and speed changes;
- event extraction, causal hypotheses, counterfactual prediction and causal confounders;
- shadows, reflections, mirrors, glass, screens, photographs and visual illusions;
- lighting/material disentanglement;
- audio/video synchronization, active-speaker binding, interruptions, overlap and background noise;
- generated dialogue variants, accents, pace, silence, room noise and TTS voices;
- normal vs anomalous long-horizon scenes;
- cross-dataset/OOD tests so permanent use cases do not become overfit shortcuts.

Research should compare ablations rather than merely add models. Persist measurements for detector/tracker/depth/flow/pose/event/causal/world-model combinations and reject changes that improve one fixture while degrading generalization or calibration.

## Evidence boundary

File replay, generated media and VPS experiments are valid empirical/component evidence when actually executed and receipted. They do **not** mint physical camera/microphone/speaker credit. The final local-host real-device/OS-permission gate remains separate.

`DOWNLOADED_MEDIA != LIVE_SENSOR`

`GENERATED_SPEECH != PHYSICAL_SPEAKER_TO_ROOM_TO_MIC`

`VPS_EXECUTION != PHYSICAL_HOST_ACCEPTANCE`

This separation is intentional: the VPS lab should make Retina/Voice extremely strong before the real hardware test, while the physical test remains an independent falsifier.
