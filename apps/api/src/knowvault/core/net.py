"""The client's address, also behind trusted reverse proxies."""

import ipaddress
from collections.abc import Sequence

from starlette.requests import Request

Network = ipaddress.IPv4Network | ipaddress.IPv6Network

UNKNOWN_CLIENT = "unknown"


def _trusted(address: str, trusted: Sequence[Network]) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in trusted)


def client_address(request: Request, trusted: Sequence[Network]) -> str:
    """The address of the client that sent the request.

    X-Forwarded-For is read only when the connection comes from a trusted proxy, and from the
    right: each trusted proxy appends the address it received the request from, so the first
    untrusted address is the client. Anything to its left can be set by the client and is
    ignored.
    """
    peer = request.client.host if request.client else UNKNOWN_CLIENT
    if not trusted or not _trusted(peer, trusted):
        return peer
    forwarded = [
        part.strip()
        for header in request.headers.getlist("x-forwarded-for")
        for part in header.split(",")
        if part.strip()
    ]
    for address in reversed(forwarded):
        try:
            ipaddress.ip_address(address)
        except ValueError:
            return peer  # a malformed hop: do not trust anything before it
        if not _trusted(address, trusted):
            return address
    return forwarded[0] if forwarded else peer
