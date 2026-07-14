# Design — Documentation Freshness Automation

_Date: 2026-07-14 · Status: approved for planning_

## Problem

`docs/documentation.md` is a file-by-file engineering doc that explains what
every module does. It goes stale the moment code changes and no one updates it.
We want it to stay current automatically, treating the doc as a **cheap
byproduct that preserves explainability** — not a central, hand-crafted artifact.

## Core insight: detect vs. update are two different jobs

The original idea ("a skill, wired in via a pre-commit hook") conflates two
execution models. A Claude Code **skill** is invoked by the LLM during a
session; a git **pre-commit hook** is a deterministic shell script. A hook
cannot "run a skill," and shelling a hook out to `claude -p` would put a slow,
costly, non-deterministic LLM call in the commit path.

The design splits the one idea into two cooperating jobs:

| Job | Engine | Why |
|-----|--------|-----|
| **Detect** the doc is probably stale | Deterministic (git hook) | Cheap, instant, reliable — "did `src/` change without the doc changing?" is a diff |
| **Update** the doc well | LLM (a skill) | Prose synthesis and judgment — what Claude is good at |

The two reinforce each other: the skill does the real work *inside* a session;
the hook is the backstop for when the skill didn't fire or the commit happened
outside a Claude session. **Defense in depth — we never rely on the LLM
remembering.**

## Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Trigger mechanism | **Pre-commit detector + skill** | Only option that fires independent of Claude, at ~zero cost; cleanly separates detection from update. |
| D2 | Enforcement strength | **Block + escape hatch** | Warn-only decays into ignored noise; hard block punishes valid refactors and gets ripped out. `--no-verify` lets you say "I checked, no doc impact." |
| D3 | Update authorship | **Claude drafts targeted edits; occasional human spot-check** | Doc is a cheap byproduct for explainability. Targeted edits keep diffs small; full regen would turn a 3-line change into a 200-line diff. |
| D4 | Doc structure | **Keep file-by-file** | Maps 1:1 to code = best for explainability. The rot risk that would argue for restructuring is exactly what this automation removes. |
| D5 | Cadence | **Event-based only** | Every code-touching commit already *is* "after something new is developed." A scheduled sweep earns its keep only on multi-committer repos. YAGNI. |

## Architecture

Two components.

### 1. Detector — git pre-commit hook

- Lives in a tracked `.githooks/pre-commit` (Option A: `core.hooksPath`, no
  framework dependency).
- Logic: inspect **staged** files. If any `src/**.py` is staged **and**
  `docs/documentation.md` is **not** staged → exit non-zero with a message:
  - what happened ("src changed but the docs didn't"),
  - what to do (run `/update-docs`, or edit the doc),
  - the escape hatch (`git commit --no-verify`).
- The detector is **deliberately dumb**: it only knows "src changed, doc didn't,"
  never whether the change *needed* doc work. The `--no-verify` escape is the
  intended way to record "I checked, no doc impact" — not a loophole. Do NOT try
  to make the hook smarter; that would mean putting an LLM in the commit path,
  the exact thing this design avoids.

### 2. Updater — `/update-docs` skill

- Lives in `.claude/skills/update-docs/SKILL.md`, modeled on the existing
  `decision-logging` skill.
- **Auto-trigger:** description tells Claude to fire when it has changed code
  under `src/` during a session. This trigger is **soft** (Claude decides) —
  which is precisely why the deterministic hook backs it up.
- **Manual:** invocable as `/update-docs`.
- **Behavior:** read the code diff (staged/recent) and the current
  `documentation.md`; make **targeted edits** to the affected file-by-file
  sections only; bump the `Last updated` stamp. Do not rewrite untouched
  sections. Do not restructure.

## Setup (one-time, documented in README)

```bash
git config core.hooksPath .githooks
```

`core.hooksPath` is per-clone git config, so this one line is required after
cloning. This is the only ceremony Option A costs.

## Data flow

```
Claude session edits src/ ──► /update-docs fires ──► targeted edit to documentation.md
                                                              │
                                                              ▼
git commit ──► .githooks/pre-commit ──► src staged & doc not? ──no──► commit proceeds
                                                │
                                               yes
                                                ▼
                                   BLOCK: run /update-docs, or --no-verify
```

## Testing / verification

- **Hook, positive:** stage a `src/*.py` change without the doc → commit is
  blocked with the guidance message.
- **Hook, negative:** stage a `src/*.py` change *and* a doc edit → commit
  proceeds.
- **Hook, irrelevant:** stage a test-only or non-`src` change → commit proceeds
  (not triggered).
- **Escape hatch:** blocked commit + `--no-verify` → proceeds.
- **Skill:** run `/update-docs` after a real `src/` change → produces a small,
  correct, targeted diff to the affected section(s) and updates the stamp.

## Out of scope (YAGNI)

- Scheduled/periodic doc sweeps (cron, `/loop`, routines).
- Any LLM call inside the git hook.
- CI enforcement (no CI exists yet).
- Restructuring the doc away from file-by-file.
- Auto-regeneration of the whole doc.

## Future migration note

If/when `ruff` (or formatting) pre-commit hooks are added, migrate this check
into a `.pre-commit-config.yaml` `repo: local` hook — the `pre-commit` framework
earns its dependency cost at 2+ hooks. Until then, the tracked script is simpler
and equally version-controlled. This is a deliberate future step, not a lock-in.
