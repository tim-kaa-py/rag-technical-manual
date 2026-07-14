# Eval report — 2026-07-14 — hybrid-small

- Embedding: `text-embedding-3-small` · Generation: `claude-sonnet-5` · Judge: `claude-opus-4-8` (prompt v1)
- Instrument notes: same-vendor limitation (Anthropic judge grading an Anthropic generator); smallest observable delta at n=11 is one question (~9 points); counts, not percentages (D17); the single trap question is a hallucination probe of n=1; the golden set is not blind (drafted knowing the M1 smoke results).
- Predicted-fail ceiling: 3 scored rows cannot pass correctness by design (D9/D19/D6) — best achievable correct = 8/11.

| id | type | expected | retrieved (rank order) | hit | RR | pages | grounded | correct | annotation |
|---|---|---|---|---|---|---|---|---|---|
| q1 | lexical | 43 | 43,20,38,29,11 | 1 | 1.00 | 1/1 | 1 | 1 |  |
| q2 | semantic | 42 | 42,44,47,44,47 | 1 | 1.00 | 1/1 | 1 | 1 | known near-duplicate: p. 47 (re-commissioning) also mentions the 50/50 ratio but does not answer the freezing-risk question — a p. 47-only retrieval is an ambiguous-source miss, not a retrieval failure |
| q3 | two-sections-one-page | 43 | 43,41,44,47,31 | 1 | 1.00 | 1/1 | 1 | 1 | two sections share the page — page-level hit cannot distinguish them (D17 known limitation) |
| q4 | cross-page | 46,47 | 47,46,47,38,46 | 1 | 1.00 | 2/2 | 1 | 1 | section 5.10 spans two pages — per-question column reports pages found x/y |
| q5 | table-displaced | 43 | 42,46,43,45,41 | 1 | 0.33 | 1/1 | 0 | 1 | the sulphur table extracts displaced to the page end — tests robustness to extraction order. CAUTION: the manual's third table row misprints '<1,0' where '>1,0' is meant (as printed it contradicts row one); golden keeps the correct engineering reading — judge results on this question must tolerate either phrasing of the >1.0% row, and a groundedness fail here may reflect the misprint, not the system |
| q6 | lexical-numeric | 33 | 33,25,13,7,22 | 1 | 1.00 | 1/1 | 1 | 1 |  |
| q7 | predicted-fail | 48 | 41,47,47,48,39 | 1 | 0.25 | 1/1 | 1 | 0 | predicted fail — D9: the p. 48 maintenance-schedule table extracts as shredded text with row-to-interval associations lost |
| q8 | predicted-fail | 49 | 35,47,31,45,8 | 0 | 0.00 | 0/1 | 1 | 0 | predicted fail — D19: the troubleshooting table is an image (this row on the p. 49 image; the table continues as images on pp. 50-51); only the 6.1 General intro text extracts |
| q9 | predicted-fail | 42 | 43,45,45,47,41 | 0 | 0.00 | 0/1 | 1 | 0 | predicted fail — D6: the answer exists only in the SAE chart image on p. 42; M5 target |
| q10 | identifier | 36 | 36,20,1,42,49 | 1 | 1.00 | 1/1 | 1 | 1 | identifier lookup — D12 sparse-wins case; baseline measured dense already at rank 1, so sparse-wins is unconfirmed at n=2 on this set (D23) |
| q11 | lexical-numeric | 30 | 30,30,13,25,45 | 1 | 1.00 | 1/1 | 1 | 1 | numeric lookup + page-spread (only scored question on p. 30); baseline measured dense already at rank 1 — no M3 headroom here (D23) |

### Judge justifications (failing rows)

- **q5/grounded**: The excerpt on p. 43 states 'If the Sulphur content exceeds 0.5%, then the engine oil must be changed more frequently' and provides a table: <0.5 NORMAL, 0.5-1.0 = 0.75, <1.0 = 0.5. The answer's first two rows and the general conclusion are supported. However, the answer reinterprets the '<1,0' row as '≥1.0%' representing higher content, which is an unsupported inference/correction; the excerpt literally shows '<1,0' and the answer adds interpretive claims not directly grounded in the text.
- **q7/correct**: The reference answer provides specific intervals (start-up, every 200 hours, and at least once a year), but the answer to grade refuses to provide this information, claiming the interval values are not available. This is a refusal when the reference contains a real answer, which is a fail.
- **q8/correct**: The reference answer contains a detailed list of possible causes for slow cranking and no-start, indicating this information exists. The graded answer refuses to provide any causes, claiming the manual lacks this information. This is a refusal when a real answer exists, which is a fail.
- **q9/correct**: The reference provides a specific answer (SAE 5W/30 for -30°C), indicating the information exists. The answer to grade refuses by claiming the manual lacks this information, which contradicts the reference. A refusal when the reference contains a real answer is a fail.

**Trap (q12)**: refused = yes — excluded from retrieval metrics (D17). trap — no torque specification anywhere in the corpus: text grep finds 'torque' only in the p. 9 towing-trailer section (no value), and all 60 pages were visually verified free of torque values (independent reviewer pass); expected behavior: explicit refusal (D15)

**Aggregates (n=11 answerable):** hit@5 = 9/11 · MRR@5 = 0.69 · grounded = 10/11 · correct = 8/11

Quadrant reading: grounded∧¬correct → retrieval-or-corpus failure (the row's annotation decides which); ¬grounded∧correct → parametric-knowledge answer (D15's target).
