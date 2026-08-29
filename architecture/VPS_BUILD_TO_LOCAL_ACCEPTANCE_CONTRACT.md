# Frankenstein 2.0 — VPS Build to Local Acceptance Contract

Status: PROJECT-OWNER PRODUCT/ENGINEERING INVARIANT
Date: 2026-08-29

## Purpose

Frankenstein 2.0 is developed and integrated primarily on the authorized VPS build/test lane, while final real-machine acceptance is performed locally with the user's coding-agent host.

```text
VPS / VERIFIED BRIDGE
-> build almost-complete Frankenstein 2.0
-> integrate modules
-> run deterministic/unit/integration/failure/restart/soak tests
-> package release candidate ZIP
-> deliver one-handoff installer

LOCAL CLAUDE CODE / CODEX / OTHER SUPPORTED HOST
-> discover real host and hardware
-> bind OS permissions/devices/hooks/services
-> run real-machine acceptance
-> perform only environment-specific repair if genuinely required
-> ACCEPT or return exact failing evidence to VPS engineering
```

The local acceptance lane is not the place to finish missing architecture, write major subsystems, or discover that the release package was only a collection of repository components.

## Build-completeness law

Before handoff, VPS engineering should complete everything that does not inherently require the final user's physical devices or host-specific permission surfaces, including the F2 cognitive/state architecture, GRID10/GWT/Hyperposition, persistent agency/restart, memory/retrieval/world model, Perception Fabric with synthetic/mock sources, voice logic where hardware-independent, Effect/Completion boundaries, host semantic ABI, installer routes, service templates, manifest/verifier, failure/concurrency/restart/package tests, optional VPS bridge implementation and diagnostics.

`LOCAL_ACCEPTANCE != DEFERRED_ARCHITECTURE_IMPLEMENTATION`

## Legitimately local work

Final local Claude Code/Opus may need to:

- discover exact OS, desktop/session system and coding-agent version;
- choose real filesystem/state paths and enable local user services;
- bind real Claude Code/Codex lifecycle surfaces;
- obtain camera, microphone and screen-capture permissions;
- enumerate actual webcams, monitors, audio devices and browser profiles;
- connect PipeWire/XDG portal or platform-equivalent capture paths;
- validate local resource budgets/hardware acceleration;
- verify real Retina, audio, display, browser and effect paths;
- bind the prebuilt CaptureOwner/Broker to actual device adapters;
- attach the optional VPS bridge to the same canonical entity/state lineage;
- run clean-machine, restart, permission-revocation and uninstall/disable tests.

These are environment bindings and acceptance probes, not permission to redesign the cognitive core locally.

## Thin-local-integration target

A good release candidate should let the local host mostly execute:

```text
READ SMALL INSTALLER ENTRY
-> DETECT HOST/CAPABILITIES
-> INSTALL PAYLOAD
-> BIND LOCAL ADAPTERS
-> REQUEST USER PERMISSIONS WHEN REQUIRED
-> START/RESTART SERVICES
-> RUN REAL ACCEPTANCE PROBES
-> READ BACK STATE/RECEIPTS
-> REPORT NATIVE | ADAPTED | DEGRADED | BLOCKED | ACCEPTED
```

If local Claude must invent major modules, reconstruct missing data contracts, reconcile competing state authorities or perform broad architectural refactoring, the VPS release candidate failed its handoff gate.

## VPS pre-handoff gate

A release candidate is eligible for local acceptance only after the available non-physical gates pass at the exact source/package identity, including deterministic package reproduction, admitted integration tests, synthetic sensor/host tests, fresh-process restart/state continuity, failure injection, resource/concurrency characterization, Perception Fabric multi-source/no-VLM soak, no-VPS local-core contract tests, bridge attach/detach tests and installer/manifest verification.

Passing this gate does not claim physical local acceptance; it proves readiness for the final machine.

## Final local acceptance authority

Final product acceptance is a real local-machine event. VPS evidence cannot fabricate camera, screen, microphone, host-hook, desktop-portal, persistence or physical effect behavior that was never exercised there.

If local acceptance reveals a core/systemic defect:

```text
LOCAL FAILURE RECEIPT
-> exact minimal reproduction/evidence
-> VPS engineering repair + regression test
-> new release candidate
-> local re-acceptance
```

Avoid accumulating one-off local patches that diverge from canonical F2 source.

This contract complements `PRODUCT_COMPLETION_LAW.md` and `architecture/PORTABLE_HOST_HARNESS_AND_DISTRIBUTION_CONTRACT.md`.
