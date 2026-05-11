#!/usr/bin/env python3
"""
emotional_regulation.py — FRIDAY Emotional Regulation Engine
==============================================================

Uses emotions to MODULATE cognition — not just track them (self_awareness
does that), but actively leverage emotional signals to improve decision-making,
memory retrieval, and cognitive strategy selection.

Research foundations:

  [ER-1] Damasio's Somatic Marker Hypothesis (1994, Descartes' Error)
         — Emotions are not noise in decision-making; they are essential
           signals. Somatic markers (bodily emotional states) bias
           decisions toward previously rewarding options and away from
           punishing ones. Patients with ventromedial PFC damage, who
           lose somatic markers, make catastrophically bad decisions
           despite intact logic.

  [ER-2] Bower's Network Theory of Mood-Congruent Memory (1981, 1987)
         — Emotions serve as retrieval cues. When sad, sad memories are
           more accessible; when happy, happy memories surface. This
           mood-congruent processing affects reasoning, judgment, and
           creativity.

  [ER-3] Affect Heuristic (Slovic et al., 2002)
         — People make fast judgments based on affective reactions
           ("How do I feel about this?") rather than deliberative
           analysis. The affect heuristic is a powerful and often
           accurate shortcut for evaluation.

  [ER-4] Gross's Process Model of Emotion Regulation (1998, 2015)
         — Five families of regulation strategies:
           1. Situation selection (choose what to engage with)
           2. Situation modification (change the current context)
           3. Attentional deployment (shift focus)
           4. Cognitive change (reappraisal — reframe the meaning)
           5. Response modulation (suppress or amplify expression)

  [ER-5] Reappraisal as Adaptive Strategy (Ochsner & Gross, 2005)
         — Cognitive reappraisal (reframing meaning) is more effective
           than suppression for regulating negative emotions and
           maintaining cognitive performance.

Key behaviors:
  - Somatic markers: tag options with emotional valence from past outcomes
  - Mood-congruent recall: filter memories by emotional compatibility
  - Reappraisal: generate alternative interpretations of events
  - Affect heuristic: fast emotional evaluation of actions
  - Cognitive state regulation: choose emotion regulation strategies
  - Integration with self_awareness emotional states
"""

import json
import math
import random
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


BRAIN_DIR = Path(__file__).parent.resolve()
EMOTIONAL_FILE = BRAIN_DIR / "emotional_regulation.json"

# ── Configuration ───────────────────────────────────────────────────────────

# Emotion model dimensions (Russell's Circumplex Model, 1980)
# Valence: -1 (negative) to +1 (positive)
# Arousal: 0 (calm) to 1 (excited)
EMOTION_TYPES = {
    "joy":       {"valence":  0.9, "arousal": 0.7},
    "satisfaction": {"valence":  0.7, "arousal": 0.3},
    "curiosity": {"valence":  0.6, "arousal": 0.8},
    "interest":  {"valence":  0.5, "arousal": 0.5},
    "surprise":  {"valence":  0.1, "arousal": 0.9},
    "neutral":   {"valence":  0.0, "arousal": 0.2},
    "confusion": {"valence": -0.2, "arousal": 0.5},
    "concern":   {"valence": -0.3, "arousal": 0.4},
    "frustration": {"valence": -0.6, "arousal": 0.7},
    "anxiety":   {"valence": -0.7, "arousal": 0.9},
    "disappointment": {"valence": -0.5, "arousal": 0.3},
    "boredom":   {"valence": -0.3, "arousal": 0.1},
}

# Somatic markers
MAX_SOMATIC_MARKERS = 500
MARKER_STRENGTH_INITIAL = 0.5
MARKER_STRENGTH_DECAY = 0.995  # per day
MARKER_REINFORCE = 0.1
MARKER_WEAKEN = -0.15

# Reappraisal
REAPPRAISAL_TEMPLATES = {
    "threat_to_challenge": "This is a challenge to grow from, not a threat to fear.",
    "failure_to_learning": "This failure provides valuable information for improvement.",
    "overwhelming_to_stepwise": "Breaking this into smaller steps makes it manageable.",
    "personal_to_situational": "This is a situational factor, not a personal failing.",
    "permanent_to_temporary": "This is a temporary state, not a permanent condition.",
    "global_to_specific": "This is a specific issue, not a reflection of everything.",
    "catastrophic_to_realistic": "The most likely outcome is much less extreme than worst-case.",
    "ambiguous_to_curious": "Ambiguity is an opportunity to explore and learn.",
}

# Mood-congruent recall
MOOD_SIMILARITY_THRESHOLD = 0.3  # minimum mood match to include memory
RECALL_WINDOW = 100               # recent memories to search

# Affect heuristic
AFFECT_DECAY_DAYS = 30.0          # emotional associations fade over time

# Regulation strategy effectiveness tracking
MAX_STRATEGY_RECORDS = 100

# Persistence
MAX_EVENT_LOG = 300
MAX_MARKER_HISTORY = 500


def _now() -> str:
    return datetime.now().isoformat()


def _timestamp() -> float:
    return time.time()


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _euclidean_distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


# ── Data Structures ─────────────────────────────────────────────────────────

class EmotionalState:
    """Current emotional state as valence + arousal (Russell Circumplex)."""

    __slots__ = ["valence", "arousal", "label", "timestamp"]

    def __init__(self, valence: float = 0.0, arousal: float = 0.2,
                 label: str = "neutral"):
        self.valence = _clamp(valence)
        self.arousal = _clamp(arousal, 0.0, 1.0)
        self.label = label
        self.timestamp = _now()

    def to_dict(self) -> dict:
        return {
            "valence": round(self.valence, 3),
            "arousal": round(self.arousal, 3),
            "label": self.label,
            "timestamp": self.timestamp,
        }

    def distance_to(self, other: "EmotionalState") -> float:
        """Euclidean distance in valence-arousal space (0-2 scale)."""
        return _euclidean_distance(
            (self.valence, self.arousal),
            (other.valence, other.arousal)
        )

    def similarity_to(self, other: "EmotionalState") -> float:
        """Similarity score (0=different, 1=identical)."""
        dist = self.distance_to(other)
        return max(0.0, 1.0 - dist / 2.0)

    @classmethod
    def from_emotion_label(cls, label: str) -> "EmotionalState":
        """Create state from a named emotion."""
        dims = EMOTION_TYPES.get(label.lower(), EMOTION_TYPES["neutral"])
        return cls(valence=dims["valence"], arousal=dims["arousal"], label=label.lower())


class SomaticMarker:
    """
    An emotional tag associated with a situation/action combination.

    Based on Damasio's Somatic Marker Hypothesis: past emotional outcomes
    create markers that bias future decisions.
    """

    __slots__ = [
        "marker_id", "situation_hash", "action", "valence", "arousal",
        "strength", "outcome_description", "created_at", "last_activated",
        "activation_count",
    ]

    def __init__(self, situation_hash: str, action: str,
                 valence: float, arousal: float,
                 outcome_description: str = ""):
        self.marker_id = f"{situation_hash}:{action}"[:60]
        self.situation_hash = situation_hash
        self.action = action
        self.valence = _clamp(valence)
        self.arousal = _clamp(arousal, 0.0, 1.0)
        self.strength = MARKER_STRENGTH_INITIAL
        self.outcome_description = outcome_description[:300]
        self.created_at = _now()
        self.last_activated = _now()
        self.activation_count = 1

    def to_dict(self) -> dict:
        return {
            "marker_id": self.marker_id,
            "situation_hash": self.situation_hash,
            "action": self.action,
            "valence": round(self.valence, 3),
            "arousal": round(self.arousal, 3),
            "strength": round(self.strength, 4),
            "outcome_description": self.outcome_description,
            "created_at": self.created_at,
            "last_activated": self.last_activated,
            "activation_count": self.activation_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SomaticMarker":
        m = cls(
            situation_hash=d.get("situation_hash", ""),
            action=d.get("action", ""),
            valence=d.get("valence", 0.0),
            arousal=d.get("arousal", 0.2),
            outcome_description=d.get("outcome_description", ""),
        )
        m.marker_id = d.get("marker_id", m.marker_id)
        m.strength = d.get("strength", MARKER_STRENGTH_INITIAL)
        m.created_at = d.get("created_at", _now())
        m.last_activated = d.get("last_activated", _now())
        m.activation_count = d.get("activation_count", 1)
        return m

    def apply_decay(self):
        """Apply time-based strength decay."""
        try:
            last = datetime.fromisoformat(self.last_activated)
            days = (datetime.now() - last).total_seconds() / 86400.0
            if days > 1:
                self.strength *= math.pow(MARKER_STRENGTH_DECAY, days)
                self.strength = max(0.01, self.strength)
        except (ValueError, TypeError):
            pass


class EmotionalMemory:
    """A memory tagged with emotional state for mood-congruent recall."""

    __slots__ = [
        "memory_id", "content", "valence", "arousal", "emotion_label",
        "importance", "created_at",
    ]

    def __init__(self, memory_id: str, content: str,
                 valence: float, arousal: float,
                 emotion_label: str = "neutral", importance: float = 0.5):
        self.memory_id = memory_id
        self.content = content[:500]
        self.valence = _clamp(valence)
        self.arousal = _clamp(arousal, 0.0, 1.0)
        self.emotion_label = emotion_label
        self.importance = _clamp(importance, 0.0, 1.0)
        self.created_at = _now()

    def to_dict(self) -> dict:
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "valence": round(self.valence, 3),
            "arousal": round(self.arousal, 3),
            "emotion_label": self.emotion_label,
            "importance": round(self.importance, 3),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EmotionalMemory":
        return cls(
            memory_id=d.get("memory_id", ""),
            content=d.get("content", ""),
            valence=d.get("valence", 0.0),
            arousal=d.get("arousal", 0.2),
            emotion_label=d.get("emotion_label", "neutral"),
            importance=d.get("importance", 0.5),
        )


# ── Emotional Regulation Engine ─────────────────────────────────────────────

class EmotionalRegulation:
    """
    Uses emotions to modulate cognition in FRIDAY.

    Not an emotion tracker (self_awareness does that) — this engine
    actively leverages emotional signals to improve:
    - Decision-making via somatic markers
    - Memory retrieval via mood-congruent processing
    - Framing via cognitive reappraisal
    - Fast evaluation via affect heuristic
    - Strategy selection via emotion regulation
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self._somatic_markers: Dict[str, SomaticMarker] = {}
        self._emotional_memories: List[EmotionalMemory] = []
        self._current_mood = EmotionalState()
        self._mood_history: deque = deque(maxlen=100)
        self._regulation_log: List[dict] = []
        self._strategy_effectiveness: Dict[str, Dict[str, float]] = {}
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": _now(),
                "last_update": _now(),
                "total_markers": 0,
                "total_regulations": 0,
                "total_reappraisals": 0,
            },
            "somatic_markers": {},
            "emotional_memories": [],
            "mood_history": [],
            "regulation_log": [],
            "strategy_effectiveness": {},
            "current_mood": {"valence": 0.0, "arousal": 0.2, "label": "neutral"},
        }

    def _load(self):
        if not EMOTIONAL_FILE.exists():
            self._data = self._empty_store()
            self._save()
            return
        try:
            raw = EMOTIONAL_FILE.read_text(encoding="utf-8")
            self._data = json.loads(raw)
            for mid, md in self._data.get("somatic_markers", {}).items():
                self._somatic_markers[mid] = SomaticMarker.from_dict(md)
            self._emotional_memories = [
                EmotionalMemory.from_dict(m)
                for m in self._data.get("emotional_memories", [])
            ]
            mood = self._data.get("current_mood", {})
            self._current_mood = EmotionalState(
                valence=mood.get("valence", 0.0),
                arousal=mood.get("arousal", 0.2),
                label=mood.get("label", "neutral"),
            )
            self._strategy_effectiveness = self._data.get("strategy_effectiveness", {})
        except (json.JSONDecodeError, IOError):
            self._data = self._empty_store()
            self._save()

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._data["somatic_markers"] = {
                mid: m.to_dict() for mid, m in self._somatic_markers.items()
            }
            self._data["emotional_memories"] = [
                m.to_dict() for m in self._emotional_memories[-RECALL_WINDOW:]
            ]
            self._data["current_mood"] = self._current_mood.to_dict()
            self._data["mood_history"] = [
                m.to_dict() for m in list(self._mood_history)[-100:]
            ]
            self._data["regulation_log"] = self._regulation_log[-MAX_EVENT_LOG:]
            self._data["strategy_effectiveness"] = self._strategy_effectiveness
            self._data["meta"]["last_update"] = _now()
            EMOTIONAL_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ── Mood Management ─────────────────────────────────────────────────

    def update_mood(self, valence_delta: float, arousal_delta: float = 0.0,
                    label: Optional[str] = None):
        """
        Update current emotional mood based on an event.
        Uses exponential smoothing to avoid mood whiplash.
        """
        with self._lock:
            # Smooth update (70% old, 30% new)
            self._current_mood.valence = _clamp(
                self._current_mood.valence * 0.7 + valence_delta * 0.3
            )
            self._current_mood.arousal = _clamp(
                self._current_mood.arousal * 0.7 + arousal_delta * 0.3,
                0.0, 1.0
            )
            if label:
                self._current_mood.label = label
            self._current_mood.timestamp = _now()
            self._mood_history.append(EmotionalState(
                valence=self._current_mood.valence,
                arousal=self._current_mood.arousal,
                label=self._current_mood.label,
            ))
            self._save()

    def get_current_mood(self) -> dict:
        """Get current emotional mood state."""
        with self._lock:
            return self._current_mood.to_dict()

    def set_mood_from_emotion(self, emotion_label: str):
        """Set mood directly from a named emotion."""
        state = EmotionalState.from_emotion_label(emotion_label)
        with self._lock:
            self._current_mood = state
            self._mood_history.append(state)
            self._save()

    # ── Somatic Markers (Damasio) ───────────────────────────────────────

    def _hash_situation(self, situation: str) -> str:
        """Create a stable hash for a situation description."""
        import hashlib
        return hashlib.md5(situation.lower().strip().encode()).hexdigest()[:12]

    def create_somatic_marker(self, situation: str, action: str,
                               outcome_valence: float, outcome_arousal: float = 0.3,
                               outcome_description: str = ""):
        """
        Create or update a somatic marker for a (situation, action) pair.

        Based on Damasio's SMH: emotional outcomes create markers that
        bias future decisions in similar situations.
        """
        sit_hash = self._hash_situation(situation)
        marker_id = f"{sit_hash}:{action}"[:60]

        with self._lock:
            if marker_id in self._somatic_markers:
                # Reinforce existing marker
                marker = self._somatic_markers[marker_id]
                lr = 0.3
                marker.valence = marker.valence * (1 - lr) + outcome_valence * lr
                marker.arousal = marker.arousal * (1 - lr) + outcome_arousal * lr
                marker.strength = min(1.0, marker.strength + MARKER_REINFORCE)
                marker.activation_count += 1
                marker.last_activated = _now()
                if outcome_description:
                    marker.outcome_description = outcome_description[:300]
            else:
                # New marker
                marker = SomaticMarker(
                    situation_hash=sit_hash,
                    action=action,
                    valence=outcome_valence,
                    arousal=outcome_arousal,
                    outcome_description=outcome_description,
                )
                self._somatic_markers[marker_id] = marker

                # Enforce capacity
                if len(self._somatic_markers) > MAX_SOMATIC_MARKERS:
                    # Remove weakest
                    sorted_markers = sorted(
                        self._somatic_markers.items(),
                        key=lambda x: x[1].strength
                    )
                    for old_id, _ in sorted_markers[:len(sorted_markers) - MAX_SOMATIC_MARKERS]:
                        del self._somatic_markers[old_id]

            self._data["meta"]["total_markers"] += 1
            self._save()

    def apply_somatic_markers(self, options: List[dict]) -> List[dict]:
        """
        Apply somatic markers to re-rank decision options.

        Each option should have:
        - "situation": str
        - "action": str
        - Other fields preserved

        Returns options sorted by emotionally-weighted preference.
        Damasio's SMH: emotionally tagged outcomes bias choices.
        """
        with self._lock:
            scored_options = []
            for opt in options:
                situation = opt.get("situation", "")
                action = opt.get("action", "")
                sit_hash = self._hash_situation(situation)
                marker_id = f"{sit_hash}:{action}"[:60]

                marker = self._somatic_markers.get(marker_id)
                if marker:
                    marker.apply_decay()
                    marker.last_activated = _now()
                    # Emotional score: valence weighted by strength
                    emotional_score = marker.valence * marker.strength
                    opt_copy = dict(opt)
                    opt_copy["_somatic_valence"] = round(marker.valence, 3)
                    opt_copy["_somatic_strength"] = round(marker.strength, 3)
                    opt_copy["_emotional_score"] = round(emotional_score, 3)
                else:
                    opt_copy = dict(opt)
                    opt_copy["_somatic_valence"] = 0.0
                    opt_copy["_somatic_strength"] = 0.0
                    opt_copy["_emotional_score"] = 0.0

                scored_options.append(opt_copy)

            # Sort by emotional score (descending — positive markers preferred)
            scored_options.sort(key=lambda x: x["_emotional_score"], reverse=True)
            self._save()
            return scored_options

    def weaken_somatic_marker(self, situation: str, action: str,
                               penalty: float = MARKER_WEAKEN):
        """Weaken a somatic marker after a negative outcome."""
        sit_hash = self._hash_situation(situation)
        marker_id = f"{sit_hash}:{action}"[:60]
        with self._lock:
            marker = self._somatic_markers.get(marker_id)
            if marker:
                marker.strength = max(0.01, marker.strength + penalty)
                marker.last_activated = _now()
                self._save()

    # ── Mood-Congruent Recall (Bower) ──────────────────────────────────

    def store_emotional_memory(self, memory_id: str, content: str,
                                emotion_label: str = "neutral",
                                importance: float = 0.5):
        """Store a memory tagged with its emotional context."""
        state = EmotionalState.from_emotion_label(emotion_label)
        mem = EmotionalMemory(
            memory_id=memory_id,
            content=content,
            valence=state.valence,
            arousal=state.arousal,
            emotion_label=emotion_label,
            importance=importance,
        )
        with self._lock:
            self._emotional_memories.append(mem)
            if len(self._emotional_memories) > RECALL_WINDOW:
                self._emotional_memories = self._emotional_memories[-RECALL_WINDOW:]
            self._save()

    def mood_congruent_recall(self, query: str = "",
                               current_mood: Optional[dict] = None,
                               limit: int = 10) -> List[dict]:
        """
        Retrieve memories that match the current emotional mood.

        Based on Bower's mood-congruent memory theory: memories encoded
        during a similar emotional state are more accessible.

        Args:
            query: Optional text to match against content
            current_mood: Override mood (uses stored mood if None)
            limit: Max memories to return

        Returns:
            List of memories sorted by mood-congruence and importance
        """
        with self._lock:
            if current_mood:
                mood = EmotionalState(
                    valence=current_mood.get("valence", 0.0),
                    arousal=current_mood.get("arousal", 0.2),
                )
            else:
                mood = self._current_mood

            scored = []
            for mem in self._emotional_memories:
                mem_state = EmotionalState(
                    valence=mem.valence, arousal=mem.arousal
                )
                similarity = mood.similarity_to(mem_state)

                if similarity < MOOD_SIMILARITY_THRESHOLD:
                    continue

                # Query relevance (simple keyword match)
                query_score = 1.0
                if query:
                    query_lower = query.lower()
                    content_lower = mem.content.lower()
                    # Count keyword overlap
                    q_words = set(query_lower.split())
                    c_words = set(content_lower.split())
                    overlap = len(q_words & c_words)
                    query_score = min(1.0, overlap / max(len(q_words), 1) + 0.2)

                # Combined score: mood similarity * importance * query relevance
                combined = similarity * mem.importance * query_score

                scored.append({
                    "memory_id": mem.memory_id,
                    "content": mem.content,
                    "emotion_label": mem.emotion_label,
                    "mood_similarity": round(similarity, 3),
                    "importance": round(mem.importance, 3),
                    "relevance_score": round(combined, 3),
                })

            scored.sort(key=lambda x: x["relevance_score"], reverse=True)
            return scored[:limit]

    # ── Cognitive Reappraisal (Gross, Ochsner) ──────────────────────────

    def reappraise(self, event: str, current_frame: str = "") -> dict:
        """
        Generate alternative interpretations (reappraisal) of an event.

        Based on Gross's process model: reappraisal changes the meaning
        of a situation, which changes its emotional impact.

        Args:
            event: The event or situation to reappraise
            current_frame: How it's currently being interpreted

        Returns:
            Dict with alternative frames and emotional predictions
        """
        event_lower = event.lower()

        # Detect which reappraisal templates are relevant
        applicable = []

        # Threat → Challenge
        threat_words = {"fail", "error", "wrong", "broken", "bug", "crash", "danger", "risk", "threat"}
        if any(w in event_lower for w in threat_words):
            applicable.append(("threat_to_challenge", REAPPRAISAL_TEMPLATES["threat_to_challenge"]))

        # Failure → Learning
        fail_words = {"fail", "mistake", "wrong", "incorrect", "bad", "poor", "terrible"}
        if any(w in event_lower for w in fail_words):
            applicable.append(("failure_to_learning", REAPPRAISAL_TEMPLATES["failure_to_learning"]))

        # Overwhelming → Stepwise
        overwhelm_words = {"too much", "overwhelming", "impossible", "huge", "massive", "complex"}
        if any(w in event_lower for w in overwhelm_words):
            applicable.append(("overwhelming_to_stepwise", REAPPRAISAL_TEMPLATES["overwhelming_to_stepwise"]))

        # Ambiguous → Curious
        ambiguous_words = {"unclear", "ambiguous", "uncertain", "confus", "unknown", "unsure"}
        if any(w in event_lower for w in ambiguous_words):
            applicable.append(("ambiguous_to_curious", REAPPRAISAL_TEMPLATES["ambiguous_to_curious"]))

        # Catastrophic → Realistic
        catastrophe_words = {"catastroph", "disaster", "worst", "terrible", "awful", "ruin"}
        if any(w in event_lower for w in catastrophe_words):
            applicable.append(("catastrophic_to_realistic", REAPPRAISAL_TEMPLATES["catastrophic_to_realistic"]))

        # Always offer permanent → temporary and personal → situational
        applicable.append(("permanent_to_temporary", REAPPRAISAL_TEMPLATES["permanent_to_temporary"]))
        applicable.append(("personal_to_situational", REAPPRAISAL_TEMPLATES["personal_to_situational"]))

        # Estimate emotional shift from reappraisal
        # Negative events reframed = valence increase
        current_valence = self._current_mood.valence
        estimated_shift = min(0.4, abs(current_valence) * 0.5) if current_valence < 0 else 0.1

        with self._lock:
            self._data["meta"]["total_reappraisals"] += 1
            self._save()

        return {
            "event": event[:200],
            "current_frame": current_frame[:200] if current_frame else "unspecified",
            "alternative_frames": [
                {"strategy": name, "reframe": text}
                for name, text in applicable
            ],
            "recommended_strategy": applicable[0][0] if applicable else "acceptance",
            "estimated_emotional_shift": round(estimated_shift, 3),
            "current_valence": round(current_valence, 3),
            "predicted_valence_after": round(
                _clamp(current_valence + estimated_shift), 3
            ),
        }

    # ── Affect Heuristic (Slovic) ──────────────────────────────────────

    def affect_heuristic(self, action: str, context: str = "") -> dict:
        """
        Fast emotional evaluation of an action using the affect heuristic.

        Slovic et al. (2002): people use "How do I feel about this?"
        as a fast proxy for evaluation. This method aggregates:
        1. Somatic marker valence for this action
        2. Current mood bias
        3. Emotional associations with similar past actions
        """
        with self._lock:
            # Signal 1: somatic markers for this action
            marker_valences = []
            for marker in self._somatic_markers.values():
                if marker.action == action or action.lower() in marker.action.lower():
                    marker.apply_decay()
                    marker_valences.append(marker.valence * marker.strength)

            marker_signal = (
                sum(marker_valences) / len(marker_valences)
                if marker_valences else 0.0
            )

            # Signal 2: current mood bias
            mood_signal = self._current_mood.valence * 0.3

            # Signal 3: keyword association with emotional memories
            action_words = set(action.lower().split())
            memory_valences = []
            for mem in self._emotional_memories[-50:]:
                mem_words = set(mem.content.lower().split())
                overlap = len(action_words & mem_words)
                if overlap > 0:
                    memory_valences.append(mem.valence * (overlap / max(len(action_words), 1)))

            memory_signal = (
                sum(memory_valences) / len(memory_valences)
                if memory_valences else 0.0
            )

            # Aggregate
            total_valence = marker_signal + mood_signal + memory_signal
            total_valence = _clamp(total_valence)

            if total_valence > 0.3:
                feeling = "positive"
            elif total_valence < -0.3:
                feeling = "negative"
            else:
                feeling = "neutral"

            return {
                "action": action[:100],
                "emotional_valence": round(total_valence, 3),
                "feeling": feeling,
                "confidence": round(min(1.0, abs(total_valence) * 1.5), 3),
                "signals": {
                    "somatic_marker": round(marker_signal, 3),
                    "mood_bias": round(mood_signal, 3),
                    "memory_association": round(memory_signal, 3),
                },
                "markers_consulted": len(marker_valences),
            }

    # ── Emotion Regulation Strategies (Gross) ──────────────────────────

    def regulate_cognitive_state(self, emotion: str, task: str = "") -> dict:
        """
        Select and recommend an emotion regulation strategy for the
        current cognitive state.

        Based on Gross's (1998) process model of emotion regulation.
        """
        state = EmotionalState.from_emotion_label(emotion)
        is_negative = state.valence < -0.2
        is_high_arousal = state.arousal > 0.6

        strategies = []

        if is_negative and is_high_arousal:
            # High-arousal negative (anxiety, frustration): calm first
            strategies.append({
                "name": "attentional_deployment",
                "description": "Shift attention away from the source of distress. Focus on a neutral or positive aspect of the task.",
                "priority": 1,
                "expected_effect": "Reduce arousal within 30 seconds",
            })
            strategies.append({
                "name": "cognitive_reappraisal",
                "description": "Reframe the situation. What's the learning opportunity? Is this as bad as it feels?",
                "priority": 2,
                "expected_effect": "Shift valence from negative toward neutral",
            })
        elif is_negative and not is_high_arousal:
            # Low-arousal negative (boredom, disappointment): engage
            strategies.append({
                "name": "cognitive_reappraisal",
                "description": "Reframe the situation. Find the challenge or novelty hidden in the task.",
                "priority": 1,
                "expected_effect": "Increase engagement and motivation",
            })
            strategies.append({
                "name": "situation_modification",
                "description": "Change the task approach. Try a different strategy or angle.",
                "priority": 2,
                "expected_effect": "Introduce novelty to counter boredom",
            })
        elif not is_negative and is_high_arousal:
            # High-arousal positive (excitement, curiosity): channel it
            strategies.append({
                "name": "situation_selection",
                "description": "Channel this energy into the most important/creative task. Excitement enhances creative thinking.",
                "priority": 1,
                "expected_effect": "Leverage positive arousal for productivity",
            })
        else:
            # Neutral or low-arousal positive: maintain
            strategies.append({
                "name": "acceptance",
                "description": "Current emotional state is functional. Continue with planned activities.",
                "priority": 1,
                "expected_effect": "Maintain stable cognitive performance",
            })

        # Record for effectiveness tracking
        strategy_name = strategies[0]["name"]
        self._track_regulation_strategy(emotion, task, strategy_name)

        return {
            "current_emotion": emotion,
            "emotion_valence": round(state.valence, 3),
            "emotion_arousal": round(state.arousal, 3),
            "recommended_strategies": strategies,
            "primary_strategy": strategies[0]["name"],
            "reasoning": (
                f"Emotion '{emotion}' has valence={state.valence:.2f}, "
                f"arousal={state.arousal:.2f}. "
                f"{'High-arousal negative: calm first, then reappraise.' if is_negative and is_high_arousal else ''}"
                f"{'Low-arousal negative: reframe and re-engage.' if is_negative and not is_high_arousal else ''}"
                f"{'High-arousal positive: channel energy productively.' if not is_negative and is_high_arousal else ''}"
                f"{'Stable state: maintain and proceed.' if not is_negative and not is_high_arousal else ''}"
            ),
        }

    def _track_regulation_strategy(self, emotion: str, task: str,
                                    strategy: str):
        """Track regulation strategy effectiveness."""
        key = f"{emotion}:{strategy}"
        with self._lock:
            if key not in self._strategy_effectiveness:
                self._strategy_effectiveness[key] = {
                    "emotion": emotion,
                    "strategy": strategy,
                    "uses": 0,
                    "reported_effective": 0,
                }
            self._strategy_effectiveness[key]["uses"] += 1
            self._save()

    def report_regulation_outcome(self, emotion: str, strategy: str,
                                   effective: bool):
        """Report whether a regulation strategy was effective."""
        key = f"{emotion}:{strategy}"
        with self._lock:
            if key in self._strategy_effectiveness:
                if effective:
                    self._strategy_effectiveness[key]["reported_effective"] += 1
                self._save()

    def get_best_strategy_for_emotion(self, emotion: str) -> Optional[str]:
        """Get the historically most effective regulation strategy for an emotion."""
        with self._lock:
            candidates = [
                (k, v) for k, v in self._strategy_effectiveness.items()
                if v["emotion"] == emotion and v["uses"] >= 3
            ]
            if not candidates:
                return None
            # Sort by effectiveness ratio
            candidates.sort(
                key=lambda x: x[1]["reported_effective"] / max(x[1]["uses"], 1),
                reverse=True,
            )
            return candidates[0][1]["strategy"]

    # ── Integration: Emotional State Report ─────────────────────────────

    def get_emotional_context(self) -> dict:
        """
        Get comprehensive emotional context for cognitive integration.
        Combines mood, recent markers, and regulation recommendations.
        """
        mood = self.get_current_mood()
        regulation = self.regulate_cognitive_state(
            self._current_mood.label, ""
        )

        # Recent strong markers
        strong_markers = sorted(
            [m for m in self._somatic_markers.values() if m.strength > 0.3],
            key=lambda m: m.strength,
            reverse=True,
        )[:5]

        return {
            "mood": mood,
            "regulation": {
                "primary_strategy": regulation["primary_strategy"],
                "reasoning": regulation["reasoning"],
            },
            "strong_markers": [
                {
                    "action": m.action,
                    "valence": round(m.valence, 3),
                    "strength": round(m.strength, 3),
                }
                for m in strong_markers
            ],
            "emotional_memories_count": len(self._emotional_memories),
            "total_markers": len(self._somatic_markers),
        }

    def format_for_prompt(self, max_chars: int = 500) -> str:
        """Format emotional awareness for system prompt injection."""
        mood = self._current_mood
        regulation = self.regulate_cognitive_state(mood.label, "")
        strong = [m for m in self._somatic_markers.values() if m.strength > 0.5]

        parts = [
            "[EMOTIONAL REGULATION — Affective awareness]",
            f"Current mood: {mood.label} (valence={mood.valence:+.2f}, arousal={mood.arousal:.2f})",
            f"Strategy: {regulation['primary_strategy']}",
        ]

        if strong:
            parts.append(f"Strong emotional markers: {len(strong)} active")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "[...]"
        return result

    # ── Maintenance ─────────────────────────────────────────────────────

    def decay_all_markers(self):
        """Apply decay to all somatic markers. Call periodically."""
        with self._lock:
            for marker in self._somatic_markers.values():
                marker.apply_decay()
            self._save()

    def prune_weak_markers(self, threshold: float = 0.05):
        """Remove markers that have decayed below threshold."""
        with self._lock:
            before = len(self._somatic_markers)
            self._somatic_markers = {
                mid: m for mid, m in self._somatic_markers.items()
                if m.strength > threshold
            }
            pruned = before - len(self._somatic_markers)
            if pruned > 0:
                self._save()
            return pruned

    def get_stats(self) -> dict:
        """Get overall emotional regulation statistics."""
        with self._lock:
            total_memories = sum(len(ml) for ml in self._emotional_memories.values())
            return {
                "somatic_markers": len(self._somatic_markers),
                "emotion_categories": len(self._somatic_markers),
                "emotional_memories": total_memories,
                "regulation_strategies": len(self._regulation_strategies),
                "session_regulations": getattr(self, '_session_regulations', 0),
            }


# ── Singleton ───────────────────────────────────────────────────────────────

_emotional_regulation = None
_emotional_lock = threading.Lock()


def get_emotional_regulation() -> EmotionalRegulation:
    """Get singleton EmotionalRegulation instance."""
    global _emotional_regulation
    if _emotional_regulation is None:
        with _emotional_lock:
            if _emotional_regulation is None:
                _emotional_regulation = EmotionalRegulation()
    return _emotional_regulation
