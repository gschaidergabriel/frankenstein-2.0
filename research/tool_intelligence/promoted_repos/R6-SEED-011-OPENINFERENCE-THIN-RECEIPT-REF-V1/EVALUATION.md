# R6-SEED-011 — OpenInference thin receipt-reference projection

Status: **E5 BUILD CANDIDATE ONLY**. Trigger-4 is required for any E6 acceptance.

## Decision

Do **not** import OpenInference wholesale for the current F2 need. Distill only a small observer-side pattern: immutable canonical F2 receipt reference + SHA-256 + minimal query fields are projected one-way into OpenInference-compatible evaluator/span metadata. Observer trace/span IDs remain correlation metadata and never replace F2 causal identity.

## Evidence

- E2 source mapping pinned `Arize-ai/openinference@d773c1ac1c7bcfef565e6280932af68d388531e7` and identified post-hoc evaluator links, typed annotator provenance, privacy masking and observer-ID limitations.
- E3 deterministic fixture: 30/30 invariants passed for source immutability, exact F2 identity preservation, privacy allowlisting, observer-disabled no-op and fail-closed malformed/authority inputs.
- E4 full-field JSON projection was overbuilt: 1635 B vs 986 B native; p50 26.573 us vs 11.281 us native.
- E4 thin-ref JSON projection: 907 B; p50 9.474 us; preserved receipt ref/digest and authority/privacy invariants.
- E4 local OpenTelemetry 1.42.1 -> OTLP protobuf: thin 1018 B vs full 1674 B; build+encode p50 62.440 us vs 83.398 us.

These measurements are local component experiments only. They do not cover collector, network, storage, exporter, VPS, physical GRID10 or full F2 runtime behavior.

## Net assessment

The thin structural distillation has enough evidence for a bounded Trigger-4 build/test candidate. Full-field projection and wholesale framework adoption are demoted. The build candidate should live in the telemetry/observer layer, remain disabled or optional until measured, and create zero reverse authority into UnifiedDB, GWT, effects or completion.

## Evidence ceiling

`E5_BUILD_CANDIDATE`; runtime, GWT causal, J-Space, effect, completion and whole-system credit remain zero.
