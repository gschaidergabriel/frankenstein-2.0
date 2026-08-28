from __future__ import annotations

import sqlite3
import tempfile
import unittest
from types import SimpleNamespace

from frankenstein2.effect_invocation_bijection import (
    EffectInvocationBijectionError,
    bind_effect_invocation,
    bind_prepared_effect_call,
    initialize_effect_invocation_bijection,
    verify_effect_invocation,
)


class EffectInvocationBijectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        initialize_effect_invocation_bijection(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_overlapping_calls_keep_distinct_bidirectional_mapping(self) -> None:
        a = bind_effect_invocation(
            self.conn, call_id="call-A", effect_id="effect-A", binding_id="binding-A", generation=7
        )
        b = bind_effect_invocation(
            self.conn, call_id="call-B", effect_id="effect-B", binding_id="binding-B", generation=7
        )
        self.assertNotEqual(a.call_id, b.call_id)
        self.assertNotEqual(a.effect_id, b.effect_id)
        self.assertEqual(
            verify_effect_invocation(
                self.conn, call_id="call-A", effect_id="effect-A", binding_id="binding-A", generation=7
            ),
            a,
        )
        self.assertEqual(
            verify_effect_invocation(
                self.conn, call_id="call-B", effect_id="effect-B", binding_id="binding-B", generation=7
            ),
            b,
        )

    def test_same_call_cannot_rebind_to_new_effect(self) -> None:
        bind_effect_invocation(
            self.conn, call_id="call-A", effect_id="effect-A", binding_id="binding-A", generation=7
        )
        with self.assertRaisesRegex(
            EffectInvocationBijectionError, "CALL_ID_REBOUND_TO_DIFFERENT_EFFECT"
        ):
            bind_effect_invocation(
                self.conn, call_id="call-A", effect_id="effect-B", binding_id="binding-B", generation=7
            )

    def test_same_effect_cannot_rebind_to_new_call(self) -> None:
        bind_effect_invocation(
            self.conn, call_id="call-A", effect_id="effect-A", binding_id="binding-A", generation=7
        )
        with self.assertRaisesRegex(
            EffectInvocationBijectionError, "EFFECT_ID_REBOUND_TO_DIFFERENT_CALL"
        ):
            bind_effect_invocation(
                self.conn, call_id="call-B", effect_id="effect-A", binding_id="binding-B", generation=7
            )

    def test_same_pair_exact_replay_is_idempotent(self) -> None:
        first = bind_effect_invocation(
            self.conn, call_id="call-A", effect_id="effect-A", binding_id="binding-A", generation=7
        )
        replay = bind_effect_invocation(
            self.conn, call_id="call-A", effect_id="effect-A", binding_id="binding-A", generation=7
        )
        self.assertEqual(first, replay)
        count = self.conn.execute("SELECT COUNT(*) FROM effect_invocation_bijection").fetchone()[0]
        self.assertEqual(count, 1)

    def test_same_pair_with_mutated_metadata_fails_closed(self) -> None:
        bind_effect_invocation(
            self.conn, call_id="call-A", effect_id="effect-A", binding_id="binding-A", generation=7
        )
        with self.assertRaisesRegex(
            EffectInvocationBijectionError, "EXISTING_BINDING_METADATA_MISMATCH"
        ):
            bind_effect_invocation(
                self.conn, call_id="call-A", effect_id="effect-A", binding_id="binding-A", generation=8
            )

    def test_binding_id_cannot_alias_another_pair(self) -> None:
        bind_effect_invocation(
            self.conn,
            call_id="call-A",
            effect_id="effect-A",
            binding_id="binding-shared",
            generation=7,
        )
        with self.assertRaisesRegex(
            EffectInvocationBijectionError, "BINDING_ID_REBOUND_TO_DIFFERENT_PAIR"
        ):
            bind_effect_invocation(
                self.conn,
                call_id="call-B",
                effect_id="effect-B",
                binding_id="binding-shared",
                generation=7,
            )

    def test_unique_constraints_arbitrate_across_connections(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".sqlite") as tmp:
            a = sqlite3.connect(tmp.name, timeout=1.0)
            b = sqlite3.connect(tmp.name, timeout=1.0)
            try:
                initialize_effect_invocation_bijection(a)
                a.commit()
                bind_effect_invocation(
                    a,
                    call_id="call-A",
                    effect_id="effect-shared",
                    binding_id="binding-A",
                    generation=7,
                )
                a.commit()
                with self.assertRaisesRegex(
                    EffectInvocationBijectionError,
                    "EFFECT_ID_REBOUND_TO_DIFFERENT_CALL",
                ):
                    bind_effect_invocation(
                        b,
                        call_id="call-B",
                        effect_id="effect-shared",
                        binding_id="binding-B",
                        generation=7,
                    )
            finally:
                a.close()
                b.close()

    def test_prepared_effect_call_adapter_binds_pre_dispatch_identity(self) -> None:
        prepared = SimpleNamespace(
            stage=SimpleNamespace(value="PREPARED"),
            invocation_id="call-A",
            effect_id="effect-A",
            binding_id="binding-A",
            result_id=None,
            result_sha256=None,
        )
        bound = bind_prepared_effect_call(self.conn, prepared, generation=7)
        self.assertEqual(bound.call_id, "call-A")
        self.assertEqual(bound.effect_id, "effect-A")
        self.assertEqual(bound.binding_id, "binding-A")
        self.assertEqual(bound.generation, 7)

    def test_non_prepared_adapter_fails_closed(self) -> None:
        prepared = SimpleNamespace(
            stage=SimpleNamespace(value="RESULT_OBSERVED"),
            invocation_id="call-A",
            effect_id="effect-A",
            binding_id="binding-A",
            result_id="result-A",
            result_sha256="a" * 64,
        )
        with self.assertRaisesRegex(
            EffectInvocationBijectionError, "CALL_BINDING_NOT_PREPARED"
        ):
            bind_prepared_effect_call(self.conn, prepared, generation=7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
