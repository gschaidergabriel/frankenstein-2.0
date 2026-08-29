# Frankenstein 2.0 installer entry

YOU ARE THE LOCAL CODING AGENT RECEIVING A FRANKENSTEIN 2.0 PACKAGE.

Do not scan the full repository first.

Frankenstein 2.0 is still under assembly. This installer entry defines the final product contract now so the build cannot drift into a VPS-only or development-checkout-only system. Until the required delivery workpackages are accepted, report the exact missing pieces instead of claiming a production install.

## Your job

1. Resolve package root as the parent directory containing this `AI_START_HERE_DO_NOT_SCAN_REPO` directory.
2. Read `../PRODUCT_COMPLETION_LAW.md` and `../architecture/PORTABLE_HOST_HARNESS_AND_DISTRIBUTION_CONTRACT.md`.
3. Read `01_ROUTES.json`.
4. Detect the real host you are running in.
5. Follow only that host route plus `03_VERIFY_INSTALL.md`.
6. Reuse one canonical durable Frankenstein state lineage. Never create an independent state store merely because the host changed.
7. Treat VPS/HCU/remote compute as optional extension. Do not require it for baseline local installation unless a future release manifest explicitly marks a feature remote-only.
8. Verify real lifecycle/state/effect integration by readback. File copy or setup command success is not installation proof.

## Expected host result

Report one of:

- `NATIVE`
- `ADAPTED`
- `DEGRADED`
- `BLOCKED`

Never invent unsupported hooks, permissions, state persistence, remote bridges, or runtime acceptance.

## One-handoff target

The intended human interaction is eventually only:

> Install Frankenstein 2.0 from this package for your environment. Start at `AI_START_HERE_DO_NOT_SCAN_REPO/00_READ_THIS_FIRST.md`, use the real host capabilities, preserve existing durable state, verify the install, and tell me exactly what is native/adapted/degraded/blocked.

If the release is not yet complete enough to satisfy that instruction, identify the exact unfinished `F2-WP-110x` gate.
