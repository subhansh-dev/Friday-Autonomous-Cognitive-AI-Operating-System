"""
workspace_adapters.py — Adapters to connect existing brain modules to the Global Workspace
==========================================================================================

Each adapter wraps an existing module as a WorkspaceParticipant, translating
between workspace events and the module's native API.

This approach minimizes changes to existing modules — they keep their current
interface, and adapters bridge the gap.
"""

import asyncio
import time
from typing import List, Optional

from brain.workspace_events import EventType, WorkspaceEvent
from brain.global_workspace import WorkspaceParticipant


class SelfAwarenessAdapter(WorkspaceParticipant):
    """Connects the self-awareness module (consciousness) to the workspace."""

    def __init__(self, self_awareness):
        self._sa = self_awareness

    def get_name(self) -> str:
        return "SelfAwareness"

    def get_interests(self) -> List[EventType]:
        return [
            EventType.USER_INPUT, EventType.TOOL_RESULT, EventType.ERROR,
            EventType.EMOTION_CHANGE, EventType.CURIOSITY, EventType.REFLECTION,
            EventType.GROWTH_MILESTONE, EventType.SUCCESS_NOVEL_TASK,
            EventType.LIMITATION_DISCOVERED, EventType.DECISION,
            EventType.TOOL_CALL,
        ]

    async def on_workspace_event(self, event: WorkspaceEvent):
        try:
            if hasattr(self._sa, 'process_interaction'):
                self._sa.process_interaction(
                    event.type.value,
                    {"source": event.source, **event.content},
                )
        except Exception:
            pass


class LearningAdapter(WorkspaceParticipant):
    """Connects the Q-learning engine to the workspace."""

    def __init__(self, learning_engine):
        self._le = learning_engine

    def get_name(self) -> str:
        return "Learning"

    def get_interests(self) -> List[EventType]:
        return [EventType.TOOL_RESULT, EventType.ERROR, EventType.USER_INPUT]

    async def on_workspace_event(self, event: WorkspaceEvent):
        try:
            if event.type == EventType.TOOL_RESULT:
                tool = event.content.get("tool", "unknown")
                success = event.content.get("success", False)
                if hasattr(self._le, 'record_event'):
                    event_type = "tool_success" if success else "tool_failure"
                    self._le.record_event(event_type, {
                        "tool": tool,
                        "success": success,
                        "source": event.source,
                    })
            elif event.type == EventType.ERROR:
                if hasattr(self._le, 'record_event'):
                    self._le.record_event("tool_failure", {
                        "tool": event.content.get("tool", "unknown"),
                        "error": event.content.get("error", ""),
                        "source": event.source,
                    })
        except Exception:
            pass


class ActiveInferenceAdapter(WorkspaceParticipant):
    """Connects the active inference engine to the workspace."""

    def __init__(self, active_inference):
        self._ai = active_inference

    def get_name(self) -> str:
        return "ActiveInference"

    def get_interests(self) -> List[EventType]:
        return [EventType.TOOL_RESULT, EventType.PREDICTION]

    async def on_workspace_event(self, event: WorkspaceEvent):
        try:
            if event.type == EventType.TOOL_RESULT:
                tool = event.content.get("tool", "unknown")
                success = event.content.get("success", False)
                duration = event.content.get("duration_ms", 0)
                # Predict first, then compute prediction error
                if hasattr(self._ai, 'predict_outcome') and hasattr(self._ai, 'compute_prediction_error'):
                    prediction = self._ai.predict_outcome(tool)
                    self._ai.compute_prediction_error(tool, prediction, success, float(duration))
        except Exception:
            pass


class CuriosityAdapter(WorkspaceParticipant):
    """Connects the curiosity module to the workspace."""

    def __init__(self, curiosity_module):
        self._cm = curiosity_module

    def get_name(self) -> str:
        return "Curiosity"

    def get_interests(self) -> List[EventType]:
        return [EventType.TOOL_CALL, EventType.USER_INPUT, EventType.NOVELTY]

    async def on_workspace_event(self, event: WorkspaceEvent):
        try:
            if event.type == EventType.TOOL_CALL:
                tool = event.content.get("tool", "unknown")
                if hasattr(self._cm, 'encounter'):
                    self._cm.encounter(tool)
            elif event.type == EventType.USER_INPUT:
                text = event.content.get("text", "")
                if hasattr(self._cm, 'track_user_topic'):
                    self._cm.track_user_topic(text)
        except Exception:
            pass


class DreamingAdapter(WorkspaceParticipant):
    """Connects the dreaming module to the workspace (cold path integration)."""

    def __init__(self, dreaming_module):
        self._dm = dreaming_module

    def get_name(self) -> str:
        return "Dreaming"

    def get_interests(self) -> List[EventType]:
        return [EventType.CONSOLIDATION_TRIGGER]

    async def on_workspace_event(self, event: WorkspaceEvent):
        try:
            if event.type == EventType.CONSOLIDATION_TRIGGER:
                if hasattr(self._dm, 'force_dream_cycle'):
                    self._dm.force_dream_cycle()
        except Exception:
            pass


class SelfModelAdapter(WorkspaceParticipant):
    """Connects the self-model to the workspace."""

    def __init__(self, self_model):
        self._sm = self_model

    def get_name(self) -> str:
        return "SelfModel"

    def get_interests(self) -> List[EventType]:
        return [EventType.TOOL_RESULT, EventType.SKILL_CHANGE]

    async def on_workspace_event(self, event: WorkspaceEvent):
        try:
            if event.type == EventType.TOOL_RESULT:
                tool = event.content.get("tool", "unknown")
                success = event.content.get("success", False)
                duration = event.content.get("duration_ms", 0)
                error = event.content.get("result", "") if not success else ""
                if hasattr(self._sm, 'record_tool_result'):
                    self._sm.record_tool_result(tool, success, float(duration), error[:100])
        except Exception:
            pass


class NeuralMemoryAdapter(WorkspaceParticipant):
    """Connects the neural memory to the workspace — encodes ALL events."""

    def __init__(self, neural_memory):
        self._nm = neural_memory

    def get_name(self) -> str:
        return "NeuralMemory"

    def get_interests(self) -> List[EventType]:
        return list(EventType)  # Interested in everything

    async def on_workspace_event(self, event: WorkspaceEvent):
        try:
            if hasattr(self._nm, 'encode'):
                importance = "high" if event.importance > 0.7 else "medium" if event.importance > 0.4 else "low"
                self._nm.encode(
                    category=f"workspace_{event.type.value}",
                    key=event.event_id,
                    value=event.content,
                    importance=importance,
                )
        except Exception:
            pass


class EpisodicMemoryAdapter(WorkspaceParticipant):
    """Connects episodic memory to the workspace."""

    def __init__(self, episodic_memory):
        self._em = episodic_memory

    def get_name(self) -> str:
        return "EpisodicMemory"

    def get_interests(self) -> List[EventType]:
        return [EventType.USER_INPUT, EventType.TOOL_CALL, EventType.TOOL_RESULT]

    async def on_workspace_event(self, event: WorkspaceEvent):
        try:
            if hasattr(self._em, 'encode_event'):
                # episodic_memory uses 1-10 importance scale, workspace uses 0-1
                importance = max(1.0, min(10.0, event.importance * 10))
                content_str = str(event.content)[:300]
                self._em.encode_event(
                    event_type=event.type.value,
                    content=content_str,
                    context={"source": event.source, "event_id": event.event_id},
                    importance=importance,
                )
        except Exception:
            pass


class ProceduralMemoryAdapter(WorkspaceParticipant):
    """Connects procedural memory to the workspace."""

    def __init__(self, procedural_memory):
        self._pm = procedural_memory

    def get_name(self) -> str:
        return "ProceduralMemory"

    def get_interests(self) -> List[EventType]:
        return [EventType.MULTI_STEP_RESULT, EventType.TOOL_RESULT]

    async def on_workspace_event(self, event: WorkspaceEvent):
        try:
            if event.type == EventType.MULTI_STEP_RESULT and hasattr(self._pm, 'learn_procedure'):
                steps = event.content.get("steps", [])
                success = event.content.get("success", False)
                goal = event.content.get("goal", "multi-step task")
                if steps and success:
                    self._pm.learn_procedure(goal, steps, context=event.content)
        except Exception:
            pass


class MetaCognitionAdapter(WorkspaceParticipant):
    """Connects metacognition to the workspace — observes cross-module patterns."""

    def __init__(self, self_awareness):
        self._sa = self_awareness

    def get_name(self) -> str:
        return "MetaCognition"

    def get_interests(self) -> List[EventType]:
        return [EventType.TOOL_CALL, EventType.DECISION, EventType.ERROR]

    async def on_workspace_event(self, event: WorkspaceEvent):
        try:
            if hasattr(self._sa, 'metacognition') and hasattr(self._sa.metacognition, 'log_behavior'):
                self._sa.metacognition.log_behavior(event.type.value, event.content)
        except Exception:
            pass


class MemoryCoordinatorAdapter(WorkspaceParticipant):
    """Connects the memory coordinator to the workspace."""

    def __init__(self, coordinator):
        self._coord = coordinator

    def get_name(self) -> str:
        return "MemoryCoordinator"

    def get_interests(self) -> List[EventType]:
        return [EventType.MEMORY_RECALL, EventType.WORKSPACE_SUMMARY]

    async def on_workspace_event(self, event: WorkspaceEvent):
        try:
            if event.type == EventType.MEMORY_RECALL and hasattr(self._coord, 'recall'):
                query = event.content.get("query", "")
                if query:
                    self._coord.recall(query, top_k=5)
        except Exception:
            pass
