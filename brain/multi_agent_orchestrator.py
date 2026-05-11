#!/usr/bin/env python3
"""
multi_agent_orchestrator.py — Simultaneous Multi-Agent Orchestration Engine
=============================================================================

Enables Friday to run multiple agency agents in parallel, have them debate,
chain them in pipelines, and synthesize their outputs into coherent results.

Inspired by:

  [MAO-1] Multi-Agent Systems (Wooldridge, 2009)
          — Autonomous agents that cooperate, compete, and coordinate
            to solve problems beyond individual agent capabilities.

  [MAO-2] Society of Mind (Minsky, 1986)
          — Intelligence emerges from the interaction of many simple agents,
            each handling a small piece of the problem space.

  [MAO-3] Ensemble Methods (Dietterich, 2000)
          — Combining multiple diverse models/agents typically outperforms
            any single model, reducing bias and variance.

  [MAO-4] Deliberation Networks (Du et al., 2023)
          — Multi-round debate among agents surfaces better answers than
            single-shot generation by forcing agents to challenge assumptions.

Key behaviors:
  - Six execution modes: parallel, debate, pipeline, voting, specialist, swarm
  - Pre-defined agent teams for common workflows
  - Agent reliability tracking with success/failure rates
  - Synthesis engine that merges diverse agent outputs
  - Full persistence and thread-safe operation
"""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Constants ──────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent
AGENTS_DIR = BASE_DIR / "agents"
BRAIN_DIR = Path(__file__).resolve().parent
ORCHESTRATOR_FILE = BRAIN_DIR / "multi_agent_state.json"

# Execution
MAX_WORKERS = 10
AGENT_TIMEOUT_S = 120
MAX_SYNTHESIS_INPUT = 3000     # chars per agent in synthesis prompt
MAX_AGENT_OUTPUT = 2000        # chars per agent in cross-pollination
SWARM_MAX_AGENTS = 5           # limit agents per swarm refinement round
SWARM_DEFAULT_ROUNDS = 5       # default swarm refinement rounds


# ── Data Classes ───────────────────────────────────────────────────────────

class ExecutionMode(Enum):
    """How agents are orchestrated."""
    PARALLEL = "parallel"        # All agents run simultaneously
    DEBATE = "debate"            # Agents argue, cross-pollinate, synthesize
    PIPELINE = "pipeline"        # A output → B input → C input
    VOTING = "voting"            # Agents vote, majority wins
    SPECIALIST = "specialist"    # Route to best agent for the task
    SWARM = "swarm"              # Self-organizing agent swarm


@dataclass
class AgentResult:
    """Result from a single agent execution."""
    agent_name: str
    output: str
    confidence: float = 0.0
    execution_time: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamConfig:
    """Configuration for an agent team."""
    name: str
    agents: List[str]
    mode: ExecutionMode
    rounds: int = 1              # for debate mode
    synthesizer: Optional[str] = None  # agent that synthesizes results


# ── Agent Directory Map ────────────────────────────────────────────────────

AGENT_MAP = {
    "ai_engineer": "engineering/ai_engineer.md",
    "backend_architect": "engineering/backend_architect.md",
    "codebase_onboarding_engineer": "engineering/codebase_onboarding_engineer.md",
    "code_reviewer": "engineering/code_reviewer.md",
    "database_optimizer": "engineering/database_optimizer.md",
    "data_engineer": "engineering/data_engineer.md",
    "devops_automator": "engineering/devops_automator.md",
    "frontend_developer": "engineering/frontend_developer.md",
    "git_workflow_master": "engineering/git_workflow_master.md",
    "incident_response_commander": "engineering/incident_response_commander.md",
    "mobile_app_builder": "engineering/mobile_app_builder.md",
    "rapid_prototyper": "engineering/rapid_prototyper.md",
    "security_engineer": "engineering/security_engineer.md",
    "senior_developer": "engineering/senior_developer.md",
    "software_architect": "engineering/software_architect.md",
    "sre": "engineering/sre.md",
    "technical_writer": "engineering/technical_writer.md",
    "threat_detection_engineer": "engineering/threat_detection_engineer.md",
    "voice_ai_integration_engineer": "engineering/voice_ai_integration_engineer.md",
    "accessibility_auditor": "testing/accessibility_auditor.md",
    "api_tester": "testing/api_tester.md",
    "performance_benchmarker": "testing/performance_benchmarker.md",
    "test_results_analyzer": "testing/test_results_analyzer.md",
    "workflow_optimizer": "testing/workflow_optimizer.md",
    "compliance_auditor": "specialized/compliance_auditor.md",
    "document_generator": "specialized/document_generator.md",
    "language_translator": "specialized/language_translator.md",
    "workflow_architect": "specialized/workflow_architect.md",
    "ui_designer": "design/ui_designer.md",
    "ux_architect": "design/ux_architect.md",
}


# ── Orchestrator ───────────────────────────────────────────────────────────

class MultiAgentOrchestrator:
    """
    Orchestrate multiple agency agents simultaneously.

    Supports six execution modes:
      - parallel:  All agents run at once, results collected
      - debate:    Agents argue across rounds, cross-pollinate, then synthesize
      - pipeline:  Sequential chain — each agent's output feeds the next
      - voting:    Agents vote on options, majority wins
      - specialist: Agents self-assess relevance, top N run the task
      - swarm:     Iterative refinement until convergence
    """

    # Pre-defined agent teams
    AGENT_TEAMS: Dict[str, TeamConfig] = {
        "full_stack_build": TeamConfig(
            name="Full Stack Build Team",
            agents=["software_architect", "frontend_developer", "backend_architect",
                    "database_optimizer", "api_tester", "security_engineer"],
            mode=ExecutionMode.PARALLEL,
            synthesizer="software_architect"
        ),
        "code_review": TeamConfig(
            name="Code Review Team",
            agents=["code_reviewer", "security_engineer", "performance_benchmarker",
                    "accessibility_auditor"],
            mode=ExecutionMode.PARALLEL,
            synthesizer="code_reviewer"
        ),
        "research": TeamConfig(
            name="Research Team",
            agents=["ai_engineer", "data_engineer", "technical_writer"],
            mode=ExecutionMode.PIPELINE,
        ),
        "design": TeamConfig(
            name="Design Team",
            agents=["ui_designer", "ux_architect", "frontend_developer"],
            mode=ExecutionMode.DEBATE,
            rounds=2,
            synthesizer="ux_architect"
        ),
        "incident_response": TeamConfig(
            name="Incident Response Team",
            agents=["incident_response_commander", "sre", "security_engineer",
                    "threat_detection_engineer"],
            mode=ExecutionMode.SPECIALIST,
            synthesizer="incident_response_commander"
        ),
        "security_audit": TeamConfig(
            name="Security Audit Team",
            agents=["security_engineer", "threat_detection_engineer", "compliance_auditor",
                    "code_reviewer"],
            mode=ExecutionMode.PARALLEL,
            synthesizer="security_engineer"
        ),
        "testing": TeamConfig(
            name="Testing Team",
            agents=["api_tester", "performance_benchmarker", "accessibility_auditor",
                    "workflow_optimizer", "test_results_analyzer"],
            mode=ExecutionMode.PIPELINE,
        ),
    }

    # Include ALL 30 agents for the "all" team
    ALL_AGENTS: List[str] = [
        "ai_engineer", "backend_architect", "codebase_onboarding_engineer",
        "code_reviewer", "database_optimizer", "data_engineer", "devops_automator",
        "frontend_developer", "git_workflow_master", "incident_response_commander",
        "mobile_app_builder", "rapid_prototyper", "security_engineer",
        "senior_developer", "software_architect", "sre", "technical_writer",
        "threat_detection_engineer", "voice_ai_integration_engineer",
        "accessibility_auditor", "api_tester", "performance_benchmarker",
        "test_results_analyzer", "workflow_optimizer",
        "compliance_auditor", "document_generator", "language_translator",
        "workflow_architect", "ui_designer", "ux_architect"
    ]

    def __init__(self):
        self._lock = threading.RLock()
        self._data = self._load()
        self._executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        self._agent_cache: Dict[str, str] = {}
        self._execution_history: List[Dict] = []
        self._load_all_agent_prompts()

    # ── Persistence ────────────────────────────────────────────────────

    def _load(self) -> dict:
        """Load orchestrator state from disk."""
        if ORCHESTRATOR_FILE.exists():
            try:
                return json.loads(ORCHESTRATOR_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "meta": {"version": 1, "total_executions": 0, "total_agents_spawned": 0},
            "execution_history": [],
            "team_performance": {},
            "agent_reliability": {},
        }

    def _save(self):
        """Persist state to disk."""
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._data["meta"]["last_update"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            ORCHESTRATOR_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8"
            )

    # ── Agent Prompt Cache ─────────────────────────────────────────────

    def _load_all_agent_prompts(self):
        """Pre-load all agent markdown files into cache."""
        for name, rel_path in AGENT_MAP.items():
            full_path = AGENTS_DIR / rel_path
            if full_path.exists():
                try:
                    self._agent_cache[name] = full_path.read_text(encoding="utf-8")
                except Exception:
                    pass

    def _get_agent_prompt(self, agent_name: str) -> Optional[str]:
        """Get cached agent prompt."""
        return self._agent_cache.get(agent_name)

    # ── Single Agent Execution ─────────────────────────────────────────

    def _run_single_agent(self, agent_name: str, task: str, context: str = "",
                          shared_state: Optional[Dict] = None) -> AgentResult:
        """Run a single agent and return its result."""
        start = time.time()
        prompt = self._get_agent_prompt(agent_name)
        if not prompt:
            return AgentResult(
                agent_name=agent_name, output="",
                error=f"Agent '{agent_name}' not found in cache"
            )

        # Build the full prompt
        full_prompt = (
            "You are now operating as the agent defined in the system prompt. "
            "Follow all rules, workflows, and deliverable formats defined there.\n\n"
            f"## Task\n{task}"
        )
        if context:
            full_prompt += f"\n\n## Context / Input\n{context}"
        if shared_state:
            full_prompt += (
                f"\n\n## Shared Team State\n"
                f"{json.dumps(shared_state, indent=2, default=str)[:MAX_SYNTHESIS_INPUT]}"
            )

        try:
            from google.genai import types
            from actions.resilience import api_retry

            # Get API client
            config_path = BASE_DIR / "config" / "api_keys.json"
            api_key = json.loads(config_path.read_text()).get("gemini_api_key", "")
            from google import genai
            client = genai.Client(api_key=api_key)

            def _call():
                cfg = types.GenerateContentConfig(
                    system_instruction=prompt,
                    max_output_tokens=8192,
                )
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=full_prompt,
                    config=cfg,
                )
                result = response.text.strip()
                if not result:
                    raise ValueError("Agent returned empty response")
                return result

            output = api_retry(_call, max_retries=2, base_delay=1.0, max_delay=30.0)
            elapsed = time.time() - start

            # Track reliability
            with self._lock:
                if agent_name not in self._data["agent_reliability"]:
                    self._data["agent_reliability"][agent_name] = {
                        "successes": 0, "failures": 0, "avg_time": 0.0
                    }
                rel = self._data["agent_reliability"][agent_name]
                rel["successes"] += 1
                n = rel["successes"]
                rel["avg_time"] = (rel["avg_time"] * (n - 1) + elapsed) / n

            return AgentResult(
                agent_name=agent_name, output=output, confidence=0.8,
                execution_time=elapsed,
                metadata={"prompt_tokens": len(full_prompt) // 4}
            )
        except Exception as e:
            elapsed = time.time() - start
            with self._lock:
                if agent_name not in self._data["agent_reliability"]:
                    self._data["agent_reliability"][agent_name] = {
                        "successes": 0, "failures": 0, "avg_time": 0.0
                    }
                self._data["agent_reliability"][agent_name]["failures"] += 1

            return AgentResult(
                agent_name=agent_name, output="", error=str(e),
                execution_time=elapsed
            )

    # ── Execution Engines ──────────────────────────────────────────────

    def run_parallel(self, agents: List[str], task: str, context: str = "",
                     shared_state: Optional[Dict] = None) -> Dict[str, AgentResult]:
        """Run multiple agents simultaneously."""
        results: Dict[str, AgentResult] = {}
        futures = {}

        for agent_name in agents:
            future = self._executor.submit(
                self._run_single_agent, agent_name, task, context, shared_state
            )
            futures[future] = agent_name

        for future in as_completed(futures):
            agent_name = futures[future]
            try:
                results[agent_name] = future.result(timeout=AGENT_TIMEOUT_S)
            except Exception as e:
                results[agent_name] = AgentResult(
                    agent_name=agent_name, output="", error=str(e)
                )

        self._track_execution("parallel", agents, len(results))
        return results

    def run_debate(self, agents: List[str], topic: str, rounds: int = 3,
                   context: str = "") -> Dict[str, Any]:
        """Agents debate a topic, cross-pollinate ideas, then synthesize."""
        # Round 1: Initial positions
        positions = self.run_parallel(
            agents, f"Argue your expert position on: {topic}", context
        )

        # Subsequent rounds: Agents see each other's positions and refine
        for round_num in range(1, rounds):
            cross_prompt = (
                f"Round {round_num + 1} of {rounds}: Review these expert positions "
                f"and refine your analysis. Challenge weak points, incorporate "
                f"strong arguments you agree with.\n\n"
            )
            for agent_name, result in positions.items():
                if result.output and not result.error:
                    cross_prompt += (
                        f"\n--- {agent_name} ---\n"
                        f"{result.output[:MAX_AGENT_OUTPUT]}\n"
                    )
            positions = self.run_parallel(agents, cross_prompt, context)

        # Synthesize
        synthesis = self._synthesize_results(positions, topic)

        self._track_execution("debate", agents, len(positions))
        return {
            "positions": {name: r.output for name, r in positions.items() if r.output},
            "synthesis": synthesis,
            "rounds": rounds,
            "agents": agents,
        }

    def run_pipeline(self, pipeline: List[str], task: str,
                     context: str = "") -> Dict[str, Any]:
        """Chain agents: A's output → B's input → C's input."""
        results: Dict[str, AgentResult] = {}
        current_input = task

        for agent_name in pipeline:
            result = self._run_single_agent(agent_name, current_input, context)
            results[agent_name] = result
            if result.error:
                break  # Pipeline breaks on error
            current_input = result.output  # Feed output to next agent

        self._track_execution("pipeline", pipeline, len(results))
        return {
            "stages": {name: r.output for name, r in results.items()},
            "final_output": current_input,
            "pipeline": pipeline,
            "errors": {name: r.error for name, r in results.items() if r.error},
        }

    def run_voting(self, agents: List[str], question: str, options: List[str],
                   context: str = "") -> Dict[str, Any]:
        """Agents vote on options, majority wins."""
        vote_prompt = (
            f"Vote on the best option. Respond with ONLY the option name.\n\n"
            f"Question: {question}\n\nOptions:\n"
            + "\n".join(f"- {opt}" for opt in options)
        )

        votes = self.run_parallel(agents, vote_prompt, context)

        # Count votes
        vote_counts: Dict[str, int] = {opt: 0 for opt in options}
        agent_votes: Dict[str, str] = {}

        for agent_name, result in votes.items():
            if result.output and not result.error:
                for opt in options:
                    if opt.lower() in result.output.lower():
                        vote_counts[opt] += 1
                        agent_votes[agent_name] = opt
                        break

        winner = max(vote_counts, key=vote_counts.get) if vote_counts else None

        self._track_execution("voting", agents, len(votes))
        return {
            "winner": winner,
            "vote_counts": vote_counts,
            "agent_votes": agent_votes,
            "total_votes": sum(vote_counts.values()),
        }

    def run_specialist(self, agents: List[str], task: str,
                       context: str = "") -> Dict[str, Any]:
        """Route to the most relevant specialist agent."""
        # Have all agents assess their own relevance
        relevance_prompt = (
            f"On a scale of 0-10, how relevant is your expertise to this task? "
            f"Respond with ONLY a number.\n\nTask: {task}"
        )
        relevance = self.run_parallel(agents, relevance_prompt)

        # Score and rank
        scores: Dict[str, float] = {}
        for agent_name, result in relevance.items():
            try:
                digits = ''.join(c for c in (result.output or "") if c.isdigit() or c == '.')
                score = float(digits[:3])
                scores[agent_name] = min(score, 10.0)
            except (ValueError, AttributeError):
                scores[agent_name] = 0.0

        # Run top 3 specialists
        top_agents = sorted(scores, key=scores.get, reverse=True)[:3]
        results = self.run_parallel(top_agents, task, context)

        self._track_execution("specialist", agents, len(results))
        return {
            "specialists": top_agents,
            "relevance_scores": scores,
            "results": {name: r.output for name, r in results.items()},
            "primary": top_agents[0] if top_agents else None,
        }

    def run_swarm(self, agents: List[str], task: str, context: str = "",
                  max_rounds: int = SWARM_DEFAULT_ROUNDS) -> Dict[str, Any]:
        """Self-organizing agent swarm — agents propose next steps and delegate."""
        # Initial broad exploration
        exploration = self.run_parallel(
            agents,
            f"Explore this task from your unique expertise. Identify the key "
            f"challenges and your proposed approach.\n\nTask: {task}",
            context
        )

        # Collect all proposals
        all_proposals: List[str] = []
        for agent_name, result in exploration.items():
            if result.output and not result.error:
                all_proposals.append(f"[{agent_name}]: {result.output[:1500]}")

        # Iterative refinement
        current_state = "\n\n".join(all_proposals)
        rounds_done = 0

        for round_num in range(max_rounds):
            rounds_done = round_num + 1
            refinement_prompt = (
                f"Round {round_num + 1}: Review the collective analysis below. "
                f"Identify remaining gaps, contradictions, or areas needing deeper "
                f"analysis. If the analysis is complete, say 'ANALYSIS COMPLETE'."
                f"\n\n{current_state}"
            )
            refinements = self.run_parallel(
                agents[:SWARM_MAX_AGENTS], refinement_prompt
            )

            new_insights: List[str] = []
            complete = True
            for agent_name, result in refinements.items():
                if result.output and not result.error:
                    if "complete" not in result.output.lower():
                        complete = False
                    new_insights.append(
                        f"[{agent_name}]: {result.output[:1500]}"
                    )

            if complete:
                break
            current_state += (
                "\n\n--- REFINEMENT ---\n\n" + "\n\n".join(new_insights)
            )

        # Final synthesis
        synthesis = self._synthesize_results(
            {name: AgentResult(agent_name=name, output=content)
             for name, content in zip(["swarm_output"], [current_state])},
            task
        )

        self._track_execution("swarm", agents, rounds_done)
        return {
            "final_analysis": current_state,
            "synthesis": synthesis,
            "rounds_completed": rounds_done,
        }

    # ── Synthesis ──────────────────────────────────────────────────────

    def _synthesize_results(self, results: Dict[str, AgentResult],
                            task: str) -> str:
        """Synthesize multiple agent results into a coherent summary."""
        combined = f"Task: {task}\n\nExpert analyses:\n"
        for agent_name, result in results.items():
            if result.output and not result.error:
                combined += (
                    f"\n--- {agent_name} ---\n"
                    f"{result.output[:MAX_AGENT_OUTPUT]}\n"
                )

        combined += (
            "\n\nSynthesize these expert analyses into a single, coherent, "
            "actionable recommendation. Resolve contradictions, highlight "
            "consensus, and provide a clear path forward."
        )

        try:
            synthesis_result = self._run_single_agent("software_architect", combined)
            return synthesis_result.output if synthesis_result.output else "Synthesis failed."
        except Exception:
            return "Synthesis unavailable."

    # ── Team Management ────────────────────────────────────────────────

    def execute_team(self, team_name: str, task: str, context: str = "",
                     **kwargs) -> Dict[str, Any]:
        """Execute a pre-defined team on a task."""
        if team_name == "all":
            team = TeamConfig(
                name="All Agents", agents=self.ALL_AGENTS,
                mode=ExecutionMode.PARALLEL
            )
        elif team_name in self.AGENT_TEAMS:
            team = self.AGENT_TEAMS[team_name]
        else:
            return {"error": f"Unknown team: {team_name}"}

        if team.mode == ExecutionMode.PARALLEL:
            return {
                "mode": "parallel",
                "results": self.run_parallel(team.agents, task, context, **kwargs)
            }
        elif team.mode == ExecutionMode.DEBATE:
            return {
                "mode": "debate",
                "results": self.run_debate(team.agents, task, team.rounds, context)
            }
        elif team.mode == ExecutionMode.PIPELINE:
            return {
                "mode": "pipeline",
                "results": self.run_pipeline(team.agents, task, context)
            }
        elif team.mode == ExecutionMode.VOTING:
            options = kwargs.get("options", [])
            return {
                "mode": "voting",
                "results": self.run_voting(team.agents, task, options, context)
            }
        elif team.mode == ExecutionMode.SPECIALIST:
            return {
                "mode": "specialist",
                "results": self.run_specialist(team.agents, task, context)
            }
        elif team.mode == ExecutionMode.SWARM:
            return {
                "mode": "swarm",
                "results": self.run_swarm(team.agents, task, context)
            }
        else:
            return {"error": f"Unknown execution mode: {team.mode}"}

    def execute_custom(self, agents: List[str], task: str,
                       mode: str = "parallel", context: str = "",
                       **kwargs) -> Dict[str, Any]:
        """Execute custom agent selection with specified mode."""
        try:
            exec_mode = ExecutionMode(mode)
        except ValueError:
            return {"error": f"Invalid execution mode: {mode}. "
                    f"Valid: {[m.value for m in ExecutionMode]}"}

        if exec_mode == ExecutionMode.PARALLEL:
            return self.run_parallel(agents, task, context)
        elif exec_mode == ExecutionMode.DEBATE:
            return self.run_debate(agents, task, kwargs.get("rounds", 3), context)
        elif exec_mode == ExecutionMode.PIPELINE:
            return self.run_pipeline(agents, task, context)
        elif exec_mode == ExecutionMode.VOTING:
            return self.run_voting(agents, task, kwargs.get("options", []), context)
        elif exec_mode == ExecutionMode.SPECIALIST:
            return self.run_specialist(agents, task, context)
        elif exec_mode == ExecutionMode.SWARM:
            return self.run_swarm(agents, task, context)
        return {"error": f"Unsupported custom mode: {mode}"}

    def list_teams(self) -> Dict[str, Any]:
        """List all available teams and their configurations."""
        teams = {}
        for name, config in self.AGENT_TEAMS.items():
            teams[name] = {
                "name": config.name,
                "agents": config.agents,
                "mode": config.mode.value,
                "agent_count": len(config.agents),
            }
        teams["all"] = {
            "name": "All Agents",
            "agents": self.ALL_AGENTS,
            "mode": "parallel",
            "agent_count": len(self.ALL_AGENTS)
        }
        return teams

    def get_agent_reliability(self) -> Dict[str, Any]:
        """Get reliability metrics for all agents."""
        return self._data.get("agent_reliability", {})

    # ── Metrics ────────────────────────────────────────────────────────

    def _track_execution(self, mode: str, agents: List[str],
                         results_count: int):
        """Track execution metrics."""
        with self._lock:
            self._data["meta"]["total_executions"] += 1
            self._data["meta"]["total_agents_spawned"] += len(agents)
        self._save()

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """Format orchestrator state for system prompt injection."""
        teams = self.list_teams()
        lines = ["## Multi-Agent Orchestration Available"]
        lines.append(f"- {len(self.ALL_AGENTS)} specialist agents ready")
        lines.append(f"- {len(self.AGENT_TEAMS)} pre-built teams")
        lines.append(
            "- Execution modes: parallel, debate, pipeline, voting, "
            "specialist, swarm"
        )
        for name, info in teams.items():
            if name != "all":
                lines.append(
                    f"- Team '{name}': {info['agent_count']} agents "
                    f"({info['mode']})"
                )
        return "\n".join(lines)[:max_chars]

    def get_stats(self) -> dict:
        """Get orchestrator statistics."""
        with self._lock:
            return {
                "total_executions": self._data["meta"].get("total_executions", 0),
                "total_agents_spawned": self._data["meta"].get(
                    "total_agents_spawned", 0
                ),
                "cached_agents": len(self._agent_cache),
                "available_teams": len(self.AGENT_TEAMS) + 1,  # +1 for "all"
                "available_agents": len(self.ALL_AGENTS),
                "agent_reliability": len(self._data.get("agent_reliability", {})),
            }


# ── Singleton ─────────────────────────────────────────────────────────────

_orchestrator_instance = None
_orchestrator_lock = threading.Lock()


def get_multi_agent_orchestrator() -> MultiAgentOrchestrator:
    """Get singleton MultiAgentOrchestrator instance."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        with _orchestrator_lock:
            if _orchestrator_instance is None:
                _orchestrator_instance = MultiAgentOrchestrator()
    return _orchestrator_instance
