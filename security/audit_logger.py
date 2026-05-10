import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


SENSITIVE_PATTERNS = [
    # Key-value patterns: api_key=xxx, token: "xxx", etc.
    re.compile(
        r'(api_key|apikey|token|secret|password|credential|auth|jwt|bearer)'
        r'\s*[=:=\s]+[\'"]?([\w\-._~+/]{8,})[\'"]?',
        re.IGNORECASE,
    ),
    # Email addresses
    re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'),
    # Bearer tokens and JWTs (eyJ...)
    re.compile(r'(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})'),
]

SENSITIVE_KEYS = {
    "gemini_api_key", "api_key", "apikey", "token", "secret",
    "password", "ac_password", "ac_email", "bot_token",
    "access_token", "refresh_token", "auth_token", "session_key",
    "private_key", "api_secret", "client_secret",
}

AUDIT_LOG_KEYS = {
    "message_text", "code", "content", "password", "token",
    "api_key", "secret", "value",
}

# Log rotation: keep files for this many days
LOG_RETENTION_DAYS = 30


def _is_sensitive_key(key: str) -> bool:
    k = key.lower().strip()
    return any(sk in k for sk in SENSITIVE_KEYS)


def _redact_value(key: str, value) -> str:
    if _is_sensitive_key(key):
        return "***REDACTED***"
    if isinstance(value, str) and len(value) > 120:
        return value[:60] + "... [truncated]"
    s = str(value)
    for pat in SENSITIVE_PATTERNS:
        if pat.search(s):
            return "***REDACTED***"
    return s


def redact_params(params: dict) -> dict:
    if not params:
        return {}
    redacted = {}
    for k, v in params.items():
        if k in AUDIT_LOG_KEYS:
            redacted[k] = "***REDACTED***"
        else:
            redacted[k] = _redact_value(k, v)
    return redacted


class AuditLogger:
    def __init__(self, log_dir: Optional[Path] = None):
        self._lock = threading.Lock()
        self._log_dir = log_dir or (Path(__file__).resolve().parent.parent / "logs")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._entries: list[dict] = []
        self._write_lock = threading.Lock()
        self._flush_interval = 10
        self._last_flush = time.time()
        self._flush_thread = None
        self._stop_event = threading.Event()
        self._start_background_flush()
        self._rotate_old_logs()

    def _start_background_flush(self):
        def _flush_loop():
            while not self._stop_event.is_set():
                self._stop_event.wait(self._flush_interval)
                if not self._stop_event.is_set():
                    self.flush()
        self._flush_thread = threading.Thread(target=_flush_loop, daemon=True)
        self._flush_thread.start()

    def _rotate_old_logs(self):
        """Remove audit log files older than LOG_RETENTION_DAYS."""
        try:
            cutoff = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
            for f in self._log_dir.glob("audit_*.jsonl"):
                try:
                    # Extract date from filename: audit_YYYYMMDD_HHMMSS.jsonl
                    parts = f.stem.split("_", 1)
                    if len(parts) >= 2:
                        date_str = parts[1][:8]  # YYYYMMDD
                        file_date = datetime.strptime(date_str, "%Y%m%d")
                        if file_date < cutoff:
                            f.unlink()
                except (ValueError, OSError):
                    pass
        except Exception:
            pass

    def log(
        self,
        action: str,
        status: str,
        source: str = "system",
        reason: str = "",
        tool_name: str = "",
        args: Optional[dict] = None,
        result: str = "",
        duration_ms: float = 0.0,
    ):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self._session_id,
            "source": source,
            "action": action,
            "tool_name": tool_name,
            "status": status,
            "reason": reason,
            "result_preview": str(result)[:100] if result else "",
            "duration_ms": round(duration_ms, 1),
        }

        if args:
            entry["args"] = redact_params(args)

        with self._lock:
            self._entries.append(entry)

    def log_decision(
        self,
        tool_name: str,
        decision: str,
        risk_tier: str,
        reason: str = "",
        source: str = "system",
        args: Optional[dict] = None,
    ):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self._session_id,
            "source": source,
            "action": "permission_check",
            "tool_name": tool_name,
            "risk_tier": risk_tier,
            "decision": decision,
            "reason": reason,
        }
        if args:
            entry["args"] = redact_params(args)
        with self._lock:
            self._entries.append(entry)

    def get_recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self._entries[-limit:])

    def flush(self):
        if not self._entries:
            return
        with self._write_lock:
            with self._lock:
                to_write = self._entries
                self._entries = []
            if not to_write:
                return
            log_file = self._log_dir / f"audit_{self._session_id}.jsonl"
            try:
                with open(log_file, "a", encoding="utf-8") as f:
                    for entry in to_write:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    f.flush()
            except Exception as e:
                print(f"[Audit] Write error: {e}")
                # Push entries back so they aren't lost
                with self._lock:
                    self._entries = to_write + self._entries

    def shutdown(self):
        """Flush remaining entries and stop background thread."""
        self._stop_event.set()
        self.flush()

    def get_stats(self) -> dict:
        """Get audit logger statistics."""
        with self._lock:
            pending = len(self._entries)
        log_files = list(self._log_dir.glob("audit_*.jsonl"))
        return {
            "session_id": self._session_id,
            "pending_entries": pending,
            "log_files": len(log_files),
            "log_dir": str(self._log_dir),
        }

    def get_log_path(self) -> Path:
        return self._log_dir / f"audit_{self._session_id}.jsonl"


# ── Lazy singleton (no side effect at import time) ────────────────────

_logger: Optional[AuditLogger] = None
_logger_lock = threading.Lock()


def get_audit_logger() -> AuditLogger:
    global _logger
    if _logger is None:
        with _logger_lock:
            if _logger is None:
                _logger = AuditLogger()
    return _logger


def log_action(
    action: str,
    status: str,
    source: str = "system",
    reason: str = "",
    tool_name: str = "",
    args: Optional[dict] = None,
    result: str = "",
    duration_ms: float = 0.0,
):
    get_audit_logger().log(
        action=action, status=status, source=source,
        reason=reason, tool_name=tool_name, args=args,
        result=result, duration_ms=duration_ms,
    )


def log_decision(
    tool_name: str,
    decision: str,
    risk_tier: str,
    reason: str = "",
    source: str = "system",
    args: Optional[dict] = None,
):
    get_audit_logger().log_decision(
        tool_name=tool_name, decision=decision,
        risk_tier=risk_tier, reason=reason,
        source=source, args=args,
    )


def redact_sensitive(text: str) -> str:
    if not text:
        return text
    for pat in SENSITIVE_PATTERNS:
        text = pat.sub(lambda m: m.group(1) + "=***REDACTED***" if m.lastindex else "***REDACTED***", text)
    return text
