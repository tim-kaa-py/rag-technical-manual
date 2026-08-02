# Redacted candidate log — 2026-07-17 rerank-small-mm

Node identities for the M5 report's hit-verification claims, extracted from
the gitignored run JSON (which contains full manual text and is never
committed). This table carries **no chunk text** — only rank, node id, and
page — so the identity evidence is publicly checkable: caption node ids are
deterministic (uuid5 of "rag-technical-manual/caption" + page, D26) and can
be recomputed from `src/multimodal.py`.

## q7 — expected p. 48 · final top-5 pages: 48,47,47,39,41

| fused rank | page | node_id | identity |
|---|---|---|---|
| 1 | 48 | `44e2022b-c0f2-575e-a03b-4288e4868bb4` | caption p. 48 |
| 2 | 41 | `85f867af-ae9f-44f3-8b0a-1fad31bc4c74` | text chunk |
| 3 | 47 | `c61b8d45-733b-4d36-a1d3-e6dc30d54e64` | text chunk |
| 4 | 47 | `a1c2055f-e86d-4f5c-aaba-5d5f9097d107` | text chunk |
| 5 | 41 | `2d66a7d4-026b-4558-848c-0cc54a48cae8` | text chunk |
| 6 | 39 | `3a50b43a-b16f-4d20-8ec0-aa071b39350b` | text chunk |
| 7 | 5 | `9ec7b0de-ecb2-4bfa-abe8-c047d97d38d6` | text chunk |
| 8 | 53 | `3d80bb76-589e-4d7f-9272-8490c9f14d85` | text chunk |
| 9 | 49 | `df361e0d-fcc8-4a40-a599-665d22ad92ce` | text chunk |
| 10 | 42 | `28695821-3944-41cf-97b3-eba0f0fbdb39` | text chunk |

## q8 — expected p. 49 · final top-5 pages: 49,50,46,51,47

| fused rank | page | node_id | identity |
|---|---|---|---|
| 1 | 49 | `28f68b1c-afe3-5ec6-8f9b-da657d6d8765` | caption p. 49 |
| 2 | 51 | `058e2435-63a9-5953-8a21-af3ff03e8e44` | caption p. 51 |
| 3 | 50 | `78c74ef0-1855-5270-abac-17ebdd59bffb` | caption p. 50 |
| 4 | 47 | `c61b8d45-733b-4d36-a1d3-e6dc30d54e64` | text chunk |
| 5 | 8 | `03f95cdc-50ad-40b1-8b59-8af148d984e9` | text chunk |
| 6 | 35 | `012c9669-9485-4f79-90aa-430f612dd162` | text chunk |
| 7 | 45 | `b7d265e1-441d-41e1-ac16-0eac51c79b5f` | text chunk |
| 8 | 46 | `3d12f8c9-33a0-4edc-994a-890349dd7b70` | text chunk |
| 9 | 47 | `a1c2055f-e86d-4f5c-aaba-5d5f9097d107` | text chunk |
| 10 | 39 | `3a50b43a-b16f-4d20-8ec0-aa071b39350b` | text chunk |

## q9 — expected p. 42 · final top-5 pages: 42,42,45,46,50

| fused rank | page | node_id | identity |
|---|---|---|---|
| 1 | 42 | `b08c02d5-de85-58e6-87bc-119ee3b2bfb9` | caption p. 42 |
| 2 | 43 | `ff2ad2ef-5ea0-4314-94b4-51facce9b7ba` | text chunk |
| 3 | 50 | `78c74ef0-1855-5270-abac-17ebdd59bffb` | caption p. 50 |
| 4 | 45 | `b7d265e1-441d-41e1-ac16-0eac51c79b5f` | text chunk |
| 5 | 45 | `8f477523-894f-461a-86d5-22dd5a56267b` | text chunk |
| 6 | 42 | `28695821-3944-41cf-97b3-eba0f0fbdb39` | text chunk |
| 7 | 51 | `058e2435-63a9-5953-8a21-af3ff03e8e44` | caption p. 51 |
| 8 | 46 | `3d12f8c9-33a0-4edc-994a-890349dd7b70` | text chunk |
| 9 | 52 | `419a5d1a-0431-4192-9370-ce1a16a4d128` | text chunk |
| 10 | 20 | `4f595452-9989-4e8a-acc0-d1dc67084b23` | text chunk |

