# -*- coding: utf-8 -*-
"""
meta_reflect.py — FRIDAY Metacognition Engine
==============================================
Self-reflection and error recovery. After tool calls, evaluates whether
the output was correct and complete. Maintains a failure journal to
avoid repeating mistakes. Inspired by Reflexion (Shinn et al., 2023).
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


BRAIN_DIR = Path(__file__).parent.parent / "brain"
JOURNAL_FILE = BRAIN_DIR / "meta_journal.json"

MAX_JOURNAL_ENTRIES = 200


class MetaReflection:
    """
    Post-execution reflection and failure journal.

    Flow:
    1. After a tool call, `reflect()` evaluates the outcome
    2. If issues found, stores a reflection entry
    3. Before similar future tasks, `get_relevant_reflections()` provides context
    4. System prompt injection prevents repeating known mistakes
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._journal: list[dict] = []
        self._load()

    # ── Persistence ─────────────────────────────────────────────────

    def _load(self):
        if not JOURNAL_FILE.exists():
            return
        try:
            data = json.loads(JOURNAL_FILE.read_text(encoding="utf-8"))
            self._journal = data.get("entries", [])[-MAX_JOURNAL_ENTRIES:]
        except (json.JSONDecodeError, IOError):
            self._journal = []

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "entries": self._journal[-MAX_JOURNAL_ENTRIES:],
            "updated_at": datetime.now().isoformat(),
        }
        JOURNAL_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Reflection ──────────────────────────────────────────────────

    def reflect(self, tool_name: str, action: str, output: str,
                success: Optional[bool] = None,
                error: Optional[str] = None,
                context: str = "") -> dict:
        """
        Evaluate a tool call outcome and extract learnings.

        Args:
            tool_name: which tool was called
            action: what action was attempted
            output: the tool's output (truncated to 500 chars for storage)
            success: whether the tool reported success (None = unknown)
            error: error message if any
            context: additional context about the request

        Returns:
            {"issues_found": bool, "reflection": str, "entry_id": str}
        """
        issues = []
        reflection_parts = []

        # Check for obvious failure signals
        if error:
            issues.append("error_reported")
            reflection_parts.append(f"Error: {error[:200]}")

        if success is False:
            issues.append("explicit_failure")
            reflection_parts.append("Tool reported failure")

        output_lower = output.lower() if output else ""

        # Check for empty/unexpected output
        if not output or len(output.strip()) < 5:
            issues.append("empty_output")
            reflection_parts.append("Output was empty or near-empty")

        # Check for common error patterns in output
        error_patterns = [
            "error", "failed", "exception", "traceback", "permission denied",
            "not found", "timeout", "connection refused", "access denied",
        ]
        for pattern in error_patterns:
            if pattern in output_lower:
                issues.append(f"error_pattern:{pattern}")
                reflection_parts.append(f"Output contains '{pattern}'")
                break  # One is enough

        # Check for partial results
        if "partial" in output_lower or "incomplete" in output_lower:
            issues.append("partial_result")
            reflection_parts.append("Result appears partial/incomplete")

        # Build reflection entry
        has_issues = len(issues) > 0
        reflection_text = "; ".join(reflection_parts) if reflection_parts else "No issues detected"

        entry = {
            "id": f"ref_{int(time.time())}",
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "action": action[:100],
            "success": success,
            "issues": issues,
            "reflection": reflection_text,
            "context": context[:200],
            "output_preview": output[:300] if output else "",
        }

        if has_issues:
            with self._lock:
                self._journal.append(entry)
                self._journal = self._journal[-MAX_JOURNAL_ENTRIES:]
                self._save()

        return {
            "issues_found": has_issues,
            "reflection": reflection_text,
            "entry_id": entry["id"],
        }

    def get_relevant_reflections(self, tool_name: str = "",
                                  action_keywords: str = "",
                                  limit: int = 5) -> list[dict]:
        """
        Get past reflections relevant to a tool/action.
        Used to inject lessons into the system prompt before execution.
        """
        with self._lock:
            if not self._journal:
                return []

            scored = []
            for entry in reversed(self._journal):
                score = 0
                if tool_name and entry.get("tool") == tool_name:
                    score += 2
                if action_keywords:
                    kw_lower = action_keywords.lower()
                    if kw_lower in entry.get("action", "").lower():
                        score += 1
                    if kw_lower in entry.get("context", "").lower():
                        score += 1
                if score > 0:
                    scored.append((score, entry))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [e for _, e in scored[:limit]]

    def get_failure_summary(self, tool_name: str = "") -> str:
        """Get a summary of common failure patterns for a tool."""
        with self._lock:
            entries = self._journal
            if tool_name:
                entries = [e for e in entries if e.get("tool") == tool_name]

            if not entries:
                return ""

            # Count issue types
            issue_counts: dict[str, int] = {}
            for e in entries:
                for issue in e.get("issues", []):
                    issue_counts[issue] = issue_counts.get(issue, 0) + 1

            if not issue_counts:
                return ""

            top_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            parts = [f"{issue}({count})" for issue, count in top_issues]
            return f"Common issues with {tool_name or 'tools'}: {', '.join(parts)}"

    def format_for_prompt(self, tool_name: str, action: str,
                           max_chars: int = 300) -> str:
        """Format relevant reflections for system prompt injection."""
        reflections = self.get_relevant_reflections(tool_name, action, limit=3)
        if not reflections:
            return ""

        parts = ["[METACOGNITION — Past lessons]"]
        for r in reflections:
            parts.append(f"- {r['reflection'][:100]}")

        result = "\n".join(parts)
        return result[:max_chars] if len(result) > max_chars else result

    # ── Query ───────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        with self._lock:
            total = len(self._journal)
            tool_counts: dict[str, int] = {}
            issue_counts: dict[str, int] = {}
            for e in self._journal:
                t = e.get("tool", "unknown")
                tool_counts[t] = tool_counts.get(t, 0) + 1
                for issue in e.get("issues", []):
                    issue_counts[issue] = issue_counts.get(issue, 0) + 1

            return {
                "total_reflections": total,
                "tools_with_issues": len(tool_counts),
                "top_offending_tools": sorted(
                    tool_counts.items(), key=lambda x: x[1], reverse=True
                )[:5],
                "top_issue_types": sorted(
                    issue_counts.items(), key=lambda x: x[1], reverse=True
                )[:5],
            }


# ── Singleton ───────────────────────────────────────────────────────────────

_meta = None
_meta_lock = threading.Lock()


def get_meta_reflection() -> MetaReflection:
    global _meta
    if _meta is None:
        with _meta_lock:
            if _meta is None:
                _meta = MetaReflection()
    return _meta
