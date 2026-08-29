"""Bounded T1 userspace runtime readback receipts for Frankenstein 2.0.

F2-WP-1202 generation 4.

This module closes the gap between the deterministic WP1202 T1 plan and an actual
read-only userspace observation.  It consumes the exact canonical WP1201 profile,
rebuilds the accepted WP1202 plan, executes only a fixed allowlist of readback
operations through injected readers, and emits a digest-bound receipt.

The receipt is evidence input, not evidence authority.  Creating one does not admit
its execution environment and grants no T4 physical-host, VPS, effect, completion,
GRID/GWT/J-Space, provider-model, training, or whole-system credit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Callable, Mapping

from .target_host_profile import TargetHostProfile
from .target_userspace_twin import (
    FIDELITY,
    ONE_HANDOFF_ENTRY,
    TwinBootstrapPlan,
    build_t1_userspace_plan,
)

READBACK_SCHEMA = "FRANKENSTEIN2_T1_USERSPACE_RUNTIME_READBACK/v1"
EVIDENCE_SCOPE = "T1_READBACK_CANDIDATE_NO_T4_EFFECT_COMPLETION_OR_WHOLE_SYSTEM_CREDIT"
PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"
_STATUSES = frozenset({PASS, FAIL, UNKNOWN})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512


class TargetUserspaceRuntimeReadbackError(ValueError):
    """Fail-closed readback input or observation error."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TargetUserspaceRuntimeReadbackError("value is not canonical JSON-safe") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: Any, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise TargetUserspaceRuntimeReadbackError(f"{name} must be exact text")
    if value != value.strip():
        raise TargetUserspaceRuntimeReadbackError(f"{name} must already be trimmed")
    if not allow_empty and not value:
        raise TargetUserspaceRuntimeReadbackError(f"{name} must be non-empty")
    if len(value) > _MAX_TEXT:
        raise TargetUserspaceRuntimeReadbackError(f"{name} exceeds {_MAX_TEXT} characters")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise TargetUserspaceRuntimeReadbackError(f"{name} contains control characters")
    return value


def _sha256(name: str, value: Any) -> str:
    value = _text(name, value)
    if _SHA256_RE.fullmatch(value) is None:
        raise TargetUserspaceRuntimeReadbackError(f"{name} must be lowercase SHA-256 text")
    return value


def _status(value: Any) -> str:
    value = _text("status", value)
    if value not in _STATUSES:
        raise TargetUserspaceRuntimeReadbackError(f"unsupported status: {value}")
    return value


def _summary(value: Any) -> str:
    return _text("summary", value)


@dataclass(frozen=True, slots=True)
class CommandResult:
    """One bounded command observation; returncode=None means unavailable/unobserved."""

    returncode: int | None
    stdout: str = ""
    stderr: str = ""

    def __post_init__(self) -> None:
        if self.returncode is not None and (type(self.returncode) is not int or self.returncode < 0):
            raise TargetUserspaceRuntimeReadbackError("returncode must be non-negative int or null")
        if type(self.stdout) is not str or type(self.stderr) is not str:
            raise TargetUserspaceRuntimeReadbackError("command output must be text")
        if len(self.stdout) > 16_384 or len(self.stderr) > 16_384:
            raise TargetUserspaceRuntimeReadbackError("command output exceeds bounded readback limit")


@dataclass(frozen=True, slots=True)
class PathStatResult:
    """Minimal stat readback without persisting a host path."""

    exists: bool | None
    owner_uid: int | None = None

    def __post_init__(self) -> None:
        if self.exists not in {True, False, None}:
            raise TargetUserspaceRuntimeReadbackError("exists must be true, false, or null")
        if self.owner_uid is not None and (type(self.owner_uid) is not int or self.owner_uid < 0):
            raise TargetUserspaceRuntimeReadbackError("owner_uid must be non-negative int or null")
        if self.exists is not True and self.owner_uid is not None:
            raise TargetUserspaceRuntimeReadbackError("owner_uid requires exists=true")


@dataclass(frozen=True, slots=True)
class HandoffEvidence:
    """Reference to separately observed one-handoff execution evidence."""

    entry: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        _text("handoff entry", self.entry)
        _sha256("handoff evidence_sha256", self.evidence_sha256)


@dataclass(frozen=True, slots=True)
class ReadbackObservation:
    check: str
    status: str
    summary: str
    observation_sha256: str

    def __post_init__(self) -> None:
        _text("check", self.check)
        _status(self.status)
        _summary(self.summary)
        _sha256("observation_sha256", self.observation_sha256)
        expected = _digest({"check": self.check, "status": self.status, "summary": self.summary})
        if self.observation_sha256 != expected:
            raise TargetUserspaceRuntimeReadbackError("observation digest mismatch")

    @classmethod
    def create(cls, check: str, status: str, summary: str) -> "ReadbackObservation":
        payload = {"check": check, "status": status, "summary": summary}
        return cls(
            check=_text("check", check),
            status=_status(status),
            summary=_summary(summary),
            observation_sha256=_digest(payload),
        )

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RuntimeFidelityGap:
    check: str
    classification: str
    target_declared: str
    twin_observed: str

    def __post_init__(self) -> None:
        _text("gap check", self.check)
        _text("gap classification", self.classification)
        _text("target_declared", self.target_declared)
        _text("twin_observed", self.twin_observed)

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class T1RuntimeReadbackReceipt:
    schema: str
    fidelity: str
    source_profile_generation: int
    source_profile_sha256: str
    plan_sha256: str
    observations: tuple[ReadbackObservation, ...]
    fidelity_gaps: tuple[RuntimeFidelityGap, ...]
    pass_count: int
    fail_count: int
    unknown_count: int
    classification: str
    evidence_scope: str = EVIDENCE_SCOPE
    runtime_credit: int = 0
    target_twin_runtime_credit: int = 0
    physical_target_credit: int = 0
    effect_credit: int = 0
    completion_credit: int = 0
    whole_system_acceptance: bool = False

    def __post_init__(self) -> None:
        if self.schema != READBACK_SCHEMA:
            raise TargetUserspaceRuntimeReadbackError("receipt schema mismatch")
        if self.fidelity != FIDELITY:
            raise TargetUserspaceRuntimeReadbackError("receipt fidelity mismatch")
        if type(self.source_profile_generation) is not int or self.source_profile_generation < 0:
            raise TargetUserspaceRuntimeReadbackError("invalid profile generation")
        _sha256("source_profile_sha256", self.source_profile_sha256)
        _sha256("plan_sha256", self.plan_sha256)
        if type(self.observations) is not tuple or not self.observations:
            raise TargetUserspaceRuntimeReadbackError("observations must be a non-empty tuple")
        if len({item.check for item in self.observations}) != len(self.observations):
            raise TargetUserspaceRuntimeReadbackError("duplicate readback check")
        expected_counts = (
            sum(item.status == PASS for item in self.observations),
            sum(item.status == FAIL for item in self.observations),
            sum(item.status == UNKNOWN for item in self.observations),
        )
        if (self.pass_count, self.fail_count, self.unknown_count) != expected_counts:
            raise TargetUserspaceRuntimeReadbackError("receipt counts mismatch")
        if self.runtime_credit != 0 or self.target_twin_runtime_credit != 0:
            raise TargetUserspaceRuntimeReadbackError("readback object cannot mint runtime credit")
        if self.physical_target_credit != 0 or self.effect_credit != 0 or self.completion_credit != 0:
            raise TargetUserspaceRuntimeReadbackError("readback object cannot mint higher-scope credit")
        if self.whole_system_acceptance is not False:
            raise TargetUserspaceRuntimeReadbackError("readback object cannot mint whole-system acceptance")
        if self.evidence_scope != EVIDENCE_SCOPE:
            raise TargetUserspaceRuntimeReadbackError("receipt evidence scope mismatch")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "fidelity": self.fidelity,
            "source_profile_generation": self.source_profile_generation,
            "source_profile_sha256": self.source_profile_sha256,
            "plan_sha256": self.plan_sha256,
            "observations": [item.as_dict() for item in self.observations],
            "fidelity_gaps": [item.as_dict() for item in self.fidelity_gaps],
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "unknown_count": self.unknown_count,
            "classification": self.classification,
            "evidence_scope": self.evidence_scope,
            "runtime_credit": self.runtime_credit,
            "target_twin_runtime_credit": self.target_twin_runtime_credit,
            "physical_target_credit": self.physical_target_credit,
            "effect_credit": self.effect_credit,
            "completion_credit": self.completion_credit,
            "whole_system_acceptance": self.whole_system_acceptance,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


CommandRunner = Callable[[tuple[str, ...]], CommandResult]
PathStatReader = Callable[[str], PathStatResult]


def _command_observation(
    check: str,
    argv: tuple[str, ...],
    runner: CommandRunner,
    *,
    success_summary: str,
    failure_summary: str,
) -> tuple[ReadbackObservation, CommandResult]:
    result = runner(argv)
    if type(result) is not CommandResult:
        raise TargetUserspaceRuntimeReadbackError("command_runner must return exact CommandResult")
    if result.returncode is None:
        return ReadbackObservation.create(check, UNKNOWN, "command-unavailable-or-unobserved"), result
    if result.returncode == 0:
        return ReadbackObservation.create(check, PASS, success_summary), result
    return ReadbackObservation.create(check, FAIL, failure_summary), result


def _plan_field(plan: TwinBootstrapPlan, name: str) -> str:
    values = dict(plan.observed_shape)
    value = values.get(name)
    if type(value) is not str:
        raise TargetUserspaceRuntimeReadbackError(f"plan missing field: {name}")
    return value


def _safe_scalar(value: str) -> str:
    value = value.strip()
    if not value:
        return UNKNOWN
    if len(value) > 128 or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        return "OBSERVED_VALUE_DIGEST:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
    return value


def execute_t1_runtime_readbacks(
    profile: Mapping[str, Any] | TargetHostProfile,
    *,
    command_runner: CommandRunner,
    environ: Mapping[str, str],
    path_stat_reader: PathStatReader,
    handoff_evidence: HandoffEvidence | None = None,
) -> T1RuntimeReadbackReceipt:
    """Execute the fixed WP1202 T1 readback set through injected read-only observers."""

    if type(environ) is not dict:
        raise TargetUserspaceRuntimeReadbackError("environ must be an exact dict snapshot")
    if any(type(key) is not str or type(value) is not str for key, value in environ.items()):
        raise TargetUserspaceRuntimeReadbackError("environ keys and values must be text")

    plan = build_t1_userspace_plan(profile)
    expected_checks = tuple(plan.required_runtime_checks)
    observations: list[ReadbackObservation] = []
    gaps: list[RuntimeFidelityGap] = []

    system_obs, _ = _command_observation(
        "systemd-system-manager-is-live",
        ("systemctl", "is-system-running"),
        command_runner,
        success_summary="system-manager-command-succeeded",
        failure_summary="system-manager-command-failed",
    )
    observations.append(system_obs)

    expected_uid = _plan_field(plan, "uid")
    uid_result = command_runner(("id", "-u"))
    if type(uid_result) is not CommandResult:
        raise TargetUserspaceRuntimeReadbackError("command_runner must return exact CommandResult")
    observed_uid = _safe_scalar(uid_result.stdout) if uid_result.returncode == 0 else UNKNOWN
    if uid_result.returncode is None or expected_uid == UNKNOWN:
        uid_status = UNKNOWN
        uid_summary = "target-user-identity-unobserved"
    elif uid_result.returncode != 0:
        uid_status = FAIL
        uid_summary = "target-user-id-command-failed"
    elif observed_uid == expected_uid and observed_uid != "0":
        uid_status = PASS
        uid_summary = "non-root-target-user-matches-plan"
    else:
        uid_status = FAIL
        uid_summary = "target-user-does-not-match-plan-or-is-root"
    observations.append(ReadbackObservation.create("non-root-target-user-exists", uid_status, uid_summary))
    if uid_status != PASS:
        gaps.append(RuntimeFidelityGap("non-root-target-user-exists", "UID_FIDELITY_GAP", expected_uid, observed_uid))

    user_obs, _ = _command_observation(
        "systemd-user-manager-is-live-for-target-user",
        ("systemctl", "--user", "is-system-running"),
        command_runner,
        success_summary="user-manager-command-succeeded",
        failure_summary="user-manager-command-failed",
    )
    observations.append(user_obs)

    xdg_runtime = environ.get("XDG_RUNTIME_DIR", "").strip()
    if not xdg_runtime or expected_uid == UNKNOWN:
        xdg_status = UNKNOWN
        xdg_summary = "xdg-runtime-dir-or-target-uid-unobserved"
        xdg_twin = UNKNOWN
    else:
        stat = path_stat_reader(xdg_runtime)
        if type(stat) is not PathStatResult:
            raise TargetUserspaceRuntimeReadbackError("path_stat_reader must return exact PathStatResult")
        if stat.exists is None:
            xdg_status, xdg_summary, xdg_twin = UNKNOWN, "xdg-runtime-dir-stat-unavailable", UNKNOWN
        elif not stat.exists:
            xdg_status, xdg_summary, xdg_twin = FAIL, "xdg-runtime-dir-missing", "MISSING"
        elif stat.owner_uid is None:
            xdg_status, xdg_summary, xdg_twin = UNKNOWN, "xdg-runtime-dir-owner-unobserved", "EXISTS_OWNER_UNKNOWN"
        elif str(stat.owner_uid) == expected_uid:
            xdg_status, xdg_summary, xdg_twin = PASS, "xdg-runtime-dir-exists-and-owner-matches", "EXISTS_OWNER_MATCH"
        else:
            xdg_status, xdg_summary, xdg_twin = FAIL, "xdg-runtime-dir-owner-mismatch", f"EXISTS_OWNER_UID:{stat.owner_uid}"
    observations.append(ReadbackObservation.create("xdg-runtime-dir-exists-and-owned-by-target-user", xdg_status, xdg_summary))
    if xdg_status != PASS:
        gaps.append(RuntimeFidelityGap("xdg-runtime-dir-exists-and-owned-by-target-user", "XDG_RUNTIME_FIDELITY_GAP", _plan_field(plan, "xdg_runtime_dir"), xdg_twin))

    dbus_address = environ.get("DBUS_SESSION_BUS_ADDRESS", "").strip()
    if not dbus_address:
        dbus_obs = ReadbackObservation.create(
            "session-dbus-is-reachable-from-target-user-context",
            UNKNOWN,
            "session-dbus-address-unobserved",
        )
        dbus_twin = UNKNOWN
    else:
        dbus_obs, _ = _command_observation(
            "session-dbus-is-reachable-from-target-user-context",
            ("busctl", "--user", "--no-pager", "status"),
            command_runner,
            success_summary="session-dbus-command-succeeded",
            failure_summary="session-dbus-command-failed",
        )
        dbus_twin = "ADDRESS_PRESENT_AND_PROBE_" + dbus_obs.status
    observations.append(dbus_obs)
    if dbus_obs.status != PASS:
        gaps.append(RuntimeFidelityGap("session-dbus-is-reachable-from-target-user-context", "SESSION_DBUS_FIDELITY_GAP", _plan_field(plan, "session_dbus"), dbus_twin))

    target_session = _plan_field(plan, "session_type")
    observed_session = _safe_scalar(environ.get("XDG_SESSION_TYPE", ""))
    if observed_session == UNKNOWN:
        session_status, session_summary = UNKNOWN, "session-type-unobserved-gap-recorded"
    elif target_session == UNKNOWN:
        session_status, session_summary = PASS, "twin-session-type-observed-target-unknown"
    elif observed_session == target_session:
        session_status, session_summary = PASS, "session-type-matches-plan"
    else:
        session_status, session_summary = FAIL, "session-type-differs-from-plan"
    observations.append(ReadbackObservation.create("declared-session-type-is-observed-or-gap-recorded", session_status, session_summary))
    if session_status != PASS or target_session == UNKNOWN:
        gaps.append(RuntimeFidelityGap("declared-session-type-is-observed-or-gap-recorded", "SESSION_TYPE_FIDELITY_GAP" if session_status != PASS else "TARGET_UNKNOWN_TWIN_OBSERVED", target_session, observed_session))

    pipe_obs, _ = _command_observation(
        "pipewire-service",
        ("systemctl", "--user", "is-active", "pipewire.service"),
        command_runner,
        success_summary="pipewire-active",
        failure_summary="pipewire-not-active",
    )
    wire_obs, _ = _command_observation(
        "wireplumber-service",
        ("systemctl", "--user", "is-active", "wireplumber.service"),
        command_runner,
        success_summary="wireplumber-active",
        failure_summary="wireplumber-not-active",
    )
    if pipe_obs.status == PASS and wire_obs.status == PASS:
        media_status, media_summary = PASS, "pipewire-and-wireplumber-active"
    elif FAIL in {pipe_obs.status, wire_obs.status}:
        media_status, media_summary = FAIL, "pipewire-or-wireplumber-not-active"
    else:
        media_status, media_summary = UNKNOWN, "pipewire-or-wireplumber-unobserved"
    observations.append(ReadbackObservation.create("pipewire-and-wireplumber-state-is-observed-or-gap-recorded", media_status, media_summary))
    if media_status != PASS:
        gaps.append(RuntimeFidelityGap("pipewire-and-wireplumber-state-is-observed-or-gap-recorded", "MULTIMEDIA_USERSPACE_FIDELITY_GAP", "TARGET_PROFILE_VERSION_FACTS_ONLY", media_summary))

    portal_obs, _ = _command_observation(
        "portal-backend-state-is-observed-or-gap-recorded",
        ("systemctl", "--user", "is-active", "xdg-desktop-portal.service"),
        command_runner,
        success_summary="xdg-desktop-portal-active",
        failure_summary="xdg-desktop-portal-not-active",
    )
    observations.append(portal_obs)
    if portal_obs.status != PASS:
        gaps.append(RuntimeFidelityGap("portal-backend-state-is-observed-or-gap-recorded", "PORTAL_FIDELITY_GAP", _plan_field(plan, "portal_backend"), portal_obs.status))

    if handoff_evidence is None:
        handoff_obs = ReadbackObservation.create(
            "one-handoff-installer-entry-is-used",
            UNKNOWN,
            "no-independent-handoff-evidence-bound",
        )
    elif type(handoff_evidence) is not HandoffEvidence:
        raise TargetUserspaceRuntimeReadbackError("handoff_evidence must be exact HandoffEvidence or null")
    elif handoff_evidence.entry != ONE_HANDOFF_ENTRY:
        handoff_obs = ReadbackObservation.create(
            "one-handoff-installer-entry-is-used",
            FAIL,
            "observed-handoff-entry-mismatch",
        )
    else:
        handoff_obs = ReadbackObservation.create(
            "one-handoff-installer-entry-is-used",
            PASS,
            "exact-one-handoff-entry-with-evidence-digest-bound",
        )
    observations.append(handoff_obs)
    if handoff_obs.status != PASS:
        gaps.append(RuntimeFidelityGap("one-handoff-installer-entry-is-used", "ONE_HANDOFF_EVIDENCE_GAP", ONE_HANDOFF_ENTRY, handoff_obs.status))

    observations.append(
        ReadbackObservation.create(
            "twin-target-differences-are-recorded-not-masked",
            PASS,
            "nonpass-and-target-unknown-differences-are-explicit-fidelity-gaps",
        )
    )

    checks = tuple(item.check for item in observations)
    if set(checks) != set(expected_checks):
        raise TargetUserspaceRuntimeReadbackError(
            "runtime readback implementation does not exactly cover plan required_runtime_checks"
        )

    ordered = tuple(sorted(observations, key=lambda item: expected_checks.index(item.check)))
    pass_count = sum(item.status == PASS for item in ordered)
    fail_count = sum(item.status == FAIL for item in ordered)
    unknown_count = sum(item.status == UNKNOWN for item in ordered)
    if fail_count:
        classification = "T1_READBACK_OBSERVED_WITH_FAILURES_NO_RUNTIME_CREDIT_MINTED"
    elif unknown_count:
        classification = "T1_READBACK_PARTIAL_WITH_EXPLICIT_GAPS_NO_RUNTIME_CREDIT_MINTED"
    else:
        classification = "T1_READBACK_ALL_DECLARED_CHECKS_PASS_NO_RUNTIME_CREDIT_MINTED"

    return T1RuntimeReadbackReceipt(
        schema=READBACK_SCHEMA,
        fidelity=plan.fidelity,
        source_profile_generation=plan.source_profile_generation,
        source_profile_sha256=plan.source_profile_sha256,
        plan_sha256=plan.sha256(),
        observations=ordered,
        fidelity_gaps=tuple(gaps),
        pass_count=pass_count,
        fail_count=fail_count,
        unknown_count=unknown_count,
        classification=classification,
    )


__all__ = [
    "CommandResult",
    "EVIDENCE_SCOPE",
    "FAIL",
    "HandoffEvidence",
    "PASS",
    "PathStatResult",
    "READBACK_SCHEMA",
    "RuntimeFidelityGap",
    "T1RuntimeReadbackReceipt",
    "TargetUserspaceRuntimeReadbackError",
    "UNKNOWN",
    "execute_t1_runtime_readbacks",
]
