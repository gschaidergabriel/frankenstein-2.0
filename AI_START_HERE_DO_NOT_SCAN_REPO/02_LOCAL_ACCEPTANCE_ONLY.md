# Local Acceptance Only — Do Not Rebuild Frankenstein 2.0 Here

The package handed to this host is intended to be a VPS-built Frankenstein 2.0 release candidate.

## Your job on the local machine

Prefer deterministic installation, environment binding and real-machine acceptance:

1. verify package manifest/hashes and VPS pre-handoff acceptance identity;
2. detect the actual coding-agent host/version and OS/session environment;
3. choose the native/adapted host route;
4. install the prebuilt runtime and one canonical durable state lineage;
5. bind real lifecycle hooks/services/paths;
6. bind real webcams/displays/microphone/browser sources through prebuilt interfaces;
7. request only the user's explicitly chosen OS permissions/capabilities;
8. bind dashboard policy to the installed capability plane;
9. run physical/local restart, state-readback, perception, voice/effect and bridge acceptance probes as enabled;
10. emit exact ACCEPTED / NATIVE / ADAPTED / DEGRADED / BLOCKED evidence.

## Do not silently finish missing architecture locally

If the package is missing major cognitive/state/perception/bridge/installer contracts, or requires broad architectural reconstruction, treat that as a release-candidate defect.

```text
LOCAL FAILURE RECEIPT
-> minimal reproduction + exact environment evidence
-> canonical VPS/repository repair + regression test
-> new release candidate
-> local re-acceptance
```

A small host-specific adapter repair may be made locally when genuinely necessary, but reusable fixes should be upstreamed so the next ZIP is better and local installation remains thin.

## Perception Fabric boundary

The package should already contain the Perception Fabric logic: source/capability contracts, immutable permission snapshots, `ObserveIntent`, CaptureOwner/Broker state machine, bounded queues, 0..4 analysis scheduler, epistemic claim pipeline, temporal fusion, MultiView handling, PerceptionWorldBridge, dashboard policy/API contract and synthetic acceptance tests.

Local work binds those prebuilt mechanisms to real OS/device surfaces and performs final physical acceptance. Do not invent a second perception authority or bypass permission snapshots.

See:

- `PRODUCT_COMPLETION_LAW.md`
- `architecture/VPS_BUILD_TO_LOCAL_ACCEPTANCE_CONTRACT.md`
- `architecture/PERCEPTION_FABRIC.md`
- `architecture/PERCEPTION_FABRIC_HARDENING_20260829.md`
