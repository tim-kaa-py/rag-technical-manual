# Eval report — 2026-07-17 — rerank-small-mm

- Embedding: `text-embedding-3-small` · Generation: `claude-sonnet-5` · Judge: `claude-opus-4-8` (prompt v1)
- Instrument notes: same-vendor limitation (Anthropic judge grading an Anthropic generator); smallest observable delta at n=11 is one question (~9 points); counts, not percentages (D17); the single trap question is a hallucination probe of n=1; the golden set is not blind (drafted knowing the M1 smoke results).
- Predicted-fail ceiling: 0 scored rows cannot pass correctness by design (D9/D19/D6) — best achievable correct = 11/11.
- Reranker: `claude-haiku-4-5`. No fallbacks — all 12 rankings parsed.

| id | type | expected | retrieved (rank order) | hit | RR | pages | grounded | correct | annotation |
|---|---|---|---|---|---|---|---|---|---|
| q1 | lexical | 43 | 43,11,20,28,38 | 1 | 1.00 | 1/1 | 1 | 1 |  |
| q2 | semantic | 42 | 42,47,44,44,47 | 1 | 1.00 | 1/1 | 1 | 1 | known near-duplicate: p. 47 (re-commissioning) also mentions the 50/50 ratio but does not answer the freezing-risk question — a p. 47-only retrieval is an ambiguous-source miss, not a retrieval failure |
| q3 | two-sections-one-page | 43 | 43,48,44,41,31 | 1 | 1.00 | 1/1 | 1 | 1 | two sections share the page — page-level hit cannot distinguish them (D17 known limitation) |
| q4 | cross-page | 46,47 | 47,46,47,46,48 | 1 | 1.00 | 2/2 | 1 | 1 | section 5.10 spans two pages — per-question column reports pages found x/y |
| q5 | table-displaced | 43 | 43,48,46,42,45 | 1 | 1.00 | 1/1 | 1 | 1 | the sulphur table extracts displaced to the page end — tests robustness to extraction order. CAUTION: the manual's third table row misprints '<1,0' where '>1,0' is meant (as printed it contradicts row one); golden keeps the correct engineering reading — judge results on this question must tolerate either phrasing of the >1.0% row, and a groundedness fail here may reflect the misprint, not the system |
| q6 | lexical-numeric | 33 | 33,13,30,38,11 | 1 | 1.00 | 1/1 | 1 | 1 |  |
| q7 | predicted-fail | 48 | 48,47,47,39,41 | 1 | 1.00 | 1/1 | 1 | 1 | pre-M5 predicted-fail (D9: the p. 48 schedule table extracts shredded, task-to-interval associations lost); M5 replaced the p. 48 text with a vision caption (D25) — pre-committed: hit is a genuine prediction (the old hit rode the deleted shredded chunks), grounded + correct expected |
| q8 | predicted-fail | 49 | 49,50,46,51,47 | 1 | 1.00 | 1/1 | 1 | 1 | pre-M5 predicted-fail (D19: troubleshooting table image-only; this row on the p. 49 image, table continues on pp. 50-51); M5 captions pp. 49-51 (D25) — pre-committed (D23): hit + correct expected; hit must be verified by caption node identity, not page |
| q9 | predicted-fail | 42 | 42,42,45,46,50 | 1 | 1.00 | 1/1 | 1 | 1 | pre-M5 predicted-fail (D6: answer only in the SAE chart image on p. 42); M5 captions the chart (D25) — pre-committed (D23): correct expected; retrieval already saturated (p. 42 at rank 1) |
| q10 | identifier | 36 | 36,34,15,20,49 | 1 | 1.00 | 1/1 | 1 | 1 | identifier lookup — D12 sparse-wins case; baseline measured dense already at rank 1, so sparse-wins is unconfirmed at n=2 on this set (D23) |
| q11 | lexical-numeric | 30 | 30,30,13,45,25 | 1 | 1.00 | 1/1 | 1 | 1 | numeric lookup + page-spread (only scored question on p. 30); baseline measured dense already at rank 1 — no M3 headroom here (D23) |

**Trap (q12)**: refused = yes — excluded from retrieval metrics (D17). trap — no torque specification anywhere in the corpus: text grep finds 'torque' only in the p. 9 towing-trailer section (no value), and all 60 pages were visually verified free of torque values (independent reviewer pass); expected behavior: explicit refusal (D15)

**Aggregates (n=11 answerable):** hit@5 = 11/11 · MRR@5 = 1.00 · grounded = 11/11 · correct = 11/11

Quadrant reading: grounded∧¬correct → retrieval-or-corpus failure (the row's annotation decides which); ¬grounded∧correct → parametric-knowledge answer (D15's target).

## M5 vs M3 (text-only → multimodal): the corpus change was the treatment

Same retrieval config (hybrid + Haiku listwise rerank, small embeddings) on a
changed corpus: 74 text chunks → 77 rows (2 shredded p. 48 chunks replaced,
5 vision-caption nodes added — D25/D26). For q7/q8/q9 the corpus change IS
the treatment, so their correctness flips are the measured M5 effect — the
usual "grounded/correct deltas are confounded" caveat applies to the *other*
rows only.

| config | hit@5 | MRR@5 | grounded | correct |
|---|---|---|---|---|
| rerank-small (blessed M3, text-only) | 10/11 | 0.91 | 10/11 | 8/11 |
| rerank-small-mm (M5, captions) | **11/11** | **1.00** | **11/11** | **11/11** |

Every remaining failure of the text-only system was a corpus gap, not a
pipeline gap — and captioning closed all of them. All four axes are now at
ceiling (hit@5, MRR@5, grounded, correct — and the hallucination probe is
n=1): the golden set can no longer distinguish further improvements (D17's
~9-points-per-question resolution). The saturation is one-sided — the set
remains a valid *regression* detector, which is its only remaining job.

### Pre-committed expectations (D23/D25, frozen before this run) — all held

- **q8 hit + correct** — held. The sole retrieval miss became rank 1, and by
  **node identity**: the fused rank-1 candidate is the p. 49 caption node
  (uuid5-verified in the logged candidates), not the coexisting 6.1-General
  prose chunk — the pre-registered spurious-page check passes. The p. 50/51
  captions follow at fused ranks 2–3 (the table's continuation pages), so the
  answer context contains the whole troubleshooting table.
- **q7 hit as a genuine prediction + grounded + correct** — held. The old hit
  rode the two deleted shredded chunks; the new rank-1 is the p. 48 caption
  node (identity-verified). The M3 grounded-fail (partial "200 hours only"
  answer lured from shredded text) became a grounded, complete
  start-up/200-hours/every-year answer — the D25 replacement argument
  measured out.
- **q9 correct** (retrieval already saturated) — held, with a bonus: the
  fused rank-1 is now the p. 42 **caption** node (the old rank-1 was the
  p. 42 text chunk whose chart content was invisible). Generation now sees
  the SAE ranges and answers 5W/30.
- **No regressions on q1–q6/q10/q11** — held: all RR 1.00, all grounded and
  correct. The +5 caption nodes reshuffled some top-5 *tails* (annotated
  "same top-5?" = no on most rows) without touching any expected page's
  rank-1. q2/q6 kept byte-identical top-5s and identical verdicts —
  consistent with zero verdict noise (n=2 cannot demonstrate zero).
- **Trap q12 still refuses** — held (and this run had zero rerank fallbacks;
  the M3 trap-row fallback did not recur).

### Changed judge verdicts: re-judged 3×, all unanimous

Per the pre-registered M3 protocol, the four verdicts that changed vs the
blessed record (q7/grounded, q7/correct, q8/correct, q9/correct) were each
re-judged 3× fresh against the logged artifacts: 4/4 unanimous with the
logged verdict — real behavior changes downstream of the corpus change, not
judge noise.

As in the M3 record: grounded/correct reflect **one generation sample** per
question. The 3× re-judge bounds judge noise on the logged answers; it does
not measure generation-to-generation variance — a perfect score needs this
line more than any other score does.

### Instrument disclosures for this run

- **The caption is the new grounding root** (D26 known limitation): the
  groundedness judge verifies answer-vs-caption, never caption-vs-image.
  Caption fidelity was secured by a manual pre-measurement audit of all five
  captions against their images. The audit found **2 cell-level errors** in
  the 33-row p. 48 transcription (two tasks with a mark in the
  First-Maintenance column mis-attributed to Start-up); both were corrected
  against the image and the corrected caption re-indexed **before** this run.
  The shipped captions are therefore human-edited vision output — caption
  fidelity is a human-in-the-loop property, audited in a single pass that
  itself found a ~2/33 cell error rate in raw vision output; non-golden
  caption rows are audited once and never re-checked by the harness.
- **Audit circularity, stated plainly:** the pre-measurement audit verified
  the q7/q8/q9-critical caption content against the golden answers (the
  V-belt intervals, the slow-crank cause list, the SAE bounds). The
  correctness flips therefore measure the end-to-end multimodal path —
  retrieval → generation → judging over pre-verified captions — not
  unaudited vision-caption fidelity. Legitimate for a before/after
  demonstration ("the mechanism works"); it must not be read as "captions
  are generally accurate."
- The header's "Predicted-fail ceiling: 0 rows … (D9/D19/D6)" line is now
  vestigial wording: those annotations were amended (D25) because M5 resolved
  the gaps the citation refers to; best-achievable correct is genuinely 11/11.
- The `large` embedding table remains text-only (D25 known limitation): a
  future `--embed large` run would compare across different corpora.
- One prior invocation of this run failed on a network timeout (q12
  generation) **before any results were written** — no results existed to
  discard; the completed run is the only artifact.
