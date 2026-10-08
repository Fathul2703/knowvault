"""`knowvault eval-entities`: how well entity names are matched (ADR 0016).

Labelled pairs of names say whether they denote the same entity. Three rules are compared:
the case-insensitive key used before, the lexical key, and the lexical key plus similarity of
name embeddings with the guard against names that contain each other. A false merge corrupts
the graph, so precision matters more than recall.
"""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from knowvault.core.embeddings import EmbeddingModel
from knowvault.modules.graph.domain.model import EntityType, may_merge, normalize_name

THRESHOLDS = (0.70, 0.75, 0.78, 0.80, 0.82, 0.84, 0.86, 0.88, 0.90)


@dataclass(frozen=True)
class Pair:
    a: str
    b: str
    same: bool
    kind: str
    similarity: float = 0.0


@dataclass(frozen=True)
class RuleResult:
    rule: str
    merged_same: int
    merged_different: int
    missed_same: int

    @property
    def precision(self) -> float:
        merged = self.merged_same + self.merged_different
        return self.merged_same / merged if merged else 1.0

    @property
    def recall(self) -> float:
        same = self.merged_same + self.missed_same
        return self.merged_same / same if same else 0.0


def load_pairs(path: Path) -> list[Pair]:
    pairs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            raw = json.loads(line)
            pairs.append(Pair(raw["a"], raw["b"], bool(raw["same"]), raw["kind"]))
    return pairs


def _case_only(name: str) -> str:
    return " ".join(name.split()).strip(" .,;:").casefold()


def _lexical(a: str, b: str) -> bool:
    return normalize_name(a, EntityType.NAME) == normalize_name(b, EntityType.NAME)


def score(pairs: list[Pair], rule: str, merges: Callable[[Pair], bool]) -> RuleResult:
    merged = [pair for pair in pairs if merges(pair)]
    return RuleResult(
        rule=rule,
        merged_same=sum(1 for p in merged if p.same),
        merged_different=sum(1 for p in merged if not p.same),
        missed_same=sum(1 for p in pairs if p.same and p not in merged),
    )


async def evaluate(
    pairs: list[Pair], embeddings: EmbeddingModel, threshold: float
) -> tuple[list[Pair], list[RuleResult], list[RuleResult]]:
    names = sorted({p.a for p in pairs} | {p.b for p in pairs})
    vectors = dict(zip(names, await embeddings.embed_documents(names), strict=True))
    scored = [
        Pair(
            p.a,
            p.b,
            p.same,
            p.kind,
            sum(x * y for x, y in zip(vectors[p.a], vectors[p.b], strict=True)),
        )
        for p in pairs
    ]

    def resolved(t: float) -> Callable[[Pair], bool]:
        return lambda p: _lexical(p.a, p.b) or may_merge(p.a, p.b, p.similarity, t)

    rules = [
        score(
            scored, "Case-insensitive key (before)", lambda p: _case_only(p.a) == _case_only(p.b)
        ),
        score(scored, "Lexical key", lambda p: _lexical(p.a, p.b)),
        score(scored, f"Lexical key + similarity ≥ {threshold:.2f} (default)", resolved(threshold)),
        score(
            scored,
            f"Similarity ≥ {threshold:.2f} without the guard",
            lambda p: _lexical(p.a, p.b) or p.similarity >= threshold,
        ),
    ]
    sweep = [score(scored, f"{t:.2f}", resolved(t)) for t in THRESHOLDS]
    return scored, rules, sweep


def to_markdown(
    model: str,
    threshold: float,
    pairs: list[Pair],
    rules: list[RuleResult],
    sweep: list[RuleResult],
) -> str:
    now = datetime.now(UTC)
    same = sum(1 for p in pairs if p.same)
    lines = [
        f"# Entity resolution — {now:%Y-%m-%d}",
        "",
        f"Generated {now:%Y-%m-%d %H:%M} UTC by `knowvault eval-entities`.",
        "",
        f"- Embedding model: `{model}`",
        f"- Pairs: {len(pairs)} ({same} the same entity, {len(pairs) - same} different)",
        "",
        "A merge of two different entities corrupts the graph; a missed merge leaves a duplicate.",
        "",
        "## Rules",
        "",
        "| Rule | Merged correctly | Merged wrongly | Missed | Precision | Recall |",
        "|---|---|---|---|---|---|",
    ]
    for r in rules:
        lines.append(
            f"| {r.rule} | {r.merged_same} | {r.merged_different} | {r.missed_same} | "
            f"{r.precision * 100:.0f}% | {r.recall * 100:.0f}% |"
        )
    lines += [
        "",
        "## Threshold (lexical key + similarity, with the guard)",
        "",
        "| Threshold | Merged correctly | Merged wrongly | Missed |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {r.rule} | {r.merged_same} | {r.merged_different} | {r.missed_same} |" for r in sweep
    ]

    def decision(p: Pair) -> str:
        if _lexical(p.a, p.b):
            return "merged (key)"
        if may_merge(p.a, p.b, p.similarity, threshold):
            return "merged (similarity)"
        return "kept apart"

    lines += [
        "",
        f"## Pairs (threshold {threshold:.2f})",
        "",
        "| Similarity | Label | Kind | Names | Decision |",
        "|---|---|---|---|---|",
    ]
    for p in sorted(pairs, key=lambda p: -p.similarity):
        verdict = decision(p)
        wrong = (verdict != "kept apart") != p.same
        lines.append(
            f"| {p.similarity:.3f} | {'same' if p.same else 'different'} | {p.kind} | "
            f"{p.a} · {p.b} | {verdict}{' ✗' if wrong else ''} |"
        )
    lines.append("")
    return "\n".join(lines)


def to_json(model: str, threshold: float, pairs: list[Pair], rules: list[RuleResult]) -> str:
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "embedding_model": model,
        "threshold": threshold,
        "rules": [{**asdict(r), "precision": r.precision, "recall": r.recall} for r in rules],
        "pairs": [asdict(p) for p in pairs],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
