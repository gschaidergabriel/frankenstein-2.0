from __future__ import annotations

import hashlib
import io
import json
import platform
import posixpath
import re
import sys
import zipfile
import zlib

SCHEMA = "F2_TRIGGER6_RELEASE_ARTIFACT_SUBJECT_REPRO/v1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
FILES = {"a.txt": b"alpha\n", "dir/b.txt": b"beta\n"}


class SubjectError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_zip(order: list[str], timestamp: tuple[int, int, int, int, int, int], comment: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.comment = comment
        for name in order:
            zi = zipfile.ZipInfo(name, date_time=timestamp)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 3
            zi.external_attr = (0o100644 & 0xFFFF) << 16
            zi.extra = b""
            zi.comment = b""
            zf.writestr(zi, FILES[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return out.getvalue()


def make_normalized_zip(compression: int) -> bytes:
    out = io.BytesIO()
    kwargs = {"compression": compression}
    if compression == zipfile.ZIP_DEFLATED:
        kwargs["compresslevel"] = 9
    with zipfile.ZipFile(out, "w", **kwargs) as zf:
        zf.comment = b""
        for name in sorted(FILES):
            zi = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            zi.compress_type = compression
            zi.create_system = 3
            zi.external_attr = (0o100644 & 0xFFFF) << 16
            zi.extra = b""
            zi.comment = b""
            zf.writestr(zi, FILES[name], compress_type=compression, compresslevel=9 if compression == zipfile.ZIP_DEFLATED else None)
    return out.getvalue()


def extracted_inventory(blob: bytes) -> list[dict[str, object]]:
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        return [
            {"path": name, "size": len(zf.read(name)), "sha256": sha256(zf.read(name))}
            for name in sorted(zf.namelist())
        ]


def validate_subject(blob: bytes, filename: str, subject: dict[str, object]) -> None:
    required = {
        "artifact_filename",
        "artifact_sha256",
        "artifact_size_bytes",
        "release_manifest_sha256",
        "source_commit",
        "source_tree",
        "release_id",
        "build_id",
    }
    if set(subject) != required:
        raise SubjectError("subject:keys_mismatch")
    if subject["artifact_filename"] != filename:
        raise SubjectError("subject:artifact_filename:mismatch")
    if subject["artifact_size_bytes"] != len(blob):
        raise SubjectError("subject:artifact_size_bytes:mismatch")
    if subject["artifact_sha256"] != sha256(blob):
        raise SubjectError("subject:artifact_sha256:mismatch")
    if not isinstance(subject["release_manifest_sha256"], str) or not HEX64.fullmatch(subject["release_manifest_sha256"]):
        raise SubjectError("subject:release_manifest_sha256:invalid")


def validate_zip_topology(blob: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        names = [item.filename for item in zf.infolist()]
        if len(names) != len(set(names)):
            raise SubjectError("zip:duplicate_member_name")
        canonical: set[str] = set()
        for item in zf.infolist():
            name = item.filename
            if "\\" in name:
                raise SubjectError("zip:noncanonical_separator")
            if name.startswith("/"):
                raise SubjectError("zip:absolute_path")
            if "\x00" in name:
                raise SubjectError("zip:nul")
            parts = name.split("/")
            if any(part in {".", ".."} for part in parts):
                raise SubjectError("zip:dot_or_parent_segment")
            normalized = posixpath.normpath(name)
            if normalized.startswith("../") or normalized == "..":
                raise SubjectError("zip:parent_traversal")
            if normalized in canonical:
                raise SubjectError("zip:duplicate_canonical_member")
            canonical.add(normalized)
            unix_mode = (item.external_attr >> 16) & 0xFFFF
            file_type = unix_mode & 0o170000
            if file_type not in {0, 0o100000, 0o040000}:
                raise SubjectError("zip:nonregular_member_type")


def one_member_zip(name: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr(name, b"x")
    return out.getvalue()


def duplicate_zip() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("x", b"1")
        zf.writestr("x", b"2")
    return out.getvalue()


def run_case(name: str, fn, expect_reject: bool) -> dict[str, object]:
    try:
        fn()
        observed = "ACCEPT"
    except Exception as exc:
        observed = f"REJECT:{type(exc).__name__}:{exc}"
    passed = (observed.startswith("REJECT") if expect_reject else observed == "ACCEPT")
    return {"name": name, "observed": observed, "passed": passed}


def main() -> None:
    zip_a = make_zip(["a.txt", "dir/b.txt"], (2026, 8, 30, 9, 0, 0), b"A")
    zip_b = make_zip(["dir/b.txt", "a.txt"], (2026, 8, 30, 10, 0, 0), b"B")
    subject = {
        "artifact_filename": "frankenstein2.zip",
        "artifact_sha256": sha256(zip_a),
        "artifact_size_bytes": len(zip_a),
        "release_manifest_sha256": "a" * 64,
        "source_commit": "b" * 40,
        "source_tree": "c" * 40,
        "release_id": "release-1",
        "build_id": "build-1",
    }
    stored_1 = make_normalized_zip(zipfile.ZIP_STORED)
    stored_2 = make_normalized_zip(zipfile.ZIP_STORED)
    deflated_1 = make_normalized_zip(zipfile.ZIP_DEFLATED)
    deflated_2 = make_normalized_zip(zipfile.ZIP_DEFLATED)

    bad_size = dict(subject)
    bad_size["artifact_size_bytes"] = int(subject["artifact_size_bytes"]) + 1
    bad_name = dict(subject)
    bad_name["artifact_filename"] = "other.zip"

    cases = [
        run_case("exact_subject_accept", lambda: validate_subject(zip_a, "frankenstein2.zip", subject), False),
        run_case("same_payload_different_outer_reject", lambda: validate_subject(zip_b, "frankenstein2.zip", subject), True),
        run_case("size_mismatch_reject", lambda: validate_subject(zip_a, "frankenstein2.zip", bad_size), True),
        run_case("filename_mismatch_reject", lambda: validate_subject(zip_a, "frankenstein2.zip", bad_name), True),
        run_case("parent_traversal_reject", lambda: validate_zip_topology(one_member_zip("../x")), True),
        run_case("absolute_path_reject", lambda: validate_zip_topology(one_member_zip("/x")), True),
        run_case("backslash_reject", lambda: validate_zip_topology(one_member_zip("a\\b")), True),
        run_case("duplicate_name_reject", lambda: validate_zip_topology(duplicate_zip()), True),
        run_case("safe_topology_accept", lambda: validate_zip_topology(zip_a), False),
    ]

    report = {
        "schema": SCHEMA,
        "environment": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "zlib_compile": zlib.ZLIB_VERSION,
            "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION,
        },
        "outer_identity_falsifier": {
            "zip_a_sha256": sha256(zip_a),
            "zip_b_sha256": sha256(zip_b),
            "zip_a_size": len(zip_a),
            "zip_b_size": len(zip_b),
            "extracted_inventory_equal": extracted_inventory(zip_a) == extracted_inventory(zip_b),
            "extracted_inventory": extracted_inventory(zip_a),
        },
        "normalized_same_runtime_double_build": {
            "zip_stored_equal": stored_1 == stored_2,
            "zip_stored_sha256": sha256(stored_1),
            "zip_deflated_equal": deflated_1 == deflated_2,
            "zip_deflated_sha256": sha256(deflated_1),
            "scope": "SAME_RUNTIME_ONLY_NOT_CROSS_HOST_REPRODUCIBILITY_CREDIT",
        },
        "cases": cases,
        "passed": all(case["passed"] for case in cases),
        "research_credit": "LOCAL_E3_REPRODUCTION_ONLY",
        "runtime_credit": 0,
        "whole_system_credit": 0,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
