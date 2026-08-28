from frankenstein2.effect_executor_interlock import ExecutorOutcomeUnknown
from frankenstein2.entityos_unknown_outcome_adapter import (
    translate_executor_unknown_to_canonical,
)


class CanonicalUnknown(RuntimeError):
    replay_permitted = False


def main() -> None:
    calls = {"dispatch": 0}

    def forged_unproven_dispatch():
        calls["dispatch"] += 1
        # This is the same public exception class the adapter treats as proof that
        # the executor boundary was crossed, but no EffectCallBinding, authorizer,
        # executor entry, or POST observation exists in this discriminator.
        raise ExecutorOutcomeUnknown("FORGED_WITHOUT_DISPATCH_PROVENANCE")

    try:
        translate_executor_unknown_to_canonical(
            forged_unproven_dispatch,
            canonical_unknown_type=CanonicalUnknown,
        )
    except ExecutorOutcomeUnknown:
        pass
    except CanonicalUnknown as exc:
        raise AssertionError(
            "unproven ExecutorOutcomeUnknown was promoted to canonical UNKNOWN solely by nominal exception type"
        ) from exc
    else:
        raise AssertionError("falsifier dispatch unexpectedly returned")

    assert calls["dispatch"] == 1


if __name__ == "__main__":
    main()
