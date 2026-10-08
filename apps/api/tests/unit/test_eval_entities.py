"""The entity resolution evaluation."""

from pathlib import Path

from knowvault.evaluation.entities import evaluate, load_pairs, to_markdown

PAIRS = [
    '{"a": "Business Day", "b": "Business Days", "same": true, "kind": "plural"}',
    '{"a": "Netherlands", "b": "Belanda", "same": true, "kind": "cross_lingual"}',
    '{"a": "Customer", "b": "Customer Data", "same": false, "kind": "related"}',
    '{"a": "Jakarta", "b": "Bekasi", "same": false, "kind": "same_kind"}',
]


class Pairwise:
    """Belanda/Netherlands and Customer/Customer Data look identical; the rest do not."""

    model_id = "pairwise"
    dimensions = 3

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        def vector(text: str) -> list[float]:
            if text in {"Netherlands", "Belanda"}:
                return [1.0, 0.0, 0.0]
            if text.startswith("Customer"):
                return [0.0, 1.0, 0.0]
            return [0.0, 0.0, 1.0] if text == "Jakarta" else [0.6, 0.0, 0.8]

        return [vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]


async def test_rules_compare_keys_similarity_and_the_guard(tmp_path: Path) -> None:
    path = tmp_path / "pairs.jsonl"
    path.write_text("\n".join(PAIRS) + "\n")

    pairs, rules, sweep = await evaluate(load_pairs(path), Pairwise(), 0.82)

    by_rule = {r.rule.split(" (")[0].split(" ≥")[0]: r for r in rules}
    assert by_rule["Lexical key"].merged_same == 1
    resolved = rules[2]
    assert (resolved.merged_same, resolved.merged_different) == (2, 0)
    unguarded = rules[3]
    assert unguarded.merged_different == 1  # Customer / Customer Data
    assert resolved.precision == 1.0
    assert len(sweep) > 3
    markdown = to_markdown("pairwise", 0.82, pairs, rules, sweep)
    assert "| Lexical key | 1 | 0 | 1 |" in markdown
