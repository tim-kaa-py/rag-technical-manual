# Multi-Folder Documentation Freshness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the documentation-freshness machinery from one folder to three (`src`, `eval`, `api`), each with its own doc under `docs/documentation/`, gated by targeted checks in the single pre-commit hook and maintained by one generalized `update-docs` skill.

**Architecture:** Move the existing `docs/documentation.md` to `docs/documentation/src.md`, fixing its internal links. Rewrite the one `.githooks/pre-commit` as a table-driven loop over three `folder|doc` pairs (each check independent and targeted). Generalize the `update-docs` skill to map any changed folder to its doc and apply the same targeted-edit procedure, following a per-folder doc shape. Write `eval.md`/`api.md` content lazily — only when `eval/`/`api/` first get real code (M2/M4). Finish with a cross-reference sweep so every living reference points at the new paths.

**Tech Stack:** Bash (git hook), git `core.hooksPath`, Claude Code skill (Markdown), `git mv`.

## Global Constraints

- **Move, don't retype:** use `git mv docs/documentation.md docs/documentation/src.md` so history is preserved.
- **One hook, table-driven.** A single `.githooks/pre-commit` loops over `folder|doc` pairs: `src|docs/documentation/src.md`, `eval|docs/documentation/eval.md`, `api|docs/documentation/api.md`. No `pre-commit` framework.
- **One generalized skill.** Do not create per-folder skills.
- **Docs are written lazily.** Do NOT create `docs/documentation/api.md` or `docs/documentation/eval.md` in this work — they are empty folders (M2/M4 unbuilt). The skill creates them on first real code.
- **Purpose-shaped docs:** `src.md` = file-by-file (unchanged); `eval.md` = methodology-first; `api.md` = contract-first.
- **Escape hatch preserved:** `git commit --no-verify` remains the intended bypass; the hook stays deliberately dumb (folder changed, doc didn't — no LLM in the hook).
- **Match rule:** folder trigger = staged path matching `^<folder>/.*\.py$`; doc satisfied = staged path exactly equal to the mapped doc.
- **Cross-reference sweep is the LAST task** (Task 3): update every living reference to the old path after the move is done.
- Supersedes the single-folder design in `docs/superpowers/specs/2026-07-14-doc-freshness-automation-design.md` (left as a historical record).

---

## File Structure

- **Move** `docs/documentation.md` → `docs/documentation/src.md` (content identical except its own relative links).
- **Rewrite** `.githooks/pre-commit` — table-driven over three folder|doc pairs.
- **Rewrite** `.claude/skills/update-docs/SKILL.md` — generalized mapping + per-folder shapes + lazy creation.
- **Modify** `README.md` — the hooks comment (line ~13) and the Documentation section (line ~43).

Three tasks. Task 1 (move + hook) and Task 2 (skill) each ship an independently testable deliverable. Task 3 is the reference sweep, deliberately last.

---

### Task 1: Restructure the src doc + generalize the hook

**Files:**
- Move: `docs/documentation.md` → `docs/documentation/src.md`
- Modify: `docs/documentation/src.md` (internal links only)
- Rewrite: `.githooks/pre-commit`

**Interfaces:**
- Consumes: the existing `core.hooksPath=.githooks` config (already set).
- Produces: a hook that maps `src|eval|api` → their docs and exits `0`/`1` per staged paths. Task 2's skill writes to the same three doc paths.

- [ ] **Step 1: Move the doc with git (preserves history)**

```bash
git mv docs/documentation.md docs/documentation/src.md
git status --short   # expect: renamed: docs/documentation.md -> docs/documentation/src.md
```

- [ ] **Step 2: Fix the moved doc's internal relative links**

The file went one directory deeper, so its relative links must gain one `../`.

In `docs/documentation/src.md`, replace both occurrences of the decisions link:
- `[decisions.md](decisions.md)` → `[decisions.md](../decisions.md)` (appears twice — lines ~7 and ~29)

And the README link:
- `[README](../README.md#quickstart)` → `[README](../../README.md#quickstart)`

Verify no stale relative links remain:

```bash
grep -nE '\]\((decisions\.md|\.\./README\.md)' docs/documentation/src.md
```

Expected: no output (both patterns now have the corrected depth).

- [ ] **Step 3: Rewrite the hook as a table-driven loop**

Replace the entire contents of `.githooks/pre-commit` with:

```bash
#!/usr/bin/env bash
# Docs freshness detector (table-driven). Each code area must keep its doc in
# sync: a commit that changes <folder>/ must also stage <doc>. Deliberately
# dumb — it only knows "<folder> changed, its doc didn't", never whether the
# change needed doc work. Bypass a genuine false positive with:
#   git commit --no-verify
set -euo pipefail

# folder|doc pairs. Add a line to cover a new code area.
PAIRS=(
  "src|docs/documentation/src.md"
  "eval|docs/documentation/eval.md"
  "api|docs/documentation/api.md"
)

staged=$(git diff --cached --name-only --diff-filter=ACM)
blocked=0

for pair in "${PAIRS[@]}"; do
  folder="${pair%%|*}"
  doc="${pair##*|}"
  changed=$(printf '%s\n' "$staged" | grep -E "^${folder}/.*\.py$" || true)
  doc_staged=$(printf '%s\n' "$staged" | grep -Fx "$doc" || true)
  if [ -n "$changed" ] && [ -z "$doc_staged" ]; then
    if [ "$blocked" -eq 0 ]; then
      echo "✗ Docs freshness check failed." >&2
      blocked=1
    fi
    {
      echo ""
      echo "  ${folder}/ changed but ${doc} did not. Changed files:"
      printf '%s\n' "$changed" | sed 's/^/    /'
    } >&2
  fi
done

if [ "$blocked" -eq 1 ]; then
  {
    echo ""
    echo "  Keep the doc(s) current:"
    echo "    • In a Claude session: run /update-docs"
    echo "    • Or edit the doc(s) named above yourself"
    echo ""
    echo "  If these changes genuinely need no doc update, bypass with:"
    echo "    git commit --no-verify"
  } >&2
  exit 1
fi
exit 0
```

- [ ] **Step 4: Verify BLOCK — src changed, src doc not**

```bash
printf '\n# freshness-check probe\n' >> src/config.py
git add src/config.py
.githooks/pre-commit; echo "exit=$?"
```

Expected: message names `src/` and `docs/documentation/src.md`; `exit=1`.

- [ ] **Step 5: Verify PASS — src doc staged alongside**

```bash
printf '\n<!-- probe -->\n' >> docs/documentation/src.md
git add docs/documentation/src.md
.githooks/pre-commit; echo "exit=$?"
```

Expected: no message; `exit=0`.

- [ ] **Step 6: Verify eval/api checks are inert, then clean up probes**

```bash
git restore --staged src/config.py docs/documentation/src.md
git checkout -- src/config.py docs/documentation/src.md
.githooks/pre-commit; echo "exit=$?"   # nothing staged
```

Expected: no message; `exit=0`. (eval/ and api/ are empty, so their checks never fire — confirms they're inert.)

- [ ] **Step 7: Commit**

This commit stages the rename + hook, no `src/**.py`, so the hook allows it.

```bash
git add .githooks/pre-commit docs/documentation/src.md
git commit -m "Restructure docs: move src doc under docs/documentation/, generalize hook to per-folder checks"
```

Expected: `git log --oneline -1` shows the commit; `git show --stat HEAD` shows the rename `documentation.md -> documentation/src.md`.

---

### Task 2: Generalize the `update-docs` skill

**Files:**
- Rewrite: `.claude/skills/update-docs/SKILL.md`

**Interfaces:**
- Consumes: the three doc paths produced by Task 1's hook table.
- Produces: a single skill that maps any changed folder (`src`/`eval`/`api`) to its doc and edits it, creating the doc on first use.

- [ ] **Step 1: Replace the skill with the generalized version**

Replace the entire contents of `.claude/skills/update-docs/SKILL.md` with:

````markdown
---
name: update-docs
description: Keep the engineering docs under docs/documentation/ in sync with the code by making targeted edits to the affected doc. Each code area has its own doc — src/ → docs/documentation/src.md, eval/ → docs/documentation/eval.md, api/ → docs/documentation/api.md. Use this whenever you have changed code under src/, eval/, or api/ during a session, or when the user says "update the docs", "sync the documentation", "the docs are stale", or runs /update-docs. The repo's pre-commit hook blocks commits that touch one of these folders without updating its doc, so run this before committing such changes. Trigger even when the user doesn't name the doc — if one of those folders changed and a commit is near, its doc probably needs reconciling.
---

# Update docs

Keep the engineering docs under `docs/documentation/` current as a **cheap byproduct that preserves explainability**. Each code area maps to exactly one doc:

| Folder | Doc | Shape |
| --- | --- | --- |
| `src/` | `docs/documentation/src.md` | file-by-file |
| `eval/` | `docs/documentation/eval.md` | methodology-first |
| `api/` | `docs/documentation/api.md` | contract-first |

When a folder changes, its doc drifts. Reconcile it with the smallest edit that makes the doc true again — not a rewrite.

The deterministic pre-commit hook (`.githooks/pre-commit`) only knows "<folder> changed, its doc didn't." It can't tell whether the change *needed* doc work. This skill is the judgment layer that decides and edits.

## Procedure

1. **See what changed.** For each of `src`, `eval`, `api`, read the diff:

   ```bash
   git diff --cached -- <folder>   # staged (the commit being prepared)
   git diff -- <folder>            # unstaged, not yet added
   ```

   Work only on the folder(s) that actually changed.

2. **Open that folder's doc** (from the table). Read it in full so edits land in the right place and match the voice. **If it doesn't exist yet** (the folder just got its first code), create it following the shape for that folder (below), starting with a `_Last updated: YYYY-MM-DD · reflects milestone …_` stamp line.

3. **Make targeted edits.** Edit only the section(s) affected by the change. Leave untouched sections exactly as they are — no reflowing or "improving" prose that didn't change.

4. **Bump the stamp.** Update the `_Last updated: …_` line near the top to today's date. Update the milestone only if the change moved the project to a new one.

## Doc shapes

Each doc is shaped to what a reader actually needs from that area — don't force one structure onto all three.

### `src.md` — file-by-file
A per-module map following the pipeline order (ingest → query). Each file gets a short section: its responsibility, key functions, and the decision-IDs behind it. This 1:1 mapping to the code is what makes it explainable.

### `eval.md` — methodology-first
Lead with **what is measured and how to trust it**, not the file list:
- metrics (e.g. retrieval hit-rate/recall over expected source pages; answer groundedness via LLM-as-judge)
- the judge rubric
- the golden Q&A set design
- the embedding A/B (small vs large)
- how to run it and how to read the output

Brief per-file notes come after the methodology.

### `api.md` — contract-first
Lead with **the contract**, not the file list:
- the endpoint(s): method + path (e.g. `POST /query`)
- request and response schema (fields + types)
- validation and error/status behavior
- how to run the service locally

Brief per-file notes come after the contract.

## What to preserve
- **Each doc's shape** (above). Never restructure `src.md` into a concept layout, and never full-regenerate a whole doc from code — that makes a huge diff for a small change and destroys hand-tuning.
- **Decision-ID references** (e.g. `D9`, `D11`). The docs point at `docs/decisions.md` for the *why* rather than re-explaining. Keep those intact; if a change touches a decision's rationale, update `docs/decisions.md` via the decision-logging skill.

## No doc impact
If a change is genuinely invisible at the doc's altitude (internal refactor, comment, local rename), the correct action is **no edit**. Say so plainly, e.g. "This change is internal to `retrieve()` and doesn't affect what `src.md` describes, so no doc update is needed." The user can then `git commit --no-verify` to bypass the hook — the intended way to record "I checked, no doc impact." Don't invent a doc change just to satisfy the hook.

## Flow
1. Read the diffs and the affected doc(s).
2. Decide: does the change alter what the doc describes? If not, report "no doc impact" and stop.
3. If yes, make the targeted edit(s) (creating the doc if absent) and bump the stamp.
4. Show a short summary of what was reconciled (which doc/sections, why).
5. Stage the doc alongside the code change so the commit passes the hook; commit per the repo's normal conventions.

## Manual invocation
When invoked as `/update-docs` (optionally with a hint like `/update-docs the eval metric change`), run the same procedure against the current diff. If the diff is empty or nothing in it affects a doc, say so rather than editing filler.
````

- [ ] **Step 2: Verify frontmatter and coverage**

```bash
sed -n '1,4p' .claude/skills/update-docs/SKILL.md
grep -c -E 'documentation/(src|eval|api)\.md' .claude/skills/update-docs/SKILL.md
```

Expected: frontmatter has `name: update-docs` and a description naming all three folders/docs and `/update-docs`; the grep count is ≥ 3 (all three doc paths present).

- [ ] **Step 3: End-to-end test — a real, reversible src change**

Bump `TOP_K` in `src/config.py` (the doc cites "top-5" in several places), then follow the skill to reconcile `src.md`:

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path("src/config.py"); s = p.read_text()
p.write_text(s.replace("TOP_K = 5", "TOP_K = 8")); print("TOP_K -> 8 (test)")
PY
grep -n -iE 'top.?5|TOP_K' docs/documentation/src.md
```

Apply targeted edits to `docs/documentation/src.md` changing the top-5 references to top-8 (and bump the stamp to today if not already today). Then confirm the doc diff is targeted:

```bash
git --no-pager diff --stat -- docs/documentation/src.md
```

Expected: only the retrieval-budget lines changed (≈5 lines), no unrelated edits.

- [ ] **Step 4: Confirm the loop closes, then revert the test change**

```bash
git add src/config.py docs/documentation/src.md
.githooks/pre-commit; echo "exit=$?"          # expect exit=0 (doc staged with src)
git restore --staged src/config.py docs/documentation/src.md
git checkout -- src/config.py docs/documentation/src.md
grep -n 'TOP_K = ' src/config.py               # expect TOP_K = 5 restored
```

Expected: hook `exit=0`; after revert `TOP_K = 5` and `src.md` shows `top-5` again.

- [ ] **Step 5: Commit the skill**

```bash
git add .claude/skills/update-docs/SKILL.md
git commit -m "Generalize update-docs skill to per-folder docs (src/eval/api) with purpose-shaped conventions"
```

Expected: commit succeeds (no `src/**.py` staged).

---

### Task 3: Cross-reference sweep (LAST)

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the final doc paths from Tasks 1–2.
- Produces: no dangling references to the old `docs/documentation.md` path in any living doc.

- [ ] **Step 1: Find every remaining reference to the old path**

```bash
git grep -n 'docs/documentation\.md' -- . ':!docs/superpowers/*'
git grep -n 'documentation\.md' -- README.md CLAUDE.md
```

Expected living references to fix are in `README.md` (the hook comment and the Documentation section). `CLAUDE.md`'s directory tree does not name the file — leave it. `docs/superpowers/*` specs/plans are historical snapshots — leave them.

- [ ] **Step 2: Update the README hooks comment**

In `README.md` Quickstart, change:

```markdown
# (one-time) enable the repo's git hooks — keeps docs/documentation.md in sync
```

to:

```markdown
# (one-time) enable the repo's git hooks — keeps docs/documentation/ in sync
```

- [ ] **Step 3: Update the README Documentation section**

Replace the current single-doc bullet block:

```markdown
- `docs/documentation.md` — engineering documentation: what every file does and why, following the ingest → query pipeline. A pre-commit hook (`.githooks/pre-commit`) blocks commits that change `src/` without updating this doc; run `git config core.hooksPath .githooks` once per clone to enable it.
- `docs/decisions.md` — running decision log (D1–D18) that the code references by ID.
- `docs/requirements.md` — engineering spec and milestones.
```

with:

```markdown
Engineering docs live under `docs/documentation/`, one per code area:

- `docs/documentation/src.md` — the RAG pipeline (ingest → query), file by file. **Present.**
- `docs/documentation/eval.md` — the evaluation harness: methodology, metrics, how to read the numbers. *Arrives with M2.*
- `docs/documentation/api.md` — the FastAPI service: endpoint contract, request/response, errors. *Arrives with M4.*

A pre-commit hook (`.githooks/pre-commit`) blocks a commit that changes `src/`, `eval/`, or `api/` without updating that area's doc. Enable it once per clone with `git config core.hooksPath .githooks`.

- `docs/decisions.md` — running decision log (D1–D18) that the code references by ID.
- `docs/requirements.md` — engineering spec and milestones.
```

- [ ] **Step 4: Confirm no living references remain**

```bash
git grep -n 'docs/documentation\.md' -- . ':!docs/superpowers/*'
```

Expected: no output (all living references now point at `docs/documentation/...`).

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "Update README references to the docs/documentation/ layout"
```

---

## Self-Review

**Spec coverage (against the approved design):**
- Rename to symmetric set (`docs/documentation/{src,api,eval}.md`) → Task 1 Steps 1–2 (src moved; eval/api created lazily by the skill, per Global Constraints). ✓
- Table-driven hook over three folder|doc pairs → Task 1 Step 3, verified Steps 4–6. ✓
- Generalized single skill with per-folder shapes + lazy creation → Task 2 Step 1. ✓
- Purpose-shaped docs (src file-by-file / eval methodology / api contract) → skill "Doc shapes" section. ✓
- Docs written lazily (no empty api.md/eval.md now) → Global Constraints; nothing in the plan creates them. ✓
- Escape hatch + dumb hook preserved → Task 1 Step 3 (message + `--no-verify`; pure bash). ✓
- Cross-reference sweep as the LAST step → Task 3. ✓
- Moved doc's own links fixed → Task 1 Step 2. ✓

**Placeholder scan:** No TBD/TODO. Full file contents given for the hook (Task 1 Step 3) and skill (Task 2 Step 1); exact edits given for README (Task 3). The lazy `eval.md`/`api.md` content is intentionally not written here — those folders have no code yet, and the skill authors them on first use (a design decision, not a gap).

**Type/path consistency:** The three doc paths (`docs/documentation/src.md`, `.../eval.md`, `.../api.md`) and the match rule (`^<folder>/.*\.py$`, exact doc path) are identical across Global Constraints, the hook table (Task 1), and the skill table (Task 2). The stamp format matches the one already in the moved `src.md`.
