# F2-WP-902 G3 — Exact-source host measurement producer

## Scope

Generation 3 adds the missing producer boundary beneath the already accepted WP902 characterization admission/summary ABI. It can create one `CharacterizationSample` candidate from one measured, named Python operation while binding the sample to exact source bytes, a concrete WP900 `WholePersistentLoopSeal`, observed host/runtime facts, metric schema, operation source and quality-scorer source.

This is **not** a target-runtime acceptance mechanism. Repository CI can establish only that the producer obeys this contract. A GitHub-hosted sample is a sample from that runner, not evidence about the canonical local-user-machine baseline.

## Evidence chain

```text
exact repo-relative source paths
  -> read exact bytes
  -> per-file SHA-256
  -> SourceBundleEvidence SHA-256

observed non-secret host/runtime facts
  -> HostEnvironmentEvidence SHA-256

concrete WholePersistentLoopSeal
  -> seal.sha256()

named source-bound operation
  + named source-bound quality scorer
  + perf_counter_ns latency
  + process high-water RSS
  + source/environment/seal recheck
  -> CharacterizationSample

matched CharacterizationSample family
  -> accepted G2 characterize_measurements(...)
  -> deterministic CharacterizationReport
```

## Fail-closed boundaries

The producer rejects:

- absolute, parent-traversing, non-normalized or symlink source paths;
- missing/duplicate source paths;
- an operation or quality scorer whose source file is outside the bound source bundle;
- lambdas/local functions without stable module-level source identity;
- source bytes changing during a trial;
- host-environment fingerprint changing during a trial;
- whole-loop seal digest changing during a trial;
- a backwards monotonic-clock observation;
- unsupported peak-RSS platform semantics;
- quality outputs outside integer micros `[0, 1_000_000]`.

The source bundle is an **explicit measured file set**, not a claim of complete transitive dependency closure. A real promotion run must choose the release/source subject deliberately and preserve that identity in its run package.

## RSS semantics

`ru_maxrss` is process high-water RSS, not interval-only allocation. Linux reports KiB and is converted to bytes; macOS reports bytes. Unsupported platform semantics fail closed. Comparable performance characterization should therefore use isolated/fresh process trials or another separately specified measurement protocol rather than pretending repeated in-process high-water marks are independent peak-memory samples.

## Quality semantics

The producer does not define what product quality means. It requires a stable module-level quality scorer whose own source bytes are bound into the same source bundle and whose result is integer micros. The scorer is measurement logic, not truth authority.

## Promotion gate after repository acceptance

No latency, RSS, quality or whole-system claim is promoted from repository CI alone. The next gate is:

1. freeze one exact source/release subject;
2. bind one accepted WP900 whole-loop seal identity;
3. run repeated matched trials on the canonical local-user-machine baseline or an explicitly authorized development host;
4. preserve immutable run-package provenance and environment evidence;
5. admit only homogeneous samples through WP902 G2;
6. compare repeated trials before making any performance/quality statement.

All runtime, physical GRID10, semantic GWT/J-Space, provider/model, real-effect, completion, training and whole-system acceptance credits remain zero until their separately scoped executable gates pass.
