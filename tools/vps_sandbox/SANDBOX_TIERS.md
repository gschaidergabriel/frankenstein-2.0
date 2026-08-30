# Frankenstein 2.0 — VPS Sandbox Tiers

Status: execution guidance under `workpackages/VPS_SANDBOX_EXECUTION_AUTHORITY.md`.

The objective is to execute the highest-information test on the VPS while preserving the owner host. Workers choose the **lowest tier that is both safe and faithful** to the invariant being tested.

## S1 — Disposable Ubuntu OCI userspace

Preferred backend: Podman or Docker, image `ubuntu:24.04`.

Use for ordinary destructive userspace work:

- package/dependency installation experiments;
- filesystem corruption/rename/delete tests inside the container;
- application crash/restart loops;
- DB migration/corruption/recovery tests;
- release extraction/install simulations that do not require a booted systemd host;
- concurrency/fuzz/adversarial input tests;
- coding-agent/API integration tests;
- bounded resource-pressure tests.

Required properties:

- checkout mounted read-only;
- writable private copy inside disposable container;
- no privileged container;
- no host PID namespace;
- no host filesystem root bind;
- resource limits;
- network disabled unless the test needs it;
- container destroyed after the test.

## S2 — Disposable Ubuntu 24.04 systemd-nspawn root

Preferred when systemd/userspace fidelity matters more than OCI convenience.

Base root:

`/var/lib/frankenstein2-sandbox-images/ubuntu-24.04-base`

The base is never a test root. Each test receives a disposable clone beneath the approved sandbox root.

Use for:

- service/unit lifecycle;
- user/group/permission behavior requiring a fuller Ubuntu filesystem;
- filesystem layout and package-manager behavior;
- target-like process hierarchy and namespace behavior;
- tests whose result changes because OCI is too thin.

Network defaults to a private namespace. Network-enabled nspawn tests use a separate veth and must not silently share the host network.

## S3 — Disposable VM / separate kernel

Required for tests that can endanger or materially alter the host kernel/network/boot domain or that make claims about a real machine reboot/kernel lifecycle, for example:

- kernel/module experiments;
- host firewall/routing replacement;
- reboot/power-cycle semantics;
- destructive block-device/filesystem tests that need a real virtual disk;
- privilege-escape/security tests where a container boundary is not sufficient;
- kernel-version-specific behavior.

Use KVM/QEMU/Incus/libvirt or another admitted disposable VM surface when available. A container/nspawn result must not be relabeled as separate-kernel evidence.

If S3 is required but no safe VM backend exists, the worker reports `SANDBOX_CAPABILITY_BLOCKED` and improves the VPS sandbox capability. It does **not** default to the owner's workstation.

## S4 — Physical local workstation

Reserved for irreducible physical evidence only:

- actual camera/microphone/display/device enumeration;
- actual workstation GUI/session integration;
- real native OS permission prompts/revocation;
- actual hardware drivers/peripherals;
- final physical one-handoff acceptance when the product completion law requires it.

Before selecting S4, record the precise physical property that S1/S2/S3 cannot reproduce.

## Decision table

```text
userspace + destructive?              -> S1
systemd/full Ubuntu userspace?        -> S2
separate kernel/reboot/block device?  -> S3
actual physical device/workstation?   -> S4
uncertain?                            -> improve/measure sandbox fidelity first
```

## Evidence scope

Sandbox tier is part of the receipt. It defines what can be promoted.

```text
S1/S2/S3 PASS != S4 physical-local PASS
S1 PASS != booted-systemd evidence when systemd was not actually booted
S2 PASS != separate-kernel/reboot evidence
S3 PASS != physical-device evidence
```

Promote only what actually executed and was independently read back.
