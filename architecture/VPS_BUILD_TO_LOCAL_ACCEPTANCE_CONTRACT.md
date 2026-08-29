# Frankenstein 2.0 — VPS Build to Local Acceptance Contract

Status: PROJECT-OWNER PRODUCT/ENGINEERING INVARIANT
Date: 2026-08-29

## 1. Purpose

Frankenstein 2.0 is developed and integrated primarily on the authorized VPS build/test lane, while the final real-machine acceptance is performed locally with the user's coding-agent host.

The required engineering direction is:

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

## 2. Build-completeness law

Before a release candidate is handed to the local acceptance lane, VPS engineering should have completed as much of the system as can be completed without access to the final user's physical devices and host-specific permission surfaces.

At minimum the VPS-built release candidate must already contain:

- the complete intended F2 runtime/core architecture;
- canonical UnifiedDB/state schema and migrations;
- GRID10/GWT/Hyperposition controller implementation;
- persistent pulse/agency/restart logic;
- memory/retrieval/world-model logic;
- Retina/Cortex/Perception Fabric implementation with mock/synthetic source adapters;
- voice/session logic where hardware-independent;
- Effect/Completion boundaries and causal evidence handling;
- host semantic ABI and Claude/Codex/generic adapter implementations as far as their public/local interfaces permit;
- installer routes, dependency discovery, service templates and verifier;
- deterministic manifests and hashes;
- unit, integration, concurrency, failure-injection, restart and package tests;
- optional VPS bridge attach/detach implementation and tests;
- release diagnostics that distinguish core defect from local environment incompatibility.

`LOCAL_ACCEPTANCE != DEFERRED_ARCHITECTURE_IMPLEMENTATION`

## 3. What remains legitimately local

The final local Claude Code/Opus acceptance may need to perform work that cannot be proven on the VPS because it depends on the actual machine or user grant. Examples include:

- discover exact OS, desktop/session system and coding-agent version;
- choose real filesystem/state paths;
- create/enable local user services;
- bind real Claude Code/Codex lifecycle hooks or native integration surfaces;
- obtain OS-mediated camera, microphone and screen-capture permissions;
- enumerate webcams, monitors, audio devices and local browser profiles;
- connect PipeWire/XDG portal or platform-equivalent capture paths;
- validate local resource budgets and hardware acceleration;
- verify real Retina, microphone, display, browser and effect paths;
- attach the optional VPS bridge to the same canonical entity/state lineage;
- run clean-machine, restart, permission-revocation and uninstall/disable tests.

These are final environment bindings and acceptance probes, not permission to redesign the cognitive core locally.

## 4. Thin-local-integration target

The engineering objective is that a capable local coding agent should mostly execute a deterministic installer/verification plan rather than perform open-ended construction.

A good release candidate therefore lets the local host do approximately this:

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

If local Claude must invent major modules, reconstruct missing data contracts, manually reconcile competing state authorities, or perform broad architectural refactoring, the VPS release candidate failed its handoff gate.

## 5. VPS engineering gate before handoff

A VPS release candidate is eligible for local acceptance only when the available non-physical gates pass at the candidate's exact source/package identity, including:

1. deterministic build/package reproduction;
2. all admitted repository-hosted component/integration tests;
3. synthetic/mocked sensor and host-adapter tests;
4. fresh-process restart/state continuity tests;
5. failure injection for stale generations, dropped workers, duplicate execution and bridge loss;
6. bounded resource and concurrency characterization;
7. Perception Fabric multi-source/no-VLM synthetic soak;
8. no-VPS local-core simulation/contract tests;
9. VPS bridge attach/detach tests without state-identity fork;
10. installer dry-run/static validation and release manifest verification.

Passing this gate does not claim physical local acceptance. It proves the package is ready to be tested on the final machine.

## 6. Final local acceptance authority

The final product acceptance is a real local-machine event. The user and the selected local coding-agent host perform the final integration/acceptance against the actual environment.

The VPS build lane may produce evidence and release candidates but cannot fabricate evidence for local camera, screen, microphone, host-hook, desktop-portal, persistence or physical effect behavior that was never exercised on that machine.

If local acceptance reveals a core/systemic defect, the preferred flow is:

```text
LOCAL FAILURE RECEIPT
-> exact minimal reproduction/evidence
-> VPS engineering repair + regression test
-> new release candidate
-> local re-acceptance
```

Avoid accumulating one-off local patches that diverge from the canonical F2 source.

## 7. Relationship to the portable-host law

This contract complements `PRODUCT_COMPLETION_LAW.md` and `architecture/PORTABLE_HOST_HARNESS_AND_DISTRIBUTION_CONTRACT.md`.

- VPS is the primary engineering/build/test workshop.
- The release artifact is built to be almost complete before handoff.
- The user's machine is the final installed product runtime and final physical acceptance environment.
- Claude Code is the reference local acceptance/integration host; Codex and other supported hosts use the same semantic host ABI.
- Optional VPS/HCU compute after installation remains an organ of the same entity, not a second product or competing state authority.
