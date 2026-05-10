#!/usr/bin/env python3
"""
code_reasoning_engine.py — FRIDAY Deep Code Reasoning Engine
=============================================================

Opus-level coding intelligence through:
1. Chain-of-thought code reasoning (think before writing)
2. Multi-file architectural awareness
3. Type inference and contract propagation
4. Design pattern selection and application
5. Iterative self-correction (write → test → fix loop)
6. Test generation and property-based verification
7. Cross-module dependency impact analysis

This is the "thinking" layer that sits above the existing pipeline.
The existing modules handle perception, planning, simulation, execution,
debugging, and reflection. This engine adds the REASONING that ties
them together at expert level.

Architecture:
  Goal → [Reason] → Architecture Decision → [Design] → Module Plan
       → [Write] → Code → [Test] → Tests → [Verify] → Fix Loop
       → [Integrate] → Cross-file Coherence → Final Output
"""

import ast
import json
import re
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

BRAIN_DIR = Path(__file__).parent.resolve()
REASONING_FILE = BRAIN_DIR / "code_reasoning_engine.json"
API_CONFIG_PATH = BRAIN_DIR.parent / "config" / "api_keys.json"
REASONING_MODEL = "gemini-2.5-flash"

# Self-correction limits
MAX_CORRECTION_ITERATIONS = 5
MAX_TEST_GENERATION_RETRIES = 3
CORRECTION_TIMEOUT = 120  # seconds per correction cycle


# ── Design Pattern Catalog ──────────────────────────────────────────────

DESIGN_PATTERNS = {
    "singleton": {
        "when": ["exactly one instance needed", "global access point", "shared resource"],
        "structure": "class with _instance, __new__, get_instance",
        "pros": ["controlled access", "reduced namespace pollution"],
        "cons": ["hidden dependencies", "hard to test", "SRP violation"],
        "testability": "low",
    },
    "factory": {
        "when": ["object creation logic complex", "multiple variants", "decouple creation"],
        "structure": "create_product(type) -> Product",
        "pros": ["loose coupling", "single responsibility", "open/closed"],
        "cons": ["more classes", "complexity for simple cases"],
        "testability": "high",
    },
    "strategy": {
        "when": ["multiple algorithms", "runtime selection", "avoid conditionals"],
        "structure": "Context(Strategy) with set_strategy()",
        "pros": ["open/closed", "runtime flexibility", "testable algorithms"],
        "cons": ["client must know strategies", "more objects"],
        "testability": "high",
    },
    "observer": {
        "when": ["event notification", "one-to-many dependency", "loose coupling"],
        "structure": "Subject.attach(Observer), notify()",
        "pros": ["loose coupling", "dynamic relationships"],
        "cons": ["memory leaks if not unsubscribed", "unexpected updates"],
        "testability": "medium",
    },
    "builder": {
        "when": ["complex object construction", "many optional params", "immutable objects"],
        "structure": "Builder.set_x().set_y().build()",
        "pros": ["readable construction", "immutable products", "step-by-step"],
        "cons": ["more code", "mutable builder state"],
        "testability": "high",
    },
    "decorator": {
        "when": ["extend behavior dynamically", "composable features", "SRP"],
        "structure": "wrap(Component) adding behavior",
        "pros": ["runtime composition", "single responsibility", "open/closed"],
        "cons": ["many small objects", "order matters"],
        "testability": "high",
    },
    "repository": {
        "when": ["data access abstraction", "testable data layer", "multiple data sources"],
        "structure": "Repository.find(id), save(entity), delete(id)",
        "pros": ["testable with mocks", "swappable persistence", "domain isolation"],
        "cons": ["abstraction leak", "extra layer"],
        "testability": "high",
    },
    "command": {
        "when": ["undo/redo", "queue operations", "macro recording"],
        "structure": "Command.execute(), undo()",
        "pros": ["undo/redo", "serialization", "queuing"],
        "cons": ["more classes", "complex state management"],
        "testability": "high",
    },
    "middleware": {
        "when": ["request processing pipeline", "cross-cutting concerns", "composable filters"],
        "structure": "Chain of handlers, each can pass or stop",
        "pros": ["composable", "separation of concerns", "reusable"],
        "cons": ["ordering matters", "debugging harder"],
        "testability": "high",
    },
    "event_sourcing": {
        "when": ["audit trail needed", "temporal queries", "complex state history"],
        "structure": "Store events, rebuild state by replaying",
        "pros": ["complete audit trail", "temporal queries", "debugging"],
        "cons": ["event schema evolution", "storage growth", "complexity"],
        "testability": "high",
    },
}


# ── Type Inference Engine ───────────────────────────────────────────────

class TypeInfo:
    """Inferred type information for a variable or expression."""

    def __init__(self, name: str, type_str: str, confidence: float = 0.5,
                 source: str = "inferred", constraints: List[str] = None):
        self.name = name
        self.type_str = type_str  # "int", "str", "List[int]", "Optional[Dict]", etc.
        self.confidence = confidence
        self.source = source  # "annotation", "inferred", "usage", "return"
        self.constraints = constraints or []

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type_str,
            "confidence": self.confidence,
            "source": self.source,
            "constraints": self.constraints,
        }


class TypeContext:
    """Type context for a scope (function, class, module)."""

    def __init__(self, scope_name: str):
        self.scope_name = scope_name
        self.variables: Dict[str, TypeInfo] = {}
        self.functions: Dict[str, Dict[str, TypeInfo]] = {}  # func_name -> {param: TypeInfo}
        self.return_types: Dict[str, TypeInfo] = {}

    def add_variable(self, name: str, type_info: TypeInfo):
        self.variables[name] = type_info

    def add_function(self, name: str, params: Dict[str, TypeInfo], return_type: TypeInfo):
        self.functions[name] = params
        self.return_types[name] = return_type

    def get_type(self, name: str) -> Optional[TypeInfo]:
        return self.variables.get(name)

    def to_dict(self) -> dict:
        return {
            "scope": self.scope_name,
            "variables": {k: v.to_dict() for k, v in self.variables.items()},
            "functions": {k: {p: t.to_dict() for p, t in params.items()}
                         for k, params in self.functions.items()},
            "return_types": {k: v.to_dict() for k, v in self.return_types.items()},
        }


def infer_types_from_ast(code: str) -> TypeContext:
    """
    Infer types from Python code using AST analysis.

    Extracts:
    - Type annotations (def foo(x: int) -> str)
    - Literal assignments (x = 42 → int)
    - Constructor calls (x = list() → List)
    - Collection literals (x = [] → List, x = {} → Dict)
    - Return statements
    """
    ctx = TypeContext("module")

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return ctx

    for node in ast.walk(tree):
        # Function definitions with annotations
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            params: Dict[str, TypeInfo] = {}
            for arg in node.args.args:
                if arg.annotation:
                    type_str = _annotation_to_str(arg.annotation)
                    params[arg.arg] = TypeInfo(arg.arg, type_str, 0.95, "annotation")
                else:
                    params[arg.arg] = TypeInfo(arg.arg, "Any", 0.3, "inferred")

            return_type = TypeInfo("return", "None", 0.5, "inferred")
            if node.returns:
                type_str = _annotation_to_str(node.returns)
                return_type = TypeInfo("return", type_str, 0.95, "annotation")

            ctx.add_function(node.name, params, return_type)

        # Variable assignments
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    type_info = _infer_from_value(node.value)
                    ctx.add_variable(target.id, type_info)

        # Annotated assignments (x: int = 5)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            type_str = _annotation_to_str(node.annotation)
            ctx.add_variable(node.target.id, TypeInfo(node.target.id, type_str, 0.95, "annotation"))

    return ctx


def _annotation_to_str(node: ast.AST) -> str:
    """Convert an AST annotation node to a type string."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Constant):
        return str(node.value)
    elif isinstance(node, ast.Attribute):
        return f"{_annotation_to_str(node.value)}.{node.attr}"
    elif isinstance(node, ast.Subscript):
        base = _annotation_to_str(node.value)
        slice_val = _annotation_to_str(node.slice)
        return f"{base}[{slice_val}]"
    elif isinstance(node, ast.Tuple):
        elements = [_annotation_to_str(e) for e in node.elts]
        return ", ".join(elements)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        # Python 3.10+ union: X | Y
        left = _annotation_to_str(node.left)
        right = _annotation_to_str(node.right)
        return f"{left} | {right}"
    return "Any"


def _infer_from_value(node: ast.AST) -> TypeInfo:
    """Infer type from a value expression."""
    if isinstance(node, ast.Constant):
        val = node.value
        if isinstance(val, bool):
            return TypeInfo("", "bool", 0.95, "literal")
        elif isinstance(val, int):
            return TypeInfo("", "int", 0.95, "literal")
        elif isinstance(val, float):
            return TypeInfo("", "float", 0.95, "literal")
        elif isinstance(val, str):
            return TypeInfo("", "str", 0.95, "literal")
        elif val is None:
            return TypeInfo("", "None", 0.95, "literal")
    elif isinstance(node, ast.List):
        if node.elts:
            elem_type = _infer_from_value(node.elts[0])
            return TypeInfo("", f"List[{elem_type.type_str}]", 0.8, "literal")
        return TypeInfo("", "List", 0.7, "literal")
    elif isinstance(node, ast.Dict):
        return TypeInfo("", "Dict", 0.7, "literal")
    elif isinstance(node, ast.Set):
        return TypeInfo("", "Set", 0.7, "literal")
    elif isinstance(node, ast.Tuple):
        return TypeInfo("", "Tuple", 0.7, "literal")
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            name = node.func.id
            type_map = {
                "int": "int", "float": "float", "str": "str",
                "bool": "bool", "list": "List", "dict": "Dict",
                "set": "Set", "tuple": "Tuple",
            }
            if name in type_map:
                return TypeInfo("", type_map[name], 0.9, "constructor")
            return TypeInfo("", name, 0.6, "constructor")
    elif isinstance(node, ast.ListComp):
        return TypeInfo("", "List", 0.7, "comprehension")
    elif isinstance(node, ast.DictComp):
        return TypeInfo("", "Dict", 0.7, "comprehension")

    return TypeInfo("", "Any", 0.3, "unknown")


# ── Contract Extraction ─────────────────────────────────────────────────

class CodeContract:
    """A pre/post condition or invariant extracted from code."""

    def __init__(self, contract_type: str, description: str, location: str,
                 confidence: float = 0.5, enforcement: str = "implicit"):
        self.contract_type = contract_type  # "precondition", "postcondition", "invariant"
        self.description = description
        self.location = location
        self.confidence = confidence
        self.enforcement = enforcement  # "assert", "type", "implicit", "docstring"

    def to_dict(self) -> dict:
        return {
            "type": self.contract_type,
            "description": self.description,
            "location": self.location,
            "confidence": self.confidence,
            "enforcement": self.enforcement,
        }


def extract_contracts(code: str) -> List[CodeContract]:
    """Extract pre/post conditions and invariants from code."""
    contracts: List[CodeContract] = []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return contracts

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_name = node.name

            # Check docstring for pre/post conditions
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                docstring = node.body[0].value.value
                contracts.extend(_extract_from_docstring(docstring, func_name))

            # Check for assert statements (explicit invariants)
            for child in ast.walk(node):
                if isinstance(child, ast.Assert):
                    if isinstance(child.test, ast.Constant):
                        desc = str(child.test.value)
                    else:
                        desc = ast.dump(child.test)[:100]
                    contracts.append(CodeContract(
                        "invariant",
                        desc,
                        f"{func_name}:line {child.lineno}",
                        0.9,
                        "assert",
                    ))

            # Type annotations as contracts
            for arg in node.args.args:
                if arg.annotation:
                    type_str = _annotation_to_str(arg.annotation)
                    contracts.append(CodeContract(
                        "precondition",
                        f"{arg.arg} must be {type_str}",
                        f"{func_name}:{arg.arg}",
                        0.85,
                        "type",
                    ))

            if node.returns:
                ret_type = _annotation_to_str(node.returns)
                contracts.append(CodeContract(
                    "postcondition",
                    f"{func_name} returns {ret_type}",
                    f"{func_name}:return",
                    0.85,
                    "type",
                ))

    return contracts


def _extract_from_docstring(docstring: str, func_name: str) -> List[CodeContract]:
    """Extract contracts from docstring text."""
    contracts = []

    # Look for Args/Returns/Raises sections
    lines = docstring.split("\n")

    in_args = False
    in_returns = False
    in_raises = False

    for line in lines:
        stripped = line.strip().lower()

        if stripped.startswith("args:") or stripped.startswith("parameters:"):
            in_args = True
            in_returns = False
            in_raises = False
            continue
        elif stripped.startswith("returns:") or stripped.startswith("return:"):
            in_args = False
            in_returns = True
            in_raises = False
            continue
        elif stripped.startswith("raises:") or stripped.startswith("raise:"):
            in_args = False
            in_returns = False
            in_raises = True
            continue
        elif stripped and not stripped.startswith("-") and not stripped.startswith(" "):
            if not any(stripped.startswith(k) for k in ["args", "returns", "raises", "note", "example"]):
                in_args = False
                in_returns = False
                in_raises = False

        if in_args and ":" in line:
            param_name = line.split(":")[0].strip().split("(")[0].strip()
            if param_name:
                contracts.append(CodeContract(
                    "precondition",
                    f"{param_name} documented in docstring",
                    f"{func_name}:{param_name}",
                    0.6,
                    "docstring",
                ))

        if in_returns and line.strip():
            contracts.append(CodeContract(
                "postcondition",
                f"return value documented: {line.strip()[:80]}",
                f"{func_name}:return",
                0.6,
                "docstring",
            ))

    return contracts


# ── Multi-File Context ──────────────────────────────────────────────────

class FileContext:
    """Context for a single file in a multi-file operation."""

    def __init__(self, path: str, content: str, role: str = "unknown"):
        self.path = path
        self.content = content
        self.role = role  # "main", "test", "config", "util", "model", "view", "controller"
        self.exports: List[str] = []  # What this file provides
        self.imports: List[str] = []  # What this file needs
        self.type_ctx: Optional[TypeContext] = None
        self.contracts: List[CodeContract] = []

    def analyze(self):
        """Analyze file for exports, imports, types, contracts."""
        try:
            tree = ast.parse(self.content)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    self.exports.append(node.name)
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    self.exports.append(node.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.imports.append(node.module)

        self.type_ctx = infer_types_from_ast(self.content)
        self.contracts = extract_contracts(self.content)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "role": self.role,
            "exports": self.exports,
            "imports": self.imports,
            "type_count": len(self.type_ctx.variables) if self.type_ctx else 0,
            "contract_count": len(self.contracts),
        }


class MultiFileContext:
    """Context for understanding code across multiple files."""

    def __init__(self):
        self.files: Dict[str, FileContext] = {}
        self.dependency_graph: Dict[str, Set[str]] = {}  # file -> set of files it imports
        self.reverse_deps: Dict[str, Set[str]] = {}  # file -> set of files that import it

    def add_file(self, path: str, content: str, role: str = "unknown") -> FileContext:
        """Add a file and analyze it."""
        fc = FileContext(path, content, role)
        fc.analyze()
        self.files[path] = fc

        # Build dependency graph
        self.dependency_graph[path] = set()
        for imp in fc.imports:
            # Try to resolve to a file in our context
            for other_path in self.files:
                if other_path != path and (imp in other_path or other_path.endswith(imp.replace(".", "/") + ".py")):
                    self.dependency_graph[path].add(other_path)
                    if other_path not in self.reverse_deps:
                        self.reverse_deps[other_path] = set()
                    self.reverse_deps[other_path].add(path)

        return fc

    def get_impact(self, file_path: str) -> List[str]:
        """Get all files affected by changes to file_path."""
        affected: Set[str] = set()
        queue = [file_path]

        while queue:
            current = queue.pop(0)
            if current in affected:
                continue
            affected.add(current)
            for dep in self.reverse_deps.get(current, set()):
                if dep not in affected:
                    queue.append(dep)

        return sorted(affected)

    def get_cross_file_types(self) -> Dict[str, Dict[str, str]]:
        """Get type information across all files."""
        all_types: Dict[str, Dict[str, str]] = {}
        for path, fc in self.files.items():
            if fc.type_ctx:
                types = {}
                for name, ti in fc.type_ctx.variables.items():
                    types[name] = ti.type_str
                for func_name, params in fc.type_ctx.functions.items():
                    for param_name, ti in params.items():
                        types[f"{func_name}.{param_name}"] = ti.type_str
                all_types[path] = types
        return all_types

    def to_dict(self) -> dict:
        return {
            "files": {k: v.to_dict() for k, v in self.files.items()},
            "dependency_graph": {k: list(v) for k, v in self.dependency_graph.items()},
        }


# ── LLM Helper ──────────────────────────────────────────────────────────

def _get_api_key() -> str:
    try:
        data = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        return data.get("gemini_api_key", data.get("GOOGLE_API_KEY", ""))
    except Exception:
        return ""


def _llm_generate(prompt: str, system: str = "", max_tokens: int = 4096) -> str:
    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=_get_api_key())
        config = genai_types.GenerateContentConfig(
            system_instruction=system if system else None,
            max_output_tokens=max_tokens,
        )
        response = client.models.generate_content(
            model=REASONING_MODEL,
            contents=prompt,
            config=config,
        )
        return response.text.strip()
    except Exception as exc:
        return f"LLM Error: {exc}"


# ── Code Reasoning Engine ───────────────────────────────────────────────

class CodeReasoningEngine:
    """
    Deep code reasoning engine for Opus-level coding intelligence.

    Provides:
    1. Chain-of-thought reasoning before code generation
    2. Design pattern selection based on requirements
    3. Type inference and contract propagation
    4. Multi-file architectural reasoning
    5. Iterative self-correction (write → test → fix)
    6. Test generation for self-validation
    7. Cross-module dependency impact analysis
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data = self._empty_store()
        self._load()
        print("[CodeReasoningEngine] Initialized — deep reasoning online")

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": datetime.now().isoformat(),
                "last_update": datetime.now().isoformat(),
                "total_reasoning_sessions": 0,
                "total_corrections": 0,
                "successful_corrections": 0,
            },
            "reasoning_sessions": [],
            "pattern_selections": [],
            "correction_history": [],
        }

    def _load(self):
        try:
            if REASONING_FILE.exists():
                raw = REASONING_FILE.read_text(encoding="utf-8")
                data = json.loads(raw)
                empty = self._empty_store()
                for key in empty:
                    if key not in data:
                        data[key] = empty[key]
                self._data = data
        except (json.JSONDecodeError, IOError) as exc:
            print(f"[CodeReasoningEngine] Load error: {exc}")
            self._data = self._empty_store()

    def _save(self):
        with self._lock:
            try:
                self._data["meta"]["last_update"] = datetime.now().isoformat()
                BRAIN_DIR.mkdir(parents=True, exist_ok=True)
                REASONING_FILE.write_text(
                    json.dumps(self._data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except IOError as exc:
                print(f"[CodeReasoningEngine] Save error: {exc}")

    # ── Chain-of-Thought Reasoning ──────────────────────────────────────

    def reason_about_task(self, goal: str, context: str = "",
                          language: str = "python") -> dict:
        """
        Deep chain-of-thought reasoning about a coding task before writing code.

        Returns structured reasoning with:
        - Problem decomposition
        - Architecture decisions
        - Key design choices
        - Potential pitfalls
        - Recommended approach
        """
        system = """You are a world-class software architect reasoning through a coding task.
Think step by step. Be thorough but concise.

Return ONLY valid JSON:
{
  "problem_understanding": "what the task really requires (not just surface description)",
  "decomposition": ["sub-problem 1", "sub-problem 2"],
  "architecture_decisions": [
    {"decision": "what to decide", "options": ["opt A", "opt B"], "choice": "opt A", "reasoning": "why"}
  ],
  "key_design_choices": [
    {"choice": "data structure / pattern / approach", "reasoning": "why this is best"}
  ],
  "potential_pitfalls": ["pitfall 1", "pitfall 2"],
  "recommended_approach": "step by step plan",
  "complexity_estimate": {"time": "O(n)", "space": "O(1)", "difficulty": "easy|medium|hard"},
  "test_strategy": "how to verify correctness"
}"""

        prompt = f"""Task: {goal}
Language: {language}
{f'Context: {context[:2000]}' if context else ''}

Think through this task carefully before writing any code.
What are the key decisions, potential issues, and the best approach?"""

        result = _llm_generate(prompt, system=system)

        try:
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                reasoning = json.loads(json_match.group())
                self._record_session(goal, reasoning)
                return reasoning
        except json.JSONDecodeError:
            pass

        return {
            "problem_understanding": goal,
            "recommended_approach": result[:500] if result else "Could not reason about task",
            "complexity_estimate": {"difficulty": "medium"},
        }

    # ── Design Pattern Selection ────────────────────────────────────────

    def select_design_pattern(self, requirements: str, constraints: List[str] = None,
                               language: str = "python") -> dict:
        """
        Select the best design pattern for given requirements.

        Analyzes requirements against the pattern catalog and recommends
        the most appropriate pattern with implementation guidance.
        """
        constraints = constraints or []

        # Score each pattern against requirements
        scored_patterns = []
        req_lower = requirements.lower()

        for pattern_name, pattern_info in DESIGN_PATTERNS.items():
            score = 0.0

            # Check "when" conditions
            for condition in pattern_info["when"]:
                if condition.lower() in req_lower:
                    score += 0.3

            # Check constraints
            for constraint in constraints:
                constraint_lower = constraint.lower()
                if "testable" in constraint_lower and pattern_info["testability"] == "high":
                    score += 0.2
                if "simple" in constraint_lower and len(pattern_info["cons"]) <= 1:
                    score += 0.1
                if "flexible" in constraint_lower and "runtime" in str(pattern_info["pros"]):
                    score += 0.15

            # Bonus for high testability
            if pattern_info["testability"] == "high":
                score += 0.1

            if score > 0.1:
                scored_patterns.append({
                    "pattern": pattern_name,
                    "score": round(score, 3),
                    "when": pattern_info["when"],
                    "structure": pattern_info["structure"],
                    "pros": pattern_info["pros"],
                    "cons": pattern_info["cons"],
                    "testability": pattern_info["testability"],
                })

        scored_patterns.sort(key=lambda x: x["score"], reverse=True)

        # Record selection
        with self._lock:
            self._data["pattern_selections"].append({
                "requirements": requirements[:200],
                "selected": scored_patterns[0]["pattern"] if scored_patterns else "none",
                "score": scored_patterns[0]["score"] if scored_patterns else 0,
                "timestamp": datetime.now().isoformat(),
            })
            self._save()

        return {
            "recommended": scored_patterns[0] if scored_patterns else None,
            "alternatives": scored_patterns[1:3] if len(scored_patterns) > 1 else [],
            "reasoning": f"Selected based on requirements match and constraint satisfaction",
        }

    # ── Iterative Self-Correction ───────────────────────────────────────

    def generate_with_correction(self, goal: str, language: str = "python",
                                  context: str = "",
                                  max_iterations: int = MAX_CORRECTION_ITERATIONS) -> dict:
        """
        Generate code with iterative self-correction.

        Loop:
        1. Generate code
        2. Generate tests for the code
        3. Run tests (mentally via simulation)
        4. If tests fail, analyze failures and fix
        5. Repeat until tests pass or max iterations

        Returns:
        dict with: code, tests, iterations, corrections, final_status
        """
        session = {
            "goal": goal,
            "language": language,
            "iterations": [],
            "final_code": "",
            "final_tests": "",
            "status": "started",
            "corrections": 0,
        }

        # Step 0: Reason about the task
        reasoning = self.reason_about_task(goal, context, language)

        # Step 1: Generate initial code
        code = self._generate_initial_code(goal, language, context, reasoning)
        session["final_code"] = code

        for iteration in range(max_iterations):
            iter_data = {
                "iteration": iteration,
                "code_length": len(code),
                "tests_generated": False,
                "tests_passed": False,
                "corrections": [],
            }

            # Step 2: Generate tests
            tests = self._generate_tests(code, goal, language)
            iter_data["tests_generated"] = bool(tests)

            # Step 3: Simulate test execution
            test_result = self._simulate_tests(code, tests, language)
            iter_data["tests_passed"] = test_result["all_passed"]

            if test_result["all_passed"]:
                iter_data["status"] = "passed"
                session["iterations"].append(iter_data)
                session["status"] = "success"
                break

            # Step 4: Analyze failures and correct
            corrections = self._correct_code(code, tests, test_result, language)
            if corrections:
                code = corrections["corrected_code"]
                session["final_code"] = code
                iter_data["corrections"] = corrections["changes"]
                session["corrections"] += 1

            session["iterations"].append(iter_data)

            if iteration == max_iterations - 1:
                session["status"] = "max_iterations"

        session["final_tests"] = tests if 'tests' in dir() else ""

        # Record
        with self._lock:
            self._data["meta"]["total_reasoning_sessions"] += 1
            self._data["meta"]["total_corrections"] += session["corrections"]
            if session["status"] == "success":
                self._data["meta"]["successful_corrections"] += session["corrections"]
            self._save()

        return session

    def _generate_initial_code(self, goal: str, language: str, context: str,
                                reasoning: dict) -> str:
        """Generate initial code with reasoning context."""
        system = f"""You are an expert {language} programmer. Write clean, production-ready code.
Requirements:
- Full type hints
- Comprehensive docstrings
- Error handling
- Follow PEP8
- Consider edge cases

Think step by step, then write the code. Return ONLY the code, no explanation."""

        approach = reasoning.get("recommended_approach", "")
        pitfalls = reasoning.get("potential_pitfalls", [])

        prompt = f"""Task: {goal}
{f'Context: {context[:1500]}' if context else ''}
{f'Recommended approach: {approach}' if approach else ''}
{f'Watch out for: {", ".join(pitfalls[:3])}' if pitfalls else ''}

Write the complete, production-ready code:"""

        result = _llm_generate(prompt, system=system)

        # Extract code from markdown blocks
        code = _extract_code(result, language)
        return code

    def _generate_tests(self, code: str, goal: str, language: str) -> str:
        """Generate tests for the given code."""
        system = f"""You are a test engineer. Write comprehensive {language} tests using pytest.
Test:
- Happy path
- Edge cases (empty input, None, boundary values)
- Error conditions (invalid input, type errors)
- Performance (large inputs if relevant)

Return ONLY the test code, no explanation."""

        # Extract function/class names for targeted testing
        test_targets = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"):
                        test_targets.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    test_targets.append(node.name)
        except SyntaxError:
            pass

        prompt = f"""Code to test:
```{language}
{code[:4000]}
```

Goal: {goal}
Key functions/classes: {', '.join(test_targets[:10])}

Write comprehensive tests:"""

        result = _llm_generate(prompt, system=system)
        return _extract_code(result, language)

    def _simulate_tests(self, code: str, tests: str, language: str) -> dict:
        """Mentally simulate running tests against code."""
        system = """You are a test execution simulator. Analyze the code and tests,
predict which tests would pass and which would fail.

Return ONLY valid JSON:
{
  "all_passed": true/false,
  "results": [
    {"test": "test_name", "passed": true/false, "reason": "why"}
  ],
  "coverage_estimate": 0.0-1.0,
  "issues_found": ["issue 1"]
}"""

        prompt = f"""Code:
```{language}
{code[:3000]}
```

Tests:
```{language}
{tests[:3000]}
```

Simulate running these tests. Which pass, which fail, and why?"""

        result = _llm_generate(prompt, system=system)

        try:
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        return {
            "all_passed": False,
            "results": [],
            "coverage_estimate": 0.5,
            "issues_found": ["Could not simulate tests"],
        }

    def _correct_code(self, code: str, tests: str, test_result: dict,
                       language: str) -> Optional[dict]:
        """Correct code based on test failures."""
        failed_tests = [
            r for r in test_result.get("results", [])
            if not r.get("passed", True)
        ]

        if not failed_tests:
            return None

        system = f"""You are debugging {language} code. Given the failing tests,
fix the code to make all tests pass. Return ONLY the corrected code."""

        failures_desc = "\n".join(
            f"- {t.get('test', '?')}: {t.get('reason', 'unknown')}"
            for t in failed_tests
        )

        prompt = f"""Original code:
```{language}
{code}
```

Failing tests:
{failures_desc}

Issues: {', '.join(test_result.get('issues_found', []))}

Fix the code to pass all tests:"""

        result = _llm_generate(prompt, system=system)
        corrected = _extract_code(result, language)

        if corrected and corrected != code:
            changes = []
            old_lines = set(code.splitlines())
            new_lines = set(corrected.splitlines())
            added = new_lines - old_lines
            removed = old_lines - new_lines
            if added:
                changes.append(f"+{len(added)} lines")
            if removed:
                changes.append(f"-{len(removed)} lines")

            return {
                "corrected_code": corrected,
                "changes": changes,
            }

        return None

    # ── Multi-File Reasoning ────────────────────────────────────────────

    def reason_about_changes(self, target_file: str, change_description: str,
                              project_files: Dict[str, str]) -> dict:
        """
        Reason about the impact of changes across multiple files.

        Analyzes:
        - Which files are affected
        - What types need updating
        - What contracts are broken
        - What tests need updating
        """
        # Build multi-file context
        mfc = MultiFileContext()
        for path, content in project_files.items():
            role = self._infer_file_role(path, content)
            mfc.add_file(path, content, role)

        # Get impact analysis
        affected = mfc.get_impact(target_file)
        cross_types = mfc.get_cross_file_types()

        # Get contracts for affected files
        broken_contracts = []
        for fpath in affected:
            fc = mfc.files.get(fpath)
            if fc:
                for contract in fc.contracts:
                    broken_contracts.append({
                        "file": fpath,
                        "contract": contract.to_dict(),
                    })

        system = """Analyze the impact of code changes across a project.
Return ONLY valid JSON:
{
  "affected_files": ["file1.py", "file2.py"],
  "required_changes": [
    {"file": "file.py", "change": "what to update", "reason": "why"}
  ],
  "type_updates_needed": ["update type hints in X"],
  "contracts_at_risk": ["precondition in Y"],
  "tests_to_update": ["test_X"],
  "risk_assessment": "low|medium|high",
  "recommended_order": ["file1.py", "file2.py"]
}"""

        files_summary = "\n".join(
            f"- {path}: role={fc.role}, exports={fc.exports[:5]}, "
            f"imports={fc.imports[:5]}"
            for path, fc in mfc.files.items()
        )

        prompt = f"""Project files:
{files_summary}

Target file: {target_file}
Change: {change_description}

Files affected by this change: {affected}
Broken contracts: {json.dumps(broken_contracts[:5])}

Analyze the full impact:"""

        result = _llm_generate(prompt, system=system)

        try:
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                analysis["multi_file_context"] = mfc.to_dict()
                return analysis
        except json.JSONDecodeError:
            pass

        return {
            "affected_files": affected,
            "risk_assessment": "medium",
            "recommended_order": affected,
        }

    def _infer_file_role(self, path: str, content: str) -> str:
        """Infer the role of a file from its path and content."""
        path_lower = path.lower()
        content_lower = content[:500].lower()

        if "test" in path_lower or "spec" in path_lower:
            return "test"
        elif "config" in path_lower or "settings" in path_lower:
            return "config"
        elif "model" in path_lower or "schema" in path_lower:
            return "model"
        elif "view" in path_lower or "template" in path_lower:
            return "view"
        elif "controller" in path_lower or "handler" in path_lower:
            return "controller"
        elif "util" in path_lower or "helper" in path_lower:
            return "util"
        elif "middleware" in path_lower:
            return "middleware"
        elif "api" in path_lower or "route" in path_lower:
            return "api"
        elif "__main__" in content_lower or "if __name__" in content_lower:
            return "main"
        elif "class " in content_lower and "def " in content_lower:
            return "module"
        return "unknown"

    # ── Type-Aware Code Generation ──────────────────────────────────────

    def generate_with_types(self, goal: str, existing_types: Dict[str, str] = None,
                             language: str = "python") -> dict:
        """
        Generate code with strong type awareness.

        Uses existing type information from the codebase to ensure
        new code is type-compatible with existing code.
        """
        existing_types = existing_types or {}

        type_context = ""
        if existing_types:
            type_context = "Existing types in codebase:\n"
            for name, type_str in list(existing_types.items())[:20]:
                type_context += f"  {name}: {type_str}\n"

        system = f"""You are an expert {language} programmer who writes fully typed code.
Requirements:
- Full type hints on ALL functions (params + return)
- Use typing module for complex types (Optional, Union, List, Dict, etc.)
- Validate input types at function boundaries
- Use dataclasses or TypedDict for structured data
- Consistent with existing codebase types

Return ONLY the code, no explanation."""

        prompt = f"""Task: {goal}
{type_context}

Write fully typed, production-ready code:"""

        result = _llm_generate(prompt, system=system)
        code = _extract_code(result, language)

        # Verify types are present
        type_score = self._score_type_coverage(code)

        return {
            "code": code,
            "type_coverage": type_score,
            "types_used": self._extract_used_types(code),
        }

    def _score_type_coverage(self, code: str) -> float:
        """Score how well-typed the code is (0.0 to 1.0)."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return 0.0

        total_functions = 0
        typed_functions = 0
        total_params = 0
        typed_params = 0

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_") and node.name != "__init__":
                    continue
                total_functions += 1
                if node.returns:
                    typed_functions += 1

                for arg in node.args.args:
                    if arg.arg == "self":
                        continue
                    total_params += 1
                    if arg.annotation:
                        typed_params += 1

        if total_functions == 0 and total_params == 0:
            return 0.0

        func_score = typed_functions / max(total_functions, 1)
        param_score = typed_params / max(total_params, 1)
        return round((func_score + param_score) / 2, 3)

    def _extract_used_types(self, code: str) -> List[str]:
        """Extract type annotations used in the code."""
        types = set()
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.returns:
                        types.add(_annotation_to_str(node.returns))
                    for arg in node.args.args:
                        if arg.annotation:
                            types.add(_annotation_to_str(arg.annotation))
                elif isinstance(node, ast.AnnAssign) and node.annotation:
                    types.add(_annotation_to_str(node.annotation))
        except SyntaxError:
            pass
        return sorted(types)

    # ── Session Recording ───────────────────────────────────────────────

    def _record_session(self, goal: str, reasoning: dict):
        """Record a reasoning session."""
        with self._lock:
            self._data["reasoning_sessions"].append({
                "goal": goal[:200],
                "reasoning_keys": list(reasoning.keys()),
                "timestamp": datetime.now().isoformat(),
            })
            # Keep last 100
            self._data["reasoning_sessions"] = self._data["reasoning_sessions"][-100:]
            self._save()

    # ── Stats & Prompt ──────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get reasoning engine statistics."""
        with self._lock:
            meta = self._data["meta"]
            correction_rate = (
                meta["successful_corrections"] /
                max(meta["total_corrections"], 1)
            )
            return {
                "total_sessions": meta["total_reasoning_sessions"],
                "total_corrections": meta["total_corrections"],
                "successful_corrections": meta["successful_corrections"],
                "correction_success_rate": round(correction_rate, 3),
                "pattern_selections": len(self._data["pattern_selections"]),
                "design_patterns_available": len(DESIGN_PATTERNS),
            }

    def format_for_prompt(self, max_chars: int = 600) -> str:
        """Format reasoning engine state for system prompt."""
        stats = self.get_stats()
        parts = [
            "[CODE REASONING ENGINE — Deep thinking]",
            f"Sessions: {stats['total_sessions']} | "
            f"Corrections: {stats['successful_corrections']}/{stats['total_corrections']} "
            f"({stats['correction_success_rate']:.0%})",
            f"Design patterns: {stats['design_patterns_available']} available",
            f"Pattern selections: {stats['pattern_selections']}",
        ]

        # Recent pattern selections
        recent = self._data["pattern_selections"][-3:]
        if recent:
            items = [s.get("selected", "?") for s in recent]
            parts.append(f"Recent patterns: {', '.join(items)}")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars].rsplit("\n", 1)[0] + "\n[...]"
        return result


# ── Helpers ──────────────────────────────────────────────────────────────

def _extract_code(text: str, language: str = "python") -> str:
    """Extract code from markdown code blocks."""
    if not text:
        return ""

    # Try to find code blocks
    patterns = [
        rf'```{language}\n(.*?)```',
        r'```\n(.*?)```',
        r'```(.*?)```',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            # Return the longest match (most complete code)
            return max(matches, key=len).strip()

    # No code blocks — return as-is if it looks like code
    if any(keyword in text for keyword in ["def ", "class ", "import ", "return "]):
        return text.strip()

    return text.strip()


# ── Singleton ────────────────────────────────────────────────────────────

_reasoning_engine: Optional[CodeReasoningEngine] = None
_reasoning_lock = threading.Lock()


def get_code_reasoning_engine() -> CodeReasoningEngine:
    """Get singleton CodeReasoningEngine instance."""
    global _reasoning_engine
    if _reasoning_engine is None:
        with _reasoning_lock:
            if _reasoning_engine is None:
                _reasoning_engine = CodeReasoningEngine()
    return _reasoning_engine
