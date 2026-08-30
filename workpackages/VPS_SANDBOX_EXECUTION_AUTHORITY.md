# VPS SANDBOX EXECUTION AUTHORITY — OWNER DIRECTIVE 2026-08-30

Status: CURRENT OWNER EXECUTION DIRECTIVE
Scope: Frankenstein 2.0 / EntityOS build, integration, falsification, release-candidate and target-like testing

## 1. Default test surface

For every test that does **not** require evidence from the owner's actual physical workstation, workers MUST prefer the owner-provisioned Ubuntu VPS sandbox / `clay-direct-dev` target-like environment over the owner's local machine.

The VPS sandbox is the primary target-like execution surface for:

- clean-host install and uninstall simulations;
- package/install/upgrade/reinstall paths;
- release ZIP extraction and one-handoff bootstrap tests;
- service lifecycle and restart/readback tests;
- filesystem layout and permissions simulations;
- process crashes, forced restarts and recovery tests;
- database/state migration and corruption/fail-closed tests;
- hostile-twin and adversarial input tests;
- network/API integration tests;
- dependency/version incompatibility tests;
- resource pressure tests bounded by host-health guards;
- multi-process concurrency and race tests;
- provider-agent substitution tests;
- any other test that can be faithfully represented inside an isolated Ubuntu sandbox.

Do NOT defer these tests merely because final product installation ultimately targets a local machine.

## 2. Local machine is a final physical-evidence gate, not the normal development sandbox

The owner's actual local machine is reserved for evidence that cannot be honestly minted on the VPS sandbox, including only when relevant:

- real physical camera/microphone/display/device enumeration;
- real desktop/browser/OS permission prompts and revocation behavior;
- actual workstation-specific paths, user session integration, GUI lifecycle or hardware drivers;
- final clean-machine/user-handoff acceptance where the product law explicitly requires the real host;
- other explicitly host-physical invariants that cannot be simulated without changing the claim scope.

If the invariant is reproducible in the Ubuntu VPS sandbox, run it there first.

VPS sandbox PASS != physical-local PASS. Promote only the exact scope executed.

## 3. Sandbox freedom

Inside an admitted disposable sandbox, workers have broad authority to run high-information tests and may mutate or destroy **sandbox-local** state as needed to exercise the product, including:

- create/delete/rename/corrupt files and directories inside sandbox-owned roots;
- install/remove packages inside the sandbox;
- start/stop/kill sandbox-local processes and services;
- wipe/recreate sandbox-local databases and caches;
- change sandbox-local permissions, users, groups and environment variables where the isolation mechanism permits it;
- simulate crashes, partial writes, stale locks, disk pressure and restart scenarios;
- compile, benchmark, fuzz and stress the product;
- use network access required by an admitted test/provider route.

This authority is for the sandbox namespace only.

## 4. Host survival fence

Workers MUST NOT intentionally mutate or delete unrelated owner-host state.

Before any potentially destructive test, establish a positive sandbox boundary. At least one of the following must be true and recorded:

- disposable VM/container/nspawn/LXC/Docker/Podman namespace with its own root filesystem;
- dedicated throw-away filesystem/root mounted specifically for the test;
- equivalent isolation with a documented reset/rebuild path.

Never run broad destructive commands against host `/`, host `/home`, host `/var`, host boot configuration, host firewall/SSH access, or unrelated persistent volumes.

Do not disable the host's ability to reconnect/recover.
Do not erase canonical repositories, owner data, credentials, or unrelated services.

If sandbox identity cannot be proven, destructive mode is FAIL CLOSED and the worker must create/fix the sandbox boundary first.

## 5. Host-health guards

High-load tests are allowed when bounded so the server remains recoverable.

Required guards for stress/resource tests:

- preserve SSH/control-plane access;
- retain host disk free-space reserve;
- retain host memory/process headroom;
- use timeout/cgroup/systemd/container limits where applicable;
- keep an independent kill/reset path;
- never intentionally fill the host root filesystem;
- never intentionally exhaust host-wide PID/file-descriptor space;
- record the resource limits used in the runtime receipt.

A host-health guard firing is `INFRA_AUTH_TRANSPORT_QUOTA` or bounded test termination, not a product PASS.

## 6. Exact target-like environment

The preferred VPS sandbox should approximate the intended Ubuntu target as closely as practical:

- same Ubuntu release/architecture where known;
- same package/runtime versions where part of the claim;
- clean user/home/service layout;
- no hidden dependency on the development checkout;
- install from the exact accepted release artifact where testing release/handoff behavior;
- separate canonical persistent-state path from disposable package/cache paths;
- explicit network, filesystem and service permissions;
- restart/reopen/readback after relevant stateful operations.

Workers should improve the sandbox fidelity when a mismatch blocks a meaningful discriminator rather than moving the test to the owner's workstation by default.

## 7. Provider / coding-agent substitution

Owner directive: GLM-5.3-Flash may be used as an alternative coding/agent model when Claude Code is unavailable or an API-backed agent is useful.

Provider use is allowed only through a configured secret boundary. Never commit, print, echo, log, persist in receipts, or place API tokens in repository files, prompts, shell history, test fixtures or artifacts.

The owner supplied a credential out-of-band in the active session; workers must consume it only from a secret/environment facility such as `ZAI_API_KEY`, `GLM_API_KEY` or the provider's supported secret store.

Exact endpoint/model names and billing/free-status MUST be verified against current official provider documentation before network use. Provider execution never changes canonical truth/evidence rules.

GLM-generated work is `ORGAN_NOT_ENTITY` and must pass the same source/test/evidence gates as work from Claude, GPT, Codex or any other worker.

## 8. Worker routing rule

Before stating `needs local-machine test`, a worker MUST classify the missing invariant:

- `VPS_SANDBOX_REPRESENTABLE` -> execute in VPS sandbox now;
- `PHYSICAL_LOCAL_ONLY` -> preserve as final/local gate with exact reason;
- `UNKNOWN_FIDELITY` -> first improve/measure sandbox fidelity, do not default to local.

Every deferral to local must name the exact property that the sandbox cannot reproduce.

## 9. Runtime-credit scope

A successful VPS sandbox run may mint only the scope actually exercised, for example:

- target-like clean-host credit;
- VPS target-environment component runtime credit;
- restart/readback/recovery credit;
- release-install/handoff simulation credit.

It does not by itself mint:

- real physical workstation hardware credit;
- real device/GUI permission credit;
- physical GRID10 credit where actual physical devices are required;
- whole-product acceptance unless the current completion law explicitly defines that gate as satisfied by this environment.

## 10. Priority

Workers should now aggressively convert repository-only acceptance into executable sandbox evidence.

Preferred flow:

`accepted exact source/artifact -> fresh Ubuntu VPS sandbox -> install/run/falsify -> restart/readback -> receipt -> exact scoped promotion -> next boundary`

This directive supersedes any stale worker interpretation that ordinary target-like tests must wait for the owner's local machine.
