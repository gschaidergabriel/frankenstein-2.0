import hashlib
import unittest

from src.frankenstein2.perception_capture_broker import (
    CaptureBrokerError,
    CaptureBrokerPolicy,
    RetinaCaptureBroker,
)
from src.frankenstein2.perception_fabric import PerceptionSource, SourceKind


P = ("test:wp709-capture-broker",)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def policy(*, frames=3, age=100, window=3):
    return CaptureBrokerPolicy(
        policy_id="capture-policy:test",
        generation=1,
        max_frames_per_source=frames,
        max_frame_age_ns=age,
        max_read_window_frames=window,
        provenance_refs=P,
    )


def source(source_id="camera:front", owner="capture-owner:camera:front", kind=SourceKind.CAMERA):
    return PerceptionSource(
        source_id=source_id,
        kind=kind,
        clock_domain="local-monotonic",
        capture_owner_id=owner,
        provenance_refs=P,
    )


def broker(**kwargs):
    return RetinaCaptureBroker(policy=policy(**kwargs))


def register_and_lease(b, *, src=None, generation=1, opened=10):
    src = src or source()
    b.register_source(source=src, generation=generation)
    lease = b.acquire_owner(
        source_id=src.source_id,
        source_generation=generation,
        capture_owner_id=src.capture_owner_id,
        opened_monotonic_ns=opened,
        provenance_refs=P,
    )
    return src, lease


class PerceptionCaptureBrokerTests(unittest.TestCase):
    def test_zero_sources_is_valid(self):
        b = broker()
        self.assertEqual(b.source_ids, ())

    def test_register_source_and_duplicate_fails_closed(self):
        b = broker()
        s = source()
        b.register_source(source=s, generation=1)
        self.assertEqual(b.source_ids, (s.source_id,))
        with self.assertRaisesRegex(CaptureBrokerError, "already registered"):
            b.register_source(source=s, generation=1)

    def test_single_owner_is_idempotent_and_competing_owner_fails(self):
        b = broker()
        s = source()
        b.register_source(source=s, generation=1)
        first = b.acquire_owner(
            source_id=s.source_id,
            source_generation=1,
            capture_owner_id=s.capture_owner_id,
            opened_monotonic_ns=10,
            provenance_refs=P,
        )
        second = b.acquire_owner(
            source_id=s.source_id,
            source_generation=1,
            capture_owner_id=s.capture_owner_id,
            opened_monotonic_ns=999,
            provenance_refs=P,
        )
        self.assertEqual(first.lease_id, second.lease_id)
        self.assertFalse(first.as_dict()["opens_physical_device"])

        with self.assertRaisesRegex(CaptureBrokerError, "canonical PerceptionSource"):
            b.acquire_owner(
                source_id=s.source_id,
                source_generation=1,
                capture_owner_id="another-owner",
                opened_monotonic_ns=20,
                provenance_refs=P,
            )

    def test_publish_requires_active_exact_owner_and_strict_time(self):
        b = broker()
        s, lease = register_and_lease(b)
        first = b.publish_frame(
            source_id=s.source_id,
            source_generation=1,
            capture_owner_id=s.capture_owner_id,
            lease_id=lease.lease_id,
            capture_monotonic_ns=20,
            frame_sha256=digest("frame-1"),
            payload_size_bytes=1234,
            provenance_refs=P,
        )
        self.assertEqual(first.source_sequence, 1)

        with self.assertRaisesRegex(CaptureBrokerError, "strictly increase"):
            b.publish_frame(
                source_id=s.source_id,
                source_generation=1,
                capture_owner_id=s.capture_owner_id,
                lease_id=lease.lease_id,
                capture_monotonic_ns=20,
                frame_sha256=digest("frame-2"),
                payload_size_bytes=1234,
                provenance_refs=P,
            )

        b.release_owner(
            source_id=s.source_id,
            source_generation=1,
            capture_owner_id=s.capture_owner_id,
            lease_id=lease.lease_id,
        )
        with self.assertRaisesRegex(CaptureBrokerError, "active capture owner"):
            b.publish_frame(
                source_id=s.source_id,
                source_generation=1,
                capture_owner_id=s.capture_owner_id,
                lease_id=lease.lease_id,
                capture_monotonic_ns=21,
                frame_sha256=digest("frame-3"),
                payload_size_bytes=1234,
                provenance_refs=P,
            )

    def test_capacity_eviction_is_bounded_and_consumer_gap_is_explicit(self):
        b = broker(frames=3, age=1000, window=3)
        s, lease = register_and_lease(b)
        for n in range(1, 6):
            b.publish_frame(
                source_id=s.source_id,
                source_generation=1,
                capture_owner_id=s.capture_owner_id,
                lease_id=lease.lease_id,
                capture_monotonic_ns=10 + n,
                frame_sha256=digest(f"frame-{n}"),
                payload_size_bytes=n,
                provenance_refs=P,
            )
        snap = b.snapshot(source_id=s.source_id, source_generation=1)
        self.assertEqual(len(snap.retained_frame_ref_ids), 3)
        self.assertEqual(snap.oldest_sequence, 3)
        self.assertEqual(snap.newest_sequence, 5)
        self.assertEqual(snap.evicted_frame_count, 2)

        read = b.read_since(
            source_id=s.source_id,
            source_generation=1,
            consumer_id="cortex:slow",
            after_sequence=0,
            now_monotonic_ns=20,
        )
        self.assertEqual(read.missed_before_sequence, 3)
        self.assertEqual([x.source_sequence for x in read.frame_refs], [3, 4, 5])

    def test_age_eviction_drops_stale_refs(self):
        b = broker(frames=10, age=5, window=10)
        s, lease = register_and_lease(b)
        for t in (10, 12, 14):
            b.publish_frame(
                source_id=s.source_id,
                source_generation=1,
                capture_owner_id=s.capture_owner_id,
                lease_id=lease.lease_id,
                capture_monotonic_ns=t,
                frame_sha256=digest(str(t)),
                payload_size_bytes=1,
                provenance_refs=P,
            )
        read = b.read_since(
            source_id=s.source_id,
            source_generation=1,
            consumer_id="cortex:reader",
            after_sequence=0,
            now_monotonic_ns=18,
        )
        self.assertEqual([x.source_sequence for x in read.frame_refs], [3])
        self.assertEqual(read.missed_before_sequence, 3)

    def test_many_consumers_read_same_refs_without_opening_device(self):
        b = broker()
        s, lease = register_and_lease(b)
        frame = b.publish_frame(
            source_id=s.source_id,
            source_generation=1,
            capture_owner_id=s.capture_owner_id,
            lease_id=lease.lease_id,
            capture_monotonic_ns=20,
            frame_sha256=digest("shared"),
            payload_size_bytes=7,
            provenance_refs=P,
        )
        windows = [
            b.read_since(
                source_id=s.source_id,
                source_generation=1,
                consumer_id=f"consumer:{n}",
                after_sequence=0,
                now_monotonic_ns=20,
            )
            for n in range(8)
        ]
        self.assertTrue(all(w.frame_refs == (frame,) for w in windows))
        self.assertTrue(all(w.as_dict()["opens_capture_device"] is False for w in windows))

    def test_frame_refs_never_contain_raw_payload_or_world_authority(self):
        b = broker()
        s, lease = register_and_lease(b)
        frame = b.publish_frame(
            source_id=s.source_id,
            source_generation=1,
            capture_owner_id=s.capture_owner_id,
            lease_id=lease.lease_id,
            capture_monotonic_ns=20,
            frame_sha256=digest("no-payload"),
            payload_size_bytes=999999,
            provenance_refs=P,
        )
        payload = frame.as_dict()
        self.assertIsNone(payload["raw_payload"])
        self.assertEqual(payload["persistence"], "RAM_REFERENCE_ONLY")
        self.assertEqual(payload["world_truth_authority"], "NONE")
        snap = b.snapshot(source_id=s.source_id, source_generation=1)
        self.assertEqual(snap.as_dict()["raw_frame_count"], 0)

    def test_rebind_requires_release_and_invalidates_old_generation(self):
        b = broker()
        s, lease = register_and_lease(b)
        b.publish_frame(
            source_id=s.source_id,
            source_generation=1,
            capture_owner_id=s.capture_owner_id,
            lease_id=lease.lease_id,
            capture_monotonic_ns=20,
            frame_sha256=digest("old"),
            payload_size_bytes=1,
            provenance_refs=P,
        )
        new_source = source(owner="capture-owner:camera:front:g2")
        with self.assertRaisesRegex(CaptureBrokerError, "released before rebind"):
            b.rebind_source(
                source_id=s.source_id,
                current_generation=1,
                new_source=new_source,
                new_generation=2,
            )
        b.release_owner(
            source_id=s.source_id,
            source_generation=1,
            capture_owner_id=s.capture_owner_id,
            lease_id=lease.lease_id,
        )
        b.rebind_source(
            source_id=s.source_id,
            current_generation=1,
            new_source=new_source,
            new_generation=2,
        )
        with self.assertRaisesRegex(CaptureBrokerError, "generation is stale"):
            b.snapshot(source_id=s.source_id, source_generation=1)
        snap = b.snapshot(source_id=s.source_id, source_generation=2)
        self.assertEqual(snap.retained_frame_ref_ids, ())
        self.assertEqual(snap.evicted_frame_count, 1)
        new_lease = b.acquire_owner(
            source_id=s.source_id,
            source_generation=2,
            capture_owner_id=new_source.capture_owner_id,
            opened_monotonic_ns=30,
            provenance_refs=P,
        )
        self.assertEqual(new_lease.capture_owner_id, new_source.capture_owner_id)

    def test_source_count_is_unbounded_by_four_worker_ceiling(self):
        b = broker()
        for n in range(9):
            b.register_source(
                source=source(
                    source_id=f"display:{n}",
                    owner=f"capture-owner:display:{n}",
                    kind=SourceKind.DISPLAY,
                ),
                generation=1,
            )
        self.assertEqual(len(b.source_ids), 9)


if __name__ == "__main__":
    unittest.main()
