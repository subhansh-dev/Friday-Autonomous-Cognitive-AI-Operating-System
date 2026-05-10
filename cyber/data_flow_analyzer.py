"""
data_flow_analyzer.py — Source Code Data Flow Analysis Engine
Traces data from user-input sources to dangerous sinks.
Uses ast_parser for extraction and flow_graph for path tracing.
"""
import hashlib
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict

from .ast_parser import parse_file, parse_directory, CodeNode
from .flow_graph import FlowGraph, FlowNode, NodeType, EdgeType
from .source_sink_db import get_sources, get_sinks, SecurityEndpoint as SourceSinkEntry
from actions.resilience import normalize_path

logger = logging.getLogger("friday.data_flow")

SKIP_PATTERNS = [".git", "node_modules", "__pycache__", ".venv", "venv",
                 ".mypy_cache", "dist", "build"]
CODE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".sol"}


@dataclass
class DataFlowPath:
    """A traced path from source to sink."""
    source_name: str
    source_file: str
    source_line: int
    sink_name: str
    sink_file: str
    sink_line: int
    vuln_class: str
    intermediate_nodes: List[str] = field(default_factory=list)
    sanitized: bool = False
    sanitization_detail: str = ""
    confidence: float = 0.5

    def to_dict(self) -> dict:
        return {
            "source": f"{self.source_name} at {self.source_file}:{self.source_line}",
            "sink": f"{self.sink_name} at {self.sink_file}:{self.sink_line}",
            "vuln_class": self.vuln_class,
            "intermediate": self.intermediate_nodes,
            "sanitized": self.sanitized,
            "sanitization_detail": self.sanitization_detail,
            "confidence": self.confidence,
        }


@dataclass
class DataFlowResult:
    """Results of data flow analysis."""
    paths: List[DataFlowPath] = field(default_factory=list)
    files_analyzed: int = 0
    sources_found: int = 0
    sinks_found: int = 0
    duration_ms: float = 0

    def to_findings(self) -> List[dict]:
        """Convert paths to findings for the findings bus."""
        findings = []
        for path in self.paths:
            if path.sanitized:
                continue
            raw = f"{path.source_file}:{path.sink_file}:{path.vuln_class}:{path.source_line}:{path.sink_line}"
            fid = hashlib.sha256(raw.encode()).hexdigest()[:16]
            findings.append({
                "agent": "DATA_FLOW",
                "vuln_class": path.vuln_class,
                "finding_id": fid,
                "file_path": path.sink_file,
                "confidence": "plausible" if path.confidence < 0.7 else "confirmed",
                "cvss_score": 7.5,
                "summary": (f"Data flow: {path.source_name} → {path.sink_name} "
                           f"({path.source_file}:{path.source_line} → "
                           f"{path.sink_file}:{path.sink_line})"),
                "detail": (f"Source: {path.source_name}, Sink: {path.sink_name}, "
                          f"Intermediate: {', '.join(path.intermediate_nodes[:5])}, "
                          f"Sanitized: {path.sanitized}"),
                "target": path.sink_file,
                "data_flow_path": path.to_dict(),
            })
        return findings


def _node_name(node: CodeNode) -> str:
    """Extract a display name from a CodeNode."""
    return node.node_id.split("::")[-1] if "::" in node.node_id else node.value[:60]


def _matches_pattern(text: str, src: SourceSinkEntry) -> bool:
    """Check if text matches a source/sink pattern."""
    import re
    return bool(re.search(src.pattern, text, re.IGNORECASE))


def _classify_vuln(sink_name: str) -> str:
    """Classify vulnerability type based on sink name."""
    name = sink_name.lower()
    if any(w in name for w in ["execute", "cursor", "query", "sql"]):
        return "SQL Injection"
    if any(w in name for w in ["system", "popen", "subprocess", "exec", "eval"]):
        return "Command Injection"
    if any(w in name for w in ["render_template", "html", "innerhtml", "write"]):
        return "XSS"
    if any(w in name for w in ["redirect", "send_file", "open"]):
        return "Path Traversal"
    if any(w in name for w in ["urlopen", "requests.get", "fetch"]):
        return "SSRF"
    if any(w in name for w in ["pickle", "yaml.load", "deserialize"]):
        return "Unsafe Deserialization"
    return "Unknown"


def _check_sanitization(path_node_ids: List[str], nodes_by_id: Dict[str, CodeNode]) -> tuple:
    """Check if data is sanitized along the path."""
    sanitizers = [
        "escape", "sanitize", "validate", "parameterize",
        "bleach", "markupsafe", "escape_html", "html.escape",
        "quote", "shlex.quote", "prepared_statement",
    ]
    for nid in path_node_ids:
        node = nodes_by_id.get(nid)
        if not node:
            continue
        text = (node.value or "").lower()
        for sanitizer in sanitizers:
            if sanitizer in text:
                return True, f"Sanitized by {sanitizer} at {node.file_path}:{node.line}"
    return False, ""


def _calc_confidence(path_length: int, sanitized: bool) -> float:
    """Calculate confidence that this is a real vulnerability."""
    conf = 0.5
    if path_length <= 2:
        conf += 0.2  # Direct flow = more confident
    if sanitized:
        conf -= 0.3
    if path_length > 5:
        conf -= 0.1  # Long paths are less certain
    return max(0.1, min(0.95, conf))


class DataFlowAnalyzer:
    """
    Analyzes codebases for data flow vulnerabilities.

    Usage:
        analyzer = DataFlowAnalyzer()
        result = analyzer.analyze("/path/to/project")
        for finding in result.to_findings():
            print(finding["summary"])
    """

    def __init__(self):
        self.graph = FlowGraph()

    def analyze(self, target: str) -> DataFlowResult:
        """Analyze a target directory for data flow vulnerabilities."""
        start = time.time()
        result = DataFlowResult()
        target_path, _path_err = normalize_path(target)

        if not target_path.exists():
            logger.warning(f"Target not found: {target}")
            return result

        # Phase 1: Parse all source files using ast_parser
        all_nodes: List[CodeNode] = []
        for f in target_path.rglob("*"):
            if not f.is_file():
                continue
            if any(skip in str(f) for skip in SKIP_PATTERNS):
                continue
            if f.suffix.lower() not in CODE_EXTENSIONS:
                continue

            try:
                nodes = parse_file(str(f))
                all_nodes.extend(nodes)
                result.files_analyzed += 1
            except Exception as e:
                logger.debug(f"Failed to parse {f}: {e}")

        logger.info(f"Parsed {result.files_analyzed} files, {len(all_nodes)} nodes")

        # Build lookup by node_id
        nodes_by_id: Dict[str, CodeNode] = {n.node_id: n for n in all_nodes}

        # Phase 2: Build flow graph from CodeNodes
        self.graph = FlowGraph()
        self._build_graph(all_nodes, nodes_by_id)

        # Phase 3: Identify sources and sinks
        source_defs = get_sources("python") + get_sources("javascript")
        sink_defs = get_sinks("python") + get_sinks("javascript")

        source_nodes = []
        sink_nodes = []

        for node in all_nodes:
            text = node.value or ""
            for src in source_defs:
                if _matches_pattern(text, src):
                    # Register as SOURCE in flow graph
                    self.graph.add_node(
                        node_id=node.node_id,
                        node_type=NodeType.SOURCE,
                        name=_node_name(node),
                        file_path=node.file_path,
                        line=node.line,
                    )
                    source_nodes.append(node)
                    break
            for sink in sink_defs:
                if _matches_pattern(text, sink):
                    # Register as SINK in flow graph
                    self.graph.add_node(
                        node_id=node.node_id,
                        node_type=NodeType.SINK,
                        name=_node_name(node),
                        file_path=node.file_path,
                        line=node.line,
                    )
                    sink_nodes.append(node)
                    break

        result.sources_found = len(source_nodes)
        result.sinks_found = len(sink_nodes)
        logger.info(f"Found {len(source_nodes)} sources, {len(sink_nodes)} sinks")

        # Phase 4: Trace paths from sources to sinks
        for source in source_nodes:
            for sink in sink_nodes:
                paths = self.graph.trace_source_to_sink(source.node_id, sink.node_id)
                for path_node_ids in paths:
                    vuln_class = _classify_vuln(_node_name(sink))
                    sanitized, san_detail = _check_sanitization(path_node_ids, nodes_by_id)
                    confidence = _calc_confidence(len(path_node_ids), sanitized)

                    flow_path = DataFlowPath(
                        source_name=_node_name(source),
                        source_file=source.file_path,
                        source_line=source.line,
                        sink_name=_node_name(sink),
                        sink_file=sink.file_path,
                        sink_line=sink.line,
                        vuln_class=vuln_class,
                        intermediate_nodes=[nodes_by_id[nid].value[:40]
                                           for nid in path_node_ids[1:-1]
                                           if nid in nodes_by_id],
                        sanitized=sanitized,
                        sanitization_detail=san_detail,
                        confidence=confidence,
                    )
                    result.paths.append(flow_path)

        result.duration_ms = (time.time() - start) * 1000
        logger.info(f"Data flow analysis: {len(result.paths)} paths in {result.duration_ms:.0f}ms")
        return result

    def _build_graph(self, nodes: List[CodeNode], nodes_by_id: Dict[str, CodeNode]):
        """Build the flow graph from parsed CodeNodes."""
        # Track variable assignments for flow tracking
        var_assignments: Dict[str, List[CodeNode]] = {}

        for node in nodes:
            # Register node in flow graph
            node_type_map = {
                "function_def": NodeType.CALL,
                "call": NodeType.CALL,
                "assignment": NodeType.VARIABLE,
                "import": NodeType.VARIABLE,
                "class_def": NodeType.VARIABLE,
                "return": NodeType.VARIABLE,
            }
            ft = node_type_map.get(node.node_type, NodeType.VARIABLE)

            self.graph.add_node(
                node_id=node.node_id,
                node_type=ft,
                name=_node_name(node),
                file_path=node.file_path,
                line=node.line,
            )

            # Track assignments for variable flow
            if node.node_type == "assignment":
                var_name = _node_name(node)
                var_assignments.setdefault(var_name, []).append(node)

        # Build edges: assignment flow (RHS → LHS)
        for node in nodes:
            if node.node_type == "assignment":
                # Check both the variable name AND the source expression
                value = node.value or ""
                source_expr = node.extra.get("source_expr", "")
                search_text = f"{value} {source_expr}"
                # Find nodes referenced in the RHS
                for other in nodes:
                    if other is node:
                        continue
                    if other.file_path != node.file_path:
                        continue
                    other_name = _node_name(other)
                    if other_name and other_name in search_text and len(other_name) > 2:
                        self.graph.add_edge(other.node_id, node.node_id, EdgeType.ASSIGNS)

            # Call argument flow: variables used as arguments flow into the call
            if node.node_type == "call":
                value = node.value or ""
                for other in nodes:
                    if other is node:
                        continue
                    if other.file_path != node.file_path:
                        continue
                    other_name = _node_name(other)
                    # Check if the variable appears near this call (within 3 lines)
                    if (other_name and len(other_name) > 2 and
                        other.node_type in ("assignment", "param", "variable") and
                        abs(other.line - node.line) <= 3):
                        self.graph.add_edge(other.node_id, node.node_id, EdgeType.CALLS)
                    # Also check if the name appears in the call value itself
                    elif other_name and other_name in value and len(other_name) > 2:
                        self.graph.add_edge(other.node_id, node.node_id, EdgeType.CALLS)

            # Return flow
            if node.node_type == "return":
                value = node.value or ""
                for other in nodes:
                    if other is node:
                        continue
                    if other.file_path != node.file_path:
                        continue
                    other_name = _node_name(other)
                    if other_name and other_name in value and len(other_name) > 2:
                        self.graph.add_edge(other.node_id, node.node_id, EdgeType.RETURNS)
