"""Read-only target-host fingerprinting for Frankenstein 2.0.

F2-WP-1201 generation 1.

This module collects only a fixed allow-list of non-secret technical host facts and
turns them into a deterministic, versioned TargetHostProfile. Probe failure or absence
is represented as UNKNOWN. The collector never invents defaults and never grants
installation, runtime, physical-host, or completion credit.

The default probe set intentionally does not read credentials, clipboard contents, user
documents, raw camera frames, raw microphone audio, browser history/cookies, process
command lines, SSH material, or environment-variable values other than the bounded
session-shape facts explicitly listed below.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence

TARGET_HOST_PROFILE_SCHEMA = "FRANKENSTEIN2_TARGET_HOST_PROFILE/v1"
COLLECTOR_VERSION = "F2-WP-1201-G1"
OBSERVED = "OBSERVED"
UNKNOWN = "UNKNOWN"
_MAX_OUTPUT_CHARS = 131_072


class TargetHostProfileError(ValueError):
    """Fail-closed target-host-profile contract error."""


@dataclass(frozen=True, slots=True)
class ProbeSpec:
    field_id: str
    source: str
    argv: tuple[str, ...] | None = None
    file_path: str | None = None
    env_key: str | None = None

    def __post_init__(self) -> None:
        selectors = sum(
            value is not None for value in (self.argv, self.file_path, self.env_key)
        )
        if selectors != 1:
            raise TargetHostProfileError("probe must define exactly one selector")
        if not self.field_id or self.field_id != self.field_id.strip():
            raise TargetHostProfileError("field_id must be non-empty and trimmed")
        if not self.source or self.source != self.source.strip():
            raise TargetHostProfileError("source must be non-empty and trimmed")
        if self.argv is not None and (not self.argv or any(not part for part in self.argv)):
            raise TargetHostProfileError("argv probe must be non-empty")
        if self.file_path is not None and not self.file_path.startswith("/"):
            raise TargetHostProfileError("file probe path must be absolute")


DEFAULT_PROBES: tuple[ProbeSpec, ...] = (
    ProbeSpec("machine_model", "sysfs:dmi_product_name", file_path="/sys/class/dmi/id/product_name"),
    ProbeSpec("board_name", "sysfs:dmi_board_name", file_path="/sys/class/dmi/id/board_name"),
    ProbeSpec("bios_version", "sysfs:dmi_bios_version", file_path="/sys/class/dmi/id/bios_version"),
    ProbeSpec("bios_date", "sysfs:dmi_bios_date", file_path="/sys/class/dmi/id/bios_date"),
    ProbeSpec("os_release", "file:/etc/os-release", file_path="/etc/os-release"),
    ProbeSpec("kernel_release", "command:uname-r", argv=("uname", "-r")),
    ProbeSpec("architecture", "command:uname-m", argv=("uname", "-m")),
    ProbeSpec("cpu_topology", "command:lscpu", argv=("lscpu",)),
    ProbeSpec("pci_inventory", "command:lspci-nnk", argv=("lspci", "-nnk")),
    ProbeSpec("usb_inventory", "command:lsusb", argv=("lsusb",)),
    ProbeSpec(
        "storage_inventory",
        "command:lsblk-bounded",
        argv=("lsblk", "-J", "-o", "NAME,TYPE,FSTYPE,SIZE"),
    ),
    ProbeSpec("session_type", "env:XDG_SESSION_TYPE", env_key="XDG_SESSION_TYPE"),
    ProbeSpec("desktop_name", "env:XDG_CURRENT_DESKTOP", env_key="XDG_CURRENT_DESKTOP"),
    ProbeSpec("systemd_user_state", "command:systemctl-user-state", argv=("systemctl", "--user", "is-system-running")),
    ProbeSpec("pipewire_version", "command:pipewire-version", argv=("pipewire", "--version")),
    ProbeSpec("wireplumber_version", "command:wireplumber-version", argv=("wireplumber", "--version")),
    ProbeSpec("pipewire_topology", "command:wpctl-status", argv=("wpctl", "status")),
    ProbeSpec("camera_inventory", "command:v4l2-list-devices", argv=("v4l2-ctl", "--list-devices")),
    ProbeSpec("firefox_version", "command:firefox-version", argv=("firefox", "--version")),
    ProbeSpec("chromium_version", "command:chromium-version", argv=("chromium", "--version")),
    ProbeSpec("chrome_version", "command:google-chrome-version", argv=("google-chrome", "--version")),
)

_ALLOWED_FIELDS = frozenset(spec.field_id for spec in DEFAULT_PROBES) | {
    "collector_uid",
    "xdg_runtime_dir_present",
    "xdg_runtime_dir_owned_by_collector_uid",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _clean_text(value: str) -> str:
    if "\x00" in value:
        raise TargetHostProfileError("probe output contains NUL")
    value = value.strip()
    if len(value) > _MAX_OUTPUT_CHARS:
        raise TargetHostProfileError("probe output exceeds bounded profile size")
    return value


def _observed(*, source: str, value: Any) -> dict[str, Any]:
    return {"status": OBSERVED, "source": source, "value": value}


def _unknown(*, source: str, reason: str) -> dict[str, Any]:
    return {"status": UNKNOWN, "source": source, "reason": reason}


def _run_read_only(argv: Sequence[str], timeout_s: float = 2.0) -> tuple[bool, str, str]:
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
    try:
        return True, _clean_text(completed.stdout), ""
    except TargetHostProfileError:
        return False, "", "INVALID_OR_OVERSIZE_OUTPUT"


def _read_bounded(path: str) -> tuple[bool, str, str]:
    try:
        value = Path(path).read_text(encoding="utf-8", errors="strict")
    except FileNotFoundError:
        return False, "", "FILE_NOT_FOUND"
    except (OSError, UnicodeError):
        return False, "", "READ_ERROR"
    try:
        return True, _clean_text(value), ""
    except TargetHostProfileError:
        return False, "", "INVALID_OR_OVERSIZE_OUTPUT"


def _validate_fact_record(field_id: str, record: Mapping[str, Any]) -> None:
    if field_id not in _ALLOWED_FIELDS:
        raise TargetHostProfileError(f"field is not in collector allow-list: {field_id}")
    status = record.get("status")
    if status not in {OBSERVED, UNKNOWN}:
        raise TargetHostProfileError(f"invalid status for {field_id}")
    source = record.get("source")
    if not isinstance(source, str) or not source:
        raise TargetHostProfileError(f"missing source for {field_id}")
    if status == OBSERVED:
        if "value" not in record or "reason" in record:
            raise TargetHostProfileError(f"invalid OBSERVED record for {field_id}")
    else:
        if "value" in record:
            raise TargetHostProfileError(f"UNKNOWN record cannot contain value for {field_id}")
        reason = record.get("reason")
        if not isinstance(reason, str) or not reason:
            raise TargetHostProfileError(f"UNKNOWN record requires reason for {field_id}")


@dataclass(frozen=True, slots=True)
class TargetHostProfile:
    schema: str
    collector_version: str
    generation: int
    facts: Mapping[str, Mapping[str, Any]]
    profile_digest_sha256: str

    def __post_init__(self) -> None:
        if self.schema != TARGET_HOST_PROFILE_SCHEMA:
            raise TargetHostProfileError("target host profile schema mismatch")
        if self.collector_version != COLLECTOR_VERSION:
            raise TargetHostProfileError("collector version mismatch")
        if type(self.generation) is not int or self.generation < 1:
            raise TargetHostProfileError("generation must be a positive integer")
        if set(self.facts) != _ALLOWED_FIELDS:
            missing = sorted(_ALLOWED_FIELDS - set(self.facts))
            unexpected = sorted(set(self.facts) - _ALLOWED_FIELDS)
            raise TargetHostProfileError(
                f"profile fact set mismatch; missing={missing!r} unexpected={unexpected!r}"
            )
        for field_id, record in self.facts.items():
            _validate_fact_record(field_id, record)
        if self.profile_digest_sha256 != self._calculate_digest():
            raise TargetHostProfileError("profile digest mismatch")

    def _payload_without_digest(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "collector_version": self.collector_version,
            "generation": self.generation,
            "facts": {key: dict(self.facts[key]) for key in sorted(self.facts)},
        }

    def _calculate_digest(self) -> str:
        return _sha256(self._payload_without_digest())

    @property
    def unknown_fields(self) -> tuple[str, ...]:
        return tuple(
            key for key in sorted(self.facts) if self.facts[key]["status"] == UNKNOWN
        )

    @property
    def observed_fields(self) -> tuple[str, ...]:
        return tuple(
            key for key in sorted(self.facts) if self.facts[key]["status"] == OBSERVED
        )

    @property
    def complete_fingerprint(self) -> bool:
        return not self.unknown_fields

    def as_dict(self) -> dict[str, Any]:
        payload = self._payload_without_digest()
        payload["profile_digest_sha256"] = self.profile_digest_sha256
        payload["observed_field_count"] = len(self.observed_fields)
        payload["unknown_field_count"] = len(self.unknown_fields)
        payload["unknown_fields"] = list(self.unknown_fields)
        payload["epistemic_scope"] = "READ_ONLY_TECHNICAL_FINGERPRINT_NOT_COMPLETION_EVIDENCE_BY_ITSELF"
        return payload

    def canonical_json(self) -> str:
        return _canonical_json(self.as_dict())


CommandRunner = Callable[[Sequence[str]], tuple[bool, str, str]]
FileReader = Callable[[str], tuple[bool, str, str]]


def collect_target_host_profile(
    *,
    generation: int,
    probes: Sequence[ProbeSpec] = DEFAULT_PROBES,
    command_runner: CommandRunner = _run_read_only,
    file_reader: FileReader = _read_bounded,
    environ: Mapping[str, str] | None = None,
    collector_uid: int | None = None,
) -> TargetHostProfile:
    """Collect the bounded technical fingerprint using only explicit read-only probes."""
    if type(generation) is not int or generation < 1:
        raise TargetHostProfileError("generation must be a positive integer")
    if tuple(probes) != DEFAULT_PROBES:
        raise TargetHostProfileError("custom probe sets are not allowed in generation 1")

    env = os.environ if environ is None else environ
    uid = os.getuid() if collector_uid is None else collector_uid
    if type(uid) is not int or uid < 0:
        raise TargetHostProfileError("collector_uid must be a non-negative integer")

    facts: dict[str, Mapping[str, Any]] = {}
    for spec in probes:
        if spec.argv is not None:
            ok, value, reason = command_runner(spec.argv)
        elif spec.file_path is not None:
            ok, value, reason = file_reader(spec.file_path)
        else:
            assert spec.env_key is not None
            raw = env.get(spec.env_key)
            if raw is None or not raw.strip():
                ok, value, reason = False, "", "ENV_ABSENT"
            else:
                try:
                    value = _clean_text(raw)
                except TargetHostProfileError:
                    ok, value, reason = False, "", "INVALID_OR_OVERSIZE_OUTPUT"
                else:
                    ok, reason = True, ""
        facts[spec.field_id] = (
            _observed(source=spec.source, value=value)
            if ok
            else _unknown(source=spec.source, reason=reason)
        )

    facts["collector_uid"] = _observed(source="runtime:getuid", value=uid)
    runtime_dir = env.get("XDG_RUNTIME_DIR")
    if runtime_dir is None or not runtime_dir.strip():
        facts["xdg_runtime_dir_present"] = _observed(
            source="runtime:XDG_RUNTIME_DIR", value=False
        )
        facts["xdg_runtime_dir_owned_by_collector_uid"] = _unknown(
            source="runtime:XDG_RUNTIME_DIR", reason="RUNTIME_DIR_ABSENT"
        )
    else:
        path = Path(runtime_dir)
        present = path.exists()
        facts["xdg_runtime_dir_present"] = _observed(
            source="runtime:XDG_RUNTIME_DIR", value=present
        )
        if not present:
            facts["xdg_runtime_dir_owned_by_collector_uid"] = _unknown(
                source="runtime:XDG_RUNTIME_DIR", reason="RUNTIME_DIR_NOT_FOUND"
            )
        else:
            try:
                owned = path.stat().st_uid == uid
            except OSError:
                facts["xdg_runtime_dir_owned_by_collector_uid"] = _unknown(
                    source="runtime:XDG_RUNTIME_DIR", reason="RUNTIME_DIR_STAT_ERROR"
                )
            else:
                facts["xdg_runtime_dir_owned_by_collector_uid"] = _observed(
                    source="runtime:XDG_RUNTIME_DIR", value=owned
                )

    payload = {
        "schema": TARGET_HOST_PROFILE_SCHEMA,
        "collector_version": COLLECTOR_VERSION,
        "generation": generation,
        "facts": {key: dict(facts[key]) for key in sorted(facts)},
    }
    digest = _sha256(payload)
    return TargetHostProfile(
        schema=TARGET_HOST_PROFILE_SCHEMA,
        collector_version=COLLECTOR_VERSION,
        generation=generation,
        facts=payload["facts"],
        profile_digest_sha256=digest,
    )


__all__ = [
    "COLLECTOR_VERSION",
    "DEFAULT_PROBES",
    "OBSERVED",
    "TARGET_HOST_PROFILE_SCHEMA",
    "UNKNOWN",
    "ProbeSpec",
    "TargetHostProfile",
    "TargetHostProfileError",
    "collect_target_host_profile",
]
