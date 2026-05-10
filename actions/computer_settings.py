import json
import re
import sys
import time
import subprocess
import platform
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

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# [FIX-3] Cached config
_config_cache: dict | None = None
_client_instance = None
GEMINI_MODEL = "gemini-2.5-flash"


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _load_config() -> dict:
    global _config_cache
    if _config_cache is None:
        try:
            path = _get_base_dir() / "config" / "api_keys.json"
            _config_cache = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            _config_cache = {}
    return _config_cache


def _get_api_key() -> str:
    return _load_config().get("gemini_api_key", "")


# [FIX-2] Cached client
def _get_client():
    global _client_instance
    if _client_instance is None:
        from google import genai
        _client_instance = genai.Client(api_key=_get_api_key())
    return _client_instance


def _get_macos_wifi_interface() -> str:
    try:
        result = subprocess.run(
            ["networksetup", "-listallhardwareports"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.splitlines()
        for i, line in enumerate(lines):
            if "Wi-Fi" in line or "AirPort" in line:
                for j in range(i, min(i + 4, len(lines))):
                    if lines[j].startswith("Device:"):
                        return lines[j].split(":", 1)[1].strip()
    except Exception:
        pass
    return "en0"


# [FIX-5] Guard helper
def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("pyautogui not installed. Run: pip install pyautogui")


# ── Volume ───────────────────────────────────────────────────────────────────

def volume_up():
    _require_pyautogui()
    if _OS == "Windows":
        for _ in range(5):
            pyautogui.press("volumeup")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            "set volume output volume (output volume of (get volume settings) + 10)"],
            capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"],
            capture_output=True)


def volume_down():
    _require_pyautogui()
    if _OS == "Windows":
        for _ in range(5):
            pyautogui.press("volumedown")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            "set volume output volume (output volume of (get volume settings) - 10)"],
            capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"],
            capture_output=True)


def volume_mute():
    _require_pyautogui()
    if _OS == "Windows":
        pyautogui.press("volumemute")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", "set volume with output muted"],
            capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
            capture_output=True)


# [FIX-4] Proper Windows fallback for volume_set
def volume_set(value: int):
    value = max(0, min(100, int(value)))
    if _OS == "Windows":
        try:
            import math
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices   = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol       = cast(interface, POINTER(IAudioEndpointVolume))
            vol_db    = -65.25 if value == 0 else max(-65.25, 20 * math.log10(value / 100))
            vol.SetMasterVolumeLevel(vol_db, None)
            return
        except ImportError:
            print("[Settings] pycaw not installed — install with: pip install pycaw comtypes")
        except Exception as e:
            print(f"[Settings] pycaw failed: {e}")

        # Fallback: use nircmd if available, otherwise keypress simulation
        nircmd = _find_exe("nircmd.exe")
        if nircmd:
            subprocess.run([nircmd, "setsysvolume", str(int(value * 655.35))],
                capture_output=True)
            return

        # Last resort: approximate with key presses
        _require_pyautogui()
        pyautogui.press("volumemute")  # unmute first
        pyautogui.press("volumemute")
        steps = value // 2  # rough approximation
        for _ in range(steps):
            pyautogui.press("volumeup")
        return

    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", f"set volume output volume {value}"],
            capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"],
            capture_output=True)


def _find_exe(name: str) -> str | None:
    """Search common locations for an executable."""
    import shutil
    found = shutil.which(name)
    if found:
        return found
    # Check common Windows tool directories
    for d in [
        Path.home() / "Tools",
        Path.home() / "bin",
        Path("C:/Tools"),
        Path("C:/nircmd"),
    ]:
        p = d / name
        if p.exists():
            return str(p)
    return None


# ── Brightness ───────────────────────────────────────────────────────────────

# [FIX-6] Cleaner brightness control
def _get_current_brightness_linux() -> float:
    """Get current brightness via brightnessctl or xrandr."""
    try:
        result = subprocess.run(
            ["brightnessctl", "get"], capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            current = float(result.stdout.strip())
            max_result = subprocess.run(
                ["brightnessctl", "max"], capture_output=True, text=True, timeout=3
            )
            max_val = float(max_result.stdout.strip())
            return current / max_val if max_val > 0 else 0.5
    except (FileNotFoundError, ValueError):
        pass
    return 0.5  # default fallback


def brightness_up():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to key code 144'],
            capture_output=True)
    elif _OS == "Linux":
        if subprocess.run(["which", "brightnessctl"],
                capture_output=True).returncode == 0:
            subprocess.run(["brightnessctl", "set", "+10%"], capture_output=True)
        else:
            # [FIX-6] Simple xrandr fallback without nested subprocess
            try:
                cur = _get_current_brightness_linux()
                new_val = min(1.0, cur + 0.1)
                result = subprocess.run(
                    ["xrandr", "--verbose"], capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    if " connected" in line:
                        output = line.split()[0]
                        subprocess.run(
                            ["xrandr", "--output", output, "--brightness", str(new_val)],
                            capture_output=True
                        )
                        return
            except Exception as e:
                print(f"[Settings] brightness_up xrandr failed: {e}")
    else:
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods)"
                 ".WmiSetBrightness(1, [math]::Min(100, "
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness)"
                 ".CurrentBrightness + 10))"],
                capture_output=True, timeout=5
            )
        except Exception as e:
            print(f"[Settings] Brightness up failed on Windows: {e}")


def brightness_down():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to key code 145'],
            capture_output=True)
    elif _OS == "Linux":
        if subprocess.run(["which", "brightnessctl"],
                capture_output=True).returncode == 0:
            subprocess.run(["brightnessctl", "set", "10%-"], capture_output=True)
        else:
            # [FIX-6] Simple xrandr fallback
            try:
                cur = _get_current_brightness_linux()
                new_val = max(0.1, cur - 0.1)
                result = subprocess.run(
                    ["xrandr", "--verbose"], capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.splitlines():
                    if " connected" in line:
                        output = line.split()[0]
                        subprocess.run(
                            ["xrandr", "--output", output, "--brightness", str(new_val)],
                            capture_output=True
                        )
                        return
            except Exception as e:
                print(f"[Settings] brightness_down xrandr failed: {e}")
    else:
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods)"
                 ".WmiSetBrightness(1, [math]::Max(0, "
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness)"
                 ".CurrentBrightness - 10))"],
                capture_output=True, timeout=5
            )
        except Exception as e:
            print(f"[Settings] Brightness down failed on Windows: {e}")


# ── Window Management ────────────────────────────────────────────────────────

def close_app():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "q")
    else:
        pyautogui.hotkey("alt", "f4")


def close_window():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "w")
    else:
        pyautogui.hotkey("ctrl", "w")


def full_screen():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("ctrl", "command", "f")
    else:
        pyautogui.press("f11")


def minimize_window():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "m")
    else:
        pyautogui.hotkey("win", "down")


def maximize_window():
    _require_pyautogui()
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to keystroke "f" '
            'using {control down, command down}'],
            capture_output=True)
    elif _OS == "Windows":
        pyautogui.hotkey("win", "up")
    else:
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-b",
                "add,maximized_vert,maximized_horz"], capture_output=True)
        except Exception:
            pyautogui.hotkey("super", "up")


# [FIX-8] macOS snap support
def snap_left():
    _require_pyautogui()
    if _OS == "Windows":
        pyautogui.hotkey("win", "left")
    elif _OS == "Darwin":
        # macOS doesn't have native snap, use Rectangle-like approach
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to tell (first process whose frontmost is true) '
            'to set position of front window to {0, 25}'],
            capture_output=True)
    elif _OS == "Linux":
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-e", "0,0,0,960,1080"],
                capture_output=True)
        except Exception:
            pass


def snap_right():
    _require_pyautogui()
    if _OS == "Windows":
        pyautogui.hotkey("win", "right")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to tell (first process whose frontmost is true) '
            'to set position of front window to {960, 25}'],
            capture_output=True)
    elif _OS == "Linux":
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-e", "0,960,0,960,1080"],
                capture_output=True)
        except Exception:
            pass


def switch_window():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "tab")
    else:
        pyautogui.hotkey("alt", "tab")


def show_desktop():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("fn", "f11")
    elif _OS == "Windows":
        pyautogui.hotkey("win", "d")
    else:
        pyautogui.hotkey("super", "d")


def open_task_manager():
    if _OS == "Windows":
        _require_pyautogui()
        pyautogui.hotkey("ctrl", "shift", "esc")
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", "Activity Monitor"])
    else:
        for cmd in [["gnome-system-monitor"], ["xfce4-taskmanager"], ["htop"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return


# ── Browser / Navigation ─────────────────────────────────────────────────────

def focus_search():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "l")
    else:
        pyautogui.hotkey("ctrl", "l")


def pause_video():
    _require_pyautogui()
    pyautogui.press("space")


def refresh_page():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "r")
    else:
        pyautogui.press("f5")


def close_tab():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "w")
    else:
        pyautogui.hotkey("ctrl", "w")


def new_tab():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "t")
    else:
        pyautogui.hotkey("ctrl", "t")


def next_tab():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "shift", "bracketright")
    else:
        pyautogui.hotkey("ctrl", "tab")


def prev_tab():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "shift", "bracketleft")
    else:
        pyautogui.hotkey("ctrl", "shift", "tab")


def go_back():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "left")
    else:
        pyautogui.hotkey("alt", "left")


def go_forward():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "right")
    else:
        pyautogui.hotkey("alt", "right")


def zoom_in():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "equal")
    else:
        pyautogui.hotkey("ctrl", "equal")


def zoom_out():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "minus")
    else:
        pyautogui.hotkey("ctrl", "minus")


def zoom_reset():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "0")
    else:
        pyautogui.hotkey("ctrl", "0")


def find_on_page():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "f")
    else:
        pyautogui.hotkey("ctrl", "f")


def reload_page_n(n: int):
    for _ in range(max(1, min(n, 20))):  # Cap at 20
        refresh_page()
        time.sleep(0.8)


# ── Scrolling ────────────────────────────────────────────────────────────────

def scroll_up(amount: int = 500):
    _require_pyautogui()
    pyautogui.scroll(abs(amount))


def scroll_down(amount: int = 500):
    _require_pyautogui()
    pyautogui.scroll(-abs(amount))


def scroll_top():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "up")
    else:
        pyautogui.hotkey("ctrl", "home")


def scroll_bottom():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "down")
    else:
        pyautogui.hotkey("ctrl", "end")


def page_up():
    _require_pyautogui()
    pyautogui.press("pageup")


def page_down():
    _require_pyautogui()
    pyautogui.press("pagedown")


# ── Clipboard / Editing ──────────────────────────────────────────────────────

def copy():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "c")
    else:
        pyautogui.hotkey("ctrl", "c")


def paste():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "v")
    else:
        pyautogui.hotkey("ctrl", "v")


def cut():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "x")
    else:
        pyautogui.hotkey("ctrl", "x")


def undo():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "z")
    else:
        pyautogui.hotkey("ctrl", "z")


def redo():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "shift", "z")
    else:
        pyautogui.hotkey("ctrl", "y")


def select_all():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "a")
    else:
        pyautogui.hotkey("ctrl", "a")


def save_file():
    _require_pyautogui()
    if _OS == "Darwin":
        pyautogui.hotkey("command", "s")
    else:
        pyautogui.hotkey("ctrl", "s")


def press_enter():
    _require_pyautogui()
    pyautogui.press("enter")


def press_escape():
    _require_pyautogui()
    pyautogui.press("escape")


def press_key(key: str):
    _require_pyautogui()
    if not key:
        return
    pyautogui.press(key)


# [FIX-11] Use pyautogui.screenshot() to actually save the image
def type_text(text: str, press_enter_after: bool = False):
    _require_pyautogui()
    if not text:
        return
    # Always use clipboard for reliability (handles Unicode)
    if _PYPERCLIP:
        pyperclip.copy(str(text))
        time.sleep(0.15)
        paste()
    else:
        pyautogui.write(str(text), interval=0.03)
    if press_enter_after:
        time.sleep(0.1)
        pyautogui.press("enter")


def take_screenshot():
    """Take an actual screenshot and save it to Desktop."""
    _require_pyautogui()
    save_path = Path.home() / "Desktop" / f"screenshot_{int(time.time())}.png"
    img = pyautogui.screenshot()
    img.save(str(save_path))
    print(f"[Settings] Screenshot saved: {save_path}")


def lock_screen():
    if _OS == "Windows":
        _require_pyautogui()
        pyautogui.hotkey("win", "l")
    elif _OS == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"], capture_output=True)
    else:
        for cmd in [
            ["gnome-screensaver-command", "-l"],
            ["xdg-screensaver", "lock"],
            ["loginctl", "lock-session"],
        ]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.run(cmd, capture_output=True)
                return


# [FIX-7] macOS "System Settings" for Ventura+
def open_system_settings():
    if _OS == "Windows":
        _require_pyautogui()
        pyautogui.hotkey("win", "i")
    elif _OS == "Darwin":
        # Try new name first (Ventura+), fall back to old name
        try:
            result = subprocess.run(
                ["open", "-a", "System Settings"],
                capture_output=True, timeout=5
            )
            if result.returncode != 0:
                subprocess.Popen(["open", "-a", "System Preferences"])
        except Exception:
            subprocess.Popen(["open", "-a", "System Preferences"])
    else:
        for cmd in [["gnome-control-center"], ["xfce4-settings-manager"], ["kcmshell5"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return


def open_file_explorer():
    if _OS == "Windows":
        _require_pyautogui()
        pyautogui.hotkey("win", "e")
    elif _OS == "Darwin":
        subprocess.Popen(["open", str(Path.home())])
    else:
        for cmd in [["nautilus"], ["thunar"], ["dolphin"], ["nemo"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return
        subprocess.Popen(["xdg-open", str(Path.home())])


def sleep_display():
    if _OS == "Windows":
        try:
            import ctypes
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        except Exception as e:
            print(f"[Settings] sleep_display failed: {e}")
    elif _OS == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"], capture_output=True)
    else:
        subprocess.run(["xset", "dpms", "force", "off"], capture_output=True)


def open_run():
    if _OS == "Windows":
        _require_pyautogui()
        pyautogui.hotkey("win", "r")


# [FIX-7] Improved dark_mode for Linux (KDE + GNOME)
def dark_mode():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell app "System Events" to tell appearance preferences '
            'to set dark mode to not dark mode'],
            capture_output=True)
    elif _OS == "Windows":
        try:
            import winreg
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            current, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            new_val = 1 - current
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, new_val)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, new_val)
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[Settings] dark_mode registry failed: {e}")
    else:
        # Try GNOME first, then KDE
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                current = result.stdout.strip()
                new_scheme = "'default'" if "dark" in current else "'prefer-dark'"
                subprocess.run(
                    ["gsettings", "set", "org.gnome.desktop.interface",
                     "color-scheme", new_scheme],
                    capture_output=True
                )
                return
        except FileNotFoundError:
            pass

        # KDE Plasma
        try:
            result = subprocess.run(
                ["qdbus", "org.kde.kdeglobals", "/General", "colorScheme"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                current = result.stdout.strip()
                new_theme = "BreezeLight" if "dark" in current.lower() else "BreezeDark"
                subprocess.run(
                    ["qdbus", "org.kde.kdeglobals", "/General",
                     "setColorScheme", new_theme],
                    capture_output=True
                )
                return
        except (FileNotFoundError, Exception):
            pass

        print("[Settings] dark_mode: no supported desktop environment found")


def toggle_wifi():
    if _OS == "Darwin":
        iface = _get_macos_wifi_interface()
        result = subprocess.run(
            ["networksetup", "-getairportpower", iface],
            capture_output=True, text=True
        )
        state = "off" if "On" in result.stdout else "on"
        subprocess.run(["networksetup", "-setairportpower", iface, state],
            capture_output=True)
    elif _OS == "Windows":
        # [FIX-19] Better error handling for admin requirement
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "$adapter = Get-NetAdapter | Where-Object "
                 "{$_.PhysicalMediaType -eq 'Native 802.11'};"
                 "if ($adapter.Status -eq 'Up') "
                 "{ Disable-NetAdapter -Name $adapter.Name -Confirm:$false }"
                 "else { Enable-NetAdapter -Name $adapter.Name -Confirm:$false }"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0 and "Access is denied" in (result.stderr or ""):
                return "WiFi toggle requires administrator privileges. Run as admin."
        except Exception as e:
            print(f"[Settings] toggle_wifi Windows failed: {e}")
    else:
        try:
            result = subprocess.run(["nmcli", "radio", "wifi"],
                capture_output=True, text=True)
            state = "off" if "enabled" in result.stdout else "on"
            subprocess.run(["nmcli", "radio", "wifi", state], capture_output=True)
        except Exception as e:
            print(f"[Settings] toggle_wifi Linux failed: {e}")


def restart_computer():
    if _OS == "Windows":
        subprocess.run(["shutdown", "/r", "/t", "5"], capture_output=True)
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to restart'],
            capture_output=True)
    else:
        subprocess.run(["systemctl", "reboot"], capture_output=True)


def shutdown_computer():
    if _OS == "Windows":
        subprocess.run(["shutdown", "/s", "/t", "5"], capture_output=True)
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to shut down'],
            capture_output=True)
    else:
        subprocess.run(["systemctl", "poweroff"], capture_output=True)


# ── Action Map ───────────────────────────────────────────────────────────────

ACTION_MAP: dict[str, callable] = {
    "volume_up":           volume_up,
    "volume_down":         volume_down,
    "mute":                volume_mute,
    "unmute":              volume_mute,
    "toggle_mute":         volume_mute,
    "brightness_up":       brightness_up,
    "brightness_down":     brightness_down,
    "sleep_display":       sleep_display,
    "screen_off":          sleep_display,
    "pause_video":         pause_video,
    "play_pause":          pause_video,
    "close_app":           close_app,
    "close_window":        close_window,
    "full_screen":         full_screen,
    "fullscreen":          full_screen,
    "minimize":            minimize_window,
    "maximize":            maximize_window,
    "snap_left":           snap_left,
    "snap_right":          snap_right,
    "switch_window":       switch_window,
    "show_desktop":        show_desktop,
    "task_manager":        open_task_manager,
    "focus_search":        focus_search,
    "refresh_page":        refresh_page,
    "reload":              refresh_page,
    "close_tab":           close_tab,
    "new_tab":             new_tab,
    "next_tab":            next_tab,
    "prev_tab":            prev_tab,
    "go_back":             go_back,
    "go_forward":          go_forward,
    "zoom_in":             zoom_in,
    "zoom_out":            zoom_out,
    "zoom_reset":          zoom_reset,
    "find_on_page":        find_on_page,
    "scroll_up":           scroll_up,
    "scroll_down":         scroll_down,
    "scroll_top":          scroll_top,
    "scroll_bottom":       scroll_bottom,
    "page_up":             page_up,
    "page_down":           page_down,
    "copy":                copy,
    "paste":               paste,
    "cut":                 cut,
    "undo":                undo,
    "redo":                redo,
    "select_all":          select_all,
    "save":                save_file,
    "enter":               press_enter,
    "escape":              press_escape,
    "screenshot":          take_screenshot,
    "lock_screen":         lock_screen,
    "open_settings":       open_system_settings,
    "file_explorer":       open_file_explorer,
    "open_run":            open_run,
    "dark_mode":           dark_mode,
    "toggle_wifi":         toggle_wifi,
    "restart":             restart_computer,
    "shutdown":            shutdown_computer,
}

_DANGEROUS_ACTIONS = {"restart", "shutdown"}


# [FIX-1] + [FIX-2] + [FIX-10] Rewritten intent detection
def _detect_action(description: str) -> dict:
    """Use Gemini to detect intent from natural language."""
    from google.genai import types

    available = ", ".join(sorted(ACTION_MAP.keys())) + \
                ", volume_set, type_text, press_key, reload_n"

    prompt = (
        f"You are an intent detector for a computer control assistant.\n\n"
        f'The user issued a command (possibly in any language): "{description}"\n\n'
        f"Available actions: {available}\n\n"
        f"Return ONLY a valid JSON object:\n"
        f'{{"action": "action_name", "value": null_or_value}}\n\n'
        f"Rules:\n"
        f"- Pick the single best matching action from the available list.\n"
        f"- For volume_set: value is an integer 0-100.\n"
        f"- For type_text: value is the exact text to type.\n"
        f"- For press_key: value is the key name (e.g. 'f5', 'tab', 'enter').\n"
        f"- For reload_n: value is an integer (number of times to reload).\n"
        f"- If no clear match, pick the closest action.\n"
        f"- Return ONLY the JSON, no explanation, no markdown."
    )

    try:
        client = _get_client()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        text = (response.text or "").strip()
        # Strip markdown fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
        result = json.loads(text)
        if isinstance(result, dict) and "action" in result:
            return result
    except Exception as e:
        print(f"[Settings] Intent detection failed: {e}")

    # [FIX-10] Fuzzy fallback — try to match partial action names
    desc_lower = description.lower().strip()
    desc_normalized = desc_lower.replace(" ", "_").replace("-", "_")

    # Direct match
    if desc_normalized in ACTION_MAP:
        return {"action": desc_normalized, "value": None}

    # Partial match — find the action that contains the most matching words
    best_action = None
    best_score = 0
    desc_words = set(desc_lower.split())
    for action_name in ACTION_MAP:
        action_words = set(action_name.split("_"))
        overlap = len(desc_words & action_words)
        if overlap > best_score:
            best_score = overlap
            best_action = action_name

    if best_action and best_score > 0:
        return {"action": best_action, "value": None}

    return {"action": desc_normalized, "value": None}


# [FIX-12] Better confirmation UX
def computer_settings(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    if not _PYAUTOGUI:
        return "pyautogui is not installed. Run: pip install pyautogui"

    params      = parameters or {}
    raw_action  = params.get("action", "").strip()
    description = params.get("description", "").strip()
    value       = params.get("value", None)

    if not raw_action and description:
        detected   = _detect_action(description)
        raw_action = detected.get("action", "")
        if value is None:
            value = detected.get("value")

    action = raw_action.lower().strip().replace(" ", "_").replace("-", "_")

    if not action:
        return "No action could be determined."

    print(f"[Settings] Action: {action}  Value: {value}  OS: {_OS}")
    if player:
        player.write_log(f"[Settings] {action}")

    # [FIX-12] Clear confirmation message
    if action in _DANGEROUS_ACTIONS:
        confirmed = str(params.get("confirmed", "")).lower()
        if confirmed not in ("yes", "true", "1", "confirm"):
            return (
                f"This will {action} the computer. "
                f"To confirm, call again with: confirmed=yes"
            )

    if action == "volume_set":
        try:
            volume_set(int(value or 50))
            return f"Volume set to {value}%."
        except Exception as e:
            return f"Could not set volume: {e}"

    if action in ("type_text", "write_on_screen", "type", "write"):
        text = str(value or params.get("text", "")).strip()
        if not text:
            return "No text provided to type."
        enter_after = str(params.get("press_enter", "false")).lower() in ("true", "1", "yes")
        type_text(text, press_enter_after=enter_after)
        return f"Typed: {text[:80]}"

    if action == "press_key":
        key = str(value or params.get("key", "")).strip()
        if not key:
            return "No key specified."
        press_key(key)
        return f"Pressed: {key}"

    if action in ("reload_n", "refresh_n", "reload_page_n"):
        try:
            n = max(1, min(int(value or 1), 20))
            reload_page_n(n)
            return f"Reloaded {n} time(s)."
        except Exception as e:
            return f"Reload failed: {e}"

    if action == "scroll_up":
        scroll_up(int(value or 500))
        return "Scrolled up."

    if action == "scroll_down":
        scroll_down(int(value or 500))
        return "Scrolled down."

    func = ACTION_MAP.get(action)
    if not func:
        return f"Unknown action: '{raw_action}'."

    try:
        func()
        return f"Done: {action}."
    except Exception as e:
        print(f"[Settings] Action failed ({action}): {e}")
        return f"Action failed ({action}): {e}"
