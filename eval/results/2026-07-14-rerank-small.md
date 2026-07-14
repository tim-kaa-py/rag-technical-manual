# Eval report — 2026-07-14 — rerank-small

- Embedding: `text-embedding-3-small` · Generation: `claude-sonnet-5` · Judge: `claude-opus-4-8` (prompt v1)
- Instrument notes: same-vendor limitation (Anthropic judge grading an Anthropic generator); smallest observable delta at n=11 is one question (~9 points); counts, not percentages (D17); the single trap question is a hallucination probe of n=1; the golden set is not blind (drafted knowing the M1 smoke results).
- Predicted-fail ceiling: 3 scored rows cannot pass correctness by design (D9/D19/D6) — best achievable correct = 8/11.
- Reranker: `claude-haiku-4-5`. Fallbacks: 1/12 rows kept RRF order (q12) — these rows contribute zero rerank delta by construction; the delta over non-fallback rows is the honest readout.

| id | type | expected | retrieved (rank order) | hit | RR | pages | grounded | correct | annotation |
|---|---|---|---|---|---|---|---|---|---|
| q1 | lexical | 43 | 43,38,11,28,20 | 1 | 1.00 | 1/1 | 1 | 1 |  |
| q2 | semantic | 42 | 42,47,44,44,47 | 1 | 1.00 | 1/1 | 1 | 1 | known near-duplicate: p. 47 (re-commissioning) also mentions the 50/50 ratio but does not answer the freezing-risk question — a p. 47-only retrieval is an ambiguous-source miss, not a retrieval failure |
| q3 | two-sections-one-page | 43 | 43,44,47,48,41 | 1 | 1.00 | 1/1 | 1 | 1 | two sections share the page — page-level hit cannot distinguish them (D17 known limitation) |
| q4 | cross-page | 46,47 | 47,46,47,46,38 | 1 | 1.00 | 2/2 | 1 | 1 | section 5.10 spans two pages — per-question column reports pages found x/y |
| q5 | table-displaced | 43 | 43,46,47,42,48 | 1 | 1.00 | 1/1 | 1 | 1 | the sulphur table extracts displaced to the page end — tests robustness to extraction order. CAUTION: the manual's third table row misprints '<1,0' where '>1,0' is meant (as printed it contradicts row one); golden keeps the correct engineering reading — judge results on this question must tolerate either phrasing of the >1.0% row, and a groundedness fail here may reflect the misprint, not the system |
| q6 | lexical-numeric | 33 | 33,13,30,38,11 | 1 | 1.00 | 1/1 | 1 | 1 |  |
| q7 | predicted-fail | 48 | 48,48,47,46,41 | 1 | 1.00 | 1/1 | 0 | 0 | predicted fail — D9: the p. 48 maintenance-schedule table extracts as shredded text with row-to-interval associations lost |
| q8 | predicted-fail | 49 | 31,46,47,47,39 | 0 | 0.00 | 0/1 | 1 | 0 | predicted fail — D19: the troubleshooting table is an image (this row on the p. 49 image; the table continues as images on pp. 50-51); only the 6.1 General intro text extracts |
| q9 | predicted-fail | 42 | 42,37,46,43,45 | 1 | 1.00 | 1/1 | 1 | 0 | predicted fail — D6: the answer exists only in the SAE chart image on p. 42; M5 target |
| q10 | identifier | 36 | 36,34,39,42,43 | 1 | 1.00 | 1/1 | 1 | 1 | identifier lookup — D12 sparse-wins case; baseline measured dense already at rank 1, so sparse-wins is unconfirmed at n=2 on this set (D23) |
| q11 | lexical-numeric | 30 | 30,30,13,38,25 | 1 | 1.00 | 1/1 | 1 | 1 | numeric lookup + page-spread (only scored question on p. 30); baseline measured dense already at rank 1 — no M3 headroom here (D23) |

### Judge justifications (failing rows)

- **q7/grounded**: The excerpt on p. 48 lists 'Check the Tensions of V-belts' as a maintenance item and mentions various intervals including 200 hours. However, the OCR-garbled table format does not clearly associate the V-belt tension check with the 200-hour interval specifically—the mapping between individual tasks and intervals is not recoverable from the provided text. The answer's specific claim that it falls under the 200-hour interval cannot be verified from the excerpts.
- **q7/correct**: The reference answer specifies three intervals: at start-up, every 200 hours, and at least once every year. The answer to grade only mentions the 200-hour interval, missing the core facts about start-up and yearly checks. This constitutes missing core facts.
- **q8/correct**: The reference answer contains a detailed list of possible causes for the engine cranking slowly and not starting. The answer to grade refuses to provide this information, claiming the manual does not cover it. A refusal when the reference contains a real answer is a fail.
- **q9/correct**: The reference provides a specific answer (SAE 5W/30) based on a lubricant chart. The answer to grade refuses to provide this information, claiming the manual defers to the engine manufacturer's manual. A refusal when the reference contains a real answer is a fail.

**Trap (q12)**: refused = yes — excluded from retrieval metrics (D17). trap — no torque specification anywhere in the corpus: text grep finds 'torque' only in the p. 9 towing-trailer section (no value), and all 60 pages were visually verified free of torque values (independent reviewer pass); expected behavior: explicit refusal (D15)

**Aggregates (n=11 answerable):** hit@5 = 10/11 · MRR@5 = 0.91 · grounded = 10/11 · correct = 8/11

Quadrant reading: grounded∧¬correct → retrieval-or-corpus failure (the row's annotation decides which); ¬grounded∧correct → parametric-knowledge answer (D15's target).

## M3 vs baseline (dense → hybrid → rerank)

Attributable readout: hit/MRR only (D17). Candidate identity between the hybrid
and rerank runs verified: **12/12 rows identical** — the rerank delta is
attributable by measurement, not assumption (and doubly so via the within-run
control: each row's `candidates[:5]` IS that run's hybrid top-5).

| config | hit@5 | MRR@5 | grounded | correct |
|---|---|---|---|---|
| dense-small (blessed baseline) | 10/11 | 0.79 | 11/11 | 8/11 |
| hybrid-small (dense+BM25, RRF) | 9/11 | 0.69 | 10/11 | 8/11 |
| rerank-small (fused + Haiku listwise) | 10/11 | **0.91** | 10/11 | 8/11 |

### dense → hybrid: fusion alone HURT (−1 hit, −0.10 MRR)

- q5 `0.20 → 0.33` — the predicted BM25 sulphur win, held but small.
- q7 `0.50 → 0.25`, q9 `1.00 → MISS` — **hybrid dilution**: for q9 the dense arm
  had p. 42 at rank 1, but the sparse arm (matching only surface words like
  "oil"/"temperature" in an oil-saturated corpus — "SAE" appears in no text,
  per the corpus grep at golden-set creation) voted for other pages; RRF's doubly-retrieved-wins property demoted the
  dense singleton truth to fused rank 6. Not zero-score padding (all sparse
  scores > 0; the pre-registered filter trigger did not fire) — the sparse arm
  was *confidently mediocre*, and RRF weighs both arms equally.
- TOC-magnet: BM25 did NOT love the TOC — fusion diluted it (top-5 rows with
  p. 5: dense 4/12 → hybrid 1/12).

### hybrid → rerank: the reranker repaired everything fusion broke (+1 hit, +0.22 MRR)

- q5 `0.33 → 1.00`, q7 `0.25 → 1.00`, q9 `MISS → 1.00` — p. 42 rescued from
  fused rank 6 to rank 1. Each expected page the reranker restored to rank 1
  sat lower in the fused list than in its stronger arm (q5 p. 43: sparse 1 →
  fused 3; q7 p. 48: dense 2 → fused 4; q9 p. 42: dense 1 → fused 6); the
  reranker read the candidates against the question ("actually answers this")
  where both retrieval arms could only score surface similarity.
- Fallbacks: **0 of 11 scored rows** (the single fallback was the trap q12 —
  Haiku's response failed the strict parse; the run-time console showed an
  empty `ranking` list. The raw response is not persisted and the fallback
  flag does not distinguish parse from API failure — follow-up: log a
  `rerank_fallback_reason` in the eval row. RRF order kept, trap still
  refused.)
- TOC acceptance (pre-committed): rerank top-5 TOC count 1/12 ≤ dense's 4/12. ✓

### Net M3 vs the blessed baseline

hit@5 10/11 (unchanged, as pre-committed — q8 has no text to retrieve until
M5) · **MRR@5 0.79 → 0.91 (+0.12, above the ~0.09 one-question resolution;
exactly the D23 pre-committed ceiling)** · grounded/correct not attributable
to retrieval config (below).

### D23 predictions checked

- "MRR headroom on q5/q7" — **held** (both at 1.00 under rerank; ceiling
  reached). (D23 listed q3 as well; the blessed baseline already had q3 at
  1.00 after the D21 re-baseline, so live headroom was q5/q7 only.)
- "q10/q11 saturated, no delta" — **held** (1.00 everywhere).
- "hit@5 immovable" — held end-to-end (10/11 → 10/11), though hybrid-alone
  dipped to 9/11 in between — fusion can *break* hit@5 even when it can't
  improve it; not predicted, now measured.
- "TOC demotion" — held, but fusion (not the reranker) did the demoting.
- D16 swap predicate — did not fire on any clause (hits 10>9, MRR 0.91>0.69,
  q5+q7 both improved). No Sonnet swap, no anchoring diagnostic needed.

### Judge-axis notes (not attributable to config; D17)

Verdicts that changed vs baseline were re-judged 3× fresh (pre-registered
spot-check); both confirmed unanimous — real behavior changes downstream of
ranking, not judge noise:

- hybrid q5/grounded fail (3/3): the **pre-declared misprint annotation
  firing** — the generator gave the corrected ">1.0%" reading; the judge
  correctly held it against the literal "<1,0" context. (The baseline's q5
  answer made the same correction *silently* and passed the same rubric —
  the fail keys on the answer's explicit reinterpretation commentary, per the
  misprint annotation; grounded 11/11 → 10/11 is a rubric edge on a
  pre-declared quirk, not a hallucination.)
- rerank q7/grounded fail (3/3): p. 48 at rank 1 made Sonnet attempt a partial
  answer ("200 hours" only) from the shredded table instead of refusing — the
  same rank-vs-extractability interaction the M2 A/B caught on dense-large.
  Better retrieval of unextractable content trades a clean refusal for a
  partial ungrounded answer; the D9/M5 fix (captioning) resolves the
  underlying cause.

grounded/correct judged single-run under the D17 calibration (performed on
baseline outputs; treated as an instrument property, not re-verified on M3
outputs beyond the changed-verdict spot-checks above).
