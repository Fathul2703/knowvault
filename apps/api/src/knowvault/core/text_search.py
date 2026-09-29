"""Shared full-text search settings.

`chunks.content_tsv` is built with this configuration and queries must use the same one, or
their lexemes will not match. Changing it requires a migration of the generated column.
"""

# No stemming and no stop words: language-neutral for mixed Indonesian and English documents.
FULLTEXT_CONFIG = "simple"
