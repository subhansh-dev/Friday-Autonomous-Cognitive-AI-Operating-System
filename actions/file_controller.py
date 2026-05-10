import os
import shutil
import platform
from pathlib import Path
from datetime import datetime

try:
    import send2trash
    _SEND2TRASH = True
except ImportError:
    _SEND2TRASH = False

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

_SAFE_ROOTS: list[Path] = [
    Path.home(),
]

# [FIX-6] Maximum content size for write operations (10MB)
MAX_WRITE_SIZE = 10 * 1024 * 1024

# [FIX-9] Maximum items to list
MAX_LIST_ITEMS = 200

# [FIX-4] Maximum directory depth for recursive searches
MAX_SEARCH_DEPTH = 8


def _is_safe_path(target: Path) -> bool:
    try:
        resolved = target.resolve()
        for root in _SAFE_ROOTS:
            root_resolved = root.resolve()
            if resolved == root_resolved or resolved.is_relative_to(root_resolved):
                return True
        return False
    except Exception:
        return False


def _get_desktop() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DESKTOP_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Desktop"


def _get_downloads() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOWNLOAD_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Downloads"


def _get_documents() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOCUMENTS_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Documents"


def _get_pictures() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_PICTURES_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Pictures"


def _get_music() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_MUSIC_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Music"


def _get_videos() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_VIDEOS_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Videos"


_SHORTCUTS: dict[str, Path] | None = None


def _resolve_path(raw: str) -> Path:
    global _SHORTCUTS
    if _SHORTCUTS is None:
        _SHORTCUTS = {
            "desktop":   _get_desktop(),
            "downloads": _get_downloads(),
            "documents": _get_documents(),
            "pictures":  _get_pictures(),
            "music":     _get_music(),
            "videos":    _get_videos(),
            "home":      Path.home(),
        }
    lower = raw.strip().lower()
    if lower in _SHORTCUTS:
        return _SHORTCUTS[lower]
    return Path(raw).expanduser()


def _format_size(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


# [FIX-7] Binary file detection
def _is_binary(path: Path, chunk_size: int = 8192) -> bool:
    try:
        chunk = path.read_bytes()[:chunk_size]
        return b"\x00" in chunk
    except Exception:
        return False


def _safe_trash(target: Path) -> str:
    if not _SEND2TRASH:
        return (
            "send2trash is not installed. "
            "Run: pip install send2trash — "
            "Permanent deletion is disabled for safety."
        )
    send2trash.send2trash(str(target))
    return f"Moved to Trash: {target.name}"


def list_files(path: str = "desktop", show_hidden: bool = False) -> str:
    try:
        target = _resolve_path(path)
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Path not found: {target}"
        if not target.is_dir():
            return f"Not a directory: {target}"

        items = []
        for item in sorted(target.iterdir()):
            if not show_hidden and item.name.startswith("."):
                continue
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                try:
                    size = _format_size(item.stat().st_size)
                except (OSError, PermissionError):
                    size = "?"
                items.append(f"📄 {item.name} ({size})")

            # [FIX-9] Cap output size
            if len(items) >= MAX_LIST_ITEMS:
                remaining = sum(1 for _ in target.iterdir()) - MAX_LIST_ITEMS
                if remaining > 0:
                    items.append(f"... and ~{remaining} more items")
                break

        if not items:
            return f"Directory is empty: {target.name}/"

        return f"Contents of {target.name}/ ({len(items)} items):\n" + "\n".join(items)

    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Error listing files: {e}"


def create_file(path: str, name: str = "", content: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base

        # [FIX-1] Safety check BEFORE creating directories
        if not _is_safe_path(target):
            return f"Access denied: {target}"

        # [FIX-6] Content size limit
        if content and len(content.encode("utf-8")) > MAX_WRITE_SIZE:
            return f"Content too large ({len(content)} chars). Max: {MAX_WRITE_SIZE // 1024}KB."

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"File created: {target.name}"
    except Exception as e:
        return f"Could not create file: {e}"


def create_folder(path: str, name: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        target.mkdir(parents=True, exist_ok=True)
        return f"Folder created: {target.name}"
    except Exception as e:
        return f"Could not create folder: {e}"


# [FIX-3] Robust protected directory check
_PROTECTED_DIRS: set[Path] | None = None


def _get_protected_dirs() -> set[Path]:
    global _PROTECTED_DIRS
    if _PROTECTED_DIRS is None:
        dirs = [
            _get_desktop(), _get_downloads(), _get_documents(),
            _get_pictures(), _get_music(), _get_videos(), Path.home()
        ]
        _PROTECTED_DIRS = set()
        for d in dirs:
            try:
                _PROTECTED_DIRS.add(d.resolve())
            except Exception:
                pass
    return _PROTECTED_DIRS


def delete_file(path: str, name: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Not found: {target.name}"

        # Protect critical user directories
        try:
            target_resolved = target.resolve()
        except Exception:
            target_resolved = target

        if target_resolved in _get_protected_dirs():
            return f"Protected directory, cannot delete: {target.name}"

        return _safe_trash(target)

    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Could not delete: {e}"


def move_file(path: str, name: str = "", destination: str = "") -> str:
    try:
        base = _resolve_path(path)
        src  = (base / name) if name else base
        dst  = _resolve_path(destination) if destination else None

        if not src.exists():
            return f"Source not found: {src.name}"
        if dst is None:
            return "No destination specified."
        if not _is_safe_path(src):
            return f"Access denied (source): {src}"
        if not _is_safe_path(dst):
            return f"Access denied (destination): {dst}"

        if dst.is_dir():
            dst = dst / src.name

        # Check for overwrite
        if dst.exists():
            return f"Destination already exists: {dst.name}. Rename first or delete the existing file."

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Moved: {src.name} → {dst.parent.name}/"

    except Exception as e:
        return f"Could not move: {e}"


# [FIX-2] Handle existing destination in copytree
def copy_file(path: str, name: str = "", destination: str = "") -> str:
    try:
        base = _resolve_path(path)
        src  = (base / name) if name else base
        dst  = _resolve_path(destination) if destination else None

        if not src.exists():
            return f"Source not found: {src.name}"
        if dst is None:
            return "No destination specified."
        if not _is_safe_path(src):
            return f"Access denied (source): {src}"
        if not _is_safe_path(dst):
            return f"Access denied (destination): {dst}"

        if dst.is_dir():
            dst = dst / src.name

        dst.parent.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            # [FIX-2] Handle existing directory
            if dst.exists():
                return (
                    f"Directory '{dst.name}' already exists at destination. "
                    f"Delete it first or choose a different name."
                )
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))

        return f"Copied: {src.name} → {dst.parent.name}/"

    except Exception as e:
        return f"Could not copy: {e}"


def rename_file(path: str, name: str = "", new_name: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Not found: {target.name}"
        if not new_name:
            return "No new name provided."

        # Validate new name doesn't contain path separators
        if "/" in new_name or "\\" in new_name:
            return "New name cannot contain path separators. Use a simple filename."

        new_path = target.parent / new_name
        if not _is_safe_path(new_path):
            return f"Access denied: {new_path}"
        if new_path.exists():
            return f"A file named '{new_name}' already exists here."

        target.rename(new_path)
        return f"Renamed: {target.name} → {new_name}"

    except Exception as e:
        return f"Could not rename: {e}"


# [FIX-7] Binary file detection in read
def read_file(path: str, name: str = "", max_chars: int = 4000) -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"File not found: {target.name}"
        if not target.is_file():
            return f"Not a file: {target.name}"

        # [FIX-7] Check for binary files
        if _is_binary(target):
            size = _format_size(target.stat().st_size)
            return f"Binary file detected ({size}): {target.name}. Cannot display as text."

        content = target.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n[Truncated — {len(content)} total chars]"
        return content

    except Exception as e:
        return f"Could not read file: {e}"


# [FIX-6] Content size limit on writes
def write_file(path: str, name: str = "", content: str = "",
               append: bool = False) -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"

        # [FIX-6] Content size limit
        if content and len(content.encode("utf-8")) > MAX_WRITE_SIZE:
            return f"Content too large ({len(content)} chars). Max: {MAX_WRITE_SIZE // 1024}KB."

        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(target, mode, encoding="utf-8") as f:
            f.write(content)
        action = "Appended to" if append else "Written to"
        return f"{action}: {target.name}"
    except Exception as e:
        return f"Could not write file: {e}"


# [FIX-4] + [FIX-11] Depth-limited search + extension normalization
def find_files(name: str = "", extension: str = "",
               path: str = "home", max_results: int = 20) -> str:
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return f"Access denied: {search_path}"
        if not search_path.exists():
            return f"Search path not found: {path}"

        # [FIX-11] Normalize extension
        if extension and not extension.startswith("."):
            extension = "." + extension

        results = []

        # [FIX-4] Depth-limited recursive search instead of rglob
        def _search(directory: Path, depth: int):
            if depth > MAX_SEARCH_DEPTH:
                return
            try:
                for item in directory.iterdir():
                    if len(results) >= max_results:
                        return
                    if item.is_dir():
                        if not item.name.startswith(".") and not item.is_symlink():
                            _search(item, depth + 1)
                    elif item.is_file():
                        if extension and item.suffix.lower() != extension.lower():
                            continue
                        if name and name.lower() not in item.name.lower():
                            continue
                        try:
                            size = _format_size(item.stat().st_size)
                        except (OSError, PermissionError):
                            size = "?"
                        results.append(f"📄 {item.name} ({size}) — {item.parent}")
            except (PermissionError, OSError):
                pass

        _search(search_path, 0)

        if not results:
            query = name or extension or "files"
            return f"No {query} found in {search_path.name}/"

        return f"Found {len(results)} file(s):\n" + "\n".join(results)

    except Exception as e:
        return f"Search error: {e}"


# [FIX-5] Depth-limited + memory-safe largest files search
def get_largest_files(path: str = "downloads", count: int = 10) -> str:
    count = min(count, 50)
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return f"Access denied: {search_path}"
        if not search_path.exists():
            return f"Path not found: {path}"

        files = []

        def _collect(directory: Path, depth: int):
            if depth > MAX_SEARCH_DEPTH:
                return
            try:
                for item in directory.iterdir():
                    if item.is_dir() and not item.name.startswith(".") and not item.is_symlink():
                        _collect(item, depth + 1)
                    elif item.is_file():
                        try:
                            files.append((item.stat().st_size, item))
                        except (OSError, PermissionError):
                            continue
            except (PermissionError, OSError):
                pass

        _collect(search_path, 0)
        files.sort(reverse=True)
        top = files[:count]

        if not top:
            return "No files found."

        lines = [f"Top {len(top)} largest files in {search_path.name}/:"]
        for size, f in top:
            lines.append(f"  {_format_size(size):>10}  {f.name}  ({f.parent})")

        return "\n".join(lines)

    except Exception as e:
        return f"Error: {e}"


def get_disk_usage(path: str = "home") -> str:
    try:
        target = _resolve_path(path)
        usage  = shutil.disk_usage(target)
        pct    = usage.used / usage.total * 100
        return (
            f"Disk usage ({target}):\n"
            f"  Total : {_format_size(usage.total)}\n"
            f"  Used  : {_format_size(usage.used)} ({pct:.1f}%)\n"
            f"  Free  : {_format_size(usage.free)}"
        )
    except Exception as e:
        return f"Could not get disk usage: {e}"


# [FIX-8] Removed duplicate organize_desktop — use desktop.py's version
# This function is kept as a lightweight fallback only
def organize_desktop() -> str:
    type_map = {
        "Images":    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic"},
        "Documents": {".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx",
                      ".ppt", ".pptx", ".csv", ".odt", ".ods", ".odp"},
        "Videos":    {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
        "Music":     {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
        "Archives":  {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
        "Code":      {".py", ".js", ".ts", ".html", ".css", ".json", ".xml",
                      ".cpp", ".java", ".cs", ".go", ".rs", ".sh"},
    }

    # [FIX-8] Skip shortcut files
    skip_exts = {".lnk", ".url", ".webloc", ".desktop"}

    desktop = _get_desktop()
    moved, skipped = [], []

    try:
        for item in desktop.iterdir():
            if item.is_dir() or item.name.startswith("."):
                continue
            if item.suffix.lower() in skip_exts:
                continue

            ext        = item.suffix.lower()
            target_dir = desktop / "Others"
            for folder, exts in type_map.items():
                if ext in exts:
                    target_dir = desktop / folder
                    break

            target_dir.mkdir(exist_ok=True)
            new_path = target_dir / item.name

            if new_path.exists():
                skipped.append(item.name)
                continue

            shutil.move(str(item), str(new_path))
            moved.append(f"{item.name} → {target_dir.name}/")

        result = f"Desktop organized: {len(moved)} files moved."
        if moved:
            result += "\n" + "\n".join(moved[:10])
            if len(moved) > 10:
                result += f"\n... and {len(moved) - 10} more."
        if skipped:
            result += f"\n{len(skipped)} file(s) skipped (name conflict)."
        return result

    except Exception as e:
        return f"Could not organize desktop: {e}"


def get_file_info(path: str, name: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Not found: {target.name}"

        stat = target.stat()
        info = {
            "Name":      target.name,
            "Type":      "Folder" if target.is_dir() else "File",
            "Size":      _format_size(stat.st_size),
            "Location":  str(target.parent),
            "Created":   datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
            "Modified":  datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "Extension": target.suffix or "—",
        }

        # Add file count for directories
        if target.is_dir():
            try:
                count = sum(1 for _ in target.iterdir())
                info["Contents"] = f"{count} items"
            except PermissionError:
                info["Contents"] = "Permission denied"

        return "\n".join(f"  {k}: {v}" for k, v in info.items())

    except Exception as e:
        return f"Could not get file info: {e}"


def find_duplicates(path: str = "home", extension: str = "") -> str:
    """Find duplicate files by size and name."""
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return f"Access denied: {search_path}"

        if extension and not extension.startswith("."):
            extension = "." + extension

        # Group by (name, size)
        file_groups: dict[tuple, list] = {}

        def _scan(directory: Path, depth: int):
            if depth > MAX_SEARCH_DEPTH:
                return
            try:
                for item in directory.iterdir():
                    if item.is_dir() and not item.name.startswith(".") and not item.is_symlink():
                        _scan(item, depth + 1)
                    elif item.is_file():
                        if extension and item.suffix.lower() != extension.lower():
                            continue
                        try:
                            key = (item.name.lower(), item.stat().st_size)
                            if key not in file_groups:
                                file_groups[key] = []
                            file_groups[key].append(item)
                        except (OSError, PermissionError):
                            continue
            except (PermissionError, OSError):
                pass

        _scan(search_path, 0)

        # Filter to groups with duplicates
        duplicates = {k: v for k, v in file_groups.items() if len(v) > 1}

        if not duplicates:
            return "No duplicate files found."

        lines = [f"Found {len(duplicates)} duplicate group(s):"]
        for (name, size), paths in sorted(duplicates.items()):
            lines.append(f"\n  {name} ({_format_size(size)}):")
            for p in paths[:5]:
                lines.append(f"    - {p.parent}")
            if len(paths) > 5:
                lines.append(f"    ... and {len(paths) - 5} more")

        return "\n".join(lines)

    except Exception as e:
        return f"Duplicate search error: {e}"


def batch_rename(path: str, pattern: str, replacement: str,
                 extension: str = "") -> str:
    """Batch rename files using pattern matching."""
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return f"Access denied: {search_path}"
        if not search_path.exists():
            return f"Path not found: {path}"

        if extension and not extension.startswith("."):
            extension = "." + extension

        renamed = []
        for item in search_path.iterdir():
            if not item.is_file():
                continue
            if extension and item.suffix.lower() != extension.lower():
                continue

            new_name = item.name.replace(pattern, replacement)
            if new_name != item.name:
                new_path = item.parent / new_name
                if not new_path.exists():
                    item.rename(new_path)
                    renamed.append(f"{item.name} → {new_name}")

        if not renamed:
            return f"No files matched pattern '{pattern}'."

        result = f"Renamed {len(renamed)} file(s):"
        for r in renamed[:10]:
            result += f"\n  {r}"
        if len(renamed) > 10:
            result += f"\n  ... and {len(renamed) - 10} more"
        return result

    except Exception as e:
        return f"Batch rename error: {e}"


def file_controller(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "").lower().strip()
    path   = params.get("path", "desktop")
    name   = params.get("name", "")

    if player:
        player.write_log(f"[file] {action} {name or path}")

    try:
        if action == "list":
            return list_files(path)

        elif action == "create_file":
            return create_file(path, name=name, content=params.get("content", ""))

        elif action == "create_folder":
            return create_folder(path, name=name)

        elif action == "delete":
            return delete_file(path, name=name)

        elif action == "move":
            return move_file(path, name=name, destination=params.get("destination", ""))

        elif action == "copy":
            return copy_file(path, name=name, destination=params.get("destination", ""))

        elif action == "rename":
            return rename_file(path, name=name, new_name=params.get("new_name", ""))

        elif action == "read":
            return read_file(path, name=name)

        elif action == "write":
            return write_file(
                path, name=name,
                content=params.get("content", ""),
                append=params.get("append", False)
            )

        elif action == "find":
            return find_files(
                name=name or params.get("name", ""),
                extension=params.get("extension", ""),
                path=path,
                max_results=min(int(params.get("max_results", 20)), 50),
            )

        elif action == "largest":
            return get_largest_files(
                path=path,
                count=int(params.get("count", 10)),
            )

        elif action == "disk_usage":
            return get_disk_usage(path)

        elif action == "organize_desktop":
            return organize_desktop()

        elif action == "info":
            return get_file_info(path, name=name)

        elif action == "find_duplicates":
            return find_duplicates(path=path, extension=params.get("extension", ""))

        elif action == "batch_rename":
            return batch_rename(
                path=path,
                pattern=params.get("pattern", ""),
                replacement=params.get("replacement", ""),
                extension=params.get("extension", ""),
            )

        else:
            return f"Unknown action: '{action}'"

    except Exception as e:
        return f"File controller error ({action}): {e}"
