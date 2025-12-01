"""
Async rate limiter utilities (RPM-based sliding one-minute windows).
RPM values are pulled from .env via settings so they can be tuned without code changes.
"""
import asyncio
import time
from collections import deque

from almabani.config.settings import get_settings


class AsyncRateLimiter:
    """Asyncio-friendly sliding-window limiter."""
    
    def __init__(self, max_requests_per_minute: int):
        self.max_requests = max_requests_per_minute
        self.window_seconds = 60.0
        self._timestamps = deque()
        self._condition = asyncio.Condition()
    
    async def acquire(self):
        """Await until a request slot is available."""
        async with self._condition:
            while True:
                now = time.monotonic()
                
                while self._timestamps and (now - self._timestamps[0]) > self.window_seconds:
                    self._timestamps.popleft()
                
                if len(self._timestamps) < self.max_requests:
                    self._timestamps.append(now)
                    self._condition.notify_all()
                    return
                
                earliest = self._timestamps[0]
                sleep_for = self.window_seconds - (now - earliest)
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=max(sleep_for, 0.001))
                except asyncio.TimeoutError:
                    continue


_settings = get_settings()
async_embedding_rate_limiter = AsyncRateLimiter(max_requests_per_minute=_settings.embeddings_rpm)
async_chat_rate_limiter = AsyncRateLimiter(max_requests_per_minute=_settings.chat_rpm)
