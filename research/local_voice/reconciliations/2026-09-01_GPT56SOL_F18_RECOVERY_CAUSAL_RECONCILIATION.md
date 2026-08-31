# Trigger 7 — F18 recovery causal reconciliation — 2026-09-01

Status: REVIEW_ONLY / EVIDENCE_RECONCILIATION
Claim: `research/local_voice/claims/2026-09-01_trigger7_gpt56sol_cortex_frontier_claim.json`
Binding authority: `research/local_voice/authority/2026-08-31_TRIGGER7_TEXT_PACKET_COMPLETION_AUTHORITY.md`
Observed F2 head before this reconciliation: `2ad62d5f949729d6987f575a7eb40419830b4c43`

## Reentry result

The previous Trigger-7 restart/reentry checkpoint identified F18, a checksum-valid but causally inconsistent closed checkpoint, as the highest-information open packet-cortex falsifier. Current granular F2 evidence supersedes that open-source assumption.

`F2-WP-715` generation 2 is now the sole active mutation/runtime owner for the F18 boundary. Its current pointer records:

- historical executable F18 negative evidence;
- repository repair source commit `c5956154fd38aab7094eb2c80abf99e2203437c0`;
- green repository-CI subject `71ddd9e5aa3791e5dcb1be37e276d5c3194f0adf`;
- `RUNTIME_SUBJECT_BOUND_AFTER_GREEN_REPOSITORY_CI__DEFER_SEMANTIC_CHURN`;
- target/VPS component runtime still unobserved.

Current `voice_packet_cortex_recovery.py` revalidates restored output-plan/action identity, terminal output state, stored `VoiceOutcome` identity, SESSION_CLOSE detail/ref relations and the reconstructed close snapshot instead of trusting the checkpoint digest alone. The recovery regression suite includes a checksum-recomputed but semantically inconsistent closed-checkpoint rejection.

The heard-result boundary is additionally guarded downstream by `voice_heard_result_reentry.py`, which binds the terminal `VoiceOutcome` result reference/hash to the completed heard-result subject before downstream re-entry. Therefore the earlier F18 research hypothesis is no longer an unimplemented source gap.

## Classification

F18 state at this reconciliation:

`HISTORICAL_PRODUCT_NEGATIVE -> REPAIRED_AT_REPOSITORY_SCOPE -> PENDING_TARGET_COMPONENT_RUNTIME`

This Trigger-7 worker MUST NOT mutate WP715 source/tests or create a second runtime dispatch while the exact G2 runtime subject is bound. Churn class: `DEFER_UNTIL_RUNTIME_RESULT`.

## External-source refresh

A fresh primary-source check on 2026-09-01 did not justify a new model/source claim. The current leading modular candidates remain already-pinned F2 research families: NVIDIA Nemotron 3.5 ASR Streaming 0.6B, Qwen3-ASR 0.6B/1.7B, and Qwen3-TTS 12Hz 0.6B. Full-duplex systems remain architecture/falsifier lanes unless they independently pass the German and integration gates. Existing source pins in `research/local_voice/sources/` already cover these families, so no duplicate source artifact is created in this cycle.

Primary refresh references used for this review:

- https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b
- https://huggingface.co/Qwen/Qwen3-ASR-0.6B-hf
- https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
- https://github.com/BayLing-Models/BayLing-Duplex
- https://arxiv.org/abs/2605.20755

## Credit fence

This reconciliation mints no new runtime/product credit.

- repository component credit: unchanged; owned by WP715/Trigger 4 evidence
- target/VPS packet-cortex runtime credit: 0 here
- acoustic credit: 0
- physical-device credit: 0
- GWT/J-Space runtime credit: 0
- effect credit: 0
- training credit: 0
- whole-product acceptance: false

## Next exact action

Do not open adjacent packet-cortex architecture. Resolve the already-bound WP715 G2 controller/VPS discriminator for exact subject `71ddd9e5aa3791e5dcb1be37e276d5c3194f0adf`. If it executes and passes, Trigger 4 may promote only the bounded repaired closed-checkpoint relation at target-component scope. If it fails, classify PRODUCT_NEGATIVE vs EVIDENCE_INVALID vs INFRA/AUTH/TRANSPORT/QUOTA before any repair. The next Trigger-7 invocation resumes from that terminal evidence rather than restarting F18 or repeating model scouting.
