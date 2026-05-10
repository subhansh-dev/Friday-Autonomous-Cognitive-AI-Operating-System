"""
Hunter Agent — Tests one attack surface per spawn. Finds vulnerabilities.
Two modes: code_analysis (regex on source) and dynamic_scan (live target).
"""
import json
import re
import time
from pathlib import Path
from typing import List
from .base_agent import BaseAgent, AgentRole, AgentResult

# Cross-platform path + WSL tool routing
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from actions.resilience import normalize_path, to_wsl_path

CODE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
                   ".java", ".php", ".rb", ".c", ".cpp", ".h", ".cs"}
SKIP_PATTERNS = [".git", "node_modules", "__pycache__", ".venv", "venv",
                 ".mypy_cache", ".pytest_cache", "dist", "build"]

VULN_PATTERNS = {
    "SQL Injection": [
        (r"execute\s*\(\s*[\"'].*%s", "String formatting in SQL execute"),
        (r"f\".*SELECT.*{", "f-string in SQL query"),
        (r"\.format\(.*SELECT", ".format() in SQL query"),
        (r"execute\(.*\+", "String concatenation in SQL execute"),
    ],
    "Command Injection": [
        (r"subprocess\.(call|run|Popen)\(.*shell\s*=\s*True", "Shell=True in subprocess"),
        (r"os\.system\(", "os.system() call"),
        (r"os\.popen\(", "os.popen() call"),
        (r"eval\(", "eval() call"),
        (r"exec\(", "exec() call"),
    ],
    "Path Traversal": [
        (r"open\(.*\+.*request", "User input in file open"),
        (r"send_file\(.*request", "User input in send_file"),
        (r"os\.path\.join\(.*request", "User input in path join"),
    ],
    "Hardcoded Secret": [
        (r"password\s*=\s*[\"'][^\"']{3,}[\"']", "Hardcoded password"),
        (r"api_key\s*=\s*[\"'][^\"']{10,}[\"']", "Hardcoded API key"),
        (r"secret\s*=\s*[\"'][^\"']{8,}[\"']", "Hardcoded secret"),
        (r"token\s*=\s*[\"'][^\"']{10,}[\"']", "Hardcoded token"),
    ],
    "Unsafe Deserialization": [
        (r"pickle\.loads?\(", "Pickle deserialization"),
        (r"yaml\.load\([^)]*\)", "Unsafe YAML load"),
    ],
    "Weak Crypto": [
        (r"md5\(", "MD5 hash usage"),
        (r"sha1\(", "SHA1 hash usage"),
        (r"DES\.", "DES encryption"),
    ],
    "XSS": [
        (r"innerHTML\s*=", "innerHTML assignment"),
        (r"document\.write\(", "document.write call"),
        (r"\.html\(", "jQuery .html() call"),
        (r"dangerouslySetInnerHTML", "React dangerouslySetInnerHTML"),
    ],
    "SSRF": [
        (r"requests\.(get|post)\(.*request\.", "User-controlled URL in request"),
        (r"urllib\.request\.urlopen\(.*request", "User URL in urlopen"),
    ],
    "Auth Bypass": [
        (r"password.*==.*request", "Password comparison with request data"),
        (r"if.*token.*==.*\"", "Hardcoded token comparison"),
    ],
    "Prompt Injection Risk": [
        (r"system_prompt.*\+.*user", "System prompt concatenated with user input"),
        (r"system_instruction.*request", "System instruction from request"),
    ],
}


class HunterAgent(BaseAgent):
    role = AgentRole.HUNTER
    tool_whitelist = ["regex_scan", "nuclei", "ffuf", "gobuster", "sqlmap", "nikto"]
    description = "Vulnerability hunter: scans code and live targets for security issues."

    def execute(self, context: dict) -> AgentResult:
        start = time.time()
        mode = context.get("mode", "code_analysis")
        target = context.get("target", "")

        if not target:
            return self._build_result(error="No target specified")

        self.record_decision(
            decision=f"Hunting in {mode} mode on {target}",
            reasoning=f"Mode selection: {mode} based on context",
            confidence=0.8,
        )

        if mode == "code_analysis":
            findings = self._code_analysis(target, context)
        elif mode == "dynamic_scan":
            findings = self._dynamic_scan(target, context)
        else:
            findings = self._code_analysis(target, context)

        # Deduplicate by finding_id
        seen = set()
        unique = []
        for f in findings:
            fid = f.get("finding_id", "")
            if fid not in seen:
                seen.add(fid)
                unique.append(f)

        result = self._build_result(findings=unique)
        result.duration_ms = (time.time() - start) * 1000
        return result

    def _code_analysis(self, target: str, context: dict) -> List[dict]:
        """Static analysis: regex patterns on source code."""
        findings = []
        target_path, path_err = normalize_path(target)

        if not target_path.exists():
            self.record_decision(
                decision="Target path does not exist",
                reasoning=path_err or f"Cannot access {target}",
                confidence=0.0,
            )
            return findings

        files_scanned = 0
        for f in target_path.rglob("*"):
            if not f.is_file():
                continue
            if any(skip in str(f) for skip in SKIP_PATTERNS):
                continue
            if f.suffix.lower() not in CODE_EXTENSIONS:
                continue

            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                lines = content.split("\n")
                files_scanned += 1

                for line_num, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith("//"):
                        continue

                    for vuln_class, patterns in VULN_PATTERNS.items():
                        for pattern, description in patterns:
                            if re.search(pattern, line, re.IGNORECASE):
                                import hashlib
                                raw = f"{f}:{vuln_class}:{line_num}"
                                fid = hashlib.sha256(raw.encode()).hexdigest()[:16]
                                findings.append({
                                    "agent": "HUNTER",
                                    "vuln_class": vuln_class,
                                    "finding_id": fid,
                                    "file_path": str(f.relative_to(target_path)),
                                    "confidence": "plausible",
                                    "cvss_score": 7.5,
                                    "summary": f"{vuln_class} at {f.name}:{line_num} — {description}",
                                    "detail": stripped[:200],
                                    "target": str(f),
                                })
                                break  # One match per pattern per line
            except Exception:
                continue

        self.record_decision(
            decision=f"Scanned {files_scanned} files, found {len(findings)} potential issues",
            reasoning="Regex pattern matching on source code",
            confidence=0.6,
        )
        return findings

    def _dynamic_scan(self, target: str, context: dict) -> List[dict]:
        """Dynamic scanning: run tools against live target."""
        findings = []
        surface = context.get("attack_surface", {})
        endpoints = surface.get("endpoints", [target])

        # Quick nuclei scan on primary target
        nuclei_findings = self._run_nuclei(target)
        findings.extend(nuclei_findings)

        # FFUF on common paths
        if context.get("run_fuzz"):
            fuzz_findings = self._run_ffuf(target)
            findings.extend(fuzz_findings)

        return findings

    def _run_nuclei(self, target: str) -> List[dict]:
        """Run nuclei scanner via WSL Kali."""
        import subprocess
        import shutil as _shutil

        # Route through WSL — nuclei lives in Kali
        wsl_exe = r"C:\Windows\System32\wsl.exe"
        wsl_distro = "kali-linux"
        cmd = f"nuclei -u {target} -severity low,medium,high,critical -silent -json 2>&1"

        for exe in [wsl_exe, "wsl"]:
            try:
                r = subprocess.run(
                    [exe, "-d", wsl_distro, "--", "bash", "-c", cmd],
                    capture_output=True, text=True, timeout=180,
                    creationflags=0x08000000 if sys.platform == "win32" else 0,  # CREATE_NO_WINDOW
                )
                findings = []
                for line in (r.stdout or "").strip().split("\n"):
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        findings.append({
                            "agent": "HUNTER",
                            "vuln_class": data.get("info", {}).get("name", "Unknown"),
                            "finding_id": f"nuclei_{data.get('template-id', 'unknown')}",
                            "file_path": data.get("matched-at", target),
                            "confidence": "confirmed",
                            "cvss_score": float(data.get("info", {}).get("severity", "medium") == "high") * 7 + 5,
                            "summary": f"Nuclei: {data.get('info', {}).get('name', 'Unknown')} at {data.get('matched-at', '')}",
                            "detail": json.dumps(data.get("info", {}))[:500],
                            "target": target,
                        })
                    except json.JSONDecodeError:
                        continue
                return findings
            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                return []

        # Fallback: try running nuclei directly (Linux native)
        try:
            r = subprocess.run(
                ["nuclei", "-u", target, "-severity", "low,medium,high,critical", "-silent", "-json"],
                capture_output=True, text=True, timeout=180,
            )
            findings = []
            for line in r.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    findings.append({
                        "agent": "HUNTER",
                        "vuln_class": data.get("info", {}).get("name", "Unknown"),
                        "finding_id": f"nuclei_{data.get('template-id', 'unknown')}",
                        "file_path": data.get("matched-at", target),
                        "confidence": "confirmed",
                        "cvss_score": float(data.get("info", {}).get("severity", "medium") == "high") * 7 + 5,
                        "summary": f"Nuclei: {data.get('info', {}).get('name', 'Unknown')} at {data.get('matched-at', '')}",
                        "detail": json.dumps(data.get("info", {}))[:500],
                        "target": target,
                    })
                except json.JSONDecodeError:
                    continue
            return findings
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

    def _run_ffuf(self, target: str) -> List[dict]:
        """Run ffuf directory fuzzing via WSL Kali."""
        import subprocess

        wordlist = "/usr/share/wordlists/dirb/common.txt"
        cmd = (
            f"ffuf -u {target}/FUZZ -w {wordlist} "
            f"-mc 200,301,302,403 -t 30 -o /dev/stdout -of json 2>&1"
        )

        wsl_exe = r"C:\Windows\System32\wsl.exe"
        wsl_distro = "kali-linux"

        for exe in [wsl_exe, "wsl"]:
            try:
                r = subprocess.run(
                    [exe, "-d", wsl_distro, "--", "bash", "-c", cmd],
                    capture_output=True, text=True, timeout=180,
                    creationflags=0x08000000 if sys.platform == "win32" else 0,
                )
                findings = []
                try:
                    data = json.loads(r.stdout)
                    for result in data.get("results", [])[:20]:
                        findings.append({
                            "agent": "HUNTER",
                            "vuln_class": "Directory Discovery",
                            "finding_id": f"ffuf_{result.get('input', {}).get('FUZZ', '')}",
                            "file_path": result.get("url", target),
                            "confidence": "confirmed",
                            "cvss_score": 2.0,
                            "summary": f"Directory found: {result.get('url', '')} ({result.get('status', '')})",
                            "detail": f"Length: {result.get('length', '')}, Words: {result.get('words', '')}",
                            "target": target,
                        })
                except json.JSONDecodeError:
                    pass
                return findings
            except FileNotFoundError:
                continue
            except subprocess.TimeoutExpired:
                return []

        # Fallback: direct execution (Linux native)
        try:
            r = subprocess.run(
                ["ffuf", "-u", f"{target}/FUZZ", "-w", wordlist,
                 "-mc", "200,301,302,403", "-t", "30", "-o", "/dev/stdout", "-of", "json"],
                capture_output=True, text=True, timeout=180,
            )
            findings = []
            data = json.loads(r.stdout)
            for result in data.get("results", [])[:20]:
                findings.append({
                    "agent": "HUNTER",
                    "vuln_class": "Directory Discovery",
                    "finding_id": f"ffuf_{result.get('input', {}).get('FUZZ', '')}",
                    "file_path": result.get("url", target),
                    "confidence": "confirmed",
                    "cvss_score": 2.0,
                    "summary": f"Directory found: {result.get('url', '')} ({result.get('status', '')})",
                    "detail": f"Length: {result.get('length', '')}, Words: {result.get('words', '')}",
                    "target": target,
                })
            return findings
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return []
