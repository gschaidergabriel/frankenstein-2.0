import unittest

from src.frankenstein2.retina_capture_broker import (
    CaptureBrokerError,
    CaptureFrameRef,
    create_capture_broker,
    latest_frame_refs,
    publish_frame_ref,
)


P = ("test:capture-broker",)


def frame(seq, time_ns=None, source_id="camera:front"):
    if time_ns is None:
        time_ns = 100 + seq
    return CaptureFrameRef(
        frame_ref_id=f"{source_id}:frame:{seq}",
        source_id=source_id,
        source_sequence=seq,
        captured_monotonic_ns=time_ns,
        payload_sha256=(f"{seq:x}" * 64)[:64],
        provenance_refs=P,
    )


class RetinaCaptureBrokerTests(unittest.TestCase):
    def test_only_declared_capture_owner_can_publish(self):
        state = create_capture_broker(
            broker_id="broker:camera:front",
            source_id="camera:front",
            capture_owner_id="owner:camera:front",
            capacity=3,
            provenance_refs=P,
        )
        with self.assertRaisesRegex(CaptureBrokerError, "capture_owner_id"):
            publish_frame_ref(
                state=state,
                publisher_owner_id="second-owner",
                frame_ref=frame(1),
            )

    def test_bounded_ring_drops_oldest_reference(self):
        state = create_capture_broker(
            broker_id="broker:camera:front",
            source_id="camera:front",
            capture_owner_id="owner:camera:front",
            capacity=2,
            provenance_refs=P,
        )
        for seq in (1, 2, 3):
            state = publish_frame_ref(
                state=state,
                publisher_owner_id="owner:camera:front",
                frame_ref=frame(seq),
            )
        self.assertEqual(
            tuple(item.frame_ref_id for item in state.frame_refs),
            ("camera:front:frame:2", "camera:front:frame:3"),
        )
        self.assertEqual(state.dropped_frame_count, 1)
        self.assertEqual(state.dropped_frame_ref_ids, ("camera:front:frame:1",))
        self.assertEqual(len(state.frame_refs), 2)
        self.assertLessEqual(len(state.provenance_refs), len(state.origin_provenance_refs) + 2)
        self.assertFalse(state.as_dict()["raw_frame_persistence"])

    def test_source_sequence_regression_fails_closed(self):
        state = create_capture_broker(
            broker_id="broker:camera:front",
            source_id="camera:front",
            capture_owner_id="owner:camera:front",
            capacity=3,
            provenance_refs=P,
        )
        state = publish_frame_ref(
            state=state,
            publisher_owner_id="owner:camera:front",
            frame_ref=frame(2),
        )
        with self.assertRaisesRegex(CaptureBrokerError, "strictly increase"):
            publish_frame_ref(
                state=state,
                publisher_owner_id="owner:camera:front",
                frame_ref=frame(1, 200),
            )

    def test_capture_time_regression_fails_closed(self):
        state = create_capture_broker(
            broker_id="broker:camera:front",
            source_id="camera:front",
            capture_owner_id="owner:camera:front",
            capacity=3,
            provenance_refs=P,
        )
        state = publish_frame_ref(
            state=state,
            publisher_owner_id="owner:camera:front",
            frame_ref=frame(1, 200),
        )
        with self.assertRaisesRegex(CaptureBrokerError, "must not regress"):
            publish_frame_ref(
                state=state,
                publisher_owner_id="owner:camera:front",
                frame_ref=frame(2, 199),
            )

    def test_reader_fanout_reads_refs_without_device_ownership(self):
        state = create_capture_broker(
            broker_id="broker:camera:front",
            source_id="camera:front",
            capture_owner_id="owner:camera:front",
            capacity=4,
            provenance_refs=P,
        )
        for seq in (1, 2, 3):
            state = publish_frame_ref(
                state=state,
                publisher_owner_id="owner:camera:front",
                frame_ref=frame(seq),
            )
        reader_a = latest_frame_refs(state, limit=2)
        reader_b = latest_frame_refs(state, limit=1)
        self.assertEqual(
            tuple(item.frame_ref_id for item in reader_a),
            ("camera:front:frame:2", "camera:front:frame:3"),
        )
        self.assertEqual(tuple(item.frame_ref_id for item in reader_b), ("camera:front:frame:3",))
        self.assertEqual(state.capture_owner_id, "owner:camera:front")

    def test_wrong_source_cannot_enter_broker(self):
        state = create_capture_broker(
            broker_id="broker:camera:front",
            source_id="camera:front",
            capture_owner_id="owner:camera:front",
            capacity=2,
            provenance_refs=P,
        )
        wrong = CaptureFrameRef(
            frame_ref_id="display:1:frame:1",
            source_id="display:1",
            source_sequence=1,
            captured_monotonic_ns=100,
            payload_sha256="a" * 64,
            provenance_refs=P,
        )
        with self.assertRaisesRegex(CaptureBrokerError, "source_id"):
            publish_frame_ref(
                state=state,
                publisher_owner_id="owner:camera:front",
                frame_ref=wrong,
            )

    def test_long_run_state_metadata_remains_bounded(self):
        capacity = 4
        total_frames = 1_024
        source_id = "camera:front"
        state = create_capture_broker(
            broker_id=f"broker:{source_id}",
            source_id=source_id,
            capture_owner_id=f"owner:{source_id}",
            capacity=capacity,
            provenance_refs=P,
        )
        for seq in range(1, total_frames + 1):
            state = publish_frame_ref(
                state=state,
                publisher_owner_id=f"owner:{source_id}",
                frame_ref=frame(seq, source_id=source_id),
            )
            self.assertLessEqual(len(state.frame_refs), capacity)
            self.assertLessEqual(len(state.dropped_frame_ref_ids), capacity)
            self.assertLessEqual(
                len(state.provenance_refs),
                len(state.origin_provenance_refs) + 2,
            )
        self.assertEqual(state.generation, total_frames)
        self.assertEqual(state.dropped_frame_count, total_frames - capacity)
        self.assertEqual(
            tuple(item.source_sequence for item in state.frame_refs),
            tuple(range(total_frames - capacity + 1, total_frames + 1)),
        )
        self.assertEqual(
            state.dropped_frame_ref_ids,
            tuple(
                f"{source_id}:frame:{seq}"
                for seq in range(total_frames - (2 * capacity) + 1, total_frames - capacity + 1)
            ),
        )
        self.assertFalse(state.as_dict()["raw_frame_persistence"])

    def test_four_source_soak_has_constant_per_source_state_bounds(self):
        source_ids = (
            "camera:front",
            "display:1",
            "browser:rendered",
            "browser:structural",
        )
        capacity = 4
        frames_per_source = 1_024
        states = {
            source_id: create_capture_broker(
                broker_id=f"broker:{source_id}",
                source_id=source_id,
                capture_owner_id=f"owner:{source_id}",
                capacity=capacity,
                provenance_refs=P,
            )
            for source_id in source_ids
        }
        for seq in range(1, frames_per_source + 1):
            for source_id in source_ids:
                states[source_id] = publish_frame_ref(
                    state=states[source_id],
                    publisher_owner_id=f"owner:{source_id}",
                    frame_ref=frame(seq, source_id=source_id),
                )
                current = states[source_id]
                self.assertLessEqual(len(current.frame_refs), capacity)
                self.assertLessEqual(len(current.dropped_frame_ref_ids), capacity)
                self.assertLessEqual(
                    len(current.provenance_refs),
                    len(current.origin_provenance_refs) + 2,
                )
                self.assertFalse(current.as_dict()["raw_frame_persistence"])
        for source_id, state in states.items():
            self.assertEqual(state.generation, frames_per_source)
            self.assertEqual(state.dropped_frame_count, frames_per_source - capacity)
            self.assertEqual(len(state.frame_refs), capacity)
            self.assertEqual(len(state.dropped_frame_ref_ids), capacity)
            self.assertEqual(state.frame_refs[-1].frame_ref_id, f"{source_id}:frame:{frames_per_source}")


if __name__ == "__main__":
    unittest.main()
