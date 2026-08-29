# Trigger 7 VPS / Sandbox Execution Binding

Date: 2026-08-29
Status: OWNER-CORRECTION / ACTIVE

Trigger 7 must resolve the current Clay execution authority before classifying runtime access.

Authoritative upstream surfaces:
- `gschaidergabriel/clay-global-research-entity:CLAY_EXECUTION_AUTHORITY.md`
- `gschaidergabriel/clay-global-research-entity:governance/CLAY_VPS_SANDBOX_BRIDGE_CURRENT.md`

Current operational interpretation:

- `clay-direct-dev` is an authorized and expected owner-provisioned sandbox for Frankenstein/Clay development, local-model downloads, package installation, compilation, llama.cpp-class runtimes, ASR/TTS/LLM experiments, benchmarks and scratch/destructive-to-scratch work.
- FREE_ONLY restricts external provider/token spend. It does not prohibit owner VPS compute, self-hosted runners or local-model execution.
- Absence of a direct ChatGPT SSH tool/button is NOT `NO_EXECUTOR`, `NO_VPS`, or `VPS_FORBIDDEN`.
- Trigger 7 must first use or repair the established bridge paths: Clay Git/SSH bridge and/or the `gschaidergabriel/Dr.-Unterweger` self-hosted runner into `clay-direct-dev`.
- A transient ChatGPT container is a separate execution surface from the owner VPS sandbox. Missing local SSH keys/config/DNS in that transient container does not imply the project VPS is unavailable.
- If a bridge/runner is degraded, classify and repair the concrete transport/control-plane failure; do not convert it into a model/runtime authority failure.
- Public model/source downloads into the authorized sandbox are allowed. Exact revisions/hashes and quarantine rules remain mandatory for evidence-bearing runs.
- Runtime credit still requires exact source/model/runtime identity plus receipts. Queue state, source presence, or a planned workflow is not execution evidence.

Trigger-7 routing correction:

```text
NO_DIRECT_CHAT_SSH != NO_EXECUTOR
TRANSIENT_CHAT_SANDBOX != CLAY_DIRECT_DEV
FREE_ONLY != NO_VPS
FREE_ONLY != NO_LOCAL_MODEL
BRIDGE_DEGRADED -> REPAIR/ROUTE, NOT RESEARCH_STOP
PUBLIC_MODEL_DOWNLOAD_TO_AUTHORIZED_SANDBOX == ALLOWED
```

The next Trigger-7 runtime attempt must therefore begin with bridge/runner re-entry and an actual `clay-direct-dev` hardware/download receipt rather than stopping at "no direct shell connector".
