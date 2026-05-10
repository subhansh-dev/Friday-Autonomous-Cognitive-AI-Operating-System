"""
Base security agent. Each agent has a narrow role and tool whitelist.
Inspired by Bounty Hunter's agent architecture — specialization prevents hallucination.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum
import time
import uuid
import logging

logger = logging.getLogger("friday.agents")


class AgentRole(Enum):
    RECON = "recon"
    HUNTER = "hunter"
    EXPLOIT = "exploit"
    CHAIN = "chain"
    VERIFY = "verify"
    GRADER = "grader"
    REPORTER = "reporter"


@dataclass
class AgentDecision:
    """A reasoning decision made by an agent."""
    decision: str
    reasoning: str
    confidence: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentResult:
    """Result from an agent's execution."""
    agent_id: str
    role: AgentRole
    findings: List[dict] = field(default_factory=list)
    decisions: List[AgentDecision] = field(default_factory=list)
    duration_ms: float = 0
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "findings_count": len(self.findings),
            "decisions_count": len(self.decisions),
            "duration_ms": self.duration_ms,
            "error": self.error,
            "metadata": self.metadata,
        }


class BaseAgent(ABC):
    """
    Base class for all security agents.

    Each agent has:
    - A specific role (recon, hunter, exploit, chain, verify, grader, reporter)
    - A tool whitelist (only tools relevant to its job)
    - An execute() method that takes context and returns AgentResult
    """
    role: AgentRole = None
    tool_whitelist: List[str] = []
    description: str = ""

    def __init__(self):
        if self.role is None:
            raise ValueError("Agent subclass must define class-level `role`")
        self.agent_id = f"{self.role.value}_{uuid.uuid4().hex[:8]}"
        self._decisions: List[AgentDecision] = []
        self.logger = logging.getLogger(f"friday.agents.{self.role.value}")

    @abstractmethod
    def execute(self, context: dict) -> AgentResult:
        """
        Execute the agent's task with given context.

        Args:
            context: dict with task-specific data. Common keys:
                - target: target URL or path
                - session_id: current assessment session
                - findings: list of findings (for chain/verify/grade)
                - attack_surface: recon data (for hunter)
                - config: agent-specific configuration

        Returns:
            AgentResult with findings, decisions, and metadata
        """
        pass

    def record_decision(self, decision: str, reasoning: str, confidence: float):
        """Record a reasoning decision with full context."""
        d = AgentDecision(
            decision=decision,
            reasoning=reasoning,
            confidence=max(0, min(1, confidence)),
        )
        self._decisions.append(d)
        self.logger.debug(f"[{self.agent_id}] Decision: {decision} (conf={confidence:.2f})")

    def can_use_tool(self, tool_name: str) -> bool:
        """Check if this agent is allowed to use a given tool."""
        return tool_name in self.tool_whitelist

    def _build_result(self, findings: List[dict] = None, metadata: dict = None,
                      error: str = None) -> AgentResult:
        """Helper to build an AgentResult."""
        return AgentResult(
            agent_id=self.agent_id,
            role=self.role,
            findings=findings or [],
            decisions=list(self._decisions),
            error=error,
            metadata=metadata or {},
        )
