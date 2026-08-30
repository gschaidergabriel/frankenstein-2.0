from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "F2_MULTIMODAL_EMPIRICAL_LAB_RECEIPT/v1"

DEFAULT_CAPABILITIES = {
    "CAMERA_SEE": True,
    "CAMERA_ANALYZE": True,
    "MICROPHONE_CAPTURE": True,
    "SPEAKER_PLAYBACK": True,
    "MEDIA_FILE_READ": True,
    "MEDIA_FILE_DECODE": True,
    "TEST_MEDIA_DOWNLOAD_PUBLIC": True,
    "AUDIO_SYNTHESIS_TEST": True,
    "RAW_RETENTION": False,
    "REMOTE_FRAME": False,
    "EXTERNAL_VLM": False,
}


@dataclass(frozen=True)
class CommandProbe:
    command: list[str]
    available: bool
    returncode: int | None
    stdout: str
    stderr: str


def _run(command: list[str], timeout: float = 5.0) -> CommandProbe:
    exe = command[0]
    if shutil.which(exe) is None:
        return CommandProbe(command, False, None, "", f"{exe}: not found")
    try:
        cp = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return CommandProbe(command, True, cp.returncode, cp.stdout, cp.stderr)
    except Exception as exc:  # probe must fail closed, never hide failure
        return CommandProbe(command, True, None, "", repr(exc))


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _device_nodes(prefix: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for p in sorted(Path("/dev").glob(f"{prefix}*")):
        try:
            st = p.stat()
            nodes.append(
                {
                    "path": str(p),
                    "mode": oct(st.st_mode & 0o777),
                    "uid": st.st_uid,
                    "gid": st.st_gid,
                    "readable": os.access(p, os.R_OK),
                    "writable": os.access(p, os.W_OK),
                }
            )
        except OSError as exc:
            nodes.append({"path": str(p), "error": repr(exc)})
    return nodes


def inspect_host() -> dict[str, Any]:
    probes = {
        "wpctl_status": asdict(_run(["wpctl", "status"])),
        "pactl_sinks": asdict(_run(["pactl", "list", "short", "sinks"])),
        "pactl_sources": asdict(_run(["pactl", "list", "short", "sources"])),
        "v4l2_devices": asdict(_run(["v4l2-ctl", "--list-devices"])),
    }
    return {
        "host": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "uid": os.getuid() if hasattr(os, "getuid") else None,
            "gid": os.getgid() if hasattr(os, "getgid") else None,
        },
        "requested_capabilities": dict(DEFAULT_CAPABILITIES),
        "important_law": "REPOSITORY_CAPABILITY_REQUEST_IS_NOT_OS_PERMISSION",
        "video_device_nodes": _device_nodes("video"),
        "probes": probes,
    }


def media_manifest(paths: Iterable[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        item: dict[str, Any] = {"path": str(p), "exists": p.exists()}
        if p.is_file():
            h = hashlib.sha256()
            with p.open("rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(chunk)
            item.update({"size": p.stat().st_size, "sha256": h.hexdigest()})
        out.append(item)
    return out


def build_receipt(media: Iterable[str] = ()) -> dict[str, Any]:
    created_ns = time.time_ns()
    body = {
        "schema": SCHEMA,
        "created_unix_ns": created_ns,
        "host_probe": inspect_host(),
        "media": media_manifest(media),
        "evidence": {
            "file_replay_credit": 0,
            "physical_speaker_mic_credit": 0,
            "live_camera_credit": 0,
            "live_duplex_credit": 0,
            "whole_system_acceptance": False,
            "note": "Probe/configuration receipt only; execution credits require observed runs.",
        },
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    body["receipt_sha256"] = _hash_text(canonical)
    return body


def main() -> int:
    parser = argparse.ArgumentParser(
        description="F2 isolated multimodal empirical-lab host/media probe"
    )
    parser.add_argument("--media", action="append", default=[], help="media file to hash")
    parser.add_argument("--out", default="multimodal_empirical_lab_receipt.json")
    args = parser.parse_args()

    receipt = build_receipt(args.media)
    Path(args.out).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
