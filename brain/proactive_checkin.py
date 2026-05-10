#!/usr/bin/env python3
"""
proactive_checkin.py — FRIDAY Proactive Check-In & Engagement System
======================================================================

Makes Friday initiate conversation during silence periods instead of
sitting quietly forever. Monitors user activity and triggers contextual
check-ins, reminder alerts, and returning-user greetings.

Behavior tiers:
  - 5 min silence  → gentle check-in: "Sir? Need anything?"
  - 15 min silence → curious: "Everything alright, sir?"
  - 30 min silence → concerned: "Sir, I'm still here. Are you okay?"
  - 60 min silence → long-absence greeting when user returns

Also:
  - Polls reminders every 60s and announces upcoming ones
  - Tracks returning-user context for warm re-engagement
  - Respects quiet hours (configurable)
  - Won't interrupt active speaking or tool execution

Designed to plug into main.py's async gather loop alongside
_keepalive, _idle_exploration, etc.
"""

import asyncio
import json
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable, Awaitable, List, Dict, Any

# ── Paths ────────────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).resolve().parent.parent
_REMINDERS_DIR = Path.home() / ".friday" / "reminders"


# ── Configuration ────────────────────────────────────────────────────────────

# Silence thresholds (seconds) — how long before each check-in tier
TIER_1_SILENCE = 300       # 5 min  — gentle
TIER_2_SILENCE = 900       # 15 min — curious
TIER_3_SILENCE = 1800      # 30 min — concerned
LONG_ABSENCE   = 3600      # 60 min — returning user greeting

# How often to check if a check-in is due (seconds)
CHECK_INTERVAL = 30

# How often to poll for upcoming reminders (seconds)
REMINDER_POLL_INTERVAL = 60

# Quiet hours — don't check in during these (24h format)
QUIET_START_HOUR = 23   # 11 PM
QUIET_END_HOUR   = 7    # 7 AM

# Minimum time between check-ins to avoid being annoying (seconds)
MIN_CHECKIN_COOLDOWN = 240  # 4 minutes

# Reminder advance notice — announce reminders coming up within this window (minutes)
REMINDER_ADVANCE_MINUTES = 15


# ── Check-in message variants (randomized for naturalness) ──────────────────

TIER_1_MESSAGES = [
    "Sir? Need anything?",
    "I'm here if you need me, sir.",
    "Anything I can help with?",
    "Just checking in — everything good?",
    "Still here, sir. Let me know if you need anything.",
]

TIER_2_MESSAGES = [
    "Everything alright, sir? You've been quiet for a bit.",
    "Sir, is everything okay? I haven't heard from you in a while.",
    "Checking in again — anything on your mind?",
    "Sir? I'm still here if you need me.",
    "Haven't heard from you in a bit, sir. Just making sure you're alright.",
]

TIER_3_MESSAGES = [
    "Sir, I'm still here. Are you okay? It's been a while since we talked.",
    "I don't mean to be a bother, sir, but you've been silent for quite some time. Is everything alright?",
    "Sir? I'm getting a bit concerned. You haven't said anything in a while.",
    "Just making sure, sir — are you still there? It's been a while.",
]

RETURNING_MESSAGES = [
    "Welcome back, sir. You were away for a while — everything okay?",
    "Good to have you back, sir. Anything I can help with?",
    "Sir! You're back. Want a quick update on what's been going on?",
    "Welcome back, sir. I was starting to miss the conversation.",
]

REMINDER_MESSAGES = [
    "Sir, just a heads up — you have a reminder coming up: {reminder}",
    "Heads up, sir. Your reminder is coming up: {reminder}",
    "Sir, don't forget — {reminder}",
    "Quick reminder, sir: {reminder}",
]


class ProactiveCheckin:
    """
    Monitors user activity and initiates conversation during silence.
    """

    def __init__(self):
        self._last_user_activity: float = time.time()
        self._last_checkin_time: float = 0.0
        self._last_tier_triggered: int = 0          # which tier was last triggered
        self._announced_reminders: set = set()       # reminder IDs already announced
        self._user_returned: bool = False            # flag for returning-user greeting
        self._silence_start: Optional[float] = None  # when silence began
        self._is_active: bool = False                # whether user is actively interacting
        self._checkin_count: int = 0                 # how many check-ins this session

    # ── Activity tracking ─────────────────────────────────────────────

    def mark_user_active(self):
        """Call when user speaks or interacts. Resets all silence tracking."""
        now = time.time()
        was_away = (now - self._last_user_activity) > LONG_ABSENCE

        self._last_user_activity = now
        self._silence_start = None
        self._last_tier_triggered = 0
        self._is_active = True

        # If user was gone a long time, flag for returning greeting
        if was_away:
            self._user_returned = True

    def mark_user_idle(self):
        """Call when user stops interacting (e.g., tool finished, turn complete)."""
        self._is_active = False
        if self._silence_start is None:
            self._silence_start = time.time()

    def get_silence_duration(self) -> float:
        """How long since last user activity (seconds)."""
        return time.time() - self._last_user_activity

    # ── Quiet hours ───────────────────────────────────────────────────

    @staticmethod
    def _is_quiet_hours() -> bool:
        hour = datetime.now().hour
        if QUIET_START_HOUR > QUIET_END_HOUR:
            # Wraps midnight (e.g., 23-7)
            return hour >= QUIET_START_HOUR or hour < QUIET_END_HOUR
        return QUIET_START_HOUR <= hour < QUIET_END_HOUR

    # ── Check-in decision logic ───────────────────────────────────────

    def should_checkin(self) -> Optional[str]:
        """
        Determine if a check-in message should be sent.
        Returns the message string if yes, None if no.
        """
        now = time.time()
        silence = self.get_silence_duration()

        # Respect quiet hours
        if self._is_quiet_hours():
            return None

        # Don't check in if user is actively interacting
        if self._is_active:
            return None

        # Cooldown — don't spam
        if (now - self._last_checkin_time) < MIN_CHECKIN_COOLDOWN:
            return None

        # Max 5 check-ins per session to avoid being annoying
        if self._checkin_count >= 5:
            return None

        # Determine which tier we're in
        if silence >= TIER_3_SILENCE and self._last_tier_triggered < 3:
            msg = random.choice(TIER_3_MESSAGES)
            self._last_tier_triggered = 3
            return msg

        if silence >= TIER_2_SILENCE and self._last_tier_triggered < 2:
            msg = random.choice(TIER_2_MESSAGES)
            self._last_tier_triggered = 2
            return msg

        if silence >= TIER_1_SILENCE and self._last_tier_triggered < 1:
            msg = random.choice(TIER_1_MESSAGES)
            self._last_tier_triggered = 1
            return msg

        return None

    def should_greet_returning(self) -> Optional[str]:
        """
        Check if user just returned after a long absence.
        Returns greeting message if yes, None if no.
        """
        if self._user_returned:
            self._user_returned = False
            absence = self.get_silence_duration()
            if absence > LONG_ABSENCE:
                hours = int(absence // 3600)
                minutes = int((absence % 3600) // 60)
                msg = random.choice(RETURNING_MESSAGES)
                if hours > 0:
                    msg += f" You were away for about {hours} hour{'s' if hours > 1 else ''}."
                elif minutes > 5:
                    msg += f" You were away for about {minutes} minutes."
                return msg
        return None

    def record_checkin(self):
        """Record that a check-in was sent."""
        self._last_checkin_time = time.time()
        self._checkin_count += 1

    # ── Reminder checking ─────────────────────────────────────────────

    def check_upcoming_reminders(self, reminders: List[Dict[str, Any]]) -> Optional[str]:
        """
        Given a list of upcoming reminders, return an announcement if any
        are within the advance notice window.

        Each reminder dict should have:
          - "id": unique identifier
          - "message": what the reminder is about
          - "time": ISO datetime string or timestamp
        """
        if not reminders:
            return None

        now = datetime.now()
        upcoming = []

        for r in reminders:
            rid = r.get("id", "")
            if rid in self._announced_reminders:
                continue

            reminder_time = r.get("time", "")
            if not reminder_time:
                continue

            try:
                if isinstance(reminder_time, str):
                    rt = datetime.fromisoformat(reminder_time)
                elif isinstance(reminder_time, (int, float)):
                    rt = datetime.fromtimestamp(reminder_time)
                else:
                    continue
            except (ValueError, TypeError):
                continue

            diff = (rt - now).total_seconds() / 60  # minutes
            if 0 < diff <= REMINDER_ADVANCE_MINUTES:
                upcoming.append({
                    "message": r.get("message", "Unknown reminder"),
                    "minutes": int(diff),
                    "id": rid,
                })

        if not upcoming:
            return None

        # Pick the soonest one
        soonest = min(upcoming, key=lambda x: x["minutes"])
        self._announced_reminders.add(soonest["id"])

        if soonest["minutes"] <= 1:
            return f"Sir, your reminder is due now: {soonest['message']}"
        elif soonest["minutes"] <= 5:
            return f"Sir, reminder coming up in {soonest['minutes']} minutes: {soonest['message']}"
        else:
            msg = random.choice(REMINDER_MESSAGES)
            return msg.format(reminder=f"{soonest['message']} (in about {soonest['minutes']} min)")

    # ── State ─────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Current status for debugging / UI display."""
        silence = self.get_silence_duration()
        return {
            "silence_seconds": round(silence, 1),
            "silence_human": _fmt_duration(silence),
            "last_tier": self._last_tier_triggered,
            "checkins_this_session": self._checkin_count,
            "is_active": self._is_active,
            "quiet_hours": self._is_quiet_hours(),
            "announced_reminders": len(self._announced_reminders),
        }

    # ── Reminder filesystem scanning ──────────────────────────────────

    @staticmethod
    def scan_reminder_files() -> List[Dict[str, Any]]:
        """
        Scan ~/.friday/reminders/ for upcoming reminder scripts.
        Parses filename datetime and embedded message from each script.
        Returns list of reminder dicts sorted by time.
        """
        if not _REMINDERS_DIR.exists():
            return []

        reminders = []
        now = datetime.now()
        pattern = re.compile(r"JARVISReminder_(\d{8})_(\d{6})")

        for script in _REMINDERS_DIR.glob("JARVISReminder_*.py"):
            if script.name.endswith("_wrapper.py"):
                continue

            match = pattern.search(script.stem)
            if not match:
                continue

            try:
                dt = datetime.strptime(
                    match.group(1) + match.group(2), "%Y%m%d%H%M%S")
            except ValueError:
                continue

            # Skip past reminders
            if dt < now:
                continue

            # Try to extract the message from the script
            message = _extract_message_from_script(script)
            if not message:
                message = script.stem  # fallback to filename

            reminders.append({
                "id": script.stem,
                "message": message,
                "time": dt.isoformat(),
                "datetime": dt,
            })

        reminders.sort(key=lambda r: r["datetime"])
        return reminders


def _extract_message_from_script(script_path: Path) -> str:
    """Extract the reminder message from a generated reminder script."""
    try:
        text = script_path.read_text(encoding="utf-8")
        # The message is usually set as: message = "..." (with json.dumps escaping)
        # or as the first assignment
        match = re.search(
            r'message\s*=\s*"([^"]*(?:\\"[^"]*)*)"', text)
        if match:
            msg = match.group(1).replace('\\"', '"').strip()
            if msg and msg != "FRIDAY Reminder":
                return msg
        # Fallback: look for the notification title + message pattern
        match = re.search(r'title="FRIDAY Reminder".*?message=([^,\)]+)', text)
        if match:
            return match.group(1).strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def _fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m"


# ── Singleton ────────────────────────────────────────────────────────────────

_instance: Optional[ProactiveCheckin] = None


def get_proactive_checkin() -> ProactiveCheckin:
    global _instance
    if _instance is None:
        _instance = ProactiveCheckin()
    return _instance
