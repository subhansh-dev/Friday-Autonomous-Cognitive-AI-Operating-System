#!/usr/bin/env python3
"""
cyber_reasoning.py — FRIDAY Cognitive Cybersecurity Reasoning Engine
=====================================================================

Advanced security reasoning inspired by autonomous bug bounty architectures:
- 7-phase FSM pipeline: RECON → HUNT → CHAIN → VERIFY → GRADE → REPORT
- 3-round adversarial verification (skeptic → balanced → final)
- Chain-building: connects low-severity findings into high-impact exploit chains
- 5-axis grading rubric with SUBMIT/HOLD/SKIP verdicts
- Structured JSON artifacts as single source of truth
- Per-task reasoning with hypothesis tracking and decision journaling

Architecture:
  Target → [Recon] → Attack Surface → [Hunt] → Raw Findings
        → [Chain] → Exploit Chains → [Verify] → Validated Findings
        → [Grade] → Scored Findings → [Report] → Submission-Ready Report

Each phase uses structured reasoning:
  1. Formulate hypotheses about what vulnerabilities might exist
  2. Design tests to validate/invalidate each hypothesis
  3. Execute tests and record evidence
  4. Adversarially challenge findings before accepting them
  5. Chain related findings into higher-impact exploits
  6. Grade on multiple axes before deciding SUBMIT/HOLD/SKIP
"""

import json
import hashlib
import time
import threading
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum


# ── Constants ─────────────────────────────────────────────────────────

BRAIN_DIR = Path(__file__).parent.resolve()
SESSIONS_DIR = BRAIN_DIR / "cyber_sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


# ── Enums ─────────────────────────────────────────────────────────────

class Phase(Enum):
    RECON = "recon"
    HUNT = "hunt"
    CHAIN = "chain"
    VERIFY = "verify"
    GRADE = "grade"
    REPORT = "report"
    COMPLETE = "complete"


class Verdict(Enum):
    SUBMIT = "submit"       # Ready for submission
    HOLD = "hold"           # Needs more evidence
    SKIP = "skip"           # False positive or low value
    CHAIN_ONLY = "chain"    # Only valuable as part of a chain


class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class VerificationRound(Enum):
    SKEPTIC = "skeptic"     # Round 1: maximum skepticism, default = "not real"
    BALANCED = "balanced"   # Round 2: catch false negatives
    FINAL = "final"         # Round 3: fresh PoC confirmation


# ── Data Classes ──────────────────────────────────────────────────────

@dataclass
class Hypothesis:
    """A vulnerability hypothesis to test."""
    id: str
    description: str
    attack_vector: str
    target_surface: str
    confidence: float = 0.3          # Prior probability
    evidence: List[str] = field(default_factory=list)
    tests_run: int = 0
    tests_passed: int = 0
    status: str = "pending"          # pending, testing, confirmed, rejected
    created_at: str = ""
    resolved_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    @property
    def evidence_strength(self) -> float:
        if not self.evidence:
            return 0.0
        return min(1.0, len(self.evidence) * 0.2 + self.tests_passed * 0.15)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Finding:
    """A security finding with full audit trail."""
    id: str
    title: str
    description: str
    severity: Severity
    target: str
    attack_vector: str
    evidence: List[str] = field(default_factory=list)
    poc_steps: List[str] = field(default_factory=list)
    impact: str = ""
    affected_components: List[str] = field(default_factory=list)
    cvss_estimate: float = 0.0
    hypothesis_id: str = ""
    verification_rounds: Dict[str, dict] = field(default_factory=dict)
    chain_ids: List[str] = field(default_factory=list)
    verdict: Verdict = Verdict.HOLD
    grade: Dict[str, float] = field(default_factory=dict)
    created_at: str = ""
    verified_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    @property
    def is_verified(self) -> bool:
        """A finding is verified only if it passed all 3 rounds."""
        required = {"skeptic", "balanced", "final"}
        passed = {r for r, v in self.verification_rounds.items() if v.get("passed")}
        return required.issubset(passed)

    @property
    def verification_confidence(self) -> float:
        if not self.verification_rounds:
            return 0.0
        confidences = [v.get("confidence", 0) for v in self.verification_rounds.values()]
        return sum(confidences) / len(confidences) if confidences else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["verdict"] = self.verdict.value
        d["is_verified"] = self.is_verified
        d["verification_confidence"] = self.verification_confidence
        return d


@dataclass
class ExploitChain:
    """An A→B exploit chain combining multiple findings."""
    id: str
    name: str
    description: str
    steps: List[dict]              # [{finding_id, action, result}]
    combined_severity: Severity
    combined_impact: str
    individual_findings: List[str]  # finding IDs
    confidence: float = 0.0
    verified: bool = False

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["combined_severity"] = self.combined_severity.value
        return d


@dataclass
class GradeResult:
    """5-axis grading for a finding."""
    finding_id: str
    impact_score: float          # 0-10: how bad is exploitation
    confidence_score: float      # 0-10: how sure are we it's real
    exploitability_score: float  # 0-10: how easy to exploit
    novelty_score: float         # 0-10: how unique/interesting
    report_quality_score: float  # 0-10: how well documented
    verdict: Verdict = Verdict.HOLD
    reasoning: str = ""

    @property
    def total_score(self) -> float:
        weights = {
            "impact": 0.30,
            "confidence": 0.25,
            "exploitability": 0.20,
            "novelty": 0.10,
            "report_quality": 0.15,
        }
        return (
            self.impact_score * weights["impact"]
            + self.confidence_score * weights["confidence"]
            + self.exploitability_score * weights["exploitability"]
            + self.novelty_score * weights["novelty"]
            + self.report_quality_score * weights["report_quality"]
        )

    def auto_verdict(self) -> Verdict:
        score = self.total_score
        if score >= 7.0 and self.confidence_score >= 7.0:
            return Verdict.SUBMIT
        elif score >= 4.0 and self.confidence_score >= 5.0:
            return Verdict.HOLD
        elif self.impact_score >= 8.0 and self.confidence_score >= 4.0:
            return Verdict.HOLD  # High impact, needs more evidence
        else:
            return Verdict.SKIP

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        d["total_score"] = self.total_score
        return d


@dataclass
class DecisionEntry:
    """A reasoning decision with full context."""
    id: str
    phase: str
    decision: str
    reasoning: str
    alternatives_considered: List[str]
    confidence: float
    outcome: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


# ── Session State ─────────────────────────────────────────────────────

class CyberSession:
    """A complete security assessment session with full state tracking."""

    def __init__(self, target: str, session_id: str = None):
        self.session_id = session_id or f"cyber_{uuid.uuid4().hex[:8]}"
        self.target = target
        self.phase = Phase.RECON
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at

        # Core state
        self.hypotheses: Dict[str, Hypothesis] = {}
        self.findings: Dict[str, Finding] = {}
        self.chains: Dict[str, ExploitChain] = {}
        self.grades: Dict[str, GradeResult] = {}
        self.decisions: List[DecisionEntry] = []

        # Recon data
        self.attack_surface: Dict[str, Any] = {
            "subdomains": [],
            "live_hosts": [],
            "open_ports": [],
            "technologies": [],
            "endpoints": [],
            "secrets_found": [],
            "nuclei_results": [],
        }

        # Phase history
        self.phase_history: List[dict] = []
        self._lock = threading.RLock()

    @property
    def is_complete(self) -> bool:
        return self.phase == Phase.COMPLETE

    @property
    def finding_count(self) -> dict:
        counts = defaultdict(int)
        for f in self.findings.values():
            counts[f.severity.value] += 1
        counts["total"] = len(self.findings)
        counts["verified"] = sum(1 for f in self.findings.values() if f.is_verified)
        counts["submit_ready"] = sum(1 for f in self.findings.values()
                                     if f.verdict == Verdict.SUBMIT)
        return dict(counts)

    def record_decision(self, phase: str, decision: str, reasoning: str,
                        alternatives: List[str], confidence: float) -> str:
        """Record a reasoning decision with full context."""
        entry = DecisionEntry(
            id=f"dec_{uuid.uuid4().hex[:8]}",
            phase=phase,
            decision=decision,
            reasoning=reasoning,
            alternatives_considered=alternatives,
            confidence=confidence,
        )
        with self._lock:
            self.decisions.append(entry)
        return entry.id

    def transition_phase(self, new_phase: Phase, reason: str):
        """Record a phase transition."""
        old = self.phase
        self.phase = new_phase
        self.updated_at = datetime.now().isoformat()
        self.phase_history.append({
            "from": old.value,
            "to": new_phase.value,
            "reason": reason,
            "timestamp": self.updated_at,
        })

    def save(self):
        """Persist session to disk."""
        session_dir = SESSIONS_DIR / self.target.replace("/", "_").replace(":", "_")
        session_dir.mkdir(parents=True, exist_ok=True)
        state_file = session_dir / "state.json"
        state_file.write_text(json.dumps(self.to_dict(), indent=2, default=str),
                              encoding="utf-8")

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "target": self.target,
            "phase": self.phase.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "finding_count": self.finding_count,
            "hypotheses": {k: v.to_dict() for k, v in self.hypotheses.items()},
            "findings": {k: v.to_dict() for k, v in self.findings.items()},
            "chains": {k: v.to_dict() for k, v in self.chains.items()},
            "grades": {k: v.to_dict() for k, v in self.grades.items()},
            "decisions": [d.to_dict() for d in self.decisions],
            "attack_surface": self.attack_surface,
            "phase_history": self.phase_history,
        }

    def format_summary(self) -> str:
        """Human-readable session summary."""
        counts = self.finding_count
        lines = [
            f"🔒 Cyber Session: {self.target}",
            f"Phase: {self.phase.value.upper()}",
            f"Hypotheses: {len(self.hypotheses)} "
            f"({sum(1 for h in self.hypotheses.values() if h.status == 'confirmed')} confirmed)",
            f"Findings: {counts['total']} total, {counts['verified']} verified, "
            f"{counts['submit_ready']} submit-ready",
            f"Chains: {len(self.chains)}",
            f"Decisions: {len(self.decisions)}",
        ]
        if counts.get("critical"):
            lines.append(f"  🔴 Critical: {counts['critical']}")
        if counts.get("high"):
            lines.append(f"  🟠 High: {counts['high']}")
        if counts.get("medium"):
            lines.append(f"  🟡 Medium: {counts['medium']}")
        if counts.get("low"):
            lines.append(f"  🟢 Low: {counts['low']}")
        return "\n".join(lines)


# ── Adversarial Verification Engine ───────────────────────────────────

class AdversarialVerifier:
    """
    3-round adversarial verification that kills hallucinated findings.

    Round 1 — Skeptic: Default answer is "this isn't real, prove me wrong."
              Re-runs every PoC, checks for false positives aggressively.
    Round 2 — Balanced: Looks for false negatives the skeptic rejected.
              Catches severity under-correction.
    Round 3 — Final: Fresh PoC with fresh context. Last confirmation.
    """

    def __init__(self, session: CyberSession):
        self.session = session

    def verify_finding(self, finding: Finding, run_test_fn=None) -> Finding:
        """Run a finding through all 3 verification rounds."""
        # Round 1: Skeptic
        r1 = self._skeptic_round(finding, run_test_fn)
        finding.verification_rounds["skeptic"] = r1
        if not r1["passed"]:
            finding.verdict = Verdict.SKIP
            return finding

        # Round 2: Balanced
        r2 = self._balanced_round(finding, run_test_fn)
        finding.verification_rounds["balanced"] = r2
        if not r2["passed"]:
            finding.verdict = Verdict.HOLD
            return finding

        # Round 3: Final
        r3 = self._final_round(finding, run_test_fn)
        finding.verification_rounds["final"] = r3
        if r3["passed"]:
            finding.verdict = Verdict.SUBMIT
            finding.verified_at = datetime.now().isoformat()

        return finding

    def _skeptic_round(self, finding: Finding, run_test_fn) -> dict:
        """
        Round 1: Maximum skepticism. Default = "not real."
        Challenges every piece of evidence.
        """
        issues = []
        confidence = 0.0

        # Check 1: Is there actual evidence?
        if not finding.evidence:
            issues.append("No evidence provided")
            return {"passed": False, "confidence": 0.0, "issues": issues,
                    "round": "skeptic", "reasoning": "No evidence to verify"}

        # Check 2: Are PoC steps specific enough?
        if not finding.poc_steps:
            issues.append("No PoC steps — cannot reproduce")
            confidence -= 0.3

        # Check 3: Is the severity justified by the evidence?
        severity_evidence_map = {
            Severity.CRITICAL: 3,  # Needs strong evidence
            Severity.HIGH: 2,
            Severity.MEDIUM: 2,
            Severity.LOW: 1,
            Severity.INFO: 1,
        }
        min_evidence = severity_evidence_map.get(finding.severity, 2)
        if len(finding.evidence) < min_evidence:
            issues.append(
                f"Severity {finding.severity.value} requires ≥{min_evidence} evidence "
                f"points, only {len(finding.evidence)} provided"
            )
            confidence -= 0.2

        # Check 4: Run PoC if test function available
        if run_test_fn and finding.poc_steps:
            try:
                test_result = run_test_fn(finding.poc_steps)
                if test_result.get("success"):
                    confidence += 0.4
                    finding.evidence.append(f"Skeptic round PoC verified: {test_result.get('output', '')[:200]}")
                else:
                    issues.append(f"PoC reproduction failed: {test_result.get('error', 'unknown')}")
                    confidence -= 0.5
            except Exception as e:
                issues.append(f"PoC test error: {e}")
                confidence -= 0.3

        # Check 5: Evidence consistency
        # Note: "error" in evidence can be positive (e.g., "SQL error leaked" for SQLi)
        # Only flag if there are more negative than positive signals
        evidence_text = " ".join(finding.evidence).lower()
        positive_words = ["confirmed", "verified", "success", "found", "detected", "leaked", "injected"]
        negative_words = ["failed", "not found", "blocked", "denied", "no vulnerability", "clean"]
        pos_count = sum(1 for w in positive_words if w in evidence_text)
        neg_count = sum(1 for w in negative_words if w in evidence_text)
        if neg_count > pos_count:
            issues.append("Evidence contains more negative than positive signals")
            confidence -= 0.1

        # Base confidence from evidence quality
        confidence += min(0.5, len(finding.evidence) * 0.1)

        passed = confidence >= 0.3 and len(issues) <= 2
        return {
            "passed": passed,
            "confidence": round(max(0, min(1, confidence)), 2),
            "issues": issues,
            "round": "skeptic",
            "reasoning": f"Skeptic analysis: {len(issues)} issues found, "
                        f"confidence {confidence:.0%}. "
                        f"{'PASSED — evidence is credible' if passed else 'FAILED — insufficient evidence'}.",
        }

    def _balanced_round(self, finding: Finding, run_test_fn) -> dict:
        """
        Round 2: Balanced review. Catches false negatives.
        Asks: "Did the skeptic reject this too aggressively?"
        """
        issues = []
        confidence = finding.verification_rounds.get("skeptic", {}).get("confidence", 0.5)

        # Re-check: Is the attack vector realistic?
        realistic_vectors = {
            "xss", "sqli", "ssrf", "idor", "rce", "lfi", "rfi",
            "authentication_bypass", "authorization_bypass", "race_condition",
            "prototype_pollution", "deserialization", "command_injection",
            "open_redirect", "cors_misconfiguration", "information_disclosure",
        }
        if finding.attack_vector.lower().replace(" ", "_") in realistic_vectors:
            confidence += 0.15  # Known realistic attack type

        # Re-check: Does the impact description make sense?
        if finding.impact and len(finding.impact) > 20:
            confidence += 0.1

        # Re-check: Are affected components specific?
        if finding.affected_components:
            confidence += 0.05

        # Re-check: Is there a chain opportunity?
        if finding.chain_ids:
            confidence += 0.1  # Chain context adds credibility

        # Penalize generic descriptions
        generic_phrases = ["possible vulnerability", "might be vulnerable",
                          "could potentially", "appears to be"]
        desc_lower = finding.description.lower()
        for phrase in generic_phrases:
            if phrase in desc_lower:
                confidence -= 0.1
                issues.append(f"Generic description: '{phrase}'")

        passed = confidence >= 0.4
        return {
            "passed": passed,
            "confidence": round(max(0, min(1, confidence)), 2),
            "issues": issues,
            "round": "balanced",
            "reasoning": f"Balanced review: adjusted confidence to {confidence:.0%}. "
                        f"{'PASSED — skeptic was too aggressive' if passed else 'CONFIRMED SKIP — not a false negative'}.",
        }

    def _final_round(self, finding: Finding, run_test_fn) -> dict:
        """
        Round 3: Final confirmation with fresh context.
        Fresh PoC execution, independent of previous rounds.
        """
        issues = []
        confidence = finding.verification_rounds.get("balanced", {}).get("confidence", 0.5)

        # Final PoC run (fresh context)
        if run_test_fn and finding.poc_steps:
            try:
                test_result = run_test_fn(finding.poc_steps)
                if test_result.get("success"):
                    confidence += 0.3
                    finding.evidence.append(f"Final round PoC confirmed: {test_result.get('output', '')[:200]}")
                else:
                    issues.append(f"Final PoC failed — finding may be flaky")
                    confidence -= 0.4
            except Exception as e:
                issues.append(f"Final test error: {e}")
                confidence -= 0.2
        else:
            # No PoC to run — lower confidence
            confidence -= 0.1

        # Check for contradictions in evidence
        if len(finding.evidence) >= 2:
            # Simple contradiction check
            positive = sum(1 for e in finding.evidence if any(
                w in e.lower() for w in ["confirmed", "verified", "success", "found", "detected"]
            ))
            negative = sum(1 for e in finding.evidence if any(
                w in e.lower() for w in ["failed", "error", "not found", "blocked", "denied"]
            ))
            if negative > positive:
                issues.append("Evidence contradicts finding — more negative than positive signals")
                confidence -= 0.2

        passed = confidence >= 0.5 and len(issues) <= 1
        return {
            "passed": passed,
            "confidence": round(max(0, min(1, confidence)), 2),
            "issues": issues,
            "round": "final",
            "reasoning": f"Final verification: confidence {confidence:.0%}. "
                        f"{'CONFIRMED — finding is real' if passed else 'REJECTED — could not confirm'}.",
        }


# ── Chain Builder ─────────────────────────────────────────────────────

class ChainBuilder:
    """
    Builds A→B exploit chains from individual findings.
    Low-severity findings can chain into critical exploits.

    Example chains:
    - Info disclosure (low) + IDOR (medium) = Account takeover (critical)
    - CORS misconfig (medium) + XSS (medium) = Token theft (high)
    - Open redirect (low) + OAuth misconfig (medium) = Account hijack (critical)
    """

    # Known chain patterns
    CHAIN_PATTERNS = [
        {
            "name": "Account Takeover via Info Disclosure + IDOR",
            "requires": ["information_disclosure", "idor"],
            "combined_severity": Severity.CRITICAL,
            "impact": "Full account takeover — attacker can access any user's data",
        },
        {
            "name": "Token Theft via CORS + XSS",
            "requires": ["cors_misconfiguration", "xss"],
            "combined_severity": Severity.HIGH,
            "impact": "Steal auth tokens from any user visiting attacker-controlled page",
        },
        {
            "name": "Account Hijack via Redirect + OAuth",
            "requires": ["open_redirect", "authentication_bypass"],
            "combined_severity": Severity.CRITICAL,
            "impact": "Hijack accounts via OAuth redirect manipulation",
        },
        {
            "name": "RCE via File Upload + Path Traversal",
            "requires": ["file_upload", "lfi"],
            "combined_severity": Severity.CRITICAL,
            "impact": "Remote code execution through uploaded webshell",
        },
        {
            "name": "Privilege Escalation via IDOR + Weak Authorization",
            "requires": ["idor", "authorization_bypass"],
            "combined_severity": Severity.HIGH,
            "impact": "Escalate from regular user to admin by modifying other users' roles",
        },
        {
            "name": "Data Exfiltration via SSRF + Metadata",
            "requires": ["ssrf", "information_disclosure"],
            "combined_severity": Severity.HIGH,
            "impact": "Access cloud metadata and internal services via SSRF chain",
        },
        {
            "name": "Full Compromise via SQLi + File Write",
            "requires": ["sqli", "file_upload"],
            "combined_severity": Severity.CRITICAL,
            "impact": "Write webshell to disk via SQL injection INTO OUTFILE",
        },
    ]

    def __init__(self, session: CyberSession):
        self.session = session

    def discover_chains(self) -> List[ExploitChain]:
        """Analyze all findings and discover exploit chains."""
        chains = []
        finding_by_vector = defaultdict(list)

        # Index findings by attack vector
        for f in self.session.findings.values():
            if f.verdict != Verdict.SKIP:
                vector_key = f.attack_vector.lower().replace(" ", "_")
                finding_by_vector[vector_key].append(f)

        # Check each chain pattern
        for pattern in self.CHAIN_PATTERNS:
            required = pattern["requires"]
            available_findings = []

            for req_vector in required:
                matches = finding_by_vector.get(req_vector, [])
                if matches:
                    # Take the best finding for each vector
                    best = max(matches, key=lambda f: f.verification_confidence)
                    available_findings.append(best)

            if len(available_findings) == len(required):
                # All components available — build chain
                chain = self._build_chain(pattern, available_findings)
                chains.append(chain)

        # Also discover ad-hoc chains
        adhoc = self._discover_adhoc_chains(finding_by_vector)
        chains.extend(adhoc)

        return chains

    def _build_chain(self, pattern: dict, findings: List[Finding]) -> ExploitChain:
        """Build a chain from a known pattern."""
        chain_id = f"chain_{uuid.uuid4().hex[:8]}"
        steps = []
        for i, f in enumerate(findings):
            steps.append({
                "step": i + 1,
                "finding_id": f.id,
                "action": f.attack_vector,
                "result": f.description[:100],
            })

        chain = ExploitChain(
            id=chain_id,
            name=pattern["name"],
            description=f"Chain combining {len(findings)} findings: "
                       + " → ".join(f.attack_vector for f in findings),
            steps=steps,
            combined_severity=pattern["combined_severity"],
            combined_impact=pattern["impact"],
            individual_findings=[f.id for f in findings],
            confidence=min(f.verification_confidence for f in findings),
        )

        # Link findings to chain
        for f in findings:
            f.chain_ids.append(chain_id)

        return chain

    def _discover_adhoc_chains(self, finding_by_vector: dict) -> List[ExploitChain]:
        """Discover chains not in known patterns using heuristic analysis."""
        chains = []
        findings_list = [f for f in self.session.findings.values()
                        if f.verdict != Verdict.SKIP]

        # Look for pairs that could chain
        for i, f1 in enumerate(findings_list):
            for f2 in findings_list[i+1:]:
                chain_score = self._chain_compatibility(f1, f2)
                if chain_score >= 0.6:
                    chain = self._build_adhoc_chain(f1, f2, chain_score)
                    chains.append(chain)

        return chains

    def _chain_compatibility(self, f1: Finding, f2: Finding) -> float:
        """Score how well two findings could chain together."""
        score = 0.0

        # Same target component
        common_components = set(f1.affected_components) & set(f2.affected_components)
        if common_components:
            score += 0.3

        # Complementary attack vectors
        complementary = {
            ("information_disclosure", "idor"),
            ("xss", "cors_misconfiguration"),
            ("ssrf", "information_disclosure"),
            ("authentication_bypass", "authorization_bypass"),
            ("file_upload", "lfi"),
            ("sqli", "file_upload"),
            ("open_redirect", "authentication_bypass"),
        }
        pair = tuple(sorted([f1.attack_vector.lower().replace(" ", "_"),
                            f2.attack_vector.lower().replace(" ", "_")]))
        if pair in complementary:
            score += 0.4

        # Both have evidence
        if f1.evidence and f2.evidence:
            score += 0.2

        # Combined severity escalation
        sev_order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        max_single = max(sev_order.get(f1.severity.value, 0),
                        sev_order.get(f2.severity.value, 0))
        if max_single <= 2:  # Both low/medium — chain could escalate
            score += 0.2

        return min(1.0, score)

    def _build_adhoc_chain(self, f1: Finding, f2: Finding, score: float) -> ExploitChain:
        """Build an ad-hoc chain from two compatible findings."""
        chain_id = f"chain_{uuid.uuid4().hex[:8]}"

        # Escalate severity
        sev_order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        sev_names = {0: "info", 1: "low", 2: "medium", 3: "high", 4: "critical"}
        combined_level = min(4, max(sev_order.get(f1.severity.value, 0),
                                    sev_order.get(f2.severity.value, 0)) + 1)
        combined_severity = Severity(sev_names[combined_level])

        chain = ExploitChain(
            id=chain_id,
            name=f"Chain: {f1.attack_vector} → {f2.attack_vector}",
            description=f"Combining {f1.attack_vector} and {f2.attack_vector} "
                       f"on shared components: {', '.join(set(f1.affected_components) & set(f2.affected_components)) or 'same target'}",
            steps=[
                {"step": 1, "finding_id": f1.id, "action": f1.attack_vector,
                 "result": f1.description[:100]},
                {"step": 2, "finding_id": f2.id, "action": f2.attack_vector,
                 "result": f2.description[:100]},
            ],
            combined_severity=combined_severity,
            combined_impact=f"Combined exploit: {f1.impact or f1.description[:50]} + {f2.impact or f2.description[:50]}",
            individual_findings=[f1.id, f2.id],
            confidence=score,
        )

        f1.chain_ids.append(chain_id)
        f2.chain_ids.append(chain_id)
        return chain


# ── Grading Engine ────────────────────────────────────────────────────

class GradingEngine:
    """
    5-axis grading rubric for security findings.

    Axes:
    1. Impact (0-10): How bad is exploitation?
    2. Confidence (0-10): How sure are we it's real?
    3. Exploitability (0-10): How easy to exploit?
    4. Novelty (0-10): How unique/interesting?
    5. Report Quality (0-10): How well documented?

    Verdict:
    - SUBMIT: score ≥ 7.0 AND confidence ≥ 7.0
    - HOLD: score ≥ 4.0 AND confidence ≥ 5.0
    - SKIP: everything else
    """

    def __init__(self, session: CyberSession):
        self.session = session

    def grade_finding(self, finding: Finding) -> GradeResult:
        """Grade a verified finding on 5 axes."""
        # Impact scoring
        impact_scores = {
            Severity.CRITICAL: 9.0,
            Severity.HIGH: 7.5,
            Severity.MEDIUM: 5.0,
            Severity.LOW: 2.5,
            Severity.INFO: 1.0,
        }
        impact = impact_scores.get(finding.severity, 5.0)

        # Adjust impact for evidence quality
        if finding.impact:
            impact_keywords = {
                "rce": 2.0, "remote code": 2.0, "data breach": 1.5,
                "account takeover": 1.5, "full access": 1.5,
                "information disclosure": -1.0, "denial of service": -0.5,
            }
            for keyword, adjustment in impact_keywords.items():
                if keyword in finding.impact.lower():
                    impact = max(0, min(10, impact + adjustment))

        # Confidence scoring
        confidence = finding.verification_confidence * 10
        if finding.is_verified:
            confidence = min(10, confidence + 1.0)

        # Exploitability scoring
        exploitability = 5.0
        if finding.poc_steps:
            exploitability += 2.0  # Has PoC
        if len(finding.poc_steps) <= 3:
            exploitability += 1.0  # Simple PoC
        if any(w in finding.description.lower() for w in ["unauthenticated", "no auth", "public"]):
            exploitability += 1.5  # No auth required

        # Novelty scoring
        novelty = 5.0
        common_vulns = {"xss", "sqli", "csrf", "info_disclosure"}
        if finding.attack_vector.lower().replace(" ", "_") not in common_vulns:
            novelty += 2.0  # Less common vector
        if finding.chain_ids:
            novelty += 1.0  # Part of a chain
        if len(finding.affected_components) > 2:
            novelty += 0.5  # Wide impact

        # Report quality scoring
        report_quality = 5.0
        if finding.poc_steps:
            report_quality += 2.0
        if finding.impact and len(finding.impact) > 50:
            report_quality += 1.0
        if finding.affected_components:
            report_quality += 0.5
        if len(finding.evidence) >= 3:
            report_quality += 1.0

        # Clamp all scores
        impact = max(0, min(10, impact))
        confidence = max(0, min(10, confidence))
        exploitability = max(0, min(10, exploitability))
        novelty = max(0, min(10, novelty))
        report_quality = max(0, min(10, report_quality))

        grade = GradeResult(
            finding_id=finding.id,
            impact_score=round(impact, 1),
            confidence_score=round(confidence, 1),
            exploitability_score=round(exploitability, 1),
            novelty_score=round(novelty, 1),
            report_quality_score=round(report_quality, 1),
        )
        grade.verdict = grade.auto_verdict()
        grade.reasoning = (
            f"Impact={impact:.1f}, Confidence={confidence:.1f}, "
            f"Exploitability={exploitability:.1f}, Novelty={novelty:.1f}, "
            f"Report={report_quality:.1f} → Total={grade.total_score:.1f} → {grade.verdict.value.upper()}"
        )

        return grade


# ── Hypothesis Engine ─────────────────────────────────────────────────

class HypothesisEngine:
    """
    Generates and tracks vulnerability hypotheses for a target.
    Uses attack surface analysis to formulate targeted hypotheses.
    """

    # Common vulnerability patterns by technology
    TECH_VULN_MAP = {
        "apache": ["path_traversal", "ssi_injection", "cve_specific"],
        "nginx": ["off_by_slash", "alias_traversal", "merge_slashes"],
        "php": ["lfi", "rfi", "deserialization", "type_juggling"],
        "node": ["prototype_pollution", "ssrf", "command_injection"],
        "python": ["deserialization", "ssti", "import_injection"],
        "java": ["deserialization", "rce", "xxe"],
        "spring": ["spel_injection", "authentication_bypass"],
        "django": ["sqli", "ssrf", "deserialization"],
        "rails": ["ssti", "deserialization", "ssrf"],
        "wordpress": ["plugin_vulns", "xmlrpc", "rest_api_exposure"],
        "react": ["xss", "prototype_pollution"],
        "angular": ["template_injection", "xss"],
        "aws": ["ssrf_metadata", "s3_misconfig", "lambda_injection"],
        "gcp": ["ssrf_metadata", "bucket_misconfig"],
        "docker": ["escape", "api_exposure"],
        "kubernetes": ["api_exposure", "rbac_bypass", "ssrf"],
        "graphql": ["introspection", "injection", "dos"],
        "rest_api": ["idor", "mass_assignment", "broken_auth"],
    }

    def generate_hypotheses(self, session: CyberSession) -> List[Hypothesis]:
        """Generate targeted hypotheses based on attack surface."""
        hypotheses = []
        techs = [t.lower() for t in session.attack_surface.get("technologies", [])]
        endpoints = session.attack_surface.get("endpoints", [])
        ports = session.attack_surface.get("open_ports", [])

        # Technology-specific hypotheses
        for tech in techs:
            for tech_key, vulns in self.TECH_VULN_MAP.items():
                if tech_key in tech:
                    for vuln in vulns:
                        h = Hypothesis(
                            id=f"hyp_{uuid.uuid4().hex[:8]}",
                            description=f"Target uses {tech} — may be vulnerable to {vuln}",
                            attack_vector=vuln,
                            target_surface=tech,
                            confidence=0.4,
                        )
                        hypotheses.append(h)

        # Endpoint-specific hypotheses
        for ep in endpoints:
            ep_lower = ep.lower() if isinstance(ep, str) else ""
            if any(k in ep_lower for k in ["api", "v1", "v2", "graphql"]):
                hypotheses.append(Hypothesis(
                    id=f"hyp_{uuid.uuid4().hex[:8]}",
                    description=f"API endpoint found: {ep} — test for IDOR, auth bypass, injection",
                    attack_vector="idor",
                    target_surface=ep,
                    confidence=0.5,
                ))
            if any(k in ep_lower for k in ["login", "auth", "oauth", "sso"]):
                hypotheses.append(Hypothesis(
                    id=f"hyp_{uuid.uuid4().hex[:8]}",
                    description=f"Auth endpoint found: {ep} — test for bypass, brute force, token issues",
                    attack_vector="authentication_bypass",
                    target_surface=ep,
                    confidence=0.5,
                ))
            if any(k in ep_lower for k in ["upload", "file", "import"]):
                hypotheses.append(Hypothesis(
                    id=f"hyp_{uuid.uuid4().hex[:8]}",
                    description=f"File endpoint found: {ep} — test for unrestricted upload, path traversal",
                    attack_vector="file_upload",
                    target_surface=ep,
                    confidence=0.4,
                ))

        # Port-based hypotheses
        port_service_map = {
            22: ("SSH", "ssh_bruteforce", 0.3),
            21: ("FTP", "ftp_anonymous", 0.4),
            3306: ("MySQL", "mysql_exposure", 0.5),
            5432: ("PostgreSQL", "postgres_exposure", 0.5),
            6379: ("Redis", "redis_exposure", 0.6),
            27017: ("MongoDB", "mongodb_exposure", 0.6),
            9200: ("Elasticsearch", "es_exposure", 0.5),
            8080: ("Alt HTTP", "web_service", 0.3),
            8443: ("Alt HTTPS", "web_service", 0.3),
        }
        for port in ports:
            port_num = int(port) if isinstance(port, (int, str)) and str(port).isdigit() else 0
            if port_num in port_service_map:
                service, vector, conf = port_service_map[port_num]
                hypotheses.append(Hypothesis(
                    id=f"hyp_{uuid.uuid4().hex[:8]}",
                    description=f"Port {port_num} ({service}) exposed — test for misconfigurations",
                    attack_vector=vector,
                    target_surface=f"port:{port_num}",
                    confidence=conf,
                ))

        # Generic hypotheses (always test)
        generic = [
            ("Test for CORS misconfiguration", "cors_misconfiguration", 0.4),
            ("Test for open redirects", "open_redirect", 0.3),
            ("Test for information disclosure via headers/errors", "information_disclosure", 0.5),
            ("Test for missing security headers", "security_headers", 0.6),
            ("Test for clickjacking", "clickjacking", 0.3),
        ]
        for desc, vector, conf in generic:
            hypotheses.append(Hypothesis(
                id=f"hyp_{uuid.uuid4().hex[:8]}",
                description=desc,
                attack_vector=vector,
                target_surface="all",
                confidence=conf,
            ))

        return hypotheses


# ── Report Generator ──────────────────────────────────────────────────

class ReportGenerator:
    """Generates submission-ready security reports."""

    def generate_report(self, session: CyberSession) -> str:
        """Generate a complete security assessment report."""
        submit_findings = [f for f in session.findings.values()
                          if f.verdict == Verdict.SUBMIT]
        hold_findings = [f for f in session.findings.values()
                        if f.verdict == Verdict.HOLD]

        lines = [
            f"# Security Assessment Report",
            f"",
            f"**Target:** {session.target}",
            f"**Date:** {session.created_at[:10]}",
            f"**Session:** {session.session_id}",
            f"",
            f"## Executive Summary",
            f"",
            f"Assessed {session.target} and identified "
            f"{len(submit_findings)} confirmed vulnerabilities "
            f"and {len(hold_findings)} findings requiring further investigation.",
            f"",
        ]

        # Severity breakdown
        counts = session.finding_count
        lines.append("### Severity Breakdown")
        lines.append("")
        for sev in ["critical", "high", "medium", "low"]:
            if counts.get(sev):
                emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}[sev]
                lines.append(f"- {emoji} **{sev.upper()}:** {counts[sev]}")
        lines.append("")

        # Chains
        if session.chains:
            lines.append("## Exploit Chains")
            lines.append("")
            for chain in session.chains.values():
                lines.append(f"### {chain.name}")
                lines.append(f"**Severity:** {chain.combined_severity.value.upper()}")
                lines.append(f"**Impact:** {chain.combined_impact}")
                lines.append(f"**Steps:**")
                for step in chain.steps:
                    lines.append(f"  {step['step']}. {step['action']} → {step['result']}")
                lines.append("")

        # Confirmed findings
        if submit_findings:
            lines.append("## Confirmed Vulnerabilities")
            lines.append("")
            for i, f in enumerate(sorted(submit_findings,
                                         key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x.severity.value, 4)), 1):
                grade = session.grades.get(f.id)
                lines.append(f"### {i}. {f.title}")
                lines.append(f"**Severity:** {f.severity.value.upper()}")
                if grade:
                    lines.append(f"**Score:** {grade.total_score:.1f}/10")
                lines.append(f"**Vector:** {f.attack_vector}")
                lines.append(f"**Target:** {f.target}")
                lines.append("")
                lines.append(f"**Description:**")
                lines.append(f"{f.description}")
                lines.append("")
                if f.impact:
                    lines.append(f"**Impact:**")
                    lines.append(f"{f.impact}")
                    lines.append("")
                if f.poc_steps:
                    lines.append(f"**Steps to Reproduce:**")
                    for j, step in enumerate(f.poc_steps, 1):
                        lines.append(f"{j}. `{step}`")
                    lines.append("")
                if f.evidence:
                    lines.append(f"**Evidence:**")
                    for ev in f.evidence[:5]:
                        lines.append(f"- {ev[:200]}")
                    lines.append("")
                if f.chain_ids:
                    lines.append(f"**Part of chain:** {', '.join(f.chain_ids)}")
                    lines.append("")
                lines.append("---")
                lines.append("")

        # Hold findings
        if hold_findings:
            lines.append("## Findings Requiring Further Investigation")
            lines.append("")
            for f in hold_findings:
                lines.append(f"- **{f.title}** ({f.severity.value}) — {f.description[:100]}")
            lines.append("")

        # Decision journal
        if session.decisions:
            lines.append("## Reasoning Journal")
            lines.append("")
            for d in session.decisions[-10:]:
                lines.append(f"- [{d.phase}] {d.decision} (confidence: {d.confidence:.0%})")
                lines.append(f"  Reasoning: {d.reasoning[:150]}")
            lines.append("")

        return "\n".join(lines)


# ── Main Orchestrator ─────────────────────────────────────────────────

class CyberReasoningEngine:
    """
    Main orchestrator for cognitive cybersecurity assessment.

    Coordinates the full pipeline:
    1. Recon → Build attack surface
    2. Hunt → Generate hypotheses, test them
    3. Chain → Discover exploit chains
    4. Verify → 3-round adversarial verification
    5. Grade → 5-axis scoring
    6. Report → Generate submission-ready report
    """

    def __init__(self):
        self._sessions: Dict[str, CyberSession] = {}
        self._hypothesis_engine = HypothesisEngine()
        self._chain_builder = None
        self._verifier = None
        self._grader = None
        self._reporter = ReportGenerator()

    def start_session(self, target: str) -> CyberSession:
        """Start a new security assessment session."""
        session = CyberSession(target)
        self._sessions[session.session_id] = session
        session.save()
        return session

    def get_session(self, session_id: str) -> Optional[CyberSession]:
        return self._sessions.get(session_id)

    def get_active_session(self, target: str = None) -> Optional[CyberSession]:
        """Get the most recent active session, optionally filtered by target."""
        candidates = [s for s in self._sessions.values() if not s.is_complete]
        if target:
            candidates = [s for s in candidates if s.target == target]
        return max(candidates, key=lambda s: s.updated_at) if candidates else None

    # ── Phase: Recon ──────────────────────────────────────────────────

    def process_recon_results(self, session_id: str, recon_data: dict) -> str:
        """Process recon tool outputs and build attack surface.
        Also ingests findings from the Mythos pipeline if available."""
        session = self._sessions.get(session_id)
        if not session:
            return "Session not found."

        # Merge recon data into attack surface
        for key in ["subdomains", "live_hosts", "open_ports", "technologies",
                     "endpoints", "secrets_found", "nuclei_results"]:
            if key in recon_data:
                existing = session.attack_surface.get(key, [])
                new_items = recon_data[key]
                if isinstance(new_items, list):
                    session.attack_surface[key] = list(set(existing + new_items))
                else:
                    session.attack_surface[key] = new_items

        # Ingest findings from Mythos pipeline (code analysis)
        mythos_ingested = 0
        try:
            from brain.findings_bus import get_findings_bus
            bus = get_findings_bus()
            mythos_findings = bus.read()
            for mf in mythos_findings:
                if mf.get("vuln_class") in ("Reconnaissance", "Triage Summary"):
                    continue  # Skip meta-findings
                finding = Finding(
                    id=mf.get("finding_id", f"mythos_{uuid.uuid4().hex[:8]}"),
                    title=mf.get("summary", "Mythos finding"),
                    description=mf.get("detail", mf.get("summary", "")),
                    severity=self._mythos_severity(mf.get("cvss_score", 5.0)),
                    target=mf.get("file_path", session.target),
                    attack_vector=mf.get("vuln_class", "unknown").lower().replace(" ", "_"),
                    evidence=[mf.get("detail", "")],
                    poc_steps=[],
                    impact=f"CVSS estimate: {mf.get('cvss_score', 'N/A')}",
                    affected_components=[mf.get("file_path", "")],
                )
                session.findings[finding.id] = finding
                mythos_ingested += 1
        except Exception as e:
            pass  # Mythos not available — continue without it

        # Generate hypotheses
        hypotheses = self._hypothesis_engine.generate_hypotheses(session)
        for h in hypotheses:
            session.hypotheses[h.id] = h

        session.record_decision(
            phase="recon",
            decision=f"Processed recon data, generated {len(hypotheses)} hypotheses, "
                    f"ingested {mythos_ingested} Mythos findings",
            reasoning=f"Attack surface: {len(session.attack_surface.get('subdomains', []))} subdomains, "
                     f"{len(session.attack_surface.get('open_ports', []))} ports, "
                     f"{len(session.attack_surface.get('endpoints', []))} endpoints, "
                     f"{mythos_ingested} Mythos code analysis findings",
            alternatives=["Skip recon, go straight to hunting"],
            confidence=0.8,
        )

        session.transition_phase(Phase.HUNT, "Recon complete, attack surface mapped")
        session.save()

        return (
            f"Recon processed. Attack surface:\n"
            f"  Subdomains: {len(session.attack_surface.get('subdomains', []))}\n"
            f"  Live hosts: {len(session.attack_surface.get('live_hosts', []))}\n"
            f"  Open ports: {len(session.attack_surface.get('open_ports', []))}\n"
            f"  Endpoints: {len(session.attack_surface.get('endpoints', []))}\n"
            f"  Technologies: {len(session.attack_surface.get('technologies', []))}\n"
            f"  Mythos findings ingested: {mythos_ingested}\n"
            f"  Hypotheses generated: {len(hypotheses)}\n"
            f"\nReady for hunting phase."
        )

    @staticmethod
    def _mythos_severity(cvss: float) -> Severity:
        """Convert Mythos CVSS score to Severity enum."""
        if cvss >= 9.0:
            return Severity.CRITICAL
        elif cvss >= 7.0:
            return Severity.HIGH
        elif cvss >= 4.0:
            return Severity.MEDIUM
        elif cvss >= 1.0:
            return Severity.LOW
        return Severity.INFO

    # ── Phase: Hunt ───────────────────────────────────────────────────

    def record_finding(self, session_id: str, finding_data: dict) -> str:
        """Record a new security finding from hunting."""
        session = self._sessions.get(session_id)
        if not session:
            return "Session not found."

        finding = Finding(
            id=f"find_{uuid.uuid4().hex[:8]}",
            title=finding_data.get("title", "Untitled Finding"),
            description=finding_data.get("description", ""),
            severity=Severity(finding_data.get("severity", "medium")),
            target=finding_data.get("target", session.target),
            attack_vector=finding_data.get("attack_vector", "unknown"),
            evidence=finding_data.get("evidence", []),
            poc_steps=finding_data.get("poc_steps", []),
            impact=finding_data.get("impact", ""),
            affected_components=finding_data.get("affected_components", []),
        )

        session.findings[finding.id] = finding

        # Update related hypothesis
        for h in session.hypotheses.values():
            if h.attack_vector == finding.attack_vector and h.status == "pending":
                h.status = "confirmed"
                h.evidence.append(f"Finding recorded: {finding.title}")
                break

        session.save()
        return f"Finding recorded: {finding.id} ({finding.severity.value}) — {finding.title}"

    # ── Phase: Chain ──────────────────────────────────────────────────

    def build_chains(self, session_id: str) -> str:
        """Discover and build exploit chains from findings."""
        session = self._sessions.get(session_id)
        if not session:
            return "Session not found."

        self._chain_builder = ChainBuilder(session)
        chains = self._chain_builder.discover_chains()

        for chain in chains:
            session.chains[chain.id] = chain

        session.record_decision(
            phase="chain",
            decision=f"Built {len(chains)} exploit chains",
            reasoning=f"Analyzed {len(session.findings)} findings for chain potential",
            alternatives=["Skip chaining, verify findings individually"],
            confidence=0.7,
        )

        if chains:
            session.transition_phase(Phase.VERIFY, f"Chains built, ready for verification")
        else:
            session.transition_phase(Phase.VERIFY, "No chains found, proceed to verification")

        session.save()

        chain_summary = "\n".join(
            f"  - {c.name} ({c.combined_severity.value}) — {c.combined_impact[:80]}"
            for c in chains
        ) or "  None found"

        return f"Chain analysis complete. {len(chains)} chains discovered:\n{chain_summary}"

    # ── Phase: Verify ─────────────────────────────────────────────────

    def verify_findings(self, session_id: str, run_test_fn=None) -> str:
        """Run all findings through 3-round adversarial verification."""
        session = self._sessions.get(session_id)
        if not session:
            return "Session not found."

        self._verifier = AdversarialVerifier(session)
        verified = 0
        rejected = 0

        for finding in session.findings.values():
            if finding.verification_rounds:
                continue  # Already verified

            result = self._verifier.verify_finding(finding, run_test_fn)
            if result.is_verified:
                verified += 1
            elif result.verdict == Verdict.SKIP:
                rejected += 1

        session.record_decision(
            phase="verify",
            decision=f"Verified {verified} findings, rejected {rejected}",
            reasoning=f"3-round adversarial verification on {len(session.findings)} findings",
            alternatives=["Skip verification, grade directly"],
            confidence=0.9 if verified > 0 else 0.5,
        )

        session.transition_phase(Phase.GRADE, "Verification complete")
        session.save()

        counts = session.finding_count
        return (
            f"Verification complete:\n"
            f"  Verified: {verified}\n"
            f"  Rejected: {rejected}\n"
            f"  Pending: {counts['total'] - verified - rejected}\n"
            f"  Submit-ready: {counts['submit_ready']}"
        )

    # ── Phase: Grade ──────────────────────────────────────────────────

    def grade_findings(self, session_id: str) -> str:
        """Grade all verified findings on 5 axes."""
        session = self._sessions.get(session_id)
        if not session:
            return "Session not found."

        self._grader = GradingEngine(session)

        for finding in session.findings.values():
            if finding.verdict == Verdict.SKIP:
                continue
            if finding.id in session.grades:
                continue  # Already graded

            grade = self._grader.grade_finding(finding)
            session.grades[finding.id] = grade
            finding.verdict = grade.verdict
            finding.grade = grade.to_dict()

        session.transition_phase(Phase.REPORT, "Grading complete")
        session.save()

        submit_count = sum(1 for g in session.grades.values() if g.verdict == Verdict.SUBMIT)
        hold_count = sum(1 for g in session.grades.values() if g.verdict == Verdict.HOLD)
        skip_count = sum(1 for g in session.grades.values() if g.verdict == Verdict.SKIP)

        return (
            f"Grading complete:\n"
            f"  SUBMIT: {submit_count}\n"
            f"  HOLD: {hold_count}\n"
            f"  SKIP: {skip_count}"
        )

    # ── Phase: Report ─────────────────────────────────────────────────

    def generate_report(self, session_id: str) -> str:
        """Generate a submission-ready security report."""
        session = self._sessions.get(session_id)
        if not session:
            return "Session not found."

        report = self._reporter.generate_report(session)

        # Save report
        session_dir = SESSIONS_DIR / session.target.replace("/", "_").replace(":", "_")
        session_dir.mkdir(parents=True, exist_ok=True)
        report_file = session_dir / "report.md"
        report_file.write_text(report, encoding="utf-8")

        session.transition_phase(Phase.COMPLETE, "Report generated")
        session.save()

        return report

    # ── Full Pipeline ─────────────────────────────────────────────────

    def run_full_pipeline(self, session_id: str, recon_data: dict,
                          run_test_fn=None) -> str:
        """Run the complete assessment pipeline end-to-end."""
        session = self._sessions.get(session_id)
        if not session:
            return "Session not found."

        results = []

        # Phase 1: Recon
        results.append("═══ Phase 1: RECON ═══")
        results.append(self.process_recon_results(session_id, recon_data))
        results.append("")

        # Phase 2: Hunt (hypotheses are already generated)
        results.append("═══ Phase 2: HUNT ═══")
        hyp_count = len(session.hypotheses)
        confirmed = sum(1 for h in session.hypotheses.values() if h.status == "confirmed")
        results.append(f"Hypotheses: {hyp_count} generated, {confirmed} confirmed by findings")
        results.append("")

        # Phase 3: Chain
        results.append("═══ Phase 3: CHAIN ═══")
        results.append(self.build_chains(session_id))
        results.append("")

        # Phase 4: Verify
        results.append("═══ Phase 4: VERIFY ═══")
        results.append(self.verify_findings(session_id, run_test_fn))
        results.append("")

        # Phase 5: Grade
        results.append("═══ Phase 5: GRADE ═══")
        results.append(self.grade_findings(session_id))
        results.append("")

        # Phase 6: Report
        results.append("═══ Phase 6: REPORT ═══")
        report = self.generate_report(session_id)
        results.append(f"Report saved ({len(report)} chars)")
        results.append("")
        results.append(session.format_summary())

        return "\n".join(results)


# ── Singleton ─────────────────────────────────────────────────────────

_cyber_engine = None
_ce_lock = threading.Lock()


def get_cyber_engine() -> CyberReasoningEngine:
    """Get singleton CyberReasoningEngine instance."""
    global _cyber_engine
    if _cyber_engine is None:
        with _ce_lock:
            if _cyber_engine is None:
                _cyber_engine = CyberReasoningEngine()
    return _cyber_engine
