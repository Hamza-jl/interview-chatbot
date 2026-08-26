"""Fixed-window rate limiting with a pluggable backend.

The in-process store is correct for a single worker and is the default for the
pilot.  ``RateLimiter`` is written against a tiny interface so a Redis store can
be dropped in for a multi-instance deployment without touching call sites.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Tuple

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class Rule:
    limit: int
    window: int

    @classmethod
    def parse(cls, spec: str) -> "Rule":
        limit, _, window = spec.partition("/")
        return cls(int(limit), int(window))


class MemoryStore:
    def __init__(self) -> None:
        self._buckets: Dict[str, Tuple[int, float]] = {}
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def hit(self, key: str, rule: Rule) -> Tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            if now - self._last_sweep > 300:
                self._buckets = {k: v for k, v in self._buckets.items() if v[1] > now}
                self._last_sweep = now

            count, reset_at = self._buckets.get(key, (0, now + rule.window))
            if reset_at <= now:
                count, reset_at = 0, now + rule.window
            count += 1
            self._buckets[key] = (count, reset_at)
            if count > rule.limit:
                return False, max(1, int(reset_at - now))
            return True, 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)


store = MemoryStore()


def client_ip(request: Request) -> str:
    """Trust ``X-Forwarded-For`` only behind a reverse proxy we control."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded and getattr(request.app.state, "trust_proxy", False):
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce(request: Request, bucket: str, spec: str, subject: str = "") -> None:
    rule = Rule.parse(spec)
    key = f"{bucket}:{subject or client_ip(request)}"
    allowed, retry_after = store.hit(key, rule)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de requetes. Merci de patienter avant de reessayer.",
            headers={"Retry-After": str(retry_after)},
        )


def clear(bucket: str, subject: str) -> None:
    store.reset(f"{bucket}:{subject}")
