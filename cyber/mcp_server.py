# -*- coding: utf-8 -*-
"""
mcp_server.py — FRIDAY Cyber Security MCP Server (patched v1.2)
Changes from v1.1:
  [FIX-A] WSL detection handles UTF-16LE null bytes
  [FIX-B] Full paths for wsl.exe and powershell.exe
  [FIX-C] _wsl() uses list form with full path instead of shell=True
  [FIX-D] _check_wsl_tools() handles WSL-unavailable gracefully
"""

import asyncio
import json
import sys
import os
import subprocess
import shutil
import re
import shlex
from pathlib import Path
from urllib.parse import urlparse


# ── Config ──────────────────────────────────────────────────────────

WSL_DISTRO = os.environ.get("FRIDAY_WSL_DISTRO", "kali-linux")
PS_SCRIPT = Path(__file__).parent / "powershell_kit.ps1"

# FIX-B: Full paths — work from any venv
WSL_EXE = r"C:\Windows\System32\wsl.exe"
POWERSHELL_EXE = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"

# Safety limits
MAX_OUTPUT_LEN = 50_000
MAX_TARGET_LEN = 500


# ── Input Sanitization ─────────────────────────────────────────────

def _sanitize_target(target: str) -> str:
    """Sanitize target input — prevent command injection."""
    if not target:
        return ""
    target = target.strip()
    if len(target) > MAX_TARGET_LEN:
        raise ValueError(f"Target too long ({len(target)} chars, max {MAX_TARGET_LEN})")
    dangerous = [';', '|', '&', '$', '`', '\n', '\r', '&&', '||', '$(', '${']
    for ch in dangerous:
        if ch in target:
            raise ValueError(f"Blocked character in target: '{ch}'")
    return target


def _sanitize_url(url: str) -> str:
    """Sanitize URL input."""
    if not url:
        return ""
    url = url.strip()
    if len(url) > MAX_TARGET_LEN:
        raise ValueError(f"URL too long ({len(url)} chars, max {MAX_TARGET_LEN})")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https", ""):
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}")
    dangerous = [';', '|', '&', '`', '\n', '\r', '$(']
    for ch in dangerous:
        if ch in url:
            raise ValueError(f"Blocked character in URL: '{ch}'")
    return url


def _sanitize_wordlist(wordlist: str) -> str:
    """Sanitize wordlist path — prevent path traversal."""
    if not wordlist:
        return "/usr/share/wordlists/dirb/common.txt"
    wl = wordlist.strip()
    if '..' in wl:
        raise ValueError("Path traversal blocked in wordlist")
    # Allow Linux paths (WSL Kali) and Windows paths
    safe_prefixes = [
        '/usr/share/wordlists/',
        '/usr/local/share/wordlists/',
        '/opt/',
        '/tmp/',
        'C:\\', 'D:\\', 'E:\\',  # Windows drives
        'C:/', 'D:/', 'E:/',
    ]
    # Also allow if it looks like a valid wordlist filename (no traversal)
    is_wordlist_file = any(wl.endswith(ext) for ext in ['.txt', '.lst', '.dic', '.wordlist'])
    if not any(wl.startswith(p) for p in safe_prefixes) and not is_wordlist_file:
        raise ValueError(f"Wordlist path not in allowed directories: {wl}")
    return wl


def _sanitize_flags(flags: str) -> str:
    """Sanitize extra flags — block dangerous options."""
    if not flags:
        return ""
    flags = flags.strip()
    dangerous_flags = [
        '--script=', '-iL', '--excludefile', '--resume',
        '-oN', '-oX', '-oG', '-oS', '-oA', '--output-file',
        '--proxy-command', '-e',
    ]
    for df in dangerous_flags:
        if df in flags.lower():
            raise ValueError(f"Blocked dangerous flag: {df}")
    for ch in [';', '|', '&', '`', '\n', '\r']:
        if ch in flags:
            raise ValueError(f"Blocked character in flags: '{ch}'")
    return flags


# ── WSL Detection (FIX-A) ──────────────────────────────────────────

def _clean_wsl_output(raw: str) -> str:
    """FIX-A: Strip null bytes from WSL UTF-16LE output."""
    cleaned = raw.replace('\x00', '').replace('\r', '')
    return cleaned.strip()


_wsl_available_cache = None


def _check_wsl_available() -> bool:
    """FIX-A + FIX-B: Detect WSL with proper encoding handling."""
    global _wsl_available_cache
    if _wsl_available_cache is not None:
        return _wsl_available_cache

    for wsl_cmd in [WSL_EXE, "wsl"]:
        try:
            for encoding in ("utf-16", "utf-8", None):
                try:
                    r = subprocess.run(
                        [wsl_cmd, "--list"],
                        capture_output=True,
                        text=True,
                        encoding=encoding,
                        timeout=10,
                    )
                    stdout_clean = _clean_wsl_output(r.stdout)
                    if stdout_clean and WSL_DISTRO.lower() in stdout_clean.lower():
                        _wsl_available_cache = True
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
                _wsl_available_cache = True
                return True

        except FileNotFoundError:
            continue
        except Exception:
            continue

    _wsl_available_cache = False
    return False


# ── Helper: Run WSL commands (FIX-C) ───────────────────────────────

def _wsl(cmd: str, timeout: int = 120) -> str:
    """FIX-C: Run a command inside WSL Kali using list form."""
    # Try full path first, then bare 'wsl'
    for wsl_exe in [WSL_EXE, "wsl"]:
        try:
            # FIX-C: Use list form instead of shell=True
            full_cmd = [wsl_exe, "-d", WSL_DISTRO, "--", "bash", "-c", cmd]
            r = subprocess.run(
                full_cmd,
                capture_output=True, text=True, timeout=timeout,
            )
            out = (r.stdout or "").strip()[:MAX_OUTPUT_LEN]
            err = (r.stderr or "").strip()[:MAX_OUTPUT_LEN]
            if r.returncode != 0:
                return json.dumps({
                    "error": err or f"Exit code {r.returncode}",
                    "output": out[:500],
                })
            return out if out else json.dumps({
                "result": "Command completed with no output.",
            })
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            return json.dumps({
                "error": f"Command timed out after {timeout}s",
            })
        except Exception as e:
            return json.dumps({"error": str(e)})

    return json.dumps({
        "error": "WSL not found. Install WSL 2 with: wsl --install -d kali-linux",
    })


def _ps(cmd: str, params_json: str = "{}") -> str:
    """FIX-B: Run a PowerShell security tool function with full path."""
    # Try full path first, then shutil.which, then bare 'powershell'
    ps_candidates = [POWERSHELL_EXE]
    found = shutil.which("powershell")
    if found:
        ps_candidates.append(found)
    found_core = shutil.which("pwsh")
    if found_core:
        ps_candidates.append(found_core)
    ps_candidates.append("powershell")
    ps_candidates.append("pwsh")

    for ps_path in ps_candidates:
        if not Path(ps_path).exists() and ps_path not in ("powershell", "pwsh"):
            continue

        if not PS_SCRIPT.exists():
            return json.dumps({
                "error": f"PowerShell script not found: {PS_SCRIPT}",
            })

        try:
            r = subprocess.run(
                [ps_path, "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", str(PS_SCRIPT), cmd, params_json],
                capture_output=True, text=True, timeout=120,
            )
            out = (r.stdout or "").strip()[:MAX_OUTPUT_LEN]
            err = (r.stderr or "").strip()[:MAX_OUTPUT_LEN]
            if r.returncode != 0 and not out:
                return json.dumps({
                    "error": err or f"PowerShell exit code {r.returncode}",
                    "output": out[:500],
                })
            for line in out.split("\n"):
                line = line.strip()
                if line.startswith("{") or line.startswith("["):
                    try:
                        json.loads(line)
                        return line
                    except json.JSONDecodeError:
                        continue
            return out if out else json.dumps({"result": "Command completed."})

        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            return json.dumps({"error": "PowerShell command timed out after 120s"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    return json.dumps({"error": "PowerShell not found on this system."})


def _py(cmd: str, params: dict) -> str:
    """Run Python-native security operations."""
    try:
        if cmd == "url_parse":
            url = params.get("url", "")
            if len(url) > 2048:
                return json.dumps({"error": "URL too long (max 2048 chars)"})
            u = urlparse(url)
            return json.dumps({
                "scheme": u.scheme,
                "hostname": u.hostname,
                "port": u.port,
                "path": u.path,
                "query": u.query,
                "fragment": u.fragment,
                "netloc": u.netloc,
            })

        elif cmd == "extract_domains":
            text = params.get("text", "")[:100_000]
            domains = sorted(set(
                re.findall(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?"
                           r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)*"
                           r"\.[a-zA-Z]{2,}", text)))
            return json.dumps({"domains": domains, "count": len(domains)})

        elif cmd == "extract_urls":
            text = params.get("text", "")[:100_000]
            urls = sorted(set(
                re.findall(r"https?://[^\s<>\"'`]+", text)))
            return json.dumps({"urls": urls, "count": len(urls)})

        elif cmd == "check_wsl_tools":
            return _check_wsl_tools()

        elif cmd == "health":
            return json.dumps({
                "status": "ready",
                "wsl_available": _check_wsl_available(),
                "wsl_distro": WSL_DISTRO,
                "ps_available": any(
                    Path(p).exists() for p in [POWERSHELL_EXE]
                ) or shutil.which("powershell") is not None
                   or shutil.which("pwsh") is not None,
                "python_version": sys.version,
                "server_pid": os.getpid(),
            })

        elif cmd == "validate_target":
            target = params.get("target", "")
            result = {"target": target, "checks": {}}
            local_patterns = [
                'localhost', '127.0.0.1', '0.0.0.0', '::1',
                '192.168.', '10.', '172.16.', '172.17.', '172.18.',
                '172.19.', '172.20.', '172.21.', '172.22.', '172.23.',
                '172.24.', '172.25.', '172.26.', '172.27.', '172.28.',
                '172.29.', '172.30.', '172.31.',
            ]
            target_lower = target.lower()
            is_local = any(p in target_lower for p in local_patterns)
            result["checks"]["is_local"] = is_local
            result["checks"]["blocked"] = is_local
            if is_local:
                result["checks"]["reason"] = (
                    "Target resolves to local/private network. "
                    "Self-targeting is not allowed."
                )
            return json.dumps(result)

        else:
            return json.dumps({"error": f"Unknown Python command: {cmd}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _check_wsl_tools() -> str:
    """FIX-D: Check which Kali tools are installed — handles WSL unavailable."""
    if not _check_wsl_available():
        return json.dumps({
            "error": f"WSL distro '{WSL_DISTRO}' not available",
            "wsl_available": False,
            "hint": "Install with: wsl --install -d kali-linux",
        })

    tools = [
        "nmap", "sqlmap", "nuclei", "ffuf", "gobuster", "subfinder",
        "httpx-toolkit", "gospider", "dnsx", "whatweb", "wpscan",
        "jq", "curl", "openssl", "nikto", "dirb", "hydra",
        "metasploit-framework", "whois", "dig",
    ]
    results = {}
    for tool in tools:
        r = _wsl(
            f"which {tool} 2>/dev/null && echo 'installed' || echo 'not_installed'",
            timeout=10,
        )
        try:
            d = json.loads(r)
            if "error" in d:
                results[tool] = "check_failed"
            else:
                results[tool] = "not_installed"
        except json.JSONDecodeError:
            results[tool] = "installed" if "installed" in r \
                             and "not_installed" not in r else "not_installed"
    return json.dumps({"tools": results, "wsl_available": True})


# ── Safe Command Builders ──────────────────────────────────────────

def _build_nmap(params: dict) -> str:
    target = _sanitize_target(params.get("target", ""))
    if not target:
        return json.dumps({"error": "No target specified"})
    flags = _sanitize_flags(params.get("flags", "-sV -F"))
    return f"nmap {flags} {shlex.quote(target)} 2>&1"


def _build_nuclei(params: dict) -> str:
    target = _sanitize_target(params.get("target", ""))
    if not target:
        return json.dumps({"error": "No target specified"})
    flags = _sanitize_flags(params.get("flags", "-severity low,medium,high,critical"))
    return f"nuclei -u {shlex.quote(target)} {flags} 2>&1"


def _build_sqlmap(params: dict) -> str:
    url = _sanitize_url(params.get("url", ""))
    if not url:
        return json.dumps({"error": "No URL specified"})
    return f"sqlmap -u {shlex.quote(url)} --batch --output-dir=/tmp/sqlmap_out 2>&1"


def _build_ffuf(params: dict) -> str:
    url = _sanitize_url(params.get("url", ""))
    if not url:
        return json.dumps({"error": "No URL specified"})
    wordlist = _sanitize_wordlist(params.get("wordlist", ""))
    flags = _sanitize_flags(params.get("flags", "-c -t 50"))
    return f"ffuf -u {shlex.quote(url + '/FUZZ')} -w {shlex.quote(wordlist)} {flags} 2>&1"


def _build_gobuster_dir(params: dict) -> str:
    url = _sanitize_url(params.get("url", ""))
    if not url:
        return json.dumps({"error": "No URL specified"})
    wordlist = _sanitize_wordlist(params.get("wordlist", ""))
    flags = _sanitize_flags(params.get("flags", "-t 30"))
    return f"gobuster dir -u {shlex.quote(url)} -w {shlex.quote(wordlist)} {flags} 2>&1"


def _build_gobuster_dns(params: dict) -> str:
    domain = _sanitize_target(params.get("domain", ""))
    if not domain:
        return json.dumps({"error": "No domain specified"})
    wordlist = _sanitize_wordlist(params.get("wordlist", ""))
    flags = _sanitize_flags(params.get("flags", "-t 30"))
    return f"gobuster dns -d {shlex.quote(domain)} -w {shlex.quote(wordlist)} {flags} 2>&1"


def _build_subfinder(params: dict) -> str:
    domain = _sanitize_target(params.get("domain", ""))
    if not domain:
        return json.dumps({"error": "No domain specified"})
    flags = _sanitize_flags(params.get("flags", "-silent"))
    return f"subfinder -d {shlex.quote(domain)} {flags} 2>&1"


def _build_httpx(params: dict) -> str:
    urls = _sanitize_target(params.get("urls", ""))
    if not urls:
        return json.dumps({"error": "No URLs specified"})
    flags = _sanitize_flags(params.get("flags", "-silent -status-code -title"))
    return f"echo {shlex.quote(urls)} | httpx-toolkit {flags} 2>&1"


def _build_dnsx(params: dict) -> str:
    domains = _sanitize_target(params.get("domains", ""))
    if not domains:
        return json.dumps({"error": "No domains specified"})
    flags = _sanitize_flags(params.get("flags", "-a -aaaa -cname"))
    return f"echo {shlex.quote(domains)} | dnsx {flags} 2>&1"


def _build_whatweb(params: dict) -> str:
    url = _sanitize_url(params.get("url", ""))
    if not url:
        return json.dumps({"error": "No URL specified"})
    flags = _sanitize_flags(params.get("flags", "--aggression 1"))
    return f"whatweb {shlex.quote(url)} {flags} 2>&1"


def _build_wpscan(params: dict) -> str:
    url = _sanitize_url(params.get("url", ""))
    if not url:
        return json.dumps({"error": "No URL specified"})
    flags = _sanitize_flags(params.get("flags", "--no-update"))
    return f"wpscan --url {shlex.quote(url)} {flags} 2>&1"


def _build_gospider(params: dict) -> str:
    url = _sanitize_url(params.get("url", ""))
    if not url:
        return json.dumps({"error": "No URL specified"})
    flags = _sanitize_flags(params.get("flags", "-c 10 -d 1"))
    return f"gospider -s {shlex.quote(url)} {flags} 2>&1"


def _build_nmap_script(params: dict) -> str:
    target = _sanitize_target(params.get("target", ""))
    if not target:
        return json.dumps({"error": "No target specified"})
    script = params.get("script", "default")
    safe_scripts = [
        "default", "safe", "vuln", "auth", "discovery", "version",
        "http-headers", "http-title", "ssl-cert", "ssl-enum-ciphers",
        "dns-brute", "whois-ip", "ssh-auth-methods",
    ]
    if script not in safe_scripts:
        return json.dumps({
            "error": f"Script '{script}' not in allowed list. "
                     f"Allowed: {', '.join(safe_scripts)}",
        })
    return f"nmap --script {shlex.quote(script)} {shlex.quote(target)} 2>&1"


def _build_nikto(params: dict) -> str:
    target = _sanitize_target(params.get("target", ""))
    if not target:
        return json.dumps({"error": "No target specified"})
    return f"nikto -h {shlex.quote(target)} -Tuning 123457890abc 2>&1"


def _build_katana(params: dict) -> str:
    url = _sanitize_url(params.get("url", ""))
    if not url:
        return json.dumps({"error": "No URL specified"})
    depth = max(1, min(int(params.get("depth", 3)), 5))
    return f"katana -u {shlex.quote(url)} -d {depth} -jc -silent 2>&1"


def _build_naabu(params: dict) -> str:
    target = _sanitize_target(params.get("target", ""))
    if not target:
        return json.dumps({"error": "No target specified"})
    ports = _sanitize_flags(params.get("ports", ""))
    port_flag = f"-p {shlex.quote(ports)}" if ports else "-top-ports 1000"
    return f"naabu -host {shlex.quote(target)} {port_flag} -silent 2>&1"


def _build_header_check(params: dict) -> str:
    target = _sanitize_target(params.get("target", ""))
    if not target:
        return json.dumps({"error": "No target specified"})
    return (
        f"curl -sI -L --max-time 15 {shlex.quote(target)} 2>&1 | "
        f"grep -iE 'server:|x-powered-by:|x-frame-options:|"
        f"content-security-policy:|strict-transport-security:|"
        f"x-content-type-options:|x-xss-protection:|"
        f"access-control-allow-origin:|set-cookie:'"
    )


def _build_cors_check(params: dict) -> str:
    target = _sanitize_target(params.get("target", ""))
    if not target:
        return json.dumps({"error": "No target specified"})
    safe = shlex.quote(target)
    return (
        f"echo '=== Origin Reflection ===' && "
        f"curl -sI -H 'Origin: https://evil.com' {safe} 2>&1 | "
        f"grep -i 'access-control' && "
        f"echo '=== Null Origin ===' && "
        f"curl -sI -H 'Origin: null' {safe} 2>&1 | "
        f"grep -i 'access-control'"
    )


# ── Tool Router ─────────────────────────────────────────────────────

TOOL_ROUTER = {
    # WSL Kali tools
    "nmap_scan":      ("wsl", lambda p: _wsl(_build_nmap(p), timeout=180)),
    "nmap_script":    ("wsl", lambda p: _wsl(_build_nmap_script(p), timeout=180)),
    "sqlmap":         ("wsl", lambda p: _wsl(_build_sqlmap(p), timeout=300)),
    "nuclei_scan":    ("wsl", lambda p: _wsl(_build_nuclei(p), timeout=300)),
    "ffuf_fuzz":      ("wsl", lambda p: _wsl(_build_ffuf(p), timeout=300)),
    "gobuster_dir":   ("wsl", lambda p: _wsl(_build_gobuster_dir(p), timeout=300)),
    "gobuster_dns":   ("wsl", lambda p: _wsl(_build_gobuster_dns(p), timeout=300)),
    "subfinder":      ("wsl", lambda p: _wsl(_build_subfinder(p), timeout=120)),
    "httpx_probe":    ("wsl", lambda p: _wsl(_build_httpx(p), timeout=120)),
    "dnsx_resolve":   ("wsl", lambda p: _wsl(_build_dnsx(p), timeout=60)),
    "whatweb":        ("wsl", lambda p: _wsl(_build_whatweb(p), timeout=120)),
    "wpscan":         ("wsl", lambda p: _wsl(_build_wpscan(p), timeout=300)),
    "gospider":       ("wsl", lambda p: _wsl(_build_gospider(p), timeout=180)),
    "nikto":          ("wsl", lambda p: _wsl(_build_nikto(p), timeout=300)),
    "katana":         ("wsl", lambda p: _wsl(_build_katana(p), timeout=180)),
    "naabu":          ("wsl", lambda p: _wsl(_build_naabu(p), timeout=120)),
    "header_check":   ("wsl", lambda p: _wsl(_build_header_check(p), timeout=30)),
    "cors_check":     ("wsl", lambda p: _wsl(_build_cors_check(p), timeout=30)),

    # PowerShell tools
    "ps_web_request": ("ps", lambda p: _ps("web_request", json.dumps(p))),
    "ps_port_scan":   ("ps", lambda p: _ps("port_scan", json.dumps(p))),
    "ps_dns_info":    ("ps", lambda p: _ps("dns_info", json.dumps(p))),
    "ps_ssl_info":    ("ps", lambda p: _ps("ssl_info", json.dumps(p))),
    "ps_whois":       ("ps", lambda p: _ps("whois", json.dumps(p))),
    "ps_fuzz":        ("ps", lambda p: _ps("fuzz", json.dumps(p))),
    "ps_http_archive":("ps", lambda p: _ps("http_archive", json.dumps(p))),

    # Python-native
    "url_parse":       ("py", lambda p: _py("url_parse", p)),
    "extract_domains": ("py", lambda p: _py("extract_domains", p)),
    "extract_urls":    ("py", lambda p: _py("extract_urls", p)),
    "check_wsl_tools": ("py", lambda p: _py("check_wsl_tools", p)),
    "validate_target": ("py", lambda p: _py("validate_target", p)),
    "health":          ("py", lambda p: _py("health", p)),
}


# ── JSON-RPC over stdin/stdout ──────────────────────────────────────

async def handle_request(request: dict) -> dict:
    """Process a JSON-RPC request and return response."""
    req_id = request.get("id", 0)
    method = request.get("method", "")
    params = request.get("params", {})

    if method not in TOOL_ROUTER:
        return {
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Unknown method: {method}",
            },
        }

    _, handler = TOOL_ROUTER[method]
    try:
        loop = asyncio.get_running_loop()
        result_str = await loop.run_in_executor(None, handler, params)

        if isinstance(result_str, str):
            try:
                result = json.loads(result_str)
            except (json.JSONDecodeError, TypeError):
                result = {"raw_output": result_str}
        else:
            result = result_str

        return {"id": req_id, "result": result}
    except ValueError as e:
        return {
            "id": req_id,
            "error": {"code": -32602, "message": f"Input validation failed: {e}"},
        }
    except Exception as e:
        return {
            "id": req_id,
            "error": {"code": -32000, "message": str(e)},
        }


async def main_loop():
    """Main MCP server loop — reads JSON-RPC from stdin, writes to stdout."""
    startup = json.dumps({
        "id": 0,
        "result": {
            "status": "started",
            "server": "friday-cyber-mcp",
            "version": "1.2.0",
            "tools": list(TOOL_ROUTER.keys()),
        },
    })
    print(startup)
    sys.stdout.flush()

    loop = asyncio.get_running_loop()

    while True:
        try:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                print(json.dumps({
                    "id": 0,
                    "error": {"code": -32700, "message": "Parse error"},
                }))
                sys.stdout.flush()
                continue

            if not isinstance(request, dict):
                print(json.dumps({
                    "id": 0,
                    "error": {"code": -32600, "message": "Invalid request: not an object"},
                }))
                sys.stdout.flush()
                continue

            response = await handle_request(request)
            print(json.dumps(response))
            sys.stdout.flush()

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(json.dumps({
                "id": 0,
                "error": {"code": -32000, "message": f"Server error: {e}"},
            }))
            sys.stdout.flush()

    print(json.dumps({
        "id": 0,
        "result": {"status": "shutdown", "server": "friday-cyber-mcp"},
    }))
    sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main_loop())
