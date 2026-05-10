# -*- coding: utf-8 -*-
"""
verification.py — FRIDAY Action Verification Layer
Captures screenshots, verifies window focus, and uses Gemini Vision
to confirm actions actually succeeded before reporting success.
"""
import io
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pygetwindow as gw
    _PYGETWINDOW = True
except ImportError:
    _PYGETWINDOW = False

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import PIL.Image
    _PIL = True
except ImportError:
    _PIL = False

_VISION_MODEL = "gemini-2.5-flash"
_client_cache = None
_config_cache = None


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _load_config() -> dict:
    global _config_cache
    if _config_cache is None:
        try:
            cfg_path = _base_dir() / "config" / "api_keys.json"
            _config_cache = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            _config_cache = {}
    return _config_cache


def _get_client():
    global _client_cache
    if _client_cache is None:
        from google import genai
        api_key = _load_config().get("gemini_api_key", "")
        if not api_key:
            raise RuntimeError("gemini_api_key not found in config.")
        _client_cache = genai.Client(api_key=api_key)
    return _client_cache


# ── Screenshot Capture ─────────────────────────────────────────────────

def capture_screenshot(compress: bool = True) -> bytes:
    """Capture full screen, return PNG bytes (compressed to JPEG if compress=True)."""
    if not _MSS:
        raise RuntimeError("mss not installed.")

    with mss.mss() as sct:
        monitors = sct.monitors
        monitor_idx = _load_config().get("screen_monitor", 1)
        if monitor_idx >= len(monitors):
            monitor_idx = 1 if len(monitors) > 1 else 0
        target = monitors[monitor_idx]
        shot = sct.grab(target)
        png = mss.tools.to_png(shot.rgb, shot.size)

    if not compress or not _PIL:
        return png

    try:
        img = PIL.Image.open(io.BytesIO(png)).convert("RGB")
        img.thumbnail((800, 450), PIL.Image.Resampling.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=65)
        return buf.getvalue()
    except Exception:
        return png


def screenshot_as_part(compress: bool = True):
    """Return a Gemini Part object ready for vision API."""
    from google.genai import types
    img_bytes = capture_screenshot(compress=compress)
    mime = "image/jpeg" if compress and _PIL else "image/png"
    return types.Part.from_bytes(data=img_bytes, mime_type=mime)


# ── Window Focus Management ───────────────────────────────────────────

def get_active_window_title() -> str:
    """Get the title of the currently focused window."""
    if not _PYGETWINDOW:
        return ""
    try:
        active = gw.getActiveWindow()
        return active.title if active else ""
    except Exception:
        return ""


def is_window_focused(title_fragment: str) -> bool:
    """Check if a window matching title_fragment is currently focused."""
    active = get_active_window_title()
    return title_fragment.lower() in active.lower()


def focus_window(title_fragment: str, timeout: float = 3.0) -> bool:
    """Focus a window matching title_fragment. Returns True if focused."""
    if not _PYGETWINDOW:
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            windows = gw.getWindowsWithTitle(title_fragment)
            if windows:
                win = windows[0]
                if win.isMinimized:
                    win.restore()
                win.activate()
                time.sleep(0.3)
                # Verify it actually focused
                if is_window_focused(title_fragment):
                    return True
        except Exception:
            pass
        time.sleep(0.3)

    return False


def ensure_window_focused(title_fragment: str, timeout: float = 5.0) -> Tuple[bool, str]:
    """Try to focus a window, return (success, message)."""
    if is_window_focused(title_fragment):
        return True, f"'{title_fragment}' is already focused."

    focused = focus_window(title_fragment, timeout=timeout)
    if focused:
        return True, f"Focused '{title_fragment}'."
    return False, f"Could not focus '{title_fragment}'."


# ── Gemini Vision Analysis ────────────────────────────────────────────

def vision_analyze(screenshot_part, prompt: str, model: str = None) -> str:
    """Send screenshot + prompt to Gemini Vision, return text response."""
    model = model or _VISION_MODEL
    client = _get_client()

    response = client.models.generate_content(
        model=model,
        contents=[
            screenshot_part,
            prompt,
        ],
    )
    return (response.text or "").strip()


def vision_query(prompt: str, compress: bool = True) -> str:
    """Capture screenshot and analyze it in one call."""
    part = screenshot_as_part(compress=compress)
    return vision_analyze(part, prompt)


# ── High-Level Verification Functions ─────────────────────────────────

def verify_screen_contains(text: str, screenshot_part=None) -> bool:
    """Check if specific text is visible on screen."""
    part = screenshot_part or screenshot_as_part()
    result = vision_analyze(
        part,
        f"Is the text '{text}' visible anywhere on this screen? "
        f"Reply with ONLY 'YES' or 'NO'."
    )
    return "yes" in result.lower()


def verify_app_opened(app_name: str) -> Tuple[bool, str]:
    """Verify that the target application is open and visible on screen."""
    part = screenshot_as_part()
    result = vision_analyze(
        part,
        f"Look at this screenshot. Is the {app_name} application open and visible? "
        f"It should be the main window or a significant portion of the screen. "
        f"Reply with ONLY 'YES' or 'NO' followed by a brief description of what you see."
    )
    is_open = result.lower().startswith("yes")
    return is_open, result


def verify_message_sent_in_chat(contact_name: str, message_text: str, app_name: str) -> Tuple[bool, str]:
    """Verify that a message appears in the chat after sending."""
    part = screenshot_as_part()
    # Truncate message for the check
    msg_preview = message_text[:80]
    result = vision_analyze(
        part,
        f"Look at this screenshot of {app_name}. "
        f"I just tried to send a message to '{contact_name}'. "
        f"The message should say: '{msg_preview}'\n\n"
        f"Can you see this message in the chat? Is it actually sent (not just typed in the input box)? "
        f"Reply with: SENT / NOT_SENT / UNCLEAR followed by what you actually see."
    )
    is_sent = "sent" in result.lower() and "not_sent" not in result.lower()
    return is_sent, result


def find_element_on_screen(description: str, screenshot_part=None) -> Optional[Tuple[int, int]]:
    """Use Gemini Vision to find a UI element and return its coordinates."""
    if not _PYAUTOGUI:
        return None

    part = screenshot_part or screenshot_as_part()
    w, h = pyautogui.size()

    result = vision_analyze(
        part,
        f"This is a screenshot of a {w}x{h} pixel screen. "
        f"Locate the UI element described as: '{description}'. "
        f"Reply with ONLY the center coordinates as: x,y "
        f"If the element is not visible, reply: NOT_FOUND"
    )

    if "not_found" in result.lower():
        return None

    match = re.search(r"(\d+)\s*,\s*(\d+)", result)
    if match:
        x, y = int(match.group(1)), int(match.group(2))
        if 0 <= x <= w and 0 <= y <= h:
            return x, y

    return None


def click_element(description: str, screenshot_part=None) -> Tuple[bool, str]:
    """Find and click a UI element by description. Returns (success, message)."""
    coords = find_element_on_screen(description, screenshot_part)
    if coords is None:
        return False, f"Could not find '{description}' on screen."

    x, y = coords
    pyautogui.click(x, y)
    time.sleep(0.3)
    return True, f"Clicked '{description}' at ({x}, {y})."


def type_in_focused_window(text: str) -> bool:
    """Type text into whatever window is currently focused."""
    if not _PYAUTOGUI:
        return False
    try:
        import pyperclip
        pyperclip.copy(text)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)
        return True
    except Exception:
        try:
            pyautogui.write(text, interval=0.03)
            return True
        except Exception:
            return False


# ── Action Wrapper with Verification ──────────────────────────────────

class ActionVerifier:
    """
    Wraps an action with pre/post verification.
    Usage:
        verifier = ActionVerifier("WhatsApp", "John")
        verifier.pre_check()  # Verify app is open
        # ... perform action ...
        verifier.post_check("Message sent successfully")
    """

    def __init__(self, app_name: str, target: str = "", player=None):
        self.app_name = app_name
        self.target = target
        self.player = player
        self.steps: list = []
        self.verified = True

    def log(self, msg: str):
        self.steps.append(msg)
        print(f"[Verify] {msg}")
        if self.player:
            try:
                self.player.write_log(f"[verify] {msg}")
            except Exception:
                pass

    def check_window(self) -> bool:
        """Verify the target app window is focused."""
        ok, msg = ensure_window_focused(self.app_name)
        self.log(f"Window check: {msg}")
        if not ok:
            self.verified = False
        return ok

    def check_app_open(self) -> bool:
        """Verify the app is actually open and visible."""
        ok, msg = verify_app_opened(self.app_name)
        self.log(f"App open check: {'OK' if ok else 'FAIL'} — {msg[:100]}")
        if not ok:
            self.verified = False
        return ok

    def check_message_sent(self) -> bool:
        """Verify a message was actually sent in the chat."""
        ok, msg = verify_message_sent_in_chat(
            self.target, "", self.app_name)
        self.log(f"Message check: {'SENT' if ok else 'NOT SENT'} — {msg[:100]}")
        if not ok:
            self.verified = False
        return ok

    def get_result(self, success_msg: str, fail_msg: str) -> str:
        """Return truthful result based on verification state."""
        if self.verified:
            self.log(f"VERIFIED: {success_msg}")
            return success_msg
        else:
            failures = [s for s in self.steps if "FAIL" in s or "NOT SENT" in s]
            detail = "; ".join(failures[:3]) if failures else "Unknown failure"
            self.log(f"FAILED: {fail_msg} — {detail}")
            return f"{fail_msg} ({detail})"
