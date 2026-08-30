# Architect Worker Coordination Protocol v1

Status: NONCANONICAL COORDINATION PLANE

This protocol gives the persistent Architect a precise way to steer one temporary worker organ, one claim/generation, one worker lane, or a bounded broadcast cohort without creating a second project truth or mutation authority.

## Prime invariant

```text
OWNER / PROJECT AUTHORITY
> EVENT + ACTIVE POINTER + RECONCILIATION AUTHORITY
> EXACT EXECUTABLE EVIDENCE
> ARCHITECT COORDINATION PACKET
> PROJECTION / CACHE / CHAT MEMORY
```

An Architect packet may change **attention, research focus, requested checks, context selection, stop/defer guidance, output format or falsifier priority**. It MUST NOT by itself:

- create or transfer workpackage mutation authority;
- mint a new generation/claim;
- override an active pointer or terminal reconciliation;
- dispatch a duplicate runtime probe;
- mint runtime/product/training/effect credit;
- reactivate the old autonomous Free-Swarm;
- authorize a provider, secret, effect or host mutation;
- turn worker count or consensus into evidence.

## Storage

Packets are immutable append-only files:

```text
coordination/architect_packets/pending/<packet_id>.json
```

Acknowledgements are separate immutable files:

```text
coordination/architect_packets/acks/<packet_id>/<worker_id>.<ack_id>.json
```

A packet is never edited in place to mark it consumed. Newer instructions use `supersedes_packet_ids`.

The directories are coordination/evidence support only. They are not canonical product state.

## Required reentry order

Workers consume packets only after current authority is resolved:

```text
REFRESH MAIN
-> RESOLVE EVENT HEAD / ACTIVE POINTER / RECONCILIATION
-> RESOLVE CURRENT WORKER/CLAIM IDENTITY
-> INSPECT MATCHING NON-EXPIRED ARCHITECT PACKETS
-> ACK / REJECT DETERMINISTICALLY
-> CONTINUE UNDER EXISTING AUTHORITY
```

This order is mandatory. A packet cannot make stale authority current.

## Packet envelope

Required fields:

```json
{
  "schema": "F2_ARCHITECT_WORKER_PACKET/v1",
  "packet_id": "AWP-...",
  "nonce": "...",
  "issued_at": "RFC3339",
  "expires_at": "RFC3339",
  "architect_id": "persistent-architect",
  "project": "frankenstein-2.0",
  "priority": 50,
  "action_class": "COORDINATION_ONLY",
  "target": {},
  "objective": "...",
  "constraints": [],
  "expected_output": {},
  "evidence_refs": [],
  "supersedes_packet_ids": [],
  "credit_authority": false,
  "mutation_authority": false,
  "runtime_dispatch_authority": false
}
```

Allowed `action_class` values in v1:

```text
COORDINATION_ONLY
CONTEXT_DELTA
REVIEW_ONLY
CANDIDATE_FALSIFIER
RESEARCH_REQUEST
STOP_DEFER
```

`STOP_DEFER` means "do not start/continue the described non-authoritative activity until re-evaluation". It still cannot revoke a higher authority by itself.

## Target selectors

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

Selectors present in the packet are conjunctive: every specified selector must match the worker context. Omitted selectors are wildcards.

For list-valued selectors, at least one packet value must equal the worker value.

Examples:

### One exact worker

```json
{"worker_id":"T7-GPT56SOL-VOICE-03"}
```

### Any Trigger-7 reviewer

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

### Bounded broadcast

```json
{"worker_lane":["REVIEW_ONLY","RESEARCH"]}
```

A target with no selectors is forbidden. There is no implicit global broadcast.

## Deterministic disposition

A worker MUST choose exactly one disposition per packet/identity:

```text
APPLIED
ACK_ONLY_DUPLICATE
REJECT_STALE
REJECT_MISADDRESSED
REJECT_SUPERSEDED
REJECT_AUTHORITY_CONFLICT
REJECT_SCHEMA_INVALID
```

Rules:

1. Invalid schema -> `REJECT_SCHEMA_INVALID`.
2. `now >= expires_at` -> `REJECT_STALE`.
3. target mismatch -> `REJECT_MISADDRESSED`.
4. packet explicitly superseded by a matching newer packet -> `REJECT_SUPERSEDED`.
5. same nonce already ACKed by this stable worker/claim identity -> `ACK_ONLY_DUPLICATE`.
6. requested action conflicts with current owner/event/claim/runtime-subject authority -> `REJECT_AUTHORITY_CONFLICT`.
7. otherwise the worker may apply it -> `APPLIED`.

A rejected packet is still useful coordination evidence and should be ACKed when practical.

## ACK envelope

```json
{
  "schema": "F2_ARCHITECT_WORKER_PACKET_ACK/v1",
  "ack_id": "AWA-...",
  "packet_id": "AWP-...",
  "nonce": "...",
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
  "credit_delta": 0
}
```

`new_mutation_authority`, `new_runtime_dispatch`, and `credit_delta` MUST remain false/zero unless some **separate canonical authority** independently performs those transitions; the ACK itself never authorizes them.

## Context-injection discipline

The packet should carry only the delta needed to change the worker's attention. Do not inject full project history.

Recommended packet budget:

```text
objective              <= 1 concise paragraph
constraints            <= 12 bounded clauses
expected_output         <= 8 fields
source/evidence refs    <= 16 exact refs
```

Workers should report `context_bytes_injected` and, when available, estimated token count. This enables measurement against full-bootstrap reentry.

## Research/improvement loop

The Architect may use targeted packets to run controlled worker-method experiments. Each experiment should define:

```text
hypothesis
cohort / target selector
baseline
intervention
success metrics
stop condition
negative-result preservation
```

Recommended metrics:

- duplicate semantic work rate;
- stale-target rejection rate;
- stale work committed before reentry;
- runtime-subject staleness/churn rate;
- infrastructure/evidence failures misclassified as product negatives;
- packet pickup/ACK latency;
- context bytes/tokens per useful closure;
- tool-call count per useful closure;
- higher-tier evidence promotions per material merge;
- recovery success after worker interruption;
- falsifier yield;
- unnecessary new-component rate.

Worker improvement is admitted only when measured. A persuasive worker self-report is not enough.

## Coordination topology

Default topology is centralized-selective:

```text
Architect
  -> exact worker / exact claim packet
  -> bounded worker-class broadcast only when needed
  <- ACK + result + telemetry
  -> next targeted delta
```

Do not default to all-to-all worker messaging. Workers may still exchange existing research packets under current protocols, but Architect steering should minimize cross-talk and context pollution.

## Fan-out fence

Creating an Architect packet MUST NOT automatically spawn a worker or workflow.

```text
PACKET_CREATED != WORKER_SPAWNED
PACKET_CREATED != NEW_GENERATION
PACKET_CREATED != RUNTIME_DISPATCH
```

A worker consumes packets only when it already has an admitted execution/reentry reason, unless a separate current authority explicitly schedules that worker.

## Runtime-subject fence

If a runtime subject is bound/pending, an Architect packet may:

- ask for status/evidence review;
- request a non-mutating falsifier review;
- request `DEFER_UNTIL_RUNTIME_RESULT`;
- identify evidence invalidity.

It MUST NOT silently request a successor semantic mutation unless current executable counterevidence independently requires repair.

## Failure attribution

Worker/coordination research MUST preserve the existing failure taxonomy:

```text
PRODUCT_NEGATIVE
EVIDENCE_INVALID
INFRA_AUTH_TRANSPORT_QUOTA
CONCURRENCY_RETRY
UNKNOWN_NONTERMINAL
```

Coordination-specific failures add a secondary label, never replace the primary product/evidence classification:

```text
PACKET_STALE
PACKET_MISADDRESSED
PACKET_DUPLICATE
PACKET_AUTHORITY_CONFLICT
PACKET_SCHEMA_INVALID
PACKET_NOT_OBSERVED
```

## Security / secrets

Packets and ACKs must not contain provider tokens, passwords, private keys or other secret material. They may reference an admitted secret boundary by name only.

## v1 acceptance tests

A v1 implementation is not accepted until tests prove at least:

1. exact worker packet matches only that worker;
2. exact claim packet matches any temporary worker operating that exact claim;
3. omitted selector acts as wildcard but empty target is rejected;
4. expired packet fails closed;
5. duplicate nonce is idempotent;
6. misaddressed packet cannot alter worker action;
7. packet cannot create mutation/runtime/credit authority;
8. higher current authority defeats conflicting packet;
9. packet creation does not itself spawn work;
10. ACK preserves exact packet/worker/authority identity.

## Research basis for this design

This protocol intentionally favors precise centralized orchestration and selective communication over uncontrolled fan-out. External research should be retained in a separate research delta; external citations are not canonical F2 authority.

## Initial rollout

1. Land protocol + deterministic packet matcher/ACK tool.
2. Update worker reentry to inspect matching packets after event/claim authority.
3. Run adversarial unit tests for stale, duplicate, misaddressed, superseded and authority-conflict packets.
4. Run one bounded Trigger-7 REVIEW_ONLY cohort and one build/runtime cohort.
5. Compare coordination quality/token overhead against a baseline without targeted packets.
6. Promote only measured worker-method improvements; keep product/runtime credit unchanged.
