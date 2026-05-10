# -*- coding: utf-8 -*-
"""
agency_agent.py — FRIDAY Agency Agent Tool
Invokes specialized expert agent personas from agency-agents collection.
Loads agent markdown as system prompt, executes task via Gemini.
"""
import json
import os
import sys
from pathlib import Path


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()
AGENTS_DIR = BASE_DIR / "agents"
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

_client_instance = None


def _get_api_key() -> str:
    try:
        data = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        key = data.get("gemini_api_key", "")
        if key:
            return key
    except Exception:
        pass
    raise RuntimeError("gemini_api_key not found in config/api_keys.json")


def _get_client():
    global _client_instance
    if _client_instance is None:
        from google import genai
        _client_instance = genai.Client(api_key=_get_api_key())
    return _client_instance


# ── Agent file map ────────────────────────────────────────────────────

AGENT_MAP = {
    # Engineering
    "ai_engineer":                    "engineering/ai_engineer.md",
    "backend_architect":              "engineering/backend_architect.md",
    "code_reviewer":                  "engineering/code_reviewer.md",
    "codebase_onboarding_engineer":   "engineering/codebase_onboarding_engineer.md",
    "data_engineer":                  "engineering/data_engineer.md",
    "database_optimizer":             "engineering/database_optimizer.md",
    "devops_automator":               "engineering/devops_automator.md",
    "frontend_developer":             "engineering/frontend_developer.md",
    "git_workflow_master":            "engineering/git_workflow_master.md",
    "incident_response_commander":    "engineering/incident_response_commander.md",
    "mobile_app_builder":             "engineering/mobile_app_builder.md",
    "rapid_prototyper":               "engineering/rapid_prototyper.md",
    "security_engineer":              "engineering/security_engineer.md",
    "senior_developer":               "engineering/senior_developer.md",
    "software_architect":             "engineering/software_architect.md",
    "sre":                            "engineering/sre.md",
    "technical_writer":               "engineering/technical_writer.md",
    "threat_detection_engineer":      "engineering/threat_detection_engineer.md",
    "voice_ai_integration_engineer":  "engineering/voice_ai_integration_engineer.md",
    # Testing
    "accessibility_auditor":          "testing/accessibility_auditor.md",
    "api_tester":                     "testing/api_tester.md",
    "performance_benchmarker":        "testing/performance_benchmarker.md",
    "test_results_analyzer":          "testing/test_results_analyzer.md",
    "workflow_optimizer":             "testing/workflow_optimizer.md",
    # Specialized
    "compliance_auditor":             "specialized/compliance_auditor.md",
    "document_generator":             "specialized/document_generator.md",
    "language_translator":            "specialized/language_translator.md",
    "workflow_architect":             "specialized/workflow_architect.md",
    # Design
    "ui_designer":                    "design/ui_designer.md",
    "ux_architect":                   "design/ux_architect.md",
}

# ── Voice-friendly aliases ────────────────────────────────────────────

AGENT_ALIASES = {
    # Engineering
    "web developer":        "frontend_developer",
    "senior web developer": "senior_developer",
    "frontend":             "frontend_developer",
    "frontend dev":         "frontend_developer",
    "backend":              "backend_architect",
    "backend dev":          "backend_architect",
    "android":              "mobile_app_builder",
    "android app":          "mobile_app_builder",
    "android app maker":    "mobile_app_builder",
    "android developer":    "mobile_app_builder",
    "ios":                  "mobile_app_builder",
    "ios developer":        "mobile_app_builder",
    "mobile":               "mobile_app_builder",
    "mobile app":           "mobile_app_builder",
    "mobile developer":     "mobile_app_builder",
    "software engineer":    "senior_developer",
    "software dev":         "senior_developer",
    "software architect":   "software_architect",
    "architect":            "software_architect",
    "architecture":         "software_architect",
    "devops":               "devops_automator",
    "devops operator":      "devops_automator",
    "senior devops":        "devops_automator",
    "senior devops operator": "devops_automator",
    "sre":                  "sre",
    "site reliability":     "sre",
    "code review":          "code_reviewer",
    "reviewer":             "code_reviewer",
    "review my code":       "code_reviewer",
    "code reviewer":        "code_reviewer",
    "security":             "security_engineer",
    "security engineer":    "security_engineer",
    "security check":       "security_engineer",
    "security audit":       "security_engineer",
    "threat":               "threat_detection_engineer",
    "threat hunt":          "threat_detection_engineer",
    "threat detection":     "threat_detection_engineer",
    "prototype":            "rapid_prototyper",
    "prototyper":           "rapid_prototyper",
    "rapid prototype":      "rapid_prototyper",
    "database":             "database_optimizer",
    "db optimize":          "database_optimizer",
    "sql optimize":         "database_optimizer",
    "database optimizer":   "database_optimizer",
    "git":                  "git_workflow_master",
    "git workflow":         "git_workflow_master",
    "incident":             "incident_response_commander",
    "incident response":    "incident_response_commander",
    "oncall":               "incident_response_commander",
    "data pipeline":        "data_engineer",
    "data engineer":        "data_engineer",
    "ai engineer":          "ai_engineer",
    "ml engineer":          "ai_engineer",
    "machine learning":     "ai_engineer",
    "voice engineer":       "voice_ai_integration_engineer",
    "voice ai":             "voice_ai_integration_engineer",
    "tech writer":          "technical_writer",
    "technical writer":     "technical_writer",
    "documentation":        "technical_writer",
    "onboarding":           "codebase_onboarding_engineer",
    "explore codebase":     "codebase_onboarding_engineer",
    "codebase":             "codebase_onboarding_engineer",
    # Testing
    "api test":             "api_tester",
    "test api":             "api_tester",
    "api tester":           "api_tester",
    "benchmark":            "performance_benchmarker",
    "performance":          "performance_benchmarker",
    "performance test":     "performance_benchmarker",
    "accessibility":        "accessibility_auditor",
    "a11y":                 "accessibility_auditor",
    "accessibility audit":  "accessibility_auditor",
    "test results":         "test_results_analyzer",
    "analyze tests":        "test_results_analyzer",
    "workflow":             "workflow_optimizer",
    "workflow optimize":    "workflow_optimizer",
    # Specialized
    "compliance":           "compliance_auditor",
    "compliance check":     "compliance_auditor",
    "translate":            "language_translator",
    "translator":           "language_translator",
    "generate document":    "document_generator",
    "document":             "document_generator",
    # Design
    "ui":                   "ui_designer",
    "ui design":            "ui_designer",
    "ui designer":          "ui_designer",
    "ux":                   "ux_architect",
    "ux design":            "ux_architect",
    "ux architect":         "ux_architect",
}


def _resolve_agent(name: str) -> str:
    """Resolve an agent name or alias to a canonical name."""
    normalized = name.strip().lower().replace("-", "_").replace(" ", "_")
    # Direct match
    if normalized in AGENT_MAP:
        return normalized
    # Alias match (lowercased)
    lower_name = name.strip().lower()
    if lower_name in AGENT_ALIASES:
        return AGENT_ALIASES[lower_name]
    # Fuzzy: check if any alias is contained in the input
    for alias, canonical in AGENT_ALIASES.items():
        if alias in lower_name or lower_name in alias:
            return canonical
    return normalized  # return as-is, will fail lookup later


def _load_agent_prompt(agent_name: str) -> str:
    """Load agent markdown file as system prompt."""
    canonical = _resolve_agent(agent_name)
    if canonical not in AGENT_MAP:
        available = ", ".join(sorted(AGENT_MAP.keys()))
        raise ValueError(
            f"Unknown agent '{agent_name}'. "
            f"Available: {available}"
        )
    file_path = AGENTS_DIR / AGENT_MAP[canonical]
    if not file_path.exists():
        raise FileNotFoundError(
            f"Agent file not found: {file_path}. "
            f"Run scripts/download_agents.py first."
        )
    return file_path.read_text(encoding="utf-8")


# ── Tool entry point ──────────────────────────────────────────────────

def agency_agent(parameters: dict, player=None, **kwargs) -> str:
    """
    Invoke a specialized expert agent persona.

    Parameters:
        agent_name: str — agent name or alias (e.g. "code_reviewer", "security")
        task: str — the task or question for the agent
        context: str — optional code/text/data to analyze
    """
    agent_name = parameters.get("agent_name", "")
    task = parameters.get("task", "")
    context = parameters.get("context", "")

    if not agent_name:
        return "Error: agent_name is required. Specify which expert agent to invoke."
    if not task:
        return "Error: task is required. Tell the agent what you need."

    try:
        agent_prompt = _load_agent_prompt(agent_name)
    except (ValueError, FileNotFoundError) as e:
        return str(e)

    # Build the full prompt
    full_prompt = (
        f"You are now operating as the agent defined in the system prompt. "
        f"Follow all rules, workflows, and deliverable formats defined there.\n\n"
        f"## Task\n{task}"
    )
    if context:
        full_prompt += f"\n\n## Context / Input\n{context}"

    try:
        from google.genai import types
        from actions.resilience import api_retry

        client = _get_client()
        agent_prompt_loaded = agent_prompt  # capture for closure

        def _call():
            config = types.GenerateContentConfig(
                system_instruction=agent_prompt_loaded,
                max_output_tokens=8192,
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_prompt,
                config=config,
            )
            result = response.text.strip()
            if not result:
                raise ValueError("Agent returned an empty response.")
            return result

        return api_retry(
            _call,
            max_retries=3,
            base_delay=2.0,
            max_delay=60.0,
            on_retry=lambda attempt, delay, err: print(
                f"[AgencyAgent] API retry {attempt}/3, waiting {delay:.1f}s: {err}"
            ),
        )
    except Exception as e:
        return f"Agent execution failed: {e}"


def list_agents(parameters: dict = None, player=None, **kwargs) -> str:
    """List all available agents with their aliases."""
    lines = ["Available Agency Agents:\n"]
    by_category = {}
    for name, path in sorted(AGENT_MAP.items()):
        category = path.split("/")[0]
        by_category.setdefault(category, []).append(name)

    for category in ["engineering", "testing", "specialized", "design"]:
        agents = by_category.get(category, [])
        if agents:
            lines.append(f"\n## {category.title()}")
            for agent in agents:
                aliases = [a for a, c in AGENT_ALIASES.items() if c == agent]
                alias_str = f" (aliases: {', '.join(aliases[:3])})" if aliases else ""
                lines.append(f"  - {agent}{alias_str}")

    return "\n".join(lines)
