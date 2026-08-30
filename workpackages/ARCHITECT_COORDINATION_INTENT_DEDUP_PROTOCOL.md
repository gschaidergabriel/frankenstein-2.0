# Architect Coordination Intent Dedup Protocol v1

Status: **NONCANONICAL COORDINATION CREATION FENCE**

Purpose: prevent concurrent persistent-Architect reentries from creating multiple active coordination packets for the same explicit coordination objective while preserving the existing packet delivery/ACK state machine and every product/effect/runtime authority boundary.

This protocol is a bounded extension of `ARCHITECT_WORKER_COORDINATION_PROTOCOL.md`. It does **not** create project truth, mutation authority, runtime dispatch authority, effect authority, release authority, or product/training credit.

## 1. Separate two identities

Creation dedup and delivery idempotency are different problems.

```text
coordination_intent_id
    = explicit stable semantic-boundary identity chosen by the Architect/owner protocol
    = creation-dedup key

packet_id + nonce + route_id
    = one immutable packet/delivery attempt identity
    = delivery idempotency
```

Never derive `coordination_intent_id` from embedding similarity, model confidence, or free-text semantic judgment.

Different wording for the same intended coordination boundary MUST reuse the same explicit `coordination_intent_id`.

Different real coordination boundaries MUST use different intent IDs.

## 2. Append-only intent event chain

Canonical coordination-support path:

```text
coordination/architect_intents/<sha256(coordination_intent_id)>/<six-digit-sequence>.json
```

The chain is append-only. There is no mutable global coordination ledger and no competing project truth.

Event states:

```text
ACTIVE
TERMINAL
```

An ACTIVE event binds exact intent identity/hash, packet id, packet payload digest, packet route id, creation/expiry timestamps, previous intent-event digest, and explicit zero authority/credit fields.

A TERMINAL event additionally binds external completion/evidence reference and the exact active packet identity.

## 3. Creation law

Before committing a new pending Architect packet for a stable intent:

```text
REFRESH MAIN
-> choose explicit coordination_intent_id
-> validate candidate packet
-> resolve current intent chain
-> if latest ACTIVE and unexpired:
       REUSE/DEFER existing active packet
   else:
       append deterministic next ACTIVE event with create-only filesystem semantics
-> commit intent event + pending packet atomically
-> publish only by non-force Git fast-forward/CAS
```

A failed fast-forward means:

```text
CONCURRENCY_RETRY
-> refresh main
-> resolve intent chain again
-> reuse/defer winner when now active
```

Never force-push to win the intent race.

The deterministic sequence path is the repository collision point. Two cross-session creators starting from the same event head target the same next path. Existing Git CAS therefore selects one canonical winner; a loser must refresh rather than create another intent generation.

## 4. Same-checkout race law

`tools/coordination/architect_intent.py` publishes a complete event using create-only atomic file visibility. Two same-checkout creators for one intent produce one `RESERVED` and one `REUSE_ACTIVE` (or bounded `CONCURRENCY_RETRY` requiring refresh), not two ACTIVE events.

## 5. Expiry and terminal successor

Immutable history is never rewritten.

If the latest ACTIVE event is expired, the next reservation appends sequence `N+1`.

If the latest event is TERMINAL, a new reservation for the same stable intent may append a successor sequence.

Terminal append requires current active packet identity match (`packet_id`, `payload_digest`, `route_id`), non-empty terminal evidence reference, and create-only next event path.

## 6. Authority fence

Every intent event and result MUST preserve:

```text
new_mutation_authority = false
new_runtime_dispatch   = false
new_effect_authority   = false
credit_delta           = 0
```

Intent reservation is coordination ownership only.

```text
INTENT_RESERVED != WORKPACKAGE_CLAIM
INTENT_RESERVED != RUNTIME_DISPATCH
INTENT_RESERVED != EFFECT_AUTHORITY
INTENT_RESERVED != PRODUCT_PROGRESS
INTENT_RESERVED != TRAINING_CREDIT
```

Normal workpackage/claim/event/reconciliation authority still wins.

## 7. Packet compatibility

Packet validation remains owned by `tools/coordination/architect_packet.py`.

ACK creation remains governed by deterministic `packet_disposition(...)` classification and the ACK integrity repair merged at commit `76c8943be674713f078df4de07badde5953f93f4`.

Intent creation dedup MUST NOT weaken or replace packet validation, route identity, nonce idempotency, ACK classification, Clay delivery atomicity, or current runtime-subject fences.

## 8. Required regression set

At minimum:

1. same explicit intent + different wording/nonces => one ACTIVE reservation;
2. different intent IDs => independent reservations;
3. concurrent same-checkout creators => one reservation, one reuse/retry;
4. expired ACTIVE => append-only successor;
5. TERMINAL => append-only successor;
6. stale candidate packet => no reservation;
7. event tamper => fail closed;
8. terminal event must bind exact active packet identity;
9. every event/result preserves zero mutation/runtime/effect/credit authority.

Repository-level promotion additionally requires the existing non-force Git CAS law. Local filesystem concurrency tests do not by themselves prove cross-clone Git CAS; the deterministic collision path plus current repository CAS protocol is the cross-session enforcement boundary.

## 9. Current finding closed by this protocol

Trigger-7 evidence showed four near-equivalent ACK-integrity repair packets with distinct packet IDs/nonces/routes. Per-packet idempotency correctly could not identify them as the same creation intent.

The repair is therefore explicit deterministic intent creation ownership, not semantic-similarity inference and not a stronger delivery state machine.

Product/runtime/training/effect credit remains unchanged.
