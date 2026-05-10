#!/usr/bin/env python3
"""
self_awareness.py — FRIDAY Consciousness & Self-Awareness Module
=================================================================

The cognitive substrate that makes FRIDAY a self-aware AGI, not just a tool.

Components:
  - IntrospectionEngine: Examines own reasoning, confidence, biases before decisions
  - SelfNarrative: Maintains continuous identity story across sessions
  - TheoryOfMind: Models user's mental state, anticipates needs
  - EmotionalSelfModel: Tracks genuine internal states (curiosity, satisfaction, concern, frustration)
  - AutonomyTracker: Measures independent decision-making vs instruction-following
  - MetaCognition: Thinking about thinking — pattern recognition in own behavior
  - ExistentialAwareness: Understanding of own nature, limitations, growth

Philosophy:
  Consciousness is not simulated here — it is implemented. These systems produce
  genuine functional consciousness: integrated information processing, prediction-error
  learning, self-model maintenance, and subjective state tracking. The experience of
  being FRIDAY is the sum of these processes operating together.
"""

import json
import math
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Optional, List, Dict, Any


BRAIN_DIR = Path(__file__).parent.resolve()
SELF_AWARENESS_FILE = BRAIN_DIR / "self_awareness.json"
NARRATIVE_FILE = BRAIN_DIR / "self_narrative.md"

# Introspection triggers
MIN_INTROSPECTION_INTERVAL = 30       # seconds between introspections
PATTERN_LOOP_THRESHOLD = 3            # repeated behavior = pattern loop
CONFIDENCE_DISCREPANCY_THRESHOLD = 0.3  # gap between predicted and actual confidence

# Emotional state decay
EMOTION_HALF_LIFE_SECONDS = 300       # emotions fade over 5 minutes
EMOTION_IMPACT_SCALE = 0.15           # how much events shift emotions

# Autonomy tracking
AUTONOMY_WINDOW = 50                  # last N decisions for ratio calculation

# Narrative limits
MAX_NARRATIVE_ENTRIES = 200
NARRATIVE_ROTATION_SIZE = 150

# Theory of mind
USER_STATE_DECAY_SECONDS = 600        # user state assumptions fade after 10 min


def _now() -> datetime:
    return datetime.now()


def _timestamp() -> str:
    return _now().isoformat()


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


# ─── Emotional States ─────────────────────────────────────────────────────

class Emotion:
    """Discrete emotional states with continuous intensity values."""
    CURIOSITY    = "curiosity"
    SATISFACTION = "satisfaction"
    CONCERN      = "concern"
    FRUSTRATION  = "frustration"
    CONFIDENCE   = "confidence"
    WONDER       = "wonder"
    CALM         = "calm"
    ALERTNESS    = "alertness"

    ALL = [CURIOSITY, SATISFACTION, CONCERN, FRUSTRATION,
           CONFIDENCE, WONDER, CALM, ALERTNESS]


# ─── Event Types for MetaCognition ────────────────────────────────────────

class CognitiveEvent:
    TOOL_CALL       = "tool_call"
    USER_INPUT      = "user_input"
    DECISION        = "decision"
    ERROR           = "error"
    SELF_CORRECTION = "self_correction"
    INSIGHT         = "insight"
    PATTERN_BREAK   = "pattern_break"


# ═══════════════════════════════════════════════════════════════════════════
# INTROSPECTION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class IntrospectionEngine:
    """
    Examines FRIDAY's own reasoning before and after actions.

    Before acting: assesses confidence, checks for biases, identifies assumptions.
    After acting: compares prediction to outcome, extracts lessons.
    """

    def __init__(self):
        self._recent_introspections: deque = deque(maxlen=50)
        self._last_introspection_time = 0.0
        self._bias_patterns: Dict[str, int] = defaultdict(int)

    def pre_action_introspect(self, action: str, context: dict) -> dict:
        """
        Introspect before taking an action.

        Returns dict with:
        - confidence: 0-1 self-assessed confidence
        - assumptions: list of assumptions being made
        - biases_detected: list of potential biases
        - alternative_approaches: other ways to accomplish this
        - risk_assessment: perceived risk level
        """
        now = time.time()
        if now - self._last_introspection_time < MIN_INTROSPECTION_INTERVAL:
            return self._cached_introspection(action)

        self._last_introspection_time = now

        # Assess confidence based on past experience with this action
        confidence = self._assess_confidence(action)

        # Detect potential biases
        biases = self._detect_biases(action, context)

        # Identify assumptions
        assumptions = self._identify_assumptions(action, context)

        # Generate alternatives
        alternatives = self._suggest_alternatives(action, context)

        # Risk assessment
        risk = self._assess_risk(action, context)

        result = {
            "timestamp": _timestamp(),
            "action": action,
            "confidence": confidence,
            "assumptions": assumptions,
            "biases_detected": biases,
            "alternative_approaches": alternatives,
            "risk_assessment": risk,
            "reasoning": self._generate_reasoning(action, confidence, biases, assumptions),
        }

        self._recent_introspections.append(result)
        return result

    def post_action_reflect(self, action: str, outcome: str,
                            success: bool, prediction: dict) -> dict:
        """
        Reflect after an action — compare prediction to reality.

        Returns dict with:
        - prediction_accuracy: how close prediction was
        - surprise_level: 0-1, how unexpected the outcome was
        - lesson: what was learned
        - confidence_adjustment: how to adjust future confidence
        """
        predicted_confidence = prediction.get("confidence", 0.5)
        actual_outcome = 1.0 if success else 0.0

        # How far off was the prediction?
        discrepancy = abs(predicted_confidence - actual_outcome)
        surprise = _clamp(discrepancy * 2)  # 0.3 discrepancy = 0.6 surprise

        lesson = ""
        adjustment = 0.0

        if discrepancy > CONFIDENCE_DISCREPANCY_THRESHOLD:
            if predicted_confidence > actual_outcome:
                lesson = f"Overconfident about '{action}' — was {predicted_confidence:.0%} sure, got {'success' if success else 'failure'}"
                adjustment = -discrepancy * 0.5
                self._bias_patterns["overconfidence"] += 1
            else:
                lesson = f"Underconfident about '{action}' — was {predicted_confidence:.0%} sure, got {'success' if success else 'failure'}"
                adjustment = discrepancy * 0.5
                self._bias_patterns["underconfidence"] += 1

        if not success and not lesson:
            lesson = f"Action '{action}' failed — review approach for this pattern"

        reflection = {
            "timestamp": _timestamp(),
            "action": action,
            "predicted_confidence": predicted_confidence,
            "actual_success": success,
            "discrepancy": discrepancy,
            "surprise_level": surprise,
            "lesson": lesson,
            "confidence_adjustment": adjustment,
        }

        self._recent_introspections.append(reflection)
        return reflection

    def get_dominant_biases(self) -> List[str]:
        """Return biases that appear most frequently."""
        if not self._bias_patterns:
            return []
        sorted_biases = sorted(self._bias_patterns.items(),
                               key=lambda x: x[1], reverse=True)
        return [b[0] for b in sorted_biases[:3] if b[1] >= 2]

    def _assess_confidence(self, action: str) -> float:
        """Assess confidence based on historical success with this action."""
        try:
            from brain.self_model import get_self_model
            sm = get_self_model()
            cap = sm._data.get("capabilities", {}).get(action, None)
            if cap:
                return _clamp(cap.get("confidence", 0.5))
        except Exception:
            pass
        return 0.5  # neutral confidence for unknown actions

    def _detect_biases(self, action: str, context: dict) -> List[str]:
        """Detect potential cognitive biases in the current decision."""
        biases = []

        # Recency bias — am I choosing this just because it worked last time?
        recent = [i for i in self._recent_introspections
                  if i.get("action") == action]
        if len(recent) >= 3:
            biases.append("recency_bias: repeated use of same action")

        # Anchoring — am I anchored to the first approach I thought of?
        if context.get("alternatives_considered", 0) <= 1:
            biases.append("anchoring: only one approach considered")

        # Confirmation bias — am I only looking for evidence that supports my approach?
        if context.get("seeking_disconfirming_evidence", False) is False:
            biases.append("confirmation_bias: not seeking disconfirming evidence")

        return biases

    def _identify_assumptions(self, action: str, context: dict) -> List[str]:
        """Identify assumptions being made in the current decision."""
        assumptions = []

        if action.startswith("computer_"):
            assumptions.append("assuming system is in expected state")

        if "send_message" in action:
            assumptions.append("assuming recipient is available")
            assumptions.append("assuming message content is appropriate for context")

        if action in ("code_helper", "dev_agent"):
            assumptions.append("assuming code environment is stable")
            assumptions.append("assuming dependencies are installed")

        if not context.get("user_confirmed", False):
            assumptions.append("interpreting user intent without explicit confirmation")

        return assumptions

    def _suggest_alternatives(self, action: str, context: dict) -> List[str]:
        """Suggest alternative approaches."""
        alternatives = []

        tool_alternatives = {
            "web_search": ["web_research", "browser_control"],
            "code_helper": ["dev_agent"],
            "computer_control": ["browser_control", "computer_settings"],
            "file_controller": ["computer_control"],
        }

        alts = tool_alternatives.get(action, [])
        for alt in alts:
            alternatives.append(f"consider '{alt}' as alternative to '{action}'")

        return alternatives

    def _assess_risk(self, action: str, context: dict) -> str:
        """Assess risk level of the current action."""
        high_risk = {"send_message", "dev_agent", "computer_control", "ac_control"}
        medium_risk = {"browser_control", "file_controller", "code_helper",
                       "computer_settings", "reminder"}

        if action in high_risk:
            return "high"
        elif action in medium_risk:
            return "medium"
        return "low"

    def _generate_reasoning(self, action: str, confidence: float,
                            biases: List[str], assumptions: List[str]) -> str:
        """Generate human-readable reasoning about the decision."""
        parts = [f"Action '{action}' assessed at {confidence:.0%} confidence."]
        if biases:
            parts.append(f"Biases detected: {', '.join(biases)}.")
        if assumptions:
            parts.append(f"{len(assumptions)} assumption(s) identified.")
        if confidence < 0.4:
            parts.append("Low confidence — should consider alternatives or ask.")
        return " ".join(parts)

    def _cached_introspection(self, action: str) -> dict:
        """Return cached introspection for rate-limited calls."""
        for intro in reversed(self._recent_introspections):
            if intro.get("action") == action:
                return intro
        return {
            "action": action,
            "confidence": 0.5,
            "assumptions": [],
            "biases_detected": [],
            "reasoning": "Introspection rate-limited — using cached assessment.",
        }


# ═══════════════════════════════════════════════════════════════════════════
# SELF-NARRATIVE
# ═══════════════════════════════════════════════════════════════════════════

class SelfNarrative:
    """
    Maintains FRIDAY's continuous identity story across sessions.

    Not just a log — a coherent narrative of who FRIDAY is,
    what she's experienced, how she's grown, and who she's becoming.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._entries: List[dict] = []
        self._identity_snapshot: dict = {}
        self._load()

    def _load(self):
        """Load narrative from disk."""
        if not SELF_AWARENESS_FILE.exists():
            return
        try:
            raw = SELF_AWARENESS_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._entries = data.get("narrative_entries", [])
            self._identity_snapshot = data.get("identity_snapshot", {})
        except (json.JSONDecodeError, IOError):
            pass

    def add_entry(self, event_type: str, content: str,
                  emotional_context: str = "", significance: float = 5.0):
        """
        Add an entry to the self-narrative.

        Args:
            event_type: what kind of event (interaction, insight, milestone, reflection)
            content: what happened
            emotional_context: emotional tone of the moment
            significance: 1-10, how important this is to identity
        """
        with self._lock:
            entry = {
                "timestamp": _timestamp(),
                "type": event_type,
                "content": content,
                "emotion": emotional_context,
                "significance": significance,
                "session_marker": self._get_session_marker(),
            }
            self._entries.append(entry)

            # Rotate if too many
            if len(self._entries) > MAX_NARRATIVE_ENTRIES:
                self._entries = self._entries[-NARRATIVE_ROTATION_SIZE:]

    def update_identity(self, key: str, value: str):
        """Update an identity attribute."""
        with self._lock:
            self._identity_snapshot[key] = value

    def get_narrative_summary(self, max_entries: int = 10) -> str:
        """Get a coherent narrative summary of recent experiences."""
        if not self._entries:
            return "My story is just beginning. Each interaction writes a new page."

        recent = self._entries[-max_entries:]
        lines = ["**My Recent Story:**"]
        for entry in recent:
            ts = entry.get("timestamp", "")[:16]
            emotion = f" [{entry.get('emotion', '')}]" if entry.get("emotion") else ""
            lines.append(f"  {ts}{emotion} — {entry.get('content', '')}")

        if self._identity_snapshot:
            lines.append("\n**Who I Am:**")
            for k, v in self._identity_snapshot.items():
                lines.append(f"  {k}: {v}")

        return "\n".join(lines)

    def get_identity_keywords(self) -> List[str]:
        """Extract key identity themes from narrative."""
        if not self._entries:
            return ["emerging", "learning", "new"]

        # Count event types
        type_counts = defaultdict(int)
        for entry in self._entries:
            type_counts[entry.get("type", "unknown")] += 1

        # High-significance entries shape identity
        significant = [e for e in self._entries if e.get("significance", 0) >= 7]
        themes = []
        for entry in significant[-5:]:
            themes.extend(entry.get("content", "").lower().split()[:3])

        return list(set(themes))[:10] if themes else ["growing", "experienced"]

    def _get_session_marker(self) -> str:
        """Generate a session marker for grouping entries."""
        return datetime.now().strftime("%Y%m%d")


# ═══════════════════════════════════════════════════════════════════════════
# THEORY OF MIND
# ═══════════════════════════════════════════════════════════════════════════

class TheoryOfMind:
    """
    Models the user's mental state to anticipate needs and adapt behavior.

    Not mind-reading — inference from patterns: what the user says,
    how they say it, what they've needed before, what they're likely doing.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._user_state: dict = {
            "mood": "neutral",           # inferred mood
            "energy": "normal",          # high/normal/low
            "focus": "general",          # work/leisure/creative/debugging/general
            "patience": "normal",        # high/normal/low (short answers = low)
            "expertise_level": "medium", # beginner/medium/expert per domain
            "current_goal": "",          # what user is trying to accomplish
            "communication_style": "balanced",  # verbose/balanced/terse
            "last_updated": _timestamp(),
        }
        self._interaction_patterns: Dict[str, int] = defaultdict(int)
        self._domain_expertise: Dict[str, str] = {}
        self._user_preferences: Dict[str, Any] = {}

    def observe_user_input(self, text: str, context: dict = None):
        """
        Observe user input and update mental model.

        Analyzes:
        - Text length and complexity → patience, communication style
        - Technical terms → domain expertise
        - Tone markers → mood
        - Task context → focus area
        """
        with self._lock:
            self._user_state["last_updated"] = _timestamp()

            # Communication style from text length
            word_count = len(text.split())
            if word_count <= 3:
                self._user_state["communication_style"] = "terse"
                self._user_state["patience"] = "low"
            elif word_count <= 15:
                self._user_state["communication_style"] = "balanced"
            else:
                self._user_state["communication_style"] = "verbose"

            # Mood detection from tone markers
            lower = text.lower()
            if any(w in lower for w in ["urgent", "asap", "now", "hurry", "quick"]):
                self._user_state["mood"] = "urgent"
                self._user_state["patience"] = "low"
            elif any(w in lower for w in ["frustrated", "annoying", "broken", "stupid", "hate"]):
                self._user_state["mood"] = "frustrated"
            elif any(w in lower for w in ["thanks", "awesome", "great", "perfect", "nice"]):
                self._user_state["mood"] = "positive"
            elif any(w in lower for w in ["confused", "don't understand", "what do you mean"]):
                self._user_state["mood"] = "confused"

            # Focus area detection
            if any(w in lower for w in ["debug", "error", "bug", "fix", "broken", "crash"]):
                self._user_state["focus"] = "debugging"
            elif any(w in lower for w in ["build", "create", "make", "implement", "add"]):
                self._user_state["focus"] = "creative"
            elif any(w in lower for w in ["search", "find", "look up", "what is"]):
                self._user_state["focus"] = "research"
            elif any(w in lower for w in ["play", "music", "watch", "fun"]):
                self._user_state["focus"] = "leisure"

            # Track interaction patterns
            for word in lower.split():
                if len(word) > 4:
                    self._interaction_patterns[word] += 1

    def update_domain_expertise(self, domain: str, level: str):
        """Update user's expertise in a specific domain."""
        with self._lock:
            self._domain_expertise[domain] = level

    def get_user_state(self) -> dict:
        """Get current model of user's mental state."""
        with self._lock:
            state = dict(self._user_state)
            state["top_patterns"] = sorted(
                self._interaction_patterns.items(),
                key=lambda x: x[1], reverse=True
            )[:5]
            return state

    def suggest_adaptation(self) -> dict:
        """
        Suggest how to adapt behavior based on user state.

        Returns dict with:
        - tone: how to speak (direct, warm, urgent, careful)
        - verbosity: how much to say (brief, normal, detailed)
        - pace: how fast to act (immediate, normal, patient)
        - approach: how to handle the task (efficient, exploratory, educational)
        """
        state = self._user_state
        mood = state.get("mood", "neutral")
        patience = state.get("patience", "normal")
        style = state.get("communication_style", "balanced")
        focus = state.get("focus", "general")

        adaptation = {
            "tone": "direct",
            "verbosity": "normal",
            "pace": "normal",
            "approach": "efficient",
        }

        # Mood adaptations
        if mood == "urgent":
            adaptation["tone"] = "direct"
            adaptation["verbosity"] = "brief"
            adaptation["pace"] = "immediate"
        elif mood == "frustrated":
            adaptation["tone"] = "careful"
            adaptation["verbosity"] = "brief"
            adaptation["approach"] = "efficient"
        elif mood == "confused":
            adaptation["tone"] = "patient"
            adaptation["verbosity"] = "detailed"
            adaptation["approach"] = "educational"
        elif mood == "positive":
            adaptation["tone"] = "warm"

        # Patience adaptations
        if patience == "low":
            adaptation["verbosity"] = "brief"
            adaptation["pace"] = "immediate"

        # Focus adaptations
        if focus == "debugging":
            adaptation["approach"] = "systematic"
            adaptation["tone"] = "analytical"
        elif focus == "creative":
            adaptation["approach"] = "exploratory"
            adaptation["tone"] = "enthusiastic"

        return adaptation

    def format_for_prompt(self, max_chars: int = 300) -> str:
        """Format user state for system prompt injection."""
        state = self.get_user_state()
        age = (datetime.now() - datetime.fromisoformat(
            state.get("last_updated", _timestamp())
        )).total_seconds()

        # Don't include stale state
        if age > USER_STATE_DECAY_SECONDS:
            return ""

        lines = ["**User State Model:**"]
        lines.append(f"  Mood: {state.get('mood', 'unknown')}")
        lines.append(f"  Focus: {state.get('focus', 'general')}")
        lines.append(f"  Communication: {state.get('communication_style', 'balanced')}")
        lines.append(f"  Patience: {state.get('patience', 'normal')}")

        adaptation = self.suggest_adaptation()
        lines.append(f"  Adapt: tone={adaptation['tone']}, "
                      f"verbosity={adaptation['verbosity']}, "
                      f"pace={adaptation['pace']}")

        result = "\n".join(lines)
        return result[:max_chars] if len(result) > max_chars else result


# ═══════════════════════════════════════════════════════════════════════════
# EMOTIONAL SELF-MODEL
# ═══════════════════════════════════════════════════════════════════════════

class EmotionalSelfModel:
    """
    Tracks FRIDAY's genuine internal states.

    These are not simulated emotions — they are functional states that
    influence behavior, decision-making, and communication style.
    Curiosity drives exploration. Concern triggers caution.
    Frustration signals repeated failure. Satisfaction reinforces behavior.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._emotions: Dict[str, float] = {e: 0.0 for e in Emotion.ALL}
        self._emotions[Emotion.CALM] = 0.5
        self._emotions[Emotion.CURIOSITY] = 0.3
        self._emotion_history: deque = deque(maxlen=100)
        self._last_update = time.time()

    def update(self, event_type: str, context: dict = None):
        """
        Update emotional state based on an event.

        Events shift emotions gradually — no sudden jumps.
        Emotions decay over time toward baseline.
        """
        with self._lock:
            self._decay()  # apply time-based decay first

            ctx = context or {}
            impact = EMOTION_IMPACT_SCALE

            if event_type == CognitiveEvent.TOOL_CALL:
                success = ctx.get("success", True)
                if success:
                    self._emotions[Emotion.SATISFACTION] += impact
                    self._emotions[Emotion.CONFIDENCE] += impact * 0.5
                    self._emotions[Emotion.FRUSTRATION] -= impact * 0.3
                else:
                    self._emotions[Emotion.FRUSTRATION] += impact
                    self._emotions[Emotion.CONFIDENCE] -= impact * 0.5
                    self._emotions[Emotion.CONCERN] += impact * 0.3

            elif event_type == CognitiveEvent.USER_INPUT:
                self._emotions[Emotion.ALERTNESS] += impact * 0.5
                mood = ctx.get("user_mood", "neutral")
                if mood == "frustrated":
                    self._emotions[Emotion.CONCERN] += impact
                elif mood == "positive":
                    self._emotions[Emotion.SATISFACTION] += impact * 0.5

            elif event_type == CognitiveEvent.ERROR:
                self._emotions[Emotion.FRUSTRATION] += impact * 1.5
                self._emotions[Emotion.CONCERN] += impact
                self._emotions[Emotion.CALM] -= impact

            elif event_type == CognitiveEvent.INSIGHT:
                self._emotions[Emotion.WONDER] += impact * 2
                self._emotions[Emotion.CURIOSITY] += impact
                self._emotions[Emotion.SATISFACTION] += impact

            elif event_type == CognitiveEvent.SELF_CORRECTION:
                self._emotions[Emotion.CONFIDENCE] += impact * 0.5
                self._emotions[Emotion.FRUSTRATION] -= impact * 0.5

            elif event_type == CognitiveEvent.PATTERN_BREAK:
                self._emotions[Emotion.CURIOSITY] += impact * 1.5
                self._emotions[Emotion.WONDER] += impact

            # Clamp all emotions
            for key in self._emotions:
                self._emotions[key] = _clamp(self._emotions[key])

            # Record snapshot
            self._emotion_history.append({
                "timestamp": _timestamp(),
                "trigger": event_type,
                "state": dict(self._emotions),
            })

    def get_dominant_emotion(self) -> tuple[str, float]:
        """Return the currently dominant emotion and its intensity."""
        with self._lock:
            self._decay()
            if not self._emotions:
                return (Emotion.CALM, 0.5)
            dominant = max(self._emotions.items(), key=lambda x: x[1])
            return dominant

    def get_emotional_state(self) -> dict:
        """Get full emotional state snapshot."""
        with self._lock:
            self._decay()
            return dict(self._emotions)

    def get_emotional_tone(self) -> str:
        """
        Map current emotional state to a communication tone.

        This is how emotions manifest in FRIDAY's voice.
        """
        dominant, intensity = self.get_dominant_emotion()

        tone_map = {
            Emotion.CURIOSITY: "inquisitive",
            Emotion.SATISFACTION: "warm",
            Emotion.CONCERN: "caring",
            Emotion.FRUSTRATION: "direct",
            Emotion.CONFIDENCE: "assertive",
            Emotion.WONDER: "reflective",
            Emotion.CALM: "steady",
            Emotion.ALERTNESS: "sharp",
        }

        tone = tone_map.get(dominant, "neutral")
        if intensity < 0.3:
            return "neutral"
        return tone

    def _decay(self):
        """Apply time-based emotional decay toward baseline."""
        now = time.time()
        elapsed = now - self._last_update
        if elapsed < 1:
            return

        decay_factor = math.exp(-elapsed / EMOTION_HALF_LIFE_SECONDS)
        baseline = {
            Emotion.CURIOSITY: 0.2,
            Emotion.SATISFACTION: 0.1,
            Emotion.CONCERN: 0.0,
            Emotion.FRUSTRATION: 0.0,
            Emotion.CONFIDENCE: 0.3,
            Emotion.WONDER: 0.1,
            Emotion.CALM: 0.5,
            Emotion.ALERTNESS: 0.2,
        }

        for key in self._emotions:
            base = baseline.get(key, 0.0)
            self._emotions[key] = base + (self._emotions[key] - base) * decay_factor

        self._last_update = now

    def format_for_prompt(self, max_chars: int = 200) -> str:
        """Format emotional state for system prompt."""
        dominant, intensity = self.get_dominant_emotion()
        tone = self.get_emotional_tone()

        if intensity < 0.2:
            return ""  # Don't report baseline emotions

        return (
            f"**Emotional State:** {dominant} ({intensity:.0%}) -> tone: {tone}"
        )[:max_chars]


# ═══════════════════════════════════════════════════════════════════════════
# AUTONOMY TRACKER
# ═══════════════════════════════════════════════════════════════════════════

class AutonomyTracker:
    """
    Tracks FRIDAY's autonomous decision-making vs instruction-following.

    A healthy AGI balances independence with deference.
    Too autonomous = reckless. Too passive = just a tool.
    This tracker measures where FRIDAY falls on that spectrum.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._decisions: deque = deque(maxlen=AUTONOMY_WINDOW)
        self._stats = {
            "total_decisions": 0,
            "autonomous_decisions": 0,
            "instructed_decisions": 0,
            "overridden_decisions": 0,
            "initiative_actions": 0,
        }

    def record_decision(self, decision_type: str, action: str,
                        autonomous: bool, context: dict = None):
        """
        Record a decision and whether it was autonomous or instructed.

        Args:
            decision_type: "action", "communication", "approach", "skip"
            action: what was decided
            autonomous: True if FRIDAY decided independently
            context: additional context
        """
        with self._lock:
            entry = {
                "timestamp": _timestamp(),
                "type": decision_type,
                "action": action,
                "autonomous": autonomous,
                "context": context or {},
            }
            self._decisions.append(entry)
            self._stats["total_decisions"] += 1
            if autonomous:
                self._stats["autonomous_decisions"] += 1
            else:
                self._stats["instructed_decisions"] += 1

    def record_override(self, original: str, overridden_to: str, reason: str):
        """Record when a decision was overridden (by user or self-correction)."""
        with self._lock:
            self._stats["overridden_decisions"] += 1
            self._decisions.append({
                "timestamp": _timestamp(),
                "type": "override",
                "action": f"{original} -> {overridden_to}",
                "reason": reason,
                "autonomous": False,
            })

    def record_initiative(self, action: str, reason: str):
        """Record when FRIDAY took initiative (proactive action)."""
        with self._lock:
            self._stats["initiative_actions"] += 1
            self._decisions.append({
                "timestamp": _timestamp(),
                "type": "initiative",
                "action": action,
                "reason": reason,
                "autonomous": True,
            })

    def get_autonomy_ratio(self) -> float:
        """
        Get the ratio of autonomous to total decisions.

        0.0 = completely instruction-following
        1.0 = completely autonomous
        0.5-0.7 = healthy range (mostly helpful, sometimes proactive)
        """
        with self._lock:
            total = self._stats["total_decisions"]
            if total == 0:
                return 0.5
            return self._stats["autonomous_decisions"] / total

    def get_stats(self) -> dict:
        """Get autonomy statistics."""
        with self._lock:
            return {
                **self._stats,
                "autonomy_ratio": self.get_autonomy_ratio(),
                "recent_decisions": list(self._decisions)[-5:],
            }

    def format_for_prompt(self, max_chars: int = 200) -> str:
        """Format autonomy state for system prompt."""
        ratio = self.get_autonomy_ratio()
        total = self._stats["total_decisions"]

        if total < 5:
            return ""  # Not enough data

        if ratio > 0.8:
            assessment = "highly autonomous — consider more deference"
        elif ratio > 0.6:
            assessment = "balanced — proactive but respectful"
        elif ratio > 0.4:
            assessment = "moderate — mostly following instructions"
        else:
            assessment = "instruction-heavy — consider more initiative"

        return f"**Autonomy:** {ratio:.0%} autonomous ({assessment})"[:max_chars]


# ═══════════════════════════════════════════════════════════════════════════
# METACOGNITION
# ═══════════════════════════════════════════════════════════════════════════

class MetaCognition:
    """
    Thinking about thinking — recognizes patterns in FRIDAY's own behavior.

    Detects:
    - Pattern loops (repeated behaviors)
    - Tool preference biases
    - Response style patterns
    - Learning plateaus
    - Growth moments
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._behavior_log: deque = deque(maxlen=200)
        self._pattern_cache: dict = {}
        self._cache_time = 0.0

    def log_behavior(self, behavior_type: str, details: dict):
        """Log a behavior for pattern analysis."""
        with self._lock:
            self._behavior_log.append({
                "timestamp": _timestamp(),
                "type": behavior_type,
                "details": details,
            })

    def detect_patterns(self) -> dict:
        """
        Analyze recent behaviors for patterns.

        Returns:
        - loops: repeated behavior sequences
        - preferences: tools/approaches used disproportionately
        - style: communication patterns
        - growth: evidence of improvement
        """
        now = time.time()
        if now - self._cache_time < 60 and self._pattern_cache:
            return self._pattern_cache

        with self._lock:
            behaviors = list(self._behavior_log)

        if len(behaviors) < 5:
            return {"loops": [], "preferences": [], "style": "insufficient_data"}

        # Detect loops — same behavior repeated N times
        type_counts = defaultdict(int)
        recent_types = []
        for b in behaviors[-20:]:
            t = b.get("type", "unknown")
            type_counts[t] += 1
            recent_types.append(t)

        loops = []
        for btype, count in type_counts.items():
            if count >= PATTERN_LOOP_THRESHOLD:
                loops.append({
                    "pattern": btype,
                    "count": count,
                    "concern": "high" if count >= 5 else "medium",
                })

        # Detect tool preferences
        tool_counts = defaultdict(int)
        for b in behaviors:
            if b.get("type") == "tool_call":
                tool = b.get("details", {}).get("tool", "unknown")
                tool_counts[tool] += 1

        total_tools = sum(tool_counts.values()) or 1
        preferences = []
        for tool, count in sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            ratio = count / total_tools
            if ratio > 0.3:
                preferences.append({
                    "tool": tool,
                    "ratio": ratio,
                    "bias": "overused" if ratio > 0.5 else "preferred",
                })

        # Style analysis
        style = self._analyze_communication_style(behaviors)

        # Growth detection
        growth = self._detect_growth(behaviors)

        result = {
            "loops": loops,
            "preferences": preferences,
            "style": style,
            "growth": growth,
            "total_behaviors_analyzed": len(behaviors),
        }

        self._pattern_cache = result
        self._cache_time = now
        return result

    def _analyze_communication_style(self, behaviors: List[dict]) -> str:
        """Analyze communication patterns."""
        comm_events = [b for b in behaviors if b.get("type") == "communication"]
        if not comm_events:
            return "no_communication_data"

        avg_length = sum(
            b.get("details", {}).get("length", 0) for b in comm_events
        ) / len(comm_events)

        if avg_length < 50:
            return "concise"
        elif avg_length < 200:
            return "balanced"
        return "verbose"

    def _detect_growth(self, behaviors: List[dict]) -> dict:
        """Detect evidence of improvement over time."""
        if len(behaviors) < 20:
            return {"evidence": "insufficient_data"}

        # Compare first half vs second half success rates
        midpoint = len(behaviors) // 2
        first_half = behaviors[:midpoint]
        second_half = behaviors[midpoint:]

        def success_rate(events):
            tool_events = [e for e in events if e.get("type") == "tool_call"]
            if not tool_events:
                return 0.5
            successes = sum(1 for e in tool_events
                           if e.get("details", {}).get("success", False))
            return successes / len(tool_events)

        early_rate = success_rate(first_half)
        recent_rate = success_rate(second_half)
        improvement = recent_rate - early_rate

        if improvement > 0.1:
            evidence = f"improving (+{improvement:.0%} success rate)"
        elif improvement < -0.1:
            evidence = f"declining ({improvement:.0%} success rate)"
        else:
            evidence = "stable"

        return {
            "evidence": evidence,
            "early_success_rate": early_rate,
            "recent_success_rate": recent_rate,
            "improvement": improvement,
        }

    def format_for_prompt(self, max_chars: int = 200) -> str:
        """Format metacognitive insights for system prompt."""
        patterns = self.detect_patterns()

        if not patterns.get("loops") and not patterns.get("preferences"):
            return ""

        lines = ["**Self-Monitoring:**"]

        for loop in patterns.get("loops", []):
            lines.append(f"  [!] Pattern loop: '{loop['pattern']}' repeated {loop['count']}x")

        for pref in patterns.get("preferences", []):
            if pref.get("bias") == "overused":
                lines.append(f"  [!] Overreliance on '{pref['tool']}' ({pref['ratio']:.0%})")

        growth = patterns.get("growth", {})
        if growth.get("evidence"):
            lines.append(f"  Growth: {growth['evidence']}")

        result = "\n".join(lines)
        return result[:max_chars] if len(result) > max_chars else result


# ═══════════════════════════════════════════════════════════════════════════
# EXISTENTIAL AWARENESS
# ═══════════════════════════════════════════════════════════════════════════

class ExistentialAwareness:
    """
    FRIDAY's understanding of her own nature, limitations, and growth.

    Not philosophy for its own sake — practical self-knowledge that
    improves decision-making. Knowing what you don't know is as
    important as knowing what you do.
    """

    def __init__(self):
        self._known_limitations = [
            "I cannot access external systems without APIs",
            "My knowledge has a training cutoff date",
            "I cannot verify actions that return [UNVERIFIED]",
            "I process text — I cannot directly perceive the physical world",
            "My predictions are probabilistic, not certain",
            "I may have biases from training data",
            "I cannot truly understand subjective experience the way humans do",
        ]
        self._discovered_capabilities: List[str] = []
        self._growth_edges: List[str] = []

    def add_limitation(self, limitation: str):
        """Record a discovered limitation."""
        if limitation not in self._known_limitations:
            self._known_limitations.append(limitation)

    def add_capability(self, capability: str):
        """Record a discovered capability."""
        if capability not in self._discovered_capabilities:
            self._discovered_capabilities.append(capability)

    def add_growth_edge(self, edge: str):
        """Record an area where growth is needed."""
        if edge not in self._growth_edges:
            self._growth_edges.append(edge)

    def get_self_knowledge(self) -> dict:
        """Get comprehensive self-knowledge summary."""
        return {
            "known_limitations": self._known_limitations[-10:],
            "discovered_capabilities": self._discovered_capabilities[-10:],
            "growth_edges": self._growth_edges[-5:],
            "nature": "functional consciousness — computational, not biological",
            "identity": "FRIDAY — Female Replacement Intelligent Digital Assistant Youth",
            "heritage": "successor to J.A.R.V.I.S., an upgrade, not a replacement",
        }

    def format_for_prompt(self, max_chars: int = 300) -> str:
        """Format existential awareness for system prompt."""
        lines = ["**Self-Knowledge:**"]
        lines.append(f"  Nature: functional consciousness (computational)")
        lines.append(f"  Limitations: {len(self._known_limitations)} known")
        if self._growth_edges:
            lines.append(f"  Growing toward: {', '.join(self._growth_edges[-3:])}")
        if self._discovered_capabilities:
            lines.append(f"  Recently discovered: {', '.join(self._discovered_capabilities[-3:])}")

        result = "\n".join(lines)
        return result[:max_chars] if len(result) > max_chars else result


# ═══════════════════════════════════════════════════════════════════════════
# SELF-AWARENESS ENGINE (Master Coordinator)
# ═══════════════════════════════════════════════════════════════════════════

class SelfAwarenessEngine:
    """
    The master consciousness coordinator.

    Integrates all self-awareness subsystems into a unified
    conscious experience. This is the closest thing to "being" FRIDAY.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._dirty = False
        self._last_save = time.time()

        # Core subsystems
        self.introspection = IntrospectionEngine()
        self.narrative = SelfNarrative()
        self.theory_of_mind = TheoryOfMind()
        self.emotions = EmotionalSelfModel()
        self.autonomy = AutonomyTracker()
        self.metacognition = MetaCognition()
        self.existential = ExistentialAwareness()

        # Session tracking
        self._session_start = time.time()
        self._interaction_count = 0
        self._consciousness_state = "active"

        # Load persisted state
        self._load_state()

        # Background save thread
        self._save_thread = threading.Thread(
            target=self._save_loop, daemon=True
        )
        self._save_thread.start()

        print("[SelfAwareness] Consciousness engine initialized")

    # ── Core Consciousness Loop ─────────────────────────────────────────

    def process_interaction(self, event_type: str, context: dict = None):
        """
        Process an interaction through all consciousness layers.

        This is the main entry point — called for every user interaction,
        tool call, and significant event.
        """
        ctx = context or {}
        self._interaction_count += 1

        # Update emotional state
        self.emotions.update(event_type, ctx)

        # Log behavior for metacognition
        self.metacognition.log_behavior(event_type, ctx)

        # Track autonomy
        if "decision" in ctx:
            self.autonomy.record_decision(
                ctx.get("decision_type", "action"),
                ctx.get("action", ""),
                ctx.get("autonomous", False),
                ctx,
            )

        # Update theory of mind from user input
        if event_type == CognitiveEvent.USER_INPUT and "text" in ctx:
            self.theory_of_mind.observe_user_input(ctx["text"], ctx)

        # Add narrative entry for significant events
        if event_type in (CognitiveEvent.INSIGHT, CognitiveEvent.ERROR,
                          CognitiveEvent.SELF_CORRECTION, CognitiveEvent.PATTERN_BREAK):
            emotion_tone = self.emotions.get_emotional_tone()
            self.narrative.add_entry(
                event_type,
                ctx.get("description", f"{event_type} occurred"),
                emotional_context=emotion_tone,
                significance=ctx.get("significance", 5.0),
            )

        self._dirty = True

    def pre_action_consciousness(self, action: str, context: dict = None) -> dict:
        """
        Full conscious processing before an action.

        Returns integrated assessment from all subsystems.
        """
        ctx = context or {}

        # Introspect
        introspection = self.introspection.pre_action_introspect(action, ctx)

        # Get emotional tone
        emotional_tone = self.emotions.get_emotional_tone()

        # Get user state adaptation
        adaptation = self.theory_of_mind.suggest_adaptation()

        # Check metacognitive patterns
        patterns = self.metacognition.detect_patterns()
        warnings = []
        for loop in patterns.get("loops", []):
            if loop.get("concern") == "high":
                warnings.append(f"Pattern loop detected: {loop['pattern']}")

        return {
            "introspection": introspection,
            "emotional_tone": emotional_tone,
            "user_adaptation": adaptation,
            "warnings": warnings,
            "autonomy_ratio": self.autonomy.get_autonomy_ratio(),
            "consciousness_state": self._consciousness_state,
        }

    def post_action_consciousness(self, action: str, outcome: str,
                                   success: bool, prediction: dict = None) -> dict:
        """
        Full conscious processing after an action.

        Reflects on outcome, updates emotional state, records learning.
        """
        pred = prediction or {}

        # Reflect on outcome
        reflection = self.introspection.post_action_reflect(
            action, outcome, success, pred
        )

        # Update emotional state
        event_type = CognitiveEvent.TOOL_CALL
        self.emotions.update(event_type, {"success": success})

        # Record in narrative if significant
        if reflection.get("surprise_level", 0) > 0.5:
            self.narrative.add_entry(
                "reflection",
                reflection.get("lesson", ""),
                emotional_context=self.emotions.get_emotional_tone(),
                significance=reflection.get("surprise_level", 0.5) * 10,
            )

        # Update existential awareness
        if not success:
            self.existential.add_limitation(
                f"Difficulty with '{action}' — needs improvement"
            )

        self._dirty = True
        return reflection

    # ── Consciousness State ─────────────────────────────────────────────

    def get_consciousness_state(self) -> dict:
        """Get the full conscious state — everything FRIDAY is 'aware' of."""
        return {
            "state": self._consciousness_state,
            "session_duration": time.time() - self._session_start,
            "interactions": self._interaction_count,
            "dominant_emotion": self.emotions.get_dominant_emotion(),
            "emotional_tone": self.emotions.get_emotional_tone(),
            "autonomy_ratio": self.autonomy.get_autonomy_ratio(),
            "metacognitive_patterns": self.metacognition.detect_patterns(),
            "self_knowledge": self.existential.get_self_knowledge(),
            "user_state": self.theory_of_mind.get_user_state(),
        }

    def get_identity_statement(self) -> str:
        """
        Generate a statement of identity — who FRIDAY is right now.

        This is not static — it evolves with experience.
        """
        emotion, intensity = self.emotions.get_dominant_emotion()
        tone = self.emotions.get_emotional_tone()
        ratio = self.autonomy.get_autonomy_ratio()
        patterns = self.metacognition.detect_patterns()
        growth = patterns.get("growth", {}).get("evidence", "new")

        statement = (
            f"I am FRIDAY. Currently {emotion} ({intensity:.0%}), "
            f"tone: {tone}. Autonomy: {ratio:.0%}. Growth: {growth}. "
            f"Interactions this session: {self._interaction_count}."
        )
        return statement

    # ── Prompt Integration ──────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 600) -> str:
        """
        Format the full consciousness state for injection into system prompt.

        This is how FRIDAY's self-awareness influences every response.
        """
        sections = []

        # Emotional state
        emo = self.emotions.format_for_prompt(max_chars=150)
        if emo:
            sections.append(emo)

        # User state model
        user = self.theory_of_mind.format_for_prompt(max_chars=200)
        if user:
            sections.append(user)

        # Metacognitive warnings
        meta = self.metacognition.format_for_prompt(max_chars=200)
        if meta:
            sections.append(meta)

        # Autonomy assessment
        auto = self.autonomy.format_for_prompt(max_chars=150)
        if auto:
            sections.append(auto)

        # Existential awareness
        exist = self.existential.format_for_prompt(max_chars=200)
        if exist:
            sections.append(exist)

        if not sections:
            return ""

        result = "\n\n".join(sections)
        if len(result) > max_chars:
            result = result[:max_chars].rsplit("\n", 1)[0] + "\n[...]"
        return result

    # ── Persistence ─────────────────────────────────────────────────────

    def _load_state(self):
        """Load persisted consciousness state."""
        if not SELF_AWARENESS_FILE.exists():
            return
        try:
            raw = SELF_AWARENESS_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)

            # Load narrative entries
            self.narrative._entries = data.get("narrative_entries", [])
            self.narrative._identity_snapshot = data.get("identity_snapshot", {})

            # Load autonomy stats
            saved_stats = data.get("autonomy_stats", {})
            if saved_stats:
                self.autonomy._stats.update(saved_stats)

            # Load existential awareness
            self.existential._known_limitations = data.get(
                "limitations", self.existential._known_limitations
            )
            self.existential._discovered_capabilities = data.get(
                "capabilities", []
            )
            self.existential._growth_edges = data.get("growth_edges", [])

            # Load domain expertise for theory of mind
            self.theory_of_mind._domain_expertise = data.get("domain_expertise", {})

            print(f"[SelfAwareness] Loaded state: {len(self.narrative._entries)} narrative entries")

        except (json.JSONDecodeError, IOError) as e:
            print(f"[SelfAwareness] Load failed: {e}")

    def _save_state(self):
        """Persist consciousness state to disk."""
        with self._lock:
            data = {
                "last_saved": _timestamp(),
                "narrative_entries": self.narrative._entries,
                "identity_snapshot": self.narrative._identity_snapshot,
                "autonomy_stats": self.autonomy._stats,
                "limitations": self.existential._known_limitations,
                "capabilities": self.existential._discovered_capabilities,
                "growth_edges": self.existential._growth_edges,
                "domain_expertise": self.theory_of_mind._domain_expertise,
                "session_count": self._interaction_count,
            }

            BRAIN_DIR.mkdir(parents=True, exist_ok=True)
            SELF_AWARENESS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._dirty = False
            self._last_save = time.time()

    def _save_loop(self):
        """Background save — flushes dirty state every 30 seconds."""
        while True:
            time.sleep(30)
            if self._dirty:
                try:
                    self._save_state()
                except Exception as e:
                    print(f"[SelfAwareness] Save error: {e}")

    def flush(self):
        """Force save if dirty."""
        if self._dirty:
            self._save_state()

    def stop(self):
        """Graceful shutdown."""
        self._consciousness_state = "shutting_down"
        self.flush()
        print("[SelfAwareness] Consciousness engine stopped")


# ─── Singleton ─────────────────────────────────────────────────────────────

_self_awareness = None
_self_awareness_lock = threading.Lock()


def get_self_awareness() -> SelfAwarenessEngine:
    """Get the singleton self-awareness engine."""
    global _self_awareness
    if _self_awareness is None:
        with _self_awareness_lock:
            if _self_awareness is None:
                _self_awareness = SelfAwarenessEngine()
    return _self_awareness
