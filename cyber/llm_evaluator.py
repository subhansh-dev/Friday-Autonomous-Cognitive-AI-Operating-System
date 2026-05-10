"""
LLM Evaluator - Sanitization evaluation for data flow paths.

Given a code path from source to sink, evaluates whether the sanitization
at intermediate nodes is sufficient to prevent exploitation.

Uses LLM for nuanced analysis when available, falls back to pattern-based
heuristics otherwise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class Verdict(str, Enum):
    SAFE = "safe"
    UNSAFE = "unsafe"
    UNCERTAIN = "uncertain"


@dataclass
class EvaluationResult:
    """Result of evaluating a data flow path for sanitization."""
    verdict: Verdict
    confidence: float  # 0.0 to 1.0
    reasoning: str
    path: list[str] = field(default_factory=list)
    vuln_class: str = ""
    intermediate_nodes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "path": self.path,
            "vuln_class": self.vuln_class,
            "intermediate_nodes": self.intermediate_nodes,
        }


# ═══════════════════════════════════════════════════════════════════
#  HEURISTIC PATTERNS (used when LLM is unavailable)
# ═══════════════════════════════════════════════════════════════════

# SQL injection safe patterns
_SQL_SAFE_PATTERNS = [
    re.compile(r"\?\s*['\"\s]*[,)]"),            # parameterized query: cursor.execute("... WHERE x = ?", (val,))
    re.compile(r"%s\s*['\"\s]*[,)]"),            # parameterized: cursor.execute("... %s", (val,))
    re.compile(r":\w+\s*['\"\s]*[,)]"),          # named params: cursor.execute("... :name", {"name": val})
    re.compile(r"prepared\s*statement", re.I),
    re.compile(r"parameterize", re.I),
    re.compile(r"sql.*escape", re.I),
]

# XSS safe patterns
_XSS_SAFE_PATTERNS = [
    re.compile(r"escape(?:s|Html)?\s*\(", re.I),
    re.compile(r"sanitize(?:s|Html)?\s*\(", re.I),
    re.compile(r"bleach\.clean\s*\(", re.I),
    re.compile(r"markupsafe", re.I),
    re.compile(r"textContent\s*=", re.I),   # safe DOM assignment
    re.compile(r"innerText\s*=", re.I),     # safe DOM assignment
    re.compile(r"createTextNode\s*\(", re.I),
    re.compile(r"encodeURIComponent\s*\(", re.I),
    re.compile(r"DOMPurify\.sanitize\s*\(", re.I),
]

# Command injection safe patterns
_CMD_SAFE_PATTERNS = [
    re.compile(r"shlex\.quote\s*\(", re.I),
    re.compile(r"shlex\.split\s*\(", re.I),
    re.compile(r"shell\s*=\s*False"),
    re.compile(r"subprocess\.list2cmdline"),
    re.compile(r"escape.*shell", re.I),
]

# Path traversal safe patterns
_PATH_SAFE_PATTERNS = [
    re.compile(r"os\.path\.abspath\s*\(", re.I),
    re.compile(r"pathlib.*resolve\s*\(", re.I),
    re.compile(r"secure_filename\s*\(", re.I),
    re.compile(r"werkzeug.*secure", re.I),
    re.compile(r"realpath\s*\(", re.I),
    re.compile(r"\.\./", re.I),  # check if path normalization is done
]

# SSRF safe patterns
_SSRF_SAFE_PATTERNS = [
    re.compile(r"urlparse.*netloc", re.I),
    re.compile(r"ipaddress", re.I),
    re.compile(r"whitelist", re.I),
    re.compile(r"allowlist", re.I),
    re.compile(r"validate.*url", re.I),
]

# Deserialization safe patterns
_DESERIALIZE_SAFE_PATTERNS = [
    re.compile(r"SafeLoader", re.I),
    re.compile(r"safe_load\s*\(", re.I),
    re.compile(r"JSONSerializer", re.I),
    re.compile(r"RestrictedUnpickler", re.I),
]

# Validation decorator patterns
_VALIDATION_DECORATORS = [
    re.compile(r"@(?:validate|sanitize|secure|authorize|login_required|permission_required)", re.I),
    re.compile(r"@app\.before_request", re.I),
    re.compile(r"@jwt_required", re.I),
    re.compile(r"@csrf\.protect", re.I),
]

# Map vuln classes to heuristic checks
_VULN_HEURISTICS: dict[str, list[re.Pattern[str]]] = {
    "CWE-89": _SQL_SAFE_PATTERNS,           # SQL injection
    "CWE-79": _XSS_SAFE_PATTERNS,            # XSS
    "CWE-78": _CMD_SAFE_PATTERNS,            # Command injection
    "CWE-22": _PATH_SAFE_PATTERNS,           # Path traversal
    "CWE-918": _SSRF_SAFE_PATTERNS,          # SSRF
    "CWE-502": _DESERIALIZE_SAFE_PATTERNS,   # Deserialization
    "CWE-94": _XSS_SAFE_PATTERNS,            # SSTI (similar sanitization)
    "CWE-601": _SSRF_SAFE_PATTERNS,          # Open redirect (similar checks)
    "CWE-113": [],                           # Header injection
}


class LLMEvaluator:
    """
    Evaluates sanitization along data flow paths.

    Uses an optional LLM callback for nuanced analysis.
    Falls back to pattern-based heuristics when LLM is unavailable.
    """

    def __init__(
        self,
        llm_callback: Callable[[str], str] | None = None,
        language: str = "python",
    ) -> None:
        """
        Args:
            llm_callback: Optional function that takes a prompt string
                         and returns an LLM response string.
            language: Target language for heuristic selection.
        """
        self._llm = llm_callback
        self._language = language
        self._evaluation_cache: dict[str, EvaluationResult] = {}

    def evaluate_path(
        self,
        code_path: list[str],
        code_lines: list[str],
        vuln_class: str,
        source_name: str = "",
        sink_name: str = "",
    ) -> EvaluationResult:
        """
        Evaluate whether a code path is properly sanitized.

        Args:
            code_path: List of node IDs in the flow path.
            code_lines: Corresponding source code lines.
            vuln_class: CWE identifier for the vulnerability type.
            source_name: Name of the source.
            sink_name: Name of the sink.

        Returns:
            EvaluationResult with verdict, confidence, and reasoning.
        """
        cache_key = f"{':'.join(code_path)}:{vuln_class}"
        if cache_key in self._evaluation_cache:
            return self._evaluation_cache[cache_key]

        # try LLM first
        if self._llm is not None:
            try:
                result = self._evaluate_with_llm(
                    code_path, code_lines, vuln_class, source_name, sink_name
                )
                self._evaluation_cache[cache_key] = result
                return result
            except Exception as e:
                # fall through to heuristics
                pass

        # fall back to heuristics
        result = self._evaluate_with_heuristics(
            code_path, code_lines, vuln_class, source_name, sink_name
        )
        self._evaluation_cache[cache_key] = result
        return result

    def _evaluate_with_llm(
        self,
        code_path: list[str],
        code_lines: list[str],
        vuln_class: str,
        source_name: str,
        sink_name: str,
    ) -> EvaluationResult:
        """Use LLM to evaluate sanitization."""
        prompt = self._build_llm_prompt(code_path, code_lines, vuln_class, source_name, sink_name)
        response = self._llm(prompt)  # type: ignore[misc]
        return self._parse_llm_response(response, code_path, vuln_class)

    def _build_llm_prompt(
        self,
        code_path: list[str],
        code_lines: list[str],
        vuln_class: str,
        source_name: str,
        sink_name: str,
    ) -> str:
        """Build a prompt for LLM-based evaluation."""
        code_block = "\n".join(f"  L{i+1}: {line}" for i, line in enumerate(code_lines))
        return f"""You are a security code reviewer. Analyze the following data flow path for security vulnerabilities.

Source: {source_name} (user-controlled input)
Sink: {sink_name} (dangerous operation)
Vulnerability class: {vuln_class}

Code path:
{code_block}

Questions:
1. Is there any sanitization, validation, or encoding applied to the data between source and sink?
2. If sanitization exists, is it sufficient to prevent {vuln_class}?
3. Are there any bypasses or edge cases?

Respond in this exact format:
VERDICT: safe|unsafe|uncertain
CONFIDENCE: 0.0-1.0
REASONING: <one paragraph explanation>
"""

    def _parse_llm_response(
        self,
        response: str,
        code_path: list[str],
        vuln_class: str,
    ) -> EvaluationResult:
        """Parse LLM response into an EvaluationResult."""
        verdict = Verdict.UNCERTAIN
        confidence = 0.5
        reasoning = response

        # extract verdict
        verdict_match = re.search(r"VERDICT:\s*(safe|unsafe|uncertain)", response, re.I)
        if verdict_match:
            verdict = Verdict(verdict_match.group(1).lower())

        # extract confidence
        conf_match = re.search(r"CONFIDENCE:\s*([\d.]+)", response)
        if conf_match:
            try:
                confidence = max(0.0, min(1.0, float(conf_match.group(1))))
            except ValueError:
                pass

        # extract reasoning
        reason_match = re.search(r"REASONING:\s*(.+?)(?:\n\n|\Z)", response, re.S)
        if reason_match:
            reasoning = reason_match.group(1).strip()

        return EvaluationResult(
            verdict=verdict,
            confidence=confidence,
            reasoning=reasoning,
            path=code_path,
            vuln_class=vuln_class,
        )

    def _evaluate_with_heuristics(
        self,
        code_path: list[str],
        code_lines: list[str],
        vuln_class: str,
        source_name: str = "",
        sink_name: str = "",
    ) -> EvaluationResult:
        """Evaluate using pattern-based heuristics."""
        safe_patterns = _VULN_HEURISTICS.get(vuln_class, [])
        combined_code = "\n".join(code_lines)

        # check for safe patterns in intermediate code
        safe_matches: list[str] = []
        for pattern in safe_patterns:
            for match in pattern.finditer(combined_code):
                safe_matches.append(match.group(0))

        # check for validation decorators
        decorator_matches: list[str] = []
        for pattern in _VALIDATION_DECORATORS:
            for match in pattern.finditer(combined_code):
                decorator_matches.append(match.group(0))

        # check for shell=True in subprocess calls (always dangerous)
        shell_true = re.search(r"shell\s*=\s*True", combined_code)

        # evaluate
        if safe_matches and not shell_true:
            return EvaluationResult(
                verdict=Verdict.SAFE,
                confidence=0.7,
                reasoning=f"Found sanitization patterns: {', '.join(set(safe_matches))}",
                path=code_path,
                vuln_class=vuln_class,
            )
        elif decorator_matches and not shell_true:
            return EvaluationResult(
                verdict=Verdict.SAFE,
                confidence=0.6,
                reasoning=f"Found validation decorators: {', '.join(set(decorator_matches))}",
                path=code_path,
                vuln_class=vuln_class,
            )
        elif shell_true:
            return EvaluationResult(
                verdict=Verdict.UNSAFE,
                confidence=0.9,
                reasoning="Found shell=True in subprocess call, which bypasses argument escaping",
                path=code_path,
                vuln_class=vuln_class,
            )
        elif len(code_lines) <= 2:
            # direct flow, no intermediate sanitization
            return EvaluationResult(
                verdict=Verdict.UNSAFE,
                confidence=0.6,
                reasoning="Direct data flow from source to sink with no intermediate sanitization",
                path=code_path,
                vuln_class=vuln_class,
            )
        else:
            return EvaluationResult(
                verdict=Verdict.UNCERTAIN,
                confidence=0.4,
                reasoning="No known sanitization patterns found; manual review recommended",
                path=code_path,
                vuln_class=vuln_class,
            )


def evaluate_sanitization(
    code_lines: list[str],
    vuln_class: str,
    llm_callback: Callable[[str], str] | None = None,
) -> EvaluationResult:
    """
    Convenience function for one-shot sanitization evaluation.

    Args:
        code_lines: Source code lines to evaluate.
        vuln_class: CWE identifier.
        llm_callback: Optional LLM function.

    Returns:
        EvaluationResult.
    """
    evaluator = LLMEvaluator(llm_callback=llm_callback)
    path = [f"line_{i+1}" for i in range(len(code_lines))]
    return evaluator.evaluate_path(path, code_lines, vuln_class)


def get_supported_vuln_classes() -> list[str]:
    """Return list of CWE IDs with heuristic support."""
    return list(_VULN_HEURISTICS.keys())
