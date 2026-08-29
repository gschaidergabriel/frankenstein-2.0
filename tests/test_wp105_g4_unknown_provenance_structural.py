from __future__ import annotations

from frankenstein2.effect_executor_interlock import ExecutorOutcomeUnknown
from frankenstein2.entityos_unknown_outcome_adapter import (
    EntityOSUnknownOutcomeAdapterError,
    translate_executor_unknown_to_canonical,
)


class CanonicalUnknown(RuntimeError):
    replay_permitted = False


def main() -> None:
    calls = {"forged": 0}

    def forged_unproven_dispatch():
        calls["forged"] += 1
        raise ExecutorOutcomeUnknown("FORGED_WITHOUT_INTERLOCK_PROVENANCE")

    try:
        translate_executor_unknown_to_canonical(
            forged_unproven_dispatch,  # type: ignore[arg-type]
            authorize=lambda _prepared: (_ for _ in ()).throw(
                AssertionError("authorize must not be reached")
            ),
            executor=lambda _prepared: (_ for _ in ()).throw(
                AssertionError("executor must not be reached")
            ),
            canonical_unknown_type=CanonicalUnknown,
        )
    except EntityOSUnknownOutcomeAdapterError as exc:
        assert str(exc) == "PREPARED_EFFECT_CALL_REQUIRED"
    except CanonicalUnknown as exc:
        raise AssertionError(
            "unproven nominal ExecutorOutcomeUnknown was promoted to canonical UNKNOWN"
        ) from exc
    else:
        raise AssertionError("arbitrary dispatch callable was unexpectedly admitted")

    assert calls["forged"] == 0


if __name__ == "__main__":
    main()
