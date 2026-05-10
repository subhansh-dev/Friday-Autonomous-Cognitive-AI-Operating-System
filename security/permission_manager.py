import enum
import threading
import time
from typing import Optional

from security.audit_logger import get_audit_logger


class RiskTier(str, enum.Enum):
    SAFE = "safe"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class Decision(str, enum.Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


TOOL_RISK_TIERS: dict[str, RiskTier] = {
    # ── SAFE: automatic ───────────────────────────────────────────────────
    "web_search": RiskTier.SAFE,
    "weather_report": RiskTier.SAFE,
    "brain_memory": RiskTier.SAFE,
    "save_memory": RiskTier.SAFE,
    "ai_pipeline": RiskTier.SAFE,
    "integration_status": RiskTier.SAFE,
    "data_analysis": RiskTier.SAFE,
    "shutdown_friday": RiskTier.SAFE,

    # ── MEDIUM: ask for confirmation ──────────────────────────────────────
    "open_app": RiskTier.MEDIUM,
    "browser_control": RiskTier.MEDIUM,
    "computer_settings": RiskTier.MEDIUM,
    "computer_control": RiskTier.MEDIUM,
    "youtube_video": RiskTier.MEDIUM,
    "desktop_control": RiskTier.MEDIUM,
    "file_controller": RiskTier.MEDIUM,
    "code_helper": RiskTier.MEDIUM,
    "web_research": RiskTier.MEDIUM,

    # ── HIGH: explicit confirmation + impact explanation ──────────────────
    "send_message": RiskTier.HIGH,
    "flight_finder": RiskTier.HIGH,
    "reminder": RiskTier.HIGH,
    "game_updater": RiskTier.HIGH,
    "dev_agent": RiskTier.HIGH,
    "ac_control": RiskTier.HIGH,
    "agent_task": RiskTier.HIGH,
    "api_server": RiskTier.HIGH,
    "screen_process": RiskTier.HIGH,

    # ── AGENCY AGENT (safe — just queries Gemini with expert persona) ────
    "agency_agent": RiskTier.SAFE,

    # ── SKILLS (all safe/medium) ─────────────────────────────────────────
    "deep_dive": RiskTier.MEDIUM,
    "system_sentinel": RiskTier.SAFE,
    "neural_clipboard": RiskTier.SAFE,
    "social_pulse": RiskTier.SAFE,
    "auto_doc": RiskTier.SAFE,
    "digital_twin": RiskTier.SAFE,
    "gesture_music": RiskTier.MEDIUM,

    # ── HOLOGRAPHIC ──────────────────────────────────────────────────────
    "holo_builder": RiskTier.MEDIUM,
    "holographic_map": RiskTier.SAFE,

    # ── CYBERSECURITY ────────────────────────────────────────────────────
    "security_tools": RiskTier.HIGH,

    # ── SELF-AWARENESS (all safe — introspective only) ─────────────────────
    "self_model_status": RiskTier.SAFE,
    "run_dream_cycle": RiskTier.SAFE,
    "curiosity_queue": RiskTier.SAFE,
    "force_learning": RiskTier.SAFE,
    "record_learning": RiskTier.SAFE,
    "reflect_learning": RiskTier.SAFE,
    "get_learnings": RiskTier.SAFE,
}


HIGH_RISK_WORDS = {
    "delete", "remove", "erase", "destroy", "wipe", "truncate",
    "send", "post", "publish", "broadcast",
    "shutdown", "restart", "reboot", "poweroff",
    "execute", "shell", "command", "system",
    "format", "overwrite", "chmod", "chown",
}


DEFAULT_DENY_ACTIONS: set[str] = {
    "shell_exec", "system_command", "raw_exec",
    "eval", "exec_code",
}


ALLOWLISTED_DOMAINS: set[str] = {
    "google.com", "bing.com", "duckduckgo.com",
    "youtube.com", "github.com", "stackoverflow.com",
    "wikipedia.org",
}


ALLOWLISTED_FILE_PATHS: set[str] = set()


ALLOWLISTED_TELEGRAM_USERS: set[int] = set()


TOOL_CONFIRMATION_OVERRIDES: dict[str, bool] = {}


class ActionPolicy:
    def __init__(
        self,
        auto_confirm_medium: bool = False,
        auto_confirm_high: bool = False,
        strict_mode: bool = True,
    ):
        self.auto_confirm_medium = auto_confirm_medium
        self.auto_confirm_high = auto_confirm_high
        self.strict_mode = strict_mode


def get_default_policy() -> ActionPolicy:
    return ActionPolicy(strict_mode=True)


class PermissionManager:
    def __init__(self, policy: Optional[ActionPolicy] = None):
        self._lock = threading.RLock()
        self.policy = policy or get_default_policy()
        self._risk_overrides: dict[str, RiskTier] = {}
        self._confirm_queue: list[dict] = []
        self._confirm_results: dict[str, bool] = {}
        self._audit = get_audit_logger()
        # Background thread to expire stale confirmations
        self._cleanup_stop = threading.Event()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def _cleanup_loop(self):
        """Expire confirmations older than their timeout."""
        while not self._cleanup_stop.wait(10):
            now = time.time()
            with self._lock:
                expired = [
                    c for c in self._confirm_queue
                    if now - c.get("timestamp", 0) > c.get("timeout", 30)
                ]
                for c in expired:
                    self._confirm_queue.remove(c)
                    confirm_id = c.get("id", "")
                    if confirm_id not in self._confirm_results:
                        self._confirm_results[confirm_id] = False
                        self._audit.log(
                            action="confirmation_expired", status="timeout",
                            source=c.get("source", "system"),
                            tool_name=c.get("tool_name", ""),
                            reason="Confirmation timed out",
                        )

    def get_risk_tier(self, tool_name: str, args: Optional[dict] = None) -> RiskTier:
        with self._lock:
            if tool_name in self._risk_overrides:
                return self._risk_overrides[tool_name]

        tier = TOOL_RISK_TIERS.get(tool_name, RiskTier.UNKNOWN)

        if tier == RiskTier.UNKNOWN and self.policy.strict_mode:
            return RiskTier.HIGH

        if args and tier == RiskTier.MEDIUM:
            action = str(args.get("action", "")).lower()
            for word in HIGH_RISK_WORDS:
                if word in action:
                    return RiskTier.HIGH

        return tier

    def check_tool(
        self,
        tool_name: str,
        args: Optional[dict] = None,
        source: str = "mic",
    ) -> tuple[Decision, str]:
        tier = self.get_risk_tier(tool_name, args)

        if tool_name in DEFAULT_DENY_ACTIONS:
            self._audit.log_decision(
                tool_name=tool_name, decision="deny",
                risk_tier="high",
                reason="Action is in default-deny list", source=source, args=args,
            )
            return Decision.DENY, f"{tool_name} is disabled by default (default-deny policy)"

        # Check if user previously confirmed this exact tool call
        confirm_id = f"{tool_name}_{hash(str(sorted((args or {}).items())))}"
        with self._lock:
            if confirm_id in TOOL_CONFIRMATION_OVERRIDES:
                allowed = TOOL_CONFIRMATION_OVERRIDES[confirm_id]
                self._audit.log_decision(
                    tool_name=tool_name,
                    decision="allow" if allowed else "deny",
                    risk_tier=tier.value,
                    reason="User override from previous confirmation",
                    source=source, args=args,
                )
                return (Decision.ALLOW if allowed else Decision.DENY), ""

        if tier == RiskTier.SAFE:
            self._audit.log_decision(
                tool_name=tool_name, decision="allow",
                risk_tier="safe",
                reason="Safe action — automatic", source=source, args=args,
            )
            return Decision.ALLOW, ""

        if tier == RiskTier.MEDIUM:
            if self.policy.auto_confirm_medium:
                self._audit.log_decision(
                    tool_name=tool_name, decision="allow",
                    risk_tier="medium",
                    reason="Auto-confirm enabled for medium-risk actions",
                    source=source, args=args,
                )
                return Decision.ALLOW, ""

            self._audit.log_decision(
                tool_name=tool_name, decision="ask",
                risk_tier="medium",
                reason="Medium-risk — user confirmation required",
                source=source, args=args,
            )
            return Decision.ASK, f"Confirm {tool_name}? [y/N]"

        if tier == RiskTier.HIGH:
            if self.policy.auto_confirm_high:
                self._audit.log_decision(
                    tool_name=tool_name, decision="allow",
                    risk_tier="high",
                    reason="Auto-confirm enabled for high-risk actions",
                    source=source, args=args,
                )
                return Decision.ALLOW, ""

            impact = self._describe_impact(tool_name, args)
            self._audit.log_decision(
                tool_name=tool_name, decision="ask",
                risk_tier="high",
                reason=f"High-risk — explicit confirmation required. {impact}",
                source=source, args=args,
            )
            return Decision.ASK, f"\u26a0\ufe0f HIGH-RISK: {impact}."

        # UNKNOWN tier (non-strict mode) — deny by default
        self._audit.log_decision(
            tool_name=tool_name, decision="deny",
            risk_tier="unknown",
            reason="Unknown tool with no risk classification",
            source=source, args=args,
        )
        return Decision.DENY, f"Unknown action '{tool_name}' rejected (default-deny)"

    def _describe_impact(self, tool_name: str, args: Optional[dict] = None) -> str:
        descriptions = {
            "send_message": "This will send a message to another person via messaging platform",
            "flight_finder": "This will access an external flight search service",
            "reminder": "This will schedule a system task",
            "dev_agent": "This will create files and potentially install software",
            "agent_task": "This will execute multiple tools in sequence",
            "api_server": "This will start a network-accessible API server",
            "ac_control": "This will control physical hardware (air conditioner)",
            "game_updater": "This will modify installed game software",
            "screen_process": "This will capture screen or camera images for AI analysis",
            "security_tools": "This will run cybersecurity tools (port scanning, vulnerability scanning, recon) against a target",
        }
        base = descriptions.get(tool_name, f"This action ({tool_name}) may modify system state")

        if tool_name == "file_controller" and args:
            action = args.get("action", "")
            path = args.get("path", "")
            if action in ("delete", "move", "overwrite"):
                base = f"This will {action} files at '{path}'"
            elif action == "write":
                base = f"This will write content to '{path}'"

        if tool_name == "computer_settings" and args:
            action = args.get("action", "")
            if action in ("shutdown", "restart"):
                base = f"This will {action} the computer"

        return base

    def request_confirmation(
        self,
        tool_name: str,
        args: Optional[dict] = None,
        source: str = "mic",
        timeout: float = 30.0,
    ) -> str | None:
        """
        Queue a confirmation request.
        Returns a confirm_id the caller can use with wait_for_confirmation(),
        or None if no confirmation needed (ALLOW/DENY already decided).
        """
        decision, reason = self.check_tool(tool_name, args, source)

        if decision == Decision.ALLOW:
            return None
        if decision == Decision.DENY:
            return None

        self._audit.log(
            action="confirmation_requested", status="pending",
            source=source, tool_name=tool_name,
            reason=reason, args=args,
        )

        confirm_id = f"{tool_name}_{time.time_ns()}"
        with self._lock:
            self._confirm_queue.append({
                "id": confirm_id,
                "tool_name": tool_name,
                "args": args,
                "source": source,
                "reason": reason,
                "timeout": timeout,
                "timestamp": time.time(),
            })

        return confirm_id

    def wait_for_confirmation(
        self, confirm_id: str, timeout: float = 30.0
    ) -> bool:
        """
        Block until the user resolves a confirmation or it times out.
        Returns True if allowed, False if denied/expired.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if confirm_id in self._confirm_results:
                    result = self._confirm_results.pop(confirm_id)
                    return result
            time.sleep(0.5)
        # Timed out
        with self._lock:
            self._confirm_results.pop(confirm_id, None)
        return False

    def resolve_confirmation(self, confirm_id: str, allowed: bool):
        """User resolved a confirmation request."""
        with self._lock:
            self._confirm_results[confirm_id] = allowed
            self._confirm_queue = [
                c for c in self._confirm_queue if c.get("id") != confirm_id
            ]

        self._audit.log(
            action="confirmation_resolved",
            status="allowed" if allowed else "denied",
            source="user",
            reason=f"User {'allowed' if allowed else 'denied'} confirmation {confirm_id}",
        )

    def set_risk_override(self, tool_name: str, tier: RiskTier):
        with self._lock:
            self._risk_overrides[tool_name] = tier

    def get_pending_confirmations(self) -> list[dict]:
        with self._lock:
            # Return copy without internal fields
            return [
                {k: v for k, v in c.items() if k != "timestamp"}
                for c in list(self._confirm_queue)
            ]

    def shutdown(self):
        """Stop background cleanup thread."""
        self._cleanup_stop.set()


_manager: Optional[PermissionManager] = None
_manager_lock = threading.Lock()


def get_permission_manager() -> PermissionManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = PermissionManager()
    return _manager
