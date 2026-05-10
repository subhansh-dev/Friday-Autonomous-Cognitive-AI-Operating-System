#!/usr/bin/env python3
"""
self_modifier.py — FRIDAY Self-Modification Engine
====================================================

Enables FRIDAY to safely analyze, propose, and track modifications
to her own codebase. Safety-first: never auto-applies to critical files,
always creates backups, validates syntax before/after every change.
"""

import ast
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

BRAIN_DIR = Path(__file__).parent.resolve()
MODIFICATION_DATA_FILE = BRAIN_DIR / "modification_data.json"

CRITICAL_PATTERNS = [
    "main.py", "SOUL.md", "AGENTS.md", "USER.md",
    "security/", "config/", "credentials/",
    "agi_orchestrator.py", "self_modifier.py",
]


def _is_critical(file_path: str) -> bool:
    path_str = str(file_path).replace("\\", "/")
    return any(p in path_str for p in CRITICAL_PATTERNS)


def _read_file(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _write_file(path: Path, content: str) -> bool:
    try:
        path.write_text(content, encoding="utf-8")
        return True
    except Exception as e:
        print(f"[SelfModifier] Write failed: {e}")
        return False


def _git_commit(message: str) -> Optional[str]:
    try:
        subprocess.run(["git", "add", "-A"], cwd=str(BRAIN_DIR.parent),
                        capture_output=True, timeout=10)
        result = subprocess.run(
            ["git", "commit", "-m", f"[SelfModifier] {message}"],
            cwd=str(BRAIN_DIR.parent), capture_output=True, timeout=10)
        if result.returncode == 0:
            h = subprocess.run(["git", "rev-parse", "HEAD"],
                               cwd=str(BRAIN_DIR.parent), capture_output=True, timeout=5)
            return h.stdout.decode().strip()[:12]
    except Exception:
        pass
    return None


def _git_revert(commit_hash: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "revert", "--no-commit", "HEAD"],
            cwd=str(BRAIN_DIR.parent), capture_output=True, timeout=10)
        return result.returncode == 0
    except Exception:
        return False


# ════════════════════════════════════════════════════════════════════════
#  CodeAnalyzer — analyze own codebase for improvement opportunities
# ════════════════════════════════════════════════════════════════════════

class CodeAnalyzer:
    """Analyze FRIDAY's codebase for improvement opportunities."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def analyze_complexity(self, file_path: str) -> Dict[str, Any]:
        """Compute cyclomatic complexity per function."""
        source = _read_file(Path(file_path))
        if not source:
            return {"error": f"Cannot read {file_path}"}
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return {"error": f"Syntax error: {e}"}

        results: Dict[str, Any] = {"file": file_path, "functions": [], "total_complexity": 0}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = 1
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler,
                                          ast.With, ast.Assert, ast.comprehension)):
                        cc += 1
                    elif isinstance(child, ast.BoolOp):
                        cc += len(child.values) - 1
                results["functions"].append({"name": node.name, "line": node.lineno, "complexity": cc})
                results["total_complexity"] += cc
        results["avg_complexity"] = (
            results["total_complexity"] / len(results["functions"]) if results["functions"] else 0
        )
        return results

    def analyze_dependencies(self, file_path: str) -> Dict[str, Any]:
        """Map import graph, detect circular dependencies."""
        source = _read_file(Path(file_path))
        if not source:
            return {"error": f"Cannot read {file_path}"}
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return {"error": f"Syntax error: {e}"}

        imports: List[Dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({"type": "import", "module": alias.name, "line": node.lineno})
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    imports.append({"type": "from_import", "module": mod, "name": alias.name, "line": node.lineno})

        brain_modules = {i["module"] for i in imports if i.get("module", "").startswith(("brain.", "."))}
        file_stem = Path(file_path).stem
        circular_risks: List[str] = []
        for mod in brain_modules:
            mod_file = BRAIN_DIR / mod.replace(".", "/").replace("brain/", "")
            if mod_file.with_suffix(".py").exists():
                dep_src = _read_file(mod_file.with_suffix(".py"))
                if dep_src and file_stem in dep_src:
                    circular_risks.append(mod)

        return {
            "file": file_path, "imports": imports,
            "brain_dependencies": list(brain_modules),
            "circular_risks": circular_risks, "total_imports": len(imports),
        }

    def analyze_patterns(self, file_path: str) -> Dict[str, Any]:
        """Find repeated code patterns that could be abstracted."""
        source = _read_file(Path(file_path))
        if not source:
            return {"error": f"Cannot read {file_path}"}
        lines = source.splitlines()
        patterns: Dict[str, List[int]] = defaultdict(list)
        suggestions: List[Dict[str, Any]] = []

        boilerplate = [
            (r"if __name__ == .__main__:", "main_guard"),
            (r"try:\s*$", "try_block"),
            (r"print\(f?['\"]\\[.*?\\]", "log_print"),
            (r"self\._lock\.acquire|with self\._lock", "lock_usage"),
            (r"Path\(__file__\)\.parent", "path_resolution"),
            (r"json\.load|json\.dump", "json_io"),
        ]
        for i, line in enumerate(lines, 1):
            for pat, name in boilerplate:
                if re.search(pat, line):
                    patterns[name].append(i)

        for name, occs in patterns.items():
            if len(occs) >= 3:
                suggestions.append({
                    "pattern": name, "occurrences": len(occs),
                    "lines": occs[:10],
                    "suggestion": f"Consider extracting '{name}' into a utility function",
                })

        # Detect long functions
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    end = getattr(node, "end_lineno", node.lineno + 50)
                    if end - node.lineno > 50:
                        suggestions.append({
                            "pattern": "long_function", "function": node.name,
                            "lines": end - node.lineno,
                            "suggestion": f"Function '{node.name}' is {end - node.lineno} lines — consider splitting",
                        })
        except SyntaxError:
            pass

        return {"file": file_path, "patterns": dict(patterns), "suggestions": suggestions}

    def analyze_docstrings(self, file_path: str) -> Dict[str, Any]:
        """Check documentation coverage."""
        source = _read_file(Path(file_path))
        if not source:
            return {"error": f"Cannot read {file_path}"}
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return {"error": f"Syntax error: {e}"}

        has_mod_doc = (isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, (ast.Constant, ast.Str))) if tree.body else False
        fn_total = fn_doc = cls_total = cls_doc = 0
        undocumented: List[str] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_total += 1
                if ast.get_docstring(node):
                    fn_doc += 1
                else:
                    undocumented.append(f"func:{node.name} (line {node.lineno})")
            elif isinstance(node, ast.ClassDef):
                cls_total += 1
                if ast.get_docstring(node):
                    cls_doc += 1
                else:
                    undocumented.append(f"class:{node.name} (line {node.lineno})")

        total = fn_total + cls_total + 1
        documented = fn_doc + cls_doc + (1 if has_mod_doc else 0)
        return {
            "file": file_path, "module_docstring": has_mod_doc,
            "functions_total": fn_total, "functions_documented": fn_doc,
            "classes_total": cls_total, "classes_documented": cls_doc,
            "coverage_pct": round(documented / total * 100, 1) if total > 0 else 100,
            "undocumented": undocumented,
        }

    def analyze_type_hints(self, file_path: str) -> Dict[str, Any]:
        """Check type hint coverage."""
        source = _read_file(Path(file_path))
        if not source:
            return {"error": f"Cannot read {file_path}"}
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return {"error": f"Syntax error: {e}"}

        total_args = typed_args = total_ret = typed_ret = 0
        untyped: List[str] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                all_args = [a for a in node.args.args + node.args.posonlyargs + node.args.kwonlyargs
                            if a.arg not in ("self", "cls")]
                for arg in all_args:
                    total_args += 1
                    if arg.annotation is not None:
                        typed_args += 1
                    else:
                        untyped.append(f"arg:{node.name}.{arg.arg}")
                total_ret += 1
                if node.returns is not None:
                    typed_ret += 1
                else:
                    untyped.append(f"return:{node.name}")

        total = total_args + total_ret
        typed = typed_args + typed_ret
        return {
            "file": file_path, "total_signatures": total, "typed_signatures": typed,
            "coverage_pct": round(typed / total * 100, 1) if total > 0 else 100,
            "args_typed": typed_args, "args_total": total_args,
            "returns_typed": typed_ret, "returns_total": total_ret,
            "untyped": untyped[:20],
        }

    def suggest_improvements(self, file_path: str) -> Dict[str, Any]:
        """Generate comprehensive improvement suggestions."""
        c = self.analyze_complexity(file_path)
        d = self.analyze_dependencies(file_path)
        p = self.analyze_patterns(file_path)
        doc = self.analyze_docstrings(file_path)
        th = self.analyze_type_hints(file_path)

        suggestions: List[Dict[str, Any]] = []
        for func in c.get("functions", []):
            if func["complexity"] > 10:
                suggestions.append({"type": "complexity", "severity": "high",
                    "target": f"{func['name']} (line {func['line']})",
                    "message": f"Cyclomatic complexity {func['complexity']} — simplify control flow",
                    "impact": min(func["complexity"] / 20, 1.0)})
            elif func["complexity"] > 6:
                suggestions.append({"type": "complexity", "severity": "medium",
                    "target": f"{func['name']} (line {func['line']})",
                    "message": f"Moderate complexity {func['complexity']} — consider refactoring",
                    "impact": func["complexity"] / 30})

        if d.get("circular_risks"):
            suggestions.append({"type": "dependency", "severity": "high", "target": file_path,
                "message": f"Potential circular dependencies: {d['circular_risks']}", "impact": 0.7})
        if doc.get("coverage_pct", 100) < 70:
            suggestions.append({"type": "documentation", "severity": "low", "target": file_path,
                "message": f"Documentation coverage {doc['coverage_pct']}%", "impact": 0.3})
        if th.get("coverage_pct", 100) < 60:
            suggestions.append({"type": "type_hints", "severity": "low", "target": file_path,
                "message": f"Type hint coverage {th['coverage_pct']}%", "impact": 0.2})
        for s in p.get("suggestions", []):
            suggestions.append({"type": "pattern", "severity": "medium", "target": file_path,
                "message": s.get("suggestion", ""), "impact": 0.4})

        suggestions.sort(key=lambda x: x.get("impact", 0), reverse=True)
        return {
            "file": file_path, "suggestions": suggestions,
            "total_suggestions": len(suggestions),
            "analysis": {"complexity": c, "dependencies": d, "patterns": p,
                         "docstrings": doc, "type_hints": th},
        }


# ════════════════════════════════════════════════════════════════════════
#  ImprovementProposer — suggest architectural changes
# ════════════════════════════════════════════════════════════════════════

class ImprovementProposer:
    """Suggest architectural improvements, scored by impact × feasibility."""

    def __init__(self):
        self._proposals: List[Dict[str, Any]] = []

    def propose_refactoring(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Suggest code refactoring based on analysis results."""
        proposals = []
        for s in analysis.get("suggestions", []):
            impact = s.get("impact", 0.5)
            feasibility = self._estimate_feasibility(s)
            proposals.append({
                "id": str(uuid.uuid4())[:8], "type": "refactoring",
                "category": s.get("type", "unknown"), "severity": s.get("severity", "medium"),
                "description": s.get("message", ""), "target": s.get("target", ""),
                "impact": impact, "feasibility": feasibility,
                "score": round(impact * feasibility, 3),
                "status": "proposed", "created_at": datetime.now().isoformat(),
            })
        proposals.sort(key=lambda x: x["score"], reverse=True)
        self._proposals.extend(proposals)
        return proposals

    def propose_new_module(self, gap: str) -> Dict[str, Any]:
        """Suggest creating a new brain module to fill a capability gap."""
        words = re.findall(r"[a-zA-Z]+", gap.lower())
        name = "_".join(words[:3]) if words else "new_module"
        proposal = {
            "id": str(uuid.uuid4())[:8], "type": "new_module",
            "description": f"New module needed: {gap}", "suggested_name": name,
            "suggested_interfaces": self._suggest_interfaces(gap),
            "impact": 0.8, "feasibility": 0.6, "score": round(0.8 * 0.6, 3),
            "status": "proposed", "created_at": datetime.now().isoformat(),
        }
        self._proposals.append(proposal)
        return proposal

    def propose_integration(self, modules: List[str]) -> List[Dict[str, Any]]:
        """Suggest wiring existing modules together."""
        proposals = []
        existing = [m for m in modules if (BRAIN_DIR / f"{m}.py").exists()]
        for i in range(len(existing)):
            for j in range(i + 1, len(existing)):
                proposals.append({
                    "id": str(uuid.uuid4())[:8], "type": "integration",
                    "modules": [existing[i], existing[j]],
                    "description": f"Integrate {existing[i]} ↔ {existing[j]}: share events, reduce duplication",
                    "impact": 0.6, "feasibility": 0.7, "score": round(0.6 * 0.7, 3),
                    "status": "proposed", "created_at": datetime.now().isoformat(),
                })
        self._proposals.extend(proposals)
        return proposals

    def get_proposals(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if status:
            return [p for p in self._proposals if p.get("status") == status]
        return list(self._proposals)

    def _estimate_feasibility(self, suggestion: Dict[str, Any]) -> float:
        base = {"low": 0.9, "medium": 0.7, "high": 0.5}.get(suggestion.get("severity", "medium"), 0.5)
        if suggestion.get("type") == "documentation":
            base = min(base + 0.2, 1.0)
        elif suggestion.get("type") == "dependency":
            base = max(base - 0.2, 0.1)
        elif suggestion.get("type") == "complexity":
            base = max(base - 0.1, 0.2)
        return round(base, 2)

    @staticmethod
    def _suggest_interfaces(gap: str) -> List[str]:
        base = ["__init__", "get_stats", "format_for_prompt"]
        g = gap.lower()
        if "learn" in g or "train" in g:
            base.extend(["learn", "evaluate", "get_progress"])
        elif "memory" in g or "store" in g:
            base.extend(["store", "retrieve", "forget", "consolidate"])
        elif "plan" in g or "goal" in g:
            base.extend(["plan", "execute", "evaluate_plan"])
        elif "sense" in g or "perceive" in g:
            base.extend(["perceive", "interpret", "get_latest"])
        else:
            base.extend(["process", "analyze", "report"])
        return base


# ════════════════════════════════════════════════════════════════════════
#  SafeModification — apply changes with backup and rollback
# ════════════════════════════════════════════════════════════════════════

class SafeModification:
    """Apply modifications with backup, rollback, and git integration."""

    def __init__(self):
        self._lock = threading.RLock()
        self._changes: Dict[str, Dict[str, Any]] = {}
        self._backups: Dict[str, str] = {}

    def propose_change(self, file: str, description: str, diff: str,
                       approved: bool = False) -> Dict[str, Any]:
        with self._lock:
            cid = str(uuid.uuid4())[:12]
            is_crit = _is_critical(file)
            change = {
                "id": cid, "file": file, "description": description, "diff": diff,
                "is_critical": is_crit, "approved": approved, "status": "proposed",
                "created_at": datetime.now().isoformat(), "applied_at": None,
                "backup_hash": None, "git_commit": None,
            }
            self._changes[cid] = change
            print(f"[SelfModifier] Proposed change {cid}: {description}")
            if is_crit:
                print(f"[SelfModifier] ⚠ CRITICAL file: {file} — requires approval")
            return copy.deepcopy(change)

    def apply_change(self, change_id: str) -> Dict[str, Any]:
        with self._lock:
            change = self._changes.get(change_id)
            if not change:
                return {"success": False, "error": f"Change {change_id} not found"}
            if change["is_critical"] and not change["approved"]:
                return {"success": False, "error": f"Critical file '{change['file']}' — approval required"}

            file_path = Path(change["file"])
            if not file_path.exists():
                return {"success": False, "error": f"File not found: {change['file']}"}

            original = _read_file(file_path)
            if original is None:
                return {"success": False, "error": f"Cannot read {change['file']}"}

            self._backups[change_id] = original
            change["backup_hash"] = hashlib.sha256(original.encode()).hexdigest()[:16]
            change["git_commit"] = _git_commit(f"pre-change backup {change_id}")

            ok, msg = IntegrityChecker.check_syntax(str(file_path))
            if not ok:
                return {"success": False, "error": f"Current file has syntax errors: {msg}"}

            if not self._apply_diff(file_path, change["diff"]):
                return {"success": False, "error": "Failed to apply diff"}

            ok, msg = IntegrityChecker.check_syntax(str(file_path))
            if not ok:
                print("[SelfModifier] Post-apply syntax error — rolling back")
                _write_file(file_path, original)
                return {"success": False, "error": f"Syntax error after apply, rolled back: {msg}"}

            change["status"] = "applied"
            change["applied_at"] = datetime.now().isoformat()
            print(f"[SelfModifier] Applied change {change_id} to {change['file']}")
            return {"success": True, "change_id": change_id}

    def rollback(self, change_id: str) -> Dict[str, Any]:
        with self._lock:
            change = self._changes.get(change_id)
            if not change:
                return {"success": False, "error": f"Change {change_id} not found"}
            backup = self._backups.get(change_id)
            if not backup:
                gh = change.get("git_commit")
                if gh and _git_revert(gh):
                    change["status"] = "rolled_back"
                    return {"success": True, "method": "git_revert"}
                return {"success": False, "error": "No backup available"}
            if _write_file(Path(change["file"]), backup):
                change["status"] = "rolled_back"
                print(f"[SelfModifier] Rolled back {change_id}")
                return {"success": True, "method": "backup_restore"}
            return {"success": False, "error": "Failed to write backup"}

    def validate_change(self, change_id: str) -> Dict[str, Any]:
        with self._lock:
            change = self._changes.get(change_id)
            if not change:
                return {"valid": False, "error": f"Change {change_id} not found"}
            fp = Path(change["file"])
            if not fp.exists():
                return {"valid": False, "error": f"File not found: {change['file']}"}
            syn_ok, syn_msg = IntegrityChecker.check_syntax(str(fp))
            imp_ok, imp_msg = IntegrityChecker.check_imports(str(fp))
            return {
                "valid": syn_ok and imp_ok,
                "syntax": {"ok": syn_ok, "message": syn_msg},
                "imports": {"ok": imp_ok, "message": imp_msg},
            }

    def get_changes(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            if status:
                return [c for c in self._changes.values() if c.get("status") == status]
            return list(self._changes.values())

    def _apply_diff(self, file_path: Path, diff: str) -> bool:
        try:
            original = _read_file(file_path)
            if original is None:
                return False
            if diff.startswith("REPLACE:"):
                parts = diff.split(":WITH:", 1)
                if len(parts) != 2:
                    print("[SelfModifier] Malformed REPLACE diff — expected REPLACE:old:WITH:new")
                    return False
                old_text = parts[0][len("REPLACE:"):]
                new_text = parts[1]
                if old_text not in original:
                    print(f"[SelfModifier] REPLACE target not found in {file_path.name}")
                    return False
                return _write_file(file_path, original.replace(old_text, new_text, 1))
            if diff.startswith("FULL_CONTENT:"):
                return _write_file(file_path, diff[len("FULL_CONTENT:"):])
            print(f"[SelfModifier] Unsupported diff format: {diff[:30]}...")
            return False
        except Exception as e:
            print(f"[SelfModifier] Diff error: {e}")
            return False


# ════════════════════════════════════════════════════════════════════════
#  IntegrityChecker — verify modifications don't break functionality
# ════════════════════════════════════════════════════════════════════════

class IntegrityChecker:
    """Verify that modifications don't break FRIDAY's functionality."""

    @staticmethod
    def check_syntax(file_path: str) -> Tuple[bool, str]:
        try:
            source = _read_file(Path(file_path))
            if source is None:
                return False, f"Cannot read: {file_path}"
            ast.parse(source)
            return True, "Syntax OK"
        except SyntaxError as e:
            return False, f"Syntax error at line {e.lineno}: {e.msg}"

    @staticmethod
    def check_imports(file_path: str) -> Tuple[bool, str]:
        source = _read_file(Path(file_path))
        if source is None:
            return False, f"Cannot read: {file_path}"
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False, "Syntax error"
        unresolved: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("brain."):
                        lp = BRAIN_DIR / alias.name.replace("brain/", "").replace(".", "/")
                        if not (lp.with_suffix(".py").exists() or (lp / "__init__.py").exists()):
                            unresolved.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod.startswith(("brain.", ".")):
                    lp = BRAIN_DIR / mod.lstrip(".").replace(".", "/")
                    if not (lp.with_suffix(".py").exists() or (lp / "__init__.py").exists()):
                        unresolved.append(mod)
        return (True, "All imports OK") if not unresolved else (False, f"Unresolved: {unresolved}")

    @staticmethod
    def check_interface(file_path: str, expected_methods: List[str]) -> Tuple[bool, Dict[str, Any]]:
        source = _read_file(Path(file_path))
        if source is None:
            return False, {"error": f"Cannot read {file_path}"}
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False, {"error": "Syntax error"}
        found: Dict[str, List[str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                found[node.name] = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        results: Dict[str, Any] = {}
        all_ok = True
        for cname, methods in found.items():
            missing = [m for m in expected_methods if m not in methods]
            results[cname] = {"found": len(methods), "missing": missing, "ok": len(missing) == 0}
            if missing:
                all_ok = False
        return all_ok, results

    @staticmethod
    def check_consistency(brain_dir: str) -> Dict[str, Any]:
        """Verify all brain modules follow FRIDAY conventions."""
        brain_path = Path(brain_dir)
        results: Dict[str, Any] = {"total_modules": 0, "consistent": 0, "inconsistent": 0, "issues": []}

        for py_file in sorted(brain_path.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            results["total_modules"] += 1
            source = _read_file(py_file)
            if not source:
                continue
            issues: List[str] = []
            try:
                tree = ast.parse(source)
            except SyntaxError:
                issues.append("syntax_error")
                results["issues"].append({"file": py_file.name, "issues": issues})
                results["inconsistent"] += 1
                continue

            if not (tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, (ast.Constant, ast.Str))):
                issues.append("missing_module_docstring")

            has_brain_dir = any(
                isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "BRAIN_DIR" for t in n.targets)
                for n in ast.walk(tree)
            )
            if not has_brain_dir:
                issues.append("missing_brain_dir")

            loc = source.count("\n")
            if not any(isinstance(n, ast.FunctionDef) and n.name.startswith("get_") for n in ast.walk(tree)) and loc > 100:
                issues.append("missing_singleton")
            if "threading" not in source and loc > 150:
                issues.append("no_thread_safety")
            if "format_for_prompt" not in source and loc > 100:
                issues.append("missing_format_for_prompt")
            if "get_stats" not in source and loc > 100:
                issues.append("missing_get_stats")

            if issues:
                results["issues"].append({"file": py_file.name, "issues": issues})
                results["inconsistent"] += 1
            else:
                results["consistent"] += 1

        results["consistency_pct"] = (
            round(results["consistent"] / results["total_modules"] * 100, 1)
            if results["total_modules"] > 0 else 100
        )
        return results


# ════════════════════════════════════════════════════════════════════════
#  EvolutionTracker — track architectural evolution over time
# ════════════════════════════════════════════════════════════════════════

class EvolutionTracker:
    """Track FRIDAY's architectural evolution over time."""

    def __init__(self, data_file: Path = MODIFICATION_DATA_FILE):
        self._lock = threading.RLock()
        self._data_file = data_file
        self._data = self._load_data()

    def _load_data(self) -> Dict[str, Any]:
        if self._data_file.exists():
            try:
                return json.loads(self._data_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"modifications": [], "metrics_history": [], "created_at": datetime.now().isoformat()}

    def _save_data(self):
        try:
            self._data_file.write_text(json.dumps(self._data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            print(f"[SelfModifier] Save failed: {e}")

    def record_modification(self, change_id: str, what: str, why: str,
                            impact: str = "unknown") -> Dict[str, Any]:
        with self._lock:
            rec = {"change_id": change_id, "what": what, "why": why,
                   "impact": impact, "timestamp": datetime.now().isoformat()}
            self._data["modifications"].append(rec)
            self._save_data()
            print(f"[SelfModifier] Recorded: {what}")
            return rec

    def snapshot_metrics(self) -> Dict[str, Any]:
        with self._lock:
            analyzer = CodeAnalyzer()
            total_loc = total_cc = module_count = 0
            for f in sorted(BRAIN_DIR.glob("*.py")):
                if f.name.startswith("_"):
                    continue
                module_count += 1
                src = _read_file(f)
                if src:
                    total_loc += src.count("\n")
                    total_cc += analyzer.analyze_complexity(str(f)).get("total_complexity", 0)

            metrics = {
                "timestamp": datetime.now().isoformat(),
                "module_count": module_count, "total_loc": total_loc,
                "total_complexity": total_cc,
                "avg_complexity": round(total_cc / module_count, 2) if module_count else 0,
            }
            self._data["metrics_history"].append(metrics)
            self._data["metrics_history"] = self._data["metrics_history"][-100:]
            self._save_data()
            return metrics

    def get_evolution_report(self, max_entries: int = 20) -> str:
        with self._lock:
            mods = self._data.get("modifications", [])[-max_entries:]
            metrics = self._data.get("metrics_history", [])
            lines = ["═══ FRIDAY Evolution Report ═══\n"]

            if metrics:
                latest = metrics[-1]
                lines.append("📊 Latest Metrics:")
                lines.append(f"  Modules: {latest.get('module_count', '?')}")
                lines.append(f"  Total LOC: {latest.get('total_loc', '?')}")
                lines.append(f"  Total Complexity: {latest.get('total_complexity', '?')}")
                lines.append(f"  Avg Complexity: {latest.get('avg_complexity', '?')}")
                if len(metrics) >= 2:
                    first = metrics[0]
                    loc_d = latest.get("total_loc", 0) - first.get("total_loc", 0)
                    mod_d = latest.get("module_count", 0) - first.get("module_count", 0)
                    lines.append(f"\n  📈 Since tracking began:")
                    lines.append(f"    LOC change: {'+' if loc_d >= 0 else ''}{loc_d}")
                    lines.append(f"    Module change: {'+' if mod_d >= 0 else ''}{mod_d}")
                lines.append("")

            if mods:
                lines.append(f"📝 Recent Modifications ({len(mods)}):")
                for m in mods:
                    ts = m.get("timestamp", "?")[:16]
                    lines.append(f"  [{ts}] {m.get('what', '?')}")
                    lines.append(f"    Why: {m.get('why', '?')}  |  Impact: {m.get('impact', '?')}")
            else:
                lines.append("📝 No modifications recorded yet.")
            return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════
#  SelfModifier — main self-modification engine
# ════════════════════════════════════════════════════════════════════════

class SelfModifier:
    """
    Main self-modification engine for FRIDAY.

    Coordinates analysis, proposals, safe modification,
    integrity checking, and evolution tracking.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self.analyzer = CodeAnalyzer()
        self.proposer = ImprovementProposer()
        self.modifier = SafeModification()
        self.checker = IntegrityChecker()
        self.tracker = EvolutionTracker()

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        with self._lock:
            return self.analyzer.suggest_improvements(file_path)

    def analyze_brain(self) -> Dict[str, Any]:
        with self._lock:
            all_results: List[Dict[str, Any]] = []
            for py_file in sorted(BRAIN_DIR.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                all_results.append(self.analyzer.suggest_improvements(str(py_file)))

            severity_counts: Dict[str, int] = defaultdict(int)
            for r in all_results:
                for s in r.get("suggestions", []):
                    severity_counts[s.get("severity", "unknown")] += 1

            return {
                "files_analyzed": len(all_results),
                "total_suggestions": sum(r.get("total_suggestions", 0) for r in all_results),
                "severity_breakdown": dict(severity_counts),
                "details": all_results,
            }

    def propose_and_record(self, file_path: str, description: str, diff: str) -> Dict[str, Any]:
        with self._lock:
            change = self.modifier.propose_change(file_path, description, diff)
            self.tracker.record_modification(change["id"], description,
                                             f"Proposed improvement to {file_path}", "pending")
            return change

    def apply_with_validation(self, change_id: str) -> Dict[str, Any]:
        with self._lock:
            validation = self.modifier.validate_change(change_id)
            if not validation.get("valid"):
                return {"success": False, "error": "Pre-validation failed", "details": validation}
            return self.modifier.apply_change(change_id)

    def self_audit(self) -> Dict[str, Any]:
        """Full self-modification audit."""
        with self._lock:
            print("[SelfModifier] Running full self-audit...")
            consistency = self.checker.check_consistency(str(BRAIN_DIR))
            metrics = self.tracker.snapshot_metrics()

            key_files = [str(f) for f in sorted(BRAIN_DIR.glob("*.py"))
                         if not f.name.startswith("_") and f.stat().st_size > 2000]
            analyses = [self.analyzer.suggest_improvements(fp) for fp in key_files[:10]]

            total_sug = sum(r.get("total_suggestions", 0) for r in analyses)
            critical = [s for r in analyses for s in r.get("suggestions", []) if s.get("severity") == "high"]

            audit = {
                "timestamp": datetime.now().isoformat(),
                "consistency": consistency, "metrics": metrics,
                "files_analyzed": len(analyses),
                "total_suggestions": total_sug,
                "critical_issues": critical,
                "recommendations": self._recommendations(consistency, metrics, critical),
            }
            print(f"[SelfModifier] Audit: {total_sug} suggestions, {len(critical)} critical")
            return audit

    def suggest_orchestrator_improvements(self) -> Dict[str, Any]:
        """Analyze and suggest improvements for the AGI orchestrator."""
        orch = BRAIN_DIR / "agi_orchestrator.py"
        if not orch.exists():
            return {"error": "agi_orchestrator.py not found"}

        analysis = self.analyzer.suggest_improvements(str(orch))
        source = _read_file(orch)
        orch_issues: List[Dict[str, str]] = []

        if source:
            if "try:" not in source or source.count("try:") < source.count("import") * 0.3:
                orch_issues.append({"type": "resilience",
                    "message": "May lack sufficient error handling for module imports"})
            if not any(k in source.lower() for k in ("publish", "emit", "event")):
                orch_issues.append({"type": "architecture",
                    "message": "Consider adding event-driven communication"})
            if "timeout" not in source.lower():
                orch_issues.append({"type": "robustness",
                    "message": "No timeout handling — modules could hang the orchestrator"})
            stages = ["perceive", "plan", "simulate", "execute", "reflect", "learn"]
            missing = [s for s in stages if s not in source.lower()]
            if missing:
                orch_issues.append({"type": "completeness",
                    "message": f"Cognitive loop missing stages: {missing}"})

        return {
            "file": str(orch), "code_analysis": analysis,
            "orchestrator_specific": orch_issues,
            "total_issues": len(orch_issues) + analysis.get("total_suggestions", 0),
        }

    def _recommendations(self, consistency: Dict, metrics: Dict, critical: List) -> List[str]:
        recs: List[str] = []
        if consistency.get("consistency_pct", 100) < 80:
            recs.append(f"Consistency {consistency['consistency_pct']}% — refactor {consistency.get('inconsistent', 0)} modules")
        if metrics.get("avg_complexity", 0) > 15:
            recs.append(f"Avg complexity {metrics['avg_complexity']} — prioritize simplification")
        if len(critical) > 3:
            recs.append(f"{len(critical)} critical issues — schedule refactoring session")
        if metrics.get("total_loc", 0) > 20000:
            recs.append("20K+ LOC — consider extracting shared utilities")
        if not recs:
            recs.append("Codebase in good shape — focus on docs and type hints")
        return recs

    def format_for_prompt(self, max_chars: int = 3000) -> str:
        with self._lock:
            parts = ["[Self-Modification Status]"]
            metrics_hist = self.tracker._data.get("metrics_history", [])
            if metrics_hist:
                m = metrics_hist[-1]
                parts.append(f"Modules: {m.get('module_count','?')} | LOC: {m.get('total_loc','?')} | Complexity: {m.get('total_complexity','?')}")
            pending = self.modifier.get_changes(status="proposed")
            if pending:
                parts.append(f"Pending changes: {len(pending)}")
                for c in pending[:3]:
                    parts.append(f"  • {c['id']}: {c['description'][:80]}")
            mods = self.tracker._data.get("modifications", [])
            if mods:
                parts.append("Recent modifications:")
                for m in mods[-3:]:
                    parts.append(f"  • {m.get('what', '?')[:80]}")
            return "\n".join(parts)[:max_chars]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            metrics_hist = self.tracker._data.get("metrics_history", [])
            mods = self.tracker._data.get("modifications", [])
            changes = self.modifier.get_changes()
            return {
                "total_modifications": len(mods),
                "total_proposals": len(changes),
                "pending_proposals": len([c for c in changes if c.get("status") == "proposed"]),
                "applied_proposals": len([c for c in changes if c.get("status") == "applied"]),
                "rolled_back": len([c for c in changes if c.get("status") == "rolled_back"]),
                "metrics_snapshots": len(metrics_hist),
                "latest_metrics": metrics_hist[-1] if metrics_hist else None,
            }


# ════════════════════════════════════════════════════════════════════════
#  Singleton
# ════════════════════════════════════════════════════════════════════════

_self_modifier = None
_sm_lock = threading.Lock()


def get_self_modifier() -> SelfModifier:
    """Get singleton SelfModifier instance."""
    global _self_modifier
    if _self_modifier is None:
        with _sm_lock:
            if _self_modifier is None:
                _self_modifier = SelfModifier()
    return _self_modifier
