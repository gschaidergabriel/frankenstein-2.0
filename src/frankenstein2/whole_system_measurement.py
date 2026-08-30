"""Exact-source local measurement producer for F2-WP-902 characterization samples.

Repository-component source-readiness scope only. This module measures one named Python
operation on the current host, derives the source-bundle digest from bytes actually read,
derives a bounded host-environment fingerprint from observed runtime facts, binds a concrete
WP900 WholePersistentLoopSeal, and emits a CharacterizationSample candidate.

It does not authorize the operation, call providers by itself, mutate UnifiedDB, execute
EffectGate/CompletionGate authority, or mint target-runtime / whole-system acceptance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import inspect
import json
import os
from pathlib import Path
import platform
import re
import resource
import sys
import time
from typing import Any, Callable, Iterable, TypeVar

from .whole_persistent_loop import WholePersistentLoopSeal
from .whole_system_characterization import (
    DEFAULT_METRIC_SCHEMA,
    CharacterizationSample,
    WholeSystemCharacterizationError,
)

SOURCE_BUNDLE_SCHEMA = "FRANKENSTEIN2_CHARACTERIZATION_SOURCE_BUNDLE/v1"
ENVIRONMENT_SCHEMA = "FRANKENSTEIN2_CHARACTERIZATION_HOST_ENVIRONMENT/v1"
MEASUREMENT_CLASSIFICATION = "HOST_MEASUREMENT_CANDIDATE_NOT_RUNTIME_OR_WHOLE_SYSTEM_AUTHORITY"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 512
_MAX_PATHS = 4096
_MAX_REFS = 4096
_T = TypeVar("_T")


class WholeSystemMeasurementError(ValueError):
    """Fail closed on ambiguous source, host, timing, RSS, or provenance evidence."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WholeSystemMeasurementError("value must be canonical-JSON encodable") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: Any) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise WholeSystemMeasurementError(f"{name} must be a non-empty trimmed string")
    if len(value) > _MAX_TEXT or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise WholeSystemMeasurementError(f"{name} is outside the text domain")
    return value


def _sha(name: str, value: Any) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise WholeSystemMeasurementError(f"{name} must be lowercase 64-hex SHA-256")
    return value


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise WholeSystemMeasurementError("provenance_refs must be an iterable of strings")
    refs = tuple(_text("provenance_ref", value) for value in values)
    if not refs:
        raise WholeSystemMeasurementError("provenance_refs must not be empty")
    if len(refs) > _MAX_REFS or len(set(refs)) != len(refs):
        raise WholeSystemMeasurementError("provenance_refs exceed bounds or contain duplicates")
    return tuple(sorted(refs))


def _safe_relative_path(value: Any) -> str:
    text = _text("source_path", value)
    path = Path(text)
    if "\\" in text or path.is_absolute() or text in {".", ".."} or ".." in path.parts:
        raise WholeSystemMeasurementError("source_path must be a normalized repository-relative path")
    normalized = path.as_posix()
    if normalized != text.replace(os.sep, "/") or normalized.startswith("./"):
        raise WholeSystemMeasurementError("source_path must already be normalized")
    return normalized


def _resolve_regular_file(repo_root: Path, relative_path: str) -> Path:
    root = repo_root.resolve(strict=True)
    cursor = root
    for part in Path(relative_path).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise WholeSystemMeasurementError(f"source_path traverses symlink: {relative_path}")
    try:
        resolved = cursor.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, ValueError) as exc:
        raise WholeSystemMeasurementError(f"source_path is missing or escapes repo root: {relative_path}") from exc
    if not resolved.is_file():
        raise WholeSystemMeasurementError(f"source_path is not a regular file: {relative_path}")
    return resolved


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceBundleEvidence:
    files: tuple[tuple[str, str], ...]
    schema: str = SOURCE_BUNDLE_SCHEMA
    classification: str = MEASUREMENT_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != SOURCE_BUNDLE_SCHEMA or self.classification != MEASUREMENT_CLASSIFICATION:
            raise WholeSystemMeasurementError("source bundle schema/classification mismatch")
        if not self.files or len(self.files) > _MAX_PATHS:
            raise WholeSystemMeasurementError("source bundle must contain a bounded non-empty file set")
        normalized: list[tuple[str, str]] = []
        for entry in self.files:
            if type(entry) is not tuple or len(entry) != 2:
                raise WholeSystemMeasurementError("source bundle entries must be exact (path, sha256) tuples")
            path, sha256 = entry
            normalized.append((_safe_relative_path(path), _sha("source_file_sha256", sha256)))
        normalized_tuple = tuple(sorted(normalized))
        if len({path for path, _ in normalized_tuple}) != len(normalized_tuple):
            raise WholeSystemMeasurementError("source bundle contains duplicate paths")
        object.__setattr__(self, "files", normalized_tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "classification": self.classification,
            "files": [{"path": path, "sha256": sha256} for path, sha256 in self.files],
            "runtime_authority": "NONE",
            "whole_system_acceptance": False,
        }

    def sha256(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True, kw_only=True)
class HostEnvironmentEvidence:
    os_name: str
    sys_platform: str
    platform_system: str
    platform_release: str
    machine: str
    python_implementation: str
    python_version: str
    byteorder: str
    schema: str = ENVIRONMENT_SCHEMA
    classification: str = MEASUREMENT_CLASSIFICATION

    def __post_init__(self) -> None:
        if self.schema != ENVIRONMENT_SCHEMA or self.classification != MEASUREMENT_CLASSIFICATION:
            raise WholeSystemMeasurementError("environment schema/classification mismatch")
        for name in (
            "os_name", "sys_platform", "platform_system", "platform_release", "machine",
            "python_implementation", "python_version", "byteorder",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update({"runtime_authority": "NONE", "whole_system_acceptance": False})
        return data

    def sha256(self) -> str:
        return _digest(self.as_dict())


def observe_source_bundle(*, repo_root: str | os.PathLike[str], source_paths: Iterable[str]) -> SourceBundleEvidence:
    """Hash the exact bytes of a bounded, symlink-free repository-relative file set."""
    if isinstance(source_paths, (str, bytes)):
        raise WholeSystemMeasurementError("source_paths must be an iterable of paths")
    paths = tuple(_safe_relative_path(path) for path in source_paths)
    if not paths or len(paths) > _MAX_PATHS or len(set(paths)) != len(paths):
        raise WholeSystemMeasurementError("source_paths must be a bounded non-empty unique set")
    root = Path(repo_root).resolve(strict=True)
    return SourceBundleEvidence(files=tuple((path, _file_sha256(_resolve_regular_file(root, path))) for path in paths))


def observe_host_environment() -> HostEnvironmentEvidence:
    """Observe stable-enough host/runtime facts without hostname, account, or secret material."""
    return HostEnvironmentEvidence(
        os_name=os.name,
        sys_platform=sys.platform,
        platform_system=platform.system() or "UNKNOWN",
        platform_release=platform.release() or "UNKNOWN",
        machine=platform.machine() or "UNKNOWN",
        python_implementation=platform.python_implementation() or "UNKNOWN",
        python_version=platform.python_version() or "UNKNOWN",
        byteorder=sys.byteorder,
    )


def _peak_rss_bytes() -> int:
    """Return process high-water RSS with platform semantics made explicit."""
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if type(value) not in {int, float} or value < 0:
        raise WholeSystemMeasurementError("ru_maxrss returned an invalid value")
    if sys.platform.startswith("linux"):
        return int(value) * 1024
    if sys.platform == "darwin":
        return int(value)
    raise WholeSystemMeasurementError("peak RSS conversion is not admitted on this platform")


def _callable_source_relative_path(name: str, function: Callable[..., Any], repo_root: Path) -> str:
    if not inspect.isfunction(function):
        raise WholeSystemMeasurementError(f"{name} must be an exact named Python function")
    source = inspect.getsourcefile(function)
    if source is None:
        raise WholeSystemMeasurementError(f"{name} source file could not be resolved")
    source_path = Path(source).resolve(strict=True)
    root = repo_root.resolve(strict=True)
    try:
        relative = source_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise WholeSystemMeasurementError(f"{name} source is outside repo_root") from exc
    if function.__name__ == "<lambda>" or "<locals>" in function.__qualname__:
        raise WholeSystemMeasurementError(f"{name} must be a stable module-level named function")
    return _safe_relative_path(relative)


def measure_characterization_sample(
    *,
    run_id: str,
    trial_index: int,
    repo_root: str | os.PathLike[str],
    source_paths: Iterable[str],
    whole_loop_seal: WholePersistentLoopSeal,
    operation: Callable[[], _T],
    quality_scorer: Callable[[_T], int],
    provenance_refs: Iterable[str],
    metric_schema_id: str = DEFAULT_METRIC_SCHEMA,
) -> CharacterizationSample:
    """Measure one operation and emit one source/host/seal-bound sample candidate.

    Source bytes and environment are observed both before and after the operation. Any drift
    rejects the sample. A successful return is still only a measurement candidate; this
    function has no authority to declare target-runtime or whole-system acceptance.
    """
    run_id = _text("run_id", run_id)
    if type(trial_index) is not int or trial_index < 0:
        raise WholeSystemMeasurementError("trial_index must be a non-negative integer")
    if type(whole_loop_seal) is not WholePersistentLoopSeal:
        raise WholeSystemMeasurementError("whole_loop_seal must be a concrete WholePersistentLoopSeal")
    if not callable(quality_scorer):
        raise WholeSystemMeasurementError("quality_scorer must be callable")
    metric_schema_id = _text("metric_schema_id", metric_schema_id)
    refs = _refs(provenance_refs)

    root = Path(repo_root).resolve(strict=True)
    operation_path = _callable_source_relative_path("operation", operation, root)
    quality_scorer_path = _callable_source_relative_path("quality_scorer", quality_scorer, root)
    normalized_source_paths = tuple(_safe_relative_path(path) for path in source_paths)
    if operation_path not in normalized_source_paths:
        raise WholeSystemMeasurementError("operation source file must be included in source_paths")
    if quality_scorer_path not in normalized_source_paths:
        raise WholeSystemMeasurementError("quality_scorer source file must be included in source_paths")

    source_before = observe_source_bundle(repo_root=root, source_paths=normalized_source_paths)
    environment_before = observe_host_environment()
    loop_sha256_before = whole_loop_seal.sha256()
    rss_before = _peak_rss_bytes()
    started_ns = time.perf_counter_ns()
    result = operation()
    finished_ns = time.perf_counter_ns()
    rss_after = _peak_rss_bytes()
    quality = quality_scorer(result)
    if type(quality) is not int or not 0 <= quality <= 1_000_000:
        raise WholeSystemMeasurementError("quality_scorer must return integer micros in [0, 1000000]")
    loop_sha256_after = whole_loop_seal.sha256()
    environment_after = observe_host_environment()
    source_after = observe_source_bundle(repo_root=root, source_paths=normalized_source_paths)

    if finished_ns < started_ns:
        raise WholeSystemMeasurementError("monotonic measurement clock moved backwards")
    if source_after != source_before:
        raise WholeSystemMeasurementError("source bundle changed during operation or quality scoring")
    if environment_after != environment_before:
        raise WholeSystemMeasurementError("host environment fingerprint changed during measured operation")
    if loop_sha256_after != loop_sha256_before:
        raise WholeSystemMeasurementError("whole-loop seal changed during measured operation")

    sample_principal = {
        "run_id": run_id,
        "trial_index": trial_index,
        "source_bundle_sha256": source_before.sha256(),
        "whole_loop_seal_sha256": loop_sha256_before,
        "environment_fingerprint_sha256": environment_before.sha256(),
        "metric_schema_id": metric_schema_id,
        "operation_module": operation.__module__,
        "operation_qualname": operation.__qualname__,
        "quality_scorer_module": quality_scorer.__module__,
        "quality_scorer_qualname": quality_scorer.__qualname__,
    }
    sample_id = f"wp902:{run_id}:{trial_index}:{_digest(sample_principal)[:24]}"
    generated_refs = (
        f"wp902:source-bundle:{source_before.sha256()}",
        f"wp902:environment:{environment_before.sha256()}",
        f"wp900:whole-loop-seal:{whole_loop_seal.seal_id}:{loop_sha256_before}",
        f"wp902:operation:{operation.__module__}:{operation.__qualname__}:{operation_path}",
        f"wp902:quality-scorer:{quality_scorer.__module__}:{quality_scorer.__qualname__}:{quality_scorer_path}",
        "wp902:clock:time.perf_counter_ns",
        f"wp902:rss:process-high-water:{sys.platform}",
    )
    all_refs = tuple(sorted(set(refs + generated_refs)))

    try:
        return CharacterizationSample(
            sample_id=sample_id,
            source_bundle_sha256=source_before.sha256(),
            whole_loop_seal_sha256=loop_sha256_before,
            environment_fingerprint_sha256=environment_before.sha256(),
            metric_schema_id=metric_schema_id,
            latency_ns=finished_ns - started_ns,
            peak_rss_bytes=max(rss_before, rss_after),
            quality_micros=quality,
            provenance_refs=all_refs,
        )
    except WholeSystemCharacterizationError as exc:
        raise WholeSystemMeasurementError(f"characterization sample admission rejected: {exc}") from exc


__all__ = [
    "ENVIRONMENT_SCHEMA",
    "MEASUREMENT_CLASSIFICATION",
    "SOURCE_BUNDLE_SCHEMA",
    "HostEnvironmentEvidence",
    "SourceBundleEvidence",
    "WholeSystemMeasurementError",
    "measure_characterization_sample",
    "observe_host_environment",
    "observe_source_bundle",
]
