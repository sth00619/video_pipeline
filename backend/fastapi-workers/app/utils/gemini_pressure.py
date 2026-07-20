"""Shared Gemini burst limiter with conservative outage back-pressure."""
from __future__ import annotations

import threading
import time
from collections import deque

from app import runtime_config


class GeminiPressureController:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: deque[float] = deque()
        self._outcomes: deque[tuple[float, bool]] = deque()

    def acquire(self) -> None:
        """Limit bursts to the configured rolling RPM, with outage cooldown."""
        while True:
            with self._lock:
                now = time.monotonic()
                while self._requests and now - self._requests[0] >= 60:
                    self._requests.popleft()
                cap = max(1, int(runtime_config.value("gemini_rpm_soft_cap")))
                if len(self._requests) < cap:
                    self._requests.append(now)
                    outcomes = [failed for at, failed in self._outcomes if now - at < 60]
                    overloaded = len(outcomes) >= 10 and sum(outcomes) / len(outcomes) > .30
                    break
                wait = max(.1, 60 - (now - self._requests[0]))
            time.sleep(min(wait, 2.0))
        if overloaded and bool(runtime_config.value("gemini_adaptive_backoff_enabled")):
            # Eight workers remain available, but their next requests are
            # staggered during a provider outage instead of creating a burst.
            time.sleep(1.5)

    def outcome(self, error: str | None = None) -> None:
        now = time.monotonic()
        transient = bool(error and ("429" in error or "503" in error))
        with self._lock:
            self._outcomes.append((now, transient))
            while self._outcomes and now - self._outcomes[0][0] >= 60:
                self._outcomes.popleft()

    def recommended_concurrency(self, configured: int) -> int:
        """Halve new/recovery fan-out after a sustained transient failure rate."""
        with self._lock:
            now = time.monotonic()
            recent = [failed for at, failed in self._outcomes if now - at < 60]
        if (
            bool(runtime_config.value("gemini_adaptive_backoff_enabled"))
            and len(recent) >= 10
            and sum(recent) / len(recent) >= .30
        ):
            return max(1, configured // 2)
        return configured


gemini_pressure = GeminiPressureController()
