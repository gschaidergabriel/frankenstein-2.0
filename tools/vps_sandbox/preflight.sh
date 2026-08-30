#!/usr/bin/env bash
set -Eeuo pipefail

# Read-only preflight for the owner-authorized VPS Ubuntu sandbox lane.
# It does not install packages or delete anything.

sandbox_root="${F2_SANDBOX_ROOT:-/var/tmp/frankenstein2-sandboxes}"
min_free_kib="${F2_SANDBOX_MIN_FREE_KIB:-5242880}"   # 5 GiB
min_mem_kib="${F2_SANDBOX_MIN_MEM_KIB:-1048576}"    # 1 GiB

canonical_root="$(readlink -m -- "$sandbox_root")"
case "$canonical_root" in
  /var/tmp/frankenstein2-sandboxes|/srv/frankenstein2-sandboxes|/opt/frankenstein2-sandboxes)
    ;;
  *)
    if [[ "${F2_ALLOW_CUSTOM_SANDBOX_ROOT:-0}" != "1" ]]; then
      echo "F2_SANDBOX_PREFLIGHT=FAIL reason=UNAPPROVED_SANDBOX_ROOT root=$canonical_root" >&2
      exit 40
    fi
    ;;
esac

case "$canonical_root" in
  /|/home|/var|/var/tmp|/etc|/usr|/root|/boot|/srv|/opt)
    echo "F2_SANDBOX_PREFLIGHT=FAIL reason=UNSAFE_SANDBOX_ROOT root=$canonical_root" >&2
    exit 41
    ;;
esac

host_root_source="$(findmnt -n -o SOURCE / 2>/dev/null || true)"
host_root_fstype="$(findmnt -n -o FSTYPE / 2>/dev/null || true)"
free_kib="$(df -Pk /var/tmp | awk 'NR==2 {print $4}')"
mem_kib="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"

if [[ -z "$free_kib" || "$free_kib" -lt "$min_free_kib" ]]; then
  echo "F2_SANDBOX_PREFLIGHT=FAIL reason=LOW_DISK free_kib=${free_kib:-0} required_kib=$min_free_kib" >&2
  exit 42
fi
if [[ -z "$mem_kib" || "$mem_kib" -lt "$min_mem_kib" ]]; then
  echo "F2_SANDBOX_PREFLIGHT=FAIL reason=LOW_MEMORY mem_available_kib=${mem_kib:-0} required_kib=$min_mem_kib" >&2
  exit 43
fi

backend="NONE"
if command -v systemd-nspawn >/dev/null 2>&1 && [[ -d "${F2_NSPAWN_BASE_ROOT:-/var/lib/frankenstein2-sandbox-images/ubuntu-24.04-base}" ]]; then
  backend="NSPAWN"
elif command -v podman >/dev/null 2>&1; then
  backend="PODMAN"
elif command -v docker >/dev/null 2>&1; then
  backend="DOCKER"
elif command -v systemd-nspawn >/dev/null 2>&1; then
  backend="NSPAWN_UNPROVISIONED"
fi

sudo_mode="NO"
if [[ "$EUID" -eq 0 ]]; then
  sudo_mode="ROOT"
elif command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
  sudo_mode="PASSWORDLESS"
fi

kvm="NO"
[[ -c /dev/kvm && -r /dev/kvm && -w /dev/kvm ]] && kvm="YES"

printf '%s\n' \
  "F2_SANDBOX_PREFLIGHT=PASS" \
  "sandbox_root=$canonical_root" \
  "backend=$backend" \
  "sudo_mode=$sudo_mode" \
  "kvm_available=$kvm" \
  "host_root_source=${host_root_source:-UNKNOWN}" \
  "host_root_fstype=${host_root_fstype:-UNKNOWN}" \
  "free_kib=$free_kib" \
  "mem_available_kib=$mem_kib"

if [[ "$backend" == "NONE" ]]; then
  echo "F2_SANDBOX_PREFLIGHT=DEGRADED reason=NO_SUPPORTED_SANDBOX_BACKEND" >&2
  exit 44
fi
