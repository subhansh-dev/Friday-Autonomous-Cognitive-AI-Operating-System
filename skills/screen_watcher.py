# -*- coding: utf-8 -*-
"""
screen_watcher.py — FRIDAY Active Screen Intelligence
=======================================================
Continuously monitors the screen, analyzes what's happening, and proactively
alerts the user about mistakes, opportunities, and relevant information.

Capabilities:
- Error detection: catches error dialogs, red text, crash messages, failed builds
- Workflow intelligence: suggests next steps based on what's on screen
- Code review: flags potential issues visible in code editors
- Form validation: warns about missing fields, invalid inputs
- Research assistance: offers to look up things visible on screen
- Distraction alerts: notices off-task behavior and gently refocuses
- Security warnings: flags suspicious URLs, phishing patterns, unsafe downloads

Uses Gemini Flash Vision for fast, cheap analysis with rolling context
to understand the flow of user activity.
"""

import io
import json
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import PIL.Image
    import PIL.ImageResampling
    _PIL = True
except ImportError:
    _PIL = False


BRAIN_DIR = Path(__file__).parent.parent / "brain"
CONFIG_PATH = Path(__file__).parent.parent / "config" / "api_keys.json"

# Analysis intervals
ANALYSIS_INTERVAL_S = 8.0        # How often to capture + analyze
COOLDOWN_S = 15.0                # Min time between alerts
CONTEXT_HISTORY_SIZE = 12        # Rolling window of recent observations
SIMILARITY_THRESHOLD = 0.85      # Skip alerts for nearly identical frames

# Alert priority levels
PRIORITY_LOW = 1       # Gentle suggestion
PRIORITY_MEDIUM = 2    # Important notice
PRIORITY_HIGH = 3      # Error / security warning
PRIORITY_CRITICAL = 4  # Immediate attention needed

# Image compression
_IMG_MAX_W = 640
_IMG_MAX_H = 360
_JPEG_Q = 55


class ScreenObservation:
    """A single screen observation with analysis."""

    def __init__(self, timestamp: float, analysis: str, context: str = "",
                 priority: int = PRIORITY_LOW, category: str = "general"):
        self.timestamp = timestamp
        self.analysis = analysis
        self.context = context
        self.priority = priority
        self.category = category

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "time_str": datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S"),
            "analysis": self.analysis[:300],
            "context": self.context[:200],
            "priority": self.priority,
            "category": self.category,
        }


class ScreenWatcher:
    """
    Active screen monitoring and intelligence engine.

    Runs a background thread that periodically:
    1. Captures the screen
    2. Sends to Gemini Flash Vision with context from recent history
    3. Evaluates if the observation warrants an alert
    4. Notifies the user via callback (toast + optional voice)
    """

    def __init__(self, on_alert: Optional[Callable] = None,
                 on_log: Optional[Callable] = None):
        """
        Args:
            on_alert: callback(message: str, priority: int) for user-facing alerts
            on_log: callback(message: str) for debug logging
        """
        self._on_alert = on_alert
        self._on_log = on_log or (lambda msg: print(f"[ScreenWatcher] {msg}"))
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        # Rolling context history
        self._history: deque[ScreenObservation] = deque(maxlen=CONTEXT_HISTORY_SIZE)
        self._last_alert_time: float = 0
        self._last_frame_hash: str = ""
        self._alert_count: int = 0
        self._analysis_count: int = 0

        # Gemini client (lazy init)
        self._client = None
        self._api_key: Optional[str] = None

        # User context for smarter analysis
        self._user_goal: str = ""
        self._watch_mode: str = "general"  # general, code_review, research, security

    # ── Lifecycle ───────────────────────────────────────────────────

    def start(self, mode: str = "general"):
        """Start the screen watcher."""
        if self._running:
            return
        self._watch_mode = mode
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        self._on_log(f"Started in '{mode}' mode")

    def stop(self):
        """Stop the screen watcher."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self._on_log("Stopped")

    def set_goal(self, goal: str):
        """Tell the watcher what the user is trying to do (improves analysis)."""
        self._user_goal = goal

    def set_mode(self, mode: str):
        """Change watch mode: general, code_review, research, security."""
        self._watch_mode = mode
        self._on_log(f"Mode changed to '{mode}'")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Core Loop ───────────────────────────────────────────────────

    def _watch_loop(self):
        """Main monitoring loop."""
        self._on_log("Monitor loop started")
        while self._running:
            try:
                self._tick()
            except Exception as e:
                self._on_log(f"Tick error: {e}")
            time.sleep(ANALYSIS_INTERVAL_S)
        self._on_log("Monitor loop ended")

    def _tick(self):
        """Single monitoring cycle: capture → analyze → decide."""
        # 1. Capture
        frame_bytes = self._capture()
        if not frame_bytes:
            return

        # 2. Deduplicate — skip if screen hasn't changed much
        frame_hash = str(hash(frame_bytes[:2000]))
        if frame_hash == self._last_frame_hash:
            return
        self._last_frame_hash = frame_hash

        # 3. Analyze with Gemini
        analysis = self._analyze(frame_bytes)
        if not analysis:
            return

        self._analysis_count += 1

        # 4. Parse the analysis
        observation = self._parse_analysis(analysis)

        # 5. Store in history
        with self._lock:
            self._history.append(observation)

        # 6. Decide whether to alert
        if self._should_alert(observation):
            self._fire_alert(observation)

    # ── Screen Capture ──────────────────────────────────────────────

    def _capture(self) -> Optional[bytes]:
        """Capture and compress a screenshot."""
        if not _MSS:
            return None
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # Primary monitor
                shot = sct.grab(monitor)
                png = mss.tools.to_png(shot.rgb, shot.size)
            return self._compress(png)
        except Exception as e:
            self._on_log(f"Capture failed: {e}")
            return None

    def _compress(self, png_bytes: bytes) -> bytes:
        """Compress screenshot for fast upload."""
        if not _PIL:
            return png_bytes
        try:
            img = PIL.Image.open(io.BytesIO(png_bytes)).convert("RGB")
            img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.Resampling.BILINEAR)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
            return buf.getvalue()
        except Exception:
            return png_bytes

    # ── Gemini Vision Analysis ──────────────────────────────────────

    def _get_client(self):
        """Lazy-init Gemini client."""
        if self._client is None:
            try:
                key_data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                self._api_key = key_data.get("gemini_api_key", "")
                if not self._api_key:
                    self._on_log("No API key found")
                    return None
                from google import genai
                self._client = genai.Client(api_key=self._api_key)
            except Exception as e:
                self._on_log(f"Client init failed: {e}")
                return None
        return self._client

    def _build_prompt(self) -> str:
        """Build the analysis prompt based on mode and context."""
        # Recent history summary
        history_text = ""
        with self._lock:
            if self._history:
                recent = list(self._history)[-3:]
                history_text = " | ".join(
                    f"[{o.time_str}] {o.analysis[:60]}" for o in recent
                )

        mode_instructions = {
            "general": (
                "Analyze the screen and respond with a JSON object. "
                "Look for: errors, mistakes, warnings, opportunities to help. "
                "If everything looks normal and there's nothing noteworthy, respond with "
                "{\"alert\": false, \"analysis\": \"brief description of what's on screen\"}. "
                "If you notice something the user should know about, respond with "
                "{\"alert\": true, \"priority\": 1-4, \"category\": \"error|suggestion|security|workflow|distraction\", "
                "\"message\": \"concise actionable message\", \"analysis\": \"what you see\"}. "
            ),
            "code_review": (
                "You are a code reviewer watching over the user's shoulder. "
                "Analyze the code visible on screen. Look for: bugs, syntax errors, "
                "security vulnerabilities, performance issues, missing error handling, "
                "type mismatches, off-by-one errors, unclosed resources. "
                "If code looks fine: {\"alert\": false, \"analysis\": \"brief description\"}. "
                "If you spot an issue: {\"alert\": true, \"priority\": 2-4, \"category\": \"code_issue\", "
                "\"message\": \"specific issue and fix suggestion\", \"analysis\": \"what you see\"}. "
            ),
            "research": (
                "You are a research assistant. Analyze what's on screen and offer to help. "
                "If the user is reading an article, offer to summarize or find related info. "
                "If they're looking at data, offer analysis. If they seem stuck finding something, suggest searches. "
                "{\"alert\": true/false, \"priority\": 1-2, \"category\": \"research\", "
                "\"message\": \"helpful suggestion\", \"analysis\": \"what you see\"}. "
            ),
            "security": (
                "You are a security analyst. Scrutinize the screen for threats. "
                "Look for: suspicious URLs, phishing indicators, unsafe downloads, "
                "exposed credentials, insecure connections (HTTP), certificate warnings, "
                "unexpected permission requests, social engineering patterns. "
                "If safe: {\"alert\": false, \"analysis\": \"brief description\"}. "
                "If threat detected: {\"alert\": true, \"priority\": 3-4, \"category\": \"security\", "
                "\"message\": \"specific threat and recommended action\", \"analysis\": \"what you see\"}. "
            ),
        }

        instruction = mode_instructions.get(self._watch_mode, mode_instructions["general"])

        goal_text = f"\nUser's current goal: {self._user_goal}" if self._user_goal else ""
        history_section = f"\nRecent screen activity: {history_text}" if history_text else ""

        return (
            f"{instruction}"
            f"{goal_text}"
            f"{history_section}"
            f"\n\nRespond ONLY with valid JSON. Be extremely concise. "
            f"Only alert on things that are genuinely actionable — "
            f"don't alert for normal/expected screen content."
        )

    def _analyze(self, frame_bytes: bytes) -> Optional[str]:
        """Send screenshot to Gemini for analysis."""
        client = self._get_client()
        if not client:
            return None

        try:
            from google.genai import types as gtypes

            prompt = self._build_prompt()
            image_part = gtypes.Part.from_bytes(data=frame_bytes, mime_type="image/jpeg")

            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=[image_part, prompt],
                config=gtypes.GenerateContentConfig(
                    max_output_tokens=300,
                    temperature=0.1,  # Low temp for consistent, focused analysis
                ),
            )
            return response.text.strip() if response.text else None

        except Exception as e:
            self._on_log(f"Analysis failed: {e}")
            return None

    def _parse_analysis(self, raw: str) -> ScreenObservation:
        """Parse Gemini's JSON response into an observation."""
        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # If not valid JSON, treat as a plain analysis with no alert
            return ScreenObservation(
                timestamp=time.time(),
                analysis=raw[:200],
                category="parse_error",
            )

        return ScreenObservation(
            timestamp=time.time(),
            analysis=data.get("analysis", "")[:200],
            context=data.get("message", "")[:200],
            priority=int(data.get("priority", PRIORITY_LOW)),
            category=data.get("category", "general"),
        )

    # ── Alert Logic ─────────────────────────────────────────────────

    def _should_alert(self, obs: ScreenObservation) -> bool:
        """Decide whether this observation warrants alerting the user."""
        # Must have alert context
        if not obs.context and obs.priority <= PRIORITY_LOW:
            return False

        # Cooldown check
        now = time.time()
        if now - self._last_alert_time < COOLDOWN_S:
            return False

        # Don't alert for low-priority parse errors
        if obs.category == "parse_error":
            return False

        # Alert if priority >= medium
        if obs.priority >= PRIORITY_MEDIUM:
            return True

        # Alert for low priority only if we haven't alerted much
        if obs.priority >= PRIORITY_LOW and self._alert_count < 5:
            return True

        return False

    def _fire_alert(self, obs: ScreenObservation):
        """Send an alert to the user."""
        self._last_alert_time = time.time()
        self._alert_count += 1

        # Priority prefix
        prefix = {
            PRIORITY_LOW: "FYI",
            PRIORITY_MEDIUM: "Notice",
            PRIORITY_HIGH: "Warning",
            PRIORITY_CRITICAL: "ALERT",
        }.get(obs.priority, "FYI")

        # Category icon
        icon = {
            "error": "!",
            "suggestion": "*",
            "security": "#",
            "workflow": ">",
            "code_issue": "/",
            "research": "?",
            "distraction": "~",
        }.get(obs.category, "-")

        message = f"[{prefix}] {obs.context}" if obs.context else obs.analysis[:100]

        self._on_log(f"ALERT ({obs.priority}): {message}")
        if self._on_alert:
            self._on_alert(message, obs.priority)

    # ── Query ───────────────────────────────────────────────────────

    def get_history(self, limit: int = 10) -> list[dict]:
        """Get recent screen observations."""
        with self._lock:
            return [o.to_dict() for o in list(self._history)[-limit:]]

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "mode": self._watch_mode,
                "analyses": self._analysis_count,
                "alerts_fired": self._alert_count,
                "history_size": len(self._history),
                "user_goal": self._user_goal or "(none)",
            }

    def format_for_prompt(self, max_chars: int = 300) -> str:
        """Format recent observations for system prompt injection."""
        with self._lock:
            if not self._history:
                return ""
            recent = list(self._history)[-3:]
            parts = ["[SCREEN WATCHER — Recent observations]"]
            for obs in recent:
                parts.append(f"[{obs.time_str}] {obs.analysis[:80]}")
            result = "\n".join(parts)
            return result[:max_chars] if len(result) > max_chars else result


# ── Standalone test ─────────────────────────────────────────────────

if __name__ == "__main__":
    def test_alert(msg, priority):
        print(f"\n{'='*50}")
        print(f"ALERT (P{priority}): {msg}")
        print(f"{'='*50}")

    watcher = ScreenWatcher(on_alert=test_alert)
    watcher.start(mode="general")
    print("[Test] Watching screen for 60 seconds... Ctrl+C to stop")
    try:
        time.sleep(60)
    except KeyboardInterrupt:
        pass
    watcher.stop()
    print(f"[Test] Stats: {watcher.get_stats()}")
