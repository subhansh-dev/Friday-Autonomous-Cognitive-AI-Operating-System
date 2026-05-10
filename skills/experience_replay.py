# -*- coding: utf-8 -*-
"""
experience_replay.py — FRIDAY Experience Replay & Skill Library
================================================================
After successfully completing multi-step tasks, saves the procedure as
a reusable template. Future similar requests retrieve and adapt templates
instead of planning from scratch. Inspired by Voyager (Wang et al., 2023).
"""

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


BRAIN_DIR = Path(__file__).parent.parent / "brain"
LIBRARY_FILE = BRAIN_DIR / "skill_library.json"

MAX_TEMPLATES = 100
MATCH_THRESHOLD = 0.6


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, strip, collapse spaces."""
    return re.sub(r'\s+', ' ', text.lower().strip())


def _tokenize(text: str) -> set[str]:
    """Simple word tokenization for similarity matching."""
    return set(re.findall(r'[a-z0-9]+', text.lower()))


def _similarity(a: str, b: str) -> float:
    """Jaccard similarity between two texts."""
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


class SkillTemplate:
    """A reusable procedure template extracted from a successful task."""

    def __init__(self, goal: str, steps: list[dict], tools_used: list[str],
                 success_indicators: list[str] = None,
                 parameter_patterns: dict = None):
        self.id = f"tpl_{int(time.time())}"
        self.goal = goal
        self.goal_normalized = _normalize(goal)
        self.steps = steps
        self.tools_used = tools_used
        self.success_indicators = success_indicators or []
        self.parameter_patterns = parameter_patterns or {}
        self.created_at = datetime.now().isoformat()
        self.use_count = 0
        self.success_count = 0
        self.last_used: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "goal_normalized": self.goal_normalized,
            "steps": self.steps,
            "tools_used": self.tools_used,
            "success_indicators": self.success_indicators,
            "parameter_patterns": self.parameter_patterns,
            "created_at": self.created_at,
            "use_count": self.use_count,
            "success_count": self.success_count,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SkillTemplate":
        tpl = cls(
            goal=d["goal"],
            steps=d.get("steps", []),
            tools_used=d.get("tools_used", []),
            success_indicators=d.get("success_indicators", []),
            parameter_patterns=d.get("parameter_patterns", {}),
        )
        tpl.id = d.get("id", tpl.id)
        tpl.goal_normalized = d.get("goal_normalized", _normalize(d["goal"]))
        tpl.created_at = d.get("created_at", tpl.created_at)
        tpl.use_count = d.get("use_count", 0)
        tpl.success_count = d.get("success_count", 0)
        tpl.last_used = d.get("last_used")
        return tpl


class ExperienceReplay:
    """
    Skill library that grows over time through experience.

    - After successful multi-step task: extract template
    - On new task: search library for matching templates
    - Matching templates provide execution shortcuts
    - Templates are rated by success rate
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._templates: list[SkillTemplate] = []
        self._load()

    # ── Persistence ─────────────────────────────────────────────────

    def _load(self):
        if not LIBRARY_FILE.exists():
            return
        try:
            data = json.loads(LIBRARY_FILE.read_text(encoding="utf-8"))
            for td in data.get("templates", []):
                self._templates.append(SkillTemplate.from_dict(td))
        except (json.JSONDecodeError, IOError):
            self._templates = []

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "templates": [t.to_dict() for t in self._templates[-MAX_TEMPLATES:]],
            "updated_at": datetime.now().isoformat(),
        }
        LIBRARY_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Store ───────────────────────────────────────────────────────

    def save_template(self, goal: str, steps: list[dict],
                      tools_used: list[str],
                      success_indicators: list[str] = None,
                      parameter_patterns: dict = None) -> SkillTemplate:
        """
        Save a successful procedure as a reusable template.

        Args:
            goal: what the task accomplished
            steps: list of {"tool": str, "params": dict, "description": str}
            tools_used: list of tool names used
            success_indicators: how to know the task succeeded
            parameter_patterns: parameterized slots for reuse
        """
        tpl = SkillTemplate(goal, steps, tools_used,
                            success_indicators, parameter_patterns)
        with self._lock:
            self._templates.append(tpl)
            self._templates = self._templates[-MAX_TEMPLATES:]
            self._save()
        return tpl

    # ── Retrieve ────────────────────────────────────────────────────

    def find_matching(self, goal: str, threshold: float = MATCH_THRESHOLD,
                      limit: int = 3) -> list[dict]:
        """
        Find templates matching a goal.

        Returns list of {"template": SkillTemplate, "similarity": float}
        sorted by similarity descending.
        """
        goal_norm = _normalize(goal)
        with self._lock:
            matches = []
            for tpl in self._templates:
                sim = _similarity(goal_norm, tpl.goal_normalized)
                if sim >= threshold:
                    matches.append({
                        "template": tpl.to_dict(),
                        "similarity": round(sim, 3),
                        "success_rate": (
                            round(tpl.success_count / max(tpl.use_count, 1), 2)
                            if tpl.use_count > 0 else None
                        ),
                    })

            matches.sort(key=lambda x: x["similarity"], reverse=True)
            return matches[:limit]

    def record_use(self, template_id: str, success: bool):
        """Record that a template was used and whether it succeeded."""
        with self._lock:
            for tpl in self._templates:
                if tpl.id == template_id:
                    tpl.use_count += 1
                    if success:
                        tpl.success_count += 1
                    tpl.last_used = datetime.now().isoformat()
                    self._save()
                    return

    # ── Query ───────────────────────────────────────────────────────

    def get_top_templates(self, limit: int = 10) -> list[dict]:
        """Get templates sorted by success rate."""
        with self._lock:
            rated = []
            for tpl in self._templates:
                if tpl.use_count > 0:
                    rate = tpl.success_count / tpl.use_count
                    rated.append({"template": tpl.to_dict(), "success_rate": round(rate, 2)})
            rated.sort(key=lambda x: x["success_rate"], reverse=True)
            return rated[:limit]

    def get_stats(self) -> dict:
        with self._lock:
            total = len(self._templates)
            total_uses = sum(t.use_count for t in self._templates)
            total_successes = sum(t.success_count for t in self._templates)
            return {
                "templates_stored": total,
                "total_uses": total_uses,
                "total_successes": total_successes,
                "overall_success_rate": round(
                    total_successes / max(total_uses, 1), 2
                ),
            }

    def format_for_prompt(self, goal: str, max_chars: int = 400) -> str:
        """Format matching templates for system prompt injection."""
        matches = self.find_matching(goal, limit=2)
        if not matches:
            return ""

        parts = ["[EXPERIENCE REPLAY — Similar past tasks]"]
        for m in matches:
            tpl = m["template"]
            steps_preview = " → ".join(
                s.get("tool", s.get("description", "?"))[:15]
                for s in tpl.get("steps", [])[:4]
            )
            rate = m.get("success_rate", "?")
            parts.append(f"- \"{tpl['goal'][:60]}\" (match={m['similarity']}, rate={rate})")
            if steps_preview:
                parts.append(f"  Steps: {steps_preview}")

        result = "\n".join(parts)
        return result[:max_chars] if len(result) > max_chars else result


# ── Singleton ───────────────────────────────────────────────────────────────

_replay = None
_replay_lock = threading.Lock()


def get_experience_replay() -> ExperienceReplay:
    global _replay
    if _replay is None:
        with _replay_lock:
            if _replay is None:
                _replay = ExperienceReplay()
    return _replay
