#!/usr/bin/env python3
import argparse
import multiprocessing as mp
import os
import time


def parent_hotspot(iterations: int) -> int:
    acc = 0
    for i in range(iterations):
        acc = (acc + ((i * 2654435761) ^ (i >> 3))) & 0xFFFFFFFF
    return acc


def child_hotspot(iterations: int, queue) -> None:
    acc = 0
    for i in range(iterations):
        acc = (acc + ((i * 2246822519) ^ (i >> 5))) & 0xFFFFFFFF
    queue.put(acc)


def attach_target(seconds: float) -> None:
    deadline = time.monotonic() + seconds
    acc = 0
    i = 1
    while time.monotonic() < deadline:
        acc = (acc + ((i * 3266489917) ^ (i >> 7))) & 0xFFFFFFFF
        i += 1
    print(f"attach_checksum={acc} pid={os.getpid()}", flush=True)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--parent-iterations", type=int, default=30_000_000)
    p.add_argument("--child-iterations", type=int, default=24_000_000)
    p.add_argument("--attach-seconds", type=float, default=0.0)
    args = p.parse_args()

    if args.attach_seconds > 0:
        attach_target(args.attach_seconds)
        return 0

    q = mp.Queue()
    child = mp.Process(target=child_hotspot, args=(args.child_iterations, q), name="fixture-child")
    child.start()
    parent_value = parent_hotspot(args.parent_iterations)
    child.join()
    child_value = q.get(timeout=5)
    print(
        f"fixture_ok parent_checksum={parent_value} child_checksum={child_value} "
        f"parent_pid={os.getpid()} child_pid={child.pid}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
