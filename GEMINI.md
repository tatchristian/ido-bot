# Project Rules & Instructions

## 🧠 Memory-First Protocol
- **Start with the Index:** For every task, consult `memory/index.md` first.
- **Surgical Reading:** Read ONLY the specific memory note relevant to the current task (e.g. `memory/tournaments_cog.md` or `memory/workflow_clan_role_directory.md`).
- **Use memory as a guide:** Read the relevant `memory/` note to find your way around, then inspect the current source code and enough surrounding context for the task. If a note conflicts with the code, trust the code. Update a note only when a change adds lasting project knowledge.
- **Memory Maintenance:** When modifying or adding code components, update the corresponding `memory/*.md` note in the same turn.
- **Selective Test Execution:** When application code changes, run the relevant tests quietly with `-q` (`pytest <test_file> -q`). Do not run tests for documentation- or note-only edits.

## 🧠 Adaptive Reasoning & Token Optimization
Dynamically modulate thinking effort and internal reasoning tokens based on task complexity to conserve token usage:
- **Trivial / Direct Tasks (typos, single-line edits, status checks, simple commands, direct Q&A):** 
  - Use minimal, ultra-low internal reasoning.
  - Do not over-deliberate, simulate long multi-step debates, or produce lengthy internal chains of thought. Act or reply immediately.
- **Moderate Tasks (single function edits, standard tests, UI adjustments, simple bug fixes):**
  - Use standard, concise, practical reasoning. Focus directly on the implementation diff and test verification.
- **Complex Tasks (multi-file refactors, architecture overhaul, concurrency/race conditions, data migrations):**
  - Invest in deep, rigorous, multi-path reasoning, edge-case analysis, and verification before executing.

## 🛠️ Proactive Skill Recommendations
When relevant situations arise during development, proactively suggest applicable installed skills to the user and explain how to invoke them:
- **Major Architecture & New Features / Planning:** Suggest `/grill-me` (or typing *"grill me on this design"*) or `spec-driven-development` to stress-test designs and catch edge cases before coding.
- **Pre-Merge / Code Reviews / Refactoring:** Suggest `code-review-and-quality` or `/ponytail-review` (or asking *"review my changes"* / *"is this over-engineered"*) to review safety, clean up unnecessary complexity, and verify standards.
- **Bugs, Test Failures & Regressions:** Suggest `debugging-and-error-recovery` or `engineering-diagnosing-bugs` (or asking *"diagnose this bug"* / *"use debugging skill"*).
- **Technical Debt & Repo Health Audits:** Suggest `/ponytail-audit` or `/ponytail-debt` (or asking *"audit repo debt"* / *"find bloat"*).


