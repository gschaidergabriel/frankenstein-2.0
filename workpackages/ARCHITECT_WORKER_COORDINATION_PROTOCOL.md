# Architect Worker Coordination Protocol v1

Status: **NONCANONICAL COORDINATION PLANE**

Purpose: let the persistent Architect steer one temporary worker organ, one exact claim/generation, one worker lane, or a bounded research cohort without creating a second project truth, delivery authority, mutation authority, runtime authority, or effect authority.

## 1. Authority invariant

```text
OWNER / PROJECT AUTHORITY
> EVENT + ACTIVE POINTER + RECONCILIATION AUTHORITY
> EXACT EXECUTABLE EVIDENCE
> ARCHITECT COORDINATION PACKET
> PROJECTION / CACHE / CHAT MEMORY
```

An Architect packet may change attention, research focus, requested checks, context selection, stop/defer guidance, output format, or falsifier priority.

It MUST NOT by itself:

- create or transfer workpackage mutation authority;
- mint a generation or claim;
- override an active pointer or terminal reconciliation;
- dispatch or duplicate a runtime probe;
- mint runtime/product/training/effect credit;
- authorize a provider, secret, effect, or host mutation;
- reactivate the old autonomous Free-Swarm;
- turn worker count, consensus, or model confidence into evidence.

## 2. Reuse existing Clay delivery atomicity

Do **not** invent a second delivery state machine.

The current research source `research_entity/coordination/live_reentry_delivery_atomicity.py` in `gschaidergabriel/clay-global-research-entity` already defines deterministic `route_id(...)`, versioned claim/CAS checks, `UNKNOWN_DELIVERY`, `DELIVERED_ACK_PENDING`, exact-marker finalization, and fail-closed recovery decisions.

F2's `tools/coordination/architect_packet.py` is therefore deliberately **stateless**. It validates packet identity, matches a packet against an already-resolved worker/claim context, and emits non-authoritative ACK evidence. Delivery ownership and retry remain under the existing Clay atomicity primitive plus current repository CAS rules.

## 3. Storage

Packets are immutable append-only files:

```text
coordination/architect_packets/pending/<packet_id>.json
```

Acknowledgements are separate immutable files:

```text
coordination/architect_packets/acks/<packet_id>/<worker_id>.<ack_id>.json
```

A packet is never edited in place to mark it consumed. New instructions use `supersedes_packet_ids`.

These paths are coordination/evidence support only. They are not canonical product state.

## 4. Worker reentry order

A worker consumes coordination only after current project authority is refreshed:

```text
REFRESH MAIN
-> RESOLVE CURRENT EVENT / CLAIM / ACTIVE POINTER / RECONCILIATION AUTHORITY
-> RESOLVE CURRENT WORKER / CLAIM / RUNTIME-SUBJECT IDENTITY
-> INSPECT ONLY MATCHING NON-EXPIRED ARCHITECT PACKETS
-> VERIFY PAYLOAD DIGEST + ROUTE ID + NONCE
-> ACK / REJECT DETERMINISTICALLY
-> APPLY ONLY IF COMPATIBLE WITH HIGHER AUTHORITY
-> CONTINUE NORMAL WORKER PROTOCOL
```

A packet cannot make stale authority current.

## 5. Packet envelope

Required v1 fields:

```json
{
  "schema": "F2_ARCHITECT_WORKER_PACKET/v1",
  "packet_id": "AWP-...",
  "route_id": "sha256...",
  "nonce": "...",
  "payload_digest": "sha256...",
  "issued_at": "RFC3339",
  "expires_at": "RFC3339",
  "architect_id": "persistent-architect",
  "project": "frankenstein-2.0",
  "priority": 50,
  "action_class": "COORDINATION_ONLY",
  "target": {"worker_id":"..."},
  "objective": "...",
  "constraints": [],
  "expected_output": {},
  "evidence_refs": [],
  "supersedes_packet_ids": [],
  "credit_authority": false,
  "mutation_authority": false,
  "runtime_dispatch_authority": false,
  "effect_authority": false
}
```

Optional bounded fields include `owner_intent_epoch` and `runtime_subject_fence`.

Allowed action classes:

```text
ACK_ONLY
STATUS
REVIEW_ONLY
CANDIDATE_FALSIFIER
COORDINATION_ONLY
CONTEXT_DELTA
RESEARCH_REQUEST
STOP_DEFER
```

`BUILD` is intentionally absent. A packet may recommend a build boundary, but canonical mutation must still be obtained through the normal workpackage/claim authority.

`STOP_DEFER` requests that the described non-authoritative activity not start/continue until re-evaluation. It cannot revoke higher authority by itself.

## 6. Payload and route identity

`payload_digest` is SHA-256 over canonical JSON containing the semantic instruction payload:

```text
objective
constraints
expected_output
evidence_refs
supersedes_packet_ids
runtime_subject_fence
owner_intent_epoch
```

`route_id` uses the same canonical identity shape as Clay's existing `route_id(...)` primitive:

```text
run_id         = packet_id
receiver       = canonical target JSON
message_kind   = ARCHITECT_COORDINATION_PACKET
decision       = action_class
payload_digest = exact packet payload_digest
```

Any payload or route tamper causes fail-closed rejection.

## 7. Target selectors

A packet may specify any subset of:

```text
worker_id
worker_lane
trigger
workpackage_id
generation
claim_id
runtime_subject_id
organ
```

Every selector present is conjunctive. Omitted selectors are wildcards. List-valued selectors match if at least one value equals the worker context value.

Examples:

### One exact worker

```json
{"worker_id":"T7-GPT56SOL-VOICE-03"}
```

### Trigger-7 reviewer cohort

```json
{"trigger":"7","worker_lane":["REVIEW_ONLY","CANDIDATE_FALSIFIER"]}
```

### Exact claim generation independent of temporary worker identity

```json
{
  "workpackage_id":"F2-WP-715",
  "generation":1,
  "claim_id":"F2-WP-715-G1-GPT56SOL-PACKET-CORTEX-CONVERGENCE-20260831"
}
```

A target with no selectors is invalid. There is no implicit global broadcast.

## 8. Deterministic disposition

Each packet/worker identity produces exactly one disposition:

```text
APPLIED
ACK_ONLY_DUPLICATE
REJECT_STALE
REJECT_MISADDRESSED
REJECT_SUPERSEDED
REJECT_AUTHORITY_CONFLICT
REJECT_SCHEMA_INVALID
```

Order:

1. schema/digest/route invalid -> `REJECT_SCHEMA_INVALID`;
2. `now >= expires_at` -> `REJECT_STALE`;
3. target mismatch -> `REJECT_MISADDRESSED`;
4. explicitly superseded -> `REJECT_SUPERSEDED`;
5. same nonce already classified by the same stable worker/claim identity -> `ACK_ONLY_DUPLICATE`;
6. action conflicts with owner/event/claim/runtime-subject authority -> `REJECT_AUTHORITY_CONFLICT`;
7. otherwise -> `APPLIED`.

ACK means **packet observed and classified**, not "instruction obeyed".

## 9. ACK envelope

```json
{
  "schema": "F2_ARCHITECT_WORKER_PACKET_ACK/v1",
  "ack_id": "AWA-...",
  "packet_id": "AWP-...",
  "route_id": "sha256...",
  "nonce": "...",
  "payload_digest": "sha256...",
  "worker_id": "...",
  "worker_lane": "...",
  "workpackage_id": "... or null",
  "generation": 1,
  "claim_id": "... or null",
  "observed_at": "RFC3339",
  "disposition": "APPLIED",
  "authority_head": "...",
  "event_head_ref": "... or null",
  "active_pointer_ref": "... or null",
  "reason": "bounded explanation",
  "context_bytes_injected": 0,
  "estimated_context_tokens_injected": 0,
  "new_mutation_authority": false,
  "new_runtime_dispatch": false,
  "new_effect_authority": false,
  "credit_delta": 0
}
```

ACKs never authorize mutation, runtime dispatch, effects, or credit.

## 10. Context-injection discipline

Packets carry only the delta needed to alter worker attention. Do not inject full project history.

Recommended packet budget:

```text
objective              <= 1 concise paragraph
constraints            <= 12 bounded clauses
expected_output         <= 8 fields
source/evidence refs    <= 16 exact refs
```

Workers report injected bytes and estimated tokens so packet-delta reentry can be compared against full-bootstrap reentry.

## 11. Fan-out fence

Creating/delivering a packet does not spawn work:

```text
PACKET_CREATED != WORKER_SPAWNED
PACKET_DELIVERED != NEW_GENERATION
PACKET_DELIVERED != RUNTIME_DISPATCH
PACKET_ACKED != PRODUCT_PROGRESS
```

A worker consumes packets during an already-admitted reentry/execution reason unless a separate current authority schedules that worker.

Broadcast packets must never create N new generations or N duplicate runtime dispatches.

## 12. Runtime-subject fence

For a bound/nonterminal runtime subject, a packet may request status/evidence review, non-mutating falsifier review, `DEFER_UNTIL_RUNTIME_RESULT`, or evidence-validity analysis.

It must not induce a semantic successor unless executable counterevidence independently requires repair or current authority proves subject invariance.

## 13. Failure attribution

Primary project failure taxonomy remains:

```text
PRODUCT_NEGATIVE
EVIDENCE_INVALID
INFRA_AUTH_TRANSPORT_QUOTA
CONCURRENCY_RETRY
UNKNOWN_NONTERMINAL
```

Coordination failures are secondary labels only:

```text
PACKET_STALE
PACKET_MISADDRESSED
PACKET_DUPLICATE
PACKET_SUPERSEDED
PACKET_AUTHORITY_CONFLICT
PACKET_SCHEMA_INVALID
PACKET_NOT_OBSERVED
UNKNOWN_DELIVERY
```

Infrastructure/coordination failure can never become `PRODUCT_NEGATIVE` without an executable product falsifier.

## 14. Research/improvement experiments

The Architect may run controlled worker-method experiments. Each requires:

```text
hypothesis
cohort / target selector
baseline
intervention
success metrics
stop condition
negative-result preservation
```

Initial experiments:

### E1 — Targeted context compression
Compare full-bootstrap reentry with packet-delta reentry for the same bounded review task.

Measure context bytes/tokens, time/tool calls to select the correct boundary, stale-projection mistakes, duplicate selection, and evidence-scope correctness.

### E2 — Stale-target rejection
Pin a packet to generation G, advance canonical work to G+1 before consumption, require rejection without mutation.

### E3 — Duplicate/idempotency
Present the same nonce/route twice; require one classification and one duplicate ACK, with no repeated dispatch/effect.

### E4 — Runtime-subject churn protection
Target a worker with a nonterminal exact runtime subject; packet must not induce successor mutation absent required repair/invariance.

### E5 — Failure-attribution preservation
Break transport/dependency around a valid discriminator; require infra/evidence classification, never product negative without execution.

### E6 — ACK completeness
Every observed packet terminates as applied/rejected/expired/unknown delivery; no silent disappearance.

### E7 — Worker-quality routing
Use historical worker metrics only as noncanonical routing features: scoped promotions per material work, duplicate avoidance, stale-probe churn, invalid-witness correction, failure-classification precision, context cost per useful closure.

## 15. Research topology

Default topology is centralized-selective:

```text
Architect
  -> exact worker / exact claim packet
  -> bounded cohort only when the task is genuinely parallel
  <- ACK + result + telemetry
  -> next targeted delta
```

Do not default to all-to-all communication. Preserve independent falsifier cohorts where useful to avoid central confirmation bias.

## 16. Security

Packets/ACKs must not contain provider tokens, passwords, private keys, or other secret material. They may reference an admitted secret boundary by name only.

## 17. v1 acceptance tests

At minimum:

1. exact worker packet matches only that worker;
2. exact claim packet matches any temporary worker on that exact claim;
3. omitted selector is wildcard but empty target is invalid;
4. expired packet fails closed;
5. duplicate nonce is idempotent;
6. misaddressed packet cannot alter worker action;
7. higher authority defeats conflicting packet;
8. payload/route tampering fails closed;
9. packet cannot create mutation/runtime/effect/credit authority;
10. ACK preserves packet/route/payload/worker/authority identity;
11. packet creation does not itself spawn work;
12. runtime-subject fence survives targeted steering.

## 18. Research basis and current project delta

Current Trigger-7 research in Clay commit `24e19ecdc9e3f8c45bb733a239290b929d36ba0d` independently converged on a noncanonical manager mailbox, deterministic route identity, TTL, nonce/idempotency, ACK semantics, no-fan-out law, and reuse of the existing Clay delivery atomicity helper.

External research supports selective orchestration, explicit task boundaries, tracing/observability, and adaptive agent counts rather than uncontrolled multi-agent fan-out. External sources are research evidence only; they do not outrank current F2 authority.

## 19. Rollout

1. Land protocol + stateless packet matcher/ACK helper.
2. Keep delivery ownership/CAS in the existing Clay atomicity primitive.
3. Add worker reentry hook only after current authority resolution.
4. Run adversarial tests for stale, duplicate, misaddressed, superseded, tampered and authority-conflict packets.
5. Run one bounded Trigger-7 REVIEW_ONLY cohort and one existing-authority build/runtime cohort.
6. Compare coordination quality/context overhead against baseline.
7. Promote only measured worker-method improvements; product/runtime/training/effect credit stays unchanged.
