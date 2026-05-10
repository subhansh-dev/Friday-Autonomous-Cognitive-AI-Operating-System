"""
security/tools_guard.py — Guards for tool inputs
Prevents SSRF, rate abuse, and path traversal attacks.
"""

import re
import time
import threading
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional


# ── SSRF Protection ──────────────────────────────────────────────────

_PRIVATE_NETS = [
    "127.", "10.", "192.168.",
    "172.16.", "172.17.", "172.18.", "172.19.", "172.20.",
    "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
    "0.", "169.254.", "::1", "fc00:", "fe80:",
]

_BLOCKED_HOSTS = {
    "localhost", "metadata.google.internal",
    "instance-data", "169.254.169.254",
}

_BLOCKED_PORTS = {22, 23, 25, 445, 3389, 5900, 6379, 27017}


def check_ssrf(url: str) -> Optional[str]:
    """Check if a URL targets an internal/private network. Returns error or None."""
    if not url:
        return None

    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
    except Exception:
        return "Invalid URL format."

    hostname = (parsed.hostname or "").lower()
    port = parsed.port

    if not hostname:
        return "URL has no hostname."

    if hostname in _BLOCKED_HOSTS:
        return f"Blocked: '{hostname}' is a local/metadata endpoint."

    for prefix in _PRIVATE_NETS:
        if hostname.startswith(prefix):
            return f"Blocked: '{hostname}' is a private network address."

    if port and port in _BLOCKED_PORTS:
        return f"Blocked: port {port} is not allowed for external requests."

    return None


# ── Rate Limiting ────────────────────────────────────────────────────

class RateLimiter:
    """Per-tool rate limiter using sliding window."""

    def __init__(self):
        self._lock = threading.Lock()
        self._windows: dict[str, list[float]] = {}

    def check(self, tool_name: str, max_calls: int = 30, window_seconds: int = 60) -> Optional[str]:
        """Check if a tool call exceeds rate limit. Returns error or None."""
        now = time.time()
        with self._lock:
            if tool_name not in self._windows:
                self._windows[tool_name] = []

            window = self._windows[tool_name]
            # Prune old entries
            cutoff = now - window_seconds
            self._windows[tool_name] = [t for t in window if t > cutoff]
            window = self._windows[tool_name]

            if len(window) >= max_calls:
                return (f"Rate limit exceeded for '{tool_name}': "
                        f"{len(window)} calls in {window_seconds}s (max {max_calls}).")

            window.append(now)
            return None


# ── Path Traversal Protection ────────────────────────────────────────

_TRAVERSAL_PATTERNS = re.compile(
    r'(\.\.[\\/]|[\\/]\.\.|^\.\.$|^~[\\/]|'
    r'%2e%2e|%252e|%c0%ae|%c1%9c)',
    re.IGNORECASE,
)

_SENSITIVE_DIRS = {
    "c:\\windows\\system32", "c:\\windows\\syswow64",
    "/etc", "/var/log", "/proc", "/sys", "/dev",
    "~/.ssh", "~/.aws", "~/.config",
}


def check_path_traversal(path: str) -> Optional[str]:
    """Check if a path attempts directory traversal. Returns error or None."""
    if not path:
        return None

    if _TRAVERSAL_PATTERNS.search(path):
        return f"Path traversal detected in: '{path}'"

    try:
        resolved = Path(path).resolve()
        resolved_str = str(resolved).lower()
        for sensitive in _SENSITIVE_DIRS:
            if resolved_str.startswith(sensitive):
                return f"Access to sensitive directory blocked: '{resolved}'"
    except Exception:
        pass

    return None


# ── Singleton ────────────────────────────────────────────────────────

_limiter: Optional[RateLimiter] = None
_limiter_lock = threading.Lock()


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                _limiter = RateLimiter()
    return _limiter
