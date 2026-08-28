from __future__ import annotations

import errno
import fcntl
import hashlib
import os
import stat
import subprocess
from dataclasses import dataclass


class EntityOSIntegrityError(PermissionError):
    pass


class EntityOSOutcomeUnknown(RuntimeError):
    """The EntityOS child started, but no verified outcome was returned."""

    replay_permitted = False


@dataclass(frozen=True)
class EntityOSBridge:
    """Execute an exact SHA-256 pinned EntityOS snapshot, not a mutable path inode."""

    path: str
    sha256: str
    timeout: float = 10.0

    _MFD_EXEC = 0x0010
    _EXEC_PATH = "/usr/bin:/bin"

    @staticmethod
    def _write_all(fd: int, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise EntityOSIntegrityError("EntityOS snapshot write failed")
            view = view[written:]

    @staticmethod
    def _seal_snapshot(fd: int) -> None:
        required = (
            "F_ADD_SEALS",
            "F_GET_SEALS",
            "F_SEAL_WRITE",
            "F_SEAL_SHRINK",
            "F_SEAL_GROW",
            "F_SEAL_SEAL",
        )
        if any(not hasattr(fcntl, name) for name in required):
            raise EntityOSIntegrityError("Linux file sealing unavailable")
        seals = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SEAL
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, seals)
        observed = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
        if observed & seals != seals:
            raise EntityOSIntegrityError("EntityOS snapshot seals incomplete")

    @classmethod
    def _new_exec_memfd(cls) -> int:
        if not hasattr(os, "memfd_create") or not hasattr(os, "MFD_ALLOW_SEALING"):
            raise EntityOSIntegrityError("Linux executable memfd unavailable")
        try:
            return os.memfd_create("EntityOS-verified", os.MFD_ALLOW_SEALING | cls._MFD_EXEC)
        except OSError as exc:
            if exc.errno != errno.EINVAL:
                raise EntityOSIntegrityError(f"EntityOS executable memfd failed: {exc}") from exc
            try:
                return os.memfd_create("EntityOS-verified", os.MFD_ALLOW_SEALING)
            except OSError as fallback_exc:
                raise EntityOSIntegrityError(f"EntityOS memfd fallback failed: {fallback_exc}") from fallback_exc

    def _open_verified(self) -> int:
        """Return an immutable executable snapshot fd whose bytes match the pin."""

        if len(self.sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in self.sha256):
            raise EntityOSIntegrityError("invalid EntityOS sha256 pin")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            source_fd = os.open(self.path, flags)
        except OSError as exc:
            raise EntityOSIntegrityError(f"EntityOS open failed: {exc}") from exc

        snapshot_fd: int | None = None
        try:
            st = os.fstat(source_fd)
            if not stat.S_ISREG(st.st_mode) or not (st.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)):
                raise EntityOSIntegrityError("EntityOS must be an executable regular file")

            snapshot_fd = self._new_exec_memfd()
            digest = hashlib.sha256()
            while True:
                chunk = os.read(source_fd, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                self._write_all(snapshot_fd, chunk)

            if digest.hexdigest().lower() != self.sha256.lower():
                raise EntityOSIntegrityError("EntityOS digest mismatch")

            os.fchmod(snapshot_fd, 0o500)
            self._seal_snapshot(snapshot_fd)
            os.lseek(snapshot_fd, 0, os.SEEK_SET)
            return snapshot_fd
        except Exception:
            if snapshot_fd is not None:
                os.close(snapshot_fd)
            raise
        finally:
            os.close(source_fd)

    def verify(self):
        """Fail-closed readiness probe for the exact sealed executable snapshot."""

        fd = self._open_verified()
        try:
            st = os.fstat(fd)
            return {
                "path": self.path,
                "sha256": self.sha256.lower(),
                "size": int(st.st_size),
                "mode": stat.S_IMODE(st.st_mode),
                "snapshot": "sealed-memfd",
            }
        finally:
            os.close(fd)

    @staticmethod
    def _reap_after_unknown(proc: subprocess.Popen[bytes]) -> None:
        """Best-effort local cleanup; terminating a child cannot undo prior effects."""

        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=1.0)
        except Exception:
            pass

    def run(self, argv):
        if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or "\x00" in x for x in argv):
            raise ValueError("explicit non-empty string argv required")
        fd = self._open_verified()
        try:
            executable = f"/proc/self/fd/{fd}"
            proc = subprocess.Popen(
                [executable, *argv],
                executable=executable,
                pass_fds=(fd,),
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={"PATH": self._EXEC_PATH},
            )
            try:
                stdout, stderr = proc.communicate(timeout=self.timeout)
            except Exception as exc:
                self._reap_after_unknown(proc)
                raise EntityOSOutcomeUnknown(
                    f"EntityOS return unknown after child start: {type(exc).__name__}"
                ) from exc
            returncode = proc.returncode
            if returncode is None:
                self._reap_after_unknown(proc)
                raise EntityOSOutcomeUnknown(
                    "EntityOS return code unresolved after child start"
                )
        finally:
            os.close(fd)
        return {
            "ok": returncode == 0,
            "exit": returncode,
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
            "stdout": stdout[:4096].decode(errors="replace"),
            "stderr": stderr[:4096].decode(errors="replace"),
        }
