# Architect Coordination Intent Creation Dedup v1

Status: **NONCANONICAL COORDINATION CREATION FENCE**

This extension closes the cross-session packet-creation duplication observed on 2026-08-31. It does not replace `ARCHITECT_WORKER_COORDINATION_PROTOCOL.md`, Clay delivery atomicity, F2 workpackage state, mutation authority, runtime authority, effect authority, or canonical product truth.

## Problem

Packet nonce and `route_id` make delivery of one packet idempotent, but they cannot identify two independently-created packets that express the same coordination objective. Four near-equivalent ACK-integrity routing packets were observed on canonical main with different packet IDs/nonces/routes.

Therefore:

```text
DELIVERY_IDEMPOTENCY != CREATION_DEDUP
NEW_ARCHITECT_SESSION != NEW_COORDINATION_INTENT
DIFFERENT_WORDING != DIFFERENT_INTENT
```

## Explicit intent identity

Every new Architect coordination objective that can be created concurrently SHOULD be assigned a caller-supplied stable `coordination_intent_id` and explicit `intent_revision`.

The authoritative dedup key is deterministic over:

```text
project
target selectors
coordination_intent_id
intent_revision
```

It MUST NOT be inferred from embeddings, LLM similarity, majority vote, or prose similarity.

`tools/coordination/architect_intent.py` derives a deterministic packet ID/path from that key. The intent identity is also inserted as an evidence ref:

```text
coordination-intent:<coordination_intent_id>@<intent_revision>
```

Because `evidence_refs` are already bound by the packet payload digest, the explicit intent identity is covered by the existing packet integrity checks without creating a second packet schema.

## Create-only law

For one explicit intent revision:

```text
same deterministic intent key
-> same deterministic pending packet path
-> create-only/CAS race
-> one CREATED winner
-> all concurrent losers REFRESH + REUSE_EXISTING/DEFER
```

A loser MUST NOT create a random fallback packet path for the same intent revision.

In one checkout/process domain the helper uses an atomic create-only filesystem operation. Across repository branches/sessions, the same deterministic Git path must be created through GitHub create-only/CAS semantics. A path conflict is `CONCURRENCY_RETRY`, not permission to mint a second packet.

## Delivery identity remains separate

The winning packet still receives its own random nonce and derived `route_id`. Those identities remain delivery/idempotency evidence only.

```text
coordination_intent_id + intent_revision = creation dedup identity
packet_id + nonce + route_id             = winning packet/delivery identity
```

Do not collapse the two layers.

## Supersession

Immutable packet history is never rewritten. When an intent is terminal/expired and a genuinely new coordination revision is required, increment/change the explicit `intent_revision`. That yields a new deterministic path while retaining the old packet as history.

Revision change must be intentional. It is not a retry escape hatch.

## Authority fence

Creation dedup cannot create or transfer:

- workpackage mutation authority;
- runtime dispatch authority;
- effect authority;
- provider authority;
- product/runtime/training/effect/whole-system credit.

A dedup failure or CAS loss is coordination/concurrency evidence only.

## Required regressions

1. Same explicit intent + different wording -> same deterministic packet path.
2. Concurrent creators of one intent revision -> exactly one created winner; loser reuses/defer.
3. Different intent IDs -> independently routable paths.
4. Explicit successor revision -> new path without rewriting history.
5. Winning packet remains valid under existing payload/route validation.
6. Creation fence preserves all authority/credit fields false.
7. Existing deterministic ACK classifier behavior remains green.

## Current implementation

- `tools/coordination/architect_intent.py`
- `tests/test_architect_coordination_intent.py`
- `.github/workflows/architect-worker-coordination-ci.yml`

This is intentionally the smallest additive fence: one deterministic creation key and create-only path, while reusing the existing packet schema and delivery classifier.
