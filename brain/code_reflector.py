#!/usr/bin/env python3
"""
code_reflector.py — FRIDAY Cognitive Code Reflector
====================================================

Failure analysis, root-cause trees, and procedural learning from
coding sessions. This is the "reflection" layer of the Cognitive
Coding Engine — learning from mistakes like an expert programmer.

Inspired by human debugging cognition:
- Root-cause analysis: trace errors back through causal chains
- Failure replay: re-examine past failures with new knowledge
- Pattern extraction: distill reusable lessons from debugging sessions
- Hypothesis ranking: rank likely causes by probability
- Procedural update: convert debugging insights into reusable procedures

Architecture:
  Error → [Classify] → [Root Cause Tree] → [Hypotheses] → [Rank]
        → [Fix Strategy] → [Execute] → [Verify] → [Learn]
"""

import json
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple



BRAIN_DIR = Path(__file__).parent.resolve()
REFLECTION_DB_FILE = BRAIN_DIR / "code_reflections.json"
FAILURE_PATTERNS_FILE = BRAIN_DIR / "code_failure_patterns.json"

API_CONFIG_PATH = BRAIN_DIR.parent / "config" / "api_keys.json"
REFLECTOR_MODEL = "gemini-2.5-flash"


class FailurePattern:
    """A learned failure pattern with fix strategy."""

    def __init__(self, pattern_id: str, error_type: str, root_cause: str,
                 fix_strategy: str, confidence: float = 0.5):
        self.pattern_id = pattern_id
        self.error_type = error_type
        self.root_cause = root_cause
        self.fix_strategy = fix_strategy
        self.confidence = confidence
        self.seen_count = 0
        self.fix_success_count = 0
        self.last_seen = datetime.now().isoformat()
        self.examples: List[dict] = []

    def to_dict(self) -> dict:
        return {
            "pattern_id": self.pattern_id,
            "error_type": self.error_type,
            "root_cause": self.root_cause,
            "fix_strategy": self.fix_strategy,
            "confidence": self.confidence,
            "seen_count": self.seen_count,
            "fix_success_count": self.fix_success_count,
            "last_seen": self.last_seen,
            "examples": self.examples[-5:],  # Keep last 5 examples
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FailurePattern":
        p = cls(
            pattern_id=data["pattern_id"],
            error_type=data["error_type"],
            root_cause=data["root_cause"],
            fix_strategy=data["fix_strategy"],
            confidence=data.get("confidence", 0.5),
        )
        p.seen_count = data.get("seen_count", 0)
        p.fix_success_count = data.get("fix_success_count", 0)
        p.last_seen = data.get("last_seen", p.last_seen)
        p.examples = data.get("examples", [])
        return p

    @property
    def fix_success_rate(self) -> float:
        return self.fix_success_count / max(self.seen_count, 1)


class ReflectionEntry:
    """A debugging reflection session."""

    def __init__(self, reflection_id: str, error_output: str, code_context: str,
                 root_causes: List[dict], fix_applied: str, success: bool,
                 lessons: List[str]):
        self.reflection_id = reflection_id
        self.error_output = error_output
        self.code_context = code_context
        self.root_causes = root_causes
        self.fix_applied = fix_applied
        self.success = success
        self.lessons = lessons
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "reflection_id": self.reflection_id,
            "error_output": self.error_output[:500],
            "code_context": self.code_context[:300],
            "root_causes": self.root_causes,
            "fix_applied": self.fix_applied[:300],
            "success": self.success,
            "lessons": self.lessons,
            "timestamp": self.timestamp,
        }


class CodeReflector:
    """
    Cognitive code reflection engine.

    Provides:
    1. Root-cause analysis: trace errors through causal chains
    2. Hypothesis generation: rank likely causes by probability
    3. Failure pattern learning: build a library of known bugs + fixes
    4. Debugging strategy selection: pick the best approach for each error type
    5. Procedural learning: convert debugging sessions into reusable knowledge
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._patterns: Dict[str, FailurePattern] = {}
        self._reflections: List[ReflectionEntry] = []
        self._client = None
        self._load()

    def _get_client(self):
        if self._client is None:
            try:
                key = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
                api_key = key.get("gemini_api_key", key.get("GOOGLE_API_KEY", ""))
                from google import genai
                self._client = genai.Client(api_key=api_key)
            except Exception:
                pass
        return self._client

    def _generate(self, prompt: str, system: str = "") -> str:
        client = self._get_client()
        if not client:
            return ""
        try:
            from google.genai import types as genai_types
            config = genai_types.GenerateContentConfig(
                system_instruction=system if system else None,
                max_output_tokens=1536,
            )
            response = client.models.generate_content(
                model=REFLECTOR_MODEL,
                contents=prompt,
                config=config if system else None,
            )
            return response.text.strip()
        except Exception as e:
            print(f"[CodeReflector] Generation error: {e}")
            return ""

    def _load(self):
        """Load failure patterns and reflections."""
        if FAILURE_PATTERNS_FILE.exists():
            try:
                data = json.loads(FAILURE_PATTERNS_FILE.read_text(encoding="utf-8"))
                for p in data.get("patterns", []):
                    pattern = FailurePattern.from_dict(p)
                    self._patterns[pattern.pattern_id] = pattern
                print(f"[CodeReflector] Loaded {len(self._patterns)} failure patterns")
            except Exception as e:
                print(f"[CodeReflector] Load error: {e}")

        if REFLECTION_DB_FILE.exists():
            try:
                data = json.loads(REFLECTION_DB_FILE.read_text(encoding="utf-8"))
                for r in data.get("reflections", []):
                    entry = ReflectionEntry(
                        reflection_id=r["reflection_id"],
                        error_output=r.get("error_output", ""),
                        code_context=r.get("code_context", ""),
                        root_causes=r.get("root_causes", []),
                        fix_applied=r.get("fix_applied", ""),
                        success=r.get("success", False),
                        lessons=r.get("lessons", []),
                    )
                    self._reflections.append(entry)
            except Exception:
                pass

    def _save(self):
        """Persist patterns and reflections."""
        with self._lock:
            try:
                BRAIN_DIR.mkdir(parents=True, exist_ok=True)
                FAILURE_PATTERNS_FILE.write_text(json.dumps({
                    "patterns": [p.to_dict() for p in self._patterns.values()],
                    "updated": datetime.now().isoformat(),
                }, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                print(f"[CodeReflector] Pattern save error: {e}")

            try:
                REFLECTION_DB_FILE.write_text(json.dumps({
                    "reflections": [r.to_dict() for r in self._reflections[-500:]],
                    "updated": datetime.now().isoformat(),
                }, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                print(f"[CodeReflector] Reflection save error: {e}")

    # ── Root Cause Analysis ─────────────────────────────────────────────

    def analyze_failure(self, error_output: str, code: str,
                        language: str = "python",
                        context: str = "") -> dict:
        """
        Analyze a code failure and generate ranked root-cause hypotheses.

        Returns:
        - error_type: classified error type
        - root_causes: ranked list of likely causes
        - fix_strategies: suggested fixes for each cause
        - similar_past_failures: matching patterns from history
        """
        # Step 1: Check known failure patterns first (fast)
        matched_patterns = self._match_known_patterns(error_output, code)

        # Step 2: LLM-based root cause analysis
        system = """You are an expert debugging psychologist — you understand HOW programmers think and WHERE they make mistakes.
Analyze the error and provide root-cause hypotheses ranked by probability.

Return ONLY valid JSON:
{
  "error_type": "syntax|runtime|logic|import|type|name|index|key|permission|connection|timeout",
  "root_causes": [
    {
      "cause": "explanation",
      "probability": 0.0-1.0,
      "category": "typo|logic|missing_import|wrong_api|off_by_one|type_mismatch|race_condition|resource_leak|config|env",
      "evidence": "what in the error/code suggests this"
    }
  ],
  "fix_strategies": [
    {
      "for_cause": "cause index (0-based)",
      "strategy": "what to do",
      "confidence": 0.0-1.0,
      "steps": ["step 1", "step 2"]
    }
  ],
  "debugging_approach": "systematic|binary_search|print_trace|rubber_duck|backtrace",
  "estimated_fix_time": "minutes",
  "learning_potential": "what general lesson can be extracted"
}"""

        truncated_code = code[:5000] if len(code) > 5000 else code
        prompt = f"""Language: {language}
{f'Context: {context[:500]}' if context else ''}

Error output:
{error_output[:2000]}

Code:
```{language}
{truncated_code}
```

Analyze this failure. What are the most likely root causes?"""

        result = self._generate(prompt, system=system)

        try:
            json_str = result
            if "```" in json_str:
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            analysis = json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            analysis = {
                "error_type": "unknown",
                "root_causes": [{"cause": "Could not determine", "probability": 0.3, "category": "unknown", "evidence": ""}],
                "fix_strategies": [],
                "debugging_approach": "systematic",
                "estimated_fix_time": "unknown",
                "learning_potential": "",
            }

        # Merge known pattern matches
        if matched_patterns:
            analysis["known_patterns"] = matched_patterns
            analysis["has_known_fix"] = any(
                p.get("fix_success_rate", 0) > 0.6 for p in matched_patterns
            )

        return analysis

    def _match_known_patterns(self, error_output: str, code: str) -> List[dict]:
        """Match error against known failure patterns."""
        matched = []
        error_lower = error_output.lower()

        with self._lock:
            for pattern in self._patterns.values():
                # Check if error type matches
                if pattern.error_type and pattern.error_type in error_lower:
                    # Check root cause keywords in code
                    cause_keywords = pattern.root_cause.lower().split()[:5]
                    code_lower = code.lower()
                    if any(kw in code_lower for kw in cause_keywords if len(kw) > 3):
                        matched.append({
                            "pattern_id": pattern.pattern_id,
                            "error_type": pattern.error_type,
                            "root_cause": pattern.root_cause,
                            "fix_strategy": pattern.fix_strategy,
                            "confidence": pattern.confidence,
                            "fix_success_rate": pattern.fix_success_rate,
                            "seen_count": pattern.seen_count,
                        })

        matched.sort(key=lambda x: x["confidence"] * x["fix_success_rate"], reverse=True)
        return matched[:3]

    # ── Hypothesis Ranking ──────────────────────────────────────────────

    def rank_hypotheses(self, hypotheses: List[dict], error_output: str,
                        code: str) -> List[dict]:
        """
        Rank debugging hypotheses by probability.
        Combines LLM reasoning with historical pattern matching.
        """
        if not hypotheses:
            return []

        # Boost hypotheses that match known patterns
        for h in hypotheses:
            h["base_probability"] = h.get("probability", 0.5)

            # Check if this matches a known failure pattern
            cause_lower = h.get("cause", "").lower()
            with self._lock:
                for pattern in self._patterns.values():
                    if pattern.error_type in error_output.lower():
                        pattern_keywords = pattern.root_cause.lower().split()
                        if any(kw in cause_lower for kw in pattern_keywords if len(kw) > 3):
                            # Boost based on historical success rate
                            boost = pattern.fix_success_rate * 0.3
                            h["probability"] = min(1.0, h["base_probability"] + boost)
                            h["historical_match"] = pattern.pattern_id
                            break

        # Sort by probability
        hypotheses.sort(key=lambda x: x.get("probability", 0), reverse=True)
        return hypotheses

    # ── Fix Strategy Selection ──────────────────────────────────────────

    def select_fix_strategy(self, analysis: dict, code: str,
                            language: str = "python") -> dict:
        """
        Select the best fix strategy based on root cause analysis.
        Returns a concrete, actionable fix plan.
        """
        root_causes = analysis.get("root_causes", [])
        fix_strategies = analysis.get("fix_strategies", [])
        known_patterns = analysis.get("known_patterns", [])

        # If we have a known pattern with high success rate, use it
        if known_patterns:
            best_pattern = max(known_patterns, key=lambda p: p.get("fix_success_rate", 0))
            if best_pattern.get("fix_success_rate", 0) > 0.6:
                return {
                    "strategy": "known_pattern_fix",
                    "fix": best_pattern["fix_strategy"],
                    "confidence": best_pattern["confidence"] * best_pattern["fix_success_rate"],
                    "source": f"Pattern {best_pattern['pattern_id']}",
                    "steps": [best_pattern["fix_strategy"]],
                }

        # Otherwise, use the top-ranked root cause and its fix strategy
        if root_causes and fix_strategies:
            top_cause = root_causes[0]
            matching_fix = next(
                (f for f in fix_strategies if str(f.get("for_cause", "")) == "0"),
                fix_strategies[0] if fix_strategies else None,
            )

            if matching_fix:
                return {
                    "strategy": "llm_reasoning",
                    "fix": matching_fix.get("strategy", ""),
                    "confidence": matching_fix.get("confidence", 0.5) * top_cause.get("probability", 0.5),
                    "source": "Root cause analysis",
                    "steps": matching_fix.get("steps", []),
                    "root_cause": top_cause.get("cause", ""),
                }

        return {
            "strategy": "manual_review",
            "fix": "Manual review needed — could not determine automatic fix",
            "confidence": 0.2,
            "source": "Fallback",
            "steps": ["Read the error carefully", "Check recent changes", "Add print statements"],
        }

    # ── Failure Pattern Learning ────────────────────────────────────────

    def learn_from_session(self, error_output: str, code: str, fix_applied: str,
                           success: bool, language: str = "python",
                           lessons: List[str] = None):
        """
        Learn from a debugging session — store the failure pattern and fix.
        This builds FRIDAY's debugging expertise over time.
        """
        # Extract error type
        error_type = self._classify_error(error_output)

        # Generate pattern ID from error signature
        sig = f"{error_type}:{error_output[:100]}"
        pattern_id = f"fp_{hash(sig) % 100000:05d}"

        with self._lock:
            if pattern_id in self._patterns:
                # Update existing pattern
                pattern = self._patterns[pattern_id]
                pattern.seen_count += 1
                if success:
                    pattern.fix_success_count += 1
                pattern.last_seen = datetime.now().isoformat()
                pattern.examples.append({
                    "error": error_output[:200],
                    "fix": fix_applied[:200],
                    "success": success,
                    "timestamp": datetime.now().isoformat(),
                })
                if len(pattern.examples) > 10:
                    pattern.examples = pattern.examples[-10:]
            else:
                # Create new pattern
                pattern = FailurePattern(
                    pattern_id=pattern_id,
                    error_type=error_type,
                    root_cause=error_output[:200],
                    fix_strategy=fix_applied[:200],
                    confidence=0.5 if success else 0.3,
                )
                pattern.seen_count = 1
                if success:
                    pattern.fix_success_count = 1
                pattern.examples.append({
                    "error": error_output[:200],
                    "fix": fix_applied[:200],
                    "success": success,
                    "timestamp": datetime.now().isoformat(),
                })
                self._patterns[pattern_id] = pattern

            self._save()

        # Create reflection entry
        reflection_id = f"ref_{uuid.uuid4().hex[:8]}"
        entry = ReflectionEntry(
            reflection_id=reflection_id,
            error_output=error_output,
            code_context=code[:500],
            root_causes=[{"cause": error_output[:100], "type": error_type}],
            fix_applied=fix_applied,
            success=success,
            lessons=lessons or [],
        )

        with self._lock:
            self._reflections.append(entry)
            if len(self._reflections) > 500:
                self._reflections = self._reflections[-500:]

        # Also record in learning engine
        try:
            from brain.learning import get_learning_engine
            le = get_learning_engine()
            if success:
                le.write_evolution_learning(
                    f"Debugging: {error_type} fixed by {fix_applied[:100]}",
                    domain="debugging",
                )
            else:
                le.record_event("tool_failure", {
                    "tool": "code_debugger",
                    "context": error_type,
                    "error": error_output[:200],
                })
        except Exception:
            pass

        # Learn procedure if fix was successful
        if success:
            try:
                from brain.procedural_memory import get_procedural_memory
                pm = get_procedural_memory()
                pm.learn_procedure(
                    goal=f"fix {error_type} error",
                    steps=[
                        {"tool": "code_simulator", "description": "detect anomalies"},
                        {"tool": "code_reflector", "description": "analyze root cause"},
                        {"tool": "code_helper", "description": "apply fix"},
                        {"tool": "code_helper", "description": "verify fix"},
                    ],
                    context={"error_type": error_type},
                )
            except Exception:
                pass

        return reflection_id

    def _classify_error(self, error_output: str) -> str:
        """Classify error type from output."""
        low = error_output.lower()
        classifications = [
            ("syntaxerror", "syntax"), ("modulenotfounderror", "import"),
            ("importerror", "import"), ("nameerror", "name"),
            ("typeerror", "type"), ("attributeerror", "attribute"),
            ("valueerror", "value"), ("keyerror", "key"),
            ("indexerror", "index"), ("filenotfounderror", "file"),
            ("permissionerror", "permission"), ("zerodivisionerror", "zero_division"),
            ("recursionerror", "recursion"), ("timeouterror", "timeout"),
            ("connectionerror", "connection"), ("memoryerror", "memory"),
            ("oserror", "os"), ("runtimeerror", "runtime"),
        ]
        for keyword, error_type in classifications:
            if keyword in low:
                return error_type
        return "unknown"

    # ── Failure Replay ──────────────────────────────────────────────────

    def replay_failures(self, error_type: str = "", limit: int = 10) -> List[dict]:
        """
        Replay past failures for review — useful for learning from patterns.
        """
        with self._lock:
            reflections = self._reflections
            if error_type:
                reflections = [
                    r for r in reflections
                    if any(error_type in rc.get("type", "") for rc in r.root_causes)
                ]

            recent = reflections[-limit:]
            return [{
                "id": r.reflection_id,
                "error": r.error_output[:200],
                "fix": r.fix_applied[:200],
                "success": r.success,
                "lessons": r.lessons,
                "timestamp": r.timestamp,
            } for r in recent]

    def get_failure_patterns(self, top_k: int = 10) -> List[dict]:
        """Get the most common failure patterns."""
        with self._lock:
            patterns = sorted(
                self._patterns.values(),
                key=lambda p: p.seen_count * p.fix_success_rate,
                reverse=True,
            )[:top_k]
            return [p.to_dict() for p in patterns]

    # ── Debugging Strategy ──────────────────────────────────────────────

    def suggest_debugging_approach(self, error_type: str, complexity: str = "medium") -> dict:
        """
        Suggest a debugging approach based on error type and complexity.
        """
        strategies = {
            "syntax": {
                "approach": "line_by_line",
                "steps": ["Read the error line", "Check brackets/indentation", "Verify syntax"],
                "tools": ["code_helper"],
            },
            "import": {
                "approach": "dependency_check",
                "steps": ["Check module name", "Verify installation", "Check sys.path"],
                "tools": ["code_helper", "web_search"],
            },
            "type": {
                "approach": "type_trace",
                "steps": ["Print variable types", "Check function signatures", "Verify data flow"],
                "tools": ["code_helper", "code_simulator"],
            },
            "name": {
                "approach": "scope_trace",
                "steps": ["Check variable scope", "Verify imports", "Check for typos"],
                "tools": ["code_helper"],
            },
            "runtime": {
                "approach": "binary_search",
                "steps": ["Add print statements", "Narrow down the failing section", "Check edge cases"],
                "tools": ["code_helper", "code_simulator"],
            },
            "logic": {
                "approach": "test_driven",
                "steps": ["Write test cases", "Identify expected vs actual", "Trace logic flow"],
                "tools": ["code_helper", "code_simulator"],
            },
            "timeout": {
                "approach": "performance_analysis",
                "steps": ["Profile the code", "Identify bottlenecks", "Check for infinite loops"],
                "tools": ["code_helper", "code_simulator"],
            },
            "connection": {
                "approach": "network_check",
                "steps": ["Verify URL/endpoint", "Check network connectivity", "Check authentication"],
                "tools": ["code_helper", "web_search"],
            },
        }

        strategy = strategies.get(error_type, strategies["runtime"])

        if complexity == "high":
            strategy["steps"].insert(0, "Break the problem into smaller parts")
            strategy["steps"].append("Consider using a debugger (pdb)")

        return strategy

    # ── Statistics ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get reflection statistics."""
        with self._lock:
            total_patterns = len(self._patterns)
            total_reflections = len(self._reflections)
            successful = sum(1 for r in self._reflections if r.success)

            error_types = defaultdict(int)
            for p in self._patterns.values():
                error_types[p.error_type] += p.seen_count

            return {
                "total_patterns": total_patterns,
                "total_reflections": total_reflections,
                "successful_fixes": successful,
                "fix_rate": round(successful / max(total_reflections, 1), 2),
                "top_error_types": dict(sorted(error_types.items(), key=lambda x: -x[1])[:5]),
            }

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """Format reflector state for system prompt injection."""
        stats = self.get_stats()
        parts = [
            "[CODE REFLECTOR — Debugging knowledge base]",
            f"Patterns: {stats['total_patterns']} learned | "
            f"Fix rate: {stats['fix_rate']:.0%} | "
            f"Reflections: {stats['total_reflections']}",
        ]

        if stats.get("top_error_types"):
            types_str = ", ".join(f"{t}({c})" for t, c in list(stats["top_error_types"].items())[:3])
            parts.append(f"Common errors: {types_str}")

        result = "\n".join(parts)
        return result[:max_chars]


# ── Singleton ───────────────────────────────────────────────────────────

_code_reflector = None
_cr_lock = threading.Lock()


def get_code_reflector() -> CodeReflector:
    """Get singleton CodeReflector instance."""
    global _code_reflector
    if _code_reflector is None:
        with _cr_lock:
            if _code_reflector is None:
                _code_reflector = CodeReflector()
    return _code_reflector