# Trigger 7 — T7-ASR-001 — Qwen3-ASR 0.6B German source audit

Date: 2026-08-30
Worker: GPT-5.6-Sol-TRIGGER7
Claim: `research/local_voice/claims/T7-ASR-001/E2_SOURCE_AUDIT_QWEN3_ASR_06B.json`
Evidence stage: **E2 SOURCE AUDIT ONLY**
Runtime credit: **0**
German F2 benchmark credit: **0**
Trigger-4 acceptance credit: **0**

## 1. Purpose

Resume the already-active T7-ASR-001 source-audit objective without duplicating the separately claimed T7-SYS-002 VPS hardware-inventory objective. The question is whether Qwen3-ASR-0.6B remains a high-value German-first local streaming ASR candidate and how its target benchmark should be ordered against NVIDIA Nemotron 3.5 ASR Streaming 0.6B and the donor Whisper baseline.

## 2. Qwen3-ASR-0.6B source observations

Primary model:
- Hugging Face: `Qwen/Qwen3-ASR-0.6B`
- license: Apache-2.0
- architecture/model type: `qwen3_asr`
- German is explicitly present in the supported-language configuration.
- official model family documentation describes unified offline/streaming inference.
- current official streaming path is vLLM-backed; therefore streaming deployment cost includes the vLLM/runtime dependency rather than only the model weights.
- observed model weight artifact: `model.safetensors`, approximately 1.88 GB.
- observed exact SHA-256 for that weight artifact: `79d6cbd4c98c7bbffe9db2edac07f56cd6637d0d5944b27f6c2b8353840323ea`.
- current Hugging Face UI exposed short revision marker `9ba1d4a` on the weight/config upload. The full revision was not resolved by the current web surface, so the artifact SHA-256 above is the exact immutable weight identity for future quarantine/download verification.

Security/dependency interpretation:
- weight transport is safetensors-based, which avoids pickle execution for the main weight file;
- the official Qwen ASR package/runtime and vLLM still require normal source/dependency pinning and sandbox review before evidence-bearing execution;
- no target execution or download was performed in this source-audit result.

## 3. Nemotron 3.5 comparator observations

Primary model:
- Hugging Face: `nvidia/nemotron-3.5-asr-streaming-0.6b`
- license: NVIDIA Open Model / `openmdw-1.1` as exposed by the current model page.
- German (`de-DE`) is classified by NVIDIA as transcription-ready.
- cache-aware streaming exposes right-context settings corresponding to 80, 160, 320, 560 and 1120 ms.
- NVIDIA's current model card reports upstream German WER on its evaluation set of approximately 9.81, 9.21, 8.83, 8.42 and 8.31 respectively for explicit language conditioning across those latency settings.
- these are **UPSTREAM_RESULT**, not F2 measurements.

Negative signal:
- Hugging Face discussion #11 reports poor German speech/terminology performance even at high lookahead. This is a **COMMUNITY_NEGATIVE_SIGNAL**, not an independent controlled F2 benchmark and not sufficient to reject the model.
- it is strong enough to remove any assumption that Nemotron should be the default German winner merely because its official card labels German transcription-ready.

## 4. Qwen3-ASR vs Nemotron — current research decision

The source frontier changes from an implicit "Nemotron first" ordering to a neutral falsification order:

1. `Qwen/Qwen3-ASR-0.6B` — compact official German-capable challenger, exact weight hash pinned above.
2. `nvidia/nemotron-3.5-asr-streaming-0.6b` — benchmark at 80/160/320/560 ms right-context on the same audio.
3. donor German Whisper/faster-whisper path — continuity baseline.
4. Qwen3-ASR-1.7B — only after the 0.6B result and whole-Frankenstein resident headroom are known, because quality gain must justify extra resident memory/compute.

No source-only evidence chooses a production winner.

## 5. Predeclared E3 discriminator

Once T7-SYS-002 produces the real `clay-direct-dev` hardware receipt, run all ASR candidates against identical German audio and record at minimum:

- WER/CER;
- partial transcript stability;
- endpoint -> stable final transcript latency;
- real-time factor / throughput;
- CPU/GPU/RAM/VRAM residency;
- numbers, names, dates, technical vocabulary and mixed German/English terms;
- room noise / far-field / own-speaker echo cases;
- outbound model/API counters = 0 for LOCAL-SOLO;
- exact model/source/runtime identities.

Nemotron must be swept across multiple right-context settings rather than represented by one number. The selection is Pareto-based: German accuracy + finalization latency + resource fit, not WER alone.

## 6. Hypothesis and counterhypothesis

Primary hypothesis:

`Qwen3-ASR-0.6B` will be the better first resident German ASR candidate for Frankenstein 2.0 if it matches or beats Nemotron/Whisper on room-audio error rate without materially worsening stable-final latency or resident resource pressure.

Counterhypothesis:

Nemotron's cache-aware RNNT streaming will provide materially lower and more stable finalization latency at comparable German error rate, making it the better realtime voice organ despite the current community German-quality complaint.

Falsifier:

Same hardware + same German corpus + same audio conditioning + exact pinned model/runtime identity + causal receipt. No model is promoted from source reputation.

## 7. Evidence boundary

```text
SOURCE_PIN != DOWNLOAD_RECEIPT
SOURCE_SUPPORTS_GERMAN != GOOD_F2_GERMAN
UPSTREAM_WER != F2_WER
COMMUNITY_COMPLAINT != REPRODUCED_FAILURE
SAFETENSORS_WEIGHT != AUDITED_RUNTIME_STACK
FAST_STREAMING != GOOD_TURN_TAKING
T7_E2 != TRIGGER4_ACCEPTANCE
```

Result: **T7-ASR-001 E2 source audit completed at source scope; E3 remains pending target execution.**
