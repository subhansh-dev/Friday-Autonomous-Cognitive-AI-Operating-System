#!/usr/bin/env python3
"""
code_intelligence.py — FRIDAY Code Intelligence Module
=======================================================

Semantic codebase understanding inspired by expert programmer cognition:
- Chunk Memory: Stores code patterns (design patterns, idioms, algorithms)
  as vector embeddings for rapid recognition — like an expert's 50K chunks
- Codebase Graph: AST + dependency analysis building a semantic map of
  file roles, module relationships, and data flows
- Pattern Recognition: Identifies structural patterns (MVC, observer,
  factory, etc.) and code idioms from partial cues

This is the "perception" layer of the Cognitive Coding Engine — it sees
and understands code the way an expert programmer does.
"""

import ast
import hashlib
import json
import re
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


BRAIN_DIR = Path(__file__).parent.resolve()
CHUNK_STORE_FILE = BRAIN_DIR / "code_chunks.json"
CODEBASE_GRAPH_FILE = BRAIN_DIR / "codebase_graph.json"

# ── Code Pattern Categories ─────────────────────────────────────────────
PATTERN_CATEGORIES = {
    "creational": ["factory", "builder", "singleton", "prototype", "abstract_factory"],
    "structural": ["adapter", "bridge", "composite", "decorator", "facade", "proxy"],
    "behavioral": ["observer", "strategy", "command", "state", "template_method", "iterator"],
    "concurrency": ["producer_consumer", "thread_pool", "async_await", "mutex", "semaphore"],
    "architectural": ["mvc", "mvp", "mvvm", "repository", "dependency_injection", "event_driven"],
    "algorithmic": ["binary_search", "quicksort", "bfs", "dfs", "dynamic_programming", "greedy"],
    "data_structure": ["linked_list", "tree", "graph", "hash_map", "stack", "queue", "heap"],
    "error_handling": ["try_except_finally", "retry_backoff", "circuit_breaker", "fallback"],
    "concurrency_pattern": ["async_generator", "producer_consumer", "reader_writer", "barrier"],
}


class CodeChunk:
    """A recognized code pattern — like an expert's mental 'chunk'."""

    def __init__(self, chunk_id: str, pattern_type: str, name: str,
                 signature: str, description: str, code_template: str = "",
                 language: str = "python", tags: List[str] = None):
        self.chunk_id = chunk_id
        self.pattern_type = pattern_type  # e.g. "creational.factory"
        self.name = name
        self.signature = signature  # structural fingerprint
        self.description = description
        self.code_template = code_template
        self.language = language
        self.tags = tags or []
        self.created = datetime.now().isoformat()
        self.use_count = 0
        self.success_count = 0
        self.last_used = self.created

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "pattern_type": self.pattern_type,
            "name": self.name,
            "signature": self.signature,
            "description": self.description,
            "code_template": self.code_template,
            "language": self.language,
            "tags": self.tags,
            "created": self.created,
            "use_count": self.use_count,
            "success_count": self.success_count,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CodeChunk":
        c = cls(
            chunk_id=data["chunk_id"],
            pattern_type=data["pattern_type"],
            name=data["name"],
            signature=data.get("signature", ""),
            description=data.get("description", ""),
            code_template=data.get("code_template", ""),
            language=data.get("language", "python"),
            tags=data.get("tags", []),
        )
        c.created = data.get("created", c.created)
        c.use_count = data.get("use_count", 0)
        c.success_count = data.get("success_count", 0)
        c.last_used = data.get("last_used", c.last_used)
        return c

    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.use_count, 1)

    def record_use(self, success: bool):
        self.use_count += 1
        if success:
            self.success_count += 1
        self.last_used = datetime.now().isoformat()


class CodebaseNode:
    """A node in the codebase semantic graph."""

    def __init__(self, node_id: str, node_type: str, name: str,
                 file_path: str = "", line_start: int = 0, line_end: int = 0):
        self.node_id = node_id
        self.node_type = node_type  # file, class, function, module, variable
        self.name = name
        self.file_path = file_path
        self.line_start = line_start
        self.line_end = line_end
        self.dependencies: Set[str] = set()  # node_ids this depends on
        self.dependents: Set[str] = set()    # node_ids that depend on this
        self.properties: Dict = {}
        self.complexity_score: float = 0.0
        self.importance_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "name": self.name,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "dependencies": list(self.dependencies),
            "dependents": list(self.dependents),
            "properties": self.properties,
            "complexity_score": self.complexity_score,
            "importance_score": self.importance_score,
        }


class CodeIntelligence:
    """
    Semantic code understanding engine.

    Provides:
    - Pattern recognition via chunk memory (expert-like rapid identification)
    - Codebase graph for structural understanding
    - Semantic search over code patterns
    - Complexity analysis
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._chunks: Dict[str, CodeChunk] = {}
        self._graph_nodes: Dict[str, CodebaseNode] = {}
        self._file_cache: Dict[str, dict] = {}  # path → parsed AST info
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _load(self):
        """Load chunk store and codebase graph."""
        if CHUNK_STORE_FILE.exists():
            try:
                data = json.loads(CHUNK_STORE_FILE.read_text(encoding="utf-8"))
                for c in data.get("chunks", []):
                    chunk = CodeChunk.from_dict(c)
                    self._chunks[chunk.chunk_id] = chunk
                print(f"[CodeIntel] Loaded {len(self._chunks)} code chunks")
            except Exception as e:
                print(f"[CodeIntel] Chunk load error: {e}")

        if CODEBASE_GRAPH_FILE.exists():
            try:
                data = json.loads(CODEBASE_GRAPH_FILE.read_text(encoding="utf-8"))
                for n in data.get("nodes", []):
                    node = CodebaseNode(
                        node_id=n["node_id"],
                        node_type=n["node_type"],
                        name=n["name"],
                        file_path=n.get("file_path", ""),
                        line_start=n.get("line_start", 0),
                        line_end=n.get("line_end", 0),
                    )
                    node.dependencies = set(n.get("dependencies", []))
                    node.dependents = set(n.get("dependents", []))
                    node.properties = n.get("properties", {})
                    node.complexity_score = n.get("complexity_score", 0)
                    node.importance_score = n.get("importance_score", 0)
                    self._graph_nodes[node.node_id] = node
                print(f"[CodeIntel] Loaded {len(self._graph_nodes)} graph nodes")
            except Exception as e:
                print(f"[CodeIntel] Graph load error: {e}")

    def _save(self):
        """Persist chunks and graph to disk."""
        with self._lock:
            try:
                BRAIN_DIR.mkdir(parents=True, exist_ok=True)
                CHUNK_STORE_FILE.write_text(json.dumps({
                    "chunks": [c.to_dict() for c in self._chunks.values()],
                    "updated": datetime.now().isoformat(),
                }, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                print(f"[CodeIntel] Chunk save error: {e}")

            try:
                CODEBASE_GRAPH_FILE.write_text(json.dumps({
                    "nodes": [n.to_dict() for n in self._graph_nodes.values()],
                    "updated": datetime.now().isoformat(),
                }, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                print(f"[CodeIntel] Graph save error: {e}")

    # ── Codebase Parsing (AST Analysis) ─────────────────────────────────

    def parse_file(self, file_path: str, content: str = None) -> dict:
        """
        Parse a Python file into structural components.
        Returns: {classes, functions, imports, complexity, dependencies}
        """
        if content is None:
            try:
                content = Path(file_path).read_text(encoding="utf-8")
            except Exception as e:
                return {"error": str(e)}

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return {"error": f"Syntax error: {e}", "partial": True}

        result = {
            "file_path": file_path,
            "classes": [],
            "functions": [],
            "imports": [],
            "global_vars": [],
            "decorators": [],
            "complexity": 0,
            "lines": len(content.splitlines()),
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = []
                class_vars = []
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        methods.append({
                            "name": item.name,
                            "args": [a.arg for a in item.args.args],
                            "line": item.lineno,
                            "is_async": isinstance(item, ast.AsyncFunctionDef),
                            "decorators": [self._get_decorator_name(d) for d in item.decorator_list],
                        })
                    elif isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                class_vars.append(target.id)
                result["classes"].append({
                    "name": node.name,
                    "line": node.lineno,
                    "bases": [self._get_name(base) for base in node.bases],
                    "methods": methods,
                    "class_vars": class_vars,
                    "decorators": [self._get_decorator_name(d) for d in node.decorator_list],
                })

            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                # Only top-level functions
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result["functions"].append({
                        "name": node.name,
                        "args": [a.arg for a in node.args.args],
                        "line": node.lineno,
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                        "decorators": [self._get_decorator_name(d) for d in node.decorator_list],
                        "returns": self._get_return_annotation(node),
                    })

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    result["imports"].append({
                        "module": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno,
                    })

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    result["imports"].append({
                        "module": f"{module}.{alias.name}",
                        "alias": alias.asname,
                        "from": module,
                        "line": node.lineno,
                    })

        # Calculate cyclomatic complexity
        result["complexity"] = self._calc_complexity(tree)

        # Cache the parsed result
        self._file_cache[file_path] = result
        return result

    def build_graph(self, project_dir: str, file_paths: List[str] = None) -> dict:
        """
        Build a semantic graph of the entire codebase.
        Nodes: files, classes, functions
        Edges: imports, calls, inheritance
        """
        project_path = Path(project_dir)
        if file_paths is None:
            file_paths = [str(f) for f in project_path.rglob("*.py")
                         if "__pycache__" not in str(f) and ".git" not in str(f)]

        nodes_added = 0
        edges_added = 0

        for fp in file_paths:
            rel_path = str(Path(fp).relative_to(project_path)) if project_path in Path(fp).parents else fp
            parsed = self.parse_file(fp)
            if "error" in parsed:
                continue

            # File node
            file_id = f"file:{rel_path}"
            file_node = CodebaseNode(
                node_id=file_id,
                node_type="file",
                name=rel_path,
                file_path=fp,
                line_start=1,
                line_end=parsed["lines"],
            )
            file_node.properties = {
                "classes": len(parsed["classes"]),
                "functions": len(parsed["functions"]),
                "imports": len(parsed["imports"]),
                "complexity": parsed["complexity"],
            }
            file_node.complexity_score = parsed["complexity"]
            with self._lock:
                self._graph_nodes[file_id] = file_node
            nodes_added += 1

            # Class nodes
            for cls in parsed["classes"]:
                cls_id = f"class:{rel_path}:{cls['name']}"
                cls_node = CodebaseNode(
                    node_id=cls_id,
                    node_type="class",
                    name=cls["name"],
                    file_path=fp,
                    line_start=cls["line"],
                )
                cls_node.properties = {
                    "methods": len(cls["methods"]),
                    "bases": cls["bases"],
                    "decorators": cls["decorators"],
                }
                with self._lock:
                    self._graph_nodes[cls_id] = cls_node
                    # Edge: file contains class
                    file_node.dependents.add(cls_id)
                    cls_node.dependencies.add(file_id)
                nodes_added += 1
                edges_added += 1

                # Method nodes
                for method in cls["methods"]:
                    method_id = f"method:{rel_path}:{cls['name']}:{method['name']}"
                    method_node = CodebaseNode(
                        node_id=method_id,
                        node_type="method",
                        name=f"{cls['name']}.{method['name']}",
                        file_path=fp,
                        line_start=method["line"],
                    )
                    method_node.properties = {
                        "args": method["args"],
                        "is_async": method["is_async"],
                    }
                    with self._lock:
                        self._graph_nodes[method_id] = method_node
                        cls_node.dependents.add(method_id)
                        method_node.dependencies.add(cls_id)
                    nodes_added += 1
                    edges_added += 1

            # Function nodes
            for func in parsed["functions"]:
                func_id = f"func:{rel_path}:{func['name']}"
                func_node = CodebaseNode(
                    node_id=func_id,
                    node_type="function",
                    name=func["name"],
                    file_path=fp,
                    line_start=func["line"],
                )
                func_node.properties = {
                    "args": func["args"],
                    "is_async": func["is_async"],
                    "decorators": func["decorators"],
                }
                with self._lock:
                    self._graph_nodes[func_id] = func_node
                    file_node.dependents.add(func_id)
                    func_node.dependencies.add(file_id)
                nodes_added += 1
                edges_added += 1

            # Import edges
            for imp in parsed["imports"]:
                import_module = imp.get("from", imp["module"])
                # Try to find the imported module in our graph
                for existing_id in self._graph_nodes:
                    if existing_id.startswith("file:") and import_module.replace(".", "/") in existing_id:
                        with self._lock:
                            file_node.dependencies.add(existing_id)
                            self._graph_nodes[existing_id].dependents.add(file_id)
                        edges_added += 1
                        break

        with self._lock:
            self._save()

        return {
            "nodes_added": nodes_added,
            "edges_added": edges_added,
            "total_nodes": len(self._graph_nodes),
            "files_parsed": len(file_paths),
        }

    # ── Chunk Memory (Expert Pattern Recognition) ───────────────────────

    def learn_chunk(self, pattern_type: str, name: str, description: str,
                    code_template: str = "", language: str = "python",
                    tags: List[str] = None) -> str:
        """Learn a new code pattern chunk."""
        chunk_id = f"chunk_{uuid.uuid4().hex[:8]}"
        signature = self._extract_signature(code_template) if code_template else name

        chunk = CodeChunk(
            chunk_id=chunk_id,
            pattern_type=pattern_type,
            name=name,
            signature=signature,
            description=description,
            code_template=code_template,
            language=language,
            tags=tags or [],
        )

        with self._lock:
            self._chunks[chunk_id] = chunk
            self._save()

        return chunk_id

    def find_matching_chunks(self, code_snippet: str = "", pattern_type: str = "",
                             tags: List[str] = None, top_k: int = 5) -> List[dict]:
        """
        Find code chunks matching the given criteria.
        Uses structural similarity, not just keyword matching.
        """
        with self._lock:
            candidates = []
            for chunk in self._chunks.values():
                score = 0.0

                # Pattern type match
                if pattern_type and chunk.pattern_type.startswith(pattern_type):
                    score += 0.4

                # Tag overlap
                if tags:
                    overlap = set(tags) & set(chunk.tags)
                    if overlap:
                        score += 0.3 * len(overlap) / max(len(tags), 1)

                # Structural similarity (if code provided)
                if code_snippet:
                    sig = self._extract_signature(code_snippet)
                    sim = self._signature_similarity(sig, chunk.signature)
                    score += 0.3 * sim

                # Boost by success rate and usage
                score += 0.1 * chunk.success_rate
                score += 0.05 * min(chunk.use_count / 10, 1.0)

                if score > 0.1:
                    candidates.append({
                        "chunk_id": chunk.chunk_id,
                        "pattern_type": chunk.pattern_type,
                        "name": chunk.name,
                        "description": chunk.description,
                        "code_template": chunk.code_template,
                        "success_rate": chunk.success_rate,
                        "use_count": chunk.use_count,
                        "score": round(score, 3),
                    })

            candidates.sort(key=lambda x: x["score"], reverse=True)
            return candidates[:top_k]

    def record_chunk_use(self, chunk_id: str, success: bool):
        """Record that a chunk was used and whether it worked."""
        with self._lock:
            chunk = self._chunks.get(chunk_id)
            if chunk:
                chunk.record_use(success)
                self._save()

    def extract_patterns_from_code(self, code: str, language: str = "python") -> List[dict]:
        """
        Analyze code and identify which patterns it uses.
        Like an expert recognizing "oh, that's a factory pattern" instantly.
        """
        patterns_found = []
        code_lower = code.lower()

        # Quick pattern heuristics
        pattern_signals = {
            "creational.factory": ["create", "factory", "make_", "build_", "get_instance"],
            "creational.singleton": ["_instance", "__instance", "singleton", "get_instance"],
            "creational.builder": ["builder", "build()", ".build()", "step_by_step"],
            "structural.adapter": ["adapter", "wrap", "adapt", "interface"],
            "structural.decorator": ["decorator", "@wraps", "functools.wraps", "wrapper"],
            "structural.facade": ["facade", "simplified", "interface"],
            "behavioral.observer": ["observer", "subscribe", "notify", "listener", "on_event", "emit"],
            "behavioral.strategy": ["strategy", "algorithm", "context", "set_strategy"],
            "behavioral.command": ["command", "execute", "undo", "redo"],
            "behavioral.state": ["state", "transition", "change_state"],
            "architectural.mvc": ["model", "view", "controller"],
            "architectural.repository": ["repository", "find_by", "save", "delete"],
            "architectural.dependency_injection": ["inject", "provide", "container"],
            "error_handling.retry_backoff": ["retry", "backoff", "exponential", "max_retries"],
            "error_handling.circuit_breaker": ["circuit", "breaker", "open", "closed", "half_open"],
            "concurrency_pattern.async_generator": ["async def", "yield", "async for"],
        }

        for pattern_name, signals in pattern_signals.items():
            matches = sum(1 for s in signals if s in code_lower)
            if matches >= 2:
                confidence = min(1.0, matches / max(len(signals), 1) * 1.5)
                patterns_found.append({
                    "pattern": pattern_name,
                    "confidence": round(confidence, 2),
                    "signals_matched": [s for s in signals if s in code_lower],
                })

        patterns_found.sort(key=lambda x: x["confidence"], reverse=True)
        return patterns_found

    # ── Complexity Analysis ─────────────────────────────────────────────

    def analyze_complexity(self, code: str, language: str = "python") -> dict:
        """
        Multi-dimensional complexity analysis:
        - Cyclomatic complexity (branching)
        - Cognitive complexity (nesting depth)
        - Lines of code
        - Parameter count
        - Coupling (dependencies)
        """
        if language != "python":
            return {"error": "Only Python analysis currently supported"}

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {"error": f"Syntax error: {e}"}

        lines = code.splitlines()
        loc = len([l for l in lines if l.strip() and not l.strip().startswith("#")])

        cyclomatic = self._calc_complexity(tree)
        max_nesting = self._max_nesting_depth(tree)
        max_params = self._max_params(tree)
        class_count = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
        func_count = sum(1 for n in ast.walk(tree)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))

        # Cognitive complexity score
        cognitive = cyclomatic + max_nesting * 2 + max(0, max_params - 3) * 1.5

        # Rating
        if cognitive < 5:
            rating = "simple"
        elif cognitive < 15:
            rating = "moderate"
        elif cognitive < 30:
            rating = "complex"
        else:
            rating = "very_complex"

        return {
            "cyclomatic": cyclomatic,
            "cognitive": round(cognitive, 1),
            "max_nesting": max_nesting,
            "max_params": max_params,
            "loc": loc,
            "classes": class_count,
            "functions": func_count,
            "rating": rating,
            "suggestions": self._complexity_suggestions(cyclomatic, max_nesting, max_params),
        }

    # ── Semantic Search ─────────────────────────────────────────────────

    def search_codebase(self, query: str, project_dir: str = "",
                        search_type: str = "all") -> List[dict]:
        """
        Search the codebase graph for nodes matching the query.
        search_type: all, file, class, function, method
        """
        query_lower = query.lower()
        results = []

        with self._lock:
            for node_id, node in self._graph_nodes.items():
                if search_type != "all" and not node_id.startswith(search_type):
                    continue

                # Name match
                name_score = 0.0
                if query_lower in node.name.lower():
                    name_score = 0.8
                elif any(word in node.name.lower() for word in query_lower.split()):
                    name_score = 0.5

                # Property match
                prop_score = 0.0
                for key, val in node.properties.items():
                    if isinstance(val, str) and query_lower in val.lower():
                        prop_score = 0.3
                    elif isinstance(val, list):
                        for item in val:
                            if isinstance(item, str) and query_lower in item.lower():
                                prop_score = 0.3
                                break

                total_score = name_score + prop_score
                if total_score > 0.2:
                    results.append({
                        "node_id": node_id,
                        "type": node.node_type,
                        "name": node.name,
                        "file_path": node.file_path,
                        "line": node.line_start,
                        "dependencies": len(node.dependencies),
                        "dependents": len(node.dependents),
                        "complexity": node.complexity_score,
                        "score": round(total_score, 3),
                    })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:20]

    # ── Graph Queries ───────────────────────────────────────────────────

    def get_file_dependencies(self, file_path: str) -> dict:
        """Get all dependencies and dependents for a file."""
        file_id = f"file:{file_path}"
        with self._lock:
            node = self._graph_nodes.get(file_id)
            if not node:
                return {"error": f"File not in graph: {file_path}"}

            deps = [self._graph_nodes[d] for d in node.dependencies if d in self._graph_nodes]
            dependents = [self._graph_nodes[d] for d in node.dependents if d in self._graph_nodes]

            return {
                "file": file_path,
                "depends_on": [{"name": d.name, "type": d.node_type} for d in deps],
                "depended_by": [{"name": d.name, "type": d.node_type} for d in dependents],
                "total_deps": len(deps),
                "total_dependents": len(dependents),
            }

    def get_impact_analysis(self, file_path: str) -> dict:
        """
        Impact analysis: what would break if this file changes?
        Traces the dependency chain to find all affected files.
        """
        file_id = f"file:{file_path}"
        visited = set()
        affected = []

        def _trace(node_id: str, depth: int):
            if node_id in visited or depth > 5:
                return
            visited.add(node_id)
            node = self._graph_nodes.get(node_id)
            if not node:
                return
            if depth > 0:  # Don't include the original file
                affected.append({
                    "node": node.name,
                    "type": node.node_type,
                    "depth": depth,
                    "file": node.file_path,
                })
            for dep_id in node.dependents:
                _trace(dep_id, depth + 1)

        with self._lock:
            _trace(file_id, 0)

        return {
            "source": file_path,
            "affected_count": len(affected),
            "affected": affected[:30],
            "max_depth": max((a["depth"] for a in affected), default=0),
        }

    def get_graph_summary(self) -> dict:
        """Get summary statistics of the codebase graph."""
        with self._lock:
            type_counts = defaultdict(int)
            total_complexity = 0.0
            for node in self._graph_nodes.values():
                type_counts[node.node_type] += 1
                total_complexity += node.complexity_score

            return {
                "total_nodes": len(self._graph_nodes),
                "by_type": dict(type_counts),
                "total_chunks": len(self._chunks),
                "avg_complexity": round(total_complexity / max(len(self._graph_nodes), 1), 2),
            }

    # ── Internal Helpers ────────────────────────────────────────────────

    def _extract_signature(self, code: str) -> str:
        """Extract a structural signature from code for similarity matching."""
        if not code:
            return ""
        # Remove comments, strings, whitespace — keep structure
        lines = []
        for line in code.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Remove inline comments
            if "#" in stripped:
                stripped = stripped[:stripped.index("#")].strip()
            if stripped:
                lines.append(stripped)
        return "\n".join(lines[:20])  # First 20 structural lines

    def _signature_similarity(self, sig1: str, sig2: str) -> float:
        """Compute structural similarity between two code signatures."""
        if not sig1 or not sig2:
            return 0.0
        words1 = set(sig1.split())
        words2 = set(sig2.split())
        if not words1 or not words2:
            return 0.0
        overlap = words1 & words2
        return len(overlap) / max(len(words1), len(words2))

    def _calc_complexity(self, tree: ast.AST) -> int:
        """Calculate cyclomatic complexity from AST."""
        complexity = 1  # Base complexity
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(node, ast.ExceptHandler):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
            elif isinstance(node, ast.Assert):
                complexity += 1
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                complexity += len(node.generators)
        return complexity

    def _max_nesting_depth(self, tree: ast.AST, depth: int = 0) -> int:
        """Find maximum nesting depth."""
        max_depth = depth
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.AsyncFor,
                                ast.With, ast.AsyncWith, ast.Try,
                                ast.ExceptHandler)):
                child_depth = self._max_nesting_depth(node, depth + 1)
                max_depth = max(max_depth, child_depth)
            else:
                child_depth = self._max_nesting_depth(node, depth)
                max_depth = max(max_depth, child_depth)
        return max_depth

    def _max_params(self, tree: ast.AST) -> int:
        """Find maximum parameter count in any function."""
        max_params = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                params = len(node.args.args)
                max_params = max(max_params, params)
        return max_params

    def _get_name(self, node: ast.AST) -> str:
        """Extract name from AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._get_name(node.func)
        return "?"

    def _get_decorator_name(self, node: ast.AST) -> str:
        """Extract decorator name."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return "?"

    def _get_return_annotation(self, node: ast.FunctionDef) -> Optional[str]:
        """Get return type annotation if present."""
        if node.returns:
            if isinstance(node.returns, ast.Name):
                return node.returns.id
            elif isinstance(node.returns, ast.Constant):
                return str(node.returns.value)
        return None

    def _complexity_suggestions(self, cyclomatic: int, nesting: int, params: int) -> List[str]:
        """Generate suggestions for reducing complexity."""
        suggestions = []
        if cyclomatic > 10:
            suggestions.append("High cyclomatic complexity — consider extracting methods or using strategy pattern")
        if nesting > 4:
            suggestions.append("Deep nesting — use early returns, guard clauses, or extract helper functions")
        if params > 5:
            suggestions.append("Too many parameters — use a config object or dataclass")
        if cyclomatic > 20:
            suggestions.append("Very complex — consider breaking into smaller, focused classes")
        return suggestions

    # ── Prompt Formatting ───────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 2000) -> str:
        """Format code intelligence state for system prompt injection."""
        parts = ["[CODE INTELLIGENCE — Semantic code understanding]"]

        summary = self.get_graph_summary()
        parts.append(
            f"Codebase: {summary['total_nodes']} nodes | "
            f"{summary.get('by_type', {}).get('file', 0)} files | "
            f"{summary.get('by_type', {}).get('class', 0)} classes | "
            f"{summary.get('by_type', {}).get('function', 0)} functions"
        )

        if self._chunks:
            parts.append(f"Pattern library: {len(self._chunks)} chunks learned")

            # Top patterns by usage
            top_chunks = sorted(
                self._chunks.values(),
                key=lambda c: c.use_count * c.success_rate,
                reverse=True,
            )[:3]
            if top_chunks:
                pattern_str = ", ".join(f"{c.name}({c.success_rate:.0%})" for c in top_chunks)
                parts.append(f"Top patterns: {pattern_str}")

        result = "\n".join(parts)
        return result[:max_chars]


# ── Singleton ───────────────────────────────────────────────────────────

_code_intelligence = None
_ci_lock = threading.Lock()


def get_code_intelligence() -> CodeIntelligence:
    """Get singleton CodeIntelligence instance."""
    global _code_intelligence
    if _code_intelligence is None:
        with _ci_lock:
            if _code_intelligence is None:
                _code_intelligence = CodeIntelligence()
    return _code_intelligence