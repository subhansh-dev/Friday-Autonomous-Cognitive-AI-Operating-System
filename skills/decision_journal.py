# -*- coding: utf-8 -*-
"""
decision_journal.py — FRIDAY Decision Journal
==============================================
Auditable reasoning trace for non-trivial actions. Records what options
were considered, why one was chosen, what was expected, and what happened.
Append-only JSONL for reliability and debuggability.
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


BRAIN_DIR = Path(__file__).parent.parent / "brain"
JOURNAL_FILE = BRAIN_DIR / "decision_log.jsonl"
MAX_ENTRY_CHARS = 2000


class DecisionJournal:
    """
    Append-only decision log. Each entry captures:
    - What task was being done
    - What options were considered
    - Which was chosen and why
    - Expected vs actual outcome
    - Lessons learned
    """

    def __init__(self):
        self._lock = threading.Lock()

    # ── Write ───────────────────────────────────────────────────────

    def log_decision(self, task_summary: str,
                     options: list[dict],
                     chosen: str,
                     reasoning: str,
                     expected_outcome: str = "",
                     tool_used: str = "",
                     context: str = "") -> str:
        """
        Log a decision before execution.

        Args:
            task_summary: what the user asked for
            options: list of {"option": str, "pros": str, "cons": str, "confidence": float}
            chosen: which option was selected
            reasoning: why this option was chosen
            expected_outcome: what we expect to happen
            tool_used: which tool will be used
            context: additional context

        Returns:
            entry_id for later updating with actual outcome
        """
        entry_id = f"dec_{int(time.time() * 1000)}"
        entry = {
            "id": entry_id,
            "timestamp": datetime.now().isoformat(),
            "phase": "decision",
            "task_summary": task_summary[:300],
            "options": options[:5],  # Cap at 5 options
            "chosen_option": chosen[:200],
            "reasoning": reasoning[:500],
            "expected_outcome": expected_outcome[:300],
            "tool_used": tool_used,
            "context": context[:200],
            "actual_outcome": None,
            "outcome_quality": None,  # "good", "partial", "bad"
            "lessons": None,
        }
        self._append(entry)
        return entry_id

    def log_outcome(self, entry_id: str, actual_outcome: str,
                    quality: str = "good", lessons: str = ""):
        """
        Update a decision entry with the actual outcome.

        Args:
            entry_id: the ID returned by log_decision
            actual_outcome: what actually happened
            quality: "good", "partial", or "bad"
            lessons: what to remember for next time
        """
        update = {
            "id": f"{entry_id}_outcome",
            "timestamp": datetime.now().isoformat(),
            "phase": "outcome",
            "parent_id": entry_id,
            "actual_outcome": actual_outcome[:500],
            "quality": quality,
            "lessons": lessons[:300] if lessons else None,
        }
        self._append(update)

    def log_simple(self, action: str, tool: str, outcome: str,
                   reasoning: str = ""):
        """
        Quick log for simpler decisions that don't need full option analysis.
        """
        entry = {
            "id": f"dec_{int(time.time() * 1000)}",
            "timestamp": datetime.now().isoformat(),
            "phase": "simple",
            "action": action[:200],
            "tool": tool,
            "outcome": outcome[:300],
            "reasoning": reasoning[:200],
        }
        self._append(entry)

    def _append(self, entry: dict):
        """Append an entry to the JSONL log."""
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        # Truncate oversized entries
        entry_str = json.dumps(entry, ensure_ascii=False)
        if len(entry_str) > MAX_ENTRY_CHARS:
            entry_str = entry_str[:MAX_ENTRY_CHARS] + "...\"}"
            try:
                entry = json.loads(entry_str)
            except json.JSONDecodeError:
                entry = {"id": entry.get("id", "truncated"), "truncated": True}

        with self._lock:
            with open(JOURNAL_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── Read ────────────────────────────────────────────────────────

    def get_recent(self, limit: int = 20) -> list[dict]:
        """Get recent journal entries."""
        if not JOURNAL_FILE.exists():
            return []
        try:
            lines = JOURNAL_FILE.read_text(encoding="utf-8").strip().split("\n")
            entries = []
            for line in lines[-limit * 2:]:  # Read extra to account for outcome entries
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            # Filter to decision/simple entries only (not outcome updates)
            decisions = [e for e in entries if e.get("phase") in ("decision", "simple")]
            return decisions[-limit:]
        except IOError:
            return []

    def query(self, keyword: str = "", tool: str = "",
              quality: str = "", limit: int = 10) -> list[dict]:
        """
        Search the decision journal.

        Args:
            keyword: match against task_summary or action
            tool: filter by tool used
            quality: filter by outcome quality
            limit: max results
        """
        if not JOURNAL_FILE.exists():
            return []
        try:
            results = []
            for line in JOURNAL_FILE.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Apply filters
                if keyword:
                    kw = keyword.lower()
                    text = (entry.get("task_summary", "") + " " +
                            entry.get("action", "") + " " +
                            entry.get("reasoning", "")).lower()
                    if kw not in text:
                        continue
                if tool and entry.get("tool_used", "") != tool and entry.get("tool", "") != tool:
                    continue
                if quality and entry.get("quality") != quality and entry.get("outcome_quality") != quality:
                    continue

                results.append(entry)
                if len(results) >= limit:
                    break

            return results
        except IOError:
            return []

    def get_stats(self) -> dict:
        """Get journal statistics."""
        if not JOURNAL_FILE.exists():
            return {"total_entries": 0}

        try:
            lines = JOURNAL_FILE.read_text(encoding="utf-8").strip().split("\n")
            total = len([l for l in lines if l.strip()])
            quality_counts = {"good": 0, "partial": 0, "bad": 0}
            tool_counts: dict[str, int] = {}

            for line in lines:
                try:
                    e = json.loads(line)
                    q = e.get("quality") or e.get("outcome_quality")
                    if q in quality_counts:
                        quality_counts[q] += 1
                    t = e.get("tool_used") or e.get("tool")
                    if t:
                        tool_counts[t] = tool_counts.get(t, 0) + 1
                except json.JSONDecodeError:
                    continue

            return {
                "total_entries": total,
                "quality_breakdown": quality_counts,
                "top_tools": sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)[:5],
            }
        except IOError:
            return {"total_entries": 0}

    def format_for_prompt(self, keyword: str = "", max_chars: int = 300) -> str:
        """Format recent decisions for system prompt injection."""
        entries = self.query(keyword=keyword, limit=3)
        if not entries:
            return ""

        parts = ["[DECISION JOURNAL — Recent reasoning]"]
        for e in entries:
            summary = e.get("task_summary") or e.get("action", "unknown")
            chosen = e.get("chosen_option", "")
            quality = e.get("quality", "")
            if chosen:
                parts.append(f"- {summary[:60]} → {chosen[:60]} [{quality}]")
            else:
                parts.append(f"- {summary[:80]}")

        result = "\n".join(parts)
        return result[:max_chars] if len(result) > max_chars else result


# ── Singleton ───────────────────────────────────────────────────────────────

_journal = None
_journal_lock = threading.Lock()


def get_decision_journal() -> DecisionJournal:
    global _journal
    if _journal is None:
        with _journal_lock:
            if _journal is None:
                _journal = DecisionJournal()
    return _journal
