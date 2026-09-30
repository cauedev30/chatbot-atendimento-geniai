"""The HTTP client each adapter keeps for the life of the app (see main.py): calls reuse its open
connections instead of opening TCP and TLS every time."""

from http.cookiejar import CookieJar, DefaultCookiePolicy

import httpx


def pooled_client(transport: httpx.AsyncBaseTransport | None, timeout: httpx.Timeout | float) -> httpx.AsyncClient:
    """Keeps no cookie, follows no redirect and has no default header: each call carries only what its
    adapter puts in it, as if it had a client of its own. `transport`: tests pass an httpx.MockTransport."""
    no_cookies = CookieJar(policy=DefaultCookiePolicy(allowed_domains=[]))
    return httpx.AsyncClient(transport=transport, timeout=timeout, cookies=no_cookies, follow_redirects=False)
