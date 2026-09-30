"""The HTTP client each adapter keeps for the life of the app (see main.py): calls reuse its open
connections instead of opening TCP and TLS every time."""

from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Final

import httpx

KEEPALIVE_S: Final = 50
"""How long an idle connection is kept for the next call. httpx's default (5 s) would drop it between
two turns of a conversation; this stays under the 60 s idle limit common in proxies. A connection the
server closed earlier is noticed and replaced before it is used."""


def pooled_client(transport: httpx.AsyncBaseTransport | None, timeout: httpx.Timeout | float) -> httpx.AsyncClient:
    """Keeps no cookie, follows no redirect and has no default header: each call carries only what its
    adapter puts in it, as if it had a client of its own. `transport`: tests pass an httpx.MockTransport."""
    no_cookies = CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))
    return httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        cookies=no_cookies,
        follow_redirects=False,
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=KEEPALIVE_S),
    )
