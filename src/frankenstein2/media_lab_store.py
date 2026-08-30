from __future__ import annotations

import argparse
import contextlib
import hashlib
import ipaddress
import json
import math
import mimetypes
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux VPS is authoritative.
    fcntl = None

SCHEMA = "F2_VPS_MEDIA_LAB_STORE/v1"
GIB = 1024 ** 3
MIB = 1024 ** 2
DEFAULT_MAX_BYTES = 10 * GIB
DEFAULT_LOW_WATER_BYTES = 8 * GIB
DEFAULT_MAX_AGE_HOURS = 72.0
CHUNK_BYTES = 1024 * 1024
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_MIME_PREFIXES = ("image/", "audio/", "video/")
ALLOWED_GENERIC_MIME = {
    "application/octet-stream",
    "application/ogg",
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
}
MEDIA_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif",
    ".wav", ".flac", ".mp3", ".ogg", ".opus", ".m4a", ".aac", ".aiff", ".aif",
    ".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".mpeg", ".mpg", ".ts",
}


def _now_ns() -> int:
    return time.time_ns()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_BYTES), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_name(name: str) -> str:
    base = Path(name).name or "media.bin"
    cleaned = "".join(c if c.isalnum() or c in "._-" else "_" for c in base)
    return cleaned[:180] or "media.bin"


def _media_kind(path: Path, content_type: str | None = None) -> str:
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if ct.startswith("image/"):
        return "image"
    if ct.startswith("audio/"):
        return "audio"
    if ct.startswith("video/"):
        return "video"
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        if guessed.startswith("image/"):
            return "image"
        if guessed.startswith("audio/"):
            return "audio"
        if guessed.startswith("video/"):
            return "video"
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}:
        return "image"
    if ext in {".wav", ".flac", ".mp3", ".ogg", ".opus", ".m4a", ".aac", ".aiff", ".aif"}:
        return "audio"
    if ext in {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".mpeg", ".mpg", ".ts"}:
        return "video"
    return "unknown"


def _validate_public_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError(f"only http/https public media URLs are allowed: {url}")
    if not parsed.hostname:
        raise ValueError("URL has no hostname")
    host = parsed.hostname
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError(f"cannot resolve hostname {host!r}: {exc}") from exc
    for info in infos:
        addr = info[4][0]
        ip = ipaddress.ip_address(addr)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(f"refusing non-public target {host!r} -> {ip}")


class _PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class MediaLabStore:
    def __init__(
        self,
        root: Path | str | None = None,
        *,
        max_bytes: int | None = None,
        low_water_bytes: int | None = None,
        max_age_hours: float | None = None,
    ) -> None:
        env_root = os.environ.get("F2_MEDIA_LAB_ROOT")
        self.root = Path(root or env_root or "~/.cache/frankenstein2/media_lab").expanduser().resolve()
        self.objects = self.root / "objects"
        self.tmp = self.root / "tmp"
        self.receipts = self.root / "receipts"
        self.index_path = self.root / "index.json"
        self.lock_path = self.root / ".lock"

        self.max_bytes = int(
            max_bytes if max_bytes is not None
            else os.environ.get("F2_MEDIA_LAB_MAX_BYTES", DEFAULT_MAX_BYTES)
        )
        self.low_water_bytes = int(
            low_water_bytes if low_water_bytes is not None
            else os.environ.get("F2_MEDIA_LAB_LOW_WATER_BYTES", DEFAULT_LOW_WATER_BYTES)
        )
        self.max_age_hours = float(
            max_age_hours if max_age_hours is not None
            else os.environ.get("F2_MEDIA_LAB_MAX_AGE_HOURS", DEFAULT_MAX_AGE_HOURS)
        )

        if self.max_bytes <= 0 or self.max_bytes > DEFAULT_MAX_BYTES:
            raise ValueError("F2 media-lab hard cap may not exceed 10 GiB")
        if not 0 <= self.low_water_bytes <= self.max_bytes:
            raise ValueError("low-water bytes must be between 0 and max_bytes")

        for d in (self.root, self.objects, self.tmp, self.receipts):
            d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass
        if not self.index_path.exists():
            self._write_index({"schema": SCHEMA, "objects": {}})

    @contextlib.contextmanager
    def lock(self) -> Iterator[None]:
        self.lock_path.touch(exist_ok=True)
        with self.lock_path.open("r+") as fh:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def _read_index(self) -> dict[str, Any]:
        try:
            data = json.loads(self.index_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            data = {"schema": SCHEMA, "objects": {}}
        data.setdefault("schema", SCHEMA)
        data.setdefault("objects", {})
        return data

    def _write_index(self, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, raw = tempfile.mkstemp(prefix=".index.", suffix=".json", dir=self.root)
        p = Path(raw)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(p, self.index_path)
        finally:
            p.unlink(missing_ok=True)

    def _usage_bytes(self) -> int:
        total = 0
        for base in (self.objects, self.tmp):
            for p in base.rglob("*"):
                if p.is_file():
                    try:
                        total += p.stat().st_size
                    except FileNotFoundError:
                        pass
        return total

    def _active_lease(self, meta: dict[str, Any], now_ns: int | None = None) -> bool:
        until = int(meta.get("lease_until_ns") or 0)
        return until > (now_ns or _now_ns())

    def _prune_missing(self, index: dict[str, Any]) -> None:
        missing = []
        for digest, meta in index["objects"].items():
            p = Path(meta["path"])
            if not p.exists():
                missing.append(digest)
        for digest in missing:
            index["objects"].pop(digest, None)

    def _delete_digest(self, index: dict[str, Any], digest: str, reason: str) -> int:
        meta = index["objects"].get(digest)
        if not meta:
            return 0
        p = Path(meta["path"])
        size = int(meta.get("size") or 0)
        p.unlink(missing_ok=True)
        index["objects"].pop(digest, None)
        self._write_receipt(
            "delete",
            {"sha256": digest, "size": size, "reason": reason, "path": str(p)},
        )
        return size

    def _write_receipt(self, action: str, payload: dict[str, Any]) -> Path:
        body = {"schema": SCHEMA, "action": action, "created_unix_ns": _now_ns(), **payload}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        body["receipt_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
        name = f"{body['created_unix_ns']}_{action}.json"
        p = self.receipts / name
        p.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
        return p

    def gc(self, *, aggressive: bool = False, required_bytes: int = 0) -> dict[str, Any]:
        with self.lock():
            return self._gc_locked(aggressive=aggressive, required_bytes=required_bytes)

    def _gc_locked(self, *, aggressive: bool = False, required_bytes: int = 0) -> dict[str, Any]:
        index = self._read_index()
        self._prune_missing(index)
        now = _now_ns()
        max_age_ns = int(self.max_age_hours * 3600 * 1e9)
        deleted: list[dict[str, Any]] = []

        candidates = sorted(
            index["objects"].items(),
            key=lambda kv: int(kv[1].get("last_access_ns") or kv[1].get("created_ns") or 0),
        )
        for digest, meta in candidates:
            if self._active_lease(meta, now):
                continue
            last = int(meta.get("last_access_ns") or meta.get("created_ns") or 0)
            if max_age_ns > 0 and now - last > max_age_ns:
                size = self._delete_digest(index, digest, "MAX_AGE")
                deleted.append({"sha256": digest, "size": size, "reason": "MAX_AGE"})

        usage = self._usage_bytes()
        target = self.low_water_bytes if (aggressive or usage > int(self.max_bytes * 0.95)) else self.max_bytes
        target = min(target, self.max_bytes - max(0, required_bytes))
        target = max(0, target)

        if usage > target:
            candidates = sorted(
                index["objects"].items(),
                key=lambda kv: int(kv[1].get("last_access_ns") or kv[1].get("created_ns") or 0),
            )
            for digest, meta in candidates:
                if usage <= target:
                    break
                if self._active_lease(meta, now):
                    continue
                size = self._delete_digest(index, digest, "LRU_CAP")
                usage -= size
                deleted.append({"sha256": digest, "size": size, "reason": "LRU_CAP"})

        self._write_index(index)
        usage = self._usage_bytes()
        ok = usage + max(0, required_bytes) <= self.max_bytes
        if not ok:
            raise RuntimeError(
                f"media lab cannot reserve {required_bytes} bytes under {self.max_bytes} hard cap; "
                "active leases or in-flight temp files occupy the remaining budget"
            )
        return {
            "usage_bytes": usage,
            "max_bytes": self.max_bytes,
            "low_water_bytes": self.low_water_bytes,
            "required_bytes": required_bytes,
            "deleted": deleted,
        }

    def _ensure_capacity_locked(self, required_bytes: int) -> None:
        self._gc_locked(required_bytes=required_bytes)
        if self._usage_bytes() + required_bytes > self.max_bytes:
            raise RuntimeError("10 GiB media-lab hard cap would be exceeded")

    def ingest(
        self,
        source: Path | str,
        *,
        source_label: str = "LOCAL_GENERATED_OR_IMPORTED",
        content_type: str | None = None,
        original_name: str | None = None,
    ) -> dict[str, Any]:
        src = Path(source).expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError(src)
        size = src.stat().st_size
        if size > self.max_bytes:
            raise ValueError("single media asset exceeds media-lab hard cap")
        kind = _media_kind(src, content_type)
        if kind == "unknown":
            raise ValueError(f"not recognized as image/audio/video media: {src}")

        with self.lock():
            self._ensure_capacity_locked(size)
            digest = _sha256_file(src)
            index = self._read_index()
            existing = index["objects"].get(digest)
            now = _now_ns()
            if existing and Path(existing["path"]).exists():
                existing["last_access_ns"] = now
                self._write_index(index)
                return dict(existing)

            suffix = src.suffix.lower() if src.suffix.lower() in MEDIA_EXTENSIONS else ".bin"
            dst = self.objects / f"{digest}{suffix}"
            temp = self.tmp / f"{digest}.{os.getpid()}.ingest.part"
            shutil.copyfile(src, temp)
            if _sha256_file(temp) != digest:
                temp.unlink(missing_ok=True)
                raise RuntimeError("ingest hash mismatch")
            os.replace(temp, dst)
            meta = {
                "sha256": digest,
                "path": str(dst),
                "size": size,
                "kind": kind,
                "content_type": content_type,
                "original_name": _safe_name(original_name or src.name),
                "source": source_label,
                "created_ns": now,
                "last_access_ns": now,
                "lease_until_ns": 0,
            }
            index["objects"][digest] = meta
            self._write_index(index)
            self._write_receipt("ingest", meta)
            self._gc_locked()
            return dict(meta)

    def fetch(self, url: str, *, timeout: float = 60.0) -> dict[str, Any]:
        _validate_public_url(url)
        opener = urllib.request.build_opener(_PublicRedirectHandler())
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Frankenstein2-MediaLab/1.0",
                "Accept": "image/*,audio/*,video/*,application/octet-stream;q=0.8,*/*;q=0.1",
            },
        )

        with self.lock():
            part = self.tmp / f"download.{os.getpid()}.{_now_ns()}.part"
            try:
                with opener.open(request, timeout=timeout) as response:
                    final_url = response.geturl()
                    _validate_public_url(final_url)
                    content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
                    if content_type and not (
                        content_type.startswith(ALLOWED_MIME_PREFIXES)
                        or content_type in ALLOWED_GENERIC_MIME
                    ):
                        raise ValueError(f"refusing non-media content-type {content_type!r}")

                    length_raw = response.headers.get("Content-Length")
                    expected = int(length_raw) if length_raw and length_raw.isdigit() else 0
                    if expected > self.max_bytes:
                        raise ValueError("remote asset exceeds media-lab hard cap")
                    if expected:
                        self._ensure_capacity_locked(expected)
                    else:
                        self._gc_locked(aggressive=False)

                    h = hashlib.sha256()
                    total = 0
                    with part.open("wb") as fh:
                        while True:
                            chunk = response.read(CHUNK_BYTES)
                            if not chunk:
                                break
                            self._ensure_capacity_locked(len(chunk))
                            fh.write(chunk)
                            h.update(chunk)
                            total += len(chunk)
                            if total > self.max_bytes:
                                raise RuntimeError("download crossed 10 GiB hard cap")

                parsed = urllib.parse.urlparse(final_url)
                name = _safe_name(Path(parsed.path).name or "download.bin")
                suffix = Path(name).suffix.lower()
                kind = _media_kind(Path(name), content_type)
                if kind == "unknown":
                    raise ValueError("download completed but payload is not recognized image/audio/video media")

                digest = h.hexdigest()
                index = self._read_index()
                self._prune_missing(index)
                existing = index["objects"].get(digest)
                now = _now_ns()
                if existing and Path(existing["path"]).exists():
                    part.unlink(missing_ok=True)
                    existing["last_access_ns"] = now
                    self._write_index(index)
                    return dict(existing)

                if suffix not in MEDIA_EXTENSIONS:
                    ext = mimetypes.guess_extension(content_type) if content_type else None
                    suffix = ext if ext in MEDIA_EXTENSIONS else ".bin"
                dst = self.objects / f"{digest}{suffix}"
                os.replace(part, dst)
                meta = {
                    "sha256": digest,
                    "path": str(dst),
                    "size": total,
                    "kind": kind,
                    "content_type": content_type or None,
                    "original_name": name,
                    "source": "PUBLIC_URL",
                    "source_url": final_url,
                    "created_ns": now,
                    "last_access_ns": now,
                    "lease_until_ns": 0,
                }
                index["objects"][digest] = meta
                self._write_index(index)
                self._write_receipt("fetch", meta)
                self._gc_locked()
                return dict(meta)
            finally:
                part.unlink(missing_ok=True)

    def fetch_ytdlp(self, url: str, *, timeout: float = 900.0) -> dict[str, Any]:
        """Resolve a public page to one direct A/V URL, then use capped streaming fetch."""
        _validate_public_url(url)
        exe = shutil.which("yt-dlp")
        if not exe:
            raise RuntimeError("yt-dlp is not installed; run the VPS multimodal bootstrap")
        cmd = [
            exe,
            "--no-playlist",
            "--no-exec",
            "--get-url",
            "-f",
            "best[protocol=https][vcodec!=none][acodec!=none]/best[protocol=https]/best",
            url,
        ]
        cp = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
        if cp.returncode != 0:
            raise RuntimeError(f"yt-dlp URL resolution failed: {cp.stderr[-2000:]}")
        urls = [line.strip() for line in cp.stdout.splitlines() if line.strip()]
        if len(urls) != 1:
            raise RuntimeError(
                "yt-dlp did not resolve exactly one combined direct media URL; "
                "choose/resolve one combined format explicitly rather than bypassing the cap"
            )
        direct = urls[0]
        _validate_public_url(direct)
        return self.fetch(direct, timeout=timeout)

    def generate_tone(self, *, seconds: float, frequency: float, sample_rate: int = 48000) -> dict[str, Any]:
        if not (0.05 <= seconds <= 300.0):
            raise ValueError("tone duration must be 0.05..300 seconds")
        if not (20.0 <= frequency <= 20000.0):
            raise ValueError("frequency must be 20..20000 Hz")
        frames = int(seconds * sample_rate)
        temp = self.tmp / f"tone.{os.getpid()}.{_now_ns()}.wav"
        amplitude = 0.20 * 32767
        with wave.open(str(temp), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            buf = bytearray()
            for i in range(frames):
                sample = int(amplitude * math.sin(2.0 * math.pi * frequency * i / sample_rate))
                buf.extend(struct.pack("<h", sample))
                if len(buf) >= CHUNK_BYTES:
                    wf.writeframesraw(bytes(buf))
                    buf.clear()
            if buf:
                wf.writeframesraw(bytes(buf))
        try:
            return self.ingest(
                temp,
                source_label="LOCALLY_GENERATED_TONE",
                content_type="audio/wav",
                original_name=f"tone_{frequency:.1f}Hz_{seconds:.2f}s.wav",
            )
        finally:
            temp.unlink(missing_ok=True)

    def generate_speech(self, text: str, *, voice: str | None = None, speed: int = 165) -> dict[str, Any]:
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not exe:
            raise RuntimeError("espeak-ng/espeak not installed; run the VPS multimodal bootstrap")
        if not text.strip():
            raise ValueError("speech text must not be empty")
        temp = self.tmp / f"speech.{os.getpid()}.{_now_ns()}.wav"
        cmd = [exe, "-s", str(speed), "-w", str(temp)]
        if voice:
            cmd += ["-v", voice]
        cmd += [text]
        cp = subprocess.run(cmd, text=True, capture_output=True, timeout=120, check=False)
        if cp.returncode != 0:
            temp.unlink(missing_ok=True)
            raise RuntimeError(f"speech generation failed: {cp.stderr[-2000:]}")
        try:
            return self.ingest(
                temp,
                source_label="LOCALLY_GENERATED_SPEECH",
                content_type="audio/wav",
                original_name="generated_speech.wav",
            )
        finally:
            temp.unlink(missing_ok=True)

    def generate_ffmpeg(self, *, kind: str, seconds: float = 5.0, size: str = "1280x720", fps: int = 24) -> dict[str, Any]:
        exe = shutil.which("ffmpeg")
        if not exe:
            raise RuntimeError("ffmpeg not installed; run the VPS multimodal bootstrap")
        if kind not in {"image", "video"}:
            raise ValueError("kind must be image or video")
        if kind == "image":
            temp = self.tmp / f"testsrc.{os.getpid()}.{_now_ns()}.png"
            cmd = [
                exe, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=1",
                "-frames:v", "1", str(temp),
            ]
            ctype = "image/png"
            label = "LOCALLY_GENERATED_IMAGE"
        else:
            if not (0.1 <= seconds <= 300.0):
                raise ValueError("video duration must be 0.1..300 seconds")
            temp = self.tmp / f"testsrc.{os.getpid()}.{_now_ns()}.mp4"
            cmd = [
                exe, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={fps}",
                "-t", str(seconds), "-pix_fmt", "yuv420p", str(temp),
            ]
            ctype = "video/mp4"
            label = "LOCALLY_GENERATED_VIDEO"
        cp = subprocess.run(cmd, text=True, capture_output=True, timeout=180, check=False)
        if cp.returncode != 0:
            temp.unlink(missing_ok=True)
            raise RuntimeError(f"ffmpeg generation failed: {cp.stderr[-2000:]}")
        try:
            return self.ingest(temp, source_label=label, content_type=ctype, original_name=temp.name)
        finally:
            temp.unlink(missing_ok=True)

    def touch(self, digest: str, *, lease_seconds: float = 0.0) -> dict[str, Any]:
        with self.lock():
            index = self._read_index()
            meta = index["objects"].get(digest)
            if not meta:
                raise KeyError(digest)
            now = _now_ns()
            meta["last_access_ns"] = now
            if lease_seconds > 0:
                meta["lease_until_ns"] = now + int(lease_seconds * 1e9)
            self._write_index(index)
            return dict(meta)

    def delete(self, digest: str) -> None:
        with self.lock():
            index = self._read_index()
            meta = index["objects"].get(digest)
            if not meta:
                return
            if self._active_lease(meta):
                raise RuntimeError("asset has active lease")
            self._delete_digest(index, digest, "EXPLICIT_DELETE")
            self._write_index(index)

    def status(self) -> dict[str, Any]:
        with self.lock():
            index = self._read_index()
            self._prune_missing(index)
            self._write_index(index)
            usage = self._usage_bytes()
            now = _now_ns()
            objects = list(index["objects"].values())
            return {
                "schema": SCHEMA,
                "root": str(self.root),
                "usage_bytes": usage,
                "max_bytes": self.max_bytes,
                "free_budget_bytes": max(0, self.max_bytes - usage),
                "object_count": len(objects),
                "active_leases": sum(1 for x in objects if self._active_lease(x, now)),
                "max_age_hours": self.max_age_hours,
                "objects": sorted(objects, key=lambda x: int(x.get("last_access_ns") or 0), reverse=True),
            }


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Frankenstein 2 VPS multimodal research media store")
    parser.add_argument("--root", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    gc_p = sub.add_parser("gc")
    gc_p.add_argument("--aggressive", action="store_true")
    ingest_p = sub.add_parser("ingest")
    ingest_p.add_argument("path")
    fetch_p = sub.add_parser("fetch")
    fetch_p.add_argument("url")
    fetch_p.add_argument("--timeout", type=float, default=60.0)
    ytdlp_p = sub.add_parser("fetch-ytdlp")
    ytdlp_p.add_argument("url")
    ytdlp_p.add_argument("--timeout", type=float, default=900.0)
    tone_p = sub.add_parser("tone")
    tone_p.add_argument("--seconds", type=float, default=1.0)
    tone_p.add_argument("--frequency", type=float, default=997.0)
    speech_p = sub.add_parser("speech")
    speech_p.add_argument("text")
    speech_p.add_argument("--voice", default=None)
    speech_p.add_argument("--speed", type=int, default=165)
    gen_p = sub.add_parser("generate")
    gen_p.add_argument("kind", choices=("image", "video"))
    gen_p.add_argument("--seconds", type=float, default=5.0)
    gen_p.add_argument("--size", default="1280x720")
    gen_p.add_argument("--fps", type=int, default=24)
    touch_p = sub.add_parser("touch")
    touch_p.add_argument("sha256")
    touch_p.add_argument("--lease-seconds", type=float, default=0.0)
    delete_p = sub.add_parser("delete")
    delete_p.add_argument("sha256")

    args = parser.parse_args()
    store = MediaLabStore(args.root)
    if args.command == "status":
        _print(store.status())
    elif args.command == "gc":
        _print(store.gc(aggressive=args.aggressive))
    elif args.command == "ingest":
        _print(store.ingest(args.path))
    elif args.command == "fetch":
        _print(store.fetch(args.url, timeout=args.timeout))
    elif args.command == "fetch-ytdlp":
        _print(store.fetch_ytdlp(args.url, timeout=args.timeout))
    elif args.command == "tone":
        _print(store.generate_tone(seconds=args.seconds, frequency=args.frequency))
    elif args.command == "speech":
        _print(store.generate_speech(args.text, voice=args.voice, speed=args.speed))
    elif args.command == "generate":
        _print(store.generate_ffmpeg(kind=args.kind, seconds=args.seconds, size=args.size, fps=args.fps))
    elif args.command == "touch":
        _print(store.touch(args.sha256, lease_seconds=args.lease_seconds))
    elif args.command == "delete":
        store.delete(args.sha256)
        _print({"deleted": args.sha256})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
