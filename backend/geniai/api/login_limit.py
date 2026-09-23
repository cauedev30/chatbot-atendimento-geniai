"""Login attempts per client address: after too many failures in a window, the login answers 429.

Per address, not global: a global limit would lock the whole team out. The browser reaches the backend
through the frontend's /api proxy, so the peer is the frontend; the client address then comes from
X-Forwarded-For, read only when the peer is a trusted proxy (TRUSTED_PROXY_IPS).
"""

import time
from collections import deque
from collections.abc import Callable
from ipaddress import IPv4Network, IPv6Network, ip_address
from typing import Final

LOGIN_MAX_FAILURES: Final = 10
LOGIN_WINDOW_S: Final = 15 * 60
TOO_MANY_ATTEMPTS: Final = "Muitas tentativas de login. Aguarde alguns minutos e tente de novo."

Network = IPv4Network | IPv6Network


def _is_trusted(address: str, trusted: tuple[Network, ...]) -> bool:
    try:
        ip = ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in trusted)


def client_ip(peer: str | None, forwarded_for: str | None, trusted: tuple[Network, ...]) -> str:
    """The peer, unless it is a trusted proxy: then the rightmost X-Forwarded-For entry that is not a
    trusted proxy. Entries on the left are whatever the client sent, so they are never believed."""
    if peer is None:
        return "unknown"
    if not _is_trusted(peer, trusted) or not forwarded_for:
        return peer
    for entry in reversed([e.strip() for e in forwarded_for.split(",") if e.strip()]):
        if not _is_trusted(entry, trusted):
            return entry
    return peer


class LoginLimiter:
    """Failed logins per key in a sliding window, in memory (one worker)."""

    def __init__(
        self,
        max_failures: int = LOGIN_MAX_FAILURES,
        window_s: float = LOGIN_WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_failures
        self._window_s = window_s
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}

    def _recent(self, key: str) -> deque[float]:
        failures = self._failures.get(key, deque())
        cutoff = self._clock() - self._window_s
        while failures and failures[0] <= cutoff:
            failures.popleft()
        if not failures:
            self._failures.pop(key, None)
        return failures

    def blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self._max

    def fail(self, key: str) -> None:
        self._failures[key] = self._recent(key)
        self._failures[key].append(self._clock())

    def succeed(self, key: str) -> None:
        self._failures.pop(key, None)
