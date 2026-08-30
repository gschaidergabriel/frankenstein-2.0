from __future__ import annotations

from pathlib import Path

import pytest

from frankenstein2.media_lab_store import GIB, MediaLabStore, _validate_public_url


def test_cap_cannot_be_configured_above_10_gib(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="may not exceed 10 GiB"):
        MediaLabStore(tmp_path / "store", max_bytes=10 * GIB + 1)


def test_generated_tone_is_content_addressed_and_deduplicated(tmp_path: Path) -> None:
    store = MediaLabStore(tmp_path / "store", max_bytes=2_000_000, low_water_bytes=500_000)
    first = store.generate_tone(seconds=0.25, frequency=997.0)
    again = store.ingest(first["path"], source_label="REINGEST_TEST")

    assert first["sha256"] == again["sha256"]
    status = store.status()
    assert status["object_count"] == 1
    assert status["usage_bytes"] <= status["max_bytes"]


def test_small_cap_evicts_old_unleased_media_instead_of_crossing_cap(tmp_path: Path) -> None:
    store = MediaLabStore(
        tmp_path / "store",
        max_bytes=130_000,
        low_water_bytes=45_000,
        max_age_hours=72,
    )

    for frequency in (440.0, 550.0, 660.0, 770.0):
        store.generate_tone(seconds=0.25, frequency=frequency)
        status = store.status()
        assert status["usage_bytes"] <= status["max_bytes"]

    final = store.gc(aggressive=True)
    assert final["usage_bytes"] <= final["max_bytes"]
    assert store.status()["usage_bytes"] <= 130_000


def test_private_and_loopback_download_targets_are_rejected() -> None:
    with pytest.raises(ValueError):
        _validate_public_url("http://127.0.0.1/test.mp4")
    with pytest.raises(ValueError):
        _validate_public_url("http://10.0.0.1/test.wav")
    with pytest.raises(ValueError):
        _validate_public_url("file:///tmp/test.mp4")
