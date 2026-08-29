import unittest

from src.frankenstein2.retina_capture_broker import (
    CaptureBrokerError,
    CaptureFrameRef,
    create_capture_broker,
    latest_frame_refs,
    publish_frame_ref,
)


P = ("test:capture-broker",)


def frame(seq, time_ns=None):
    if time_ns is None:
        time_ns = 100 + seq
    return CaptureFrameRef(
        frame_ref_id=f"frame:{seq}",
        source_id="camera:front",
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
        self.assertEqual(tuple(item.frame_ref_id for item in state.frame_refs), ("frame:2", "frame:3"))
        self.assertEqual(state.dropped_frame_ref_ids, ("frame:1",))
        self.assertEqual(len(state.frame_refs), 2)
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
        self.assertEqual(tuple(item.frame_ref_id for item in reader_a), ("frame:2", "frame:3"))
        self.assertEqual(tuple(item.frame_ref_id for item in reader_b), ("frame:3",))
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
            frame_ref_id="wrong:1",
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


if __name__ == "__main__":
    unittest.main()
