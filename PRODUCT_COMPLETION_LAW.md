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

## Local-first law

The user's machine is the product's baseline execution environment.

- canonical durable user state must survive host/plugin upgrades and must not live only inside disposable plugin/cache directories;
- the core cognitive/state semantics must remain host-independent;
- host adapters may map real lifecycle/tool events into the common semantic contract;
- installation must discover and verify the host's real capabilities instead of blindly copying another host's hook names;
- unsupported capabilities must be reported as NATIVE / ADAPTED / DEGRADED / BLOCKED rather than faked;
- a VPS, remote HCU lane, provider, cloud model, or remote bridge may accelerate or extend Frankenstein 2.0, but **must not be required for the baseline local product to install, retain state, and operate its admitted local core**;
- the VPS bridge is an optional execution/compute organ of the same entity, not the location where the product itself lives.

## One-handoff acceptance gate

A production release cannot be called Frankenstein 2.0 complete until clean-machine tests prove at least:

1. a release ZIP contains a deterministic installer entry and manifest;
2. a fresh Claude Code environment can be given only the ZIP plus the one-handoff install instruction and reach a verified install;
3. a fresh Codex CLI environment can do the same through a native or explicitly ADAPTED host route;
4. at least one generic/other-agent route proves the semantic adapter contract or explicitly reports the missing capability;
5. durable local state is outside disposable host caches and survives host/plugin update/reinstall;
6. the same installed state is not duplicated into competing per-host truths;
7. optional VPS bridge attachment/detachment does not destroy local identity/state continuity;
8. uninstall/disable and permission withdrawal are explicit and testable;
9. the installer verifies real lifecycle/state/effect integration by readback rather than treating a successful setup command as proof;
10. a generated install report records exact host, mode, paths, state location, mapped hooks/capabilities, limitations and verification results.

## Completion consequence

Repository CI, VPS runtime success, GRID10 success, Retina success, voice success, whole-loop success, and security success are necessary evidence but are not sufficient for final product completion without the portable-host release gate above.

See `architecture/PORTABLE_HOST_HARNESS_AND_DISTRIBUTION_CONTRACT.md` and `workpackages/PORTABLE_DELIVERY_PHASE.json`.
