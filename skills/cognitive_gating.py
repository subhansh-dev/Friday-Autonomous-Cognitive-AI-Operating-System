# -*- coding: utf-8 -*-
"""
cognitive_gating.py — FRIDAY Cognitive Load Manager
====================================================
Routes incoming requests through appropriate processing pipelines based on
complexity. Inspired by Kahneman's dual-process theory (System 1 vs System 2).

Scoring:
  0-2  → direct response (no reasoning overhead)
  3-5  → single-pass reasoning
  6-8  → thinking_loop (multi-pass)
  9-10 → full agent pipeline (multi-tool orchestration)

Replaces the brittle keyword-matching in thinking_loop.py with a weighted
multi-signal classifier.
"""

import re
from typing import Optional


# ── Signal weights ──────────────────────────────────────────────────────────

_MULTI_STEP_MARKERS = [
    "and then", "after that", "also", "first", "then", "finally",
    "once that's done", "when that's finished", "next",
]

_TOOL_DENSITY_MARKERS = [
    "search", "find", "open", "send", "save", "download", "create",
    "write", "build", "make", "install", "configure", "check", "scan",
    "analyze", "compare", "summarize", "generate", "update", "delete",
    "move", "copy", "rename", "compress", "extract",
]

_AMBIGUITY_MARKERS = [
    "something like", "kind of", "maybe", "not sure", "figure out",
    "whatever", "something", "anything", "somehow", "probably",
]

_DOMAIN_COMPLEX = [
    "security", "pentest", "vulnerability", "exploit", "recon",
    "architecture", "refactor", "migration", "deploy", "ci/cd",
    "database", "schema", "api", "authentication", "encryption",
    "machine learning", "neural", "training", "model",
]

_SIMPLE_OVERRIDE = [
    "what time", "what's the time", "weather", "play ", "open ",
    "volume", "mute", "unmute", "pause", "stop", "yes", "no",
    "thanks", "thank you", "ok", "okay", "got it", "sure",
    "hello", "hi", "hey", "morning", "good night",
]


def _count_markers(text: str, markers: list[str]) -> int:
    text_lower = text.lower()
    return sum(1 for m in markers if m in text_lower)


def assess_complexity(text: str) -> dict:
    """
    Assess the cognitive complexity of a request.

    Returns:
        {
            "score": 0-10,
            "tier": "direct" | "single_pass" | "thinking_loop" | "full_agent",
            "signals": {signal_name: score_contribution},
            "reasoning": "human-readable explanation",
        }
    """
    text_stripped = text.strip()
    text_lower = text_stripped.lower()
    word_count = len(text_stripped.split())

    # Simple override — short-circuit
    for trigger in _SIMPLE_OVERRIDE:
        if text_lower.startswith(trigger) or trigger in text_lower:
            return {
                "score": 0,
                "tier": "direct",
                "signals": {"simple_override": 0},
                "reasoning": f"Matched simple trigger '{trigger.strip()}'",
            }

    signals = {}

    # Signal 1: Length (0-2 points)
    if word_count > 30:
        signals["length"] = 2
    elif word_count > 15:
        signals["length"] = 1
    else:
        signals["length"] = 0

    # Signal 2: Multi-step indicators (0-3 points)
    multi_step = _count_markers(text_stripped, _MULTI_STEP_MARKERS)
    signals["multi_step"] = min(3, multi_step)

    # Signal 3: Tool density — how many different actions implied (0-2 points)
    tool_hits = _count_markers(text_stripped, _TOOL_DENSITY_MARKERS)
    signals["tool_density"] = min(2, max(0, tool_hits - 1))

    # Signal 4: Ambiguity — vagueness requires more reasoning (0-1 point)
    ambiguity = _count_markers(text_stripped, _AMBIGUITY_MARKERS)
    signals["ambiguity"] = min(1, ambiguity)

    # Signal 5: Domain complexity (0-2 points)
    domain = _count_markers(text_stripped, _DOMAIN_COMPLEX)
    signals["domain_complexity"] = min(2, domain)

    # Signal 6: Question mark count (multiple questions = multi-part)
    q_count = text_stripped.count("?")
    if q_count >= 3:
        signals["questions"] = 1
    else:
        signals["questions"] = 0

    total = sum(signals.values())
    total = min(10, max(0, total))

    # Determine tier
    if total <= 2:
        tier = "direct"
    elif total <= 5:
        tier = "single_pass"
    elif total <= 8:
        tier = "thinking_loop"
    else:
        tier = "full_agent"

    reasoning_parts = []
    for sig, val in signals.items():
        if val > 0:
            reasoning_parts.append(f"{sig}={val}")

    return {
        "score": total,
        "tier": tier,
        "signals": signals,
        "reasoning": ", ".join(reasoning_parts) if reasoning_parts else "all signals low",
    }


def should_use_thinking_loop(text: str) -> bool:
    """Quick check: does this request need the thinking loop?"""
    result = assess_complexity(text)
    return result["tier"] in ("thinking_loop", "full_agent")


def should_use_full_agent(text: str) -> bool:
    """Quick check: does this request need the full agent pipeline?"""
    result = assess_complexity(text)
    return result["tier"] == "full_agent"


def format_assessment(text: str, max_chars: int = 200) -> str:
    """Format assessment for logging/debugging."""
    result = assess_complexity(text)
    return (
        f"[COGNITIVE GATE] score={result['score']} tier={result['tier']} "
        f"signals={result['reasoning']}"
    )[:max_chars]
