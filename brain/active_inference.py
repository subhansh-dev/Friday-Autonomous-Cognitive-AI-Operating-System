#!/usr/bin/env python3
"""
active_inference.py — FRIDAY Active Inference Engine
======================================================

Augments the existing Q-learning engine with prediction-error driven learning.
Based on the Free Energy Principle (Karl Friston):
- Perception: minimize prediction error between expected and actual outcomes
- Action: choose actions that reduce uncertainty (epistemic foraging)
- Learning: update world model when predictions consistently fail

Architecture:
- World model: lightweight predictor that forecasts tool outcomes
- Prediction error: measures gap between expected and actual results
- Epistemic value: quantifies information gain potential of actions
- Precision weighting: confidence modulates how much prediction errors update beliefs

This does NOT replace brain/learning.py — it feeds INTO it.
Prediction errors become learning signals that Q-learning can use.
"""

import json
import math
import threading
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict


BRAIN_DIR = Path(__file__).parent.resolve()
INFERENCE_FILE = BRAIN_DIR / "active_inference.json"


class ActiveInferenceEngine:
    """
    Active Inference engine that augments FRIDAY's Q-learning.

    Core mechanism:
    1. Before a tool call: predict outcome (will it succeed? how long?)
    2. After a tool call: compute prediction error
    3. Update world model: adjust future predictions based on error
    4. Epistemic foraging: when uncertainty is high, flag for exploration

    This operates alongside Q-learning — prediction errors become
    additional signals that shape future decisions.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data = self._empty_store()
        self._load()
        self._session_errors = []
        self._prediction_history = []

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": datetime.now().isoformat(),
                "last_update": datetime.now().isoformat(),
                "total_predictions": 0,
                "total_errors": 0,
            },
            "world_model": {
                # tool_name: {
                #   "expected_success_rate": 0.5,     # prior belief
                #   "expected_duration_ms": 1000,      # prior duration
                #   "prediction_accuracy": 0.5,         # how often predictions match
                #   "uncertainty": 0.5,                 # 0=very certain, 1=very uncertain
                #   "observations": [],                  # recent (predicted, actual) pairs
                # }
            },
            "prediction_errors": [
                # {"timestamp": "", "tool": "", "predicted": {}, "actual": {}, "error": 0.0
            ],
            "epistemic_scores": {
                # tool_name: epistemic_value (0-1), information gain potential
            },
        }

    # ── Persistence ─────────────────────────────────────────────────────

    def _load(self):
        if not INFERENCE_FILE.exists():
            self._save()
            return
        try:
            raw = INFERENCE_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            empty = self._empty_store()
            for section in ["meta", "world_model", "prediction_errors", "epistemic_scores"]:
                if section not in data:
                    data[section] = empty[section]
            self._data = data
        except (json.JSONDecodeError, IOError):
            self._data = self._empty_store()
            self._save()

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._data["meta"]["last_update"] = datetime.now().isoformat()
            INFERENCE_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ── Prediction ──────────────────────────────────────────────────────

    def predict_outcome(self, tool_name: str, context: str = "") -> dict:
        """
        Predict the outcome of a tool call before execution.

        Returns a dict with:
        - expected_success: 0.0-1.0 probability of success
        - expected_duration_ms: predicted duration
        - uncertainty: 0.0-1.0 how uncertain the prediction is
        - epistemic_value: 0.0-1.0 information gain if we call this
        """
        with self._lock:
            model = self._data["world_model"].get(tool_name, {})
            epistemic = self._data["epistemic_scores"].get(tool_name, 0.5)

            expected_success = model.get("expected_success_rate", 0.5)
            expected_duration = model.get("expected_duration_ms", 1000.0)
            uncertainty = model.get("uncertainty", 0.8)

            # Context modulation: if tool has context-specific data, use it
            context_key = f"{tool_name}:{context}"
            ctx_data = self._data["world_model"].get(context_key)
            if ctx_data:
                # Blend prior with context-specific
                ctx_success = ctx_data.get("expected_success_rate", expected_success)
                ctx_uncertainty = ctx_data.get("uncertainty", uncertainty)
                expected_success = (expected_success + ctx_success) * 0.5
                uncertainty = (uncertainty + ctx_uncertainty) * 0.5

            return {
                "expected_success": round(expected_success, 3),
                "expected_duration_ms": round(expected_duration, 1),
                "uncertainty": round(uncertainty, 3),
                "epistemic_value": round(epistemic, 3),
            }

    def compute_prediction_error(self, tool_name: str, prediction: dict,
                                  actual_success: bool,
                                  actual_duration_ms: float = 0.0) -> float:
        """
        Compute prediction error after a tool call.

        Error is a combination of:
        - Success prediction error: |predicted - actual|
        - Duration prediction error: relative error in timing

        Returns a single error score (0.0 = perfect prediction, 1.0+ = way off).
        """
        pred_success = prediction.get("expected_success", 0.5)
        actual_val = 1.0 if actual_success else 0.0

        # Success prediction error
        success_error = abs(pred_success - actual_val)

        # Duration prediction error (log scale to handle wide ranges)
        pred_duration = prediction.get("expected_duration_ms", 1000.0)
        if actual_duration_ms > 0 and pred_duration > 0:
            ratio = actual_duration_ms / max(pred_duration, 1)
            if ratio > 1:
                duration_error = math.log2(ratio) * 0.3
            else:
                duration_error = abs(1 - ratio) * 0.3
        else:
            duration_error = 0.0

        # Combined error (success is primary)
        total_error = success_error + duration_error

        # Clamp
        return round(min(total_error, 2.0), 3)

    def observe(self, tool_name: str, context: str, actual_success: bool,
                actual_duration_ms: float = 0.0):
        """
        Process the outcome of a tool call — the core learning step.

        1. Generate prediction
        2. Compute prediction error
        3. Update world model
        4. Update epistemic scores
        """
        # Generate prior prediction
        prediction = self.predict_outcome(tool_name, context)
        prediction_error = self.compute_prediction_error(
            tool_name, prediction, actual_success, actual_duration_ms
        )

        with self._lock:
            # Update world model for this tool
            model = self._data["world_model"].get(tool_name, {
                "expected_success_rate": 0.5,
                "expected_duration_ms": 1000.0,
                "prediction_accuracy": 0.5,
                "uncertainty": 0.8,
                "observations": [],
                "total_predictions": 0,
            })

            model["total_predictions"] = model.get("total_predictions", 0) + 1

            # Update expected success rate (Bayesian-like update)
            # learning_rate decreases with more observations
            n = model["total_predictions"]
            lr = max(0.05, 1.0 / max(n, 2))
            actual_val = 1.0 if actual_success else 0.0
            old_rate = model.get("expected_success_rate", 0.5)
            model["expected_success_rate"] = round(
                old_rate + lr * (actual_val - old_rate), 3
            )

            # Update expected duration (exponential moving average)
            old_duration = model.get("expected_duration_ms", 1000.0)
            if actual_duration_ms > 0:
                model["expected_duration_ms"] = round(
                    old_duration * 0.9 + actual_duration_ms * 0.1, 1
                )

            # Update prediction accuracy
            old_accuracy = model.get("prediction_accuracy", 0.5)
            # Prediction is "accurate" if error < 0.3
            was_accurate = 1.0 if prediction_error < 0.3 else 0.0
            model["prediction_accuracy"] = round(
                old_accuracy + lr * (was_accurate - old_accuracy), 3
            )

            # Update uncertainty: decreases with accurate predictions, increases with errors
            old_uncertainty = model.get("uncertainty", 0.8)
            if prediction_error > 0.5:
                # Big error = more uncertain (surprise increases uncertainty)
                model["uncertainty"] = round(
                    min(1.0, old_uncertainty + prediction_error * 0.2), 3
                )
            else:
                # Good prediction = less uncertain
                model["uncertainty"] = round(
                    max(0.05, old_uncertainty - (1.0 - prediction_error) * 0.1), 3
                )

            # Store recent observations (keep last 20)
            observations = model.get("observations", [])
            observations.append({
                "predicted_success": prediction["expected_success"],
                "actual_success": actual_success,
                "prediction_error": prediction_error,
                "duration_ms": actual_duration_ms,
            })
            model["observations"] = observations[-20:]

            self._data["world_model"][tool_name] = model

            # Update context-specific model too
            context_key = f"{tool_name}:{context}"
            if context:
                ctx_model = self._data["world_model"].get(context_key, {
                    "expected_success_rate": 0.5,
                    "uncertainty": 0.8,
                    "total_predictions": 0,
                })
                ctx_model["total_predictions"] = ctx_model.get("total_predictions", 0) + 1
                ctx_n = ctx_model["total_predictions"]
                ctx_lr = max(0.05, 1.0 / max(ctx_n, 2))
                ctx_model["expected_success_rate"] = round(
                    ctx_model["expected_success_rate"] + ctx_lr * (actual_val - ctx_model["expected_success_rate"]), 3
                )
                ctx_model["uncertainty"] = round(
                    max(0.05, min(1.0, ctx_model["uncertainty"] + (prediction_error - 0.3) * 0.15)), 3
                )
                self._data["world_model"][context_key] = ctx_model

            # Update epistemic scores (information gain potential)
            # High uncertainty = high epistemic value
            epistemic = min(1.0, model.get("uncertainty", 0.5) * 1.2)
            self._data["epistemic_scores"][tool_name] = round(epistemic, 3)

            # Store prediction error
            error_entry = {
                "timestamp": datetime.now().isoformat(),
                "tool": tool_name,
                "context": context,
                "predicted_success": prediction["expected_success"],
                "actual_success": actual_success,
                "prediction_error": prediction_error,
                "uncertainty": model["uncertainty"],
            }
            self._data["prediction_errors"].append(error_entry)
            self._data["prediction_errors"] = self._data["prediction_errors"][-200:]
            self._data["meta"]["total_predictions"] += 1
            if prediction_error > 0.5:
                self._data["meta"]["total_errors"] += 1

            self._session_errors.append(error_entry)
            if len(self._session_errors) > 50:
                self._session_errors = self._session_errors[-50:]

            self._save()

        return prediction_error

    # ── Query ───────────────────────────────────────────────────────────

    def get_uncertain_tools(self, threshold: float = 0.6) -> list[tuple[str, float]]:
        """Get tools with uncertainty above threshold, sorted highest first."""
        with self._lock:
            result = []
            for tool_name, model in self._data["world_model"].items():
                if ":" in tool_name:
                    continue  # Skip context-specific entries
                unc = model.get("uncertainty", 0.5)
                if unc >= threshold:
                    result.append((tool_name, unc))
            result.sort(key=lambda x: x[1], reverse=True)
            return result

    def get_high_epistemic_tools(self, threshold: float = 0.6) -> list[tuple[str, float]]:
        """Get tools with high epistemic value (high info gain if explored)."""
        with self._lock:
            result = []
            for tool_name, score in self._data["epistemic_scores"].items():
                if score >= threshold:
                    result.append((tool_name, score))
            result.sort(key=lambda x: x[1], reverse=True)
            return result

    def get_prediction_accuracy(self, tool_name: str) -> float:
        """Get how accurate FRIDAY's predictions are for a given tool."""
        with self._lock:
            model = self._data["world_model"].get(tool_name, {})
            return model.get("prediction_accuracy", 0.5)

    def should_explore(self, tool_name: str) -> bool:
        """
        Should FRIDAY explore this tool more to reduce uncertainty?
        Based on epistemic value.
        """
        with self._lock:
            epistemic = self._data["epistemic_scores"].get(tool_name, 0.5)
            model = self._data["world_model"].get(tool_name, {})
            n = model.get("total_predictions", 0)
            # High epistemic value AND low number of observations = explore
            return epistemic > 0.7 and n < 10

    def get_surprising_events(self, top_k: int = 5) -> list[dict]:
        """Get the most surprising (largest prediction error) recent events."""
        with self._lock:
            errors = sorted(
                self._data["prediction_errors"],
                key=lambda e: e.get("prediction_error", 0),
                reverse=True,
            )
            return errors[:top_k]

    def get_stats(self) -> dict:
        """Get active inference statistics."""
        with self._lock:
            tools = set()
            total_predictions = 0
            high_uncertainty = 0
            accuracies = []

            for tool_name, model in self._data["world_model"].items():
                if ":" in tool_name:
                    continue
                tools.add(tool_name)
                total_predictions += model.get("total_predictions", 0)
                if model.get("uncertainty", 0.5) > 0.6:
                    high_uncertainty += 1
                acc = model.get("prediction_accuracy", 0.5)
                if acc > 0:
                    accuracies.append(acc)

            avg_accuracy = round(
                sum(accuracies) / max(len(accuracies), 1), 3
            ) if accuracies else 0.5

            return {
                "tools_tracked": len(tools),
                "total_predictions": total_predictions,
                "total_errors": self._data["meta"]["total_errors"],
                "high_uncertainty_tools": high_uncertainty,
                "avg_prediction_accuracy": avg_accuracy,
                "recent_surprising_events": len(self.get_surprising_events(3)),
            }

    def format_for_prompt(self, max_chars: int = 600) -> str:
        """
        Format active inference awareness for system prompt.
        This gives FRIDAY awareness of her own prediction capabilities.
        """
        stats = self.get_stats()
        uncertain = self.get_uncertain_tools(threshold=0.6)[:3]
        surprising = self.get_surprising_events(3)

        parts = [
            "[ACTIVE INFERENCE — Prediction awareness]",
            f"Tracking {stats['tools_tracked']} tools | "
            f"Prediction accuracy: {stats['avg_prediction_accuracy']:.0%}",
        ]

        if uncertain:
            parts.append(
                f"Uncertain about: {', '.join(f'{t}({u:.0%})' for t, u in uncertain)}"
            )

        if surprising:
            surprise_items = []
            for e in surprising:
                surprise_items.append(f"{e['tool']}(err={e['prediction_error']:.2f})")
            parts.append(f"Recent surprises: {', '.join(surprise_items)}")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars].rsplit("\n", 1)[0] + "\n[...]"
        return result


# ── Singleton ───────────────────────────────────────────────────────────────

_inference_engine = None
_inference_lock = threading.Lock()


def get_active_inference() -> ActiveInferenceEngine:
    """Get singleton active inference engine instance."""
    global _inference_engine
    if _inference_engine is None:
        with _inference_lock:
            if _inference_engine is None:
                _inference_engine = ActiveInferenceEngine()
    return _inference_engine
