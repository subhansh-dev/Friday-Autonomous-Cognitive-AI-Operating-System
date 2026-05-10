#!/usr/bin/env python3
"""
code_planner.py — FRIDAY Cognitive Code Planner
=================================================

Hierarchical goal decomposition with Active Inference (Free Energy Principle).
Breaks complex coding tasks into subgoals, predicts outcomes, and selects
the plan that minimizes Expected Free Energy (EFE).

Inspired by expert programmer cognition:
- Recursive decomposition: goal → subgoals → atomic steps
- Mental simulation: predict execution paths before writing code
- Prior retrieval: query chunk memory for known patterns
- Adaptive replanning: update plan when predictions fail

Architecture:
  Goal → [Decompose] → Subgoals → [Simulate] → Predictions
       → [Select min EFE] → Execution Plan → [Monitor] → Replan on error
"""

import json
import math
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple



BRAIN_DIR = Path(__file__).parent.resolve()
PLANNER_FILE = BRAIN_DIR / "code_plans.json"
PLAN_HISTORY_FILE = BRAIN_DIR / "code_plan_history.json"

API_CONFIG_PATH = BRAIN_DIR.parent / "config" / "api_keys.json"
PLANNER_MODEL = "gemini-2.5-flash"

# Active Inference parameters
EFE_WEIGHTS = {
    "expected_cost": 0.30,       # How much effort/time
    "expected_risk": 0.25,       # Chance of failure
    "information_gain": 0.20,    # Learning potential
    "goal_relevance": 0.15,      # How directly it serves the goal
    "complexity_penalty": 0.10,  # Cognitive load penalty
}


class SubGoal:
    """A decomposed subgoal with predicted outcomes."""

    def __init__(self, goal_id: str, description: str, parent_id: str = "",
                 depth: int = 0):
        self.goal_id = goal_id
        self.description = description
        self.parent_id = parent_id
        self.depth = depth
        self.status = "pending"  # pending, active, completed, failed, skipped
        self.steps: List[dict] = []  # [{tool, action, description, params}]
        self.predicted_outcome: dict = {}
        self.actual_outcome: dict = {}
        self.prediction_error: float = 0.0
        self.efe_score: float = 0.0
        self.children: List[str] = []  # child goal_ids
        self.context: dict = {}
        self.created = datetime.now().isoformat()
        self.completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "goal_id": self.goal_id,
            "description": self.description,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "status": self.status,
            "steps": self.steps,
            "predicted_outcome": self.predicted_outcome,
            "actual_outcome": self.actual_outcome,
            "prediction_error": self.prediction_error,
            "efe_score": self.efe_score,
            "children": self.children,
            "context": self.context,
            "created": self.created,
            "completed_at": self.completed_at,
        }


class ExecutionPlan:
    """A complete execution plan with ordered subgoals."""

    def __init__(self, plan_id: str, goal: str, language: str = "python"):
        self.plan_id = plan_id
        self.goal = goal
        self.language = language
        self.subgoals: Dict[str, SubGoal] = {}
        self.execution_order: List[str] = []  # goal_ids in execution order
        self.status = "planning"  # planning, executing, completed, failed
        self.created = datetime.now().isoformat()
        self.completed_at: Optional[str] = None
        self.total_efe: float = 0.0
        self.replan_count: int = 0
        self.context: dict = {}  # codebase context, user prefs, etc.

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "language": self.language,
            "subgoals": {k: v.to_dict() for k, v in self.subgoals.items()},
            "execution_order": self.execution_order,
            "status": self.status,
            "created": self.created,
            "completed_at": self.completed_at,
            "total_efe": self.total_efe,
            "replan_count": self.replan_count,
            "context": self.context,
        }


class CodePlanner:
    """
    Cognitive code planning engine.

    Implements:
    1. Hierarchical decomposition (goal → subgoals → steps)
    2. Active inference (EFE minimization for plan selection)
    3. Mental simulation (predict outcomes before execution)
    4. Adaptive replanning (update plan on prediction failures)
    5. Prior retrieval (query chunk memory for known patterns)
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._plans: Dict[str, ExecutionPlan] = {}
        self._plan_history: List[dict] = []
        self._client = None
        self._load()

    def _get_client(self):
        try:
            from google import genai
        except ImportError:
            return None
        if self._client is None:
            try:
                key = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
                api_key = key.get("gemini_api_key", key.get("GOOGLE_API_KEY", ""))
                self._client = genai.Client(api_key=api_key)
            except Exception as e:
                print(f"[CodePlanner] API client error: {e}")
        return self._client

    def _generate(self, prompt: str, system: str = "") -> str:
        try:
            from google.genai import types
        except ImportError:
            return ""
        client = self._get_client()
        if not client:
            return ""
        try:
            config = types.GenerateContentConfig(
                system_instruction=system if system else None,
                max_output_tokens=2048,
            )
            response = client.models.generate_content(
                model=PLANNER_MODEL,
                contents=prompt,
                config=config,
            )
            return response.text.strip()
        except Exception as e:
            print(f"[CodePlanner] Generation error: {e}")
            return ""

    def _load(self):
        if PLAN_HISTORY_FILE.exists():
            try:
                data = json.loads(PLAN_HISTORY_FILE.read_text(encoding="utf-8"))
                self._plan_history = data.get("history", [])
            except Exception:
                pass

    def _save_history(self):
        with self._lock:
            try:
                BRAIN_DIR.mkdir(parents=True, exist_ok=True)
                PLAN_HISTORY_FILE.write_text(json.dumps({
                    "history": self._plan_history[-200:],  # Keep last 200
                    "updated": datetime.now().isoformat(),
                }, indent=2), encoding="utf-8")
            except Exception:
                pass

    # ── Goal Decomposition ──────────────────────────────────────────────

    def decompose_goal(self, goal: str, codebase_context: str = "",
                       language: str = "python",
                       max_depth: int = 3) -> ExecutionPlan:
        """
        Decompose a coding goal into a hierarchical execution plan.

        Uses LLM-assisted decomposition with chunk memory retrieval.
        """
        plan_id = f"plan_{uuid.uuid4().hex[:8]}"
        plan = ExecutionPlan(plan_id, goal, language)

        # Step 1: Retrieve relevant chunks from code intelligence
        chunk_context = ""
        try:
            from brain.code_intelligence import get_code_intelligence
            ci = get_code_intelligence()
            chunks = ci.find_matching_chunks(code_snippet=goal, top_k=3)
            if chunks:
                chunk_context = "Known patterns:\n"
                for c in chunks:
                    chunk_context += f"- {c['name']} ({c['pattern_type']}): {c['description'][:100]}\n"
        except Exception:
            pass

        # Step 2: LLM decomposition
        system = """You are a senior software architect decomposing a coding task.
Break the goal into 3-7 subgoals, each with concrete steps.

Return ONLY valid JSON:
{
  "subgoals": [
    {
      "id": "sg1",
      "description": "what to accomplish",
      "steps": [
        {"tool": "code_helper|dev_agent|web_search|file_controller|browser_control", 
         "action": "specific action", 
         "description": "what to do"}
      ],
      "dependencies": [],
      "risk": "low|medium|high",
      "estimated_complexity": 1-10
    }
  ],
  "execution_order": ["sg1", "sg2", ...],
  "risks": ["potential issue 1"],
  "assumptions": ["assumption 1"]
}"""

        prompt = f"""Goal: {goal}
Language: {language}
{f'Codebase context: {codebase_context[:1000]}' if codebase_context else ''}
{chunk_context}

Decompose this into a concrete execution plan. Each subgoal should be independently testable."""

        result = self._generate(prompt, system=system)

        try:
            # Parse JSON from response
            json_str = result
            if "```" in json_str:
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            plan_data = json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            # Fallback: create a simple plan
            plan_data = {
                "subgoals": [{
                    "id": "sg1",
                    "description": goal,
                    "steps": [{"tool": "code_helper", "action": "build", "description": goal}],
                    "dependencies": [],
                    "risk": "medium",
                    "estimated_complexity": 5,
                }],
                "execution_order": ["sg1"],
                "risks": ["Fallback plan — LLM decomposition failed"],
                "assumptions": [],
            }

        # Build SubGoal objects
        for sg_data in plan_data.get("subgoals", []):
            sg = SubGoal(
                goal_id=sg_data["id"],
                description=sg_data.get("description", ""),
                depth=1,
            )
            sg.steps = sg_data.get("steps", [])
            sg.context = {
                "risk": sg_data.get("risk", "medium"),
                "complexity": sg_data.get("estimated_complexity", 5),
                "dependencies": sg_data.get("dependencies", []),
            }
            # Calculate EFE for this subgoal
            sg.efe_score = self._calculate_efe(sg)
            plan.subgoals[sg.goal_id] = sg

        plan.execution_order = plan_data.get("execution_order", list(plan.subgoals.keys()))
        plan.total_efe = sum(sg.efe_score for sg in plan.subgoals.values())
        plan.context = {
            "risks": plan_data.get("risks", []),
            "assumptions": plan_data.get("assumptions", []),
            "chunks_used": len(chunks) if 'chunks' in dir() else 0,
        }

        with self._lock:
            self._plans[plan_id] = plan

        return plan

    # ── Expected Free Energy (EFE) Calculation ──────────────────────────

    def _calculate_efe(self, subgoal: SubGoal) -> float:
        """
        Calculate Expected Free Energy for a subgoal.

        EFE = weighted sum of:
        - Expected cost (time/effort)
        - Expected risk (probability of failure)
        - Information gain (learning potential)
        - Goal relevance (how directly it serves the goal)
        - Complexity penalty (cognitive load)
        """
        ctx = subgoal.context

        # Estimate cost from step count and complexity
        step_count = len(subgoal.steps)
        complexity = ctx.get("complexity", 5)
        expected_cost = min(1.0, (step_count * 0.15 + complexity * 0.05))

        # Risk from context
        risk_map = {"low": 0.2, "medium": 0.5, "high": 0.8}
        expected_risk = risk_map.get(ctx.get("risk", "medium"), 0.5)

        # Information gain: higher for novel or uncertain tasks
        info_gain = 0.5  # Default moderate
        if subgoal.depth == 0:
            info_gain = 0.7  # Top-level goals have more learning potential

        # Goal relevance: subgoals at lower depth are more directly relevant
        goal_relevance = max(0.3, 1.0 - subgoal.depth * 0.2)

        # Complexity penalty
        complexity_penalty = min(1.0, complexity / 10.0)

        efe = (
            EFE_WEIGHTS["expected_cost"] * expected_cost +
            EFE_WEIGHTS["expected_risk"] * expected_risk +
            EFE_WEIGHTS["information_gain"] * (1.0 - info_gain) +  # Invert: lower EFE = better
            EFE_WEIGHTS["goal_relevance"] * (1.0 - goal_relevance) +
            EFE_WEIGHTS["complexity_penalty"] * complexity_penalty
        )

        return round(efe, 4)

    def select_best_plan(self, plans: List[ExecutionPlan]) -> ExecutionPlan:
        """Select the plan with lowest total EFE (best predicted outcome)."""
        if not plans:
            return None
        return min(plans, key=lambda p: p.total_efe)

    # ── Mental Simulation ───────────────────────────────────────────────

    def simulate_step(self, step: dict, codebase_context: str = "") -> dict:
        """
        Mentally simulate executing a step before actually doing it.
        Predicts: will it succeed? what output? what side effects?
        """
        system = """You are simulating a code execution step. Predict the outcome.
Return ONLY valid JSON:
{
  "predicted_success": true/false,
  "confidence": 0.0-1.0,
  "predicted_output": "what would happen",
  "potential_errors": ["possible error 1"],
  "side_effects": ["file changes, dependencies affected"],
  "estimated_time_seconds": 10
}"""

        prompt = f"""Step: {json.dumps(step)}
Context: {codebase_context[:500] if codebase_context else 'no context'}

Simulate this step. What would happen?"""

        result = self._generate(prompt, system=system)

        try:
            json_str = result
            if "```" in json_str:
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            return json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            return {
                "predicted_success": True,
                "confidence": 0.3,
                "predicted_output": "Could not simulate",
                "potential_errors": [],
                "side_effects": [],
                "estimated_time_seconds": 30,
            }

    def simulate_plan(self, plan: ExecutionPlan, codebase_context: str = "") -> dict:
        """
        Simulate an entire execution plan.
        Returns aggregate predictions and identifies high-risk steps.
        """
        results = []
        cumulative_time = 0
        cumulative_risk = 0.0

        for goal_id in plan.execution_order:
            sg = plan.subgoals.get(goal_id)
            if not sg:
                continue

            for step in sg.steps:
                sim = self.simulate_step(step, codebase_context)
                sg.predicted_outcome = sim
                results.append({
                    "goal_id": goal_id,
                    "step": step.get("description", ""),
                    "simulation": sim,
                })
                cumulative_time += sim.get("estimated_time_seconds", 30)
                if not sim.get("predicted_success", True):
                    cumulative_risk += 1.0 - sim.get("confidence", 0.5)

        # Identify high-risk steps
        high_risk = [r for r in results
                    if not r["simulation"].get("predicted_success", True)
                    or r["simulation"].get("confidence", 0.5) < 0.4]

        return {
            "total_steps": len(results),
            "estimated_time_seconds": cumulative_time,
            "cumulative_risk": round(cumulative_risk, 2),
            "high_risk_steps": high_risk,
            "overall_confidence": round(
                sum(r["simulation"].get("confidence", 0.5) for r in results)
                / max(len(results), 1), 2
            ),
        }

    # ── Adaptive Replanning ─────────────────────────────────────────────

    def record_step_outcome(self, plan_id: str, goal_id: str,
                            actual_outcome: dict, success: bool):
        """
        Record actual outcome and compute prediction error.
        If prediction error is high, trigger replanning.
        """
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return

            sg = plan.subgoals.get(goal_id)
            if not sg:
                return

            sg.actual_outcome = actual_outcome

            # Compute prediction error
            predicted = sg.predicted_outcome
            if predicted:
                pred_success = predicted.get("predicted_success", True)
                success_error = 0.0 if pred_success == success else 1.0
                pred_time = predicted.get("estimated_time_seconds", 30)
                actual_time = actual_outcome.get("elapsed_seconds", 30)
                time_error = abs(pred_time - actual_time) / max(pred_time, 1)
                sg.prediction_error = round(success_error + min(time_error, 1.0), 3)
            else:
                sg.prediction_error = 0.5  # No prediction = moderate error

            sg.status = "completed" if success else "failed"
            sg.completed_at = datetime.now().isoformat()

            # Record in history
            self._plan_history.append({
                "plan_id": plan_id,
                "goal_id": goal_id,
                "description": sg.description,
                "success": success,
                "prediction_error": sg.prediction_error,
                "timestamp": datetime.now().isoformat(),
            })
            self._save_history()

    def should_replan(self, plan_id: str) -> Tuple[bool, str]:
        """
        Check if the plan needs replanning based on accumulated prediction errors.
        """
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return False, "Plan not found"

            # Check for failed subgoals
            failed = [sg for sg in plan.subgoals.values() if sg.status == "failed"]
            if failed:
                return True, f"{len(failed)} subgoal(s) failed"

            # Check for high prediction errors
            high_error = [sg for sg in plan.subgoals.values()
                         if sg.prediction_error > 0.7 and sg.status != "pending"]
            if len(high_error) >= 2:
                return True, "Multiple high prediction errors"

            return False, ""

    def replan(self, plan_id: str, failure_context: str = "") -> Optional[ExecutionPlan]:
        """
        Generate a new plan based on what went wrong.
        Learns from failures to create a better plan.
        """
        with self._lock:
            old_plan = self._plans.get(plan_id)
            if not old_plan:
                return None

            # Extract failure information
            failures = []
            for sg in old_plan.subgoals.values():
                if sg.status == "failed":
                    failures.append({
                        "description": sg.description,
                        "error": sg.actual_outcome.get("error", "unknown"),
                        "prediction_error": sg.prediction_error,
                    })

            # Create new plan with failure context
            new_goal = f"{old_plan.goal} (REPLANNED — previous attempt had {len(failures)} failure(s))"
            if failure_context:
                new_goal += f"\nFailure context: {failure_context}"

            new_plan = self.decompose_goal(
                goal=new_goal,
                codebase_context=json.dumps(failures)[:500],
                language=old_plan.language,
            )
            new_plan.replan_count = old_plan.replan_count + 1

            # Archive old plan
            old_plan.status = "replanned"

            return new_plan

    # ── Query ───────────────────────────────────────────────────────────

    def get_plan(self, plan_id: str) -> Optional[dict]:
        """Get a plan by ID."""
        with self._lock:
            plan = self._plans.get(plan_id)
            return plan.to_dict() if plan else None

    def get_active_plans(self) -> List[dict]:
        """Get all active (non-completed) plans."""
        with self._lock:
            return [p.to_dict() for p in self._plans.values()
                   if p.status in ("planning", "executing")]

    def get_plan_stats(self) -> dict:
        """Get planning statistics."""
        with self._lock:
            total = len(self._plans)
            completed = sum(1 for p in self._plans.values() if p.status == "completed")
            failed = sum(1 for p in self._plans.values() if p.status == "failed")
            replanned = sum(1 for p in self._plans.values() if p.replan_count > 0)

            history = self._plan_history[-50:]
            avg_error = (sum(h.get("prediction_error", 0) for h in history)
                        / max(len(history), 1))

            return {
                "total_plans": total,
                "completed": completed,
                "failed": failed,
                "replanned": replanned,
                "avg_prediction_error": round(avg_error, 3),
                "history_entries": len(self._plan_history),
            }

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """Format planner state for system prompt injection."""
        stats = self.get_plan_stats()
        parts = [
            "[CODE PLANNER — Hierarchical goal decomposition]",
            f"Plans: {stats['total_plans']} total, {stats['completed']} completed, "
            f"{stats['failed']} failed | Avg prediction error: {stats['avg_prediction_error']:.2f}",
        ]

        # Recent plan patterns from history
        if self._plan_history:
            recent = self._plan_history[-10:]
            success_rate = sum(1 for h in recent if h.get("success")) / max(len(recent), 1)
            parts.append(f"Recent success rate: {success_rate:.0%}")

        result = "\n".join(parts)
        return result[:max_chars]


# ── Singleton ───────────────────────────────────────────────────────────

_code_planner = None
_cp_lock = threading.Lock()


def get_code_planner() -> CodePlanner:
    """Get singleton CodePlanner instance."""
    global _code_planner
    if _code_planner is None:
        with _cp_lock:
            if _code_planner is None:
                _code_planner = CodePlanner()
    return _code_planner