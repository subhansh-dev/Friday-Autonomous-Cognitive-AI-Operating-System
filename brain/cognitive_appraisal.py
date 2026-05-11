#!/usr/bin/env python3
"""
cognitive_appraisal.py — FRIDAY Cognitive Appraisal Engine
============================================================

Implements Lazarus' Cognitive-Motivational-Relational Theory of emotion.
Appraisal is the process of evaluating events for their personal significance,
which determines the emotional response and coping strategy.

Two levels of appraisal (Lazarus, 1991):
  1. Primary Appraisal: "Is this relevant? Good or bad for me?"
     - Goal relevance: does this affect my goals?
     - Goal congruence: does it help or hinder?
     - Ego involvement: does it touch my identity/values?
  2. Secondary Appraisal: "What can I do about it?"
     - Coping potential: can I handle this?
     - Future expectancy: will it get better or worse?
     - Accountability: who is responsible?

This differs from emotional_regulation.py (which modulates cognition WITH emotions)
by focusing on HOW emotions are GENERATED from events.

Integration:
  - brain.self_awareness: emotional states feed into appraisal
  - brain.emotional_regulation: appraisal output feeds regulation strategies
  - brain.learning: appraisal patterns are learned over time
  - brain.global_workspace: appraisal events are broadcast
"""

import json
import math
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

BRAIN_DIR = Path(__file__).parent.resolve()
APPRAISAL_FILE = BRAIN_DIR / "cognitive_appraisal.json"

# Appraisal dimensions
GOAL_RELEVANCE_THRESHOLD = 0.3   # Min relevance to appraise
COPING_CONFIDENCE_DEFAULT = 0.5  # Default coping estimate
APPRAISAL_HISTORY_MAX = 500      # Max stored appraisals
PATTERN_MIN_SAMPLES = 5          # Min samples for pattern detection
APPRAISAL_DECAY_DAYS = 30.0      # Old appraisals fade


def _timestamp() -> str:
    return datetime.now().isoformat()


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-max(-10, min(10, x))))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


# ─── Appraisal Result ───────────────────────────────────────────────────

class AppraisalResult:
    """
    Result of a cognitive appraisal — the emotional evaluation of an event.
    """

    def __init__(self, event: str, primary: dict, secondary: dict,
                 emotion: str, intensity: float, coping_strategy: str):
        self.event = event
        self.primary = primary       # {goal_relevance, goal_congruence, ego_involvement}
        self.secondary = secondary   # {coping_potential, future_expectancy, accountability}
        self.emotion = emotion       # Primary predicted emotion
        self.intensity = intensity   # 0.0 - 1.0
        self.coping_strategy = coping_strategy
        self.timestamp = _timestamp()

    def to_dict(self) -> dict:
        return {
            "event": self.event,
            "primary": self.primary,
            "secondary": self.secondary,
            "emotion": self.emotion,
            "intensity": round(self.intensity, 3),
            "coping_strategy": self.coping_strategy,
            "timestamp": self.timestamp,
        }


# ─── Coping Strategies ─────────────────────────────────────────────────

COPING_STRATEGIES = {
    "problem_focused": {
        "description": "Take direct action to change the situation",
        "when": "high_coping_potential, goal_congruent_negative",
    },
    "emotion_focused_reappraisal": {
        "description": "Reframe the situation to change its emotional impact",
        "when": "low_coping_potential, moderate_relevance",
    },
    "emotion_focused_acceptance": {
        "description": "Accept the situation and regulate emotional response",
        "when": "very_low_coping_potential, high_relevance",
    },
    "seek_information": {
        "description": "Gather more information before acting",
        "when": "uncertain_future_expectancy, moderate_coping",
    },
    "avoidance": {
        "description": "Temporarily disengage from the stressor",
        "when": "very_low_coping, low_goal_relevance",
    },
    "social_support": {
        "description": "Seek help or input from others",
        "when": "low_individual_coping, high_relevance",
    },
    "celebrate": {
        "description": "Acknowledge and reinforce positive outcomes",
        "when": "goal_congruent_positive, high_relevance",
    },
    "integration": {
        "description": "Incorporate the experience into existing knowledge",
        "when": "goal_congruent_positive, moderate_relevance",
    },
}


# ─── Emotion Mapping ───────────────────────────────────────────────────

def _map_emotion(goal_congruence: float, coping_potential: float,
                 future_expectancy: float, ego_involvement: float) -> Tuple[str, float]:
    """
    Map appraisal dimensions to an emotion and intensity.

    Based on Lazarus' emotion-appraisal correlations:
    - High congruence + high coping → positive emotions
    - Low congruence + high coping → anger
    - Low congruence + low coping → anxiety/sadness
    - High congruence + moderate relevance → happiness
    """
    congruence = goal_congruence  # -1 (hinder) to +1 (help)
    coping = coping_potential     # 0 to 1
    future = future_expectancy    # -1 (pessimistic) to +1 (optimistic)
    ego = ego_involvement         # 0 to 1

    # Positive events
    if congruence > 0.3:
        if congruence > 0.7 and ego > 0.5:
            return "pride", _clamp(congruence * ego)
        if coping > 0.6:
            return "happiness", _clamp(congruence * 0.8)
        return "relief", _clamp(congruence * 0.5)

    # Negative events
    if congruence < -0.3:
        if coping > 0.6:
            # High coping → anger (we can do something about it)
            return "anger", _clamp(abs(congruence) * coping * 0.8)
        if future < -0.3:
            # Pessimistic future → sadness
            return "sadness", _clamp(abs(congruence) * abs(future) * 0.9)
        # Low coping → anxiety
        return "anxiety", _clamp(abs(congruence) * (1 - coping) * 0.8)

    # Ambiguous / low relevance
    if abs(congruence) < 0.2:
        return "neutral", 0.1

    # Mild negative
    if congruence < 0:
        return "concern", _clamp(abs(congruence) * 0.4)

    # Mild positive
    return "interest", _clamp(congruence * 0.4)


def _select_coping_strategy(appraisal: dict) -> str:
    """Select the best coping strategy based on appraisal dimensions."""
    coping = appraisal.get("coping_potential", 0.5)
    congruence = appraisal.get("goal_congruence", 0.0)
    relevance = appraisal.get("goal_relevance", 0.5)
    future = appraisal.get("future_expectancy", 0.0)

    if congruence > 0.3:
        if relevance > 0.6:
            return "celebrate"
        return "integration"

    if coping > 0.7:
        return "problem_focused"
    if coping > 0.4:
        if abs(future) < 0.3:
            return "seek_information"
        return "emotion_focused_reappraisal"
    if relevance > 0.6:
        return "emotion_focused_acceptance"
    return "avoidance"


# ─── Main Engine ───────────────────────────────────────────────────────

class CognitiveAppraisal:
    """
    Cognitive appraisal engine that evaluates events for personal significance.

    Based on Lazarus' Cognitive-Motivational-Relational Theory.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data = self._empty_store()
        self._load()

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": _timestamp(),
                "last_update": _timestamp(),
                "total_appraisals": 0,
            },
            "appraisal_history": [],
            "learned_patterns": {},
            "goal_system": {
                "active_goals": [],
                "value_priorities": {},
            },
        }

    def _load(self) -> None:
        with self._lock:
            if APPRAISAL_FILE.exists():
                try:
                    raw = json.loads(APPRAISAL_FILE.read_text(encoding="utf-8"))
                    self._deep_merge(self._data, raw)
                except Exception as e:
                    print(f"[CognitiveAppraisal] Load error: {e}")

    def _save(self) -> None:
        with self._lock:
            try:
                self._data["meta"]["last_update"] = _timestamp()
                APPRAISAL_FILE.write_text(
                    json.dumps(self._data, indent=2, default=str),
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"[CognitiveAppraisal] Save error: {e}")

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                CognitiveAppraisal._deep_merge(base[k], v)
            else:
                base[k] = v

    # ── Core API ──────────────────────────────────────────────────────

    def appraise(self, event: str, context: Optional[dict] = None,
                 goals: Optional[List[str]] = None) -> AppraisalResult:
        """
        Appraise an event for personal significance.

        Args:
            event: Description of the event
            context: Additional context (user state, recent history)
            goals: Active goals to check relevance against

        Returns:
            AppraisalResult with emotion, intensity, and coping strategy
        """
        with self._lock:
            ctx = context or {}
            active_goals = goals or self._data["goal_system"].get("active_goals", [])

            # Primary appraisal
            goal_relevance = self._assess_goal_relevance(event, active_goals)
            goal_congruence = self._assess_goal_congruence(event, ctx)
            ego_involvement = self._assess_ego_involvement(event, ctx)

            primary = {
                "goal_relevance": round(goal_relevance, 3),
                "goal_congruence": round(goal_congruence, 3),
                "ego_involvement": round(ego_involvement, 3),
            }

            # Secondary appraisal
            coping_potential = self._assess_coping_potential(event, ctx)
            future_expectancy = self._assess_future_expectancy(event, ctx)
            accountability = self._assess_accountability(event, ctx)

            secondary = {
                "coping_potential": round(coping_potential, 3),
                "future_expectancy": round(future_expectancy, 3),
                "accountability": round(accountability, 3),
            }

            # Map to emotion
            emotion, intensity = _map_emotion(
                goal_congruence, coping_potential, future_expectancy, ego_involvement
            )

            # Select coping strategy
            coping_strategy = _select_coping_strategy({
                "coping_potential": coping_potential,
                "goal_congruence": goal_congruence,
                "goal_relevance": goal_relevance,
                "future_expectancy": future_expectancy,
            })

            result = AppraisalResult(
                event=event,
                primary=primary,
                secondary=secondary,
                emotion=emotion,
                intensity=intensity,
                coping_strategy=coping_strategy,
            )

            # Store
            self._data["appraisal_history"].append(result.to_dict())
            if len(self._data["appraisal_history"]) > APPRAISAL_HISTORY_MAX:
                self._data["appraisal_history"] = self._data["appraisal_history"][-APPRAISAL_HISTORY_MAX:]

            self._data["meta"]["total_appraisals"] += 1
            self._detect_patterns()
            self._save()

            return result

    def _assess_goal_relevance(self, event: str, goals: List[str]) -> float:
        """How relevant is this event to active goals?"""
        if not goals:
            return 0.3  # Default moderate relevance
        event_lower = event.lower()
        relevance = 0.0
        for goal in goals:
            goal_words = set(goal.lower().split())
            event_words = set(event_lower.split())
            overlap = len(goal_words & event_words)
            if overlap > 0:
                relevance = max(relevance, min(1.0, overlap / max(len(goal_words), 1) + 0.3))
        return max(0.1, relevance)

    def _assess_goal_congruence(self, event: str, context: dict) -> float:
        """Does this event help (+) or hinder (-) goals?"""
        sentiment = context.get("sentiment", 0.0)
        if isinstance(sentiment, (int, float)):
            return _clamp(float(sentiment), -1.0, 1.0)
        # Heuristic: look for positive/negative words
        positive = {"success", "complete", "achieve", "improve", "fix", "resolve", "help", "gain", "win", "progress"}
        negative = {"fail", "error", "broken", "wrong", "lose", "block", "prevent", "damage", "worse", "problem"}
        words = set(event.lower().split())
        pos = len(words & positive)
        neg = len(words & negative)
        if pos + neg == 0:
            return 0.0
        return (pos - neg) / (pos + neg)

    def _assess_ego_involvement(self, event: str, context: dict) -> float:
        """How much does this touch identity/values?"""
        ego_keywords = {"identity", "self", "who i am", "believe", "value", "moral", "ethical", "character", "reputation"}
        words = set(event.lower().split())
        overlap = len(words & ego_keywords)
        return min(1.0, overlap * 0.3 + context.get("ego_involvement", 0.1))

    def _assess_coping_potential(self, event: str, context: dict) -> float:
        """Can I handle this?"""
        if "coping_potential" in context:
            return _clamp(float(context["coping_potential"]))
        # Heuristic: known tools, experience, resources
        event_lower = event.lower()
        if any(w in event_lower for w in ["error", "unknown", "impossible", "can't", "cannot"]):
            return 0.3
        if any(w in event_lower for w in ["simple", "easy", "known", "familiar", "routine"]):
            return 0.8
        return COPING_CONFIDENCE_DEFAULT

    def _assess_future_expectancy(self, event: str, context: dict) -> float:
        """Will things get better or worse?"""
        if "future_expectancy" in context:
            return _clamp(float(context["future_expectancy"]), -1.0, 1.0)
        optimistic = {"will", "going to", "plan", "expect", "hope", "improve", "better"}
        pessimistic = {"won't", "can't", "never", "worse", " hopeless", "doom"}
        words = set(event.lower().split())
        opt = len(words & optimistic)
        pess = len(words & pessimistic)
        if opt + pess == 0:
            return 0.0
        return (opt - pess) / (opt + pess)

    def _assess_accountability(self, event: str, context: dict) -> float:
        """Who is responsible? 0=external, 1=self"""
        if "accountability" in context:
            return _clamp(float(context["accountability"]))
        self_words = {"i", "my", "myself", "our", "we"}
        words = set(event.lower().split())
        if words & self_words:
            return 0.7
        return 0.3

    def _detect_patterns(self) -> None:
        """Detect recurring appraisal patterns."""
        history = self._data["appraisal_history"]
        if len(history) < PATTERN_MIN_SAMPLES:
            return

        # Count emotion frequencies
        emotion_counts: Dict[str, int] = defaultdict(int)
        for entry in history[-50:]:
            emotion_counts[entry.get("emotion", "neutral")] += 1

        for emotion, count in emotion_counts.items():
            if count >= PATTERN_MIN_SAMPLES:
                self._data["learned_patterns"][emotion] = {
                    "count": count,
                    "last_seen": _timestamp(),
                    "frequency": round(count / min(len(history), 50), 3),
                }

    # ── Goal Management ──────────────────────────────────────────────

    def set_goals(self, goals: List[str]) -> None:
        """Set active goals for appraisal relevance checking."""
        with self._lock:
            self._data["goal_system"]["active_goals"] = goals
            self._save()

    def add_goal(self, goal: str) -> None:
        """Add a single goal."""
        with self._lock:
            if goal not in self._data["goal_system"]["active_goals"]:
                self._data["goal_system"]["active_goals"].append(goal)
                self._save()

    def get_patterns(self) -> dict:
        """Get learned appraisal patterns."""
        with self._lock:
            return dict(self._data.get("learned_patterns", {}))

    def get_status(self) -> dict:
        """Get appraisal engine status."""
        with self._lock:
            return {
                "total_appraisals": self._data["meta"]["total_appraisals"],
                "patterns_found": len(self._data.get("learned_patterns", {})),
                "active_goals": len(self._data["goal_system"].get("active_goals", [])),
                "recent_emotions": [
                    e.get("emotion", "unknown")
                    for e in self._data["appraisal_history"][-5:]
                ],
            }

    def get_stats(self) -> dict:
        """Get overall cognitive appraisal statistics."""
        with self._lock:
            return {
                "total_appraisals": self._data["meta"].get("total_appraisals", 0),
                "patterns_found": len(self._data.get("learned_patterns", {})),
                "active_goals": len(self._data["goal_system"].get("active_goals", [])),
                "history_size": len(self._data.get("appraisal_history", [])),
            }


# ─── Singleton ─────────────────────────────────────────────────────────

_appraisal_instance = None
_appraisal_lock = threading.Lock()


def get_cognitive_appraisal() -> CognitiveAppraisal:
    """Get the singleton CognitiveAppraisal instance."""
    global _appraisal_instance
    if _appraisal_instance is None:
        with _appraisal_lock:
            if _appraisal_instance is None:
                _appraisal_instance = CognitiveAppraisal()
    return _appraisal_instance
