#!/usr/bin/env bash
set -Eeuo pipefail

# Execute a command in a disposable Ubuntu target-like sandbox while keeping
# the owner host, checkout and unrelated persistent state outside the writable boundary.
# Auto mode prefers resource-bounded Podman/Docker. Use --backend nspawn when
# closer systemd/userspace fidelity is required and the nspawn base is provisioned.
#
# --boot-systemd is an opt-in S2 mode. It boots the disposable nspawn clone with
# systemd as PID 1, registers the machine only for the lifetime of the probe, and
# executes the requested command through that live system manager. It never changes
# the reusable base or the canonical checkout and is deliberately unavailable to OCI.
backend="${F2_SANDBOX_BACKEND:-auto}"
network="${F2_SANDBOX_NETWORK:-off}"
cpus="${F2_SANDBOX_CPUS:-2}"
memory="${F2_SANDBOX_MEMORY:-4g}"
pids="${F2_SANDBOX_PIDS:-1024}"
sandbox_root="$(readlink -m -- "${F2_SANDBOX_ROOT:-/var/tmp/frankenstein2-sandboxes}")"
nspawn_base="$(readlink -m -- "${F2_NSPAWN_BASE_ROOT:-/var/lib/frankenstein2-sandbox-images/ubuntu-24.04-base-v2}")"
workspace="$(readlink -m -- "${F2_SANDBOX_SOURCE_ROOT:-${GITHUB_WORKSPACE:-$PWD}}")"
name="f2-${GITHUB_RUN_ID:-manual}-${GITHUB_RUN_ATTEMPT:-1}-$$"
boot_systemd=0

usage() {
  echo "usage: $0 [--backend auto|nspawn|podman|docker] [--network off|on] [--boot-systemd] [--] command [args...]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend) backend="$2"; shift 2 ;;
    --network) network="$2"; shift 2 ;;
    --boot-systemd) boot_systemd=1; shift ;;
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
  if [[ "$boot_systemd" == "1" ]] && command -v systemd-nspawn >/dev/null 2>&1 && [[ -d "$nspawn_base" ]]; then
    backend="nspawn"
  elif command -v podman >/dev/null 2>&1; then
    backend="podman"
  elif command -v docker >/dev/null 2>&1; then
    backend="docker"
  elif command -v systemd-nspawn >/dev/null 2>&1 && [[ -d "$nspawn_base" ]]; then
    backend="nspawn"
  else
    echo "no supported sandbox backend; run host_prepare_ubuntu_nspawn.sh or install Podman/Docker" >&2
    exit 69
  fi
fi

case "$backend" in nspawn|podman|docker) ;; *) echo "unsupported backend: $backend" >&2; exit 70 ;; esac
if [[ "$boot_systemd" == "1" && "$backend" != "nspawn" ]]; then
  echo "--boot-systemd requires --backend nspawn (S2)" >&2
  exit 74
fi

mkdir -p -- "$sandbox_root"

# A host sentinel proves the sandbox command did not erase the runner's own
# minimal control file. It is not sufficient evidence by itself, but catches gross boundary mistakes.
host_sentinel="$(mktemp /var/tmp/f2-host-survival.XXXXXX)"
printf 'host-survival:%s\n' "$name" > "$host_sentinel"
cleanup_host_sentinel() { rm -f -- "$host_sentinel"; }
trap cleanup_host_sentinel EXIT

run_oci() {
  local engine="$1"
  shift
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

validate_nspawn_base() {
  local marker="$nspawn_base/.f2-sandbox-base.json"
  [[ -d "$nspawn_base" ]] || { echo "nspawn base not provisioned: $nspawn_base" >&2; return 1; }
  [[ -f "$marker" ]] || { echo "nspawn base marker missing: $marker" >&2; return 1; }
  grep -q '"schema":"F2_VPS_SANDBOX_BASE/v2"' "$marker" || {
    echo "nspawn base marker is not v2-capability-bound: $marker" >&2; return 1;
  }
  grep -q '"suite":"noble"' "$marker" || { echo "nspawn base suite mismatch" >&2; return 1; }
  [[ -x "$nspawn_base/usr/bin/python3" ]] || { echo "nspawn base missing python3 capability" >&2; return 1; }
  [[ -x "$nspawn_base/usr/bin/git" ]] || { echo "nspawn base missing git capability" >&2; return 1; }
  [[ -x "$nspawn_base/usr/bin/curl" ]] || { echo "nspawn base missing curl capability" >&2; return 1; }
  [[ -x "$nspawn_base/bin/bash" || -x "$nspawn_base/usr/bin/bash" ]] || { echo "nspawn base missing bash capability" >&2; return 1; }
}

run_nspawn() {
  validate_nspawn_base || exit 71
  command -v systemd-nspawn >/dev/null 2>&1 || { echo "systemd-nspawn missing" >&2; exit 72; }
  if [[ "$EUID" -ne 0 ]]; then sudo -n true >/dev/null 2>&1 || { echo "nspawn requires root/passwordless sudo" >&2; exit 73; }; fi

  local run_root="$sandbox_root/run-$name"
  local -a root_cmd=()
  [[ "$EUID" -eq 0 ]] || root_cmd=(sudo -n)
  local nspawn_pid=""
  local machine_registered=0

  "${root_cmd[@]}" mkdir -p -- "$run_root"
  # Copy-on-write where supported; otherwise a normal copy. The base image is never used as a writable test root.
  "${root_cmd[@]}" cp -a --reflink=auto "$nspawn_base/." "$run_root/"

  cleanup_nspawn() {
    if [[ "$machine_registered" == "1" ]]; then
      "${root_cmd[@]}" machinectl terminate "$name" >/dev/null 2>&1 || true
      machine_registered=0
    fi
    if [[ -n "$nspawn_pid" ]]; then
      for _ in $(seq 1 40); do
        kill -0 "$nspawn_pid" >/dev/null 2>&1 || break
        sleep 0.25
      done
      if kill -0 "$nspawn_pid" >/dev/null 2>&1; then
        kill "$nspawn_pid" >/dev/null 2>&1 || true
      fi
      wait "$nspawn_pid" >/dev/null 2>&1 || true
      nspawn_pid=""
    fi
    safe_remove_run_root "$run_root" || true
  }
  trap 'cleanup_nspawn; cleanup_host_sentinel' EXIT

  local -a net_args=(--private-network)
  if [[ "$network" == "on" ]]; then
    # Separate veth rather than host-network sharing. Internet reachability depends
    # on the host's admitted bridge/NAT configuration.
    net_args=(--network-veth)
  fi

  if [[ "$boot_systemd" == "0" ]]; then
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
  else
    command -v machinectl >/dev/null 2>&1 || { echo "machinectl missing for --boot-systemd" >&2; exit 75; }
    command -v systemd-run >/dev/null 2>&1 || { echo "systemd-run missing for --boot-systemd" >&2; exit 76; }

    # Give each disposable clone its own machine identity. The reusable base must
    # never accumulate a boot-derived identity that all future clones would share.
    "${root_cmd[@]}" rm -f -- "$run_root/var/lib/dbus/machine-id"
    "${root_cmd[@]}" sh -c ": > '$run_root/etc/machine-id'"

    # Store the caller's argv as shell-escaped data in the disposable clone.
    # This avoids re-parsing untrusted argv through an extra interpolation layer.
    {
      printf '%s\n' '#!/usr/bin/env bash' 'set -Eeuo pipefail' \
        'mkdir -p /work' \
        'rm -rf /work/f2' \
        'cp -a /f2-src /work/f2' \
        'cd /work/f2'
      printf 'exec'
      printf ' %q' "$@"
      printf '\n'
    } | "${root_cmd[@]}" tee "$run_root/root/f2-sandbox-entrypoint.sh" >/dev/null
    "${root_cmd[@]}" chmod 0700 "$run_root/root/f2-sandbox-entrypoint.sh"

    # Boot a real systemd PID 1 and register only this ephemeral machine so the
    # host can execute the bounded command through the container's manager.
    "${root_cmd[@]}" systemd-nspawn \
      --quiet \
      --boot \
      --register=yes \
      --machine="$name" \
      --directory="$run_root" \
      "${net_args[@]}" \
      --bind-ro="$workspace:/f2-src" &
    nspawn_pid=$!

    local ready=0
    local state=""
    for _ in $(seq 1 120); do
      if ! kill -0 "$nspawn_pid" >/dev/null 2>&1; then
        wait "$nspawn_pid" || true
        echo "booted nspawn exited before machine became ready" >&2
        exit 77
      fi
      state="$("${root_cmd[@]}" machinectl show "$name" --property=State --value 2>/dev/null || true)"
      if [[ "$state" == "running" ]]; then
        ready=1
        machine_registered=1
        break
      fi
      sleep 0.25
    done
    [[ "$ready" == "1" ]] || { echo "booted nspawn did not reach running state" >&2; exit 78; }

    local command_rc=0
    set +e
    "${root_cmd[@]}" systemd-run \
      --quiet \
      --machine="$name" \
      --wait \
      --pipe \
      --collect \
      /bin/bash /root/f2-sandbox-entrypoint.sh
    command_rc=$?
    set -e

    # Request a clean shutdown first. cleanup_nspawn remains the fail-safe if it
    # does not complete promptly.
    "${root_cmd[@]}" machinectl poweroff "$name" >/dev/null 2>&1 || true
    for _ in $(seq 1 40); do
      kill -0 "$nspawn_pid" >/dev/null 2>&1 || break
      sleep 0.25
    done
    if kill -0 "$nspawn_pid" >/dev/null 2>&1; then
      "${root_cmd[@]}" machinectl terminate "$name" >/dev/null 2>&1 || true
    fi
    machine_registered=0
    wait "$nspawn_pid" >/dev/null 2>&1 || true
    nspawn_pid=""

    if [[ "$command_rc" -ne 0 ]]; then
      echo "booted nspawn command failed: rc=$command_rc" >&2
      return "$command_rc"
    fi
  fi

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
  "systemd_boot=$([[ "$boot_systemd" == "1" ]] && echo LIVE_PID1_MODE || echo DIRECT_COMMAND_MODE)" \
  "source_mount=READ_ONLY" \
  "sandbox_local_mutation=ALLOWED" \
  "host_survival_sentinel=PASS" \
  "physical_local_credit=0" \
  "whole_system_acceptance=false"
