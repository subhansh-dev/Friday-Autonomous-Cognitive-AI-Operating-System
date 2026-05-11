#!/usr/bin/env python3
"""
predictive_memory.py — FRIDAY Predictive Memory (Anticipatory Recall)
======================================================================

Anticipates what memories will be needed based on current context,
pre-loading relevant memories and learning from prediction accuracy.

Inspired by:
  - Prospective memory (Einstein & McDaniel, 1996)
  - Predictive processing framework (Clark, 2013)
  - Prefrontal cortex anticipatory activation patterns

Key behaviors:
  - Predict needed context from current situation
  - Pre-load relevant memories into working memory
  - Track prediction accuracy to improve over time
  - Report prediction confidence

Persistence: brain/predictive_state.json
"""

import hashlib
import json
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


BRAIN_DIR = Path(__file__).parent.resolve()
PREDICTIVE_FILE = BRAIN_DIR / "predictive_state.json"

# ── Configuration ───────────────────────────────────────────────────────────

MAX_TASK_PATTERNS = 200
MAX_PREDICTION_HISTORY = 500
MAX_PRELOAD_ITEMS = 20
ACCURACY_WINDOW = 50          # rolling window for accuracy calc
CONFIDENCE_THRESHOLD = 0.6
CONTEXT_SIMILARITY_THRESHOLD = 0.3


def _now() -> str:
    return datetime.now().isoformat()


def _timestamp() -> float:
    return time.time()


# ── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class TaskPattern:
    """A learned pattern of what memories are needed for a task type."""
    pattern_id: str
    task_type: str
    context_keywords: List[str] = field(default_factory=list)
    memory_tags_needed: List[str] = field(default_factory=list)
    confidence: float = 0.5
    use_count: int = 0
    success_count: int = 0
    created_at: str = ""
    last_used: str = ""

    def to_dict(self) -> dict:
        return {
            "pattern_id": self.pattern_id,
            "task_type": self.task_type,
            "context_keywords": self.context_keywords,
            "memory_tags_needed": self.memory_tags_needed,
            "confidence": round(self.confidence, 4),
            "use_count": self.use_count,
            "success_count": self.success_count,
            "created_at": self.created_at,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TaskPattern":
        return cls(
            pattern_id=d.get("pattern_id", ""),
            task_type=d.get("task_type", ""),
            context_keywords=d.get("context_keywords", []),
            memory_tags_needed=d.get("memory_tags_needed", []),
            confidence=d.get("confidence", 0.5),
            use_count=d.get("use_count", 0),
            success_count=d.get("success_count", 0),
            created_at=d.get("created_at", ""),
            last_used=d.get("last_used", ""),
        )


@dataclass
class PredictionRecord:
    """Record of a prediction and its outcome."""
    prediction_id: str
    context: str
    predicted_tags: List[str] = field(default_factory=list)
    was_useful: Optional[bool] = None
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "prediction_id": self.prediction_id,
            "context": self.context,
            "predicted_tags": self.predicted_tags,
            "was_useful": self.was_useful,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PredictionRecord":
        return cls(
            prediction_id=d.get("prediction_id", ""),
            context=d.get("context", ""),
            predicted_tags=d.get("predicted_tags", []),
            was_useful=d.get("was_useful"),
            timestamp=d.get("timestamp", ""),
        )


# ── Predictive Memory ───────────────────────────────────────────────────────

class PredictiveMemory:
    """
    Anticipatory memory system that predicts what memories will be needed.

    Learns task-type → memory-need associations over time, pre-loads
    relevant memories, and tracks prediction accuracy to self-improve.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self._task_patterns: Dict[str, TaskPattern] = {}
        self._prediction_history: List[PredictionRecord] = []
        self._preloaded: List[dict] = []
        self._session_predictions: int = 0
        self._session_hits: int = 0
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": _now(),
                "last_update": _now(),
                "total_predictions": 0,
                "total_hits": 0,
                "total_misses": 0,
            },
            "task_patterns": {},
            "prediction_history": [],
        }

    def _load(self):
        if not PREDICTIVE_FILE.exists():
            self._data = self._empty_store()
            self._save()
            return
        try:
            raw = PREDICTIVE_FILE.read_text(encoding="utf-8")
            self._data = json.loads(raw)
            for pid, pdata in self._data.get("task_patterns", {}).items():
                self._task_patterns[pid] = TaskPattern.from_dict(pdata)
            self._prediction_history = [
                PredictionRecord.from_dict(r)
                for r in self._data.get("prediction_history", [])
            ]
        except (json.JSONDecodeError, IOError):
            self._data = self._empty_store()
            self._save()

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._data["task_patterns"] = {
                pid: p.to_dict() for pid, p in self._task_patterns.items()
            }
            self._data["prediction_history"] = [
                r.to_dict() for r in self._prediction_history[-MAX_PREDICTION_HISTORY:]
            ]
            self._data["meta"]["last_update"] = _now()
            PREDICTIVE_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ── Learning ────────────────────────────────────────────────────────

    def learn_task_pattern(self, task_type: str, context_keywords: List[str],
                           memory_tags_needed: List[str]) -> str:
        """
        Learn or reinforce a task-type → memory-need pattern.

        Returns the pattern_id.
        """
        # Check if similar pattern exists
        existing = self._find_similar_pattern(task_type, context_keywords)
        if existing:
            existing.use_count += 1
            existing.memory_tags_needed = list(set(
                existing.memory_tags_needed + memory_tags_needed
            ))
            existing.context_keywords = list(set(
                existing.context_keywords + context_keywords
            ))
            existing.last_used = _now()
            self._save()
            return existing.pattern_id

        pattern_id = hashlib.md5(
            f"{task_type}:{_now()}".encode()
        ).hexdigest()[:12]

        pattern = TaskPattern(
            pattern_id=pattern_id,
            task_type=task_type,
            context_keywords=context_keywords,
            memory_tags_needed=memory_tags_needed,
            confidence=0.5,
            use_count=1,
            created_at=_now(),
            last_used=_now(),
        )

        with self._lock:
            self._task_patterns[pattern_id] = pattern
            # Enforce capacity
            if len(self._task_patterns) > MAX_TASK_PATTERNS:
                weakest = min(
                    self._task_patterns.values(),
                    key=lambda p: p.confidence * p.use_count,
                )
                del self._task_patterns[weakest.pattern_id]
            self._save()

        return pattern_id

    def _find_similar_pattern(self, task_type: str,
                               keywords: List[str]) -> Optional[TaskPattern]:
        """Find an existing pattern matching this task type and keywords."""
        best: Optional[TaskPattern] = None
        best_score = 0.0

        for pattern in self._task_patterns.values():
            score = 0.0
            if pattern.task_type == task_type:
                score += 0.5
            # Keyword overlap
            kw_overlap = set(k.lower() for k in keywords) & \
                         set(k.lower() for k in pattern.context_keywords)
            if kw_overlap:
                score += 0.5 * len(kw_overlap) / max(len(keywords), 1)
            if score > best_score and score >= CONTEXT_SIMILARITY_THRESHOLD:
                best_score = score
                best = pattern

        return best

    # ── Prediction ──────────────────────────────────────────────────────

    def predict_needed_context(self, current_context: str) -> List[dict]:
        """
        Predict what memory tags/context are likely needed soon.

        Args:
            current_context: Description of the current situation

        Returns:
            List of predictions: [{tags, confidence, source_pattern}]
        """
        context_lower = current_context.lower()
        context_words = set(context_lower.split())

        with self._lock:
            self._session_predictions += 1
            self._data["meta"]["total_predictions"] += 1

            predictions: List[dict] = []

            for pattern in self._task_patterns.values():
                # Match by keyword overlap
                kw_overlap = context_words & set(
                    k.lower() for k in pattern.context_keywords
                )
                if not kw_overlap:
                    continue

                match_score = len(kw_overlap) / max(len(context_words), 1)
                confidence = match_score * pattern.confidence

                if confidence >= CONTEXT_SIMILARITY_THRESHOLD:
                    predictions.append({
                        "tags": pattern.memory_tags_needed,
                        "confidence": round(confidence, 4),
                        "source_pattern": pattern.pattern_id,
                        "task_type": pattern.task_type,
                        "matched_keywords": list(kw_overlap),
                    })

            predictions.sort(key=lambda p: p["confidence"], reverse=True)

            # Record prediction
            pred_id = hashlib.md5(
                f"pred:{current_context}:{_now()}".encode()
            ).hexdigest()[:12]

            all_tags: List[str] = []
            for p in predictions[:3]:
                all_tags.extend(p["tags"])

            record = PredictionRecord(
                prediction_id=pred_id,
                context=current_context[:300],
                predicted_tags=list(set(all_tags)),
                timestamp=_now(),
            )
            self._prediction_history.append(record)
            if len(self._prediction_history) > MAX_PREDICTION_HISTORY:
                self._prediction_history = self._prediction_history[-MAX_PREDICTION_HISTORY:]

            self._save()
            return predictions

    def preload_predictions(self, task_type: str) -> List[dict]:
        """
        Pre-load relevant memory tags for a task type.

        Returns list of preloaded items (tags and keywords to fetch).
        """
        with self._lock:
            matching = [
                p for p in self._task_patterns.values()
                if p.task_type == task_type or
                   any(kw.lower() in task_type.lower()
                       for kw in p.context_keywords)
            ]

            if not matching:
                # Return generic suggestions
                return [{
                    "tags": [],
                    "keywords": task_type.split(),
                    "confidence": 0.1,
                    "source": "fallback",
                }]

            # Sort by confidence * use_count
            matching.sort(
                key=lambda p: p.confidence * p.use_count,
                reverse=True,
            )

            preloaded: List[dict] = []
            seen_tags: set = set()

            for pattern in matching[:5]:
                new_tags = [t for t in pattern.memory_tags_needed if t not in seen_tags]
                if not new_tags:
                    continue
                seen_tags.update(new_tags)
                preloaded.append({
                    "tags": new_tags,
                    "keywords": pattern.context_keywords,
                    "confidence": round(pattern.confidence, 4),
                    "source": pattern.pattern_id,
                    "use_count": pattern.use_count,
                })

            self._preloaded = preloaded
            self._save()
            return preloaded

    # ── Accuracy Tracking ───────────────────────────────────────────────

    def track_prediction_accuracy(self, was_useful: bool,
                                   prediction_id: Optional[str] = None):
        """
        Track whether a prediction was useful.

        Learns to improve future predictions by adjusting pattern confidence.
        """
        with self._lock:
            # Update the most recent prediction if no ID given
            target: Optional[PredictionRecord] = None
            if prediction_id:
                for rec in self._prediction_history:
                    if rec.prediction_id == prediction_id:
                        target = rec
                        break
            elif self._prediction_history:
                # Find the most recent untracked prediction
                for rec in reversed(self._prediction_history):
                    if rec.was_useful is None:
                        target = rec
                        break

            if target:
                target.was_useful = was_useful

            # Update global counters
            if was_useful:
                self._data["meta"]["total_hits"] += 1
                self._session_hits += 1
            else:
                self._data["meta"]["total_misses"] += 1

            # Update pattern confidences
            if target and target.predicted_tags:
                for pattern in self._task_patterns.values():
                    tag_overlap = set(target.predicted_tags) & set(pattern.memory_tags_needed)
                    if tag_overlap:
                        if was_useful:
                            pattern.confidence = min(1.0, pattern.confidence + 0.05)
                            pattern.success_count += 1
                        else:
                            pattern.confidence = max(0.1, pattern.confidence - 0.03)

            self._save()

    def get_prediction_confidence(self) -> dict:
        """
        Report how good predictions are overall.

        Returns accuracy metrics and confidence statistics.
        """
        with self._lock:
            # Rolling accuracy
            recent = [
                r for r in self._prediction_history[-ACCURACY_WINDOW:]
                if r.was_useful is not None
            ]
            if recent:
                hits = sum(1 for r in recent if r.was_useful)
                accuracy = hits / len(recent)
            else:
                accuracy = 0.0

            # Pattern confidence distribution
            if self._task_patterns:
                confidences = [p.confidence for p in self._task_patterns.values()]
                avg_confidence = sum(confidences) / len(confidences)
                max_confidence = max(confidences)
            else:
                avg_confidence = 0.0
                max_confidence = 0.0

            return {
                "accuracy": round(accuracy, 4),
                "recent_predictions": len(recent),
                "total_predictions": self._data["meta"].get("total_predictions", 0),
                "total_hits": self._data["meta"].get("total_hits", 0),
                "total_misses": self._data["meta"].get("total_misses", 0),
                "avg_pattern_confidence": round(avg_confidence, 4),
                "max_pattern_confidence": round(max_confidence, 4),
                "task_patterns_count": len(self._task_patterns),
                "session_predictions": self._session_predictions,
                "session_hits": self._session_hits,
            }

    # ── Query ───────────────────────────────────────────────────────────

    def get_task_patterns(self, task_type: Optional[str] = None) -> List[TaskPattern]:
        """Get task patterns, optionally filtered by type."""
        with self._lock:
            if task_type:
                return [
                    p for p in self._task_patterns.values()
                    if p.task_type == task_type
                ]
            return list(self._task_patterns.values())

    def get_recent_predictions(self, limit: int = 10) -> List[PredictionRecord]:
        """Get recent prediction history."""
        with self._lock:
            return list(self._prediction_history[-limit:])

    # ── Statistics ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get overall predictive memory statistics."""
        with self._lock:
            return {
                "task_patterns": len(self._task_patterns),
                "prediction_history_size": len(self._prediction_history),
                "total_predictions": self._data["meta"].get("total_predictions", 0),
                "total_hits": self._data["meta"].get("total_hits", 0),
                "total_misses": self._data["meta"].get("total_misses", 0),
                "preloaded_items": len(self._preloaded),
                "session_predictions": self._session_predictions,
                "session_hits": self._session_hits,
            }

    def format_for_prompt(self, max_chars: int = 500) -> str:
        """Format predictive memory state for system prompt injection."""
        stats = self.get_stats()
        confidence = self.get_prediction_confidence()
        parts = [
            "[PREDICTIVE MEMORY — Anticipatory recall]",
            f"Task patterns: {stats['task_patterns']} | "
            f"Predictions made: {stats['total_predictions']}",
            f"Accuracy: {confidence['accuracy']:.0%} | "
            f"Avg pattern confidence: {confidence['avg_pattern_confidence']:.2f}",
        ]
        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "[...]"
        return result


# ── Singleton ───────────────────────────────────────────────────────────────

_predictive_memory = None
_predictive_lock = threading.Lock()


def get_predictive_memory() -> PredictiveMemory:
    """Get singleton PredictiveMemory instance."""
    global _predictive_memory
    if _predictive_memory is None:
        with _predictive_lock:
            if _predictive_memory is None:
                _predictive_memory = PredictiveMemory()
    return _predictive_memory
