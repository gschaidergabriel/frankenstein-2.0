import hashlib
import unittest

from src.frankenstein2.perception_capture_broker import CaptureBrokerPolicy, RetinaCaptureBroker
from src.frankenstein2.perception_fabric import PerceptionSource, SourceKind


P = ("test:wp709-capture-broker-soak",)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def make_broker(*, frames: int = 4) -> RetinaCaptureBroker:
    return RetinaCaptureBroker(
        policy=CaptureBrokerPolicy(
            policy_id="capture-policy:soak",
            generation=1,
            max_frames_per_source=frames,
            max_frame_age_ns=10_000_000,
            max_read_window_frames=frames,
            provenance_refs=P,
        )
    )


def make_source(source_id: str) -> PerceptionSource:
    return PerceptionSource(
        source_id=source_id,
        kind=SourceKind.CAMERA,
        clock_domain="local-monotonic",
        capture_owner_id=f"capture-owner:{source_id}",
        provenance_refs=P,
    )


def register_and_lease(broker: RetinaCaptureBroker, source_id: str):
    src = make_source(source_id)
    broker.register_source(source=src, generation=1)
    lease = broker.acquire_owner(
        source_id=source_id,
        source_generation=1,
        capture_owner_id=src.capture_owner_id,
        opened_monotonic_ns=1,
        provenance_refs=P,
    )
    return src, lease


class PerceptionCaptureBrokerSoakTests(unittest.TestCase):
    def test_1024_frame_single_source_retention_remains_bounded(self):
        capacity = 4
        total_frames = 1_024
        source_id = "camera:soak:single"
        b = make_broker(frames=capacity)
        src, lease = register_and_lease(b, source_id)

        for seq in range(1, total_frames + 1):
            b.publish_frame(
                source_id=source_id,
                source_generation=1,
                capture_owner_id=src.capture_owner_id,
                lease_id=lease.lease_id,
                capture_monotonic_ns=seq + 1,
                frame_sha256=digest(f"{source_id}:{seq}"),
                payload_size_bytes=seq,
                provenance_refs=P,
            )
            snap = b.snapshot(source_id=source_id, source_generation=1)
            self.assertLessEqual(len(snap.retained_frame_ref_ids), capacity)
            self.assertEqual(snap.as_dict()["raw_frame_count"], 0)

        snap = b.snapshot(source_id=source_id, source_generation=1)
        self.assertEqual(len(snap.retained_frame_ref_ids), capacity)
        self.assertEqual(snap.oldest_sequence, total_frames - capacity + 1)
        self.assertEqual(snap.newest_sequence, total_frames)
        self.assertEqual(snap.evicted_frame_count, total_frames - capacity)

    def test_four_source_1024_frame_soak_has_constant_per_source_retention_bound(self):
        capacity = 4
        frames_per_source = 1_024
        source_ids = tuple(f"camera:soak:{index}" for index in range(4))
        b = make_broker(frames=capacity)
        leases = {}
        sources = {}
        for source_id in source_ids:
            src, lease = register_and_lease(b, source_id)
            sources[source_id] = src
            leases[source_id] = lease

        for seq in range(1, frames_per_source + 1):
            for source_id in source_ids:
                b.publish_frame(
                    source_id=source_id,
                    source_generation=1,
                    capture_owner_id=sources[source_id].capture_owner_id,
                    lease_id=leases[source_id].lease_id,
                    capture_monotonic_ns=seq + 1,
                    frame_sha256=digest(f"{source_id}:{seq}"),
                    payload_size_bytes=seq,
                    provenance_refs=P,
                )

        self.assertEqual(b.source_ids, source_ids)
        for source_id in source_ids:
            snap = b.snapshot(source_id=source_id, source_generation=1)
            self.assertEqual(len(snap.retained_frame_ref_ids), capacity)
            self.assertEqual(snap.oldest_sequence, frames_per_source - capacity + 1)
            self.assertEqual(snap.newest_sequence, frames_per_source)
            self.assertEqual(snap.evicted_frame_count, frames_per_source - capacity)
            self.assertEqual(snap.as_dict()["raw_frame_count"], 0)


if __name__ == "__main__":
    unittest.main()
