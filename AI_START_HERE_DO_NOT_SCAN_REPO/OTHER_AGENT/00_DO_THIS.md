# Other local coding-agent route

Use capability discovery, not product-name guessing.

1. Resolve ROOT and read `../01_ROUTES.json` plus the portable distribution contract.
2. Detect whether the host provides durable local files/state, lifecycle events, pre/post tool/effect events, restart persistence, background process/service support, and external tool/bridge APIs.
3. Map only verified host primitives onto the F2 semantic host ABI.
4. Choose the strongest truthful mode:
   - native-like semantics available -> `ADAPTED` or `NATIVE` only if a release specifically verifies native support;
   - durable state but incomplete lifecycle -> `DEGRADED` with exact missing roles;
   - no durable writable state or required runtime capability -> `BLOCKED`.
5. Reuse the same canonical local F2 state lineage. Never create a separate truth store just because this host is different.
6. Install/manage any F2 persistent local runtime independently from the host's conversation context.
7. Treat VPS/HCU as optional extension after local boot.
8. Execute `../03_VERIFY_INSTALL.md` and report exact evidence and limitations.

Do not claim compatibility from file presence alone.
