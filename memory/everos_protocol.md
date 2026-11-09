# EVEROS System Instructions & Procedural Memory Protocol

> This protocol governs all interactions in the workspace to minimize context bloat and token consumption.

## Operating Rules:
1. **Never read entire multi-thousand line files:** Always consult `memory/architecture_map.md` first to locate exact function line numbers and class boundaries.
2. **Surgical Inspects Only:** Read only the required 10–30 lines around a target function rather than 200+ line blocks.
3. **Quiet Command Execution:** Run pytest and git commands in compact/quiet mode (`-q`) to prevent dumping hundreds of lines into the conversation context.
4. **Self-Updating Memory:** When new features, classes, or hooks are added or modified, update `memory/architecture_map.md` line pointers in the same turn.
