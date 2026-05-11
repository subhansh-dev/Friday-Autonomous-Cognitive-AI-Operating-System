#!/usr/bin/env python3
"""
associative_memory.py — FRIDAY Associative Memory (Spreading Activation)
=========================================================================

Implements spreading activation networks for context-dependent recall.
Memories are stored as nodes in a graph; recall activates matching nodes
and spreads activation to connected nodes, returning results ranked by
activation strength.

Inspired by:
  - Collins & Loftus (1975) — Spreading Activation theory of semantic processing
  - ACT-R memory retrieval (Anderson, 2007)
  - Context-dependent memory retrieval (Tulving & Thomson, 1973)

Key behaviors:
  - Store memories with associative links (tags, connections)
  - Recall via spreading activation (activate → spread → rank)
  - Create bidirectional associations between memories
  - Forget weakly activated, rarely accessed nodes
  - Retrieve surrounding context for any memory node

Persistence: brain/associative_state.json
"""

import hashlib
import json
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


BRAIN_DIR = Path(__file__).parent.resolve()
ASSOCIATIVE_FILE = BRAIN_DIR / "associative_state.json"

# ── Configuration ───────────────────────────────────────────────────────────

MAX_NODES = 2000
MAX_CONNECTIONS_PER_NODE = 50
SPREAD_DECAY = 0.5           # activation decay per hop
ACTIVATION_THRESHOLD = 0.1   # minimum activation to propagate
DEFAULT_DECAY_RATE = 0.01    # daily passive decay
MIN_ACTIVATION = 0.01
MAX_SPREAD_DEPTH = 4
ACCESS_BOOST = 0.1           # activation boost on access
FORGET_THRESHOLD = 0.05


def _now() -> str:
    return datetime.now().isoformat()


def _timestamp() -> float:
    return time.time()


# ── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class Connection:
    """A weighted directional connection between two memory nodes."""
    target_id: str
    strength: float = 0.5
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "strength": round(self.strength, 4),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Connection":
        return cls(
            target_id=d.get("target_id", ""),
            strength=d.get("strength", 0.5),
            created_at=d.get("created_at", ""),
        )


@dataclass
class MemoryNode:
    """A node in the associative memory network."""
    node_id: str
    content: str
    tags: List[str] = field(default_factory=list)
    activation_level: float = 0.0
    base_activation: float = 0.5
    decay_rate: float = DEFAULT_DECAY_RATE
    connections: List[Connection] = field(default_factory=list)
    access_count: int = 0
    created_at: str = ""
    last_accessed: str = ""

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "content": self.content,
            "tags": self.tags,
            "activation_level": round(self.activation_level, 4),
            "base_activation": round(self.base_activation, 4),
            "decay_rate": round(self.decay_rate, 4),
            "connections": [c.to_dict() for c in self.connections],
            "access_count": self.access_count,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryNode":
        return cls(
            node_id=d.get("node_id", ""),
            content=d.get("content", ""),
            tags=d.get("tags", []),
            activation_level=d.get("activation_level", 0.0),
            base_activation=d.get("base_activation", 0.5),
            decay_rate=d.get("decay_rate", DEFAULT_DECAY_RATE),
            connections=[Connection.from_dict(c) for c in d.get("connections", [])],
            access_count=d.get("access_count", 0),
            created_at=d.get("created_at", ""),
            last_accessed=d.get("last_accessed", ""),
        )


# ── Associative Memory ──────────────────────────────────────────────────────

class AssociativeMemory:
    """
    Spreading activation network for context-dependent memory recall.

    Memories are nodes in a weighted graph. Recall activates nodes matching
    a query, then spreads activation along connections, surfacing the most
    contextually relevant memories.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self._nodes: Dict[str, MemoryNode] = {}
        self._tag_index: Dict[str, Set[str]] = {}  # tag → node_ids
        self._session_recalls: int = 0
        self._session_stores: int = 0
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": _now(),
                "last_update": _now(),
                "total_nodes": 0,
                "total_connections": 0,
                "total_recalls": 0,
                "total_stores": 0,
            },
            "nodes": {},
        }

    def _load(self):
        if not ASSOCIATIVE_FILE.exists():
            self._data = self._empty_store()
            self._save()
            return
        try:
            raw = ASSOCIATIVE_FILE.read_text(encoding="utf-8")
            self._data = json.loads(raw)
            for nid, ndata in self._data.get("nodes", {}).items():
                node = MemoryNode.from_dict(ndata)
                self._nodes[nid] = node
                for tag in node.tags:
                    self._tag_index.setdefault(tag, set()).add(nid)
        except (json.JSONDecodeError, IOError):
            self._data = self._empty_store()
            self._save()

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._data["nodes"] = {
                nid: node.to_dict() for nid, node in self._nodes.items()
            }
            total_conns = sum(len(n.connections) for n in self._nodes.values())
            self._data["meta"]["total_nodes"] = len(self._nodes)
            self._data["meta"]["total_connections"] = total_conns
            self._data["meta"]["last_update"] = _now()
            ASSOCIATIVE_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ── Store ───────────────────────────────────────────────────────────

    def store(self, content: str, tags: Optional[List[str]] = None,
              connections: Optional[List[str]] = None) -> str:
        """
        Store a memory node with associative links.

        Args:
            content: Memory content text
            tags: Categorical tags for indexing
            connections: List of existing node_ids to connect to

        Returns:
            The new node_id
        """
        node_id = hashlib.md5(
            f"{content}:{_now()}".encode()
        ).hexdigest()[:12]

        now = _now()
        conns: List[Connection] = []
        if connections:
            for target_id in connections:
                if target_id in self._nodes:
                    conns.append(Connection(
                        target_id=target_id,
                        strength=0.5,
                        created_at=now,
                    ))

        node = MemoryNode(
            node_id=node_id,
            content=content,
            tags=tags or [],
            activation_level=1.0,
            base_activation=0.5,
            connections=conns,
            created_at=now,
            last_accessed=now,
        )

        with self._lock:
            self._nodes[node_id] = node
            for tag in node.tags:
                self._tag_index.setdefault(tag, set()).add(node_id)

            # Create reverse connections
            for conn in conns:
                target = self._nodes.get(conn.target_id)
                if target and len(target.connections) < MAX_CONNECTIONS_PER_NODE:
                    # Check if reverse connection already exists
                    existing_ids = {c.target_id for c in target.connections}
                    if node_id not in existing_ids:
                        target.connections.append(Connection(
                            target_id=node_id,
                            strength=conn.strength,
                            created_at=now,
                        ))

            # Enforce capacity
            if len(self._nodes) > MAX_NODES:
                self._evict_weakest()

            self._session_stores += 1
            self._data["meta"]["total_stores"] += 1
            self._save()

        return node_id

    def _evict_weakest(self):
        """Remove the weakest node when capacity is exceeded."""
        if not self._nodes:
            return
        weakest_id = min(
            self._nodes,
            key=lambda nid: self._nodes[nid].base_activation *
                            (1 + self._nodes[nid].access_count * 0.01),
        )
        self._remove_node(weakest_id)

    def _remove_node(self, node_id: str):
        """Remove a node and all references to it."""
        node = self._nodes.pop(node_id, None)
        if node is None:
            return
        for tag in node.tags:
            self._tag_index.get(tag, set()).discard(node_id)
        # Remove incoming connections
        for other in self._nodes.values():
            other.connections = [
                c for c in other.connections if c.target_id != node_id
            ]

    # ── Recall ──────────────────────────────────────────────────────────

    def recall(self, query: str, depth: int = 2) -> List[Tuple[MemoryNode, float]]:
        """
        Spreading activation recall.

        1. Activate nodes matching the query (by content/tags)
        2. Spread activation to connected nodes up to `depth` hops
        3. Return nodes ranked by final activation level

        Args:
            query: Search query
            depth: Maximum spread depth (default 2)

        Returns:
            List of (MemoryNode, activation_level) tuples, sorted by activation
        """
        depth = min(depth, MAX_SPREAD_DEPTH)

        with self._lock:
            self._session_recalls += 1
            self._data["meta"]["total_recalls"] += 1

            # Phase 1: Direct activation
            activated: Dict[str, float] = {}
            query_lower = query.lower()
            query_words = set(query_lower.split())

            for nid, node in self._nodes.items():
                score = 0.0
                # Content match
                content_lower = node.content.lower()
                content_words = set(content_lower.split())
                overlap = query_words & content_words
                if overlap:
                    score += len(overlap) / max(len(query_words), 1)
                if query_lower in content_lower:
                    score += 0.5
                # Tag match
                for tag in node.tags:
                    if tag.lower() in query_lower or query_lower in tag.lower():
                        score += 0.3

                if score > 0:
                    activated[nid] = min(1.0, score)
                    node.access_count += 1
                    node.last_accessed = _now()

            # Phase 2: Spread activation
            for _hop in range(depth):
                new_activations: Dict[str, float] = {}
                for nid, activation in list(activated.items()):
                    node = self._nodes.get(nid)
                    if not node:
                        continue
                    for conn in node.connections:
                        spread = activation * conn.strength * SPREAD_DECAY
                        if spread < ACTIVATION_THRESHOLD:
                            continue
                        target_id = conn.target_id
                        if target_id in self._nodes:
                            current = activated.get(target_id, 0.0)
                            new_val = min(1.0, current + spread)
                            if new_val > current:
                                new_activations[target_id] = new_val

                # Merge new activations
                for nid, val in new_activations.items():
                    activated[nid] = val
                    self._nodes[nid].access_count += 1
                    self._nodes[nid].last_accessed = _now()

            # Phase 3: Rank and return
            results: List[Tuple[MemoryNode, float]] = []
            for nid, activation in activated.items():
                node = self._nodes.get(nid)
                if node and activation >= ACTIVATION_THRESHOLD:
                    node.activation_level = activation
                    results.append((node, activation))

            results.sort(key=lambda x: x[1], reverse=True)
            self._save()
            return results

    # ── Associate ───────────────────────────────────────────────────────

    def associate(self, node_a: str, node_b: str, strength: float = 0.5):
        """
        Create a bidirectional association between two nodes.

        Args:
            node_a: First node ID
            node_b: Second node ID
            strength: Connection strength (0.0 to 1.0)
        """
        now = _now()
        strength = max(0.0, min(1.0, strength))

        with self._lock:
            a = self._nodes.get(node_a)
            b = self._nodes.get(node_b)
            if not a or not b:
                return

            # Add a → b
            existing_a = {c.target_id for c in a.connections}
            if node_b not in existing_a and len(a.connections) < MAX_CONNECTIONS_PER_NODE:
                a.connections.append(Connection(
                    target_id=node_b, strength=strength, created_at=now,
                ))
            else:
                # Update existing strength
                for c in a.connections:
                    if c.target_id == node_b:
                        c.strength = max(c.strength, strength)

            # Add b → a
            existing_b = {c.target_id for c in b.connections}
            if node_a not in existing_b and len(b.connections) < MAX_CONNECTIONS_PER_NODE:
                b.connections.append(Connection(
                    target_id=node_a, strength=strength, created_at=now,
                ))
            else:
                for c in b.connections:
                    if c.target_id == node_a:
                        c.strength = max(c.strength, strength)

            self._save()

    # ── Forget ──────────────────────────────────────────────────────────

    def forget(self, threshold: float = FORGET_THRESHOLD) -> int:
        """
        Remove weakly activated, rarely accessed nodes.
        Returns number of nodes removed.
        """
        with self._lock:
            to_remove: List[str] = []
            for nid, node in self._nodes.items():
                # Compute a persistence score
                recency = 0.0
                try:
                    last = datetime.fromisoformat(node.last_accessed)
                    days_since = (datetime.now() - last).total_seconds() / 86400.0
                    recency = max(0, 1.0 - days_since / 30.0)
                except (ValueError, TypeError):
                    pass

                persistence = (
                    node.base_activation * 0.3 +
                    min(1.0, node.access_count / 10.0) * 0.3 +
                    recency * 0.2 +
                    min(1.0, len(node.connections) / 5.0) * 0.2
                )

                if persistence < threshold:
                    to_remove.append(nid)

            for nid in to_remove:
                self._remove_node(nid)

            if to_remove:
                self._save()
            return len(to_remove)

    # ── Context ─────────────────────────────────────────────────────────

    def get_context(self, node_id: str, depth: int = 1) -> dict:
        """
        Get the surrounding associative context for a node.

        Returns the node and its immediate neighbors with connection strengths.
        """
        with self._lock:
            node = self._nodes.get(node_id)
            if not node:
                return {"error": "node not found"}

            neighbors: List[dict] = []
            for conn in node.connections:
                target = self._nodes.get(conn.target_id)
                if target:
                    neighbors.append({
                        "node_id": target.node_id,
                        "content": target.content[:200],
                        "tags": target.tags,
                        "connection_strength": round(conn.strength, 4),
                        "activation": round(target.activation_level, 4),
                    })

            # Second-degree neighbors
            second_degree: List[dict] = []
            if depth >= 2:
                seen = {node_id} | {n["node_id"] for n in neighbors}
                for n_info in neighbors:
                    n_node = self._nodes.get(n_info["node_id"])
                    if not n_node:
                        continue
                    for conn in n_node.connections:
                        if conn.target_id in seen:
                            continue
                        seen.add(conn.target_id)
                        target = self._nodes.get(conn.target_id)
                        if target:
                            second_degree.append({
                                "node_id": target.node_id,
                                "content": target.content[:200],
                                "tags": target.tags,
                                "via": n_node.node_id,
                                "connection_strength": round(conn.strength, 4),
                            })

            return {
                "node": {
                    "node_id": node.node_id,
                    "content": node.content,
                    "tags": node.tags,
                    "activation": round(node.activation_level, 4),
                    "access_count": node.access_count,
                },
                "neighbors": neighbors,
                "second_degree": second_degree,
            }

    # ── Query Helpers ───────────────────────────────────────────────────

    def get_node(self, node_id: str) -> Optional[MemoryNode]:
        """Get a node by ID."""
        with self._lock:
            return self._nodes.get(node_id)

    def get_by_tag(self, tag: str) -> List[MemoryNode]:
        """Get all nodes with a given tag."""
        with self._lock:
            nids = self._tag_index.get(tag, set())
            return [self._nodes[nid] for nid in nids if nid in self._nodes]

    def get_all_tags(self) -> List[str]:
        """Get all tags in the network."""
        with self._lock:
            return list(self._tag_index.keys())

    # ── Statistics ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get overall associative memory statistics."""
        with self._lock:
            total_conns = sum(len(n.connections) for n in self._nodes.values())
            avg_conns = total_conns / max(len(self._nodes), 1)
            total_access = sum(n.access_count for n in self._nodes.values())
            return {
                "total_nodes": len(self._nodes),
                "total_connections": total_conns,
                "avg_connections_per_node": round(avg_conns, 2),
                "total_tags": len(self._tag_index),
                "total_access_count": total_access,
                "total_recalls": self._data["meta"].get("total_recalls", 0),
                "total_stores": self._data["meta"].get("total_stores", 0),
                "session_recalls": self._session_recalls,
                "session_stores": self._session_stores,
            }

    def format_for_prompt(self, max_chars: int = 500) -> str:
        """Format associative memory state for system prompt injection."""
        stats = self.get_stats()
        tags = self.get_all_tags()[:10]
        parts = [
            "[ASSOCIATIVE MEMORY — Spreading activation network]",
            f"Nodes: {stats['total_nodes']} | "
            f"Connections: {stats['total_connections']} | "
            f"Tags: {stats['total_tags']}",
            f"Recalls: {stats['total_recalls']} | "
            f"Avg connections/node: {stats['avg_connections_per_node']:.1f}",
        ]
        if tags:
            parts.append(f"Active tags: {', '.join(tags)}")
        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "[...]"
        return result


# ── Singleton ───────────────────────────────────────────────────────────────

_associative_memory = None
_associative_lock = threading.Lock()


def get_associative_memory() -> AssociativeMemory:
    """Get singleton AssociativeMemory instance."""
    global _associative_memory
    if _associative_memory is None:
        with _associative_lock:
            if _associative_memory is None:
                _associative_memory = AssociativeMemory()
    return _associative_memory
