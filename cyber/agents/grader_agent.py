"""
Grader Agent — 5-axis scoring: impact, confidence, exploitability, novelty, report quality.
"""
import time
from typing import List
from .base_agent import BaseAgent, AgentRole, AgentResult

SEVERITY_SCORES = {
    "critical": 9.0, "high": 7.5, "medium": 5.0, "low": 2.5, "info": 1.0,
}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

VERDICT_THRESHOLDS = {
    "submit": {"min_score": 7.0, "min_confidence": 7.0},
    "hold": {"min_score": 4.0, "min_confidence": 5.0},
}


class GraderAgent(BaseAgent):
    role = AgentRole.GRADER
    tool_whitelist = ["findings_reader"]
    description = "Grades findings on 5 axes and issues SUBMIT/HOLD/SKIP verdicts."

    def execute(self, context: dict) -> AgentResult:
        start = time.time()
        findings = context.get("findings", [])

        if not findings:
            return self._build_result(error="No findings to grade")

        self.record_decision(
            decision=f"Grading {len(findings)} findings on 5 axes",
            reasoning="5-axis rubric: impact, confidence, exploitability, novelty, report quality",
            confidence=0.9,
        )

        graded = []
        verdicts = {"submit": 0, "hold": 0, "skip": 0}

        for finding in findings:
            grade = self._grade_finding(finding)
            finding["grade"] = grade
            finding["verdict"] = grade["verdict"]
            graded.append(finding)
            verdicts[grade["verdict"]] += 1

        # Sort by total score descending
        graded.sort(key=lambda f: f["grade"]["total_score"], reverse=True)

        result = self._build_result(
            findings=graded,
            metadata={"verdicts": verdicts, "total_graded": len(graded)},
        )
        result.duration_ms = (time.time() - start) * 1000
        return result

    def _grade_finding(self, finding: dict) -> dict:
        """Grade a single finding on 5 axes."""
        # 1. Impact (0-10)
        impact = SEVERITY_SCORES.get(finding.get("vuln_class", "").lower(), 5.0)
        cvss = finding.get("cvss_score", 5.0)
        impact = (impact + cvss) / 2  # Average with CVSS

        # Boost for chains
        if finding.get("chain_steps"):
            impact = min(10, impact + 1.5)

        # 2. Confidence (0-10)
        confidence_map = {
            "verified": 9.0, "confirmed": 7.5, "plausible": 5.0, "possible": 3.0,
        }
        confidence = confidence_map.get(finding.get("confidence", "plausible"), 5.0)
        if finding.get("exploit_evidence"):
            confidence = min(10, confidence + 1.5)
        if finding.get("verification_rounds"):
            confidence = min(10, confidence + 1.0)

        # 3. Exploitability (0-10)
        exploitability = 5.0
        if finding.get("exploit_poc"):
            exploitability += 2.0
        if finding.get("exploit_payloads_successful", 0) > 0:
            exploitability += 1.5
        vc = finding.get("vuln_class", "").lower()
        easy_exploit = {"sql injection", "xss", "idor", "open redirect", "cors misconfiguration"}
        if vc in easy_exploit:
            exploitability += 1.0

        # 4. Novelty (0-10)
        novelty = 5.0
        common = {"xss", "sql injection", "hardcoded secret", "weak crypto", "information disclosure"}
        if vc not in common:
            novelty += 2.0
        if finding.get("chain_steps"):
            novelty += 1.5
        if finding.get("additional_evidence"):
            novelty += 0.5

        # 5. Report Quality (0-10)
        report_quality = 5.0
        if finding.get("exploit_poc"):
            report_quality += 2.0
        if finding.get("detail") and len(finding["detail"]) > 50:
            report_quality += 1.0
        if finding.get("file_path"):
            report_quality += 0.5
        if finding.get("summary") and len(finding["summary"]) > 20:
            report_quality += 0.5

        # Clamp
        impact = max(0, min(10, impact))
        confidence = max(0, min(10, confidence))
        exploitability = max(0, min(10, exploitability))
        novelty = max(0, min(10, novelty))
        report_quality = max(0, min(10, report_quality))

        # Weighted total
        total = (
            impact * 0.30 +
            confidence * 0.25 +
            exploitability * 0.20 +
            novelty * 0.10 +
            report_quality * 0.15
        )

        # Verdict
        if total >= 7.0 and confidence >= 7.0:
            verdict = "submit"
        elif total >= 4.0 and confidence >= 5.0:
            verdict = "hold"
        elif impact >= 8.0 and confidence >= 4.0:
            verdict = "hold"  # High impact, needs more evidence
        else:
            verdict = "skip"

        return {
            "impact": round(impact, 1),
            "confidence_score": round(confidence, 1),
            "exploitability": round(exploitability, 1),
            "novelty": round(novelty, 1),
            "report_quality": round(report_quality, 1),
            "total_score": round(total, 1),
            "verdict": verdict,
            "reasoning": (f"I={impact:.1f} C={confidence:.1f} E={exploitability:.1f} "
                         f"N={novelty:.1f} R={report_quality:.1f} → {total:.1f} → {verdict.upper()}"),
        }
