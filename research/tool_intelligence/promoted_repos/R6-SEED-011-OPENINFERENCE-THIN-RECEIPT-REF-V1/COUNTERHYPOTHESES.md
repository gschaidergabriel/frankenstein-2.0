# Counterhypotheses / rejection conditions

1. **Native receipts are enough.** Cross-tool trace compatibility may not improve any real F2 inspection/debug/evaluation task enough to justify another observer schema.
2. **Local microbenchmarks understate system cost.** Batch processors, exporters, collectors, network, storage and query backends may dominate the adapter savings.
3. **Convention churn.** Tracking OpenInference/OpenTelemetry semantic conventions may cost more than keeping a stable F2-native observer view.
4. **Link without information gain.** A post-hoc Span Link may be visually convenient but add no decision-relevant information beyond immutable receipt refs.
5. **Authority confusion.** Operators or code may accidentally treat observer trace/span IDs or missing sampled spans as canonical identity/negative evidence.
6. **Privacy regression.** Broad instrumentation defaults can expose prompt/output/tool/metadata content unless the F2 adapter remains positive-allowlist only.

## Falsifiers

Reject or disable the candidate if Trigger-4 shows no material inspection/query benefit over native receipts, if bounded overhead cannot be demonstrated, if full framework/provider instrumentation becomes necessary, if any reverse-write authority is introduced, or if privacy/UNKNOWN semantics cannot remain fail-closed.
