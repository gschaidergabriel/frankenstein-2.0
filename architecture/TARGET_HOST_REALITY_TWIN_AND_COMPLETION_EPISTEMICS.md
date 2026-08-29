# Frankenstein 2.0 — Target Host Reality Twin + Completion Epistemics

Status: PROJECT-OWNER ARCHITECTURE INVARIANT / REQUIRED BEFORE PORTABLE RELEASE CLAIM
Date: 2026-08-29

## 0. Why this exists

Frankenstein 2.0 currently has a structural asymmetry:

- repository/VPS work can be highly complete, deterministic and internally consistent;
- a real Ubuntu desktop host is stateful, permissioned, device-driven, timing-sensitive and heterogeneous;
- the same agent that builds a change can then inspect the artifacts it expected to create and conclude that the target is complete without discovering omitted host obligations.

This is not only a missing test problem. It is a **completion epistemology problem**.

The failure mode is:

```text
PLAN -> IMPLEMENT EXPECTED ARTIFACTS -> CHECK EXPECTED ARTIFACTS -> DECLARE COMPLETE
```

while the real requirement is:

```text
TARGET OBLIGATIONS
-> IMPLEMENT
-> INDEPENDENT TARGET READBACK
-> NEGATIVE-SPACE SEARCH
-> FAILURE INJECTION
-> RESTART / REBIND / REVOKE / HOTPLUG
-> OBSERVE REAL EFFECT
-> ONLY THEN ACCEPT
```

A builder can be correct about what it implemented and still be wrong about what the target required.

This document therefore introduces two coupled systems:

1. **Target Host Reality Twin** — a VPS/sandbox environment designed to reproduce the *failure surface* of the final Ubuntu host, not merely its nominal software stack.
2. **Completion Epistemics** — a target-relative proof model that prevents self-confirming completion claims.

---

## 1. Core diagnosis: closed-world completion fallacy

The observed failure class is called here the **Closed-World Completion Fallacy**.

Definition:

> A change is judged complete because all artifacts inside the builder's model of the task exist, while obligations absent from that model are never queried and therefore silently disappear.

Typical signatures:

- build agent says a remote installation is complete before target-side lifecycle readback;
- it verifies files/services it created but not the surrounding user session, permissions, devices, default routes or post-restart behavior;
- it treats absence of an error as positive evidence;
- it uses the same assumptions to both generate and verify the implementation;
- it sees `service active`, `file exists`, or `command exited 0` and promotes that to user-visible completion;
- after being challenged, it looks again but searches mostly for the objects it already knows about.

This explains why self-modification can appear much more successful than transferring a change to another host. In self-modification, the working context already contains most of the hidden assumptions and local topology. On a foreign host, those assumptions are external state and must be discovered.

### Hard correction

```text
BUILT != INSTALLED
INSTALLED != BOUND
BOUND != RUNNING
RUNNING != USABLE
USABLE_ONCE != RESTART_SAFE
EXECUTED != EFFECT_OBSERVED
NO_ERROR != PASS
MISSING_EVIDENCE != PASS
SELF_REPORT != COMPLETION_EVIDENCE
SIMULATION_PASS != PHYSICAL_PASS
REPOSITORY_PASS != TARGET_PASS
```

Any missing required evidence is `UNKNOWN`, never implicit `PASS`.

---

## 2. Target baseline: what is known, and what is not

Known hardware family from the owner target description: **Minisforum UM790 Pro**.

Vendor-published hardware baseline includes:

- AMD Ryzen 9 7940HS, 8C/16T;
- AMD Radeon 780M iGPU;
- DDR5 dual-channel memory;
- dual M.2 2280 PCIe 4.0 storage slots;
- Wi-Fi 6E / Bluetooth;
- 2.5G Ethernet;
- dual USB4;
- HDMI outputs;
- analog audio jack and digital microphone.

Reference: https://store.minisforum.com/products/minisforum-um790-pro-mini-pc

The exact final Ubuntu target fingerprint is **not yet verified by repository evidence**. Therefore the sandbox must not hard-code an Ubuntu version, kernel version, GNOME version, BIOS version, Wi-Fi chipset, audio routing, display topology or browser version merely because those are plausible.

Until a target-side probe is captured, these fields remain `UNKNOWN`.

This matters because community reports for the UM790 Pro family include suspend/USB4/display and GPU-related failures under some BIOS/kernel/workload combinations. Those reports are useful as fault seeds, not proof that the owner's exact unit has the same defect.

---

## 3. The Reality Twin goal: reproduce the failure surface, not the logo

A VPS cannot physically emulate every behavior of a Phoenix APU, Radeon 780M, BIOS/AGESA, USB4 controller, real webcam, real microphone or monitor.

Therefore the goal is not false hardware equivalence.

The goal is:

> **Maximize the probability that host-integration defects are discovered before the release reaches the physical target.**

The twin is a layered fidelity system.

### Fidelity levels

#### T0 — Contract simulation
Pure deterministic models/fakes.

Useful for:
- state machines;
- permission generations;
- stale authority;
- queue bounds;
- scheduling;
- epistemic typing;
- restart invariants.

Cannot grant hardware credit.

#### T1 — Ubuntu userspace twin
A VM/container/rootfs matching the target's observed distro/package/session shape as closely as possible.

Must reproduce where feasible:
- exact `/etc/os-release` family;
- package versions or bounded version ranges;
- systemd system + user managers;
- user UID/session topology;
- `XDG_RUNTIME_DIR` and user D-Bus behavior;
- PipeWire/WirePlumber services;
- xdg-desktop-portal and compositor backend packages;
- browser package form (Snap/deb/etc.);
- permissions, groups, filesystem paths and service locations;
- target-like resource ceilings.

#### T2 — Device/session fault twin
Userspace device endpoints and adapters with controlled failure injection.

Simulate at minimum:
- device absent;
- device appears late;
- device disappears while in use;
- device ID/name changes after reset;
- default audio source/sink changes;
- capture owner gets `EBUSY`;
- permission denied, revoked or portal cancelled;
- portal service is active but no usable capture path exists;
- PipeWire graph node disappears/reappears;
- audio xrun / delayed process callback;
- browser CDP/DOM channel unavailable while rendered pixels remain available, and inverse;
- monitor count/resolution/scale changes;
- Wayland/X11 mismatch;
- D-Bus session disappears and returns;
- systemd user manager not reachable from a system context;
- package dependency missing or version skewed;
- filesystem becomes read-only / disk low / permission changes;
- network latency, packet loss, DNS failure, bridge disconnect and reconnect;
- suspend/resume-equivalent lifecycle invalidation;
- process kill between write and readback;
- reboot between installation phases;
- clock skew and stale observations;
- CPU/memory pressure causing perception degradation.

#### T3 — Target trace replay
A sanitized target-side fingerprint and event trace captured from the real machine is replayed against the twin.

This is how the twin becomes **Andreas-host-shaped** rather than generic-Ubuntu-shaped.

Trace replay should include topology/state transitions, not private user content.

Examples:
- device add/remove sequence;
- PipeWire node IDs changing;
- portal response lifecycle;
- service start ordering;
- D-Bus owner changes;
- audio default route changes;
- monitor topology transitions;
- browser start/stop and capability changes;
- bridge reconnect timing;
- restart and login ordering.

#### T4 — Physical host acceptance
Real target hardware, real OS permissions, real user session, real devices.

Only T4 can grant physical completion credit.

---

## 4. Why Ubuntu desktop failures differ from VPS failures

The VPS is usually homogeneous: stable network interface, no user desktop session, no real audio graph, no portal permission UX, no hotplugging monitor/webcam/microphone, and fewer firmware/device lifecycle states.

A desktop path is instead a chain of independently failing authorities:

```text
Frankenstein process
  -> correct user identity
  -> live login session
  -> XDG_RUNTIME_DIR
  -> session D-Bus
  -> xdg-desktop-portal
  -> compositor portal backend
  -> PipeWire/WirePlumber
  -> current permission store
  -> current device/node
  -> current default route
  -> application adapter
  -> real physical device
```

For Wayland screen/camera capture, portal-mediated access is explicitly tied to D-Bus and PipeWire permissions. A service merely being active does not prove the requested source is visible or authorized.

Research references:
- https://flatpak.github.io/xdg-desktop-portal/docs/pipewire.html
- https://pipewire.pages.freedesktop.org/pipewire/page_portal.html
- https://docs.pipewire.org/page_audio.html
- https://docs.pipewire.org/group__pw__stream.html
- Ubuntu 24.04 release subsystem versions: https://documentation.ubuntu.com/release-notes/24.04/

PipeWire explicitly models device plug/unplug, default devices, latency changes and deadline/xrun behavior. Those states must become ordinary test inputs rather than surprises discovered only after installation.

---

## 5. Completion Epistemics: target-relative proof, not builder confidence

Every host-affecting change must define a **Target Obligation Set** before implementation.

An obligation is not `install file X`.

An obligation is a target-visible invariant such as:

```text
O: after user login and Frankenstein restart, the enabled microphone source is discoverable,
   permission-valid, openable by the single capture owner, produces fresh samples,
   survives one PipeWire restart, and produces an audit receipt bound to the new device generation.
```

Each obligation must declare:

- target scope;
- preconditions;
- action;
- expected externally observable state;
- independent readback probe;
- negative evidence probe;
- restart/rebind requirement;
- fault cases;
- minimum fidelity level needed for credit;
- whether physical T4 evidence is mandatory.

### Evidence separation

The implementation path must not be the sole verifier.

Preferred hierarchy:

1. deterministic verifier/probe;
2. independent OS readback;
3. stored receipt/log with exact source identity;
4. second agent/model critique only as supplemental evidence.

LLM self-assertion is never primary completion evidence.

### Negative-space scan

Before a target change can be accepted, the verifier must ask mechanically:

```text
What target capabilities were expected?
Which were actually observed?
Which expected objects are absent?
Which objects exist but are stale, disabled, wrong-owner, wrong-user, wrong-session or unproven?
What changed unexpectedly?
What remained UNKNOWN?
```

This is the inverse of checking only what the installer says it created.

### Counterevidence-first rule

For each claimed success, define at least one probe that would succeed if the claim were false.

Examples:

Claim: screen capture works.
Counterevidence probes:
- portal permission absent/revoked;
- PipeWire node absent;
- frame freshness frozen;
- frame sequence not increasing;
- wrong monitor source;
- session D-Bus unavailable;
- captured dimensions inconsistent with selected display.

Claim: service installed.
Counterevidence probes:
- service belongs to wrong user;
- process starts before runtime dir exists;
- restart loses state path;
- log says active but socket/readback absent;
- unit survives shell but not logout/login/reboot.

---

## 6. Target Host Fingerprint — build the twin from observation

A target-side, read-only probe should produce `TARGET_HOST_PROFILE.json`.

It should collect non-secret technical state including:

### Machine / firmware
- DMI model and board identifiers;
- BIOS/UEFI version/date;
- CPU model;
- RAM total;
- PCI device IDs + kernel drivers;
- USB topology and device IDs;
- storage devices/filesystems/free space;
- kernel command line.

### OS
- `/etc/os-release`;
- kernel version;
- architecture;
- key package versions;
- Snap package inventory relevant to browser/runtime;
- Python/runtime versions actually used by F2.

### Session
- current UID;
- `loginctl` session type/class/state;
- Wayland vs X11;
- desktop environment;
- `XDG_RUNTIME_DIR` existence/ownership;
- session D-Bus reachability;
- systemd user manager reachability.

### Multimedia
- PipeWire version;
- WirePlumber version;
- portal version/backend;
- `wpctl status` topology digest;
- source/sink/node identities;
- default devices;
- camera/video device identities;
- monitor/display topology and scale metadata where available.

### Browser
- browser type/version/package form;
- CDP/remote debugging capability if enabled;
- DOM/AX capability route;
- rendered-capture route.

### Frankenstein-relevant filesystem/service topology
- canonical state directory;
- service/unit locations;
- executable paths;
- owner/group/mode;
- local bridge paths;
- host adapter capability status.

Secrets, user documents, clipboard data, raw camera frames, raw microphone audio and credentials are out of scope.

The profile must be hashed and versioned. Any material target change creates a new generation.

---

## 7. Fault catalog required in the sandbox

The sandbox should contain a first-class `FaultScenario` engine.

### Permission / identity faults
- wrong UID;
- no user session;
- expired/revoked capability;
- stale permission digest;
- portal deny/cancel;
- permission survives UI state but not backend state;
- service launched as root while required portal is user-session only.

### Audio faults
- source missing on boot;
- source appears after service start;
- default source switches;
- device removed/reinserted with new node ID;
- PipeWire restart;
- WirePlumber restart;
- xrun/deadline miss;
- format/rate mismatch;
- microphone muted at policy layer;
- device busy;
- one-way capture silence despite open stream.

### Video / screen faults
- camera `EBUSY` from duplicate opener;
- camera unplug/replug;
- portal grant denied/revoked;
- portal backend missing;
- PipeWire node created but no frames;
- stale/frozen frame source;
- monitor disappears;
- resolution/scaling change;
- multi-monitor reorder;
- Wayland source unavailable from system service context;
- rendered browser image available while structural channel fails;
- structural channel available while visual output is occluded/stale.

### GPU / display faults
- GPU work stalls;
- compositor restart;
- display blank/recover;
- hardware acceleration disabled;
- memory pressure on shared iGPU/system RAM;
- post-suspend equivalent device generation change.

No VPS simulation of these faults may be labelled an actual Radeon 780M physical test.

### Network / bridge faults
- latency spikes;
- packet loss;
- DNS failure;
- TCP reset;
- VPS bridge unavailable;
- reconnect with stale queued intents;
- clock offset/drift;
- duplicated/delayed event delivery.

### Filesystem / installation faults
- package manager lock;
- package missing;
- version skew;
- state dir exists with wrong ownership;
- read-only path;
- low disk;
- interrupted migration;
- partial install from prior version;
- stale plugin/cache copy;
- host adapter switched while state remains.

### Lifecycle faults
- process killed mid-write;
- logout/login;
- user manager restart;
- reboot;
- suspend/resume-equivalent epoch change;
- service starts before dependencies;
- service starts after dependent consumer;
- stale PID/socket after crash.

---

## 8. Sandbox topology

Recommended target-twin topology:

```text
VPS
|
+-- F2 canonical repo
|
+-- Target Host Twin Controller
|     +-- target profile generation
|     +-- obligation compiler
|     +-- fault scenario scheduler
|     +-- trace replay
|     `-- independent verifier
|
+-- Ubuntu software twin (VM preferred where available)
|     +-- systemd system manager
|     +-- simulated/logged-in user
|     +-- systemd --user
|     +-- session D-Bus
|     +-- GNOME/Wayland-equivalent session boundary where feasible
|     +-- xdg-desktop-portal + backend
|     +-- PipeWire + WirePlumber
|     +-- browser/adapters
|     `-- Frankenstein installed exactly as release ZIP would install it
|
+-- Synthetic Device Fabric
|     +-- camera source adapter
|     +-- display source adapter
|     +-- browser rendered source
|     +-- browser structural source
|     +-- audio source/sink
|     +-- coarse user activity source
|     `-- hotplug/reset/latency/permission injection
|
`-- Evidence Store
      +-- exact scenario
      +-- target-profile SHA
      +-- package SHA
      +-- fault timeline
      +-- external readbacks
      +-- negative-space result
      `-- acceptance result
```

A VM is preferable to a process-only fake for systemd/session/filesystem/package behavior. Synthetic adapters remain necessary because a VM on a remote VPS cannot reproduce the physical UM790 Pro peripherals faithfully.

---

## 9. Release confidence must be a vector

Do not report one misleading scalar such as `88% complete` without dimensions.

At minimum track:

```text
repo_contracts
repo_component_ci
ubuntu_userspace_twin
session_permission_twin
multimedia_fault_twin
restart_recovery
portable_installer
trace_replay_against_target_profile
physical_target_acceptance
```

Each dimension has an evidence level:

- `NONE`
- `T0_CONTRACT`
- `T1_USERSPACE`
- `T2_FAULT_TWIN`
- `T3_TARGET_TRACE`
- `T4_PHYSICAL`

No high score in one dimension can silently substitute for a missing dimension.

---

## 10. Handoff law for Frankenstein building on a foreign host

Before Frankenstein may say a host transfer/build is complete, it must produce a `TargetCompletionReport` containing:

1. exact target profile generation;
2. exact desired obligation set;
3. observed obligation results;
4. negative-space scan;
5. all UNKNOWN obligations;
6. all target deltas from expected profile;
7. restart/readback results;
8. permission/device generation results;
9. fault scenarios exercised and fidelity level;
10. evidence that the running target, not the installer process, produced the expected effect;
11. explicit list of anything still requiring physical/user action.

If any required obligation is `UNKNOWN`, the overall result is not `COMPLETE`.

Allowed top-level outcomes:

```text
COMPLETE_AT_TWIN_SCOPE
READY_FOR_PHYSICAL_ACCEPTANCE
PHYSICALLY_ACCEPTED
DEGRADED
BLOCKED
UNKNOWN
```

`COMPLETE` without scope is prohibited for host-transfer work.

---

## 11. Relationship to existing F2 laws

This architecture strengthens, not replaces:

- `PRODUCT_COMPLETION_LAW.md`;
- `architecture/VPS_BUILD_TO_LOCAL_ACCEPTANCE_CONTRACT.md`;
- `architecture/PORTABLE_HOST_HARNESS_AND_DISTRIBUTION_CONTRACT.md`;
- `architecture/PERCEPTION_FABRIC.md`;
- `architecture/PERCEPTION_FABRIC_HARDENING_20260829.md`.

In particular:

> VPS/repo completeness must approach the real host as far as technically possible, but simulated fidelity must never be promoted to physical evidence.

The purpose of the Reality Twin is to **shrink the VPS→physical gap**, not hide it.

---

## 12. Immediate owner directive

All workers touching portable delivery, perception host adapters, audio/voice, browser integration, local services, permissions, update/rollback or VPS bridge behavior must now design against this model.

Priority order:

1. target profile schema + read-only collector;
2. target obligation / completion report schema;
3. Ubuntu userspace twin bootstrap;
4. session/D-Bus/portal/PipeWire synthetic topology;
5. fault scenario engine;
6. independent negative-space verifier;
7. install the release candidate inside the twin using the same one-handoff path intended for the real machine;
8. replay target traces when a real target profile becomes available;
9. require T4 physical acceptance for final product completion.

The target is not to make the sandbox look impressive. The target is to make it **hostile in the same ways a real Ubuntu workstation is hostile**, so omissions become visible before handoff.
