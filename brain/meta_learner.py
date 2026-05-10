# -*- coding: utf-8 -*-
"""
meta_learner.py — FRIDAY Meta-Learning System
===============================================

"Learning to learn" — FRIDAY adapts her own learning strategies based on
experience. This module sits above the learning engine and active inference,
tuning their parameters and selecting strategies automatically.

Components:
- LearningRateAdapter: adapts per-domain learning rates based on accuracy trends
- StrategySelector: picks the best learning strategy for each task type
- ExplorationScheduler: tunes exploration vs exploitation per domain
- MetaCognitiveLoop: reflects on the learning process itself
- AntiCatastrophicForgetting: protects important Q-values from being overwritten
- meta_reflect(): full meta-learning reflection session

Integrations:
- brain.learning: adjusts Q-learning rate and exploration rate
- brain.active_inference: adjusts prediction model learning rates
- brain.self_improve_engine: meta-lessons feed into improvement cycle
"""

import json
import math
import threading
import time
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict, deque

BRAIN_DIR = Path(__file__).parent.resolve()
META_DATA_FILE = BRAIN_DIR / "meta_learning_data.json"

# ─── Configuration ───────────────────────────────────────────────────────────

ACCURACY_WINDOW       = 50       # Sliding window size for accuracy tracking
LR_MIN                = 0.01     # Minimum learning rate
LR_MAX                = 0.8      # Maximum learning rate
LR_DEFAULT            = 0.3      # Default learning rate
LR_ADAPT_SPEED        = 0.05     # How aggressively to adjust LR

EXPLORATION_MIN       = 0.01     # Minimum exploration rate
EXPLORATION_MAX       = 0.5      # Maximum exploration rate
EXPLORATION_DEFAULT   = 0.1      # Default exploration rate
EXPLORATION_DECAY     = 0.995    # Multiplicative decay per reflection

META_REFLECT_INTERVAL = 1800     # Seconds between meta-reflections
REHEARSAL_BATCH_SIZE  = 20       # Q-values to rehearse per idle cycle
REHEARSAL_INTERVAL    = 600      # Seconds between rehearsal cycles

STRATEGIES = ["q_learning", "error_driven", "trial_and_error", "imitation", "reasoning"]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().isoformat()


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


# ─── 1. LearningRateAdapter ─────────────────────────────────────────────────

class LearningRateAdapter:
    """
    Adapts learning rate per domain based on prediction accuracy trends.

    - Tracks accuracy over a sliding window per domain
    - If accuracy is improving → decrease LR (fine-tuning phase)
    - If accuracy is declining → increase LR (need faster adaptation)
    - If accuracy is stable  → maintain current LR
    """

    def __init__(self):
        self._lock = threading.RLock()
        # domain → deque of (timestamp, accuracy) pairs
        self._accuracy_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=ACCURACY_WINDOW)
        )
        # domain → current learning rate
        self._learning_rates: Dict[str, float] = {}

    def record_accuracy(self, domain: str, accuracy: float):
        """Record an accuracy observation for a domain (0.0 to 1.0)."""
        with self._lock:
            accuracy = _clamp(accuracy, 0.0, 1.0)
            self._accuracy_history[domain].append(
                (time.time(), round(accuracy, 4))
            )
            self._adapt_learning_rate(domain)

    def _compute_trend(self, domain: str) -> float:
        """
        Compute accuracy trend over the sliding window.
        Returns positive if improving, negative if declining, near zero if stable.
        Uses simple linear regression slope.
        """
        history = list(self._accuracy_history.get(domain, []))
        if len(history) < 5:
            return 0.0  # Not enough data

        values = [h[1] for h in history]
        n = len(values)
        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n

        num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        den = sum((i - x_mean) ** 2 for i in range(n))

        if den == 0:
            return 0.0
        slope = num / den
        return round(slope, 6)

    def _adapt_learning_rate(self, domain: str):
        """Adjust learning rate based on accuracy trend."""
        trend = self._compute_trend(domain)
        current_lr = self._learning_rates.get(domain, LR_DEFAULT)

        if trend > 0.005:
            # Accuracy improving → decrease LR (fine-tuning)
            new_lr = current_lr - LR_ADAPT_SPEED * abs(trend) * 10
        elif trend < -0.005:
            # Accuracy declining → increase LR (need to adapt faster)
            new_lr = current_lr + LR_ADAPT_SPEED * abs(trend) * 10
        else:
            # Stable → maintain
            new_lr = current_lr

        self._learning_rates[domain] = round(_clamp(new_lr, LR_MIN, LR_MAX), 4)

    def get_learning_rate(self, domain: str) -> float:
        """Get the current adapted learning rate for a domain."""
        with self._lock:
            return self._learning_rates.get(domain, LR_DEFAULT)

    def set_learning_rate(self, domain: str, lr: float):
        """Manually set a learning rate for a domain."""
        with self._lock:
            self._learning_rates[domain] = round(_clamp(lr, LR_MIN, LR_MAX), 4)

    def get_accuracy_trend(self, domain: str) -> Dict[str, Any]:
        """Get accuracy trend info for a domain."""
        with self._lock:
            history = list(self._accuracy_history.get(domain, []))
            if not history:
                return {"domain": domain, "trend": 0.0, "samples": 0, "current_lr": LR_DEFAULT}
            trend = self._compute_trend(domain)
            recent_acc = history[-1][1] if history else 0.0
            avg_acc = sum(h[1] for h in history) / len(history)
            return {
                "domain": domain,
                "trend": trend,
                "recent_accuracy": round(recent_acc, 4),
                "average_accuracy": round(avg_acc, 4),
                "samples": len(history),
                "current_lr": self._learning_rates.get(domain, LR_DEFAULT),
            }

    def get_all_domains(self) -> List[str]:
        """List all tracked domains."""
        with self._lock:
            domains = set(self._accuracy_history.keys())
            domains.update(self._learning_rates.keys())
            return sorted(domains)

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "learning_rates": dict(self._learning_rates),
                "accuracy_history": {
                    d: list(h)[-20:]  # persist last 20 per domain
                    for d, h in self._accuracy_history.items()
                },
            }

    def from_dict(self, data: dict):
        with self._lock:
            self._learning_rates = data.get("learning_rates", {})
            for d, entries in data.get("accuracy_history", {}).items():
                for ts, acc in entries:
                    self._accuracy_history[d].append((ts, acc))


# ─── 2. StrategySelector ────────────────────────────────────────────────────

class StrategySelector:
    """
    Chooses the best learning strategy for each task type.

    Strategies:
    - q_learning: value-based reinforcement learning
    - error_driven: learn from prediction errors
    - trial_and_error: random exploration with outcome tracking
    - imitation: copy successful patterns from similar tasks
    - reasoning: explicit logical deduction

    Tracks success rate of each strategy per task type and selects
    the one with the best historical performance.
    """

    def __init__(self):
        self._lock = threading.RLock()
        # task_type → {strategy → {"successes": int, "attempts": int, "avg_quality": float}}
        self._strategy_scores: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(
            lambda: {s: {"successes": 0, "attempts": 0, "avg_quality": 0.5} for s in STRATEGIES}
        )
        # task_type → currently selected strategy
        self._current_strategy: Dict[str, str] = {}
        # EMA smoothing for quality updates
        self._ema_alpha = 0.3

    def record_outcome(self, task_type: str, strategy: str, success: bool,
                       quality: float = 0.5):
        """Record the outcome of using a strategy on a task type."""
        with self._lock:
            if strategy not in STRATEGIES:
                strategy = "q_learning"  # fallback
            scores = self._strategy_scores[task_type][strategy]
            scores["attempts"] += 1
            if success:
                scores["successes"] += 1
            # Update EMA of quality
            scores["avg_quality"] = round(
                self._ema_alpha * quality + (1 - self._ema_alpha) * scores["avg_quality"], 4
            )

    def select_strategy(self, task_type: str) -> str:
        """Select the best strategy for a task type based on past performance."""
        with self._lock:
            scores = self._strategy_scores.get(task_type)
            if not scores:
                # No data → explore randomly
                choice = random.choice(STRATEGIES)
                self._current_strategy[task_type] = choice
                return choice

            # Compute expected value for each strategy
            best_strategy = None
            best_score = -1.0

            for strat, stats in scores.items():
                attempts = stats["attempts"]
                if attempts == 0:
                    # Untried strategies get a bonus (exploration)
                    ev = 0.6 + random.uniform(0, 0.2)
                else:
                    success_rate = stats["successes"] / attempts
                    quality = stats["avg_quality"]
                    # Blend success rate and quality, with exploration bonus for low attempts
                    confidence = min(1.0, attempts / 20)
                    ev = confidence * (0.6 * success_rate + 0.4 * quality) + \
                         (1 - confidence) * 0.5

                if ev > best_score:
                    best_score = ev
                    best_strategy = strat

            self._current_strategy[task_type] = best_strategy
            return best_strategy

    def get_current_strategy(self, task_type: str) -> str:
        """Get the currently selected strategy for a task type."""
        with self._lock:
            return self._current_strategy.get(task_type, "q_learning")

    def get_strategy_report(self, task_type: str) -> Dict[str, Any]:
        """Get detailed strategy performance for a task type."""
        with self._lock:
            scores = self._strategy_scores.get(task_type, {})
            report = {}
            for strat, stats in scores.items():
                attempts = stats["attempts"]
                report[strat] = {
                    "attempts": attempts,
                    "success_rate": round(stats["successes"] / attempts, 4) if attempts > 0 else None,
                    "avg_quality": stats["avg_quality"],
                }
            return {
                "task_type": task_type,
                "current_strategy": self._current_strategy.get(task_type, "q_learning"),
                "strategies": report,
            }

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "strategy_scores": {
                    t: dict(s) for t, s in self._strategy_scores.items()
                },
                "current_strategy": dict(self._current_strategy),
            }

    def from_dict(self, data: dict):
        with self._lock:
            for t, strategies in data.get("strategy_scores", {}).items():
                for s, stats in strategies.items():
                    self._strategy_scores[t][s] = stats
            self._current_strategy = data.get("current_strategy", {})


# ─── 3. ExplorationScheduler ────────────────────────────────────────────────

class ExplorationScheduler:
    """
    Adapts exploration rate per domain based on uncertainty.

    - High uncertainty → explore more
    - Well-known domains → exploit what works
    - Decreasing returns → reduce exploration over time
    - Per-domain tracking
    """

    def __init__(self):
        self._lock = threading.RLock()
        # domain → exploration rate
        self._exploration_rates: Dict[str, float] = {}
        # domain → {"uncertainty": float, "sample_count": int, "last_update": str}
        self._domain_info: Dict[str, Dict[str, Any]] = {}
        # Global decay counter (number of reflection sessions)
        self._global_steps: int = 0

    def update_uncertainty(self, domain: str, uncertainty: float,
                           success: Optional[bool] = None):
        """
        Update exploration rate for a domain based on observed uncertainty.

        uncertainty: 0.0 (fully certain) to 1.0 (max uncertainty)
        success: if provided, adjust based on whether action succeeded
        """
        with self._lock:
            uncertainty = _clamp(uncertainty, 0.0, 1.0)

            info = self._domain_info.setdefault(domain, {
                "uncertainty": 0.5, "sample_count": 0, "last_update": _now_iso()
            })

            # EMA update of uncertainty
            alpha = 0.2
            info["uncertainty"] = round(
                alpha * uncertainty + (1 - alpha) * info["uncertainty"], 4
            )
            info["sample_count"] += 1
            info["last_update"] = _now_iso()

            # Compute exploration rate: high uncertainty → high exploration
            # But apply global decay (learned domains explore less over time)
            base_exploration = info["uncertainty"] * EXPLORATION_MAX
            decay_factor = EXPLORATION_DECAY ** self._global_steps
            exploration = base_exploration * decay_factor

            # Floor: never go below EXPLORATION_MIN for low-sample domains
            if info["sample_count"] < 10:
                exploration = max(exploration, EXPLORATION_MIN * 2)

            self._exploration_rates[domain] = round(
                _clamp(exploration, EXPLORATION_MIN, EXPLORATION_MAX), 4
            )

    def get_exploration_rate(self, domain: str) -> float:
        """Get the current exploration rate for a domain."""
        with self._lock:
            return self._exploration_rates.get(domain, EXPLORATION_DEFAULT)

    def should_explore(self, domain: str) -> bool:
        """Decide whether to explore or exploit for a domain."""
        with self._lock:
            rate = self._exploration_rates.get(domain, EXPLORATION_DEFAULT)
            return random.random() < rate

    def decay_step(self):
        """Called after each meta-reflection to globally reduce exploration."""
        with self._lock:
            self._global_steps += 1
            # Apply decay to all domains
            for domain in list(self._exploration_rates.keys()):
                self._exploration_rates[domain] = round(
                    max(EXPLORATION_MIN,
                        self._exploration_rates[domain] * EXPLORATION_DECAY), 4
                )

    def get_domain_info(self, domain: str) -> Dict[str, Any]:
        """Get exploration info for a domain."""
        with self._lock:
            return {
                "domain": domain,
                "exploration_rate": self._exploration_rates.get(domain, EXPLORATION_DEFAULT),
                **self._domain_info.get(domain, {"uncertainty": 0.5, "sample_count": 0}),
                "global_steps": self._global_steps,
            }

    def get_all_domains(self) -> List[str]:
        with self._lock:
            domains = set(self._exploration_rates.keys())
            domains.update(self._domain_info.keys())
            return sorted(domains)

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "exploration_rates": dict(self._exploration_rates),
                "domain_info": dict(self._domain_info),
                "global_steps": self._global_steps,
            }

    def from_dict(self, data: dict):
        with self._lock:
            self._exploration_rates = data.get("exploration_rates", {})
            self._domain_info = data.get("domain_info", {})
            self._global_steps = data.get("global_steps", 0)


# ─── 4. MetaCognitiveLoop ───────────────────────────────────────────────────

class MetaCognitiveLoop:
    """
    Reflects on the learning process itself.

    Key questions:
    - "Am I learning effectively?"
    - "Should I change my approach?"
    - "What am I failing to learn?"

    Maintains a history of meta-reflection sessions.
    """

    def __init__(self):
        self._lock = threading.RLock()
        # List of reflection session results
        self._reflections: List[Dict[str, Any]] = []
        self._last_reflection_time: float = 0.0
        # Domains where learning has stalled
        self._stalled_domains: List[str] = []
        # Domains where learning is progressing well
        self._thriving_domains: List[str] = []

    def should_reflect(self) -> bool:
        """Check if enough time has passed for a new reflection."""
        with self._lock:
            return (time.time() - self._last_reflection_time) >= META_REFLECT_INTERVAL

    def run_reflection(self, lr_adapter: LearningRateAdapter,
                       strategy_selector: StrategySelector,
                       exploration_scheduler: ExplorationScheduler) -> Dict[str, Any]:
        """
        Run a meta-cognitive reflection session.

        Analyzes learning effectiveness across all domains and produces
        actionable insights.
        """
        with self._lock:
            session = {
                "timestamp": _now_iso(),
                "insights": [],
                "stalled": [],
                "thriving": [],
                "recommendations": [],
            }

            # Gather all domains from all subsystems
            all_domains = set()
            all_domains.update(lr_adapter.get_all_domains())
            all_domains.update(exploration_scheduler.get_all_domains())
            all_domains.update(strategy_selector._strategy_scores.keys())

            for domain in all_domains:
                # Check learning rate trends
                lr_info = lr_adapter.get_accuracy_trend(domain)
                expl_info = exploration_scheduler.get_domain_info(domain)

                trend = lr_info.get("trend", 0.0)
                avg_acc = lr_info.get("average_accuracy", 0.5)
                samples = lr_info.get("samples", 0)
                exploration = expl_info.get("exploration_rate", EXPLORATION_DEFAULT)

                # Classify domain health
                if samples < 3:
                    # Too little data to judge
                    session["insights"].append(
                        f"{domain}: insufficient data ({samples} samples)"
                    )
                elif trend < -0.01 and avg_acc < 0.4:
                    # Declining and low accuracy → stalled
                    session["stalled"].append(domain)
                    session["insights"].append(
                        f"{domain}: STALLED — accuracy declining "
                        f"(trend={trend:.4f}, avg={avg_acc:.2f})"
                    )
                    session["recommendations"].append(
                        f"{domain}: increase LR from {lr_info['current_lr']:.3f}, "
                        f"try different strategy, increase exploration"
                    )
                elif trend > 0.005 and avg_acc > 0.6:
                    # Improving and decent accuracy → thriving
                    session["thriving"].append(domain)
                    session["insights"].append(
                        f"{domain}: THRIVING — accuracy improving "
                        f"(trend={trend:.4f}, avg={avg_acc:.2f})"
                    )
                elif abs(trend) < 0.003 and samples > 20:
                    # Plateau with enough data
                    session["insights"].append(
                        f"{domain}: PLATEAUED — no significant change "
                        f"(trend={trend:.4f}, avg={avg_acc:.2f})"
                    )
                    if avg_acc < 0.5:
                        session["recommendations"].append(
                            f"{domain}: consider switching strategy or increasing exploration"
                        )

                # Check if exploration should be reduced
                if exploration > 0.3 and samples > 30 and avg_acc > 0.7:
                    session["recommendations"].append(
                        f"{domain}: reduce exploration from {exploration:.3f} — "
                        f"well-learned domain"
                    )

            # Check strategy effectiveness across task types
            for task_type in strategy_selector._strategy_scores:
                report = strategy_selector.get_strategy_report(task_type)
                current = report["current_strategy"]
                strat_data = report["strategies"].get(current, {})
                success_rate = strat_data.get("success_rate")
                if success_rate is not None and success_rate < 0.3:
                    session["recommendations"].append(
                        f"task '{task_type}': current strategy '{current}' has "
                        f"low success rate ({success_rate:.2f}) — consider switching"
                    )

            # Global assessment
            n_stalled = len(session["stalled"])
            n_thriving = len(session["thriving"])
            n_total = len(all_domains)

            if n_total > 0:
                health_ratio = (n_thriving - n_stalled) / n_total
                if health_ratio > 0.3:
                    session["overall"] = "healthy"
                elif health_ratio > -0.2:
                    session["overall"] = "mixed"
                else:
                    session["overall"] = "concerning"
            else:
                session["overall"] = "no_data"

            # Store
            self._stalled_domains = session["stalled"]
            self._thriving_domains = session["thriving"]
            self._reflections.append(session)
            self._reflections = self._reflections[-50:]  # keep last 50
            self._last_reflection_time = time.time()

            return session

    def get_last_reflection(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._reflections[-1] if self._reflections else None

    def get_stalled_domains(self) -> List[str]:
        with self._lock:
            return list(self._stalled_domains)

    def get_thriving_domains(self) -> List[str]:
        with self._lock:
            return list(self._thriving_domains)

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "reflections": self._reflections[-20:],
                "last_reflection_time": self._last_reflection_time,
                "stalled_domains": self._stalled_domains,
                "thriving_domains": self._thriving_domains,
            }

    def from_dict(self, data: dict):
        with self._lock:
            self._reflections = data.get("reflections", [])
            self._last_reflection_time = data.get("last_reflection_time", 0.0)
            self._stalled_domains = data.get("stalled_domains", [])
            self._thriving_domains = data.get("thriving_domains", [])


# ─── 5. AntiCatastrophicForgetting ──────────────────────────────────────────

class AntiCatastrophicForgetting:
    """
    Protects important Q-values from being overwritten by new learning.

    Inspired by Elastic Weight Consolidation (EWC):
    - Tracks importance of each Q-value via access count and confidence
    - Important values get lower effective learning rates
    - Periodic rehearsal of old knowledge during idle time

    This prevents FRIDAY from "forgetting" well-learned skills when
    learning something new.
    """

    def __init__(self):
        self._lock = threading.RLock()
        # "action::context" → {"importance": float, "access_count": int,
        #                       "last_access": str, "q_value_snapshot": float}
        self._importance_scores: Dict[str, Dict[str, Any]] = {}
        self._last_rehearsal_time: float = 0.0
        self._rehearsal_count: int = 0

    def record_access(self, action: str, context: str, q_value: float):
        """Record that a Q-value was accessed (learned or used)."""
        with self._lock:
            key = f"{action}::{context}"
            entry = self._importance_scores.setdefault(key, {
                "importance": 0.1,
                "access_count": 0,
                "last_access": _now_iso(),
                "q_value_snapshot": 0.0,
                "confidence": 0.0,
            })
            entry["access_count"] += 1
            entry["last_access"] = _now_iso()
            entry["q_value_snapshot"] = round(q_value, 4)

            # Importance grows with access count (logarithmic) and confidence
            access_factor = math.log1p(entry["access_count"]) / math.log1p(100)
            confidence = min(1.0, entry["access_count"] / 30)
            entry["confidence"] = round(confidence, 4)
            entry["importance"] = round(
                _clamp(0.3 * access_factor + 0.7 * confidence, 0.0, 1.0), 4
            )

    def get_effective_lr(self, action: str, context: str,
                         base_lr: float) -> float:
        """
        Compute effective learning rate for a Q-value.
        Important values get lower LR to protect them.
        """
        with self._lock:
            key = f"{action}::{context}"
            entry = self._importance_scores.get(key)
            if not entry:
                return base_lr

            importance = entry["importance"]
            # Scale: high importance → lower LR
            # At importance=1.0, LR is 20% of base
            # At importance=0.0, LR is 100% of base
            scale = 1.0 - 0.8 * importance
            return round(base_lr * scale, 4)

    def get_protected_values(self, min_importance: float = 0.7) -> List[Dict[str, Any]]:
        """Get Q-values that are considered important and protected."""
        with self._lock:
            protected = []
            for key, entry in self._importance_scores.items():
                if entry["importance"] >= min_importance:
                    action, context = key.split("::", 1)
                    protected.append({
                        "action": action,
                        "context": context,
                        "importance": entry["importance"],
                        "access_count": entry["access_count"],
                        "q_value": entry["q_value_snapshot"],
                    })
            return sorted(protected, key=lambda x: x["importance"], reverse=True)

    def get_rehearsal_candidates(self, batch_size: int = REHEARSAL_BATCH_SIZE) -> List[str]:
        """
        Get Q-value keys that should be rehearsed.
        Prioritizes high-importance values that haven't been accessed recently.
        """
        with self._lock:
            now = time.time()
            candidates = []
            for key, entry in self._importance_scores.items():
                if entry["importance"] < 0.3:
                    continue
                # Prefer values not accessed recently
                try:
                    last = datetime.fromisoformat(entry["last_access"]).timestamp()
                    age_hours = (now - last) / 3600
                except (ValueError, TypeError):
                    age_hours = 999

                # Score: importance × age (higher = more urgent to rehearse)
                score = entry["importance"] * (1 + math.log1p(age_hours))
                candidates.append((key, score))

            candidates.sort(key=lambda x: x[1], reverse=True)
            return [k for k, _ in candidates[:batch_size]]

    def should_rehearse(self) -> bool:
        """Check if it's time for a rehearsal cycle."""
        with self._lock:
            return (time.time() - self._last_rehearsal_time) >= REHEARSAL_INTERVAL

    def mark_rehearsal_done(self):
        """Mark that a rehearsal cycle has been completed."""
        with self._lock:
            self._last_rehearsal_time = time.time()
            self._rehearsal_count += 1

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "importance_scores": dict(self._importance_scores),
                "last_rehearsal_time": self._last_rehearsal_time,
                "rehearsal_count": self._rehearsal_count,
            }

    def from_dict(self, data: dict):
        with self._lock:
            self._importance_scores = data.get("importance_scores", {})
            self._last_rehearsal_time = data.get("last_rehearsal_time", 0.0)
            self._rehearsal_count = data.get("rehearsal_count", 0)


# ─── 6. MetaLearner (Main Orchestrator) ─────────────────────────────────────

class MetaLearner:
    """
    Top-level meta-learning orchestrator for FRIDAY.

    Coordinates all meta-learning subsystems and integrates with
    brain.learning, brain.active_inference, and brain.self_improve_engine.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self.lr_adapter = LearningRateAdapter()
        self.strategy_selector = StrategySelector()
        self.exploration_scheduler = ExplorationScheduler()
        self.meta_loop = MetaCognitiveLoop()
        self.forgetting_guard = AntiCatastrophicForgetting()

        # Session stats
        self._session_start = time.time()
        self._total_reflections = 0
        self._total_lr_adjustments = 0
        self._total_strategy_switches = 0

        # Load persisted data
        self._load()
        print(f"[MetaLearner] Initialized — loaded {len(self.lr_adapter.get_all_domains())} domains")

    def _load(self):
        """Load persisted meta-learning data."""
        with self._lock:
            if not META_DATA_FILE.exists():
                return
            try:
                with open(META_DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.lr_adapter.from_dict(data.get("lr_adapter", {}))
                self.strategy_selector.from_dict(data.get("strategy_selector", {}))
                self.exploration_scheduler.from_dict(data.get("exploration_scheduler", {}))
                self.meta_loop.from_dict(data.get("meta_loop", {}))
                self.forgetting_guard.from_dict(data.get("forgetting_guard", {}))
                self._total_reflections = data.get("total_reflections", 0)
                self._total_lr_adjustments = data.get("total_lr_adjustments", 0)
                self._total_strategy_switches = data.get("total_strategy_switches", 0)
                print(f"[MetaLearner] Loaded data — {self._total_reflections} prior reflections")
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[MetaLearner] Warning: could not load data: {e}")

    def _save(self):
        """Persist meta-learning data."""
        with self._lock:
            data = {
                "last_update": _now_iso(),
                "total_reflections": self._total_reflections,
                "total_lr_adjustments": self._total_lr_adjustments,
                "total_strategy_switches": self._total_strategy_switches,
                "lr_adapter": self.lr_adapter.to_dict(),
                "strategy_selector": self.strategy_selector.to_dict(),
                "exploration_scheduler": self.exploration_scheduler.to_dict(),
                "meta_loop": self.meta_loop.to_dict(),
                "forgetting_guard": self.forgetting_guard.to_dict(),
            }
            try:
                with open(META_DATA_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except OSError as e:
                print(f"[MetaLearner] Warning: could not save data: {e}")

    # ── Integration with brain.learning ──────────────────────────────────────

    def adjust_learning_params(self, domain: str = "general"):
        """
        Adjust Q-learning parameters in brain.learning based on meta-learning.

        Reads adapted LR and exploration rates, then applies them.
        """
        try:
            from brain.learning import get_learning_engine, Q_LEARNING_RATE
            engine = get_learning_engine()

            adapted_lr = self.lr_adapter.get_learning_rate(domain)
            exploration = self.exploration_scheduler.get_exploration_rate(domain)

            # Apply via monkey-patching the module constants
            import brain.learning as learning_mod
            old_lr = getattr(learning_mod, 'Q_LEARNING_RATE', Q_LEARNING_RATE)
            learning_mod.Q_LEARNING_RATE = adapted_lr
            learning_mod.Q_EXPLORATION_RATE = exploration

            if abs(adapted_lr - old_lr) > 0.01:
                self._total_lr_adjustments += 1
                print(f"[MetaLearner] Adjusted Q-LR for '{domain}': "
                      f"{old_lr:.4f} → {adapted_lr:.4f}, exploration: {exploration:.4f}")

        except ImportError:
            print("[MetaLearner] brain.learning not available for integration")

    def adjust_active_inference_params(self, domain: str = "general"):
        """
        Adjust active inference model learning rates based on meta-learning.
        """
        try:
            from brain.active_inference import get_active_inference
            ai = get_active_inference()

            adapted_lr = self.lr_adapter.get_learning_rate(domain)

            # Update the active inference engine's internal learning rate
            with ai._lock:
                if hasattr(ai, '_data') and 'meta' in ai._data:
                    ai._data['meta']['learning_rate'] = adapted_lr
                    ai._save()
                    print(f"[MetaLearner] Adjusted ActiveInference LR for "
                          f"'{domain}': {adapted_lr:.4f}")

        except ImportError:
            print("[MetaLearner] brain.active_inference not available for integration")

    def feed_to_self_improve(self, insight: str, quality: float = 0.7):
        """Feed a meta-learning insight into the self-improvement engine."""
        try:
            from brain.self_improve_engine import get_self_improve_engine
            engine = get_self_improve_engine()

            engine.record_experience({
                "action": "meta_reflection",
                "context": "meta_learning",
                "outcome": {"success": quality > 0.5, "quality": quality},
                "lesson": insight,
                "source": "meta_learner",
            })
        except ImportError:
            print("[MetaLearner] brain.self_improve_engine not available for integration")

    def on_tool_result(self, tool_name: str, context: str, success: bool,
                       quality: float = 0.5, prediction_error: float = 0.0):
        """
        Called after each tool execution to feed all meta-learning subsystems.

        This is the main integration point — call this from the orchestrator
        after every tool call.
        """
        domain = self._classify_domain(tool_name, context)

        # 1. Update accuracy → adapt learning rate
        accuracy = 1.0 - prediction_error if prediction_error > 0 else (1.0 if success else 0.0)
        self.lr_adapter.record_accuracy(domain, accuracy)

        # 2. Update strategy performance
        strategy = self.strategy_selector.get_current_strategy(domain)
        self.strategy_selector.record_outcome(domain, strategy, success, quality)

        # 3. Update exploration based on uncertainty
        uncertainty = prediction_error if prediction_error > 0 else (0.3 if not success else 0.1)
        self.exploration_scheduler.update_uncertainty(domain, uncertainty, success)

        # 4. Track Q-value importance for forgetting guard
        self.forgetting_guard.record_access(tool_name, context, quality)

        # 5. Periodically adjust learning params
        self.adjust_learning_params(domain)
        self.adjust_active_inference_params(domain)

    def _classify_domain(self, tool_name: str, context: str) -> str:
        """Classify a tool/context into a learning domain."""
        tool_lower = tool_name.lower()
        context_lower = context.lower() if context else ""

        # Security domain
        security_keywords = ["security", "vuln", "scan", "nmap", "exploit",
                             "cve", "audit", "pentest", "firewall", "malware"]
        if any(kw in tool_lower or kw in context_lower for kw in security_keywords):
            return "security"

        # Code domain
        code_keywords = ["code", "script", "compile", "debug", "refactor",
                         "git", "commit", "test", "lint", "build"]
        if any(kw in tool_lower or kw in context_lower for kw in code_keywords):
            return "coding"

        # Communication domain
        comm_keywords = ["email", "message", "chat", "notify", "reply",
                         "summarize", "explain", "write", "draft"]
        if any(kw in tool_lower or kw in context_lower for kw in comm_keywords):
            return "communication"

        # Research domain
        research_keywords = ["search", "fetch", "web", "query", "lookup",
                             "research", "analyze", "data"]
        if any(kw in tool_lower or kw in context_lower for kw in research_keywords):
            return "research"

        # System domain
        sys_keywords = ["exec", "shell", "bash", "process", "file", "read",
                        "write", "install", "config", "system"]
        if any(kw in tool_lower or kw in context_lower for kw in sys_keywords):
            return "system"

        return "general"

    # ── Strategy Selection ───────────────────────────────────────────────────

    def select_learning_strategy(self, task_type: str) -> str:
        """Select the best learning strategy for a task type."""
        return self.strategy_selector.select_strategy(task_type)

    # ── Rehearsal (Anti-Forgetting) ──────────────────────────────────────────

    def run_rehearsal(self):
        """
        Rehearse important Q-values to prevent catastrophic forgetting.

        This should be called during idle time. It re-accesses important
        Q-values to keep them fresh.
        """
        if not self.forgetting_guard.should_rehearse():
            return

        candidates = self.forgetting_guard.get_rehearsal_candidates()
        if not candidates:
            return

        try:
            from brain.learning import get_learning_engine
            engine = get_learning_engine()

            rehearsed = 0
            for key in candidates:
                parts = key.split("::", 1)
                if len(parts) != 2:
                    continue
                action, context = parts
                # Re-access the Q-value (this refreshes it in memory)
                q_val = engine.get_q_value(action, context)
                self.forgetting_guard.record_access(action, context, q_val)
                rehearsed += 1

            self.forgetting_guard.mark_rehearsal_done()
            print(f"[MetaLearner] Rehearsal complete — rehearsed {rehearsed} Q-values")

        except ImportError:
            print("[MetaLearner] brain.learning not available for rehearsal")

    # ── Full Meta-Reflection ─────────────────────────────────────────────────

    def meta_reflect(self, force: bool = False) -> Optional[Dict[str, Any]]:
        """
        Run a full meta-learning reflection session.

        This is the top-level entry point that:
        1. Runs the meta-cognitive loop
        2. Adjusts learning parameters across all domains
        3. Selects/switches strategies for stalled domains
        4. Triggers rehearsal of important knowledge
        5. Feeds insights into the self-improvement engine
        6. Persists all changes
        """
        with self._lock:
            if not force and not self.meta_loop.should_reflect():
                return None

            print("[MetaLearner] Starting meta-reflection session...")

            # 1. Run meta-cognitive reflection
            reflection = self.meta_loop.run_reflection(
                self.lr_adapter, self.strategy_selector, self.exploration_scheduler
            )

            # 2. For stalled domains, adjust parameters aggressively
            for domain in reflection.get("stalled", []):
                # Increase learning rate
                current_lr = self.lr_adapter.get_learning_rate(domain)
                new_lr = min(LR_MAX, current_lr * 1.5)
                self.lr_adapter.set_learning_rate(domain, new_lr)
                print(f"[MetaLearner] Stalled domain '{domain}': "
                      f"boosted LR {current_lr:.4f} → {new_lr:.4f}")

                # Switch strategy if current one is failing
                old_strategy = self.strategy_selector.get_current_strategy(domain)
                new_strategy = self.strategy_selector.select_strategy(domain)
                if new_strategy != old_strategy:
                    self._total_strategy_switches += 1
                    print(f"[MetaLearner] Domain '{domain}': "
                          f"switched strategy {old_strategy} → {new_strategy}")

                # Increase exploration
                self.exploration_scheduler.update_uncertainty(domain, 0.8)

            # 3. For thriving domains, fine-tune (reduce LR, reduce exploration)
            for domain in reflection.get("thriving", []):
                current_lr = self.lr_adapter.get_learning_rate(domain)
                new_lr = max(LR_MIN, current_lr * 0.8)
                self.lr_adapter.set_learning_rate(domain, new_lr)
                self.exploration_scheduler.update_uncertainty(domain, 0.1)

            # 4. Global exploration decay
            self.exploration_scheduler.decay_step()

            # 5. Run rehearsal
            self.run_rehearsal()

            # 6. Apply adjusted params to integrated modules
            for domain in self.lr_adapter.get_all_domains():
                self.adjust_learning_params(domain)
                self.adjust_active_inference_params(domain)

            # 7. Feed key insights to self-improvement engine
            for rec in reflection.get("recommendations", []):
                self.feed_to_self_improve(rec, quality=0.7)

            self._total_reflections += 1

            # 8. Persist
            self._save()

            # Summary
            n_insights = len(reflection.get("insights", []))
            n_stalled = len(reflection.get("stalled", []))
            n_thriving = len(reflection.get("thriving", []))
            print(f"[MetaLearner] Reflection #{self._total_reflections} complete — "
                  f"{n_insights} insights, {n_stalled} stalled, {n_thriving} thriving, "
                  f"overall: {reflection.get('overall', 'unknown')}")

            return reflection

    # ── Stats & Formatting ───────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive meta-learning statistics."""
        with self._lock:
            uptime_min = (time.time() - self._session_start) / 60
            all_domains = self.lr_adapter.get_all_domains()

            domain_stats = {}
            for domain in all_domains:
                lr_info = self.lr_adapter.get_accuracy_trend(domain)
                expl_info = self.exploration_scheduler.get_domain_info(domain)
                domain_stats[domain] = {
                    "learning_rate": lr_info.get("current_lr", LR_DEFAULT),
                    "accuracy_trend": lr_info.get("trend", 0.0),
                    "average_accuracy": lr_info.get("average_accuracy", 0.0),
                    "exploration_rate": expl_info.get("exploration_rate", EXPLORATION_DEFAULT),
                    "samples": lr_info.get("samples", 0),
                }

            protected = self.forgetting_guard.get_protected_values()

            last_reflection = self.meta_loop.get_last_reflection()

            return {
                "uptime_minutes": round(uptime_min, 1),
                "total_reflections": self._total_reflections,
                "total_lr_adjustments": self._total_lr_adjustments,
                "total_strategy_switches": self._total_strategy_switches,
                "domains_tracked": len(all_domains),
                "domain_stats": domain_stats,
                "protected_values_count": len(protected),
                "rehearsal_count": self.forgetting_guard._rehearsal_count,
                "stalled_domains": self.meta_loop.get_stalled_domains(),
                "thriving_domains": self.meta_loop.get_thriving_domains(),
                "last_reflection_overall": last_reflection.get("overall") if last_reflection else None,
            }

    def format_for_prompt(self, max_chars: int = 2000) -> str:
        """Format meta-learning state for inclusion in FRIDAY's prompt."""
        with self._lock:
            stats = self.get_stats()
            lines = ["## Meta-Learning Status"]

            lines.append(f"Reflections: {stats['total_reflections']} | "
                        f"LR adjustments: {stats['total_lr_adjustments']} | "
                        f"Strategy switches: {stats['total_strategy_switches']}")

            # Domain summary
            if stats["domain_stats"]:
                lines.append("\n### Domain Performance")
                for domain, ds in stats["domain_stats"].items():
                    trend_arrow = "↑" if ds["accuracy_trend"] > 0.005 else (
                        "↓" if ds["accuracy_trend"] < -0.005 else "→"
                    )
                    lines.append(
                        f"- **{domain}**: LR={ds['learning_rate']:.3f}, "
                        f"acc={ds['average_accuracy']:.2f} {trend_arrow}, "
                        f"explore={ds['exploration_rate']:.3f}"
                    )

            # Stalled/thriving
            if stats["stalled_domains"]:
                lines.append(f"\n⚠️ Stalled: {', '.join(stats['stalled_domains'])}")
            if stats["thriving_domains"]:
                lines.append(f"\n✅ Thriving: {', '.join(stats['thriving_domains'])}")

            # Strategy report
            lines.append("\n### Current Strategies")
            for task_type in self.strategy_selector._strategy_scores:
                strategy = self.strategy_selector.get_current_strategy(task_type)
                report = self.strategy_selector.get_strategy_report(task_type)
                sr = report["strategies"].get(strategy, {}).get("success_rate")
                sr_str = f" ({sr:.0%})" if sr is not None else ""
                lines.append(f"- {task_type}: {strategy}{sr_str}")

            # Protection
            n_protected = stats["protected_values_count"]
            if n_protected > 0:
                lines.append(f"\n🛡️ {n_protected} Q-values protected from forgetting")

            # Last reflection
            last = self.meta_loop.get_last_reflection()
            if last:
                overall = last.get("overall", "unknown")
                emoji = {"healthy": "🟢", "mixed": "🟡", "concerning": "🔴"}.get(overall, "⚪")
                lines.append(f"\n{emoji} Learning health: {overall}")

            result = "\n".join(lines)
            if len(result) > max_chars:
                result = result[:max_chars - 20] + "\n... (truncated)"
            return result


# ─── Singleton ───────────────────────────────────────────────────────────────

_meta_learner: Optional[MetaLearner] = None
_meta_learner_lock = threading.Lock()


def get_meta_learner() -> MetaLearner:
    """Get the singleton MetaLearner instance."""
    global _meta_learner
    if _meta_learner is None:
        with _meta_learner_lock:
            if _meta_learner is None:
                _meta_learner = MetaLearner()
    return _meta_learner
