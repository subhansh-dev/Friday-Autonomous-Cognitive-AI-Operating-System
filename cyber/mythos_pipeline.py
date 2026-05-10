"""
cyber/mythos_pipeline.py — Multi-Agent Security Orchestrator
Coordinates 7 specialized security agents in sequence.
Pipeline: RECON -> HUNTER -> ADVERSARIAL -> EXPLOIT -> TRIAGE -> AI_SECURITY -> SUPPLY_CHAIN
Inspired by anshug/claude-mythos and mythos-agent/mythos-agent.
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brain.findings_bus import get_findings_bus, _compute_finding_id
from actions.resilience import normalize_path


@dataclass
class ScanResult:
    agent: str
    phase: int
    findings: list = field(default_factory=list)
    duration_ms: float = 0
    error: Optional[str] = None


@dataclass
class PipelineResult:
    target: str
    scan_type: str
    agents_run: list = field(default_factory=list)
    total_findings: int = 0
    confidence_summary: dict = field(default_factory=dict)
    duration_ms: float = 0
    results: list = field(default_factory=list)
    report: str = ""


# Skip patterns — never scan these
SKIP_PATTERNS = [".git", "node_modules", "__pycache__", ".venv", "venv",
                 ".mypy_cache", ".pytest_cache", "dist", "build", ".tox"]

# File extensions to scan
CODE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
                   ".java", ".php", ".rb", ".c", ".cpp", ".h", ".cs", ".sol"}


def _should_skip(path: str) -> bool:
    return any(skip in path for skip in SKIP_PATTERNS)


class MythosPipeline:
    """Multi-agent security orchestrator."""

    def __init__(self):
        self.bus = get_findings_bus()

    def run(self, target: str, scan_type: str = "full") -> PipelineResult:
        start = time.time()
        result = PipelineResult(target=target, scan_type=scan_type)

        agents = [
            ("RECON", self._run_recon),
            ("HUNTER", self._run_hunter),
            ("ADVERSARIAL", self._run_adversarial),
            ("EXPLOIT", self._run_exploit),
            ("TRIAGE", self._run_triage),
            ("AI_SECURITY", self._run_ai_security),
            ("SUPPLY_CHAIN", self._run_supply_chain),
        ]

        prev_result = None
        for agent_name, agent_fn in agents:
            scan_result = agent_fn(target, prev_result)
            result.results.append(scan_result)
            result.agents_run.append(agent_name)
            prev_result = scan_result

        result.total_findings = sum(len(r.findings) for r in result.results)
        result.confidence_summary = self.bus.get_confidence_summary()
        result.duration_ms = (time.time() - start) * 1000
        result.report = self._generate_report(result)

        return result

    # ── Phase 1: RECON ─────────────────────────────────────────────────

    def _run_recon(self, target: str, prev: Optional[ScanResult] = None) -> ScanResult:
        start = time.time()
        result = ScanResult(agent="RECON", phase=1)

        try:
            target_path, _path_err = normalize_path(target)
            if not target_path.exists():
                result.error = _path_err or f"Target not found: {target}"
                return result

            files = []
            entry_points = []
            tech_stack = set()
            config_files = []

            for f in target_path.rglob("*"):
                if not f.is_file() or _should_skip(str(f)):
                    continue
                files.append(f)

                suffix = f.suffix.lower()
                if suffix == ".py": tech_stack.add("python")
                elif suffix in (".js", ".ts", ".jsx", ".tsx"): tech_stack.add("javascript")
                elif suffix == ".go": tech_stack.add("go")
                elif suffix == ".rs": tech_stack.add("rust")
                elif suffix == ".java": tech_stack.add("java")

                name = f.name.lower()
                if name in ("main.py", "app.py", "server.py", "index.js",
                           "main.go", "app.js", "server.js", "manage.py", "wsgi.py"):
                    entry_points.append(str(f.relative_to(target_path)))

                if name in (".env", ".env.local", ".env.production",
                           "docker-compose.yml", "dockerfile", "nginx.conf",
                           "config.yaml", "config.json", "settings.py"):
                    config_files.append(str(f.relative_to(target_path)))

            finding = {
                "agent": "RECON",
                "phase": 1,
                "finding_id": _compute_finding_id(target, "recon_summary", "0"),
                "file_path": target,
                "vuln_class": "Reconnaissance",
                "confidence": "confirmed",
                "cvss_score": 0,
                "summary": f"Found {len(files)} files, {len(entry_points)} entry points, tech: {', '.join(tech_stack)}",
                "detail": json.dumps({
                    "total_files": len(files),
                    "entry_points": entry_points[:20],
                    "config_files": config_files[:10],
                    "tech_stack": list(tech_stack),
                }),
            }
            self.bus.write(finding)
            result.findings.append(finding)

        except Exception as e:
            result.error = str(e)

        result.duration_ms = (time.time() - start) * 1000
        return result

    # ── Phase 2: HUNTER ────────────────────────────────────────────────

    def _run_hunter(self, target: str, prev: Optional[ScanResult] = None) -> ScanResult:
        start = time.time()
        result = ScanResult(agent="HUNTER", phase=2)

        vuln_patterns = {
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
                (r"marshal\.loads?\(", "Marshal deserialization"),
            ],
            "Weak Crypto": [
                (r"md5\(", "MD5 hash usage"),
                (r"sha1\(", "SHA1 hash usage"),
                (r"DES\.", "DES encryption"),
                (r"ECB", "ECB mode"),
            ],
        }

        try:
            target_path, _path_err = normalize_path(target)
            if not target_path.exists():
                result.error = _path_err or f"Target not found: {target}"
                return result
            findings_count = 0

            for f in target_path.rglob("*"):
                if not f.is_file() or _should_skip(str(f)):
                    continue
                if f.suffix.lower() not in CODE_EXTENSIONS:
                    continue

                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    lines = content.split("\n")

                    for line_num, line in enumerate(lines, 1):
                        stripped = line.strip()
                        if stripped.startswith("#") or stripped.startswith("//"):
                            continue

                        for vuln_class, patterns in vuln_patterns.items():
                            for pattern, description in patterns:
                                if re.search(pattern, line, re.IGNORECASE):
                                    finding_id = _compute_finding_id(
                                        str(f), vuln_class, str(line_num)
                                    )
                                    finding = {
                                        "agent": "HUNTER",
                                        "phase": 2,
                                        "finding_id": finding_id,
                                        "file_path": str(f.relative_to(target_path)),
                                        "vuln_class": vuln_class,
                                        "confidence": "plausible",
                                        "cvss_score": 7.5,
                                        "summary": f"{vuln_class} at {f.name}:{line_num} — {description}",
                                        "detail": f"Line: {stripped[:120]}",
                                    }
                                    if self.bus.write(finding):
                                        result.findings.append(finding)
                                        findings_count += 1
                                    break  # One match per pattern per line
                except Exception:
                    continue

        except Exception as e:
            result.error = str(e)

        result.duration_ms = (time.time() - start) * 1000
        return result

    # ── Phase 3: ADVERSARIAL ───────────────────────────────────────────

    def _run_adversarial(self, target: str, prev: Optional[ScanResult] = None) -> ScanResult:
        start = time.time()
        result = ScanResult(agent="ADVERSARIAL", phase=3)

        # Analyze hunter findings for chain potential
        hunter_findings = prev.findings if prev else []
        by_file = {}

        for f in hunter_findings:
            fp = f.get("file_path", "")
            if fp not in by_file:
                by_file[fp] = []
            by_file[fp].append(f)

        # Find files with multiple vulnerability types (chain potential)
        for fp, findings in by_file.items():
            if len(findings) >= 2:
                vuln_classes = set(f.get("vuln_class", "") for f in findings)
                if len(vuln_classes) >= 2:
                    chain = {
                        "agent": "ADVERSARIAL",
                        "phase": 3,
                        "finding_id": _compute_finding_id(fp, "exploit_chain", "0"),
                        "file_path": fp,
                        "vuln_class": "Exploit Chain",
                        "confidence": "plausible",
                        "cvss_score": 9.0,
                        "summary": f"Chain potential: {' + '.join(vuln_classes)} in {fp}",
                        "detail": json.dumps([f["summary"] for f in findings]),
                    }
                    if self.bus.write(chain):
                        result.findings.append(chain)

        # Look for auth bypass patterns
        target_path, _path_err = normalize_path(target)
        if not target_path.exists():
            return result
        for f in target_path.rglob("*"):
            if not f.is_file() or _should_skip(str(f)):
                continue
            if f.suffix.lower() not in CODE_EXTENSIONS:
                continue

            try:
                content = f.read_text(encoding="utf-8", errors="ignore")

                # Check for auth-related issues
                if "password" in content.lower() and "==" in content:
                    if "request" in content.lower() or "input" in content.lower():
                        finding = {
                            "agent": "ADVERSARIAL",
                            "phase": 3,
                            "finding_id": _compute_finding_id(str(f), "auth_bypass", "0"),
                            "file_path": str(f.relative_to(target_path)),
                            "vuln_class": "Auth Bypass Risk",
                            "confidence": "plausible",
                            "cvss_score": 8.0,
                            "summary": f"Potential auth bypass in {f.name} — password comparison with user input",
                            "detail": "Direct password comparison with request/input data",
                        }
                        if self.bus.write(finding):
                            result.findings.append(finding)
            except Exception:
                continue

        result.duration_ms = (time.time() - start) * 1000
        return result

    # ── Phase 4: EXPLOIT ───────────────────────────────────────────────

    def _run_exploit(self, target: str, prev: Optional[ScanResult] = None) -> ScanResult:
        start = time.time()
        result = ScanResult(agent="EXPLOIT", phase=4)

        # Validate and escalate confidence of chained findings
        for finding in (prev.findings if prev else []):
            if finding.get("vuln_class") == "Exploit Chain":
                validated = dict(finding)
                validated["agent"] = "EXPLOIT"
                validated["phase"] = 4
                validated["confidence"] = "confirmed"
                validated["finding_id"] = _compute_finding_id(
                    finding["file_path"], "validated_chain", "0"
                )
                validated["summary"] = f"[VALIDATED] {finding['summary']}"
                if self.bus.write(validated):
                    result.findings.append(validated)

        result.duration_ms = (time.time() - start) * 1000
        return result

    # ── Phase 5: TRIAGE ────────────────────────────────────────────────

    def _run_triage(self, target: str, prev: Optional[ScanResult] = None) -> ScanResult:
        start = time.time()
        result = ScanResult(agent="TRIAGE", phase=5)

        all_findings = self.bus.read()
        critical = [f for f in all_findings if f.get("cvss_score", 0) >= 9.0]
        high = [f for f in all_findings if 7.0 <= f.get("cvss_score", 0) < 9.0]
        medium = [f for f in all_findings if 4.0 <= f.get("cvss_score", 0) < 7.0]

        summary = {
            "agent": "TRIAGE",
            "phase": 5,
            "finding_id": _compute_finding_id(target, "triage_summary", "0"),
            "file_path": target,
            "vuln_class": "Triage Summary",
            "confidence": "confirmed",
            "cvss_score": 0,
            "summary": f"Total: {len(all_findings)} findings — {len(critical)} critical, {len(high)} high, {len(medium)} medium",
            "detail": json.dumps(self.bus.get_confidence_summary()),
        }
        if self.bus.write(summary):
            result.findings.append(summary)

        result.duration_ms = (time.time() - start) * 1000
        return result

    # ── Phase 6: AI_SECURITY ───────────────────────────────────────────

    def _run_ai_security(self, target: str, prev: Optional[ScanResult] = None) -> ScanResult:
        start = time.time()
        result = ScanResult(agent="AI_SECURITY", phase=6)

        target_path, _path_err = normalize_path(target)
        if not target_path.exists():
            return result

        for f in target_path.rglob("*"):
            if not f.is_file() or _should_skip(str(f)):
                continue
            if f.suffix.lower() not in CODE_EXTENSIONS:
                continue

            try:
                content = f.read_text(encoding="utf-8", errors="ignore")

                # Prompt injection risk
                if ("system_prompt" in content or "SYSTEM_PROMPT" in content or
                    "system_instruction" in content):
                    if "user" in content.lower() or "request" in content.lower() or "input" in content.lower():
                        finding = {
                            "agent": "AI_SECURITY",
                            "phase": 6,
                            "finding_id": _compute_finding_id(str(f), "prompt_injection", "0"),
                            "file_path": str(f.relative_to(target_path)),
                            "vuln_class": "Prompt Injection Risk",
                            "confidence": "plausible",
                            "cvss_score": 6.5,
                            "summary": f"Prompt injection risk in {f.name} — user input may reach system prompt",
                            "detail": "File contains system prompt/instruction and user input — verify sanitization",
                        }
                        if self.bus.write(finding):
                            result.findings.append(finding)

                # Unsafe eval with user input
                if "eval(" in content or "exec(" in content:
                    if "user" in content.lower() or "request" in content.lower():
                        finding = {
                            "agent": "AI_SECURITY",
                            "phase": 6,
                            "finding_id": _compute_finding_id(str(f), "unsafe_eval", "0"),
                            "file_path": str(f.relative_to(target_path)),
                            "vuln_class": "Unsafe Code Execution",
                            "confidence": "plausible",
                            "cvss_score": 8.0,
                            "summary": f"Unsafe eval/exec with user input in {f.name}",
                            "detail": "eval() or exec() with user-controlled input",
                        }
                        if self.bus.write(finding):
                            result.findings.append(finding)

                # Tool misuse — unrestricted tool execution
                if "tool_call" in content or "function_call" in content:
                    if "validate" not in content.lower() and "check" not in content.lower():
                        finding = {
                            "agent": "AI_SECURITY",
                            "phase": 6,
                            "finding_id": _compute_finding_id(str(f), "tool_misuse", "0"),
                            "file_path": str(f.relative_to(target_path)),
                            "vuln_class": "Unvalidated Tool Execution",
                            "confidence": "plausible",
                            "cvss_score": 5.5,
                            "summary": f"Tool execution without validation in {f.name}",
                            "detail": "Tool/function calls without visible validation or sanitization",
                        }
                        if self.bus.write(finding):
                            result.findings.append(finding)

            except Exception:
                continue

        result.duration_ms = (time.time() - start) * 1000
        return result

    # ── Phase 7: SUPPLY_CHAIN ──────────────────────────────────────────

    def _run_supply_chain(self, target: str, prev: Optional[ScanResult] = None) -> ScanResult:
        start = time.time()
        result = ScanResult(agent="SUPPLY_CHAIN", phase=7)

        target_path, _path_err = normalize_path(target)
        if not target_path.exists():
            return result

        # Check for exposed secret files
        secret_names = {".env", ".env.local", ".env.production", ".env.development",
                       "credentials.json", "secrets.json", "id_rsa", "id_ed25519",
                       ".htpasswd", "keystore.jks", "pfx", ".pem"}

        for f in target_path.rglob("*"):
            if not f.is_file() or _should_skip(str(f)):
                continue
            if f.name.lower() in secret_names or f.suffix.lower() in (".pem", ".key", ".pfx"):
                finding = {
                    "agent": "SUPPLY_CHAIN",
                    "phase": 7,
                    "finding_id": _compute_finding_id(str(f), "exposed_secret", "0"),
                    "file_path": str(f.relative_to(target_path)),
                    "vuln_class": "Exposed Secret",
                    "confidence": "confirmed",
                    "cvss_score": 8.5,
                    "summary": f"Secret file found: {f.name}",
                    "detail": f"File may contain credentials — ensure it is in .gitignore",
                }
                if self.bus.write(finding):
                    result.findings.append(finding)

        # Check for unpinned dependencies
        for req_file in target_path.rglob("requirements*.txt"):
            if _should_skip(str(req_file)):
                continue
            try:
                content = req_file.read_text(encoding="utf-8")
                unpinned = [line.strip() for line in content.split("\n")
                           if line.strip() and not line.strip().startswith("#")
                           and "==" not in line and ">=" not in line]
                if unpinned:
                    finding = {
                        "agent": "SUPPLY_CHAIN",
                        "phase": 7,
                        "finding_id": _compute_finding_id(str(req_file), "unpinned_deps", "0"),
                        "file_path": str(req_file.relative_to(target_path)),
                        "vuln_class": "Unpinned Dependencies",
                        "confidence": "plausible",
                        "cvss_score": 4.0,
                        "summary": f"{len(unpinned)} unpinned dependencies in {req_file.name}",
                        "detail": f"Unpinned: {', '.join(unpinned[:10])}",
                    }
                    if self.bus.write(finding):
                        result.findings.append(finding)
            except Exception:
                continue

        # Check for .env not in .gitignore
        gitignore = target_path / ".gitignore"
        env_files = list(target_path.rglob(".env*"))
        if env_files and gitignore.exists():
            try:
                gi_content = gitignore.read_text(encoding="utf-8")
                if ".env" not in gi_content:
                    finding = {
                        "agent": "SUPPLY_CHAIN",
                        "phase": 7,
                        "finding_id": _compute_finding_id(str(target_path), "env_not_ignored", "0"),
                        "file_path": ".gitignore",
                        "vuln_class": "Secrets in Git",
                        "confidence": "confirmed",
                        "cvss_score": 7.0,
                        "summary": ".env files exist but .env is not in .gitignore",
                        "detail": "Environment files may be committed to git",
                    }
                    if self.bus.write(finding):
                        result.findings.append(finding)
            except Exception:
                pass

        result.duration_ms = (time.time() - start) * 1000
        return result

    # ── Report Generation ──────────────────────────────────────────────

    def _generate_report(self, result: PipelineResult) -> str:
        lines = [
            "# Security Scan Report",
            "",
            f"**Target:** {result.target}",
            f"**Scan Type:** {result.scan_type}",
            f"**Duration:** {result.duration_ms:.0f}ms",
            f"**Agents:** {' -> '.join(result.agents_run)}",
            "",
            "## Confidence Summary",
            "",
            "| Tier | Count |",
            "|------|-------|",
        ]

        for tier, count in result.confidence_summary.items():
            if tier != "total":
                lines.append(f"| {tier.capitalize()} | {count} |")

        lines.append(f"| **Total** | **{result.total_findings}** |")
        lines.append("")

        # Top findings by severity
        all_findings = self.bus.read()
        critical = sorted(
            [f for f in all_findings if f.get("cvss_score", 0) >= 7.0],
            key=lambda x: x.get("cvss_score", 0),
            reverse=True,
        )

        if critical:
            lines.append("## Critical/High Findings")
            lines.append("")
            for f in critical[:15]:
                score = f.get("cvss_score", 0)
                vclass = f.get("vuln_class", "Unknown")
                fpath = f.get("file_path", "?")
                summary = f.get("summary", "")
                lines.append(f"- **[{vclass}]** CVSS {score} `{fpath}` — {summary}")
            lines.append("")

        # Per-agent breakdown
        lines.append("## Agent Breakdown")
        lines.append("")
        for r in result.results:
            status = "ERROR" if r.error else f"{len(r.findings)} findings"
            lines.append(f"- **{r.agent}** (Phase {r.phase}): {status} ({r.duration_ms:.0f}ms)")
        lines.append("")

        return "\n".join(lines)


_pipeline_instance: Optional[MythosPipeline] = None


def get_mythos_pipeline() -> MythosPipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = MythosPipeline()
    return _pipeline_instance
