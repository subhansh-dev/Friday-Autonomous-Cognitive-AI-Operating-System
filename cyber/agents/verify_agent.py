"""
Verify Agent — 3-round adversarial verification.
Round 1 (skeptic): default = "not real"
Round 2 (balanced): catch false negatives
Round 3 (final): fresh PoC confirmation
"""
import time
from typing import List
from .base_agent import BaseAgent, AgentRole, AgentResult


class VerifyAgent(BaseAgent):
    role = AgentRole.VERIFY
    tool_whitelist = ["exploit_engine", "findings_reader"]
    description = "3-round adversarial verification: skeptic → balanced → final."

    def execute(self, context: dict) -> AgentResult:
        start = time.time()
        findings = context.get("findings", [])
        run_exploits = context.get("run_exploits", False)

        if not findings:
            return self._build_result(error="No findings to verify")

        self.record_decision(
            decision=f"Verifying {len(findings)} findings through 3 rounds",
            reasoning="Adversarial verification kills false positives",
            confidence=0.8,
        )

        verified = []
        rejected = []
        hold = []

        for finding in findings:
            result = self._verify_finding(finding, run_exploits, context)
            if result["verdict"] == "verified":
                verified.append(finding)
            elif result["verdict"] == "rejected":
                rejected.append(finding)
            else:
                hold.append(finding)

        result = self._build_result(
            findings=verified,
            metadata={
                "verified": len(verified),
                "rejected": len(rejected),
                "hold": len(hold),
                "total": len(findings),
            },
        )
        result.duration_ms = (time.time() - start) * 1000
        return result

    def _verify_finding(self, finding: dict, run_exploits: bool,
                        context: dict) -> dict:
        """Run a finding through 3 verification rounds."""
        rounds = {}

        # Round 1: Skeptic
        r1 = self._skeptic_round(finding)
        rounds["skeptic"] = r1
        if not r1["passed"]:
            return {"verdict": "rejected", "rounds": rounds}

        # Round 2: Balanced
        r2 = self._balanced_round(finding, r1)
        rounds["balanced"] = r2
        if not r2["passed"]:
            return {"verdict": "hold", "rounds": rounds}

        # Round 3: Final
        r3 = self._final_round(finding, run_exploits, context)
        rounds["final"] = r3
        if r3["passed"]:
            finding["verification_rounds"] = rounds
            finding["confidence"] = "verified"
            return {"verdict": "verified", "rounds": rounds}

        return {"verdict": "hold", "rounds": rounds}

    def _skeptic_round(self, finding: dict) -> dict:
        """Round 1: Maximum skepticism. Default = 'not real'."""
        issues = []
        confidence = 0.0

        # Has evidence?
        evidence = finding.get("detail", "") or finding.get("summary", "")
        if not evidence:
            issues.append("No evidence provided")
            return {"passed": False, "confidence": 0.0, "issues": issues}

        # Has specific file/line reference?
        fp = finding.get("file_path", "")
        if not fp or fp == "unknown":
            issues.append("No specific file location")
            confidence -= 0.2

        # Confidence level from original finding
        orig_conf = finding.get("confidence", "plausible")
        if orig_conf == "confirmed":
            confidence += 0.4
        elif orig_conf == "plausible":
            confidence += 0.2
        elif orig_conf == "possible":
            confidence += 0.1

        # Has exploit evidence?
        if finding.get("exploit_evidence"):
            confidence += 0.3

        # CVSS score reasonableness
        cvss = finding.get("cvss_score", 5.0)
        if cvss >= 9.0 and not finding.get("exploit_evidence"):
            issues.append(f"CVSS {cvss} without exploit evidence — likely inflated")
            confidence -= 0.2

        # Evidence quality
        if len(evidence) > 20:
            confidence += 0.1

        passed = confidence >= 0.3 and len(issues) <= 2
        return {
            "passed": passed,
            "confidence": max(0, min(1, confidence)),
            "issues": issues,
            "reasoning": f"Skeptic: {len(issues)} issues, confidence {confidence:.0%}",
        }

    def _balanced_round(self, finding: dict, skeptic_result: dict) -> dict:
        """Round 2: Catch false negatives from skeptic."""
        confidence = skeptic_result.get("confidence", 0.3)
        issues = []

        # Known realistic attack vectors get a boost
        realistic = {"sql injection", "xss", "ssrf", "idor", "command injection",
                     "path traversal", "authentication bypass", "cors misconfiguration",
                     "open redirect", "unsafe deserialization"}
        vc = finding.get("vuln_class", "").lower()
        if vc in realistic:
            confidence += 0.15

        # Exploit evidence is strong confirmation
        if finding.get("exploit_evidence"):
            confidence += 0.2
            if finding.get("exploit_payloads_successful", 0) > 0:
                confidence += 0.1

        # Multiple findings in same file add credibility
        if finding.get("additional_evidence"):
            confidence += 0.1

        # Penalize generic descriptions
        summary = finding.get("summary", "").lower()
        generic = ["possible", "might be", "could potentially", "appears to be"]
        for phrase in generic:
            if phrase in summary:
                confidence -= 0.1
                issues.append(f"Generic language: '{phrase}'")

        passed = confidence >= 0.4
        return {
            "passed": passed,
            "confidence": max(0, min(1, confidence)),
            "issues": issues,
            "reasoning": f"Balanced: confidence {confidence:.0%}",
        }

    def _final_round(self, finding: dict, run_exploits: bool,
                     context: dict) -> dict:
        """Round 3: Final confirmation."""
        confidence = 0.5  # Start fresh
        issues = []

        # If we have exploit evidence, that's strong
        if finding.get("exploit_evidence"):
            confidence += 0.3
        elif finding.get("confidence") == "confirmed":
            confidence += 0.2
        else:
            confidence -= 0.1
            issues.append("No exploit confirmation")

        # Check for contradictions
        if finding.get("error"):
            issues.append(f"Finding has error: {finding['error'][:50]}")
            confidence -= 0.2

        # File-based findings need less proof than network findings
        fp = finding.get("file_path", "")
        if fp and not fp.startswith("http"):
            confidence += 0.1  # Static findings are more reliable

        passed = confidence >= 0.5 and len(issues) <= 1
        return {
            "passed": passed,
            "confidence": max(0, min(1, confidence)),
            "issues": issues,
            "reasoning": f"Final: confidence {confidence:.0%}",
        }
