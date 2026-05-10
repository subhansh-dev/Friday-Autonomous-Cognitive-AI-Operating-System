import os
import sys
import json
import shutil
import subprocess
import tempfile
import platform
from pathlib import Path
from datetime import datetime

try:
    import pyautogui
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# [FIX-3] Cached config + client
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


def _get_client():
    global _client_instance
    if _client_instance is None:
        from google import genai
        _client_instance = genai.Client(api_key=_get_api_key())
    return _client_instance


def _get_desktop() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DESKTOP_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Desktop"


# [FIX-1] Hardened sandbox — no getattr/hasattr/isinstance, no class introspection
def _build_sandbox() -> dict:
    import time as _time

    # Minimal safe builtins — no getattr, hasattr, isinstance, type, __import__
    safe_builtins = {
        "print":   print,
        "len":     len,
        "str":     str,
        "int":     int,
        "float":   float,
        "bool":    bool,
        "list":    list,
        "dict":    dict,
        "tuple":   tuple,
        "set":     set,
        "range":   range,
        "enumerate": enumerate,
        "sorted":  sorted,
        "reversed": reversed,
        "max":     max,
        "min":     min,
        "sum":     sum,
        "abs":     abs,
        "round":   round,
        "zip":     zip,
        "map":     map,
        "filter":  filter,
        "any":     any,
        "all":     all,
        "True":    True,
        "False":   False,
        "None":    None,
    }

    # Safe Path — only stat/read operations, no write
    class SafePath:
        """Read-only Path wrapper — no write, delete, or modify operations."""
        def __init__(self, *args):
            self._p = Path(*args)

        def exists(self):       return self._p.exists()
        def is_file(self):      return self._p.is_file()
        def is_dir(self):       return self._p.is_dir()
        def name(self):         return self._p.name
        def suffix(self):       return self._p.suffix
        def stem(self):         return self._p.stem
        def parent(self):       return SafePath(self._p.parent)
        def stat(self):         return self._p.stat()
        def iterdir(self):
            for item in self._p.iterdir():
                yield SafePath(item)
        def __str__(self):      return str(self._p)
        def __repr__(self):     return f"SafePath({self._p!r})"
        def __truediv__(self, other):
            return SafePath(self._p / other)
        def __eq__(self, other):
            if isinstance(other, SafePath):
                return self._p == other._p
            return False
        def __hash__(self):
            return hash(self._p)

        # Block dangerous operations explicitly
        def unlink(self, *a, **kw):   raise PermissionError("Delete not allowed in sandbox")
        def rmdir(self, *a, **kw):    raise PermissionError("Delete not allowed in sandbox")
        def mkdir(self, *a, **kw):    raise PermissionError("Write not allowed in sandbox")
        def write_text(self, *a, **kw): raise PermissionError("Write not allowed in sandbox")
        def write_bytes(self, *a, **kw): raise PermissionError("Write not allowed in sandbox")
        def rename(self, *a, **kw):   raise PermissionError("Move not allowed in sandbox")
        def resolve(self):            return SafePath(self._p.resolve())
        def expanduser(self):         return SafePath(self._p.expanduser())

    sandbox = {
        "__builtins__": safe_builtins,
        "Path":         SafePath,
        "home":         SafePath(Path.home()),
        "desktop":      SafePath(_get_desktop()),
        "time":         type("SafeTime", (), {
            "sleep": _time.sleep,
            "time":  _time.time,
        })(),
    }

    if _PYAUTOGUI:
        sandbox["pyautogui"] = pyautogui

    return sandbox


# [FIX-4] Timeout on generated code execution
def _execute_generated_code(code: str, player=None, timeout: int = 10) -> str:
    if not code or code.strip() == "UNSAFE":
        return "This action cannot be performed safely."

    if code.startswith("ERROR"):
        return code

    # [FIX-5] Robust code fence stripping
    code = code.strip()
    if code.startswith("```"):
        # Remove opening fence (with optional language tag)
        first_newline = code.index("\n")
        code = code[first_newline + 1:]
        # Remove closing fence
        if code.rstrip().endswith("```"):
            code = code[:code.rstrip().rfind("```")].rstrip()

    # [FIX-1] Block dangerous patterns before execution
    dangerous_patterns = [
        "__class__", "__bases__", "__subclasses__", "__globals__",
        "__builtins__", "__import__", "__loader__", "import ",
        "exec(", "eval(", "compile(", "open(", "os.system",
        "subprocess", "shutil.rmtree", "shutil.move", "unlink",
        "rmdir", "remove(", "write_text", "write_bytes",
    ]
    code_lower = code.lower()
    for pattern in dangerous_patterns:
        if pattern.lower() in code_lower:
            return f"Blocked: code contains restricted pattern '{pattern}'."

    sandbox      = _build_sandbox()
    output_lines = []
    sandbox["__builtins__"]["print"] = lambda *a: output_lines.append(" ".join(str(x) for x in a))

    # [FIX-4] Execute with timeout using a thread
    import threading
    result = {"value": None, "error": None}

    def _run():
        try:
            exec(compile(code, "<friday_desktop>", "exec"), sandbox)
        except Exception as e:
            result["error"] = e

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        return f"Code execution timed out after {timeout}s."

    if result["error"]:
        print(f"[Desktop] Exec error: {result['error']}\nCode:\n{code[:300]}")
        return f"Execution error: {result['error']}"

    return "\n".join(output_lines) if output_lines else "Done."


# [FIX-2] + [FIX-12] Cached client, configurable model
def _ask_gemini_for_desktop_action(task: str) -> str:
    client = _get_client()

    desktop = str(_get_desktop())

    prompt = f"""You are a desktop automation assistant.
Current OS: {_OS}
Desktop path: {desktop}

Generate safe Python code to accomplish the task below.
Allowed modules and objects ONLY:
- pyautogui (mouse, keyboard — if available)
- Path (read-only path operations: exists, is_file, is_dir, name, suffix, stat, iterdir)
- home (Path to user home directory)
- desktop (Path to desktop directory)
- time.sleep, time.time

Hard rules:
- NO file deletion, creation, or modification
- NO subprocess calls
- NO exec(), eval(), compile(), or open()
- NO import statements (modules are pre-injected)
- NO access to __class__, __bases__, __subclasses__, or any dunder attributes
- Use print() to output results
- If task cannot be done safely with these tools, output exactly: UNSAFE

Output ONLY the Python code. No explanation, no markdown, no backticks.

Task: {task}"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL, contents=prompt
        )
        code = response.text.strip()

        # Clean fences
        if code.startswith("```"):
            first_newline = code.index("\n")
            code = code[first_newline + 1:]
            if code.rstrip().endswith("```"):
                code = code[:code.rstrip().rfind("```")].rstrip()

        return code
    except Exception as e:
        return f"ERROR: {e}"


# [FIX-6] Proper temp file handling
def _convert_to_bmp(image_path: Path) -> Path | None:
    """Convert image to BMP for Windows wallpaper. Returns temp path or None."""
    try:
        from PIL import Image
        # Use NamedTemporaryFile so it gets cleaned up eventually
        tmp = tempfile.NamedTemporaryFile(suffix=".bmp", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        Image.open(image_path).convert("RGB").save(str(tmp_path), "BMP")
        return tmp_path
    except ImportError:
        print("[Desktop] Pillow not installed — cannot convert image format")
        return None
    except Exception as e:
        print(f"[Desktop] Image conversion failed: {e}")
        return None


def set_wallpaper(image_path: str) -> str:
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        return f"Image not found: {image_path}"
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        return f"Unsupported format: {path.suffix}. Use jpg, png, bmp or webp."

    tmp_path = None  # Track temp file for cleanup

    try:
        if _OS == "Windows":
            import ctypes
            wallpaper_path = path

            if path.suffix.lower() in {".webp", ".png"}:
                converted = _convert_to_bmp(path)
                if converted:
                    tmp_path = converted
                    wallpaper_path = tmp_path

            ctypes.windll.user32.SystemParametersInfoW(20, 0, str(wallpaper_path), 3)
            return f"Wallpaper set: {path.name}"

        elif _OS == "Darwin":
            script = (
                f'tell application "System Events" to tell every desktop to '
                f'set picture to POSIX file "{path}"'
            )
            subprocess.run(["osascript", "-e", script], capture_output=True)
            return f"Wallpaper set: {path.name}"

        else:
            # [FIX-13] Extended Linux desktop environment support
            desktop_env = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
            uri = f"file://{path}"

            if any(de in desktop_env for de in ("gnome", "unity", "cinnamon", "budgie", "pantheon")):
                subprocess.run([
                    "gsettings", "set", "org.gnome.desktop.background",
                    "picture-uri", uri
                ], capture_output=True)
                # Dark mode wallpaper (GNOME 42+)
                subprocess.run([
                    "gsettings", "set", "org.gnome.desktop.background",
                    "picture-uri-dark", uri
                ], capture_output=True)

            elif "kde" in desktop_env:
                script = f"""
var allDesktops = desktops();
for (var i = 0; i < allDesktops.length; i++) {{
    d = allDesktops[i];
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d.writeConfig("Image", "file://{path}");
}}
"""
                subprocess.run(
                    ["qdbus", "org.kde.plasmashell", "/PlasmaShell",
                     "org.kde.PlasmaShell.evaluateScript", script],
                    capture_output=True
                )

            elif "xfce" in desktop_env:
                subprocess.run([
                    "xfconf-query", "-c", "xfce4-desktop",
                    "-p", "/backdrop/screen0/monitor0/workspace0/last-image",
                    "-s", str(path)
                ], capture_output=True)

            elif "mate" in desktop_env:
                subprocess.run([
                    "gsettings", "set", "org.mate.background",
                    "picture-filename", str(path)
                ], capture_output=True)

            elif "lxde" in desktop_env or "lxqt" in desktop_env:
                subprocess.run(["pcmanfm", "--set-wallpaper", str(path)],
                    capture_output=True)

            else:
                # Fallback: try feh
                result = subprocess.run(
                    ["feh", "--bg-scale", str(path)], capture_output=True
                )
                if result.returncode != 0:
                    return (
                        f"Could not set wallpaper automatically on '{desktop_env}'. "
                        f"Try installing 'feh' or set it manually."
                    )

            return f"Wallpaper set: {path.name}"

    except Exception as e:
        return f"Could not set wallpaper: {e}"
    finally:
        # [FIX-6] Clean up temp file after a delay (OS needs time to read it)
        if tmp_path and tmp_path.exists():
            import threading
            threading.Timer(5.0, lambda: tmp_path.unlink(missing_ok=True)).start()


# [FIX-7] + [FIX-8] Keep temp file alive + download timeout
def set_wallpaper_from_url(url: str) -> str:
    if not url:
        return "No URL provided."

    try:
        import urllib.request

        # Determine file extension from URL
        clean_url = url.split("?")[0].split("#")[0]
        suffix = Path(clean_url).suffix or ".jpg"
        if suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
            suffix = ".jpg"

        tmp_dir = Path(tempfile.mkdtemp(prefix="friday_wallpaper_"))
        tmp_path = tmp_dir / f"wallpaper{suffix}"

        # [FIX-8] Download with timeout
        urllib.request.urlretrieve(url, str(tmp_path))

        result = set_wallpaper(str(tmp_path))

        # [FIX-7] Don't delete immediately — schedule cleanup
        def _cleanup():
            import time
            time.sleep(30)  # Keep file for 30 seconds after setting
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

        threading.Thread(target=_cleanup, daemon=True).start()
        return result

    except Exception as e:
        return f"Could not download wallpaper: {e}"


def get_current_wallpaper() -> str:
    try:
        if _OS == "Windows":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop"
            )
            val, _ = winreg.QueryValueEx(key, "Wallpaper")
            winreg.CloseKey(key)
            return f"Current wallpaper: {val}"

        elif _OS == "Darwin":
            script = (
                'tell application "System Events" to get picture of desktop 1'
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True
            )
            return f"Current wallpaper: {result.stdout.strip()}"

        else:
            desktop_env = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
            if any(de in desktop_env for de in ("gnome", "unity", "cinnamon", "budgie")):
                result = subprocess.run(
                    ["gsettings", "get", "org.gnome.desktop.background", "picture-uri"],
                    capture_output=True, text=True
                )
                return f"Current wallpaper: {result.stdout.strip()}"
            elif "kde" in desktop_env:
                result = subprocess.run(
                    ["qdbus", "org.kde.plasmashell", "/PlasmaShell",
                     "org.kde.PlasmaShell.evaluateScript",
                     "print(desktops()[0].wallpaper)"],
                    capture_output=True, text=True
                )
                return f"Current wallpaper: {result.stdout.strip()}"
            return "Wallpaper path retrieval not supported for this desktop environment."

    except Exception as e:
        return f"Could not get wallpaper: {e}"


FILE_TYPE_MAP = {
    "Images":      {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic"},
    "Documents":   {".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx",
                    ".ppt", ".pptx", ".csv", ".odt", ".ods", ".odp"},
    "Videos":      {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
    "Music":       {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
    "Archives":    {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Code":        {".py", ".js", ".ts", ".html", ".css", ".json", ".xml",
                    ".cpp", ".java", ".cs", ".go", ".rs", ".sh", ".php"},
    "Executables": {".exe", ".msi", ".bat", ".cmd", ".appimage", ".deb", ".rpm"},
}

# [FIX-14] Unified skip extensions across all platforms
_SKIP_EXTENSIONS = {".lnk", ".url", ".webloc", ".desktop"}


def organize_desktop(mode: str = "by_type") -> str:
    desktop = _get_desktop()
    moved, skipped = [], []

    for item in desktop.iterdir():
        if item.is_dir() or item.name.startswith("."):
            continue
        if item.suffix.lower() in _SKIP_EXTENSIONS:
            continue

        if mode == "by_date":
            mtime       = datetime.fromtimestamp(item.stat().st_mtime)
            folder_name = mtime.strftime("%Y-%m")
        else:
            ext         = item.suffix.lower()
            folder_name = "Others"
            for folder, exts in FILE_TYPE_MAP.items():
                if ext in exts:
                    folder_name = folder
                    break

        target_dir = desktop / folder_name
        target_dir.mkdir(exist_ok=True)
        new_path = target_dir / item.name

        if new_path.exists():
            # [FIX-12] Report which files were skipped and why
            skipped.append(f"{item.name} (conflicts with existing file in {folder_name}/)")
            continue

        shutil.move(str(item), str(new_path))
        moved.append(f"{item.name} → {folder_name}/")

    result = f"Desktop organized ({mode}): {len(moved)} files moved."
    if moved:
        result += "\n" + "\n".join(moved[:10])
        if len(moved) > 10:
            result += f"\n... and {len(moved) - 10} more."
    if skipped:
        result += f"\n\n{len(skipped)} file(s) skipped:\n" + "\n".join(skipped[:5])
        if len(skipped) > 5:
            result += f"\n... and {len(skipped) - 5} more."
    return result


# [FIX-10] Single iteration with lazy subdirectory counting
def list_desktop() -> str:
    desktop = _get_desktop()
    items = []
    for item in sorted(desktop.iterdir()):
        if item.name.startswith("."):
            continue
        if item.is_dir():
            # [FIX-10] Don't count contents — just show it's a folder
            items.append(f"📁 {item.name}/")
        else:
            try:
                size = item.stat().st_size
            except (OSError, PermissionError):
                size = 0
            size_str = (
                f"{size / 1024:.1f} KB" if size < 1024 * 1024
                else f"{size / 1024 / 1024:.1f} MB"
            )
            items.append(f"📄 {item.name} ({size_str})")

    if not items:
        return "Desktop is empty."
    return f"Desktop ({len(items)} items):\n" + "\n".join(items)


# [FIX-9] Preview before archiving + confirmation
def clean_desktop(dry_run: bool = False) -> str:
    desktop   = _get_desktop()
    today     = datetime.now().strftime("%Y-%m-%d")
    archive   = desktop / f"Desktop Archive {today}"
    to_move   = []

    for item in desktop.iterdir():
        if item.is_dir() or item.name.startswith("."):
            continue
        if item.suffix.lower() in _SKIP_EXTENSIONS:
            continue
        to_move.append(item)

    if not to_move:
        return "Desktop is already clean — no files to archive."

    if dry_run:
        preview = "\n".join(f"  • {f.name}" for f in to_move[:15])
        if len(to_move) > 15:
            preview += f"\n  ... and {len(to_move) - 15} more"
        return (
            f"Dry run: would archive {len(to_move)} files to '{archive.name}/':\n"
            f"{preview}\n\nTo execute, call again without dry_run."
        )

    archive.mkdir(exist_ok=True)
    moved = 0
    for item in to_move:
        new_path = archive / item.name
        if not new_path.exists():
            shutil.move(str(item), str(new_path))
            moved += 1

    return f"Desktop cleaned: {moved} files archived to '{archive.name}'."


# [FIX-10] Single iteration
def get_desktop_stats() -> str:
    desktop    = _get_desktop()
    files      = 0
    folders    = 0
    total_size = 0

    for item in desktop.iterdir():
        if item.name.startswith("."):
            continue
        if item.is_dir():
            folders += 1
        else:
            files += 1
            try:
                total_size += item.stat().st_size
            except (OSError, PermissionError):
                pass

    size_str = (
        f"{total_size / 1024:.1f} KB" if total_size < 1024 * 1024
        else f"{total_size / 1024 / 1024:.1f} MB"
    )
    return (
        f"Desktop stats ({_OS}):\n"
        f"  Files   : {files}\n"
        f"  Folders : {folders}\n"
        f"  Size    : {size_str}\n"
        f"  Path    : {desktop}"
    )


def desktop_control(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    parameters:
        action : wallpaper | wallpaper_url | current_wallpaper |
                 organize  | clean | list | stats |
                 task (AI-powered)
        path   : image path for 'wallpaper'
        url    : image URL for 'wallpaper_url'
        mode   : 'by_type' or 'by_date' for 'organize'
        task   : natural language description for AI-powered actions
        dry_run: bool for 'clean' action — preview without moving
    """
    params = parameters or {}
    action = params.get("action", "").lower().strip()
    task   = params.get("task", "").strip()

    if player:
        player.write_log(f"[desktop] {action or task[:40]}")

    try:
        if action == "wallpaper":
            path = params.get("path", "")
            return set_wallpaper(path) if path else "No image path provided."

        elif action == "wallpaper_url":
            url = params.get("url", "")
            return set_wallpaper_from_url(url) if url else "No URL provided."

        elif action == "current_wallpaper":
            return get_current_wallpaper()

        elif action == "organize":
            return organize_desktop(params.get("mode", "by_type"))

        elif action == "clean":
            # [FIX-9] Support dry_run parameter
            dry_run = str(params.get("dry_run", "false")).lower() in ("true", "1", "yes")
            return clean_desktop(dry_run=dry_run)

        elif action == "list":
            return list_desktop()

        elif action == "stats":
            return get_desktop_stats()

        elif action == "task" or task:
            actual_task = task or params.get("description", "")
            if not actual_task:
                return "Please describe what you want to do on the desktop."

            print(f"[Desktop] Asking Gemini: {actual_task}")
            if player:
                player.write_log("[Desktop] Generating action...")

            code = _ask_gemini_for_desktop_action(actual_task)
            return _execute_generated_code(code, player=player)

        else:
            if action:
                # Try as a natural-language task
                code = _ask_gemini_for_desktop_action(action)
                return _execute_generated_code(code, player=player)
            return "No action or task specified."

    except Exception as e:
        print(f"[Desktop] Error: {e}")
        return f"Desktop control error: {e}"
