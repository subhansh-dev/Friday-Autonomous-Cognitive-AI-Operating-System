"""
Recon Agent — Subdomain enum, live host probing, tech detection, endpoint crawling.
Routes all Kali tools through WSL on Windows.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import List
from .base_agent import BaseAgent, AgentRole, AgentResult

# WSL routing for Kali tools
WSL_EXE = r"C:\Windows\System32\wsl.exe"
WSL_DISTRO = "kali-linux"


def _run_kali(cmd: str, timeout: int = 120, input_data: str = None) -> subprocess.CompletedProcess:
    """Run a command via WSL Kali. Falls back to direct execution on Linux."""
    if sys.platform == "win32":
        for exe in [WSL_EXE, "wsl"]:
            try:
                return subprocess.run(
                    [exe, "-d", WSL_DISTRO, "--", "bash", "-c", cmd],
                    input=input_data,
                    capture_output=True, text=True, timeout=timeout,
                    creationflags=0x08000000,  # CREATE_NO_WINDOW
                )
            except FileNotFoundError:
                continue
    # Linux fallback
    return subprocess.run(
        ["bash", "-c", cmd],
        input=input_data,
        capture_output=True, text=True, timeout=timeout,
    )


class ReconAgent(BaseAgent):
    role = AgentRole.RECON
    tool_whitelist = ["subfinder", "httpx", "nmap", "whatweb", "gospider", "katana",
                      "dnsx", "naabu", "curl", "header_check", "extract_domains", "extract_urls"]
    description = "Reconnaissance: subdomain enumeration, live host probing, tech detection, port scanning."

    def execute(self, context: dict) -> AgentResult:
        start = time.time()
        target = context.get("target", "")
        if not target:
            return self._build_result(error="No target specified")

        self.record_decision(
            decision=f"Starting recon on {target}",
            reasoning="First phase: map the attack surface",
            confidence=0.9,
        )

        attack_surface = {
            "subdomains": [],
            "live_hosts": [],
            "open_ports": [],
            "technologies": [],
            "endpoints": [],
            "headers": {},
        }

        # Phase 1: Subdomain enumeration
        domain = self._extract_domain(target)
        if domain:
            subs = self._run_subfinder(domain)
            attack_surface["subdomains"] = subs
            self.record_decision(
                decision=f"Found {len(subs)} subdomains",
                reasoning="subfinder enumeration",
                confidence=0.8,
            )

            # Phase 2: Live host probing
            all_hosts = [domain] + subs
            live = self._run_httpx(all_hosts[:50])  # Cap at 50
            attack_surface["live_hosts"] = live
            self.record_decision(
                decision=f"Found {len(live)} live hosts",
                reasoning="httpx probe for live hosts",
                confidence=0.85,
            )

        # Phase 3: Port scanning (top ports only for speed)
        ports = self._run_port_scan(target)
        attack_surface["open_ports"] = ports

        # Phase 4: Technology detection on primary target
        techs = self._run_whatweb(target)
        attack_surface["technologies"] = techs

        # Phase 5: Header analysis
        headers = self._check_headers(target)
        attack_surface["headers"] = headers

        # Phase 6: Endpoint discovery
        endpoints = self._crawl_endpoints(target)
        attack_surface["endpoints"] = endpoints

        # Build findings
        findings = []
        findings.append({
            "agent": "RECON",
            "vuln_class": "Reconnaissance",
            "finding_id": f"recon_{domain or target}",
            "file_path": target,
            "confidence": "confirmed",
            "cvss_score": 0,
            "summary": (f"Recon: {len(attack_surface['subdomains'])} subdomains, "
                       f"{len(attack_surface['live_hosts'])} live, "
                       f"{len(attack_surface['open_ports'])} ports, "
                       f"{len(attack_surface['endpoints'])} endpoints"),
            "detail": json.dumps(attack_surface, default=str)[:2000],
        })

        # Flag interesting findings
        if len(attack_surface["open_ports"]) > 10:
            findings.append({
                "agent": "RECON",
                "vuln_class": "Information Disclosure",
                "finding_id": f"recon_many_ports_{domain}",
                "file_path": target,
                "confidence": "plausible",
                "cvss_score": 3.0,
                "summary": f"{len(attack_surface['open_ports'])} open ports detected — broad attack surface",
                "detail": json.dumps(attack_surface["open_ports"]),
            })

        result = self._build_result(
            findings=findings,
            metadata={"attack_surface": attack_surface},
        )
        result.duration_ms = (time.time() - start) * 1000
        return result

    def _extract_domain(self, target: str) -> str:
        """Extract domain from URL."""
        target = target.replace("https://", "").replace("http://", "")
        return target.split("/")[0].split(":")[0]

    def _run_subfinder(self, domain: str) -> List[str]:
        """Run subfinder for subdomain enumeration via WSL Kali."""
        try:
            r = _run_kali(f"subfinder -d {domain} -silent 2>&1", timeout=60)
            if r.returncode == 0:
                return [s.strip() for s in r.stdout.strip().split("\n") if s.strip()]
        except subprocess.TimeoutExpired:
            pass
        return []

    def _run_httpx(self, hosts: List[str]) -> List[str]:
        """Run httpx to probe for live hosts via WSL Kali."""
        if not hosts:
            return []
        try:
            input_data = "\n".join(hosts)
            r = _run_kali(
                "httpx -silent -status-code -title 2>&1",
                input_data=input_data, timeout=120,
            )
            if r.returncode == 0:
                live = []
                for line in r.stdout.strip().split("\n"):
                    if line.strip():
                        host = line.split()[0] if line.split() else line
                        live.append(host)
                return live
        except subprocess.TimeoutExpired:
            pass
        return []

    def _run_port_scan(self, target: str) -> List[int]:
        """Quick port scan with nmap top ports via WSL Kali."""
        domain = self._extract_domain(target)
        try:
            r = _run_kali(f"nmap -F --open -oG - {domain} 2>&1", timeout=60)
            ports = []
            for match in re.finditer(r"(\d+)/open", r.stdout):
                ports.append(int(match.group(1)))
            return sorted(ports)
        except subprocess.TimeoutExpired:
            pass
        return []

    def _run_whatweb(self, target: str) -> List[str]:
        """Run whatweb for technology detection via WSL Kali."""
        try:
            r = _run_kali(f"whatweb --silent {target} 2>&1", timeout=30)
            if r.returncode == 0:
                techs = re.findall(r"\[([^\]]+)\]", r.stdout)
                return list(set(techs))
        except subprocess.TimeoutExpired:
            pass
        return []

    def _check_headers(self, target: str) -> dict:
        """Check HTTP security headers via WSL Kali curl."""
        try:
            r = _run_kali(f"curl -sI -L --max-time 10 {target} 2>&1", timeout=15)
            headers = {}
            security_headers = [
                "server", "x-powered-by", "x-frame-options",
                "content-security-policy", "strict-transport-security",
                "x-content-type-options", "x-xss-protection",
                "access-control-allow-origin", "set-cookie",
            ]
            for line in r.stdout.split("\n"):
                for header in security_headers:
                    if line.lower().startswith(header + ":"):
                        headers[header] = line.split(":", 1)[1].strip()
            return headers
        except subprocess.TimeoutExpired:
            pass
        return {}

    def _crawl_endpoints(self, target: str) -> List[str]:
        """Quick endpoint crawl with curl + link extraction via WSL Kali."""
        try:
            r = _run_kali(f"curl -sL --max-time 10 {target} 2>&1", timeout=15)
            endpoints = set()
            for match in re.finditer(r'(?:href|src|action)=["\']([^"\']+)["\']', r.stdout):
                url = match.group(1)
                if url.startswith("/") or url.startswith(target):
                    endpoints.add(url)
            return sorted(endpoints)[:100]
        except subprocess.TimeoutExpired:
            pass
        return []
