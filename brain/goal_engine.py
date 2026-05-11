#!/usr/bin/env python3
"""
goal_engine.py — FRIDAY Hierarchical Goal Management Engine
=============================================================

Implements a hierarchical goal system that enables Friday to set, track,
decompose, and prioritize goals across multiple levels of abstraction.

Inspired by:

  [GE-1] Goal-Setting Theory (Locke & Latham, 2002)
         — Specific, challenging goals lead to higher performance than
           vague "do your best" goals. Goals need feedback mechanisms.

  [GE-2] Hierarchical Task Network (HTN) Planning
         — Complex goals decompose into subgoals, which decompose further
           until reaching primitive actions. This mirrors how humans plan.

  [GE-3] Self-Regulation Theory (Carver & Scheier, 1998)
         — Behavior is guided by feedback loops: set goal → monitor progress →
           adjust. Discrepancy between current state and goal drives action.

  [GE-4] Implementation Intentions (Gollwitzer, 1999)
         — "If-then" plans that specify when, where, and how to pursue goals
           dramatically increase follow-through.

Key behaviors:
  - Hierarchical goals with parent-child relationships
  - Priority-based ordering with automatic re-prioritization
  - LLM-powered goal decomposition for complex goals
  - Status lifecycle: pending → active → completed/abandoned
  - Metrics tracking per goal (progress, attempts, time spent)
  - Full persistence and thread-safe operation
"""

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Constants ──────────────────────────────────────────────────────────────

BRAIN_DIR = Path(__file__).resolve().parent
BASE_DIR = BRAIN_DIR.parent
GOAL_FILE = BRAIN_DIR / "goal_state.json"

# Goal management
MAX_GOALS = 200
MAX_SUBGOALS_PER_GOAL = 20
MAX_GOAL_DEPTH = 5
DEFAULT_PRIORITY = 5          # 1 = highest, 10 = lowest
GOAL_TIMEOUT_DAYS = 90        # auto-abandon after this many days inactive

# Decomposition
DECOMPOSE_MIN_SUBGOALS = 2
DECOMPOSE_MAX_SUBGOALS = 7
DECOMPOSE_MODEL = "gemini-2.5-flash"


# ── Data Classes ───────────────────────────────────────────────────────────

class GoalStatus(Enum):
    """Lifecycle states for a goal."""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    BLOCKED = "blocked"


@dataclass
class Goal:
    """A single goal with hierarchical structure and metrics."""
    id: str
    description: str
    priority: int = DEFAULT_PRIORITY
    status: GoalStatus = GoalStatus.PENDING
    parent_goal: Optional[str] = None       # parent goal ID
    subgoals: List[str] = field(default_factory=list)  # child goal IDs
    created_at: str = ""
    updated_at: str = ""
    deadline: Optional[str] = None
    completed_at: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    implementation_plan: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at
        if not self.metrics:
            self.metrics = {
                "progress": 0.0,       # 0.0 to 1.0
                "attempts": 0,
                "time_spent_s": 0.0,
                "blockers": [],
            }

    def to_dict(self) -> dict:
        """Serialize goal to dictionary."""
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority,
            "status": self.status.value,
            "parent_goal": self.parent_goal,
            "subgoals": self.subgoals,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deadline": self.deadline,
            "completed_at": self.completed_at,
            "tags": self.tags,
            "metrics": self.metrics,
            "implementation_plan": self.implementation_plan,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Goal":
        """Deserialize goal from dictionary."""
        data = dict(data)  # copy
        data["status"] = GoalStatus(data.get("status", "pending"))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class GoalMetrics:
    """Aggregate metrics across all goals."""
    total_goals: int = 0
    active_goals: int = 0
    completed_goals: int = 0
    abandoned_goals: int = 0
    blocked_goals: int = 0
    avg_completion_time_s: float = 0.0
    completion_rate: float = 0.0


# ── Goal Engine ────────────────────────────────────────────────────────────

class GoalEngine:
    """
    Hierarchical goal management system.

    Manages goals as a tree structure where complex goals decompose into
    subgoals. Supports LLM-powered decomposition, priority-based ordering,
    and progress tracking.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._goals: Dict[str, Goal] = {}
        self._data = self._load()
        self._restore_goals()

    # ── Persistence ────────────────────────────────────────────────────

    def _load(self) -> dict:
        """Load goal state from disk."""
        if GOAL_FILE.exists():
            try:
                raw = json.loads(GOAL_FILE.read_text(encoding="utf-8"))
                return raw
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "meta": {"version": 1, "total_created": 0, "total_completed": 0},
            "goals": {},
        }

    def _save(self):
        """Persist goal state to disk."""
        with self._lock:
            # Serialize all goals
            self._data["goals"] = {
                gid: goal.to_dict() for gid, goal in self._goals.items()
            }
            self._data["meta"]["last_update"] = datetime.now().isoformat()

        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        GOAL_FILE.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )

    def _restore_goals(self):
        """Restore Goal objects from persisted data."""
        with self._lock:
            for gid, gdata in self._data.get("goals", {}).items():
                try:
                    self._goals[gid] = Goal.from_dict(gdata)
                except Exception:
                    pass

    # ── Goal CRUD ──────────────────────────────────────────────────────

    def create_goal(self, description: str, priority: int = DEFAULT_PRIORITY,
                    parent_goal: Optional[str] = None,
                    deadline: Optional[str] = None,
                    tags: Optional[List[str]] = None) -> Goal:
        """Create a new goal."""
        with self._lock:
            if len(self._goals) >= MAX_GOALS:
                # Evict oldest abandoned goals
                self._evict_abandoned()

            goal_id = f"goal_{uuid.uuid4().hex[:12]}"
            goal = Goal(
                id=goal_id,
                description=description,
                priority=max(1, min(10, priority)),
                parent_goal=parent_goal,
                deadline=deadline,
                tags=tags or [],
            )

            # Wire parent-child
            if parent_goal and parent_goal in self._goals:
                parent = self._goals[parent_goal]
                if len(parent.subgoals) < MAX_SUBGOALS_PER_GOAL:
                    parent.subgoals.append(goal_id)
                    parent.updated_at = datetime.now().isoformat()

            self._goals[goal_id] = goal
            self._data["meta"]["total_created"] = (
                self._data["meta"].get("total_created", 0) + 1
            )

        self._save()
        return goal

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get a goal by ID."""
        with self._lock:
            return self._goals.get(goal_id)

    def update_status(self, goal_id: str, status: GoalStatus,
                      progress: Optional[float] = None) -> bool:
        """Update a goal's status and optionally its progress."""
        with self._lock:
            goal = self._goals.get(goal_id)
            if not goal:
                return False

            goal.status = status
            goal.updated_at = datetime.now().isoformat()

            if status == GoalStatus.COMPLETED:
                goal.completed_at = datetime.now().isoformat()
                goal.metrics["progress"] = 1.0
                self._data["meta"]["total_completed"] = (
                    self._data["meta"].get("total_completed", 0) + 1
                )
            elif progress is not None:
                goal.metrics["progress"] = max(0.0, min(1.0, progress))

        self._save()
        return True

    def update_progress(self, goal_id: str, progress: float,
                        time_spent: float = 0.0) -> bool:
        """Update goal progress and time tracking."""
        with self._lock:
            goal = self._goals.get(goal_id)
            if not goal:
                return False

            goal.metrics["progress"] = max(0.0, min(1.0, progress))
            goal.metrics["time_spent_s"] = (
                goal.metrics.get("time_spent_s", 0.0) + time_spent
            )
            goal.metrics["attempts"] = goal.metrics.get("attempts", 0) + 1
            goal.updated_at = datetime.now().isoformat()

            # Auto-complete if progress reaches 1.0
            if progress >= 1.0 and goal.status == GoalStatus.ACTIVE:
                goal.status = GoalStatus.COMPLETED
                goal.completed_at = datetime.now().isoformat()
                self._data["meta"]["total_completed"] = (
                    self._data["meta"].get("total_completed", 0) + 1
                )

        self._save()
        return True

    def add_subgoal(self, parent_id: str, description: str,
                    priority: int = DEFAULT_PRIORITY,
                    tags: Optional[List[str]] = None) -> Optional[Goal]:
        """Add a subgoal under an existing goal."""
        with self._lock:
            parent = self._goals.get(parent_id)
            if not parent:
                return None
            if len(parent.subgoals) >= MAX_SUBGOALS_PER_GOAL:
                return None

        # Create the subgoal with parent reference
        return self.create_goal(
            description=description,
            priority=priority,
            parent_goal=parent_id,
            tags=tags,
        )

    def add_blocker(self, goal_id: str, blocker: str) -> bool:
        """Add a blocker to a goal."""
        with self._lock:
            goal = self._goals.get(goal_id)
            if not goal:
                return False
            blockers = goal.metrics.setdefault("blockers", [])
            if blocker not in blockers:
                blockers.append(blocker)
            if goal.status == GoalStatus.ACTIVE:
                goal.status = GoalStatus.BLOCKED
            goal.updated_at = datetime.now().isoformat()

        self._save()
        return True

    def remove_blocker(self, goal_id: str, blocker: str) -> bool:
        """Remove a blocker from a goal."""
        with self._lock:
            goal = self._goals.get(goal_id)
            if not goal:
                return False
            blockers = goal.metrics.get("blockers", [])
            if blocker in blockers:
                blockers.remove(blocker)
            if not blockers and goal.status == GoalStatus.BLOCKED:
                goal.status = GoalStatus.ACTIVE
            goal.updated_at = datetime.now().isoformat()

        self._save()
        return True

    # ── Goal Queries ───────────────────────────────────────────────────

    def get_active_goals(self) -> List[Goal]:
        """Get all active (non-terminal) goals, sorted by priority."""
        with self._lock:
            active = [
                g for g in self._goals.values()
                if g.status in (GoalStatus.ACTIVE, GoalStatus.PENDING, GoalStatus.BLOCKED)
            ]
        return sorted(active, key=lambda g: (g.priority, g.created_at))

    def get_root_goals(self) -> List[Goal]:
        """Get top-level goals (no parent)."""
        with self._lock:
            return sorted(
                [g for g in self._goals.values() if not g.parent_goal],
                key=lambda g: (g.priority, g.created_at)
            )

    def get_subgoals(self, goal_id: str) -> List[Goal]:
        """Get direct subgoals of a goal."""
        with self._lock:
            goal = self._goals.get(goal_id)
            if not goal:
                return []
            return [
                self._goals[sid] for sid in goal.subgoals
                if sid in self._goals
            ]

    def get_goal_tree(self, root_id: Optional[str] = None,
                      max_depth: int = MAX_GOAL_DEPTH) -> Dict[str, Any]:
        """Get the full goal tree structure."""
        def _build_tree(goal_id: str, depth: int) -> Dict[str, Any]:
            if depth >= max_depth:
                return {"id": goal_id, "truncated": True}
            goal = self._goals.get(goal_id)
            if not goal:
                return {"id": goal_id, "missing": True}
            node = {
                "id": goal.id,
                "description": goal.description,
                "status": goal.status.value,
                "priority": goal.priority,
                "progress": goal.metrics.get("progress", 0.0),
                "children": [],
            }
            for sid in goal.subgoals:
                child = _build_tree(sid, depth + 1)
                if child:
                    node["children"].append(child)
            return node

        with self._lock:
            if root_id:
                return _build_tree(root_id, 0)
            else:
                roots = [
                    g for g in self._goals.values() if not g.parent_goal
                ]
                return {
                    "roots": [_build_tree(g.id, 0) for g in roots],
                    "total_goals": len(self._goals),
                }

    def prioritize_goals(self) -> List[Goal]:
        """
        Re-prioritize goals using a weighted scoring system.

        Factors:
          - Base priority (1-10, lower = higher priority)
          - Deadline urgency (closer deadline = higher priority)
          - Progress (more progress = higher priority to finish)
          - Blocker count (more blockers = lower priority)
        """
        with self._lock:
            active = [
                g for g in self._goals.values()
                if g.status in (GoalStatus.ACTIVE, GoalStatus.PENDING, GoalStatus.BLOCKED)
            ]

        now = datetime.now()
        scored = []
        for goal in active:
            score = 0.0

            # Base priority (inverted: 1 → 10 points, 10 → 1 point)
            score += (11 - goal.priority) * 10

            # Deadline urgency
            if goal.deadline:
                try:
                    deadline_dt = datetime.fromisoformat(goal.deadline)
                    days_left = max(0, (deadline_dt - now).total_seconds() / 86400)
                    if days_left < 1:
                        score += 50
                    elif days_left < 7:
                        score += 30
                    elif days_left < 30:
                        score += 10
                except (ValueError, TypeError):
                    pass

            # Progress boost (closer to done = more important to finish)
            progress = goal.metrics.get("progress", 0.0)
            if progress > 0.7:
                score += 20
            elif progress > 0.3:
                score += 10

            # Blocker penalty
            blockers = len(goal.metrics.get("blockers", []))
            score -= blockers * 5

            scored.append((score, goal))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [goal for _, goal in scored]

    def decompose_goal(self, goal_id: str,
                       context: str = "") -> Optional[List[Goal]]:
        """
        Use LLM to decompose a complex goal into actionable subgoals.

        Returns list of created subgoals, or None if decomposition fails.
        """
        with self._lock:
            goal = self._goals.get(goal_id)
            if not goal:
                return None
            description = goal.description
            existing = [
                self._goals[sid].description
                for sid in goal.subgoals if sid in self._goals
            ]

        # Build decomposition prompt
        prompt = (
            f"Break down this goal into {DECOMPOSE_MIN_SUBGOALS}-{DECOMPOSE_MAX_SUBGOALS} "
            f"specific, actionable subgoals. Each subgoal should be concrete and measurable.\n\n"
            f"Goal: {description}\n"
        )
        if existing:
            prompt += f"\nExisting subgoals (don't duplicate):\n"
            for e in existing:
                prompt += f"- {e}\n"
        if context:
            prompt += f"\nContext: {context}\n"
        prompt += (
            "\nRespond in JSON array format: "
            '[{"description": "...", "priority": 1-10}, ...]'
        )

        try:
            from google.genai import types
            from actions.resilience import api_retry

            config_path = BASE_DIR / "config" / "api_keys.json"
            api_key = json.loads(config_path.read_text()).get("gemini_api_key", "")
            from google import genai
            client = genai.Client(api_key=api_key)

            def _call():
                cfg = types.GenerateContentConfig(
                    system_instruction="You are a goal decomposition expert. "
                    "Respond only with valid JSON.",
                    max_output_tokens=2048,
                )
                response = client.models.generate_content(
                    model=DECOMPOSE_MODEL,
                    contents=prompt,
                    config=cfg,
                )
                text = response.text.strip()
                # Extract JSON from markdown code blocks if present
                if "```" in text:
                    start = text.find("[")
                    end = text.rfind("]") + 1
                    if start >= 0 and end > start:
                        text = text[start:end]
                return text

            raw = api_retry(_call, max_retries=2, base_delay=1.0, max_delay=15.0)
            subgoal_specs = json.loads(raw)

            # Create subgoals
            created = []
            for spec in subgoal_specs[:MAX_SUBGOALS_PER_GOAL]:
                desc = spec.get("description", "").strip()
                if not desc:
                    continue
                prio = spec.get("priority", DEFAULT_PRIORITY)
                subgoal = self.add_subgoal(goal_id, desc, priority=prio)
                if subgoal:
                    created.append(subgoal)

            return created if created else None

        except Exception as e:
            # Fallback: create a simple decomposition
            fallback = [
                f"Analyze and plan: {description}",
                f"Execute core work: {description}",
                f"Verify and refine: {description}",
            ]
            created = []
            for i, desc in enumerate(fallback):
                subgoal = self.add_subgoal(goal_id, desc, priority=goal.priority)
                if subgoal:
                    created.append(subgoal)
            return created if created else None

    # ── Maintenance ────────────────────────────────────────────────────

    def _evict_abandoned(self):
        """Remove old abandoned goals to make room."""
        with self._lock:
            abandoned = [
                (gid, g) for gid, g in self._goals.items()
                if g.status == GoalStatus.ABANDONED
            ]
            # Sort by updated_at (oldest first)
            abandoned.sort(key=lambda x: x[1].updated_at)
            # Remove oldest 10%
            to_remove = max(1, len(abandoned) // 10)
            for gid, _ in abandoned[:to_remove]:
                del self._goals[gid]

    def check_stale_goals(self) -> List[str]:
        """Check for goals that have been inactive too long."""
        stale_ids = []
        now = datetime.now()
        timeout = timedelta(days=GOAL_TIMEOUT_DAYS)

        with self._lock:
            for gid, goal in self._goals.items():
                if goal.status in (GoalStatus.ACTIVE, GoalStatus.PENDING):
                    try:
                        updated = datetime.fromisoformat(goal.updated_at)
                        if now - updated > timeout:
                            stale_ids.append(gid)
                    except (ValueError, TypeError):
                        pass

        return stale_ids

    # ── Formatting ─────────────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 1000) -> str:
        """Format goal state for system prompt injection."""
        with self._lock:
            active = [
                g for g in self._goals.values()
                if g.status in (GoalStatus.ACTIVE, GoalStatus.PENDING, GoalStatus.BLOCKED)
            ]
            completed_count = sum(
                1 for g in self._goals.values()
                if g.status == GoalStatus.COMPLETED
            )

        active.sort(key=lambda g: (g.priority, g.created_at))

        parts = ["## Active Goals"]
        for goal in active[:10]:
            progress = goal.metrics.get("progress", 0.0)
            blockers = goal.metrics.get("blockers", [])
            status_emoji = {
                GoalStatus.ACTIVE: "🟢",
                GoalStatus.PENDING: "⏳",
                GoalStatus.BLOCKED: "🚫",
            }.get(goal.status, "❓")

            line = f"- {status_emoji} [{goal.priority}] {goal.description}"
            line += f" ({progress:.0%} done)"
            if blockers:
                line += f" ⚠ {len(blockers)} blocker(s)"
            parts.append(line)

        if len(active) > 10:
            parts.append(f"  ... and {len(active) - 10} more")

        parts.append(f"\nTotal: {len(self._goals)} goals, "
                     f"{completed_count} completed")

        result = "\n".join(parts)
        return result[:max_chars] if len(result) > max_chars else result

    def get_metrics(self) -> GoalMetrics:
        """Get aggregate goal metrics."""
        with self._lock:
            total = len(self._goals)
            active = sum(
                1 for g in self._goals.values()
                if g.status in (GoalStatus.ACTIVE, GoalStatus.PENDING)
            )
            completed = sum(
                1 for g in self._goals.values()
                if g.status == GoalStatus.COMPLETED
            )
            abandoned = sum(
                1 for g in self._goals.values()
                if g.status == GoalStatus.ABANDONED
            )
            blocked = sum(
                1 for g in self._goals.values()
                if g.status == GoalStatus.BLOCKED
            )

            # Average completion time
            completion_times = []
            for g in self._goals.values():
                if g.status == GoalStatus.COMPLETED and g.completed_at:
                    try:
                        created = datetime.fromisoformat(g.created_at)
                        completed_dt = datetime.fromisoformat(g.completed_at)
                        completion_times.append(
                            (completed_dt - created).total_seconds()
                        )
                    except (ValueError, TypeError):
                        pass

            avg_time = (
                sum(completion_times) / len(completion_times)
                if completion_times else 0.0
            )
            rate = completed / total if total > 0 else 0.0

            return GoalMetrics(
                total_goals=total,
                active_goals=active,
                completed_goals=completed,
                abandoned_goals=abandoned,
                blocked_goals=blocked,
                avg_completion_time_s=avg_time,
                completion_rate=rate,
            )

    def get_stats(self) -> dict:
        """Get goal engine statistics."""
        m = self.get_metrics()
        return {
            "total_goals": m.total_goals,
            "active": m.active_goals,
            "completed": m.completed_goals,
            "abandoned": m.abandoned_goals,
            "blocked": m.blocked_goals,
            "completion_rate": f"{m.completion_rate:.1%}",
            "avg_completion_hours": f"{m.avg_completion_time_s / 3600:.1f}",
        }


# ── Singleton ─────────────────────────────────────────────────────────────

_goal_engine_instance = None
_goal_engine_lock = threading.Lock()


def get_goal_engine() -> GoalEngine:
    """Get singleton GoalEngine instance."""
    global _goal_engine_instance
    if _goal_engine_instance is None:
        with _goal_engine_lock:
            if _goal_engine_instance is None:
                _goal_engine_instance = GoalEngine()
    return _goal_engine_instance
