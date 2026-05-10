"""
Report Agent — Generates submission-ready security assessment reports.
"""
import time
from datetime import datetime
from typing import List
from .base_agent import BaseAgent, AgentRole, AgentResult


class ReportAgent(BaseAgent):
    role = AgentRole.REPORTER
    tool_whitelist = ["findings_reader", "file_writer"]
    description = "Generates submission-ready security assessment reports."

    def execute(self, context: dict) -> AgentResult:
        start = time.time()
        findings = context.get("findings", [])
        chains = context.get("chains", [])
        target = context.get("target", "Unknown")
        session_id = context.get("session_id", "")

        if not findings:
            return self._build_result(error="No findings to report")

        self.record_decision(
            decision=f"Generating report for {target}",
            reasoning=f"{len(findings)} findings, {len(chains)} chains",
            confidence=0.9,
        )

        report = self._generate_report(findings, chains, target, session_id)

        result = self._build_result(
            findings=[{"report": report}],
            metadata={"report_length": len(report), "findings_reported": len(findings)},
        )
        result.duration_ms = (time.time() - start) * 1000
        return result

    def _generate_report(self, findings: list, chains: list,
                         target: str, session_id: str) -> str:
        """Generate a complete security assessment report."""
        # Separate by verdict
        submit = [f for f in findings if f.get("verdict") == "submit"]
        hold = [f for f in findings if f.get("verdict") == "hold"]
        skip = [f for f in findings if f.get("verdict") == "skip"]

        # Sort by severity
        submit.sort(key=lambda f: SEVERITY_ORDER.get(
            f.get("vuln_class", "").lower(), 4))

        lines = [
            "# Security Assessment Report",
            "",
            f"**Target:** {target}",
            f"**Date:** {datetime.now().strftime('%Y-%m-%d')}",
            f"**Session:** {session_id}",
            "",
            "## Executive Summary",
            "",
            f"Assessed **{target}** and identified **{len(submit)} confirmed vulnerabilities** "
            f"and **{len(hold)} findings** requiring further investigation.",
            "",
        ]

        # Severity breakdown
        severity_counts = {}
        for f in submit:
            vc = f.get("vuln_class", "Unknown")
            severity_counts[vc] = severity_counts.get(vc, 0) + 1

        if severity_counts:
            lines.append("### Findings by Type")
            lines.append("")
            for vc, count in sorted(severity_counts.items(), key=lambda x: -x[1]):
                lines.append(f"- **{vc}:** {count}")
            lines.append("")

        # Exploit chains
        if chains:
            lines.append("## Exploit Chains")
            lines.append("")
            for chain in chains:
                lines.append(f"### {chain.get('chain_name', chain.get('summary', 'Chain'))}")
                chain_steps = chain.get("chain_steps", [])
                lines.append(f"**Severity:** {chain.get('cvss_score', 'N/A')}")
                lines.append(f"**Impact:** {chain.get('detail', '')[:150]}")
                if chain_steps:
                    lines.append("**Steps:**")
                    for step in chain_steps:
                        lines.append(f"  {step.get('step', '?')}. "
                                   f"{step.get('action', '?')} → {step.get('result', '?')[:80]}")
                lines.append("")

        # Confirmed findings
        if submit:
            lines.append("## Confirmed Vulnerabilities")
            lines.append("")
            for i, f in enumerate(submit, 1):
                grade = f.get("grade", {})
                lines.append(f"### {i}. {f.get('summary', f.get('vuln_class', 'Finding'))}")
                lines.append(f"**Severity:** {f.get('vuln_class', 'Unknown')}")
                if grade:
                    lines.append(f"**Score:** {grade.get('total_score', 'N/A')}/10")
                lines.append(f"**Location:** `{f.get('file_path', 'N/A')}`")
                lines.append(f"**Confidence:** {f.get('confidence', 'N/A')}")
                lines.append("")

                if f.get("detail"):
                    lines.append(f"**Description:** {f['detail'][:300]}")
                    lines.append("")

                if f.get("exploit_evidence"):
                    lines.append(f"**Exploit Evidence:** {f['exploit_evidence']}")
                    lines.append("")

                if f.get("exploit_poc"):
                    lines.append("**Proof of Concept:**")
                    for j, step in enumerate(f["exploit_poc"], 1):
                        lines.append(f"{j}. `{step}`")
                    lines.append("")

                if f.get("chain_steps"):
                    lines.append(f"**Part of chain:** {f.get('chain_name', 'Yes')}")
                    lines.append("")

                lines.append("---")
                lines.append("")

        # Hold findings
        if hold:
            lines.append("## Findings Requiring Further Investigation")
            lines.append("")
            for f in hold:
                lines.append(f"- **{f.get('vuln_class', 'Unknown')}** — "
                           f"{f.get('summary', '')[:100]} "
                           f"(`{f.get('file_path', '?')}`)")
            lines.append("")

        # Summary stats
        lines.append("## Statistics")
        lines.append("")
        lines.append(f"- **Total findings analyzed:** {len(findings)}")
        lines.append(f"- **Confirmed (SUBMIT):** {len(submit)}")
        lines.append(f"- **Needs investigation (HOLD):** {len(hold)}")
        lines.append(f"- **Low confidence (SKIP):** {len(skip)}")
        lines.append(f"- **Exploit chains:** {len(chains)}")
        lines.append("")

        return "\n".join(lines)


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
