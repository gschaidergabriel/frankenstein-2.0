# Portable Host Harness and Distribution Contract

Status: canonical product architecture constraint
Date: 2026-08-29

## 1. Purpose

Frankenstein 2.0 must preserve the strongest product property of the Frankenstein 1.x donor: a user can hand a package to a capable local coding agent and have that agent install the harness into its own real environment, verify the integration, and then use Frankenstein as the persistent cognitive body around that host.

This contract separates **product topology** from **development topology**. Development may use repository CI, the authorized VPS sandbox, VPS bridges, remote providers, or HCU experiments. The shipped product remains local-first and host-portable.

## 2. Donor property being preserved

The inspected Frankenstein 1.x package defines a one-handoff flow for Claude Code, Codex CLI, Hermes/other local agents and browser variants. Its key implementation ideas are:

- an `AI_START_HERE_DO_NOT_SCAN_REPO/` installer entry rather than requiring a human to understand the entire repository;
- host-specific routes around one semantic lifecycle/state contract;
- Claude Code as the reference/native integration;
- Codex/other coding agents mapping their real lifecycle/tool surfaces instead of blindly copying Claude-specific event names;
- durable state outside disposable plugin caches;
- verification by triggering real lifecycle events and reading persistent state/effect receipts back;
- explicit `NATIVE | ADAPTED | DEGRADED | BLOCKED` reporting;
- package-local source plus host-level installation glue;
- no fake success when a required host capability is missing.

Frankenstein 2.0 may change the runtime architecture radically, including a real persistent pulse/background scheduler, but it must preserve this **distribution and host-adaptation behavior**.

## 3. Product topology

```text
                           optional
                    +--------------------+
                    | VPS / HCU / remote |
                    | compute bridge     |
                    +----------^---------+
                               |
                               | typed bridge ABI
                               |
+---------------------------------------------------------------+
| USER MACHINE                                                   |
|                                                               |
| Coding-agent host                                              |
| Claude Code | Codex CLI | Other supported host                |
|         |                                                     |
|         v                                                     |
| Host Adapter / Semantic Lifecycle ABI                         |
|         |                                                     |
|         v                                                     |
| Frankenstein 2.0 local runtime                                |
| GRID10 · GWT · UnifiedDB · Memory · Retina · Voice · Effects   |
|         |                                                     |
|         v                                                     |
| durable local state + local sensors/effect boundaries          |
+---------------------------------------------------------------+
```

The VPS is not a second Frankenstein and not canonical state authority. It may run delegated compute, experiments, heavy workers, or remote execution requested by the same entity. Removing the VPS bridge must not erase local identity or canonical state.

## 4. Required package shape

The final release ZIP should expose a small deterministic top level instead of making the receiving agent scan everything:

```text
AI_START_HERE_DO_NOT_SCAN_REPO/
  00_READ_THIS_FIRST.md
  01_ROUTES.json
  03_VERIFY_INSTALL.md
  CLAUDE_CODE/00_DO_THIS.md
  CODEX_CLI/00_DO_THIS.md
  OTHER_AGENT/00_DO_THIS.md
PRODUCT_COMPLETION_LAW.md
manifest/release-manifest.json
payload/ or equivalent canonical runtime/package root
```

Names may evolve only if the release self-describes an equally simple deterministic entry. The one-handoff property is invariant; exact directory spelling is compatibility surface.

## 5. Semantic host ABI

The core must not depend on Claude-specific or Codex-specific hook names. Host adapters map concrete host events onto semantic roles such as:

- `SESSION_START`
- `USER_TURN`
- `PRE_EFFECT`
- `POST_EFFECT`
- `SESSION_STOP`
- `PRE_COMPACT_OR_CHECKPOINT`
- `TOOL_RESULT_RETURN`
- `BACKGROUND_WAKE` where the host/runtime supports it

The adapter must record which concrete event/tool surface implements each role and verify timing, payload identity and firing multiplicity. Matching names are not sufficient evidence.

## 6. State law

There is one canonical installed state lineage.

- host plugin/cache directories may contain code copies but not the only durable state;
- reinstall/update must discover and reuse or deliberately migrate the existing state lineage;
- Claude Code and Codex adapters on the same machine must not silently create independent Frankenstein memories;
- a host may maintain adapter-private cache, but canonical facts/goals/episodes/method state remain in the shared F2 state authority;
- remote/VPS replicas are caches/projections unless explicitly promoted by the canonical state protocol.

## 7. Installer behavior

The receiving local coding agent must:

1. resolve package root and release manifest;
2. identify its actual host/version and available lifecycle/tool/state capabilities;
3. select the native route when one is verified, otherwise the generic semantic adapter route;
4. choose a persistent local state path outside disposable caches;
5. install runtime payload and host adapter without creating a second state authority;
6. install only owner/user-authorized optional sensors, effects, background services and bridges;
7. run the smallest real integration probes;
8. read writes/results back from durable state;
9. emit an install report with `NATIVE`, `ADAPTED`, `DEGRADED`, or `BLOCKED` plus exact limitations;
10. never report LIVE merely because files were copied.

## 8. Persistent-runtime difference from 1.x

Frankenstein 1.x was predominantly hook-driven and deliberately avoided requiring a permanent process. Frankenstein 2.0's persistent agency may require one or more local supervised background components.

That architectural evolution is allowed, but installation must manage it as part of the local product: explicit service ownership, health/status, restart behavior, clean disable/uninstall, resource budgets and state continuity. A VPS process is not a substitute for a missing local installation contract.

## 9. Optional VPS bridge law

The VPS bridge is a supported optional organ:

- attachable after baseline local install;
- permission- and policy-gated;
- typed request/result transport rather than implicit remote shell authority;
- bounded by resource/load policy;
- incapable of minting canonical local world truth/effect completion merely by returning text;
- detachable without identity loss;
- not required for local boot, memory continuity, basic GRID cognition or host lifecycle integration unless a future release explicitly labels a feature as remote-only.

## 10. Clean-machine acceptance matrix

Before final release, test from clean environments with no pre-existing Frankenstein state:

| Host | Required release result |
|---|---|
| Claude Code | NATIVE unless current host capabilities force an explicitly evidenced adapter |
| Codex CLI | NATIVE or ADAPTED using current real Codex lifecycle/tool mechanisms |
| Other capable coding agent | ADAPTED or precise DEGRADED/BLOCKED report |
| No VPS configured | baseline local core still installs and boots |
| VPS configured | bridge attaches without creating competing state authority |

Tests must include reinstall/update persistence, restart recovery, hook/event verification, state readback, optional bridge attach/detach, and uninstall/disable.

## 11. Release artifact acceptance

A release ZIP must carry:

- exact version/build identity;
- source/tree provenance;
- deterministic file manifest + SHA-256 hashes;
- supported-host routes;
- minimum runtime dependencies;
- explicit state migration version;
- optional-feature capability requirements;
- verifier/self-test entry;
- no embedded user secrets or user state.

The release package is code and installer metadata. User state remains local and separate.

## 12. Completion rule

A system that works only in GitHub Actions, only on `clay-direct-dev`, only behind the VPS bridge, or only inside the development checkout is **not a finished Frankenstein 2.0 product**.

Final completion requires the one-handoff portable-host gate in `PRODUCT_COMPLETION_LAW.md`.
