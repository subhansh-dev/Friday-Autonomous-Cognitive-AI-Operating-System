#!/usr/bin/env python3
"""
self_model.py — FRIDAY Self-Model System (patched v1.1)
Changes from v1.0:
  [FIX-1] _save_async now flushes via background thread every 60s — no more data loss
  [FIX-2] Schema evolution uses recursive deep merge — new nested keys get added
"""

import json
import threading
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict


BRAIN_DIR = Path(__file__).parent.resolve()
SELF_MODEL_FILE = BRAIN_DIR / "self_model.json"


class SelfModel:
    """
    Persistent self-model for FRIDAY.

    Tracks:
    - Tool competence: success rates, confidence, skill level
    - Session awareness: state, uptime, interaction counts
    - Personality metrics: verbosity, proactivity, emotional tone distribution
    - Growth tracking: skill acquisition over time, learning velocity
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data = self._empty_model()
        self._dirty = False
        self._load()
        self._session_start = time.time()
        self._interaction_count = 0
        # FIX-1: background flush thread — saves dirty data every 60s
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()

    def _empty_model(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "total_sessions": 0,
                "total_interactions": 0,
            },
            "capabilities": {},
            "state": {
                "current_status": "initialized",
                "uptime_seconds": 0,
                "session_count": 0,
                "current_mood": "neutral",
                "focus_mode": False,
                "think_mode": False,
            },
            "personality": {
                "verbosity_score": 0.5,
                "proactivity_score": 0.5,
                "tone_distribution": {
                    "neutral": 0,
                    "witty": 0,
                    "concerned": 0,
                    "urgent": 0,
                    "warm": 0,
                    "seductive": 0,
                },
                "interaction_patterns": {
                    "avg_response_time_ms": 0,
                    "tool_calls_per_session": 0,
                    "preferred_tools": [],
                },
            },
            "growth": {
                "skills_acquired": [],
                "learning_velocity": 0.0,
                "milestones": [],
                "confidence_curve": [],
            },
        }

    # ── Persistence ─────────────────────────────────────────────────────

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """FIX-2: Recursive merge — new nested keys from base get added to override."""
        result = dict(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    def _load(self):
        if not SELF_MODEL_FILE.exists():
            self._save()
            return
        try:
            raw = SELF_MODEL_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            empty = self._empty_model()
            # FIX-2: deep merge handles new nested keys from schema evolution
            self._data = self._deep_merge(empty, data)
        except (json.JSONDecodeError, IOError):
            self._data = self._empty_model()
            self._save()

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._data["meta"]["last_updated"] = datetime.now().isoformat()
            SELF_MODEL_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # FIX-1: Background flush loop — saves dirty data every 60s
    def _flush_loop(self):
        while True:
            time.sleep(60)
            self.flush()

    def _save_async(self):
        """Mark dirty — background flusher will save within 60s."""
        self._dirty = True

    def flush(self):
        """Force save to disk if dirty."""
        if self._dirty:
            self._save()
            self._dirty = False

    # ── Capability Tracking ─────────────────────────────────────────────

    def record_tool_result(self, tool_name: str, success: bool,
                           duration_ms: float = 0.0, error: str = ""):
        """
        Record a tool execution result and update confidence/skill level.
        Called automatically by the tool execution system.
        """
        with self._lock:
            cap = self._data["capabilities"].get(tool_name, {
                "total_calls": 0,
                "successes": 0,
                "failures": 0,
                "avg_duration_ms": 0.0,
                "confidence": 0.5,
                "skill_level": "unknown",
                "last_used": "",
                "recent_errors": [],
                "consecutive_failures": 0,
                "consecutive_successes": 0,
            })

            cap["total_calls"] += 1
            cap["last_used"] = datetime.now().isoformat()

            if success:
                cap["successes"] += 1
                cap["consecutive_successes"] = cap.get("consecutive_successes", 0) + 1
                cap["consecutive_failures"] = 0
            else:
                cap["failures"] += 1
                cap["consecutive_failures"] = cap.get("consecutive_failures", 0) + 1
                cap["consecutive_successes"] = 0
                if error:
                    cap["recent_errors"].append(error[:100])
                    cap["recent_errors"] = cap["recent_errors"][-5:]

            # Rolling average duration (exponential)
            if cap["total_calls"] == 1:
                cap["avg_duration_ms"] = duration_ms
            else:
                cap["avg_duration_ms"] = (
                    cap["avg_duration_ms"] * 0.9 + duration_ms * 0.1
                )

            # Confidence: weighted recent success rate
            total = cap["successes"] + cap["failures"]
            if total > 0:
                raw_confidence = cap["successes"] / max(total, 1)
                # Penalize for consecutive failures
                if cap.get("consecutive_failures", 0) >= 3:
                    raw_confidence *= max(0.1, 1.0 - cap["consecutive_failures"] * 0.15)
                # Bonus for consecutive successes
                if cap.get("consecutive_successes", 0) >= 5:
                    raw_confidence = min(1.0, raw_confidence + 0.1)
                cap["confidence"] = round(max(0.0, min(1.0, raw_confidence)), 3)

            # Skill level based on volume + success rate
            if cap["total_calls"] < 3:
                cap["skill_level"] = "unknown"
            elif cap["total_calls"] < 10:
                cap["skill_level"] = "learning"
            elif cap["total_calls"] < 30:
                cap["skill_level"] = "practicing" if cap["confidence"] < 0.8 else "proficient"
            else:
                cap["skill_level"] = "proficient" if cap["confidence"] < 0.9 else "expert"

            self._data["capabilities"][tool_name] = cap
            self._save_async()

    def get_capability(self, tool_name: str) -> dict:
        """Get the capability model for a specific tool."""
        with self._lock:
            return dict(self._data["capabilities"].get(tool_name, {
                "total_calls": 0, "confidence": 0.5, "skill_level": "unknown"
            }))

    def get_confidence(self, tool_name: str) -> float:
        """Get confidence score (0.0-1.0) for a tool."""
        with self._lock:
            cap = self._data["capabilities"].get(tool_name, {})
            return cap.get("confidence", 0.5)

    def get_skill_level(self, tool_name: str) -> str:
        """Get skill level label for a tool."""
        with self._lock:
            cap = self._data["capabilities"].get(tool_name, {})
            return cap.get("skill_level", "unknown")

    # ── State Tracking ─────────────────────────────────────────────────

    def update_state(self, **kwargs):
        """Update state fields (status, focus_mode, think_mode, mood)."""
        with self._lock:
            for key, val in kwargs.items():
                if key in self._data["state"]:
                    self._data["state"][key] = val
            self._data["state"]["uptime_seconds"] = int(time.time() - self._session_start)
            self._save_async()

    def start_session(self):
        """Called when a new session begins."""
        with self._lock:
            self._data["meta"]["total_sessions"] += 1
            self._data["state"]["session_count"] = self._data["meta"]["total_sessions"]
            self._data["state"]["current_status"] = "connected"
        self._session_start = time.time()
        self._save()

    def record_interaction(self):
        """Increment interaction counter."""
        with self._lock:
            self._interaction_count += 1
            self._data["meta"]["total_interactions"] += 1

    # ── Personality Tracking ────────────────────────────────────────────

    def record_tone(self, tone: str):
        """Record the tone used in a response."""
        with self._lock:
            dist = self._data["personality"]["tone_distribution"]
            dist[tone] = dist.get(tone, 0) + 1
            self._save_async()

    def get_dominant_tone(self) -> str:
        """Get the most frequently used tone."""
        with self._lock:
            dist = self._data["personality"]["tone_distribution"]
            if not dist or all(v == 0 for v in dist.values()):
                return "neutral"
            return max(dist, key=dist.get)

    # ── Growth Tracking ────────────────────────────────────────────────

    def record_milestone(self, milestone: str):
        """Record a growth milestone."""
        with self._lock:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "milestone": milestone,
            }
            self._data["growth"]["milestones"].append(entry)
            self._save()

    def record_skill_acquired(self, skill_name: str):
        """Record acquisition of a new capability."""
        with self._lock:
            acquired = [s["name"] for s in self._data["growth"]["skills_acquired"]]
            if skill_name not in acquired:
                entry = {
                    "name": skill_name,
                    "acquired_at": datetime.now().isoformat(),
                }
                self._data["growth"]["skills_acquired"].append(entry)
                self._save()

    def update_confidence_curve(self):
        """Record current average confidence for growth tracking."""
        with self._lock:
            caps = self._data["capabilities"].values()
            if caps:
                avg_conf = sum(c.get("confidence", 0.5) for c in caps) / max(len(caps), 1)
                self._data["growth"]["confidence_curve"].append([
                    datetime.now().isoformat(), round(avg_conf, 3)
                ])
                self._data["growth"]["confidence_curve"] = \
                    self._data["growth"]["confidence_curve"][-100:]

    # ── Query ───────────────────────────────────────────────────────────

    def get_summary(self) -> dict:
        """Get a concise summary of the self-model."""
        with self._lock:
            caps = self._data["capabilities"]
            total_tools = len(caps)
            proficient = sum(1 for c in caps.values()
                             if c.get("skill_level") in ("proficient", "expert"))
            learning = sum(1 for c in caps.values()
                           if c.get("skill_level") in ("learning", "unknown"))

            state = dict(self._data["state"])
            state["uptime_seconds"] = int(time.time() - self._session_start)

            return {
                "capabilities": {
                    "total_tools": total_tools,
                    "proficient": proficient,
                    "learning": learning,
                    "avg_confidence": round(
                        sum(c.get("confidence", 0.5) for c in caps.values()) / max(len(caps), 1), 3
                    ) if caps else 0.5,
                },
                "state": state,
                "personality": {
                    "dominant_tone": self.get_dominant_tone(),
                    "verbosity": self._data["personality"]["verbosity_score"],
                    "proactivity": self._data["personality"]["proactivity_score"],
                },
                "growth": {
                    "total_milestones": len(self._data["growth"]["milestones"]),
                    "skills_acquired": len(self._data["growth"]["skills_acquired"]),
                    "total_sessions": self._data["meta"]["total_sessions"],
                    "total_interactions": self._data["meta"]["total_interactions"],
                },
            }

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """
        Format self-model for inclusion in system prompt.
        Gives FRIDAY awareness of her own capabilities and state.
        """
        summary = self.get_summary()
        caps = summary["capabilities"]
        state = summary["state"]
        growth = summary["growth"]

        parts = [
            "[SELF-MODEL — My capabilities and state]",
            f"Current status: {state.get('current_status', 'unknown')}",
            f"Session: #{growth['total_sessions']} | "
            f"Uptime: {state.get('uptime_seconds', 0)}s | "
            f"Interactions: {growth['total_interactions']}",
            f"Tools: {caps['total_tools']} total "
            f"({caps['proficient']} proficient, {caps['learning']} learning) | "
            f"Avg confidence: {caps['avg_confidence']:.0%}",
            f"Dominant tone: {summary['personality']['dominant_tone']}",
        ]

        # Add low-confidence tools (areas to be careful with)
        low_conf = []
        with self._lock:
            for tname, cap in self._data["capabilities"].items():
                if cap.get("confidence", 0.5) < 0.4 and cap.get("total_calls", 0) >= 2:
                    low_conf.append(f"{tname} ({cap['confidence']:.0%})")
        if low_conf:
            parts.append(f"Low confidence: {', '.join(low_conf[:3])}")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars].rsplit("\n", 1)[0] + "\n[...]"
        return result


# ── Singleton ───────────────────────────────────────────────────────────────

_self_model = None
_self_model_lock = threading.Lock()


def get_self_model() -> SelfModel:
    """Get the singleton self-model instance."""
    global _self_model
    if _self_model is None:
        with _self_model_lock:
            if _self_model is None:
                _self_model = SelfModel()
    return _self_model
