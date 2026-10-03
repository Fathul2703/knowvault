"""Client addresses behind trusted proxies."""

import ipaddress

import pytest
from starlette.requests import Request

from knowvault.core.net import client_address

TRUSTED = (ipaddress.ip_network("10.0.0.0/8"),)


def request(peer: str, *forwarded: str) -> Request:
    headers = [(b"x-forwarded-for", value.encode()) for value in forwarded]
    return Request({"type": "http", "client": (peer, 1234), "headers": headers})


@pytest.mark.parametrize(
    ("peer", "forwarded", "trusted", "expected"),
    [
        # Without trusted proxies the header is ignored.
        ("203.0.113.9", ("1.2.3.4",), (), "203.0.113.9"),
        # An untrusted peer cannot claim another address.
        ("203.0.113.9", ("1.2.3.4",), TRUSTED, "203.0.113.9"),
        # Behind a trusted proxy, the address it saw.
        ("10.0.0.2", ("198.51.100.7",), TRUSTED, "198.51.100.7"),
        # Values a client prepended are ignored; trusted hops are skipped from the right.
        ("10.0.0.2", ("6.6.6.6, 198.51.100.7, 10.0.0.5",), TRUSTED, "198.51.100.7"),
        ("10.0.0.2", ("6.6.6.6", "198.51.100.7"), TRUSTED, "198.51.100.7"),
        # A malformed hop: nothing before it is trusted.
        ("10.0.0.2", ("198.51.100.7, garbage",), TRUSTED, "10.0.0.2"),
        # Only proxies: the left-most address.
        ("10.0.0.2", ("10.0.0.3, 10.0.0.4",), TRUSTED, "10.0.0.3"),
        ("10.0.0.2", (), TRUSTED, "10.0.0.2"),
    ],
)
def test_client_address(
    peer: str,
    forwarded: tuple[str, ...],
    trusted: tuple[ipaddress.IPv4Network, ...],
    expected: str,
) -> None:
    assert client_address(request(peer, *forwarded), trusted) == expected
