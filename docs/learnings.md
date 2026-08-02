# What building this taught me

The build story behind the [results table](../README.md#results): four configurations, one frozen exam, and a retrieval score that went **0.79 → 0.69 → 0.91 → 1.00** — with the dip and the last jump being the two most instructive parts. Everything below is reconstructable from the committed artifacts: the [decision log](decisions.md), the [eval reports](../eval/results/), and the [methodology doc](documentation/eval.md).

## 1. The system in one paragraph

A ~60-page diesel-generator service manual is parsed, chunked (512 tokens, sentence-aware, section-tagged), embedded, and stored in pgvector. A query runs dense retrieval and in-memory BM25 in parallel, fuses both by Reciprocal Rank Fusion, has a single Haiku call rerank the 10 fused candidates listwise, and hands the top 5 to Sonnet with a hard rule: answer only from this context, cite pages, refuse explicitly if the answer isn't there. A FastAPI endpoint serves it; an LLM-as-judge harness measures it. The governing rule of the build ([requirements.md §1](requirements.md)): **no quality claim without a measurement.**

## 2. Freeze the exam before you sit it

The golden set — 11 answerable questions plus one trap — was written and locked in git **before the first eval ran** (D17). Three questions were *pre-registered as fails*: their answers live in a shredded schedule table and in images that text extraction cannot see (D9, D19). The trap question asks for a cylinder-head bolt torque that provably appears nowhere in the corpus — so hallucination isn't a fear, it's a measured row ("refused: yes/no", D15).

Honesty requires the converse disclosure too: the set is frozen-before-results but **not blind** — it was drafted knowing how the pipeline behaved in early smoke tests. Every report header says so. Small-n eval design is mostly about knowing, and stating, which accusations you can and cannot rule out.

## 3. Baseline first: dense-only, 0.79 — and deliberately no ANN index

The first measured config was the simplest one that could work: dense cosine retrieval, exact scan, top-5. At ~75 vectors an HNSW index solves a problem that doesn't exist and adds approximate recall as a confound *inside the eval* (D11). The baseline scored hit@5 10/11, MRR 0.79, and — the important part — it turned every later change into a delta against a number instead of an impression.

## 4. Hybrid retrieval made it worse: 0.69

Adding BM25 + RRF — the fashionable move — **degraded** retrieval: one lost hit, −0.10 MRR. The [M3 report](../eval/results/2026-07-14-rerank-small.md) contains the full post-mortem, and the mechanism generalizes:

The SAE-grade question had its answer page at dense rank 1. But "SAE" appeared in *no extracted text* (the chart is an image), so the sparse arm could only match surface words — "oil", "temperature" — in an oil-saturated corpus. The sparse votes were *confidently mediocre*, all positive scores, no signal. RRF weighs both arms equally and rewards documents retrieved by both — so the dense arm's singleton truth fell from rank 1 to fused rank 6.

The lesson isn't "hybrid is bad." It's that **fusion redistributes trust between arms, and an arm with no real signal still votes.** If I had shipped hybrid without measuring the intermediate step, the regression would have been invisible inside the combined "hybrid+rerank is better" result.

## 5. Reranking repaired everything fusion broke: 0.91

One listwise Haiku call — all 10 candidates, return the top 5 as JSON — restored every page fusion had demoted, back to rank 1. The mechanism is the textbook one, observed live: bi-encoders score query and chunk *independently* ("same topic"); a reranker reads them *together* ("actually answers this"). Every page the reranker rescued had sat lower in the fused list than in its stronger arm.

Design corollary that mattered in serving: the reranker is the one stage allowed to fail gracefully (parse failure → fall back to RRF order, flag it in the API response as `rerank_degraded`), while generation is *not* allowed to degrade — no answer beats a wrong answer (D14 vs D15). Deciding per-stage which failure mode is acceptable was more valuable than any single component choice.

## 6. The last three failures weren't in the pipeline

At 0.91, the three remaining incorrect answers were all pre-registered corpus gaps: the answers existed only in a chart image, an icon-matrix table, and troubleshooting-table images. No retrieval or prompting change could fix them — **the information was not in the index in any form.**

The fix was to change the corpus: caption the five image-bound pages with a vision model, index the captions as first-class chunks, and *delete* the shredded text they replace (measured earlier as actively harmful — it had lured the generator into a partial, ungrounded answer). Result: 11/11 hit, MRR 1.00, 11/11 grounded, 11/11 correct, trap still refused ([M5 report](../eval/results/2026-07-17-rerank-small-mm.md)).

The takeaway I'd carry to any RAG project: **diagnose whether a failure is a pipeline failure or a corpus failure before optimizing the pipeline.** The judge's two axes made that diagnosis mechanical — grounded-but-wrong means retrieval/corpus, ungrounded-but-right means the model answered from its own knowledge.

## 7. How the numbers were kept honest

- **Pre-committed expectations.** Before each measurement, the expected per-question deltas were written into the decision log (D23, D25) — including where improvement was *impossible* ("retrieval already saturated"). In D23's words: so that "a small delta reads as instrument saturation, not failed work — and a large delta can't be retro-fitted a story."
- **The judge was calibrated, then trusted.** Every verdict re-judged 3× against the logged artifacts: 0 flips in 92 verdicts → single-run judging, with a standing rule that any changed verdict in later runs gets the 3× spot-check again.
- **Honesty is emitted by code.** The report generator prints the caveats (same-vendor judge, ~9-points resolution, non-blind set, predicted-fail ceiling) into every report header — a future run *cannot* produce a number without its disclosures.
- **The perfect score ships with its own discounts**, adjacent to the number: the caption audit verified the golden-critical content before the exam (and the caption *prompts* were golden-informed too — elicitation circularity, disclosed); correctness reflects one generation sample; the instrument is saturated and now detects only regressions. A perfect score you can't discount is marketing; one you can is a measurement.

## 8. What breaks at scale (named, not discovered later)

The small-scale choices carry explicit upgrade triggers in the decision log: exact scan → HNSW toward ~10M vectors or p95 latency targets (D11); in-memory BM25 → in-database sparse search when the corpus outgrows a startup rebuild (D12); drop-and-rebuild ingest → content-hash upserts when re-embedding costs real money (D18); n=11 golden set → per-claim decomposition when answers become long procedures (D17). Scoping small is fine; scoping small *silently* is how prototypes get mistaken for products.
