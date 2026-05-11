#!/usr/bin/env python3
"""
memory_consolidation.py — FRIDAY Memory Consolidation (Sleep-Like Processing)
=============================================================================

Implements sleep-like memory consolidation that compresses episodic memories
into semantic knowledge, inspired by the complementary learning systems theory
(McClelland et al., 1995) and hippocampal replay during sleep.

Key behaviors:
  - Consolidate episodic memories into semantic patterns
  - Compress redundant / duplicate memories
  - Strengthen frequently-referenced memories
  - Decay old, unused memories
  - Full consolidation cycle (like a "sleep" pass)

Persistence: brain/consolidation_state.json
"""

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


BRAIN_DIR = Path(__file__).parent.resolve()
CONSOLIDATION_FILE = BRAIN_DIR / "consolidation_state.json"

# ── Configuration ───────────────────────────────────────────────────────────

CONSOLIDATION_INTERVAL_HOURS = 6.0
MAX_EPISODIC_BUFFER = 200
SIMILARITY_THRESHOLD = 0.75
STRENGTHEN_BOOST = 0.15
DECAY_RATE = 0.02
MIN_MEMORY_STRENGTH = 0.05
MAX_SEMANTIC_ENTRIES = 500
MAX_COMPRESSED_LOG = 100


def _now() -> str:
    return datetime.now().isoformat()


def _timestamp() -> float:
    return time.time()


# ── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class EpisodicMemory:
    """A single episodic (event-based) memory."""
    memory_id: str
    content: str
    tags: List[str] = field(default_factory=list)
    strength: float = 1.0
    reference_count: int = 0
    created_at: str = ""
    last_accessed: str = ""

    def to_dict(self) -> dict:
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "tags": self.tags,
            "strength": round(self.strength, 4),
            "reference_count": self.reference_count,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EpisodicMemory":
        return cls(
            memory_id=d.get("memory_id", ""),
            content=d.get("content", ""),
            tags=d.get("tags", []),
            strength=d.get("strength", 1.0),
            reference_count=d.get("reference_count", 0),
            created_at=d.get("created_at", ""),
            last_accessed=d.get("last_accessed", ""),
        )


@dataclass
class SemanticMemory:
    """A consolidated semantic (fact/knowledge) memory."""
    semantic_id: str
    content: str
    source_episodes: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    strength: float = 1.0
    reference_count: int = 0
    created_at: str = ""
    last_accessed: str = ""

    def to_dict(self) -> dict:
        return {
            "semantic_id": self.semantic_id,
            "content": self.content,
            "source_episodes": self.source_episodes,
            "tags": self.tags,
            "strength": round(self.strength, 4),
            "reference_count": self.reference_count,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SemanticMemory":
        return cls(
            semantic_id=d.get("semantic_id", ""),
            content=d.get("content", ""),
            source_episodes=d.get("source_episodes", []),
            tags=d.get("tags", []),
            strength=d.get("strength", 1.0),
            reference_count=d.get("reference_count", 0),
            created_at=d.get("created_at", ""),
            last_accessed=d.get("last_accessed", ""),
        )


# ── Memory Consolidation ────────────────────────────────────────────────────

class MemoryConsolidation:
    """
    Sleep-like memory consolidation engine.

    Periodically processes episodic memories: compresses them into semantic
    knowledge, merges duplicates, strengthens important memories, and decays
    unused ones. Mimics hippocampal-neocortical consolidation during sleep.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self._episodic_buffer: List[EpisodicMemory] = []
        self._semantic_store: List[SemanticMemory] = []
        self._compression_log: List[dict] = []
        self._cycle_count: int = 0
        self._session_consolidations: int = 0
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": _now(),
                "last_update": _now(),
                "total_cycles": 0,
                "total_consolidated": 0,
                "total_compressed": 0,
                "total_decayed": 0,
            },
            "episodic_buffer": [],
            "semantic_store": [],
            "compression_log": [],
        }

    def _load(self):
        if not CONSOLIDATION_FILE.exists():
            self._data = self._empty_store()
            self._save()
            return
        try:
            raw = CONSOLIDATION_FILE.read_text(encoding="utf-8")
            self._data = json.loads(raw)
            self._episodic_buffer = [
                EpisodicMemory.from_dict(e)
                for e in self._data.get("episodic_buffer", [])
            ]
            self._semantic_store = [
                SemanticMemory.from_dict(s)
                for s in self._data.get("semantic_store", [])
            ]
            self._compression_log = self._data.get("compression_log", [])
            self._cycle_count = self._data["meta"].get("total_cycles", 0)
        except (json.JSONDecodeError, IOError):
            self._data = self._empty_store()
            self._save()

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._data["episodic_buffer"] = [e.to_dict() for e in self._episodic_buffer]
            self._data["semantic_store"] = [s.to_dict() for s in self._semantic_store]
            self._data["compression_log"] = self._compression_log[-MAX_COMPRESSED_LOG:]
            self._data["meta"]["last_update"] = _now()
            CONSOLIDATION_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ── Ingest ──────────────────────────────────────────────────────────

    def ingest_episode(self, content: str, tags: Optional[List[str]] = None) -> str:
        """
        Add an episodic memory to the consolidation buffer.

        Returns the memory_id.
        """
        import hashlib
        memory_id = hashlib.md5(
            f"{content}:{_now()}".encode()
        ).hexdigest()[:12]

        episode = EpisodicMemory(
            memory_id=memory_id,
            content=content,
            tags=tags or [],
            created_at=_now(),
            last_accessed=_now(),
        )

        with self._lock:
            self._episodic_buffer.append(episode)
            # Trim buffer if too large
            if len(self._episodic_buffer) > MAX_EPISODIC_BUFFER:
                self._episodic_buffer = self._episodic_buffer[-MAX_EPISODIC_BUFFER:]
            self._save()

        return memory_id

    # ── Consolidation ───────────────────────────────────────────────────

    def consolidate_episodes(self) -> int:
        """
        Take recent episodic memories, extract patterns, and merge
        into semantic knowledge. Returns number of new semantic entries.
        """
        with self._lock:
            if not self._episodic_buffer:
                return 0

            new_semantic = 0
            now = _now()

            # Group episodes by tag overlap
            tag_groups: Dict[str, List[EpisodicMemory]] = {}
            for ep in self._episodic_buffer:
                if ep.tags:
                    for tag in ep.tags:
                        tag_groups.setdefault(tag, []).append(ep)
                else:
                    tag_groups.setdefault("_untagged", []).append(ep)

            import hashlib

            for tag, episodes in tag_groups.items():
                if len(episodes) < 2:
                    continue

                # Create semantic entry summarizing the group
                contents = [ep.content for ep in episodes]
                summary = self._summarize_contents(contents)
                source_ids = [ep.memory_id for ep in episodes]

                semantic_id = hashlib.md5(
                    f"semantic:{tag}:{_now()}".encode()
                ).hexdigest()[:12]

                semantic = SemanticMemory(
                    semantic_id=semantic_id,
                    content=summary,
                    source_episodes=source_ids,
                    tags=[tag] if tag != "_untagged" else [],
                    strength=1.0,
                    created_at=now,
                    last_accessed=now,
                )
                self._semantic_store.append(semantic)
                new_semantic += 1

                # Mark source episodes as consolidated (reduce strength)
                for ep in episodes:
                    ep.strength *= 0.5

            # Trim semantic store
            if len(self._semantic_store) > MAX_SEMANTIC_ENTRIES:
                self._semantic_store.sort(key=lambda s: s.strength, reverse=True)
                self._semantic_store = self._semantic_store[:MAX_SEMANTIC_ENTRIES]

            self._data["meta"]["total_consolidated"] += new_semantic
            self._save()
            return new_semantic

    def compress_redundancy(self) -> int:
        """
        Find and merge duplicate / similar memories.
        Returns number of merges performed.
        """
        with self._lock:
            merges = 0

            # Compress episodic buffer
            to_remove: set = set()
            for i in range(len(self._episodic_buffer)):
                if i in to_remove:
                    continue
                for j in range(i + 1, len(self._episodic_buffer)):
                    if j in to_remove:
                        continue
                    sim = self._content_similarity(
                        self._episodic_buffer[i].content,
                        self._episodic_buffer[j].content,
                    )
                    if sim >= SIMILARITY_THRESHOLD:
                        # Keep the stronger one, merge tags
                        if self._episodic_buffer[i].strength >= self._episodic_buffer[j].strength:
                            keeper, removed = i, j
                        else:
                            keeper, removed = j, i

                        self._episodic_buffer[keeper].tags = list(set(
                            self._episodic_buffer[keeper].tags +
                            self._episodic_buffer[removed].tags
                        ))
                        self._episodic_buffer[keeper].reference_count += (
                            self._episodic_buffer[removed].reference_count
                        )
                        to_remove.add(removed)
                        merges += 1

            if to_remove:
                self._episodic_buffer = [
                    ep for i, ep in enumerate(self._episodic_buffer)
                    if i not in to_remove
                ]

            # Compress semantic store
            to_remove_sem: set = set()
            for i in range(len(self._semantic_store)):
                if i in to_remove_sem:
                    continue
                for j in range(i + 1, len(self._semantic_store)):
                    if j in to_remove_sem:
                        continue
                    sim = self._content_similarity(
                        self._semantic_store[i].content,
                        self._semantic_store[j].content,
                    )
                    if sim >= SIMILARITY_THRESHOLD:
                        if self._semantic_store[i].strength >= self._semantic_store[j].strength:
                            keeper, removed = i, j
                        else:
                            keeper, removed = j, i

                        self._semantic_store[keeper].source_episodes = list(set(
                            self._semantic_store[keeper].source_episodes +
                            self._semantic_store[removed].source_episodes
                        ))
                        self._semantic_store[keeper].tags = list(set(
                            self._semantic_store[keeper].tags +
                            self._semantic_store[removed].tags
                        ))
                        to_remove_sem.add(removed)
                        merges += 1

            if to_remove_sem:
                self._semantic_store = [
                    s for i, s in enumerate(self._semantic_store)
                    if i not in to_remove_sem
                ]

            self._data["meta"]["total_compressed"] += merges
            if merges > 0:
                self._compression_log.append({
                    "timestamp": _now(),
                    "merges": merges,
                    "episodic_remaining": len(self._episodic_buffer),
                    "semantic_remaining": len(self._semantic_store),
                })
                self._save()

            return merges

    def strengthen_important(self) -> int:
        """
        Boost memories that are referenced frequently.
        Returns number of memories strengthened.
        """
        with self._lock:
            strengthened = 0

            for ep in self._episodic_buffer:
                if ep.reference_count >= 3:
                    boost = min(STRENGTHEN_BOOST * (ep.reference_count / 3), 0.5)
                    ep.strength = min(1.0, ep.strength + boost)
                    strengthened += 1

            for sem in self._semantic_store:
                if sem.reference_count >= 3:
                    boost = min(STRENGTHEN_BOOST * (sem.reference_count / 3), 0.5)
                    sem.strength = min(1.0, sem.strength + boost)
                    strengthened += 1

            if strengthened > 0:
                self._save()
            return strengthened

    def decay_old(self) -> int:
        """
        Weaken unused memories. Returns number of memories decayed.
        """
        with self._lock:
            decayed = 0
            now = datetime.now()

            for ep in self._episodic_buffer:
                try:
                    last = datetime.fromisoformat(ep.last_accessed)
                    days = (now - last).total_seconds() / 86400.0
                    if days > 1:
                        ep.strength = max(MIN_MEMORY_STRENGTH, ep.strength - DECAY_RATE * days)
                        decayed += 1
                except (ValueError, TypeError):
                    pass

            for sem in self._semantic_store:
                try:
                    last = datetime.fromisoformat(sem.last_accessed)
                    days = (now - last).total_seconds() / 86400.0
                    if days > 1:
                        sem.strength = max(MIN_MEMORY_STRENGTH, sem.strength - DECAY_RATE * days)
                        decayed += 1
                except (ValueError, TypeError):
                    pass

            self._data["meta"]["total_decayed"] += decayed
            if decayed > 0:
                self._save()
            return decayed

    def run_consolidation_cycle(self) -> dict:
        """
        Full consolidation pass — like a sleep cycle.

        Returns a summary of what was done.
        """
        self._session_consolidations += 1
        self._cycle_count += 1

        consolidated = self.consolidate_episodes()
        compressed = self.compress_redundancy()
        strengthened = self.strengthen_important()
        decayed = self.decay_old()

        # Remove very weak episodic memories
        pruned = 0
        with self._lock:
            before = len(self._episodic_buffer)
            self._episodic_buffer = [
                ep for ep in self._episodic_buffer
                if ep.strength > MIN_MEMORY_STRENGTH
            ]
            pruned = before - len(self._episodic_buffer)

            self._data["meta"]["total_cycles"] = self._cycle_count
            self._save()

        return {
            "cycle": self._cycle_count,
            "episodes_consolidated": consolidated,
            "redundancies_compressed": compressed,
            "memories_strengthened": strengthened,
            "memories_decayed": decayed,
            "weak_memories_pruned": pruned,
            "episodic_count": len(self._episodic_buffer),
            "semantic_count": len(self._semantic_store),
            "timestamp": _now(),
        }

    # ── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _content_similarity(a: str, b: str) -> float:
        """Simple Jaccard word similarity."""
        if not a or not b:
            return 0.0
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    @staticmethod
    def _summarize_contents(contents: List[str]) -> str:
        """Create a simple summary from multiple content strings."""
        if len(contents) == 1:
            return contents[0]
        # Use the longest content as base, note count
        longest = max(contents, key=len)
        return f"[Consolidated from {len(contents)} episodes] {longest}"

    # ── Query ───────────────────────────────────────────────────────────

    def search_semantic(self, query: str, limit: int = 5) -> List[SemanticMemory]:
        """Search semantic memories by content similarity."""
        with self._lock:
            scored: List[Tuple[float, SemanticMemory]] = []
            for sem in self._semantic_store:
                sim = self._content_similarity(query, sem.content)
                if sim > 0:
                    sem.last_accessed = _now()
                    sem.reference_count += 1
                    scored.append((sim * sem.strength, sem))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [s for _, s in scored[:limit]]

    def get_episodic_buffer(self, limit: int = 20) -> List[EpisodicMemory]:
        """Get recent episodic memories."""
        with self._lock:
            return list(self._episodic_buffer[-limit:])

    # ── Statistics ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get overall consolidation statistics."""
        with self._lock:
            return {
                "episodic_count": len(self._episodic_buffer),
                "semantic_count": len(self._semantic_store),
                "total_cycles": self._cycle_count,
                "total_consolidated": self._data["meta"].get("total_consolidated", 0),
                "total_compressed": self._data["meta"].get("total_compressed", 0),
                "total_decayed": self._data["meta"].get("total_decayed", 0),
                "session_consolidations": self._session_consolidations,
            }

    def format_for_prompt(self, max_chars: int = 500) -> str:
        """Format consolidation state for system prompt injection."""
        stats = self.get_stats()
        parts = [
            "[MEMORY CONSOLIDATION — Sleep-like processing]",
            f"Episodic buffer: {stats['episodic_count']} | "
            f"Semantic store: {stats['semantic_count']}",
            f"Consolidation cycles: {stats['total_cycles']} | "
            f"Compressions: {stats['total_compressed']}",
        ]
        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "[...]"
        return result


# ── Singleton ───────────────────────────────────────────────────────────────

_memory_consolidation = None
_consolidation_lock = threading.Lock()


def get_memory_consolidation() -> MemoryConsolidation:
    """Get singleton MemoryConsolidation instance."""
    global _memory_consolidation
    if _memory_consolidation is None:
        with _consolidation_lock:
            if _memory_consolidation is None:
                _memory_consolidation = MemoryConsolidation()
    return _memory_consolidation
