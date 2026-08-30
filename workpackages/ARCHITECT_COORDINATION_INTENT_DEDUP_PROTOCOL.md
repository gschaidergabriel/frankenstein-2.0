# Architect Coordination Intent Creation-Dedup Fence v1

Status: **MANDATORY NONCANONICAL COORDINATION CREATION FENCE**

This is a narrow successor/addendum to `workpackages/ARCHITECT_WORKER_COORDINATION_PROTOCOL.md`.
It does not create project truth, mutation authority, runtime authority, effect authority, or
another delivery state machine.

## Problem

Packet delivery was already idempotent by packet nonce/route identity, but packet **creation**
had no cross-session semantic-boundary fence. Two Architect reentries could describe the same
coordination objective differently, mint two packet IDs/nonces, and both become pending.

Delivery idempotency cannot repair that because the duplicate exists before delivery.

## Law

Every newly active Architect coordination packet that participates in cross-session coordination
MUST first be compiled through:

```text
tools/coordination/architect_intent.py
```

The creator supplies an **explicit stable `intent_id`**. The system MUST NOT infer authoritative
intent identity from embeddings, free-text similarity, or an LLM judgment.

The compiler canonicalizes:

```text
project
architect_id
explicit intent_id
```

into one deterministic `intent_key`.

For each explicit intent generation, the only reservation path is:

```text
coordination/architect_packets/intents/<intent_key>/<generation:06d>.json
```

The reservation and its candidate packet:

```text
coordination/architect_packets/pending/<packet_id>.json
```

MUST be created together in **one Git tree/commit** from refreshed `main`, followed by a
non-force fast-forward CAS update.

Therefore:

```text
SAME_EXPLICIT_INTENT + SAME_GENERATION
    -> SAME_CREATE_ONLY_RESERVATION_PATH
    -> ONE CAS WINNER
    -> LOSER REFRESHES
    -> REUSE_EXISTING_PACKET OR DEFER
```

No force push. No second active packet because wording changed.

## Generation selection is not caller authority

A caller MUST NOT freely choose the next intent generation.

The public creation compiler intentionally has no caller-selectable `generation` parameter:

```text
no observed predecessor
    -> compiler may propose GENERATION_1 only

validated active + unexpired predecessor N
    -> REUSE_EXISTING_PACKET
    -> no new packet
    -> no successor reservation

validated expired or externally-terminal predecessor N
    -> compiler derives GENERATION_N_PLUS_1 exactly
```

This closes the generation-skip bypass of the create-only collision path. If a creator ignores
an already-observed predecessor and calls the compiler as if no predecessor exists, it can only
propose generation 1 again and therefore collides with the already-existing generation-1 path at
repository CAS; it cannot jump directly to generation 2 or an arbitrary generation.

The observed predecessor supplied for successor derivation MUST be the current reservation obtained
after refresh. Git CAS remains the cross-session authority if another creator advances the same
intent between read and write. A CAS loser refreshes and re-evaluates; it never force-pushes.

## Separation from delivery identity

The creation key is deliberately independent from packet delivery identity:

```text
coordination intent key != packet_id != nonce != route_id
```

A winning packet keeps its own packet ID, nonce, payload digest, route ID and existing deterministic
ACK classification. The intent reservation only prevents multiple packets from becoming active for
the same explicit coordination boundary.

`tools/coordination/architect_packet.py` remains the packet validator/matcher/ACK helper.
Clay's existing live-reentry delivery atomicity primitive remains the delivery authority.

## Expiry / terminal transition

Reservation files are immutable. They are never rewritten to make a new packet active.

If the current packet is expired or externally established terminal, the compiler validates the
observed reservation and derives exactly the next generation. Historical reservation and packet
evidence remain intact.

```text
EXPIRED_OR_TERMINAL_GENERATION_N
    -> COMPILER_DERIVES_GENERATION_N_PLUS_1
    -> NEW CREATE_ONLY PATH
```

No public creation path may accept an arbitrary `N+1` supplied by the caller.

## Failure / credit

Creation collision, stale reservation, malformed intent identity or CAS loss is coordination
evidence only.

It MUST NOT mint:

- workpackage mutation authority;
- runtime dispatch authority;
- effect authority;
- product/runtime evidence;
- training credit;
- whole-system credit.

A packet created without a winning same-commit reservation has zero creation-ownership standing
under this fence.

## Required regressions

At minimum:

1. same explicit intent ID + different prose -> identical generation-1 reservation path;
2. different explicit intent IDs -> independent paths;
3. same-intent candidate packets retain distinct nonce/packet/route identities before CAS;
4. active existing reservation -> `REUSE_EXISTING_PACKET` and **no new packet**;
5. omitting observed state can only re-propose generation 1, preserving same-path collision;
6. expired or terminal reservation N -> compiler derives exactly generation N+1;
7. public creation API/CLI has no arbitrary generation selector;
8. reservation from another intent -> fail closed;
9. reservation identity/path tamper -> fail closed;
10. reservation cannot grant authority or credit;
11. repository writer creates reservation + packet in one refreshed-main CAS commit.

## Compatibility

This fence preserves the deterministic ACK repair in
`76c8943be674713f078df4de07badde5953f93f4`.

Legacy packet files remain valid historical evidence. This rule governs new active cross-session
coordination creation after adoption; it does not rewrite old packet history.
