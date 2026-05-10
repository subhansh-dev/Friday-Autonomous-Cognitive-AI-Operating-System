# -*- coding: utf-8 -*-
"""
learning.py — FRIDAY Learning & Evolution Engine
==================================================

Inspired by human cognitive science:
- Error-driven learning: mistakes → reflection → behavioral update
- Reinforcement learning: positive/negative feedback shapes future decisions
- Metacognition: thinking about thinking, reflecting on outcomes
- Deliberate practice: tracking improvement over time
- World Values Survey: values-driven adaptation, not blind optimization

Architecture:
- Short-term buffer: recent events + outcomes (like working memory)
- Learning consolidation: periodic extraction of patterns from buffer
- Learnings file: human-readable persistent record of learned insights
- Q-values: simple action-outcome scoring to guide future choices
- Reflection triggers: errors, user corrections, failed tools, time intervals
"""

import json
import threading
import time
import random
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from collections import defaultdict


# ─── Configuration ───────────────────────────────────────────────────────────

BASE_DIR       = Path(__file__).resolve().parent.parent
LEARNINGS_DIR  = BASE_DIR / "brain"
LEARNINGS_FILE = LEARNINGS_DIR / "learnings.md"
LEARNING_DATA_FILE = LEARNINGS_DIR / "learning_data.json"

# Learning engine params
BUFFER_MAX_SIZE      = 200       # Max events in working memory buffer
CONSOLIDATE_INTERVAL = 600       # Consolidate every 10 minutes
Q_LEARNING_RATE      = 0.3       # How fast Q-values update
Q_DISCOUNT_FACTOR    = 0.9       # How much future reward matters
Q_EXPLORATION_RATE   = 0.1       # Explore vs exploit probability

# Reflection thresholds
REFLECTION_ERROR_THRESHOLD  = 3     # Reflect after N errors
REFLECTION_TIME_INTERVAL    = 3600  # Reflect every hour anyway
MIN_REFLECTION_INTERVAL_SEC = 120   # Don't reflect more often than 2 min

# Learnings file size limit [#1]
MAX_LEARNINGS_FILE_SIZE = 500_000  # 500KB — rotate if bigger


# ─── Helper ──────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now()


def _timestamp() -> str:
    return _now().isoformat()


def _tag() -> str:
    return _now().strftime("%Y-%m-%d %H:%M")


def _ensure_dir():
    LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)


# ─── Learning Event Types ────────────────────────────────────────────────────

class EventType:
    TOOL_SUCCESS     = "tool_success"
    TOOL_FAILURE     = "tool_failure"
    USER_CORRECTION  = "user_correction"
    USER_PRAISE      = "user_praise"
    USER_DISMISSAL   = "user_dismissal"
    REFLECTION       = "reflection"
    TASK_COMPLETE    = "task_complete"
    INFO_LEARNED     = "info_learned"
    PATTERN_SEEN     = "pattern_seen"
    SECURITY_FINDING = "security_finding"


# ─── Learning Engine ─────────────────────────────────────────────────────────

class LearningEngine:
    """
    Core learning engine for FRIDAY.

    Implements:
    1. Error-driven learning: mistakes get reflected on, patterns extracted
    2. Reinforcement signals: user feedback adjusts Q-values
    3. Metacognitive reflection: periodic "thinking about thinking" sessions
    4. Learning consolidation: raw experiences → distilled insights
    5. Q-learning: simple action-value table for tool selection optimization
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._consolidation_thread: Optional[threading.Thread] = None

        # Working memory buffer
        self.buffer: List[dict] = []

        # Q-table: action -> context -> value
        self.q_table: Dict[str, Dict[str, float]] = defaultdict(
            lambda: defaultdict(float))

        # Error counter (triggers reflection)
        self.error_count = 0
        self.consecutive_failures: Dict[str, int] = defaultdict(int)

        # Track learnings written to file (to avoid duplicates)
        self.written_learnings: set = set()

        # Reflection cooldown
        self._last_reflection_time = 0.0

        # Load persisted data
        self._load()

        # Start background consolidation
        self._start_consolidation()

        print("[Learning] Engine initialized")

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self):
        """Load learning data from disk."""
        _ensure_dir()
        if LEARNING_DATA_FILE.exists():
            try:
                data = json.loads(
                    LEARNING_DATA_FILE.read_text(encoding="utf-8"))
                self.q_table = defaultdict(
                    lambda: defaultdict(float),
                    {k: defaultdict(float, v)
                     for k, v in data.get("q_table", {}).items()},
                )
                self.written_learnings = set(
                    data.get("written_learnings", []))
                self.error_count = data.get("error_count", 0)
                print(f"[Learning] Loaded {len(self.written_learnings)} "
                      f"learnings, {len(self.q_table)} q-values")
            except json.JSONDecodeError as e:  # [#2]
                print(f"[Learning] ⚠️ Corrupted data file: {e} — resetting")
                self._backup_corrupted_file()
            except Exception as e:
                print(f"[Learning] Load error: {e}")

    def _backup_corrupted_file(self):  # [#2]
        """Back up corrupted data file instead of losing it."""
        try:
            backup = LEARNING_DATA_FILE.with_suffix(".json.bak")
            LEARNING_DATA_FILE.rename(backup)
            print(f"[Learning] Corrupted file backed up to {backup}")
        except Exception:
            pass

    def _save(self):
        """Save learning data to disk."""
        _ensure_dir()
        try:
            data = {
                "q_table": {k: dict(v)
                            for k, v in self.q_table.items()},
                "written_learnings": list(self.written_learnings),
                "error_count": self.error_count,
                "last_saved": _timestamp(),
            }
            # Write to temp file first, then rename (atomic write) [#3]
            tmp_path = LEARNING_DATA_FILE.with_suffix(".json.tmp")
            tmp_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp_path.replace(LEARNING_DATA_FILE)
        except Exception as e:
            print(f"[Learning] Save error: {e}")

    # ── Event Recording ─────────────────────────────────────────────────────

    def record_event(self, event_type: str, data: dict):
        """Record a learning event in working memory buffer."""
        event = {
            "type":      event_type,
            "data":      data,
            "timestamp": _timestamp(),
            "id":        f"evt_{int(time.time() * 1000)}"
                         f"_{random.randint(100, 999)}",
        }

        with self._lock:
            self.buffer.append(event)
            if len(self.buffer) > BUFFER_MAX_SIZE:
                self.buffer = self.buffer[-BUFFER_MAX_SIZE:]

            # Track errors for reflection triggering
            if event_type == EventType.TOOL_FAILURE:
                self.error_count += 1
                tool = data.get("tool", "unknown")
                self.consecutive_failures[tool] += 1
            elif event_type == EventType.USER_CORRECTION:
                self.error_count += 2
            elif event_type == EventType.USER_PRAISE:
                self.error_count = max(0, self.error_count - 1)

        # Immediate reflection on repeated failures
        if event_type == EventType.TOOL_FAILURE:
            tool = data.get("tool", "unknown")
            if self.consecutive_failures[tool] >= REFLECTION_ERROR_THRESHOLD:
                self._learn_from_failure(tool, data)

    def record_tool_result(
        self,
        tool_name: str,
        success: bool,
        context: str = "",
        error: str = "",
    ):
        """Convenience method to record a tool execution result."""
        if success:
            self.record_event(EventType.TOOL_SUCCESS, {
                "tool":    tool_name,
                "context": context,
            })
            with self._lock:
                self.consecutive_failures[tool_name] = 0
            # Positive Q-value update [#4]
            self._update_q_value(tool_name, context, 0.5)
        else:
            self.record_event(EventType.TOOL_FAILURE, {
                "tool":    tool_name,
                "context": context,
                "error":   str(error)[:200],
            })
            self._update_q_value(tool_name, context, -0.5)

    def record_user_feedback(self, positive: bool, context: str = ""):
        """Record user feedback (praise or correction)."""
        if positive:
            self.record_event(EventType.USER_PRAISE, {"context": context})
        else:
            self.record_event(EventType.USER_CORRECTION, {"context": context})

    def record_security_finding(self, finding: dict):
        """Record a security finding as a learning event."""
        vuln_class = finding.get("vuln_class", "unknown")
        confidence = finding.get("confidence", "unknown")
        cvss = finding.get("cvss_score", 0)
        file_path = finding.get("file_path", "unknown")
        summary = finding.get("summary", "")

        event = {
            "type":      EventType.SECURITY_FINDING,
            "data":      {
                "vuln_class": vuln_class,
                "confidence": confidence,
                "cvss_score": cvss,
                "file_path": file_path,
                "summary": summary[:150],
            },
            "timestamp": _timestamp(),
        }

        with self._lock:
            self.buffer.append(event)
            if len(self.buffer) > BUFFER_MAX_SIZE:
                self.buffer = self.buffer[-BUFFER_MAX_SIZE:]

        if cvss >= 7.0:
            self._write_learning({
                "type":           "security_finding",
                "vuln_class":     vuln_class,
                "confidence":     confidence,
                "cvss_score":     cvss,
                "file_path":     file_path,
                "insight":       f"Found {vuln_class} in {file_path} (CVSS {cvss}, {confidence})",
                "recommendation": f"Review {file_path} for {vuln_class} remediation",
                "timestamp":      _tag(),
                "source":         "security_pipeline",
            })

        print(f"[Learning] Recorded security finding: {vuln_class} (CVSS {cvss})")

    def learn_from_security_scan(self, findings: list):
        """Process multiple findings from a security scan."""
        for finding in findings:
            self.record_security_finding(finding)

    # ── Q-Learning ──────────────────────────────────────────────────────────

    def _update_q_value(self, action: str, context: str, reward: float):
        """
        Simplified Q-learning update.
        Q(action, context) += lr * (reward - Q(action, context))
        """
        with self._lock:
            old_q = self.q_table[action].get(context, 0.0)
            new_q = old_q + Q_LEARNING_RATE * (reward - old_q)
            self.q_table[action][context] = round(new_q, 4)

    def get_q_value(self, action: str, context: str = "") -> float:
        """Get current Q-value for an action in a context."""
        with self._lock:
            return self.q_table[action].get(context, 0.0)

    def should_explore(self) -> bool:
        """Should we try a new approach vs using what works?"""
        return random.random() < Q_EXPLORATION_RATE

    def best_tool_for_context(
        self,
        context: str,
        available_tools: List[str],
    ) -> Optional[str]:
        """
        Suggest the best tool for a context based on past reinforcement.
        Returns None if no data yet.
        """
        with self._lock:
            candidates = []
            for tool in available_tools:
                q = self.q_table[tool].get(context, 0.0)
                if q != 0.0:
                    candidates.append((tool, q))

            if not candidates:
                return None

            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]

    # ── Error-Driven Learning ───────────────────────────────────────────────

    def _learn_from_failure(self, tool: str, data: dict):
        """When a tool fails repeatedly, analyze why and generate a learning."""
        error = data.get("error", "unknown error")
        context = data.get("context", "general")

        learning = {
            "type":           "failure_pattern",
            "tool":           tool,
            "error":          error,
            "context":        context,
            "insight":        (f"Tool '{tool}' fails in '{context}' context "
                               f"with error: {error[:100]}. "
                               f"Consider alternative approaches or pre-checks."),
            "recommendation": self._generate_recommendation(tool, error, context),
            "timestamp":      _tag(),
            "source":         "error_driven",
        }

        self._write_learning(learning)

        with self._lock:
            self.consecutive_failures[tool] = 0

        print(f"[Learning] Error-driven learning from {tool}: {error[:60]}")

    def _generate_recommendation(
        self, tool: str, error: str, context: str,
    ) -> str:
        """Generate a practical recommendation from a failure."""
        error_lower = error.lower()

        if "timeout" in error_lower or "timed out" in error_lower:
            return (f"Increase timeout for '{tool}' or break the task "
                    f"into smaller steps")
        elif "not found" in error_lower or "not installed" in error_lower:
            return f"Verify prerequisites for '{tool}' before use"
        elif "permission" in error_lower or "access denied" in error_lower:
            return f"Check permissions before calling '{tool}'"
        elif "connection" in error_lower or "network" in error_lower:
            return f"Check network connectivity before using '{tool}'"
        else:
            return (f"Pre-validate inputs before calling '{tool}' "
                    f"and have a fallback plan")

    # ── Metacognitive Reflection ────────────────────────────────────────────

    def reflect(self, force: bool = False) -> Optional[str]:
        """
        Run a metacognitive reflection session.
        Returns markdown-formatted reflection if insights were generated.
        """
        now = time.time()
        if (not force
                and (now - self._last_reflection_time) < MIN_REFLECTION_INTERVAL_SEC):
            return None

        self._last_reflection_time = now

        with self._lock:
            if not self.buffer:
                return None

            recent = self.buffer[-50:]

            type_counts: Dict[str, int] = defaultdict(int)
            tool_failures: List[str] = []
            tool_successes: List[str] = []
            corrections: List[str] = []

            for evt in recent:
                type_counts[evt["type"]] += 1
                if evt["type"] == EventType.TOOL_FAILURE:
                    tool_failures.append(evt["data"].get("tool", "?"))
                elif evt["type"] == EventType.TOOL_SUCCESS:
                    tool_successes.append(evt["data"].get("tool", "?"))
                elif evt["type"] == EventType.USER_CORRECTION:
                    corrections.append(evt["data"].get("context", ""))

        # Generate insights
        insights: List[str] = []

        # Failure patterns
        if tool_failures:
            failure_counts: Dict[str, int] = defaultdict(int)
            for t in tool_failures:
                failure_counts[t] += 1
            worst = max(failure_counts, key=failure_counts.get)  # type: ignore
            if failure_counts[worst] >= 2:
                insights.append(
                    f"Tool '{worst}' failed {failure_counts[worst]}x recently. "
                    f"Should pre-validate or use alternative strategy.")

        # Success patterns
        if tool_successes:
            success_counts: Dict[str, int] = defaultdict(int)
            for t in tool_successes:
                success_counts[t] += 1
            best = max(success_counts, key=success_counts.get)  # type: ignore
            if success_counts[best] >= 3:
                insights.append(
                    f"Tool '{best}' is performing well "
                    f"({success_counts[best]} successes). "
                    f"Prefer it when appropriate.")

        # User correction patterns [#5]
        if corrections:
            unique_ctx = list(set(c for c in corrections if c))
            if unique_ctx:
                insights.append(
                    f"User corrected FRIDAY {len(corrections)}x recently. "
                    f"Areas: {', '.join(unique_ctx[:3])}")

        if not insights:
            return None

        reflection = (
            f"## Metacognitive Reflection — {_tag()}\n\n"
            f"**Observed patterns in recent {len(recent)} events:**\n\n"
        )
        for ins in insights:
            reflection += f"- {ins}\n"
        reflection += "\n"

        self.record_event(EventType.REFLECTION, {"insights": insights})

        return reflection

    # ── Learning File Management ────────────────────────────────────────────

    def _write_learning(self, learning: dict):
        """Write a learning entry to the learnings.md file."""
        _ensure_dir()

        dedup_key = (f"{learning['type']}:"
                     f"{learning.get('tool', '')}:"
                     f"{learning['insight'][:80]}")

        with self._lock:
            if dedup_key in self.written_learnings:
                return
            self.written_learnings.add(dedup_key)

        entry = self._format_learning_entry(learning)

        try:
            # Rotate file if too large [#1]
            if (LEARNINGS_FILE.exists()
                    and LEARNINGS_FILE.stat().st_size > MAX_LEARNINGS_FILE_SIZE):
                self._rotate_learnings_file()

            with open(LEARNINGS_FILE, "a", encoding="utf-8") as f:
                f.write(entry)

            self._save()
            print(f"[Learning] Wrote: {learning.get('type', 'learning')}")

        except Exception as e:
            print(f"[Learning] Write error: {e}")

    def _rotate_learnings_file(self):  # [#1]
        """Rotate learnings.md when it gets too large."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = LEARNINGS_DIR / f"learnings_{timestamp}.md"
            LEARNINGS_FILE.rename(backup)
            print(f"[Learning] Rotated learnings to {backup.name}")

            # Write fresh header
            header = (
                "# FRIDAY Learnings (rotated)\n\n"
                f"_Previous learnings archived to {backup.name}_\n\n"
                "---\n\n"
            )
            LEARNINGS_FILE.write_text(header, encoding="utf-8")
        except Exception as e:
            print(f"[Learning] Rotate error: {e}")

    def _format_learning_entry(self, learning: dict) -> str:
        """Format a learning event as a markdown entry."""
        lt = learning.get("type", "insight")
        ts = learning.get("timestamp", _tag())

        if lt == "failure_pattern":
            return (
                f"### Failure Pattern — {ts}\n"
                f"**Tool:** {learning.get('tool', '?')} | "
                f"**Context:** {learning.get('context', 'general')}\n\n"
                f"**Error:** {learning.get('error', '?')}\n\n"
                f"**Insight:** {learning.get('insight', '')}\n\n"
                f"**Recommendation:** {learning.get('recommendation', '')}\n\n"
                f"---\n\n"
            )
        elif lt == "success_pattern":
            return (
                f"### Confirmed Strategy — {ts}\n"
                f"**Tool:** {learning.get('tool', '?')} | "
                f"**Context:** {learning.get('context', 'general')}\n\n"
                f"**Insight:** {learning.get('insight', '')}\n\n"
                f"---\n\n"
            )
        elif lt == "user_preference":
            return (
                f"### User Preference — {ts}\n"
                f"**Insight:** {learning.get('insight', '')}\n\n"
                f"---\n\n"
            )
        elif lt == "evolution":
            return (
                f"### Evolution — {ts}\n"
                f"**Domain:** {learning.get('context', 'general')}\n\n"
                f"**Insight:** {learning.get('insight', '')}\n\n"
                f"**Change:** {learning.get('recommendation', '')}\n\n"
                f"---\n\n"
            )
        elif lt == "security_finding":
            return (
                f"### Security Finding — {ts}\n"
                f"**Vulnerability:** {learning.get('vuln_class', '?')} | "
                f"**CVSS:** {learning.get('cvss_score', 0)} | "
                f"**Confidence:** {learning.get('confidence', '?')}\n\n"
                f"**File:** {learning.get('file_path', '?')}\n\n"
                f"**Insight:** {learning.get('insight', '')}\n\n"
                f"**Recommendation:** {learning.get('recommendation', '')}\n\n"
                f"---\n\n"
            )
        else:
            return (
                f"### Learning — {ts}\n"
                f"**Type:** {lt}\n\n"
                f"**Insight:** {learning.get('insight', '')}\n\n"
                f"---\n\n"
            )

    def write_evolution_learning(
        self,
        insight: str,
        domain: str = "general",
        recommendation: str = "",
    ):
        """Write an evolution/growth learning (proactive improvement)."""
        learning = {
            "type":           "evolution",
            "insight":        insight,
            "context":        domain,
            "recommendation": recommendation,
            "timestamp":      _tag(),
            "source":         "evolution",
        }
        self._write_learning(learning)

    def write_user_preference(self, insight: str):
        """Write a user preference learning."""
        learning = {
            "type":      "user_preference",
            "insight":   insight,
            "timestamp": _tag(),
            "source":    "user_feedback",
        }
        self._write_learning(learning)

    # ── Consolidation ───────────────────────────────────────────────────────

    def consolidate(self):
        """
        Periodic consolidation: analyze buffer patterns and extract learnings.
        Like human sleep consolidation — replays experiences to find patterns.
        """
        with self._lock:
            if len(self.buffer) < 10:
                return

            recent = self.buffer[-100:]

            # Track tool transition patterns
            transitions: Dict[str, Dict[str, int]] = defaultdict(
                lambda: defaultdict(int))
            prev_tool = None
            for evt in recent:
                if evt["type"] in (EventType.TOOL_SUCCESS,
                                   EventType.TOOL_FAILURE):
                    tool = evt["data"].get("tool", "")
                    if tool and prev_tool and tool != prev_tool:
                        transitions[prev_tool][tool] += 1
                    if tool:
                        prev_tool = tool

            # Generate learnings from patterns
            for from_tool, to_tools in transitions.items():
                for to_tool, count in to_tools.items():
                    if count >= 3:
                        q_from = self.q_table[from_tool].get("general", 0)
                        q_to = self.q_table[to_tool].get("general", 0)
                        if q_from < 0 or q_to < 0:
                            self.write_evolution_learning(
                                f"Tools '{from_tool}' → '{to_tool}' used "
                                f"together {count}x. If {from_tool} has low "
                                f"success rate, consider skipping it and "
                                f"going directly to {to_tool}.",
                                domain="workflow_optimization",
                            )

        # Run reflection
        self.reflect()

        self._save()

    def _consolidation_loop(self):
        """Background thread: runs consolidation periodically."""
        while not self._stop_event.is_set():
            self._stop_event.wait(CONSOLIDATE_INTERVAL)
            if self._stop_event.is_set():
                break
            try:
                self.consolidate()
            except Exception as e:
                print(f"[Learning] Consolidation error: {e}")

    def _start_consolidation(self):
        if (self._consolidation_thread is None
                or not self._consolidation_thread.is_alive()):
            self._consolidation_thread = threading.Thread(
                target=self._consolidation_loop,
                daemon=True,
                name="LearningConsolidation",
            )
            self._consolidation_thread.start()

    def stop(self):
        """Gracefully stop the learning engine."""
        self._stop_event.set()
        self._save()

    # ── Query & Stats ───────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get learning engine statistics."""
        with self._lock:
            total_learnings = len(self.written_learnings)
            buffer_size = len(self.buffer)
            q_entries = sum(len(v) for v in self.q_table.values())
            tools_learned = list(self.q_table.keys())
            recent_events = self.buffer[-20:] if self.buffer else []

        type_dist: Dict[str, int] = defaultdict(int)
        for evt in recent_events:
            type_dist[evt["type"]] += 1

        return {
            "total_learnings":    total_learnings,
            "buffer_size":        buffer_size,
            "q_table_entries":    q_entries,
            "tools_with_q_data":  len(tools_learned),
            "last_events_by_type": dict(type_dist),
            "error_count":        self.error_count,
        }

    def format_learnings_for_prompt(self, max_entries: int = 5) -> str:
        """
        Get recent learnings formatted for system prompt inclusion.
        """
        if not LEARNINGS_FILE.exists():
            return ""

        try:
            content = LEARNINGS_FILE.read_text(encoding="utf-8")
            entries = content.split("---")
            recent = [e.strip() for e in entries if e.strip()][-max_entries:]
            if not recent:
                return ""

            result = (
                "[LEARNINGS — What I've learned from experience]\n"
                "These are patterns I've learned through trial and error. "
                "Use them to make better decisions.\n\n"
            )

            for entry in recent:
                result += entry.strip() + "\n\n"

            if len(result) > 1500:
                result = result[:1500] + "\n[...]\n"

            return result

        except Exception:
            return ""

    def get_learnings_summary(self) -> str:
        """Get a human-readable summary of all learnings."""
        if not LEARNINGS_FILE.exists():
            return "No learnings recorded yet."

        try:
            content = LEARNINGS_FILE.read_text(encoding="utf-8")
            entries = [e.strip() for e in content.split("---") if e.strip()]
            return f"{len(entries)} learnings recorded.\n\n" + content
        except Exception as e:
            return f"Error reading learnings: {e}"

    def get_recent_learnings(self, count: int = 10) -> List[dict]:  # [#6]
        """Get the most recent learning events from buffer."""
        with self._lock:
            return list(self.buffer[-count:])

    def get_tool_reliability(self, tool_name: str) -> dict:  # [#7]
        """Get reliability stats for a specific tool."""
        with self._lock:
            successes = sum(
                1 for e in self.buffer
                if e["type"] == EventType.TOOL_SUCCESS
                and e["data"].get("tool") == tool_name)
            failures = sum(
                1 for e in self.buffer
                if e["type"] == EventType.TOOL_FAILURE
                and e["data"].get("tool") == tool_name)
            total = successes + failures
            return {
                "tool":       tool_name,
                "successes":  successes,
                "failures":   failures,
                "total":      total,
                "success_rate": (round(successes / total * 100, 1)
                                 if total > 0 else 0.0),
                "q_value":    self.q_table[tool_name].get("general", 0.0),
            }

    def get_security_learnings(self, count: int = 5) -> list:
        """Get recent security-related learnings."""
        learnings = []
        try:
            if LEARNINGS_FILE.exists():
                content = LEARNINGS_FILE.read_text(encoding="utf-8")
                entries = content.split("---")
                for entry in entries:
                    if "Security Finding" in entry:
                        learnings.append(entry.strip())
                        if len(learnings) >= count:
                            break
        except Exception:
            pass
        return learnings

    def clear_buffer(self):  # [#8]
        """Clear working memory buffer (useful for testing)."""
        with self._lock:
            self.buffer.clear()
            self.error_count = 0
            self.consecutive_failures.clear()
        print("[Learning] Buffer cleared")


# ─── Singleton ───────────────────────────────────────────────────────────────

_engine: Optional[LearningEngine] = None
_engine_lock = threading.Lock()


def get_learning_engine() -> LearningEngine:
    """Get the singleton learning engine instance."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = LearningEngine()
    return _engine


# ─── Initialize learnings file ───────────────────────────────────────────────

def init_learnings_file():
    """Create the learnings.md file with a header if it doesn't exist."""
    _ensure_dir()
    if not LEARNINGS_FILE.exists():
        header = (
            "# FRIDAY Learnings\n\n"
            "_What I've learned through experience, reflection, and evolution._\n\n"
            "Each entry represents a real lesson — from mistakes, successes, "
            "user feedback, or metacognitive reflection.\n\n"
            "---\n\n"
        )
        LEARNINGS_FILE.write_text(header, encoding="utf-8")
        print("[Learning] Created learnings.md")


# ─── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_learnings_file()
    engine = get_learning_engine()

    print("Simulating learning events...")

    engine.record_tool_result("web_search", False, "general",
                              "Timeout: connection failed")
    engine.record_tool_result("web_search", False, "general",
                              "Timeout: connection failed")
    engine.record_tool_result("web_search", False, "general",
                              "Timeout: connection failed")

    engine.record_tool_result("weather_report", True, "weather")
    engine.record_tool_result("weather_report", True, "weather")
    engine.record_tool_result("weather_report", True, "weather")

    engine.record_user_feedback(True, "good job on the weather")

    reflection = engine.reflect(force=True)
    if reflection:
        print(f"Reflection generated:\n{reflection}")

    print(f"Stats: {engine.get_stats()}")
    print(f"\nLearnings file: {LEARNINGS_FILE}")

    print(f"\nQ-table samples:")
    for tool, contexts in engine.q_table.items():
        for ctx, val in contexts.items():
            print(f"  {tool}[{ctx}] = {val:.3f}")

    # Show reliability [#7]
    for tool in ("web_search", "weather_report"):
        rel = engine.get_tool_reliability(tool)
        print(f"\n{tool}: {rel}")
