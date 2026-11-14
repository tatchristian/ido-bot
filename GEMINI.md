# Project Rules & Instructions

## 📑 Table of Contents
| Section / Skill | Line | Purpose |
| :--- | :--- | :--- |
| Memory-First Protocol | `L26` | Quick jump |
| Adaptive Reasoning | `L35` | Quick jump |
| Proactive Skill Recommendations | `L47` | Quick jump |
| ↳ `/grill-me` (Planning) | `L51` | Quick jump |
| ↳ `spec-driven-development` (Planning) | `L52` | Quick jump |
| ↳ `autoplan` (Planning) | `L53` | Quick jump |
| ↳ `/ponytail` (Senior Dev Mode) | `L56` | Quick jump |
| ↳ `/ponytail-review` (Code Review) | `L57` | Quick jump |
| ↳ `code-review-and-quality` (Review) | `L58` | Quick jump |
| ↳ `code-simplification` (Refactor) | `L59` | Quick jump |
| ↳ `debugging-and-error-recovery` (Debug) | `L62` | Quick jump |
| ↳ `diagnosing-bugs` (Diagnosis) | `L63` | Quick jump |
| ↳ `/ponytail-audit` (Repo Audit) | `L66` | Quick jump |
| ↳ `/ponytail-debt` (Debt Ledger) | `L67` | Quick jump |
| ↳ `/caveman` (Token Saver) | `L70` | Quick jump |
| ↳ `tdd` (Testing) | `L73` | Quick jump |
| ↳ `verify-and-stop` (Verification) | `L74` | Quick jump |

---

## 🧠 Memory-First Protocol
- **Start with the Index:** For every task, consult `memory/index.md` first.
- **Surgical Reading:** Read ONLY the specific memory note relevant to the current task (e.g. `memory/tournaments_cog.md` or `memory/workflow_clan_role_directory.md`).
- **Use memory as a guide:** Read the relevant `memory/` note to find your way around, then inspect the current source code and enough surrounding context for the task. If a note conflicts with the code, trust the code. Update a note only when a change adds lasting project knowledge.
- **Memory Maintenance:** When modifying or adding code components, update the corresponding `memory/*.md` note in the same turn.
- **Selective Test Execution:** When application code changes, run the relevant tests quietly with `-q` (`pytest <test_file> -q`). Do not run tests for documentation- or note-only edits.

---

## 🧠 Adaptive Reasoning & Token Optimization
Dynamically modulate thinking effort and internal reasoning tokens based on task complexity to conserve token usage:
- **Trivial / Direct Tasks (typos, single-line edits, status checks, simple commands, direct Q&A):** 
  - Use minimal, ultra-low internal reasoning.
  - Do not over-deliberate, simulate long multi-step debates, or produce lengthy internal chains of thought. Act or reply immediately.
- **Moderate Tasks (single function edits, standard tests, UI adjustments, simple bug fixes):**
  - Use standard, concise, practical reasoning. Focus directly on the implementation diff and test verification.
- **Complex Tasks (multi-file refactors, architecture overhaul, concurrency/race conditions, data migrations):**
  - Invest in deep, rigorous, multi-path reasoning, edge-case analysis, and verification before executing.

---

## 🛠️ Proactive Skill Recommendations
When relevant situations arise during development, proactively suggest applicable installed skills to the user and explain how to invoke them:

### Planning & Architecture
- **`/grill-me` (or `grilling`):** Stress-test designs, plans, and requirements before writing code.
- **`spec-driven-development` (or `spec`):** Turn vague feature ideas into exact specs with capability maps.
- **`autoplan`:** Automated review pipeline (architecture, edge cases, failure modes, tests).

### Senior Dev Mode & Code Review
- **`/ponytail`:** Lazy senior dev mode — the smallest change that fully solves the task, zero fluff/bloat.
- **`/ponytail-review`:** Pre-merge review checking if code is overengineered, safe, and holds under real load.
- **`code-review-and-quality`:** Multi-axis review assessing code quality against repository standards.
- **`code-simplification`:** Simplify existing code for readability without altering behavior.

### Debugging & Diagnosis
- **`debugging-and-error-recovery`:** Systematic root-cause debugging for unexpected crashes and failures.
- **`diagnosing-bugs`:** Hypothesis-driven diagnosis loop for hard bugs and performance regressions.

### Repo Audits & Debt
- **`/ponytail-audit`:** Full-repo quality audit: bugs, load limits, risky code, and dead code cleanup.
- **`/ponytail-debt`:** Shows all deferred shortcuts and technical debt comments in a clean ledger.

### Token Optimization & Terse Output
- **`/caveman`:** Ultra-terse output mode; cuts conversational fluff and saves 50–70% output tokens.

### Testing & Verification
- **`tdd` / `test-driven-development`:** Red-green-refactor workflow to drive logic changes test-first.
- **`verify-and-stop`:** Proves acceptance conditions are met with focused tests without scope creep.
