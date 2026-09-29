"""Normalisation and chunking: pure functions, no I/O."""

import random
from itertools import pairwise

import pytest

from knowvault.modules.ingestion.domain.chunking import (
    ChunkingConfig,
    chunk_blocks,
    join_blocks,
)
from knowvault.modules.ingestion.domain.model import Block
from knowvault.modules.ingestion.domain.normalize import normalize_blocks, normalize_text

SMALL = ChunkingConfig(target_chars=200, max_chars=300, overlap_chars=40)


class TestNormalize:
    def test_splits_paragraphs_and_collapses_whitespace(self) -> None:
        assert normalize_text("First  line\nwraps here.\n\n\n  Second\tpara.  ") == [
            "First line wraps here.",
            "Second para.",
        ]

    def test_joins_words_hyphenated_across_lines(self) -> None:
        assert normalize_text("exam-\nple and pre-\nWar") == ["example and pre- War"]

    def test_applies_nfc_and_removes_control_characters(self) -> None:
        decomposed = "cafe\u0301\x00\x07 ok\u00a0here"
        assert normalize_text(decomposed) == ["café ok here"]

    def test_blocks_keep_location_and_drop_empty_text(self) -> None:
        blocks = normalize_blocks(
            [
                Block("One.\n\nTwo.", page=3, heading_path=("  Intro ",)),
                Block("   \n\n  ", page=4),
            ]
        )
        assert blocks == [
            Block("One.", page=3, heading_path=("Intro",)),
            Block("Two.", page=3, heading_path=("Intro",)),
        ]


def _random_text(seed: int, words: int) -> str:
    rng = random.Random(seed)
    tokens = []
    for i in range(words):
        word = "".join(rng.choice("abcdefghijklmnop") for _ in range(rng.randint(1, 10)))
        tokens.append(word + ("." if rng.random() < 0.08 else ""))
        if i % 97 == 96:
            tokens.append("\n\n")
    return " ".join(tokens)


def _covered(chunks: list[tuple[int, int]], length: int) -> list[bool]:
    covered = [False] * length
    for start, end in chunks:
        for i in range(start, end):
            covered[i] = True
    return covered


class TestChunking:
    def test_short_document_is_one_chunk(self) -> None:
        chunks = chunk_blocks([Block("Hello world.", page=1)], SMALL)
        assert len(chunks) == 1
        assert chunks[0].content == "Hello world."
        assert (chunks[0].page_start, chunks[0].page_end) == (1, 1)
        assert chunks[0].ordinal == 0

    def test_config_is_validated(self) -> None:
        with pytest.raises(ValueError, match="overlap_chars"):
            ChunkingConfig(target_chars=100, max_chars=90, overlap_chars=10)

    @pytest.mark.parametrize("seed", range(8))
    def test_properties_hold_for_random_documents(self, seed: int) -> None:
        rng = random.Random(seed)
        blocks = normalize_blocks(
            [
                Block(
                    _random_text(seed * 10 + i, rng.randint(5, 400)),
                    page=i + 1,
                    heading_path=(f"Section {i // 3}",),
                )
                for i in range(rng.randint(1, 12))
            ]
        )
        chunks = chunk_blocks(blocks, SMALL)
        text = join_blocks(blocks)

        for i, chunk in enumerate(chunks):
            assert chunk.ordinal == i
            assert 0 < len(chunk.content) <= SMALL.max_chars
            assert chunk.content == text[chunk.char_start : chunk.char_end]
        # Chunks advance through the text.
        starts = [c.char_start for c in chunks]
        assert starts == sorted(starts)
        assert len(set(starts)) == len(starts)
        # No text is lost: every non-whitespace character is in some chunk.
        covered = _covered([(c.char_start, c.char_end) for c in chunks], len(text))
        assert all(covered[i] for i, ch in enumerate(text) if not ch.isspace())

    def test_chunks_do_not_cross_sections(self) -> None:
        blocks = [
            Block("Alpha sentence one. " * 5, heading_path=("A",)),
            Block("Beta sentence one. " * 5, heading_path=("B",)),
        ]
        chunks = chunk_blocks(normalize_blocks(blocks), SMALL)
        assert {c.heading_path for c in chunks} == {("A",), ("B",)}
        for chunk in chunks:
            assert ("Alpha" in chunk.content) != ("Beta" in chunk.content)

    def test_consecutive_chunks_overlap_within_budget(self) -> None:
        sentences = " ".join(f"Sentence number {i} is here." for i in range(60))
        chunks = chunk_blocks(normalize_blocks([Block(sentences)]), SMALL)
        assert len(chunks) > 2
        for previous, current in pairwise(chunks):
            overlap = previous.char_end - current.char_start
            assert 0 < overlap <= SMALL.overlap_chars

    def test_overlong_sentence_is_split_at_spaces(self) -> None:
        long_sentence = " ".join(["word"] * 200)  # ~1000 chars, no sentence boundary
        chunks = chunk_blocks([Block(long_sentence)], SMALL)
        assert len(chunks) > 1
        assert all(len(c.content) <= SMALL.max_chars for c in chunks)
        assert all(not c.content.startswith(" ") and "wor d" not in c.content for c in chunks)

    def test_text_without_spaces_is_hard_split(self) -> None:
        chunks = chunk_blocks([Block("x" * 1000)], SMALL)
        assert all(len(c.content) <= SMALL.max_chars for c in chunks)
        assert chunks[-1].char_end == 1000

    def test_page_range_spans_the_pages_in_the_chunk(self) -> None:
        blocks = [Block(f"Page {n} text.", page=n) for n in (4, 5, 6)]
        chunks = chunk_blocks(blocks, SMALL)
        assert len(chunks) == 1
        assert (chunks[0].page_start, chunks[0].page_end) == (4, 6)

    def test_empty_input_produces_no_chunks(self) -> None:
        assert chunk_blocks([], SMALL) == []
