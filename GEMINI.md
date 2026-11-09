# Project Rules & Instructions

## 🧠 Memory-First Protocol
- **Start with the Index:** For every task, consult `memory/index.md` first.
- **Surgical Reading:** Read ONLY the specific memory note relevant to the current task (e.g. `memory/tournaments_cog.md` or `memory/workflow_clan_role_directory.md`).
- **Use memory as a guide:** Read the relevant `memory/` note to find your way around, then inspect the current source code and enough surrounding context for the task. If a note conflicts with the code, trust the code. Update a note only when a change adds lasting project knowledge.
- **Memory Maintenance:** When modifying or adding code components, update the corresponding `memory/*.md` note in the same turn.
- **Selective Test Execution:** When application code changes, run the relevant tests quietly with `-q` (`pytest <test_file> -q`). Do not run tests for documentation- or note-only edits.
