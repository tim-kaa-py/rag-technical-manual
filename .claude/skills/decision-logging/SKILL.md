---
name: decision-logging
description: Append a concise entry to the project decision log (docs/decisions.md) whenever a design decision gets settled. Use this whenever a design, architecture, tooling, or process decision is confirmed in conversation — an option is chosen over alternatives, a trade-off is resolved, a reviewer's recommendation is accepted, or the user says "let's go with X", "I follow that recommendation", "option A", or approves a proposal. Trigger at the moment the decision is CONFIRMED, not while options are still being weighed. Also invocable manually as /decision-logging to log a decision after the fact.
---

# Decision logging

Keep `docs/decisions.md` current: every settled design decision becomes one concise, defensible entry, written at the moment the decision is made — while the options and reasoning are still fresh in the conversation.

## What counts as a loggable decision

Apply the **defensibility test** — log the decision only if both hold:

1. **Two or more viable options were genuinely weighed.** A choice with no real alternative (there was only one sensible way) is not a decision, it's an implementation detail.
2. **The choice constrains future work or would need defending later** — to a reviewer, a new team member, or the author six months out.

Examples: chunk size and overlap → log. Vector index type → log. Naming a module `ingest.py`, picking a variable name, an obvious library default nobody questioned → don't log.

When unsure, ask: "Would someone probing this project ask *why* we did it this way?" If yes, log it.

## When to write the entry

Immediately after the decision is confirmed in conversation — not during the discussion (options still open), and not batched at the end of the session (rationale gets lossy). If several decisions were confirmed at once (e.g. one approval covering multiple questions), write one entry per decision.

## Entry format

Append to `docs/decisions.md`, matching the file's existing style exactly:

```markdown
## D<n> — <Short decision title> (<YYYY-MM-DD>)

**Decision:** <what was decided, concretely — include the actual numbers/names, not vague labels>

**Considered:**
- *<Chosen option>* — chosen: <the decisive reason>.
- *<Alternative>* — <its genuine merit>, but <why it lost>. Rejected.

**Why:** <the core trade-off reasoning in 1–3 sentences — written so the choice can be defended aloud without re-reading the conversation>
```

Rules:

- `<n>` is the next sequential number after the highest D-number already in the file — read the file first.
- Date is today's date.
- Keep it concise: the whole entry should usually fit in 10–15 lines. The log's value depends on it staying readable; a bloated log stops being read. Long supporting analysis belongs in the conversation or a separate doc, not here.
- Optional extra blocks only when they carry real content: **Named upgrade triggers** (measured conditions that would revisit the decision) and **Known limitation** (an accepted weakness, documented rather than hidden).
- Give rejected options their honest strongest case before the rejection reason — an entry that strawmans the alternatives can't be defended later.

If `docs/decisions.md` does not exist yet, create it with this header before the first entry:

```markdown
# Decision log

Running log of design decisions. Each entry: what was decided, what was considered, why the winner won. Newest at the bottom.
```

## Flow

1. Draft the entry from the conversation.
2. Show the entry in the response (the user sees what was logged without opening the file).
3. Append it to `docs/decisions.md`.
4. Commit along with the work it belongs to (or on its own if the decision precedes implementation), following the repository's normal commit conventions.

No approval gate before appending — the decision itself was already agreed in conversation, and the log is trivially amendable.

## Manual invocation

When invoked as `/decision-logging` (optionally with a hint like `/decision-logging the reranker choice`), scan the recent conversation for confirmed decisions that pass the defensibility test and are not yet in the log, then follow the same flow. If nothing qualifies, say so rather than logging filler.
