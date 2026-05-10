#!/usr/bin/env python3
"""
curiosity.py — FRIDAY Curiosity & Autonomous Exploration Module (v2.0)
======================================================================

New in v2.0:
  [FEAT-1] Time-decay curiosity — explored items regain curiosity over days
  [FEAT-2] User-interest mirroring — tracks user topic patterns, suggests related
  [FEAT-3] Confidence-driven curiosity — low-confidence tools get higher priority
  [FEAT-4] Idle exploration trigger — auto-explores after 30min idle
  [FEAT-5] Surprise tracking — flags unexpected failures for investigation
"""

import json
import math
import random
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict


BRAIN_DIR = Path(__file__).parent.resolve()
CURIOSITY_FILE = BRAIN_DIR / "curiosity.json"

# How many seconds of idle before auto-exploration triggers
IDLE_THRESHOLD_SECONDS = 1800  # 30 minutes

# How many days until fully explored items regain max curiosity
CURIOSITY_RECOVERY_DAYS = 3.0

# Topic clusters — exploring one reduces curiosity for related topics
TOPIC_CLUSTERS = {
    "search": ["web_search", "web_research", "deep_dive"],
    "system": ["computer_settings", "computer_control", "desktop_control", "file_controller"],
    "media": ["youtube_video", "gesture_music"],
    "communication": ["send_message", "reminder"],
    "security": ["security_tools"],
    "development": ["code_helper", "dev_agent", "auto_doc"],
    "data": ["data_analysis", "ai_pipeline", "integration_status"],
    "visual": ["screen_process", "holographic_map", "holo_builder"],
}

# Reverse map: tool -> cluster name
TOOL_TO_CLUSTER = {}
for cluster, tools in TOPIC_CLUSTERS.items():
    for tool in tools:
        TOOL_TO_CLUSTER[tool] = cluster


class CuriosityModule:
    """
    Curiosity and exploration module for FRIDAY.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data = self._empty_store()
        self._load()
        self._last_user_activity = time.time()
        self._idle_callback = None

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 2,
                "created": datetime.now().isoformat(),
                "last_update": "",
                "total_explorations": 0,
                "total_surprises": 0,
            },
            "novelty_tracker": {},
            "exploration_history": [],
            "curiosity_queue": [],
            "skill_curiosity": {},
            # FEAT-2: Track what the user talks about
            "user_interests": {
                # topic_keyword: {
                #   "count": 0,
                #   "last_seen": "",
                #   "related_suggested": False,
                # }
            },
            # FEAT-5: Unexpected events worth investigating
            "surprises": [
                # {
                #   "timestamp": "",
                #   "tool": "",
                #   "what": "",
                #   "severity": "low" | "medium" | "high",
                #   "investigated": False,
                # }
            ],
            # FEAT-3: Confidence data from self-model (cached here for scoring)
            "confidence_cache": {
                # tool_name: {"confidence": 0.5, "last_synced": ""}
            },
        }

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Recursive merge for schema evolution."""
        result = dict(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def _load(self):
        if not CURIOSITY_FILE.exists():
            self._save()
            return
        try:
            raw = CURIOSITY_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            empty = self._empty_store()
            self._data = self._deep_merge(empty, data)
        except (json.JSONDecodeError, IOError):
            self._data = self._empty_store()
            self._save()

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._data["meta"]["last_update"] = datetime.now().isoformat()
            CURIOSITY_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ── Novelty Tracking ────────────────────────────────────────────────

    def encounter(self, concept: str):
        """Register an encounter with a concept (tool, topic, etc)."""
        with self._lock:
            tracker = self._data["novelty_tracker"]
            tracker[concept] = tracker.get(concept, 0) + 1
            if len(tracker) > 200:
                sorted_items = sorted(tracker.items(), key=lambda x: x[1], reverse=True)
                self._data["novelty_tracker"] = dict(sorted_items[:150])
            self._last_user_activity = time.time()

    def get_novelty(self, concept: str) -> float:
        """
        Get novelty score (0-1) for a concept.
        1.0 = completely novel (never seen)
        0.0 = very familiar (seen many times)
        """
        with self._lock:
            count = self._data["novelty_tracker"].get(concept, 0)
            if count == 0:
                return 1.0
            return max(0.0, 1.0 - math.log2(count + 1) * 0.15)

    # ── FEAT-1: Time-Decay Curiosity ────────────────────────────────────

    def get_time_decay_bonus(self, tool_name: str) -> float:
        """
        Curiosity recovers over time since last exploration.
        Fully explored today = 0.0 bonus
        Not explored for 3+ days = up to 0.5 bonus
        """
        with self._lock:
            skill = self._data["skill_curiosity"].get(tool_name, {})
            last_explored = skill.get("last_explored", "")

        if not last_explored:
            return 0.5  # Never explored = max bonus

        try:
            last_dt = datetime.fromisoformat(last_explored)
            days_since = (datetime.now() - last_dt).total_seconds() / 86400.0
        except (ValueError, TypeError):
            return 0.3

        # Sigmoid recovery: slow at first, then faster
        # At 0 days: 0.0, at 1.5 days: ~0.25, at 3 days: ~0.45
        recovery = 0.5 / (1 + math.exp(-1.5 * (days_since - CURIOSITY_RECOVERY_DAYS / 2)))
        return round(recovery, 3)

    # ── FEAT-2: User Interest Mirroring ─────────────────────────────────

    def track_user_topic(self, topic: str):
        """
        Track a topic the user asked about.
        Extracts keywords and builds an interest profile.
        """
        # Normalize: lowercase, split, take words > 3 chars
        keywords = set()
        for word in topic.lower().split():
            cleaned = ''.join(c for c in word if c.isalnum())
            if len(cleaned) > 3 and cleaned not in {
                "what", "when", "where", "which", "about", "that",
                "this", "from", "with", "have", "been", "will",
                "would", "could", "should", "your", "tell", "give",
                "show", "find", "search", "look", "help", "need",
                "like", "just", "also", "more", "some", "here",
                "there", "then", "than", "them", "they", "their",
            }:
                keywords.add(cleaned)

        with self._lock:
            interests = self._data["user_interests"]
            for kw in keywords:
                if kw not in interests:
                    interests[kw] = {
                        "count": 0,
                        "last_seen": "",
                        "related_suggested": False,
                    }
                interests[kw]["count"] += 1
                interests[kw]["last_seen"] = datetime.now().isoformat()

            # Cap at 100 keywords, keep most frequent
            if len(interests) > 100:
                sorted_kw = sorted(interests.items(), key=lambda x: x[1]["count"], reverse=True)
                self._data["user_interests"] = dict(sorted_kw[:80])

    def get_user_top_interests(self, limit: int = 5) -> list[str]:
        """Get the user's most frequent topic keywords."""
        with self._lock:
            interests = self._data["user_interests"]
        sorted_kw = sorted(interests.items(), key=lambda x: x[1]["count"], reverse=True)
        return [kw for kw, _ in sorted_kw[:limit]]

    def get_related_suggestions(self) -> list[str]:
        """
        Suggest tools related to user interests that haven't been tried.
        Example: user asks about 'security' a lot → suggest security_tools.
        """
        top_interests = self.get_user_top_interests(10)
        if not top_interests:
            return []

        suggestions = []
        with self._lock:
            for keyword in top_interests:
                for cluster_name, tools in TOPIC_CLUSTERS.items():
                    if keyword in cluster_name or cluster_name in keyword:
                        for tool in tools:
                            skill = self._data["skill_curiosity"].get(tool, {})
                            count = skill.get("exploration_count", 0)
                            if count < 3:
                                suggestions.append(tool)

        return list(set(suggestions))

    # ── FEAT-3: Confidence-Driven Curiosity ─────────────────────────────

    def sync_confidence(self, tool_name: str, confidence: float):
        """
        Sync confidence data from the self-model.
        Called by main.py after tool execution.
        """
        with self._lock:
            self._data["confidence_cache"][tool_name] = {
                "confidence": round(confidence, 3),
                "last_synced": datetime.now().isoformat(),
            }

    def get_confidence_penalty(self, tool_name: str) -> float:
        """
        Low confidence = higher curiosity priority.
        Returns 0.0-0.5 bonus for low-confidence tools.
        """
        with self._lock:
            cached = self._data["confidence_cache"].get(tool_name, {})
            confidence = cached.get("confidence", 0.5)

        # Invert: low confidence = high bonus
        # confidence 0.2 → bonus 0.4
        # confidence 0.8 → bonus 0.1
        return round(max(0.0, (1.0 - confidence) * 0.5), 3)

    # ── FEAT-5: Surprise Tracking ───────────────────────────────────────

    def record_surprise(self, tool_name: str, what: str,
                        severity: str = "medium"):
        """
        Record an unexpected event worth investigating.
        Called when a tool fails in an unusual way or returns unexpected data.
        """
        with self._lock:
            self._data["surprises"].append({
                "timestamp": datetime.now().isoformat(),
                "tool": tool_name,
                "what": what[:200],
                "severity": severity,
                "investigated": False,
            })
            self._data["surprises"] = self._data["surprises"][-50:]
            self._data["meta"]["total_surprises"] += 1
            self._save()

    def get_uninvestigated_surprises(self) -> list[dict]:
        """Get surprises that haven't been looked into yet."""
        with self._lock:
            return [s for s in self._data["surprises"]
                    if not s.get("investigated", False)]

    def mark_surprise_investigated(self, index: int):
        """Mark a surprise as investigated."""
        with self._lock:
            surprises = self._data["surprises"]
            if 0 <= index < len(surprises):
                surprises[index]["investigated"] = True
                self._save()

    # ── FEAT-4: Idle Exploration ────────────────────────────────────────

    def get_idle_duration(self) -> float:
        """Seconds since last user activity."""
        return time.time() - self._last_user_activity

    def should_idle_explore(self) -> bool:
        """
        Should FRIDAY explore something during idle time?
        Returns True if idle > 30min AND there's something worth exploring.
        """
        if self.get_idle_duration() < IDLE_THRESHOLD_SECONDS:
            return False
        queue = self.get_curiosity_queue()
        return len(queue) > 0 and queue[0].get("priority", 0) > 0.4

    def get_idle_exploration_task(self) -> dict | None:
        """
        Get a task for idle-time exploration.
        Returns a dict with what to do and why.
        """
        if not self.should_idle_explore():
            return None

        queue = self.get_curiosity_queue()
        if not queue:
            return None

        top = queue[0]
        return {
            "action": "explore",
            "target": top["target"],
            "type": top.get("type", "tool"),
            "reason": top.get("reason", "Curiosity"),
            "prompt": f"During idle time, explore '{top['target']}' to improve "
                      f"understanding. Reason: {top.get('reason', 'curiosity')}",
        }

    # ── Information Gain Estimation ─────────────────────────────────────

    def estimate_information_gain(self, tool_name: str,
                                    active_inference_stats: dict = None) -> float:
        """Estimate how much FRIDAY would learn by exploring a tool."""
        with self._lock:
            skill_data = self._data["skill_curiosity"].get(tool_name, {
                "exploration_count": 0,
                "curiosity_score": 0.5,
            })

        uncertainty = 0.8
        if active_inference_stats:
            tool_stats = active_inference_stats.get(tool_name, {})
            uncertainty = tool_stats.get("uncertainty", 0.8)

        exploration_count = skill_data.get("exploration_count", 0)
        novelty_factor = 1.0 if exploration_count == 0 else max(
            0.1, 1.0 / math.sqrt(exploration_count)
        )
        uncertainty_factor = uncertainty
        info_gain = (novelty_factor * 0.4 + uncertainty_factor * 0.6)
        return round(min(1.0, info_gain), 3)

    # ── Curiosity Queue Management ───────────────────────────────────────

    def update_curiosity_queue(self,
                                active_inference_engine=None,
                                active_inference_stats: dict = None,
                                available_tools: list[str] = None):
        """
        Refresh the curiosity queue with high-value exploration targets.
        Combines all scoring factors: novelty, info gain, time decay,
        confidence penalty, user interests, and surprise investigation.
        """
        if available_tools is None:
            available_tools = [
                "web_search", "weather_report", "youtube_video",
                "screen_process", "computer_settings", "browser_control",
                "file_controller", "code_helper", "desktop_control",
                "open_app", "game_updater", "flight_finder",
                "send_message", "reminder", "web_research",
                "ai_pipeline", "data_analysis", "deep_dive",
                "security_tools", "holo_builder", "holographic_map",
            ]

        ai_stats = active_inference_stats or {}
        if active_inference_engine and not ai_stats:
            for tool in available_tools:
                try:
                    pred = active_inference_engine.predict_outcome(tool)
                    ai_stats[tool] = pred
                except Exception:
                    pass

        # FEAT-2: Get user-interest suggestions
        interest_suggestions = set(self.get_related_suggestions())

        scored = []
        for tool in available_tools:
            info_gain = self.estimate_information_gain(tool, ai_stats)
            novelty = self.get_novelty(tool)
            time_decay = self.get_time_decay_bonus(tool)
            conf_penalty = self.get_confidence_penalty(tool)

            # Base score
            combined = (
                info_gain * 0.30 +
                novelty * 0.25 +
                time_decay * 0.20 +
                conf_penalty * 0.15
            )

            # FEAT-2: Bonus for user-interest alignment
            if tool in interest_suggestions:
                combined += 0.15

            scored.append((tool, round(combined, 3)))

        scored.sort(key=lambda x: x[1], reverse=True)

        new_queue = []
        for tool, score in scored[:5]:
            if score > 0.25:
                new_queue.append({
                    "target": tool,
                    "type": "tool",
                    "priority": score,
                    "reason": self._generate_curiosity_reason(
                        tool, score, ai_stats, tool in interest_suggestions
                    ),
                })

        with self._lock:
            self._data["curiosity_queue"] = new_queue
            self._save()

        return new_queue

    def _generate_curiosity_reason(self, tool: str, score: float,
                                     ai_stats: dict,
                                     user_interested: bool = False) -> str:
        """Generate a human-readable reason for curiosity about a tool."""
        tool_stats = ai_stats.get(tool, {})
        uncertainty = tool_stats.get("uncertainty", 0.8)

        with self._lock:
            skill_data = self._data["skill_curiosity"].get(tool, {})
            count = skill_data.get("exploration_count", 0)
            conf = self._data["confidence_cache"].get(tool, {}).get("confidence", 0.5)

        reasons = []
        if count == 0:
            reasons.append("never explored")
        elif uncertainty > 0.7:
            reasons.append(f"high uncertainty ({uncertainty:.0%})")
        elif count < 3:
            reasons.append(f"only tried {count}x")

        if conf < 0.4:
            reasons.append(f"low confidence ({conf:.0%})")

        time_bonus = self.get_time_decay_bonus(tool)
        if time_bonus > 0.2:
            reasons.append("not explored recently")

        if user_interested:
            reasons.append("matches your interests")

        return "; ".join(reasons) if reasons else f"curiosity score: {score:.0%}"

    def get_curiosity_queue(self) -> list[dict]:
        """Get the current curiosity queue, sorted by priority."""
        with self._lock:
            queue = list(self._data["curiosity_queue"])
        queue.sort(key=lambda x: x.get("priority", 0), reverse=True)
        return queue

    def get_top_curiosity(self) -> dict | None:
        """Get the single highest-priority curiosity target."""
        queue = self.get_curiosity_queue()
        return queue[0] if queue else None

    # ── Exploration Tracking ─────────────────────────────────────────────

    def record_exploration(self, target: str, target_type: str,
                            outcome: str, info_gain: float = 0.0):
        """Record that FRIDAY explored something."""
        with self._lock:
            self._data["exploration_history"].append({
                "timestamp": datetime.now().isoformat(),
                "target": target,
                "type": target_type,
                "outcome": outcome[:200],
                "info_gain": info_gain,
            })
            self._data["exploration_history"] = self._data["exploration_history"][-100:]
            self._data["meta"]["total_explorations"] += 1

            if target_type == "tool":
                skill = self._data["skill_curiosity"].get(target, {
                    "exploration_count": 0,
                    "curiosity_score": 0.5,
                    "last_explored": "",
                })
                skill["exploration_count"] += 1
                skill["last_explored"] = datetime.now().isoformat()
                skill["curiosity_score"] = round(
                    max(0.0, 1.0 - math.log2(skill["exploration_count"] + 1) * 0.15), 3
                )
                self._data["skill_curiosity"][target] = skill

            self._save()

    # ── Query ───────────────────────────────────────────────────────────

    def should_explore(self) -> bool:
        """Check if there's a high-value exploration opportunity."""
        queue = self.get_curiosity_queue()
        return len(queue) > 0 and queue[0].get("priority", 0) > 0.5

    def get_stats(self) -> dict:
        """Get curiosity module statistics."""
        with self._lock:
            uninvestigated = sum(
                1 for s in self._data["surprises"]
                if not s.get("investigated", False)
            )
            return {
                "total_explorations": self._data["meta"]["total_explorations"],
                "concepts_tracked": len(self._data["novelty_tracker"]),
                "queue_size": len(self._data["curiosity_queue"]),
                "tools_with_curiosity": sum(
                    1 for s in self._data["skill_curiosity"].values()
                    if s.get("curiosity_score", 0) > 0.3
                ),
                "user_interests_tracked": len(self._data["user_interests"]),
                "total_surprises": self._data["meta"].get("total_surprises", 0),
                "uninvestigated_surprises": uninvestigated,
                "idle_seconds": int(self.get_idle_duration()),
            }

    def format_for_prompt(self, max_chars: int = 400) -> str:
        """Format curiosity state for system prompt."""
        queue = self.get_curiosity_queue()[:3]
        interests = self.get_user_top_interests(3)
        surprises = self.get_uninvestigated_surprises()[:2]

        parts = []
        if queue:
            parts.append("[CURIOSITY — Things I could learn about]")
            for item in queue:
                parts.append(f"  • {item['target']} ({item.get('reason', '')})")

        if interests:
            parts.append(f"[USER INTERESTS] {', '.join(interests)}")

        if surprises:
            parts.append("[SURPRISES — Worth investigating]")
            for s in surprises:
                parts.append(f"  • {s['tool']}: {s['what'][:60]}")

        if not parts:
            return ""

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars].rsplit("\n", 1)[0] + "\n  [...]"
        return result


# ── Singleton ───────────────────────────────────────────────────────────────

_curiosity = None
_curiosity_lock = threading.Lock()


def get_curiosity_module() -> CuriosityModule:
    """Get the singleton curiosity module instance."""
    global _curiosity
    if _curiosity is None:
        with _curiosity_lock:
            if _curiosity is None:
                _curiosity = CuriosityModule()
    return _curiosity
