"""
security/input_sanitizer.py — Input sanitization for tool parameters
"""

import re
from typing import Optional


# ── Shell Injection ──────────────────────────────────────────────────

_SHELL_INJECTION_RE = re.compile(
    r'[;&|`$(){}\n\r]|'
    r'\$\(|'
    r'`[^`]*`|'
    r'\|\||'
    r'&&',
)


def sanitize_shell_input(text: str) -> Optional[str]:
    """Check for shell injection patterns. Returns error or None."""
    if not text:
        return None
    if _SHELL_INJECTION_RE.search(text):
        return "Input contains potentially dangerous shell characters."
    return None


# ── SQL Injection ────────────────────────────────────────────────────

_SQL_INJECTION_RE = re.compile(
    r"(\b(union\s+select|drop\s+table|delete\s+from|insert\s+into|"
    r"update\s+\w+\s+set|exec\s*\(|execute\s*\(|xp_)|"
    r"(--|;--|/\*|\*/|'\s*or\s+'|'\s*or\s+\d))",
    re.IGNORECASE,
)


def sanitize_sql_input(text: str) -> Optional[str]:
    """Check for SQL injection patterns. Returns error or None."""
    if not text:
        return None
    if _SQL_INJECTION_RE.search(text):
        return "Input contains potentially dangerous SQL patterns."
    return None


# ── URL Validation ───────────────────────────────────────────────────

_VALID_URL_SCHEMES = {"http", "https"}


def validate_url(url: str) -> Optional[str]:
    """Validate a URL is well-formed and uses an allowed scheme. Returns error or None."""
    if not url:
        return None
    url = url.strip()
    if len(url) > 2048:
        return "URL too long (max 2048 characters)."
    # Basic scheme check
    for scheme in _VALID_URL_SCHEMES:
        if url.lower().startswith(f"{scheme}://"):
            return None
    if url.startswith("//"):
        return None  # Protocol-relative URLs are OK
    return f"URL must start with http:// or https://."


# ── General Input Length ─────────────────────────────────────────────

MAX_INPUT_LENGTH = 10000


def check_input_length(text: str, max_len: int = MAX_INPUT_LENGTH) -> Optional[str]:
    """Check if input exceeds maximum length. Returns error or None."""
    if text and len(text) > max_len:
        return f"Input too long ({len(text)} chars, max {max_len})."
    return None
