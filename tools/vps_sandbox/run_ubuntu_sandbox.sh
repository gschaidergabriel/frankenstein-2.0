#!/usr/bin/env bash
set -Eeuo pipefail

# Execute a command in a disposable Ubuntu target-like sandbox while keeping
# the owner host, checkout and unrelated persistent state outside the writable boundary.
# Preferred backends: provisioned systemd-nspawn, Podman, Docker.

backend="${F2_SANDBOX_BACKEND:-auto}"
network="${F2_SANDBOX_NETWORK:-off}"
cpus="${F2_SANDBOX_CPUS:-2}"
memory="${F2_SANDBOX_MEMORY:-4g}"
pids="${F2_SANDBOX_PIDS:-1024}"
sandbox_root="$(readlink -m -- "${F2_SANDBOX_ROOT:-/var/tmp/frankenstein2-sandboxes}")"
nspawn_base="$(readlink -m -- "${F2_NSPAWN_BASE_ROOT:-/var/lib/frankenstein2-sandbox-images/ubuntu-24.04-base}")"
workspace="$(readlink -m -- "${F2_SANDBOX_SOURCE_ROOT:-${GITHUB_WORKSPACE:-$PWD}}")"
name="f2-${GITHUB_RUN_ID:-manual}-${GITHUB_RUN_ATTEMPT:-1}-$$"

usage() {
  echo "usage: $0 [--backend auto|nspawn|podman|docker] [--network off|on] [--] command [args...]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend) backend="$2"; shift 2 ;;
    --network) network="$2"; shift 2 ;;
    --) shift; break ;;
    -h|--help) usage; exit 0 ;;
    *) break ;;
  esac
done

[[ $# -gt 0 ]] || { usage; exit 64; }
[[ "$network" == "off" || "$network" == "on" ]] || { echo "invalid network mode" >&2; exit 65; }
[[ -d "$workspace" ]] || { echo "source root missing: $workspace" >&2; exit 66; }

case "$sandbox_root" in
  /var/tmp/frankenstein2-sandboxes|/srv/frankenstein2-sandboxes|/opt/frankenstein2-sandboxes) ;;
  *)
    [[ "${F2_ALLOW_CUSTOM_SANDBOX_ROOT:-0}" == "1" ]] || {
      echo "refusing unapproved sandbox root: $sandbox_root" >&2; exit 67;
    }
    ;;
esac
case "$sandbox_root" in
  /|/home|/var|/var/tmp|/etc|/usr|/root|/boot|/srv|/opt)
    echo "refusing unsafe sandbox root: $sandbox_root" >&2; exit 68 ;;
esac

if [[ "$backend" == "auto" ]]; then
  if command -v systemd-nspawn >/dev/null 2>&1 && [[ -d "$nspawn_base" ]]; then
    backend="nspawn"
  elif command -v podman >/dev/null 2>&1; then
    backend="podman"
  elif command -v docker >/dev/null 2>&1; then
    backend="docker"
  else
    echo "no supported sandbox backend; run host_prepare_ubuntu_nspawn.sh or install Podman/Docker" >&2
    exit 69
  fi
fi

case "$backend" in nspawn|podman|docker) ;; *) echo "unsupported backend: $backend" >&2; exit 70 ;; esac

mkdir -p -- "$sandbox_root"

# A host sentinel proves the sandbox command did not erase the runner's own
# minimal control file. It is not sufficient evidence by itself, but catches gross boundary mistakes.
host_sentinel="$(mktemp /var/tmp/f2-host-survival.XXXXXX)"
printf 'host-survival:%s\n' "$name" > "$host_sentinel"
cleanup_host_sentinel() { rm -f -- "$host_sentinel"; }
trap cleanup_host_sentinel EXIT

run_oci() {
  local engine="$1"
  local -a net_args=()
  [[ "$network" == "off" ]] && net_args=(--network none)

  # Checkout is mounted read-only. A private writable copy is made inside the
  # disposable container so destructive tests cannot delete the canonical checkout.
  "$engine" run --rm \
    --name "$name" \
    --cpus "$cpus" \
    --memory "$memory" \
    --pids-limit "$pids" \
    --security-opt no-new-privileges \
    "${net_args[@]}" \
    --mount "type=bind,src=$workspace,dst=/f2-src,readonly" \
    ubuntu:24.04 \
    /bin/bash -lc '
      set -Eeuo pipefail
      mkdir -p /work
      cp -a /f2-src /work/f2
      cd /work/f2
      exec "$@"
    ' bash "$@"
}

safe_remove_run_root() {
  local path="$1"
  local resolved
  resolved="$(readlink -m -- "$path")"
  case "$resolved" in
    "$sandbox_root"/run-*) ;;
    *) echo "refusing cleanup outside sandbox run root: $resolved" >&2; return 90 ;;
  esac
  if [[ "$EUID" -eq 0 ]]; then
    rm -rf --one-file-system -- "$resolved"
  else
    sudo -n rm -rf --one-file-system -- "$resolved"
  fi
}

run_nspawn() {
  [[ -d "$nspawn_base" ]] || { echo "nspawn base not provisioned: $nspawn_base" >&2; exit 71; }
  command -v systemd-nspawn >/dev/null 2>&1 || { echo "systemd-nspawn missing" >&2; exit 72; }
  if [[ "$EUID" -ne 0 ]]; then sudo -n true >/dev/null 2>&1 || { echo "nspawn requires root/passwordless sudo" >&2; exit 73; }; fi

  local run_root="$sandbox_root/run-$name"
  local -a root_cmd=()
  [[ "$EUID" -eq 0 ]] || root_cmd=(sudo -n)

  "${root_cmd[@]}" mkdir -p -- "$run_root"
  # Copy-on-write where supported; otherwise a normal copy. The base image is never used as a writable test root.
  "${root_cmd[@]}" cp -a --reflink=auto "$nspawn_base/." "$run_root/"

  cleanup_nspawn() { safe_remove_run_root "$run_root" || true; }
  trap 'cleanup_nspawn; cleanup_host_sentinel' EXIT

  local -a net_args=(--private-network)
  if [[ "$network" == "on" ]]; then
    # Separate veth rather than host-network sharing. Internet reachability depends
    # on the host's admitted bridge/NAT configuration.
    net_args=(--network-veth)
  fi

  "${root_cmd[@]}" systemd-nspawn \
    --quiet \
    --register=no \
    --machine="$name" \
    --directory="$run_root" \
    "${net_args[@]}" \
    --bind-ro="$workspace:/f2-src" \
    /bin/bash -lc '
      set -Eeuo pipefail
      mkdir -p /work
      cp -a /f2-src /work/f2
      cd /work/f2
      exec "$@"
    ' bash "$@"

  cleanup_nspawn
  trap cleanup_host_sentinel EXIT
}

case "$backend" in
  podman) run_oci podman "$@" ;;
  docker) run_oci docker "$@" ;;
  nspawn) run_nspawn "$@" ;;
esac

if [[ ! -f "$host_sentinel" ]] || ! grep -qx "host-survival:$name" "$host_sentinel"; then
  echo "F2_SANDBOX_RESULT=FAIL reason=HOST_SURVIVAL_SENTINEL_LOST" >&2
  exit 91
fi

printf '%s\n' \
  "F2_SANDBOX_RESULT=PASS" \
  "backend=$backend" \
  "ubuntu_target=24.04" \
  "network=$network" \
  "source_mount=READ_ONLY" \
  "sandbox_local_mutation=ALLOWED" \
  "host_survival_sentinel=PASS" \
  "physical_local_credit=0" \
  "whole_system_acceptance=false"
