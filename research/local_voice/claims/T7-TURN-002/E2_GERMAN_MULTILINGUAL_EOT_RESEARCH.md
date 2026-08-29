# T7-TURN-002 — German multilingual end-of-turn research delta

Date: 2026-08-30
Trigger: 7
Worker: GPT-5.6-Sol-TRIGGER7
Evidence ceiling: SOURCE/RESEARCH ONLY

## Why this lane exists

The current Frankenstein 2.0 voice frontier already contains a two-channel audio endpointing lane, but its German behavior is not established. This delta adds a German-specific, reproducible EOT benchmark path instead of inferring German quality from English endpointing evidence.

## Source-pinned benchmark

- Repository: `livekit/eot-bench`
- Revision: `6594d8b3b8af385b15f116dde310ce45af92d646`
- Upstream scope: real human-to-agent conversations across 14 languages, including German; silence pauses >=100 ms are annotated, with final pause as true EOT and earlier pauses as mid-turn hesitations.
- Evaluation shape: latency/false-cutoff Pareto trade-off rather than one scalar accuracy score.
- Upstream repository/data licensing is reported as Apache-2.0; the detector model itself has a separate LiveKit Model License and must be reviewed independently before product adoption.

## Local challenger

The open-weight LiveKit multilingual text turn detector is a useful CPU-local challenger because German is explicit, the model is exported as INT8 ONNX, and current upstream documentation reports approximately 50–160 ms inference per turn and <500 MB RAM. Upstream German TPR/TNR are reported as 99.3% / 87.8%.

These are upstream measurements only. They grant zero Frankenstein runtime or quality credit.

## TurnBench methodological correction

TurnBench (arXiv:2608.25218, 2026-08-25) reports that interruption false positives vary strongly by interaction style and concentrate in backchannel-dense dialogue. Its released benchmark is not a German production gate for Frankenstein, but it changes the test design: the German suite should explicitly contain backchannels, self-corrections, hesitations, mid-sentence pauses, short acknowledgements, and smooth floor transfers instead of only clean read speech.

## Nemotron negative evidence

An upstream Hugging Face discussion reports poor German terminology/spelling behavior for Nemotron 3.5 ASR Streaming 0.6B even at 1120 ms context in one user's workload; NVIDIA recommends word boosting/context biasing or fine-tuning. This is anecdotal negative evidence, not a model-wide verdict. It strengthens the existing decision to keep Nemotron as a measured challenger and to compare it against Qwen3-ASR and the Whisper-family continuity baseline on identical German audio.

## Predeclared F2 experiment

When the target hardware receipt exists and local dependencies fit:

1. run the German slice of eot-bench through a silence/VAD baseline;
2. run the local multilingual turn detector with fixed German thresholding;
3. compare against the existing Trigger-7 endpointing candidate(s) using the same false-cutoff budgets;
4. add Frankenstein-specific German backchannel/self-correction fixtures inspired by TurnBench interaction-style findings;
5. record endpoint delay, false cutoffs, CPU time, RSS, and interaction with ASR partial timing;
6. do not award integration credit until the detector is exercised through the actual deterministic turn FSM and playback-cancellation path.

## Falsifier

Do not adopt the added detector if, on target hardware and German F2 audio, it fails to improve the latency/false-cutoff Pareto frontier enough to justify its resident memory/CPU cost, or if it destabilizes ASR/LLM/TTS tails under the whole-Frankenstein resident workload.

## Evidence boundary

No model or dataset was downloaded in this research write. No target runtime was observed by this document. No German quality, end-to-end voice, Trigger-4 acceptance, or whole-system credit is minted here.
