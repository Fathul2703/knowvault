"""Markdown and JSON reports for a retrieval evaluation run."""

import json
import math
from collections.abc import Sequence
from dataclasses import asdict

from knowvault.evaluation.metrics import percentile
from knowvault.evaluation.runner import CUTOFFS, EvalReport

MODE_LABELS = {"hybrid": "hybrid (RRF)", "vector": "vector", "fulltext": "full text"}
# Longer lists of misses drown the rest of the report; the JSON report has every result.
MAX_LISTED_MISSES = 10


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _stats(values: Sequence[float]) -> str:
    if not values:
        return "—"
    return (
        f"min {min(values):.3f} · p25 {percentile(values, 25):.3f} · "
        f"median {percentile(values, 50):.3f} · max {max(values):.3f}"
    )


def to_markdown(report: EvalReport) -> str:
    config = report.config
    lines = [
        f"# Retrieval evaluation — {report.created_at:%Y-%m-%d}"
        + (f" ({config['label']})" if config.get("label") else ""),
        "",
        f"Generated {report.created_at:%Y-%m-%d %H:%M} UTC by `knowvault eval-retrieval`.",
        "",
        "## Setup",
        "",
        f"- Embedding model: `{config['embedding_model']}`",
        (
            f"- Reranker (hybrid mode): `{config['reranker']}`, top "
            f"{config['rerank_candidates']} fused results"
            if config.get("reranker")
            else "- Reranker: none"
        ),
        f"- Corpus: {config['documents']} documents, {config['chunks']} chunks "
        f"(target {config['chunk_target_chars']} / max {config['chunk_max_chars']} characters, "
        f"overlap {config['chunk_overlap_chars']})",
        f"- Questions: {config['questions']} ({config['answerable_questions']} answerable)",
        f"- Hybrid: RRF k = {config['rrf_k']}, {config['candidates_per_list']} candidates per "
        f"method; top k = {config['top_k']}",
        "",
        "A result counts as relevant when it comes from the labelled document and contains one of "
        "the labelled evidence passages. Metrics cover answerable questions only.",
        "",
        "## Results",
        "",
        "| Mode | "
        + " | ".join(f"Success@{k}" for k in CUTOFFS)
        + " | MRR@10 | Latency p50 | Latency p95 |",
        "|---|" + "---|" * (len(CUTOFFS) + 3),
    ]
    for summary in report.summaries:
        cells = [_pct(summary.success[k]) for k in CUTOFFS]
        lines.append(
            f"| {MODE_LABELS.get(summary.mode, summary.mode)} | {' | '.join(cells)} | "
            f"{summary.mrr:.3f} | {summary.latency_p50_ms:.0f} ms | "
            f"{summary.latency_p95_ms:.0f} ms |"
        )

    categories = sorted({c for s in report.summaries for c in s.by_category})
    lines += [
        "",
        "## By question category (Success@5 / MRR@10)",
        "",
        "| Category | Questions | "
        + " | ".join(MODE_LABELS.get(s.mode, s.mode) for s in report.summaries)
        + " |",
        "|---|---|" + "---|" * len(report.summaries),
    ]
    for category in categories:
        counts = {int(s.by_category[category]["questions"]) for s in report.summaries}
        cells = [
            f"{_pct(s.by_category[category]['success@5'])} / "
            f"{s.by_category[category]['mrr@10']:.3f}"
            for s in report.summaries
        ]
        lines.append(f"| {category} | {max(counts)} | {' | '.join(cells)} |")

    lines += [
        "",
        "## Similarity distributions (hybrid)",
        "",
        "For calibrating a minimum-evidence threshold before answering (Phase 4).",
        "",
        f"- First relevant chunk of answerable questions: {_stats(report.similarity['relevant'])}",
        f"- Best chunk for unanswerable questions: {_stats(report.similarity['unanswerable_top'])}",
        *(
            [
                "",
                "Reranker scores (hybrid):",
                "",
                f"- First relevant chunk of answerable questions: "
                f"{_stats(report.similarity['rerank_relevant'])}",
                f"- Best chunk for unanswerable questions: "
                f"{_stats(report.similarity.get('rerank_unanswerable_top', []))}",
            ]
            if report.similarity.get("rerank_relevant")
            else []
        ),
        "",
        "## Misses (no relevant chunk in the top 10)",
        "",
    ]
    by_id = {q.id: q for q in report.questions}
    any_miss = False
    for summary in report.summaries:
        misses = [
            r
            for r in report.results
            if r.mode == summary.mode and r.rank is None and by_id[r.question_id].answerable
        ]
        if not misses:
            continue
        any_miss = True
        lines += [
            f"### {MODE_LABELS.get(summary.mode, summary.mode)}: {len(misses)} of "
            f"{summary.questions}",
            "",
            "| Question | Category | Expected | Top results |",
            "|---|---|---|---|",
        ]
        for result in misses[:MAX_LISTED_MISSES]:
            question = by_id[result.question_id]
            lines.append(
                f"| {question.question} | {question.category} | {question.document} | "
                f"{', '.join(result.top_documents) or '—'} |"
            )
        if len(misses) > MAX_LISTED_MISSES:
            lines.append(
                f"\n…and {len(misses) - MAX_LISTED_MISSES} more; see the JSON report for all "
                "results."
            )
        lines.append("")
    if not any_miss:
        lines.append("None.")
    lines += [
        "",
        "## Caveats",
        "",
        "The corpus and questions are synthetic and were written by the same author, which can "
        "make questions closer to the wording of their documents than real queries. "
        "Cross-lingual questions and topically overlapping distractor documents reduce, but do "
        "not remove, this bias. Compare runs with each other rather than reading absolute "
        "numbers as production quality.",
        "",
    ]
    return "\n".join(lines)


def to_json(report: EvalReport) -> str:
    def clean(value: object) -> object:
        if isinstance(value, float) and math.isnan(value):
            return None
        return value

    payload = {
        "created_at": report.created_at.isoformat(),
        "config": report.config,
        "summaries": [
            {
                **{k: clean(v) for k, v in asdict(s).items() if k != "success"},
                "success": {f"@{k}": v for k, v in s.success.items()},
            }
            for s in report.summaries
        ],
        "similarity": report.similarity,
        "results": [asdict(r) for r in report.results],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
