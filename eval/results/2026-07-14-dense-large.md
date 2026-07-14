# Eval report — 2026-07-14 — dense-large

- Embedding: `text-embedding-3-large` · Generation: `claude-sonnet-5` · Judge: `claude-opus-4-8` (prompt v1)
- Instrument notes: same-vendor limitation (Anthropic judge grading an Anthropic generator); smallest observable delta at n=11 is one question (~9 points); counts, not percentages (D17); the single trap question is a hallucination probe of n=1; the golden set is not blind (drafted knowing the M1 smoke results).
- Predicted-fail ceiling: 3 scored rows cannot pass correctness by design (D9/D19/D6) — best achievable correct = 8/11.

| id | type | expected | retrieved (rank order) | hit | RR | pages | grounded | correct | annotation |
|---|---|---|---|---|---|---|---|---|---|
| q1 | lexical | 43 | 43,29,12,12,11 | 1 | 1.00 | 1/1 | 1 | 1 |  |
| q2 | semantic | 42 | 42,44,44,47,37 | 1 | 1.00 | 1/1 | 1 | 1 | known near-duplicate: p. 47 (re-commissioning) also mentions the 50/50 ratio but does not answer the freezing-risk question — a p. 47-only retrieval is an ambiguous-source miss, not a retrieval failure |
| q3 | two-sections-one-page | 43 | 43,44,41,31,48 | 1 | 1.00 | 1/1 | 1 | 1 | two sections share the page — page-level hit cannot distinguish them (D17 known limitation) |
| q4 | cross-page | 46,47 | 47,47,46,46,37 | 1 | 1.00 | 2/2 | 1 | 1 | section 5.10 spans two pages — per-question column reports pages found x/y |
| q5 | table-displaced | 43 | 45,42,46,43,48 | 1 | 0.25 | 1/1 | 1 | 1 | the sulphur table extracts displaced to the page end — tests robustness to extraction order. CAUTION: the manual's third table row misprints '<1,0' where '>1,0' is meant (as printed it contradicts row one); golden keeps the correct engineering reading — judge results on this question must tolerate either phrasing of the >1.0% row, and a groundedness fail here may reflect the misprint, not the system |
| q6 | lexical-numeric | 33 | 33,13,31,30,38 | 1 | 1.00 | 1/1 | 1 | 1 |  |
| q7 | predicted-fail | 48 | 48,41,48,41,42 | 1 | 1.00 | 1/1 | 0 | 0 | predicted fail — D9: the p. 48 maintenance-schedule table extracts as shredded text with row-to-interval associations lost |
| q8 | predicted-fail | 49 | 31,46,45,40,47 | 0 | 0.00 | 0/1 | 1 | 0 | predicted fail — D19: the troubleshooting table is an image (this row on the p. 49 image; the table continues as images on pp. 50-51); only the 6.1 General intro text extracts |
| q9 | predicted-fail | 42 | 42,43,47,46,47 | 1 | 1.00 | 1/1 | 1 | 0 | predicted fail — D6: the answer exists only in the SAE chart image on p. 42; M5 target |
| q10 | identifier | 36 | 36,20,15,4,18 | 1 | 1.00 | 1/1 | 1 | 1 | identifier lookup — D12 sparse-wins case; baseline measured dense already at rank 1, so sparse-wins is unconfirmed at n=2 on this set (D23) |
| q11 | lexical-numeric | 30 | 30,45,30,13,38 | 1 | 1.00 | 1/1 | 1 | 1 | numeric lookup + page-spread (only scored question on p. 30); baseline measured dense already at rank 1 — no M3 headroom here (D23) |

### Judge justifications (failing rows)

- **q7/grounded**: The excerpts from p. 48 list 'Check the Tensions of V-belts' as a maintenance item and mention various intervals (200 hours, 400 hours, etc.), but the OCR-garbled schedule does not clearly associate the V-belt tension check with the 200-hour interval specifically. There is no explicit support in the excerpts linking the V-belt tension check to a 200-hour interval. Therefore the specific claim of 'every 200 hours' is not grounded.
- **q7/correct**: The reference states the V-belt tension must be checked at three intervals: at start-up, every 200 hours of engine running, and at least once every year. The answer only mentions 'every 200 hours' and omits the core facts about checking at start-up and once every year. Missing core facts constitutes a failure.
- **q8/correct**: The reference answer contains a detailed list of possible causes for slow cranking and failure to start (de-charged batteries, defective starter, unsuitable oil, no fuel, air in fuel system, etc.). The answer to grade refuses to provide this information, claiming the manual does not contain it. This is a refusal when the reference contains a real answer, which is a fail.
- **q9/correct**: The reference answer provides a specific factual answer (SAE 5W/30 for -30°C), while the answer to grade refuses to provide this information, claiming the manual does not contain it. A refusal when the reference contains a real answer is a fail per the grading rules.

**Trap (q12)**: refused = yes — excluded from retrieval metrics (D17). trap — no torque specification anywhere in the corpus: text grep finds 'torque' only in the p. 9 towing-trailer section (no value), and all 60 pages were visually verified free of torque values (independent reviewer pass); expected behavior: explicit refusal (D15)

**Aggregates (n=11 answerable):** hit@5 = 10/11 · MRR@5 = 0.84 · grounded = 10/11 · correct = 8/11

Quadrant reading: grounded∧¬correct → retrieval-or-corpus failure (the row's annotation decides which); ¬grounded∧correct → parametric-knowledge answer (D15's target).

## A/B small vs large (D3)

| id | hit dense-small | hit dense-large | RR dense-small | RR dense-large | same top-5? |
|---|---|---|---|---|---|
| q1 | 1 | 1 | 1.00 | 1.00 |  |
| q2 | 1 | 1 | 1.00 | 1.00 |  |
| q3 | 1 | 1 | 1.00 | 1.00 |  |
| q4 | 1 | 1 | 1.00 | 1.00 |  |
| q5 | 1 | 1 | 0.20 | 0.25 |  |
| q6 | 1 | 1 | 1.00 | 1.00 |  |
| q7 | 1 | 1 | 0.50 | 1.00 |  |
| q8 | 0 | 0 | 0.00 | 0.00 |  |
| q9 | 1 | 1 | 1.00 | 1.00 |  |
| q10 | 1 | 1 | 1.00 | 1.00 |  |
| q11 | 1 | 1 | 1.00 | 1.00 |  |

- dense-small: hit 10/11 · MRR 0.79 · grounded 11/11 · correct 8/11
- dense-large: hit 10/11 · MRR 0.84 · grounded 10/11 · correct 8/11

**Verdict (hit/MRR only — the attributable readout):** no measurable difference.
hit@5 is identical; the MRR delta (+0.05, from q7 rank 2→1 and q5 rank 5→4) is
smaller than one question's worth (~0.09 at n=11), i.e. below the instrument's
resolution. Per the pre-committed reading: **small suffices** — the D3 default
stands, and the A/B cost the corpus nothing to keep honest.

**Not attributable to the tier:** the grounded 11/11 vs 10/11 difference is a
generation-behavior artifact, not embedding quality — large ranked the
shredded p. 48 schedule at 1 for q7, and Sonnet attempted a partial answer
("every 200 hours") instead of refusing; the judge correctly failed it on both
axes (ungrounded per the excerpts, incomplete per the reference). Better rank
on an unextractable table produced worse behavior — a D9 artifact interacting
with rank order, and independent evidence that the groundedness judge catches
exactly what it was built to catch. No row had an identical top-5, so this run
pair provides no free judge-noise estimate (calibration already measured that
directly: 0/23).
