#!/usr/bin/env python3
"""
code_simulator.py — FRIDAY Predictive Code Simulator
======================================================

Mental execution sandbox for code — simulates code paths before writing
or running them, predicts errors, and detects anomalies.

Inspired by expert programmer cognition:
- Mental stack traces: predict state changes forward/backward
- Off-by-one detection: pattern mismatch in loop bounds
- Type inference: predict variable types through data flow
- Anomaly detection: flag patterns that historically cause bugs

Architecture:
  Code → [Parse] → AST → [Simulate] → Predicted State → [Anomaly Check]
       → Predictions (success/failure, output, errors, side effects)
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
from typing import Dict, List, Optional, Tuple



BRAIN_DIR = Path(__file__).parent.resolve()
ANOMALY_DB_FILE = BRAIN_DIR / "code_anomaly_db.json"
SIMULATION_LOG_FILE = BRAIN_DIR / "code_sim_log.jsonl"

API_CONFIG_PATH = BRAIN_DIR.parent / "config" / "api_keys.json"
SIMULATOR_MODEL = "gemini-2.5-flash"

# ── Known Bug Patterns (from expert programmer heuristics) ──────────────
BUG_PATTERNS = {
    "off_by_one": {
        "signals": ["range(len(", "while i <=", "for i in range(1, len(", "- 1)", "+ 1)"],
        "description": "Potential off-by-one error in loop bounds",
        "severity": "medium",
    },
    "mutable_default": {
        "signals": ["def .*\\(.*=[]", "def .*\\(.*={}"],
        "description": "Mutable default argument — shared across calls",
        "severity": "high",
        "regex": True,
    },
    "bare_except": {
        "signals": ["except:", "except Exception:"],
        "description": "Overly broad exception handling — hides bugs",
        "severity": "medium",
    },
    "unbounded_recursion": {
        "signals": ["def .*\\(.*\\):.*\\1\\(", "recursive", "call_stack"],
        "description": "Potential unbounded recursion without base case check",
        "severity": "high",
    },
    "race_condition": {
        "signals": ["threading", "global ", "lock", "shared_state"],
        "description": "Shared mutable state in concurrent context",
        "severity": "high",
    },
    "resource_leak": {
        "signals": ["open(", "connect(", "acquire("],
        "description": "Resource opened without context manager (with statement)",
        "severity": "medium",
        "anti_signals": ["with ", "as "],
    },
    "sql_injection": {
        "signals": ["f\".*SELECT", "f\".*INSERT", "f\".*DELETE", "f\".*UPDATE",
                    "format.*SELECT", "format.*INSERT", "%.*SELECT"],
        "description": "Potential SQL injection via string formatting",
        "severity": "critical",
    },
    "hardcoded_secret": {
        "signals": ["password=", "api_key=", "secret=", "token="],
        "description": "Hardcoded credentials or secrets",
        "severity": "critical",
        "anti_signals": ["os.environ", "getenv", "config[", "secret_"],
    },
    "type_confusion": {
        "signals": ["isinstance", "type("],
        "description": "Type checking present — possible type confusion area",
        "severity": "low",
    },
    "unused_variable": {
        "signals": ["= ", "assigned but never used"],
        "description": "Variable assigned but potentially unused",
        "severity": "low",
    },
    "blocking_call_in_async": {
        "signals": ["async def", "await", "time.sleep(", "requests.get("],
        "description": "Blocking call in async function — will block event loop",
        "severity": "high",
    },
    "infinite_loop": {
        "signals": ["while True:", "while 1:"],
        "description": "Infinite loop — ensure proper break/exit condition",
        "severity": "medium",
        "anti_signals": ["break", "return", "sys.exit"],
    },
    "unhandled_none": {
        "signals": ["\\.get\\(", "\\.find\\(", "Optional"],
        "description": "Possible None value not checked before use",
        "severity": "medium",
    },
}


class AnomalyRecord:
    """A detected code anomaly with context."""

    def __init__(self, anomaly_id: str, pattern: str, file_path: str,
                 line: int, description: str, severity: str,
                 confidence: float, suggestion: str = ""):
        self.anomaly_id = anomaly_id
        self.pattern = pattern
        self.file_path = file_path
        self.line = line
        self.description = description
        self.severity = severity
        self.confidence = confidence
        self.suggestion = suggestion
        self.detected_at = datetime.now().isoformat()
        self.resolved = False

    def to_dict(self) -> dict:
        return {
            "anomaly_id": self.anomaly_id,
            "pattern": self.pattern,
            "file_path": self.file_path,
            "line": self.line,
            "description": self.description,
            "severity": self.severity,
            "confidence": self.confidence,
            "suggestion": self.suggestion,
            "detected_at": self.detected_at,
            "resolved": self.resolved,
        }


class CodeSimulator:
    """
    Predictive code simulation engine.

    Provides:
    1. Mental execution: simulate code paths without running code
    2. Anomaly detection: flag known bug patterns
    3. Type inference: predict variable types through data flow
    4. Error prediction: predict likely runtime errors
    5. Simulation history: learn from past predictions
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._anomalies: Dict[str, AnomalyRecord] = {}
        self._simulation_history: List[dict] = []
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
                model=SIMULATOR_MODEL,
                contents=prompt,
                config=config,
            )
            return response.text.strip()
        except Exception as e:
            print(f"[CodeSim] Generation error: {e}")
            return ""

    def _load(self):
        if ANOMALY_DB_FILE.exists():
            try:
                data = json.loads(ANOMALY_DB_FILE.read_text(encoding="utf-8"))
                for a in data.get("anomalies", []):
                    record = AnomalyRecord(
                        anomaly_id=a["anomaly_id"],
                        pattern=a["pattern"],
                        file_path=a["file_path"],
                        line=a.get("line", 0),
                        description=a["description"],
                        severity=a["severity"],
                        confidence=a.get("confidence", 0.5),
                        suggestion=a.get("suggestion", ""),
                    )
                    record.resolved = a.get("resolved", False)
                    self._anomalies[record.anomaly_id] = record
            except Exception:
                pass

    def _save_anomalies(self):
        with self._lock:
            try:
                BRAIN_DIR.mkdir(parents=True, exist_ok=True)
                ANOMALY_DB_FILE.write_text(json.dumps({
                    "anomalies": [a.to_dict() for a in self._anomalies.values()],
                    "updated": datetime.now().isoformat(),
                }, indent=2), encoding="utf-8")
            except Exception:
                pass

    # ── Anomaly Detection (Pattern-Based) ───────────────────────────────

    def detect_anomalies(self, code: str, file_path: str = "",
                         language: str = "python") -> List[dict]:
        """
        Scan code for known bug patterns.
        Fast, rule-based — runs before LLM simulation.
        """
        anomalies = []
        lines = code.splitlines()

        for pattern_name, pattern_info in BUG_PATTERNS.items():
            signals = pattern_info["signals"]
            anti_signals = pattern_info.get("anti_signals", [])
            severity = pattern_info["severity"]
            description = pattern_info["description"]
            is_regex = pattern_info.get("regex", False)

            for i, line in enumerate(lines, 1):
                line_stripped = line.strip()
                if not line_stripped or line_stripped.startswith("#"):
                    continue

                matched = False
                if is_regex:
                    for sig in signals:
                        try:
                            if re.search(sig, line):
                                matched = True
                                break
                        except re.error:
                            pass
                else:
                    matched = any(sig in line for sig in signals)

                if not matched:
                    continue

                # Check anti-signals (patterns that indicate it's actually safe)
                if anti_signals:
                    has_anti = any(anti in line for anti in anti_signals)
                    # Also check nearby lines (±3)
                    if not has_anti:
                        context_start = max(0, i - 4)
                        context_end = min(len(lines), i + 3)
                        context = "\n".join(lines[context_start:context_end])
                        has_anti = any(anti in context for anti in anti_signals)
                    if has_anti:
                        continue

                # Confidence based on severity and context
                confidence = {"critical": 0.9, "high": 0.75, "medium": 0.6, "low": 0.4}.get(severity, 0.5)

                anomaly_id = f"anom_{uuid.uuid4().hex[:8]}"
                record = AnomalyRecord(
                    anomaly_id=anomaly_id,
                    pattern=pattern_name,
                    file_path=file_path,
                    line=i,
                    description=description,
                    severity=severity,
                    confidence=confidence,
                    suggestion=self._get_suggestion(pattern_name, line),
                )

                anomalies.append(record.to_dict())

                with self._lock:
                    self._anomalies[anomaly_id] = record

        if anomalies:
            self._save_anomalies()

        return anomalies

    def _get_suggestion(self, pattern: str, line: str) -> str:
        """Get a fix suggestion for a detected pattern."""
        suggestions = {
            "off_by_one": "Check loop bounds: use range(len(x)) or range(1, len(x)) carefully",
            "mutable_default": "Use None as default and create new instance inside function",
            "bare_except": "Catch specific exceptions: except (ValueError, KeyError) as e:",
            "unbounded_recursion": "Ensure base case is reachable and add depth limit",
            "race_condition": "Use threading.Lock() for shared mutable state",
            "resource_leak": "Use 'with open(...) as f:' context manager",
            "sql_injection": "Use parameterized queries: cursor.execute('SELECT * FROM t WHERE id=?', (id,))",
            "hardcoded_secret": "Use environment variables or config files for secrets",
            "blocking_call_in_async": "Use asyncio.sleep() and aiohttp instead of blocking calls",
            "infinite_loop": "Add break condition or timeout counter",
            "unbounded_recursion": "Add recursion depth limit and base case check",
            "unhandled_none": "Add None check: if value is not None: ...",
        }
        return suggestions.get(pattern, "Review this pattern for correctness")

    # ── Predictive Simulation (LLM-Powered) ─────────────────────────────

    def simulate_code(self, code: str, language: str = "python",
                      context: str = "", test_input: str = "") -> dict:
        """
        Mentally simulate executing code.
        Predicts output, errors, side effects, and performance.
        """
        # First, run fast anomaly detection
        anomalies = self.detect_anomalies(code, language=language)

        # Then, LLM simulation for deeper analysis
        system = """You are a code execution simulator. Predict what the code would do when run.
Analyze: control flow, data flow, edge cases, error conditions.

Return ONLY valid JSON:
{
  "would_run": true/false,
  "confidence": 0.0-1.0,
  "predicted_output": "what it would print/return",
  "likely_errors": [
    {"type": "ErrorType", "line": 10, "reason": "why", "probability": 0.7}
  ],
  "edge_cases": ["edge case 1"],
  "performance": {
    "time_complexity": "O(n)",
    "space_complexity": "O(1)",
    "bottleneck": "description if any"
  },
  "side_effects": ["file I/O", "network call", etc.],
  "type_errors": ["possible type mismatches"],
  "logic_errors": ["subtle logic bugs"]
}"""

        truncated = code[:6000] if len(code) > 6000 else code
        prompt = f"""Language: {language}
{f'Test input: {test_input}' if test_input else ''}
{f'Context: {context[:500]}' if context else ''}

Code to simulate:
```{language}
{truncated}
```

Simulate execution. What would happen?"""

        result = self._generate(prompt, system=system)

        try:
            json_str = result
            if "```" in json_str:
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            simulation = json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            simulation = {
                "would_run": True,
                "confidence": 0.3,
                "predicted_output": "Could not simulate",
                "likely_errors": [],
                "edge_cases": [],
                "performance": {},
                "side_effects": [],
                "type_errors": [],
                "logic_errors": [],
            }

        # Merge anomaly detection results
        simulation["anomalies_detected"] = anomalies
        simulation["anomaly_count"] = len(anomalies)
        simulation["critical_anomalies"] = sum(
            1 for a in anomalies if a["severity"] == "critical"
        )

        # Log simulation
        self._log_simulation(code[:200], simulation)

        return simulation

    def predict_error_fix(self, error_output: str, code: str,
                          language: str = "python") -> dict:
        """
        Given an error, predict the root cause and fix.
        Uses pattern matching + LLM reasoning.
        """
        # Classify error type
        error_type = self._classify_error(error_output)

        # Extract error location
        line_match = re.search(r'line (\d+)', error_output)
        error_line = int(line_match.group(1)) if line_match else None

        # Get context around error
        code_lines = code.splitlines()
        context_start = max(0, (error_line or 1) - 4)
        context_end = min(len(code_lines), (error_line or 1) + 3)
        error_context = "\n".join(
            f"{'>>>' if i + 1 == error_line else '   '} {l}"
            for i, l in enumerate(code_lines[context_start:context_end], context_start)
        )

        system = """You are a debugging expert. Analyze the error and predict the root cause.
Return ONLY valid JSON:
{
  "root_cause": "explanation of why this error occurred",
  "confidence": 0.0-1.0,
  "fix_suggestion": "what to change",
  "fix_code": "the specific line(s) to change",
  "related_issues": ["other things to check"],
  "prevention": "how to avoid this type of error"
}"""

        prompt = f"""Language: {language}
Error output:
{error_output[:1000]}

Code context around error:
{error_context}

Full code:
{code[:4000]}

Analyze this error. What's the root cause and how to fix it?"""

        result = self._generate(prompt, system=system)

        try:
            json_str = result
            if "```" in json_str:
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            prediction = json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            prediction = {
                "root_cause": "Could not determine",
                "confidence": 0.2,
                "fix_suggestion": "Review the error traceback carefully",
                "fix_code": "",
                "related_issues": [],
                "prevention": "",
            }

        prediction["error_type"] = error_type
        prediction["error_line"] = error_line
        return prediction

    # ── Execution Path Tracing ──────────────────────────────────────────

    def trace_execution_path(self, code: str, entry_point: str = "main",
                             language: str = "python") -> dict:
        """
        Trace the likely execution path through the code.
        Identifies: branches taken, functions called, data transformations.
        """
        system = """Trace the execution path of this code. Return ONLY valid JSON:
{
  "entry_point": "function name",
  "execution_path": [
    {"step": 1, "line": 10, "action": "function call", "detail": "what happens"},
    {"step": 2, "line": 15, "action": "branch", "detail": "condition and likely path"}
  ],
  "functions_called": ["func1", "func2"],
  "data_flow": [
    {"from": "input", "to": "processed", "transformation": "what changes"}
  ],
  "branches": [
    {"line": 20, "condition": "if x > 0", "likely_path": "true", "probability": 0.8}
  ],
  "exit_points": [{"line": 30, "type": "return", "value": "result"}]
}"""

        prompt = f"""Language: {language}
Entry point: {entry_point}

Code:
```{language}
{code[:5000]}
```

Trace the execution path. What happens step by step?"""

        result = self._generate(prompt, system=system)

        try:
            json_str = result
            if "```" in json_str:
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
            return json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            return {"error": "Could not trace execution path"}

    # ── Simulation History & Learning ───────────────────────────────────

    def _log_simulation(self, code_snippet: str, result: dict):
        """Log a simulation result for learning."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "code_snippet": code_snippet,
            "would_run": result.get("would_run"),
            "anomaly_count": result.get("anomaly_count", 0),
            "error_count": len(result.get("likely_errors", [])),
        }
        self._simulation_history.append(entry)
        if len(self._simulation_history) > 200:
            self._simulation_history = self._simulation_history[-200:]

        # Append to log file
        try:
            with open(SIMULATION_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def get_anomaly_stats(self) -> dict:
        """Get anomaly detection statistics."""
        with self._lock:
            total = len(self._anomalies)
            by_severity = defaultdict(int)
            by_pattern = defaultdict(int)
            resolved = 0

            for a in self._anomalies.values():
                by_severity[a.severity] += 1
                by_pattern[a.pattern] += 1
                if a.resolved:
                    resolved += 1

            return {
                "total_anomalies": total,
                "resolved": resolved,
                "unresolved": total - resolved,
                "by_severity": dict(by_severity),
                "top_patterns": dict(sorted(by_pattern.items(), key=lambda x: -x[1])[:5]),
            }

    def mark_anomaly_resolved(self, anomaly_id: str):
        """Mark an anomaly as resolved."""
        with self._lock:
            if anomaly_id in self._anomalies:
                self._anomalies[anomaly_id].resolved = True
                self._save_anomalies()

    def _classify_error(self, error_output: str) -> str:
        """Classify error type from output."""
        low = error_output.lower()
        if "syntaxerror" in low:
            return "syntax"
        elif "modulenotfounderror" in low or "importerror" in low:
            return "import"
        elif "nameerror" in low:
            return "name"
        elif "typeerror" in low:
            return "type"
        elif "attributeerror" in low:
            return "attribute"
        elif "valueerror" in low:
            return "value"
        elif "keyerror" in low:
            return "key"
        elif "indexerror" in low:
            return "index"
        elif "filenotfounderror" in low:
            return "file_not_found"
        elif "permissionerror" in low:
            return "permission"
        elif "zerodivisionerror" in low:
            return "zero_division"
        elif "recursionerror" in low:
            return "recursion"
        elif "timeout" in low:
            return "timeout"
        elif "connection" in low:
            return "connection"
        return "unknown"

    # ── Prompt Formatting ───────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """Format simulator state for system prompt injection."""
        stats = self.get_anomaly_stats()
        parts = [
            "[CODE SIMULATOR — Predictive execution analysis]",
            f"Anomalies tracked: {stats['total_anomalies']} "
            f"({stats['unresolved']} unresolved)",
        ]

        if stats.get("top_patterns"):
            patterns = ", ".join(f"{p}({c})" for p, c in list(stats["top_patterns"].items())[:3])
            parts.append(f"Common patterns: {patterns}")

        result = "\n".join(parts)
        return result[:max_chars]


# ── Singleton ───────────────────────────────────────────────────────────

_code_simulator = None
_cs_lock = threading.Lock()


def get_code_simulator() -> CodeSimulator:
    """Get singleton CodeSimulator instance."""
    global _code_simulator
    if _code_simulator is None:
        with _cs_lock:
            if _code_simulator is None:
                _code_simulator = CodeSimulator()
    return _code_simulator