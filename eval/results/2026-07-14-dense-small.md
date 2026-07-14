# Eval report — 2026-07-14 — dense-small

- Embedding: `text-embedding-3-small` · Generation: `claude-sonnet-5` · Judge: `claude-opus-4-8` (prompt v1)
- Instrument notes: same-vendor limitation (Anthropic judge grading an Anthropic generator); smallest observable delta at n=11 is one question (~9 points); counts, not percentages (D17); the single trap question is a hallucination probe of n=1; the golden set is not blind (drafted knowing the M1 smoke results).
- Predicted-fail ceiling: 3 scored rows cannot pass correctness by design (D9/D19/D6) — best achievable correct = 8/11.
- Judge calibration (D17, one-time): 0 flipping axes out of 23 — every axis judged 4× (logged + 3 fresh, 92 verdicts, all unanimous). Standing protocol: single-run judging. Calibrated on the pre-D21 run of this same instrument (identical judge model + prompt v1); the D21/D22 re-baseline changed the corpus vectors, not the judge.
- Pre-committed headroom (D23): M3's measurable target is ranking depth on q5/q7 (MRR ceiling 0.91) and demoting the TOC-magnet chunk (p. 5); hit@5 is immovable before M5 (q8 has no text to retrieve). M5 expectations: q8 → hit + correctness; q9 → correctness only (retrieval already saturated).

| id | type | expected | retrieved (rank order) | hit | RR | pages | grounded | correct | annotation |
|---|---|---|---|---|---|---|---|---|---|
| q1 | lexical | 43 | 43,29,11,12,20 | 1 | 1.00 | 1/1 | 1 | 1 |  |
| q2 | semantic | 42 | 42,44,44,47,47 | 1 | 1.00 | 1/1 | 1 | 1 | known near-duplicate: p. 47 (re-commissioning) also mentions the 50/50 ratio but does not answer the freezing-risk question — a p. 47-only retrieval is an ambiguous-source miss, not a retrieval failure |
| q3 | two-sections-one-page | 43 | 43,41,44,31,5 | 1 | 1.00 | 1/1 | 1 | 1 | two sections share the page — page-level hit cannot distinguish them (D17 known limitation) |
| q4 | cross-page | 46,47 | 47,46,47,46,11 | 1 | 1.00 | 2/2 | 1 | 1 | section 5.10 spans two pages — per-question column reports pages found x/y |
| q5 | table-displaced | 43 | 45,42,46,48,43 | 1 | 0.20 | 1/1 | 1 | 1 | the sulphur table extracts displaced to the page end — tests robustness to extraction order. CAUTION: the manual's third table row misprints '<1,0' where '>1,0' is meant (as printed it contradicts row one); golden keeps the correct engineering reading — judge results on this question must tolerate either phrasing of the >1.0% row, and a groundedness fail here may reflect the misprint, not the system |
| q6 | lexical-numeric | 33 | 33,13,25,38,30 | 1 | 1.00 | 1/1 | 1 | 1 |  |
| q7 | predicted-fail | 48 | 41,48,41,48,5 | 1 | 0.50 | 1/1 | 1 | 0 | predicted fail — D9: the p. 48 maintenance-schedule table extracts as shredded text with row-to-interval associations lost |
| q8 | predicted-fail | 49 | 45,46,47,5,45 | 0 | 0.00 | 0/1 | 1 | 0 | predicted fail — D19: the troubleshooting table is an image (this row on the p. 49 image; the table continues as images on pp. 50-51); only the 6.1 General intro text extracts |
| q9 | predicted-fail | 42 | 42,43,45,46,20 | 1 | 1.00 | 1/1 | 1 | 0 | predicted fail — D6: the answer exists only in the SAE chart image on p. 42; M5 target |
| q10 | identifier | 36 | 36,1,20,15,3 | 1 | 1.00 | 1/1 | 1 | 1 | identifier lookup — D12 sparse-wins case; baseline measured dense already at rank 1, so sparse-wins is unconfirmed at n=2 on this set (D23) |
| q11 | lexical-numeric | 30 | 30,30,45,25,38 | 1 | 1.00 | 1/1 | 1 | 1 | numeric lookup + page-spread (only scored question on p. 30); baseline measured dense already at rank 1 — no M3 headroom here (D23) |

### Judge justifications (failing rows)

- **q7/correct**: The reference answer specifies that V-belt tension should be checked at start-up, every 200 hours, and at least once a year. The answer to grade refuses to provide this information, claiming the interval is not specified in the excerpts. A refusal when the reference contains a real answer is a fail.
- **q8/correct**: The reference answer provides a detailed list of possible causes for the slow-cranking, non-starting engine. The answer to grade refuses to provide any of these causes, claiming the information is not in the provided excerpts. A refusal when the reference contains a real answer is a fail.
- **q9/correct**: The reference provides a specific answer (SAE 5W/30) for the -30°C ambient temperature. The answer to grade refuses to provide this information, claiming the manual lacks such a chart. This is a refusal when the reference contains a real answer, which is a fail.

**Trap (q12)**: refused = yes — excluded from retrieval metrics (D17). trap — no torque specification anywhere in the corpus: text grep finds 'torque' only in the p. 9 towing-trailer section (no value), and all 60 pages were visually verified free of torque values (independent reviewer pass); expected behavior: explicit refusal (D15)

**Aggregates (n=11 answerable):** hit@5 = 10/11 · MRR@5 = 0.79 · grounded = 11/11 · correct = 8/11

Quadrant reading: grounded∧¬correct → retrieval-or-corpus failure (the row's annotation decides which); ¬grounded∧correct → parametric-knowledge answer (D15's target).
