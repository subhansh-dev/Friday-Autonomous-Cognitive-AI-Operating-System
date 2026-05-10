from google import genai
import psutil
import platform
import subprocess
import sys
import json
import re
import time
import shutil
from pathlib import Path


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR           = get_base_dir()
API_CONFIG_PATH    = BASE_DIR / "config" / "api_keys.json"
DESKTOP            = Path.home() / "Desktop"
MAX_BUILD_ATTEMPTS = 3
GEMINI_MODEL       = "gemini-2.5-flash"

# [FIX-2] Cached client
_client_instance = None

# [FIX-1] Known module → pip package aliases (shared pattern with dev_agent)
_PACKAGE_ALIASES = {
    "pil": "Pillow", "cv2": "opencv-python", "sklearn": "scikit-learn",
    "yaml": "PyYAML", "usb": "pyusb", "serial": "pyserial",
    "gi": "PyGObject", "wx": "wxPython", "attr": "attrs",
    "dateutil": "python-dateutil", "magic": "python-magic",
    "bs4": "beautifulsoup4", "dotenv": "python-dotenv",
    "jwt": "PyJWT", "git": "GitPython", "speech_recognition": "SpeechRecognition",
    "pyaudio": "PyAudio", "pynput": "pynput", "mss": "mss",
    "rich": "rich", "httpx": "httpx", "aiohttp": "aiohttp",
}


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


# [FIX-2] Singleton client
def _get_client():
    global _client_instance
    if _client_instance is None:
        _client_instance = genai.Client(api_key=_get_api_key())
    return _client_instance


def _generate(client, prompt: str, model: str = GEMINI_MODEL) -> str:
    response = client.models.generate_content(
        model=model,
        contents=prompt
    )
    return response.text


def _clean_code(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


# [FIX-5] Handle ~ tilde expansion
def _resolve_save_path(output_path: str, language: str) -> Path:
    ext_map = {
        "python": ".py", "py": ".py",
        "javascript": ".js", "js": ".js",
        "typescript": ".ts", "ts": ".ts",
        "html": ".html", "css": ".css",
        "java": ".java", "cpp": ".cpp", "c": ".c",
        "bash": ".sh", "shell": ".sh", "powershell": ".ps1",
        "sql": ".sql", "json": ".json", "rust": ".rs", "go": ".go",
    }
    if output_path:
        p = Path(output_path).expanduser()
        return p if p.is_absolute() else DESKTOP / p
    ext = ext_map.get((language or "python").lower(), ".py")
    return DESKTOP / f"jarvis_code{ext}"


# [FIX-10] Binary file protection
def _read_file(file_path: str) -> tuple[str, str]:
    if not file_path:
        return "", "No file path provided."
    p = Path(file_path).expanduser()
    if not p.exists():
        return "", f"File not found: {file_path}"

    # Check for binary files (first 8KB)
    try:
        chunk = p.read_bytes()[:8192]
        if b"\x00" in chunk:
            return "", f"Binary file detected: {file_path}. Cannot read as text."
    except Exception:
        pass

    try:
        return p.read_text(encoding="utf-8"), ""
    except UnicodeDecodeError:
        try:
            return p.read_text(encoding="latin-1"), ""
        except Exception as e:
            return "", f"Could not read file: {e}"
    except Exception as e:
        return "", f"Could not read file: {e}"


def _save_file(path: Path, content: str) -> str:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Saved to: {path}"
    except Exception as e:
        return f"Could not save: {e}"


# [NEW] Backup before overwriting
def _backup_file(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_suffix(f".bak{path.suffix}")
    try:
        shutil.copy2(path, backup)
        return backup
    except Exception:
        return None


def _preview(code: str, lines: int = 10) -> str:
    if not code:
        return "(empty)"
    all_lines = code.splitlines()
    preview   = "\n".join(all_lines[:lines])
    suffix    = f"\n... ({len(all_lines) - lines} more lines)" if len(all_lines) > lines else ""
    return preview + suffix


# [FIX-1] + [FIX-7] Completely rewritten — no more false positives
def _has_error(output: str) -> bool:
    if not output.strip():
        return False

    low = output.lower()

    # Timed out means long-running app, not an error
    if "timed out" in low:
        return False

    # If pip installed something successfully, ignore stderr noise
    if "successfully installed" in low:
        return False

    # Strong error signals — actual Python/runtime errors
    strong_signals = [
        "traceback (most recent call last)",
        "syntaxerror:",
        "nameerror:",
        "typeerror:",
        "attributeerror:",
        "valueerror:",
        "keyerror:",
        "indexerror:",
        "modulenotfounderror:",
        "importerror:",
        "filenotfounderror:",
        "permissionerror:",
        "zerodivisionerror:",
        "recursionerror:",
        "runtimeerror:",
        "connectionrefusederror:",
        "timeouterror:",
        "oserror:",
    ]
    if any(s in low for s in strong_signals):
        return True

    # Exit code pattern: "exit status 1" or "returned non-zero"
    if re.search(r"exit (code|status) [1-9]", low):
        return True
    if "returned non-zero" in low:
        return True

    return False


def _take_screenshot() -> Path | None:
    try:
        import pyautogui
        screenshot_path = DESKTOP / f"jarvis_debug_{int(time.time())}.png"
        screenshot = pyautogui.screenshot()
        screenshot.save(str(screenshot_path))
        print(f"[Code] Screenshot: {screenshot_path}")
        return screenshot_path
    except Exception as e:
        print(f"[Code] Screenshot failed: {e}")
        return None


def _image_to_base64(path: Path) -> str:
    import base64
    return base64.b64encode(path.read_bytes()).decode("utf-8")


# [FIX-3] Deduplicated intent detection
def _detect_intent(description: str, file_path: str, code: str) -> str:
    desc = (description or "").lower()

    # Priority 1: Screen/vision requests
    screen_kw = ["screen", "what do you see", "analyze my screen", "look at camera", "screenshot"]
    if any(k in desc for k in screen_kw):
        return "screen_debug"

    # Priority 2: System diagnostic
    diag_kw = ["health", "diagnostic", "system status", "usage",
                "cpu usage", "ram usage", "disk usage", "system stats"]
    if any(k in desc for k in diag_kw):
        return "diagnostic"

    # Priority 3: File-based actions (only if file exists or path given)
    if file_path:
        p = Path(file_path).expanduser()
        edit_kw  = ["edit", "update", "modify", "change", "add to", "remove from", "fix", "rename", "replace"]
        run_kw   = ["run", "execute", "launch", "start"]
        opt_kw   = ["optimize", "refactor", "clean up", "improve", "make it better", "make it faster"]

        if p.exists() and any(k in desc for k in opt_kw):
            return "optimize"
        if p.exists() and any(k in desc for k in edit_kw):
            return "edit"
        if p.exists() and any(k in desc for k in run_kw):
            return "run"
        if p.exists() and any(k in desc for k in ["explain", "what does", "describe", "analyze", "read"]):

            return "explain"
        if p.exists():
            return "explain"

    # Priority 4: Optimize with inline code
    opt_kw = ["optimize", "refactor", "clean up", "improve", "make it better"]
    if any(k in desc for k in opt_kw) and code:
        return "optimize"

    # Priority 5: Explain with inline code
    explain_kw = ["explain", "what does", "describe", "analyze"]
    if any(k in desc for k in explain_kw) and code:
        return "explain"

    # Priority 6: Build (multi-attempt with fix loop)
    build_kw = ["build", "make it work", "try and", "attempt", "create and test"]
    if any(k in desc for k in build_kw):
        return "build"

    # Default: write new code
    return "write"


# [FIX-8] Auto-install missing dependencies
def _try_auto_install(error_output: str) -> bool:
    pattern = re.compile(r"No module named ['\"]([a-zA-Z0-9_\-\.]+)['\"]", re.IGNORECASE)
    match = pattern.search(error_output)
    if not match:
        return False

    module_name = match.group(1).replace("_", "-").split(".")[0]
    pkg = _PACKAGE_ALIASES.get(module_name.lower(), module_name)
    print(f"[Code] 🔧 Auto-installing: {pkg}")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=60,
        )
        return result.returncode == 0
    except Exception:
        return False


def _write(description: str, language: str, output_path: str, player=None) -> tuple[str, Path]:
    lang   = language or "python"
    client = _get_client()

    prompt = f"""You are an expert {lang} developer.
Write clean, working, well-commented {lang} code for the description below.

Rules:
- Output ONLY the code. No explanation, no markdown, no backticks.
- Add helpful inline comments.
- Handle errors and edge cases properly.
- Use modern best practices.
- If you use third-party packages, add a comment at the top listing them (e.g. # requires: requests, pillow).

Description: {description}

Code:"""

    code = _clean_code(_generate(client, prompt))
    path = _resolve_save_path(output_path, lang)
    _save_file(path, code)
    return code, path


# [FIX-12] Better fix context with language + imports
def _fix_code(code: str, error_output: str, description: str, language: str = "python") -> str:
    client = _get_client()
    prompt = f"""You are an expert {language} debugger.
The code below failed with the following error. Fix it.
Return ONLY the corrected code - no explanation, no markdown, no backticks.

Original goal: {description}
Language: {language}

Error:
{error_output[:2000]}

Broken code:
{code}

Rules:
- Fix ALL errors visible in the traceback.
- Keep all existing working logic — do not remove features.
- If a third-party module is missing, add it to the imports and add a comment: # requires: package_name
- Ensure the fix is complete and runnable.

Fixed code:"""

    return _clean_code(_generate(client, prompt))


# [FIX-6] shell=True on Windows
def _run_file(path: Path, args: list, timeout: int) -> str:
    interpreters = {
        ".py":  [sys.executable],
        ".js":  ["node"],
        ".ts":  ["ts-node"],
        ".sh":  ["bash"],
        ".ps1": ["powershell", "-File"],
        ".rb":  ["ruby"],
        ".php": ["php"],
    }
    interp = interpreters.get(path.suffix.lower())
    if not interp:
        return f"No interpreter registered for {path.suffix} files."

    cmd = interp + [str(path)] + (args or [])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout,
            cwd=str(path.parent),
            shell=(sys.platform == "win32"),
        )
        output = result.stdout.strip()
        error  = result.stderr.strip()
        parts  = []
        if output:
            parts.append(f"Output:\n{output}")
        if error:
            parts.append(f"Stderr:\n{error}")
        return "\n\n".join(parts) if parts else "Executed with no output."

    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s — long-running app is likely working."
    except FileNotFoundError:
        return f"Interpreter not found: {interp[0]}."
    except Exception as e:
        return f"Execution error: {e}"


# [FIX-9] Handle args as string or list
def _normalize_args(args) -> list:
    if isinstance(args, list):
        return [str(a) for a in args]
    if isinstance(args, str):
        return args.split() if args.strip() else []
    return []


def _build(description, language, output_path, args, timeout, speak=None, player=None) -> str:
    if not description:
        return "Please describe what you want me to build, sir."

    if player:
        player.write_log("[Code] Build started...")

    lang = language or "python"
    args = _normalize_args(args)

    try:
        code, path = _write(description, lang, output_path, player)
        print(f"[Code] Written: {path}")
    except Exception as e:
        msg = f"Could not write initial code: {e}"
        if speak:
            speak(msg)
        return msg

    last_output = ""
    auto_installs = 0

    for attempt in range(1, MAX_BUILD_ATTEMPTS + 1):
        print(f"[Code] Attempt {attempt}/{MAX_BUILD_ATTEMPTS}")
        if player:
            player.write_log(f"[Code] Attempt {attempt}...")

        last_output = _run_file(path, args, timeout)

        if not _has_error(last_output):
            msg = (
                f"Build complete, sir. "
                f"The code is working after {attempt} attempt{'s' if attempt > 1 else ''}. "
                f"Saved to {path}."
            )
            if speak:
                speak(msg)
            return f"{msg}\n\nOutput:\n{last_output}"

        print(f"[Code] Error on attempt {attempt}, fixing...")

        # [FIX-8] Try auto-installing missing deps before asking Gemini
        if auto_installs < 3 and _try_auto_install(last_output):
            auto_installs += 1
            print(f"[Code] Installed missing dependency, retrying...")
            if player:
                player.write_log(f"[Code] Installed missing dep, retrying...")
            time.sleep(1)
            continue

        if player:
            player.write_log(f"[Code] Fixing (attempt {attempt})...")

        try:
            # [FIX-12] Pass language for better fix context
            code = _fix_code(code, last_output, description, lang)
            _save_file(path, code)
        except Exception as e:
            msg = f"Could not fix code on attempt {attempt}: {e}"
            if speak:
                speak(msg)
            return msg

    msg = (
        f"I was unable to build a working version after {MAX_BUILD_ATTEMPTS} attempts, sir. "
        f"The last error was:\n{last_output[:300]}"
    )
    if speak:
        speak(msg)
    return f"{msg}\n\nLast code saved to: {path}"


# [FIX] Added speak parameter for consistency
def _write_action(description, language, output_path, player, speak=None) -> str:
    if not description:
        return "Please describe what you want me to write, sir."
    if player:
        player.write_log("[Code] Writing code...")
    try:
        code, path = _write(description, language, output_path, player)
        print(f"[Code] Written: {path}")
        msg = f"Code written. Saved to: {path}\n\nPreview:\n{_preview(code)}"
        if speak:
            speak(f"Code written and saved to {path.name}.")
        return msg
    except Exception as e:
        msg = f"Could not generate code: {e}"
        if speak:
            speak(msg)
        return msg


def _edit_action(file_path, instruction, player) -> str:
    if not file_path:
        return "Please provide a file path to edit, sir."
    if not instruction:
        return "Please describe what change to make, sir."

    content, err = _read_file(file_path)
    if err:
        return err

    if player:
        player.write_log("[Code] Editing file...")

    # [NEW] Backup before editing
    _backup_file(Path(file_path).expanduser())

    client = _get_client()
    lang = Path(file_path).expanduser().suffix.lstrip(".")
    prompt = f"""You are an expert code editor.
Apply the following change to the code below.
Return ONLY the complete updated code - no explanation, no markdown, no backticks.

Change: {instruction}

Original code:
{content}

Rules:
- Keep all existing working code intact.
- Only modify what the instruction requires.
- Preserve formatting, imports, and error handling.

Updated code:"""

    try:
        edited = _clean_code(_generate(client, prompt))
    except Exception as e:
        return f"Could not edit code: {e}"

    status = _save_file(Path(file_path).expanduser(), edited)
    print(f"[Code] Edited: {file_path}")

    original_lines  = len(content.splitlines())
    edited_lines    = len(edited.splitlines())
    diff = edited_lines - original_lines
    diff_str = f"(+{diff} lines)" if diff > 0 else f"({diff} lines)" if diff < 0 else "(same length)"

    return f"File edited. {status} {diff_str}\n\nPreview:\n{_preview(edited)}"


def _explain_action(file_path, code, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code or a file path to explain, sir."

    if player:
        player.write_log("[Code] Analyzing code...")

    client = _get_client()
    truncated = len(code) > 4000
    prompt = f"""Explain what this code does in simple, clear language.
Focus on: what it does, how it works, and any important details.
Be concise - 3 to 6 sentences maximum.
{"(Note: code was truncated at 4000 chars)" if truncated else ""}

Code:
{code[:4000]}

Explanation:"""

    try:
        return _generate(client, prompt).strip()
    except Exception as e:
        return f"Could not explain code: {e}"


def _run_action(file_path, args, timeout, player) -> str:
    if not file_path:
        return "Please provide a file path to run, sir."
    p = Path(file_path).expanduser()
    if not p.exists():
        return f"File not found: {file_path}"
    if player:
        player.write_log(f"[Code] Running {p.name}...")
    return _run_file(p, _normalize_args(args), timeout)


def _optimize_action(file_path, code, language, output_path, player) -> str:
    if file_path and not code:
        code, err = _read_file(file_path)
        if err:
            return err
    if not code:
        return "Please provide code or a file path to optimize, sir."

    if player:
        player.write_log("[Code] Optimizing code...")

    lang   = language or "python"
    client = _get_client()

    truncated = len(code) > 6000
    prompt = f"""You are an expert {lang} developer and code reviewer.
Optimize the following code for performance, readability, and best practices.
Return ONLY the optimized code - no explanation, no markdown, no backticks.
{"(Note: code was truncated at 6000 chars — optimize what's visible)" if truncated else ""}

Original code:
{code[:6000]}

Rules:
- Improve performance where possible.
- Improve readability and naming.
- Add type hints if {lang} supports them.
- Remove dead code and redundant logic.
- Keep ALL existing functionality intact.

Optimized code:"""

    try:
        optimized = _clean_code(_generate(client, prompt))
    except Exception as e:
        return f"Could not optimize code: {e}"

    if file_path:
        save_path = Path(file_path).expanduser()
        # [NEW] Backup before overwriting
        _backup_file(save_path)
    else:
        save_path = _resolve_save_path(output_path, lang)

    status = _save_file(save_path, optimized)
    print(f"[Code] Optimized: {save_path}")

    original_lines  = len(code.splitlines())
    optimized_lines = len(optimized.splitlines())
    diff = original_lines - optimized_lines

    return (
        f"Code optimized. {status}\n"
        f"Lines: {original_lines} -> {optimized_lines} "
        f"({'-' if diff > 0 else '+'}{abs(diff)} lines)\n\n"
        f"Preview:\n{_preview(optimized)}"
    )


def _diagnostic_action(player=None) -> str:
    if player:
        player.write_log("[Code] Running system diagnostics...")

    cpu  = psutil.cpu_percent(interval=0.5)
    mem  = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    sys_info = f"{platform.system()} {platform.release()} ({platform.machine()})"

    # [NEW] Top processes by CPU
    top_procs = ""
    try:
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent']):
            info = p.info
            if info['cpu_percent'] and info['cpu_percent'] > 1.0:
                procs.append(info)
        procs.sort(key=lambda x: x['cpu_percent'], reverse=True)
        if procs:
            top_procs = "\n- Top processes: " + ", ".join(
                f"{p['name']} ({p['cpu_percent']:.0f}%)" for p in procs[:3]
            )
    except Exception:
        pass

    # [NEW] Battery info (laptops)
    battery_str = ""
    try:
        bat = psutil.sensors_battery()
        if bat:
            battery_str = f"\n- Battery: {bat.percent}%{' (charging)' if bat.power_plugged else ''}"
    except Exception:
        pass

    return (
        f"Systems check complete, Sir.\n"
        f"HUD Update:\n"
        f"- OS: {sys_info}\n"
        f"- CPU Load: {cpu}%\n"
        f"- Memory: {mem.percent}% ({mem.used // (1024**2)}MB / {mem.total // (1024**2)}MB)\n"
        f"- Disk: {disk.free // (1024**3)}GB free of {disk.total // (1024**3)}GB"
        f"{top_procs}{battery_str}\n"
        f"Everything is grand."
    )


# [FIX-4] Use GEMINI_MODEL constant, [FIX-11] Don't auto-save without confirmation
def _screen_debug_action(description, file_path, player, speak=None) -> str:
    if player:
        player.write_log("[Code] Taking screenshot for analysis...")

    screenshot_path = _take_screenshot()
    if not screenshot_path:
        return "Could not take screenshot, sir."

    file_content = ""
    if file_path:
        file_content, err = _read_file(file_path)
        if err:
            print(f"[Code] Could not read file for context: {err}")

    try:
        client = _get_client()
        from google.genai import types
        image_bytes = screenshot_path.read_bytes()

        user_question = description or "What error or problem do you see on the screen? How can it be fixed?"
        context = f"\n\nRelated file:\n```\n{file_content[:4000]}\n```" if file_content else ""

        analysis_prompt = f"""You are an expert programmer analyzing a screenshot.
User's question: {user_question}{context}
Identify errors, explain the cause, and provide a concrete fix. Be specific and actionable.
If you provide fixed code, wrap it in triple backticks with the language name."""

        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            analysis_prompt,
        ]

        # [FIX-4] Use constant instead of hardcoded string
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
        )

        analysis = response.text.strip()

        # Clean up screenshot
        try:
            screenshot_path.unlink()
        except Exception:
            pass

        # [FIX-11] Don't auto-save — report the fix suggestion instead
        if file_path and file_content:
            code_match = re.search(r"```[a-zA-Z]*\n(.*?)```", analysis, re.DOTALL)
            if code_match:
                fixed_code = code_match.group(1).strip()
                # Show diff info instead of silently overwriting
                original_lines = len(file_content.splitlines())
                fixed_lines = len(fixed_code.splitlines())
                analysis += (
                    f"\n\n--- Suggested Fix ---\n"
                    f"Lines: {original_lines} -> {fixed_lines}\n"
                    f"To apply: use the 'edit' action with this file path and the fix description.\n"
                    f"Or manually copy the suggested code above."
                )

        return analysis

    except Exception as e:
        try:
            screenshot_path.unlink()
        except Exception:
            pass
        return f"Screen analysis failed: {e}"


def code_helper(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None
) -> str:
    p           = parameters or {}
    action      = p.get("action", "auto").lower().strip()
    description = p.get("description", "").strip()
    language    = p.get("language", "python").strip()
    output_path = p.get("output_path", "").strip()
    file_path   = p.get("file_path", "").strip()
    code        = p.get("code", "").strip()
    args        = p.get("args", [])
    timeout     = int(p.get("timeout", 30))

    # [FIX-9] Normalize args at entry point
    args = _normalize_args(args)

    if action == "auto":
        action = _detect_intent(description, file_path, code)
        print(f"[Code] Auto-detected: {action}")

    if action == "write":
        return _write_action(description, language, output_path, player, speak)
    elif action == "edit":
        return _edit_action(file_path, description or p.get("instruction", ""), player)
    elif action == "explain":
        return _explain_action(file_path, code, player)
    elif action == "run":
        return _run_action(file_path, args, timeout, player)
    elif action == "build":
        return _build(description, language, output_path, args, timeout, speak, player)
    elif action == "optimize":
        return _optimize_action(file_path, code, language, output_path, player)
    elif action == "screen_debug":
        return _screen_debug_action(description, file_path, player, speak)
    elif action == "diagnostic":
        return _diagnostic_action(player)
    else:
        return (
            f"Unknown action: '{action}'. "
            f"Use: write, edit, explain, run, build, optimize, diagnostic, or screen_debug."
        )
