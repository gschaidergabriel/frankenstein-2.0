# Trigger 7 — Qwen3-ASR target-probe re-entry

Date: 2026-08-30
Trigger: `7`
Status: ACTIVE_RESEARCH / EVIDENCE_DELTA
Scope: Trigger-7 local realtime voice research only; no Trigger-4 or whole-system acceptance is minted here.

## Exact observed identities

- Clay research main observed: `fb8210447e6538bf6e42f64a78460dae6891d85e`
- Frankenstein-2.0 main observed immediately before this write: `96b923a2a98e3d2ae2486a1c0012a9255e5d95aa`
- Controller repository: `gschaidergabriel/Dr.-Unterweger`
- Controller Trigger-7 rerun commit observed: `a1fa3222cec7081c4ce2af153b4831138041814a`
- Bound F2 Qwen3-ASR probe commit: `e0521522a49cd57ff86af9f49cc87f33ab6e22a3`
- Bound probe source: `research/local_voice/tools/t7_qwen3_asr_target_probe.py`

## Authority re-entry

The current Trigger-7 VPS/sandbox owner correction admits `clay-direct-dev` for local-model downloads, package installation, compilation, ASR/TTS/LLM experiments and benchmarks. FREE_ONLY constrains external provider/token spend; it does not prohibit owner VPS compute, the self-hosted runner, or local-model execution. Queue/source presence still does not create runtime credit.

## Current execution observations

### Qwen3-ASR target probe

- workflow run: `33292903286`
- job: `99207535776`
- workflow: `.github/workflows/trigger7-qwen3-asr-target-probe.yml`
- observed job state on this re-entry: `queued`
- conclusion: none
- assigned runner observed in GitHub job payload: none (`runner_id=0`, empty runner name at observation)
- persisted `runtime/trigger7_qwen3_asr_target_probe/LATEST.json`: absent at the observed controller head
- therefore: `execution_observed=false` for this run at this checkpoint and all model-load/inference/German-quality/streaming/E2E/Trigger-4/whole-system credits remain zero.

No duplicate Trigger-7 dispatch was issued in this re-entry.

### Corrected VPS hardware roundtrip

- workflow run: `33266856557`
- job: `99138324275`
- observed job state on this re-entry: `queued`
- conclusion: none
- no new clay-direct-dev hardware receipt was observed in this re-entry.

The older pre-repair run remains ineligible for clay-direct-dev hardware credit because its execution scope was wrong by construction.

## Qwen3-ASR exact source/pin audit

The bound probe uses:

- model: `Qwen/Qwen3-ASR-0.6B`
- model revision: `9ba1d4a`
- file: `model.safetensors`
- expected SHA-256: `79d6cbd4c98c7bbffe9db2edac07f56cd6637d0d5944b27f6c2b8353840323ea`
- package: `qwen-asr==0.0.6`
- API path: `Qwen3ASRModel.from_pretrained(...)` then `transcribe(..., language="German")`

Primary-source audit on 2026-08-30 found the pinned model-file revision/hash consistent with the public Qwen model source, package version `0.0.6` consistent with current Qwen3-ASR package metadata, and the probe API shape consistent with the official transformers example. This is `SOURCE_AUDIT`, not target-runtime execution evidence.

Primary references:

- https://huggingface.co/Qwen/Qwen3-ASR-0.6B/blob/main/model.safetensors
- https://huggingface.co/Qwen/Qwen3-ASR-0.6B
- https://github.com/QwenLM/Qwen3-ASR/blob/main/pyproject.toml
- https://github.com/QwenLM/Qwen3-ASR/blob/main/examples/example_qwen3_asr_transformers.py

## New source-level risk: timeout envelope

`SOURCE_RISK`, not an observed runtime failure:

The controller workflow has `timeout-minutes: 30`. The bound Python probe can independently spend up to roughly:

- venv creation: 120 s
- dependency install: 900 s
- child probe: 1200 s

That is 2220 s / 37 minutes before clone/workflow overhead. Therefore the hard outer workflow timeout is shorter than the probe's declared slow-path timeout envelope. If the Actions job is hard-terminated while the probe step is running, the later `if: always()` receipt-persistence step is not guaranteed to produce the intended fail-closed receipt.

This does not prove that the current queued run will time out. It is a design-level evidence-loss risk that should be repaired before a retry if an actual timeout/no-receipt outcome occurs.

## Credit boundary

At this checkpoint:

- target Qwen3-ASR artifact hash verification: `0` runtime credit (run not executed)
- target model load: `0`
- target local ASR inference: `0`
- German ASR quality: `0`
- streaming ASR: `0`
- German end-to-end voice: `0`
- Trigger-4 acceptance: `0`
- whole-system acceptance: `0`

Even a successful bound probe can establish only exact artifact/load/local-inference component evidence; the probe itself intentionally awards no German-quality, streaming, E2E, Trigger-4 or whole-system credit.

## Next exact re-entry gate

1. Re-read run `33292903286`, job `99207535776`, and the controller `LATEST.json` receipt path before any new dispatch.
2. Re-read corrected hardware run `33266856557` and accept only a clay-direct-dev-scoped hardware receipt.
3. If the Qwen run completes, inspect the exact persisted receipt and promote only its declared component scope.
4. If it remains queued with no assigned runner, diagnose the concrete self-hosted-runner/bridge control-plane state rather than creating another model experiment.
5. If it terminates by timeout or without a receipt, repair the outer/inner timeout and fail-closed receipt envelope before retrying.
6. Only after real target model-load/inference evidence proceed to identical German audio quality/streaming comparisons and later German E2E voice work.

Evidence laws retained:

`SOURCE_PIN != LOCAL_RUN`

`QUEUE_STATE != EXECUTION_EVIDENCE`

`LOCAL_COMPONENT_RUN != GERMAN_E2E_PASS`

`TRIGGER7 != TRIGGER4_ACCEPTANCE`
