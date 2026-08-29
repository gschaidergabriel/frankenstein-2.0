# Codex CLI route

Port the Frankenstein 2.0 semantic host contract using the **current installed Codex capabilities**, not stale Claude-specific assumptions.

1. Resolve ROOT and read `../01_ROUTES.json` plus the distribution contract.
2. Inspect the installed Codex version and its actual hooks/plugin/config/tool-event surface.
3. Map available concrete events onto F2 semantic roles such as `SESSION_START`, `USER_TURN`, `PRE_EFFECT`, `POST_EFFECT`, `SESSION_STOP`, `PRE_COMPACT_OR_CHECKPOINT`, `TOOL_RESULT_RETURN` and any supported background wake mechanism.
4. Same-looking event names are not enough: verify timing, payload identity, matcher coverage and firing multiplicity.
5. Prefer native Codex packaging when verified. Otherwise build the smallest adapter necessary; do not copy Claude hook names blindly.
6. Install/reuse the same canonical durable local F2 state lineage outside disposable Codex/plugin caches.
7. F2 persistent runtime components are local product components, not Codex conversation context.
8. Optional VPS/HCU bridge attaches only after baseline local boot and cannot create a second state authority.
9. Execute the real probes in `../03_VERIFY_INSTALL.md` and report `NATIVE`, `ADAPTED`, `DEGRADED`, or `BLOCKED`.

If current Codex lacks a required semantic primitive, mark the exact primitive missing. Do not emulate a hook by merely promising to remember to call something later.
