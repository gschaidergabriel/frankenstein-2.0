# Frankenstein 2.0 — Product Completion Law

Status: PROJECT-OWNER PRODUCT INVARIANT
Date: 2026-08-29

Frankenstein 2.0 is not complete merely because its cognitive runtime works on a development VPS, in repository CI, or on one preconfigured machine.

## Final product form

The finished product is a **portable local host harness** delivered as a downloadable ZIP/release package (repository URL may be an equivalent source during development).

A normal user must be able to hand that ZIP to a capable local coding agent such as Claude Code, OpenAI Codex CLI, or another supported coding-agent host and ask it to install Frankenstein 2.0 for the current environment.

The installer entry must be explicit and self-describing. The reference shape inherited from the Frankenstein 1.x donor is:

`ZIP -> AI_START_HERE_DO_NOT_SCAN_REPO -> host detection -> semantic mapping -> install -> verify -> LIVE`

Claude Code is the reference/native host integration unless later evidence changes that. Codex and other hosts use native equivalents or bounded adapters. Host-specific hook/event names are glue; they must not become cognitive-state authority.

## VPS-build / local-acceptance law

The development topology and the final product topology are intentionally different.

During construction, the authorized VPS/bridge lane is the **primary assembly, implementation, integration, testing, falsification and release-candidate build environment**. Trigger-4 engineering should finish everything there that does not inherently require the user's final physical machine or OS permission grant.

The intended handoff is:

`VPS BUILDS ALMOST-COMPLETE RELEASE CANDIDATE -> ZIP -> LOCAL CLAUDE CODE/OPUS FINAL REAL-MACHINE INTEGRATION + ACCEPTANCE`

The local Claude Code/Opus lane is expected to perform thin environment binding and final acceptance: host/version detection, local paths/services, real device enumeration, OS permissions, lifecycle-hook binding, physical Retina/audio/display/browser tests, restart/state readback and optional VPS bridge attachment.

It is **not** the intended place to finish missing cognitive architecture or write major subsystems that should already have been completed and falsified on the VPS.

If local acceptance requires broad architectural reconstruction, the release candidate failed the VPS handoff gate and the repair should normally return to canonical VPS engineering with a regression test.

See `architecture/VPS_BUILD_TO_LOCAL_ACCEPTANCE_CONTRACT.md`.

## Local-first product law

The user's machine is the product's baseline installed execution environment after release/installation.

- canonical durable user state must survive host/plugin upgrades and must not live only inside disposable plugin/cache directories;
- the core cognitive/state semantics must remain host-independent;
- host adapters may map real lifecycle/tool events into the common semantic contract;
- installation must discover and verify the host's real capabilities instead of blindly copying another host's hook names;
- unsupported capabilities must be reported as NATIVE / ADAPTED / DEGRADED / BLOCKED rather than faked;
- a VPS, remote HCU lane, provider, cloud model, or remote bridge may accelerate or extend Frankenstein 2.0, but **must not be required for the baseline installed local product to retain state and operate its admitted local core**;
- the VPS bridge is an optional execution/compute organ of the same entity after installation, not the location where the product's canonical local state lives.

This local-first product law does **not** prohibit or discourage VPS-first development. The project is expected to use the VPS aggressively and safely to make the delivered local package as complete as possible before final acceptance.

## Perception Fabric completion law

Frankenstein 2.0 completion also requires the permission-gated multi-source Perception Fabric defined in `architecture/PERCEPTION_FABRIC.md` and `workpackages/PERCEPTION_FABRIC_PHASE.json`.

At minimum the completed architecture must support:

- explicit user/dashboard capability control for webcam, displays, browser visual/structural sources and admitted user-activity metadata;
- one capture owner per source with bounded RAM fan-out;
- continuous cheap Retina L0 without required LLM/VLM-token use;
- GRID10-driven `ObserveIntent` active sensing;
- a dynamically admitted 0..4 Retina/Cortex analysis-worker pool;
- local OCR/UI/DOM/AX/tracking/specialist analysis before generic VLM escalation;
- temporal/multi-view fusion into epistemically typed world-model updates;
- typed VPS PerceptionWorldBridge events with raw/ROI transfer only under explicit permission;
- default no raw-frame persistence;
- explicit VLM escalation permission;
- local dashboard pause/revocation/audit controls;
- a bounded four-source no-general-VLM soak before final real-device acceptance.

Source presence alone does not satisfy this law.

## One-handoff acceptance gate

A production release cannot be called Frankenstein 2.0 complete until clean-machine tests prove at least:

1. a release ZIP contains a deterministic installer entry and manifest;
2. the exact ZIP was produced from a VPS release candidate that passed all available non-physical handoff gates;
3. a fresh Claude Code environment can be given only the ZIP plus the one-handoff install instruction and reach a verified install;
4. a fresh Codex CLI environment can do the same through a native or explicitly ADAPTED host route;
5. at least one generic/other-agent route proves the semantic adapter contract or explicitly reports the missing capability;
6. durable local state is outside disposable host caches and survives host/plugin update/reinstall;
7. the same installed state is not duplicated into competing per-host truths;
8. optional VPS bridge attachment/detachment does not destroy local identity/state continuity;
9. uninstall/disable and permission withdrawal are explicit and testable;
10. the installer verifies real lifecycle/state/effect integration by readback rather than treating a successful setup command as proof;
11. the real local Perception Fabric/device/permission gates are exercised where those capabilities are enabled;
12. a generated install report records exact host, mode, paths, state location, mapped hooks/capabilities, sensor/permission status, limitations and verification results.

## Completion consequence

Repository CI, VPS runtime success, GRID10 success, Retina success, voice success, whole-loop success, and security success are necessary evidence but are not sufficient for final product completion without the portable-host release and real local acceptance gates above.

Conversely, local Claude Code/Opus acceptance is not permission to defer unfinished core engineering from the VPS lane. The target is a nearly complete, reproducible release candidate before local handoff.

See:

- `architecture/PORTABLE_HOST_HARNESS_AND_DISTRIBUTION_CONTRACT.md`;
- `architecture/VPS_BUILD_TO_LOCAL_ACCEPTANCE_CONTRACT.md`;
- `architecture/PERCEPTION_FABRIC.md`;
- `workpackages/PORTABLE_DELIVERY_PHASE.json`;
- `workpackages/PERCEPTION_FABRIC_PHASE.json`.
