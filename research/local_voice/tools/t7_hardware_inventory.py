#!/usr/bin/env python3
import glob
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, timeout=3):
    exe = shutil.which(cmd[0])
    if not exe:
        return {"available": False}
    try:
        p = subprocess.run(
            [exe, *cmd[1:]],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "available": True,
            "returncode": p.returncode,
            "stdout": p.stdout[-12000:],
            "stderr": p.stderr[-4000:],
        }
    except Exception as exc:
        return {"available": True, "error": type(exc).__name__ + ": " + str(exc)}


def meminfo():
    out = {}
    path = Path("/proc/meminfo")
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
                out[key] = value.strip()
    return out


def disk(path):
    usage = shutil.disk_usage(path)
    return {
        "path": str(path),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
    }


def device_paths(pattern):
    return sorted(glob.glob(pattern))[:256]


def main():
    root = Path(
        os.environ.get(
            "FRANKENSTEIN_T7_MODEL_ROOT",
            Path.home() / ".cache" / "frankenstein2" / "trigger7",
        )
    ).expanduser()
    disk_probe = root.parent if root.parent.exists() else Path.home()
    probe = {
        "schema_version": 1,
        "host": platform.node(),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version,
        "cpu_count_logical": os.cpu_count(),
        "memory": meminfo(),
        "model_root": str(root),
        "disk": disk(disk_probe),
        "device_paths": {
            "linux_dri_render": device_paths("/dev/dri/renderD*"),
            "linux_dri_cards": device_paths("/dev/dri/card*"),
            "linux_audio": device_paths("/dev/snd/*"),
        },
        "commands": {
            "lscpu": run(["lscpu"]),
            "free": run(["free", "-b"]),
            "lspci": run(["lspci", "-nnk"]),
            "nvidia_smi": run(["nvidia-smi"]),
            "rocm_smi": run(["rocm-smi"]),
            "rocminfo": run(["rocminfo"]),
            "vulkaninfo": run(["vulkaninfo", "--summary"]),
            "clinfo": run(["clinfo", "--raw"]),
            "system_profiler_hardware": run(["system_profiler", "SPHardwareDataType"]),
            "system_profiler_graphics": run(["system_profiler", "SPDisplaysDataType"]),
            "sysctl_memsize": run(["sysctl", "-n", "hw.memsize"]),
            "ffmpeg": run(["ffmpeg", "-version"]),
            "aplay": run(["aplay", "--version"]),
            "arecord": run(["arecord", "--version"]),
            "pw_cli": run(["pw-cli", "--version"]),
            "pactl": run(["pactl", "--version"]),
            "llama_server": run(["llama-server", "--version"]),
            "ollama": run(["ollama", "--version"]),
            "hf": run(["hf", "--version"]),
            "huggingface_cli": run(["huggingface-cli", "--version"]),
        },
    }
    print(json.dumps(probe, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
