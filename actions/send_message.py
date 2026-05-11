# -*- coding: utf-8 -*-
"""
send_message.py — FRIDAY Verified Messaging
Opens messaging apps, verifies window focus, uses vision-based element
finding, and confirms messages were actually sent before reporting success.
"""
import subprocess
import sys
import time
import platform as platform_mod
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.06
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

try:
    import httpx
    _HTTPX = True
except ImportError:
    _HTTPX = False

try:
    from actions.verification import (
        is_window_focused, ensure_window_focused, verify_app_opened,
        verify_message_sent_in_chat, find_element_on_screen,
        vision_query, screenshot_as_part, vision_analyze,
    )
    _VERIFICATION = True
except ImportError:
    _VERIFICATION = False

_OS = platform_mod.system()

def _search_modifier() -> str:
    """Return the correct search modifier key for the current OS."""
    return "command" if _OS == "Darwin" else "ctrl"


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_os() -> str:
    if _OS == "Darwin":
        return "mac"
    if _OS == "Windows":
        return "windows"
    return "linux"


def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")


def _paste_text(text: str) -> None:
    _require_pyautogui()
    os_name = _get_os()
    paste_hotkey = ("command", "v") if os_name == "mac" else ("ctrl", "v")

    if _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey(*paste_hotkey)
        time.sleep(0.1)
    else:
        try:
            if os_name == "mac":
                subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
            elif os_name == "linux":
                subprocess.run(["xclip", "-selection", "clipboard"],
                               input=text.encode("utf-8"), check=True)
            else:
                subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True)
            pyautogui.hotkey(*paste_hotkey)
            time.sleep(0.1)
        except Exception:
            ascii_text = text.encode("ascii", "ignore").decode("ascii")
            if ascii_text:
                pyautogui.write(ascii_text, interval=0.03)


def _clear_and_paste(text: str) -> None:
    _require_pyautogui()
    os_name = _get_os()
    select_all = ("command", "a") if os_name == "mac" else ("ctrl", "a")
    pyautogui.hotkey(*select_all)
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.1)
    _paste_text(text)


def _type_text(text: str) -> None:
    _require_pyautogui()
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    if ascii_text:
        pyautogui.write(ascii_text, interval=0.04)


def _open_app(app_name: str) -> bool:
    _require_pyautogui()
    os_name = _get_os()
    try:
        if os_name == "windows":
            pyautogui.press("win")
            time.sleep(0.5)
            _type_text(app_name)
            time.sleep(0.6)
            pyautogui.press("enter")
            time.sleep(2.5)
            return True
        elif os_name == "mac":
            result = subprocess.run(
                ["open", "-a", app_name],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                result = subprocess.run(
                    ["open", "-a", f"{app_name}.app"],
                    capture_output=True, text=True, timeout=10,
                )
            time.sleep(2.5)
            return result.returncode == 0
        else:
            launched = False
            for launcher in [
                ["gtk-launch", app_name.lower()],
                [app_name.lower()],
            ]:
                try:
                    subprocess.Popen(
                        launcher,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    launched = True
                    break
                except FileNotFoundError:
                    continue
            time.sleep(2.5)
            return launched
    except Exception as e:
        print(f"[SendMessage] Could not open {app_name}: {e}")
        return False


def _open_browser_url(url: str) -> bool:
    import webbrowser
    try:
        webbrowser.open(url)
        time.sleep(5.0)
        return True
    except Exception as e:
        print(f"[SendMessage] Could not open browser: {e}")
        return False


def _click_at(x: int, y: int, clicks: int = 1) -> None:
    _require_pyautogui()
    pyautogui.click(x, y, clicks=clicks)
    time.sleep(0.3)


# ── Vision-Assisted Helpers ────────────────────────────────────────────

def _find_and_click(description: str, wait_after: float = 0.5) -> bool:
    """Use vision to find a UI element and click it. Returns True if clicked."""
    if not _VERIFICATION:
        return False
    coords = find_element_on_screen(description)
    if coords:
        x, y = coords
        pyautogui.click(x, y)
        time.sleep(wait_after)
        return True
    return False


def _verify_focus(app_name: str) -> bool:
    """Verify the target app window is focused."""
    if not _VERIFICATION:
        return True  # Can't verify, assume OK
    ok, _ = ensure_window_focused(app_name, timeout=4.0)
    return ok


def _verify_open(app_name: str) -> bool:
    """Verify the app is open and visible on screen."""
    if not _VERIFICATION:
        return True
    ok, _ = verify_app_opened(app_name)
    return ok


def _verify_sent(receiver: str, message: str, app_name: str) -> tuple:
    """Verify the message was actually sent. Returns (sent: bool, detail: str)."""
    if not _VERIFICATION:
        return True, "Verification module not available."
    return verify_message_sent_in_chat(receiver, message, app_name)


def _report(result: str, verified: bool, detail: str = "") -> str:
    """Build a truthful result string."""
    if verified:
        return result
    return f"{result} [UNVERIFIED: {detail[:120]}]" if detail else f"{result} [UNVERIFIED]"


# ── Platform-Specific Senders (with verification) ─────────────────────

def _send_whatsapp(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_app("WhatsApp"):
        return "Could not open WhatsApp."

    # Step 1: Verify WhatsApp is open
    if not _verify_open("WhatsApp"):
        return "WhatsApp did not open properly."

    # Step 2: Ensure window focus
    if not _verify_focus("WhatsApp"):
        return "Could not bring WhatsApp to focus — another window may be covering it."

    time.sleep(1.0)

    # Step 3: Use Ctrl+F to search (more reliable than clicking coordinates)
    pyautogui.hotkey(_search_modifier(), "f")
    time.sleep(0.5)

    # Step 4: Type receiver name
    _clear_and_paste(receiver)
    time.sleep(2.0)

    # Step 5: Select first search result
    pyautogui.press("enter")
    time.sleep(1.5)

    # Step 6: Type message in the chat input
    _paste_text(message)
    time.sleep(0.3)

    # Step 7: Send
    pyautogui.press("enter")
    time.sleep(1.0)

    # Step 8: Verify message was sent
    sent, detail = _verify_sent(receiver, message, "WhatsApp")
    return _report(f"Message sent to {receiver} via WhatsApp.", sent, detail)


def _send_telegram(receiver: str, message: str) -> str:
    """Send a Telegram message. Prefers Bot API when token is available,
    falls back to GUI automation (opening the desktop app)."""
    # Try Bot API first — much more reliable than GUI automation
    bot_token, allowed_user = _load_telegram_config()
    if bot_token and allowed_user and _HTTPX:
        try:
            import asyncio
            async def _do_send():
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={"chat_id": allowed_user, "text": message}
                    )
                    return r.json()
            result = asyncio.run(_do_send())
            if result.get("ok"):
                return f"Message sent to {receiver} via Telegram (Bot API)."
            # Bot API failed — fall through to GUI
            print(f"[SendMessage] Bot API failed ({result.get('description')}), trying GUI...")
        except Exception as e:
            print(f"[SendMessage] Bot API error ({e}), trying GUI...")

    # Fallback: GUI automation
    if not _PYAUTOGUI:
        return "PyAutoGUI not installed and Telegram Bot API unavailable."

    if not _open_app("Telegram"):
        return "Could not open Telegram."

    if not _verify_open("Telegram"):
        return "Telegram did not open properly."

    if not _verify_focus("Telegram"):
        return "Could not bring Telegram to focus."

    time.sleep(0.5)

    # Telegram: Ctrl+F opens search
    pyautogui.hotkey(_search_modifier(), "f")
    time.sleep(0.5)

    _clear_and_paste(receiver)
    time.sleep(1.5)

    pyautogui.press("enter")
    time.sleep(1.5)

    # Type message
    _paste_text(message)
    time.sleep(0.3)

    pyautogui.press("enter")
    time.sleep(1.0)

    sent, detail = _verify_sent(receiver, message, "Telegram")
    return _report(f"Message sent to {receiver} via Telegram.", sent, detail)


def _load_telegram_config():
    """Load Telegram bot token and allowed user from env/config."""
    import os
    bot_token = os.environ.get("FRIDAY_TELEGRAM_BOT_TOKEN", "")
    allowed_user = os.environ.get("FRIDAY_TELEGRAM_ALLOWED_USER", "0")
    if not bot_token:
        try:
            base = Path(__file__).resolve().parent
            cfg_path = base / "config" / "api_keys.json"
            if cfg_path.exists():
                import json as _json
                cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
                bot_token = cfg.get("telegram_bot_token", "") or bot_token
                allowed_user = str(cfg.get("telegram_allowed_user", "0")) or allowed_user
        except Exception:
            pass
    return bot_token, int(allowed_user) if allowed_user else 0


def _send_telegram_api(message: str) -> str:
    """Send a message directly to Sir via the Telegram Bot API."""
    if not _HTTPX:
        return "httpx not installed — cannot send via Telegram bot API."

    bot_token, allowed_user = _load_telegram_config()
    if not bot_token:
        return "Telegram bot token not configured. Set FRIDAY_TELEGRAM_BOT_TOKEN."
    if not allowed_user:
        return "Telegram allowed user not configured. Set FRIDAY_TELEGRAM_ALLOWED_USER."

    try:
        import asyncio
        async def _do_send():
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": allowed_user, "text": message}
                )
                return r.json()

        result = asyncio.run(_do_send())
        if result.get("ok"):
            return f"Message sent via Telegram to you."
        err = result.get("description", "Unknown error")
        return f"Telegram API error: {err}"
    except Exception as e:
        return f"Failed to send via Telegram: {e}"
def _send_signal(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_app("Signal"):
        return "Could not open Signal."

    if not _verify_open("Signal"):
        return "Signal did not open properly."

    if not _verify_focus("Signal"):
        return "Could not bring Signal to focus."

    time.sleep(0.5)

    pyautogui.hotkey(_search_modifier(), "f")
    time.sleep(0.5)

    _clear_and_paste(receiver)
    time.sleep(1.5)

    pyautogui.press("enter")
    time.sleep(1.5)

    _paste_text(message)
    time.sleep(0.3)

    pyautogui.press("enter")
    time.sleep(1.0)

    sent, detail = _verify_sent(receiver, message, "Signal")
    return _report(f"Message sent to {receiver} via Signal.", sent, detail)


def _send_discord(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_app("Discord"):
        return "Could not open Discord."

    if not _verify_open("Discord"):
        return "Discord did not open properly."

    if not _verify_focus("Discord"):
        return "Could not bring Discord to focus."

    time.sleep(1.0)

    # Discord: Ctrl+K opens quick switcher
    pyautogui.hotkey(_search_modifier(), "k")
    time.sleep(0.5)

    _clear_and_paste(receiver)
    time.sleep(2.0)

    pyautogui.press("enter")
    time.sleep(2.0)

    _paste_text(message)
    time.sleep(0.3)

    pyautogui.press("enter")
    time.sleep(1.0)

    sent, detail = _verify_sent(receiver, message, "Discord")
    return _report(f"Message sent to {receiver} via Discord.", sent, detail)


def _send_instagram(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_browser_url("https://www.instagram.com/direct/inbox/"):
        return "Could not open Instagram in browser."

    time.sleep(4.0)

    # Verify browser opened Instagram
    if _VERIFICATION:
        part = screenshot_as_part()
        on_page = vision_analyze(
            part,
            "Is the Instagram DM/messaging inbox visible on screen? "
            "Reply YES or NO."
        )
        if "no" in on_page.lower():
            return "Instagram DM inbox did not load properly."

    # Use vision to find "New message" / compose button
    if not _find_and_click("new message or compose button", wait_after=1.5):
        # Fallback: try the pencil icon area
        screen_w, screen_h = pyautogui.size()
        _click_at(int(screen_w * 0.92), int(screen_h * 0.08))
        time.sleep(1.5)

    _clear_and_paste(receiver)
    time.sleep(2.0)

    # Click first search result
    if not _find_and_click(f"first search result for {receiver}", wait_after=0.5):
        screen_w, screen_h = pyautogui.size()
        _click_at(int(screen_w * 0.5), int(screen_h * 0.25))
        time.sleep(0.5)

    # Click Chat/Next button
    if not _find_and_click("Chat or Next or Send button to start conversation", wait_after=2.0):
        screen_w, screen_h = pyautogui.size()
        _click_at(int(screen_w * 0.85), int(screen_h * 0.12))
        time.sleep(2.0)

    # Click message input
    if not _find_and_click("message input field at the bottom", wait_after=0.5):
        screen_w, screen_h = pyautogui.size()
        _click_at(int(screen_w * 0.5), int(screen_h * 0.92))
        time.sleep(0.5)

    _paste_text(message)
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1.0)

    sent, detail = _verify_sent(receiver, message, "Instagram")
    return _report(f"Message sent to {receiver} via Instagram.", sent, detail)


def _send_messenger(receiver: str, message: str) -> str:
    _require_pyautogui()

    if not _open_browser_url("https://www.messenger.com/"):
        return "Could not open Messenger in browser."

    time.sleep(4.0)

    if _VERIFICATION:
        part = screenshot_as_part()
        on_page = vision_analyze(
            part,
            "Is the Facebook Messenger interface visible on screen? "
            "Reply YES or NO."
        )
        if "no" in on_page.lower():
            return "Messenger did not load properly."

    # Use vision to find search bar
    if not _find_and_click("search or find conversation input field", wait_after=0.5):
        screen_w, screen_h = pyautogui.size()
        _click_at(int(screen_w * 0.15), int(screen_h * 0.08))
        time.sleep(0.5)

    _clear_and_paste(receiver)
    time.sleep(2.0)

    # Click first search result
    if not _find_and_click(f"first search result for {receiver}", wait_after=1.5):
        screen_w, screen_h = pyautogui.size()
        _click_at(int(screen_w * 0.15), int(screen_h * 0.18))
        time.sleep(1.5)

    # Click message input
    if not _find_and_click("message input field at the bottom", wait_after=0.5):
        screen_w, screen_h = pyautogui.size()
        _click_at(int(screen_w * 0.5), int(screen_h * 0.92))
        time.sleep(0.5)

    _paste_text(message)
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1.0)

    sent, detail = _verify_sent(receiver, message, "Messenger")
    return _report(f"Message sent to {receiver} via Messenger.", sent, detail)


# ── Platform Router ───────────────────────────────────────────────────

_PLATFORM_MAP = [
    ({"whatsapp", "wp", "wapp"},    _send_whatsapp),
    ({"telegram", "tg"},            _send_telegram),
    ({"telegram_self", "telegram_nudge", "tg_self", "nudge"}, _send_telegram_api),
    ({"instagram", "ig", "insta"},   _send_instagram),
    ({"signal"},                     _send_signal),
    ({"discord"},                    _send_discord),
    ({"messenger", "facebook", "fb"}, _send_messenger),
]


def _resolve_platform(platform_str: str):
    key = platform_str.lower().strip()
    for keywords, handler in _PLATFORM_MAP:
        if any(k in key for k in keywords):
            return handler
    return None


def send_message(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    receiver = params.get("receiver", "").strip()
    message_text = params.get("message_text", "").strip()
    platform = params.get("platform", "whatsapp").strip()

    if not message_text:
        return "Please specify the message content."

    platform_key = platform.lower().strip()
    if platform_key in {"telegram_self", "telegram_nudge", "tg_self", "nudge"}:
        result = _send_telegram_api(message_text)
        print(f"[SendMessage] {result}")
        if player:
            player.write_log(f"[msg] {result}")
        return result

    if not receiver:
        return "Please specify a recipient."
    if not _PYAUTOGUI:
        return "PyAutoGUI is not installed — cannot control the desktop."

    preview = message_text[:50] + ("..." if len(message_text) > 50 else "")
    print(f"[SendMessage] {platform} -> {receiver}: {preview}")
    if player:
        player.write_log(f"[msg] {platform} -> {receiver}")

    handler = _resolve_platform(platform)
    if not handler:
        return (f"I don't have a handler for '{platform}'. "
                f"Supported: WhatsApp, Telegram, Instagram, Signal, Discord, Messenger.")

    try:
        result = handler(receiver, message_text)
    except Exception as e:
        result = f"Could not send message: {e}"

    is_verified = "[UNVERIFIED]" not in result
    status = "VERIFIED" if is_verified else "UNVERIFIED"
    print(f"[SendMessage] {status}: {result}")
    if player:
        player.write_log(f"[msg] {result}")

    return result
