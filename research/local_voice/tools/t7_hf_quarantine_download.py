#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

REV_RE = re.compile(r"^[0-9a-fA-F]{40}$")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest(root: Path):
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "T7_SHA256_MANIFEST.json":
            rows.append(
                {
                    "path": str(path.relative_to(root)),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return rows


def select_cli():
    if shutil.which("hf"):
        return "hf"
    if shutil.which("huggingface-cli"):
        return "huggingface-cli"
    raise SystemExit("Neither hf nor huggingface-cli is installed.")


def resolved_target(root: Path, name: str) -> Path:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / name).resolve()
    if root != target and root not in target.parents:
        raise SystemExit("Target escapes model root.")
    return target


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Pinned Hugging Face model download into Trigger-7 quarantine; "
            "never executes model repository code."
        )
    )
    parser.add_argument("--repo-id", required=True)
    parser.add_argument(
        "--revision",
        required=True,
        help="Exact 40-hex Hugging Face commit SHA; mutable branches/tags are rejected.",
    )
    parser.add_argument("--name", required=True, help="Local quarantine directory name.")
    parser.add_argument(
        "--root",
        default=os.environ.get(
            "FRANKENSTEIN_T7_MODEL_ROOT",
            str(Path.home() / ".cache" / "frankenstein2" / "trigger7" / "models"),
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not REPO_RE.fullmatch(args.repo_id):
        raise SystemExit("repo-id must be owner/model with conservative characters only.")
    if not REV_RE.fullmatch(args.revision):
        raise SystemExit("revision must be an immutable 40-hex commit SHA.")
    if not NAME_RE.fullmatch(args.name):
        raise SystemExit("name contains unsupported characters.")

    root = Path(args.root)
    target = resolved_target(root, args.name)
    if target.exists() and any(target.iterdir()):
        raise SystemExit(
            "Refusing to overwrite a non-empty quarantine directory: " + str(target)
        )

    cli = select_cli()
    cmd = [
        cli,
        "download",
        args.repo_id,
        "--revision",
        args.revision,
        "--local-dir",
        str(target),
    ]
    receipt = {
        "schema_version": 1,
        "repo_id": args.repo_id,
        "revision": args.revision.lower(),
        "target": str(target),
        "command": cmd,
        "executes_remote_code": False,
        "started_unix": time.time(),
    }

    if args.dry_run:
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return

    target.mkdir(parents=True, exist_ok=False)
    proc = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    receipt["returncode"] = proc.returncode
    receipt["stdout_tail"] = proc.stdout[-12000:]
    receipt["stderr_tail"] = proc.stderr[-12000:]

    if proc.returncode != 0:
        (target / "T7_DOWNLOAD_FAILURE.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True)
        )
        raise SystemExit(proc.returncode)

    receipt["files"] = manifest(target)
    receipt["total_bytes"] = sum(row["bytes"] for row in receipt["files"])
    (target / "T7_SHA256_MANIFEST.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True)
    )
    print(
        json.dumps(
            {
                "status": "OK",
                "target": str(target),
                "files": len(receipt["files"]),
                "total_bytes": receipt["total_bytes"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
