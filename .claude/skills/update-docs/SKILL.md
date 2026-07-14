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
