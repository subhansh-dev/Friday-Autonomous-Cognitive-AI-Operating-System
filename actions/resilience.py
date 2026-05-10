# -*- coding: utf-8 -*-
"""
resilience.py — Shared utilities for path normalization and API retry logic.
Fixes:
  1. Cross-platform path handling (Windows <-> WSL)
  2. Gemini API 429 RESOURCE_EXHAUSTED with exponential backoff
"""

import os
import platform
import re
import time
from pathlib import Path, PureWindowsPath, PurePosixPath
from typing import Optional


# ── Cross-Platform Path Normalization ──────────────────────────────────

_WIN_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")
_WSL_MOUNT_RE = re.compile(r"^/mnt/([a-z])/(.*)$")


def _is_windows() -> bool:
    return platform.system() == "Windows"


def _is_wsl() -> bool:
    """Detect if running inside WSL."""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def normalize_path(target: str) -> tuple[Path, Optional[str]]:
    """
    Normalize a target path for the current OS.

    Returns:
        (resolved_path, error_message_or_None)

    Strategy:
        - On Windows: keep Windows paths as-is, convert WSL paths to Windows
        - On Linux/WSL: convert Windows paths to WSL mount paths
        - Always expand ~ and resolve relative paths
    """
    if not target:
        return Path(), "No target path specified."

    target = target.strip().strip("'\"")

    # Expand ~
    if target.startswith("~"):
        target = os.path.expanduser(target)

    system = platform.system()

    # ── Running on Windows ──────────────────────────────────────────
    if system == "Windows":
        # Check for WSL-style path (/mnt/c/...)
        wsl_match = _WSL_MOUNT_RE.match(target)
        if wsl_match:
            drive = wsl_match.group(1).upper()
            rest = wsl_match.group(2).replace("/", "\\")
            win_path = f"{drive}:\\{rest}"
            resolved = Path(win_path)
            if resolved.exists():
                return resolved, None
            # Return the converted path even if it doesn't exist yet
            return resolved, f"WSL path converted to Windows: {win_path}"

        # Normal Windows path — Path handles it natively
        resolved = Path(target).expanduser().resolve()
        return resolved, None

    # ── Running on Linux / WSL ──────────────────────────────────────
    elif system == "Linux":
        # Check for Windows-style path (C:\Users\... or C:/Users/...)
        win_match = _WIN_DRIVE_RE.match(target)
        if win_match:
            drive = win_match.group(1).lower()
            rest = win_match.group(2).replace("\\", "/")
            wsl_path = f"/mnt/{drive}/{rest}"
            resolved = Path(wsl_path)
            if resolved.exists():
                return resolved, None
            # Also try raw path (maybe it's a relative path that looks like a drive)
            raw = Path(target)
            if raw.exists():
                return raw, None
            return resolved, (
                f"Windows path '{target}' -> WSL path '{wsl_path}' (not found). "
                f"Ensure the drive is mounted in WSL."
            )

        # Normal Linux path
        resolved = Path(target).expanduser().resolve()
        return resolved, None

    else:
        # macOS or other
        resolved = Path(target).expanduser().resolve()
        return resolved, None


def validate_target_path(target: str) -> tuple[Path, Optional[str]]:
    """
    Normalize AND verify the path exists.
    Returns (path, error_msg_or_None).
    """
    path, err = normalize_path(target)
    if err:
        return path, err
    if not path.exists():
        return path, f"Target path not found: {path}"
    return path, None


def to_wsl_path(windows_path: str) -> str:
    """Convert a Windows path to WSL /mnt/ format."""
    match = _WIN_DRIVE_RE.match(windows_path)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{rest}"
    return windows_path.replace("\\", "/")


def to_windows_path(wsl_path: str) -> str:
    """Convert a WSL /mnt/ path to Windows format."""
    match = _WSL_MOUNT_RE.match(wsl_path)
    if match:
        drive = match.group(1).upper()
        rest = match.group(2).replace("/", "\\")
        return f"{drive}:\\{rest}"
    return wsl_path


# ── API Retry with Exponential Backoff ─────────────────────────────────

_RETRYABLE_CODES = {429, 500, 502, 503, 504}
_RETRYABLE_MESSAGES = [
    "resource_exhausted",
    "rate limit",
    "quota exceeded",
    "too many requests",
    "service unavailable",
    "internal error",
    "deadline exceeded",
    "timeout",
    "429",
    "500",
    "502",
    "503",
    "504",
]


def is_retryable(error: Exception) -> bool:
    """Check if an API error is retryable."""
    err_str = str(error).lower()
    return any(msg in err_str for msg in _RETRYABLE_MESSAGES)


def extract_retry_after(error: Exception) -> Optional[float]:
    """Try to extract Retry-After value from error."""
    err_str = str(error)
    match = re.search(r"retry[._\s-]?after[:\s]+(\d+)", err_str, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def api_retry(
    fn,
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    on_retry: Optional[callable] = None,
):
    """
    Execute an API call with exponential backoff on retryable errors.

    Args:
        fn: Callable to execute
        max_retries: Maximum retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay cap
        on_retry: Optional callback(attempt, delay, error) for logging

    Returns:
        The result of fn()

    Raises:
        The last exception if all retries exhausted
    """
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_error = e

            if attempt >= max_retries:
                raise

            if not is_retryable(e):
                raise

            # Calculate delay
            retry_after = extract_retry_after(e)
            if retry_after:
                delay = min(retry_after, max_delay)
            else:
                delay = min(base_delay * (2 ** attempt), max_delay)

            if on_retry:
                on_retry(attempt + 1, delay, e)

            time.sleep(delay)

    raise last_error  # Safety net
