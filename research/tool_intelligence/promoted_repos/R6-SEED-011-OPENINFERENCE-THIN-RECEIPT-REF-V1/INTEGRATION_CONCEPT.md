# Integration concept — non-authoritative thin observer projection

## Intended boundary

```text
admitted immutable F2 receipt/runpackage
        |
        v
pure positive-allowlist projection
        |
        +--> receipt_ref + receipt_sha256 (primary correlation key)
        +--> minimal typed query index
        +--> optional OpenInference evaluator metadata
        +--> optional single post-hoc OTel Span Link
        |
        v
observer/export surface only
```

There is intentionally **no reverse arrow** to UnifiedDB, canonical causal identity, GRID/GWT state, EffectGate, completion, goals, memory or world truth.

## Minimal query index

Only include fields demonstrated useful for observer lookup and already present in admitted evidence, e.g. broadcast ID/generation, recipient cell, binding/uptake status, and explicit `causal_influence_claim=NOT_ESTABLISHED_BY_BINDING`. The immutable receipt ref+digest remains the way back to full evidence.

## Privacy

Use a positive export allowlist before sampling/export. Prompt/output/tool definitions, secrets and arbitrary metadata are absent by default. Upstream permissive capture defaults are not copied.

## Failure semantics

- telemetry missing because observer disabled/suppressed/sampled/dropped -> `UNKNOWN`, never event absence;
- malformed or ambiguous canonical receipt identity -> reject projection;
- observer ID mismatch -> observer correlation failure only, never canonical-state mutation;
- evaluator result -> judgment telemetry only, never fact/completion/effect authority.

## Trigger-4 job

Implement the smallest adapter compatible with the existing F2 telemetry spine, add repository-hosted deterministic tests, compare adapter-disabled/native vs thin adapter, and measure serialization plus end-to-end observer overhead. Keep the dependency optional if possible. Trigger-4 may reject the adapter if it provides no useful inspection/query gain.
