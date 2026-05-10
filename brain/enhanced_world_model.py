#!/usr/bin/env python3
"""
enhanced_world_model.py — FRIDAY Enhanced World Model
=====================================================

Upgrades the linear world model with:
- Non-linear transitions (2-layer MLP with ReLU)
- Compositional hierarchical states (low/mid/high level)
- Causal transition integration
- Multi-step simulation with branching (15+ steps)
- Ensemble prediction combining linear, nonlinear, and causal methods

Backward-compatible with the WorldModel interface.
All math in pure Python — no numpy, no torch.
"""

import json
import math
import random
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict


BRAIN_DIR = Path(__file__).parent.resolve()
DATA_FILE = BRAIN_DIR / "enhanced_wm_data.json"

# Configuration
MAX_EXPERIENCES = 1000
LATENT_DIM = 16
HIDDEN_DIM = 32
PREDICTION_DECAY = 0.95
TRANSITION_LEARNING_RATE = 0.05
MLP_LEARNING_RATE = 0.01
MAX_FEATURE_HISTORY = 200
MAX_TRAJECTORY_STEPS = 20
BRANCHING_FACTOR = 3
BRANCH_PRUNE_THRESHOLD = 0.15
ENSEMBLE_HISTORY_LEN = 100


def _timestamp() -> str:
    return datetime.now().isoformat()


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-max(-10, min(10, x))))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _relu(x: float) -> float:
    return max(0.0, x)


def _relu_derivative(x: float) -> float:
    return 1.0 if x > 0.0 else 0.0


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _vec_add(a: List[float], b: List[float]) -> List[float]:
    return [x + y for x, y in zip(a, b)]


def _vec_sub(a: List[float], b: List[float]) -> List[float]:
    return [x - y for x, y in zip(a, b)]


def _vec_scale(a: List[float], s: float) -> List[float]:
    return [x * s for x in a]


def _vec_norm(a: List[float]) -> float:
    return math.sqrt(sum(x * x for x in a))


def _mat_vec_mul(mat: List[List[float]], vec: List[float]) -> List[float]:
    return [_dot(row, vec) for row in mat]


def _outer(a: List[float], b: List[float]) -> List[List[float]]:
    return [[ai * bj for bj in b] for ai in a]


# ── NonLinearTransition ─────────────────────────────────────────────────

class NonLinearTransition:
    """
    2-layer MLP transition model with ReLU activation.
    input_dim → hidden_dim (32) → output_dim (same as input_dim)
    Trained via backpropagation from observed state transitions.
    One instance per action type.
    """

    def __init__(self, input_dim: int = LATENT_DIM, hidden_dim: int = HIDDEN_DIM):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = input_dim

        # Xavier-ish initialization
        scale_h = math.sqrt(2.0 / (input_dim + hidden_dim))
        scale_o = math.sqrt(2.0 / (hidden_dim + input_dim))

        # Layer 1: input → hidden
        self.W1 = [
            [random.gauss(0, scale_h) for _ in range(input_dim)]
            for _ in range(hidden_dim)
        ]
        self.b1 = [0.0] * hidden_dim

        # Layer 2: hidden → output
        self.W2 = [
            [random.gauss(0, scale_o) for _ in range(hidden_dim)]
            for _ in range(input_dim)
        ]
        self.b2 = [0.0] * input_dim

        self._train_count = 0

    def forward(self, x: List[float]) -> Tuple[List[float], List[float]]:
        """
        Forward pass. Returns (output, hidden_activations).
        hidden_activations cached for backprop.
        """
        # Hidden layer: z1 = W1 @ x + b1, h1 = relu(z1)
        z1 = [_dot(self.W1[i], x) + self.b1[i] for i in range(self.hidden_dim)]
        h1 = [_relu(z) for z in z1]

        # Output layer: out = W2 @ h1 + b2
        out = [_dot(self.W2[i], h1) + self.b2[i] for i in range(self.output_dim)]

        return out, h1

    def predict(self, x: List[float]) -> List[float]:
        out, _ = self.forward(x)
        return out

    def train_step(self, x: List[float], target: List[float],
                   lr: float = MLP_LEARNING_RATE) -> float:
        """
        One step of backpropagation. Returns MSE loss.
        """
        # Forward
        z1 = [_dot(self.W1[i], x) + self.b1[i] for i in range(self.hidden_dim)]
        h1 = [_relu(z) for z in z1]
        out = [_dot(self.W2[i], h1) + self.b2[i] for i in range(self.output_dim)]

        # Loss: MSE
        errors = [out[i] - target[i] for i in range(self.output_dim)]
        loss = sum(e * e for e in errors) / self.output_dim

        # Backprop output layer
        # d_loss/d_out_i = 2 * error_i / output_dim
        d_out = [2.0 * errors[i] / self.output_dim for i in range(self.output_dim)]

        # Gradients for W2, b2
        d_W2 = _outer(d_out, h1)
        d_b2 = list(d_out)

        # Backprop hidden layer
        # d_h1_j = sum_i(d_out_i * W2[i][j])
        d_h1 = [0.0] * self.hidden_dim
        for j in range(self.hidden_dim):
            for i in range(self.output_dim):
                d_h1[j] += d_out[i] * self.W2[i][j]

        # Through ReLU
        d_z1 = [d_h1[j] * _relu_derivative(z1[j]) for j in range(self.hidden_dim)]

        # Gradients for W1, b1
        d_W1 = _outer(d_z1, x)
        d_b1 = list(d_z1)

        # Update weights
        for i in range(self.output_dim):
            for j in range(self.hidden_dim):
                self.W2[i][j] -= lr * d_W2[i][j]
            self.b2[i] -= lr * d_b2[i]

        for i in range(self.hidden_dim):
            for j in range(self.input_dim):
                self.W1[i][j] -= lr * d_W1[i][j]
            self.b1[i] -= lr * d_b1[i]

        self._train_count += 1
        return loss

    def to_dict(self) -> dict:
        return {
            "W1": self.W1, "b1": self.b1,
            "W2": self.W2, "b2": self.b2,
            "input_dim": self.input_dim,
            "hidden_dim": self.hidden_dim,
            "train_count": self._train_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NonLinearTransition":
        obj = cls(d["input_dim"], d["hidden_dim"])
        obj.W1 = d["W1"]
        obj.b1 = d["b1"]
        obj.W2 = d["W2"]
        obj.b2 = d["b2"]
        obj._train_count = d.get("train_count", 0)
        return obj


# ── CompositionalState ──────────────────────────────────────────────────

# Mid-level cluster labels and their feature ranges
_MID_LEVEL_LABELS = {
    "challenging":   {"complexity": (0.6, 1.0), "confidence": (0.0, 0.4)},
    "routine":       {"complexity": (0.0, 0.4), "confidence": (0.5, 1.0)},
    "exploratory":   {"novelty": (0.6, 1.0), "tool_familiarity": (0.0, 0.4)},
    "mastered":      {"tool_familiarity": (0.7, 1.0), "success_rate": (0.7, 1.0)},
    "risky":         {"risk_level": (0.6, 1.0), "error_proneness": (0.4, 1.0)},
    "efficient":     {"resource_demand": (0.0, 0.3), "success_rate": (0.6, 1.0)},
    "complex":       {"dependency_depth": (0.6, 1.0), "complexity": (0.5, 1.0)},
}

# High-level summary rules: map (mid-level combo + success) → summary
_HIGH_LEVEL_RULES = [
    ({"challenging", "risky"}, False, "stuck"),
    ({"challenging"}, True, "on track"),
    ({"exploratory"}, None, "exploring"),
    ({"mastered"}, True, "on track"),
    ({"mastered"}, False, "setback"),
    ({"routine"}, True, "on track"),
    ({"routine"}, False, "setback"),
    ({"efficient"}, True, "on track"),
    ({"complex"}, False, "stuck"),
]


class CompositionalState:
    """
    Hierarchical state representation with three levels:
    - Low-level: raw feature vector (16-dim)
    - Mid-level: abstract state clusters
    - High-level: goal-relevant summary
    """

    def __init__(self):
        self._custom_clusters: Dict[str, Dict[str, Tuple[float, float]]] = {}

    def abstract(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Given a flat feature dict, produce a three-level compositional state.

        Returns dict with:
          - low_level: the raw features
          - mid_level: set of matching cluster labels
          - high_level: summary string
          - description: human-readable state description
        """
        low = dict(features)

        # Mid-level: check each cluster definition
        mid_labels = set()
        for label, ranges in self._all_clusters().items():
            match = True
            for feat, (lo, hi) in ranges.items():
                val = features.get(feat, 0.5)
                if val < lo or val > hi:
                    match = False
                    break
            if match:
                mid_labels.add(label)

        # If no cluster matched, assign to the closest one
        if not mid_labels:
            mid_labels.add(self._closest_cluster(features))

        # High-level summary
        success = features.get("success_rate", 0.5)
        success_bool = success > 0.6 if success != 0.5 else None
        high = self._derive_high_level(mid_labels, success_bool)

        # Human-readable description
        mid_desc = ", ".join(sorted(mid_labels)) if mid_labels else "neutral"
        desc = f"{high} ({mid_desc})"

        return {
            "low_level": low,
            "mid_level": sorted(mid_labels),
            "high_level": high,
            "description": desc,
        }

    def add_cluster(self, label: str,
                    feature_ranges: Dict[str, Tuple[float, float]]):
        """Register a custom mid-level cluster."""
        self._custom_clusters[label] = feature_ranges

    def _all_clusters(self) -> Dict[str, Dict[str, Tuple[float, float]]]:
        merged = dict(_MID_LEVEL_LABELS)
        merged.update(self._custom_clusters)
        return merged

    def _closest_cluster(self, features: Dict[str, float]) -> str:
        best_label = "neutral"
        best_score = float("inf")
        for label, ranges in self._all_clusters().items():
            dist = 0.0
            for feat, (lo, hi) in ranges.items():
                val = features.get(feat, 0.5)
                mid = (lo + hi) / 2.0
                dist += (val - mid) ** 2
            if dist < best_score:
                best_score = dist
                best_label = label
        return best_label

    def _derive_high_level(self, mid_labels: set,
                           success: Optional[bool]) -> str:
        for required, succ_req, summary in _HIGH_LEVEL_RULES:
            if required.issubset(mid_labels):
                if succ_req is None or succ_req == success:
                    return summary
        # Default heuristic
        if success is True:
            return "on track"
        if success is False:
            return "setback"
        return "exploring"

    def to_dict(self) -> dict:
        return {"custom_clusters": {
            k: {fk: list(fv) for fk, fv in v.items()}
            for k, v in self._custom_clusters.items()
        }}

    @classmethod
    def from_dict(cls, d: dict) -> "CompositionalState":
        obj = cls()
        raw = d.get("custom_clusters", {})
        for label, ranges in raw.items():
            obj._custom_clusters[label] = {
                fk: tuple(fv) for fk, fv in ranges.items()
            }
        return obj


# ── CausalTransition ────────────────────────────────────────────────────

class CausalTransition:
    """
    Causal-graph-constrained transition predictions.
    Uses a causal graph (DAG) to constrain and intervene on predictions.
    """

    def __init__(self):
        # Causal graph: parent → list of children with edge weights
        # e.g., {"complexity": [("error_proneness", 0.6), ...]}
        self._causal_graph: Dict[str, List[Tuple[str, float]]] = {}
        self._reverse_graph: Dict[str, List[Tuple[str, float]]] = {}

    def set_causal_graph(self, graph: Dict[str, List[Tuple[str, float]]]):
        """Set the causal graph. Each key maps to [(child, weight), ...]."""
        self._causal_graph = graph
        self._reverse_graph = defaultdict(list)
        for parent, children in graph.items():
            for child, weight in children:
                self._reverse_graph[child].append((parent, weight))

    def learn_causal_edge(self, cause: str, effect: str,
                          strength: float):
        """Add or update a causal edge."""
        if cause not in self._causal_graph:
            self._causal_graph[cause] = []
        # Update existing or add
        found = False
        for i, (child, _) in enumerate(self._causal_graph[cause]):
            if child == effect:
                # Exponential moving average
                old_w = self._causal_graph[cause][i][1]
                new_w = old_w * 0.7 + strength * 0.3
                self._causal_graph[cause][i] = (child, new_w)
                found = True
                break
        if not found:
            self._causal_graph[cause].append((effect, strength))

        # Rebuild reverse
        self._reverse_graph = defaultdict(list)
        for parent, children in self._causal_graph.items():
            for child, weight in children:
                self._reverse_graph[child].append((parent, weight))

    def constrain_prediction(self, predicted: Dict[str, float],
                             current: Dict[str, float]) -> Dict[str, float]:
        """
        Use causal graph to adjust predictions.
        If a parent changed significantly, propagate to children.
        """
        constrained = dict(predicted)

        for parent, children in self._causal_graph.items():
            parent_delta = predicted.get(parent, 0.5) - current.get(parent, 0.5)
            if abs(parent_delta) < 0.01:
                continue
            for child, weight in children:
                # Propagate weighted effect
                effect = parent_delta * weight
                old_val = constrained.get(child, 0.5)
                constrained[child] = _clamp(old_val + effect * 0.3, 0.0, 1.0)

        return constrained

    def intervene(self, features: Dict[str, float],
                  intervention: Dict[str, float]) -> Dict[str, float]:
        """
        Simulate a causal intervention: set specific variables to new values
        and propagate effects through the causal graph.
        """
        result = dict(features)
        # Apply intervention (do-calculus style: override values)
        for var, val in intervention.items():
            result[var] = val

        # Propagate downstream effects via topological BFS
        visited = set(intervention.keys())
        queue = list(intervention.keys())

        while queue:
            current_var = queue.pop(0)
            children = self._causal_graph.get(current_var, [])
            for child, weight in children:
                if child in visited:
                    continue
                # Effect = delta in parent * edge weight
                parent_delta = result[current_var] - features.get(current_var, 0.5)
                effect = parent_delta * weight
                result[child] = _clamp(
                    result.get(child, 0.5) + effect, 0.0, 1.0
                )
                visited.add(child)
                queue.append(child)

        return result

    def to_dict(self) -> dict:
        return {"causal_graph": {
            k: [list(e) for e in v]
            for k, v in self._causal_graph.items()
        }}

    @classmethod
    def from_dict(cls, d: dict) -> "CausalTransition":
        obj = cls()
        raw = d.get("causal_graph", {})
        for parent, edges in raw.items():
            obj._causal_graph[parent] = [(e[0], e[1]) for e in edges]
        # Rebuild reverse
        obj._reverse_graph = defaultdict(list)
        for p, children in obj._causal_graph.items():
            for c, w in children:
                obj._reverse_graph[c].append((p, w))
        return obj


# ── MultiStepSimulation ────────────────────────────────────────────────

class _Branch:
    """A single simulation branch with state and accumulated confidence."""

    __slots__ = ("state", "confidence", "path", "pruned", "_trajectory")

    def __init__(self, state: Dict[str, float], confidence: float,
                 path: List[str]):
        self.state = state
        self.confidence = confidence
        self.path = path
        self.pruned = False
        self._trajectory: List[Dict[str, Any]] = []


class MultiStepSimulation:
    """
    Longer-horizon trajectory imagination (15-20 steps) with branching.
    Simulates multiple alternative futures in parallel, pruning low-confidence
    branches early.
    """

    def __init__(self, max_steps: int = MAX_TRAJECTORY_STEPS,
                 branching: int = BRANCHING_FACTOR,
                 prune_threshold: float = BRANCH_PRUNE_THRESHOLD):
        self.max_steps = max_steps
        self.branching = branching
        self.prune_threshold = prune_threshold

    def simulate(self, start_state: Dict[str, float],
                 action_sequence: list,
                 predict_fn,  # Callable: (state, action_type, step) -> state
                 horizon: Optional[int] = None,
                 num_branches: int = 1) -> List[Dict[str, Any]]:
        """
        Run multi-step simulation with optional branching.

        Args:
            start_state: initial feature dict
            action_sequence: list of action dicts or strings
            predict_fn: function(state, action_type, step) -> predicted_state
            horizon: max steps (default: self.max_steps)
            num_branches: how many parallel branches to explore

        Returns:
            List of branch results, each with trajectory, confidence, path
        """
        horizon = horizon or self.max_steps
        horizon = min(horizon, len(action_sequence), self.max_steps)
        num_branches = max(1, min(num_branches, self.branching))

        branches: List[_Branch] = []
        for b in range(num_branches):
            # Add small noise to start state for diversity
            noisy_state = {}
            for k, v in start_state.items():
                noise = random.gauss(0, 0.02) if b > 0 else 0.0
                noisy_state[k] = max(0.0, min(1.0, v + noise))
            branches.append(_Branch(noisy_state, 1.0, []))

        all_results = []

        for step in range(horizon):
            action = action_sequence[step]
            if isinstance(action, dict):
                action_type = action.get("tool", "default")
            else:
                action_type = str(action)

            surviving = [b for b in branches if not b.pruned]
            if not surviving:
                break

            new_branches = []
            for branch in surviving:
                # Predict next state
                predicted = predict_fn(branch.state, action_type, step)

                # Confidence decay (linear per step, not compounding)
                branch.confidence *= PREDICTION_DECAY
                branch.state = predicted
                branch.path.append(action_type)

                # Record step
                branch_entry = {
                    "step": step,
                    "action": action_type,
                    "features": {k: round(v, 4) for k, v in predicted.items()},
                    "confidence": round(branch.confidence, 4),
                }
                branch._trajectory.append(branch_entry)

                # Prune check
                if branch.confidence < self.prune_threshold:
                    branch.pruned = True

                new_branches.append(branch)

            branches = new_branches

        # Collect results from all branches
        for branch in branches:
            traj = branch._trajectory
            all_results.append({
                "trajectory": traj,
                "final_confidence": round(branch.confidence, 4),
                "path": branch.path,
                "pruned": branch.pruned,
                "steps_simulated": len(traj),
            })

        return all_results


# ── EnsembleTransition ─────────────────────────────────────────────────

class EnsembleTransition:
    """
    Combines multiple prediction methods (linear, nonlinear, causal)
    with weighted averaging based on past accuracy.
    """

    def __init__(self):
        # Weights for each method (normalized internally)
        self._weights: Dict[str, float] = {
            "linear": 0.33,
            "nonlinear": 0.34,
            "causal": 0.33,
        }
        # Per-method error tracking (recent window)
        self._errors: Dict[str, List[float]] = {
            "linear": [],
            "nonlinear": [],
            "causal": [],
        }
        self._update_count = 0

    def predict(self,
                linear_fn,      # Callable: state -> predicted_state
                nonlinear_fn,   # Callable: state -> predicted_state
                causal_fn,      # Callable: state -> predicted_state (or None)
                current_state: Dict[str, float]) -> Dict[str, float]:
        """
        Produce an ensemble prediction by weighted averaging.
        """
        predictions = {}
        predictions["linear"] = linear_fn(current_state)
        predictions["nonlinear"] = nonlinear_fn(current_state)

        if causal_fn is not None:
            predictions["causal"] = causal_fn(current_state)
        else:
            # Fall back to linear if no causal model
            predictions["causal"] = predictions["linear"]

        # Weighted average
        result = {}
        all_keys = set()
        for p in predictions.values():
            all_keys.update(p.keys())

        for key in all_keys:
            weighted_sum = 0.0
            weight_total = 0.0
            for method, pred in predictions.items():
                w = self._weights.get(method, 0.0)
                weighted_sum += pred.get(key, 0.5) * w
                weight_total += w
            result[key] = weighted_sum / weight_total if weight_total > 0 else 0.5

        return result

    def update_weights(self, actual: Dict[str, float],
                       predictions: Dict[str, Dict[str, float]]):
        """
        Update method weights based on prediction errors.
        predictions: {"linear": {...}, "nonlinear": {...}, "causal": {...}}
        """
        for method, pred in predictions.items():
            if method not in self._errors:
                continue
            # Compute MSE for this method
            error = 0.0
            count = 0
            for key, actual_val in actual.items():
                if key in pred:
                    error += (pred[key] - actual_val) ** 2
                    count += 1
            if count > 0:
                mse = error / count
                self._errors[method].append(mse)
                if len(self._errors[method]) > ENSEMBLE_HISTORY_LEN:
                    self._errors[method] = self._errors[method][-ENSEMBLE_HISTORY_LEN:]

        # Recompute weights: inverse of average error
        self._recompute_weights()
        self._update_count += 1

    def _recompute_weights(self):
        inv_errors = {}
        for method, errs in self._errors.items():
            if errs:
                avg = sum(errs) / len(errs)
                inv_errors[method] = 1.0 / (avg + 1e-8)
            else:
                inv_errors[method] = 1.0

        total = sum(inv_errors.values())
        if total > 0:
            for method in self._weights:
                self._weights[method] = inv_errors.get(method, 1.0) / total

    def get_weights(self) -> Dict[str, float]:
        return dict(self._weights)

    def to_dict(self) -> dict:
        return {
            "weights": self._weights,
            "errors": {k: v[-50:] for k, v in self._errors.items()},
            "update_count": self._update_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EnsembleTransition":
        obj = cls()
        if "weights" in d:
            obj._weights.update(d["weights"])
        if "errors" in d:
            for k, v in d["errors"].items():
                obj._errors[k] = v
        obj._update_count = d.get("update_count", 0)
        return obj


# ── EnhancedWorldModel ─────────────────────────────────────────────────

class EnhancedWorldModel:
    """
    Enhanced world model with non-linear transitions, compositional states,
    causal integration, and multi-step simulation.

    Backward-compatible with the WorldModel interface.
    """

    def __init__(self):
        self._lock = threading.RLock()

        # Core data (same structure as WorldModel)
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

        # Linear transition weights (backward compat)
        self._transition_weights: Dict[str, List[List[float]]] = {}

        # Enhanced components
        self._nonlinear_transitions: Dict[str, NonLinearTransition] = {}
        self._compositional = CompositionalState()
        self._causal = CausalTransition()
        self._simulation = MultiStepSimulation()
        self._ensemble = EnsembleTransition()

        # Stats
        self._prediction_errors: List[float] = []
        self._total_experiences: int = 0
        self._total_predictions: int = 0
        self._created_at: str = _timestamp()

        self._load()
        print("[EnhancedWorldModel] Initialized")

    # ── Persistence ──────────────────────────────────────────────────────

    def _save_unlocked(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                "meta": {
                    "version": 2,
                    "created": self._created_at,
                    "last_updated": _timestamp(),
                },
                "experiences": self._experiences[-MAX_EXPERIENCES:],
                "latent_vectors": self._latent_vectors[-MAX_FEATURE_HISTORY:],
                "transition_weights": self._transition_weights,
                "nonlinear_transitions": {
                    k: v.to_dict()
                    for k, v in self._nonlinear_transitions.items()
                },
                "compositional": self._compositional.to_dict(),
                "causal": self._causal.to_dict(),
                "ensemble": self._ensemble.to_dict(),
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
            print(f"[EnhancedWorldModel] Save error: {e}")

    def save(self):
        """Persist enhanced world model data to disk."""
        with self._lock:
            self._save_unlocked()

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

            # Load enhanced components
            for k, v in data.get("nonlinear_transitions", {}).items():
                self._nonlinear_transitions[k] = NonLinearTransition.from_dict(v)

            if "compositional" in data:
                self._compositional = CompositionalState.from_dict(data["compositional"])
            if "causal" in data:
                self._causal = CausalTransition.from_dict(data["causal"])
            if "ensemble" in data:
                self._ensemble = EnsembleTransition.from_dict(data["ensemble"])

            print(f"[EnhancedWorldModel] Loaded {self._total_experiences} experiences, "
                  f"{len(self._nonlinear_transitions)} nonlinear models")
        except (json.JSONDecodeError, IOError) as e:
            print(f"[EnhancedWorldModel] Load error: {e}")

    # ── Feature Extraction ───────────────────────────────────────────────

    def _extract_features(self, experience: dict) -> Dict[str, float]:
        """Extract normalized feature values from an experience."""
        features = {}

        features["complexity"] = max(0.0, min(1.0,
            float(experience.get("complexity", 0.5))))

        success = experience.get("success", None)
        if success is True:
            features["success_rate"] = 1.0
        elif success is False:
            features["success_rate"] = 0.0
        else:
            features["success_rate"] = 0.5

        tool = experience.get("tool", "unknown")
        tool_count = sum(
            1 for e in self._experiences
            if e.get("raw", {}).get("tool") == tool
        )
        features["tool_familiarity"] = min(1.0, tool_count / 10.0)

        context = str(experience.get("context", ""))
        features["context_richness"] = min(1.0, len(context) / 500.0)

        error = str(experience.get("error", ""))
        features["error_proneness"] = min(1.0, len(error) / 200.0) if error else 0.0

        features["novelty"] = 1.0 - features["tool_familiarity"]

        features["urgency"] = max(0.0, min(1.0,
            float(experience.get("urgency", 0.5))))
        features["resource_demand"] = max(0.0, min(1.0,
            float(experience.get("resource_demand", 0.3))))
        features["dependency_depth"] = max(0.0, min(1.0,
            float(experience.get("dependency_depth", 0.3))))
        features["confidence"] = max(0.0, min(1.0,
            float(experience.get("confidence", 0.5))))
        features["recency"] = 1.0
        features["category_strength"] = 0.5
        features["action_diversity"] = 0.5
        features["outcome_predictability"] = 0.5
        features["learning_potential"] = features["novelty"] * 0.7 + 0.3
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
            h = hash(name) % LATENT_DIM
            latent[h] += value * 0.5
            h2 = (h + 1) % LATENT_DIM
            latent[h2] += value * 0.2
        norm = _vec_norm(latent)
        if norm > 0:
            latent = [v / norm for v in latent]
        return [round(v, 6) for v in latent]

    def _features_to_list(self, features: Dict[str, float]) -> List[float]:
        """Convert feature dict to ordered list matching _feature_names."""
        return [features.get(name, 0.5) for name in self._feature_names]

    def _list_to_features(self, values: List[float]) -> Dict[str, float]:
        """Convert ordered list back to feature dict."""
        result = {}
        for i, name in enumerate(self._feature_names):
            if i < len(values):
                result[name] = max(0.0, min(1.0, values[i]))
            else:
                result[name] = 0.5
        return result

    # ── Transition Updates ───────────────────────────────────────────────

    def _update_transitions(self, experience: dict, features: Dict[str, float],
                            latent: List[float]):
        """Update all transition models from a new observation."""
        action_type = experience.get("tool", "default")

        # 1. Linear transition (backward compat)
        if action_type not in self._transition_weights:
            self._transition_weights[action_type] = [
                [random.uniform(-0.01, 0.01) for _ in range(LATENT_DIM)]
                for _ in range(LATENT_DIM)
            ]

        if len(self._latent_vectors) >= 2:
            prev_latent = self._latent_vectors[-2]
            W = self._transition_weights[action_type]

            for i in range(LATENT_DIM):
                for j in range(LATENT_DIM):
                    error = latent[i] - prev_latent[i]
                    W[i][j] += TRANSITION_LEARNING_RATE * error * prev_latent[j]
                    W[i][j] = _clamp(W[i][j])

        # 2. Nonlinear transition
        if action_type not in self._nonlinear_transitions:
            self._nonlinear_transitions[action_type] = NonLinearTransition(
                LATENT_DIM, HIDDEN_DIM
            )

        if len(self._latent_vectors) >= 2:
            prev_latent = self._latent_vectors[-2]
            mlp = self._nonlinear_transitions[action_type]
            loss = mlp.train_step(prev_latent, latent, MLP_LEARNING_RATE)
            self._prediction_errors.append(loss)
            if len(self._prediction_errors) > 200:
                self._prediction_errors = self._prediction_errors[-200:]

        # 3. Learn causal edges from feature correlations
        if len(self._experiences) >= 3:
            self._learn_causal_edges(features)

    def _learn_causal_edges(self, current_features: Dict[str, float]):
        """Infer causal edges from temporal feature correlations."""
        if len(self._experiences) < 3:
            return

        prev = self._experiences[-2].get("features", {})
        if not prev:
            return

        for feat_a in self._feature_names:
            delta_a = current_features.get(feat_a, 0.5) - prev.get(feat_a, 0.5)
            if abs(delta_a) < 0.05:
                continue
            for feat_b in self._feature_names:
                if feat_a == feat_b:
                    continue
                delta_b = current_features.get(feat_b, 0.5) - prev.get(feat_b, 0.5)
                if abs(delta_b) < 0.05:
                    continue
                # If A changed and B changed in same step, possible causal link
                correlation = delta_a * delta_b
                if abs(correlation) > 0.01:
                    strength = _clamp(correlation * 2.0, -1.0, 1.0)
                    self._causal.learn_causal_edge(feat_a, feat_b, strength)

    # ── Encoding ─────────────────────────────────────────────────────────

    def encode_experience(self, experience: dict) -> list:
        """
        Encode an experience dict into a latent vector.
        Backward-compatible with WorldModel.encode_experience.
        """
        with self._lock:
            self._total_experiences += 1

            features = self._extract_features(experience)
            latent = self._features_to_latent(features)

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

            self._update_transitions(experience, features, latent)
            self._save_unlocked()
            return latent

    # ── State Features ───────────────────────────────────────────────────

    def get_state_features(self) -> dict:
        """
        Get current latent space state features.
        Returns enhanced data with compositional state info.
        """
        with self._lock:
            if not self._latent_vectors:
                base = {
                    "feature_count": len(self._feature_names),
                    "latent_vector": [0.0] * LATENT_DIM,
                    "feature_names": self._feature_names,
                }
                base["compositional"] = self._compositional.abstract(
                    {n: 0.5 for n in self._feature_names}
                )
                return base

            recent = self._latent_vectors[-10:]
            avg_latent = [0.0] * LATENT_DIM
            for vec in recent:
                for i in range(min(LATENT_DIM, len(vec))):
                    avg_latent[i] += vec[i]
            avg_latent = [v / len(recent) for v in avg_latent]

            # Reconstruct features from average latent for compositional state
            avg_features = {}
            for name in self._feature_names:
                h = hash(name) % LATENT_DIM
                h2 = (h + 1) % LATENT_DIM
                raw = avg_latent[h] * 2.0 + avg_latent[h2] * 0.5
                avg_features[name] = max(0.0, min(1.0, _sigmoid(raw)))

            compositional = self._compositional.abstract(avg_features)

            return {
                "feature_count": len(self._feature_names),
                "latent_vector": [round(v, 6) for v in avg_latent],
                "feature_names": self._feature_names,
                "compositional": compositional,
            }

    # ── Trajectory Imagination ───────────────────────────────────────────

    def imagine_trajectory(self, start_state: dict, action_sequence: list,
                           horizon: int = 5) -> list:
        """
        Simulate a sequence of actions from a start state.
        Enhanced: uses ensemble prediction and multi-step simulation.

        Backward-compatible with WorldModel.imagine_trajectory interface.
        """
        with self._lock:
            self._total_predictions += 1

            features = self._state_dict_to_features(start_state)
            steps = min(len(action_sequence), horizon, MAX_TRAJECTORY_STEPS)

            # Use ensemble predict internally
            trajectory = []
            current = features

            for step in range(steps):
                action = action_sequence[step]
                if isinstance(action, dict):
                    action_type = action.get("tool", "default")
                else:
                    action_type = str(action)

                predicted = self._ensemble_predict(current, action_type, step)

                # Compositional state for this step
                comp = self._compositional.abstract(predicted)

                state = {
                    "step": step,
                    "action": action_type,
                    "features": {k: round(v, 4) for k, v in predicted.items()},
                    "confidence": round(max(0.1, 1.0 - step * (1.0 - PREDICTION_DECAY)), 4),
                    "compositional": comp,
                }
                trajectory.append(state)
                current = predicted

            return trajectory

    def imagine_trajectory_branching(self, start_state: dict,
                                     action_sequence: list,
                                     horizon: int = 15,
                                     num_branches: int = 3) -> List[Dict[str, Any]]:
        """
        Enhanced: simulate multiple parallel trajectories with branching.
        Returns list of branch results.
        """
        with self._lock:
            self._total_predictions += 1

            features = self._state_dict_to_features(start_state)

            def predict_fn(state, action_type, step):
                return self._ensemble_predict(state, action_type, step)

            results = self._simulation.simulate(
                features, action_sequence, predict_fn, horizon, num_branches
            )

            return results

    def _ensemble_predict(self, current: Dict[str, float],
                          action_type: str, step: int) -> Dict[str, float]:
        """Predict next state using the ensemble of methods."""

        # Linear prediction
        def linear_pred(state):
            return self._predict_linear(state, action_type, step)

        # Nonlinear prediction
        def nonlinear_pred(state):
            return self._predict_nonlinear(state, action_type, step)

        # Causal prediction (if graph has edges)
        causal_pred = None
        if self._causal._causal_graph:
            def causal_pred_fn(state):
                linear_result = self._predict_linear(state, action_type, step)
                return self._causal.constrain_prediction(linear_result, state)
            causal_pred = causal_pred_fn

        return self._ensemble.predict(linear_pred, nonlinear_pred, causal_pred, current)

    def _predict_linear(self, current: Dict[str, float],
                        action_type: str, step: int) -> Dict[str, float]:
        """Linear transition prediction (backward compat)."""
        predicted = dict(current)

        if action_type in self._transition_weights:
            W = self._transition_weights[action_type]
            current_latent = self._features_to_latent(current)
            new_latent = _mat_vec_mul(W, current_latent)

            for idx, name in enumerate(self._feature_names):
                h = hash(name) % LATENT_DIM
                h2 = (h + 1) % LATENT_DIM
                raw = new_latent[h] * 2.0 + new_latent[h2] * 0.5
                predicted[name] = max(0.0, min(1.0, _sigmoid(raw)))
        else:
            success_delta = 0.1 if action_type not in ("error", "unknown") else -0.1
            predicted["success_rate"] = max(0.0, min(1.0,
                current["success_rate"] + success_delta * (PREDICTION_DECAY ** step)))
            predicted["recency"] = max(0.0, current["recency"] * PREDICTION_DECAY)
            predicted["tool_familiarity"] = min(1.0, current["tool_familiarity"] + 0.05)

        return predicted

    def _predict_nonlinear(self, current: Dict[str, float],
                           action_type: str, step: int) -> Dict[str, float]:
        """Nonlinear (MLP) transition prediction."""
        if action_type in self._nonlinear_transitions:
            mlp = self._nonlinear_transitions[action_type]
            current_latent = self._features_to_latent(current)
            new_latent = mlp.predict(current_latent)

            predicted = {}
            for idx, name in enumerate(self._feature_names):
                h = hash(name) % LATENT_DIM
                h2 = (h + 1) % LATENT_DIM
                raw = new_latent[h] * 2.0 + new_latent[h2] * 0.5
                predicted[name] = max(0.0, min(1.0, _sigmoid(raw)))
            return predicted
        else:
            # Fallback to linear
            return self._predict_linear(current, action_type, step)

    def _state_dict_to_features(self, state: dict) -> Dict[str, float]:
        features = {}
        for name in self._feature_names:
            if name in state:
                features[name] = max(0.0, min(1.0, float(state[name])))
            else:
                features[name] = 0.5
        return features

    # ── Causal Interface ─────────────────────────────────────────────────

    def set_causal_graph(self, graph: Dict[str, List[Tuple[str, float]]]):
        """Set the causal graph for constrained predictions."""
        with self._lock:
            self._causal.set_causal_graph(graph)

    def causal_intervene(self, intervention: Dict[str, float]) -> Dict[str, float]:
        """
        Simulate a causal intervention on the current state.
        Returns the resulting state after propagation.
        """
        with self._lock:
            current = self.get_state_features()
            features = {}
            latent = current.get("latent_vector", [])
            names = current.get("feature_names", [])
            for i, name in enumerate(names):
                if i < len(latent):
                    features[name] = latent[i]
                else:
                    features[name] = 0.5
            return self._causal.intervene(features, intervention)

    # ── Plan Evaluation ──────────────────────────────────────────────────

    def evaluate_plan(self, action_sequence: list) -> dict:
        """
        Evaluate a plan by simulating and scoring.
        Enhanced: uses ensemble predictions and compositional analysis.

        Backward-compatible with WorldModel.evaluate_plan.
        """
        with self._lock:
            if not action_sequence:
                return {
                    "predicted_success": 0.5,
                    "risk_score": 0.5,
                    "confidence": 0.0,
                    "steps_evaluated": 0,
                }

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

            trajectory = self.imagine_trajectory(start_state, action_sequence,
                                                 horizon=min(len(action_sequence), 15))

            if not trajectory:
                return {
                    "predicted_success": 0.5,
                    "risk_score": 0.5,
                    "confidence": 0.0,
                    "steps_evaluated": 0,
                }

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

            # Compositional summary of final state
            final_comp = trajectory[-1].get("compositional", {})

            return {
                "predicted_success": round(predicted_success, 4),
                "risk_score": round(risk_score, 4),
                "confidence": round(avg_confidence, 4),
                "steps_evaluated": len(trajectory),
                "final_state_summary": final_comp.get("high_level", "unknown"),
                "trajectory_summary": [
                    {"step": s["step"], "action": s["action"],
                     "success_pred": s["features"].get("success_rate", 0.5)}
                    for s in trajectory
                ],
            }

    # ── Stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get enhanced world model statistics."""
        with self._lock:
            avg_error = (
                sum(self._prediction_errors) / len(self._prediction_errors)
                if self._prediction_errors else None
            )

            # Per-method MSE from ensemble
            ensemble_errors = {}
            for method, errs in self._ensemble._errors.items():
                if errs:
                    ensemble_errors[method] = round(sum(errs) / len(errs), 6)

            return {
                "total_experiences": self._total_experiences,
                "total_predictions": self._total_predictions,
                "stored_experiences": len(self._experiences),
                "latent_vectors": len(self._latent_vectors),
                "transition_models": len(self._transition_weights),
                "nonlinear_models": len(self._nonlinear_transitions),
                "causal_edges": sum(
                    len(v) for v in self._causal._causal_graph.values()
                ),
                "ensemble_weights": self._ensemble.get_weights(),
                "ensemble_mse": ensemble_errors,
                "avg_prediction_error": round(avg_error, 4) if avg_error is not None else None,
                "latent_dim": LATENT_DIM,
                "feature_count": len(self._feature_names),
            }

    # ── Prompt Formatting ────────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 500) -> str:
        """Format enhanced world model state for system prompt inclusion."""
        with self._lock:
            stats = self.get_stats()
            if stats["total_experiences"] == 0:
                return ""

            parts = ["[ENHANCED WORLD MODEL — Advanced simulation state]"]
            parts.append(
                f"  Experiences: {stats['total_experiences']} | "
                f"Predictions: {stats['total_predictions']} | "
                f"Transitions: {stats['transition_models']} linear, "
                f"{stats['nonlinear_models']} nonlinear"
            )
            parts.append(
                f"  Causal edges: {stats['causal_edges']} | "
                f"Ensemble methods: {len(stats['ensemble_weights'])}"
            )

            if stats["avg_prediction_error"] is not None:
                accuracy = max(0.0, 1.0 - stats["avg_prediction_error"])
                parts.append(f"  Prediction accuracy: {accuracy:.0%}")

            # Ensemble weights
            weights = stats.get("ensemble_weights", {})
            if weights:
                w_str = ", ".join(f"{k}={v:.2f}" for k, v in weights.items())
                parts.append(f"  Ensemble weights: {w_str}")

            # Current compositional state
            if self._latent_vectors:
                comp = self.get_state_features().get("compositional", {})
                if comp:
                    parts.append(f"  Current state: {comp.get('description', 'unknown')}")

            result = "\n".join(parts)
            if len(result) > max_chars:
                result = result[:max_chars].rsplit("\n", 1)[0] + "\n  [...]"
            return result


# ── Singleton ───────────────────────────────────────────────────────────────

_instance: Optional[EnhancedWorldModel] = None
_instance_lock = threading.Lock()


def get_enhanced_world_model() -> EnhancedWorldModel:
    """Get the singleton enhanced world model instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = EnhancedWorldModel()
    return _instance


# ── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    wm = get_enhanced_world_model()

    print("=== Encoding test experiences ===")
    for i in range(8):
        exp = {
            "tool": f"tool_{i % 3}",
            "success": i % 3 != 0,
            "complexity": 0.3 + (i * 0.08),
            "context": f"test context {i}",
            "confidence": 0.4 + (i * 0.05),
        }
        latent = wm.encode_experience(exp)
        print(f"  Experience {i}: latent[:4] = {[round(v, 3) for v in latent[:4]]}")

    print("\n=== State Features + Compositional ===")
    features = wm.get_state_features()
    comp = features.get("compositional", {})
    print(f"  Feature count: {features['feature_count']}")
    print(f"  Compositional: {comp.get('description', 'N/A')}")
    print(f"  Mid-level: {comp.get('mid_level', [])}")
    print(f"  High-level: {comp.get('high_level', 'N/A')}")

    print("\n=== Trajectory (basic) ===")
    trajectory = wm.imagine_trajectory(
        start_state={"complexity": 0.5, "success_rate": 0.7, "confidence": 0.6},
        action_sequence=[
            {"tool": "web_search"},
            {"tool": "code_helper"},
            {"tool": "file_controller"},
            {"tool": "web_search"},
            {"tool": "code_helper"},
        ],
        horizon=5,
    )
    for s in trajectory:
        print(f"  Step {s['step']}: {s['action']} → "
              f"success={s['features'].get('success_rate', '?'):.2f} "
              f"conf={s['confidence']:.2f} "
              f"state={s.get('compositional', {}).get('high_level', '?')}")

    print("\n=== Branching Trajectory (15 steps) ===")
    branches = wm.imagine_trajectory_branching(
        start_state={"complexity": 0.5, "success_rate": 0.7, "confidence": 0.6},
        action_sequence=[{"tool": f"tool_{i % 3}"} for i in range(15)],
        horizon=15,
        num_branches=3,
    )
    for i, branch in enumerate(branches):
        print(f"  Branch {i}: {branch['steps_simulated']} steps, "
              f"conf={branch['final_confidence']:.4f}, "
              f"pruned={branch['pruned']}")

    print("\n=== Causal Intervention ===")
    wm.set_causal_graph({
        "complexity": [("error_proneness", 0.7), ("confidence", -0.5)],
        "confidence": [("success_rate", 0.6)],
    })
    result = wm.causal_intervene({"complexity": 0.9})
    print(f"  After setting complexity=0.9:")
    for k in ["complexity", "error_proneness", "confidence", "success_rate"]:
        print(f"    {k}: {result.get(k, 'N/A'):.4f}")

    print("\n=== Plan Evaluation ===")
    evaluation = wm.evaluate_plan([
        {"tool": "web_search"},
        {"tool": "code_helper"},
        {"tool": "file_controller"},
    ])
    print(f"  Predicted success: {evaluation['predicted_success']}")
    print(f"  Risk score: {evaluation['risk_score']}")
    print(f"  Confidence: {evaluation['confidence']}")
    print(f"  Final state: {evaluation.get('final_state_summary', 'N/A')}")

    print("\n=== Ensemble Weights ===")
    stats = wm.get_stats()
    print(f"  Weights: {stats['ensemble_weights']}")
    print(f"  Causal edges: {stats['causal_edges']}")
    print(f"  Nonlinear models: {stats['nonlinear_models']}")

    wm.save()
    print(f"\n=== Full Stats ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print(f"\n=== Prompt Format ===\n{wm.format_for_prompt()}")
