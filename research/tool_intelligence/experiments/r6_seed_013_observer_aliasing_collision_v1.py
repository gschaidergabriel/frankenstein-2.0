"""Trigger-6 E3 source-level falsifier for R6-SEED-013.

This fixture does NOT execute a real GWT observer. It reproduces the canonical
CellUptakeReceipt.as_dict()/sha256 field boundary from exact WP507 source blob
f25c03d4e4e49c4fed44acd0c5c96edfb40f664e and tests whether observer
identity/configuration can affect the receipt digest. It cannot in the current
schema because no observer binding is serialized.
"""
from __future__ import annotations

import hashlib
import json

SOURCE_BLOB_SHA = "f25c03d4e4e49c4fed44acd0c5c96edfb40f664e"


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def current_receipt_payload() -> dict[str, object]:
    # Exact serialized field set of CellUptakeReceipt.as_dict() at SOURCE_BLOB_SHA.
    return {
        "schema": "FRANKENSTEIN2_GWT_CELL_UPTAKE_RECEIPT/v2",
        "classification": "OBSERVED_UPTAKE_EVIDENCE_NOT_HIDDEN_STATE_OR_TRUTH_AUTHORITY",
        "receipt_id": "r-G1",
        "broadcast_id": "b1",
        "broadcast_sha256": "a" * 64,
        "cycle_id": "cycle-1",
        "broadcast_generation": 3,
        "selection_id": "sel-1",
        "selection_generation": 2,
        "selection_sha256": "b" * 64,
        "plan_id": "plan-1",
        "plan_generation": 4,
        "plan_sha256": "c" * 64,
        "cell_id": "G1",
        "delivery_status": "DELIVERED",
        "uptake_status": "UPTAKEN",
        "downstream_ref": "d:G1",
        "downstream_sha256": "d" * 64,
        "provenance_refs": ["sensor:generic"],
    }


def main() -> None:
    observer_sync = {
        "observer_type": "direct-inprocess-hook/v1",
        "observer_instance_id": "hook-17",
        "observer_artifact_sha256": "1" * 64,
        "observer_config_sha256": "2" * 64,
        "evidence_class": "synchronous_direct",
    }
    observer_async = {
        "observer_type": "async-log-scraper/v1",
        "observer_instance_id": "scraper-9",
        "observer_artifact_sha256": "3" * 64,
        "observer_config_sha256": "4" * 64,
        "evidence_class": "asynchronous_derived",
    }

    base = current_receipt_payload()
    current_sync = digest(base)
    current_async = digest(base)

    with_sync = dict(base, observer_binding_sha256=digest(observer_sync))
    with_async = dict(base, observer_binding_sha256=digest(observer_async))

    result = {
        "source_blob_sha": SOURCE_BLOB_SHA,
        "current_receipt_digest_sync_observer": current_sync,
        "current_receipt_digest_async_observer": current_async,
        "current_collision": current_sync == current_async,
        "observer_sync_digest": digest(observer_sync),
        "observer_async_digest": digest(observer_async),
        "bound_receipt_digest_sync": digest(with_sync),
        "bound_receipt_digest_async": digest(with_async),
        "bound_collision": digest(with_sync) == digest(with_async),
        "only_difference_external_to_current_schema": observer_sync != observer_async,
    }

    assert result["current_collision"] is True
    assert result["bound_collision"] is False
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
