"""
AST Parser - Multi-language source code extraction for security analysis.

Extracts security-relevant nodes (functions, calls, assignments, imports,
classes) from Python and JavaScript/TypeScript source files.

Python: uses the built-in `ast` module for accurate parsing.
JavaScript/TypeScript: uses regex-based parsing (v1 approach).

Supports: .py, .js, .ts, .jsx, .tsx, .sol
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Cross-platform path normalization
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from actions.resilience import normalize_path


@dataclass
class CodeNode:
    """A simplified node extracted from source code."""
    node_id: str
    node_type: str  # "function_def", "call", "assignment", "import", "class_def", "param", "return"
    value: str
    file_path: str = ""
    line: int = 0
    col: int = 0
    parent_function: str = ""
    parent_class: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "value": self.value,
            "file_path": self.file_path,
            "line": self.line,
            "col": self.col,
            "parent_function": self.parent_function,
            "parent_class": self.parent_class,
            "extra": self.extra,
        }


SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".sol"}


def parse_file(file_path: str) -> list[CodeNode]:
    """
    Parse a source file and extract security-relevant nodes.

    Args:
        file_path: Path to the source file.

    Returns:
        List of extracted CodeNode objects.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If file extension is not supported.
    """
    path, _ = normalize_path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported extension '{ext}'. Supported: {SUPPORTED_EXTENSIONS}")

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()

    if ext == ".py":
        return _parse_python(source, file_path)
    else:
        return _parse_javascript(source, file_path, ext)


def parse_directory(
    directory: str,
    extensions: set[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> list[CodeNode]:
    """
    Recursively parse all supported files in a directory.

    Args:
        directory: Root directory to scan.
        extensions: Override default extensions filter.
        exclude_patterns: Glob patterns to exclude (e.g., ["node_modules", ".git"]).

    Returns:
        Combined list of CodeNode objects from all files.
    """
    if extensions is None:
        extensions = SUPPORTED_EXTENSIONS
    if exclude_patterns is None:
        exclude_patterns = ["node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"]

    all_nodes: list[CodeNode] = []
    root, _ = normalize_path(directory)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded directories
        dirnames[:] = [
            d for d in dirnames
            if d not in exclude_patterns and not any(
                d.startswith(p.rstrip("*")) for p in exclude_patterns if "*" in p
            )
        ]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() in extensions:
                try:
                    nodes = parse_file(str(fpath))
                    all_nodes.extend(nodes)
                except (SyntaxError, UnicodeDecodeError) as e:
                    # skip files that can't be parsed
                    print(f"[ast_parser] Skipping {fpath}: {e}")
    return all_nodes


# ═══════════════════════════════════════════════════════════════════
#  PYTHON PARSER (using built-in ast module)
# ═══════════════════════════════════════════════════════════════════

class _PythonExtractor(ast.NodeVisitor):
    """Extract security-relevant nodes from Python AST."""

    def __init__(self, source: str, file_path: str) -> None:
        self.source = source
        self.file_path = file_path
        self.nodes: list[CodeNode] = []
        self._func_stack: list[str] = []
        self._class_stack: list[str] = []
        self._counter = 0

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}_{self._counter}"

    def _current_func(self) -> str:
        return self._func_stack[-1] if self._func_stack else "<module>"

    def _current_class(self) -> str:
        return self._class_stack[-1] if self._class_stack else ""

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        name = node.name
        self._func_stack.append(name)
        self.nodes.append(CodeNode(
            node_id=self._next_id("func"),
            node_type="function_def",
            value=name,
            file_path=self.file_path,
            line=node.lineno,
            col=node.col_offset,
            parent_function=self._current_func() if len(self._func_stack) > 1 else "<module>",
            parent_class=self._current_class(),
            extra={
                "args": [a.arg for a in node.args.args],
                "decorators": [_get_decorator_name(d) for d in node.decorator_list],
            },
        ))
        # extract parameters as separate nodes
        for arg in node.args.args:
            self.nodes.append(CodeNode(
                node_id=self._next_id("param"),
                node_type="param",
                value=arg.arg,
                file_path=self.file_path,
                line=node.lineno,
                col=node.col_offset,
                parent_function=name,
                parent_class=self._current_class(),
            ))
        self.generic_visit(node)
        self._func_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        # treat async functions the same way
        name = node.name
        self._func_stack.append(name)
        self.nodes.append(CodeNode(
            node_id=self._next_id("func"),
            node_type="function_def",
            value=name,
            file_path=self.file_path,
            line=node.lineno,
            col=node.col_offset,
            parent_function=self._current_func() if len(self._func_stack) > 1 else "<module>",
            parent_class=self._current_class(),
            extra={
                "args": [a.arg for a in node.args.args],
                "async": True,
                "decorators": [_get_decorator_name(d) for d in node.decorator_list],
            },
        ))
        for arg in node.args.args:
            self.nodes.append(CodeNode(
                node_id=self._next_id("param"),
                node_type="param",
                value=arg.arg,
                file_path=self.file_path,
                line=node.lineno,
                col=node.col_offset,
                parent_function=name,
                parent_class=self._current_class(),
            ))
        self.generic_visit(node)
        self._func_stack.pop()

    visit_AsyncFunctionDef = visit_AsyncFunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_stack.append(node.name)
        self.nodes.append(CodeNode(
            node_id=self._next_id("class"),
            node_type="class_def",
            value=node.name,
            file_path=self.file_path,
            line=node.lineno,
            col=node.col_offset,
            parent_function=self._current_func(),
            extra={
                "bases": [_ast_to_name(b) for b in node.bases],
                "decorators": [_get_decorator_name(d) for d in node.decorator_list],
            },
        ))
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        func_name = _ast_to_name(node.func)
        self.nodes.append(CodeNode(
            node_id=self._next_id("call"),
            node_type="call",
            value=func_name,
            file_path=self.file_path,
            line=node.lineno,
            col=node.col_offset,
            parent_function=self._current_func(),
            parent_class=self._current_class(),
            extra={
                "num_args": len(node.args),
                "keyword_args": {kw.arg: _ast_to_name(kw.value) for kw in node.keywords if kw.arg},
            },
        ))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            target_name = _ast_to_name(target)
            self.nodes.append(CodeNode(
                node_id=self._next_id("assign"),
                node_type="assignment",
                value=target_name,
                file_path=self.file_path,
                line=node.lineno,
                col=node.col_offset,
                parent_function=self._current_func(),
                parent_class=self._current_class(),
                extra={
                    "source_expr": _ast_to_name(node.value),
                },
            ))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.target:
            target_name = _ast_to_name(node.target)
            self.nodes.append(CodeNode(
                node_id=self._next_id("assign"),
                node_type="assignment",
                value=target_name,
                file_path=self.file_path,
                line=node.lineno,
                col=node.col_offset,
                parent_function=self._current_func(),
                parent_class=self._current_class(),
                extra={
                    "annotation": _ast_to_name(node.annotation) if node.annotation else "",
                    "source_expr": _ast_to_name(node.value) if node.value else "",
                },
            ))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.nodes.append(CodeNode(
                node_id=self._next_id("import"),
                node_type="import",
                value=alias.name,
                file_path=self.file_path,
                line=node.lineno,
                col=node.col_offset,
                parent_function=self._current_func(),
                extra={"asname": alias.asname or ""},
            ))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        for alias in node.names:
            full_name = f"{module}.{alias.name}" if module else alias.name
            self.nodes.append(CodeNode(
                node_id=self._next_id("import"),
                node_type="import",
                value=full_name,
                file_path=self.file_path,
                line=node.lineno,
                col=node.col_offset,
                parent_function=self._current_func(),
                extra={"module": module, "asname": alias.asname or ""},
            ))

    def visit_Return(self, node: ast.Return) -> None:
        if node.value:
            self.nodes.append(CodeNode(
                node_id=self._next_id("return"),
                node_type="return",
                value=_ast_to_name(node.value),
                file_path=self.file_path,
                line=node.lineno,
                col=node.col_offset,
                parent_function=self._current_func(),
                parent_class=self._current_class(),
            ))
        self.generic_visit(node)


def _parse_python(source: str, file_path: str) -> list[CodeNode]:
    """Parse Python source code using the ast module."""
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        raise SyntaxError(f"Python syntax error in {file_path}: {e}") from e
    extractor = _PythonExtractor(source, file_path)
    extractor.visit(tree)
    return extractor.nodes


def _ast_to_name(node: ast.AST) -> str:
    """Convert an AST node to a string name representation."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_ast_to_name(node.value)}.{node.attr}"
    elif isinstance(node, ast.Call):
        return _ast_to_name(node.func)
    elif isinstance(node, ast.Constant):
        return repr(node.value)
    elif isinstance(node, ast.JoinedStr):
        return "f-string"
    elif isinstance(node, ast.List):
        return "[...]"
    elif isinstance(node, ast.Dict):
        return "{...}"
    elif isinstance(node, ast.Tuple):
        return "(...)"
    elif isinstance(node, ast.Set):
        return "{...}"
    elif isinstance(node, ast.Subscript):
        return f"{_ast_to_name(node.value)}[...]"
    elif isinstance(node, ast.BinOp):
        return f"{_ast_to_name(node.left)} {_ast_to_name(node.op)} {_ast_to_name(node.right)}"
    elif isinstance(node, ast.UnaryOp):
        return f"{_ast_to_name(node.op)}{_ast_to_name(node.operand)}"
    elif isinstance(node, ast.BoolOp):
        return "bool_op"
    elif isinstance(node, ast.Compare):
        return "compare"
    elif isinstance(node, ast.Lambda):
        return "lambda"
    elif isinstance(node, ast.ListComp):
        return "list_comp"
    elif isinstance(node, ast.DictComp):
        return "dict_comp"
    elif isinstance(node, ast.SetComp):
        return "set_comp"
    elif isinstance(node, ast.GeneratorExp):
        return "gen_exp"
    elif isinstance(node, ast.Starred):
        return f"*{_ast_to_name(node.value)}"
    elif isinstance(node, ast.keyword):
        return f"{node.arg}={_ast_to_name(node.value)}"
    else:
        return type(node).__name__.lower()


def _get_decorator_name(node: ast.AST) -> str:
    """Extract decorator name from AST node."""
    return _ast_to_name(node)


# ═══════════════════════════════════════════════════════════════════
#  JAVASCRIPT/TYPESCRIPT PARSER (regex-based)
# ═══════════════════════════════════════════════════════════════════

# Regex patterns for JS/TS extraction
_JS_PATTERNS = {
    "function_def": re.compile(
        r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)|"
        r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>|"
        r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function\s*\(([^)]*)\)",
        re.MULTILINE,
    ),
    "arrow_fn_short": re.compile(
        r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(\w+)\s*=>",
        re.MULTILINE,
    ),
    "class_def": re.compile(
        r"(?:export\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+[\w,\s]+)?\s*\{",
        re.MULTILINE,
    ),
    "call": re.compile(
        r"(\w+(?:\.\w+)*)\s*\(",
        re.MULTILINE,
    ),
    "method_def": re.compile(
        r"(?:async\s+)?(\w+)\s*\(([^)]*)\)\s*\{",
        re.MULTILINE,
    ),
    "import_default": re.compile(
        r"import\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]",
        re.MULTILINE,
    ),
    "import_named": re.compile(
        r"import\s+\{([^}]+)\}\s+from\s+['\"]([^'\"]+)['\"]",
        re.MULTILINE,
    ),
    "import_namespace": re.compile(
        r"import\s+\*\s+as\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]",
        re.MULTILINE,
    ),
    "require": re.compile(
        r"(?:const|let|var)\s+(\w+)\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
        re.MULTILINE,
    ),
    "assignment": re.compile(
        r"(?:const|let|var)\s+(\w+)\s*=\s*(.+?)(?:;|$)",
        re.MULTILINE,
    ),
    "property_assign": re.compile(
        r"(\w+(?:\.\w+)*)\s*=\s*(.+?)(?:;|$)",
        re.MULTILINE,
    ),
    "return_stmt": re.compile(
        r"\breturn\s+(.+?)(?:;|$)",
        re.MULTILINE,
    ),
}


def _parse_javascript(source: str, file_path: str, ext: str) -> list[CodeNode]:
    """Parse JavaScript/TypeScript source code using regex patterns."""
    nodes: list[CodeNode] = []
    counter = 0
    lines = source.split("\n")

    def next_id(prefix: str) -> str:
        nonlocal counter
        counter += 1
        return f"{prefix}_{counter}"

    def line_col_for(match: re.Match[str]) -> tuple[int, int]:
        """Get line and column for a regex match."""
        pos = match.start()
        line_num = source[:pos].count("\n") + 1
        last_nl = source.rfind("\n", 0, pos)
        col = pos - last_nl - 1 if last_nl >= 0 else pos
        return line_num, col

    # track current function scope by line ranges
    func_ranges: list[tuple[int, int, str]] = []  # (start_line, end_line, name)
    class_ranges: list[tuple[int, int, str]] = []

    # ── class definitions ────────────────────────────────────
    for m in _JS_PATTERNS["class_def"].finditer(source):
        name = m.group(1)
        base = m.group(2) or ""
        line, col = line_col_for(m)
        nodes.append(CodeNode(
            node_id=next_id("class"),
            node_type="class_def",
            value=name,
            file_path=file_path,
            line=line,
            col=col,
            extra={"base": base},
        ))
        # estimate class body range
        brace_start = source.find("{", m.end() - 1)
        if brace_start >= 0:
            end = _find_matching_brace(source, brace_start)
            end_line = source[:end].count("\n") + 1 if end >= 0 else line + 50
            class_ranges.append((line, end_line, name))

    # ── function definitions ─────────────────────────────────
    for m in _JS_PATTERNS["function_def"].finditer(source):
        name = m.group(1) or m.group(3) or m.group(5) or ""
        params_str = m.group(2) or m.group(4) or m.group(6) or ""
        if not name:
            continue
        line, col = line_col_for(m)
        parent_class = _find_enclosing(class_ranges, line)
        nodes.append(CodeNode(
            node_id=next_id("func"),
            node_type="function_def",
            value=name,
            file_path=file_path,
            line=line,
            col=col,
            parent_class=parent_class,
            extra={
                "params": [p.strip().split(":")[0].strip() for p in params_str.split(",") if p.strip()],
                "async": "async" in (m.group(0)[:m.group(0).index(name)] if name in m.group(0) else ""),
            },
        ))
        # track range for parent resolution
        brace_start = source.find("{", m.end() - 1)
        if brace_start >= 0:
            end = _find_matching_brace(source, brace_start)
            end_line = source[:end].count("\n") + 1 if end >= 0 else line + 20
            func_ranges.append((line, end_line, name))

    # short arrow functions: const x = arg =>
    for m in _JS_PATTERNS["arrow_fn_short"].finditer(source):
        name = m.group(1)
        param = m.group(2)
        line, col = line_col_for(m)
        nodes.append(CodeNode(
            node_id=next_id("func"),
            node_type="function_def",
            value=name,
            file_path=file_path,
            line=line,
            col=col,
            extra={"params": [param], "arrow": True},
        ))

    # ── imports ──────────────────────────────────────────────
    for m in _JS_PATTERNS["import_default"].finditer(source):
        line, col = line_col_for(m)
        nodes.append(CodeNode(
            node_id=next_id("import"),
            node_type="import",
            value=m.group(2),
            file_path=file_path,
            line=line,
            col=col,
            extra={"local_name": m.group(1), "kind": "default"},
        ))

    for m in _JS_PATTERNS["import_named"].finditer(source):
        line, col = line_col_for(m)
        names = [n.strip() for n in m.group(1).split(",")]
        for imported_name in names:
            # handle "as" aliases
            parts = imported_name.split(" as ")
            nodes.append(CodeNode(
                node_id=next_id("import"),
                node_type="import",
                value=m.group(2),
                file_path=file_path,
                line=line,
                col=col,
                extra={"imported_name": parts[0].strip(), "local_name": parts[-1].strip(), "kind": "named"},
            ))

    for m in _JS_PATTERNS["import_namespace"].finditer(source):
        line, col = line_col_for(m)
        nodes.append(CodeNode(
            node_id=next_id("import"),
            node_type="import",
            value=m.group(2),
            file_path=file_path,
            line=line,
            col=col,
            extra={"local_name": m.group(1), "kind": "namespace"},
        ))

    for m in _JS_PATTERNS["require"].finditer(source):
        line, col = line_col_for(m)
        nodes.append(CodeNode(
            node_id=next_id("import"),
            node_type="import",
            value=m.group(2),
            file_path=file_path,
            line=line,
            col=col,
            extra={"local_name": m.group(1), "kind": "require"},
        ))

    # ── function calls ───────────────────────────────────────
    for m in _JS_PATTERNS["call"].finditer(source):
        func_name = m.group(1)
        # skip keywords
        if func_name in ("if", "for", "while", "switch", "catch", "typeof", "new", "delete", "void"):
            continue
        line, col = line_col_for(m)
        parent_func = _find_enclosing(func_ranges, line)
        nodes.append(CodeNode(
            node_id=next_id("call"),
            node_type="call",
            value=func_name,
            file_path=file_path,
            line=line,
            col=col,
            parent_function=parent_func,
            parent_class=_find_enclosing(class_ranges, line),
        ))

    # ── variable assignments ─────────────────────────────────
    for m in _JS_PATTERNS["assignment"].finditer(source):
        name = m.group(1)
        expr = m.group(2).strip()
        line, col = line_col_for(m)
        parent_func = _find_enclosing(func_ranges, line)
        nodes.append(CodeNode(
            node_id=next_id("assign"),
            node_type="assignment",
            value=name,
            file_path=file_path,
            line=line,
            col=col,
            parent_function=parent_func,
            parent_class=_find_enclosing(class_ranges, line),
            extra={"source_expr": expr},
        ))

    # ── return statements ────────────────────────────────────
    for m in _JS_PATTERNS["return_stmt"].finditer(source):
        expr = m.group(1).strip()
        line, col = line_col_for(m)
        parent_func = _find_enclosing(func_ranges, line)
        nodes.append(CodeNode(
            node_id=next_id("return"),
            node_type="return",
            value=expr,
            file_path=file_path,
            line=line,
            col=col,
            parent_function=parent_func,
        ))

    return nodes


def _find_matching_brace(source: str, open_pos: int) -> int:
    """Find the matching closing brace for an opening brace."""
    depth = 0
    i = open_pos
    in_string = False
    string_char = ""
    in_template = False
    in_comment = False
    in_line_comment = False

    while i < len(source):
        ch = source[i]

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_comment:
            if ch == "*" and i + 1 < len(source) and source[i + 1] == "/":
                in_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == string_char:
                in_string = False
            i += 1
            continue

        if in_template:
            if ch == "\\":
                i += 2
                continue
            if ch == "`":
                in_template = False
            i += 1
            continue

        if ch == "/" and i + 1 < len(source):
            if source[i + 1] == "/":
                in_line_comment = True
                i += 2
                continue
            if source[i + 1] == "*":
                in_comment = True
                i += 2
                continue

        if ch in ("'", '"'):
            in_string = True
            string_char = ch
            i += 1
            continue

        if ch == "`":
            in_template = True
            i += 1
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i

        i += 1

    return -1


def _find_enclosing(ranges: list[tuple[int, int, str]], line: int) -> str:
    """Find the enclosing range (function/class) for a given line number."""
    best: str = ""
    best_start = -1
    for start, end, name in ranges:
        if start <= line <= end and start > best_start:
            best = name
            best_start = start
    return best


# ═══════════════════════════════════════════════════════════════════
#  CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def get_functions(nodes: list[CodeNode]) -> list[CodeNode]:
    """Filter nodes to only function definitions."""
    return [n for n in nodes if n.node_type == "function_def"]


def get_calls(nodes: list[CodeNode]) -> list[CodeNode]:
    """Filter nodes to only function calls."""
    return [n for n in nodes if n.node_type == "call"]


def get_assignments(nodes: list[CodeNode]) -> list[CodeNode]:
    """Filter nodes to only variable assignments."""
    return [n for n in nodes if n.node_type == "assignment"]


def get_imports(nodes: list[CodeNode]) -> list[CodeNode]:
    """Filter nodes to only import statements."""
    return [n for n in nodes if n.node_type == "import"]


def get_classes(nodes: list[CodeNode]) -> list[CodeNode]:
    """Filter nodes to only class definitions."""
    return [n for n in nodes if n.node_type == "class_def"]


def nodes_in_function(nodes: list[CodeNode], func_name: str) -> list[CodeNode]:
    """Get all nodes within a specific function scope."""
    return [n for n in nodes if n.parent_function == func_name]


def nodes_at_line(nodes: list[CodeNode], line: int) -> list[CodeNode]:
    """Get all nodes at a specific line number."""
    return [n for n in nodes if n.line == line]


def detect_language(file_path: str) -> str:
    """Detect language from file extension."""
    ext = Path(file_path).suffix.lower()
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".sol": "solidity",
    }
    return mapping.get(ext, "unknown")
