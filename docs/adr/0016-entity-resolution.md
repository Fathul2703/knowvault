# ADR 0016: Entity resolution — lexical keys, then guarded name similarity

- Status: Accepted
- Date: 2026-10-08

## Context

The rule-based extractor (ADR 0015) keyed entities by their case-insensitive name. The same
thing written differently became separate entities: "Business Day" and "Business Days",
"Retry-After" and "Retry After", or "Netherlands" and "Belanda" in a bilingual library. The
architecture planned resolution by normalisation and embedding similarity (§5).

Merging is asymmetric in its risk. A missed merge leaves a duplicate node. A wrong merge puts
"Customer" and "Customer Data", or "Bank Indonesia" and "Indonesia", into one entity, and every
relation and citation of either then points at the wrong thing.

## Decision

1. **Lexical key for names.** Case, hyphens, underscores and slashes, surrounding punctuation,
   and an English plural on the last word do not matter. Rules: policies → policy,
   addresses → address, days → day; words ending in -ss, -us or -is are kept. Codes keep their
   exact characters (`ERR_4711` ≠ `ERR-4711`).
2. **Similarity for names that have no key match.** When a newly found name matches no
   existing key or alias, its bge-m3 embedding is compared with the owner's entities of the same
   type. It joins the nearest one if:
   - the cosine similarity is at least `GRAPH_MERGE_THRESHOLD` (default 0.82), and
   - neither name contains all the words of the other. That guard keeps "Customer" apart from
     "Customer Data".

   The merged spelling is recorded in `entity_aliases` with its similarity, so later mentions
   find it directly, and the entity API lists it. The first spelling seen names the entity.
3. **Codes are never merged by similarity.** `ERR_4711` and `ERR_4712` look alike and differ.
4. **Name embeddings are computed outside any transaction** with the worker's single embedding
   model instance. Entities store their embedding and model; comparisons only use embeddings
   from the same model. `GRAPH_MERGE_THRESHOLD=1` turns similarity merging off.

## Measurements

36 labelled pairs of names (`eval/datasets/entity-pairs.jsonl`): 18 that denote the same
entity (case, plural, punctuation, long forms, cross-lingual, abbreviations) and 18 that do not
(related, sharing a word, the same kind of thing). `knowvault eval-entities`, bge-m3
([report](../../eval/reports/2026-10-08-0820-entities.md)):

| Rule | Merged correctly | Merged wrongly | Missed | Precision | Recall |
|---|---|---|---|---|---|
| Case-insensitive key (before) | 3 | 0 | 15 | 100% | 17% |
| Lexical key | 8 | 0 | 10 | 100% | 44% |
| **Lexical key + similarity ≥ 0.82 with the guard** | **12** | **0** | 6 | **100%** | **67%** |

- **What the similarity adds:** cross-lingual names (Netherlands/Belanda 0.876, Finance
  Team/Tim Keuangan 0.831) and a plural inside a name (Master Services/Service Agreement).
- **What the guard is for.** Without it the threshold cannot go lower: Customer/Customer Data
  scores 0.815. With it, 0.78 would also merge Human Resources/Sumber Daya Manusia (0.784), but
  the closest pair of different names left (Public API/Partner API, 0.762) would then be 0.018
  away. The default keeps a margin of 0.058.
- **Still missed:** abbreviations (BI, ISO: 0.45–0.58), long forms that contain the short name
  (DKI Jakarta, Republik Indonesia — the guard keeps them apart on purpose), and Kantor
  Pusat/Head Office (0.674).
- **On the evaluation corpus** (31 documents): 66 entities instead of 69. Lexical keys merged
  plural and possessive variants, no name was merged by similarity, and Customer and Customer
  Data stayed apart. The corpus has few names written in two languages.

## Consequences

- Keys of existing names change, so the new keys apply as documents are extracted again
  (`knowvault extract-graph`); old entities without mentions are removed.
- The pairs are few and written by hand. The threshold should be revisited with pairs from real
  libraries, or decided by a language-model extractor that can tell kinds of entities apart.
- Abbreviations need context that a name alone does not carry; they are left to a model-based
  extractor.
