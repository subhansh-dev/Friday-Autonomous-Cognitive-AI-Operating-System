"""
dead_end_tracker.py — Negative result memory for FRIDAY cyber assessments.

JSONL-based log of tested-and-failed approaches. Used by hunter agents to
skip dead leads and avoid re-testing known-failed attack vectors.
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("friday.cyber.dead_ends")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "dead_ends"
DEFAULT_DEAD_ENDS_FILE = DATA_DIR / "dead_ends.jsonl"
DEFAULT_PRUNE_DAYS = 30


class DeadEndTracker:
    """Tracks negative results — tested-and-failed attack approaches."""

    def __init__(self, path: Optional[Path] = None, prune_days: int = DEFAULT_PRUNE_DAYS):
        self.path = Path(path) if path is not None else DEFAULT_DEAD_ENDS_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self.prune_days = prune_days

    def log(self, target: str, attack_vector: str, surface_id: str,
            reason: str, session_id: str = "", agent: str = "",
            metadata: Optional[dict] = None) -> dict:
        """Log a dead-end (tested-and-failed) approach."""
        entry = {
            "target": target,
            "attack_vector": attack_vector,
            "surface_id": surface_id,
            "reason": reason,
            "session_id": session_id,
            "agent": agent,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }

        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        logger.info("Dead end: %s / %s / %s — %s",
                     target, attack_vector, surface_id, reason[:80])
        return entry

    def is_dead_end(self, target: str, attack_vector: str,
                    surface_id: str) -> bool:
        """Check if this exact target+vector+surface has been tested and failed."""
        for entry in self._read_all():
            if (entry.get("target") == target and
                entry.get("attack_vector") == attack_vector and
                entry.get("surface_id") == surface_id):
                return True
        return False

    def is_vector_dead(self, target: str, attack_vector: str) -> bool:
        """Check if this target+vector has any dead-end (regardless of surface)."""
        for entry in self._read_all():
            if (entry.get("target") == target and
                entry.get("attack_vector") == attack_vector):
                return True
        return False

    def query(self, target: Optional[str] = None,
              attack_vector: Optional[str] = None,
              surface_id: Optional[str] = None,
              session_id: Optional[str] = None,
              since_hours: Optional[int] = None) -> list[dict]:
        """Query dead ends with flexible filters."""
        results = []
        cutoff = None
        if since_hours is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)

        for entry in self._read_all():
            if target and entry.get("target") != target:
                continue
            if attack_vector and entry.get("attack_vector") != attack_vector:
                continue
            if surface_id and entry.get("surface_id") != surface_id:
                continue
            if session_id and entry.get("session_id") != session_id:
                continue
            if cutoff:
                try:
                    ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                    if ts < cutoff:
                        continue
                except (KeyError, ValueError):
                    continue
            results.append(entry)

        return results

    def get_all_targets(self) -> list[str]:
        """Get all unique targets that have dead ends."""
        targets = set()
        for entry in self._read_all():
            t = entry.get("target")
            if t:
                targets.add(t)
        return sorted(targets)

    def get_vectors_for_target(self, target: str) -> list[str]:
        """Get all attack vectors that are dead for a target."""
        vectors = set()
        for entry in self._read_all():
            if entry.get("target") == target:
                v = entry.get("attack_vector")
                if v:
                    vectors.add(v)
        return sorted(vectors)

    def prune(self, days: Optional[int] = None) -> int:
        """Remove entries older than N days."""
        days = days or self.prune_days
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        kept = []
        removed = 0

        for entry in self._read_all():
            try:
                ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                if ts >= cutoff:
                    kept.append(json.dumps(entry, ensure_ascii=False))
                else:
                    removed += 1
            except (KeyError, ValueError):
                kept.append(json.dumps(entry, ensure_ascii=False))

        with open(self.path, "w", encoding="utf-8") as f:
            for line in kept:
                f.write(line + "\n")

        if removed > 0:
            logger.info("Pruned %d dead-end entries older than %d days", removed, days)
        return removed

    def count(self) -> int:
        """Count total dead-end entries."""
        count = 0
        for _ in self._read_all():
            count += 1
        return count

    def get_stats(self) -> dict:
        """Get statistics about dead ends."""
        entries = self._read_all()
        targets = set()
        vectors = set()
        surfaces = set()
        sessions = set()
        count = 0

        for entry in entries:
            count += 1
            if entry.get("target"):
                targets.add(entry["target"])
            if entry.get("attack_vector"):
                vectors.add(entry["attack_vector"])
            if entry.get("surface_id"):
                surfaces.add(entry["surface_id"])
            if entry.get("session_id"):
                sessions.add(entry["session_id"])

        return {
            "total_entries": count,
            "unique_targets": len(targets),
            "unique_vectors": len(vectors),
            "unique_surfaces": len(surfaces),
            "unique_sessions": len(sessions),
            "file_path": str(self.path),
            "prune_days": self.prune_days,
        }

    def _read_all(self) -> list[dict]:
        """Read all dead-end entries from the JSONL file."""
        entries = []
        if not self.path.exists():
            return entries
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries


# ── Convenience singleton ─────────────────────────────────────────

_tracker: Optional[DeadEndTracker] = None


def get_dead_end_tracker(path: Optional[Path] = None,
                         prune_days: int = DEFAULT_PRUNE_DAYS) -> DeadEndTracker:
    """Get or create the global DeadEndTracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = DeadEndTracker(path, prune_days)
    return _tracker
