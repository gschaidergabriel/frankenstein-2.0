# Verify Frankenstein 2.0 install

Do not report success because files copied or a setup command returned zero.

## Minimum proof

Verify, where supported by the selected host/release:

```text
A release/package identity resolved
B host/version/capability surface detected
C canonical durable local state path resolved outside disposable plugin/cache directories
D existing state reused or explicit migration performed
E session/start semantic event fires
F user-turn semantic event fires
G pre-effect boundary fires before a real effect-capable call
H post-effect/result boundary fires and correlates to the exact invocation
I checkpoint/stop/compact equivalent is verified or explicitly MISSING
J a state write is read back from the canonical durable store
K restart recovers identity/state without relying on conversation context
L optional local persistent-runtime service is healthy, restartable and disableable when this release uses one
M VPS bridge absent: baseline local core still boots
N VPS bridge present: attach/detach preserves the same local identity/state lineage
O no second per-host canonical memory/state authority was created
P permissions/sensors/effects remain user-policy gated
```

## Required report

```text
host:
host_version:
release_id:
mode: NATIVE|ADAPTED|DEGRADED|BLOCKED
package_root:
runtime_root:
state_path:
state_lineage_id_or_fingerprint:
semantic_event_mapping:
hooks_or_equivalents_verified:
hooks_or_equivalents_missing:
state_readback_verified:
restart_recovery_verified:
persistent_runtime_status:
vps_bridge_status: ABSENT|ATTACHED|DEGRADED|BLOCKED
baseline_local_boot_without_vps:
effect_boundary_verified:
permissions_verified:
limitations:
unfinished_delivery_workpackages:
```

## Classification

- **NATIVE** — host has a direct verified implementation of required semantic roles and local runtime/state works.
- **ADAPTED** — host glue differs but equivalent semantics are verified.
- **DEGRADED** — admitted core works while optional capabilities are missing; exact limitations are recorded.
- **BLOCKED** — required lifecycle/state/runtime capability is absent, unverified, denied, or the release package itself is incomplete.

A development VPS success, CI success, or repository source presence is never a substitute for this clean local install proof.
