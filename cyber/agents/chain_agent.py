"""
Chain Agent — Builds A→B exploit chains from individual findings.
"""
import time
import uuid
from typing import List
from .base_agent import BaseAgent, AgentRole, AgentResult

CHAIN_PATTERNS = [
    {
        "name": "Account Takeover via Info Disclosure + IDOR",
        "requires": ["information disclosure", "idor"],
        "combined_severity": "critical",
        "impact": "Full account takeover — attacker can access any user's data",
    },
    {
        "name": "Token Theft via CORS + XSS",
        "requires": ["cors misconfiguration", "xss"],
        "combined_severity": "high",
        "impact": "Steal auth tokens from any user visiting attacker-controlled page",
    },
    {
        "name": "Account Hijack via Redirect + OAuth",
        "requires": ["open redirect", "authentication bypass"],
        "combined_severity": "critical",
        "impact": "Hijack accounts via OAuth redirect manipulation",
    },
    {
        "name": "RCE via File Upload + Path Traversal",
        "requires": ["file upload", "path traversal"],
        "combined_severity": "critical",
        "impact": "Remote code execution through uploaded webshell",
    },
    {
        "name": "Privilege Escalation via IDOR + Weak Auth",
        "requires": ["idor", "authorization bypass"],
        "combined_severity": "high",
        "impact": "Escalate from regular user to admin",
    },
    {
        "name": "Data Exfiltration via SSRF + Info Disclosure",
        "requires": ["ssrf", "information disclosure"],
        "combined_severity": "high",
        "impact": "Access cloud metadata and internal services",
    },
    {
        "name": "Full Compromise via SQLi + File Write",
        "requires": ["sql injection", "path traversal"],
        "combined_severity": "critical",
        "impact": "Write webshell to disk via SQL injection",
    },
    {
        "name": "Auth Bypass via Command Injection + SSRF",
        "requires": ["command injection", "ssrf"],
        "combined_severity": "critical",
        "impact": "Execute commands on internal infrastructure",
    },
]

COMPLEMENTARY_PAIRS = {
    ("information disclosure", "idor"),
    ("xss", "cors misconfiguration"),
    ("ssrf", "information disclosure"),
    ("authentication bypass", "authorization bypass"),
    ("path traversal", "sql injection"),
    ("open redirect", "authentication bypass"),
    ("command injection", "ssrf"),
    ("xss", "information disclosure"),
}


class ChainAgent(BaseAgent):
    role = AgentRole.CHAIN
    tool_whitelist = ["findings_reader"]
    description = "Discovers and builds exploit chains from individual findings."

    def execute(self, context: dict) -> AgentResult:
        start = time.time()
        findings = context.get("findings", [])

        if not findings:
            return self._build_result(error="No findings to analyze for chains")

        self.record_decision(
            decision=f"Analyzing {len(findings)} findings for chain potential",
            reasoning="Multi-finding chains can escalate low-severity issues to critical",
            confidence=0.7,
        )

        chains = []

        # Index findings by attack vector
        by_vector = {}
        for f in findings:
            vc = f.get("vuln_class", "").lower().strip()
            by_vector.setdefault(vc, []).append(f)

        # Check known chain patterns
        for pattern in CHAIN_PATTERNS:
            required = pattern["requires"]
            available = []
            for req in required:
                matches = by_vector.get(req, [])
                if matches:
                    best = max(matches, key=lambda f: f.get("cvss_score", 0))
                    available.append(best)

            if len(available) == len(required):
                chain = self._build_chain(pattern, available)
                chains.append(chain)
                self.record_decision(
                    decision=f"Built chain: {pattern['name']}",
                    reasoning=f"Combined {len(required)} findings into {pattern['combined_severity']} chain",
                    confidence=0.8,
                )

        # Ad-hoc chain discovery
        adhoc = self._discover_adhoc(findings, by_vector)
        chains.extend(adhoc)

        result = self._build_result(
            findings=chains,
            metadata={"chains_found": len(chains)},
        )
        result.duration_ms = (time.time() - start) * 1000
        return result

    def _build_chain(self, pattern: dict, findings: list) -> dict:
        """Build a chain from a known pattern."""
        chain_id = f"chain_{uuid.uuid4().hex[:8]}"
        steps = []
        for i, f in enumerate(findings):
            steps.append({
                "step": i + 1,
                "finding_id": f.get("finding_id", ""),
                "action": f.get("vuln_class", ""),
                "result": f.get("summary", "")[:100],
            })

        return {
            "agent": "CHAIN",
            "vuln_class": "Exploit Chain",
            "finding_id": chain_id,
            "file_path": findings[0].get("file_path", ""),
            "confidence": "plausible",
            "cvss_score": {"critical": 9.5, "high": 8.0, "medium": 6.0}.get(
                pattern["combined_severity"], 8.0),
            "summary": f"Chain: {pattern['name']}",
            "detail": f"{pattern['impact']}. Steps: {' → '.join(s['action'] for s in steps)}",
            "chain_steps": steps,
            "chain_name": pattern["name"],
            "individual_findings": [f.get("finding_id", "") for f in findings],
        }

    def _discover_adhoc(self, findings: list, by_vector: dict) -> list:
        """Discover chains not in known patterns."""
        chains = []
        # Simple heuristic: findings in the same file with different vuln classes
        by_file = {}
        for f in findings:
            fp = f.get("file_path", "")
            by_file.setdefault(fp, []).append(f)

        for fp, file_findings in by_file.items():
            if len(file_findings) < 2:
                continue
            vuln_classes = set(f.get("vuln_class", "") for f in file_findings)
            if len(vuln_classes) >= 2:
                # Check if any pair is complementary
                found_chain = False
                for vc1 in vuln_classes:
                    if found_chain:
                        break
                    for vc2 in vuln_classes:
                        if vc1 >= vc2:
                            continue
                        pair = tuple(sorted([vc1.lower(), vc2.lower()]))
                        if pair in COMPLEMENTARY_PAIRS:
                            chain_id = f"chain_{uuid.uuid4().hex[:8]}"
                            relevant = [f for f in file_findings
                                       if f.get("vuln_class", "").lower() in pair]
                            chains.append({
                                "agent": "CHAIN",
                                "vuln_class": "Exploit Chain",
                                "finding_id": chain_id,
                                "file_path": fp,
                                "confidence": "plausible",
                                "cvss_score": 8.5,
                                "summary": f"Ad-hoc chain: {' + '.join(vuln_classes)} in {fp}",
                                "detail": " + ".join(f.get("summary", "")[:60] for f in relevant),
                                "chain_steps": [{"step": i+1, "finding_id": f.get("finding_id", ""),
                                               "action": f.get("vuln_class", "")}
                                              for i, f in enumerate(relevant)],
                                "individual_findings": [f.get("finding_id", "") for f in relevant],
                            })
                            found_chain = True
                            break
        return chains
