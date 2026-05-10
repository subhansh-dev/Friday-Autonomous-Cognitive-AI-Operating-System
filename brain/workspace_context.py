"""
workspace_context.py — Workspace State Context Injection
=========================================================

Generates a textual summary of the Global Workspace state for injection
into Gemini prompts. This gives Gemini situational awareness about
FRIDAY's internal state — what she's thinking, feeling, predicting.
"""

import time
from typing import Optional

from brain.workspace_events import EventType, WorkspaceEvent
from brain.global_workspace import GlobalWorkspace, get_global_workspace


def generate_workspace_context(workspace: Optional[GlobalWorkspace] = None,
                               max_events: int = 5,
                               include_predictions: bool = True) -> str:
    """
    Generate a textual summary of the workspace state for Gemini prompt injection.

    Returns a string like:
        [WORKSPACE STATE]
        Active goals: [find flight to NYC]
        Emotional state: curious (0.7), calm (0.5)
        Recent events: [user asked about flights, memory recalled previous NYC trip]
        Active predictions: [browser_control likely succeeds, web_search may timeout]
        Curiosity targets: [flight_finder tool hasn't been used in 2 weeks]
        Autonomy ratio: 0.6 (mostly following instructions)
    """
    if workspace is None:
        workspace = get_global_workspace()

    sections = ["[WORKSPACE STATE]"]

    # Active goals
    goals = workspace.get_active_goals()
    if goals:
        sections.append(f"Active goals: {goals}")

    # Recent events summary
    recent = workspace.get_recent_events(max_events)
    if recent:
        event_summaries = []
        for evt in recent:
            source = evt.source
            etype = evt.type.value
            # Extract key info from content
            content = evt.content
            if etype == "user_input":
                text = content.get("text", "")
                if len(text) > 60:
                    text = text[:60] + "..."
                event_summaries.append(f"user said: '{text}'")
            elif etype == "tool_call":
                tool = content.get("tool", "?")
                event_summaries.append(f"called {tool}")
            elif etype == "tool_result":
                tool = content.get("tool", "?")
                success = content.get("success", True)
                event_summaries.append(f"{tool} {'succeeded' if success else 'failed'}")
            elif etype == "emotion_change":
                emotion = content.get("emotion", "?")
                intensity = content.get("intensity", 0)
                event_summaries.append(f"emotion: {emotion} ({intensity:.1f})")
            elif etype == "error":
                event_summaries.append(f"error from {source}")
            elif etype == "curiosity":
                topic = content.get("topic", "?")
                event_summaries.append(f"curious about {topic}")
            else:
                event_summaries.append(f"{source}:{etype}")
        sections.append(f"Recent events: [{', '.join(event_summaries)}]")

    # Emotional state from self-awareness module
    emotional_state = _get_emotional_state()
    if emotional_state:
        sections.append(f"Emotional state: {emotional_state}")

    # Active predictions from active inference
    if include_predictions:
        predictions = _get_predictions()
        if predictions:
            sections.append(f"Active predictions: {predictions}")

    # Curiosity targets
    curiosity = _get_curiosity_targets()
    if curiosity:
        sections.append(f"Curiosity targets: {curiosity}")

    # Autonomy ratio
    autonomy = _get_autonomy_info()
    if autonomy:
        sections.append(f"Autonomy: {autonomy}")

    # Patterns detected
    patterns = workspace._pattern_detector.get_patterns()
    if patterns:
        recent_patterns = [p for p in patterns if time.time() - p.get("detected_at", 0) < 3600]
        if recent_patterns:
            pattern_summaries = [p.get("type", "?") for p in recent_patterns[:3]]
            sections.append(f"Recent patterns: [{', '.join(pattern_summaries)}]")

    return "\n".join(sections)


def _get_emotional_state() -> str:
    """Get emotional state from self-awareness module."""
    try:
        from brain.self_awareness import get_self_awareness
        sa = get_self_awareness()
        if hasattr(sa, 'emotional_model'):
            em = sa.emotional_model
            states = []
            for emotion_name in ["curiosity", "satisfaction", "concern", "frustration",
                                  "confidence", "wonder", "calm", "alertness"]:
                intensity = em.get_intensity(emotion_name) if hasattr(em, 'get_intensity') else 0
                if intensity > 0.3:
                    states.append(f"{emotion_name} ({intensity:.1f})")
            if states:
                return ", ".join(states[:4])  # Top 4 emotions
    except Exception:
        pass
    return ""


def _get_predictions() -> str:
    """Get active predictions from the active inference engine."""
    try:
        from brain.active_inference import get_active_inference
        ai = get_active_inference()
        if hasattr(ai, '_data') and 'world_model' in ai._data:
            predictions = []
            for tool, model in list(ai._data["world_model"].items())[:3]:
                success_rate = model.get("expected_success_rate", 0.5)
                uncertainty = model.get("uncertainty", 0.5)
                if uncertainty < 0.5:
                    predictions.append(f"{tool} likely {'succeeds' if success_rate > 0.6 else 'fails'}")
                else:
                    predictions.append(f"{tool} uncertain")
            if predictions:
                return "[" + ", ".join(predictions) + "]"
    except Exception:
        pass
    return ""


def _get_curiosity_targets() -> str:
    """Get curiosity module's top exploration targets."""
    try:
        from brain.curiosity import get_curiosity_module
        cm = get_curiosity_module()
        if hasattr(cm, '_data') and 'curiosity_queue' in cm._data:
            queue = cm._data["curiosity_queue"]
            if queue:
                targets = [item.get("tool", item.get("topic", "?")) for item in queue[:3]]
                return "[" + ", ".join(targets) + "]"
    except Exception:
        pass
    return ""


def _get_autonomy_info() -> str:
    """Get autonomy ratio from self-awareness module."""
    try:
        from brain.self_awareness import get_self_awareness
        sa = get_self_awareness()
        if hasattr(sa, 'autonomy_tracker'):
            at = sa.autonomy_tracker
            ratio = at.get_autonomy_ratio() if hasattr(at, 'get_autonomy_ratio') else 0.5
            if ratio > 0.7:
                desc = "mostly autonomous"
            elif ratio > 0.4:
                desc = "balanced"
            else:
                desc = "mostly following instructions"
            return f"{ratio:.1f} ({desc})"
    except Exception:
        pass
    return ""


def inject_workspace_context(prompt: str, workspace: Optional[GlobalWorkspace] = None) -> str:
    """
    Inject workspace context into a Gemini prompt.
    Appends the workspace state after the original prompt.
    """
    context = generate_workspace_context(workspace)
    if context and context != "[WORKSPACE STATE]":
        return f"{prompt}\n\n{context}"
    return prompt
