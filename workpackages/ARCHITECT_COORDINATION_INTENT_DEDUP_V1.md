# Architect Coordination Intent Creation-Dedup Fence v1

Status: **NONCANONICAL COORDINATION PLANE ADDENDUM**

Scope: creation deduplication for Architect coordination packets only. This does not create project truth, workpackage mutation authority, runtime dispatch authority, effect authority, release authority, product credit, or training credit.

## Problem

Per-packet nonce/route idempotency prevents duplicate handling of one packet, but it cannot prevent two independent Architect reentries from creating different packets for the same semantic coordination objective. Canonical evidence on 2026-08-31 showed four near-equivalent ACK-integrity repair packets with distinct packet ids/nonces/routes.

## Deterministic creation identity

Every newly generated packet must carry an explicit caller-supplied stable boundary identity:

```text
coordination_intent_id
coordination_intent_generation
```

The identifier is **not** inferred from prose, embeddings, model similarity, or majority judgment.

For one `(coordination_intent_id, coordination_intent_generation)` pair:

```text
intent_key = SHA256(exact normalized coordination_intent_id)
packet_id  = AWP-I<intent_key>-G<6-digit generation>
canonical pending path =
  coordination/architect_packets/pending/<packet_id>.json
```

Therefore different wording for the same explicit intent/generation still targets the same immutable repository path.

## Separation from delivery idempotency

Creation dedup and delivery idempotency are separate:

```text
coordination_intent_id + generation
    -> creation ownership / same pending path

packet nonce + route_id
    -> delivery/classification idempotency after one creation wins
```

The packet nonce remains unique. The route identity remains bound to the exact winning packet payload and target.

## Create-only / CAS law

New packet creation through `tools/coordination/architect_packet.py new`:

1. requires `--intent-id`;
2. uses intent generation 1 unless an explicit later generation is selected;
3. emits a deterministic packet filename;
4. uses create-only file creation (`open(..., "x")`) when `--output` is supplied;
5. returns `INTENT_ALREADY_RESERVED` rather than overwriting an existing same-generation packet.

Repository convergence remains under existing Git/CAS law:

```text
refresh current main
-> generate same deterministic pending path
-> create-only commit / PR
-> one content/path wins current main
-> loser refreshes
-> reuse/defer/review instead of creating a semantic duplicate
```

No force push and no alternate filename for the same intent generation.

## Successor law

Immutable packet history is never rewritten.

A later coordination intent generation may be created only after the current generation is expired or terminal under current evidence. Generation `N > 1` must explicitly list predecessor packet id(s) in `supersedes_packet_ids`.

The helper enforces explicit supersession presence. The higher-level caller remains responsible for proving that supersession is legally eligible (expired/terminal) before repository mutation.

## Legacy compatibility

Existing `F2_ARCHITECT_WORKER_PACKET/v1` packets that predate these fields remain valid for read/classification/ACK compatibility.

New packet generation uses the intent-bound creation path.

The intent fields are sealed into the payload digest for new packets, and `packet_id` is validated against the exact intent id/generation. Re-sealing a tampered intent without changing its deterministic packet id fails closed.

## Acceptance regressions

Required:

1. same explicit intent + generation + different wording -> same `packet_id`;
2. concurrent local creators for the same deterministic output path -> exactly one create success and one `INTENT_ALREADY_RESERVED`;
3. different intent ids -> different packet ids and independent routing;
4. successor generation >1 without explicit predecessor -> reject;
5. intent-id tamper remains invalid even if payload digest and route id are recomputed;
6. legacy v1 packet without intent fields remains valid;
7. all authority/credit booleans remain false;
8. existing deterministic ACK classifier regressions remain green.

## Evidence scope

A pass proves only coordination creation-integrity behavior at the executed test/CI scope.

It does **not** mint:

- product runtime credit;
- target/physical host credit;
- GRID10 credit;
- GWT/J-Space credit;
- effect credit;
- training credit;
- whole-product completion.
