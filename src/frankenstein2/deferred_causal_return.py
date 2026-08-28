"""Compatibility surface for the canonical F2-WP-104 deferred-return implementation.

The create-only F2-WP-104 active claim predates the later standalone donor claim.
Canonical deferred-return logic therefore lives in ``frankenstein2.deferred_return``.
This module intentionally contains no independent validation or serialization logic; it
preserves the later public names for current downstream consumers while preventing two
competing implementations from becoming semantic authorities.

Compatibility does not create runtime, delivery, effect, completion, VPS, GRID10, or
whole-system credit.
"""
from __future__ import annotations

from .deferred_return import DeferredReturnEnvelope, DeferredReturnError

# Backward-compatible names used by the later donor lane and current WP105 adapter.
# These are aliases, not subclasses, so isinstance checks resolve to the canonical type.
DeferredCausalReturn = DeferredReturnEnvelope
DeferredCausalReturnError = DeferredReturnError

__all__ = ["DeferredCausalReturn", "DeferredCausalReturnError"]
