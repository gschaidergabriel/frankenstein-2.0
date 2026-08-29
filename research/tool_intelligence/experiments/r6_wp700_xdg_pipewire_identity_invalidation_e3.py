#!/usr/bin/env python3
"""Trigger-6 E3 synthetic falsifier for XDG/PipeWire capture identity rules.

Research-only. This does not open a portal, PipeWire remote, camera/display, provider,
network effect, or F2 runtime. It mechanically tests the proposed E2 lifecycle fence:
F2 generation + expected pipewire-serial + native ACTIVE state must all agree before a
native buffer may become eligible for CaptureFrameRef publication.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json


@dataclass(frozen=True)
class Binding:
    source_generation: int
    pipewire_serial: int
    host_grant_valid: bool
    native_state: str


@dataclass(frozen=True)
class Observation:
    event: str
    observed_generation: int
    observed_pipewire_serial: int | None
    restore_token_present: bool = False
    native_permission_observed: bool = True


@dataclass(frozen=True)
class Decision:
    allow_frame_publication: bool
    invalidate_host_grant: bool
    require_generation_increment_before_reopen: bool
    reason: str


def decide(binding: Binding, obs: Observation) -> Decision:
    terminal = {"SESSION_CLOSED", "DBUS_OWNER_LOST", "PIPEWIRE_ERROR", "PIPEWIRE_UNCONNECTED"}
    if obs.event in terminal:
        return Decision(False, True, True, "native-session-or-stream-invalidated")

    if obs.event == "RESTORE_ATTEMPT":
        if not obs.native_permission_observed:
            return Decision(False, True, False, "restore-token-is-not-permission-proof")
        if obs.observed_pipewire_serial is None:
            return Decision(False, True, True, "restored-stream-missing-serial")
        if obs.observed_pipewire_serial != binding.pipewire_serial:
            return Decision(False, True, True, "restored-native-stream-instance-changed")
        return Decision(False, False, True, "restored-session-requires-new-f2-generation-before-publication")

    if binding.native_state != "ACTIVE" or not binding.host_grant_valid:
        return Decision(False, True, True, "binding-not-currently-admissible")

    if obs.observed_generation != binding.source_generation:
        return Decision(False, True, True, "f2-generation-mismatch")

    if obs.observed_pipewire_serial != binding.pipewire_serial:
        return Decision(False, True, True, "pipewire-serial-mismatch-node-id-reuse-safe")

    return Decision(True, False, False, "current-active-binding")


CASES = [
    {
        "id": "stable-active-same-serial",
        "binding": Binding(7, 1001, True, "ACTIVE"),
        "obs": Observation("BUFFER", 7, 1001),
        "expected": Decision(True, False, False, "current-active-binding"),
    },
    {
        "id": "legacy-node-id-could-be-reused-but-serial-changed",
        "binding": Binding(7, 1001, True, "ACTIVE"),
        "obs": Observation("BUFFER", 7, 1002),
        "expected": Decision(False, True, True, "pipewire-serial-mismatch-node-id-reuse-safe"),
    },
    {
        "id": "session-closed-before-next-buffer",
        "binding": Binding(7, 1001, True, "ACTIVE"),
        "obs": Observation("SESSION_CLOSED", 7, 1001),
        "expected": Decision(False, True, True, "native-session-or-stream-invalidated"),
    },
    {
        "id": "dbus-owner-lost",
        "binding": Binding(7, 1001, True, "ACTIVE"),
        "obs": Observation("DBUS_OWNER_LOST", 7, 1001),
        "expected": Decision(False, True, True, "native-session-or-stream-invalidated"),
    },
    {
        "id": "pipewire-error",
        "binding": Binding(7, 1001, True, "ACTIVE"),
        "obs": Observation("PIPEWIRE_ERROR", 7, 1001),
        "expected": Decision(False, True, True, "native-session-or-stream-invalidated"),
    },
    {
        "id": "stale-f2-generation",
        "binding": Binding(8, 2001, True, "ACTIVE"),
        "obs": Observation("BUFFER", 7, 2001),
        "expected": Decision(False, True, True, "f2-generation-mismatch"),
    },
    {
        "id": "restore-token-present-but-permission-withdrawn",
        "binding": Binding(7, 1001, True, "ACTIVE"),
        "obs": Observation("RESTORE_ATTEMPT", 7, None, True, False),
        "expected": Decision(False, True, False, "restore-token-is-not-permission-proof"),
    },
    {
        "id": "same-logical-stream-restored-with-new-serial",
        "binding": Binding(7, 1001, True, "ACTIVE"),
        "obs": Observation("RESTORE_ATTEMPT", 7, 3001, True, True),
        "expected": Decision(False, True, True, "restored-native-stream-instance-changed"),
    },
    {
        "id": "same-serial-restored-session-still-requires-generation-bump",
        "binding": Binding(7, 1001, True, "ACTIVE"),
        "obs": Observation("RESTORE_ATTEMPT", 7, 1001, True, True),
        "expected": Decision(False, False, True, "restored-session-requires-new-f2-generation-before-publication"),
    },
]


def main() -> int:
    results = []
    failures = []
    for case in CASES:
        actual = decide(case["binding"], case["obs"])
        passed = actual == case["expected"]
        row = {
            "id": case["id"],
            "passed": passed,
            "actual": asdict(actual),
            "expected": asdict(case["expected"]),
        }
        results.append(row)
        if not passed:
            failures.append(row)

    canonical = json.dumps(results, sort_keys=True, separators=(",", ":"), allow_nan=False)
    receipt = {
        "schema": "FRANKENSTEIN2_TRIGGER6_SYNTHETIC_FALSIFIER_RESULT/v1",
        "research_id": "R6-WP700-XDG-PORTAL-PIPEWIRE-CAPTURE-001",
        "claim_target": "E3_CLAIM_REPRODUCED_XDG_PIPEWIRE_IDENTITY_INVALIDATION_FIXTURE",
        "cases": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "result_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "results": results,
        "evidence_boundary": "SYNTHETIC_DETERMINISTIC_STATE_MACHINE_ONLY_NOT_PORTAL_PIPEWIRE_OR_DEVICE_RUNTIME",
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
