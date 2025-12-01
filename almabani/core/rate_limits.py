"""
Thread-safe rate limiter utilities.
Enforces a maximum number of requests per rolling minute window.
"""
import time
from collections import deque
from threading import Condition

from almabani.config.settings import get_settings


class RateLimiter:
    """Simple sliding-window rate limiter."""
    
    def __init__(self, max_requests_per_minute: int):
        self.max_requests = max_requests_per_minute
        self.window_seconds = 60.0
        self._timestamps = deque()
        self._condition = Condition()
    
    def acquire(self):
        """Block until a request slot is available."""
        with self._condition:
            while True:
                now = time.monotonic()
                
                # Drop timestamps outside the window
                while self._timestamps and (now - self._timestamps[0]) > self.window_seconds:
                    self._timestamps.popleft()
                
                if len(self._timestamps) < self.max_requests:
                    self._timestamps.append(now)
                    self._condition.notify_all()
                    return
                
                # Wait until the oldest timestamp falls out of the window
                earliest = self._timestamps[0]
                sleep_for = self.window_seconds - (now - earliest)
                self._condition.wait(timeout=max(sleep_for, 0.001))


_settings = get_settings()
embedding_rate_limiter = RateLimiter(max_requests_per_minute=_settings.embeddings_rpm)
chat_rate_limiter = RateLimiter(max_requests_per_minute=_settings.chat_rpm)
