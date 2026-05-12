"""
cyber/authorization.py — Authorization & Consent Gate
=======================================================

Two-layer authorization system:
1. Target Guard — classifies targets as local/owned/blocked/unknown
2. Consent Gate — requires typed consent for external targets

Localhost and private IPs are always allowed (testing your own stuff).
External targets require explicit ownership confirmation.
Cloud metadata endpoints are always blocked.

Usage:
    from cyber.authorization import require_authorization, AuthorizationError

    # Before running any live operation:
    require_authorization(target, operation="port_scan")
"""

import json
import hashlib
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from cyber.target_guard import get_target_guard, CONSENT_PHRASE

logger = logging.getLogger("friday.cyber.authorization")

# ── Constants ─────────────────────────────────────────────────────────

CONSENT_LOG_FILE = Path(__file__).parent.parent / "config" / "consent_log.json"
CONSENT_EXPIRY_HOURS = 24

# Operations that require authorization (anything involving network)
LIVE_OPERATIONS = {
    "port_scan", "nmap_scan", "nmap_script", "subdomain_enum", "subfinder",
    "httpx_probe", "dns_info", "dnsx", "ssl_info", "whois", "web_fuzz_ps",
    "ffuf", "gobuster", "nuclei", "sqlmap", "whatweb", "wpscan", "gospider",
    "http_archive", "katana", "naabu", "header_check", "cors_check",
    "recon_full", "cyber_scan", "mythos_scan",
    "exploit_validation", "business_logic", "full_pipeline",
}

# Operations that are always allowed (local file analysis only)
SAFE_OPERATIONS = {
    "static_analysis", "data_flow", "source_sink", "code_review",
    "check_tools", "debug_wsl", "health", "url_parse",
    "extract_domains", "extract_urls", "start_mcp", "stop_mcp", "reset_wsl",
}


class AuthorizationError(Exception):
    """Raised when user has not authorized live operations."""
    def __init__(self, target: str, operation: str, message: str = None):
        self.target = target
        self.operation = operation
        self.message = message or (
            f"Authorization required for '{operation}' on '{target}'.\n"
            f"To authorize, type: {CONSENT_PHRASE}"
        )
        super().__init__(self.message)


@dataclass
class ConsentRecord:
    """A single consent record."""
    target: str
    timestamp: float
    timestamp_human: str
    consent_phrase_hash: str
    ip_hash: Optional[str] = None


class AuthorizationManager:
    """
    Manages user consent for live cyber operations.

    Integrates with TargetGuard for target classification:
    - LOCAL targets → always allowed, no consent needed
    - OWNED targets → previously authorized, allowed
    - BLOCKED targets → never allowed
    - UNKNOWN targets → require consent
    """

    def __init__(self):
        self._consent_log: list[dict] = []
        self._active_consents: dict[str, float] = {}
        self._target_guard = get_target_guard()
        self._load_consent_log()

    def _load_consent_log(self):
        """Load existing consent records from disk."""
        try:
            if CONSENT_LOG_FILE.exists():
                data = json.loads(CONSENT_LOG_FILE.read_text(encoding="utf-8"))
                self._consent_log = data.get("records", [])
                now = time.time()
                for record in self._consent_log:
                    expiry = record["timestamp"] + (CONSENT_EXPIRY_HOURS * 3600)
                    if expiry > now:
                        self._active_consents[record["target"]] = expiry
        except Exception as e:
            logger.warning(f"Failed to load consent log: {e}")
            self._consent_log = []

    def _save_consent_log(self):
        """Persist consent records to disk."""
        try:
            CONSENT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "description": "Audit log of user consent for live cyber operations",
                "records": self._consent_log,
            }
            CONSENT_LOG_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"Failed to save consent log: {e}")

    def is_authorized(self, target: str) -> bool:
        """
        Check if target is authorized for live operations.

        Returns True if:
        - Target is local (localhost/private IP), OR
        - Target is owned (user previously consented), OR
        - User has active consent for this target
        """
        classification = self._target_guard.classify(target)

        if classification == "local":
            return True  # Always allowed — your own machine
        if classification == "blocked":
            return False  # Never allowed
        if classification == "owned":
            return True  # Previously authorized via target guard

        # Check legacy consent system too
        expiry = self._active_consents.get(target)
        if expiry and time.time() < expiry:
            return True
        if target in self._active_consents:
            del self._active_consents[target]
        return False

    def grant_consent(self, target: str, consent_phrase: str) -> tuple[bool, str]:
        """
        Attempt to grant consent for a target.

        Delegates to TargetGuard for ownership tracking.
        """
        success, msg = self._target_guard.grant_ownership(target, consent_phrase)
        if success:
            # Also log in legacy consent system
            now = time.time()
            record = ConsentRecord(
                target=target,
                timestamp=now,
                timestamp_human=datetime.now(timezone.utc).isoformat(),
                consent_phrase_hash=hashlib.sha256(
                    CONSENT_PHRASE.encode()
                ).hexdigest()[:16],
            )
            self._consent_log.append(asdict(record))
            self._active_consents[target] = now + (CONSENT_EXPIRY_HOURS * 3600)
            self._save_consent_log()
        return success, msg

    def revoke_consent(self, target: str) -> bool:
        """Revoke active consent for a target."""
        self._target_guard.revoke(target)
        revoked = False
        if target in self._active_consents:
            del self._active_consents[target]
            revoked = True
        # Also remove from legacy consent log active tracking
        self._consent_log = [r for r in self._consent_log if r.get("target") != target]
        self._save_consent_log()
        return revoked

    def revoke_all(self) -> int:
        """Revoke all active consents."""
        count = self._target_guard.revoke()
        count += len(self._active_consents)
        self._active_consents.clear()
        self._consent_log.clear()
        self._save_consent_log()
        return count

    def get_active_consents(self) -> list[dict]:
        """List all active (non-expired) consents."""
        return self._target_guard.list_owned()

    def get_consent_log(self) -> list[dict]:
        """Return full consent audit log."""
        return list(self._consent_log)

    def require_authorization(self, target: str, operation: str):
        """
        Gate: raises AuthorizationError if not authorized.

        Call this before any live cyber operation.
        """
        if not self.is_authorized(target):
            # Build helpful error message
            guard_msg = self._target_guard.check(target, operation)
            raise AuthorizationError(target, operation, guard_msg)

        logger.debug(f"Authorization confirmed for {operation} on {target}")


# ── Singleton ─────────────────────────────────────────────────────────

_auth_manager: Optional[AuthorizationManager] = None


def get_auth_manager() -> AuthorizationManager:
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthorizationManager()
    return _auth_manager


def is_authorized(target: str) -> bool:
    return get_auth_manager().is_authorized(target)


def require_authorization(target: str, operation: str = "unknown"):
    get_auth_manager().require_authorization(target, operation)


def grant_consent(target: str, consent_phrase: str) -> tuple[bool, str]:
    return get_auth_manager().grant_consent(target, consent_phrase)


def is_live_operation(operation: str) -> bool:
    return operation in LIVE_OPERATIONS
