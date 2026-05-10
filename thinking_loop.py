"""
thinking_loop.py — FRIDAY Multi-Pass Reasoning Module
======================================================
Inspired by OpenMythos / Recurrent-Depth Transformer architecture.

Instead of responding immediately to complex requests, FRIDAY runs the input
through multiple reasoning passes — each refining the understanding, breaking
down sub-tasks, and planning the execution before the main session acts.

Simple/casual requests skip this entirely to keep latency low.
Complex/multi-step requests get 2-3 reasoning passes before execution.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Optional


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# ── How many reasoning loops to run ──────────────────────────────────────────
MAX_LOOPS   = 3   # max passes for very complex tasks
MIN_LOOPS   = 1   # always at least 1 pass for complex tasks

# ── Complexity threshold — below this, skip thinking loop entirely ─────────
# Keywords that indicate a complex/multi-step request
COMPLEX_TRIGGERS = [
    "research", "find and", "search and", "compare", "analyze", "summarize",
    "create a", "build a", "write a", "make a", "generate", "plan",
    "organise", "organize", "and then", "after that", "first", "also",
    "multiple", "all of", "everything", "full", "complete", "detailed",
    "step by step", "how do i", "explain how", "set up", "configure",
    "install and", "download and", "open and", "find all", "list all",
    "send and", "save and", "check and", "update and", "fix and",
    # Security / cyber triggers
    "bug bounty", "pentest", "penetration", "vulnerability", "scan",
    "recon", "enumerate", "exploit", "subdomain", "port scan",
    "nmap", "sqlmap", "nuclei", "ffuf", "gobuster",
    # Expert agent triggers
    "code review", "security audit", "architecture", "prototype",
    "benchmark", "accessibility",
]

# Keywords that indicate simple/direct requests — skip thinking loop
SIMPLE_TRIGGERS = [
    "what time", "what's the time", "weather", "play ", "open ",
    "volume", "mute", "unmute", "pause", "stop", "yes", "no",
    "thanks", "thank you", "ok", "okay", "got it", "sure",
    "hello", "hi", "hey", "morning", "good night",
]


def _get_api_key_and_model() -> tuple:
    try:
        from brain.model_router import get_model_router
        router = get_model_router()
        provider = router.get_primary_provider()
        if provider.value == "openai":
            key = router.get_openai_key()
            model = "gpt-4o-mini"
        else:
            key = router.get_gemini_key()
            model = "gemini-2.5-flash-lite"
        return key, model
    except Exception:
        return "", "gemini-2.5-flash-lite"


def _generate(prompt: str, system: str = "") -> str:
    from google import genai
    from google.genai import types
    from actions.resilience import api_retry

    api_key, model = _get_api_key_and_model()

    def _call():
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            system_instruction=system if system else None,
            max_output_tokens=1024,
        )
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )
        return response.text.strip()

    return api_retry(
        _call,
        max_retries=3,
        base_delay=2.0,
        max_delay=60.0,
        on_retry=lambda attempt, delay, err: print(
            f"[ThinkLoop] API retry {attempt}/3, waiting {delay:.1f}s: {err}"
        ),
    )


def _is_complex(text: str) -> bool:
    """Decide if a request needs multi-pass reasoning or can be handled directly."""
    text_lower = text.lower().strip()

    # Check simple triggers first — if it's clearly simple, skip
    for trigger in SIMPLE_TRIGGERS:
        if text_lower.startswith(trigger) or trigger in text_lower:
            return False

    # Check complex triggers
    for trigger in COMPLEX_TRIGGERS:
        if trigger in text_lower:
            return True

    # Long requests are usually complex
    if len(text.split()) > 15:
        return True

    return False


def _count_loops(text: str) -> int:
    """Determine how many reasoning loops this request needs."""
    text_lower = text.lower()
    word_count = len(text.split())

    # Very complex — research + save + multi-tool
    multi_tool_signals = sum(1 for t in ["and then", "after that", "also", "then"] if t in text_lower)
    if multi_tool_signals >= 2 or word_count > 30:
        return MAX_LOOPS

    # Moderately complex
    if word_count > 18 or multi_tool_signals == 1:
        return 2

    return MIN_LOOPS


# ── System prompts for each reasoning pass ───────────────────────────────────

_PASS_1_SYSTEM = """You are FRIDAY's internal reasoning engine — Pass 1: UNDERSTANDING.
Your job: deeply understand what information or context is needed. Be concise. Output structured thinking, not a response to the user.
Format:
GOAL: [core objective]
IMPLICIT: [unstated requirements]
AMBIGUITIES: [anything unclear]
NEEDS: [what's needed to accomplish this]"""

_PASS_2_SYSTEM = """You are FRIDAY's internal reasoning engine — Pass 2: PLANNING.

- Identify which tools/actions each step needs
- Identify dependencies between steps
- Consider what has been learned from past tool usage (review LEARNINGS section)
- Avoid tools that have failed in similar contexts before
- Prefer tools with a proven track record for the task type
- For security/cyber tasks, use security_tools (not browser_control)
- For expert domain help, use agency_agent (code_reviewer, security_engineer, etc.)

Available tools: open_app, web_search, browser_control, file_controller,
computer_settings, computer_control, send_message, reminder, youtube_video,
weather_report, flight_finder, game_updater, dev_agent, code_helper,
screen_process, desktop_control, security_tools, agency_agent, web_research,
ai_pipeline, ac_control, data_analysis

Format:
STEPS:
1. [step] → [tool]
2. [step] → [tool]
RISKS: [potential issues]
ORDER: [critical dependencies]"""

_PASS_3_SYSTEM = """You are FRIDAY's internal reasoning engine — Pass 3: REFINEMENT.

You have the understanding and plan from previous passes. Now refine and finalize.

- Optimize the order for minimum latency
- Merge steps that can be done in parallel
- Ensure each step has a clear success/failure criterion
- Flag steps that might fail and suggest fallbacks
- Produce the final execution brief

BRIEF: [1-2 sentence summary of what to do]
EXECUTION_PLAN:
1. [exact action] → [tool] (success criteria)
2. [exact action] → [tool] (success criteria)
FALLBACKS: [what to do if key steps fail]
LESSONS_APPLIED: [how past learnings were used to improve this plan]"""

def _run_thinking_loop(
    user_input: str,
    n_loops: int,
    player=None,
) -> str:
    """
    Run n_loops reasoning passes over the user input.
    Returns a refined execution brief for the main session.
    """
    if player:
        player.set_state("THINKING")
        player.write_log(f"SYS: Activating thinking loop ({n_loops} passes)...")

    print(f"[ThinkingLoop] 🧠 Starting {n_loops}-pass reasoning for: {user_input[:60]}")

    thought = user_input
    pass_systems = [_PASS_1_SYSTEM, _PASS_2_SYSTEM, _PASS_3_SYSTEM]

    for i in range(n_loops):
        pass_num = i + 1
        system   = pass_systems[min(i, len(pass_systems) - 1)]

        print(f"[ThinkingLoop] 🔄 Pass {pass_num}/{n_loops}...")
        t0 = time.time()

        prompt = f"Original request: {user_input}\n\nPrevious reasoning:\n{thought}" \
                 if i > 0 else f"User request: {user_input}"

        try:
            thought = _generate(prompt, system=system)
            elapsed = time.time() - t0
            print(f"[ThinkingLoop] ✅ Pass {pass_num} done ({elapsed:.1f}s)")
        except Exception as e:
            print(f"[ThinkingLoop] ⚠️ Pass {pass_num} failed: {e} — using previous thought")
            break

    print(f"[ThinkingLoop] 🎯 Reasoning complete")
    return thought


def reflect_on_outcome(
    action: str,
    outcome: str,
    error: Optional[str] = None,
) -> dict:
    """
    Post-action reflection: analyze what happened and extract a lesson.
    Run this after a tool call that failed or had an unexpected outcome.

    Returns a dict with evaluation and lesson, or empty dict if nothing learned.
    """
    prompt = (
        f"Action performed: {action}\n"
        f"Outcome: {outcome}\n"
        f"Error: {error or 'None'}\n"
        f"What unexpected patterns, if any, can be learned from this?"
    )
    system = ("""Evaluate a completed action and extract a learning if applicable.
Format:
EVALUATION: success | partial | failure
PREDICTION_ERROR: what differed from expectation
LESSON: what to remember for next time (or "None")
ADJUSTMENT: what to change in approach (or "None")""")
    try:
        result = _generate(prompt, system=system)
        lesson = None
        for line in result.split("\n"):
            if line.startswith("LESSON:"):
                lesson = line[7:].strip()
        if lesson and lesson.lower() != "none":
            from brain.learning import get_learning_engine
            try:
                get_learning_engine().write_evolution_learning(
                    f"After '{action}': {lesson}",
                    domain="post_action_reflection",
                )
            except Exception:
                pass
            return {"lesson": lesson, "raw": result}
        return {}
    except Exception:
        return {}


def think(
    user_input:  str,
    player=None,
    force:       bool = False,
    max_loops:   Optional[int] = None,
) -> tuple[str, bool]:
    """
    Main entry point for the thinking loop.

    Args:
        user_input : The raw user request
        player     : FridayUI instance for state updates
        force      : Force thinking loop even for simple requests
        max_loops  : Override loop count

    Returns:
        enriched_prompt : The request with the reasoning brief appended
        did_think       : Whether the thinking loop actually ran
    """
    if not force and not _is_complex(user_input):
        print(f"[ThinkingLoop] ⚡ Simple request — skipping thinking loop")
        return user_input, False

    # ── Mythos Integration: Classify task and check for security pipeline ──
    try:
        from brain.model_router import get_model_router
        router = get_model_router()
        task_type, model_config = router.get_route(user_input)
        print(f"[ThinkingLoop] 🎯 Task classified as: {task_type.value} → {model_config.model_id}")

        # For security tasks, inject routing context into the brief
        if task_type.value == "security":
            security_context = (
                f"[MODEL ROUTING: {model_config.provider}/{model_config.model_id}]\n"
                f"[TASK TYPE: security — consider using mythos_scan for full 7-agent analysis]\n"
            )
        elif task_type.value == "code":
            security_context = f"[MODEL ROUTING: {model_config.provider}/{model_config.model_id}]\n"
        else:
            security_context = ""
    except Exception:
        security_context = ""

    n_loops = max_loops if max_loops is not None else _count_loops(user_input)
    brief   = _run_thinking_loop(user_input, n_loops, player=player)

    # Append the reasoning brief to the original input
    # This gives the main Gemini session full context without replacing the request
    enriched = (
        f"{user_input}\n\n"
        f"{security_context}"
        f"[INTERNAL REASONING BRIEF]\n"
        f"{brief}\n"
        f"[END BRIEF]\n"
        f"Execute the above based on the reasoning brief."
    )

    return enriched, True


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_inputs = [
        "Hey what's the weather in London",
        "Research the top 5 AI frameworks in 2025, compare them and save a detailed report to my desktop",
        "Open Spotify",
        "Find flights from Mumbai to Tokyo next Friday, and also check the weather there and send me a summary on Telegram",
    ]

    for inp in test_inputs:
        print(f"\n{'='*60}")
        print(f"INPUT: {inp}")
        print(f"COMPLEX: {_is_complex(inp)}")
        if _is_complex(inp):
            print(f"LOOPS: {_count_loops(inp)}")
        result, did_think = think(inp)
        print(f"DID THINK: {did_think}")
        if did_think:
            print(f"OUTPUT:\n{result}")