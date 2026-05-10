# -*- coding: utf-8 -*-
"""
working_memory.py — FRIDAY Working Memory Buffer
=================================================
Structured scratchpad for active task context. Short-term, task-scoped,
auto-cleared between tasks. Inspired by Baddeley's Working Memory model.

Slots follow Miller's Law: 7 +/- 2 items max. Each slot has a priority
score and auto-expires after a configurable TTL.
"""

import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


BRAIN_DIR = Path(__file__).parent.parent / "brain"
STORE_FILE = BRAIN_DIR / "working_memory.json"

MAX_SLOTS = 8
SLOT_TTL_SECONDS = 1800  # 30 minutes


class WorkingMemorySlot:
    """A single item in working memory."""

    def __init__(self, key: str, value: Any, priority: float = 0.5,
                 source: str = "user"):
        self.id = str(uuid.uuid4())[:8]
        self.key = key
        self.value = value
        self.priority = min(1.0, max(0.0, priority))
        self.source = source  # "user", "tool", "inference"
        self.created_at = time.time()
        self.last_accessed = time.time()
        self.access_count = 0

    def access(self) -> Any:
        """Access the slot value, boosting its recency."""
        self.last_accessed = time.time()
        self.access_count += 1
        return self.value

    def is_expired(self, ttl: float = SLOT_TTL_SECONDS) -> bool:
        return (time.time() - self.last_accessed) > ttl

    def effective_priority(self) -> float:
        """Priority decays with age but boosts with access frequency."""
        age_factor = max(0.1, 1.0 - (time.time() - self.last_accessed) / SLOT_TTL_SECONDS)
        access_boost = min(0.3, self.access_count * 0.05)
        return min(1.0, self.priority * age_factor + access_boost)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "priority": self.priority,
            "source": self.source,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorkingMemorySlot":
        slot = cls(d["key"], d["value"], d.get("priority", 0.5), d.get("source", "user"))
        slot.id = d.get("id", slot.id)
        slot.created_at = d.get("created_at", time.time())
        slot.last_accessed = d.get("last_accessed", time.time())
        slot.access_count = d.get("access_count", 0)
        return slot


class WorkingMemory:
    """
    Working memory buffer with priority-based eviction.

    - Max 8 slots (Miller's Law)
    - Low-priority slots evicted first when full
    - Expired slots auto-cleaned on access
    - Persisted to disk for crash recovery
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._slots: dict[str, WorkingMemorySlot] = {}
        self._task_id: Optional[str] = None
        self._goal: Optional[str] = None
        self._load()

    # ── Persistence ─────────────────────────────────────────────────

    def _load(self):
        if not STORE_FILE.exists():
            return
        try:
            data = json.loads(STORE_FILE.read_text(encoding="utf-8"))
            self._task_id = data.get("task_id")
            self._goal = data.get("goal")
            for sd in data.get("slots", []):
                slot = WorkingMemorySlot.from_dict(sd)
                if not slot.is_expired():
                    self._slots[slot.key] = slot
        except (json.JSONDecodeError, IOError):
            pass

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "task_id": self._task_id,
            "goal": self._goal,
            "slots": [s.to_dict() for s in self._slots.values()],
            "updated_at": datetime.now().isoformat(),
        }
        STORE_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Task management ─────────────────────────────────────────────

    def set_task(self, task_id: str, goal: str):
        """Start a new task, clearing previous context."""
        with self._lock:
            self._task_id = task_id
            self._goal = goal
            self._save()

    def clear_task(self):
        """Clear all task context."""
        with self._lock:
            self._task_id = None
            self._goal = None
            self._slots.clear()
            self._save()

    # ── Slot operations ─────────────────────────────────────────────

    def _evict_if_needed(self):
        """Evict lowest effective-priority slot if at capacity."""
        if len(self._slots) < MAX_SLOTS:
            return
        # Find lowest priority slot
        worst_key = min(
            self._slots,
            key=lambda k: self._slots[k].effective_priority(),
        )
        del self._slots[worst_key]

    def _clean_expired(self):
        """Remove expired slots."""
        expired = [k for k, s in self._slots.items() if s.is_expired()]
        for k in expired:
            del self._slots[k]

    def store(self, key: str, value: Any, priority: float = 0.5,
              source: str = "user"):
        """Store a value in working memory."""
        with self._lock:
            self._clean_expired()
            self._evict_if_needed()
            self._slots[key] = WorkingMemorySlot(key, value, priority, source)
            self._save()

    def recall(self, key: str) -> Optional[Any]:
        """Recall a value from working memory. Returns None if not found."""
        with self._lock:
            self._clean_expired()
            slot = self._slots.get(key)
            if slot:
                return slot.access()
            return None

    def has(self, key: str) -> bool:
        with self._lock:
            self._clean_expired()
            return key in self._slots

    def remove(self, key: str) -> bool:
        with self._lock:
            if key in self._slots:
                del self._slots[key]
                self._save()
                return True
            return False

    # ── Query ───────────────────────────────────────────────────────

    def get_all(self) -> dict[str, Any]:
        """Get all active slots as a dict."""
        with self._lock:
            self._clean_expired()
            return {k: s.value for k, s in self._slots.items()}

    def get_status(self) -> dict:
        """Get working memory status."""
        with self._lock:
            self._clean_expired()
            return {
                "task_id": self._task_id,
                "goal": self._goal,
                "slots_used": len(self._slots),
                "slots_max": MAX_SLOTS,
                "slots": [
                    {"key": s.key, "priority": round(s.effective_priority(), 2),
                     "source": s.source, "access_count": s.access_count}
                    for s in sorted(self._slots.values(),
                                    key=lambda s: s.effective_priority(),
                                    reverse=True)
                ],
            }

    def format_for_prompt(self, max_chars: int = 400) -> str:
        """Format working memory state for system prompt injection."""
        status = self.get_status()
        if not status["slots_used"]:
            return ""

        parts = ["[WORKING MEMORY]"]
        if status["goal"]:
            parts.append(f"Goal: {status['goal']}")
        parts.append(f"Active context ({status['slots_used']}/{MAX_SLOTS} slots):")

        for s in status["slots"]:
            val_str = str(s["key"])
            parts.append(f"  - {val_str} (p={s['priority']}, src={s['source']})")

        result = "\n".join(parts)
        return result[:max_chars] if len(result) > max_chars else result


# ── Singleton ───────────────────────────────────────────────────────────────

_wm = None
_wm_lock = threading.Lock()


def get_working_memory() -> WorkingMemory:
    global _wm
    if _wm is None:
        with _wm_lock:
            if _wm is None:
                _wm = WorkingMemory()
    return _wm
