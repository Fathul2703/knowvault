"""Imports every ORM model so they are registered on `Base.metadata`.

Used by Alembic (migrations/env.py). Add new model modules here.
"""

from knowvault.core import jobs, rate_limit
from knowvault.core.db import Base
from knowvault.modules.assistant.infrastructure import models as assistant_models
from knowvault.modules.graph.infrastructure import models as graph_models
from knowvault.modules.identity import models as identity_models
from knowvault.modules.ingestion.infrastructure import chunks
from knowvault.modules.library import models as library_models

__all__ = [
    "Base",
    "assistant_models",
    "chunks",
    "graph_models",
    "identity_models",
    "jobs",
    "library_models",
    "rate_limit",
]
