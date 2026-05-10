# -*- coding: utf-8 -*-
"""
executor.py — FRIDAY Autonomous Task Executor
Takes a plan from the planner, executes steps with error recovery,
context injection, and auto-generated code fallback.
"""
import json
import re
import sys
import threading
import subprocess
import tempfile
import os
import time
from pathlib import Path
from typing import Callable, Optional, Dict, Any, List

from agent.planner       import create_plan, replan
from agent.error_handler import analyze_error, generate_fix, ErrorDecision


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# Shared API key cache to avoid repeated file reads
_api_key_cache: Optional[str] = None


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


# ── Dangerous code patterns — blocked before execution ────────────────
_DANGEROUS_PATTERNS = [
    "os.system(",
    "subprocess.Popen(",
    "subprocess.call(",
    "subprocess.run(",
    "eval(",
    "exec(",
    "__import__(",
    "compile(",
    "ctypes.",
    "shutil.rmtree(",
    "os.remove(",
    "os.unlink(",
    "importlib.",
    "socket.socket(",
    "urllib.request.urlopen(",
]


def _check_code_safety(code: str) -> Optional[str]:
    """Return reason if code is dangerous, None if safe."""
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in code:
            return f"Contains blocked pattern: {pattern}"
    return None


def _run_generated_code(
    description: str,
    speak: Optional[Callable] = None,
    timeout: int = 120,
) -> str:
    if speak:
        speak("Writing custom code for this task, sir.")

    home      = Path.home()
    desktop   = home / "Desktop"
    downloads = home / "Downloads"
    documents = home / "Documents"

    # Resolve Windows desktop via registry if default path missing
    if not desktop.exists():
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
            desktop = Path(winreg.QueryValueEx(key, "Desktop")[0])
        except Exception:
            pass

    system_prompt = (
        "You are an expert Python developer working for FRIDAY AI assistant. "
        "Write clean, complete, working Python code. "
        "Use standard library + common packages. "
        "Install missing packages with subprocess + pip if needed. "
        "NEVER use: os.system, eval, exec, __import__, ctypes, socket. "
        "Return ONLY the Python code. No explanation, no markdown, no backticks.\n\n"
        f"SYSTEM PATHS:\n"
        f"  Desktop   = r'{desktop}'\n"
        f"  Downloads = r'{downloads}'\n"
        f"  Documents = r'{documents}'\n"
        f"  Home      = r'{home}'\n"
    )

    tmp_path = None
    try:
        code = _generate(
            "gemini-2.5-flash",
            f"Write Python code to accomplish this task:\n\n{description}",
            system=system_prompt,
        )
        code = code.strip()
        code = re.sub(r"```(?:python)?\s*", "", code).strip().rstrip("`").strip()

        # Safety check before execution
        danger = _check_code_safety(code)
        if danger:
            print(f"[Executor] 🚫 Generated code blocked: {danger}")
            if speak:
                speak("Generated code was unsafe. Trying a safer approach, sir.")
            raise RuntimeError(f"Code safety check failed: {danger}")

        # Length limit
        if len(code) > 10000:
            code = code[:10000] + "\n# Truncated"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        print(f"[Executor] 🐍 Running generated code: {tmp_path}")
        print(f"[Executor] 📝 Code preview:\n{code[:300]}...")

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, text=True,
            timeout=timeout,
            cwd=str(home),
        )

        output = result.stdout.strip()
        error  = result.stderr.strip()

        if result.returncode == 0 and output:
            return output
        elif result.returncode == 0:
            return "Task completed successfully."
        elif error:
            raise RuntimeError(f"Code error: {error[:400]}")
        return "Completed."

    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Generated code timed out after {timeout} seconds.")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Generated code failed: {e}")
    finally:
        # Always clean up temp file — even on timeout or crash
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ── Context injection between steps ───────────────────────────────────

def _inject_context(
    params: dict,
    tool: str,
    step_results: dict,
    goal: str = "",
) -> dict:
    """Inject previous step results into file write operations."""
    if not step_results:
        return params

    params = dict(params)

    if tool == "file_controller" and params.get("action") in ("write", "create_file"):
        content = params.get("content", "")
        if not content or len(content) < 50:
            all_results = [
                v for v in step_results.values()
                if v and len(str(v)) > 100 and str(v) not in ("Done.", "Completed.")
            ]
            if all_results:
                combined = "\n\n---\n\n".join(str(r) for r in all_results)
                translated = _translate_to_goal_language(combined, goal)
                params["content"] = translated
                print(f"[Executor] 💉 Injected + translated content")

    return params


def _detect_language(text: str) -> str:
    try:
        result = _generate(
            "gemini-2.5-flash-lite",
            f"What language is this text written in? "
            f"Reply with ONLY the language name in English "
            f"(e.g. Turkish, English, French).\n\n"
            f"Text: {text[:200]}"
        )
        return result.strip()
    except Exception:
        return "English"


def _translate_to_goal_language(content: str, goal: str) -> str:
    if not goal:
        return content
    try:
        target_lang = _detect_language(goal)
        print(f"[Executor] 🌐 Translating to: {target_lang}")

        prompt = (
            f"You are a professional translator. "
            f"Translate the following text into {target_lang}.\n"
            f"IMPORTANT:\n"
            f"- Translate EVERYTHING, leave nothing in English\n"
            f"- Keep all facts, numbers, and data intact\n"
            f"- Keep the structure and formatting\n"
            f"- Output ONLY the translated text, nothing else\n\n"
            f"Text to translate:\n{content[:4000]}"
        )
        translated = _generate("gemini-2.5-flash", prompt)
        print(f"[Executor] ✅ Translation done ({target_lang})")
        return translated.strip()
    except Exception as e:
        print(f"[Executor] ⚠️ Translation failed: {e}")
        return content


# ── Tool dispatch ─────────────────────────────────────────────────────

def _call_tool(
    tool: str,
    parameters: dict,
    speak: Optional[Callable],
) -> str:
    """Dispatch a tool call to the appropriate action module."""

    # Map tool names to (module_path, function_name, needs_speak)
    TOOL_MAP = {
        "open_app":           ("actions.open_app",          "open_app",          False),
        "web_search":         ("actions.web_search",        "web_search",        False),
        "game_updater":       ("actions.game_updater",      "game_updater",      True),
        "browser_control":    ("actions.browser_control",   "browser_control",   False),
        "file_controller":    ("actions.file_controller",   "file_controller",   False),
        "code_helper":        ("actions.code_helper",       "code_helper",       True),
        "dev_agent":          ("actions.dev_agent",         "dev_agent",         True),
        "send_message":       ("actions.send_message",      "send_message",      False),
        "reminder":           ("actions.reminder",          "reminder",          False),
        "youtube_video":      ("actions.youtube_video",     "youtube_video",     False),
        "weather_report":     ("actions.weather_report",    "weather_action",    False),
        "computer_settings":  ("actions.computer_settings", "computer_settings", False),
        "desktop_control":    ("actions.desktop",           "desktop_control",   False),
        "computer_control":   ("actions.computer_control",  "computer_control",  False),
        "flight_finder":      ("actions.flight_finder",     "flight_finder",     True),
        "web_research":       ("actions.web_research",      "web_research",      False),
        "security_tools":     ("actions.security_tools",    "security_tools",    False),
    }

    # Special case: generated_code (runs model-written code)
    if tool in ("generated_code", "code_runner"):
        description = parameters.get("description", "")
        if not description:
            raise ValueError("generated_code requires a 'description' parameter.")
        timeout = parameters.get("timeout", 120)
        return _run_generated_code(description, speak=speak, timeout=timeout)

    # Special case: screen_process (fire-and-forget)
    if tool == "screen_process":
        from actions.screen_processor import screen_process
        screen_process(parameters=parameters, player=None)
        return "Screen captured and analyzed."

    # Lookup in tool map
    if tool in TOOL_MAP:
        module_path, func_name, needs_speak = TOOL_MAP[tool]
        module = __import__(module_path, fromlist=[func_name])
        fn = getattr(module, func_name)

        call_params = {"parameters": parameters, "player": None}
        if needs_speak:
            call_params["speak"] = speak

        result = fn(**call_params)
        return result if result is not None else "Done."

    # Unknown tool — fall back to code generation
    print(f"[Executor] ⚠️ Unknown tool '{tool}' — "
          f"falling back to generated_code")
    return _run_generated_code(
        f"Accomplish this task: {parameters}", speak=speak)


# ── Agent Executor ────────────────────────────────────────────────────

class AgentExecutor:
    """
    Executes a multi-step plan with error recovery.
    Supports retry, skip, replan, and abort decisions.
    """

    MAX_REPLAN_ATTEMPTS = 3
    MAX_STEP_ATTEMPTS   = 3
    MAX_TOTAL_TIME      = 600  # 10 minute overall cap

    def __init__(self):
        self._metrics: Dict[str, Any] = {
            "steps_completed": 0,
            "steps_failed": 0,
            "steps_skipped": 0,
            "replan_count": 0,
            "total_time": 0.0,
        }

    def execute(
        self,
        goal: str,
        speak: Optional[Callable] = None,
        cancel_flag: Optional[threading.Event] = None,
        on_step_start: Optional[Callable] = None,    # progress callback
        on_step_done: Optional[Callable] = None,      # progress callback
    ) -> str:
        print(f"\n[Executor] 🎯 Goal: {goal}")
        start_time = time.time()

        replan_attempts = 0
        completed_steps: List[dict] = []
        step_results: Dict[Any, str] = {}
        plan = create_plan(goal)

        while True:
            # Overall timeout check
            elapsed = time.time() - start_time
            if elapsed > self.MAX_TOTAL_TIME:
                msg = (f"Task timed out after "
                       f"{int(elapsed)}s, sir. "
                       f"Completed {len(completed_steps)} steps.")
                if speak:
                    speak(msg)
                self._metrics["total_time"] = elapsed
                return msg

            steps = plan.get("steps", [])
            if not steps:
                msg = "I couldn't create a valid plan for this task, sir."
                if speak:
                    speak(msg)
                return msg

            success      = True
            failed_step  = None
            failed_error = ""

            for step in steps:
                if cancel_flag and cancel_flag.is_set():
                    if speak:
                        speak("Task cancelled, sir.")
                    return "Task cancelled."

                step_num = step.get("step", "?")
                tool     = step.get("tool", "generated_code")
                desc     = step.get("description", "")
                params   = step.get("parameters", {})
                critical = step.get("critical", False)

                # Inject context from previous steps
                params = _inject_context(params, tool, step_results, goal=goal)

                print(f"\n[Executor] ▶️ Step {step_num}: [{tool}] {desc}")

                # Progress callback
                if on_step_start:
                    try:
                        on_step_start(step_num, tool, desc)
                    except Exception:
                        pass

                attempt  = 1
                step_ok  = False

                while attempt <= self.MAX_STEP_ATTEMPTS:
                    if cancel_flag and cancel_flag.is_set():
                        break
                    try:
                        result = _call_tool(tool, params, speak)
                        step_results[step_num] = str(result)
                        completed_steps.append(step)
                        self._metrics["steps_completed"] += 1
                        print(f"[Executor] ✅ Step {step_num} done: "
                              f"{str(result)[:100]}")
                        step_ok = True

                        # Progress callback
                        if on_step_done:
                            try:
                                on_step_done(step_num, "success", str(result)[:200])
                            except Exception:
                                pass
                        break

                    except Exception as e:
                        error_msg = str(e)
                        print(f"[Executor] ❌ Step {step_num} attempt "
                              f"{attempt} failed: {error_msg}")

                        recovery = analyze_error(
                            step, error_msg, attempt=attempt,
                            max_attempts=self.MAX_STEP_ATTEMPTS)
                        decision = recovery["decision"]
                        user_msg = recovery.get("user_message", "")

                        if speak and user_msg:
                            speak(user_msg)

                        if decision == ErrorDecision.RETRY:
                            attempt += 1
                            wait = min(2 * attempt, 10)
                            time.sleep(wait)
                            continue

                        elif decision == ErrorDecision.SKIP:
                            print(f"[Executor] ⏭️ Skipping step {step_num}")
                            completed_steps.append(step)
                            step_results[step_num] = f"Skipped: {error_msg[:100]}"
                            self._metrics["steps_skipped"] += 1
                            step_ok = True

                            if on_step_done:
                                try:
                                    on_step_done(step_num, "skipped", user_msg)
                                except Exception:
                                    pass
                            break

                        elif decision == ErrorDecision.ABORT:
                            msg = (f"Task aborted, sir. "
                                   f"{recovery.get('reason', '')}")
                            if speak:
                                speak(msg)
                            self._metrics["steps_failed"] += 1
                            self._metrics["total_time"] = time.time() - start_time
                            return msg

                        else:  # REPLAN
                            fix_suggestion = recovery.get("fix_suggestion", "")
                            if fix_suggestion and tool != "generated_code":
                                try:
                                    fixed_step = generate_fix(
                                        step, error_msg, fix_suggestion)
                                    if speak:
                                        speak("Trying an alternative approach, sir.")
                                    res = _call_tool(
                                        fixed_step["tool"],
                                        fixed_step["parameters"],
                                        speak,
                                    )
                                    step_results[step_num] = str(res)
                                    completed_steps.append(step)
                                    self._metrics["steps_completed"] += 1
                                    step_ok = True

                                    if on_step_done:
                                        try:
                                            on_step_done(step_num, "fixed",
                                                         str(res)[:200])
                                        except Exception:
                                            pass
                                    break
                                except Exception as fix_err:
                                    print(f"[Executor] ⚠️ Fix failed: {fix_err}")

                            failed_step  = step
                            failed_error = error_msg
                            success      = False
                            break

                if not step_ok and not failed_step:
                    failed_step  = step
                    failed_error = "Max retries exceeded"
                    success      = False
                    self._metrics["steps_failed"] += 1

                if not success:
                    break

            if success:
                self._metrics["total_time"] = time.time() - start_time
                return self._summarize(goal, completed_steps, speak)

            replan_attempts += 1
            self._metrics["replan_count"] = replan_attempts

            if replan_attempts >= self.MAX_REPLAN_ATTEMPTS:
                msg = (f"Task failed after {replan_attempts} "
                       f"replan attempts, sir.")
                if speak:
                    speak(msg)
                self._metrics["total_time"] = time.time() - start_time
                return msg

            if speak:
                speak("Adjusting my approach, sir.")

            print(f"[Executor] 🔄 Replan #{replan_attempts}")
            plan = replan(goal, completed_steps, failed_step, failed_error)

    def _summarize(
        self,
        goal: str,
        completed_steps: list,
        speak: Optional[Callable],
    ) -> str:
        step_count = len(completed_steps)
        fallback = (f"All done, sir. Completed {step_count} "
                    f"step{'s' if step_count != 1 else ''} for: {goal[:60]}.")

        steps_str = "\n".join(
            f"- {s.get('description', '')}" for s in completed_steps)
        prompt = (
            f'User goal: "{goal}"\n'
            f"Completed steps:\n{steps_str}\n\n"
            "Write a single natural sentence summarizing what was "
            "accomplished. Address the user as 'sir'. "
            "Be direct and positive. Max 30 words."
        )
        try:
            summary = _generate("gemini-2.5-flash-lite", prompt)
            summary = summary.strip()
            if not summary or len(summary) > 200:
                summary = fallback
            if speak:
                speak(summary)
            return summary
        except Exception:
            if speak:
                speak(fallback)
            return fallback

    def get_metrics(self) -> Dict[str, Any]:
        """Return execution metrics for logging/monitoring."""
        return dict(self._metrics)
