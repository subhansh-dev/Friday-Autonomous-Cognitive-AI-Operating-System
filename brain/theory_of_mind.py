#!/usr/bin/env python3
"""
theory_of_mind.py — FRIDAY Theory of Mind (User Mental Model)
================================================================

Models the user's mental state to provide personalized, context-aware
interactions. Infers expertise, intent, emotional state, communication
style, and predicts future needs.

Inspired by:
  - Premack & Woodruff (1978) — Does the chimpanzee have a theory of mind?
  - Baron-Cohen's Empathizing-Systemizing theory
  - User modeling in HCI (Kobsa, 2001)
  - Affective computing (Picard, 1997)

Key behaviors:
  - Learn from each interaction to build user model
  - Infer expertise level per topic
  - Infer user intent and emotional state
  - Adapt communication style to user preferences
  - Predict what the user will need next

Persistence: brain/tom_state.json
"""

import json
import math
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


BRAIN_DIR = Path(__file__).parent.resolve()
TOM_FILE = BRAIN_DIR / "tom_state.json"

# ── Configuration ───────────────────────────────────────────────────────────

MAX_INTERACTION_HISTORY = 300
MAX_TOPIC_EXPERTISE = 100
EXPERTISE_DECAY_DAYS = 30.
EMOTION_KEYWORDS = {
    "frustrated": "frustrated",
    "annoyed": "frustrated",
    "angry": "angry",
    "mad": "angry",
    "happy": "happy",
    "great": "happy",
    "excited": "excited",
    "awesome": "excited",
    "sad": "sad",
    "down": "sad",
    "confused": "confused",
    "lost": "confused",
    "worried": "anxious",
    "anxious": "anxious",
    "stressed": "stressed",
    "overwhelmed": "stressed",
    "calm": "calm",
    "relaxed": "calm",
    "curious": "curious",
    "interested": "curious",
    "tired": "tired",
    "exhausted": "tired",
}
INTENT_PATTERNS = {
    "question": [r"\?", r"^what\b", r"^how\b", r"^why\b", r"^when\b",
                 r"^where\b", r"^who\b", r"^can you\b", r"^do you\b"],
    "request": [r"^please\b", r"^could you\b", r"^would you\b",
                r"^i need\b", r"^i want\b", r"^help me\b"],
    "command": [r"^(do|run|make|create|build|fix|delete|update|set)\b"],
    "clarification": [r"^what do you mean\b", r"^i don.t understand\b",
                      r"^can you explain\b", r"^clarify\b"],
    "feedback": [r"^that.s (wrong|incorrect|right|correct|good|bad)\b",
                 r"^no\b", r"^yes\b", r"^actually\b"],
    "social": [r"^(hi|hello|hey|thanks|thank you|goodbye|bye)\b"],
}


def _now() -> str:
    return datetime.now().isoformat()


def _timestamp() -> float:
    return time.time()


# ── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class UserMentalModel:
    """Complete model of the user's mental state."""
    expertise_level: Dict[str, float] = field(default_factory=dict)
    preferences: Dict[str, Any] = field(default_factory=dict)
    emotional_state: str = "neutral"
    emotional_history: List[dict] = field(default_factory=list)
    communication_style: str = "adaptive"
    beliefs: Dict[str, str] = field(default_factory=dict)
    goals: List[str] = field(default_factory=list)
    interests: List[str] = field(default_factory=list)
    annoyances: List[str] = field(default_factory=list)
    interaction_count: int = 0
    topics_discussed: Dict[str, int] = field(default_factory=dict)
    style_signals: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "expertise_level": {k: round(v, 3) for k, v in self.expertise_level.items()},
            "preferences": self.preferences,
            "emotional_state": self.emotional_state,
            "emotional_history": self.emotional_history[-50:],
            "communication_style": self.communication_style,
            "beliefs": self.beliefs,
            "goals": self.goals,
            "interests": self.interests,
            "annoyances": self.annoyances,
            "interaction_count": self.interaction_count,
            "topics_discussed": self.topics_discussed,
            "style_signals": self.style_signals,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UserMentalModel":
        return cls(
            expertise_level=d.get("expertise_level", {}),
            preferences=d.get("preferences", {}),
            emotional_state=d.get("emotional_state", "neutral"),
            emotional_history=d.get("emotional_history", []),
            communication_style=d.get("communication_style", "adaptive"),
            beliefs=d.get("beliefs", {}),
            goals=d.get("goals", []),
            interests=d.get("interests", []),
            annoyances=d.get("annoyances", []),
            interaction_count=d.get("interaction_count", 0),
            topics_discussed=d.get("topics_discussed", {}),
            style_signals=d.get("style_signals", {}),
        )


@dataclass
class InteractionRecord:
    """A record of a single interaction."""
    record_id: str
    user_message: str
    assistant_response: str
    inferred_intent: str = "unknown"
    inferred_emotion: str = "neutral"
    topics: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "user_message": self.user_message[:500],
            "assistant_response": self.assistant_response[:500],
            "inferred_intent": self.inferred_intent,
            "inferred_emotion": self.inferred_emotion,
            "topics": self.topics,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InteractionRecord":
        return cls(
            record_id=d.get("record_id", ""),
            user_message=d.get("user_message", ""),
            assistant_response=d.get("assistant_response", ""),
            inferred_intent=d.get("inferred_intent", "unknown"),
            inferred_emotion=d.get("inferred_emotion", "neutral"),
            topics=d.get("topics", []),
            timestamp=d.get("timestamp", ""),
        )


# ── Theory of Mind ──────────────────────────────────────────────────────────

class TheoryOfMind:
    """
    Models the user's mental state to personalize interactions.

    Builds and maintains a UserMentalModel through interaction analysis,
    inferring expertise, intent, emotion, communication style, and
    predicting future needs.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self._user_model = UserMentalModel()
        self._interaction_history: List[InteractionRecord] = []
        self._session_interactions: int = 0
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": _now(),
                "last_update": _now(),
                "total_interactions": 0,
            },
            "user_model": UserMentalModel().to_dict(),
            "interaction_history": [],
        }

    def _load(self):
        if not TOM_FILE.exists():
            self._data = self._empty_store()
            self._save()
            return
        try:
            raw = TOM_FILE.read_text(encoding="utf-8")
            self._data = json.loads(raw)
            self._user_model = UserMentalModel.from_dict(
                self._data.get("user_model", {})
            )
            self._interaction_history = [
                InteractionRecord.from_dict(r)
                for r in self._data.get("interaction_history", [])
            ]
        except (json.JSONDecodeError, IOError):
            self._data = self._empty_store()
            self._save()

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._data["user_model"] = self._user_model.to_dict()
            self._data["interaction_history"] = [
                r.to_dict() for r in self._interaction_history[-MAX_INTERACTION_HISTORY:]
            ]
            self._data["meta"]["last_update"] = _now()
            TOM_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ── Core Update ─────────────────────────────────────────────────────

    def update_from_interaction(self, message: str, response: str):
        """
        Learn from each interaction to update the user model.

        Analyzes the message for intent, emotion, expertise signals,
        communication style, and topic interests.
        """
        import hashlib
        record_id = hashlib.md5(
            f"{message}:{_now()}".encode()
        ).hexdigest()[:12]

        intent = self.infer_intent(message)
        emotion = self.infer_emotional_state(message)
        topics = self._extract_topics(message)
        style = self._detect_style_signals(message)

        with self._lock:
            self._session_interactions += 1
            self._user_model.interaction_count += 1
            self._data["meta"]["total_interactions"] += 1

            # Update emotional state
            self._user_model.emotional_state = emotion
            self._user_model.emotional_history.append({
                "emotion": emotion,
                "timestamp": _now(),
            })
            if len(self._user_model.emotional_history) > 50:
                self._user_model.emotional_history = self._user_model.emotional_history[-50:]

            # Update topics
            for topic in topics:
                self._user_model.topics_discussed[topic] = (
                    self._user_model.topics_discussed.get(topic, 0) + 1
                )

            # Update style signals
            for signal, count in style.items():
                self._user_model.style_signals[signal] = (
                    self._user_model.style_signals.get(signal, 0) + count
                )

            # Update communication style
            self._update_communication_style()

            # Update expertise signals
            self._update_expertise_from_message(message, topics)

            # Record interaction
            record = InteractionRecord(
                record_id=record_id,
                user_message=message,
                assistant_response=response,
                inferred_intent=intent,
                inferred_emotion=emotion,
                topics=topics,
                timestamp=_now(),
            )
            self._interaction_history.append(record)
            if len(self._interaction_history) > MAX_INTERACTION_HISTORY:
                self._interaction_history = self._interaction_history[-MAX_INTERACTION_HISTORY:]

            self._save()

    # ── Inference Methods ───────────────────────────────────────────────

    def infer_expertise(self, topic: str) -> dict:
        """
        Estimate user's knowledge level for a topic.

        Returns expertise assessment with level and confidence.
        """
        with self._lock:
            topic_lower = topic.lower()

            # Direct expertise score
            direct_score = 0.0
            for stored_topic, score in self._user_model.expertise_level.items():
                if stored_topic.lower() == topic_lower:
                    direct_score = score
                    break

            # Frequency-based signal
            freq = self._user_model.topics_discussed.get(topic_lower, 0)
            freq_score = min(1.0, freq / 20.0)

            # Technical vocabulary signal
            tech_score = 0.0
            for record in self._interaction_history[-30:]:
                if topic_lower in record.user_message.lower():
                    # Check for technical vocabulary
                    msg = record.user_message
                    tech_indicators = [
                        len(re.findall(r"\b[A-Z]{2,}\b", msg)),  # acronyms
                        len(re.findall(r"\d+\.\d+", msg)),        # version numbers
                        msg.count("_") + msg.count("::"),          # code patterns
                    ]
                    tech_score = min(1.0, sum(tech_indicators) / 10.0)

            combined = (
                direct_score * 0.4 +
                freq_score * 0.3 +
                tech_score * 0.3
            )

            if combined >= 0.8:
                level = "expert"
            elif combined >= 0.6:
                level = "advanced"
            elif combined >= 0.4:
                level = "intermediate"
            elif combined >= 0.2:
                level = "beginner"
            else:
                level = "novice"

            return {
                "topic": topic,
                "level": level,
                "score": round(combined, 3),
                "direct_expertise": round(direct_score, 3),
                "discussion_frequency": freq,
                "technical_score": round(tech_score, 3),
            }

    def infer_intent(self, message: str) -> str:
        """
        Infer what the user REALLY wants from their message.

        Returns intent category: question, request, command,
        clarification, feedback, social, or unknown.
        """
        msg_lower = message.lower().strip()

        for intent, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, msg_lower):
                    return intent

        # Default heuristics
        if len(message) > 200:
            return "request"
        return "unknown"

    def infer_emotional_state(self, message: str) -> str:
        """
        Infer the user's emotional state from their message.

        Returns an emotion label.
        """
        msg_lower = message.lower()
        scores: Dict[str, float] = {}

        for keyword, emotion in EMOTION_KEYWORDS.items():
            if keyword in msg_lower:
                scores[emotion] = scores.get(emotion, 0) + 1.0

        # Punctuation signals
        if "!!" in message:
            scores["excited"] = scores.get("excited", 0) + 0.5
            scores["angry"] = scores.get("angry", 0) + 0.3
        if "..." in message:
            scores["frustrated"] = scores.get("frustrated", 0) + 0.3
        if message.isupper() and len(message) > 5:
            scores["angry"] = scores.get("angry", 0) + 0.5

        # Emoji signals
        emoji_emotion_map = {
            "😊": "happy", "😄": "happy", "🎉": "excited",
            "😢": "sad", "😤": "angry", "🤔": "curious",
            "😴": "tired", "😰": "anxious", "👍": "happy",
            "❤️": "happy", "🔥": "excited", "💯": "excited",
        }
        for emoji, emotion in emoji_emotion_map.items():
            if emoji in message:
                scores[emotion] = scores.get(emotion, 0) + 0.5

        if not scores:
            return "neutral"

        return max(scores, key=scores.get)

    def get_communication_style(self) -> str:
        """
        Determine the user's preferred communication style.

        Returns: formal, casual, technical, simple, or adaptive.
        """
        with self._lock:
            return self._user_model.communication_style

    def predict_user_needs(self) -> List[dict]:
        """
        Predict what the user will likely need next.

        Based on interaction patterns, topics, and goals.
        """
        with self._lock:
            predictions: List[dict] = []

            # Based on recent topics
            recent_topics: Dict[str, int] = {}
            for record in self._interaction_history[-10:]:
                for topic in record.topics:
                    recent_topics[topic] = recent_topics.get(topic, 0) + 1

            for topic, count in sorted(recent_topics.items(),
                                        key=lambda x: x[1], reverse=True)[:3]:
                expertise = self.infer_expertise(topic)
                predictions.append({
                    "type": "topic_continuation",
                    "topic": topic,
                    "confidence": min(1.0, count / 5.0),
                    "user_expertise": expertise["level"],
                    "suggestion": f"User may need more help with {topic}",
                })

            # Based on emotional state
            emotion = self._user_model.emotional_state
            if emotion in ("frustrated", "angry", "stressed"):
                predictions.append({
                    "type": "emotional_support",
                    "emotion": emotion,
                    "confidence": 0.7,
                    "suggestion": "User may need simpler explanations or encouragement",
                })
            elif emotion == "confused":
                predictions.append({
                    "type": "clarification_needed",
                    "emotion": emotion,
                    "confidence": 0.6,
                    "suggestion": "User may benefit from step-by-step explanations",
                })

            # Based on goals
            for goal in self._user_model.goals[:3]:
                predictions.append({
                    "type": "goal_progress",
                    "goal": goal,
                    "confidence": 0.4,
                    "suggestion": f"User may want progress updates on: {goal}",
                })

            return predictions

    def adapt_response(self, response: str) -> str:
        """
        Tailor a response to the user model.

        Adjusts formality, detail level, and tone based on
        inferred user preferences.
        """
        style = self._user_model.communication_style
        emotion = self._user_model.emotional_state

        # Style adaptations (light touch — don't rewrite, just suggest tone)
        if style == "formal":
            # Avoid contractions, casual language
            pass
        elif style == "casual":
            # Allow contractions, shorter sentences
            pass
        elif style == "technical":
            # Use precise terminology, skip basic explanations
            pass
        elif style == "simple":
            # Shorter sentences, avoid jargon
            pass

        # Emotional adaptations
        if emotion in ("frustrated", "angry"):
            # Add acknowledgment of difficulty
            if not any(w in response.lower() for w in ["understand", "frustrating", "tough"]):
                response = "I understand this can be frustrating. " + response
        elif emotion == "confused":
            # Add clarification offer
            if not any(w in response.lower() for w in ["clarify", "explain", "mean"]):
                response += "\n\nLet me know if any part needs clarification."

        return response

    # ── Internal Helpers ────────────────────────────────────────────────

    def _extract_topics(self, message: str) -> List[str]:
        """Extract topic keywords from a message."""
        # Simple keyword extraction
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "i", "you", "he", "she", "it", "we", "they", "me", "him",
            "her", "us", "them", "my", "your", "his", "its", "our",
            "their", "this", "that", "these", "those", "what", "which",
            "who", "whom", "how", "when", "where", "why", "and", "but",
            "or", "nor", "not", "so", "yet", "both", "either", "neither",
            "each", "every", "all", "any", "few", "more", "most", "other",
            "some", "such", "no", "only", "own", "same", "than", "too",
            "very", "just", "because", "as", "until", "while", "of", "at",
            "by", "for", "with", "about", "against", "between", "through",
            "during", "before", "after", "above", "below", "to", "from",
            "up", "down", "in", "out", "on", "off", "over", "under",
            "again", "further", "then", "once", "here", "there", "please",
            "can", "help", "want", "need", "like", "know", "think",
        }

        words = re.findall(r"\b[a-zA-Z]{3,}\b", message.lower())
        topics = [w for w in words if w not in stop_words]

        # Count frequency and return top topics
        freq: Dict[str, int] = {}
        for t in topics:
            freq[t] = freq.get(t, 0) + 1

        sorted_topics = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [t for t, _ in sorted_topics[:5]]

    def _detect_style_signals(self, message: str) -> Dict[str, int]:
        """Detect communication style signals in a message."""
        signals: Dict[str, int] = {}

        # Formality signals
        if re.search(r"\b(please|kindly|would you|could you)\b", message.lower()):
            signals["formal"] = signals.get("formal", 0) + 1
        if re.search(r"\b(hey|yo|sup|gonna|wanna|gotta)\b", message.lower()):
            signals["casual"] = signals.get("casual", 0) + 1

        # Technical signals
        if re.search(r"\b(api|sdk|http|json|sql|git|npm|pip)\b", message.lower()):
            signals["technical"] = signals.get("technical", 0) + 1
        if re.search(r"[a-zA-Z_]+\.[a-zA-Z_]+\(", message):
            signals["technical"] = signals.get("technical", 0) + 1

        # Simplicity signals
        avg_word_len = sum(len(w) for w in message.split()) / max(len(message.split()), 1)
        if avg_word_len < 4:
            signals["simple"] = signals.get("simple", 0) + 1

        # Detail preference
        if len(message) > 300:
            signals["detailed"] = signals.get("detailed", 0) + 1
        elif len(message) < 50:
            signals["brief"] = signals.get("brief", 0) + 1

        return signals

    def _update_communication_style(self):
        """Update the user's preferred communication style from signals."""
        signals = self._user_model.style_signals
        if not signals:
            return

        style_scores = {
            "formal": signals.get("formal", 0),
            "casual": signals.get("casual", 0),
            "technical": signals.get("technical", 0),
            "simple": signals.get("simple", 0),
        }

        total = sum(style_scores.values())
        if total < 3:
            return  # Not enough data

        dominant = max(style_scores, key=style_scores.get)
        dominant_ratio = style_scores[dominant] / total

        if dominant_ratio > 0.5:
            self._user_model.communication_style = dominant
        else:
            self._user_model.communication_style = "adaptive"

    def _update_expertise_from_message(self, message: str, topics: List[str]):
        """Update expertise scores based on message content."""
        msg_lower = message.lower()

        # Technical sophistication indicators
        tech_score = 0.0
        if re.search(r"\b(implement|architecture|algorithm|optimiz|refactor)\b", msg_lower):
            tech_score += 0.2
        if re.search(r"\b(async|concurrent|thread|mutex|cache|latency)\b", msg_lower):
            tech_score += 0.2
        if re.search(r"[a-zA-Z_]+\.[a-zA-Z_]+\(.*\)", message):
            tech_score += 0.15
        if re.search(r"\b(docker|kubernetes|terraform|aws|gcp|azure)\b", msg_lower):
            tech_score += 0.15

        # Update expertise for discussed topics
        for topic in topics:
            current = self._user_model.expertise_level.get(topic, 0.0)
            # Blend current with new signal
            updated = current * 0.9 + tech_score * 0.1
            self._user_model.expertise_level[topic] = min(1.0, updated)

        # Enforce capacity
        if len(self._user_model.expertise_level) > MAX_TOPIC_EXPERTISE:
            # Remove lowest-scoring topics
            sorted_topics = sorted(
                self._user_model.expertise_level.items(),
                key=lambda x: x[1],
            )
            for topic, _ in sorted_topics[:len(sorted_topics) - MAX_TOPIC_EXPERTISE]:
                del self._user_model.expertise_level[topic]

    # ── Profile ─────────────────────────────────────────────────────────

    def get_user_profile(self) -> dict:
        """Get the full user mental model."""
        with self._lock:
            model = self._user_model

            # Top expertise areas
            top_expertise = sorted(
                model.expertise_level.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:10]

            # Top topics
            top_topics = sorted(
                model.topics_discussed.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:10]

            # Dominant emotion (last 10 interactions)
            recent_emotions = [
                h["emotion"] for h in model.emotional_history[-10:]
            ]
            if recent_emotions:
                emotion_freq: Dict[str, int] = {}
                for e in recent_emotions:
                    emotion_freq[e] = emotion_freq.get(e, 0) + 1
                dominant_emotion = max(emotion_freq, key=emotion_freq.get)
            else:
                dominant_emotion = "neutral"

            return {
                "communication_style": model.communication_style,
                "current_emotion": model.emotional_state,
                "dominant_emotion": dominant_emotion,
                "top_expertise": [
                    {"topic": t, "score": round(s, 3)} for t, s in top_expertise
                ],
                "top_topics": [
                    {"topic": t, "count": c} for t, c in top_topics
                ],
                "interests": model.interests,
                "goals": model.goals,
                "annoyances": model.annoyances,
                "preferences": model.preferences,
                "interaction_count": model.interaction_count,
                "style_signals": model.style_signals,
            }

    # ── Goals & Interests ───────────────────────────────────────────────

    def add_goal(self, goal: str):
        """Add a user goal."""
        with self._lock:
            if goal not in self._user_model.goals:
                self._user_model.goals.append(goal)
                self._save()

    def add_interest(self, interest: str):
        """Add a user interest."""
        with self._lock:
            if interest not in self._user_model.interests:
                self._user_model.interests.append(interest)
                self._save()

    def add_annoyance(self, annoyance: str):
        """Record something that annoys the user."""
        with self._lock:
            if annoyance not in self._user_model.annoyances:
                self._user_model.annoyances.append(annoyance)
                self._save()

    def set_preference(self, key: str, value: Any):
        """Set a user preference."""
        with self._lock:
            self._user_model.preferences[key] = value
            self._save()

    # ── Statistics ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get Theory of Mind statistics."""
        with self._lock:
            return {
                "interaction_count": self._user_model.interaction_count,
                "topics_tracked": len(self._user_model.topics_discussed),
                "expertise_areas": len(self._user_model.expertise_level),
                "communication_style": self._user_model.communication_style,
                "current_emotion": self._user_model.emotional_state,
                "goals_count": len(self._user_model.goals),
                "interests_count": len(self._user_model.interests),
                "annoyances_count": len(self._user_model.annoyances),
                "history_size": len(self._interaction_history),
                "session_interactions": self._session_interactions,
            }

    def format_for_prompt(self, max_chars: int = 500) -> str:
        """Format user model for system prompt injection."""
        profile = self.get_user_profile()
        parts = [
            "[THEORY OF MIND — User mental model]",
            f"Style: {profile['communication_style']} | "
            f"Emotion: {profile['current_emotion']} "
            f"(dominant: {profile['dominant_emotion']})",
            f"Interactions: {profile['interaction_count']} | "
            f"Topics: {profile['topics_tracked']}",
        ]
        if profile["top_expertise"]:
            expertise_str = ", ".join(
                f"{e['topic']}={e['score']:.2f}" for e in profile["top_expertise"][:5]
            )
            parts.append(f"Expertise: {expertise_str}")
        if profile["goals"]:
            parts.append(f"Goals: {', '.join(profile['goals'][:3])}")
        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "[...]"
        return result


# ── Singleton ───────────────────────────────────────────────────────────────

_theory_of_mind = None
_tom_lock = threading.Lock()


def get_theory_of_mind() -> TheoryOfMind:
    """Get singleton TheoryOfMind instance."""
    global _theory_of_mind
    if _theory_of_mind is None:
        with _tom_lock:
            if _theory_of_mind is None:
                _theory_of_mind = TheoryOfMind()
    return _theory_of_mind
