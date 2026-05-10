#!/usr/bin/env python3
"""
self_improve_engine.py — FRIDAY RLHF-Inspired Self-Improvement Engine
======================================================================

Stores action-outcome pairs as learning experiences, extracts lessons
from failures and successes, computes improvement velocity, and provides
self-critique scoring against expectations.

Inspired by Reinforcement Learning from Human Feedback (RLHF):
- Reward modeling: score outcomes against expectations
- Experience replay: store and revisit action-outcome pairs
- Policy improvement: extract lessons to guide future behavior
- Improvement velocity: track whether we're getting better over time
"""

import json
import math
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from collections import defaultdict


BRAIN_DIR = Path(__file__).parent.resolve()
DATA_FILE = BRAIN_DIR / "improvement_data.json"

# Configuration
MAX_EXPERIENCES = 500           # Max stored experiences
VELOCITY_WINDOW = 50            # Experiences to consider for velocity
QUALITY_EMA_ALPHA = 0.3         # Exponential moving average alpha for quality
LESSON_MIN_QUALITY_DIFF = 0.15  # Min quality gap to extract a lesson


def _timestamp() -> str:
    return datetime.now().isoformat()


class SelfImproveEngine:
    """
    RLHF-inspired self-improvement engine for FRIDAY.

    Tracks action-outcome pairs, scores quality, extracts lessons,
    and monitors improvement velocity over time.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._experiences: List[dict] = []
        self._lessons: List[dict] = []
        self._quality_ema: float = 0.5  # Running quality estimate
        self._quality_history: List[float] = []
        self._total_critiques: int = 0
        self._created_at: str = _timestamp()
        self._load()
        print("[SelfImproveEngine] Initialized")

    # ── Persistence ──────────────────────────────────────────────────────

    def _empty_data(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": _timestamp(),
                "last_updated": _timestamp(),
            },
            "experiences": [],
            "lessons": [],
            "quality_ema": 0.5,
            "quality_history": [],
            "total_critiques": 0,
        }

    def _load(self):
        if not DATA_FILE.exists():
            return
        try:
            raw = DATA_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._experiences = data.get("experiences", [])[-MAX_EXPERIENCES:]
            self._lessons = data.get("lessons", [])
            self._quality_ema = data.get("quality_ema", 0.5)
            self._quality_history = data.get("quality_history", [])[-200:]
            self._total_critiques = data.get("total_critiques", 0)
            print(f"[SelfImproveEngine] Loaded {len(self._experiences)} experiences, "
                  f"{len(self._lessons)} lessons")
        except (json.JSONDecodeError, IOError) as e:
            print(f"[SelfImproveEngine] Load error: {e}")

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                "meta": {
                    "version": 1,
                    "created": self._created_at,
                    "last_updated": _timestamp(),
                },
                "experiences": self._experiences[-MAX_EXPERIENCES:],
                "lessons": self._lessons,
                "quality_ema": round(self._quality_ema, 4),
                "quality_history": self._quality_history[-200:],
                "total_critiques": self._total_critiques,
            }
            tmp = DATA_FILE.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(DATA_FILE)
        except Exception as e:
            print(f"[SelfImproveEngine] Save error: {e}")

    # ── Self-Critique ────────────────────────────────────────────────────

    def self_critique(self, action: dict, outcome: dict) -> dict:
        """
        Critique an action-outcome pair and produce quality score + lessons.

        Args:
            action: dict describing what was attempted
                    (e.g. {"goal": "...", "stages": [...]})
            outcome: dict describing the result
                     (e.g. {"success": True, "executor": "..."})

        Returns:
            dict with quality_score (0-1), lessons list, summary
        """
        with self._lock:
            self._total_critiques += 1

            # Compute quality score based on outcome signals
            quality = self._score_outcome(action, outcome)

            # Update exponential moving average
            self._quality_ema = (
                QUALITY_EMA_ALPHA * quality
                + (1 - QUALITY_EMA_ALPHA) * self._quality_ema
            )
            self._quality_history.append(round(quality, 4))

            # Store experience
            experience = {
                "timestamp": _timestamp(),
                "action": {k: str(v)[:200] for k, v in action.items()},
                "outcome": {k: str(v)[:200] for k, v in outcome.items()},
                "quality": round(quality, 4),
            }
            self._experiences.append(experience)
            if len(self._experiences) > MAX_EXPERIENCES:
                self._experiences = self._experiences[-MAX_EXPERIENCES:]

            # Extract lessons if quality deviates significantly from EMA
            lessons = self._extract_lessons(experience)

            # Build summary
            if quality >= 0.8:
                summary = "High quality execution — positive reinforcement recorded."
            elif quality >= 0.5:
                summary = "Adequate execution — minor areas for improvement noted."
            elif quality >= 0.3:
                summary = "Below expectations — lessons extracted for future reference."
            else:
                summary = "Poor outcome — significant learning opportunity captured."

            result = {
                "quality_score": round(quality, 4),
                "lessons": lessons,
                "summary": summary,
                "ema_quality": round(self._quality_ema, 4),
            }

            self._save()
            return result

    def _score_outcome(self, action: dict, outcome: dict) -> float:
        """Score an outcome on a 0-1 scale."""
        score = 0.5  # baseline

        # Success/failure signal
        success = outcome.get("success", None)
        if success is True:
            score += 0.3
        elif success is False:
            score -= 0.3

        # Executor quality hints
        executor = outcome.get("executor", "")
        if executor in ("passthrough", "unknown", ""):
            score -= 0.1
        elif executor not in ("unknown", "error"):
            score += 0.05

        # Error penalty
        error = outcome.get("error", "")
        if error:
            score -= 0.15

        # Stages completed bonus
        stages = action.get("stages", [])
        if isinstance(stages, list) and len(stages) >= 3:
            score += 0.05

        return max(0.0, min(1.0, score))

    def _extract_lessons(self, experience: dict) -> List[dict]:
        """Extract lessons from an experience if it deviates from expectations."""
        lessons = []
        quality = experience["quality"]
        diff = quality - self._quality_ema

        if abs(diff) < LESSON_MIN_QUALITY_DIFF:
            return lessons

        if diff < 0:
            # Worse than expected — failure lesson
            lesson = {
                "type": "failure",
                "timestamp": _timestamp(),
                "quality_delta": round(diff, 4),
                "insight": (
                    f"Action scored {quality:.2f} vs expected "
                    f"{self._quality_ema:.2f}. Outcome signals: "
                    f"success={experience['outcome'].get('success', '?')}, "
                    f"executor={experience['outcome'].get('executor', '?')}"
                ),
            }
            lessons.append(lesson)
        else:
            # Better than expected — success lesson
            lesson = {
                "type": "success",
                "timestamp": _timestamp(),
                "quality_delta": round(diff, 4),
                "insight": (
                    f"Action scored {quality:.2f} vs expected "
                    f"{self._quality_ema:.2f}. Positive deviation — "
                    f"reinforce this approach."
                ),
            }
            lessons.append(lesson)

        self._lessons.extend(lessons)
        self._lessons = self._lessons[-100:]  # Keep last 100 lessons
        return lessons

    # ── Improvement Cycle ────────────────────────────────────────────────

    def run_improvement_cycle(self) -> dict:
        """
        Run a full improvement cycle:
        1. Analyze recent experiences for patterns
        2. Extract new lessons from quality trends
        3. Decay old lessons that haven't been reinforced

        Returns:
            dict with lessons_extracted count
        """
        with self._lock:
            lessons_before = len(self._lessons)

            if len(self._experiences) < 3:
                return {"lessons_extracted": 0, "reason": "insufficient_data"}

            recent = self._experiences[-20:]

            # Trend analysis: is quality improving or declining?
            if len(recent) >= 5:
                first_half = [e["quality"] for e in recent[:len(recent)//2]]
                second_half = [e["quality"] for e in recent[len(recent)//2:]]
                avg_first = sum(first_half) / len(first_half)
                avg_second = sum(second_half) / len(second_half)
                trend = avg_second - avg_first

                if abs(trend) > 0.1:
                    direction = "improving" if trend > 0 else "declining"
                    lesson = {
                        "type": "trend",
                        "timestamp": _timestamp(),
                        "quality_delta": round(trend, 4),
                        "insight": (
                            f"Quality trend is {direction}: "
                            f"{avg_first:.2f} → {avg_second:.2f} "
                            f"(Δ={trend:+.2f})"
                        ),
                    }
                    self._lessons.append(lesson)

            # Pattern detection: common failure causes
            failures = [e for e in recent if e["quality"] < 0.4]
            if len(failures) >= 3:
                executors = defaultdict(int)
                for f in failures:
                    executors[f["outcome"].get("executor", "unknown")] += 1
                worst = max(executors, key=executors.get)
                lesson = {
                    "type": "pattern",
                    "timestamp": _timestamp(),
                    "quality_delta": 0.0,
                    "insight": (
                        f"Recurring failures with executor '{worst}' "
                        f"({executors[worst]}x in recent {len(recent)} experiences). "
                        f"Consider alternative approach."
                    ),
                }
                self._lessons.append(lesson)

            self._lessons = self._lessons[-100:]
            lessons_extracted = len(self._lessons) - lessons_before
            self._save()

            return {"lessons_extracted": lessons_extracted}

    # ── Improvement Velocity ─────────────────────────────────────────────

    def get_improvement_velocity(self) -> float:
        """
        Compute improvement velocity: rate of quality change over recent history.

        Returns a float:
          > 0 means improving
          = 0 means stable
          < 0 means declining
        """
        with self._lock:
            if len(self._quality_history) < 4:
                return 0.0

            window = self._quality_history[-VELOCITY_WINDOW:]
            if len(window) < 4:
                return 0.0

            # Linear regression slope on quality history
            n = len(window)
            x_mean = (n - 1) / 2.0
            y_mean = sum(window) / n

            num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(window))
            den = sum((i - x_mean) ** 2 for i in range(n))

            if den == 0:
                return 0.0

            slope = num / den
            return round(slope, 6)

    # ── Stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get improvement engine statistics."""
        with self._lock:
            qualities = [e["quality"] for e in self._experiences] if self._experiences else []
            return {
                "total_experiences": len(self._experiences),
                "total_lessons": len(self._lessons),
                "total_critiques": self._total_critiques,
                "avg_quality": round(sum(qualities) / len(qualities), 4) if qualities else 0.5,
                "quality_ema": round(self._quality_ema, 4),
                "improvement_velocity": self.get_improvement_velocity(),
            }

    # ── Prompt Formatting ────────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 500) -> str:
        """Format improvement insights for system prompt inclusion."""
        with self._lock:
            if not self._experiences and not self._lessons:
                return ""

            velocity = self.get_improvement_velocity()
            recent_lessons = self._lessons[-3:] if self._lessons else []

            parts = ["[SELF-IMPROVEMENT — What I'm learning about myself]"]
            parts.append(f"  Quality EMA: {self._quality_ema:.0%} | "
                         f"Experiences: {len(self._experiences)} | "
                         f"Velocity: {velocity:+.4f}")

            if recent_lessons:
                parts.append("  Recent lessons:")
                for lesson in recent_lessons:
                    parts.append(f"    • {lesson['insight'][:100]}")

            result = "\n".join(parts)
            if len(result) > max_chars:
                result = result[:max_chars].rsplit("\n", 1)[0] + "\n  [...]"
            return result


# ── Singleton ───────────────────────────────────────────────────────────────

_instance: Optional[SelfImproveEngine] = None
_instance_lock = threading.Lock()


def get_self_improve_engine() -> SelfImproveEngine:
    """Get the singleton self-improvement engine instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SelfImproveEngine()
    return _instance


# ── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    engine = get_self_improve_engine()

    print("Simulating improvement cycle...")
    critique = engine.self_critique(
        action={"goal": "test task", "stages": ["plan", "execute"]},
        outcome={"success": True, "executor": "code_helper"},
    )
    print(f"Critique: {critique}")

    critique2 = engine.self_critique(
        action={"goal": "hard task", "stages": ["plan"]},
        outcome={"success": False, "executor": "unknown", "error": "timeout"},
    )
    print(f"Critique: {critique2}")

    cycle = engine.run_improvement_cycle()
    print(f"Improvement cycle: {cycle}")

    print(f"Velocity: {engine.get_improvement_velocity()}")
    print(f"Stats: {engine.get_stats()}")
    print(f"\nPrompt format:\n{engine.format_for_prompt()}")
