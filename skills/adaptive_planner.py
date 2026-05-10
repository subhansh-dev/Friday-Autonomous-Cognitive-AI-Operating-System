# -*- coding: utf-8 -*-
"""
adaptive_planner.py — FRIDAY Adaptive Planner
==============================================
Dynamic re-planning on failure. When a multi-step plan fails, re-assesses
from the failure point and generates alternatives. Tracks strategy success
rates to prefer historically reliable approaches. Inspired by DEPS
(Wang et al., 2023).
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


BRAIN_DIR = Path(__file__).parent.parent / "brain"
STRATEGY_FILE = BRAIN_DIR / "strategy_scores.json"

MAX_STRATEGIES = 50


class PlanStep:
    """A single step in an execution plan."""

    def __init__(self, step_num: int, description: str, tool: str,
                 params: dict = None, fallback_tool: str = "",
                 fallback_params: dict = None):
        self.step_num = step_num
        self.description = description
        self.tool = tool
        self.params = params or {}
        self.fallback_tool = fallback_tool
        self.fallback_params = fallback_params or {}
        self.status = "pending"  # pending, running, success, failed, skipped
        self.error: Optional[str] = None
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "step_num": self.step_num,
            "description": self.description,
            "tool": self.tool,
            "params": self.params,
            "fallback_tool": self.fallback_tool,
            "fallback_params": self.fallback_params,
            "status": self.status,
            "error": self.error,
            "duration_ms": (
                round((self.completed_at - self.started_at) * 1000)
                if self.started_at and self.completed_at else None
            ),
        }


class ExecutionPlan:
    """A multi-step execution plan with re-planning capability."""

    def __init__(self, plan_id: str, goal: str, steps: list[PlanStep]):
        self.plan_id = plan_id
        self.goal = goal
        self.steps = steps
        self.current_step = 0
        self.status = "active"  # active, completed, failed, replanned
        self.alternatives_tried: list[str] = []
        self.created_at = time.time()

    def get_current(self) -> Optional[PlanStep]:
        if 0 <= self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def mark_success(self):
        step = self.get_current()
        if step:
            step.status = "success"
            step.completed_at = time.time()
        self.current_step += 1
        if self.current_step >= len(self.steps):
            self.status = "completed"

    def mark_failed(self, error: str):
        step = self.get_current()
        if step:
            step.status = "failed"
            step.error = error
            step.completed_at = time.time()

    def try_fallback(self) -> Optional[PlanStep]:
        """Try the fallback for the current step."""
        step = self.get_current()
        if step and step.fallback_tool:
            self.alternatives_tried.append(step.tool)
            step.tool = step.fallback_tool
            step.params = step.fallback_params
            step.status = "pending"
            step.error = None
            step.started_at = None
            step.completed_at = None
            return step
        return None

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "current_step": self.current_step,
            "status": self.status,
            "alternatives_tried": self.alternatives_tried,
            "created_at": self.created_at,
            "duration_s": round(time.time() - self.created_at, 1),
        }


class AdaptivePlanner:
    """
    Wraps plan execution with failure recovery and strategy learning.

    - On step failure: try fallback, then re-plan
    - Tracks which tools succeed/fail for which task types
    - Prefers historically reliable strategies
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._strategies: dict[str, dict] = {}
        self._active_plan: Optional[ExecutionPlan] = None
        self._load()

    # ── Persistence ─────────────────────────────────────────────────

    def _load(self):
        if not STRATEGY_FILE.exists():
            return
        try:
            data = json.loads(STRATEGY_FILE.read_text(encoding="utf-8"))
            self._strategies = data.get("strategies", {})
        except (json.JSONDecodeError, IOError):
            self._strategies = {}

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "strategies": self._strategies,
            "updated_at": datetime.now().isoformat(),
        }
        STRATEGY_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Strategy tracking ───────────────────────────────────────────

    def _strategy_key(self, task_type: str, tool: str) -> str:
        return f"{task_type}:{tool}"

    def record_outcome(self, task_type: str, tool: str, success: bool,
                       duration_ms: float = 0):
        """Record a tool outcome for strategy learning."""
        key = self._strategy_key(task_type, tool)
        with self._lock:
            if key not in self._strategies:
                self._strategies[key] = {
                    "task_type": task_type,
                    "tool": tool,
                    "attempts": 0,
                    "successes": 0,
                    "total_duration_ms": 0,
                }
            s = self._strategies[key]
            s["attempts"] += 1
            if success:
                s["successes"] += 1
            s["total_duration_ms"] += duration_ms
            s["success_rate"] = round(s["successes"] / s["attempts"], 3)
            s["avg_duration_ms"] = round(s["total_duration_ms"] / s["attempts"], 1)

            # Prune old strategies
            if len(self._strategies) > MAX_STRATEGIES:
                # Keep top by attempt count
                sorted_keys = sorted(
                    self._strategies.keys(),
                    key=lambda k: self._strategies[k]["attempts"],
                    reverse=True,
                )
                self._strategies = {
                    k: self._strategies[k] for k in sorted_keys[:MAX_STRATEGIES]
                }

            self._save()

    def get_best_tool(self, task_type: str,
                      candidate_tools: list[str] = None) -> Optional[str]:
        """
        Get the historically best tool for a task type.
        Returns None if no history exists.
        """
        with self._lock:
            candidates = []
            for key, s in self._strategies.items():
                if s["task_type"] == task_type:
                    if candidate_tools is None or s["tool"] in candidate_tools:
                        candidates.append(s)

            if not candidates:
                return None

            # Sort by success rate, then by speed
            candidates.sort(
                key=lambda s: (s.get("success_rate", 0), -s.get("avg_duration_ms", 999999)),
                reverse=True,
            )
            return candidates[0]["tool"]

    # ── Plan management ─────────────────────────────────────────────

    def create_plan(self, goal: str, steps: list[dict]) -> ExecutionPlan:
        """
        Create an execution plan.

        Args:
            goal: what the plan accomplishes
            steps: list of {"description": str, "tool": str, "params": dict,
                           "fallback_tool": str, "fallback_params": dict}
        """
        plan_id = f"plan_{int(time.time())}"
        plan_steps = []
        for i, s in enumerate(steps):
            plan_steps.append(PlanStep(
                step_num=i + 1,
                description=s.get("description", f"Step {i+1}"),
                tool=s.get("tool", ""),
                params=s.get("params", {}),
                fallback_tool=s.get("fallback_tool", ""),
                fallback_params=s.get("fallback_params", {}),
            ))

        plan = ExecutionPlan(plan_id, goal, plan_steps)
        with self._lock:
            self._active_plan = plan
        return plan

    def get_active_plan(self) -> Optional[ExecutionPlan]:
        with self._lock:
            return self._active_plan

    def clear_plan(self):
        with self._lock:
            self._active_plan = None

    def handle_step_failure(self, error: str) -> dict:
        """
        Handle a step failure. Tries fallback first, then flags for re-plan.

        Returns:
            {"action": "fallback" | "replan" | "abort",
             "new_tool": str or None,
             "reason": str}
        """
        with self._lock:
            if not self._active_plan:
                return {"action": "abort", "reason": "No active plan"}

            self._active_plan.mark_failed(error)

            # Try fallback
            fallback = self._active_plan.try_fallback()
            if fallback:
                return {
                    "action": "fallback",
                    "new_tool": fallback.tool,
                    "reason": f"Trying fallback tool '{fallback.tool}' for step {fallback.step_num}",
                }

            # Check if we've tried too many alternatives
            if len(self._active_plan.alternatives_tried) >= 3:
                self._active_plan.status = "failed"
                return {
                    "action": "abort",
                    "reason": f"Too many failures. Tried: {', '.join(self._active_plan.alternatives_tried)}",
                }

            return {
                "action": "replan",
                "reason": f"Step {self._active_plan.current_step} failed: {error[:100]}. No fallback available.",
            }

    # ── Query ───────────────────────────────────────────────────────

    def get_strategy_report(self, task_type: str = "") -> list[dict]:
        """Get strategy performance data."""
        with self._lock:
            results = []
            for key, s in self._strategies.items():
                if task_type and s["task_type"] != task_type:
                    continue
                results.append(s)
            results.sort(key=lambda s: s.get("success_rate", 0), reverse=True)
            return results

    def get_stats(self) -> dict:
        with self._lock:
            total_strategies = len(self._strategies)
            if total_strategies == 0:
                return {"strategies_tracked": 0}

            rates = [s.get("success_rate", 0) for s in self._strategies.values()]
            return {
                "strategies_tracked": total_strategies,
                "avg_success_rate": round(sum(rates) / len(rates), 3),
                "best_strategy": max(
                    self._strategies.values(),
                    key=lambda s: s.get("success_rate", 0),
                ),
            }

    def format_for_prompt(self, task_type: str = "", max_chars: int = 300) -> str:
        """Format strategy info for system prompt injection."""
        report = self.get_strategy_report(task_type)[:3]
        if not report:
            return ""

        parts = ["[ADAPTIVE PLANNER — Strategy preferences]"]
        for s in report:
            rate = s.get("success_rate", 0)
            parts.append(f"- {s['tool']} for {s['task_type']}: {rate:.0%} success ({s['attempts']} uses)")

        result = "\n".join(parts)
        return result[:max_chars] if len(result) > max_chars else result


# ── Singleton ───────────────────────────────────────────────────────────────

_planner = None
_planner_lock = threading.Lock()


def get_adaptive_planner() -> AdaptivePlanner:
    global _planner
    if _planner is None:
        with _planner_lock:
            if _planner is None:
                _planner = AdaptivePlanner()
    return _planner
