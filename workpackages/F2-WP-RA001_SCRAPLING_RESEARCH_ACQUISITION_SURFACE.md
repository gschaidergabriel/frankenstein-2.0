# F2-WP-RA001 — Scrapling Research Acquisition Surface

State: NOT_STARTED
Priority: P1 enabling infrastructure

## Goal

Build a reproducible, bounded external research acquisition surface for Frankenstein 2.0 and Triggerword-4 workers using Scrapling as an optional escalation tool.

Canonical architecture: `architecture/RESEARCH_ACQUISITION_AND_SCRAPLING.md`

## Tasks

- [ ] Build isolated pinned Scrapling runtime (venv/container).
- [ ] Install or pin the official Scrapling Agent Skill for coding workers.
- [ ] Implement `ResearchNeed -> ResearchAcquisitionRequest`.
- [ ] Implement static, dynamic and bounded-crawl modes with cheapest-first routing.
- [ ] Keep stealth/protected-public mode explicit and last-resort.
- [ ] Persist `ResearchEvidenceEnvelope` with URL/query/timestamp/hash/selector/tool version/source class.
- [ ] Link research events to run/workpackage/worker/trace/hypothesis IDs.
- [ ] Persist research artifacts in the same immutable test-series package that caused the request.
- [ ] Connect results to hypothesis/counterhypothesis DB as candidate evidence only.
- [ ] Connect latency/resource/token/usefulness measurements to performance telemetry.
- [ ] Emit RCPD MethodEpisodes for research decisions.

## Required tests

- [ ] Static public doc -> sanitized Markdown + valid envelope.
- [ ] CSS targeting reduces context while preserving target evidence.
- [ ] Hidden/comment/template/zero-width injection fixture does not become model-facing instruction.
- [ ] JS fixture escalates static -> dynamic only when needed.
- [ ] Bounded crawl stays inside allowed domains and finite page cap.
- [ ] Auth/paywall/private-network attempt is rejected by the F2 adapter.
- [ ] Scraped text cannot mutate worker authority/workpackage/effect state.
- [ ] Duplicate identical content dedupes by stable hash.
- [ ] Changed source yields a new evidence version/hash.
- [ ] Research result cannot directly mark bug FIXED or hypothesis TRUE.

## Measurements

Measure static, dynamic, persistent-session and bounded-crawl modes where applicable:

- p50/p95/p99 acquisition latency;
- browser startup and session reuse delta;
- CPU/RSS/PSS/browser cost;
- bytes/pages fetched;
- sanitized bytes delivered to cognition;
- downstream model tokens;
- retry/backoff/block rate;
- usefulness / uncertainty reduction / decision impact.

## Acceptance

`ACCEPTED_AT_SCOPE` requires executed receipts for static + dynamic + bounded crawl, GRF/authority-boundary tests, archived latency/resource measurements, hypothesis/telemetry integration, and at least one recorded negative-result path.
