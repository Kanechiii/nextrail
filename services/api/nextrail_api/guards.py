"""Bounded per-instance API request throttling for local and single-worker use."""
import time

from fastapi import HTTPException, Request


class FixedWindowLimiter:
    """Do not trust proxy-forwarded IP headers; isolate counts by request route."""

    def __init__(self, clock=None, max_keys=4096):
        self.clock = time.monotonic if clock is None else clock
        self.max_keys = max_keys
        self._entries = {}

    def enforce(self, request: Request, route: str, limit: int, seconds: int = 60):
        address = request.client.host if request.client else "unknown"
        key = (route, address)
        now = self.clock()
        slot = int(now // seconds)
        if key not in self._entries and len(self._entries) >= self.max_keys:
            self._entries = {
                item: count for item, count in self._entries.items()
                if count[0] == slot
            }
        if key not in self._entries and len(self._entries) >= self.max_keys:
            raise HTTPException(
                429, "Request capacity exceeded", headers={"Retry-After": str(seconds)}
            )
        old_slot, used = self._entries.get(key, (slot, 0))
        used = used + 1 if old_slot == slot else 1
        self._entries[key] = (slot, used)
        if used > limit:
            retry = max(1, int((slot + 1) * seconds - now) + 1)
            raise HTTPException(
                429, "Too many requests", headers={"Retry-After": str(retry)}
            )
