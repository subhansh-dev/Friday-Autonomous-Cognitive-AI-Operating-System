# -*- coding: utf-8 -*-
"""
error_handler.py — FRIDAY Autonomous Error Recovery
Analyzes task failures and decides retry/skip/replan/abort.
Generates alternative steps when replanning.
"""
import json
import re
import sys
from pathlib import Path
from enum import Enum


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


class ErrorDecision(Enum):
    RETRY  = "retry"
    SKIP   = "skip"
    REPLAN = "replan"
    ABORT  = "abort"


ERROR_ANALYST_PROMPT = """You are the error recovery module of FRIDAY AI assistant.

A task step has failed. Analyze the error and decide what to do.

DECISIONS:
- retry   : Transient error (network timeout, temporary file lock, race condition).
             The same step can succeed if tried again.
- skip    : This step is not critical and the task can succeed without it.
- replan  : The approach was wrong. A different tool or method should be tried.
- abort   : The task is fundamentally impossible or unsafe to continue.

DECISION GUIDELINES:
- "WSL not found" / "not installed" → abort (can't fix missing dependencies)
- "Timed out" → retry once, then replan with shorter timeout or different approach
- "Permission denied" / "access denied" → abort (security boundary)
- "Rate limited" → retry with delay
- "Not found" (file/URL) → replan (wrong path or URL)
- Network errors → retry (transient)
- JSON parse errors → replan (tool returned unexpected format)
- "exit code" non-zero → analyze: if tool-specific, replan; if transient, retry

Also provide:
- A brief explanation of WHY it failed (1 sentence)
- A fix suggestion if decision is replan (what to try instead)
- Max retries: how many times to retry if decision is retry (1 or 2)

Return ONLY valid JSON:
{
  "decision": "retry|skip|replan|abort",
  "reason": "why it failed",
  "fix_suggestion": "what to try instead (for replan)",
  "max_retries": 1,
  "user_message": "Short message to tell the user (max 15 words)"
}
"""


def _get_api_key() -> str:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            key = data.get("gemini_api_key", "")
            if not key:
                raise ValueError("gemini_api_key is empty or missing in api_keys.json")
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
            model=model_name,
            contents=prompt,
            config=config,
        )
    else:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
    return response.text


def analyze_error(
    step: dict,
    error: str,
    attempt: int = 1,
    max_attempts: int = 2
) -> dict:
    if attempt >= max_attempts:
        print(f"[ErrorHandler] ⚠️ Max attempts reached for step "
              f"{step.get('step')} — forcing replan")
        return {
            "decision":       ErrorDecision.REPLAN,
            "reason":         f"Failed {attempt} times: {error[:100]}",
            "fix_suggestion": "Try a completely different approach or tool",
            "max_retries":    0,
            "user_message":   "Trying a different approach, sir."
        }

    prompt = f"""Failed step:
Tool: {step.get('tool')}
Description: {step.get('description')}
Parameters: {json.dumps(step.get('parameters', {}), indent=2)}
Critical: {step.get('critical', False)}

Error:
{error[:500]}

Attempt number: {attempt}"""

    try:
        text = _generate("gemini-2.5-flash-lite", prompt,
                         system=ERROR_ANALYST_PROMPT)
        text = text.strip()
        text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()

        result = json.loads(text)

        # Validate required fields
        if "decision" not in result:
            result["decision"] = "replan"
        if "reason" not in result:
            result["reason"] = "Unknown error"
        if "fix_suggestion" not in result:
            result["fix_suggestion"] = "Try alternative approach"
        if "max_retries" not in result:
            result["max_retries"] = 1
        if "user_message" not in result:
            result["user_message"] = "Adjusting approach, sir."

        decision_str = result.get("decision", "replan").lower()
        decision_map = {
            "retry":  ErrorDecision.RETRY,
            "skip":   ErrorDecision.SKIP,
            "replan": ErrorDecision.REPLAN,
            "abort":  ErrorDecision.ABORT,
        }
        result["decision"] = decision_map.get(decision_str, ErrorDecision.REPLAN)

        # Critical steps can't be skipped
        if step.get("critical") and result["decision"] == ErrorDecision.SKIP:
            result["decision"]     = ErrorDecision.REPLAN
            result["user_message"] = ("This step is critical — finding "
                                      "alternative approach, sir.")

        # Clamp max_retries to sane range
        result["max_retries"] = max(0, min(int(result.get("max_retries", 1)), 3))

        print(f"[ErrorHandler] Decision: {result['decision'].value} — "
              f"{result.get('reason', '')}")
        return result

    except json.JSONDecodeError as e:
        print(f"[ErrorHandler] ⚠️ Invalid JSON from model: {e}")
        return {
            "decision":       ErrorDecision.REPLAN,
            "reason":         f"Model returned invalid JSON: {e}",
            "fix_suggestion": "Try alternative approach",
            "max_retries":    1,
            "user_message":   "Encountered an issue, adjusting approach, sir."
        }
    except Exception as e:
        print(f"[ErrorHandler] ⚠️ Analysis failed: {e} — defaulting to replan")
        return {
            "decision":       ErrorDecision.REPLAN,
            "reason":         str(e),
            "fix_suggestion": "Try alternative approach",
            "max_retries":    1,
            "user_message":   "Encountered an issue, adjusting approach, sir."
        }


def generate_fix(step: dict, error: str, fix_suggestion: str) -> dict:
    prompt = f"""A task step failed. Generate a replacement step.

Original step:
Tool: {step.get('tool')}
Description: {step.get('description')}
Parameters: {json.dumps(step.get('parameters', {}), indent=2)}

Error: {error[:300]}
Fix suggestion: {fix_suggestion}

Write a Python script that accomplishes the same goal differently.
Return ONLY the Python code, no explanation.
Keep it under 100 lines. Do NOT use dangerous operations
(os.system, subprocess with shell=True, eval, exec on user input)."""

    try:
        code = _generate("gemini-2.5-flash", prompt)
        code = code.strip()
        code = re.sub(r"```(?:python)?\s*", "", code).strip().rstrip("`").strip()

        # Basic safety check
        dangerous = ["os.system(", "subprocess.Popen(", "eval(", "exec(",
                     "__import__(", "compile("]
        for pattern in dangerous:
            if pattern in code:
                print(f"[ErrorHandler] ⚠️ Generated code contains "
                      f"dangerous call: {pattern} — stripping")
                code = f"# BLOCKED: contained {pattern}\nprint('Fix blocked for safety')"

        # Length limit
        if len(code) > 5000:
            code = code[:5000] + "\n# Truncated — code too long"

        return {
            "step":        step.get("step"),
            "tool":        "code_helper",
            "description": f"Auto-fix for: {step.get('description')}",
            "parameters": {
                "action":      "run",
                "description": fix_suggestion,
                "code":        code,
                "language":    "python",
                "timeout":     30,
            },
            "depends_on": step.get("depends_on", []),
            "critical":   step.get("critical", False)
        }

    except Exception as e:
        print(f"[ErrorHandler] ⚠️ Fix generation failed: {e}")
        return {
            "step":        step.get("step"),
            "tool":        "code_helper",
            "description": f"Fallback for: {step.get('description')}",
            "parameters": {
                "action":      "auto",
                "description": step.get("description", ""),
            },
            "depends_on":  step.get("depends_on", []),
            "critical":    step.get("critical", False)
        }
