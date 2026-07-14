# Documentation Freshness Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `docs/documentation.md` current by pairing a deterministic git pre-commit *detector* with an LLM-powered `/update-docs` *updater* skill.

**Architecture:** Split the job in two. A tracked `.githooks/pre-commit` bash script blocks any commit that stages `src/**.py` changes without staging `docs/documentation.md` (escape hatch: `git commit --no-verify`). A `.claude/skills/update-docs/` skill, authored via `/skill-creator`, makes targeted edits to the affected file-by-file sections during a Claude session. The hook is the deterministic backstop; the skill does the real work.

**Tech Stack:** Bash (git hook), git `core.hooksPath`, Claude Code skill (Markdown), `/skill-creator`.

## Global Constraints

- **Option A delivery:** tracked `.githooks/` + `git config core.hooksPath .githooks`. No `pre-commit` framework, no new Python/tool dependencies.
- **No LLM in the git hook.** The hook is pure bash and deliberately dumb — it only knows "src changed, doc didn't," never whether the change needed doc work.
- **Escape hatch is intended, not a loophole:** `git commit --no-verify` is how the user records "I checked, no doc impact."
- **Doc structure stays file-by-file.** The skill edits affected sections only; it never restructures or full-regenerates.
- **Event-based only.** No scheduler, cron, or CI. No periodic sweep.
- **Detector match rules:** src trigger = staged path matching `^src/.*\.py$`; doc satisfied = staged path exactly `docs/documentation.md`.
- Spec of record: `docs/superpowers/specs/2026-07-14-doc-freshness-automation-design.md`.

---

## File Structure

- **Create** `.githooks/pre-commit` — the detector (tracked, executable bash).
- **Modify** `README.md` — add the one-time `core.hooksPath` setup note.
- **Create** `.claude/skills/update-docs/SKILL.md` — the updater skill (authored via `/skill-creator`).

Two tasks. Task 1 delivers the detector + its setup + README note (a reviewer could accept the hook independently of the skill). Task 2 delivers the skill.

---

### Task 1: Pre-commit detector hook

**Files:**
- Create: `.githooks/pre-commit`
- Modify: `README.md` (Quickstart area — add a one-time setup line)

**Interfaces:**
- Consumes: nothing (entry point is git's pre-commit stage).
- Produces: a git hook that exits `0` (allow) or `1` (block) based on staged paths. Task 2's skill is what the block message tells the user to run.

- [ ] **Step 1: Write the hook script**

Create `.githooks/pre-commit`:

```bash
#!/usr/bin/env bash
# Docs freshness detector (see docs/superpowers/specs/2026-07-14-doc-freshness-automation-design.md).
# Blocks a commit that changes src/ Python without updating the engineering doc.
# Deliberately dumb: it only knows "src changed, doc didn't" — not whether the
# change needed doc work. Bypass a genuine false positive with: git commit --no-verify
set -euo pipefail

staged=$(git diff --cached --name-only --diff-filter=ACM)
src_changed=$(printf '%s\n' "$staged" | grep -E '^src/.*\.py$' || true)
doc_staged=$(printf '%s\n' "$staged" | grep -Fx 'docs/documentation.md' || true)

if [ -n "$src_changed" ] && [ -z "$doc_staged" ]; then
  {
    echo "✗ Docs freshness check: src/ changed but docs/documentation.md did not."
    echo ""
    echo "  Changed source files:"
    printf '%s\n' "$src_changed" | sed 's/^/    /'
    echo ""
    echo "  Keep the engineering doc current:"
    echo "    • In a Claude session: run /update-docs"
    echo "    • Or edit docs/documentation.md yourself"
    echo ""
    echo "  If this change genuinely needs no doc update, bypass with:"
    echo "    git commit --no-verify"
  } >&2
  exit 1
fi
exit 0
```

- [ ] **Step 2: Make it executable and enable the hooks path**

```bash
chmod +x .githooks/pre-commit
git config core.hooksPath .githooks
```

Expected: no output; `git config --get core.hooksPath` prints `.githooks`.

- [ ] **Step 3: Verify the BLOCK case (src staged, doc not)**

Stage a harmless src change and run the hook directly:

```bash
printf '\n# freshness-check probe\n' >> src/config.py
git add src/config.py
.githooks/pre-commit; echo "exit=$?"
```

Expected: the "✗ Docs freshness check" message prints and `exit=1`.

- [ ] **Step 4: Verify the PASS case (src + doc staged together)**

```bash
git add docs/documentation.md   # stage the doc alongside (touch it first if unchanged)
touch docs/documentation.md && git add docs/documentation.md
.githooks/pre-commit; echo "exit=$?"
```

Expected: no message and `exit=0`.

- [ ] **Step 5: Verify the IRRELEVANT case (non-src change only), then clean up**

```bash
git restore --staged src/config.py docs/documentation.md
git checkout -- src/config.py
git add README.md 2>/dev/null || true   # any non-src staged file
.githooks/pre-commit; echo "exit=$?"
git restore --staged README.md 2>/dev/null || true
```

Expected: no message and `exit=0`. (Confirms a docs-only or non-src commit is never blocked.)

- [ ] **Step 6: Add the one-time setup note to the README**

In `README.md`, under the Quickstart, add after the `uv sync` step:

```markdown
# (one-time) enable the repo's git hooks — keeps docs/documentation.md in sync
git config core.hooksPath .githooks
```

Rationale to include as prose near the Documentation section: `core.hooksPath` is per-clone git config, so each clone runs this once.

- [ ] **Step 7: Commit**

```bash
git add .githooks/pre-commit README.md
git commit -m "Add pre-commit detector that blocks src changes with stale docs"
```

Expected: commit succeeds (this commit stages no `src/**.py`, so the hook allows it).

---

### Task 2: `/update-docs` skill

**Files:**
- Create: `.claude/skills/update-docs/SKILL.md` (authored via `/skill-creator`)

**Interfaces:**
- Consumes: the block message from Task 1's hook points the user here; the skill reads the code diff + current `docs/documentation.md`.
- Produces: a manually- and auto-invocable `update-docs` skill that makes targeted edits to `docs/documentation.md`.

- [ ] **Step 1: Invoke `/skill-creator` to author the skill**

Run `/skill-creator` and create a skill named `update-docs` with this brief (model it on the existing `.claude/skills/decision-logging/SKILL.md`):

- **Purpose:** keep `docs/documentation.md` current as a cheap byproduct that preserves explainability.
- **Auto-trigger (description):** fire when Claude has changed code under `src/` during the session, or when the user says "update the docs", "sync the documentation", or runs `/update-docs`. Trigger at the point code is changed, not while still exploring.
- **Behavior in the body:**
  1. Determine what changed: read the staged/recent diff of `src/**` (`git diff --cached -- src` then `git diff -- src`).
  2. Read the current `docs/documentation.md`.
  3. Make **targeted edits** to the affected file-by-file section(s) only — do not rewrite untouched sections, do not restructure, do not full-regenerate.
  4. Update the `_Last updated: YYYY-MM-DD · reflects milestone …_` stamp near the top to today's date.
  5. Keep the file-by-file structure and the decision-ID references (e.g. `D9`) intact; point to `docs/decisions.md` for the *why* rather than re-explaining.
- **Scope note in the body:** the detector hook only knows "src changed, doc didn't"; this skill is what actually reconciles them. If a src change has no doc impact, say so and leave the doc unchanged (the user can bypass the hook with `--no-verify`).

- [ ] **Step 2: Verify the skill file exists with correct frontmatter**

```bash
sed -n '1,12p' .claude/skills/update-docs/SKILL.md
```

Expected: YAML frontmatter with `name: update-docs` and a `description:` that names the `src/` trigger and the `/update-docs` manual invocation.

- [ ] **Step 3: End-to-end test — make a real src change and run the skill**

Make a small, real change to a `src/` module (e.g. rename a helper or add a parameter), then invoke `/update-docs`.

Expected: the skill produces a **small, targeted** diff to `docs/documentation.md` touching only the section for the changed file, and bumps the `Last updated` stamp to today. It must NOT rewrite unrelated sections.

- [ ] **Step 4: Confirm the hook + skill loop closes**

With both the src change and the skill's doc edit staged:

```bash
git add -A
.githooks/pre-commit; echo "exit=$?"
```

Expected: `exit=0` — because the doc was updated alongside src, the detector allows the commit.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/update-docs/ docs/documentation.md src/
git commit -m "Add update-docs skill and sync documentation for the test change"
```

(If the Step 3 test change is not one you want to keep, revert it and the corresponding doc edit before committing, and commit only `.claude/skills/update-docs/`.)

---

## Self-Review

**Spec coverage:**
- D1 pre-commit detector + skill → Tasks 1 & 2. ✓
- D2 block + escape hatch → Task 1 Step 1 (exit 1 + `--no-verify` message), verified Steps 3–5. ✓
- D3 Claude targeted edits → Task 2 Step 1 behavior + Step 3 verification. ✓
- D4 keep file-by-file → Global Constraints + Task 2 behavior. ✓
- D5 event-based only → Global Constraints (no scheduler); nothing in the plan adds one. ✓
- Option A (`core.hooksPath`, no framework) → Global Constraints + Task 1 Steps 2, 6. ✓
- One-time setup documented in README → Task 1 Step 6. ✓
- "Deliberately dumb hook / no LLM in hook" guardrail → Global Constraints + hook comment. ✓
- Future `pre-commit`-framework migration note → out of scope for build; recorded in the spec, not re-planned here. ✓ (intentional)

**Placeholder scan:** No TBD/TODO; every code and command step shows exact content. Task 2 Step 1 is a `/skill-creator` brief rather than a verbatim file — intentional, since the user asked for the skill to be authored via `/skill-creator`; the brief fully specifies name, trigger, and behavior, and Steps 2–4 verify the result.

**Type consistency:** Hook match rules (`^src/.*\.py$`, exact `docs/documentation.md`) are stated identically in Global Constraints and Task 1 Step 1. The skill's stamp format matches the one already in `docs/documentation.md`.
