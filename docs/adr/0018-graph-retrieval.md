# ADR 0018: Graph-augmented retrieval — built, measured, off by default

- Status: Accepted
- Date: 2026-10-08

## Context

Phase 5 plans retrieval that uses the knowledge graph: expand the search through the entities
of the question and their neighbours, and keep it only if it beats the hybrid baseline (§5).

The graph comes from the offline heuristic extractor (ADR 0015) with entity resolution
(ADR 0016). Its entities are codes and capitalised names; its relations are co-occurrence in a
passage.

Hybrid search already finds a relevant passage in the top 5 for every answerable question of the
evaluation set (Success@5 100%). The only room left is the order at the top (Success@1, MRR).

## Decision

### 1. The graph as a third ranked list

Hybrid search fuses three ranked lists with RRF (ADR 0006): vector, full text, and graph.

- **Linking the question to entities.** Every run of up to six words of the question is turned
  into an entity key with the same normalisation as entities (case, hyphens, plurals,
  possessives), and the keys are looked up among the user's entities and aliases. Nothing guesses
  which words are names; only names that exist in the user's graph match.
- **Scoring passages.** A passage scores the sum of the inverse document frequencies of the named
  entities it mentions, so a rare code counts more than a name found everywhere.
- **`neighbours`.** Also counts the five entities most often mentioned with each named entity,
  at half weight.
- **No named entity, no change.** When the question names no known entity, the list is empty and
  the fusion is exactly the plain hybrid one.

### 2. Module boundaries

- The retrieval module defines the port `EntityLinks`.
- The graph module implements it (`PostgresEntityLinks`).
- `main.py` and the evaluation wire it in. Retrieval still does not import the graph, and the
  14 import contracts are unchanged.

### 3. Setting: `GRAPH_RETRIEVAL=none|entities|neighbours`, default `none`

### 4. Evaluation compares variants on one database

`eval-retrieval --graph-variants none entities neighbours` adds a hybrid run per setting on the
same database.

The first attempt compared separate runs, and that did not work:

- Questions changed rank even where the graph list was empty.
- Every ingestion gives chunks new random ids, and ids break ties in full-text ranking and in
  the fusion.
- Plain hybrid scored 84.7% in one run and 87.4% in another.

Within one run, the variant without the graph repeats plain hybrid exactly (checked in the
report and in a test).

## Measurements

The evaluation set has 124 questions (111 answerable). The model is bge-m3 int8, with chunks of
1000/1400/150 characters. Two independent runs: `eval/reports/2026-10-08-0911-retrieval-graph-run1`
and `…-0912-…-run2`.

| Variant | Run 1 Success@1 | Run 1 MRR@10 | Run 2 Success@1 | Run 2 MRR@10 |
|---|---|---|---|---|
| hybrid (no graph) | **87.4%** | **0.933** | **84.7%** | **0.919** |
| + graph (entities) | 83.8% | 0.914 | 82.9% | 0.908 |
| + graph (neighbours) | 84.7% | 0.917 | 82.9% | 0.908 |

- **Scale and cost:**
  - Success@5 and Success@10 stay at 100% in every variant.
  - The graph list was non-empty for 31 of 124 questions.
  - Latency changes by a few milliseconds (p50 52 → 55–56 ms in run 1).
- **Where it loses** (MRR@10, by category):
  - Distractors fall from 0.917 to 0.764–0.875.
    - "Berapa lama kenaikan kuota sementara untuk API partner bisa berlaku?" names "API", which
      both the public and the partner API documents mention.
    - Its rank falls from 1 to 4–5.
  - Unstructured documents fall from 0.919 to 0.833–0.859 (run 1).
    - A name repeated in every passage of a long document ("cover crop", "services agreement")
      promotes the wrong passage of the right document.
- **Where it wins:**
  - "When do invoices under the services agreement have to be paid?" improves from rank 5 to 3.
  - An error-code question improves from rank 2 to 1 in run 2.
  - Identifiers improve slightly in run 2 (0.976 → 1.000) and drop slightly in run 1.

The graph signal mostly repeats what full-text search already contributes: a passage mentions
the name in the question. Counted a second time, that lexical evidence outweighs meaning exactly
where meaning matters, in distractors and in long documents with a recurring name.

## Consequences

- **Kept:**
  - The retrieval port, its implementation and the evaluation variants.
  - Graph retrieval stays off. Turning it on is one setting, and measuring it again is one
    command.
- **Not concluded:**
  - The graph is not useless for retrieval in general.
  - The evaluation set has no questions that need two hops ("which team owns the service that
    raises ERR_4711?"), which is where a graph should help.
  - The relations are co-occurrence, not meanings.
  - Writing such questions now, after seeing these results, would tune the set to the feature.
    They belong in the next dataset revision, written before the next measurement.
- **Revisit when** a language-model extractor gives typed relations, or the dataset gains
  multi-hop questions. Measure with `--graph-variants`, and turn the setting on only if Success@1
  improves within the same run.
