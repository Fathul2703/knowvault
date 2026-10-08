"""Request dependencies of the retrieval module."""

from typing import Annotated

from fastapi import Depends, Request

from knowvault.modules.retrieval.application.search import EntityLinks


def get_entity_links(request: Request) -> EntityLinks | None:
    """Graph retrieval as wired by the application; None when it is off."""
    links: EntityLinks | None = getattr(request.app.state, "entity_links", None)
    return links


EntityLinksDep = Annotated[EntityLinks | None, Depends(get_entity_links)]
