#!/usr/bin/env python3
"""
metacognitive_monitor.py — FRIDAY Metacognitive Monitoring System
===================================================================

Continuous self-monitoring that watches the cognitive process itself.
FRIDAY doesn't just think — she watches herself think, detects when
her thinking is going wrong, and adjusts strategies accordingly.

Research foundations:

  [MM-1] Flavell's Metacognition (1979)
         — Metacognition = knowledge about cognition + regulation of cognition.
           "Thinking about thinking" — monitoring comprehension, strategy
           effectiveness, and one's own cognitive state.

  [MM-2] Nelson & Narens' Metamemory Framework (1990)
         — Monitoring: JOL (Judgments of Learning), confidence calibration
           Control: allocation of study time, strategy selection
           The monitoring→control loop drives adaptive cognition.

  [MM-3] Cognitive Load Theory (Sweller, 1988)
         — Working memory has limited capacity. When cognitive load is high,
           performance degrades. Monitor must detect overload and recommend
           offloading or strategy changes.

  [MM-4] Confidence Calibration (Kahneman, 2011; Lichtenstein et al., 1982)
         — Well-calibrated confidence = predicted confidence matches actual
           accuracy. Miscalibration (over/under-confidence) is common and
           must be detected and corrected.

  [MM-5] Error Pattern Detection (Reason, 1990)
         — Human Error: systematic error patterns (slips, lapses, mistakes)
           Recurring errors reveal cognitive biases or strategy failures.

Key behaviors:
  - Track cognitive load from active modules
  - Calibrate confidence predictions against actual outcomes
  - Detect recurring error patterns
  - Suggest optimal cognitive strategies per task type
  - Monitor attention allocation across modules
  - Detect cognitive fatigue from performance degradation
"""

import json
import math
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


BRAIN_DIR = Path(__file__).parent.resolve()
METACOGNITIVE_FILE = BRAIN_DIR / "metacognitive_data.json"

# ── Configuration ───────────────────────────────────────────────────────────

# Cognitive load
MAX_CONCURRENT_MODULES = 8       # working memory capacity estimate
LOAD_LOW = 0.3
LOAD_MEDIUM = 0.6
LOAD_HIGH = 0.8
LOAD_CRITICAL = 0.95

# Confidence calibration
CALIBRATION_WINDOW = 100         # recent predictions for calibration
CALIBRATION_BINS = 10            # bins for calibration curve (0.0-0.1, 0.1-0.2, ...)
OVERCONFIDENCE_THRESHOLD = 0.15  # avg predicted - actual > this = overconfident
UNDERCONFIDENCE_THRESHOLD = -0.15

# Error pattern detection
ERROR_WINDOW = 200               # recent errors to analyze
MIN_PATTERN_OCCURRENCES = 3      # minimum repeats to count as pattern
ERROR_SIMILARITY_THRESHOLD = 0.7

# Strategy effectiveness
STRATEGY_WINDOW = 50             # recent strategy uses per task type
MIN_STRATEGY_USES = 5            # minimum uses before recommending

# Attention tracking
ATTENTION_WINDOW = 60.0          # seconds of recent activity
ATTENTION_DECAY = 0.9            # per-second decay of attention scores

# Fatigue detection
FATIGUE_WINDOW = 30              # recent operations to check
FATIGUE_DEGRADATION_THRESHOLD = 0.2  # performance drop = fatigued
FATIGUE_MIN_OPERATIONS = 10

# Persistence
MAX_LOG_ENTRIES = 500
MAX_CALIBRATION_ENTRIES = 1000
MAX_ERROR_ENTRIES = 500


def _now() -> str:
    return datetime.now().isoformat()


def _timestamp() -> float:
    return time.time()


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-max(-10, min(10, x))))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


# ── Data Structures ─────────────────────────────────────────────────────────

class CognitiveLoadState:
    """Snapshot of current cognitive load."""

    __slots__ = [
        "timestamp", "active_modules", "load_level", "load_score",
        "working_memory_pressure", "recommendation",
    ]

    def __init__(self, active_modules: int, load_score: float,
                 recommendation: str = ""):
        self.timestamp = _now()
        self.active_modules = active_modules
        self.load_score = round(load_score, 3)
        self.working_memory_pressure = round(
            active_modules / MAX_CONCURRENT_MODULES, 3
        )
        if load_score >= LOAD_CRITICAL:
            self.load_level = "critical"
        elif load_score >= LOAD_HIGH:
            self.load_level = "high"
        elif load_score >= LOAD_MEDIUM:
            self.load_level = "medium"
        elif load_score >= LOAD_LOW:
            self.load_level = "low"
        else:
            self.load_level = "minimal"
        self.recommendation = recommendation

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "active_modules": self.active_modules,
            "load_level": self.load_level,
            "load_score": self.load_score,
            "working_memory_pressure": self.working_memory_pressure,
            "recommendation": self.recommendation,
        }


class ErrorPattern:
    """A detected recurring error pattern."""

    __slots__ = [
        "pattern_id", "description", "occurrences", "first_seen",
        "last_seen", "error_type", "contexts", "suggested_fix",
    ]

    def __init__(self, pattern_id: str, description: str,
                 error_type: str = "unknown"):
        self.pattern_id = pattern_id
        self.description = description
        self.occurrences = 0
        self.first_seen = _now()
        self.last_seen = _now()
        self.error_type = error_type
        self.contexts: List[str] = []
        self.suggested_fix: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "pattern_id": self.pattern_id,
            "description": self.description,
            "occurrences": self.occurrences,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "error_type": self.error_type,
            "contexts": self.contexts[-10:],
            "suggested_fix": self.suggested_fix,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ErrorPattern":
        ep = cls(
            pattern_id=d.get("pattern_id", ""),
            description=d.get("description", ""),
            error_type=d.get("error_type", "unknown"),
        )
        ep.occurrences = d.get("occurrences", 0)
        ep.first_seen = d.get("first_seen", _now())
        ep.last_seen = d.get("last_seen", _now())
        ep.contexts = d.get("contexts", [])
        ep.suggested_fix = d.get("suggested_fix")
        return ep


class StrategyRecord:
    """Tracks effectiveness of a cognitive strategy for a task type."""

    __slots__ = [
        "task_type", "strategy_name", "uses", "successes",
        "avg_confidence", "avg_duration_s", "last_used",
    ]

    def __init__(self, task_type: str, strategy_name: str):
        self.task_type = task_type
        self.strategy_name = strategy_name
        self.uses = 0
        self.successes = 0
        self.avg_confidence = 0.5
        self.avg_duration_s = 0.0
        self.last_used = _now()

    @property
    def success_rate(self) -> float:
        return self.successes / max(self.uses, 1)

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "strategy_name": self.strategy_name,
            "uses": self.uses,
            "successes": self.successes,
            "success_rate": round(self.success_rate, 3),
            "avg_confidence": round(self.avg_confidence, 3),
            "avg_duration_s": round(self.avg_duration_s, 2),
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyRecord":
        sr = cls(
            task_type=d.get("task_type", "general"),
            strategy_name=d.get("strategy_name", "default"),
        )
        sr.uses = d.get("uses", 0)
        sr.successes = d.get("successes", 0)
        sr.avg_confidence = d.get("avg_confidence", 0.5)
        sr.avg_duration_s = d.get("avg_duration_s", 0.0)
        sr.last_used = d.get("last_used", _now())
        return sr


# ── Metacognitive Monitor ───────────────────────────────────────────────────

class MetacognitiveMonitor:
    """
    Watches FRIDAY's own cognitive processes and provides meta-level guidance.

    Monitors:
    - Cognitive load (how many modules active, working memory pressure)
    - Confidence calibration (predicted vs actual accuracy)
    - Strategy effectiveness (what works for what tasks)
    - Error patterns (recurring mistakes)
    - Attention allocation (what's consuming resources)
    - Cognitive fatigue (performance degradation over time)
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self._active_modules: Dict[str, float] = {}  # module → activation time
        self._calibration_entries: List[dict] = []
        self._error_log: List[dict] = []
        self._error_patterns: Dict[str, ErrorPattern] = {}
        self._strategies: Dict[str, StrategyRecord] = {}
        self._performance_log: deque = deque(maxlen=FATIGUE_WINDOW * 2)
        self._attention_scores: Dict[str, float] = {}
        self._session_ops = 0
        self._session_start = _timestamp()
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": _now(),
                "last_update": _now(),
                "total_calibrations": 0,
                "total_errors_logged": 0,
                "total_strategy_records": 0,
            },
            "calibration_entries": [],
            "error_log": [],
            "error_patterns": {},
            "strategies": {},
            "load_history": [],
            "fatigue_history": [],
        }

    def _load(self):
        if not METACOGNITIVE_FILE.exists():
            self._data = self._empty_store()
            self._save()
            return
        try:
            raw = METACOGNITIVE_FILE.read_text(encoding="utf-8")
            self._data = json.loads(raw)
            self._calibration_entries = self._data.get("calibration_entries", [])
            self._error_log = self._data.get("error_log", [])
            for pid, pd in self._data.get("error_patterns", {}).items():
                self._error_patterns[pid] = ErrorPattern.from_dict(pd)
            for key, sd in self._data.get("strategies", {}).items():
                self._strategies[key] = StrategyRecord.from_dict(sd)
        except (json.JSONDecodeError, IOError):
            self._data = self._empty_store()
            self._save()

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._data["calibration_entries"] = self._calibration_entries[-MAX_CALIBRATION_ENTRIES:]
            self._data["error_log"] = self._error_log[-MAX_ERROR_ENTRIES:]
            self._data["error_patterns"] = {
                pid: ep.to_dict() for pid, ep in self._error_patterns.items()
            }
            self._data["strategies"] = {
                key: sr.to_dict() for key, sr in self._strategies.items()
            }
            self._data["meta"]["last_update"] = _now()
            METACOGNITIVE_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ── Module Registration ─────────────────────────────────────────────

    def register_module_active(self, module_name: str):
        """Register a module as currently active (consuming cognitive resources)."""
        with self._lock:
            self._active_modules[module_name] = _timestamp()
            self._attention_scores[module_name] = self._attention_scores.get(
                module_name, 0.0
            ) + 1.0

    def register_module_idle(self, module_name: str):
        """Register a module as no longer active."""
        with self._lock:
            self._active_modules.pop(module_name, None)

    # ── Cognitive Load ──────────────────────────────────────────────────

    def check_cognitive_load(self, extra_modules: int = 0) -> CognitiveLoadState:
        """
        Assess current cognitive load and provide recommendations.

        Based on Cognitive Load Theory (Sweller, 1988):
        - Intrinsic load: complexity of the task itself
        - Extraneous load: unnecessary processing overhead
        - Germane load: productive learning/processing

        Returns a CognitiveLoadState with level and recommendation.
        """
        with self._lock:
            active = len(self._active_modules) + extra_modules
            # Load score considers both count and recency
            now = _timestamp()
            recent_modules = sum(
                1 for t in self._active_modules.values()
                if now - t < 5.0  # active in last 5 seconds
            )
            load_score = recent_modules / MAX_CONCURRENT_MODULES
            load_score = min(1.0, load_score)

            recommendation = ""
            if load_score >= LOAD_CRITICAL:
                recommendation = (
                    "CRITICAL: Cognitive overload. Prioritize essential modules only. "
                    "Defer non-critical processing. Consider simplifying the task."
                )
            elif load_score >= LOAD_HIGH:
                recommendation = (
                    "HIGH load: Consider offloading to simpler strategies. "
                    "Batch similar operations. Reduce context switching."
                )
            elif load_score >= LOAD_MEDIUM:
                recommendation = (
                    "MEDIUM load: Operating near capacity. "
                    "Monitor for degradation. Prioritize by importance."
                )
            elif load_score >= LOAD_LOW:
                recommendation = "LOW load: Comfortable operating range. All options available."
            else:
                recommendation = "MINIMAL load: Idle capacity available for complex tasks."

            state = CognitiveLoadState(
                active_modules=recent_modules,
                load_score=load_score,
                recommendation=recommendation,
            )

            # Store in history
            history = self._data.get("load_history", [])
            history.append(state.to_dict())
            self._data["load_history"] = history[-100:]

            return state

    # ── Confidence Calibration ──────────────────────────────────────────

    def calibrate_confidence(self, predicted: float, actual: float,
                              context: str = ""):
        """
        Record a (predicted_confidence, actual_outcome) pair for calibration.

        Based on Lichtenstein et al. (1982) calibration paradigm:
        - Overconfident: consistently predict higher than actual
        - Underconfident: consistently predict lower than actual
        - Well-calibrated: predictions match reality
        """
        entry = {
            "timestamp": _now(),
            "predicted": round(predicted, 4),
            "actual": round(actual, 4),
            "error": round(predicted - actual, 4),
            "context": context[:200],
        }

        with self._lock:
            self._calibration_entries.append(entry)
            if len(self._calibration_entries) > MAX_CALIBRATION_ENTRIES:
                self._calibration_entries = self._calibration_entries[-MAX_CALIBRATION_ENTRIES:]
            self._data["meta"]["total_calibrations"] += 1
            self._save()

    def get_calibration_report(self) -> dict:
        """
        Analyze confidence calibration over recent predictions.

        Returns:
        - bias: positive = overconfident, negative = underconfident
        - calibration_curve: accuracy per confidence bin
        - brier_score: overall calibration quality (lower = better)
        """
        with self._lock:
            entries = self._calibration_entries[-CALIBRATION_WINDOW:]
            if not entries:
                return {
                    "bias": 0.0,
                    "calibration_quality": "insufficient_data",
                    "sample_size": 0,
                }

            errors = [e["error"] for e in entries]
            avg_bias = sum(errors) / len(errors)

            # Brier score (mean squared error)
            brier = sum(e["error"] ** 2 for e in entries) / len(entries)

            # Calibration curve: bin predictions and check accuracy
            bins: Dict[int, List[float]] = defaultdict(list)
            for e in entries:
                bin_idx = min(CALIBRATION_BINS - 1, int(e["predicted"] * CALIBRATION_BINS))
                bins[bin_idx].append(e["actual"])

            curve = {}
            for bin_idx in range(CALIBRATION_BINS):
                if bin_idx in bins:
                    vals = bins[bin_idx]
                    pred_center = (bin_idx + 0.5) / CALIBRATION_BINS
                    avg_actual = sum(vals) / len(vals)
                    curve[f"{bin_idx/CALIBRATION_BINS:.1f}-{(bin_idx+1)/CALIBRATION_BINS:.1f}"] = {
                        "predicted_center": round(pred_center, 2),
                        "actual_avg": round(avg_actual, 3),
                        "count": len(vals),
                        "gap": round(pred_center - avg_actual, 3),
                    }

            if avg_bias > OVERCONFIDENCE_THRESHOLD:
                quality = "overconfident"
            elif avg_bias < UNDERCONFIDENCE_THRESHOLD:
                quality = "underconfident"
            elif brier < 0.05:
                quality = "well_calibrated"
            else:
                quality = "moderate"

            return {
                "bias": round(avg_bias, 4),
                "brier_score": round(brier, 4),
                "calibration_quality": quality,
                "sample_size": len(entries),
                "calibration_curve": curve,
            }

    def adjust_confidence(self, raw_confidence: float) -> float:
        """
        Adjust a raw confidence estimate based on calibration history.

        If historically overconfident, reduce confidence.
        If underconfident, increase it.
        """
        report = self.get_calibration_report()
        bias = report.get("bias", 0.0)
        adjusted = raw_confidence - bias * 0.5  # partial correction
        return round(max(0.0, min(1.0, adjusted)), 4)

    # ── Strategy Effectiveness ──────────────────────────────────────────

    def record_strategy_use(self, task_type: str, strategy_name: str,
                            success: bool, confidence: float = 0.5,
                            duration_s: float = 0.0):
        """Record the use and outcome of a cognitive strategy."""
        key = f"{task_type}:{strategy_name}"
        with self._lock:
            if key not in self._strategies:
                self._strategies[key] = StrategyRecord(task_type, strategy_name)
            sr = self._strategies[key]
            sr.uses += 1
            if success:
                sr.successes += 1
            # Exponential moving average for confidence and duration
            lr = 1.0 / max(sr.uses, 5)
            sr.avg_confidence = sr.avg_confidence * (1 - lr) + confidence * lr
            sr.avg_duration_s = sr.avg_duration_s * (1 - lr) + duration_s * lr
            sr.last_used = _now()
            self._save()

    def suggest_strategy(self, task_type: str,
                         available_strategies: Optional[List[str]] = None) -> str:
        """
        Suggest the best cognitive strategy for a task type.

        Based on historical success rates, confidence, and speed.
        Returns strategy name.
        """
        with self._lock:
            candidates = []
            for key, sr in self._strategies.items():
                if sr.task_type == task_type:
                    if available_strategies and sr.strategy_name not in available_strategies:
                        continue
                    if sr.uses >= MIN_STRATEGY_USES:
                        # Score: success_rate * confidence * recency_bonus
                        try:
                            last = datetime.fromisoformat(sr.last_used)
                            recency = max(0.5, 1.0 - (datetime.now() - last).days / 30.0)
                        except (ValueError, TypeError):
                            recency = 0.5
                        score = sr.success_rate * sr.avg_confidence * recency
                        candidates.append((sr.strategy_name, score, sr))

            if candidates:
                candidates.sort(key=lambda x: x[1], reverse=True)
                return candidates[0][0]

            # Fallback: check general strategies
            for key, sr in self._strategies.items():
                if sr.task_type == "general" and sr.uses >= MIN_STRATEGY_USES:
                    return sr.strategy_name

            return "default"

    def get_strategy_report(self) -> List[dict]:
        """Get effectiveness report for all tracked strategies."""
        with self._lock:
            return [sr.to_dict() for sr in self._strategies.values()]

    # ── Error Pattern Detection ─────────────────────────────────────────

    def log_error(self, error_type: str, description: str,
                  context: str = ""):
        """
        Log an error for pattern detection.

        Error types: "reasoning", "factual", "strategic", "execution",
                     "bias", "omission", "commission"
        """
        entry = {
            "timestamp": _now(),
            "error_type": error_type,
            "description": description[:300],
            "context": context[:200],
        }

        with self._lock:
            self._error_log.append(entry)
            if len(self._error_log) > MAX_ERROR_ENTRIES:
                self._error_log = self._error_log[-MAX_ERROR_ENTRIES:]
            self._data["meta"]["total_errors_logged"] += 1

            # Check for pattern formation
            self._detect_patterns(error_type, description, context)
            self._save()

    def _detect_patterns(self, error_type: str, description: str, context: str):
        """Check if this error matches an existing pattern or forms a new one."""
        # Simple pattern matching: group by error_type and look for repeated descriptions
        desc_key = f"{error_type}:{description[:80]}"

        if desc_key in self._error_patterns:
            ep = self._error_patterns[desc_key]
            ep.occurrences += 1
            ep.last_seen = _now()
            if context and context not in ep.contexts:
                ep.contexts.append(context)
        else:
            ep = ErrorPattern(
                pattern_id=desc_key,
                description=f"[{error_type}] {description[:200]}",
                error_type=error_type,
            )
            ep.occurrences = 1
            if context:
                ep.contexts.append(context)
            self._error_patterns[desc_key] = ep

    def detect_error_patterns(self, min_occurrences: int = MIN_PATTERN_OCCURRENCES) -> List[dict]:
        """
        Detect recurring error patterns from error history.

        Returns patterns that have occurred >= min_occurrences times,
        sorted by frequency.
        """
        with self._lock:
            patterns = [
                ep.to_dict() for ep in self._error_patterns.values()
                if ep.occurrences >= min_occurrences
            ]
            patterns.sort(key=lambda p: p["occurrences"], reverse=True)
            return patterns

    def suggest_fix_for_pattern(self, pattern_id: str) -> Optional[str]:
        """Get or generate a suggested fix for an error pattern."""
        with self._lock:
            ep = self._error_patterns.get(pattern_id)
            if not ep:
                return None
            if ep.suggested_fix:
                return ep.suggested_fix

            # Generate basic fix suggestions based on error type
            fixes = {
                "reasoning": "Add explicit logical verification step before concluding.",
                "factual": "Cross-reference with multiple sources before stating facts.",
                "strategic": "Consider alternative approaches; use deliberative reasoning.",
                "execution": "Add pre-execution validation and post-execution checks.",
                "bias": "Actively seek disconfirming evidence before deciding.",
                "omission": "Use systematic checklist to ensure completeness.",
                "commission": "Verify necessity before taking action; prefer inaction when uncertain.",
            }
            fix = fixes.get(ep.error_type, "Review this error pattern and develop targeted mitigation.")
            ep.suggested_fix = fix
            return fix

    # ── Attention Tracking ──────────────────────────────────────────────

    def track_attention(self, module_name: str, weight: float = 1.0):
        """Record attention being directed to a module."""
        with self._lock:
            current = self._attention_scores.get(module_name, 0.0)
            self._attention_scores[module_name] = current + weight

    def get_attention_report(self) -> dict:
        """
        Report what's consuming cognitive resources right now.

        Returns attention distribution across modules.
        """
        with self._lock:
            now = _timestamp()

            # Decay attention scores
            for module in list(self._attention_scores.keys()):
                self._attention_scores[module] *= ATTENTION_DECAY
                if self._attention_scores[module] < 0.01:
                    del self._attention_scores[module]

            # Active modules
            active = {
                m: round(now - t, 1)
                for m, t in self._active_modules.items()
            }

            # Attention distribution
            total = sum(self._attention_scores.values()) or 1.0
            distribution = {
                m: round(score / total, 3)
                for m, score in sorted(
                    self._attention_scores.items(),
                    key=lambda x: x[1], reverse=True
                )
            }

            return {
                "active_modules": active,
                "active_count": len(active),
                "attention_distribution": distribution,
                "top_consumer": max(distribution, key=distribution.get) if distribution else None,
                "timestamp": _now(),
            }

    # ── Cognitive Fatigue ───────────────────────────────────────────────

    def record_performance(self, success: bool, confidence: float = 0.5):
        """Record a performance data point for fatigue detection."""
        with self._lock:
            self._performance_log.append({
                "timestamp": _timestamp(),
                "success": success,
                "confidence": confidence,
            })
            self._session_ops += 1

    def detect_fatigue(self) -> dict:
        """
        Detect cognitive fatigue from performance degradation patterns.

        Based on monitoring for:
        - Declining success rate over time
        - Decreasing confidence
        - Increasing error frequency
        - Time-on-task effects
        """
        with self._lock:
            if len(self._performance_log) < FATIGUE_MIN_OPERATIONS:
                return {
                    "fatigued": False,
                    "confidence": 0.0,
                    "reason": "insufficient_data",
                }

            entries = list(self._performance_log)
            midpoint = len(entries) // 2
            first_half = entries[:midpoint]
            second_half = entries[midpoint:]

            # Success rate comparison
            early_success = sum(1 for e in first_half if e["success"]) / max(len(first_half), 1)
            late_success = sum(1 for e in second_half if e["success"]) / max(len(second_half), 1)
            success_drop = early_success - late_success

            # Confidence comparison
            early_conf = sum(e["confidence"] for e in first_half) / max(len(first_half), 1)
            late_conf = sum(e["confidence"] for e in second_half) / max(len(second_half), 1)
            conf_drop = early_conf - late_conf

            # Session duration
            session_duration_min = (_timestamp() - self._session_start) / 60.0

            # Fatigue signals
            signals = []
            if success_drop > FATIGUE_DEGRADATION_THRESHOLD:
                signals.append(f"success_rate_drop={success_drop:.2f}")
            if conf_drop > FATIGUE_DEGRADATION_THRESHOLD:
                signals.append(f"confidence_drop={conf_drop:.2f}")
            if session_duration_min > 60:
                signals.append(f"long_session={session_duration_min:.0f}min")

            is_fatigued = len(signals) >= 2 or success_drop > 0.3
            fatigue_confidence = min(1.0, len(signals) * 0.35) if signals else 0.0

            return {
                "fatigued": is_fatigued,
                "confidence": round(fatigue_confidence, 3),
                "signals": signals,
                "success_rate_early": round(early_success, 3),
                "success_rate_late": round(late_success, 3),
                "confidence_early": round(early_conf, 3),
                "confidence_late": round(late_conf, 3),
                "session_duration_min": round(session_duration_min, 1),
                "recommendation": (
                    "Consider simplifying tasks or taking a break."
                    if is_fatigued else "Performance stable."
                ),
            }

    # ── Comprehensive Report ────────────────────────────────────────────

    def get_metacognitive_report(self) -> dict:
        """
        Generate a comprehensive metacognitive status report.

        Combines all monitoring subsystems into one overview.
        """
        load = self.check_cognitive_load()
        calibration = self.get_calibration_report()
        errors = self.detect_error_patterns()
        attention = self.get_attention_report()
        fatigue = self.detect_fatigue()
        strategies = self.get_strategy_report()

        return {
            "timestamp": _now(),
            "cognitive_load": load.to_dict(),
            "calibration": calibration,
            "error_patterns_count": len(errors),
            "top_error_patterns": errors[:5],
            "attention": attention,
            "fatigue": fatigue,
            "strategies_tracked": len(strategies),
            "session_operations": self._session_ops,
        }

    def format_for_prompt(self, max_chars: int = 600) -> str:
        """Format metacognitive awareness for system prompt injection."""
        load = self.check_cognitive_load()
        cal = self.get_calibration_report()
        fatigue = self.detect_fatigue()
        attention = self.get_attention_report()
        errors = self.detect_error_patterns()

        parts = [
            "[METACOGNITIVE MONITOR — Self-awareness]",
            f"Cognitive load: {load.load_level} ({load.load_score:.0%})",
        ]

        if cal.get("sample_size", 0) > 5:
            parts.append(
                f"Confidence calibration: {cal['calibration_quality']} "
                f"(bias={cal['bias']:+.3f})"
            )

        if fatigue.get("fatigued"):
            parts.append(f"⚠ Fatigue detected: {', '.join(fatigue.get('signals', []))}")

        if attention.get("top_consumer"):
            parts.append(f"Top attention: {attention['top_consumer']}")

        if errors:
            parts.append(f"Recurring errors: {len(errors)} patterns detected")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "[...]"
        return result

    # ── Maintenance ─────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get overall metacognitive monitor statistics."""
        with self._lock:
            return {
                "session_ops": self._session_ops,
                "session_start": self._session_start,
                "calibration_entries": len(self._calibration_entries),
                "error_log_size": len(self._error_log),
                "error_patterns": len(self._error_patterns),
                "strategies": len(self._strategies),
                "active_modules": len(self._active_modules),
                "attention_modules": len(self._attention_scores),
                "total_calibrations": self._data.get("meta", {}).get("total_calibrations", 0),
                "total_errors_logged": self._data.get("meta", {}).get("total_errors_logged", 0),
                "total_strategy_records": self._data.get("meta", {}).get("total_strategy_records", 0),
            }

    def cleanup_old_data(self, days: int = 30):
        """Remove data older than specified days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._lock:
            self._calibration_entries = [
                e for e in self._calibration_entries
                if e.get("timestamp", "") > cutoff
            ]
            self._error_log = [
                e for e in self._error_log
                if e.get("timestamp", "") > cutoff
            ]
            self._save()


# ── Singleton ───────────────────────────────────────────────────────────────

_metacognitive_monitor = None
_metacognitive_lock = threading.Lock()


def get_metacognitive_monitor() -> MetacognitiveMonitor:
    """Get singleton MetacognitiveMonitor instance."""
    global _metacognitive_monitor
    if _metacognitive_monitor is None:
        with _metacognitive_lock:
            if _metacognitive_monitor is None:
                _metacognitive_monitor = MetacognitiveMonitor()
    return _metacognitive_monitor
