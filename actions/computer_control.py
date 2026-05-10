import io
import json
import os
import re
import string
import subprocess
import sys
import time
import random
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE         = _base_dir()
_CONFIG_PATH  = _BASE / "config" / "api_keys.json"
_MEMORY_PATH  = _BASE / "memory" / "long_term.json"

# [FIX-3] Cache config and OS detection
_config_cache: dict | None = None
_os_cache: str | None = None
_client_instance = None


def _load_config() -> dict:
    global _config_cache
    if _config_cache is None:
        try:
            _config_cache = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            _config_cache = {}
    return _config_cache


# [FIX-3] Cached OS detection
def _get_os() -> str:
    global _os_cache
    if _os_cache is None:
        _os_cache = _load_config().get("os_system", "").lower()
        if not _os_cache:
            # Auto-detect if not in config
            import platform
            system = platform.system().lower()
            _os_cache = {"darwin": "mac", "windows": "windows", "linux": "linux"}.get(system, "windows")
    return _os_cache


def _get_api_key() -> str:
    return _load_config().get("gemini_api_key", "")


# [FIX-2] Platform-aware modifier key
def _mod_key() -> str:
    """Return the primary modifier key for the current platform."""
    return "command" if _get_os() == "mac" else "ctrl"


# [FIX-5] Cached Gemini client
def _get_client():
    global _client_instance
    if _client_instance is None:
        from google import genai
        _client_instance = genai.Client(api_key=_get_api_key())
    return _client_instance


_SAFE_SCREENSHOT_ROOTS = (
    Path.home(),
)


def _safe_screenshot_path(requested: str | None) -> Path:
    fallback = Path.home() / "Desktop" / "jarvis_screenshot.png"
    if not requested:
        return fallback
    try:
        p = Path(requested).expanduser().resolve()
        for root in _SAFE_SCREENSHOT_ROOTS:
            if p.is_relative_to(root.resolve()):
                p.parent.mkdir(parents=True, exist_ok=True)
                return p
    except Exception:
        pass
    return fallback


def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")


_FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Drew", "Quinn",
    "Avery", "Blake", "Cameron", "Dakota", "Emerson", "Finley", "Harper",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson",
]
_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "proton.me", "mail.com"]


def _random_data(data_type: str) -> str:
    dt = data_type.lower().strip()

    if dt == "first_name":
        return random.choice(_FIRST_NAMES)
    if dt == "last_name":
        return random.choice(_LAST_NAMES)
    if dt == "name":
        return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"
    if dt == "email":
        first = random.choice(_FIRST_NAMES).lower()
        last  = random.choice(_LAST_NAMES).lower()
        num   = random.randint(10, 999)
        return f"{first}.{last}{num}@{random.choice(_DOMAINS)}"
    if dt == "username":
        return f"{random.choice(_FIRST_NAMES).lower()}{random.randint(100, 9999)}"
    if dt == "password":
        # [FIX-11] Simpler, guaranteed-complexity password
        upper   = random.choice(string.ascii_uppercase)
        lower   = random.choice(string.ascii_lowercase)
        digit   = random.choice(string.digits)
        special = random.choice("!@#$%&*")
        rest    = "".join(random.choices(string.ascii_letters + string.digits + "!@#$%&*", k=8))
        raw     = upper + lower + digit + special + rest
        return "".join(random.sample(raw, len(raw)))
    if dt == "phone":
        return f"+1{random.randint(200, 999)}{random.randint(1_000_000, 9_999_999)}"
    if dt == "birthday":
        y = random.randint(1980, 2005)
        m = random.randint(1, 12)
        d = random.randint(1, 28)
        return f"{m:02d}/{d:02d}/{y}"
    if dt == "address":
        num    = random.randint(100, 9999)
        street = random.choice(["Main St", "Oak Ave", "Park Blvd", "Elm St", "Cedar Ln"])
        return f"{num} {street}"
    if dt == "zip_code":
        return str(random.randint(10000, 99999))
    if dt == "city":
        return random.choice(["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"])
    if dt == "country":
        return random.choice(["United States", "Canada", "United Kingdom", "Germany", "France"])
    if dt == "company":
        return random.choice(["Acme Corp", "Globex Inc", "Initech", "Umbrella Corp", "Stark Industries"])

    return f"random_{data_type}_{random.randint(1000, 9999)}"


def _user_profile() -> dict:
    """Read identity fields from long-term memory."""
    try:
        if _MEMORY_PATH.exists():
            data     = json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
            identity = data.get("identity", {})
            return {k: v.get("value", "") for k, v in identity.items()}
    except Exception:
        pass
    return {}


# [FIX-1] Complete rewrite — clipboard-backed typing for ALL text (handles Unicode)
def _type(text: str, interval: float = 0.03) -> str:
    _require_pyautogui()
    if not text:
        return "No text to type."

    time.sleep(0.15)

    # Always use clipboard for non-ASCII or longer text
    has_non_ascii = any(ord(c) > 127 for c in text)
    if has_non_ascii or len(text) > 10:
        if _PYPERCLIP:
            pyperclip.copy(text)
            time.sleep(0.05)
            pyautogui.hotkey(_mod_key(), "v")
            return f"Typed (clipboard): {text[:60]}{'…' if len(text) > 60 else ''}"
        # Fallback: strip non-ASCII and use typewrite
        text = text.encode("ascii", "ignore").decode("ascii")
        if not text:
            return "Cannot type Unicode text without pyperclip."

    pyautogui.typewrite(text, interval=interval)
    return f"Typed: {text[:60]}{'…' if len(text) > 60 else ''}"


# [FIX-1] + [FIX-4] Unicode-safe smart typing
def _smart_type(text: str, clear_first: bool = True) -> str:
    _require_pyautogui()
    if not text:
        return "No text to type."

    if clear_first:
        _clear_field()
        time.sleep(0.1)

    # [FIX-4] Always use clipboard for non-ASCII text, regardless of length
    has_non_ascii = any(ord(c) > 127 for c in text)
    if has_non_ascii or len(text) > 20:
        if _PYPERCLIP:
            pyperclip.copy(text)
            time.sleep(0.1)
            pyautogui.hotkey(_mod_key(), "v")
            return f"Smart-typed (clipboard): {text[:60]}{'…' if len(text) > 60 else ''}"

    pyautogui.typewrite(text, interval=0.04)
    return f"Smart-typed: {text[:60]}{'…' if len(text) > 60 else ''}"


# [FIX-9] Coordinate validation
def _validate_coords(x: int, y: int) -> bool:
    try:
        w, h = pyautogui.size()
        return 0 <= x <= w and 0 <= y <= h
    except Exception:
        return True  # If we can't check, allow it


def _click(x=None, y=None, button: str = "left", clicks: int = 1) -> str:
    _require_pyautogui()
    if x is not None and y is not None:
        x, y = int(x), int(y)
        if not _validate_coords(x, y):
            return f"Coordinates ({x}, {y}) are out of screen bounds."
        pyautogui.click(x, y, button=button, clicks=clicks)
        label = "Double-c" if clicks == 2 else "C"
        return f"{label}licked ({x}, {y}) [{button}]"
    pyautogui.click(button=button, clicks=clicks)
    return f"Clicked at current position [{button}]"


def _hotkey(*keys) -> str:
    _require_pyautogui()
    pyautogui.hotkey(*keys)
    return f"Hotkey: {'+'.join(keys)}"


def _press(key: str) -> str:
    _require_pyautogui()
    pyautogui.press(key)
    return f"Pressed: {key}"


def _scroll(direction: str = "down", amount: int = 3) -> str:
    _require_pyautogui()
    vertical = direction in ("up", "down")
    clicks   = amount if direction in ("up", "right") else -amount
    if vertical:
        pyautogui.scroll(clicks)
    else:
        pyautogui.hscroll(clicks)
    return f"Scrolled {direction} ×{amount}"


def _move(x: int, y: int, duration: float = 0.3) -> str:
    _require_pyautogui()
    x, y = int(x), int(y)
    if not _validate_coords(x, y):
        return f"Coordinates ({x}, {y}) are out of screen bounds."
    pyautogui.moveTo(x, y, duration=duration)
    return f"Mouse → ({x}, {y})"


def _drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> str:
    _require_pyautogui()
    pyautogui.moveTo(int(x1), int(y1), duration=0.2)
    pyautogui.dragTo(int(x2), int(y2), duration=duration, button="left")
    return f"Dragged ({x1},{y1}) → ({x2},{y2})"


# [FIX-2] Platform-aware clipboard operations
def _clipboard_get() -> str:
    if _PYPERCLIP:
        return pyperclip.paste()
    _require_pyautogui()
    pyautogui.hotkey(_mod_key(), "c")
    time.sleep(0.2)
    return "(copied — pyperclip unavailable for readback)"


def _clipboard_paste(text: str) -> str:
    if not text:
        return "No text to paste."
    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.1)
        _require_pyautogui()
        pyautogui.hotkey(_mod_key(), "v")
        return f"Pasted: {text[:60]}{'…' if len(text) > 60 else ''}"
    return "pyperclip not available — cannot paste."


def _screenshot(save_path: str | None = None) -> str:
    _require_pyautogui()
    path = _safe_screenshot_path(save_path)
    img  = pyautogui.screenshot()
    img.save(str(path))
    return f"Screenshot saved: {path}"


# [FIX-2] Platform-aware clear
def _clear_field() -> str:
    _require_pyautogui()
    pyautogui.hotkey(_mod_key(), "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    return "Field cleared"


def _focus_window(title: str) -> str:
    if not title:
        return "No window title provided."

    os_name = _get_os()

    if os_name == "windows":
        try:
            script = f'(New-Object -ComObject WScript.Shell).AppActivate("{title}")'
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, timeout=5,
            )
            time.sleep(0.3)
            return f"Focused window: {title}"
        except Exception as e:
            return f"focus_window (Windows) failed: {e}"

    if os_name == "mac":
        script = (
            f'tell application "System Events" to '
            f'set frontmost of (first process whose name contains "{title}") to true'
        )
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, timeout=5,
            )
            time.sleep(0.3)
            return f"Focused window: {title}"
        except Exception as e:
            return f"focus_window (macOS) failed: {e}"

    if os_name == "linux":
        # Try wmctrl first
        try:
            result = subprocess.run(
                ["wmctrl", "-a", title],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                time.sleep(0.3)
                return f"Focused window: {title}"
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[ComputerControl] wmctrl error: {e}")

        # [FIX-10] Try xdotool with proper error handling
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", title, "windowactivate"],
                capture_output=True, timeout=5,
            )
            time.sleep(0.3)
            if result.returncode == 0:
                return f"Focused window: {title}"
            return f"Could not find window: {title}"
        except FileNotFoundError:
            return "focus_window (Linux) requires wmctrl or xdotool — neither found."
        except Exception as e:
            return f"focus_window (Linux) failed: {e}"

    return f"focus_window: unknown OS '{os_name}'"


# [FIX-5] Cached client for screen_find
GEMINI_VISION_MODEL = "gemini-2.5-flash"


def _screen_find(description: str) -> tuple[int, int] | None:
    if not description:
        return None

    api_key = _get_api_key()
    if not api_key:
        print("[ComputerControl] ⚠️ No API key for screen_find")
        return None

    try:
        from google.genai import types

        _require_pyautogui()
        w, h = pyautogui.size()
        img  = pyautogui.screenshot()
        buf  = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        client = _get_client()
        prompt = (
            f"This is a screenshot of a {w}×{h} pixel screen. "
            f"Locate the UI element described as: '{description}'. "
            f"Reply with ONLY the center coordinates as: x,y "
            f"If the element is not visible, reply: NOT_FOUND"
        )

        response = client.models.generate_content(
            model=GEMINI_VISION_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ],
        )

        text = (response.text or "").strip()
        if "NOT_FOUND" in text.upper():
            return None

        match = re.search(r"(\d+)\s*,\s*(\d+)", text)
        if match:
            x, y = int(match.group(1)), int(match.group(2))
            # Validate the returned coords are on screen
            if 0 <= x <= w and 0 <= y <= h:
                return x, y
            print(f"[ComputerControl] ⚠️ AI returned off-screen coords: ({x},{y})")

    except Exception as e:
        print(f"[ComputerControl] ⚠️ screen_find failed: {e}")

    return None


def computer_control(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Dispatch table for all computer control actions.

    Actions: type, smart_type, click, double_click, right_click, move, drag,
             hotkey, press, scroll, copy, paste, screenshot, wait, clear_field,
             focus_window, screen_find, screen_click, random_data, user_data
    """
    params = parameters or {}
    action = params.get("action", "").lower().strip()

    if not action:
        return "No action specified for computer_control."

    if player:
        player.write_log(f"[Computer] {action}")

    print(f"[ComputerControl] ▶ {action}  {params}")

    try:
        # [FIX-7] elif chain — stop checking after first match
        if action == "type":
            return _type(params.get("text", ""))

        elif action == "smart_type":
            return _smart_type(
                params.get("text", ""),
                clear_first=params.get("clear_first", True),
            )

        elif action in ("click", "left_click"):
            return _click(params.get("x"), params.get("y"), "left", 1)

        elif action == "double_click":
            return _click(params.get("x"), params.get("y"), "left", 2)

        elif action == "right_click":
            return _click(params.get("x"), params.get("y"), "right", 1)

        elif action == "move":
            return _move(int(params.get("x", 0)), int(params.get("y", 0)))

        elif action == "drag":
            # [FIX-8] Support both x1/y1/x2/y2 and x/y pairs
            x1 = int(params.get("x1", params.get("x", 0)))
            y1 = int(params.get("y1", params.get("y", 0)))
            x2 = int(params.get("x2", 0))
            y2 = int(params.get("y2", 0))
            return _drag(x1, y1, x2, y2)

        elif action == "hotkey":
            raw  = params.get("keys", "")
            keys = [k.strip() for k in raw.split("+")] if isinstance(raw, str) else raw
            if not keys or not keys[0]:
                return "No keys specified for hotkey."
            return _hotkey(*keys)

        elif action == "press":
            return _press(params.get("key", "enter"))

        elif action == "scroll":
            return _scroll(
                direction=params.get("direction", "down"),
                amount=int(params.get("amount", 3)),
            )

        elif action == "copy":
            return _clipboard_get()

        elif action == "paste":
            return _clipboard_paste(params.get("text", ""))

        elif action == "screenshot":
            return _screenshot(params.get("path"))

        elif action == "screen_find":
            coords = _screen_find(params.get("description", ""))
            return f"{coords[0]},{coords[1]}" if coords else "NOT_FOUND"

        elif action == "screen_click":
            desc   = params.get("description", "")
            coords = _screen_find(desc)
            if coords:
                time.sleep(0.2)
                _click(x=coords[0], y=coords[1])
                return f"Clicked '{desc}' at {coords}"
            return f"Element not found on screen: '{desc}'"

        elif action == "wait":
            secs = float(params.get("seconds", 1.0))
            secs = max(0.1, min(secs, 30.0))  # Clamp to [0.1, 30]
            time.sleep(secs)
            return f"Waited {secs}s"

        elif action == "clear_field":
            return _clear_field()

        elif action == "focus_window":
            return _focus_window(params.get("title", ""))

        elif action == "random_data":
            dt     = params.get("type", "name")
            result = _random_data(dt)
            print(f"[ComputerControl] 🎲 random {dt} → {result}")
            return result

        elif action == "user_data":
            field   = params.get("field", "name")
            profile = _user_profile()
            value   = profile.get(field, "")
            if not value:
                value = _random_data(field)
                print(f"[ComputerControl] ⚠️ No '{field}' in memory, using random: {value}")
            return value

        else:
            return f"Unknown action: '{action}'"

    except Exception as e:
        print(f"[ComputerControl] ❌ {action}: {e}")
        return f"computer_control '{action}' failed: {e}"
