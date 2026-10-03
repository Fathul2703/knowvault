"""Totals of a filled-in review sheet (see `answer_report.to_review_sheet`)."""

import re
from dataclasses import dataclass, field

from knowvault.evaluation.answer_report import ANSWER_VERDICTS, CITATION_VERDICTS

_SECTION = re.compile(r"^## (\d+)\. ", re.MULTILINE)
_CITATION = re.compile(
    r"^- \[([ xX])\] \[(\d+)\] (" + "|".join(map(re.escape, CITATION_VERDICTS)) + r")\s*$",
    re.MULTILINE,
)
_ANSWER = re.compile(
    r"^- \[([ xX])\] (" + "|".join(map(re.escape, ANSWER_VERDICTS)) + r")\s*$", re.MULTILINE
)


@dataclass
class ReviewTally:
    answers: int = 0
    citations: dict[str, int] = field(default_factory=lambda: dict.fromkeys(CITATION_VERDICTS, 0))
    overall: dict[str, int] = field(default_factory=lambda: dict.fromkeys(ANSWER_VERDICTS, 0))
    # Section numbers with a citation or answer left unmarked, or marked more than once.
    incomplete: list[int] = field(default_factory=list)


def tally_review(text: str) -> ReviewTally:
    tally = ReviewTally()
    starts = [(int(m.group(1)), m.start()) for m in _SECTION.finditer(text)]
    for index, (number, start) in enumerate(starts):
        end = starts[index + 1][1] if index + 1 < len(starts) else len(text)
        section = text[start:end]
        tally.answers += 1
        complete = True

        marks: dict[str, list[str]] = {}
        for box, ordinal, verdict in _CITATION.findall(section):
            marks.setdefault(ordinal, [])
            if box != " ":
                marks[ordinal].append(verdict)
        for chosen in marks.values():
            if len(chosen) == 1:
                tally.citations[chosen[0]] += 1
            else:
                complete = False

        overall = [verdict for box, verdict in _ANSWER.findall(section) if box != " "]
        if len(overall) == 1:
            tally.overall[overall[0]] += 1
        else:
            complete = False
        if not complete:
            tally.incomplete.append(number)
    return tally


def format_tally(tally: ReviewTally) -> str:
    def share(count: int, total: int) -> str:
        return f"{count} ({count / total * 100:.0f}%)" if total else str(count)

    cited = sum(tally.citations.values())
    judged = sum(tally.overall.values())
    lines = [
        f"Answers: {tally.answers} ({judged} with an overall verdict)",
        f"Citations judged: {cited}",
        *(f"  {verdict}: {share(n, cited)}" for verdict, n in tally.citations.items()),
        "Answers:",
        *(f"  {verdict}: {share(n, judged)}" for verdict, n in tally.overall.items()),
    ]
    if tally.incomplete:
        lines.append(
            "Incomplete (unmarked or marked twice): "
            + ", ".join(str(number) for number in tally.incomplete)
        )
    return "\n".join(lines)
