#!/usr/bin/env python3
"""
world_model.py — FRIDAY Latent Dynamics Prediction Model
=========================================================

Maintains a latent space representation of experiences, predicts outcomes
of action sequences (mental simulation), and tracks prediction accuracy.

Inspired by world models in model-based reinforcement learning:
- Encoder: maps experiences to latent vectors
- Transition model: predicts latent state changes from actions
- Evaluation: scores plans before execution
- Learning: updates dynamics from observed outcomes
"""

import json
import math
import random
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from collections import defaultdict


BRAIN_DIR = Path(__file__).parent.resolve()
DATA_FILE = BRAIN_DIR / "world_model_data.json"

# Configuration
MAX_EXPERIENCES = 1000          # Max stored experiences
LATENT_DIM = 16                 # Latent space dimensionality
PREDICTION_DECAY = 0.95         # Confidence decay per prediction step
TRANSITION_LEARNING_RATE = 0.1  # How fast transition weights update
MAX_FEATURE_HISTORY = 200       # Feature vectors to keep


def _timestamp() -> str:
    return datetime.now().isoformat()


def _sigmoid(x: float) -> float:
    """Sigmoid activation."""
    try:
        return 1.0 / (1.0 + math.exp(-max(-10, min(10, x))))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


class WorldModel:
    """
    Latent dynamics prediction model for FRIDAY.

    Maintains a latent space where experiences are encoded as vectors,
    learns transition dynamics, and can simulate action sequences to
    predict outcomes before execution.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._experiences: List[dict] = []
        self._latent_vectors: List[List[float]] = []
        self._feature_names: List[str] = [
            "complexity", "success_rate", "tool_familiarity",
            "context_richness", "error_proneness", "novelty",
            "urgency", "resource_demand", "dependency_depth",
            "confidence", "recency", "category_strength",
            "action_diversity", "outcome_predictability",
            "learning_potential", "risk_level",
        ]
        # Transition weights: simple linear model
        # W[action_type] maps input features → output feature deltas
        self._transition_weights: Dict[str, List[List[float]]] = {}
        # Prediction tracking
        self._prediction_errors: List[float] = []
        self._total_experiences: int = 0
        self._total_predictions: int = 0
        self._created_at: str = _timestamp()
        self._load()
        print("[WorldModel] Initialized")

    # ── Persistence ──────────────────────────────────────────────────────

    def _empty_data(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": _timestamp(),
                "last_updated": _timestamp(),
            },
            "experiences": [],
            "latent_vectors": [],
            "transition_weights": {},
            "prediction_errors": [],
            "total_experiences": 0,
            "total_predictions": 0,
        }

    def _load(self):
        if not DATA_FILE.exists():
            return
        try:
            raw = DATA_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._experiences = data.get("experiences", [])[-MAX_EXPERIENCES:]
            self._latent_vectors = data.get("latent_vectors", [])[-MAX_FEATURE_HISTORY:]
            self._transition_weights = data.get("transition_weights", {})
            self._prediction_errors = data.get("prediction_errors", [])[-200:]
            self._total_experiences = data.get("total_experiences", 0)
            self._total_predictions = data.get("total_predictions", 0)
            print(f"[WorldModel] Loaded {self._total_experiences} experiences, "
                  f"{len(self._latent_vectors)} latent vectors")
        except (json.JSONDecodeError, IOError) as e:
            print(f"[WorldModel] Load error: {e}")

    def save(self):
        """Persist world model data to disk."""
        with self._lock:
            self._save_unlocked()

    def _save_unlocked(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                "meta": {
                    "version": 1,
                    "created": self._created_at,
                    "last_updated": _timestamp(),
                },
                "experiences": self._experiences[-MAX_EXPERIENCES:],
                "latent_vectors": self._latent_vectors[-MAX_FEATURE_HISTORY:],
                "transition_weights": self._transition_weights,
                "prediction_errors": self._prediction_errors[-200:],
                "total_experiences": self._total_experiences,
                "total_predictions": self._total_predictions,
            }
            tmp = DATA_FILE.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(DATA_FILE)
        except Exception as e:
            print(f"[WorldModel] Save error: {e}")

    # ── Encoding ─────────────────────────────────────────────────────────

    def encode_experience(self, experience: dict) -> list:
        """
        Encode an experience dict into a latent vector.

        Maps experience features to a fixed-dimensional latent space
        using learned or heuristic feature extraction.

        Args:
            experience: dict with keys like tool, success, complexity, context, etc.

        Returns:
            list of floats (latent vector of length LATENT_DIM)
        """
        with self._lock:
            self._total_experiences += 1

            # Extract features from experience
            features = self._extract_features(experience)

            # Encode to latent space via feature hashing + normalization
            latent = self._features_to_latent(features)

            # Store
            self._experiences.append({
                "timestamp": _timestamp(),
                "raw": {k: str(v)[:200] for k, v in experience.items()},
                "features": features,
            })
            if len(self._experiences) > MAX_EXPERIENCES:
                self._experiences = self._experiences[-MAX_EXPERIENCES:]

            self._latent_vectors.append(latent)
            if len(self._latent_vectors) > MAX_FEATURE_HISTORY:
                self._latent_vectors = self._latent_vectors[-MAX_FEATURE_HISTORY:]

            # Update transition model with this new observation
            self._update_transitions(experience, features, latent)

            self._save_unlocked()
            return latent

    def _extract_features(self, experience: dict) -> Dict[str, float]:
        """Extract normalized feature values from an experience."""
        features = {}

        # Complexity: from experience or estimate
        features["complexity"] = float(experience.get("complexity", 0.5))
        features["complexity"] = max(0.0, min(1.0, features["complexity"]))

        # Success signal
        success = experience.get("success", None)
        if success is True:
            features["success_rate"] = 1.0
        elif success is False:
            features["success_rate"] = 0.0
        else:
            features["success_rate"] = 0.5

        # Tool familiarity: how often we've seen this tool
        tool = experience.get("tool", "unknown")
        tool_count = sum(
            1 for e in self._experiences
            if e.get("raw", {}).get("tool") == tool
        )
        features["tool_familiarity"] = min(1.0, tool_count / 10.0)

        # Context richness
        context = str(experience.get("context", ""))
        features["context_richness"] = min(1.0, len(context) / 500.0)

        # Error proneness
        error = str(experience.get("error", ""))
        features["error_proneness"] = min(1.0, len(error) / 200.0) if error else 0.0

        # Novelty: inverse of familiarity
        features["novelty"] = 1.0 - features["tool_familiarity"]

        # Urgency
        features["urgency"] = float(experience.get("urgency", 0.5))
        features["urgency"] = max(0.0, min(1.0, features["urgency"]))

        # Resource demand
        features["resource_demand"] = float(experience.get("resource_demand", 0.3))
        features["resource_demand"] = max(0.0, min(1.0, features["resource_demand"]))

        # Dependency depth
        features["dependency_depth"] = float(experience.get("dependency_depth", 0.3))
        features["dependency_depth"] = max(0.0, min(1.0, features["dependency_depth"]))

        # Confidence from self-model if available
        features["confidence"] = float(experience.get("confidence", 0.5))
        features["confidence"] = max(0.0, min(1.0, features["confidence"]))

        # Recency: always 1.0 for new, decays for stored
        features["recency"] = 1.0

        # Category strength
        features["category_strength"] = 0.5

        # Action diversity
        features["action_diversity"] = 0.5

        # Outcome predictability
        features["outcome_predictability"] = 0.5

        # Learning potential
        features["learning_potential"] = features["novelty"] * 0.7 + 0.3

        # Risk level
        features["risk_level"] = (
            features["error_proneness"] * 0.4
            + features["novelty"] * 0.3
            + (1.0 - features["confidence"]) * 0.3
        )

        return features

    def _features_to_latent(self, features: Dict[str, float]) -> List[float]:
        """Map feature dict to fixed-dim latent vector via hashing."""
        latent = [0.0] * LATENT_DIM

        for name, value in features.items():
            # Deterministic hash to assign feature to latent dimensions
            h = hash(name) % LATENT_DIM
            latent[h] += value * 0.5

            # Also influence neighbor dimension for smoothness
            h2 = (h + 1) % LATENT_DIM
            latent[h2] += value * 0.2

        # Normalize
        norm = math.sqrt(sum(v * v for v in latent))
        if norm > 0:
            latent = [v / norm for v in latent]

        return [round(v, 6) for v in latent]

    def _update_transitions(self, experience: dict, features: Dict[str, float],
                            latent: List[float]):
        """Update transition model weights from new observation."""
        action_type = experience.get("tool", "default")

        if action_type not in self._transition_weights:
            # Initialize with small random weights
            self._transition_weights[action_type] = [
                [random.uniform(-0.01, 0.01) for _ in range(LATENT_DIM)]
                for _ in range(LATENT_DIM)
            ]

        # Simple gradient-like update: push transition weights toward
        # reproducing the observed latent vector
        if len(self._latent_vectors) >= 2:
            prev_latent = self._latent_vectors[-2]
            W = self._transition_weights[action_type]

            for i in range(LATENT_DIM):
                for j in range(LATENT_DIM):
                    # Target: prev + W * action ≈ current
                    error = latent[i] - prev_latent[i]
                    W[i][j] += TRANSITION_LEARNING_RATE * error * prev_latent[j]
                    # Clamp to prevent explosion
                    W[i][j] = max(-1.0, min(1.0, W[i][j]))

    # ── State Features ───────────────────────────────────────────────────

    def get_state_features(self) -> dict:
        """
        Get current latent space state features.

        Returns:
            dict with feature_count, latent_vector, feature_names
        """
        with self._lock:
            if not self._latent_vectors:
                return {
                    "feature_count": len(self._feature_names),
                    "latent_vector": [0.0] * LATENT_DIM,
                    "feature_names": self._feature_names,
                }

            # Average latent vector from recent experiences
            recent = self._latent_vectors[-10:]
            avg_latent = [0.0] * LATENT_DIM
            for vec in recent:
                for i in range(min(LATENT_DIM, len(vec))):
                    avg_latent[i] += vec[i]
            avg_latent = [v / len(recent) for v in avg_latent]

            return {
                "feature_count": len(self._feature_names),
                "latent_vector": [round(v, 6) for v in avg_latent],
                "feature_names": self._feature_names,
            }

    # ── Trajectory Imagination ───────────────────────────────────────────

    def imagine_trajectory(self, start_state: dict, action_sequence: list,
                           horizon: int = 5) -> list:
        """
        Simulate a sequence of actions from a start state, predicting
        resulting states at each step.

        Args:
            start_state: dict mapping feature names to values
            action_sequence: list of action dicts (each has at least 'tool')
            horizon: max steps to simulate

        Returns:
            list of predicted state dicts
        """
        with self._lock:
            self._total_predictions += 1

            trajectory = []
            current_features = self._state_dict_to_features(start_state)
            steps = min(len(action_sequence), horizon)

            for step in range(steps):
                action = action_sequence[step] if isinstance(action_sequence[step], dict) else {"tool": str(action_sequence[step])}
                action_type = action.get("tool", "default")

                # Predict next state using transition model
                predicted_features = self._predict_next_state(current_features, action_type, step)

                state = {
                    "step": step,
                    "action": action_type,
                    "features": {k: round(v, 4) for k, v in predicted_features.items()},
                    "confidence": round(max(0.1, 1.0 - step * (1.0 - PREDICTION_DECAY)), 4),
                }
                trajectory.append(state)
                current_features = predicted_features

            return trajectory

    def _state_dict_to_features(self, state: dict) -> Dict[str, float]:
        """Convert a state dict to normalized feature values."""
        features = {}
        for name in self._feature_names:
            if name in state:
                features[name] = max(0.0, min(1.0, float(state[name])))
            else:
                features[name] = 0.5
        return features

    def _predict_next_state(self, current: Dict[str, float],
                            action_type: str, step: int) -> Dict[str, float]:
        """Predict next state features given current state and action."""
        predicted = dict(current)

        if action_type in self._transition_weights:
            W = self._transition_weights[action_type]
            current_latent = self._features_to_latent(current)

            # Apply transition: new_latent = W * current_latent
            new_latent = [0.0] * LATENT_DIM
            for i in range(LATENT_DIM):
                for j in range(LATENT_DIM):
                    if i < len(W) and j < len(W[i]) and j < len(current_latent):
                        new_latent[i] += W[i][j] * current_latent[j]

            # Map back to features (inverse of _features_to_latent heuristic)
            for idx, name in enumerate(self._feature_names):
                h = hash(name) % LATENT_DIM
                h2 = (h + 1) % LATENT_DIM
                # Reconstruct from latent contributions
                raw_value = (new_latent[h] * 2.0 + new_latent[h2] * 0.5) if h < LATENT_DIM and h2 < LATENT_DIM else 0.0
                predicted[name] = max(0.0, min(1.0, _sigmoid(raw_value)))
        else:
            # No transition model for this action — apply heuristic perturbation
            success_delta = 0.1 if action_type not in ("error", "unknown") else -0.1
            predicted["success_rate"] = max(0.0, min(1.0,
                current["success_rate"] + success_delta * (PREDICTION_DECAY ** step)))
            predicted["recency"] = max(0.0, current["recency"] * PREDICTION_DECAY)
            predicted["tool_familiarity"] = min(1.0, current["tool_familiarity"] + 0.05)

        return predicted

    # ── Plan Evaluation ──────────────────────────────────────────────────

    def evaluate_plan(self, action_sequence: list) -> dict:
        """
        Evaluate a plan (action sequence) by simulating it and scoring.

        Returns:
            dict with evaluation metrics:
            - predicted_success: overall predicted success probability
            - risk_score: estimated risk
            - confidence: confidence in the prediction
            - steps_evaluated: how many steps were simulated
            - trajectory: the imagined trajectory
        """
        with self._lock:
            if not action_sequence:
                return {
                    "predicted_success": 0.5,
                    "risk_score": 0.5,
                    "confidence": 0.0,
                    "steps_evaluated": 0,
                }

            # Start from current latent state
            features = self.get_state_features()
            start_state = {}
            latent = features.get("latent_vector", [])
            names = features.get("feature_names", [])
            if latent and names:
                for i, name in enumerate(names):
                    if i < len(latent):
                        start_state[name] = latent[i]
                    else:
                        start_state[name] = 0.5

            trajectory = self.imagine_trajectory(start_state, action_sequence, horizon=5)

            if not trajectory:
                return {
                    "predicted_success": 0.5,
                    "risk_score": 0.5,
                    "confidence": 0.0,
                    "steps_evaluated": 0,
                }

            # Aggregate metrics across trajectory
            success_values = [
                s["features"].get("success_rate", 0.5) for s in trajectory
            ]
            risk_values = [
                s["features"].get("risk_level", 0.5) for s in trajectory
            ]
            confidences = [s["confidence"] for s in trajectory]

            predicted_success = sum(success_values) / len(success_values)
            risk_score = sum(risk_values) / len(risk_values)
            avg_confidence = sum(confidences) / len(confidences)

            return {
                "predicted_success": round(predicted_success, 4),
                "risk_score": round(risk_score, 4),
                "confidence": round(avg_confidence, 4),
                "steps_evaluated": len(trajectory),
                "trajectory_summary": [
                    {"step": s["step"], "action": s["action"],
                     "success_pred": s["features"].get("success_rate", 0.5)}
                    for s in trajectory
                ],
            }

    # ── Stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get world model statistics."""
        with self._lock:
            avg_error = (
                sum(self._prediction_errors) / len(self._prediction_errors)
                if self._prediction_errors else None
            )
            return {
                "total_experiences": self._total_experiences,
                "total_predictions": self._total_predictions,
                "stored_experiences": len(self._experiences),
                "latent_vectors": len(self._latent_vectors),
                "transition_models": len(self._transition_weights),
                "avg_prediction_error": round(avg_error, 4) if avg_error is not None else None,
                "latent_dim": LATENT_DIM,
                "feature_count": len(self._feature_names),
            }

    # ── Prompt Formatting ────────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 400) -> str:
        """Format world model state for system prompt inclusion."""
        with self._lock:
            stats = self.get_stats()
            if stats["total_experiences"] == 0:
                return ""

            parts = ["[WORLD MODEL — Internal simulation state]"]
            parts.append(f"  Experiences: {stats['total_experiences']} | "
                         f"Predictions: {stats['total_predictions']} | "
                         f"Transition models: {stats['transition_models']}")

            if stats["avg_prediction_error"] is not None:
                accuracy = 1.0 - stats["avg_prediction_error"]
                parts.append(f"  Prediction accuracy: {accuracy:.0%}")

            result = "\n".join(parts)
            if len(result) > max_chars:
                result = result[:max_chars].rsplit("\n", 1)[0] + "\n  [...]"
            return result


# ── Singleton ───────────────────────────────────────────────────────────────

_instance: Optional[WorldModel] = None
_instance_lock = threading.Lock()


def get_world_model() -> WorldModel:
    """Get the singleton world model instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = WorldModel()
    return _instance


# ── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    wm = get_world_model()

    print("Encoding test experiences...")
    for i in range(5):
        exp = {
            "tool": f"tool_{i % 3}",
            "success": i % 3 != 0,
            "complexity": 0.3 + (i * 0.15),
            "context": f"test context {i}",
        }
        latent = wm.encode_experience(exp)
        print(f"  Experience {i}: latent[:4] = {latent[:4]}")

    features = wm.get_state_features()
    print(f"\nState features: {features['feature_count']} dims")

    trajectory = wm.imagine_trajectory(
        start_state={"complexity": 0.5, "success_rate": 0.7},
        action_sequence=[
            {"tool": "web_search"},
            {"tool": "code_helper"},
            {"tool": "file_controller"},
        ],
        horizon=3,
    )
    print(f"\nTrajectory ({len(trajectory)} steps):")
    for s in trajectory:
        print(f"  Step {s['step']}: {s['action']} → "
              f"success={s['features'].get('success_rate', '?'):.2f} "
              f"conf={s['confidence']:.2f}")

    evaluation = wm.evaluate_plan([
        {"tool": "web_search"},
        {"tool": "code_helper"},
    ])
    print(f"\nPlan evaluation: {evaluation}")

    wm.save()
    print(f"\nStats: {wm.get_stats()}")
    print(f"\nPrompt format:\n{wm.format_for_prompt()}")
