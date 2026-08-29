# Trigger 7 authority delta — Claude Code as optional inference provider

Date: 2026-08-29
Status: OWNER-DIRECTED / ACTIVE
Scope: Frankenstein 2.0 local realtime voice and cognitive runtime

## Owner clarification

Claude Code MAY continue to be used as an inference provider / reasoning organ for Frankenstein 2.0.

This changes the previous interpretation that every accepted runtime mode must categorically prohibit all external model inference. The target architecture is now explicitly dual-mode:

### LOCAL-SOLO mode — mandatory installation/runtime floor

After installation on the target system, Frankenstein 2.0 must remain operational with its required runtime substrate resident locally on the target system. Core identity/state/memory/effect authority, GRID10/HCU/GWT/J-Space, local voice transport, turn-taking, wake/VAD, local ASR/TTS, and a usable local dialogue/reasoning path must not require Claude Code or another remote model provider.

LOCAL-SOLO is the portability, resilience, privacy and offline acceptance floor.

### CLAUDE-AUGMENTED mode — explicitly allowed

Claude Code may be attached as an optional inference/reasoning provider when available and authorized. It may improve reasoning depth, coding, planning, research, dialogue or tool-selection quality, subject to the same causal/state/effect boundaries as any other model organ.

Claude Code MUST NOT become:

- Frankenstein identity authority;
- canonical memory/state authority;
- GRID10/HCU/GWT/J-Space authority;
- direct effect authority;
- the only dialogue path;
- a required dependency for boot, basic conversation, memory access, local voice, or safe degradation.

Provider loss must degrade capability, not terminate the entity.

## Voice-specific interpretation

Trigger 7 continues to target local realtime ASR and TTS on the installed target system. The dialogue/reasoning layer must benchmark two classes:

1. fully local LLM/reasoning path;
2. optional Claude Code augmented inference path.

The local path remains mandatory for LOCAL-SOLO acceptance. Claude-augmented quality may be tracked separately and may be the preferred online operating mode if it materially improves quality without violating state/effect authority.

## Acceptance matrix

A candidate voice stack is not complete until both of these are characterized:

- LOCAL-SOLO: Claude disabled/unavailable; Frankenstein still boots and completes wake -> German conversation -> memory/tool use -> barge-in -> semantic close locally.
- CLAUDE-AUGMENTED: Claude enabled; measurable gain/loss in quality, latency, tool correctness, state consistency and failure behavior is recorded.

No hidden dependency is allowed: a successful CLAUDE-AUGMENTED run cannot substitute for LOCAL-SOLO acceptance.

## Updated invariants

```text
LOCAL_SOLO_REQUIRED == TRUE
CLAUDE_CODE_OPTIONAL_INFERENCE == ALLOWED
CLAUDE_CODE_REQUIRED_FOR_BOOT == FALSE
CLAUDE_CODE_REQUIRED_FOR_BASIC_CONVERSATION == FALSE
CLAUDE_CODE != FRANKENSTEIN_IDENTITY
CLAUDE_CODE != CANONICAL_MEMORY
CLAUDE_CODE != EFFECT_AUTHORITY
PROVIDER_LOSS -> DEGRADED_LOCAL_OPERATION, NOT ENTITY_FAILURE
LOCAL_ASR_REQUIRED == TRUE
LOCAL_TTS_REQUIRED == TRUE
```
