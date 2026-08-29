# WORKER DIRECTIVE — TARGET HOST REALITY TWIN / COMPLETION EPISTEMICS

Date: 2026-08-29
Status: PROJECT OWNER DIRECTIVE

All workers touching portable delivery, host integration, perception, voice/audio, browser, service lifecycle, permissions, update/rollback or VPS bridge behavior must read:

1. `architecture/TARGET_HOST_REALITY_TWIN_AND_COMPLETION_EPISTEMICS.md`
2. `workpackages/TARGET_HOST_REALITY_TWIN_PHASE.json`
3. `schemas/TARGET_HOST_PROFILE.schema.json`
4. `schemas/TARGET_OBLIGATION.schema.json`
5. existing `PRODUCT_COMPLETION_LAW.md`

## Owner correction

The VPS sandbox is currently too homogeneous to predict enough real Ubuntu workstation failures. At the same time, Frankenstein has repeatedly shown a premature-completion pattern on foreign-host work: it tends to inspect expected artifacts and conclude completion without discovering omitted target obligations.

Treat this as an architecture defect.

## Mandatory semantic changes

For host-affecting work:

- do not define completion as files/services/commands created;
- define a target obligation set first;
- absence of required evidence is `UNKNOWN`, not `PASS`;
- verify by independent target readback, not only the implementation path;
- include a negative-space scan for missing, stale, wrong-owner, wrong-user, wrong-session and unproven state;
- include at least one counterevidence probe per mandatory obligation;
- require restart/rebind/revoke/hotplug behavior where relevant;
- explicitly record test fidelity `T0..T4`;
- never promote T0-T3 simulation to T4 physical evidence;
- `service active` is not equivalent to usable device/session integration;
- `command exited 0` is not completion evidence;
- `no visible error` is not a pass condition.

## Immediate work allocation

Preferred independent lanes:

### Lane A — F2-WP-1200
Implement TargetObligation + TargetCompletionReport semantics and deterministic validator/falsifiers.

### Lane B — F2-WP-1201
Implement read-only non-secret target fingerprint collector. Unknown real-host facts must remain UNKNOWN.

### Lane C — F2-WP-1202
Bootstrap Ubuntu userspace twin with systemd system/user/session topology. Do not assume the exact owner's Ubuntu version until target profile evidence exists.

### Lane D — F2-WP-1203
Build session multimedia topology: session D-Bus, xdg-desktop-portal boundary, PipeWire/WirePlumber, synthetic audio/video/display/browser endpoints.

### Lane E — F2-WP-1204
Build deterministic FaultScenario engine: permissions, device hotplug/reset, EBUSY, PipeWire reset/xrun, portal denial, systemd-user loss, network/bridge, filesystem/package, process/reboot/session faults.

### Lane F — F2-WP-1206
Build independent negative-space verifier. It must not trust installer self-report.

### Lane G — F2-WP-1207/1208
Exercise the exact portable release path in the hostile twin and run sustained heterogeneous chaos scenarios.

Do not wait for physical access to implement T0-T2. T3 begins when a sanitized target trace/profile exists. T4 remains final local acceptance.

## Hardware family seed, not exact-target truth

Owner target family: Minisforum UM790 Pro / Ryzen 9 7940HS / Radeon 780M.

Use hardware-family reports only as fault seeds. Do not assert that a reported UM790 defect exists on the owner's exact unit without target evidence.

High-value fault seeds:

- suspend/resume generation changes;
- USB4/display recovery;
- Radeon/compositor reset/black-screen recovery;
- Wi-Fi disconnect/reconnect;
- shared-memory pressure affecting iGPU + cognition;
- audio graph route changes;
- real device hotplug;
- portal and session permission churn.

## Completion wording

Allowed host-level top statuses:

- `COMPLETE_AT_TWIN_SCOPE`
- `READY_FOR_PHYSICAL_ACCEPTANCE`
- `PHYSICALLY_ACCEPTED`
- `DEGRADED`
- `BLOCKED`
- `UNKNOWN`

Unscoped `COMPLETE` is prohibited for foreign-host transfer/integration.

## End state

The twin succeeds when it repeatedly finds defects that would otherwise first appear on the real Ubuntu machine. It fails if it merely makes CI greener.
