#!/usr/bin/env python3
"""
hierarchical_active_inference.py — FRIDAY Hierarchical Active Inference
=======================================================================

Extends the flat ActiveInferenceEngine with a 3-level hierarchical model
based on the Free Energy Principle (Karl Friston).

Levels:
  Meta     — Strategic priors, goal decomposition, system competence beliefs
  Subgoal  — Tactical planning, subgoal selection, resource allocation
  Action   — Motor commands, tool calls, parameter selection

Each level maintains:
  - Belief state (probability distribution over hypotheses)
  - Prediction model (predicts outcomes at its abstraction level)
  - Precision weighting (confidence modulates learning rate)
  - Free energy computation (variational free energy)

POMDP belief updates for partial observability:
  - Bayesian update given new evidence
  - Forward model prediction
  - Expected Free Energy (EFE) for action selection

Top-down: meta beliefs constrain subgoal, subgoal constrains action
Bottom-up: action-level prediction errors propagate upward

Integrates with:
- active_inference.py — extends, doesn't replace
- global_workspace.py — publishes prediction error events
"""

import json
import math
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BRAIN_DIR = Path(__file__).parent.resolve()
HAI_FILE = BRAIN_DIR / "hierarchical_active_inference.json"

# Free energy weights
EFE_WEIGHTS = {
    "expected_cost": 0.25,
    "expected_risk": 0.25,
    "information_gain": 0.20,
    "goal_relevance": 0.15,
    "complexity_penalty": 0.15,
}

# Precision defaults
DEFAULT_PRECISION = 1.0
MIN_PRECISION = 0.1
MAX_PRECISION = 10.0
PRECISION_LR = 0.05

# Belief update parameters
BELIEF_LR = 0.1
PRIOR_DECAY = 0.95


class BeliefState:
    """
    A probability distribution over hypotheses at one hierarchical level.

    Maintains beliefs as a dict of hypothesis → probability,
    with precision weighting that modulates learning rate.
    """

    def __init__(self, level_name: str, hypotheses: Optional[Dict[str, float]] = None):
        self.level_name = level_name
        self.hypotheses: Dict[str, float] = hypotheses or {"default": 1.0}
        self.precision: float = DEFAULT_PRECISION
        self.prediction_history: List[dict] = []
        self.free_energy_history: List[float] = []
        self._normalize()

    def _normalize(self) -> None:
        """Normalize hypothesis probabilities to sum to 1."""
        total = sum(self.hypotheses.values())
        if total > 0:
            self.hypotheses = {k: v / total for k, v in self.hypotheses.items()}
        else:
            n = len(self.hypotheses)
            if n > 0:
                self.hypotheses = {k: 1.0 / n for k in self.hypotheses}

    def update(self, observation: Dict[str, float], learning_rate: float = BELIEF_LR) -> None:
        """
        Bayesian belief update given new observation.

        Args:
            observation: Mapping from hypothesis names to likelihood (0-1)
            learning_rate: Base learning rate (modulated by precision)
        """
        effective_lr = learning_rate * self.precision

        for hyp, likelihood in observation.items():
            if hyp in self.hypotheses:
                # Bayesian-style update: posterior ∝ prior × likelihood
                prior = self.hypotheses[hyp]
                self.hypotheses[hyp] = prior + effective_lr * (likelihood - prior)
            else:
                # New hypothesis discovered
                self.hypotheses[hyp] = effective_lr * likelihood

        # Decay uninformed hypotheses
        for hyp in list(self.hypotheses.keys()):
            if hyp not in observation:
                self.hypotheses[hyp] *= PRIOR_DECAY

        self._normalize()

    def get_top_hypothesis(self) -> Tuple[str, float]:
        """Get the most probable hypothesis."""
        if not self.hypotheses:
            return ("unknown", 0.0)
        top = max(self.hypotheses.items(), key=lambda x: x[1])
        return top

    def get_entropy(self) -> float:
        """Compute Shannon entropy of belief distribution."""
        entropy = 0.0
        for p in self.hypotheses.values():
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy

    def get_confidence(self) -> float:
        """Get confidence = 1 - normalized entropy."""
        max_entropy = math.log2(max(len(self.hypotheses), 2))
        if max_entropy == 0:
            return 1.0
        return max(0.0, 1.0 - self.get_entropy() / max_entropy)

    def to_dict(self) -> dict:
        return {
            "level": self.level_name,
            "hypotheses": self.hypotheses,
            "precision": round(self.precision, 3),
            "entropy": round(self.get_entropy(), 3),
            "confidence": round(self.get_confidence(), 3),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BeliefState":
        bs = cls(
            level_name=data.get("level", "unknown"),
            hypotheses=data.get("hypotheses", {"default": 1.0}),
        )
        bs.precision = data.get("precision", DEFAULT_PRECISION)
        return bs


class HierarchicalLevel:
    """
    One level in the hierarchical active inference model.

    Contains belief state, prediction model, and free energy computation.
    """

    def __init__(self, name: str, hypotheses: Optional[Dict[str, float]] = None):
        self.name = name
        self.beliefs = BeliefState(name, hypotheses)
        self.prediction_model: Dict[str, Dict[str, float]] = {}
        # action → {outcome: probability}
        self.observation_count = 0
        self.total_free_energy = 0.0

    def predict_next_state(self, action: str) -> Dict[str, float]:
        """
        Forward model: predict outcome distribution given an action.

        Args:
            action: The action to predict outcomes for

        Returns:
            Dict mapping outcome names to probabilities
        """
        if action in self.prediction_model:
            return dict(self.prediction_model[action])

        # Default: uncertain prediction
        return {"success": 0.5, "failure": 0.5}

    def update_prediction_model(self, action: str, outcome: str,
                                 success: bool, lr: float = BELIEF_LR) -> None:
        """
        Update the forward prediction model based on observed outcome.

        Args:
            action: The action taken
            outcome: The observed outcome name
            success: Whether the outcome was successful
        """
        if action not in self.prediction_model:
            self.prediction_model[action] = {"success": 0.5, "failure": 0.5}

        effective_lr = lr * self.beliefs.precision
        model = self.prediction_model[action]

        if success:
            model["success"] = model.get("success", 0.5) + effective_lr * (1.0 - model.get("success", 0.5))
            model["failure"] = 1.0 - model["success"]
        else:
            model["failure"] = model.get("failure", 0.5) + effective_lr * (1.0 - model.get("failure", 0.5))
            model["success"] = 1.0 - model["failure"]

    def compute_variational_free_energy(self, observation: Dict[str, float]) -> float:
        """
        Compute variational free energy: F = KL(q||p) - E_q[ln p(o|s)]

        Simplified: measures surprise given current beliefs.

        Args:
            observation: Observed outcome distribution

        Returns:
            Free energy scalar (lower is better)
        """
        fe = 0.0
        for hyp, obs_prob in observation.items():
            belief = self.beliefs.hypotheses.get(hyp, 0.01)
            if belief > 0 and obs_prob > 0:
                # KL contribution
                fe += belief * math.log(belief / max(obs_prob, 1e-10))

        self.total_free_energy += fe
        self.observation_count += 1
        return fe

    def compute_expected_free_energy(self, action: str,
                                      goal_distribution: Dict[str, float]) -> float:
        """
        Compute Expected Free Energy (EFE) for action selection.

        EFE = expected_cost + expected_risk + information_gain
              + goal_relevance + complexity_penalty

        Args:
            action: The action to evaluate
            goal_distribution: Desired outcome distribution

        Returns:
            EFE scalar (lower is better — prefer actions with low EFE)
        """
        predicted = self.predict_next_state(action)

        # Expected cost: deviation from goal
        expected_cost = 0.0
        for outcome, goal_prob in goal_distribution.items():
            pred_prob = predicted.get(outcome, 0.5)
            expected_cost += abs(goal_prob - pred_prob)

        # Expected risk: entropy of predicted outcomes
        expected_risk = 0.0
        for p in predicted.values():
            if p > 0:
                expected_risk -= p * math.log2(p)

        # Information gain: how much we'd learn
        current_entropy = self.beliefs.get_entropy()
        # Predicted entropy after observation
        predicted_entropy = 0.0
        for outcome, prob in predicted.items():
            if prob > 0:
                predicted_entropy -= prob * math.log2(prob)
        information_gain = max(0, current_entropy - predicted_entropy)

        # Goal relevance: how directly the action serves the goal
        goal_relevance = 0.0
        for outcome, goal_prob in goal_distribution.items():
            if outcome in predicted:
                goal_relevance += goal_prob * predicted[outcome]

        # Complexity penalty: prefer simpler actions
        complexity_penalty = len(action.split("_")) * 0.1

        efe = (
            EFE_WEIGHTS["expected_cost"] * expected_cost +
            EFE_WEIGHTS["expected_risk"] * expected_risk -
            EFE_WEIGHTS["information_gain"] * information_gain +
            EFE_WEIGHTS["goal_relevance"] * (1.0 - goal_relevance) +
            EFE_WEIGHTS["complexity_penalty"] * complexity_penalty
        )

        return round(efe, 4)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "beliefs": self.beliefs.to_dict(),
            "prediction_model": self.prediction_model,
            "observation_count": self.observation_count,
            "avg_free_energy": round(
                self.total_free_energy / max(self.observation_count, 1), 4
            ),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HierarchicalLevel":
        level = cls(
            name=data.get("name", "unknown"),
        )
        if "beliefs" in data:
            level.beliefs = BeliefState.from_dict(data["beliefs"])
        level.prediction_model = data.get("prediction_model", {})
        level.observation_count = data.get("observation_count", 0)
        level.total_free_energy = data.get("avg_free_energy", 0) * level.observation_count
        return level


class HierarchicalActiveInference:
    """
    3-level Hierarchical Active Inference engine.

    Meta level:  Strategic priors, goal decomposition, system competence
    Subgoal level: Tactical planning, subgoal selection, resource allocation
    Action level:  Motor commands, tool calls, parameter selection

    Top-down: meta beliefs constrain subgoal selection,
              subgoal constrains action selection
    Bottom-up: action-level prediction errors propagate upward
    """

    def __init__(self):
        self._lock = threading.RLock()

        # Three hierarchical levels
        self.meta = HierarchicalLevel("meta", {
            "high_competence": 0.5,
            "moderate_competence": 0.3,
            "low_competence": 0.2,
        })
        self.subgoal = HierarchicalLevel("subgoal", {
            "explore": 0.3,
            "exploit": 0.4,
            "consolidate": 0.3,
        })
        self.action = HierarchicalLevel("action", {
            "direct_execute": 0.4,
            "plan_first": 0.3,
            "seek_help": 0.3,
        })

        # Cross-level connections
        self._prediction_errors: List[dict] = []
        self._session_count = 0

        # Load persisted state
        self._load()
        print("[HierarchicalAIF] Initialized — 3-level active inference online")

    # ── Persistence ─────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load hierarchical state from disk."""
        try:
            if HAI_FILE.exists():
                raw = HAI_FILE.read_text(encoding="utf-8")
                data = json.loads(raw)

                if "meta_level" in data:
                    self.meta = HierarchicalLevel.from_dict(data["meta_level"])
                if "subgoal_level" in data:
                    self.subgoal = HierarchicalLevel.from_dict(data["subgoal_level"])
                if "action_level" in data:
                    self.action = HierarchicalLevel.from_dict(data["action_level"])

                self._prediction_errors = data.get("prediction_errors", [])[-100:]
                self._session_count = data.get("session_count", 0)

                print(f"[HierarchicalAIF] Loaded state — {self._session_count} sessions")
        except (json.JSONDecodeError, IOError) as exc:
            print(f"[HierarchicalAIF] Load error: {exc}")

    def _save(self) -> None:
        """Persist hierarchical state to disk."""
        with self._lock:
            try:
                data = {
                    "meta_level": self.meta.to_dict(),
                    "subgoal_level": self.subgoal.to_dict(),
                    "action_level": self.action.to_dict(),
                    "prediction_errors": self._prediction_errors[-100:],
                    "session_count": self._session_count,
                    "last_update": datetime.now().isoformat(),
                }
                BRAIN_DIR.mkdir(parents=True, exist_ok=True)
                HAI_FILE.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except IOError as exc:
                print(f"[HierarchicalAIF] Save error: {exc}")

    # ── POMDP Belief Updates ────────────────────────────────────────────

    def update_beliefs(self, observation: Dict[str, Any]) -> dict:
        """
        Bayesian belief update across all levels given new evidence.

        Observations propagate through the hierarchy:
        - Action-level updates first (direct observation)
        - Prediction errors propagate upward
        - Top-down priors constrain lower levels

        Args:
            observation: Dict with keys:
                - level: "action"|"subgoal"|"meta" (which level observed)
                - hypotheses: dict of hypothesis → likelihood
                - outcome: observed outcome description
                - success: bool
                - action: action that was taken (optional)

        Returns:
            dict with updated beliefs at all levels and prediction errors
        """
        result = {
            "meta_beliefs": {},
            "subgoal_beliefs": {},
            "action_beliefs": {},
            "prediction_errors": [],
        }

        try:
            level = observation.get("level", "action")
            hypotheses = observation.get("hypotheses", {})
            success = observation.get("success", True)
            action = observation.get("action", "")

            with self._lock:
                # Update the observed level
                if level == "action":
                    self.action.beliefs.update(hypotheses)
                    if action:
                        self.action.update_prediction_model(
                            action, observation.get("outcome", "unknown"), success
                        )
                elif level == "subgoal":
                    self.subgoal.beliefs.update(hypotheses)
                elif level == "meta":
                    self.meta.beliefs.update(hypotheses)

                # Bottom-up: compute prediction errors and propagate
                if level == "action":
                    pe = self._compute_prediction_error("action", observation)
                    if abs(pe) > 0.3:
                        self._propagate_upward("action", pe, observation)
                        result["prediction_errors"].append({
                            "source": "action",
                            "error": round(pe, 3),
                            "observation": str(observation.get("outcome", ""))[:100],
                        })

                elif level == "subgoal":
                    pe = self._compute_prediction_error("subgoal", observation)
                    if abs(pe) > 0.4:
                        self._propagate_upward("subgoal", pe, observation)
                        result["prediction_errors"].append({
                            "source": "subgoal",
                            "error": round(pe, 3),
                        })

                # Top-down: apply priors from higher levels
                self._apply_top_down_priors()

                # Update result with current beliefs
                result["meta_beliefs"] = dict(self.meta.beliefs.hypotheses)
                result["subgoal_beliefs"] = dict(self.subgoal.beliefs.hypotheses)
                result["action_beliefs"] = dict(self.action.beliefs.hypotheses)

                # Adjust precision based on prediction errors
                self._update_precisions(result.get("prediction_errors", []))

                self._save()

        except Exception as exc:
            print(f"[HierarchicalAIF] Belief update error: {exc}")

        return result

    def predict_next_state(self, action: str) -> dict:
        """
        Forward model prediction at all levels.

        Args:
            action: The action to predict outcomes for

        Returns:
            dict with predictions at each level
        """
        with self._lock:
            return {
                "meta_prediction": self.meta.predict_next_state(action),
                "subgoal_prediction": self.subgoal.predict_next_state(action),
                "action_prediction": self.action.predict_next_state(action),
                "meta_confidence": self.meta.beliefs.get_confidence(),
                "subgoal_confidence": self.subgoal.beliefs.get_confidence(),
                "action_confidence": self.action.beliefs.get_confidence(),
            }

    def compute_expected_free_energy(self, action: str) -> dict:
        """
        Compute Expected Free Energy (EFE) for action selection at all levels.

        Lower EFE = preferred action.

        Args:
            action: The action to evaluate

        Returns:
            dict with EFE at each level and weighted total
        """
        with self._lock:
            # Goal distributions derived from current beliefs
            meta_goal = self.meta.beliefs.hypotheses
            subgoal_goal = self.subgoal.beliefs.hypotheses
            action_goal = self.action.beliefs.hypotheses

            meta_efe = self.meta.compute_expected_free_energy(action, meta_goal)
            subgoal_efe = self.subgoal.compute_expected_free_energy(action, subgoal_goal)
            action_efe = self.action.compute_expected_free_energy(action, action_goal)

            # Weighted total: meta has highest weight
            total_efe = 0.5 * meta_efe + 0.3 * subgoal_efe + 0.2 * action_efe

            return {
                "meta_efe": meta_efe,
                "subgoal_efe": subgoal_efe,
                "action_efe": action_efe,
                "total_efe": round(total_efe, 4),
                "action": action,
            }

    def select_action(self, available_actions: List[str]) -> Tuple[str, dict]:
        """
        Select the action with lowest Expected Free Energy.

        Args:
            available_actions: List of possible action names

        Returns:
            Tuple of (selected_action, efe_breakdown)
        """
        if not available_actions:
            return ("noop", {"total_efe": 0.0})

        best_action = available_actions[0]
        best_efe = float("inf")
        best_breakdown: dict = {}

        for action in available_actions:
            efe_result = self.compute_expected_free_energy(action)
            if efe_result["total_efe"] < best_efe:
                best_efe = efe_result["total_efe"]
                best_action = action
                best_breakdown = efe_result

        return best_action, best_breakdown

    # ── Cross-Level Dynamics ────────────────────────────────────────────

    def _compute_prediction_error(self, level: str, observation: dict) -> float:
        """
        Compute prediction error at a given level.

        Compares predicted outcome with actual observation.
        """
        level_obj = self._get_level(level)
        if level_obj is None:
            return 0.0

        action = observation.get("action", "unknown")
        predicted = level_obj.predict_next_state(action)
        success = observation.get("success", True)

        # Prediction error = |predicted_success_prob - actual|
        predicted_success = predicted.get("success", 0.5)
        actual = 1.0 if success else 0.0
        error = abs(predicted_success - actual)

        return error

    def _propagate_upward(self, source_level: str, error: float,
                           observation: dict) -> None:
        """
        Propagate prediction errors upward through the hierarchy.

        Action → Subgoal → Meta
        """
        # Record the error
        self._prediction_errors.append({
            "source": source_level,
            "error": round(error, 3),
            "timestamp": datetime.now().isoformat(),
            "observation": str(observation.get("outcome", ""))[:100],
        })

        if source_level == "action":
            # Action errors affect subgoal beliefs
            # High error → subgoal may need replanning
            if error > 0.5:
                self.subgoal.beliefs.update({
                    "explore": 0.6,
                    "exploit": 0.2,
                    "consolidate": 0.2,
                })
                # Also affect meta beliefs about competence
                self.meta.beliefs.update({
                    "high_competence": 0.3,
                    "moderate_competence": 0.4,
                    "low_competence": 0.3,
                })

        elif source_level == "subgoal":
            # Subgoal errors primarily affect meta beliefs
            if error > 0.5:
                self.meta.beliefs.update({
                    "high_competence": 0.2,
                    "moderate_competence": 0.4,
                    "low_competence": 0.4,
                })

    def _apply_top_down_priors(self) -> None:
        """
        Apply top-down priors: higher-level beliefs constrain lower levels.

        Meta beliefs → subgoal selection
        Subgoal beliefs → action selection
        """
        meta_top, meta_conf = self.meta.beliefs.get_top_hypothesis()

        # Meta → Subgoal
        if meta_top == "high_competence":
            # Confident: prefer exploitation
            self.subgoal.beliefs.update({
                "exploit": 0.5,
                "explore": 0.2,
                "consolidate": 0.3,
            }, learning_rate=0.05)
        elif meta_top == "low_competence":
            # Uncertain: prefer exploration
            self.subgoal.beliefs.update({
                "explore": 0.5,
                "exploit": 0.2,
                "consolidate": 0.3,
            }, learning_rate=0.05)

        subgoal_top, subgoal_conf = self.subgoal.beliefs.get_top_hypothesis()

        # Subgoal → Action
        if subgoal_top == "explore":
            self.action.beliefs.update({
                "plan_first": 0.5,
                "direct_execute": 0.2,
                "seek_help": 0.3,
            }, learning_rate=0.05)
        elif subgoal_top == "exploit":
            self.action.beliefs.update({
                "direct_execute": 0.5,
                "plan_first": 0.3,
                "seek_help": 0.2,
            }, learning_rate=0.05)
        elif subgoal_top == "consolidate":
            self.action.beliefs.update({
                "plan_first": 0.4,
                "direct_execute": 0.3,
                "seek_help": 0.3,
            }, learning_rate=0.05)

    def _update_precisions(self, prediction_errors: List[dict]) -> None:
        """
        Update precision weights based on prediction errors.

        High prediction error → decrease precision (less confident)
        Low prediction error → increase precision (more confident)
        """
        for pe in prediction_errors:
            error = abs(pe.get("error", 0))
            source = pe.get("source", "action")
            level_obj = self._get_level(source)
            if level_obj is None:
                continue

            if error > 0.5:
                # Big surprise → decrease precision
                level_obj.beliefs.precision = max(
                    MIN_PRECISION,
                    level_obj.beliefs.precision - PRECISION_LR * error
                )
            else:
                # Good prediction → increase precision
                level_obj.beliefs.precision = min(
                    MAX_PRECISION,
                    level_obj.beliefs.precision + PRECISION_LR * (1 - error)
                )

    def _get_level(self, name: str) -> Optional[HierarchicalLevel]:
        """Get level by name."""
        if name == "meta":
            return self.meta
        elif name == "subgoal":
            return self.subgoal
        elif name == "action":
            return self.action
        return None

    def _publish_prediction_error(self, error_info: dict) -> None:
        """Publish prediction error event to global workspace."""
        try:
            from brain.workspace_events import EventType, WorkspaceEvent

            event = WorkspaceEvent(
                source="hierarchical_active_inference",
                type=EventType.PREDICTION,
                content={
                    "prediction_error": error_info.get("error", 0),
                    "source_level": error_info.get("source", "unknown"),
                    "description": error_info.get("observation", ""),
                },
                importance=min(1.0, abs(error_info.get("error", 0))),
            )

            # Try to publish to workspace (may not be running)
            try:
                import asyncio
                from brain.global_workspace import get_global_workspace
                workspace = get_global_workspace()
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(workspace.publish(event), loop)
            except (RuntimeError, ImportError):
                pass  # Workspace not available
        except Exception as exc:
            print(f"[HierarchicalAIF] Event publish error: {exc}")

    # ── Integration ─────────────────────────────────────────────────────

    def integrate_with_flat_aif(self) -> dict:
        """
        Synchronize with the existing flat ActiveInferenceEngine.

        Pulls tool-level predictions from the flat model into the action level.
        """
        try:
            from brain.active_inference import get_active_inference
            flat = get_active_inference()

            stats = flat.get_stats()
            uncertain = flat.get_uncertain_tools(threshold=0.5)

            # Feed uncertainty into action-level beliefs
            if uncertain:
                uncertainty_level = sum(u for _, u in uncertain) / len(uncertain)
                if uncertainty_level > 0.7:
                    self.action.beliefs.update({
                        "plan_first": 0.5,
                        "seek_help": 0.3,
                        "direct_execute": 0.2,
                    }, learning_rate=0.03)

            return {
                "flat_tools_tracked": stats.get("tools_tracked", 0),
                "flat_avg_accuracy": stats.get("avg_prediction_accuracy", 0),
                "uncertain_tools": len(uncertain),
                "integrated": True,
            }
        except ImportError:
            return {"integrated": False, "reason": "active_inference not available"}
        except Exception as exc:
            return {"integrated": False, "reason": str(exc)}

    # ── Stats & Prompt ──────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get hierarchical active inference statistics."""
        with self._lock:
            recent_errors = self._prediction_errors[-20:]
            avg_error = (
                sum(abs(e.get("error", 0)) for e in recent_errors) /
                max(len(recent_errors), 1)
            )

            return {
                "meta": {
                    "top_hypothesis": self.meta.beliefs.get_top_hypothesis()[0],
                    "confidence": round(self.meta.beliefs.get_confidence(), 3),
                    "entropy": round(self.meta.beliefs.get_entropy(), 3),
                    "precision": round(self.meta.beliefs.precision, 3),
                },
                "subgoal": {
                    "top_hypothesis": self.subgoal.beliefs.get_top_hypothesis()[0],
                    "confidence": round(self.subgoal.beliefs.get_confidence(), 3),
                    "entropy": round(self.subgoal.beliefs.get_entropy(), 3),
                    "precision": round(self.subgoal.beliefs.precision, 3),
                },
                "action": {
                    "top_hypothesis": self.action.beliefs.get_top_hypothesis()[0],
                    "confidence": round(self.action.beliefs.get_confidence(), 3),
                    "entropy": round(self.action.beliefs.get_entropy(), 3),
                    "precision": round(self.action.beliefs.precision, 3),
                },
                "prediction_errors_recent": len(recent_errors),
                "avg_prediction_error": round(avg_error, 3),
                "session_count": self._session_count,
            }

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """
        Format hierarchical state for system prompt injection.
        Gives FRIDAY awareness of her own cognitive state across levels.
        """
        stats = self.get_stats()

        parts = [
            "[HIERARCHICAL ACTIVE INFERENCE — Cognitive state]",
            "",
            "Meta (strategic):",
            f"  Belief: {stats['meta']['top_hypothesis']} "
            f"(confidence: {stats['meta']['confidence']:.0%})",
            f"  Precision: {stats['meta']['precision']:.2f}",
            "",
            "Subgoal (tactical):",
            f"  Belief: {stats['subgoal']['top_hypothesis']} "
            f"(confidence: {stats['subgoal']['confidence']:.0%})",
            f"  Precision: {stats['subgoal']['precision']:.2f}",
            "",
            "Action (motor):",
            f"  Belief: {stats['action']['top_hypothesis']} "
            f"(confidence: {stats['action']['confidence']:.0%})",
            f"  Precision: {stats['action']['precision']:.2f}",
        ]

        if stats["prediction_errors_recent"] > 0:
            parts.append(
                f"\nRecent prediction errors: {stats['prediction_errors_recent']} "
                f"(avg: {stats['avg_prediction_error']:.2f})"
            )

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars].rsplit("\n", 1)[0] + "\n[...]"
        return result


# ── Singleton ───────────────────────────────────────────────────────────────

_hai: Optional[HierarchicalActiveInference] = None
_hai_lock = threading.Lock()


def get_hierarchical_aif() -> HierarchicalActiveInference:
    """Get singleton HierarchicalActiveInference instance."""
    global _hai
    if _hai is None:
        with _hai_lock:
            if _hai is None:
                _hai = HierarchicalActiveInference()
    return _hai
