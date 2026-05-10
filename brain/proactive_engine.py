# -*- coding: utf-8 -*-
"""
proactive_engine.py — FRIDAY Proactive Assistant System
========================================================
Analyzes user patterns and proactively suggests actions.
Inspired by 2026 AI assistants (Gemini Agent, Claude, GPT-5).

Core capabilities:
- Pattern learning from user behavior
- Proactive suggestions based on context
- Task anticipation (prepare before asked)
- Morning/evening briefings with relevant info
"""

import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from collections import defaultdict


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROACTIVE_FILE = DATA_DIR / "proactive_patterns.json"


class ProactiveEngine:
    """
    Proactive assistant engine that learns from user behavior
    and suggests actions before being asked.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._patterns: dict = {}
        self._suggestions_queue: List[dict] = []
        self._load()
        print("[ProactiveEngine] Initialized")

    def _load(self):
        """Load learned patterns from disk."""
        if PROACTIVE_FILE.exists():
            try:
                data = json.loads(PROACTIVE_FILE.read_text(encoding="utf-8"))
                raw_patterns = data.get("patterns", {})
                # Convert lists back to sets
                self._patterns = {}
                for k, v in raw_patterns.items():
                    self._patterns[k] = {
                        "count": v.get("count", 0),
                        "last_seen": v.get("last_seen"),
                        "contexts": set(v.get("contexts", [])),
                        "success_count": v.get("success_count", 0),
                    }
                print(f"[ProactiveEngine] Loaded {len(self._patterns)} patterns")
            except Exception as e:
                print(f"[ProactiveEngine] Load error: {e}")
                self._patterns = {}

    def _save(self):
        """Save patterns to disk."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            # Convert sets to lists for JSON serialization
            patterns_json = {}
            for k, v in self._patterns.items():
                patterns_json[k] = {
                    "count": v.get("count", 0),
                    "last_seen": v.get("last_seen"),
                    "contexts": list(v.get("contexts", set())),
                    "success_count": v.get("success_count", 0),
                }
            PROACTIVE_FILE.write_text(
                json.dumps({"patterns": patterns_json}, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[ProactiveEngine] Save error: {e}")

    def record_user_action(self, action: str, context: str = "", result: str = ""):
        """Record a user action to learn patterns."""
        key = f"{action}:{context[:50]}" if context else action
        with self._lock:
            if key not in self._patterns:
                self._patterns[key] = {
                    "count": 0,
                    "last_seen": None,
                    "contexts": set(),
                    "success_count": 0,
                }
            self._patterns[key]["count"] += 1
            self._patterns[key]["last_seen"] = datetime.now().isoformat()
            if context:
                self._patterns[key]["contexts"].add(context[:100])
            if result in ("success", "ok", "done"):
                self._patterns[key]["success_count"] += 1
        self._save()

    def get_suggestions(self, current_context: dict) -> List[dict]:
        """Get proactive suggestions based on learned patterns and context."""
        suggestions = []
        now = datetime.now()
        hour = now.hour

        with self._lock:
            patterns = dict(self._patterns)

        # Time-based suggestions
        if 6 <= hour < 9:
            suggestions.append({
                "type": "morning_briefing",
                "action": "Provide morning briefing",
                "reason": "Time is morning - check calendar, weather, tasks",
                "priority": "high",
            })

        if 18 <= hour < 20:
            suggestions.append({
                "type": "evening_summary",
                "action": "Summarize today's progress",
                "reason": "Time is evening - review what was accomplished",
                "priority": "medium",
            })

        # Pattern-based suggestions
        for key, data in patterns.items():
            if data.get("count", 0) >= 3:
                success_rate = data.get("success_count", 0) / max(data.get("count", 1), 1)
                if success_rate >= 0.7:
                    action = key.split(":")[0]
                    # Check if this action makes sense in current context
                    if self._matches_context(action, current_context):
                        suggestions.append({
                            "type": "pattern_based",
                            "action": action,
                            "reason": f"You often do this ({data['count']}x)",
                            "priority": "medium",
                            "confidence": success_rate,
                        })

        # Context-based suggestions
        context_keywords = current_context.get("keywords", [])
        if "meeting" in context_keywords or "call" in context_keywords:
            suggestions.append({
                "type": "meeting_prep",
                "action": "Prepare for meeting",
                "reason": "Meeting detected - offer to take notes",
                "priority": "high",
            })

        if "research" in context_keywords or "find" in context_keywords:
            suggestions.append({
                "type": "research_help",
                "action": "Deep research",
                "reason": "Research task detected - offer web search",
                "priority": "medium",
            })

        if "code" in context_keywords or "debug" in context_keywords:
            suggestions.append({
                "type": "coding_help",
                "action": "Code assistant",
                "reason": "Coding detected - offer debugging help",
                "priority": "high",
            })

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 2))

        return suggestions[:5]

    def _matches_context(self, action: str, context: dict) -> bool:
        """Check if an action matches the current context."""
        context_keywords = context.get("keywords", [])
        action_keywords = {
            "weather_report": ["weather", "outside", "rain"],
            "web_search": ["search", "find", "look up"],
            "reminder": ["remind", "later", "don't forget"],
            "open_app": ["open", "launch", "start"],
            "code_helper": ["code", "debug", "write", "fix"],
        }
        relevant = action_keywords.get(action, [])
        return any(kw in context_keywords for kw in relevant) if relevant else True

    def get_top_patterns(self, limit: int = 10) -> List[dict]:
        """Get the most frequent user actions."""
        with self._lock:
            sorted_patterns = sorted(
                self._patterns.items(),
                key=lambda x: x[1].get("count", 0),
                reverse=True
            )
        return [
            {
                "action": key,
                "count": data.get("count", 0),
                "success_rate": data.get("success_count", 0) / max(data.get("count", 1), 1),
            }
            for key, data in sorted_patterns[:limit]
        ]

    def clear_patterns(self):
        """Clear all learned patterns."""
        with self._lock:
            self._patterns.clear()
        self._save()
        print("[ProactiveEngine] Patterns cleared")


# Singleton
_engine: Optional[ProactiveEngine] = None
_engine_lock = threading.Lock()


def get_proactive_engine() -> ProactiveEngine:
    """Get the singleton proactive engine."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = ProactiveEngine()
    return _engine