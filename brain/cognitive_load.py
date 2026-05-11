#!/usr/bin/env python3
"""
cognitive_load.py — FRIDAY Cognitive Load Management
======================================================

Implements Sweller's Cognitive Load Theory for managing FRIDAY's working memory
and processing resources. Just as humans have limited working memory capacity,
FRIDAY has finite computational resources per request.

Three types of cognitive load (Sweller, 1988):
  1. Intrinsic Load: inherent complexity of the task itself
  2. Extraneous Load: poor presentation/organization wasting resources
  3. Germane Load: productive effort toward learning/understanding

Key idea: total load = intrinsic + extraneous + germane
If total load > capacity → performance degrades (errors, slower responses)

This module:
  - Estimates task complexity before processing
  - Tracks active cognitive modules and their resource usage
  - Detects overload conditions and triggers load-shedding
  - Optimizes resource allocation across competing demands
  - Manages working memory slots (Miller's 7±2 chunk limit)

Integration:
  - brain.metacognitive_monitor: load reports feed monitoring
  - brain.cognitive_integration: load guides routing decisions
  - brain.module_competition: load constraints affect bidding
  - brain.global_workspace: load events are broadcast
"""

import json
import math
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict, deque

BRAIN_DIR = Path(__file__).parent.resolve()
LOAD_FILE = BRAIN_DIR / "cognitive_load.json"

# Miller's Magic Number: working memory capacity
WORKING_MEMORY_SLOTS = 7
WORKING_MEMORY_VARIANCE = 2  # ±2 depending on complexity

# Load thresholds
LOAD_LOW = 0.3
LOAD_MODERATE = 0.6
LOAD_HIGH = 0.8
LOAD_CRITICAL = 0.95

# Module resource costs (relative units)
MODULE_COSTS = {
    "neural_memory": 0.05,
    "learning": 0.05,
    "self_model": 0.03,
    "active_inference": 0.10,
    "dreaming": 0.15,
    "curiosity": 0.05,
    "self_awareness": 0.08,
    "memory_coordinator": 0.05,
    "procedural_memory": 0.05,
    "episodic_memory": 0.05,
    "vector_memory": 0.05,
    "global_workspace": 0.03,
    "proactive_engine": 0.05,
    "agi_orchestrator": 0.15,
    "analogy_engine": 0.12,
    "causal_reasoner": 0.15,
    "creativity_engine": 0.12,
    "meta_learner": 0.10,
    "module_competition": 0.08,
    "neurosymbolic_reasoner": 0.15,
    "narrative_intelligence": 0.10,
    "world_model": 0.12,
    "enhanced_world_model": 0.15,
    "hierarchical_active_inference": 0.15,
    "integrated_info": 0.10,
    "transfer_learning": 0.10,
    "self_improve_engine": 0.08,
    "intuition_engine": 0.05,
    "metacognitive_monitor": 0.05,
    "emotional_regulation": 0.05,
    "cognitive_appraisal": 0.05,
    "cognitive_integration": 0.10,
}

# Task complexity keywords and their load estimates
COMPLEXITY_KEYWORDS = {
    # Low complexity (System 1)
    "what is": 0.1, "define": 0.1, "list": 0.1, "show": 0.1,
    "time": 0.05, "date": 0.05, "weather": 0.05,
    # Medium complexity
    "explain": 0.3, "compare": 0.4, "analyze": 0.5, "summarize": 0.3,
    "find": 0.3, "search": 0.3, "calculate": 0.4,
    # High complexity (System 2)
    "design": 0.7, "architect": 0.7, "plan": 0.6, "debug": 0.6,
    "optimize": 0.7, "refactor": 0.6, "implement": 0.7,
    "security": 0.6, "vulnerability": 0.6,
    # Very high complexity
    "create system": 0.8, "build entire": 0.9, "from scratch": 0.8,
    "agi": 0.8, "consciousness": 0.7, "redesign": 0.8,
}


def _timestamp() -> str:
    return datetime.now().isoformat()


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


# ─── Working Memory Chunk ──────────────────────────────────────────────

class MemoryChunk:
    """A chunk in working memory — a unit of active information."""

    def __init__(self, content: str, source: str, importance: float = 0.5):
        self.content = content
        self.source = source
        self.importance = importance
        self.created_at = time.time()
        self.last_accessed = time.time()
        self.access_count = 1

    def access(self) -> None:
        self.last_accessed = time.time()
        self.access_count += 1

    def age(self) -> float:
        return time.time() - self.created_at

    def to_dict(self) -> dict:
        return {
            "content": self.content[:100],  # Truncate for storage
            "source": self.source,
            "importance": round(self.importance, 3),
            "age_seconds": round(self.age(), 1),
            "access_count": self.access_count,
        }


# ─── Cognitive Load Manager ───────────────────────────────────────────

class CognitiveLoadManager:
    """
    Manages cognitive load and working memory for FRIDAY.

    Estimates task complexity, tracks active modules, detects overload,
    and implements load-shedding strategies.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data = self._empty_store()
        self._working_memory: List[MemoryChunk] = []
        self._active_modules: Set[str] = set()
        self._load_history: deque = deque(maxlen=100)
        self._load()

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": _timestamp(),
                "last_update": _timestamp(),
                "total_assessments": 0,
                "overload_events": 0,
            },
            "capacity_history": [],
            "load_history": [],
            "shedding_log": [],
        }

    def _load(self) -> None:
        with self._lock:
            if LOAD_FILE.exists():
                try:
                    raw = json.loads(LOAD_FILE.read_text(encoding="utf-8"))
                    self._deep_merge(self._data, raw)
                except Exception as e:
                    print(f"[CognitiveLoadManager] Load error: {e}")

    def _save(self) -> None:
        with self._lock:
            try:
                self._data["meta"]["last_update"] = _timestamp()
                LOAD_FILE.write_text(
                    json.dumps(self._data, indent=2, default=str),
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"[CognitiveLoadManager] Save error: {e}")

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                CognitiveLoadManager._deep_merge(base[k], v)
            else:
                base[k] = v

    # ── Task Complexity Estimation ───────────────────────────────────

    def estimate_task_complexity(self, task_description: str,
                                 context: Optional[dict] = None) -> dict:
        """
        Estimate the cognitive load of a task before processing.

        Returns:
            {
                "intrinsic_load": 0-1,
                "estimated_total": 0-1,
                "recommended_path": "system1" | "system2" | "system2_full",
                "recommended_modules": [...],
                "warnings": [...]
            }
        """
        with self._lock:
            ctx = context or {}
            task_lower = task_description.lower()

            # Intrinsic load: how complex is the task itself?
            intrinsic_load = 0.3  # Base
            for keyword, weight in COMPLEXITY_KEYWORDS.items():
                if keyword in task_lower:
                    intrinsic_load = max(intrinsic_load, weight)

            # Adjust for input length (longer = more to process)
            word_count = len(task_description.split())
            length_factor = min(1.0, word_count / 200)
            intrinsic_load = _clamp(intrinsic_load + length_factor * 0.1)

            # Adjust for context complexity
            if ctx.get("multi_step", False):
                intrinsic_load = min(1.0, intrinsic_load + 0.2)
            if ctx.get("requires_reasoning", False):
                intrinsic_load = min(1.0, intrinsic_load + 0.15)
            if ctx.get("code_involved", False):
                intrinsic_load = min(1.0, intrinsic_load + 0.1)

            # Estimate extraneous load (poor structure, ambiguity)
            extraneous_load = 0.0
            if "?" in task_description and task_description.count("?") > 2:
                extraneous_load += 0.1  # Multiple questions = more load
            if len(set(task_description.lower().split())) < len(task_description.split()) * 0.5:
                extraneous_load += 0.05  # Repetition

            # Germane load (productive learning effort)
            germane_load = 0.1 if ctx.get("learning_opportunity", False) else 0.0

            total = _clamp(intrinsic_load + extraneous_load + germane_load)

            # Determine recommended processing path
            if total < LOAD_LOW:
                path = "system1"
            elif total < LOAD_HIGH:
                path = "system2"
            else:
                path = "system2_full"

            # Recommend modules based on task type
            recommended = self._recommend_modules(task_description, total)

            # Warnings
            warnings = []
            if total > LOAD_CRITICAL:
                warnings.append("CRITICAL: Task complexity near capacity limit")
            if total > LOAD_HIGH:
                warnings.append("HIGH LOAD: Consider task decomposition")

            result = {
                "intrinsic_load": round(intrinsic_load, 3),
                "extraneous_load": round(extraneous_load, 3),
                "germane_load": round(germane_load, 3),
                "estimated_total": round(total, 3),
                "recommended_path": path,
                "recommended_modules": recommended,
                "warnings": warnings,
            }

            self._data["meta"]["total_assessments"] += 1
            self._load_history.append({
                "timestamp": _timestamp(),
                "task": task_description[:80],
                "total": round(total, 3),
                "path": path,
            })
            self._save()

            return result

    def _recommend_modules(self, task: str, complexity: float) -> List[str]:
        """Recommend which modules to activate based on task analysis."""
        task_lower = task.lower()
        modules = []

        # Always-on modules
        modules.extend(["neural_memory", "self_model", "global_workspace"])

        # Task-specific modules
        if any(w in task_lower for w in ["code", "program", "function", "debug", "implement"]):
            modules.extend(["code_intelligence", "code_planner", "code_simulator"])
        if any(w in task_lower for w in ["security", "vulnerability", "scan", "exploit"]):
            modules.extend(["cyber_reasoning"])
        if any(w in task_lower for w in ["why", "cause", "reason", "because"]):
            modules.append("causal_reasoner")
        if any(w in task_lower for w in ["similar", "like", "analogy", "compare"]):
            modules.append("analogy_engine")
        if any(w in task_lower for w in ["creative", "novel", "new idea", "brainstorm"]):
            modules.append("creativity_engine")
        if any(w in task_lower for w in ["learn", "improve", "adapt"]):
            modules.extend(["meta_learner", "self_improve_engine"])
        if any(w in task_lower for w in ["story", "narrative", "what happened"]):
            modules.append("narrative_intelligence")
        if complexity > LOAD_HIGH:
            modules.extend(["hierarchical_active_inference", "world_model"])

        # Deduplicate while preserving order
        seen = set()
        result = []
        for m in modules:
            if m not in seen:
                seen.add(m)
                result.append(m)
        return result

    # ── Working Memory Management ────────────────────────────────────

    def add_to_working_memory(self, content: str, source: str,
                              importance: float = 0.5) -> bool:
        """
        Add a chunk to working memory.

        Returns True if added, False if memory is full and chunk wasn't
        important enough to displace existing chunks.
        """
        with self._lock:
            chunk = MemoryChunk(content, source, importance)

            if len(self._working_memory) < WORKING_MEMORY_SLOTS:
                self._working_memory.append(chunk)
                return True

            # Find least important chunk to potentially replace
            min_idx = -1
            min_importance = importance
            for i, existing in enumerate(self._working_memory):
                # Weight by importance, recency, and access count
                score = existing.importance * (0.5 + 0.5 / (1 + existing.access_count))
                score *= max(0.1, 1.0 - existing.age() / 300)  # Decay over 5 min
                if score < min_importance:
                    min_importance = score
                    min_idx = i

            if min_idx >= 0:
                self._working_memory[min_idx] = chunk
                return True

            return False

    def get_working_memory_contents(self) -> List[dict]:
        """Get current working memory contents."""
        with self._lock:
            return [chunk.to_dict() for chunk in self._working_memory]

    def clear_working_memory(self) -> int:
        """Clear working memory, return number of chunks cleared."""
        with self._lock:
            count = len(self._working_memory)
            self._working_memory.clear()
            return count

    def get_working_memory_pressure(self) -> float:
        """How full is working memory? 0.0 (empty) to 1.0 (full)."""
        with self._lock:
            return len(self._working_memory) / WORKING_MEMORY_SLOTS

    # ── Module Tracking ─────────────────────────────────────────────

    def activate_module(self, module_name: str) -> float:
        """
        Mark a module as active and return the current total load.

        Returns the updated total cognitive load after activation.
        """
        with self._lock:
            self._active_modules.add(module_name)
            return self._compute_current_load()

    def deactivate_module(self, module_name: str) -> float:
        """Mark a module as inactive."""
        with self._lock:
            self._active_modules.discard(module_name)
            return self._compute_current_load()

    def _compute_current_load(self) -> float:
        """Compute total load from currently active modules."""
        total = sum(MODULE_COSTS.get(m, 0.05) for m in self._active_modules)
        return _clamp(total)

    def get_active_load(self) -> dict:
        """Get current load breakdown."""
        with self._lock:
            module_loads = {
                m: MODULE_COSTS.get(m, 0.05)
                for m in self._active_modules
            }
            total = sum(module_loads.values())
            return {
                "active_modules": sorted(self._active_modules),
                "module_loads": module_loads,
                "total_load": round(_clamp(total), 3),
                "working_memory_used": len(self._working_memory),
                "working_memory_capacity": WORKING_MEMORY_SLOTS,
                "working_memory_pressure": round(self.get_working_memory_pressure(), 3),
                "load_level": self._classify_load(total),
            }

    def _classify_load(self, load: float) -> str:
        if load < LOAD_LOW:
            return "low"
        elif load < LOAD_MODERATE:
            return "moderate"
        elif load < LOAD_HIGH:
            return "high"
        elif load < LOAD_CRITICAL:
            return "very_high"
        return "critical"

    # ── Load Shedding ────────────────────────────────────────────────

    def check_overload(self) -> dict:
        """
        Check if the system is overloaded and suggest load-shedding.

        Returns:
            {
                "overloaded": bool,
                "load_level": str,
                "shedding_suggestions": [...]
            }
        """
        with self._lock:
            load = self._compute_current_load()
            wm_pressure = self.get_working_memory_pressure()
            total_pressure = (load + wm_pressure) / 2

            overloaded = total_pressure > LOAD_HIGH
            suggestions = []

            if overloaded:
                self._data["meta"]["overload_events"] += 1

                # Suggest deactivating lowest-priority modules
                module_costs = [
                    (m, MODULE_COSTS.get(m, 0.05))
                    for m in self._active_modules
                ]
                module_costs.sort(key=lambda x: x[1], reverse=True)

                # Keep the top N modules, suggest dropping the rest
                keep_count = max(3, int(WORKING_MEMORY_SLOTS * 0.6))
                for m, cost in module_costs[keep_count:]:
                    suggestions.append(f"Deactivate {m} (saves {cost:.2f} load units)")

                if wm_pressure > 0.8:
                    suggestions.append("Clear low-importance working memory chunks")
                    suggestions.append("Consolidate working memory into episodic memory")

                self._data["shedding_log"].append({
                    "timestamp": _timestamp(),
                    "load": round(load, 3),
                    "wm_pressure": round(wm_pressure, 3),
                    "suggestions_count": len(suggestions),
                })
                self._save()

            return {
                "overloaded": overloaded,
                "load_level": self._classify_load(total_pressure),
                "total_pressure": round(total_pressure, 3),
                "shedding_suggestions": suggestions,
            }

    def get_status(self) -> dict:
        """Get comprehensive load management status."""
        with self._lock:
            return {
                "total_assessments": self._data["meta"]["total_assessments"],
                "overload_events": self._data["meta"]["overload_events"],
                "active_modules": len(self._active_modules),
                "working_memory_used": len(self._working_memory),
                "current_load": round(self._compute_current_load(), 3),
                "recent_loads": [
                    {"task": e["task"][:40], "total": e["total"], "path": e["path"]}
                    for e in list(self._load_history)[-5:]
                ],
            }

    def get_stats(self) -> dict:
        """Get overall cognitive load statistics."""
        with self._lock:
            return {
                "active_modules": len(self._active_modules),
                "working_memory_used": len(self._working_memory),
                "working_memory_capacity": self._max_chunks,
                "current_load": round(self._compute_current_load(), 3),
                "load_history_size": len(self._load_history),
                "fatigue_score": getattr(self, '_fatigue_score', 0.0),
            }


# ─── Singleton ─────────────────────────────────────────────────────────

_load_instance = None
_load_lock = threading.Lock()


def get_cognitive_load_manager() -> CognitiveLoadManager:
    """Get the singleton CognitiveLoadManager instance."""
    global _load_instance
    if _load_instance is None:
        with _load_lock:
            if _load_instance is None:
                _load_instance = CognitiveLoadManager()
    return _load_instance
