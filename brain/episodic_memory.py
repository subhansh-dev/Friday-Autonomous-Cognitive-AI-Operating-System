#!/usr/bin/env python3
"""
episodic_memory.py — FRIDAY Episodic Memory System
====================================================

Timestamped event memory that tracks what happened, when, and in what context.
Inspired by human episodic memory:
- Events are encoded with temporal context (when did this happen?)
- Memories decay over time (recent events are stronger)
- Related events cluster into episodes (conversation threads)
- Retrieval by time range, type, content, or semantic similarity

Unlike neural_memory (which stores facts), episodic memory stores EXPERIENCES:
- Conversation turns
- Tool executions
- User interactions
- System events
- Errors and surprises
"""

import json
import threading
import time
import math
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from collections import defaultdict


BRAIN_DIR = Path(__file__).parent.resolve()
EPISODES_FILE = BRAIN_DIR / "episodic_store.json"

# Configuration
MAX_EVENTS = 2000
STRENGTH_HALF_LIFE_HOURS = 48  # Episodic memories decay slower than neural
EPISODE_WINDOW_SECONDS = 300   # Events within 5 min are same episode
MAX_EPISODES = 200


class EpisodicMemory:
    """
    Episodic memory system for FRIDAY.

    Stores timestamped events with:
    - Temporal context (when, duration, episode)
    - Strength decay (recent events are stronger)
    - Episode clustering (related events grouped)
    - Multi-dimensional search (by time, type, content)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._data = self._empty_store()
        self._load()

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": datetime.now().isoformat(),
                "total_events": 0,
                "total_episodes": 0,
            },
            "events": [],
            "episodes": [],
        }

    # ── Persistence ─────────────────────────────────────────────────────

    def _load(self):
        if not EPISODES_FILE.exists():
            self._save()
            return
        try:
            raw = EPISODES_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            for key in ("events", "episodes", "meta"):
                if key not in data:
                    data[key] = self._empty_store()[key]
            self._data = data
            print(f"[Episodic] Loaded {len(self._data['events'])} events, "
                  f"{len(self._data['episodes'])} episodes")
        except (json.JSONDecodeError, IOError) as e:
            print(f"[Episodic] Load error: {e}. Starting fresh.")
            self._data = self._empty_store()
            self._save()

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        try:
            tmp_path = EPISODES_FILE.with_suffix(".json.tmp")
            tmp_path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_path.replace(EPISODES_FILE)
        except Exception as e:
            print(f"[Episodic] Save error: {e}")

    # ── Event Encoding ──────────────────────────────────────────────────

    def encode_event(
        self,
        event_type: str,
        content: str,
        context: Optional[dict] = None,
        importance: float = 5.0,
    ) -> str:
        """
        Encode a new episodic event.

        Args:
            event_type: Category (conversation, tool_call, system, error, etc.)
            content: What happened (text description)
            context: Additional context (tool name, user input, etc.)
            importance: 1-10, how important this event is (affects initial strength)

        Returns:
            event_id
        """
        event_id = f"ep_{uuid.uuid4().hex[:12]}"
        now = datetime.now()
        now_iso = now.isoformat()

        event = {
            "event_id": event_id,
            "type": event_type,
            "content": content[:500],
            "context": context or {},
            "timestamp": now_iso,
            "importance": max(1.0, min(10.0, importance)),
            "strength": max(1.0, min(10.0, importance)),
            "episode_id": None,
            "access_count": 0,
            "last_accessed": now_iso,
        }

        with self._lock:
            # Find or create episode
            episode_id = self._find_or_create_episode(now, event_type)
            event["episode_id"] = episode_id

            self._data["events"].append(event)
            self._data["meta"]["total_events"] += 1

            # Trim old events
            if len(self._data["events"]) > MAX_EVENTS:
                self._prune_weakest_events()

        return event_id

    def _find_or_create_episode(self, timestamp: datetime,
                                 event_type: str) -> str:
        """Find an existing episode to attach to, or create a new one."""
        events = self._data["events"]
        episodes = self._data["episodes"]

        # Check if the most recent event is within the episode window
        if events:
            last_event = events[-1]
            try:
                last_ts = datetime.fromisoformat(last_event["timestamp"])
                gap = (timestamp - last_ts).total_seconds()
                if gap < EPISODE_WINDOW_SECONDS:
                    return last_event.get("episode_id", "")
            except (ValueError, TypeError):
                pass

        # Create new episode
        episode_id = f"epi_{uuid.uuid4().hex[:8]}"
        episode = {
            "episode_id": episode_id,
            "start_time": timestamp.isoformat(),
            "end_time": timestamp.isoformat(),
            "event_count": 1,
            "types": [event_type],
            "summary": "",
        }
        episodes.append(episode)
        self._data["meta"]["total_episodes"] += 1

        # Trim old episodes
        if len(episodes) > MAX_EPISODES:
            episodes.sort(key=lambda e: e.get("start_time", ""), reverse=True)
            self._data["episodes"] = episodes[:MAX_EPISODES]

        return episode_id

    def _prune_weakest_events(self):
        """Remove weakest events to stay within MAX_EVENTS."""
        now = datetime.now()
        for event in self._data["events"]:
            event["strength"] = self._compute_strength(event, now)

        self._data["events"].sort(key=lambda e: e.get("strength", 0))
        self._data["events"] = self._data["events"][MAX_EVENTS // 4:]

    # ── Strength Computation ────────────────────────────────────────────

    def _compute_strength(self, event: dict, now: Optional[datetime] = None) -> float:
        """Compute current strength based on time decay and access."""
        if now is None:
            now = datetime.now()

        try:
            created = datetime.fromisoformat(event["timestamp"])
            hours_since = (now - created).total_seconds() / 3600
        except (ValueError, TypeError):
            return 0.0

        importance = event.get("importance", 5.0)
        access_count = event.get("access_count", 0)

        # Time decay
        decay = math.exp(-hours_since / STRENGTH_HALF_LIFE_HOURS)

        # Access potentiation
        potentiation = 1.0 + math.log2(max(1, access_count) + 1) * 0.2

        raw = importance * decay * potentiation
        return max(0.0, min(10.0, round(raw, 4)))

    # ── Retrieval ───────────────────────────────────────────────────────

    def recall_event(self, event_id: str) -> Optional[dict]:
        """Recall a specific event by ID. Updates access count (LTP)."""
        with self._lock:
            for event in self._data["events"]:
                if event["event_id"] == event_id:
                    event["access_count"] = event.get("access_count", 0) + 1
                    event["last_accessed"] = datetime.now().isoformat()
                    event["strength"] = self._compute_strength(event)
                    return dict(event)
        return None

    def get_recent_events(self, limit: int = 20,
                          event_type: Optional[str] = None) -> List[dict]:
        """Get the most recent events, optionally filtered by type."""
        with self._lock:
            events = self._data["events"]
            if event_type:
                events = [e for e in events if e.get("type") == event_type]

            # Sort by timestamp descending
            events = sorted(events,
                          key=lambda e: e.get("timestamp", ""),
                          reverse=True)
            return events[:limit]

    def get_episode(self, episode_id: str) -> List[dict]:
        """Get all events in an episode."""
        with self._lock:
            return [dict(e) for e in self._data["events"]
                    if e.get("episode_id") == episode_id]

    def get_recent_episodes(self, limit: int = 5) -> List[dict]:
        """Get recent episodes with their event counts."""
        with self._lock:
            episodes = sorted(
                self._data["episodes"],
                key=lambda e: e.get("start_time", ""),
                reverse=True,
            )
            return episodes[:limit]

    def search_events(self, query: str, top_k: int = 10) -> List[dict]:
        """Search events by content keyword matching."""
        q = query.lower()
        results = []
        now = datetime.now()

        with self._lock:
            for event in self._data["events"]:
                content = event.get("content", "").lower()
                event_type = event.get("type", "").lower()
                context_str = " ".join(str(v) for v in event.get("context", {}).values()).lower()

                score = 0
                if q in content:
                    score = 3
                elif q in event_type:
                    score = 2
                elif q in context_str:
                    score = 1

                # Also check individual words
                if score == 0:
                    for word in q.split():
                        if len(word) > 3 and word in content:
                            score = max(score, 0.5)

                if score > 0:
                    strength = self._compute_strength(event, now)
                    results.append({
                        **event,
                        "_match_score": score,
                        "_strength": strength,
                    })

        results.sort(key=lambda r: (r["_match_score"], r["_strength"]),
                    reverse=True)

        # Clean up internal fields
        for r in results:
            r.pop("_match_score", None)
            r.pop("_strength", None)

        return results[:top_k]

    def get_events_by_time_range(self, start: datetime,
                                  end: datetime) -> List[dict]:
        """Get events within a time range."""
        start_iso = start.isoformat()
        end_iso = end.isoformat()

        with self._lock:
            return [
                dict(e) for e in self._data["events"]
                if start_iso <= e.get("timestamp", "") <= end_iso
            ]

    # ── Consolidation ───────────────────────────────────────────────────

    def consolidate(self):
        """Consolidate: update episode summaries, prune weak events."""
        with self._lock:
            now = datetime.now()

            # Update episode end times and summaries
            for episode in self._data["episodes"]:
                episode_events = [
                    e for e in self._data["events"]
                    if e.get("episode_id") == episode["episode_id"]
                ]
                if episode_events:
                    episode["event_count"] = len(episode_events)
                    episode["end_time"] = episode_events[-1].get("timestamp", "")
                    types = set(e.get("type", "") for e in episode_events)
                    episode["types"] = list(types)

                    # Generate summary from event contents
                    contents = [e.get("content", "")[:50] for e in episode_events[:5]]
                    episode["summary"] = "; ".join(contents)[:200]

            # Remove episodes with no events
            active_episodes = set(e.get("episode_id") for e in self._data["events"])
            self._data["episodes"] = [
                ep for ep in self._data["episodes"]
                if ep["episode_id"] in active_episodes
            ]

            # Prune expired events (strength too low)
            surviving = []
            for event in self._data["events"]:
                event["strength"] = self._compute_strength(event, now)
                if event["strength"] > 0.1:
                    surviving.append(event)

            pruned = len(self._data["events"]) - len(surviving)
            self._data["events"] = surviving

            self._save()

        if pruned > 0:
            print(f"[Episodic] Consolidation: pruned {pruned} weak events")

    # ── Stats ───────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get episodic memory statistics."""
        with self._lock:
            now = datetime.now()
            strengths = [self._compute_strength(e, now) for e in self._data["events"]]
            avg_strength = sum(strengths) / len(strengths) if strengths else 0

            type_dist = defaultdict(int)
            for e in self._data["events"]:
                type_dist[e.get("type", "unknown")] += 1

            return {
                "total_events": len(self._data["events"]),
                "total_episodes": len(self._data["episodes"]),
                "avg_strength": round(avg_strength, 2),
                "type_distribution": dict(type_dist),
                "total_created": self._data["meta"]["total_events"],
            }

    def format_for_prompt(self, max_chars: int = 500) -> str:
        """Format recent episodic memory for system prompt."""
        recent = self.get_recent_events(limit=5)
        if not recent:
            return ""

        parts = ["[EPISODIC MEMORY — Recent events]"]
        for event in recent:
            ts = event.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(ts)
                time_str = dt.strftime("%H:%M")
            except (ValueError, TypeError):
                time_str = "??:??"
            content = event.get("content", "")[:80]
            parts.append(f"  [{time_str}] {event.get('type', '?')}: {content}")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "[...]"
        return result

    def stop(self):
        """Save and stop."""
        self._save()


# ── Singleton ───────────────────────────────────────────────────────────

_episodic_memory = None
_episodic_lock = threading.Lock()


def get_episodic_memory() -> EpisodicMemory:
    """Get the singleton episodic memory instance."""
    global _episodic_memory
    if _episodic_memory is None:
        with _episodic_lock:
            if _episodic_memory is None:
                _episodic_memory = EpisodicMemory()
    return _episodic_memory
