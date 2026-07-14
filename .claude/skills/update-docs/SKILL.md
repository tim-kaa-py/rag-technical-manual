---
name: update-docs
description: Keep docs/documentation.md in sync with the code by making targeted edits to the affected file-by-file sections. Use this whenever you have changed code under src/ during a session (a module's behavior, signature, responsibility, or a new/removed file), or when the user says "update the docs", "sync the documentation", "the docs are stale", or runs /update-docs. The repo's pre-commit hook blocks commits that touch src/ without updating this doc, so run this before committing src/ changes. Trigger even when the user doesn't name the doc explicitly — if src/ changed and the commit is near, the doc probably needs reconciling.
---

# Update docs

Keep `docs/documentation.md` current as a **cheap byproduct that preserves explainability**. The doc is a file-by-file map of what each module does and why; when `src/` changes, the map drifts. This skill reconciles them with the smallest edit that makes the doc true again — not a rewrite.

The deterministic pre-commit hook (`.githooks/pre-commit`) only knows "`src/` changed, the doc didn't." It can't tell whether the change *needed* doc work. This skill is the judgment layer that actually decides and edits.

## When a src change affects the doc

The doc describes each module's **responsibility, key functions, and the decisions behind them**. A src change affects the doc when it changes any of those:

- a new or deleted file under `src/`
- a module's responsibility or role in the pipeline shifting
- a function/class that the doc names being renamed, removed, or changing signature in a way the doc describes
- behavior the doc explains changing (e.g. the doc says "exact scan, no ANN index" and the retrieval path changes)

A src change does **not** affect the doc when it's internal and invisible at the doc's altitude: refactoring a function body, renaming a local variable, adjusting a comment, tweaking a value the doc doesn't cite. In that case, make no edit — see "No doc impact" below.

## Procedure

1. **See what changed.** Read the diff:

   ```bash
   git diff --cached -- src   # staged changes (the commit being prepared)
   git diff -- src            # unstaged changes not yet added
   ```

   Both, because the change may be in either state depending on when this runs.

2. **Read the current doc.** Read `docs/documentation.md` in full so edits land in the right sections and match the surrounding voice.

3. **Make targeted edits.** Edit only the file-by-file section(s) for the modules that actually changed. Update the description to match the new reality. Add a section for a new file, remove one for a deleted file. Leave every untouched section exactly as it is — do not rewrite, reflow, or "improve" prose that didn't need to change.

4. **Bump the stamp.** Update the `_Last updated: YYYY-MM-DD · reflects milestone …_` line near the top to today's date. Update the milestone only if the change actually moved the project to a new milestone; otherwise leave the milestone label.

## What to preserve

- **The file-by-file structure.** This structure maps 1:1 to the code, which is exactly what makes the doc explainable. Never restructure it into a concept/flow layout, and never full-regenerate the whole file from the code — that produces a huge diff for a small change and destroys any hand-tuning.
- **Decision-ID references** (e.g. `D9`, `D11`). The doc points at `docs/decisions.md` for the *why* rather than re-explaining it. Keep those references intact; if a change touches a decision's rationale, update `docs/decisions.md` via the decision-logging skill rather than expanding the explanation here.

## No doc impact

If the src change is genuinely invisible at the doc's altitude (internal refactor, comment, local rename), the correct action is **no edit**. Say so plainly — e.g. "This change is internal to `retrieve()` and doesn't affect what the doc describes, so no doc update is needed." The user can then commit with `git commit --no-verify` to bypass the hook, which is the intended way to record "I checked, no doc impact." Don't invent a doc change just to satisfy the hook.

## Flow

1. Read the diff and the current doc.
2. Decide: does this change what the doc describes? If not, report "no doc impact" and stop.
3. If yes, make the targeted edit(s) and bump the stamp.
4. Show a short summary of what was reconciled (which sections, why).
5. Stage the doc alongside the src change so the commit passes the hook; commit following the repo's normal conventions.

## Manual invocation

When invoked as `/update-docs` (optionally with a hint like `/update-docs the retrieval change`), run the same procedure against the current diff. If the diff is empty or nothing in it affects the doc, say so rather than editing filler.
