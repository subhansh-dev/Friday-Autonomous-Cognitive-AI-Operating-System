"""
Flow Graph - In-memory data flow graph for security analysis.

Provides a simple dict-based graph structure to track data flow
between variables, function calls, and sinks. No external
graph libraries required.

Node types:
  - variable: named variable or parameter
  - call: function/method invocation
  - literal: string/number/bool constant
  - source: external input entry point
  - sink: dangerous operation
  - param: function parameter

Edge types:
  - assigns: data flows from RHS to LHS
  - calls: data flows into function call arguments
  - returns: data flows from return value
  - passes: parameter passing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class NodeType(str, Enum):
    VARIABLE = "variable"
    CALL = "call"
    LITERAL = "literal"
    SOURCE = "source"
    SINK = "sink"
    PARAM = "param"


class EdgeType(str, Enum):
    ASSIGNS = "assigns"       # var = expr
    CALLS = "calls"           # fn(args)
    RETURNS = "returns"       # return expr
    PASSES = "passes"         # arg → param


@dataclass
class FlowNode:
    """A node in the data flow graph."""
    node_id: str
    node_type: NodeType
    name: str
    file_path: str = ""
    line: int = 0
    col: int = 0
    parent_function: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def __hash__(self) -> int:
        return hash(self.node_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FlowNode):
            return NotImplemented
        return self.node_id == other.node_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "name": self.name,
            "file_path": self.file_path,
            "line": self.line,
            "col": self.col,
            "parent_function": self.parent_function,
            "extra": self.extra,
        }


@dataclass
class FlowEdge:
    """A directed edge representing data flow."""
    source_id: str
    target_id: str
    edge_type: EdgeType
    label: str = ""
    file_path: str = ""
    line: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "label": self.label,
            "file_path": self.file_path,
            "line": self.line,
        }


class FlowGraph:
    """
    In-memory data flow graph.

    Stores nodes and edges using plain dicts for zero-dependency operation.
    Supports path tracing from sources to sinks via BFS/DFS.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, FlowNode] = {}
        self._edges: list[FlowEdge] = []
        # adjacency: node_id → list of (edge, target_id)
        self._adj: dict[str, list[tuple[FlowEdge, str]]] = {}
        # reverse adjacency for backward tracing
        self._radj: dict[str, list[tuple[FlowEdge, str]]] = {}
        self._counter: int = 0

    # ── node management ──────────────────────────────────────────────

    def add_node(
        self,
        node_type: NodeType,
        name: str,
        file_path: str = "",
        line: int = 0,
        col: int = 0,
        parent_function: str = "",
        node_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> FlowNode:
        """Add a node and return it. Auto-generates ID if not provided."""
        if node_id is None:
            node_id = self._next_id(node_type)
        node = FlowNode(
            node_id=node_id,
            node_type=node_type,
            name=name,
            file_path=file_path,
            line=line,
            col=col,
            parent_function=parent_function,
            extra=extra or {},
        )
        self._nodes[node_id] = node
        self._adj.setdefault(node_id, [])
        self._radj.setdefault(node_id, [])
        return node

    def get_node(self, node_id: str) -> FlowNode | None:
        return self._nodes.get(node_id)

    def get_nodes_by_type(self, node_type: NodeType) -> list[FlowNode]:
        return [n for n in self._nodes.values() if n.node_type == node_type]

    def get_nodes_by_name(self, name: str) -> list[FlowNode]:
        return [n for n in self._nodes.values() if n.name == name]

    def all_nodes(self) -> list[FlowNode]:
        return list(self._nodes.values())

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    # ── edge management ──────────────────────────────────────────────

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
        label: str = "",
        file_path: str = "",
        line: int = 0,
    ) -> FlowEdge:
        """Add a directed edge. Raises KeyError if nodes don't exist."""
        if source_id not in self._nodes:
            raise KeyError(f"Source node '{source_id}' not in graph")
        if target_id not in self._nodes:
            raise KeyError(f"Target node '{target_id}' not in graph")
        edge = FlowEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            label=label,
            file_path=file_path,
            line=line,
        )
        self._edges.append(edge)
        self._adj[source_id].append((edge, target_id))
        self._radj[target_id].append((edge, source_id))
        return edge

    def get_edges_from(self, node_id: str) -> list[FlowEdge]:
        return [e for e, _ in self._adj.get(node_id, [])]

    def get_edges_to(self, node_id: str) -> list[FlowEdge]:
        return [e for e, _ in self._radj.get(node_id, [])]

    def all_edges(self) -> list[FlowEdge]:
        return list(self._edges)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    # ── path tracing ─────────────────────────────────────────────────

    def trace_source_to_sink(
        self,
        source_id: str,
        sink_id: str,
        max_depth: int = 20,
    ) -> list[list[str]]:
        """
        Find all paths from a source node to a sink node using DFS.

        Returns a list of paths, where each path is a list of node_ids.
        Limits search to max_depth to prevent infinite loops.
        """
        if source_id not in self._nodes or sink_id not in self._nodes:
            return []
        paths: list[list[str]] = []
        self._dfs_paths(source_id, sink_id, [source_id], set(), paths, max_depth, 0)
        return paths

    def _dfs_paths(
        self,
        current: str,
        target: str,
        path: list[str],
        visited: set[str],
        results: list[list[str]],
        max_depth: int,
        depth: int,
    ) -> None:
        if depth >= max_depth:
            return
        if current == target and depth > 0:
            results.append(list(path))
            return
        for edge, neighbor in self._adj.get(current, []):
            if neighbor not in visited:
                visited.add(neighbor)
                path.append(neighbor)
                self._dfs_paths(neighbor, target, path, visited, results, max_depth, depth + 1)
                path.pop()
                visited.discard(neighbor)

    def get_path(
        self,
        source_id: str,
        sink_id: str,
        max_depth: int = 20,
    ) -> list[str] | None:
        """Find the shortest path from source to sink using BFS."""
        if source_id not in self._nodes or sink_id not in self._nodes:
            return None
        from collections import deque
        queue: deque[tuple[str, list[str]]] = deque([(source_id, [source_id])])
        visited = {source_id}
        while queue:
            current, path = queue.popleft()
            if current == sink_id and len(path) > 1:
                return path
            for _, neighbor in self._adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return None

    def get_all_source_to_sink_paths(self, max_depth: int = 20) -> list[list[str]]:
        """Find all paths from any source node to any sink node."""
        sources = self.get_nodes_by_type(NodeType.SOURCE)
        sinks = self.get_nodes_by_type(NodeType.SINK)
        all_paths: list[list[str]] = []
        for src in sources:
            for sink in sinks:
                paths = self.trace_source_to_sink(src.node_id, sink.node_id, max_depth)
                all_paths.extend(paths)
        return all_paths

    # ── utilities ────────────────────────────────────────────────────

    def _next_id(self, node_type: NodeType) -> str:
        self._counter += 1
        return f"{node_type.value}_{self._counter}"

    def get_subgraph(self, node_ids: set[str]) -> "FlowGraph":
        """Extract a subgraph containing only the given nodes."""
        sub = FlowGraph()
        for nid in node_ids:
            node = self._nodes.get(nid)
            if node:
                sub.add_node(
                    node_type=node.node_type,
                    name=node.name,
                    file_path=node.file_path,
                    line=node.line,
                    col=node.col,
                    parent_function=node.parent_function,
                    node_id=node.node_id,
                    extra=dict(node.extra),
                )
        for edge in self._edges:
            if edge.source_id in node_ids and edge.target_id in node_ids:
                sub.add_edge(
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    edge_type=edge.edge_type,
                    label=edge.label,
                    file_path=edge.file_path,
                    line=edge.line,
                )
        return sub

    def merge(self, other: "FlowGraph") -> None:
        """Merge another FlowGraph into this one."""
        for node in other.all_nodes():
            if node.node_id not in self._nodes:
                self.add_node(
                    node_type=node.node_type,
                    name=node.name,
                    file_path=node.file_path,
                    line=node.line,
                    col=node.col,
                    parent_function=node.parent_function,
                    node_id=node.node_id,
                    extra=dict(node.extra),
                )
        for edge in other.all_edges():
            existing = [
                e for e in self._edges
                if e.source_id == edge.source_id and e.target_id == edge.target_id
                and e.edge_type == edge.edge_type
            ]
            if not existing:
                self.add_edge(
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    edge_type=edge.edge_type,
                    label=edge.label,
                    file_path=edge.file_path,
                    line=edge.line,
                )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the graph to a dict."""
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges],
        }

    def summary(self) -> dict[str, int]:
        """Return a summary of node/edge counts by type."""
        node_counts: dict[str, int] = {}
        for n in self._nodes.values():
            node_counts[n.node_type.value] = node_counts.get(n.node_type.value, 0) + 1
        edge_counts: dict[str, int] = {}
        for e in self._edges:
            edge_counts[e.edge_type.value] = edge_counts.get(e.edge_type.value, 0) + 1
        return {"nodes": node_counts, "edges": edge_counts}

    def __repr__(self) -> str:
        return f"FlowGraph(nodes={self.node_count}, edges={self.edge_count})"
