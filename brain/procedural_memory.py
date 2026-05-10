#!/usr/bin/env python3
"""
procedural_memory.py — FRIDAY Procedural Memory System
=======================================================
Stores successful multi-step tool executions as reusable procedures.
When a similar task comes up, retrieves and suggests the best procedure.

This is "muscle memory" for an AI — once you learn to ride a bike,
you don't re-learn it. Procedures are learned from successful
tool chains and adapted to new contexts.
"""

import json
import threading
import time
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict


BRAIN_DIR = Path(__file__).parent.resolve()
PROCEDURES_FILE = BRAIN_DIR / "procedural_store.json"

# Configuration
MAX_PROCEDURES = 100
MIN_SUCCESS_RATE = 0.5  # Prune procedures below 50% success
DECAY_DAYS = 90  # Procedures unused for 90 days get pruned


class Procedure:
    """A learned tool chain template."""

    def __init__(self, proc_id: str, goal_pattern: str, steps: List[dict],
                 context: Optional[dict] = None):
        self.proc_id = proc_id
        self.goal_pattern = goal_pattern  # Keywords/pattern that triggers this procedure
        self.steps = steps  # [{"tool": str, "params_pattern": dict, "description": str}]
        self.context = context or {}
        self.created = datetime.now().isoformat()
        self.last_used = self.created
        self.success_count = 0
        self.failure_count = 0
        self.total_count = 0

    def to_dict(self) -> dict:
        return {
            "proc_id": self.proc_id,
            "goal_pattern": self.goal_pattern,
            "steps": self.steps,
            "context": self.context,
            "created": self.created,
            "last_used": self.last_used,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_count": self.total_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Procedure":
        proc = cls(
            proc_id=data["proc_id"],
            goal_pattern=data["goal_pattern"],
            steps=data["steps"],
            context=data.get("context"),
        )
        proc.created = data.get("created", proc.created)
        proc.last_used = data.get("last_used", proc.last_used)
        proc.success_count = data.get("success_count", 0)
        proc.failure_count = data.get("failure_count", 0)
        proc.total_count = data.get("total_count", 0)
        return proc

    @property
    def success_rate(self) -> float:
        if self.total_count == 0:
            return 0.0
        return self.success_count / self.total_count

    def record_use(self, success: bool):
        self.total_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        self.last_used = datetime.now().isoformat()


class ProceduralMemory:
    """
    Stores and retrieves learned procedures (successful tool chains).

    Learning: After a successful multi-step task, extract the procedure.
    Retrieval: When a new task arrives, find the most relevant procedure.
    Adaptation: Procedures evolve based on success/failure feedback.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._procedures: Dict[str, Procedure] = {}
        self._load()

    def _load(self):
        if not PROCEDURES_FILE.exists():
            return
        try:
            data = json.loads(PROCEDURES_FILE.read_text(encoding="utf-8"))
            for p in data.get("procedures", []):
                proc = Procedure.from_dict(p)
                self._procedures[proc.proc_id] = proc
            print(f"[Procedural] Loaded {len(self._procedures)} procedures")
        except Exception as e:
            print(f"[Procedural] Load error: {e}")

    def _save(self):
        try:
            BRAIN_DIR.mkdir(parents=True, exist_ok=True)
            PROCEDURES_FILE.write_text(json.dumps({
                "procedures": [p.to_dict() for p in self._procedures.values()],
                "updated": datetime.now().isoformat(),
            }, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[Procedural] Save error: {e}")

    def learn_procedure(self, goal: str, steps: List[dict],
                        context: Optional[dict] = None) -> str:
        """
        Learn a new procedure from a successful task execution.

        Args:
            goal: The original goal description
            steps: List of {"tool": str, "description": str, "params_pattern": dict}
            context: Optional context (user preferences, time of day, etc.)

        Returns:
            procedure_id
        """
        # Extract keywords from goal for matching
        keywords = self._extract_keywords(goal)
        if not keywords:
            return ""

        proc_id = f"proc_{uuid.uuid4().hex[:8]}"
        proc = Procedure(
            proc_id=proc_id,
            goal_pattern=keywords,
            steps=steps,
            context=context,
        )
        proc.record_use(True)  # It was successful, that's why we're learning it

        with self._lock:
            self._procedures[proc_id] = proc
            self._prune_if_needed()
            self._save()

        print(f"[Procedural] Learned: {proc_id} ({len(steps)} steps, pattern: {keywords})")
        return proc_id

    def find_procedure(self, goal: str, top_k: int = 3) -> List[dict]:
        """
        Find the most relevant procedure for a given goal.

        Returns list of matching procedures sorted by relevance and success rate.
        """
        keywords = self._extract_keywords(goal)
        if not keywords:
            return []

        with self._lock:
            scored = []
            for proc in self._procedures.values():
                score = self._match_score(keywords, proc.goal_pattern)
                if score > 0:
                    # Combine match score with success rate
                    combined = score * 0.6 + proc.success_rate * 0.3
                    # Bonus for recently used
                    try:
                        last = datetime.fromisoformat(proc.last_used)
                        days_since = (datetime.now() - last).days
                        recency_bonus = max(0, 0.1 - days_since * 0.001)
                        combined += recency_bonus
                    except Exception:
                        pass

                    scored.append({
                        "proc_id": proc.proc_id,
                        "goal_pattern": proc.goal_pattern,
                        "steps": proc.steps,
                        "success_rate": proc.success_rate,
                        "total_uses": proc.total_count,
                        "score": round(combined, 3),
                        "last_used": proc.last_used,
                    })

            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:top_k]

    def record_outcome(self, proc_id: str, success: bool):
        """Record whether a procedure worked when used."""
        with self._lock:
            proc = self._procedures.get(proc_id)
            if proc:
                proc.record_use(success)
                self._save()

    def _extract_keywords(self, text: str) -> str:
        """Extract meaningful keywords from a goal description."""
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "above",
            "below", "between", "and", "but", "or", "nor", "not", "so",
            "yet", "both", "either", "neither", "each", "every", "all",
            "any", "few", "more", "most", "other", "some", "such", "no",
            "only", "own", "same", "than", "too", "very", "just", "i",
            "me", "my", "we", "our", "you", "your", "he", "she", "it",
            "they", "them", "this", "that", "these", "those", "please",
            "help", "want", "need", "make", "get", "set",
        }
        words = text.lower().split()
        keywords = [w for w in words if len(w) > 2 and w not in stop_words]
        return " ".join(keywords[:10])

    def _match_score(self, query_kw: str, proc_kw: str) -> float:
        """Compute keyword overlap score between query and procedure."""
        q_words = set(query_kw.split())
        p_words = set(proc_kw.split())
        if not q_words or not p_words:
            return 0
        overlap = q_words & p_words
        return len(overlap) / max(len(q_words), len(p_words))

    def _prune_if_needed(self):
        """Remove low-performing or old procedures."""
        if len(self._procedures) <= MAX_PROCEDURES:
            return

        now = datetime.now()
        to_remove = []

        for proc_id, proc in self._procedures.items():
            # Remove low success rate
            if proc.total_count >= 3 and proc.success_rate < MIN_SUCCESS_RATE:
                to_remove.append(proc_id)
                continue

            # Remove old unused procedures
            try:
                last = datetime.fromisoformat(proc.last_used)
                if (now - last).days > DECAY_DAYS:
                    to_remove.append(proc_id)
            except Exception:
                pass

        for proc_id in to_remove[:len(self._procedures) - MAX_PROCEDURES]:
            del self._procedures[proc_id]

    def get_stats(self) -> dict:
        with self._lock:
            total = len(self._procedures)
            if total == 0:
                return {"total_procedures": 0}
            avg_success = sum(p.success_rate for p in self._procedures.values()) / total
            total_uses = sum(p.total_count for p in self._procedures.values())
            return {
                "total_procedures": total,
                "avg_success_rate": round(avg_success, 2),
                "total_uses": total_uses,
            }

    def format_for_prompt(self, max_chars: int = 500) -> str:
        """Format top procedures for system prompt injection."""
        with self._lock:
            if not self._procedures:
                return ""

            # Get top procedures by success rate and usage
            top = sorted(
                self._procedures.values(),
                key=lambda p: p.success_rate * p.total_count,
                reverse=True,
            )[:5]

            parts = ["[PROCEDURAL MEMORY — Learned skill templates]"]
            for proc in top:
                steps_str = " → ".join(
                    s.get("tool", "?") for s in proc.steps[:4]
                )
                parts.append(
                    f"  [{proc.success_rate:.0%} success, {proc.total_count}x] "
                    f"{proc.goal_pattern}: {steps_str}"
                )

            result = "\n".join(parts)
            if len(result) > max_chars:
                result = result[:max_chars] + "[...]"
            return result


# ── Singleton ─────────────────────────────────────────────────────────

_procedural_memory = None
_procedural_lock = threading.Lock()


def get_procedural_memory() -> ProceduralMemory:
    global _procedural_memory
    if _procedural_memory is None:
        with _procedural_lock:
            if _procedural_memory is None:
                _procedural_memory = ProceduralMemory()
    return _procedural_memory
