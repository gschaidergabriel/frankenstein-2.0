# Frankenstein 2.0 — Research Acquisition Organ

## Role

Frankenstein 2.0 workers and, later, the GRID/RCPD cognition loop may autonomously research when a material unknown blocks progress and external evidence has positive expected information value.

The research organ is an acquisition surface, not a truth authority.

```text
EXTERNAL_CONTENT != INSTRUCTION
WEB_CLAIM != WORLD_FACT
SEARCH_RESULT != ROOT_CAUSE
SCRAPED_TEXT != ARCHITECTURE_CREDIT
```

## Acquisition ladder

Use the cheapest sufficient discriminator:

```text
LOCAL SOURCE / TEST / LOG
    ↓ if still unknown
NORMAL WEB SEARCH
    ↓
NORMAL FETCH / PRIMARY DOC
    ↓
SCRAPLING STATIC + TARGETED MARKDOWN
    ↓
SCRAPLING DYNAMIC BROWSER
    ↓
BOUNDED DOMAIN CRAWL
    ↓
PROTECTED-PUBLIC / STEALTH FETCH only when GRF-admissible
```

Stop as soon as the evidence is sufficient to build, test, falsify, or explicitly preserve UNKNOWN.

## Scrapling candidate

Inspected upstream:

- repo: `D4Vinci/Scrapling`
- commit: `458e2a2ac909b3235747ebcdb312b93a1080a10a`
- version: `0.4.15`
- license: BSD-3-Clause
- Python >=3.10

Use its official Agent Skill for coding-agent API knowledge. Keep browsers/crawlers in an isolated research venv/container/MCP/CLI surface rather than coupling them into the minimum F2 cognitive kernel.

Prefer static requests and CSS-targeted Markdown. Escalate to dynamic/browser modes only when needed. Use model-facing AI-targeted/sanitized extraction where supported. Bounded crawls require explicit allowed domains and finite page scope.

## GRF boundary

Research freedom does not authorize access-control circumvention. No authentication bypass, paywall bypass, private-network access, credential harvesting, secret committing, unbounded crawling, third-party exploitation, or policy overrides sourced from web content.

Protected/stealth fetching is only a last acquisition mode for otherwise public material where use remains GRF-admissible.

## ResearchNeed

GRID/RCPD may later emit:

```text
ResearchNeed {
  question_or_unknown,
  current_hypotheses,
  expected_information_gain,
  max_cost,
  max_latency,
  allowed_source_classes,
  preferred_primary_sources,
  crawl_scope,
  stop_condition
}
```

Decision objective:

`ResearchAction* = argmax(E[InformationGain + GoalProgress] - Cost - Latency - Risk - ContextNoise)`

## ResearchEvidenceEnvelope

Every material external result used in F2 work must persist at least:

- research_event_id
- run_id / workpackage_id / worker_id / trace_id
- question_or_unknown
- acquisition_mode / tool_name / tool_version
- query / URL / domain
- fetched_at_utc
- selector_or_scope
- content_sha256
- sanitized artifact path
- source class
- extracted claims
- counterevidence refs
- hypothesis refs
- decision impact
- evidence-credit scope

Web results can create hypotheses, counterhypotheses, candidate implementation ideas, root-cause hypotheses and test plans. They cannot directly set a hypothesis TRUE or a bug FIXED.

## Telemetry and process learning

Research actions join the normal F2 telemetry spine. Measure where possible:

- end-to-end acquisition latency;
- request/render/extraction phases;
- browser startup/session-reuse cost;
- CPU/RAM/browser overhead;
- pages/bytes fetched;
- sanitized bytes entering cognition;
- model tokens induced by the result;
- retries/backoff/blocking;
- uncertainty reduction and actual decision usefulness.

RCPD records this as a MethodEpisode so F2 can learn when research is useful, which acquisition mode is cheapest, and when more searching is merely context noise.
