"""
workspace_events.py — Global Workspace Event Types
===================================================
Defines the event taxonomy and data structures for the Global Workspace.
Every module communicates through these events.
"""

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class EventType(Enum):
    """All event types that flow through the Global Workspace."""
    USER_INPUT = "user_input"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    EMOTION_CHANGE = "emotion_change"
    MEMORY_RECALL = "memory_recall"
    CURIOSITY = "curiosity"
    REFLECTION = "reflection"
    GOAL = "goal"
    PLAN_STEP = "plan_step"
    DECISION = "decision"
    PRE_EXECUTION = "pre_execution"
    GROWTH_MILESTONE = "growth_milestone"
    PREDICTION = "prediction"
    CONSOLIDATION_TRIGGER = "consolidation_trigger"
    WORKSPACE_SUMMARY = "workspace_summary"
    REPLAN_NEEDED = "replan_needed"
    MULTI_STEP_RESULT = "multi_step_result"
    SUCCESS_NOVEL_TASK = "success_novel_task"
    LIMITATION_DISCOVERED = "limitation_discovered"
    NOVELTY = "novelty"
    SKILL_CHANGE = "skill_change"


@dataclass
class WorkspaceEvent:
    """A single event in the Global Workspace."""
    source: str                        # Which module generated this
    type: EventType                    # Event classification
    content: dict                      # The actual data
    importance: float = 0.5            # 0.0 - 1.0, computed by attention engine
    timestamp: float = field(default_factory=time.time)
    requires_response: bool = False    # Does this need action?
    context: dict = field(default_factory=dict)  # Links to related events
    vetoed: bool = False               # Security layer can veto
    event_id: str = ""                 # Unique ID

    def __post_init__(self):
        if not self.event_id:
            self.event_id = f"{self.source}_{self.type.value}_{int(self.timestamp * 1000)}"

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "source": self.source,
            "type": self.type.value,
            "content": self.content,
            "importance": round(self.importance, 4),
            "timestamp": self.timestamp,
            "requires_response": self.requires_response,
            "context": self.context,
            "vetoed": self.vetoed,
        }

    def summary(self) -> str:
        content_str = str(self.content)
        if len(content_str) > 100:
            content_str = content_str[:100] + "..."
        return f"[{self.source}:{self.type.value}] {content_str}"
