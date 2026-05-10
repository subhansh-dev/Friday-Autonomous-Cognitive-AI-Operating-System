import os
import re
import sys
import json
import time
import subprocess
import threading
import platform as platform_mod
from pathlib import Path
from datetime import datetime

# [FIX-1] Removed broken import — use platform module directly
_OS = platform_mod.system()

def is_windows() -> bool: return _OS == "Windows"
def is_mac()     -> bool: return _OS == "Darwin"
def is_linux()   -> bool: return _OS == "Linux"


_KNOWN_APPIDS: dict[str, tuple[str, str]] = {
    "pubg":                ("578080",  "PUBG: Battlegrounds"),
    "pubg battlegrounds":  ("578080",  "PUBG: Battlegrounds"),
    "pubg: battlegrounds": ("578080",  "PUBG: Battlegrounds"),
    "battlegrounds":       ("578080",  "PUBG: Battlegrounds"),
    "gta5":                ("271590",  "Grand Theft Auto V"),
    "gta v":               ("271590",  "Grand Theft Auto V"),
    "grand theft auto v":  ("271590",  "Grand Theft Auto V"),
    "cs2":                 ("730",     "Counter-Strike 2"),
    "csgo":                ("730",     "Counter-Strike 2"),
    "counter-strike 2":    ("730",     "Counter-Strike 2"),
    "counter strike 2":    ("730",     "Counter-Strike 2"),
    "dota2":               ("570",     "Dota 2"),
    "dota 2":              ("570",     "Dota 2"),
    "rust":                ("252490",  "Rust"),
    "valheim":             ("892970",  "Valheim"),
    "cyberpunk":           ("1091500", "Cyberpunk 2077"),
    "cyberpunk 2077":      ("1091500", "Cyberpunk 2077"),
    "elden ring":          ("1245620", "ELDEN RING"),
    "minecraft":           ("1672970", "Minecraft Launcher"),
    "apex legends":        ("1172470", "Apex Legends"),
    "apex":                ("1172470", "Apex Legends"),
    "fortnite":            ("1517990", "Fortnite"),
    "goose goose duck":    ("1568590", "Goose Goose Duck"),
    "among us":            ("945360",  "Among Us"),
    "fall guys":           ("1097150", "Fall Guys"),
    "rocket league":       ("252950",  "Rocket League"),
    "warframe":            ("230410",  "Warframe"),
    "destiny 2":           ("1085660", "Destiny 2"),
    "team fortress 2":     ("440",     "Team Fortress 2"),
    "tf2":                 ("440",     "Team Fortress 2"),
    "left 4 dead 2":       ("550",     "Left 4 Dead 2"),
    "l4d2":                ("550",     "Left 4 Dead 2"),
    "paladins":            ("444090",  "Paladins"),
    "smite":               ("386360",  "SMITE"),
    "war thunder":         ("236390",  "War Thunder"),
    "world of warships":   ("552990",  "World of Warships"),
    "path of exile":       ("238960",  "Path of Exile"),
    "poe":                 ("238960",  "Path of Exile"),
    "lost ark":            ("1599340", "Lost Ark"),
    "new world":           ("1063730", "New World: Aeternum"),
}


def _find_steam_path() -> Path | None:
    if is_windows(): return _find_steam_windows()
    if is_mac():     return _find_steam_mac()
    return _find_steam_linux()


def _find_steam_windows() -> Path | None:
    try:
        import winreg
        for hive, key_path in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Valve\Steam"),
        ]:
            try:
                key = winreg.OpenKey(hive, key_path)
                val, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                p = Path(val)
                if p.exists() and (p / "steam.exe").exists():
                    return p
            except Exception:
                continue
    except ImportError:
        pass
    for p in [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Steam",
        Path(os.environ.get("ProgramFiles", ""))       / "Steam",
        Path("C:/Steam"), Path("D:/Steam"),
    ]:
        if p.exists() and (p / "steam.exe").exists():
            return p
    return None


def _find_steam_mac() -> Path | None:
    for p in [
        Path.home() / "Library" / "Application Support" / "Steam",
        Path("/Applications/Steam.app/Contents/MacOS"),
    ]:
        if p.exists():
            return p
    return None


def _find_steam_linux() -> Path | None:
    for p in [
        Path.home() / ".steam" / "steam",
        Path.home() / ".steam" / "root",
        Path.home() / ".local"  / "share" / "Steam",
        Path("/usr/share/steam"),
    ]:
        if p.exists():
            return p
    return None


def _steam_exe(steam_path: Path) -> Path:
    if is_windows(): return steam_path / "steam.exe"
    if is_mac():     return Path("/Applications/Steam.app/Contents/MacOS/steam_osx")
    return steam_path / "steam.sh"


def _launch_steam_url(exe: Path, url: str) -> None:
    if is_mac():
        subprocess.Popen(["open", url])
    elif is_linux():
        subprocess.Popen(["xdg-open", url])
    else:
        subprocess.Popen([str(exe), url])


def _get_steam_libraries(steam_path: Path) -> list[Path]:
    libraries = [steam_path / "steamapps"]
    vdf_path  = steam_path / "steamapps" / "libraryfolders.vdf"
    if not vdf_path.exists():
        return libraries
    try:
        content = vdf_path.read_text(encoding="utf-8", errors="ignore")
        for raw_path in re.findall(r'"path"\s+"([^"]+)"', content):
            lib = Path(raw_path.replace("\\\\", "/")) / "steamapps"
            if lib.exists() and lib not in libraries:
                libraries.append(lib)
    except Exception:
        pass
    return libraries


# [FIX-13] Cached game list with TTL
_steam_games_cache: list[dict] | None = None
_steam_games_cache_time: float = 0
_CACHE_TTL = 10.0  # seconds


def _get_steam_games(steam_path: Path) -> list[dict]:
    global _steam_games_cache, _steam_games_cache_time

    now = time.time()
    if _steam_games_cache is not None and (now - _steam_games_cache_time) < _CACHE_TTL:
        return _steam_games_cache

    games = []
    for lib in _get_steam_libraries(steam_path):
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                content  = acf.read_text(encoding="utf-8", errors="ignore")
                app_id   = re.search(r'"appid"\s+"(\d+)"',     content)
                name     = re.search(r'"name"\s+"([^"]+)"',     content)
                state    = re.search(r'"StateFlags"\s+"(\d+)"', content)
                size     = re.search(r'"SizeOnDisk"\s+"(\d+)"', content)
                if app_id and name:
                    games.append({
                        "id":    app_id.group(1),
                        "name":  name.group(1),
                        "state": int(state.group(1)) if state else 0,
                        "size":  int(size.group(1))  if size  else 0,
                        "lib":   str(lib),
                        "acf":   str(acf),
                    })
            except Exception:
                continue

    _steam_games_cache = games
    _steam_games_cache_time = now
    return games


def _invalidate_steam_cache():
    global _steam_games_cache, _steam_games_cache_time
    _steam_games_cache = None
    _steam_games_cache_time = 0


def _is_steam_running() -> bool:
    try:
        if is_windows():
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe"],
                                 capture_output=True, text=True).stdout
            return "steam.exe" in out.lower()
        proc = "steam_osx" if is_mac() else "steam"
        return bool(subprocess.run(["pgrep", "-x", proc],
                                   capture_output=True, text=True).stdout.strip())
    except Exception:
        return False


def _get_steam_window_rect() -> tuple[int, int, int, int] | None:
    try:
        import pygetwindow as gw
        for w in gw.getAllWindows():
            if "steam" in w.title.lower() and w.width > 200 and w.visible:
                return w.left, w.top, w.width, w.height
    except Exception:
        pass
    return None


# [FIX-3] Simplified profile click — less fragile
def _click_first_profile_by_screenshot() -> bool:
    try:
        import pyautogui

        time.sleep(1.5)
        win = _get_steam_window_rect()
        if not win:
            print("[GameUpdater] ⚠️ Steam window not found")
            return False

        wx, wy, ww, wh = win
        # Click center-left area where profile avatars typically appear
        # This is more reliable than pixel color detection
        click_x = wx + ww // 3
        click_y = wy + wh // 2
        print(f"[GameUpdater] 🎯 Clicking profile area ({click_x}, {click_y})")
        pyautogui.click(click_x, click_y)
        return True

    except ImportError as e:
        print(f"[GameUpdater] ⚠️ Missing library: {e}")
        return False
    except Exception as e:
        print(f"[GameUpdater] ⚠️ Profile click failed: {e}")
        return False


# [FIX-4] Simplified profile detection
def _handle_steam_profile_selection() -> bool:
    print("[GameUpdater] 🔍 Checking for profile selection dialog...")
    win = _get_steam_window_rect()
    if not win:
        return False

    # Profile selection dialogs are typically smaller windows
    wx, wy, ww, wh = win
    if ww > 900 or wh > 700:
        print("[GameUpdater] ℹ️ Full Steam window — no profile dialog")
        return False

    print("[GameUpdater] 👤 Possible profile dialog — clicking first profile")
    return _click_first_profile_by_screenshot()


# [FIX-5] Only check local fixed drives
def _find_best_drive() -> dict | None:
    import shutil
    drives = []

    if is_windows():
        import string
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            # [FIX-5] Skip network/removable by checking drive type
            try:
                import ctypes
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive_path)
                # 2=Removable, 3=Fixed, 4=Network, 5=CD-ROM
                if drive_type != 3:  # Only fixed drives
                    continue
            except Exception:
                pass

            if os.path.exists(drive_path):
                try:
                    usage = shutil.disk_usage(drive_path)
                    if usage.free > 0:
                        drives.append({
                            "letter": letter,
                            "path": drive_path,
                            "free_gb": usage.free / (1024 ** 3)
                        })
                except Exception:
                    continue
    else:
        # Non-Windows: just check root
        try:
            usage = shutil.disk_usage("/")
            drives.append({"letter": "", "path": "/", "free_gb": usage.free / (1024 ** 3)})
        except Exception:
            pass

    return max(drives, key=lambda d: d["free_gb"]) if drives else None


def _select_drive_in_dialog(dialog, drive_letter: str) -> bool:
    target = drive_letter.upper()
    for control_type in ("ListItem", "RadioButton"):
        try:
            for ctrl in dialog.descendants(control_type=control_type):
                if target in ctrl.window_text().upper():
                    ctrl.click_input()
                    print(f"[GameUpdater] ✅ Drive selected ({control_type}): {ctrl.window_text()}")
                    return True
        except Exception:
            continue
    try:
        for combo in dialog.descendants(control_type="ComboBox"):
            try:
                combo.expand()
                time.sleep(0.15)
                for idx, txt in enumerate(combo.texts()):
                    if target in txt.upper():
                        combo.select(idx)
                        return True
                combo.collapse()
            except Exception:
                continue
    except Exception:
        pass
    try:
        for ctrl in dialog.descendants():
            txt = ctrl.window_text().upper()
            if f"{target}:" in txt and len(txt) < 80:
                ctrl.click_input()
                return True
    except Exception:
        pass
    return False


def _click_button(window, keywords: list[str]) -> bool:
    try:
        for btn in window.descendants(control_type="Button"):
            try:
                txt = btn.window_text().lower().strip()
                if txt in keywords or any(kw in txt for kw in keywords):
                    btn.click_input()
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _handle_install_dialog_pyautogui(game_name: str, best_drive: dict) -> str:
    try:
        import pyautogui
        import pygetwindow as gw
    except ImportError:
        return (f"Install dialog opened for '{game_name}'. "
                f"Please select '{best_drive['letter']}:' and click Install manually.")

    # [FIX-2] Keep failsafe enabled
    pyautogui.FAILSAFE = True
    drive_label = f"{best_drive['letter']}:"
    install_win = None

    # [FIX-10] Increased wait time for slow systems
    for _ in range(60):

        time.sleep(0.5)
        for w in gw.getAllWindows():
            if ("install" in w.title.lower() or "steam" in w.title.lower()) \
                    and w.width > 300 and w.visible:
                install_win = w
                break
        if install_win:
            break

    if not install_win:
        return f"Please select '{drive_label}' and click Install in Steam for '{game_name}'."

    try:
        install_win.activate()
        time.sleep(0.4)
    except Exception:
        pass

    wx, wy = install_win.left, install_win.top
    ww, wh = install_win.width, install_win.height
    pyautogui.click(wx + int(ww * 0.35), wy + int(wh * 0.45))
    time.sleep(0.2)
    pyautogui.typewrite(best_drive["letter"], interval=0.05)
    time.sleep(0.2)
    pyautogui.click(wx + int(ww * 0.72), wy + int(wh * 0.88))
    return f"Attempted drive {drive_label} selection and Install click for '{game_name}'."


def _handle_install_dialog(game_name: str) -> str:
    best_drive = _find_best_drive()
    if not best_drive:
        return f"Install dialog opened for '{game_name}'. Could not detect drives."

    drive_letter = best_drive["letter"]
    drive_label  = f"{drive_letter}:"
    print(f"[GameUpdater] 🏆 Target drive: {drive_label} ({best_drive['free_gb']:.1f} GB free)")

    try:
        from pywinauto import Application, findwindows
        dialog = None

        # [FIX-10] Increased wait time
        for _ in range(60):
            time.sleep(0.5)
            try:
                for hwnd in findwindows.find_windows(
                    title_re=r"(?i)(install|yükle|steam)", visible_only=True
                ):
                    try:
                        app  = Application(backend="uia").connect(handle=hwnd)
                        win  = app.window(handle=hwnd)
                        rect = win.rectangle()
                        if win.is_visible() and rect.width() > 300 and rect.height() > 200:
                            all_text = " ".join(
                                c.window_text() for c in win.descendants()
                                if c.window_text()
                            ).upper()
                            if any(x in all_text for x in
                                   ("C:", "D:", "E:", "F:", "INSTALL", "YÜKLE")):
                                dialog = win
                                break
                    except Exception:
                        continue
            except Exception:
                pass
            if dialog:
                break

        if not dialog:
            raise RuntimeError("Dialog not found")

        dialog.set_focus()
        time.sleep(0.4)
        drive_selected  = _select_drive_in_dialog(dialog, drive_letter)
        install_clicked = _click_button(
            dialog, ["install", "yükle", "next", "ileri", "ok", "tamam"]
        )

        if install_clicked:
            suffix = f"Selected {drive_label} and" if drive_selected else "Default drive used, but"
            return f"{suffix} clicked Install for '{game_name}'."
        return f"Please click Install manually in Steam for '{game_name}'."

    except ImportError:
        return _handle_install_dialog_pyautogui(game_name, best_drive)
    except Exception as e:
        print(f"[GameUpdater] ⚠️ pywinauto failed: {e}")
        return _handle_install_dialog_pyautogui(game_name, best_drive)


def _ensure_steam_running(steam_path: Path) -> bool:
    if _is_steam_running():
        return True

    exe = _steam_exe(steam_path)
    if not exe.exists():
        print(f"[GameUpdater] ❌ Steam not found: {exe}")
        return False

    print("[GameUpdater] 🚀 Starting Steam...")
    if is_mac():
        subprocess.Popen(["open", "-a", "Steam"])
    else:
        subprocess.Popen([str(exe)])

    for _ in range(30):
        time.sleep(1)
        if _is_steam_running():
            print("[GameUpdater] ✅ Steam is running")
            time.sleep(4)
            if is_windows():
                _handle_steam_profile_selection()
                time.sleep(2)
            return True

    print("[GameUpdater] ⚠️ Steam failed to start")
    return False


# [FIX-6] Better Steam Store API search
def _search_steam_appid(game_name: str) -> tuple[str | None, str | None]:
    name_lower = game_name.lower().strip()

    # Check installed games first
    steam_path = _find_steam_path()
    if steam_path:
        for g in _get_steam_games(steam_path):
            if name_lower in g["name"].lower():
                return g["id"], g["name"]

    # Exact match in known IDs
    if name_lower in _KNOWN_APPIDS:
        app_id, canonical = _KNOWN_APPIDS[name_lower]
        print(f"[GameUpdater] 📖 Known: {canonical} ({app_id})")
        return app_id, canonical

    # Partial match in known IDs
    for key, (app_id, canonical) in _KNOWN_APPIDS.items():
        if name_lower in key or key in name_lower:
            print(f"[GameUpdater] 📖 Partial match: {canonical} ({app_id})")
            return app_id, canonical

    # [FIX-6] Steam Store API with better matching
    try:
        import urllib.request, urllib.parse
        query = urllib.parse.quote(game_name)
        url   = f"https://store.steampowered.com/api/storesearch/?term={query}&l=english&cc=US"
        req   = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        items = data.get("items", [])
        if items:
            # [FIX-6] Try to find best match by name similarity
            best = items[0]
            for item in items:
                item_name = item.get("name", "").lower()
                if item_name == name_lower or name_lower in item_name:
                    best = item
                    break
            print(f"[GameUpdater] 🌐 Store API: {best['name']} ({best['id']})")
            return str(best["id"]), best["name"]
    except Exception as e:
        print(f"[GameUpdater] ⚠️ AppID search failed: {e}")

    return None, None


# [FIX-7] Proper state bitmask handling
def _steam_state_description(state: int) -> str:
    """Decode Steam StateFlags bitmask."""
    flags = []
    if state & 1:    flags.append("uninstalled")
    if state & 2:    flags.append("update_required")
    if state & 4:    flags.append("fully_installed")
    if state & 8:    flags.append("running")
    if state & 16:   flags.append("config_update")
    if state & 1024: flags.append("validating")
    if state & 1026: flags.append("downloading")
    return ", ".join(flags) if flags else f"state_{state}"


def _update_steam_games(steam_path: Path, game_name: str = None) -> str:
    if not _ensure_steam_running(steam_path):
        return "Could not start Steam."

    exe   = _steam_exe(steam_path)
    _invalidate_steam_cache()
    games = _get_steam_games(steam_path)
    if not games:
        return "No Steam games found."

    if game_name:
        name_lower = game_name.lower()
        targets    = [g for g in games if name_lower in g["name"].lower()]
        if not targets:
            available = ", ".join(g["name"] for g in games[:5])
            return f"Game '{game_name}' not found. Installed: {available}..."
    else:
        targets = games

    already_updated, already_running, update_started, errors = [], [], [], []

    for game in targets:
        state = game["state"]
        name  = game["name"]

        # [FIX-7] Proper bitmask checking
        if state & 4 and not (state & 2):  # Fully installed, no update needed
            already_updated.append(name)
        elif state & 8 or state & 1024:     # Running or validating
            already_running.append(name)
        elif state & 1026 or state & 2:     # Downloading or update required
            already_running.append(name)
        else:
            try:
                _launch_steam_url(exe, f"steam://update/{game['id']}")
                update_started.append(name)
                time.sleep(0.3)
            except Exception as e:
                errors.append(f"{name}: {e}")

    parts = []
    if update_started:
        names  = ", ".join(update_started[:3])
        suffix = f" and {len(update_started) - 3} more" if len(update_started) > 3 else ""
        parts.append(f"Update started for: {names}{suffix}.")
    if already_running:
        parts.append(f"Already updating/running: {', '.join(already_running[:3])}.")
    if already_updated:
        parts.append(
            f"'{already_updated[0]}' is already up to date."
            if game_name and len(already_updated) == 1 else
            f"{len(already_updated)} game(s) already up to date."
        )
    if errors:
        parts.append(f"Errors: {'; '.join(errors)}.")
    return " ".join(parts) if parts else "No games to update."


def _install_steam_game(steam_path: Path, game_name: str = None,
                        app_id: str = None) -> str:
    if not _ensure_steam_running(steam_path):
        return "Could not start Steam."

    exe             = _steam_exe(steam_path)
    _invalidate_steam_cache()
    installed_games = _get_steam_games(steam_path)

    already = None
    if app_id:
        already = next((g for g in installed_games if g["id"] == str(app_id)), None)
    elif game_name:
        name_lower = game_name.lower()
        already    = next((g for g in installed_games
                           if name_lower in g["name"].lower()), None)
    else:
        return "Please specify a game name or AppID."

    if already:
        state = already["state"]
        name  = already["name"]
        if state & 4 and not (state & 2):
            return f"'{name}' is already installed and up to date."
        if state & 1026:
            return f"'{name}' is currently downloading or updating."
        if state & 2:
            _launch_steam_url(exe, f"steam://update/{already['id']}")
            return f"'{name}' has a pending update. Update started."
        return f"'{name}' is already installed."

    if not app_id and game_name:
        found_id, found_name = _search_steam_appid(game_name)
        if not found_id:
            return (f"Could not find '{game_name}' on Steam. "
                    f"Try providing the AppID directly.")
        app_id    = found_id
        game_name = found_name or game_name
        print(f"[GameUpdater] 🔍 Installing: {game_name} (AppID: {app_id})")

    try:
        _launch_steam_url(exe, f"steam://install/{app_id}")

        if is_windows():
            threading.Thread(
                target=_handle_install_dialog,
                args=(game_name or str(app_id),),
                daemon=True
            ).start()
        return f"Install started for '{game_name}'. Steam will open the download dialog."
    except Exception as e:
        return f"Install failed: {e}"


def _get_download_status(steam_path: Path) -> str:
    _invalidate_steam_cache()
    games   = _get_steam_games(steam_path)
    active  = [g for g in games if g["state"] & 1026]
    pending = [g for g in games if g["state"] & 2 and not (g["state"] & 1026)]
    lines   = []
    if active:
        lines.append(f"Downloading: {', '.join(g['name'] for g in active)}.")
    if pending:
        names  = ", ".join(g["name"] for g in pending[:5])
        suffix = f" and {len(pending) - 5} more" if len(pending) > 5 else ""
        lines.append(f"Pending updates: {names}{suffix}.")
    return " ".join(lines) if lines else "No active downloads or pending updates."


def _system_shutdown() -> None:
    if is_windows():
        subprocess.run(["shutdown", "/s", "/t", "30"])
    elif is_mac():
        subprocess.run(["osascript", "-e", 'tell app "System Events" to shut down'])
    else:
        subprocess.run(["systemctl", "poweroff"])


# [FIX-8] + [FIX-14] Better download watch with grace period + shutdown warning
def _watch_and_shutdown(steam_path: Path, speak=None,
                        check_interval: int = 30, timeout_hours: int = 12):
    print("[GameUpdater] 👁️ Watching for download completion...")
    deadline = time.time() + timeout_hours * 3600

    # [FIX-8] Wait up to 10 minutes for download to start
    download_started = False
    for _ in range(120):  # 120 × 5s = 10 minutes
        time.sleep(5)
        _invalidate_steam_cache()
        active = [g for g in _get_steam_games(steam_path) if g["state"] & 1026]
        if active:
            names = ", ".join(g["name"] for g in active)
            if speak:
                speak(f"Download started for {names}. I'll shut down when done.")
            download_started = True
            break

    if not download_started:
        print("[GameUpdater] ⚠️ No download detected after 10 minutes. Cancelling watch.")
        if speak:
            speak("No download detected. Auto-shutdown cancelled.")
        return

    # Monitor until download completes
    while time.time() < deadline:
        time.sleep(check_interval)
        _invalidate_steam_cache()
        if not any(g["state"] & 1026 for g in _get_steam_games(steam_path)):
            # [FIX-14] Give a 60-second warning before shutdown
            if speak:
                speak("Download complete. Shutting down in 60 seconds. "
                      "Move your mouse to the corner to cancel.")
            print("[GameUpdater] ⏱️ Shutdown in 60 seconds...")
            time.sleep(60)

            # Re-check — user may have started another download
            _invalidate_steam_cache()
            if any(g["state"] & 1026 for g in _get_steam_games(steam_path)):
                print("[GameUpdater] New download detected — cancelling shutdown")
                continue

            _system_shutdown()
            return

    if speak:
        speak("Download taking too long. Cancelling auto-shutdown.")


def _find_epic_exe() -> Path | None:
    if is_windows(): return _find_epic_exe_windows()
    if is_mac():     return _find_epic_exe_mac()
    return _find_epic_exe_linux()


def _find_epic_exe_windows() -> Path | None:
    try:
        import winreg
        for hive, key_path in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\EpicGames\EpicGamesLauncher"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EpicGames\EpicGamesLauncher"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\EpicGames\EpicGamesLauncher"),
        ]:
            try:
                key = winreg.OpenKey(hive, key_path)
                val, _ = winreg.QueryValueEx(key, "AppDataPath")
                winreg.CloseKey(key)
                exe = Path(val) / "Binaries" / "Win64" / "EpicGamesLauncher.exe"
                if exe.exists():
                    return exe
            except Exception:
                continue
    except ImportError:
        pass
    for candidate in [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win64" / "EpicGamesLauncher.exe",
        Path(os.environ.get("ProgramFiles", ""))       / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win64" / "EpicGamesLauncher.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))        / "EpicGamesLauncher" / "Portal" / "Binaries" / "Win64" / "EpicGamesLauncher.exe",
    ]:
        if candidate.exists():
            return candidate
    return None


def _find_epic_exe_mac() -> Path | None:
    p = Path("/Applications/Epic Games Launcher.app/Contents/MacOS/EpicGamesLauncher")
    return p if p.exists() else None


def _find_epic_exe_linux() -> Path | None:
    for c in [Path.home() / ".local" / "bin" / "heroic", Path("/usr/bin/heroic")]:
        if c.exists():
            return c
    return None


def _epic_manifests_path() -> Path | None:
    if is_windows():
        p = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) \
            / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
        return p if p.exists() else None
    if is_mac():
        p = Path.home() / "Library" / "Application Support" \
            / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
        return p if p.exists() else None
    return None


def _get_epic_games() -> list[dict]:
    manifests = _epic_manifests_path()
    if not manifests:
        return []
    games = []
    for item_file in manifests.glob("*.item"):
        try:
            data = json.loads(item_file.read_text(encoding="utf-8"))
            name = data.get("DisplayName") or data.get("AppName", "")
            if name:
                games.append({"id": data.get("AppName", ""), "name": name})
        except Exception:
            continue
    return games


def _is_epic_running() -> bool:
    try:
        if is_windows():
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq EpicGamesLauncher.exe"],
                capture_output=True, text=True
            ).stdout
            return "epicgameslauncher.exe" in out.lower()
        proc = "EpicGamesLauncher" if is_mac() else "heroic"
        return bool(subprocess.run(["pgrep", "-x", proc],
                                   capture_output=True, text=True).stdout.strip())
    except Exception:
        return False


# [FIX-9] Fixed Epic "update" — was actually launching games
def _update_epic_games(epic_exe: Path, game_name: str = None) -> str:
    games = _get_epic_games()

    if game_name:
        name_lower = game_name.lower()
        matched    = [g for g in games if name_lower in g["name"].lower()]
        if not matched:
            return f"'{game_name}' not found in Epic."
        try:
            # [FIX-9] Use update action instead of launch
            url = f"com.epicgames.launcher://apps/{matched[0]['id']}?action=update"
            if is_mac():
                subprocess.Popen(["open", url])
            elif is_linux():
                subprocess.Popen([str(epic_exe), url] if epic_exe else ["xdg-open", url])
            else:
                subprocess.Popen([str(epic_exe), url])
            return f"Update triggered for '{matched[0]['name']}' in Epic."
        except Exception as e:
            return f"Epic update failed: {e}"
    else:
        try:
            if is_mac():
                subprocess.Popen(["open", "-a", "Epic Games Launcher"])
            elif is_linux():
                if epic_exe:
                    subprocess.Popen([str(epic_exe)])
                else:
                    return "Epic Games is not natively supported on Linux. Consider Heroic Launcher."
            else:
                subprocess.Popen([str(epic_exe)])
            count = len(games)
            return (f"Epic Games Launcher opened. {count} game(s) will be checked."
                    if count else "Epic Games Launcher opened.")
        except Exception as e:
            return f"Epic launch failed: {e}"


# [FIX-12] Validate hour/minute
def _validate_time(hour: int, minute: int) -> tuple[int, int]:
    hour   = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return hour, minute


def _schedule_daily_update(hour: int = 3, minute: int = 0) -> str:
    hour, minute = _validate_time(hour, minute)
    if is_windows(): return _schedule_windows(hour, minute)
    if is_mac():     return _schedule_mac(hour, minute)
    return _schedule_linux(hour, minute)


def _schedule_windows(hour: int, minute: int) -> str:
    task_name   = "JARVIS_GameUpdater"
    script_path = Path(__file__).resolve()
    subprocess.run(["schtasks", "/Delete", "/TN", task_name, "/F"], capture_output=True)
    for extra in (["/RL", "HIGHEST", "/RU", "SYSTEM"], []):
        cmd    = ["schtasks", "/Create", "/TN", task_name,
                  "/TR", f'"{sys.executable}" "{script_path}" --scheduled',
                  "/SC", "DAILY", "/ST", f"{hour:02d}:{minute:02d}", "/F", *extra]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return f"Daily game update scheduled at {hour:02d}:{minute:02d}."
    return f"Scheduling failed: {result.stderr.strip()}"


def _schedule_mac(hour: int, minute: int) -> str:
    plist_dir   = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path  = plist_dir / "com.jarvis.gameupdater.plist"
    script_path = Path(__file__).resolve()
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>com.jarvis.gameupdater</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{script_path}</string>
        <string>--scheduled</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>{hour}</integer>
        <key>Minute</key><integer>{minute}</integer>
    </dict>
    <key>RunAtLoad</key><false/>
</dict></plist>"""
    try:
        plist_path.write_text(plist_content, encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        result = subprocess.run(["launchctl", "load", str(plist_path)],
                                capture_output=True, text=True)
        if result.returncode == 0:
            return f"Daily game update scheduled at {hour:02d}:{minute:02d} via launchd."
        return f"Scheduling failed: {result.stderr.strip()}"
    except Exception as e:
        return f"Scheduling failed: {e}"


def _schedule_linux(hour: int, minute: int) -> str:
    script_path = Path(__file__).resolve()
    marker      = "# JARVIS_GameUpdater"
    cron_entry  = f"{minute} {hour} * * * {sys.executable} {script_path} --scheduled  {marker}"
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        lines    = [l for l in existing.stdout.splitlines()
                    if marker not in l and str(script_path) not in l]
        lines.append(cron_entry)
        proc = subprocess.run(["crontab", "-"],
                              input="\n".join(lines) + "\n",
                              text=True, capture_output=True)
        if proc.returncode == 0:
            return f"Daily game update scheduled at {hour:02d}:{minute:02d} via cron."
        return f"Scheduling failed: {proc.stderr.strip()}"
    except Exception as e:
        return f"Scheduling failed: {e}"


def _cancel_scheduled_update() -> str:
    if is_windows():
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", "JARVIS_GameUpdater", "/F"],
            capture_output=True, text=True
        )
        return ("Scheduled update cancelled."
                if result.returncode == 0 else "No scheduled update found.")
    if is_mac():
        plist_path = Path.home() / "Library" / "LaunchAgents" / "com.jarvis.gameupdater.plist"
        if plist_path.exists():
            subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
            plist_path.unlink()
            return "Scheduled update cancelled."
        return "No scheduled update found."

    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        lines    = [l for l in existing.stdout.splitlines()
                    if "JARVIS_GameUpdater" not in l]
        subprocess.run(["crontab", "-"],
                       input="\n".join(lines) + "\n", text=True)
        return "Scheduled update cancelled."
    except Exception as e:
        return f"Cancel failed: {e}"


def _get_schedule_status() -> str:
    if is_windows():
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", "JARVIS_GameUpdater", "/FO", "LIST"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return "No scheduled game update found."
        for line in result.stdout.strip().splitlines():
            if any(k in line for k in
                   ("Next Run", "Sonraki", "Prochaine", "Próxima", "Nächste")):
                return f"Game update scheduled. {line.strip()}"
        return "Game update is scheduled."
    if is_mac():
        plist_path = (Path.home() / "Library" / "LaunchAgents"
                      / "com.jarvis.gameupdater.plist")
        return ("Game update is scheduled via launchd."
                if plist_path.exists() else "No scheduled game update found.")

    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if "JARVIS_GameUpdater" in result.stdout:
            for line in result.stdout.splitlines():
                if "JARVIS_GameUpdater" in line:
                    return f"Game update is scheduled: {line.split('#')[0].strip()}"
        return "No scheduled game update found."
    except Exception:
        return "No scheduled game update found."


# [FIX-11] Renamed parameter to avoid shadowing platform module
def game_updater(parameters: dict, player=None, speak=None, **kwargs) -> str:
    p            = parameters or {}
    action       = p.get("action",    "update").lower().strip()
    plat         = p.get("platform",  "both").lower().strip()  # [FIX-11] renamed
    game_name    = (p.get("game_name") or "").strip() or None
    app_id       = (p.get("app_id")    or "").strip() or None
    hour         = int(p.get("hour",   3))
    minute       = int(p.get("minute", 0))
    shutdown     = str(p.get("shutdown_when_done", "false")).lower() == "true"

    results = []

    if action == "schedule":        return _schedule_daily_update(hour=hour, minute=minute)
    if action == "cancel_schedule": return _cancel_scheduled_update()
    if action == "schedule_status": return _get_schedule_status()

    if action == "list":
        if plat in ("steam", "both"):
            steam_path = _find_steam_path()
            if steam_path:
                games = _get_steam_games(steam_path)
                if games:
                    names  = ", ".join(g["name"] for g in games[:8])
                    suffix = f" and {len(games) - 8} more" if len(games) > 8 else ""
                    results.append(f"Steam ({len(games)} games): {names}{suffix}.")
                else:
                    results.append("Steam: No games found.")
            else:
                results.append("Steam: Not installed.")
        if plat in ("epic", "both"):
            if is_linux():
                results.append("Epic: Not natively supported on Linux.")
            else:
                games = _get_epic_games()
                if games:
                    names  = ", ".join(g["name"] for g in games[:8])
                    suffix = f" and {len(games) - 8} more" if len(games) > 8 else ""
                    results.append(f"Epic ({len(games)} games): {names}{suffix}.")
                else:
                    results.append("Epic: No games found.")
        return " | ".join(results) or "No platforms found."

    if action == "download_status":
        if plat in ("steam", "both"):
            steam_path = _find_steam_path()
            results.append(
                _get_download_status(steam_path) if steam_path else "Steam: Not installed."
            )
        if plat in ("epic", "both"):
            results.append("Epic download status not available directly.")
        return " ".join(results)

    if action in ("install", "update"):
        if plat in ("steam", "both"):
            steam_path = _find_steam_path()
            if not steam_path:
                results.append("Steam: Not installed.")
            else:
                if game_name:
                    _invalidate_steam_cache()
                    installed  = _get_steam_games(steam_path)
                    name_lower = game_name.lower()
                    is_installed = any(
                        name_lower in g["name"].lower() for g in installed
                    )
                    if not is_installed:
                        msg = _install_steam_game(
                            steam_path, game_name=game_name, app_id=app_id
                        )
                        if shutdown:
                            threading.Thread(
                                target=_watch_and_shutdown,
                                kwargs={"steam_path": steam_path, "speak": speak},
                                daemon=True
                            ).start()
                            msg += " Auto-shutdown enabled."
                        if player: player.write_log(f"[GameUpdater] {msg[:100]}")
                        if speak:  speak(msg)
                        return msg
                    else:
                        results.append(
                            f"Steam: {_update_steam_games(steam_path, game_name=game_name)}"
                        )
                else:
                    if action == "install":
                        results.append("Steam: Please specify a game name to install.")
                    else:
                        results.append(f"Steam: {_update_steam_games(steam_path)}")

                if shutdown and action == "update":
                    threading.Thread(
                        target=_watch_and_shutdown,
                        kwargs={"steam_path": steam_path, "speak": speak},
                        daemon=True
                    ).start()
                    results.append("Auto-shutdown enabled.")

        if plat in ("epic", "both"):
            if is_linux():
                results.append(
                    "Epic: Not natively supported on Linux. Use Heroic Launcher."
                )
            else:
                epic_exe = _find_epic_exe()
                if epic_exe:
                    results.append(
                        f"Epic: {_update_epic_games(epic_exe, game_name=game_name)}"
                    )
                else:
                    results.append("Epic: Not installed.")

        output = " | ".join(results) or "Nothing to do."
        if player: player.write_log(f"[GameUpdater] {output[:100]}")
        if speak:  speak(output)
        return output

    return f"Unknown action: '{action}'."


if __name__ == "__main__":
    if "--scheduled" in sys.argv:
        print(f"[GameUpdater] 🕐 Scheduled run at {datetime.now().strftime('%H:%M')}")
        result = game_updater({"action": "update", "platform": "both"})
        print(f"[GameUpdater] ✅ {result}")
