"""Rule-based entity extraction and entity keys."""

import uuid

import pytest

from knowvault.modules.graph.domain.heuristic import HeuristicExtractor, extract
from knowvault.modules.graph.domain.model import (
    CO_OCCURS,
    ChunkText,
    EntityType,
    contains_other,
    may_merge,
    normalize_name,
)


def found(text: str, **kwargs: int) -> dict[str, str]:
    graph = extract(ChunkText(uuid.uuid4(), text), **kwargs)
    return {entity.name: entity.type.value for entity in graph.entities}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ERR_4713 means the card was declined; see ERR_7411.", {"ERR_4713", "ERR_7411"}),
        ("Barang SKU-A1270 disimpan di rak C3.", {"SKU-A1270"}),
        ("What changed in version 2.4.1 and 2.3.12?", {"2.4.1", "2.3.12"}),
        ("Status T30 berarti paket dalam perjalanan.", {"T30"}),
    ],
)
def test_codes(text: str, expected: set[str]) -> None:
    entities = found(text)
    assert expected <= {name for name, kind in entities.items() if kind == "code"}


def test_not_codes() -> None:
    # Headers without digits, abbreviations, prices, times and decimals.
    entities = found("Send X-RateLimit-Limit to the CEO. It costs 1.240 euros at 07.00 or 0.25 h.")
    assert not [name for name, kind in entities.items() if kind == "code"]


def test_names_in_english_and_indonesian() -> None:
    entities = found(
        "This Master Services Agreement is governed by the laws of the Netherlands. "
        "Gudang baru di Bekasi beroperasi sejak Agustus 2025 untuk pelanggan di Jabodetabek."
    )
    assert {"Master Services Agreement", "Netherlands", "Bekasi", "Jabodetabek"} <= set(entities)
    assert all(kind == "name" for kind in entities.values())


def test_sentence_starts_months_and_codes_are_not_names() -> None:
    entities = found("Employees get leave. Pada bulan Maret sisa cuti hangus. Status T30 tiba.")
    assert "Employees" not in entities
    assert "Maret" not in entities
    assert "Status T30" not in entities


def test_connectors_join_names() -> None:
    assert "Bank of Indonesia" in found("Payments go through the Bank of Indonesia today.")


def test_counts_limits_and_co_occurrence() -> None:
    text = "The Provider and the Customer agree. The Provider bills the Customer. " + " ".join(
        f"Code X{i}{i}{i}" for i in range(1, 9)
    )
    graph = extract(ChunkText(uuid.uuid4(), text), max_entities=4)
    assert len(graph.entities) == 4
    provider = next(e for e in graph.entities if e.name == "Provider")
    assert provider.count == 2
    # Every pair of kept entities co-occurs once.
    assert len(graph.relations) == 6
    assert {r.type for r in graph.relations} == {CO_OCCURS}


async def test_extractor_keeps_chunk_order() -> None:
    chunks = [
        ChunkText(uuid.uuid4(), "ERR_4711 failed."),
        ChunkText(uuid.uuid4(), "No names here."),
    ]
    graphs = await HeuristicExtractor().extract(chunks)
    assert [g.chunk_id for g in graphs] == [c.chunk_id for c in chunks]
    assert graphs[1].entities == []


def test_normalized_keys() -> None:
    assert normalize_name("  Master  Services Agreement. ", EntityType.NAME) == (
        "master services agreement"
    )
    assert normalize_name("err_4711", EntityType.CODE) == "ERR_4711"
    assert normalize_name("ERR-4711", EntityType.CODE) != normalize_name(
        "ERR_4711", EntityType.CODE
    )


def test_possessives_belong_to_the_name() -> None:
    entities = found(
        "The Customer pays. Data of the Customer's users and the Provider\u2019s staff."
    )
    assert {"Customer", "Provider"} <= set(entities)
    assert not any(name.endswith(("'s", "\u2019s")) for name in entities)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Business Days", "Business Day"),
        ("Retry-After", "retry after"),
        ("Release Notes", "Release Note"),
        ("Data_Retention Policies", "Data Retention Policy"),
        ("Addresses", "Address"),
    ],
)
def test_lexical_variants_share_a_key(a: str, b: str) -> None:
    assert normalize_name(a, EntityType.NAME) == normalize_name(b, EntityType.NAME)


@pytest.mark.parametrize("word", ["Analysis", "Status", "Business", "Bus"])
def test_words_that_only_look_plural_are_kept(word: str) -> None:
    assert normalize_name(word, EntityType.NAME) == word.casefold()


def test_names_that_contain_each_other_are_never_merged() -> None:
    assert contains_other("Customer", "Customer Data")
    assert contains_other("Bank Indonesia", "indonesia")
    assert not contains_other("Netherlands", "Belanda")
    assert not may_merge("Customer", "Customer Data", 0.99, 0.82)
    assert may_merge("Belanda", "Netherlands", 0.88, 0.82)
    assert not may_merge("Belanda", "Netherlands", 0.80, 0.82)
