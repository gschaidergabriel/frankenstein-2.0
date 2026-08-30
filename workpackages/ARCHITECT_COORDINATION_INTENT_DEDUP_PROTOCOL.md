# Architect Coordination Intent Creation-Dedup Protocol v1

Status: **NONCANONICAL COORDINATION CREATION FENCE**

This protocol closes the cross-session creation-duplication class observed after the Architect worker coordination plane was introduced. It does not create project truth, workpackage mutation authority, runtime dispatch authority, effect authority, provider authority, product credit, or training credit.

## 1. Two identities, two jobs

Architect coordination uses two deliberately separate identities:

```text
coordination_intent_id
    = explicit stable identity of the coordination objective / semantic boundary
    = creation-dedup key

packet_id + nonce + route_id
    = immutable packet / delivery identity
    = delivery idempotency and ACK binding
```

Do not use nonce equality to deduplicate separate Architect sessions. Do not use embedding similarity, LLM judgment, or free-text objective similarity as the authoritative creation gate.

## 2. Required creation order

Before a new active Architect packet for a known coordination objective is committed:

```text
REFRESH CURRENT MAIN
-> choose explicit coordination_intent_id
-> build candidate immutable packet
-> run tools/coordination/architect_intent.py against coordination/architect_packets/intents
-> if CLAIMED: commit active intent marker + immutable history marker + packet under normal repository CAS
-> if REUSE_ACTIVE: do not create a second active packet; reuse/defer to the recorded packet
-> if CONCURRENCY_RETRY / repository fast-forward loss: refresh main and re-run the decision
-> if SUPERSEDED_EXPIRED or SUPERSEDED_TERMINAL: preserve old history and admit the successor only at the same deterministic intent key
```

A packet committed while bypassing this creation fence cannot be treated as proof that the semantic objective had unique active coordination ownership.

## 3. Deterministic paths

For explicit intent string `I`:

```text
key = SHA256(UTF8(I))

coordination/architect_packets/intents/active/<key>.json
coordination/architect_packets/intents/history/<key>/<sha256(packet_id)>.json
```

Every concurrent creator for the same intent targets the same active-marker path. Local same-checkout contenders are serialized by the helper. Cross-checkout/repository contenders are resolved by the existing non-force fast-forward/CAS law; a loser refreshes and re-evaluates instead of force-pushing.

The active marker is a coordination projection/ownership fence, not canonical product state.

## 4. State and supersession

One intent has at most one active packet owner at a time.

A successor may replace the active marker only when the previous packet is:

- expired by exact `expires_at`; or
- terminal according to current packet/ACK coordination evidence.

Immutable history is append-only and is never rewritten to hide prior contenders or expired owners.

## 5. Authority fence

Every intent record/result preserves:

```text
new_mutation_authority = false
new_runtime_dispatch = false
new_effect_authority = false
credit_delta = 0
```

Creation dedup is coordination quality only. It cannot mint runtime, product, GRID10, GWT/J-Space, effect, training, or whole-product credit.

## 6. Acceptance tests

Minimum regressions:

1. same explicit intent + different wording -> one `CLAIMED`, later `REUSE_ACTIVE`;
2. two concurrent local creators for the same intent -> exactly one active owner;
3. different intent IDs remain independently routable;
4. expired active intent can be superseded without rewriting old history;
5. terminal active intent can be superseded;
6. all results preserve zero authority/credit;
7. existing deterministic ACK-classification tests continue to pass.

Repository-CAS behavior remains an integration obligation: a stale cross-checkout creator must refresh after fast-forward loss and observe/reuse the winner rather than force-push a second active marker.
