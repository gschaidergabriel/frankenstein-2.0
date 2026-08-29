# Frankenstein 2.0 — VPS Build / Local Acceptance Contract

Status: PROJECT-OWNER DELIVERY INVARIANT
Date: 2026-08-29

## Principle

The canonical engineering lane builds Frankenstein 2.0 as far as technically possible on the authorized VPS/bridge development environment. Final real-machine integration and product acceptance are performed locally with Claude Code + Opus (or another explicitly chosen local host), because the real user's hardware, OS permissions, sensors, browser session and desktop runtime exist there.

This division must not be misread as permission to defer architecture or unfinished implementation to the local acceptance step.

Target law:

`VPS BUILD = IMPLEMENT + SIMULATE + TEST + PACKAGE + PREWIRE`

`LOCAL CLAUDE/OPUS = HOST/HARDWARE BIND + VERIFY + ACCEPT + EDGE FIX ONLY`

## What must be finished before local handoff

The VPS-side build should deliver, wherever technically possible:

- complete host-independent source implementation;
- stable semantic contracts and schemas;
- deterministic policy/control logic;
- state migrations and persistent-state layout;
- bridge protocol and local/remote boundary definitions;
- simulator/fake-device adapters for hardware-dependent components;
- unit, integration, failure-injection, restart, concurrency and resource tests;
- replay fixtures and expected receipts;
- dashboard/backend contracts and permission model;
- install/update/rollback/uninstall logic that can be exercised without the real device where possible;
- release ZIP layout, manifest, hashes and installer routes;
- explicit capability degradation when a host lacks a native primitive;
- a machine-readable local acceptance checklist/report schema.

## What may legitimately remain local

The local Claude Code/Opus acceptance lane may perform work that fundamentally requires the real target machine, including:

- OS permission prompts and durable grants;
- actual camera/display/PipeWire/portal binding;
- actual browser CDP/DOM/AX attachment to the user's browser profile;
- actual microphone/audio-device selection;
- local service/supervisor registration and desktop-session integration;
- host-native lifecycle hook mapping when capability discovery confirms the concrete version/API;
- real sensor calibration, latency measurement and resource characterization;
- real dashboard permission interaction;
- final physical end-to-end acceptance and small target-specific edge fixes.

## What local acceptance must NOT have to invent

If Claude Code/Opus must design any of the following from scratch during final acceptance, VPS-side assembly is incomplete:

- canonical state authority;
- GRID10/GWT semantics;
- world-model epistemics;
- permission/capability semantics;
- ObserveIntent/active-sensing semantics;
- perception worker scheduling/backpressure policy;
- temporal fusion rules;
- bridge payload authority rules;
- memory/observation separation;
- EffectGate/CompletionGate semantics;
- install topology or state ownership;
- host-switch identity semantics.

## Perception Fabric application

For Perception Fabric specifically, VPS-side assembly must provide the contracts and tested implementations for `PerceptionSource`, `PerceptionCapabilitySnapshot`, `ObserveIntent`, dynamic `0..4` worker allocation, single-owner bounded capture broker, temporal observation windows, typed bridge envelopes, audit receipts, VisualNeed-to-ObserveIntent compilation, failure/revocation behavior, and sustained simulated multi-source tests.

Local acceptance should then connect these finished contracts to real camera/display/browser/activity adapters and prove the hardware gates.

## Acceptance consequence

A feature is not considered ready for final local acceptance merely because its architecture is documented. It should arrive with executable source plus deterministic tests/fixtures for every part that does not intrinsically require the user's physical machine.

Conversely, absence of a physical camera/display/desktop in repository CI must not be used to pretend physical integration passed. The VPS/CI lane proves the host-independent implementation and simulations; Claude Code/Opus on the actual machine proves the final hardware/runtime integration.
