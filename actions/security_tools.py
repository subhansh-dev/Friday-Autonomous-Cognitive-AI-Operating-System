# FRIDAY Cyber Security Tools Action Module (patched v2.1)
# Changes from v2.0:
#   [FIX] Added missing `import shutil`
#   [FIX] _run_ps_streaming: fixed indentation crash, stray 's', ps_kit→PS_KIT
#   [FIX] _run_ps_streaming: added encoding='utf-8' and errors='replace' for UTF-16 fix
#   [FIX] _run_ps_streaming: added creationflags to hide PS window

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── MCP Client ──────────────────────────────────────────────────────
try:
    from security.security_mcp_client import get_mcp_client, CyberMCPClient
    _mcp = get_mcp_client()
except ImportError:
    _mcp = None

# ── Security guards ──────────────────────────────────────────────────
try:
    from security.tools_guard import check_ssrf, get_rate_limiter, check_path_traversal
    from security.input_sanitizer import sanitize_shell_input, validate_url
    _guards_available = True
except ImportError:
    _guards_available = False

BASE_DIR = Path(__file__).resolve().parent.parent
PS_KIT = BASE_DIR / "cyber" / "powershell_kit.ps1"

WSL_DISTRO = os.environ.get("FRIDAY_WSL_DISTRO", "kali-linux")

# Full paths — work from any venv
WSL_EXE = r"C:\Windows\System32\wsl.exe"
POWERSHELL_EXE = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

# ── Platform detection ──────────────────────────────────────────────
IS_LINUX = sys.platform.startswith("linux")
IS_WINDOWS = sys.platform == "win32"

# Native wordlist paths (Linux/Kali)
_NATIVE_WORDLISTS = [
    "/usr/share/wordlists/dirb/common.txt",
    "/usr/share/dirb/wordlists/common.txt",
    "/usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt",
    "/usr/share/seclists/Discovery/Web-Content/common.txt",
]

def _find_wordlist(name: str = None) -> str:
    """Find a wordlist on the system."""
    if name and Path(name).exists():
        return name
    for wl in _NATIVE_WORDLISTS:
        if Path(wl).exists():
            return wl
    return "/usr/share/wordlists/dirb/common.txt"  # default fallback

def _tool_available(tool_name: str) -> bool:
    """Check if a tool is available on PATH."""
    return shutil.which(tool_name) is not None

# ── Streaming state ────────────────────────────────────────────────
_active_player = None  # Set by security_tools() entry point


def _safe_log(player, msg: str):
    """Safely write to player log from background thread."""
    try:
        if player and hasattr(player, 'write_log'):
            player.write_log(msg)
    except Exception:
        pass


# ── Cached state ────────────────────────────────────────────────────
_wsl_checked = False
_wsl_available = False


def _reset_wsl_cache() -> None:
    global _wsl_checked, _wsl_available
    _wsl_checked = False
    _wsl_available = False


def _clean_wsl_output(raw: str) -> str:
    """Strip null bytes from WSL UTF-16LE output."""
    cleaned = raw.replace('\x00', '').replace('\r', '')
    return cleaned.strip()


def _check_wsl() -> bool:
    """Detect WSL distro with proper encoding handling."""
    global _wsl_checked, _wsl_available
    if _wsl_checked:
        return _wsl_available

    for wsl_cmd in [WSL_EXE, "wsl"]:
        try:
            for encoding in ("utf-16", "utf-8"):
                try:
                    r = subprocess.run(
                        [wsl_cmd, "--list"],
                        capture_output=True,
                        text=True,
                        encoding=encoding,
                        errors='replace',
                        timeout=10,
                    )
                    stdout_clean = _clean_wsl_output(r.stdout)
                    if stdout_clean:
                        distro_lower = WSL_DISTRO.lower()
                        stdout_lower = stdout_clean.lower()
                        if distro_lower in stdout_lower:
                            _wsl_available = True
                            _wsl_checked = True
                            return True
                        distro_base = distro_lower.split("-")[0]
                        if distro_base in stdout_lower:
                            _wsl_available = True
                            _wsl_checked = True
                            return True
                except (UnicodeDecodeError, UnicodeError):
                    continue

            # Raw bytes fallback
            r = subprocess.run(
                [wsl_cmd, "--list"],
                capture_output=True,
                timeout=10,
            )
            stdout_clean = _clean_wsl_output(
                r.stdout.decode("utf-16-le", errors="ignore"))
            if WSL_DISTRO.lower() in stdout_clean.lower():
                _wsl_available = True
                _wsl_checked = True
                return True

        except FileNotFoundError:
            continue
        except Exception:
            continue

    _wsl_available = False
    _wsl_checked = True
    return False



def _get_wsl_list_raw() -> str:
    """Debug helper."""
    for wsl_cmd in [WSL_EXE, "wsl"]:
        try:
            r = subprocess.run(
                [wsl_cmd, "--list"],
                capture_output=True, timeout=10,
            )
            raw_hex = r.stdout[:200].hex()
            decoded = _clean_wsl_output(
                r.stdout.decode("utf-16-le", errors="ignore"))
            return (
                f"Command: {wsl_cmd}\n"
                f"Return code: {r.returncode}\n"
                f"Raw bytes (hex): {raw_hex}\n"
                f"Decoded: {decoded}"
            )
        except FileNotFoundError:
            continue
        except Exception as e:
            return f"Error: {e}"
    return "WSL not found"


# ── Input validation ────────────────────────────────────────────────
_IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
_SHELL_META_QUOTE = set(";&|`$()\n\r\\")


def _safe_quote(s: str) -> str:
    """Quote a string safely for shell commands on both Windows and Unix."""
    if not s:
        return "''"
    if sys.platform == "win32":
        return "'" + s.replace("'", "'\\''") + "'"
    return shlex.quote(s)


def _detect_target_type(target: str) -> str:
    target = target.strip()
    if target.startswith("http://") or target.startswith("https://"):
        return "url"
    if _IP_RE.match(target):
        return "ip"
    if re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", target):
        return "domain"
    return "unknown"


def _validate_target(target: str, expected_types: tuple[str, ...] = None) -> str | None:
    if not target:
        return "No target specified."
    if any(c in target for c in _SHELL_META_QUOTE):
        return f"Target contains invalid characters: {target}"
    target_type = _detect_target_type(target)
    if target_type == "unknown":
        return f"'{target}' doesn't look like a valid URL, IP, or domain."
    if expected_types and target_type not in expected_types:
        return f"Expected {', '.join(expected_types)}, got: {target}"
    if len(target) > 512:
        return "Target is too long (max 512 characters)."
    return None


def _validate_flags(flags: str) -> str | None:
    if not flags:
        return None
    safe_pattern = re.compile(r'^[a-zA-Z0-9\-_ ./=,]+$')
    if not safe_pattern.match(flags):
        return f"Flags contain invalid characters: {flags}"
    if len(flags) > 256:
        return "Flags string too long (max 256 characters)."
    return None


def _format_result(raw: str, max_len: int = 1500) -> str:
    if not raw:
        return "No results."
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            if "error" in data:
                return f"Error: {data['error']}"
            pretty = json.dumps(data, indent=2)
            if len(pretty) <= max_len:
                return pretty
            lines = pretty.split("\n")
            result = []
            total = 0
            for line in lines:
                if total + len(line) + 1 > max_len - 20:
                    result.append("  ... (truncated)")
                    break
                result.append(line)
                total += len(line) + 1
            return "\n".join(result)
        if isinstance(data, list):
            pretty = json.dumps(data, indent=2)
            if len(pretty) <= max_len:
                return pretty
            lines = pretty.split("\n")
            result = []
            total = 0
            for line in lines:
                if total + len(line) + 1 > max_len - 20:
                    result.append("  ... (truncated)")
                    break
                result.append(line)
                total += len(line) + 1
            return "\n".join(result)
        return str(data)[:max_len]
    except (json.JSONDecodeError, TypeError):
        return raw.strip()[:max_len]


# ── Streaming execution ─────────────────────────────────────────────

_SPINNER = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']


def _kill_proc_tree(proc):
    """Force-kill a process and all its children on Windows."""
    try:
        import signal
        proc.kill()
    except Exception:
        pass
    # On Windows, also kill child processes via taskkill
    if sys.platform == "win32" and proc.poll() is None:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=5)
        except Exception:
            pass


def _run_wsl_streaming(cmd: str, timeout: int = 120) -> str:
    """Run WSL command with real-time output streaming to UI."""
    player = _active_player

    for wsl_exe in [WSL_EXE, "wsl"]:
        try:
            proc = subprocess.Popen(
                [wsl_exe, "-d", WSL_DISTRO, "--", "bash", "-c", cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )

            output_lines = []
            start_time = time.time()
            done_event = threading.Event()

            _safe_log(player, f"[Cyber] ▶ {cmd[:100]}...")

            def _reader():
                try:
                    for line in proc.stdout:
                        line = line.rstrip('\n\r')
                        if not line:
                            continue
                        output_lines.append(line)
                        count = len(output_lines)
                        if count <= 30 or count % 5 == 0:
                            _safe_log(player, f"[Cyber] │ {line[:150]}")
                except Exception:
                    pass
                finally:
                    done_event.set()

            def _progress():
                i = 0
                while not done_event.wait(5):
                    elapsed = time.time() - start_time
                    lines = len(output_lines)
                    _safe_log(
                        player,
                        f"[Cyber] {_SPINNER[i % len(_SPINNER)]} "
                        f"Running... ({elapsed:.0f}s, {lines} lines)")
                    i += 1
                    if elapsed > timeout:
                        _safe_log(player, f"[Cyber] ✗ Timeout — force killing")
                        _kill_proc_tree(proc)
                        done_event.set()
                        break

            reader = threading.Thread(target=_reader, daemon=True)
            progress = threading.Thread(target=_progress, daemon=True)
            reader.start()
            progress.start()

            reader.join(timeout=timeout + 5)

            if reader.is_alive():
                _kill_proc_tree(proc)
                done_event.set()
                _safe_log(player, "[Cyber] ✗ Timed out")
                return json.dumps({"error": f"Timed out after {timeout}s"})

            done_event.set()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _kill_proc_tree(proc)

            elapsed = time.time() - start_time
            full_output = '\n'.join(output_lines)

            if proc.returncode != 0 and not full_output.strip():
                _safe_log(player, f"[Cyber] ✗ Failed (exit {proc.returncode}, {elapsed:.1f}s)")
                return json.dumps({
                    "error": f"Exit code {proc.returncode}",
                })

            _safe_log(
                player,
                f"[Cyber] ✓ Done ({elapsed:.1f}s, "
                f"{len(output_lines)} lines)")

            return full_output if full_output.strip() else json.dumps({"result": "Done."})

        except FileNotFoundError:
            continue
        except Exception as e:
            done_event.set()
            _safe_log(player, f"[Cyber] ✗ Error: {e}")
            return json.dumps({"error": str(e)})

    return json.dumps({"error": "WSL not found"})


def _run_ps_streaming(cmd: str, params_json: str = "{}") -> str:
    """Run PowerShell command with real-time output streaming to UI."""
    player = _active_player

    if not PS_KIT.exists():
        return json.dumps({"error": f"PowerShell kit not found: {PS_KIT}"})

    ps_candidates = [POWERSHELL_EXE]
    found = shutil.which("powershell")
    if found:
        ps_candidates.append(found)
    found_core = shutil.which("pwsh")
    if found_core:
        ps_candidates.append(found_core)
    ps_candidates.extend(["powershell", "pwsh"])

    for ps_path in ps_candidates:
        if not Path(ps_path).exists() and ps_path not in ("powershell", "pwsh"):
            continue

        try:
            proc = subprocess.Popen(
                [ps_path, "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(PS_KIT), cmd, params_json],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            output_lines = []
            start_time = time.time()
            done_event = threading.Event()

            _safe_log(player, f"[Cyber] ▶ PowerShell: {cmd}")

            def _reader():
                try:
                    for line in proc.stdout:
                        line = line.rstrip('\n\r')
                        if not line:
                            continue
                        output_lines.append(line)
                        count = len(output_lines)
                        if count <= 30 or count % 5 == 0:
                            _safe_log(player, f"[Cyber] │ {line[:150]}")
                except Exception:
                    pass
                finally:
                    done_event.set()

            def _progress():
                i = 0
                while not done_event.wait(5):
                    elapsed = time.time() - start_time
                    _safe_log(
                        player,
                        f"[Cyber] {_SPINNER[i % len(_SPINNER)]} "
                        f"PowerShell running... ({elapsed:.0f}s)")
                    i += 1
                    if elapsed > 120:
                        _safe_log(player, "[Cyber] ✗ PS timeout — force killing")
                        _kill_proc_tree(proc)
                        done_event.set()
                        break

            reader = threading.Thread(target=_reader, daemon=True)
            progress = threading.Thread(target=_progress, daemon=True)
            reader.start()
            progress.start()

            reader.join(timeout=130)

            if reader.is_alive():
                proc.kill()
                done_event.set()
                _safe_log(player, "[Cyber] ✗ PowerShell timed out")
                return json.dumps({"error": "Timed out (120s)"})

            done_event.set()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

            elapsed = time.time() - start_time
            full_output = '\n'.join(output_lines)

            if proc.returncode != 0 and not full_output.strip():
                _safe_log(player, f"[Cyber] ✗ PS failed (exit {proc.returncode})")
                return json.dumps({
                    "error": f"Exit code {proc.returncode}",
                })

            _safe_log(player, f"[Cyber] ✓ PowerShell done ({elapsed:.1f}s)")

            # Try to find JSON in output
            for line in full_output.split("\n"):
                line = line.strip()
                if line.startswith("{") or line.startswith("["):
                    try:
                        json.loads(line)
                        return line
                    except json.JSONDecodeError:
                        continue

            return full_output[:1000] if full_output.strip() else json.dumps({"result": "Done."})

        except FileNotFoundError:
            continue
        except Exception as e:
            done_event.set()
            return json.dumps({"error": str(e)})

    return json.dumps({"error": "PowerShell not found"})


# ── Non-streaming fallback (for MCP server or no player) ───────────

def _run_native_streaming(cmd: str, timeout: int = 120) -> str:
    """Run command natively on Linux with real-time output streaming to UI."""
    player = _active_player

    try:
        proc = subprocess.Popen(
            ["bash", "-c", cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace',
        )

        output_lines = []
        start_time = time.time()
        done_event = threading.Event()

        _safe_log(player, f"[Cyber] ▶ {cmd[:100]}...")

        def _reader():
            try:
                for line in proc.stdout:
                    line = line.rstrip('\n\r')
                    if not line:
                        continue
                    output_lines.append(line)
                    count = len(output_lines)
                    if count <= 30 or count % 5 == 0:
                        _safe_log(player, f"[Cyber] │ {line[:150]}")
            except Exception:
                pass
            finally:
                done_event.set()

        def _progress():
            i = 0
            while not done_event.wait(5):
                elapsed = time.time() - start_time
                lines = len(output_lines)
                _safe_log(
                    player,
                    f"[Cyber] {_SPINNER[i % len(_SPINNER)]} "
                    f"Running... ({elapsed:.0f}s, {lines} lines)")
                i += 1
                if elapsed > timeout:
                    _safe_log(player, f"[Cyber] ✗ Timeout — force killing")
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    done_event.set()
                    break

        reader = threading.Thread(target=_reader, daemon=True)
        progress = threading.Thread(target=_progress, daemon=True)
        reader.start()
        progress.start()

        reader.join(timeout=timeout + 5)

        if reader.is_alive():
            try:
                proc.kill()
            except Exception:
                pass
            done_event.set()
            _safe_log(player, "[Cyber] ✗ Timed out")

        proc.wait(timeout=5)
        output = "\n".join(output_lines)

        if proc.returncode != 0 and not output:
            return json.dumps({"error": f"Exit code {proc.returncode}"})
        return output.strip() if output.strip() else json.dumps({"result": "Done."})

    except Exception as e:
        return json.dumps({"error": str(e)})


def _run_native(cmd: str, timeout: int = 120) -> str:
    """Run command natively on Linux. Uses streaming if _active_player is set."""
    if _active_player:
        return _run_native_streaming(cmd, timeout)

    try:
        r = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True, text=True, timeout=timeout,
            encoding='utf-8', errors='replace',
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode != 0:
            return json.dumps({
                "error": err or f"Exit code {r.returncode}",
                "output": out[:500],
            })
        return out if out else json.dumps({"result": "Done."})
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Timed out after {timeout}s"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _run_wsl(cmd: str, timeout: int = 120) -> str:
    """Run WSL command (Windows) or native command (Linux)."""
    # On Linux, run natively
    if IS_LINUX:
        return _run_native(cmd, timeout)

    # On Windows, use WSL
    if _active_player:
        return _run_wsl_streaming(cmd, timeout)

    for wsl_exe in [WSL_EXE, "wsl"]:
        try:
            full_cmd = [wsl_exe, "-d", WSL_DISTRO, "--", "bash", "-c", cmd]
            r = subprocess.run(
                full_cmd,
                capture_output=True, text=True, timeout=timeout,
            )
            out = (r.stdout or "").strip()
            err = (r.stderr or "").strip()
            if r.returncode != 0:
                return json.dumps({
                    "error": err or f"Exit code {r.returncode}",
                    "output": out[:500],
                })
            return out if out else json.dumps({"result": "Done."})
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            return json.dumps({"error": f"Timed out after {timeout}s"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    return json.dumps({"error": "WSL not found"})


def _run_powershell(cmd: str, params: dict = None) -> str:
    """Run PowerShell command. Uses streaming if _active_player is set."""
    if _active_player:
        return _run_ps_streaming(cmd, json.dumps(params or {}))

    if not PS_KIT.exists():
        return json.dumps({"error": f"PowerShell kit not found: {PS_KIT}"})

    params_json = json.dumps(params or {})
    ps_candidates = [POWERSHELL_EXE]
    found = shutil.which("powershell")
    if found:
        ps_candidates.append(found)
    ps_candidates.append("powershell")

    for ps_cmd in ps_candidates:
        if not Path(ps_cmd).exists() and ps_cmd != "powershell":
            continue
        try:
            r = subprocess.run(
                [ps_cmd, "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(PS_KIT), cmd, params_json],
                capture_output=True, text=True,
                encoding='utf-8', errors='replace',
                timeout=120,
            )
            out = r.stdout.strip()
            err = r.stderr.strip()
            if r.returncode != 0 and not out:
                return json.dumps({"error": err or f"Exit code {r.returncode}"})
            for line in out.split("\n"):
                line = line.strip()
                if line.startswith("{") or line.startswith("["):
                    return line
            return out[:1000] if out else "Command completed."
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            return json.dumps({"error": "Timed out (120s)"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    return json.dumps({"error": "PowerShell not found"})


def _via_mcp_or_wsl(mcp_method: str, params: dict, wsl_cmd: str) -> str:
    """Try MCP server first, fall back to native/WSL execution."""
    if _mcp and _mcp.is_running:
        try:
            result = _mcp.call(mcp_method, params, timeout=120)
            return _format_result(result)
        except Exception as e:
            _safe_log(_active_player, f"[Cyber] MCP failed, falling back: {e}")
    # On Linux, run natively
    if IS_LINUX:
        return _format_result(_run_native(wsl_cmd))
    # On Windows, use WSL
    if _check_wsl():
        return _format_result(_run_wsl(wsl_cmd))
    return (
        f"WSL Kali Linux not detected. Distro: '{WSL_DISTRO}'\n"
        f"Install with: wsl --install -d kali-linux\n"
        f"Use action 'debug_wsl' to troubleshoot."
    )


# ── Public API ──────────────────────────────────────────────────────

def security_tools(parameters: dict, player=None, **kwargs) -> str:
    """
    Main entry point for all FRIDAY cybersecurity tool calls.
    When player is provided, streams output in real-time to the UI.
    """
    global _active_player
    _active_player = player  # Enable streaming for this call

    try:
        return _handle_security_action(parameters)
    finally:
        _active_player = None  # Clean up


def _handle_security_action(parameters: dict) -> str:
    """Internal handler — separated so _active_player is always cleaned up."""
    action = (parameters.get("action") or "").strip().lower()
    target = (parameters.get("target") or "").strip()
    ports = parameters.get("ports", "")
    flags = parameters.get("flags", "")
    wordlist = parameters.get("wordlist", "")
    urls_str = parameters.get("urls", "")
    domains_str = parameters.get("domains", "")
    script = parameters.get("script", "")
    depth = parameters.get("depth", 1)

    _ACTIONS_LIST = (
        "health, check_tools, debug_wsl, port_scan, port_scan_ps, "
        "nmap_scan, nmap_script, subdomain_enum, subfinder, httpx_probe, "
        "dns_info, dnsx, ssl_info, whois, web_fuzz_ps, ffuf, gobuster, "
        "nuclei, sqlmap, whatweb, wpscan, gospider, http_archive, "
        "url_parse, extract_domains, extract_urls, start_mcp, stop_mcp, "
        "reset_wsl, nikto, katana, naabu, header_check, cors_check, "
        "recon_full, mythos_scan, cyber_scan"
    )

    if not action:
        return f"Please specify a security action. Available: {_ACTIONS_LIST}"

    flags_err = _validate_flags(flags)
    if flags_err:
        return flags_err

    # ── Security guard checks ────────────────────────────────────
    if _guards_available:
        # Rate limiting
        rate_err = get_rate_limiter().check(f"security_{action}", max_calls=50, window_seconds=60)
        if rate_err:
            return rate_err

        # SSRF check for URL/domain targets
        if target and action in ("ffuf", "gobuster", "nuclei", "sqlmap",
                                  "whatweb", "wpscan", "gospider",
                                  "httpx_probe", "web_fuzz_ps"):
            ssrf_err = check_ssrf(target)
            if ssrf_err:
                return ssrf_err
            url_err = validate_url(target)
            if url_err and action in ("ffuf", "gobuster", "nuclei", "sqlmap", "web_fuzz_ps"):
                return url_err

        # Path traversal check for wordlist
        if wordlist:
            traversal_err = check_path_traversal(wordlist)
            if traversal_err:
                return traversal_err

    # ── Authorization gate for ALL live network operations ──────
    LIVE_ACTIONS = {
        "port_scan", "port_scan_ps", "nmap_scan", "nmap_script",
        "subdomain_enum", "subfinder", "httpx_probe",
        "dns_info", "dnsx", "ssl_info", "whois",
        "web_fuzz_ps", "ffuf", "gobuster",
        "nuclei", "sqlmap", "whatweb", "wpscan", "gospider",
        "http_archive", "nikto", "katana", "naabu",
        "header_check", "cors_check", "recon_full",
    }
    if action in LIVE_ACTIONS:
        from cyber.authorization import require_authorization, AuthorizationError
        auth_target = target or urls_str or domains_str
        if auth_target:
            try:
                require_authorization(auth_target, action)
            except AuthorizationError as e:
                return str(e)

    # ── Health / Status ──────────────────────────────────────────
    if action == "health":
        wsl_ok = _check_wsl() if IS_WINDOWS else False
        # Check native tools on Linux
        native_tools = {}
        if IS_LINUX:
            for tool in ["nmap", "nikto", "sqlmap", "nuclei", "ffuf", "gobuster",
                         "subfinder", "httpx", "dnsx", "whatweb", "wpscan", "naabu",
                         "katana", "hydra", "john", "whois", "dig", "curl", "openssl"]:
                native_tools[tool] = _tool_available(tool)
        return json.dumps({
            "status": "ready",
            "platform": "linux" if IS_LINUX else "windows",
            "wsl_kali": wsl_ok,
            "native_execution": IS_LINUX,
            "native_tools": native_tools if IS_LINUX else None,
            "mcp_available": _mcp is not None,
            "mcp_running": _mcp.is_running if _mcp else False,
            "ps_kit": PS_KIT.exists(),
            "wsl_distro": WSL_DISTRO,
            "streaming": True,
        }, indent=2)

    if action == "debug_wsl":
        raw = _get_wsl_list_raw()
        wsl_ok = _check_wsl()
        return (
            f"WSL Available: {wsl_ok}\n"
            f"WSL Distro: {WSL_DISTRO}\n"
            f"WSL Exe: {WSL_EXE} (exists: {Path(WSL_EXE).exists()})\n"
            f"Raw detection output:\n{raw}"
        )

    if action == "check_tools":
        if _mcp and _mcp.is_running:
            return _format_result(_mcp.call("check_wsl_tools", timeout=30))
        if IS_LINUX:
            tools = {
                "nmap": _tool_available("nmap"),
                "nikto": _tool_available("nikto"),
                "sqlmap": _tool_available("sqlmap"),
                "nuclei": _tool_available("nuclei"),
                "ffuf": _tool_available("ffuf"),
                "gobuster": _tool_available("gobuster"),
                "subfinder": _tool_available("subfinder"),
                "httpx": _tool_available("httpx"),
                "dnsx": _tool_available("dnsx"),
                "whatweb": _tool_available("whatweb"),
                "wpscan": _tool_available("wpscan"),
                "naabu": _tool_available("naabu"),
                "katana": _tool_available("katana"),
                "hydra": _tool_available("hydra"),
                "john": _tool_available("john"),
                "whois": _tool_available("whois"),
                "dig": _tool_available("dig"),
                "curl": _tool_available("curl"),
                "openssl": _tool_available("openssl"),
            }
            available = [k for k, v in tools.items() if v]
            missing = [k for k, v in tools.items() if not v]
            lines = [
                f"Platform: Linux (native execution)",
                f"Available ({len(available)}): {', '.join(available)}",
            ]
            if missing:
                lines.append(f"Missing ({len(missing)}): {', '.join(missing)}")
                lines.append("Install missing tools with: apt install <tool> or go install/github releases")
            return "\n".join(lines)
        wsl_ok = _check_wsl()
        if not wsl_ok:
            return (
                "WSL Kali Linux is not detected.\n"
                "Install with: wsl --install -d kali-linux\n"
                "Use action 'debug_wsl' to troubleshoot."
            )
        return _format_result(_run_wsl(
            "which nmap sqlmap nuclei ffuf gobuster subfinder httpx-toolkit "
            "dnsx whatweb wpscan 2>&1 || echo 'Some tools missing'"
        ))

    # ── MCP Server Management ─────────────────────────────────────
    if action == "start_mcp":
        if not _mcp:
            return "MCP client not available."
        return _mcp.start()

    if action == "stop_mcp":
        if not _mcp:
            return "MCP client not available."
        return _mcp.stop()

    if action == "reset_wsl":
        _reset_wsl_cache()
        return "WSL cache reset."

    # ── Port Scanning ──────────────────────────────────────────
    if action == "port_scan":
        err = _validate_target(target, ("ip", "domain"))
        if err:
            return err
        port_flag = f"-p {_safe_quote(ports)}" if ports else "-F"
        return _via_mcp_or_wsl(
            "nmap_scan", {"target": target, "flags": f"-sV {port_flag}"},
            f"nmap -sV {port_flag} {_safe_quote(target)} 2>&1"
        )

    if action == "port_scan_ps":
        err = _validate_target(target, ("ip", "domain"))
        if err:
            return err
        if IS_LINUX:
            p = ports or "21,22,23,25,53,80,110,143,443,445,993,995,1433,1521,2049,2375,3306,3389,5432,5900,6379,8080,8443,9000,27017"
            return _format_result(_run_native(f"nmap -p {_safe_quote(p)} {_safe_quote(target)} 2>&1"))
        return _format_result(_run_powershell("port_scan", {
            "Hostname": target,
            "Ports": ports or "21,22,23,25,53,80,110,143,443,445,993,995,"
                              "1433,1521,2049,2375,3306,3389,5432,5900,6379,"
                              "8080,8443,9000,27017"
        }))

    if action == "nmap_scan":
        err = _validate_target(target, ("ip", "domain"))
        if err:
            return err
        return _via_mcp_or_wsl(
            "nmap_scan", {"target": target, "flags": flags or "-sV -sC -O"},
            f"nmap -sV -sC -O {_safe_quote(target)} 2>&1"
        )

    if action == "nmap_script":
        err = _validate_target(target, ("ip", "domain"))
        if err:
            return err
        safe_script = _safe_quote(script or "vuln")
        return _via_mcp_or_wsl(
            "nmap_script", {"target": target, "script": script or "vuln"},
            f"nmap --script {safe_script} {_safe_quote(target)} 2>&1"
        )

    # ── Subdomain Enumeration ──────────────────────────────────
    if action in ("subdomain_enum", "subfinder"):
        err = _validate_target(target, ("domain",))
        if err:
            return err
        return _via_mcp_or_wsl(
            "subfinder", {"domain": target},
            f"subfinder -d {_safe_quote(target)} -silent 2>&1"
        )

    if action == "httpx_probe":
        urls = urls_str or target
        if not urls:
            return "Specify urls (comma-separated) or a target."
        url_list = [u.strip() for u in urls.split(",") if u.strip()]
        for u in url_list:
            err = _validate_target(u)
            if err:
                return f"Invalid URL '{u}': {err}"
        urls_clean = "\n".join(url_list)
        safe_urls = _safe_quote(urls_clean)
        return _via_mcp_or_wsl(
            "httpx_probe", {"urls": urls_clean},
            f"echo {safe_urls} | httpx-toolkit -silent -status-code -title -tech-detect 2>&1"
        )

    # ── DNS ────────────────────────────────────────────────────
    if action == "dns_info":
        err = _validate_target(target, ("domain",))
        if err:
            return err
        if IS_LINUX:
            safe_t = _safe_quote(target)
            cmd = (
                f"echo '=== A Records ===' && dig +short {safe_t} A 2>&1 && "
                f"echo '=== AAAA Records ===' && dig +short {safe_t} AAAA 2>&1 && "
                f"echo '=== MX Records ===' && dig +short {safe_t} MX 2>&1 && "
                f"echo '=== NS Records ===' && dig +short {safe_t} NS 2>&1 && "
                f"echo '=== TXT Records ===' && dig +short {safe_t} TXT 2>&1 && "
                f"echo '=== CNAME ===' && dig +short {safe_t} CNAME 2>&1 && "
                f"echo '=== SOA ===' && dig +short {safe_t} SOA 2>&1"
            )
            return _format_result(_run_native(cmd))
        return _format_result(_run_powershell("dns_info", {"Domain": target}))

    if action == "dnsx":
        err = _validate_target(target, ("domain",))
        if err:
            return err
        domains = domains_str or target
        domain_list = [d.strip() for d in domains.split(",") if d.strip()]
        for d in domain_list:
            d_err = _validate_target(d, ("domain",))
            if d_err:
                return f"Invalid domain '{d}': {d_err}"
        domains_clean = "\n".join(domain_list)
        safe_domains = _safe_quote(domains_clean)
        return _via_mcp_or_wsl(
            "dnsx_resolve", {"domains": domains_clean},
            f"echo {safe_domains} | dnsx -a -aaaa -cname 2>&1"
        )

    # ── SSL / TLS ──────────────────────────────────────────────
    if action == "ssl_info":
        err = _validate_target(target, ("domain", "url"))
        if err:
            return err
        hostname = target.replace("https://", "").replace("http://", "").split("/")[0]
        if IS_LINUX:
            safe_h = _safe_quote(hostname)
            cmd = (
                f"echo | openssl s_client -connect {safe_h}:443 -servername {safe_h} 2>/dev/null | "
                f"openssl x509 -noout -subject -issuer -dates -serial -fingerprint -ext subjectAltName 2>&1 && "
                f"echo '=== Protocol ===' && "
                f"echo | openssl s_client -connect {safe_h}:443 -servername {safe_h} 2>&1 | grep -E 'Protocol|Cipher|Session-ID'"
            )
            return _format_result(_run_native(cmd))
        return _format_result(_run_powershell("ssl_info", {"Hostname": hostname}))

    # ── Whois ──────────────────────────────────────────────────
    if action == "whois":
        err = _validate_target(target, ("domain", "ip"))
        if err:
            return err
        if IS_LINUX:
            return _format_result(_run_native(f"whois {_safe_quote(target)} 2>&1"))
        return _format_result(_run_powershell("whois", {"Domain": target}))

    # ── Web Fuzzing ────────────────────────────────────────────
    if action == "web_fuzz_ps":
        err = _validate_target(target, ("url", "domain"))
        if err:
            return err
        if IS_LINUX:
            safe_t = _safe_quote(target)
            wl = _find_wordlist(wordlist)
            safe_wl = _safe_quote(wl)
            if _tool_available("ffuf"):
                return _format_result(_run_native(f"ffuf -u {safe_t}/FUZZ -w {safe_wl} -c -t 50 2>&1"))
            elif _tool_available("gobuster"):
                return _format_result(_run_native(f"gobuster dir -u {safe_t} -w {safe_wl} -t 30 2>&1"))
            else:
                return json.dumps({"error": "No fuzzing tools available. Install ffuf or gobuster."})
        params = {"BaseUrl": target}
        if wordlist:
            params["Wordlist"] = wordlist
        return _format_result(_run_powershell("fuzz", params))

    if action == "ffuf":
        err = _validate_target(target, ("url",))
        if err:
            return err
        wl = wordlist or "/usr/share/wordlists/dirb/common.txt"
        safe_target = _safe_quote(target)
        safe_wl = _safe_quote(wl)
        safe_flags = _safe_quote(flags) if flags else "-c -t 50"
        return _via_mcp_or_wsl(
            "ffuf_fuzz", {"url": target, "wordlist": wl, "flags": flags or "-c -t 50"},
            f"ffuf -u {safe_target}/FUZZ -w {safe_wl} {safe_flags} 2>&1"
        )

    if action == "gobuster":
        err = _validate_target(target, ("url", "domain"))
        if err:
            return err
        wl = wordlist or "/usr/share/wordlists/dirb/common.txt"
        safe_target = _safe_quote(target)
        safe_wl = _safe_quote(wl)
        user_flags = flags.strip() if flags else ""
        gobuster_flags = f"{user_flags} -t 30" if user_flags else "-t 30"
        safe_flags = _safe_quote(gobuster_flags)
        return _via_mcp_or_wsl(
            "gobuster_dir", {"url": target, "wordlist": wl, "flags": gobuster_flags},
            f"gobuster dir -u {safe_target} -w {safe_wl} {safe_flags} 2>&1"
        )

    # ── Vulnerability Scanning ─────────────────────────────────
    if action == "nuclei":
        err = _validate_target(target, ("url", "domain", "ip"))
        if err:
            return err
        safe_target = _safe_quote(target)
        nuclei_flags = flags or "-severity low,medium,high,critical -silent"
        safe_flags = _safe_quote(nuclei_flags)
        return _via_mcp_or_wsl(
            "nuclei_scan", {"target": target, "flags": nuclei_flags},
            f"nuclei -u {safe_target} {safe_flags} 2>&1"
        )

    if action == "sqlmap":
        err = _validate_target(target, ("url",))
        if err:
            return err
        safe_target = _safe_quote(target)
        return _via_mcp_or_wsl(
            "sqlmap", {"url": target},
            f"sqlmap -u {safe_target} --batch --output-dir=/tmp/sqlmap_out 2>&1"
        )

    # ── Technology / CMS Detection ──────────────────────────────
    if action == "whatweb":
        err = _validate_target(target, ("url", "domain"))
        if err:
            return err
        safe_target = _safe_quote(target)
        return _via_mcp_or_wsl(
            "whatweb", {"url": target},
            f"whatweb {safe_target} --aggression 1 2>&1"
        )

    if action == "wpscan":
        err = _validate_target(target, ("url", "domain"))
        if err:
            return err
        safe_target = _safe_quote(target)
        return _via_mcp_or_wsl(
            "wpscan", {"url": target},
            f"wpscan --url {safe_target} --no-update 2>&1"
        )

    # ── Crawling / Spider ──────────────────────────────────────
    if action == "gospider":
        err = _validate_target(target, ("url", "domain"))
        if err:
            return err
        safe_target = _safe_quote(target)
        safe_depth = max(1, min(int(depth), 5))
        return _via_mcp_or_wsl(
            "gospider", {"url": target, "flags": f"-c 10 -d {safe_depth}"},
            f"gospider -s {safe_target} -c 10 -d {safe_depth} 2>&1"
        )

    # ── OSINT / Recon ──────────────────────────────────────────
    if action == "http_archive":
        err = _validate_target(target, ("domain",))
        if err:
            return err
        if IS_LINUX:
            safe_t = _safe_quote(target)
            return _format_result(_run_native(
                f"curl -s 'https://web.archive.org/cdx/search/cdx?url={safe_t}/*&output=text&fl=original,statuscode&limit=50' 2>&1"
            ))
        return _format_result(_run_powershell("http_archive", {"Domain": target}))

    # ── Python-native utilities ─────────────────────────────────
    if action == "url_parse":
        if not target:
            return "Specify a URL."
        from urllib.parse import urlparse
        u = urlparse(target)
        return json.dumps({
            "scheme": u.scheme, "hostname": u.hostname, "port": u.port,
            "path": u.path, "query": u.query, "fragment": u.fragment,
        }, indent=2)

    if action == "extract_domains":
        text = parameters.get("text", target)
        if not text:
            return "Specify text to extract domains from."
        domain_re = re.compile(
            r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)"
            r"+(?:com|org|net|io|dev|co|uk|de|fr|tr|ru|cn|jp|br|au|in|"
            r"info|biz|me|tv|cc|us|ca|nl|se|no|fi|dk|pl|cz|es|it|pt|"
            r"gov|edu|mil|xyz|tech|online|site|store|app|cloud)",
            re.IGNORECASE
        )
        domains = list(set(domain_re.findall(text)))
        return json.dumps({"domains": domains, "count": len(domains)}, indent=2)

    if action == "extract_urls":
        text = parameters.get("text", target)
        if not text:
            return "Specify text to extract URLs from."
        urls = list(set(re.findall(r"https?://[^\s<>\"'`|;]+", text)))
        return json.dumps({"urls": urls, "count": len(urls)}, indent=2)

    # ── Nikto Web Scanner ────────────────────────────────────────
    if action == "nikto":
        err = _validate_target(target, ("url", "domain", "ip"))
        if err:
            return err
        safe_target = _safe_quote(target)
        return _via_mcp_or_wsl(
            "nikto", {"target": target},
            f"nikto -h {safe_target} -Tuning 123457890abc 2>&1"
        )

    # ── Katana Crawler ──────────────────────────────────────────
    if action == "katana":
        err = _validate_target(target, ("url", "domain"))
        if err:
            return err
        safe_target = _safe_quote(target)
        safe_depth = max(1, min(int(depth), 5))
        return _via_mcp_or_wsl(
            "katana", {"url": target, "depth": safe_depth},
            f"katana -u {safe_target} -d {safe_depth} -jc -silent 2>&1"
        )

    # ── Naabu Port Scanner ──────────────────────────────────────
    if action == "naabu":
        err = _validate_target(target, ("ip", "domain"))
        if err:
            return err
        safe_target = _safe_quote(target)
        port_flag = f"-p {_safe_quote(ports)}" if ports else "-top-ports 1000"
        return _via_mcp_or_wsl(
            "naabu", {"target": target, "ports": ports},
            f"naabu -host {safe_target} {port_flag} -silent 2>&1"
        )

    # ── HTTP Header Check ───────────────────────────────────────
    if action == "header_check":
        err = _validate_target(target, ("url", "domain"))
        if err:
            return err
        safe_target = _safe_quote(target)
        cmd = (
            f"curl -sI -L --max-time 15 {safe_target} 2>&1 | "
            f"grep -iE 'server:|x-powered-by:|x-frame-options:|"
            f"content-security-policy:|strict-transport-security:|"
            f"x-content-type-options:|x-xss-protection:|"
            f"access-control-allow-origin:|set-cookie:'"
        )
        return _via_mcp_or_wsl("header_check", {"target": target}, cmd)

    # ── CORS Check ──────────────────────────────────────────────
    if action == "cors_check":
        err = _validate_target(target, ("url", "domain"))
        if err:
            return err
        safe_target = _safe_quote(target)
        cmd = (
            f"echo '=== Origin Reflection ===' && "
            f"curl -sI -H 'Origin: https://evil.com' {safe_target} 2>&1 | "
            f"grep -i 'access-control' && "
            f"echo '=== Null Origin ===' && "
            f"curl -sI -H 'Origin: null' {safe_target} 2>&1 | "
            f"grep -i 'access-control' && "
            f"echo '=== Wildcard ===' && "
            f"curl -sI {safe_target} 2>&1 | "
            f"grep -i 'access-control-allow-origin: \\*'"
        )
        return _via_mcp_or_wsl("cors_check", {"target": target}, cmd)

    # ── Full Recon Chain ────────────────────────────────────────
    if action == "recon_full":
        err = _validate_target(target, ("domain",))
        if err:
            return err
        safe_target = _safe_quote(target)
        # Chain: subfinder → httpx → nuclei on live hosts
        cmd = (
            f"echo '[*] Phase 1: Subdomain Enumeration' && "
            f"subfinder -d {safe_target} -silent 2>/dev/null | tee /tmp/friday_subs.txt | wc -l && "
            f"echo '[*] Phase 2: Live Host Probing' && "
            f"cat /tmp/friday_subs.txt | httpx -silent -status-code -title 2>/dev/null | tee /tmp/friday_live.txt | wc -l && "
            f"echo '[*] Phase 3: Technology Detection' && "
            f"cat /tmp/friday_live.txt | awk '{{print $1}}' | head -20 | whatweb --silent 2>/dev/null && "
            f"echo '[*] Phase 4: Nuclei Scan (critical,high)' && "
            f"cat /tmp/friday_live.txt | awk '{{print $1}}' | nuclei -severity critical,high -silent 2>/dev/null && "
            f"echo '[*] Recon Complete'"
        )
        return _format_result(_run_wsl(cmd, timeout=300))

    # ── Mythos Multi-Agent Pipeline ──────────────────────────────
    if action == "mythos_scan":
        if not target:
            return "Please specify a target path for mythos_scan. Example: target='C:/path/to/project'"
        from actions.resilience import validate_target_path
        target_path, err = validate_target_path(target)
        if err:
            return err
        try:
            from cyber.mythos_pipeline import get_mythos_pipeline
            pipeline = get_mythos_pipeline()
            scan_type = parameters.get("scan_type", "full")
            result = pipeline.run(str(target_path), scan_type=scan_type)
            return result.report
        except Exception as e:
            return f"Mythos pipeline error: {e}"

    # ── Full Cyber Pipeline (static + data flow + exploit + business logic) ──
    if action == "cyber_scan":
        if not target:
            return ("Please specify a target. Example: "
                    "target='/path/to/project' for static analysis, or "
                    "target='http://example.com' for full scan with exploit validation.")
        try:
            from cyber.pipeline import get_pipeline
            pipeline = get_pipeline()
            scan_type = parameters.get("scan_type", "full")
            target_url = parameters.get("target_url", "")

            # If target is a URL, use it for exploit validation too
            if target.startswith("http"):
                target_url = target_url or target
                # For URLs, run with exploit validation
                result = pipeline.run(target, scan_type=scan_type,
                                      target_url=target_url)
            else:
                # Local path — static analysis + data flow
                from actions.resilience import validate_target_path
                target_path, err = validate_target_path(target)
                if err:
                    return err
                result = pipeline.run(str(target_path), scan_type=scan_type,
                                      target_url=target_url or None)
            return result.report
        except Exception as e:
            import traceback
            return f"Cyber pipeline error: {e}\n{traceback.format_exc()}"

    return f"Unknown security action: '{action}'. Available: {_ACTIONS_LIST}"
