"""Login attempts per client address: after too many failures in a window, the login answers 429.

Per address, not global: a global limit would lock the whole team out. The browser reaches the backend
through the frontend's /api proxy, so the peer is the frontend; the client address then comes from
X-Forwarded-For, read only when the peer is a trusted proxy (TRUSTED_PROXY_IPS). Only a reverse proxy in
front of the frontend sets that header; without one, a request from the trusted frontend carries no
usable client address. Those requests share one key and are slowed down (1 s per recent failure, up to
5 s) instead of refused, so a stranger's failures cannot lock the team out.
"""

import time
from collections import deque
from collections.abc import Callable
from ipaddress import IPv4Network, IPv6Network, ip_address
from typing import Final

LOGIN_MAX_FAILURES: Final = 10
LOGIN_WINDOW_S: Final = 15 * 60
TOO_MANY_ATTEMPTS: Final = "Muitas tentativas de login. Aguarde alguns minutos e tente de novo."
UNIDENTIFIED: Final = "unidentified"
"""The key of the requests with no usable client address."""
DELAY_STEP_S: Final = 1.0
MAX_DELAY_S: Final = 5.0

Network = IPv4Network | IPv6Network


def _is_trusted(address: str, trusted: tuple[Network, ...]) -> bool:
    try:
        ip = ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in trusted)


def _is_address(value: str) -> bool:
    try:
        ip_address(value)
    except ValueError:
        return False
    return True


def client_ip(peer: str | None, forwarded_for: str | None, trusted: tuple[Network, ...]) -> str | None:
    """The peer, unless it is a trusted proxy: then the rightmost X-Forwarded-For entry that is not a
    trusted proxy. Entries on the left are whatever the client sent, so they are never believed. None when
    there is no usable client address: no peer, or a trusted proxy that forwarded none."""
    if peer is None:
        return None
    if not _is_trusted(peer, trusted):
        return peer
    for entry in reversed([e.strip() for e in (forwarded_for or "").split(",") if e.strip()]):
        if not _is_trusted(entry, trusted):
            return entry if _is_address(entry) else None
    return None


class LoginLimiter:
    """Failed logins per key in a sliding window, in memory (one worker)."""

    def __init__(
        self,
        max_failures: int = LOGIN_MAX_FAILURES,
        window_s: float = LOGIN_WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
        delay_step_s: float = DELAY_STEP_S,
        max_delay_s: float = MAX_DELAY_S,
    ) -> None:
        self._max = max_failures
        self._delay_step_s = delay_step_s
        self._max_delay_s = max_delay_s
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

    def delay_s(self, key: str) -> float:
        """How long to hold a login with no usable address: grows with the recent failures, never refused."""
        return min(len(self._recent(key)) * self._delay_step_s, self._max_delay_s)

    def fail(self, key: str) -> None:
        self._failures[key] = self._recent(key)
        self._failures[key].append(self._clock())

    def succeed(self, key: str) -> None:
        self._failures.pop(key, None)
