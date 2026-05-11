"""
autonomous_planner.py — Long-Horizon Autonomous Planning Engine
MCTS-inspired planning with plan creation, evaluation, replanning,
and multi-step execution tracking for Friday's autonomous goal pursuit.
"""
import json
import time
import threading
import uuid
import math
import random
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

# ── Paths ──────────────────────────────────────────────────────────────

BRAIN_DIR = Path(__file__).resolve().parent
PLANNER_FILE = BRAIN_DIR / "planner_state.json"

# ── Constants ──────────────────────────────────────────────────────────

MAX_PLAN_STEPS = 20
MAX_ALTERNATIVES = 5
MAX_ACTIVE_PLANS = 10
SIMULATION_ITERATIONS = 50
EXPLORATION_CONSTANT = 1.41  # UCB1 exploration


# ── Helpers ────────────────────────────────────────────────────────────

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def _timestamp() -> float:
    return time.time()

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))

def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ── Data Classes ───────────────────────────────────────────────────────

class PlanStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class StepStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """A single step in a plan."""
    step_id: str
    description: str
    order: int
    status: StepStatus = StepStatus.PENDING
    dependencies: List[str] = field(default_factory=list)  # step_ids this depends on
    estimated_duration: float = 0.0  # seconds
    actual_duration: float = 0.0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    agent: Optional[str] = None  # which agent should execute this
    substeps: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "order": self.order,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "estimated_duration": self.estimated_duration,
            "actual_duration": self.actual_duration,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result[:500] if self.result else None,
            "error": self.error,
            "agent": self.agent,
            "substeps": self.substeps,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PlanStep":
        return cls(
            step_id=d["step_id"],
            description=d["description"],
            order=d["order"],
            status=StepStatus(d.get("status", "pending")),
            dependencies=d.get("dependencies", []),
            estimated_duration=d.get("estimated_duration", 0),
            actual_duration=d.get("actual_duration", 0),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            result=d.get("result"),
            error=d.get("error"),
            agent=d.get("agent"),
            substeps=d.get("substeps", []),
            metadata=d.get("metadata", {}),
        )


@dataclass
class Plan:
    """A multi-step plan with alternatives and success tracking."""
    plan_id: str
    goal: str
    description: str
    status: PlanStatus = PlanStatus.DRAFT
    steps: List[PlanStep] = field(default_factory=list)
    alternatives: List["Plan"] = field(default_factory=list)
    success_probability: float = 0.5
    risk_factors: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    parent_plan_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "description": self.description,
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
            "alternatives": [a.to_dict() for a in self.alternatives[:MAX_ALTERNATIVES]],
            "success_probability": round(self.success_probability, 3),
            "risk_factors": self.risk_factors,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "parent_plan_id": self.parent_plan_id,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Plan":
        plan = cls(
            plan_id=d["plan_id"],
            goal=d["goal"],
            description=d.get("description", ""),
            status=PlanStatus(d.get("status", "draft")),
            success_probability=d.get("success_probability", 0.5),
            risk_factors=d.get("risk_factors", []),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            parent_plan_id=d.get("parent_plan_id"),
            tags=d.get("tags", []),
            metadata=d.get("metadata", {}),
        )
        plan.steps = [PlanStep.from_dict(s) for s in d.get("steps", [])]
        plan.alternatives = [cls.from_dict(a) for a in d.get("alternatives", [])]
        return plan

    @property
    def progress(self) -> float:
        """Completion percentage (0-1)."""
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)
        return completed / len(self.steps)

    @property
    def next_step(self) -> Optional[PlanStep]:
        """Get the next actionable step (pending with all dependencies met)."""
        completed_ids = {s.step_id for s in self.steps if s.status == StepStatus.COMPLETED}
        for step in sorted(self.steps, key=lambda s: s.order):
            if step.status == StepStatus.PENDING:
                if all(dep in completed_ids for dep in step.dependencies):
                    return step
        return None

    @property
    def is_blocked(self) -> bool:
        """Check if plan is blocked (all pending steps have unmet dependencies)."""
        completed_ids = {s.step_id for s in self.steps if s.status == StepStatus.COMPLETED}
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                if all(dep in completed_ids for dep in step.dependencies):
                    return False  # At least one step is actionable
        return True  # All pending steps are blocked


@dataclass
class MCTSNode:
    """Node in Monte Carlo Tree Search."""
    state: Dict[str, Any]
    action: Optional[str] = None
    parent: Optional["MCTSNode"] = None
    children: List["MCTSNode"] = field(default_factory=list)
    visits: int = 0
    total_reward: float = 0.0

    @property
    def avg_reward(self) -> float:
        return self.total_reward / max(self.visits, 1)

    def ucb1(self, exploration: float = EXPLORATION_CONSTANT) -> float:
        if self.visits == 0:
            return float("inf")
        if self.parent and self.parent.visits > 0:
            return self.avg_reward + exploration * math.sqrt(
                math.log(self.parent.visits) / self.visits
            )
        return self.avg_reward


# ── Planner Engine ─────────────────────────────────────────────────────

class AutonomousPlanner:
    """
    Long-horizon planning engine with MCTS-inspired search,
    plan evaluation, replanning, and multi-step execution.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data = self._load()
        self._plans: Dict[str, Plan] = {}
        self._plan_history: List[Dict] = []
        self._replan_count = 0
        self._deserialize()

    # ── Persistence ─────────────────────────────────────────────────

    def _load(self) -> dict:
        if PLANNER_FILE.exists():
            try:
                raw = PLANNER_FILE.read_text(encoding="utf-8")
                return json.loads(raw)
            except (json.JSONDecodeError, IOError):
                pass
        return self._empty_store()

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": _now(),
                "last_update": _now(),
                "total_plans_created": 0,
                "total_plans_completed": 0,
                "total_replans": 0,
                "total_steps_executed": 0,
            },
            "plans": {},
            "history": [],
        }

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._data["plans"] = {
                pid: p.to_dict() for pid, p in self._plans.items()
            }
            self._data["history"] = self._plan_history[-100:]
            self._data["meta"]["last_update"] = _now()
            PLANNER_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )

    def _deserialize(self):
        for pid, pd in self._data.get("plans", {}).items():
            try:
                self._plans[pid] = Plan.from_dict(pd)
            except Exception:
                pass
        self._plan_history = self._data.get("history", [])

    # ── Plan Creation ───────────────────────────────────────────────

    def create_plan(
        self,
        goal: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        description: str = "",
        tags: Optional[List[str]] = None,
        risk_factors: Optional[List[str]] = None,
    ) -> Plan:
        """Create a new plan for a goal."""
        with self._lock:
            plan = Plan(
                plan_id=_new_id(),
                goal=goal,
                description=description or f"Plan for: {goal}",
                created_at=_now(),
                updated_at=_now(),
                tags=tags or [],
                risk_factors=risk_factors or [],
            )

            if steps:
                for i, step_def in enumerate(steps):
                    step = PlanStep(
                        step_id=_new_id(),
                        description=step_def.get("description", f"Step {i+1}"),
                        order=i,
                        dependencies=step_def.get("dependencies", []),
                        estimated_duration=step_def.get("estimated_duration", 0),
                        agent=step_def.get("agent"),
                        metadata=step_def.get("metadata", {}),
                    )
                    plan.steps.append(step)

            # Estimate success probability
            plan.success_probability = self._estimate_success(plan)

            self._plans[plan.plan_id] = plan
            self._data["meta"]["total_plans_created"] += 1
            self._save()

            self._log_event("plan_created", plan.plan_id, {"goal": goal})
            return plan

    def add_step(
        self,
        plan_id: str,
        description: str,
        dependencies: Optional[List[str]] = None,
        estimated_duration: float = 0,
        agent: Optional[str] = None,
    ) -> Optional[PlanStep]:
        """Add a step to an existing plan."""
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return None
            step = PlanStep(
                step_id=_new_id(),
                description=description,
                order=len(plan.steps),
                dependencies=dependencies or [],
                estimated_duration=estimated_duration,
                agent=agent,
            )
            plan.steps.append(step)
            plan.updated_at = _now()
            plan.success_probability = self._estimate_success(plan)
            self._save()
            return step

    # ── Plan Decomposition (MCTS-inspired) ──────────────────────────

    def decompose_goal(
        self,
        goal: str,
        context: str = "",
        max_depth: int = 3,
        iterations: int = SIMULATION_ITERATIONS,
    ) -> Plan:
        """
        Use MCTS-inspired search to find the best plan decomposition.
        Simulates multiple decompositions and selects the most promising.
        """
        root = MCTSNode(state={"goal": goal, "depth": 0, "steps": []})

        for _ in range(iterations):
            node = self._select(root)
            if node.state["depth"] < max_depth:
                child = self._expand(node, goal, context)
                reward = self._simulate(child, goal)
                self._backpropagate(child, reward)
            else:
                reward = self._simulate(node, goal)
                self._backpropagate(node, reward)

        # Extract best plan from tree
        best_child = max(root.children, key=lambda c: c.avg_reward) if root.children else root
        steps = best_child.state.get("steps", [])

        return self.create_plan(
            goal=goal,
            steps=steps,
            description=f"MCTS-decomposed plan for: {goal}",
        )

    def _select(self, node: MCTSNode) -> MCTSNode:
        """Select most promising node using UCB1."""
        while node.children:
            node = max(node.children, key=lambda c: c.ucb1())
        return node

    def _expand(self, node: MCTSNode, goal: str, context: str) -> MCTSNode:
        """Expand node with possible next steps."""
        possible_actions = self._generate_possible_steps(
            goal, node.state.get("depth", 0), node.state.get("steps", [])
        )
        if not possible_actions:
            return node

        action = random.choice(possible_actions)
        new_steps = node.state["steps"] + [action]
        child = MCTSNode(
            state={"goal": goal, "depth": node.state["depth"] + 1, "steps": new_steps},
            action=action["description"],
            parent=node,
        )
        node.children.append(child)
        return child

    def _simulate(self, node: MCTSNode, goal: str) -> float:
        """Simulate plan execution to estimate success probability."""
        steps = node.state.get("steps", [])
        if not steps:
            return 0.0

        # Heuristic scoring
        score = 0.5  # Base

        # Fewer steps = higher probability (up to a point)
        step_count = len(steps)
        if 2 <= step_count <= 8:
            score += 0.2
        elif step_count > 12:
            score -= 0.1

        # Steps with dependencies show planning depth
        has_deps = sum(1 for s in steps if s.get("dependencies"))
        if has_deps > 0:
            score += 0.1

        # Steps with agents assigned = more concrete
        has_agents = sum(1 for s in steps if s.get("agent"))
        if has_agents > 0:
            score += 0.1

        # Random variation for exploration
        score += random.gauss(0, 0.1)
        return _clamp(score)

    def _backpropagate(self, node: MCTSNode, reward: float):
        """Backpropagate reward up the tree."""
        while node:
            node.visits += 1
            node.total_reward += reward
            node = node.parent

    def _generate_possible_steps(
        self, goal: str, depth: int, existing_steps: List[Dict]
    ) -> List[Dict[str, Any]]:
        """Generate possible next steps for plan decomposition."""
        goal_lower = goal.lower()
        templates = []

        # Analyze goal type and suggest appropriate steps
        if any(w in goal_lower for w in ["build", "create", "develop", "implement"]):
            templates = [
                {"description": "Analyze requirements and constraints", "agent": "software_architect"},
                {"description": "Design architecture and components", "agent": "software_architect"},
                {"description": "Implement core functionality", "agent": "senior_developer"},
                {"description": "Write tests", "agent": "api_tester"},
                {"description": "Security review", "agent": "security_engineer"},
                {"description": "Performance optimization", "agent": "performance_benchmarker"},
                {"description": "Documentation", "agent": "technical_writer"},
            ]
        elif any(w in goal_lower for w in ["research", "analyze", "investigate", "understand"]):
            templates = [
                {"description": "Gather initial information and sources", "agent": "data_engineer"},
                {"description": "Deep analysis of findings", "agent": "ai_engineer"},
                {"description": "Cross-reference and validate", "agent": "code_reviewer"},
                {"description": "Synthesize into actionable insights", "agent": "technical_writer"},
            ]
        elif any(w in goal_lower for w in ["fix", "debug", "resolve", "repair"]):
            templates = [
                {"description": "Reproduce and characterize the issue", "agent": "api_tester"},
                {"description": "Root cause analysis", "agent": "code_reviewer"},
                {"description": "Implement fix", "agent": "senior_developer"},
                {"description": "Verify fix and regression test", "agent": "api_tester"},
                {"description": "Document the fix", "agent": "technical_writer"},
            ]
        elif any(w in goal_lower for w in ["design", "ui", "ux", "interface"]):
            templates = [
                {"description": "User research and requirements", "agent": "ux_architect"},
                {"description": "Create wireframes and prototypes", "agent": "ui_designer"},
                {"description": "Implement frontend", "agent": "frontend_developer"},
                {"description": "Accessibility audit", "agent": "accessibility_auditor"},
                {"description": "User testing", "agent": "workflow_optimizer"},
            ]
        else:
            templates = [
                {"description": f"Analyze: {goal}", "agent": None},
                {"description": f"Plan approach for: {goal}", "agent": None},
                {"description": f"Execute: {goal}", "agent": None},
                {"description": f"Verify results of: {goal}", "agent": None},
            ]

        # Filter out already-added steps
        existing_descs = {s.get("description", "").lower() for s in existing_steps}
        available = [t for t in templates if t["description"].lower() not in existing_descs]

        return available[:5]

    # ── Plan Evaluation ─────────────────────────────────────────────

    def _estimate_success(self, plan: Plan) -> float:
        """Estimate plan success probability based on structure."""
        if not plan.steps:
            return 0.3

        score = 0.5

        # Step count factor
        n = len(plan.steps)
        if 3 <= n <= 10:
            score += 0.15
        elif n > 15:
            score -= 0.1

        # Dependencies show planning
        dep_count = sum(len(s.dependencies) for s in plan.steps)
        if dep_count > 0:
            score += 0.1

        # Agent assignment shows specificity
        agent_count = sum(1 for s in plan.steps if s.agent)
        score += 0.05 * min(agent_count, 5)

        # Risk factors penalty
        score -= 0.05 * len(plan.risk_factors)

        return _clamp(score)

    def evaluate_plan(self, plan_id: str) -> Dict[str, Any]:
        """Evaluate a plan's viability and structure."""
        plan = self._plans.get(plan_id)
        if not plan:
            return {"error": f"Plan {plan_id} not found"}

        total_steps = len(plan.steps)
        completed = sum(1 for s in plan.steps if s.status == StepStatus.COMPLETED)
        failed = sum(1 for s in plan.steps if s.status == StepStatus.FAILED)
        blocked = plan.is_blocked

        return {
            "plan_id": plan_id,
            "goal": plan.goal,
            "status": plan.status.value,
            "total_steps": total_steps,
            "completed": completed,
            "failed": failed,
            "progress": round(plan.progress, 3),
            "success_probability": round(plan.success_probability, 3),
            "is_blocked": blocked,
            "next_step": plan.next_step.description if plan.next_step else None,
            "risk_factors": plan.risk_factors,
            "has_alternatives": len(plan.alternatives) > 0,
        }

    # ── Plan Execution ──────────────────────────────────────────────

    def start_plan(self, plan_id: str) -> Optional[Plan]:
        """Activate a plan for execution."""
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return None
            plan.status = PlanStatus.ACTIVE
            plan.started_at = _now()
            plan.updated_at = _now()
            self._save()
            self._log_event("plan_started", plan_id, {})
            return plan

    def complete_step(self, plan_id: str, step_id: str, result: str = "") -> bool:
        """Mark a step as completed."""
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return False
            for step in plan.steps:
                if step.step_id == step_id:
                    step.status = StepStatus.COMPLETED
                    step.completed_at = _now()
                    step.result = result
                    if step.started_at:
                        try:
                            start = time.mktime(time.strptime(step.started_at, "%Y-%m-%dT%H:%M:%S"))
                            step.actual_duration = time.time() - start
                        except Exception:
                            pass
                    plan.updated_at = _now()
                    self._data["meta"]["total_steps_executed"] += 1

                    # Check if plan is complete
                    if all(s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in plan.steps):
                        plan.status = PlanStatus.COMPLETED
                        plan.completed_at = _now()
                        self._data["meta"]["total_plans_completed"] += 1
                        self._log_event("plan_completed", plan_id, {"goal": plan.goal})

                    self._save()
                    return True
            return False

    def fail_step(self, plan_id: str, step_id: str, error: str = "") -> bool:
        """Mark a step as failed."""
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return False
            for step in plan.steps:
                if step.step_id == step_id:
                    step.status = StepStatus.FAILED
                    step.error = error
                    plan.updated_at = _now()
                    self._save()
                    self._log_event("step_failed", plan_id,
                                   {"step": step.description, "error": error})
                    return True
            return False

    def start_step(self, plan_id: str, step_id: str) -> bool:
        """Mark a step as in-progress."""
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                return False
            for step in plan.steps:
                if step.step_id == step_id:
                    step.status = StepStatus.ACTIVE
                    step.started_at = _now()
                    plan.updated_at = _now()
                    self._save()
                    return True
            return False

    # ── Replanning ──────────────────────────────────────────────────

    def replan(self, plan_id: str, reason: str = "") -> Optional[Plan]:
        """Create a revised plan when the current one fails or stalls."""
        original = self._plans.get(plan_id)
        if not original:
            return None

        with self._lock:
            # Identify completed and failed steps
            completed_steps = [s for s in original.steps if s.status == StepStatus.COMPLETED]
            failed_steps = [s for s in original.steps if s.status == StepStatus.FAILED]
            remaining_steps = [s for s in original.steps if s.status == StepStatus.PENDING]

            # Create new plan preserving completed work
            new_steps = []
            for s in completed_steps:
                new_steps.append({
                    "description": s.description,
                    "dependencies": s.dependencies,
                    "agent": s.agent,
                    "metadata": {"completed_in": original.plan_id},
                })

            # Re-add failed steps with modifications
            for s in failed_steps:
                new_steps.append({
                    "description": f"[RETRY] {s.description}",
                    "dependencies": s.dependencies,
                    "agent": s.agent,
                    "metadata": {"retried_from": original.plan_id, "previous_error": s.error},
                })

            # Add remaining steps
            for s in remaining_steps:
                new_steps.append({
                    "description": s.description,
                    "dependencies": s.dependencies,
                    "agent": s.agent,
                })

            new_plan = self.create_plan(
                goal=original.goal,
                steps=new_steps,
                description=f"Replanned from {plan_id}: {reason}",
                tags=original.tags + ["replan"],
                risk_factors=original.risk_factors + [f"Previous plan failed: {reason}"],
            )

            # Mark original as abandoned
            original.status = PlanStatus.ABANDONED
            original.updated_at = _now()
            new_plan.parent_plan_id = plan_id

            self._replan_count += 1
            self._data["meta"]["total_replans"] += 1
            self._save()

            self._log_event("replan", new_plan.plan_id,
                           {"original": plan_id, "reason": reason})
            return new_plan

    # ── Query ───────────────────────────────────────────────────────

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        return self._plans.get(plan_id)

    def get_active_plans(self) -> List[Plan]:
        return [p for p in self._plans.values() if p.status == PlanStatus.ACTIVE]

    def get_all_plans(self, status: Optional[PlanStatus] = None) -> List[Plan]:
        if status:
            return [p for p in self._plans.values() if p.status == status]
        return list(self._plans.values())

    def get_next_actions(self) -> List[Dict[str, Any]]:
        """Get the next actionable step from all active plans."""
        actions = []
        for plan in self.get_active_plans():
            ns = plan.next_step
            if ns:
                actions.append({
                    "plan_id": plan.plan_id,
                    "goal": plan.goal,
                    "step_id": ns.step_id,
                    "description": ns.description,
                    "agent": ns.agent,
                    "dependencies_met": True,
                })
        return actions

    # ── Logging ─────────────────────────────────────────────────────

    def _log_event(self, event_type: str, plan_id: str, details: Dict):
        self._plan_history.append({
            "event": event_type,
            "plan_id": plan_id,
            "details": details,
            "timestamp": _now(),
        })
        if len(self._plan_history) > 200:
            self._plan_history = self._plan_history[-100:]

    # ── Prompt / Stats ──────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """Format planner state for system prompt injection."""
        active = self.get_active_plans()
        lines = ["## Autonomous Planner"]
        lines.append(f"- Total plans: {len(self._plans)}")
        lines.append(f"- Active plans: {len(active)}")
        lines.append(f"- Total replans: {self._replan_count}")

        if active:
            lines.append("\n### Active Plans:")
            for p in active[:5]:
                ns = p.next_step
                next_desc = ns.description if ns else "blocked"
                lines.append(
                    f"  - [{p.plan_id}] {p.goal} "
                    f"({p.progress:.0%} done, next: {next_desc})"
                )

        actions = self.get_next_actions()
        if actions:
            lines.append("\n### Next Actions:")
            for a in actions[:3]:
                lines.append(f"  - {a['description']} (agent: {a.get('agent', 'any')})")

        return "\n".join(lines)[:max_chars]

    def get_stats(self) -> dict:
        """Get planner statistics."""
        with self._lock:
            return {
                "total_plans": len(self._plans),
                "active_plans": len(self.get_active_plans()),
                "completed_plans": self._data["meta"].get("total_plans_completed", 0),
                "total_steps_executed": self._data["meta"].get("total_steps_executed", 0),
                "total_replans": self._replan_count,
                "history_size": len(self._plan_history),
            }


# ── Singleton ──────────────────────────────────────────────────────────

_planner_instance = None
_planner_lock = threading.Lock()


def get_autonomous_planner() -> AutonomousPlanner:
    """Get singleton AutonomousPlanner instance."""
    global _planner_instance
    if _planner_instance is None:
        with _planner_lock:
            if _planner_instance is None:
                _planner_instance = AutonomousPlanner()
    return _planner_instance
