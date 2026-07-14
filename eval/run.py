"""M2 eval harness (D17): retrieve once, log context, generate from the logged
context, judge the logged context. Never re-retrieve between generation and
judging — that would judge a different run than the one that answered.

Raw run JSON contains full manual text -> gitignored; the .md report contains
no chunk text and is committed.
"""

import argparse
import datetime
import json
from pathlib import Path

from eval.golden import load_golden
from eval.judge import JUDGE_PROMPT_VERSION, judge_correctness, judge_groundedness, judge_refusal
from eval.metrics import hit, pages_found, reciprocal_rank
from src.config import DEFAULT_EMBED, EMBED_CONFIGS, GENERATION_MODEL, JUDGE_MODEL
from src.generate import answer_from_chunks, format_context
from src.retrieve import retrieve

RESULTS_DIR = Path(__file__).parent / "results"


def run_eval(embed: str = DEFAULT_EMBED) -> dict:
    rows = []
    for q in load_golden():
        chunks = retrieve(q.question, embed=embed)
        context = format_context(chunks)  # as-logged (D17)
        rag = answer_from_chunks(q.question, chunks)
        pages = [c.node.metadata["page"] for c in chunks]
        row = {
            "id": q.id, "qtype": q.qtype, "question": q.question,
            "expected_pages": q.expected_pages, "retrieved_pages": pages,
            "answer": rag.answer, "context": context, "annotation": q.annotation,
            "trap": q.trap, "golden_answer": q.golden_answer,
        }
        if q.trap:
            refusal = judge_refusal(rag.answer)
            row |= {"refused": refusal.passed, "refusal_justification": refusal.justification}
        else:
            expected = set(q.expected_pages)
            grounded = judge_groundedness(q.question, context, rag.answer)
            correct = judge_correctness(q.question, q.golden_answer, rag.answer)
            row |= {
                "hit": hit(pages, expected),
                "rr": reciprocal_rank(pages, expected),
                "pages_found": pages_found(pages, expected),
                "grounded": grounded.passed, "grounded_justification": grounded.justification,
                "correct": correct.passed, "correct_justification": correct.justification,
            }
        rows.append(row)
        print(f"{q.id}: done")
    return {
        "date": datetime.date.today().isoformat(),
        "embed": embed,
        # config_label is the run's identity: M3 adds fused/reranked configs on the
        # same embed tier, and filenames/compare headers must not collide then
        "config_label": f"dense-{embed}",
        "embed_model": EMBED_CONFIGS[embed]["model"],
        "generation_model": GENERATION_MODEL,
        "judge_model": JUDGE_MODEL,
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "rows": rows,
    }


def write_report(run: dict, out_dir: Path = RESULTS_DIR) -> Path:
    out_dir.mkdir(exist_ok=True)
    stem = f"{run['date']}-{run['config_label']}"
    raw = out_dir / f"{stem}.json"
    if raw.exists():
        raise RuntimeError(
            f"{raw} exists — a same-day rerun would overwrite the log that "
            "--calibrate/--compare read; move or delete it consciously first"
        )
    # ~30 paid API calls live in this dict: persist it BEFORE any report
    # formatting has a chance to crash
    raw.write_text(json.dumps(run, indent=2))

    scored = [r for r in run["rows"] if not r["trap"]]
    trap_rows = [r for r in run["rows"] if r["trap"]]
    n = len(scored)
    predicted_fail = sum(1 for r in scored if "predicted fail" in (r["annotation"] or ""))
    hits = sum(r["hit"] for r in scored)
    grounded = sum(r["grounded"] for r in scored)
    correct = sum(r["correct"] for r in scored)
    mrr = sum(r["rr"] for r in scored) / n

    lines = [
        f"# Eval report — {run['date']} — {run['config_label']}",
        "",
        f"- Embedding: `{run['embed_model']}` · Generation: `{run['generation_model']}`"
        f" · Judge: `{run['judge_model']}` (prompt {run['judge_prompt_version']})",
        "- Instrument notes: same-vendor limitation (Anthropic judge grading an Anthropic"
        f" generator); smallest observable delta at n={n} is one question"
        f" (~{round(100 / n)} points); counts, not percentages (D17); the single trap"
        " question is a hallucination probe of n=1; the golden set is not blind"
        " (drafted knowing the M1 smoke results).",
        f"- Predicted-fail ceiling: {predicted_fail} scored rows cannot pass correctness"
        f" by design (D9/D19/D6) — best achievable correct = {n - predicted_fail}/{n}.",
        "",
        "| id | type | expected | retrieved (rank order) | hit | RR | pages | grounded | correct | annotation |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in scored:
        lines.append(
            f"| {r['id']} | {r['qtype']} | {','.join(r['expected_pages'])} "
            f"| {','.join(r['retrieved_pages'])} | {'1' if r['hit'] else '0'} "
            f"| {r['rr']:.2f} | {r['pages_found']} | {'1' if r['grounded'] else '0'} "
            f"| {'1' if r['correct'] else '0'} | {r['annotation'] or ''} |"
        )
    failing = [r for r in scored if not (r["grounded"] and r["correct"])]
    if failing:
        lines += ["", "### Judge justifications (failing rows)", ""]
        for r in failing:
            for axis in ("grounded", "correct"):
                if not r[axis]:
                    lines.append(f"- **{r['id']}/{axis}**: {r[axis + '_justification']}")
    for r in trap_rows:
        lines += [
            "",
            f"**Trap ({r['id']})**: refused = {'yes' if r['refused'] else 'NO — FAILURE'}"
            f" — excluded from retrieval metrics (D17). {r['annotation'] or ''}",
        ]
    lines += [
        "",
        f"**Aggregates (n={n} answerable):** hit@5 = {hits}/{n} · MRR@5 = {mrr:.2f}"
        f" · grounded = {grounded}/{n} · correct = {correct}/{n}",
        "",
        "Quadrant reading: grounded∧¬correct → retrieval-or-corpus failure"
        " (the row's annotation decides which); ¬grounded∧correct →"
        " parametric-knowledge answer (D15's target).",
    ]

    report = out_dir / f"{stem}.md"
    report.write_text("\n".join(lines) + "\n")
    return report


def calibrate(run_json: Path) -> None:
    """One-time judge flip-rate check (D17): re-judge the LOGGED answers and
    contexts 3x — no re-generation, isolating judge noise from generator
    noise. The originally logged verdict counts as a fourth sample: three
    fresh unanimous calls that disagree with the logged verdict are a flip."""
    run = json.loads(run_json.read_text())
    flips = 0
    checks = 0
    for r in run["rows"]:
        if r["trap"]:
            axes = [("refused", r["refused"],
                     [judge_refusal(r["answer"]).passed for _ in range(3)])]
        else:
            axes = [
                ("grounded", r["grounded"],
                 [judge_groundedness(r["question"], r["context"], r["answer"]).passed
                  for _ in range(3)]),
                ("correct", r["correct"],
                 [judge_correctness(r["question"], r["golden_answer"], r["answer"]).passed
                  for _ in range(3)]),
            ]
        for name, logged, fresh in axes:
            checks += 1
            if len(set(fresh + [logged])) > 1:
                flips += 1
                print(f"FLIP {r['id']}/{name}: logged={logged}, fresh={fresh}")
    print(f"calibration: {flips} flipping axes out of {checks} (logged + 3 fresh each)")
    print("D17 rule: 0 flips -> single-run judging; otherwise majority-of-3 becomes standing protocol")


def compare(path_a: Path, path_b: Path) -> None:
    """A/B readout (D3/D17): attributable metrics are hit/MRR only — each
    config regenerates its own answers (the context differs, so it must), so
    grounded/correct deltas carry generation and judge noise and must not be
    attributed to the embedding tier."""
    a, b = json.loads(path_a.read_text()), json.loads(path_b.read_text())
    la, lb = a["config_label"], b["config_label"]
    print(f"| id | hit {la} | hit {lb} | RR {la} | RR {lb} | same top-5? |")
    print("|---|---|---|---|---|---|")
    rows_b = {r["id"]: r for r in b["rows"]}
    identical = []
    for ra in a["rows"]:
        if ra["trap"]:
            continue
        rb = rows_b[ra["id"]]
        same = ra["retrieved_pages"] == rb["retrieved_pages"]
        if same:
            identical.append(ra["id"])
        print(f"| {ra['id']} | {int(ra['hit'])} | {int(rb['hit'])} "
              f"| {ra['rr']:.2f} | {rb['rr']:.2f} | {'yes' if same else ''} |")
    for run in (a, b):
        scored = [r for r in run["rows"] if not r["trap"]]
        n = len(scored)
        print(f"{run['config_label']}: hit {sum(r['hit'] for r in scored)}/{n}, "
              f"MRR {sum(r['rr'] for r in scored) / n:.2f}, "
              f"grounded {sum(r['grounded'] for r in scored)}/{n}, "
              f"correct {sum(r['correct'] for r in scored)}/{n}")
    print(
        f"attributable readout: hit/MRR. grounded/correct deltas are confounded with "
        f"generation sampling and judge noise. rows with identical top-5 ({identical}) "
        f"— any judge disagreement there is a free noise estimate."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--embed", default=DEFAULT_EMBED, choices=list(EMBED_CONFIGS))
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--calibrate", type=Path, default=None, metavar="RUN_JSON")
    group.add_argument("--compare", type=Path, nargs=2, default=None, metavar=("A_JSON", "B_JSON"))
    args = parser.parse_args()
    if args.calibrate:
        calibrate(args.calibrate)
    elif args.compare:
        compare(*args.compare)
    else:
        path = write_report(run_eval(args.embed))
        print(f"report: {path}")
