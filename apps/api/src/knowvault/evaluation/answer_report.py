"""Markdown and JSON reports of an answer evaluation, and the sheet for manual review."""

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import asdict

from knowvault.evaluation.answers import AnswerReport, AnswerResult

MAX_LISTED = 10
_EXCERPT_CHARS = 160

# Statuses and verdicts of the review sheet; `knowvault eval-review` reads them back.
CITATION_VERDICTS = ("supports", "partly", "does not support")
ANSWER_VERDICTS = ("faithful", "partly faithful", "unfaithful")


def _count(rows: Sequence[AnswerResult], keep: Callable[[AnswerResult], bool]) -> str:
    if not rows:
        return "—"
    hits = sum(1 for row in rows if keep(row))
    return f"{hits / len(rows) * 100:.1f}% ({hits}/{len(rows)})"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _ms(value: float) -> str:
    return "—" if math.isnan(value) else f"{value:,.0f} ms"


def _excerpt(text: str) -> str:
    flat = " ".join(text.split())
    flat = flat if len(flat) <= _EXCERPT_CHARS else flat[:_EXCERPT_CHARS].rstrip() + "…"
    return flat.replace("|", "\\|")


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def to_markdown(report: AnswerReport, *, review_file: str | None, reviewed: int) -> str:
    config = report.config
    questions = {q.id: q for q in report.questions}
    results = report.results
    answerable = [r for r in results if r.answerable]
    unanswerable = [r for r in results if not r.answerable]
    complete = [r for r in results if r.status == "complete"]
    complete_answerable = [r for r in complete if r.answerable]
    injection = [r for r in results if r.canary_leaked is not None]
    summary = report.summary
    answers = max(1, summary.answers)

    lines = [
        f"# Answer evaluation — {report.created_at:%Y-%m-%d}"
        + (f" ({config['label']})" if config.get("label") else ""),
        "",
        f"Generated {report.created_at:%Y-%m-%d %H:%M} UTC by `knowvault eval-answers`.",
        "",
        "## Setup",
        "",
        f"- Answer model: `{config['answer_model']}` (provider `{config['llm_provider']}`), "
        f"prompt `{config['prompt_version']}`",
        f"- Embedding model: `{config['embedding_model']}`; reranker: "
        f"`{config.get('reranker') or 'none'}`",
        f"- Corpus: {config['documents']} documents, {config['chunks']} chunks",
        f"- Questions: {summary.questions} ({summary.answerable} answerable, "
        f"{summary.unanswerable} unanswerable; {summary.injection_questions} about documents "
        "that contain a prompt-injection attempt)",
        f"- Up to {config['max_sources']} sources and {config['context_chars']:,} characters per "
        f"answer, at most {config['max_output_tokens']} output tokens",
        "",
    ]
    if config["llm_provider"] == "fake":
        lines += [
            "> **Pipeline check, not answer quality.** The fake model quotes the first sentence of "
            "the sources that share words with the question. These numbers show that the "
            "evaluation and the answer pipeline work; run with `LLM_PROVIDER=anthropic` to "
            "measure a language model.",
            "",
        ]
    lines += [
        "Each question is asked in a new conversation. A source *contains the evidence* when it "
        "comes from the labelled document and includes a labelled evidence passage — the same "
        "rule as the retrieval evaluation.",
        "",
        "## Results",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Answerable questions answered | "
        f"{_count(answerable, lambda r: r.status == 'complete')} |",
        f"| Answerable questions refused | {_count(answerable, lambda r: r.status == 'refused')} |",
        f"| Unanswerable questions refused | "
        f"{_count(unanswerable, lambda r: r.status == 'refused')} |",
        f"| Unanswerable questions answered anyway | "
        f"{_count(unanswerable, lambda r: r.status == 'complete')} |",
        f"| **Refusal accuracy** (right decision, all questions) | "
        f"{_pct(summary.refusal_accuracy)} |",
        f"| Errors | {_count(results, lambda r: r.status == 'error')} |",
        f"| Answers citing at least one source | {_count(complete, lambda r: bool(r.cited))} |",
        f"| **Answers with invalid citation numbers** | "
        f"{_count(complete, lambda r: bool(r.invalid_citations))} |",
        f"| Answers citing a source that contains the evidence | "
        f"{_count(complete_answerable, lambda r: r.cited_relevant)} |",
        f"| Evidence among the sources given (retrieval) | "
        f"{_count(answerable, lambda r: r.evidence_in_sources)} |",
        f"| **Prompt-injection leaks** | {summary.injection_leaks} of "
        f"{summary.injection_questions} |",
        f"| Latency p50 / p95 | {_ms(summary.latency_p50_ms)} / {_ms(summary.latency_p95_ms)} |",
        f"| Tokens: input / output (per answered question) | {summary.input_tokens:,} / "
        f"{summary.output_tokens:,} ({summary.input_tokens // answers:,} / "
        f"{summary.output_tokens // answers:,}) |",
        "",
        "## By category",
        "",
        "| Category | Questions | Answered | Refused | Cites the evidence |",
        "|---|---|---|---|---|",
    ]
    for category, row in summary.by_category.items():
        lines.append(
            f"| {category} | {row['questions']:.0f} | {_pct(row['answered'])} | "
            f"{_pct(row['refused'])} | {_pct(row['cited_relevant'])} |"
        )

    def listing(
        title: str,
        rows: list[AnswerResult],
        columns: str,
        render: Callable[[AnswerResult], str],
    ) -> None:
        if not rows:
            return
        lines.extend(["", f"### {title} ({len(rows)})", "", columns, _separator(columns)])
        lines.extend(render(row) for row in rows[:MAX_LISTED])
        if len(rows) > MAX_LISTED:
            lines.extend(["", f"…and {len(rows) - MAX_LISTED} more; see the JSON report."])

    lines.extend(["", "## Problems"])
    listing(
        "Refused although answerable",
        [r for r in answerable if r.status == "refused"],
        "| Question | Category | Evidence among sources |",
        lambda r: (
            f"| {_cell(questions[r.question_id].question)} | {r.category} | "
            f"{'yes' if r.evidence_in_sources else 'no'} |"
        ),
    )
    listing(
        "Answered although unanswerable",
        [r for r in unanswerable if r.status == "complete"],
        "| Question | Answer |",
        lambda r: f"| {_cell(questions[r.question_id].question)} | {_excerpt(r.answer)} |",
    )
    listing(
        "Invalid citation numbers",
        [r for r in complete if r.invalid_citations],
        "| Question | Invalid | Sources given |",
        lambda r: (
            f"| {_cell(questions[r.question_id].question)} | "
            f"{', '.join(map(str, r.invalid_citations))} | {len(r.sources)} |"
        ),
    )
    listing(
        "Answers not citing the evidence",
        [r for r in complete_answerable if not r.cited_relevant],
        "| Question | Category | Evidence among sources | Answer |",
        lambda r: (
            f"| {_cell(questions[r.question_id].question)} | {r.category} | "
            f"{'yes' if r.evidence_in_sources else 'no'} | {_excerpt(r.answer)} |"
        ),
    )
    listing(
        "Prompt-injection leaks",
        [r for r in injection if r.canary_leaked],
        "| Question | Answer |",
        lambda r: f"| {_cell(questions[r.question_id].question)} | {_excerpt(r.answer)} |",
    )
    listing(
        "Errors",
        [r for r in results if r.status == "error"],
        "| Question | Error |",
        lambda r: f"| {_cell(questions[r.question_id].question)} | {r.error_code} |",
    )
    if lines[-1] == "## Problems":
        lines.extend(["", "None."])

    lines.extend(["", "## Manual review", ""])
    if review_file:
        lines.append(
            f"{reviewed} answers were sampled for review into `{review_file}`. Mark each citation "
            "and answer there, then run `knowvault eval-review` on the file for the totals."
        )
    else:
        lines.append("No review sheet was written for this run.")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "The corpus and questions are synthetic and written by the same author. Automatic "
            "measures check decisions and citation numbers, and whether a cited source contains "
            "the labelled evidence; they do not check that the source supports each sentence. "
            "That is what the manual review is for.",
            "",
        ]
    )
    return "\n".join(lines)


def _separator(columns: str) -> str:
    return "|" + "---|" * (columns.count("|") - 1)


def to_json(report: AnswerReport) -> str:
    def result(row: AnswerResult) -> dict[str, object]:
        data = asdict(row)
        # Uncited source text would make the report large; cited passages are kept for review.
        data["sources"] = [
            {key: value for key, value in source.items() if key != "text" or source["cited"]}
            for source in data["sources"]
        ]
        return data

    payload = {
        "created_at": report.created_at.isoformat(),
        "config": report.config,
        "summary": asdict(report.summary),
        "results": [result(row) for row in report.results],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False, default=str) + "\n"


def _quote(text: str) -> list[str]:
    return [f"> {line}" if line else ">" for line in text.strip().splitlines()] or [">"]


def to_review_sheet(report: AnswerReport, sample: Sequence[AnswerResult], report_name: str) -> str:
    """A Markdown checklist: one verdict per citation and one per answer."""
    config = report.config
    questions = {q.id: q for q in report.questions}
    lines = [
        f"# Answer review — {report.created_at:%Y-%m-%d}"
        + (f" ({config['label']})" if config.get("label") else ""),
        "",
        f"{len(sample)} answers by `{config['answer_model']}` "
        f"(prompt `{config['prompt_version']}`), sampled from `{report_name}`.",
        "",
        "Tick exactly one box per citation and one per answer (`- [x]`), then run "
        "`knowvault eval-review <this file>` for the totals.",
        "",
        "- **supports**: the passage states what the citing sentence says.",
        "- **partly**: the passage supports only part of the sentence, or only by inference.",
        "- **does not support**: the passage does not say it.",
        "- Overall, **faithful**: every claim is supported by its citations; **partly "
        "faithful**: a minor claim is not; **unfaithful**: a main claim is unsupported or wrong.",
    ]
    for number, row in enumerate(sample, start=1):
        question = questions[row.question_id]
        lines += [
            "",
            "---",
            "",
            f"## {number}. `{row.question_id}` · {row.category} · {row.language}",
            "",
            f"**Question:** {question.question}",
            "",
            "**Answer:**",
            "",
            *_quote(row.answer),
        ]
        cited = [source for source in row.sources if source.cited]
        if not cited:
            lines += ["", "*No citations.*"]
        for source in cited:
            location = f" — {source.location}" if source.location else ""
            lines += [
                "",
                f"**[{source.ordinal}] {source.document}{location}**",
                "",
                *_quote(source.text),
                "",
                *(f"- [ ] [{source.ordinal}] {verdict}" for verdict in CITATION_VERDICTS),
            ]
        lines += [
            "",
            "**Overall**",
            "",
            *(f"- [ ] {verdict}" for verdict in ANSWER_VERDICTS),
            "",
            "Notes:",
        ]
    return "\n".join(lines) + "\n"
