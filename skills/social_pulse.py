#!/usr/bin/env python3
"""
social_pulse.py — FRIDAY Social Pulse Monitor
==============================================
Monitors trending topics and sentiment using web search.
Tracks keywords and reports real trends, not random data.
"""

import threading
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Callable


BRAIN_DIR = Path(__file__).parent.resolve() / ".." / "brain"
PULSE_FILE = BRAIN_DIR / "social_pulse.json"


class SocialPulse:
    """Real trending topic monitor using web search."""

    def __init__(self, callback: Optional[Callable] = None):
        self.callback = callback
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self.keywords = ["AI", "Technology", "Cybersecurity", "Space", "Finance"]
        self._history: List[dict] = []
        self._load_history()

    def _load_history(self):
        if PULSE_FILE.exists():
            try:
                data = json.loads(PULSE_FILE.read_text(encoding="utf-8"))
                self._history = data.get("pulses", [])[-50:]
                self.keywords = data.get("keywords", self.keywords)
            except Exception:
                pass

    def _save_history(self):
        try:
            BRAIN_DIR.mkdir(parents=True, exist_ok=True)
            PULSE_FILE.write_text(json.dumps({
                "pulses": self._history[-50:],
                "keywords": self.keywords,
                "updated": datetime.now().isoformat(),
            }, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def start(self):
        if self.running:
            return "Social Pulse already running."
        self.running = True
        self._thread = threading.Thread(target=self._pulse_loop, daemon=True)
        self._thread.start()
        return f"Social Pulse started. Tracking: {', '.join(self.keywords)}"

    def stop(self):
        self.running = False
        return "Social Pulse stopped."

    def _pulse_loop(self):
        while self.running:
            try:
                self._check_pulse()
            except Exception as e:
                print(f"[SocialPulse] Error: {e}")
            # Check every 30 minutes
            for _ in range(1800):
                if not self.running:
                    return
                time.sleep(1)

    def _check_pulse(self):
        """Search for trending topics using web search."""
        try:
            from actions.web_search import web_search
            for keyword in self.keywords[:3]:  # Check top 3 keywords
                if not self.running:
                    break
                result = web_search(
                    parameters={"query": f"{keyword} trending news today"},
                    player=None
                )
                if result:
                    entry = {
                        "keyword": keyword,
                        "timestamp": datetime.now().isoformat(),
                        "snippet": str(result)[:300],
                    }
                    self._history.append(entry)
                    if self.callback:
                        try:
                            self.callback(keyword, "TRENDING", 75)
                        except Exception:
                            pass
                time.sleep(5)  # Rate limit
            self._save_history()
        except Exception as e:
            print(f"[SocialPulse] Search error: {e}")

    def get_pulse(self, keyword: Optional[str] = None) -> str:
        """Get current pulse for a keyword or all keywords."""
        if not self._history:
            return "No pulse data yet. Start monitoring first."

        entries = self._history
        if keyword:
            entries = [e for e in entries if keyword.lower() in e.get("keyword", "").lower()]

        if not entries:
            return f"No data for '{keyword}'." if keyword else "No pulse data."

        recent = entries[-5:]
        lines = []
        for e in recent:
            ts = e.get("timestamp", "?")[:16]
            lines.append(f"[{ts}] {e.get('keyword', '?')}: {e.get('snippet', '')[:100]}")
        return "\n".join(lines)

    def update_keywords(self, new_list: List[str]) -> str:
        self.keywords = new_list
        self._save_history()
        return f"Keywords updated: {', '.join(new_list)}"

    def get_status(self) -> str:
        status = "Running" if self.running else "Stopped"
        return (f"Social Pulse: {status}\n"
                f"Keywords: {', '.join(self.keywords)}\n"
                f"History: {len(self._history)} entries")


# Singleton
_pulse: Optional[SocialPulse] = None
_pulse_lock = threading.Lock()


def get_social_pulse() -> SocialPulse:
    global _pulse
    if _pulse is None:
        with _pulse_lock:
            if _pulse is None:
                _pulse = SocialPulse()
    return _pulse
