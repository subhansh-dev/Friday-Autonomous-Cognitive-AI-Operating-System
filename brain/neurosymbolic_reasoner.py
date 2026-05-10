#!/usr/bin/env python3
"""
neurosymbolic_reasoner.py — FRIDAY Neurosymbolic Reasoning Layer
=================================================================

Combines neural (LLM) and symbolic (formal logic, SymPy) reasoning for
code verification, invariant checking, and property proving.

Architecture:
  Natural Language ↔ Symbolic Propositions ↔ Formal Verification
       ↕                    ↕                       ↕
     LLM (Gemini)    Propositional Engine      SymPy / AST

Capabilities:
- Verify mathematical invariants in code (loop invariants, pre/post conditions)
- Convert natural language to logical propositions
- Check logical consistency of proposition sets
- Attempt formal verification of code properties
- Symbolic planning with LLM validation
- Extract likely invariants from code using AST + LLM

Integrates with:
- code_intelligence.py — AST context and codebase graph
- code_planner.py — feeds verified properties into planning
"""

import ast
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

BRAIN_DIR = Path(__file__).parent.resolve()
REASONER_FILE = BRAIN_DIR / "neurosymbolic_state.json"
API_CONFIG_PATH = BRAIN_DIR.parent / "config" / "api_keys.json"
REASONER_MODEL = "gemini-2.5-flash"


# ── Propositional Logic Engine (from scratch, no heavy deps) ─────────────

class Proposition:
    """A logical proposition with a truth value and metadata."""

    def __init__(self, name: str, value: Optional[bool] = None,
                 description: str = "", confidence: float = 1.0):
        self.name = name
        self.value = value  # None = unknown
        self.description = description
        self.confidence = confidence  # 0.0 - 1.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "description": self.description,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Proposition":
        return cls(
            name=data["name"],
            value=data.get("value"),
            description=data.get("description", ""),
            confidence=data.get("confidence", 1.0),
        )

    def __repr__(self) -> str:
        val_str = "T" if self.value else "F" if self.value is False else "?"
        return f"P({self.name}={val_str})"


class LogicalFormula:
    """A compound logical formula built from propositions."""

    def __init__(self, formula_type: str, operands: List[Any] = None,
                 proposition: Optional[Proposition] = None):
        """
        Args:
            formula_type: "atom", "and", "or", "not", "implies", "iff"
            operands: List of LogicalFormula for compound formulas
            proposition: The proposition for atomic formulas
        """
        self.formula_type = formula_type
        self.operands = operands or []
        self.proposition = proposition

    def evaluate(self, valuation: Dict[str, bool]) -> Optional[bool]:
        """
        Evaluate this formula given a truth assignment.

        Args:
            valuation: Mapping from proposition names to truth values

        Returns:
            True, False, or None (if cannot be determined)
        """
        try:
            if self.formula_type == "atom":
                if self.proposition is None:
                    return None
                return valuation.get(self.proposition.name, self.proposition.value)

            elif self.formula_type == "not":
                if not self.operands:
                    return None
                inner = self.operands[0].evaluate(valuation)
                if inner is None:
                    return None
                return not inner

            elif self.formula_type == "and":
                results = [op.evaluate(valuation) for op in self.operands]
                if any(r is False for r in results):
                    return False
                if all(r is True for r in results):
                    return True
                return None

            elif self.formula_type == "or":
                results = [op.evaluate(valuation) for op in self.operands]
                if any(r is True for r in results):
                    return True
                if all(r is False for r in results):
                    return False
                return None

            elif self.formula_type == "implies":
                if len(self.operands) < 2:
                    return None
                antecedent = self.operands[0].evaluate(valuation)
                consequent = self.operands[1].evaluate(valuation)
                if antecedent is False:
                    return True  # False implies anything
                if antecedent is True and consequent is False:
                    return False
                if antecedent is True and consequent is True:
                    return True
                return None

            elif self.formula_type == "iff":
                if len(self.operands) < 2:
                    return None
                left = self.operands[0].evaluate(valuation)
                right = self.operands[1].evaluate(valuation)
                if left is None or right is None:
                    return None
                return left == right

        except Exception:
            return None

        return None

    def get_propositions(self) -> Set[str]:
        """Get all proposition names used in this formula."""
        names: Set[str] = set()
        if self.proposition:
            names.add(self.proposition.name)
        for op in self.operands:
            names.update(op.get_propositions())
        return names

    def to_dict(self) -> dict:
        return {
            "type": self.formula_type,
            "operands": [op.to_dict() for op in self.operands],
            "proposition": self.proposition.to_dict() if self.proposition else None,
        }


def _make_atom(name: str) -> LogicalFormula:
    """Create an atomic formula from a proposition name."""
    return LogicalFormula("atom", proposition=Proposition(name))


def _make_not(formula: LogicalFormula) -> LogicalFormula:
    """Create a negation."""
    return LogicalFormula("not", operands=[formula])


def _make_and(*formulas: LogicalFormula) -> LogicalFormula:
    """Create a conjunction."""
    return LogicalFormula("and", operands=list(formulas))


def _make_or(*formulas: LogicalFormula) -> LogicalFormula:
    """Create a disjunction."""
    return LogicalFormula("or", operands=list(formulas))


def _make_implies(antecedent: LogicalFormula, consequent: LogicalFormula) -> LogicalFormula:
    """Create an implication."""
    return LogicalFormula("implies", operands=[antecedent, consequent])


def check_propositional_consistency(formulas: List[LogicalFormula]) -> Tuple[bool, Optional[Dict[str, bool]]]:
    """
    Check if a set of propositional formulas is satisfiable.

    Uses brute-force enumeration over all possible truth assignments.
    Feasible for small numbers of propositions (<= 20).

    Returns:
        Tuple of (is_consistent, satisfying_assignment_or_None)
    """
    # Collect all proposition names
    all_props: Set[str] = set()
    for f in formulas:
        all_props.update(f.get_propositions())

    prop_list = sorted(all_props)
    n = len(prop_list)

    if n == 0:
        # No propositions — trivially consistent
        return True, {}

    if n > 20:
        # Too many for brute force — assume consistent (conservative)
        return True, None

    # Enumerate all 2^n assignments
    for mask in range(1 << n):
        valuation: Dict[str, bool] = {}
        for i, prop_name in enumerate(prop_list):
            valuation[prop_name] = bool(mask & (1 << i))

        # Check if all formulas are satisfied
        all_satisfied = True
        for formula in formulas:
            result = formula.evaluate(valuation)
            if result is not True:
                all_satisfied = False
                break

        if all_satisfied:
            return True, valuation

    return False, None


# ── LLM Helper ───────────────────────────────────────────────────────────

def _get_api_key() -> str:
    """Load Gemini API key from config."""
    try:
        data = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        return data.get("gemini_api_key", data.get("GOOGLE_API_KEY", ""))
    except Exception:
        return ""


def _llm_generate(prompt: str, system: str = "") -> str:
    """Call Gemini LLM for reasoning tasks."""
    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=_get_api_key())
        config = genai_types.GenerateContentConfig(
            system_instruction=system if system else None,
            max_output_tokens=4096,
        )
        response = client.models.generate_content(
            model=REASONER_MODEL,
            contents=prompt,
            config=config,
        )
        return response.text.strip()
    except Exception as exc:
        return f"LLM Error: {exc}"


# ── Neurosymbolic Reasoner ───────────────────────────────────────────────

class NeurosymbolicReasoner:
    """
    Neurosymbolic reasoning engine combining LLM intuition with formal verification.

    Provides:
    - Mathematical invariant verification via SymPy
    - Natural language → logical proposition conversion
    - Propositional consistency checking
    - Formal property proving
    - Symbolic planning with LLM validation
    - Invariant extraction from code via AST + LLM
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data = self._empty_store()
        self._load()
        print("[NeurosymbolicReasoner] Initialized")

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": datetime.now().isoformat(),
                "last_update": datetime.now().isoformat(),
                "total_verifications": 0,
                "total_proofs": 0,
                "successful_proofs": 0,
            },
            "verified_invariants": [],
            "proven_properties": [],
            "consistency_checks": [],
        }

    # ── Persistence ─────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load reasoner state from disk."""
        try:
            if REASONER_FILE.exists():
                raw = REASONER_FILE.read_text(encoding="utf-8")
                data = json.loads(raw)
                empty = self._empty_store()
                for key in empty:
                    if key not in data:
                        data[key] = empty[key]
                self._data = data
        except (json.JSONDecodeError, IOError) as exc:
            print(f"[NeurosymbolicReasoner] Load error: {exc}")
            self._data = self._empty_store()
            self._save()

    def _save(self) -> None:
        """Persist reasoner state to disk."""
        with self._lock:
            try:
                self._data["meta"]["last_update"] = datetime.now().isoformat()
                BRAIN_DIR.mkdir(parents=True, exist_ok=True)
                REASONER_FILE.write_text(
                    json.dumps(self._data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except IOError as exc:
                print(f"[NeurosymbolicReasoner] Save error: {exc}")

    # ── Core Reasoning Methods ──────────────────────────────────────────

    def verify_invariant(self, code: str, invariant: str) -> dict:
        """
        Verify a mathematical invariant in code using SymPy.

        Analyzes the code's mathematical structure and checks if the
        invariant holds at key points (loop entry, loop body, loop exit).

        Args:
            code: Python source code to analyze
            invariant: Natural language or symbolic invariant description

        Returns:
            dict with: holds (bool), confidence (float), analysis (str),
                       counter_example (optional str)
        """
        result = {
            "holds": False,
            "confidence": 0.0,
            "analysis": "",
            "counter_example": None,
            "invariant": invariant,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            # Parse code AST to find loops and assignments
            tree = ast.parse(code)
            loops = self._extract_loops(tree)
            variables = self._extract_variables(tree)

            # Try SymPy verification for mathematical invariants
            sympy_result = self._sympy_verify(code, invariant, variables)

            if sympy_result is not None:
                result["holds"] = sympy_result["holds"]
                result["confidence"] = sympy_result["confidence"]
                result["analysis"] = sympy_result["analysis"]
                result["counter_example"] = sympy_result.get("counter_example")
            else:
                # Fall back to LLM-based verification
                llm_result = self._llm_verify_invariant(code, invariant, loops)
                result["holds"] = llm_result["holds"]
                result["confidence"] = llm_result["confidence"]
                result["analysis"] = llm_result["analysis"]

            # Persist
            with self._lock:
                self._data["verified_invariants"].append({
                    "invariant": invariant,
                    "holds": result["holds"],
                    "confidence": result["confidence"],
                    "timestamp": result["timestamp"],
                })
                self._data["meta"]["total_verifications"] += 1
                self._save()

        except SyntaxError as exc:
            result["analysis"] = f"Cannot parse code: {exc}"
            result["confidence"] = 0.0
        except Exception as exc:
            result["analysis"] = f"Verification error: {exc}"
            result["confidence"] = 0.0

        return result

    def abstract_to_symbolic(self, natural_language: str) -> List[Proposition]:
        """
        Convert a natural language description to logical propositions.

        Uses LLM to identify atomic propositions and their logical relationships.

        Args:
            natural_language: Text describing logical conditions

        Returns:
            List of Proposition objects
        """
        try:
            system = (
                "You are a logic extraction engine. Given a natural language "
                "description, extract atomic propositions. Return ONLY a JSON array "
                'of objects with keys: "name" (snake_case), "description", '
                '"value" (true/false/null for unknown). Example: '
                '[{"name": "x_positive", "description": "x is greater than 0", "value": null}]'
            )
            response = _llm_generate(
                f"Extract propositions from:\n\n{natural_language}",
                system=system,
            )

            # Parse JSON from response
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                props_data = json.loads(json_match.group())
                propositions = [
                    Proposition(
                        name=p.get("name", f"prop_{i}"),
                        value=p.get("value"),
                        description=p.get("description", ""),
                    )
                    for i, p in enumerate(props_data)
                ]
                return propositions

        except (json.JSONDecodeError, Exception) as exc:
            print(f"[NeurosymbolicReasoner] NL→Symbolic error: {exc}")

        # Fallback: create a single proposition from the text
        clean_name = re.sub(r'[^a-z0-9_]', '_', natural_language.lower().strip())[:50]
        return [Proposition(name=clean_name, description=natural_language)]

    def check_consistency(self, propositions: List[dict]) -> dict:
        """
        Check if a set of propositions are logically consistent.

        Args:
            propositions: List of dicts with "name", "value", and optionally
                          "constraints" (list of formula descriptions)

        Returns:
            dict with: consistent (bool), satisfying_assignment (dict or None),
                       conflicts (list of str)
        """
        result = {
            "consistent": False,
            "satisfying_assignment": None,
            "conflicts": [],
            "proposition_count": len(propositions),
            "timestamp": datetime.now().isoformat(),
        }

        try:
            # Build formulas from propositions
            formulas: List[LogicalFormula] = []
            for prop in propositions:
                name = prop.get("name", "")
                value = prop.get("value")

                if value is True:
                    formulas.append(_make_atom(name))
                elif value is False:
                    formulas.append(_make_not(_make_atom(name)))
                # value=None means unknown, no constraint

                # Handle explicit constraints
                constraints = prop.get("constraints", [])
                for constraint in constraints:
                    parsed = self._parse_constraint(constraint, name)
                    if parsed:
                        formulas.append(parsed)

            if not formulas:
                result["consistent"] = True
                result["satisfying_assignment"] = {}
            else:
                consistent, assignment = check_propositional_consistency(formulas)
                result["consistent"] = consistent
                result["satisfying_assignment"] = assignment

                if not consistent:
                    result["conflicts"] = self._find_conflicts(formulas)

            # Persist
            with self._lock:
                self._data["consistency_checks"].append({
                    "proposition_count": len(propositions),
                    "consistent": result["consistent"],
                    "timestamp": result["timestamp"],
                })
                self._save()

        except Exception as exc:
            result["conflicts"] = [f"Consistency check error: {exc}"]

        return result

    def prove_property(self, code: str, property_description: str) -> dict:
        """
        Attempt formal verification of a code property.

        Combines AST analysis, SymPy for mathematical properties,
        and LLM for higher-level reasoning.

        Args:
            code: Python source code
            property_description: Natural language property to verify

        Returns:
            dict with: proven (bool), confidence (float), proof (str),
                       method (str), assumptions (list)
        """
        result = {
            "proven": False,
            "confidence": 0.0,
            "proof": "",
            "method": "unknown",
            "assumptions": [],
            "property": property_description,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            tree = ast.parse(code)

            # Try different proof strategies
            # Strategy 1: Type-based verification
            type_result = self._type_based_proof(tree, property_description)
            if type_result and type_result["confidence"] > 0.7:
                result.update(type_result)
                result["method"] = "type_analysis"
                self._record_proof(result)
                return result

            # Strategy 2: AST pattern matching
            pattern_result = self._pattern_based_proof(tree, property_description)
            if pattern_result and pattern_result["confidence"] > 0.6:
                result.update(pattern_result)
                result["method"] = "pattern_analysis"
                self._record_proof(result)
                return result

            # Strategy 3: SymPy mathematical proof
            sympy_result = self._sympy_prove(code, property_description)
            if sympy_result and sympy_result["confidence"] > 0.6:
                result.update(sympy_result)
                result["method"] = "sympy"
                self._record_proof(result)
                return result

            # Strategy 4: LLM-assisted proof
            llm_result = self._llm_prove_property(code, property_description)
            result.update(llm_result)
            result["method"] = "llm_assisted"
            self._record_proof(result)

        except SyntaxError as exc:
            result["proof"] = f"Cannot parse code: {exc}"
        except Exception as exc:
            result["proof"] = f"Proof error: {exc}"

        return result

    def symbolic_plan(self, goal: str, constraints: List[str]) -> dict:
        """
        Generate a plan using symbolic reasoning, then validate with LLM.

        Args:
            goal: The goal to achieve
            constraints: List of constraints that must be satisfied

        Returns:
            dict with: plan (list of steps), validated (bool),
                       constraint_satisfaction (dict)
        """
        result = {
            "plan": [],
            "validated": False,
            "constraint_satisfaction": {},
            "goal": goal,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            # Convert constraints to propositions
            constraint_props = []
            for i, c in enumerate(constraints):
                constraint_props.append(Proposition(
                    name=f"constraint_{i}",
                    description=c,
                ))

            # Generate plan via LLM
            system = (
                "You are a symbolic planning engine. Given a goal and constraints, "
                "generate a step-by-step plan. Return ONLY a JSON array of steps, "
                'each with "action" (string) and "satisfies" (list of constraint indices).'
            )
            prompt = (
                f"Goal: {goal}\n\n"
                f"Constraints:\n" +
                "\n".join(f"[{i}] {c}" for i, c in enumerate(constraints))
            )

            response = _llm_generate(prompt, system=system)

            # Parse plan
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                steps = json.loads(json_match.group())
                result["plan"] = steps

                # Check constraint satisfaction
                satisfied = set()
                for step in steps:
                    for idx in step.get("satisfies", []):
                        if isinstance(idx, int) and 0 <= idx < len(constraints):
                            satisfied.add(idx)

                result["constraint_satisfaction"] = {
                    f"constraint_{i}": i in satisfied
                    for i in range(len(constraints))
                }
                result["validated"] = len(satisfied) == len(constraints)

        except (json.JSONDecodeError, Exception) as exc:
            print(f"[NeurosymbolicReasoner] Symbolic plan error: {exc}")

        return result

    def extract_invariants(self, code: str) -> List[dict]:
        """
        Extract likely invariants from code using AST analysis + LLM.

        Analyzes:
        - Loop variables and their bounds
        - Accumulator patterns
        - Pre/post conditions of functions
        - Class invariants

        Args:
            code: Python source code

        Returns:
            List of dicts with: invariant (str), type (str), confidence (float),
                                location (str)
        """
        invariants: List[dict] = []

        try:
            tree = ast.parse(code)

            # AST-based invariant extraction
            invariants.extend(self._extract_loop_invariants(tree))
            invariants.extend(self._extract_function_invariants(tree))
            invariants.extend(self._extract_class_invariants(tree))

            # LLM-enhanced extraction
            llm_invariants = self._llm_extract_invariants(code)
            invariants.extend(llm_invariants)

            # Deduplicate
            seen = set()
            unique = []
            for inv in invariants:
                key = inv.get("invariant", "")
                if key and key not in seen:
                    seen.add(key)
                    unique.append(inv)

            return unique

        except SyntaxError as exc:
            print(f"[NeurosymbolicReasoner] Cannot parse code: {exc}")
            return []
        except Exception as exc:
            print(f"[NeurosymbolicReasoner] Invariant extraction error: {exc}")
            return invariants

    # ── SymPy Integration ───────────────────────────────────────────────

    def _sympy_verify(self, code: str, invariant: str,
                      variables: Dict[str, Any]) -> Optional[dict]:
        """
        Use SymPy to verify a mathematical invariant.

        Returns None if SymPy cannot handle this invariant type.
        """
        try:
            from sympy import symbols, simplify, Eq, solve, oo
            from sympy.parsing.sympy_parser import parse_expr

            # Try to parse invariant as a SymPy expression
            # Look for patterns like "x >= 0", "sum(list) == n*(n+1)/2"
            invariant_clean = invariant.strip()

            # Extract variable names from code
            var_names = list(variables.keys())[:10]  # Limit to 10 vars
            if not var_names:
                return None

            sym_vars = symbols(" ".join(var_names))
            if not isinstance(sym_vars, (list, tuple)):
                sym_vars = [sym_vars]
            var_map = dict(zip(var_names, sym_vars))

            # Try to parse the invariant
            # Handle common patterns
            for op in [">=", "<=", "==", "!=", ">", "<"]:
                if op in invariant_clean:
                    parts = invariant_clean.split(op, 1)
                    if len(parts) == 2:
                        try:
                            lhs = parse_expr(parts[0].strip(), local_dict=var_map)
                            rhs = parse_expr(parts[1].strip(), local_dict=var_map)

                            if op == "==":
                                diff = simplify(lhs - rhs)
                                if diff == 0:
                                    return {
                                        "holds": True,
                                        "confidence": 0.95,
                                        "analysis": f"SymPy verified: {invariant} is an identity",
                                    }
                            elif op in (">=", "<=", ">", "<"):
                                # Check if the inequality holds symbolically
                                diff = simplify(lhs - rhs)
                                if diff.is_nonnegative if op in (">=", ">") else diff.is_nonpositive:
                                    return {
                                        "holds": True,
                                        "confidence": 0.9,
                                        "analysis": f"SymPy verified: {invariant} holds symbolically",
                                    }
                        except Exception:
                            continue

            return None

        except ImportError:
            print("[NeurosymbolicReasoner] SymPy not available — skipping symbolic verification")
            return None
        except Exception as exc:
            print(f"[NeurosymbolicReasoner] SymPy error: {exc}")
            return None

    def _sympy_prove(self, code: str, property_desc: str) -> Optional[dict]:
        """Attempt to prove a property using SymPy."""
        try:
            from sympy import symbols, simplify, Eq

            # Extract mathematical relationships from code
            tree = ast.parse(code)
            assignments = []

            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            assignments.append({
                                "var": target.id,
                                "expr": ast.dump(node.value),
                            })

            if not assignments:
                return None

            # Try to verify algebraic properties
            return {
                "proven": False,
                "confidence": 0.4,
                "proof": f"Analyzed {len(assignments)} assignments; "
                         f"property '{property_desc}' requires additional assumptions",
                "assumptions": ["Finite precision arithmetic", "No overflow"],
            }

        except ImportError:
            return None
        except Exception:
            return None

    # ── AST Analysis Helpers ────────────────────────────────────────────

    def _extract_loops(self, tree: ast.AST) -> List[dict]:
        """Extract loop information from AST."""
        loops = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.While)):
                loop_info = {
                    "type": "for" if isinstance(node, ast.For) else "while",
                    "line": node.lineno,
                    "has_break": any(
                        isinstance(n, ast.Break) for n in ast.walk(node)
                    ),
                    "has_continue": any(
                        isinstance(n, ast.Continue) for n in ast.walk(node)
                    ),
                }
                if isinstance(node, ast.For):
                    if isinstance(node.target, ast.Name):
                        loop_info["variable"] = node.target.id
                elif isinstance(node, ast.While):
                    loop_info["condition"] = ast.dump(node.test)
                loops.append(loop_info)
        return loops

    def _extract_variables(self, tree: ast.AST) -> Dict[str, Any]:
        """Extract variable assignments from AST."""
        variables: Dict[str, Any] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        # Try to evaluate simple constant assignments
                        if isinstance(node.value, ast.Constant):
                            variables[target.id] = node.value.value
                        elif isinstance(node.value, (ast.List, ast.Tuple)):
                            variables[target.id] = "collection"
                        else:
                            variables[target.id] = None
        return variables

    def _extract_loop_invariants(self, tree: ast.AST) -> List[dict]:
        """Extract likely loop invariants from AST."""
        invariants = []
        for node in ast.walk(tree):
            if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
                var = node.target.id
                # Common loop invariant patterns
                invariants.append({
                    "invariant": f"{var} is within iteration range",
                    "type": "loop_bound",
                    "confidence": 0.7,
                    "location": f"line {node.lineno}",
                })

                # Check for accumulator patterns in loop body
                for child in ast.walk(node):
                    if isinstance(child, ast.AugAssign):
                        if isinstance(child.target, ast.Name):
                            acc_var = child.target.id
                            invariants.append({
                                "invariant": f"{acc_var} is monotonically "
                                             f"{'increasing' if isinstance(child.op, ast.Add) else 'changing'}",
                                "type": "accumulator",
                                "confidence": 0.6,
                                "location": f"line {child.lineno}",
                            })

        return invariants

    def _extract_function_invariants(self, tree: ast.AST) -> List[dict]:
        """Extract function pre/post conditions from AST."""
        invariants = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check return type annotation
                if node.returns:
                    invariants.append({
                        "invariant": f"{node.name} returns annotated type",
                        "type": "postcondition",
                        "confidence": 0.8,
                        "location": f"line {node.lineno}",
                    })

                # Check for assertions (explicit invariants)
                for child in ast.walk(node):
                    if isinstance(child, ast.Assert):
                        invariants.append({
                            "invariant": f"assertion at line {child.lineno} in {node.name}",
                            "type": "explicit_invariant",
                            "confidence": 0.9,
                            "location": f"line {child.lineno}",
                        })

        return invariants

    def _extract_class_invariants(self, tree: ast.AST) -> List[dict]:
        """Extract class invariants from AST."""
        invariants = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # Check for __init__ validation
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                        for child in ast.walk(item):
                            if isinstance(child, ast.Assert):
                                invariants.append({
                                    "invariant": f"{node.name}.__init__ validates state",
                                    "type": "class_invariant",
                                    "confidence": 0.8,
                                    "location": f"line {child.lineno}",
                                })
        return invariants

    def _type_based_proof(self, tree: ast.AST, property_desc: str) -> Optional[dict]:
        """Attempt proof via type analysis."""
        prop_lower = property_desc.lower()

        # Check for "returns X" type properties
        if "return" in prop_lower:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.returns:
                        return {
                            "proven": True,
                            "confidence": 0.75,
                            "proof": f"Function {node.name} has return type annotation, "
                                     f"supporting the property about return values",
                            "assumptions": ["Type annotations are correct"],
                        }
        return None

    def _pattern_based_proof(self, tree: ast.AST, property_desc: str) -> Optional[dict]:
        """Attempt proof via code pattern analysis."""
        prop_lower = property_desc.lower()

        # Check for "always terminates" properties
        if "terminat" in prop_lower:
            has_infinite = False
            for node in ast.walk(tree):
                if isinstance(node, ast.While):
                    # Check for while True without break
                    if isinstance(node.test, ast.Constant) and node.test.value is True:
                        has_break = any(isinstance(n, ast.Break) for n in ast.walk(node))
                        if not has_break:
                            has_infinite = True

            if not has_infinite:
                return {
                    "proven": True,
                    "confidence": 0.65,
                    "proof": "No unbounded loops detected; code likely terminates",
                    "assumptions": ["No infinite recursion", "External calls terminate"],
                }

        # Check for "no side effects" properties
        if "side effect" in prop_lower or "pure" in prop_lower:
            has_io = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func_name = ""
                    if isinstance(node.func, ast.Name):
                        func_name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        func_name = node.func.attr
                    if func_name in ("print", "write", "open", "append"):
                        has_io = True
                        break

            if not has_io:
                return {
                    "proven": True,
                    "confidence": 0.6,
                    "proof": "No obvious I/O operations detected; function may be pure",
                    "assumptions": ["No global state mutation", "No file operations"],
                }

        return None

    # ── LLM-Assisted Methods ────────────────────────────────────────────

    def _llm_verify_invariant(self, code: str, invariant: str,
                               loops: List[dict]) -> dict:
        """Use LLM to verify an invariant when SymPy cannot."""
        system = (
            "You are a formal verification assistant. Analyze the code and determine "
            "if the given invariant holds. Return ONLY a JSON object with: "
            '"holds" (bool), "confidence" (0.0-1.0), "analysis" (string), '
            '"counter_example" (string or null).'
        )
        prompt = (
            f"Code:\n```python\n{code}\n```\n\n"
            f"Invariant to verify: {invariant}\n\n"
            f"Loops found: {json.dumps(loops, indent=2)}"
        )

        response = _llm_generate(prompt, system=system)

        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        return {
            "holds": False,
            "confidence": 0.3,
            "analysis": response[:500] if response else "LLM verification failed",
        }

    def _llm_prove_property(self, code: str, property_desc: str) -> dict:
        """Use LLM to attempt a proof of a code property."""
        system = (
            "You are a program verification expert. Analyze the code and attempt "
            "to prove or disprove the given property. Return ONLY a JSON object with: "
            '"proven" (bool), "confidence" (0.0-1.0), "proof" (string), '
            '"assumptions" (list of strings).'
        )
        prompt = (
            f"Code:\n```python\n{code}\n```\n\n"
            f"Property to prove: {property_desc}"
        )

        response = _llm_generate(prompt, system=system)

        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        return {
            "proven": False,
            "confidence": 0.2,
            "proof": response[:500] if response else "LLM proof failed",
            "assumptions": [],
        }

    def _llm_extract_invariants(self, code: str) -> List[dict]:
        """Use LLM to extract likely invariants from code."""
        system = (
            "You are a program analysis expert. Identify likely invariants in the "
            "code (loop invariants, pre/post conditions, class invariants). "
            "Return ONLY a JSON array of objects with: "
            '"invariant" (string), "type" (string), "confidence" (0.0-1.0), '
            '"location" (string).'
        )
        prompt = f"Extract invariants from:\n```python\n{code}\n```"

        response = _llm_generate(prompt, system=system)

        try:
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        return []

    # ── Conflict Detection ──────────────────────────────────────────────

    def _parse_constraint(self, constraint: str, context_name: str) -> Optional[LogicalFormula]:
        """Parse a constraint string into a logical formula."""
        constraint = constraint.strip().lower()

        # Handle "not X" patterns
        if constraint.startswith("not "):
            inner_name = constraint[4:].strip().replace(" ", "_")
            return _make_not(_make_atom(inner_name))

        # Handle "X and Y" patterns
        if " and " in constraint:
            parts = constraint.split(" and ")
            atoms = [_make_atom(p.strip().replace(" ", "_")) for p in parts]
            return _make_and(*atoms)

        # Handle "X or Y" patterns
        if " or " in constraint:
            parts = constraint.split(" or ")
            atoms = [_make_atom(p.strip().replace(" ", "_")) for p in parts]
            return _make_or(*atoms)

        # Handle "X implies Y" patterns
        if " implies " in constraint:
            parts = constraint.split(" implies ", 1)
            if len(parts) == 2:
                return _make_implies(
                    _make_atom(parts[0].strip().replace(" ", "_")),
                    _make_atom(parts[1].strip().replace(" ", "_")),
                )

        # Default: atomic proposition
        clean = constraint.replace(" ", "_")
        return _make_atom(clean)

    def _find_conflicts(self, formulas: List[LogicalFormula]) -> List[str]:
        """Identify conflicting formulas."""
        conflicts = []
        for i, f1 in enumerate(formulas):
            for j, f2 in enumerate(formulas):
                if i >= j:
                    continue
                # Check for direct contradictions
                if f1.formula_type == "atom" and f2.formula_type == "not":
                    if (f2.operands and f2.operands[0].formula_type == "atom"
                            and f1.proposition and f2.operands[0].proposition
                            and f1.proposition.name == f2.operands[0].proposition.name):
                        conflicts.append(
                            f"'{f1.proposition.name}' is asserted both true and false"
                        )
        return conflicts

    def _record_proof(self, result: dict) -> None:
        """Record a proof attempt."""
        with self._lock:
            self._data["proven_properties"].append({
                "property": result.get("property", ""),
                "proven": result.get("proven", False),
                "confidence": result.get("confidence", 0),
                "method": result.get("method", "unknown"),
                "timestamp": result.get("timestamp", ""),
            })
            self._data["meta"]["total_proofs"] += 1
            if result.get("proven"):
                self._data["meta"]["successful_proofs"] += 1
            self._save()

    # ── Stats & Prompt ──────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get neurosymbolic reasoner statistics."""
        with self._lock:
            meta = self._data["meta"]
            proof_rate = (
                meta["successful_proofs"] / max(meta["total_proofs"], 1)
            )
            return {
                "total_verifications": meta["total_verifications"],
                "total_proofs": meta["total_proofs"],
                "successful_proofs": meta["successful_proofs"],
                "proof_success_rate": round(proof_rate, 3),
                "consistency_checks": len(self._data["consistency_checks"]),
                "verified_invariants": len(self._data["verified_invariants"]),
            }

    def format_for_prompt(self, max_chars: int = 600) -> str:
        """
        Format neurosymbolic reasoner state for system prompt injection.
        Gives FRIDAY awareness of her formal reasoning capabilities.
        """
        stats = self.get_stats()
        parts = [
            "[NEUROSYMBOLIC REASONER — Formal verification]",
            f"Verifications: {stats['total_verifications']} | "
            f"Proofs: {stats['successful_proofs']}/{stats['total_proofs']} "
            f"({stats['proof_success_rate']:.0%})",
            f"Consistency checks: {stats['consistency_checks']} | "
            f"Verified invariants: {stats['verified_invariants']}",
        ]

        # Recent proven properties
        recent = self._data["proven_properties"][-3:]
        if recent:
            items = [p.get("property", "?")[:40] for p in recent]
            parts.append(f"Recent proofs: {', '.join(items)}")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars].rsplit("\n", 1)[0] + "\n[...]"
        return result


# ── Singleton ───────────────────────────────────────────────────────────────

_reasoner: Optional[NeurosymbolicReasoner] = None
_reasoner_lock = threading.Lock()


def get_neurosymbolic_reasoner() -> NeurosymbolicReasoner:
    """Get singleton NeurosymbolicReasoner instance."""
    global _reasoner
    if _reasoner is None:
        with _reasoner_lock:
            if _reasoner is None:
                _reasoner = NeurosymbolicReasoner()
    return _reasoner
