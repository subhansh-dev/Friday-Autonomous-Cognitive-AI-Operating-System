"""
cyber/pipeline.py — Unified Cybersecurity Pipeline
===================================================

Orchestrates ALL cyber modules into a single end-to-end pipeline:
  RECON → HUNTER → DATA_FLOW → ADVERSARIAL → EXPLOIT → BUSINESS_LOGIC → CORRELATE → TRIAGE → REPORT

This is the bridge between the dead cyber modules and main.py.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

from brain.findings_bus import get_findings_bus

logger = logging.getLogger("friday.pipeline")


@dataclass
class UnifiedResult:
    """Result of the full cybersecurity pipeline."""
    target: str
    scan_type: str
    phases_run: list = field(default_factory=list)
    total_findings: int = 0
    confirmed_findings: int = 0
    denied_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    duration_ms: float = 0
    report: str = ""
    findings: list = field(default_factory=list)
    exploit_results: list = field(default_factory=list)
    data_flow_paths: int = 0
    business_logic_violations: int = 0


class CyberPipeline:
    """
    Unified cybersecurity pipeline that wires ALL cyber modules together.

    Usage:
        from cyber.pipeline import get_pipeline
        pipeline = get_pipeline()
        result = pipeline.run("/path/to/target", scan_type="full")
        print(result.report)
    """

    def __init__(self):
        self.bus = get_findings_bus()

    def run(self, target: str, scan_type: str = "full",
            target_url: str = None) -> UnifiedResult:
        """
        Run the full cybersecurity pipeline.

        Args:
            target: Local path OR URL to scan
            scan_type: "full" (all phases) or "quick" (static only)
            target_url: Optional URL for live exploit validation
        """
        start = time.time()
        result = UnifiedResult(target=target, scan_type=scan_type)

        # Clear the findings bus for this run
        self.bus.prune()

        # Phase 1: Static Analysis (Mythos Pipeline)
        self._phase_static_analysis(target, result)

        # Phase 2: Data Flow Analysis
        if scan_type == "full":
            self._phase_data_flow(target, result)

        # Phase 3: Cognitive Reasoning (chain building, verification, grading)
        self._phase_cognitive_reasoning(target, result)

        # Phase 4: Exploit Validation (if we have a URL)
        if target_url and scan_type == "full":
            self._phase_exploit_validation(target_url, result)

        # Phase 5: Business Logic Testing (if we have a URL)
        if target_url and scan_type == "full":
            self._phase_business_logic(target_url, result)

        # Phase 6: Correlation & Deduplication
        self._phase_correlation(result)

        # Phase 7: Triage & Grading
        self._phase_triage(result)

        # Phase 8: Generate Report
        result.report = self._generate_report(result)
        result.duration_ms = (time.time() - start) * 1000

        return result

    # ── Phase 1: Static Analysis ──────────────────────────────────────

    def _phase_static_analysis(self, target: str, result: UnifiedResult):
        """Run the mythos 7-agent static analysis pipeline."""
        try:
            from cyber.mythos_pipeline import get_mythos_pipeline
            pipeline = get_mythos_pipeline()
            mythos_result = pipeline.run(target, scan_type="full")

            result.phases_run.append("STATIC_ANALYSIS")
            result.total_findings += mythos_result.total_findings
            result.findings.extend(self.bus.read())

            logger.info(f"Static analysis: {mythos_result.total_findings} findings")
        except Exception as e:
            logger.error(f"Static analysis failed: {e}")
            result.phases_run.append(f"STATIC_ANALYSIS(ERROR: {e})")

    # ── Phase 2: Data Flow Analysis ───────────────────────────────────

    def _phase_data_flow(self, target: str, result: UnifiedResult):
        """Trace data from user-input sources to dangerous sinks."""
        try:
            from cyber.data_flow_analyzer import DataFlowAnalyzer
            analyzer = DataFlowAnalyzer()
            flow_result = analyzer.analyze(target)

            # Write data flow findings to bus
            flow_findings = flow_result.to_findings()
            for f in flow_findings:
                self.bus.write(f)

            result.phases_run.append("DATA_FLOW")
            result.data_flow_paths = len(flow_result.paths)
            result.total_findings += len(flow_findings)
            result.findings.extend(flow_findings)

            logger.info(f"Data flow: {len(flow_result.paths)} paths in {flow_result.files_analyzed} files")
        except Exception as e:
            logger.error(f"Data flow analysis failed: {e}")
            result.phases_run.append(f"DATA_FLOW(ERROR: {e})")

    # ── Phase 3: Cognitive Reasoning ──────────────────────────────────

    def _phase_cognitive_reasoning(self, target: str, result: UnifiedResult):
        """Use the CyberReasoningEngine for chain building, verification, and grading."""
        try:
            from brain.cyber_reasoning import CyberReasoningEngine
            engine = CyberReasoningEngine()

            # Start a session
            session = engine.start_session(target)

            # Feed all current findings into the reasoning engine
            all_findings = self.bus.read()
            for f in all_findings:
                engine.record_finding(session.session_id, f)

            # Build exploit chains
            chain_report = engine.build_chains(session.session_id)

            # Grade findings
            grade_report = engine.grade_findings(session.session_id)

            # Get the session's chains and add them as findings
            session = engine.get_session(session.session_id)
            if session:
                for chain_id, chain in session.chains.items():
                    finding = {
                        "agent": "COGNITIVE_REASONING",
                        "finding_id": f"chain_{chain_id}",
                        "file_path": target,
                        "vuln_class": "Exploit Chain",
                        "confidence": "confirmed" if chain.verified else "plausible",
                        "cvss_score": 9.5 if chain.combined_severity.value == "critical" else 8.0,
                        "summary": f"[CHAIN] {chain.name}: {chain.description}",
                        "detail": json.dumps({
                            "steps": chain.steps,
                            "individual_findings": chain.individual_findings,
                            "confidence": chain.confidence,
                        }),
                    }
                    self.bus.write(finding)
                    result.findings.append(finding)

                # Add graded findings back
                for fid, grade in session.grades.items():
                    if grade.verdict.value == "submit":
                        # High-confidence graded finding
                        finding = {
                            "agent": "COGNITIVE_GRADER",
                            "finding_id": f"graded_{fid}",
                            "file_path": target,
                            "vuln_class": "Graded Finding",
                            "confidence": "confirmed",
                            "cvss_score": grade.total_score,
                            "summary": f"[GRADED] Score {grade.total_score:.1f}/10 — {grade.reasoning[:100]}",
                            "detail": json.dumps({
                                "impact": grade.impact_score,
                                "confidence": grade.confidence_score,
                                "exploitability": grade.exploitability_score,
                                "novelty": grade.novelty_score,
                                "report_quality": grade.report_quality_score,
                                "verdict": grade.verdict.value,
                            }),
                        }
                        self.bus.write(finding)

            result.phases_run.append("COGNITIVE_REASONING")
            logger.info(f"Cognitive reasoning: chains + grading complete")
        except Exception as e:
            logger.error(f"Cognitive reasoning failed: {e}")
            result.phases_run.append(f"COGNITIVE_REASONING(ERROR: {e})")

    # ── Phase 3: Exploit Validation ───────────────────────────────────

    def _phase_exploit_validation(self, target_url: str, result: UnifiedResult):
        """Validate findings with live PoC execution (non-destructive)."""
        try:
            from cyber.exploit_engine import get_exploit_engine
            engine = get_exploit_engine()

            # Get all findings that have exploitable vuln classes
            all_findings = self.bus.read()

            # Update findings with target URL for exploit engine
            for f in all_findings:
                if not f.get("target"):
                    f["target"] = target_url

            batch = engine.exploit_batch(all_findings)

            # Write exploit results back to bus
            for attempt in batch.attempts:
                if attempt.confirmed:
                    finding = {
                        "agent": "EXPLOIT_VALIDATOR",
                        "finding_id": f"exploit_{attempt.finding_id}",
                        "file_path": attempt.target,
                        "vuln_class": attempt.vuln_class,
                        "confidence": "confirmed",
                        "cvss_score": 9.0,
                        "summary": f"[CONFIRMED] {attempt.vuln_class} — {attempt.best_evidence[:100]}",
                        "detail": json.dumps({
                            "payloads_tested": attempt.total_payloads,
                            "successful": attempt.successful_payloads,
                            "evidence": attempt.best_evidence,
                            "poc_steps": attempt.best_poc,
                        }),
                    }
                    self.bus.write(finding)
                    result.exploit_results.append(attempt)

            result.phases_run.append("EXPLOIT_VALIDATION")
            result.confirmed_findings += batch.confirmed
            result.denied_findings += batch.denied
            result.total_findings += batch.confirmed

            logger.info(f"Exploit validation: {batch.confirmed} confirmed, {batch.denied} denied")
        except Exception as e:
            logger.error(f"Exploit validation failed: {e}")
            result.phases_run.append(f"EXPLOIT_VALIDATION(ERROR: {e})")

    # ── Phase 4: Business Logic Testing ───────────────────────────────

    def _phase_business_logic(self, target_url: str, result: UnifiedResult):
        """Test for business logic vulnerabilities."""
        try:
            from cyber.business_logic_tester import BusinessLogicTester
            tester = BusinessLogicTester()

            # Discover endpoints and test invariants
            endpoints = tester._discover_endpoints(target_url)
            if endpoints:
                bl_result = tester.test(endpoints=endpoints)
                violations = bl_result.get("violations", [])

                for v in violations:
                    finding = {
                        "agent": "BUSINESS_LOGIC",
                        "finding_id": f"bl_{hash(str(v)) % 10000:04d}",
                        "file_path": target_url,
                        "vuln_class": v.get("invariant_type", "Business Logic"),
                        "confidence": "plausible",
                        "cvss_score": v.get("severity", 6.0),
                        "summary": f"Business logic violation: {v.get('description', 'Unknown')}",
                        "detail": json.dumps(v),
                    }
                    self.bus.write(finding)
                    result.findings.append(finding)

                result.business_logic_violations = len(violations)
                result.total_findings += len(violations)

            result.phases_run.append("BUSINESS_LOGIC")
            logger.info(f"Business logic: {result.business_logic_violations} violations")
        except Exception as e:
            logger.error(f"Business logic testing failed: {e}")
            result.phases_run.append(f"BUSINESS_LOGIC(ERROR: {e})")

    # ── Phase 5: Correlation ──────────────────────────────────────────

    def _phase_correlation(self, result: UnifiedResult):
        """Deduplicate and correlate findings across all phases."""
        try:
            from cyber.correlator import get_correlator
            correlator = get_correlator()

            all_findings = self.bus.read()
            report = correlator.correlate(all_findings)

            # Update result with correlated findings
            confirmed = report.get("confirmed", [])
            result.confirmed_findings += len(confirmed)

            result.phases_run.append("CORRELATION")
            logger.info(f"Correlation: {report.get('summary', {}).get('total_static', 0)} findings, "
                       f"{len(confirmed)} confirmed dynamically")
        except Exception as e:
            logger.error(f"Correlation failed: {e}")
            result.phases_run.append(f"CORRELATION(ERROR: {e})")

    # ── Phase 6: Triage ───────────────────────────────────────────────

    def _phase_triage(self, result: UnifiedResult):
        """Grade and categorize all findings by severity."""
        all_findings = self.bus.read()

        for f in all_findings:
            score = f.get("cvss_score", 0)
            if score >= 9.0:
                result.critical_count += 1
            elif score >= 7.0:
                result.high_count += 1
            elif score >= 4.0:
                result.medium_count += 1
            else:
                result.low_count += 1

        result.phases_run.append("TRIAGE")
        result.total_findings = len(all_findings)

    # ── Report Generation ─────────────────────────────────────────────

    def _generate_report(self, result: UnifiedResult) -> str:
        """Generate a comprehensive security report."""
        all_findings = self.bus.read()

        lines = [
            "# 🔒 Security Assessment Report",
            "",
            f"**Target:** `{result.target}`",
            f"**Scan Type:** {result.scan_type}",
            f"**Phases:** {' → '.join(result.phases_run)}",
            f"**Duration:** {result.duration_ms:.0f}ms",
            "",
            "## 📊 Summary",
            "",
            f"| Severity | Count |",
            f"|----------|-------|",
            f"| 🔴 Critical | {result.critical_count} |",
            f"| 🟠 High | {result.high_count} |",
            f"| 🟡 Medium | {result.medium_count} |",
            f"| 🔵 Low | {result.low_count} |",
            f"| **Total** | **{result.total_findings}** |",
            "",
        ]

        if result.data_flow_paths:
            lines.append(f"**Data Flow Paths:** {result.data_flow_paths}")
        if result.confirmed_findings:
            lines.append(f"**Confirmed by Exploit:** {result.confirmed_findings}")
        if result.denied_findings:
            lines.append(f"**Denied by Exploit:** {result.denied_findings}")
        if result.business_logic_violations:
            lines.append(f"**Business Logic Violations:** {result.business_logic_violations}")
        lines.append("")

        # Critical/High findings detail
        critical_high = sorted(
            [f for f in all_findings if f.get("cvss_score", 0) >= 7.0],
            key=lambda x: x.get("cvss_score", 0),
            reverse=True,
        )

        if critical_high:
            lines.append("## 🚨 Critical & High Findings")
            lines.append("")
            for f in critical_high[:20]:
                score = f.get("cvss_score", 0)
                vclass = f.get("vuln_class", "Unknown")
                fpath = f.get("file_path", "?")
                summary = f.get("summary", "")
                agent = f.get("agent", "?")
                conf = f.get("confidence", "?")
                emoji = "🔴" if score >= 9.0 else "🟠"
                lines.append(f"- {emoji} **[{vclass}]** CVSS {score} `{fpath}` ({agent}, {conf})")
                lines.append(f"  {summary}")
            lines.append("")

        # Exploit results
        if result.exploit_results:
            lines.append("## 💥 Exploit Validation Results")
            lines.append("")
            for attempt in result.exploit_results:
                lines.append(f"- ✅ **{attempt.vuln_class}** confirmed at `{attempt.target}`")
                lines.append(f"  Evidence: {attempt.best_evidence[:150]}")
                if attempt.best_poc:
                    lines.append(f"  PoC: {' → '.join(attempt.best_poc[:3])}")
            lines.append("")

        # Medium findings (compact)
        medium = [f for f in all_findings if 4.0 <= f.get("cvss_score", 0) < 7.0]
        if medium:
            lines.append("## ⚠️ Medium Findings")
            lines.append("")
            for f in medium[:15]:
                score = f.get("cvss_score", 0)
                vclass = f.get("vuln_class", "Unknown")
                summary = f.get("summary", "")[:80]
                lines.append(f"- [{vclass}] CVSS {score} — {summary}")
            lines.append("")

        # Recommendations
        lines.append("## 🛡️ Recommendations")
        lines.append("")
        if result.critical_count > 0:
            lines.append("- **IMMEDIATE:** Fix critical vulnerabilities before deployment")
        if result.high_count > 0:
            lines.append("- **HIGH PRIORITY:** Address high-severity findings")
        if result.data_flow_paths > 0:
            lines.append("- **DATA FLOW:** Review source-to-sink paths for injection risks")
        if result.business_logic_violations > 0:
            lines.append("- **BUSINESS LOGIC:** Review invariant violations for logic flaws")
        if result.total_findings == 0:
            lines.append("- No significant findings. Consider deeper manual review.")
        lines.append("")

        return "\n".join(lines)


# Singleton
_pipeline: Optional[CyberPipeline] = None


def get_pipeline() -> CyberPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = CyberPipeline()
    return _pipeline
