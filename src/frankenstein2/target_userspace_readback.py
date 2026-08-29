"""Read-only T1 userspace runtime readbacks for Frankenstein 2.0.

This module continues the accepted F2-WP-1202 boundary.  It consumes one exact
canonical F2-WP-1201 TargetHostProfile through ``build_t1_userspace_plan`` and
collects only bounded post-materialization userspace observations:

* systemd --user manager state,
* XDG runtime directory presence/ownership,
* session D-Bus address shape and bus reachability,
* XDG session type consistency,
* one explicitly named systemd user service state.

The collector is evidence-only.  It never starts/stops/enables services, never
uses a shell, never invokes providers or networking, and never grants T4 physical
host, effect, completion, GRID10, GWT, J-Space, model, or training credit.

    T1_RUNTIME_READBACK_PASS != T4_SAME_HOST_PHYSICAL_PASS
    T1_RUNTIME_READBACK_PASS != WHOLE_SYSTEM_PASS
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Callable, Mapping, Sequence

from .target_host_profile import TargetHostProfile
from .target_userspace_twin import (
    ONE_HANDOFF_ENTRY,
    UNKNOWN,
    TwinBootstrapPlan,
    build_t1_userspace_plan,
)

READBACK_SCHEMA = "FRANKENSTEIN2_T1_USERSPACE_RUNTIME_READBACK/v1"
READBACK_CLASSIFICATION = "T1_RUNTIME_READBACK_NO_T4_PHYSICAL_OR_COMPLETION_CREDIT"
PASS = "PASS"
FAIL = "FAIL"
UNKNOWN_STATUS = "UNKNOWN"
_MAX_TEXT = 16_384
_SERVICE_RE = re.compile(r"^[A-Za-z0-9_.@:-]+\.service$")


class TargetUserspaceReadbackError(ValueError):
    """Fail-closed T1 runtime-readback contract error."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _clean(name: str, value: Any) -> str:
    if type(value) is not str:
        raise TargetUserspaceReadbackError(f"{name} must be text")
    if value != value.strip() or not value:
        raise TargetUserspaceReadbackError(f"{name} must be non-empty and trimmed")
    if len(value) > _MAX_TEXT:
        raise TargetUserspaceReadbackError(f"{name} exceeds bounded readback size")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise TargetUserspaceReadbackError(f"{name} contains control characters")
    return value


def _validate_service_unit(value: str) -> str:
    value = _clean("service_unit", value)
    if _SERVICE_RE.fullmatch(value) is None:
        raise TargetUserspaceReadbackError(
            "service_unit must be one bounded systemd .service unit name"
        )
    return value


def _run_read_only(
    argv: Sequence[str], timeout_s: float = 2.0
) -> tuple[bool, str, str]:
    try:
        completed = subprocess.run(
            tuple(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except FileNotFoundError:
        return False, "", "COMMAND_NOT_FOUND"
    except subprocess.TimeoutExpired:
        return False, "", "TIMEOUT"
    except OSError:
        return False, "", "EXEC_ERROR"
    if completed.returncode != 0:
        return False, "", "NONZERO_EXIT"
    output = completed.stdout.strip()
    if len(output) > _MAX_TEXT or "\x00" in output:
        return False, "", "INVALID_OR_OVERSIZE_OUTPUT"
    return True, output, ""


def _stat_owner(path: str) -> tuple[bool, int | None, str]:
    try:
        stat = Path(path).stat()
    except FileNotFoundError:
        return False, None, "PATH_NOT_FOUND"
    except OSError:
        return False, None, "STAT_ERROR"
    return True, stat.st_uid, ""


CommandRunner = Callable[[Sequence[str]], tuple[bool, str, str]]
StatReader = Callable[[str], tuple[bool, int | None, str]]


@dataclass(frozen=True, slots=True)
class ReadbackCheck:
    check_id: str
    status: str
    observed: str
    expected: str
    reason: str

    def __post_init__(self) -> None:
        if self.status not in {PASS, FAIL, UNKNOWN_STATUS}:
            raise TargetUserspaceReadbackError("invalid readback check status")
        for name in ("check_id", "observed", "expected", "reason"):
            value = getattr(self, name)
            if type(value) is not str:
                raise TargetUserspaceReadbackError(f"{name} must be text")

    def as_dict(self) -> dict[str, str]:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "observed": self.observed,
            "expected": self.expected,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class TargetUserspaceRuntimeReadback:
    schema: str
    source_profile_generation: int
    source_profile_sha256: str
    source_plan_sha256: str
    handoff_entry: str
    service_unit: str
    checks: tuple[ReadbackCheck, ...]
    remaining_fidelity_gaps: tuple[str, ...]
    classification: str = READBACK_CLASSIFICATION
    runtime_credit: int = 0
    physical_target_credit: int = 0
    effect_credit: int = 0
    completion_credit: int = 0
    whole_system_credit: int = 0

    @property
    def t1_runtime_readback_pass(self) -> bool:
        return bool(self.checks) and all(check.status == PASS for check in self.checks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source_profile_generation": self.source_profile_generation,
            "source_profile_sha256": self.source_profile_sha256,
            "source_plan_sha256": self.source_plan_sha256,
            "handoff_entry": self.handoff_entry,
            "service_unit": self.service_unit,
            "checks": [check.as_dict() for check in self.checks],
            "remaining_fidelity_gaps": list(self.remaining_fidelity_gaps),
            "classification": self.classification,
            "t1_runtime_readback_pass": self.t1_runtime_readback_pass,
            "runtime_credit": self.runtime_credit,
            "physical_target_credit": self.physical_target_credit,
            "effect_credit": self.effect_credit,
            "completion_credit": self.completion_credit,
            "whole_system_credit": self.whole_system_credit,
        }

    def sha256(self) -> str:
        return _sha256(self.as_dict())


def _check(
    check_id: str,
    *,
    ok: bool,
    observed: str,
    expected: str,
    reason: str = "",
) -> ReadbackCheck:
    return ReadbackCheck(
        check_id=check_id,
        status=PASS if ok else FAIL,
        observed=observed,
        expected=expected,
        reason=reason if reason else ("MATCH" if ok else "MISMATCH"),
    )


def _command_check(
    check_id: str,
    argv: Sequence[str],
    *,
    command_runner: CommandRunner,
    expected: str,
    accept: Callable[[str], bool],
) -> ReadbackCheck:
    ok, output, reason = command_runner(tuple(argv))
    if not ok:
        return _check(
            check_id,
            ok=False,
            observed="UNAVAILABLE",
            expected=expected,
            reason=reason or "COMMAND_FAILED",
        )
    try:
        output = _clean(check_id, output)
    except TargetUserspaceReadbackError:
        return _check(
            check_id,
            ok=False,
            observed="INVALID_OUTPUT",
            expected=expected,
            reason="INVALID_OUTPUT",
        )
    return _check(
        check_id,
        ok=accept(output),
        observed=output,
        expected=expected,
    )


def _service_state(output: str) -> tuple[str, str, str] | None:
    fields: dict[str, str] = {}
    for line in output.splitlines():
        if "=" not in line:
            return None
        key, value = line.split("=", 1)
        if key not in {"LoadState", "ActiveState", "SubState"} or key in fields:
            return None
        if not value or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
            return None
        fields[key] = value
    if set(fields) != {"LoadState", "ActiveState", "SubState"}:
        return None
    return fields["LoadState"], fields["ActiveState"], fields["SubState"]


def _critical_plan_value(plan: TwinBootstrapPlan, field: str) -> str:
    values = dict(plan.observed_shape)
    value = values[field]
    if value == UNKNOWN:
        raise TargetUserspaceReadbackError(
            f"canonical WP1201 profile has no observed {field}; cannot mint T1 runtime readiness"
        )
    return value


def collect_t1_userspace_runtime_readback(
    profile: Mapping[str, Any] | TargetHostProfile,
    *,
    service_unit: str,
    command_runner: CommandRunner = _run_read_only,
    stat_reader: StatReader = _stat_owner,
    environ: Mapping[str, str] | None = None,
    handoff_entry: str = ONE_HANDOFF_ENTRY,
) -> TargetUserspaceRuntimeReadback:
    """Collect bounded T1 userspace observations without changing target state.

    The canonical WP1201 profile remains the only host-capability input.  Direct
    readbacks below are post-materialization evidence and do not mutate or extend
    that profile.  A PASS therefore means only that this T1 readback predicate was
    observed; every broader credit remains explicitly zero.
    """

    plan = build_t1_userspace_plan(profile)
    service_unit = _validate_service_unit(service_unit)
    if handoff_entry != plan.one_handoff_installer_entry:
        raise TargetUserspaceReadbackError("one-handoff installer entry mismatch")

    target_uid_text = _critical_plan_value(plan, "uid")
    try:
        target_uid = int(target_uid_text)
    except ValueError as exc:
        raise TargetUserspaceReadbackError("canonical target uid is not an integer") from exc
    if target_uid <= 0:
        raise TargetUserspaceReadbackError("T1 runtime readback requires non-root target uid")

    expected_systemd = _critical_plan_value(plan, "systemd_user")
    expected_session = _critical_plan_value(plan, "session_type")
    env = os.environ if environ is None else environ

    checks: list[ReadbackCheck] = []
    checks.append(
        _command_check(
            "systemd_user_manager_state",
            ("systemctl", "--user", "is-system-running"),
            command_runner=command_runner,
            expected=expected_systemd,
            accept=lambda output: output == expected_systemd,
        )
    )

    runtime_dir_raw = env.get("XDG_RUNTIME_DIR")
    if runtime_dir_raw is None or not runtime_dir_raw.strip():
        runtime_dir = ""
        checks.append(
            _check(
                "xdg_runtime_dir_owner",
                ok=False,
                observed="UNAVAILABLE",
                expected=f"ABSOLUTE_PATH_OWNED_BY_UID_{target_uid}",
                reason="XDG_RUNTIME_DIR_ABSENT",
            )
        )
    else:
        try:
            runtime_dir = _clean("XDG_RUNTIME_DIR", runtime_dir_raw)
        except TargetUserspaceReadbackError:
            runtime_dir = ""
            checks.append(
                _check(
                    "xdg_runtime_dir_owner",
                    ok=False,
                    observed="INVALID",
                    expected=f"ABSOLUTE_PATH_OWNED_BY_UID_{target_uid}",
                    reason="XDG_RUNTIME_DIR_INVALID",
                )
            )
        else:
            if not runtime_dir.startswith("/"):
                checks.append(
                    _check(
                        "xdg_runtime_dir_owner",
                        ok=False,
                        observed="NON_ABSOLUTE_PATH",
                        expected=f"ABSOLUTE_PATH_OWNED_BY_UID_{target_uid}",
                        reason="XDG_RUNTIME_DIR_NOT_ABSOLUTE",
                    )
                )
            else:
                stat_ok, owner_uid, stat_reason = stat_reader(runtime_dir)
                checks.append(
                    _check(
                        "xdg_runtime_dir_owner",
                        ok=stat_ok and owner_uid == target_uid,
                        observed=(
                            f"PRESENT_OWNER_UID_{owner_uid}"
                            if stat_ok
                            else "UNAVAILABLE"
                        ),
                        expected=f"ABSOLUTE_PATH_OWNED_BY_UID_{target_uid}",
                        reason=(
                            "OWNER_MATCH"
                            if stat_ok and owner_uid == target_uid
                            else (stat_reason or "OWNER_MISMATCH")
                        ),
                    )
                )

    dbus_raw = env.get("DBUS_SESSION_BUS_ADDRESS")
    expected_dbus = f"unix:path={runtime_dir}/bus" if runtime_dir else "XDG_RUNTIME_BUS"
    if dbus_raw is None or not dbus_raw.strip():
        checks.append(
            _check(
                "session_dbus_address",
                ok=False,
                observed="UNAVAILABLE",
                expected=expected_dbus,
                reason="DBUS_SESSION_BUS_ADDRESS_ABSENT",
            )
        )
    else:
        try:
            dbus_address = _clean("DBUS_SESSION_BUS_ADDRESS", dbus_raw)
        except TargetUserspaceReadbackError:
            checks.append(
                _check(
                    "session_dbus_address",
                    ok=False,
                    observed="INVALID",
                    expected=expected_dbus,
                    reason="DBUS_SESSION_BUS_ADDRESS_INVALID",
                )
            )
        else:
            checks.append(
                _check(
                    "session_dbus_address",
                    ok=bool(runtime_dir) and dbus_address == expected_dbus,
                    observed=(
                        "UNIX_PATH_XDG_RUNTIME_BUS"
                        if runtime_dir and dbus_address == expected_dbus
                        else "OTHER_ADDRESS_SHAPE"
                    ),
                    expected="UNIX_PATH_XDG_RUNTIME_BUS",
                    reason=(
                        "ADDRESS_MATCH"
                        if runtime_dir and dbus_address == expected_dbus
                        else "ADDRESS_MISMATCH"
                    ),
                )
            )

    checks.append(
        _command_check(
            "session_dbus_reachable",
            ("busctl", "--user", "--no-pager", "--no-legend", "list"),
            command_runner=command_runner,
            expected="READ_ONLY_BUS_LIST_SUCCEEDS",
            accept=lambda output: bool(output),
        )
    )

    session_raw = env.get("XDG_SESSION_TYPE")
    if session_raw is None or not session_raw.strip():
        checks.append(
            _check(
                "xdg_session_type",
                ok=False,
                observed="UNAVAILABLE",
                expected=expected_session,
                reason="XDG_SESSION_TYPE_ABSENT",
            )
        )
    else:
        try:
            session_type = _clean("XDG_SESSION_TYPE", session_raw)
        except TargetUserspaceReadbackError:
            checks.append(
                _check(
                    "xdg_session_type",
                    ok=False,
                    observed="INVALID",
                    expected=expected_session,
                    reason="XDG_SESSION_TYPE_INVALID",
                )
            )
        else:
            checks.append(
                _check(
                    "xdg_session_type",
                    ok=session_type == expected_session,
                    observed=session_type,
                    expected=expected_session,
                )
            )

    service_argv = (
        "systemctl",
        "--user",
        "show",
        service_unit,
        "--property=LoadState",
        "--property=ActiveState",
        "--property=SubState",
        "--no-pager",
    )
    service_ok, service_output, service_reason = command_runner(service_argv)
    parsed_service = _service_state(service_output) if service_ok else None
    if parsed_service is None:
        checks.append(
            _check(
                "service_state",
                ok=False,
                observed="UNAVAILABLE_OR_INVALID",
                expected="LoadState=loaded;ActiveState=active;SubState!=failed/dead",
                reason=service_reason or "INVALID_SERVICE_READBACK",
            )
        )
    else:
        load_state, active_state, sub_state = parsed_service
        service_pass = (
            load_state == "loaded"
            and active_state == "active"
            and sub_state not in {"failed", "dead"}
        )
        checks.append(
            _check(
                "service_state",
                ok=service_pass,
                observed=(
                    f"LoadState={load_state};ActiveState={active_state};SubState={sub_state}"
                ),
                expected="LoadState=loaded;ActiveState=active;SubState!=failed/dead",
            )
        )

    closed_gap_fields = {"xdg_runtime_dir", "session_dbus"}
    if not all(
        check.status == PASS
        for check in checks
        if check.check_id
        in {"xdg_runtime_dir_owner", "session_dbus_address", "session_dbus_reachable"}
    ):
        closed_gap_fields.clear()
    remaining_gaps = tuple(
        sorted(
            gap.field
            for gap in plan.fidelity_gaps
            if gap.field not in closed_gap_fields
        )
    )

    return TargetUserspaceRuntimeReadback(
        schema=READBACK_SCHEMA,
        source_profile_generation=plan.source_profile_generation,
        source_profile_sha256=plan.source_profile_sha256,
        source_plan_sha256=plan.sha256(),
        handoff_entry=handoff_entry,
        service_unit=service_unit,
        checks=tuple(checks),
        remaining_fidelity_gaps=remaining_gaps,
    )


__all__ = [
    "FAIL",
    "PASS",
    "READBACK_CLASSIFICATION",
    "READBACK_SCHEMA",
    "ReadbackCheck",
    "TargetUserspaceReadbackError",
    "TargetUserspaceRuntimeReadback",
    "collect_t1_userspace_runtime_readback",
]
