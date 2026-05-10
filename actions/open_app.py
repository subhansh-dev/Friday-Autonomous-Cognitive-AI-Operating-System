import time
import subprocess
import platform
import shutil
import re

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_SYSTEM = platform.system()

_APP_ALIASES: dict[str, dict[str, str]] = {
    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "msedge",                  "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "msedge",                  "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "whatsapp-for-linux"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram-desktop"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skypeforlinux"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal-desktop"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "gnome-terminal"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",            "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Settings",      "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    "instagram":          {"Windows": "Instagram",               "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Settings",      "Linux": "gnome-control-center"},
}

# URL patterns that should be opened in a browser, not as apps
_URL_PATTERN = re.compile(
    r"^(https?://|www\.|[a-zA-Z0-9-]+\.(com|org|net|io|dev|co|tr|de|uk|fr)(/|$))",
    re.IGNORECASE
)


def _is_url(text: str) -> bool:
    return bool(_URL_PATTERN.match(text.strip()))


# [FIX-5] Exact match first, then partial — with word boundary check
def _normalize(raw: str) -> str:
    key = raw.lower().strip()

    # Exact match
    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)

    # [FIX-5] Partial match — require word boundary, not substring
    key_words = set(key.split())
    best_match = None
    best_score = 0
    for alias_key, os_map in _APP_ALIASES.items():
        alias_words = set(alias_key.split())
        # Count overlapping words
        overlap = len(key_words & alias_words)
        if overlap > best_score:
            best_score = overlap
            best_match = os_map.get(_SYSTEM, raw)

    if best_match and best_score > 0:
        return best_match

    return raw


# [FIX-8] URL opening helper
def _open_url(url: str) -> bool:
    """Open a URL in the default browser."""
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        if _SYSTEM == "Windows":
            subprocess.Popen(["cmd", "/c", "start", url], shell=False)
        elif _SYSTEM == "Darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
        time.sleep(1.0)
        return True
    except Exception as e:
        print(f"[open_app] URL open failed: {e}")
        return False


# [FIX-1] + [FIX-2] Proper handling of URI protocols + no shell injection
def _launch_windows(app_name: str) -> bool:
    # [FIX-1] Handle URI protocols (ms-settings:, ms-store:, etc.)
    if ":" in app_name and not app_name.endswith(".exe"):
        try:
            subprocess.Popen(["cmd", "/c", "start", "", app_name], shell=False)
            time.sleep(1.0)
            return True
        except Exception as e:
            print(f"[open_app] URI launch failed: {e}")

    # Try as executable / command
    exe_name = app_name.split()[0]  # Handle "libreoffice --writer"
    if shutil.which(exe_name) or shutil.which(exe_name.split(".")[0]):
        try:
            # [FIX-2] Use list, not shell=True
            parts = app_name.split()
            subprocess.Popen(
                parts,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
            time.sleep(1.0)
            return True
        except Exception as e:
            print(f"[open_app] subprocess failed: {e}")

    # Try as Windows Store app (UWP) — these are found by Start Menu search
    try:
        import pyautogui
        pyautogui.PAUSE = 0.1
        pyautogui.press("win")
        time.sleep(0.5)
        # [FIX-3] Use clipboard for non-ASCII support
        _type_text_safe(app_name)
        time.sleep(0.7)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] Start Menu search failed: {e}")

    return False


def _launch_macos(app_name: str) -> bool:
    # Try open -a
    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    # Try with .app suffix
    try:
        result = subprocess.run(
            ["open", "-a", f"{app_name}.app"],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    # Try as binary
    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    # [FIX-6] Spotlight fallback — clear any existing query first
    try:
        import pyautogui
        pyautogui.hotkey("command", "space")
        time.sleep(0.5)
        # Clear any existing Spotlight query
        pyautogui.hotkey("command", "a")
        time.sleep(0.1)
        _type_text_safe(app_name)
        time.sleep(0.6)
        pyautogui.press("enter")
        time.sleep(1.0)
        return True
    except Exception as e:
        print(f"[open_app] Spotlight failed: {e}")

    return False


# [FIX-9] Better Linux desktop environment support
def _launch_linux(app_name: str) -> bool:
    # Try as binary
    binary = (
        shutil.which(app_name) or
        shutil.which(app_name.lower()) or
        shutil.which(app_name.lower().replace(" ", "-")) or
        shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    # Try .desktop file launch via various methods
    desktop_names = [
        app_name.lower(),
        app_name.lower().replace(" ", "-"),
        app_name.lower().replace(" ", ""),
        app_name.lower() + ".desktop",
    ]

    # [FIX-9] Try gtk-launch (GNOME/GTK), kde-open (KDE), then generic
    for launcher_cmd in ["gtk-launch", "gio launch"]:
        launcher = launcher_cmd.split()[0]
        if not shutil.which(launcher):
            continue
        for desktop_name in desktop_names:
            try:
                cmd = launcher_cmd.split() + [desktop_name]
                result = subprocess.run(cmd, capture_output=True, timeout=5)
                if result.returncode == 0:
                    return True
            except Exception:
                continue

    # Try to find and launch .desktop file directly
    desktop_dirs = [
        Path.home() / ".local" / "share" / "applications",
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
    ]
    from pathlib import Path
    for ddir in desktop_dirs:
        if not ddir.exists():
            continue
        for desktop_name in desktop_names:
            for dfile in ddir.glob(f"*{desktop_name}*"):
                if dfile.suffix == ".desktop":
                    try:
                        # Extract Exec= line from .desktop file
                        content = dfile.read_text(encoding="utf-8", errors="ignore")
                        for line in content.splitlines():
                            if line.startswith("Exec="):
                                exec_cmd = line.split("=", 1)[1].strip()
                                # Remove field codes (%f, %u, etc.)
                                exec_cmd = re.sub(r"%[fFuUdDnNickvm]", "", exec_cmd).strip()
                                subprocess.Popen(
                                    exec_cmd.split(),
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                )
                                time.sleep(1.0)
                                return True
                    except Exception:
                        continue

    return False


# [FIX-3] Unicode-safe typing via clipboard
def _type_text_safe(text: str) -> None:
    """Type text using clipboard for Unicode support."""
    try:
        import pyperclip
        pyperclip.copy(text)
        time.sleep(0.05)
        import pyautogui
        if _SYSTEM == "Darwin":
            pyautogui.hotkey("command", "v")
        else:
            pyautogui.hotkey("ctrl", "v")
    except ImportError:
        # Fallback: strip non-ASCII
        import pyautogui
        ascii_text = text.encode("ascii", "ignore").decode("ascii")
        if ascii_text:
            pyautogui.write(ascii_text, interval=0.05)


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin":  _launch_macos,
    "Linux":   _launch_linux,
}


def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    app_name = (parameters or {}).get("app_name", "").strip()

    if not app_name:
        return "No application name provided."

    # [FIX-8] Handle URLs
    if _is_url(app_name):
        if _open_url(app_name):
            return f"Opened {app_name} in browser."
        return f"Could not open URL: {app_name}"

    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if launcher is None:
        return f"Unsupported operating system: {_SYSTEM}"

    normalized = _normalize(app_name)
    print(f"[open_app] Launching: '{app_name}' → '{normalized}' ({_SYSTEM})")

    if player:
        player.write_log(f"[open_app] {app_name}")

    try:
        # Try normalized name first
        if launcher(normalized):
            return f"Opened {app_name}."

        # [FIX-5] Try original name as fallback (only if different)
        if normalized.lower() != app_name.lower():
            if launcher(app_name):
                return f"Opened {app_name}."

        return (
            f"Could not confirm that {app_name} launched. "
            f"It may still be loading, or it might not be installed."
        )
    except Exception as e:
        print(f"[open_app] Error: {e}")
        return f"Failed to open {app_name}: {e}"
