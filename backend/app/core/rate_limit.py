import time
from collections import defaultdict
from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, requests_per_minute: int = 30, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self._history: dict[str, list[float]] = defaultdict(list)
        self._lock: Final[object] = object()

    def _cleanup(self, client_ip: str, now: float) -> None:
        window_start = now - self.window_seconds
        self._history[client_ip] = [timestamp for timestamp in self._history.get(client_ip, []) if timestamp > window_start]
        if not self._history[client_ip]:
            self._history.pop(client_ip, None)

    async def dispatch(self, request: Request, call_next):
        if request.url.path.endswith("/files/upload"):
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()
            self._cleanup(client_ip, now)
            timestamps = self._history[client_ip]
            if len(timestamps) >= self.requests_per_minute:
                return JSONResponse(status_code=429, content={"detail": "Too many upload requests"})
            timestamps.append(now)
            self._history[client_ip] = timestamps

        return await call_next(request)
