# Claude Code route

You are the reference local host for Frankenstein 2.0.

1. Resolve ROOT from `../00_READ_THIS_FIRST.md` and read `../01_ROUTES.json`.
2. Inspect the installed Claude Code version and its real plugin/hook/config surface. Do not assume the Frankenstein 1.x packaging API is unchanged.
3. Prefer a native Claude Code package/plugin route when current capabilities support the required semantic lifecycle roles.
4. Map concrete Claude events to the F2 semantic host ABI. Host names are glue; F2 core state semantics are canonical.
5. Install code/runtime locally. If F2 uses supervised background components, install/manage them locally with explicit status/restart/disable behavior.
6. Put canonical durable F2 state outside disposable Claude plugin/cache directories. Reuse an existing state lineage if present.
7. Optional VPS/HCU bridge comes after baseline local boot and must attach to the same identity/state lineage.
8. Run `../03_VERIFY_INSTALL.md` proofs and read state/effect results back.
9. Report `NATIVE`, `ADAPTED`, `DEGRADED`, or `BLOCKED` plus exact paths and limitations.

Do not make Claude Code itself the canonical cognitive controller. Claude Code is a host/executor integration around the same Frankenstein 2.0 runtime and state authority.
