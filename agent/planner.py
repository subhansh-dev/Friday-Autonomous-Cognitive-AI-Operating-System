# -*- coding: utf-8 -*-
"""
planner.py — FRIDAY Autonomous Task Planner
Breaks user goals into step-by-step plans using Gemini.
Handles initial planning, replanning after failures, and fallback strategies.
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# Shared API key cache
_api_key_cache: Optional[str] = None


PLANNER_PROMPT = """You are the planning module of FRIDAY, a personal AI assistant.
Your job: break any user goal into a sequence of steps using ONLY the tools listed below.

ABSOLUTE RULES:
- NEVER use generated_code or write Python scripts. It does not exist.
- NEVER reference previous step results in parameters. Every step is independent.
- Use web_search for ANY information retrieval, research, or current data.
- Use file_controller to save content to disk.
- Max 7 steps. Use the minimum steps needed.
- For dates: use YYYY-MM-DD format. For "today" use the actual current date provided.
- For times: use HH:MM 24h format. For "in 30 minutes" calculate from current time.
- Always fill in ALL required parameters. Never leave them as placeholders.

AVAILABLE TOOLS AND THEIR PARAMETERS:

open_app
  app_name: string (required)

web_search
  query: string (required) — write a clear, focused search query
  mode: "search" or "compare" (optional, default: search)
  items: list of strings (optional, for compare mode)
  aspect: string (optional, for compare mode)

game_updater
  action: "update" | "install" | "list" | "download_status" | "schedule" (required)
  platform: "steam" | "epic" | "both" (optional, default: both)
  game_name: string (optional)
  app_id: string (optional)
  shutdown_when_done: boolean (optional)

browser_control
  action: "go_to" | "search" | "click" | "type" | "scroll" | "get_text" | "press" | "close" (required)
  url: string (for go_to)
  query: string (for search)
  text: string (for click/type)
  direction: "up" | "down" (for scroll)

file_controller
  action: "write" | "create_file" | "read" | "list" | "delete" | "move" | "copy" | "find" | "disk_usage" (required)
  path: string — use "desktop" for Desktop folder
  name: string — filename
  content: string — file content (for write/create_file)

computer_settings
  action: string (required)
  description: string — natural language description
  value: string (optional)

computer_control
  action: "type" | "click" | "hotkey" | "press" | "scroll" | "screenshot" | "screen_find" | "screen_click" (required)
  text: string (for type)
  x, y: int (for click)
  keys: string (for hotkey, e.g. "ctrl+c")
  key: string (for press)
  direction: "up" | "down" (for scroll)
  description: string (for screen_find/screen_click)

screen_process
  text: string (required) — what to analyze or ask about the screen
  angle: "screen" | "camera" (optional)

send_message
  receiver: string (required)
  message_text: string (required)
  platform: string (required)

reminder
  date: string YYYY-MM-DD (required)
  time: string HH:MM (required)
  message: string (required)

desktop_control
  action: "wallpaper" | "organize" | "clean" | "list" | "task" (required)
  path: string (optional)
  task: string (optional)

youtube_video
  action: "play" | "summarize" | "trending" (required)
  query: string (for play)

weather_report
  city: string (required)

flight_finder
  origin: string (required)
  destination: string (required)
  date: string (required)

code_helper
  action: "write" | "edit" | "run" | "explain" (required)
  description: string (required)
  language: string (optional)
  output_path: string (optional)
  file_path: string (optional)

dev_agent
  description: string (required)
  language: string (optional)

web_research
  query: string (required)
  depth: 1 or 2 (optional, default: 1)
  max_results: 1-10 (optional, default: 5)

security_tools
  action: string (required — health, port_scan, nmap_scan, etc.)
  target: string (optional — URL, IP, or domain)

ai_pipeline
  operation: "summarize" | "translate" | "sentiment" | "entities" (required)
  text: string (required)
  language: string (optional, for translate)

agency_agent
  agent_name: string (required — code_reviewer, security_engineer, software_architect, frontend_developer, mobile_app_builder, devops_automator, senior_developer, database_optimizer, api_tester, performance_benchmarker, ui_designer, technical_writer, sre, threat_detection_engineer, rapid_prototyper, data_engineer, ai_engineer, etc. Aliases: "web developer", "android", "devops", "security", "benchmark")
  task: string (required — what the agent should do)
  context: string (optional — code or text to analyze)
  action: "run" (default) | "list"

EXAMPLES:

Goal: "research mechanical engineering and save it to a notepad file"
Steps:
1. web_search | query: "mechanical engineering overview definition history"
2. web_search | query: "mechanical engineering applications and future trends"
3. file_controller | action: write, path: desktop, name: mechanical_engineering.txt, content: "Use results from steps 1 and 2 to write a comprehensive summary."

Goal: "What is the price of Bitcoin"
Steps:
1. web_search | query: "Bitcoin price today USD"

Goal: "List the files on the desktop and find the largest 5 files"
Steps:
1. file_controller | action: list, path: desktop
2. file_controller | action: largest, path: desktop, count: 5

Goal: "Install PUBG from Steam"
Steps:
1. game_updater | action: install, platform: steam, game_name: "PUBG"

Goal: "Update all my Steam games"
Steps:
1. game_updater | action: update, platform: steam

Goal: "Send John a message on WhatsApp saying there is a meeting tomorrow"
Steps:
1. send_message | receiver: John, message_text: "There is a meeting tomorrow", platform: WhatsApp

Goal: "Open the clock and set a reminder for 30 minutes later"
Steps:
1. reminder | date: {today}, time: {now_plus_30min}, message: "Reminder"

OUTPUT — return ONLY valid JSON, no markdown, no explanation, no code blocks:
{
  "goal": "...",
  "steps": [
    {
      "step": 1,
      "tool": "tool_name",
      "description": "what this step does",
      "parameters": {},
      "critical": true
    }
  ]
}
"""


def _get_api_key() -> str:
    global _api_key_cache
    if _api_key_cache:
        return _api_key_cache
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            key = data.get("gemini_api_key", "")
            if not key:
                raise ValueError("gemini_api_key is empty or missing")
            _api_key_cache = key
            return key
    except FileNotFoundError:
        raise FileNotFoundError(f"API config not found at {API_CONFIG_PATH}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in api_keys.json: {e}")


def _generate(model_name: str, prompt: str, system: str = "") -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_get_api_key())

    if system:
        config = types.GenerateContentConfig(system_instruction=system)
        response = client.models.generate_content(
            model=model_name, contents=prompt, config=config)
    else:
        response = client.models.generate_content(
            model=model_name, contents=prompt)
    return response.text


# ── Validation helpers ────────────────────────────────────────────────

VALID_TOOLS = {
    "open_app", "web_search", "game_updater", "browser_control",
    "file_controller", "computer_settings", "computer_control",
    "screen_process", "send_message", "reminder", "desktop_control",
    "youtube_video", "weather_report", "flight_finder", "code_helper",
    "dev_agent", "web_research", "security_tools", "ai_pipeline",
    "agency_agent",
}

REQUIRED_PARAMS = {
    "open_app":          ["app_name"],
    "web_search":        ["query"],
    "weather_report":    ["city"],
    "send_message":      ["receiver", "message_text", "platform"],
    "reminder":          ["date", "time", "message"],
    "flight_finder":     ["origin", "destination", "date"],
    "screen_process":    ["text"],
    "code_helper":       ["action"],
    "dev_agent":         ["description"],
    "computer_control":  ["action"],
    "file_controller":   ["action"],
    "desktop_control":   ["action"],
    "youtube_video":     ["action"],
    "game_updater":      [],  # has defaults
    "browser_control":   ["action"],
    "computer_settings": [],
    "web_research":      ["query"],
    "security_tools":    ["action"],
    "ai_pipeline":       ["operation"],
    "agency_agent":      ["agent_name"],
}


def _validate_plan(plan: dict) -> dict:
    """Validate and sanitize a plan from the model."""
    if "steps" not in plan or not isinstance(plan["steps"], list):
        raise ValueError("Invalid plan structure: missing 'steps'")

    if "goal" not in plan:
        plan["goal"] = ""

    valid_steps = []
    for step in plan["steps"]:
        tool = step.get("tool", "")

        # Replace banned tools
        if tool in ("generated_code", "code_runner"):
            print(f"[Planner] ⚠️ Replacing banned tool '{tool}' "
                  f"in step {step.get('step')}")
            step["tool"] = "web_search"
            step["parameters"] = {"query": step.get("description", "")[:200]}

        # Reject unknown tools
        if step["tool"] not in VALID_TOOLS:
            print(f"[Planner] ⚠️ Unknown tool '{step['tool']}' "
                  f"in step {step.get('step')} — replacing with web_search")
            step["tool"] = "web_search"
            step["parameters"] = {"query": step.get("description", "")[:200]}

        # Ensure step number exists
        if "step" not in step:
            step["step"] = len(valid_steps) + 1

        # Ensure description exists
        if "description" not in step:
            step["description"] = f"Execute {step['tool']}"

        # Ensure parameters exist
        if "parameters" not in step or not isinstance(step["parameters"], dict):
            step["parameters"] = {}

        # Ensure critical field exists
        if "critical" not in step:
            step["critical"] = True

        # Check required params
        required = REQUIRED_PARAMS.get(step["tool"], [])
        params = step["parameters"]
        missing = [p for p in required if not params.get(p)]
        if missing:
            print(f"[Planner] ⚠️ Step {step['step']} ({step['tool']}) "
                  f"missing required params: {missing}")
            # Don't remove — let executor handle the error

        valid_steps.append(step)

    plan["steps"] = valid_steps
    return plan


def _inject_time_context(user_input: str) -> str:
    """Add current date/time context so the model can fill date/time params."""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")
    day_name = now.strftime("%A")

    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    next_week = (now + timedelta(days=7)).strftime("%Y-%m-%d")

    time_ctx = (
        f"\n\nCURRENT CONTEXT (use these exact values, not placeholders):\n"
        f"  Today's date: {today} ({day_name})\n"
        f"  Current time: {current_time}\n"
        f"  Tomorrow: {tomorrow}\n"
        f"  Next week: {next_week}\n"
    )
    return user_input + time_ctx


# ── Plan creation ─────────────────────────────────────────────────────

def create_plan(goal: str, context: str = "") -> dict:
    user_input = _inject_time_context(f"Goal: {goal}")
    if context:
        user_input += f"\n\nContext: {context}"

    try:
        text = _generate("gemini-2.5-flash-lite", user_input,
                         system=PLANNER_PROMPT)
        text = text.strip()
        text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()

        plan = json.loads(text)
        plan = _validate_plan(plan)

        print(f"[Planner] ✅ Plan: {len(plan['steps'])} steps")
        for s in plan["steps"]:
            print(f"  Step {s['step']}: [{s['tool']}] {s['description']}")

        return plan

    except json.JSONDecodeError as e:
        print(f"[Planner] ⚠️ JSON parse failed: {e}")
        return _fallback_plan(goal)
    except Exception as e:
        print(f"[Planner] ⚠️ Planning failed: {e}")
        return _fallback_plan(goal)


def _fallback_plan(goal: str) -> dict:
    """Last-resort plan when the model fails to produce valid JSON."""
    print("[Planner] 🔄 Using fallback plan")
    return {
        "goal": goal,
        "steps": [
            {
                "step": 1,
                "tool": "web_search",
                "description": f"Search for: {goal}",
                "parameters": {"query": goal},
                "critical": True,
            }
        ],
    }


# ── Replanning after failure ─────────────────────────────────────────

def replan(
    goal: str,
    completed_steps: list,
    failed_step: dict,
    error: str,
) -> dict:
    completed_summary = "\n".join(
        f"  - Step {s.get('step', '?')} ({s.get('tool', '?')}): DONE"
        for s in completed_steps
    )

    prompt = (
        f"Goal: {goal}\n\n"
        f"Already completed:\n"
        f"{completed_summary if completed_summary else '  (none)'}\n\n"
        f"Failed step: [{failed_step.get('tool', '?')}] "
        f"{failed_step.get('description', '?')}\n"
        f"Error: {error[:300]}\n\n"
        f"Create a REVISED plan for the remaining work only. "
        f"Do not repeat completed steps. "
        f"Use a DIFFERENT approach or tool for the failed step."
    )

    prompt = _inject_time_context(prompt)

    try:
        text = _generate("gemini-2.5-flash", prompt, system=PLANNER_PROMPT)
        text = text.strip()
        text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()

        plan = json.loads(text)
        plan = _validate_plan(plan)

        print(f"[Planner] 🔄 Revised plan: {len(plan['steps'])} steps")
        for s in plan["steps"]:
            print(f"  Step {s['step']}: [{s['tool']}] {s['description']}")

        return plan

    except Exception as e:
        print(f"[Planner] ⚠️ Replan failed: {e}")
        return _fallback_plan(goal)
