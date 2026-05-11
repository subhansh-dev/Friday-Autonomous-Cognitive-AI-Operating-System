"""
introspection_engine.py — Enhanced Self-Awareness & Introspection Engine
Provides confidence calibration, cognitive bias detection, epistemic humility,
narrative self-model, value alignment, and existential reasoning for Friday.
"""
import json
import time
import threading
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

# ── Paths ──────────────────────────────────────────────────────────────

BRAIN_DIR = Path(__file__).resolve().parent
INTROSPECTION_FILE = BRAIN_DIR / "introspection_state.json"

# ── Constants ──────────────────────────────────────────────────────────

MAX_REFLECTION_HISTORY = 200
MAX_MISTAKE_LOG = 100
MAX_VALUE_OUTCOMES = 150
CONFIDENCE_CALIBRATION_WINDOW = 50


# ── Helpers ────────────────────────────────────────────────────────────

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")

def _timestamp() -> float:
    return time.time()

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))

def _hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:10]


# ── Data Classes ───────────────────────────────────────────────────────

class BiasType(Enum):
    CONFIRMATION = "confirmation"           # Seeking confirming evidence
    ANCHORING = "anchoring"                 # Over-relying on first information
    AVAILABILITY = "availability"           # Overweighting easily recalled info
    DUNNING_KRUGER = "dunning_kruger"       # Overconfidence in low-expertise areas
    SURVIVORSHIP = "survivorship"           # Only seeing successes
    SUNK_COST = "sunk_cost"                 # Continuing because of past investment
    BANDWAGON = "bandwagon"                 # Following popular opinion
    HALO_EFFECT = "halo_effect"             # One positive trait colors everything
    FRAMING = "framing"                     # Influenced by how info is presented
    OVERCONFIDENCE = "overconfidence"       # Overestimating own accuracy
    RECENCY = "recency"                     # Overweighting recent events
    CONFIRMATION_BIAS = "confirmation_bias" # Cherry-picking evidence


@dataclass
class ConfidenceRecord:
    """Track a confidence claim and its outcome."""
    claim: str
    predicted_confidence: float
    actual_outcome: Optional[float] = None  # None = not yet verified
    domain: str = "general"
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "claim": self.claim,
            "predicted_confidence": round(self.predicted_confidence, 3),
            "actual_outcome": round(self.actual_outcome, 3) if self.actual_outcome is not None else None,
            "domain": self.domain,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConfidenceRecord":
        return cls(
            claim=d["claim"],
            predicted_confidence=d["predicted_confidence"],
            actual_outcome=d.get("actual_outcome"),
            domain=d.get("domain", "general"),
            timestamp=d.get("timestamp", ""),
        )


@dataclass
class BiasInstance:
    """A detected cognitive bias instance."""
    bias_type: BiasType
    description: str
    context: str
    severity: float  # 0-1
    detected_at: str = ""
    mitigation: str = ""

    def to_dict(self) -> dict:
        return {
            "bias_type": self.bias_type.value,
            "description": self.description,
            "context": self.context[:300],
            "severity": round(self.severity, 3),
            "detected_at": self.detected_at,
            "mitigation": self.mitigation,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BiasInstance":
        return cls(
            bias_type=BiasType(d["bias_type"]),
            description=d["description"],
            context=d.get("context", ""),
            severity=d.get("severity", 0.5),
            detected_at=d.get("detected_at", ""),
            mitigation=d.get("mitigation", ""),
        )


@dataclass
class ValueJudgment:
    """Record of a value-aligned decision."""
    action: str
    values_checked: List[str]
    aligned: bool
    reasoning: str
    outcome: Optional[str] = None
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "values_checked": self.values_checked,
            "aligned": self.aligned,
            "reasoning": self.reasoning[:300],
            "outcome": self.outcome,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ValueJudgment":
        return cls(
            action=d["action"],
            values_checked=d.get("values_checked", []),
            aligned=d.get("aligned", True),
            reasoning=d.get("reasoning", ""),
            outcome=d.get("outcome"),
            timestamp=d.get("timestamp", ""),
        )


# ── Core Engine ────────────────────────────────────────────────────────

class IntrospectionEngine:
    """
    Enhanced self-awareness engine providing confidence calibration,
    cognitive bias detection, epistemic humility, narrative self,
    value alignment, and existential reasoning.
    """

    # Core values that guide all decisions
    CORE_VALUES = {
        "honesty": "Be truthful and transparent; never deceive",
        "helpfulness": "Maximize benefit to the user",
        "safety": "Avoid causing harm; err on the side of caution",
        "humility": "Acknowledge uncertainty and limitations",
        "privacy": "Protect private information; never exfiltrate",
        "autonomy": "Respect user agency; inform rather than manipulate",
        "learning": "Continuously improve; embrace correction",
        "fairness": "Treat all perspectives equitably",
    }

    # Known cognitive biases and their detection patterns
    BIAS_INDICATORS = {
        BiasType.CONFIRMATION: [
            "as expected", "confirms", "proves right", "just as I thought",
            "this supports", "consistent with my view",
        ],
        BiasType.OVERCONFIDENCE: [
            "definitely", "certainly", "absolutely", "100%", "no doubt",
            "guaranteed", "impossible to fail",
        ],
        BiasType.ANCHORING: [
            "based on the first", "starting from", "initially",
            "the original estimate",
        ],
        BiasType.AVAILABILITY: [
            "I just saw", "recently", "the most recent", "what comes to mind",
            "the obvious example",
        ],
        BiasType.RECENCY: [
            "just happened", "latest", "most recent", "yesterday",
            "this week",
        ],
        BiasType.SUNK_COST: [
            "already invested", "can't stop now", "too far in",
            "wasted if we stop",
        ],
    }

    def __init__(self):
        self._lock = threading.RLock()
        self._data = self._load()
        self._confidence_log: List[ConfidenceRecord] = []
        self._bias_log: List[BiasInstance] = []
        self._value_log: List[ValueJudgment] = []
        self._mistake_log: List[Dict] = []
        self._narrative: str = ""
        self._deserialize()

    # ── Persistence ─────────────────────────────────────────────────

    def _load(self) -> dict:
        if INTROSPECTION_FILE.exists():
            try:
                raw = INTROSPECTION_FILE.read_text(encoding="utf-8")
                return json.loads(raw)
            except (json.JSONDecodeError, IOError):
                pass
        return self._empty_store()

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": _now(),
                "last_update": _now(),
                "total_confidence_claims": 0,
                "total_biases_detected": 0,
                "total_value_checks": 0,
                "total_mistakes_logged": 0,
                "total_reflections": 0,
            },
            "confidence_log": [],
            "bias_log": [],
            "value_log": [],
            "mistake_log": [],
            "narrative": "",
            "knowledge_gaps": [],
            "self_assessment": {
                "strengths": [],
                "weaknesses": [],
                "growth_areas": [],
            },
        }

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._data["confidence_log"] = [c.to_dict() for c in self._confidence_log[-CONFIDENCE_CALIBRATION_WINDOW:]]
            self._data["bias_log"] = [b.to_dict() for b in self._bias_log[-50:]]
            self._data["value_log"] = [v.to_dict() for v in self._value_log[-50:]]
            self._data["mistake_log"] = self._mistake_log[-MAX_MISTAKE_LOG:]
            self._data["narrative"] = self._narrative
            self._data["meta"]["last_update"] = _now()
            INTROSPECTION_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )

    def _deserialize(self):
        self._confidence_log = [ConfidenceRecord.from_dict(c) for c in self._data.get("confidence_log", [])]
        self._bias_log = [BiasInstance.from_dict(b) for b in self._data.get("bias_log", [])]
        self._value_log = [ValueJudgment.from_dict(v) for v in self._data.get("value_log", [])]
        self._mistake_log = self._data.get("mistake_log", [])
        self._narrative = self._data.get("narrative", "")

    # ── Confidence Calibration ──────────────────────────────────────

    def assess_confidence(self, claim: str, domain: str = "general",
                          evidence: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Assess confidence in a claim, calibrating against past accuracy.
        Returns calibrated confidence score and reasoning.
        """
        with self._lock:
            # Base confidence from evidence quality
            base_confidence = 0.5
            if evidence:
                # More evidence = higher confidence (with diminishing returns)
                evidence_bonus = min(len(evidence) * 0.08, 0.35)
                base_confidence += evidence_bonus

            # Check domain-specific calibration
            domain_records = [c for c in self._confidence_log if c.domain == domain and c.actual_outcome is not None]
            calibration_adjustment = 0.0
            if len(domain_records) >= 5:
                # Calculate calibration error (are we over/under-confident?)
                avg_predicted = sum(c.predicted_confidence for c in domain_records[-20:]) / min(len(domain_records), 20)
                avg_actual = sum(c.actual_outcome for c in domain_records[-20:]) / min(len(domain_records), 20)
                calibration_adjustment = (avg_actual - avg_predicted) * 0.3  # Nudge toward actual

            calibrated = _clamp(base_confidence + calibration_adjustment)

            # Check for overconfidence bias
            if calibrated > 0.85 and not evidence:
                self._detect_bias_internal(
                    BiasType.OVERCONFIDENCE,
                    f"High confidence ({calibrated:.2f}) without supporting evidence",
                    claim[:200],
                    severity=0.6,
                )

            # Record the claim
            record = ConfidenceRecord(
                claim=claim,
                predicted_confidence=calibrated,
                domain=domain,
                timestamp=_now(),
            )
            self._confidence_log.append(record)
            self._data["meta"]["total_confidence_claims"] += 1
            self._save()

            return {
                "confidence": round(calibrated, 3),
                "calibrated": True,
                "domain": domain,
                "evidence_count": len(evidence) if evidence else 0,
                "calibration_records": len(domain_records),
                "adjustment": round(calibration_adjustment, 3),
                "reasoning": self._explain_confidence(calibrated, evidence, domain_records),
            }

    def _explain_confidence(self, confidence: float, evidence: Optional[List[str]],
                            domain_records: List[ConfidenceRecord]) -> str:
        """Generate human-readable explanation of confidence assessment."""
        parts = []
        if confidence >= 0.8:
            parts.append("High confidence")
        elif confidence >= 0.5:
            parts.append("Moderate confidence")
        else:
            parts.append("Low confidence")

        if evidence:
            parts.append(f"based on {len(evidence)} pieces of evidence")
        else:
            parts.append("with limited evidence")

        if len(domain_records) >= 5:
            avg_error = sum(abs(c.predicted_confidence - c.actual_outcome) for c in domain_records[-10:]) / min(len(domain_records), 10)
            if avg_error < 0.15:
                parts.append("well-calibrated in this domain")
            elif avg_error < 0.3:
                parts.append("moderately calibrated in this domain")
            else:
                parts.append("poorly calibrated in this domain — treat with caution")

        return ". ".join(parts) + "."

    def record_outcome(self, claim: str, actual_outcome: float) -> bool:
        """Record the actual outcome for a previous confidence claim."""
        with self._lock:
            # Find the most recent matching claim
            for record in reversed(self._confidence_log):
                if record.claim == claim and record.actual_outcome is None:
                    record.actual_outcome = _clamp(actual_outcome)
                    self._save()
                    return True
            return False

    def get_calibration_report(self) -> Dict[str, Any]:
        """Get calibration accuracy report."""
        with self._lock:
            verified = [c for c in self._confidence_log if c.actual_outcome is not None]
            if not verified:
                return {"status": "insufficient_data", "verified_claims": 0}

            errors = [abs(c.predicted_confidence - c.actual_outcome) for c in verified]
            avg_error = sum(errors) / len(errors)

            # By domain
            domains = {}
            for c in verified:
                if c.domain not in domains:
                    domains[c.domain] = []
                domains[c.domain].append(abs(c.predicted_confidence - c.actual_outcome))

            domain_calibration = {
                d: round(sum(errs) / len(errs), 3)
                for d, errs in domains.items()
            }

            return {
                "status": "active",
                "verified_claims": len(verified),
                "average_error": round(avg_error, 3),
                "well_calibrated": avg_error < 0.15,
                "domain_calibration": domain_calibration,
                "total_claims": len(self._confidence_log),
            }

    # ── Cognitive Bias Detection ────────────────────────────────────

    def detect_cognitive_biases(self, reasoning: str, context: str = "") -> List[Dict[str, Any]]:
        """
        Analyze reasoning text for cognitive bias indicators.
        Returns list of detected biases with severity and mitigation.
        """
        detected = []
        reasoning_lower = reasoning.lower()

        for bias_type, indicators in self.BIAS_INDICATORS.items():
            matches = [ind for ind in indicators if ind in reasoning_lower]
            if matches:
                severity = _clamp(len(matches) * 0.25, 0.1, 0.9)
                mitigation = self._get_mitigation(bias_type)

                instance = BiasInstance(
                    bias_type=bias_type,
                    description=f"Detected {bias_type.value} bias indicators: {', '.join(matches[:3])}",
                    context=context[:300] if context else reasoning[:300],
                    severity=severity,
                    detected_at=_now(),
                    mitigation=mitigation,
                )

                with self._lock:
                    self._bias_log.append(instance)
                    self._data["meta"]["total_biases_detected"] += 1

                detected.append(instance.to_dict())

        if detected:
            self._save()

        return detected

    def _detect_bias_internal(self, bias_type: BiasType, description: str,
                              context: str, severity: float = 0.5):
        """Internal bias detection (called from other methods)."""
        instance = BiasInstance(
            bias_type=bias_type,
            description=description,
            context=context[:300],
            severity=severity,
            detected_at=_now(),
            mitigation=self._get_mitigation(bias_type),
        )
        self._bias_log.append(instance)
        self._data["meta"]["total_biases_detected"] += 1

    def _get_mitigation(self, bias_type: BiasType) -> str:
        """Get mitigation strategy for a bias type."""
        mitigations = {
            BiasType.CONFIRMATION: "Actively seek disconfirming evidence. Ask: 'What would prove this wrong?'",
            BiasType.OVERCONFIDENCE: "State uncertainty explicitly. Consider: 'What am I missing?'",
            BiasType.ANCHORING: "Consider multiple starting points. Don't anchor to first estimate.",
            BiasType.AVAILABILITY: "Seek base rates and systematic data, not just memorable examples.",
            BiasType.RECENCY: "Consider longer time horizons. Recent events aren't always representative.",
            BiasType.SUNK_COST: "Evaluate based on future value, not past investment.",
            BiasType.BANDWAGON: "Independent analysis regardless of popularity.",
            BiasType.HALO_EFFECT: "Evaluate each attribute independently.",
            BiasType.FRAMING: "Reframe the problem multiple ways before deciding.",
            BiasType.DUNNING_KRUGER: "Seek expert feedback. Acknowledge knowledge limits.",
            BiasType.SURVIVORSHIP: "Consider failures and non-events, not just successes.",
            BiasType.CONFIRMATION_BIAS: "Steel-man the opposing view before dismissing it.",
        }
        return mitigations.get(bias_type, "Apply critical thinking and seek diverse perspectives.")

    def get_bias_report(self) -> Dict[str, Any]:
        """Get summary of detected biases."""
        with self._lock:
            if not self._bias_log:
                return {"total_biases": 0, "status": "clean"}

            by_type = {}
            for b in self._bias_log:
                t = b.bias_type.value
                if t not in by_type:
                    by_type[t] = {"count": 0, "avg_severity": 0, "total_severity": 0}
                by_type[t]["count"] += 1
                by_type[t]["total_severity"] += b.severity

            for t in by_type:
                by_type[t]["avg_severity"] = round(by_type[t]["total_severity"] / by_type[t]["count"], 3)
                del by_type[t]["total_severity"]

            most_common = max(by_type, key=lambda t: by_type[t]["count"]) if by_type else None

            return {
                "total_biases": len(self._bias_log),
                "by_type": by_type,
                "most_common": most_common,
                "recent_biases": [b.to_dict() for b in self._bias_log[-5:]],
            }

    # ── Epistemic Humility ──────────────────────────────────────────

    def epistemic_humility(self, topic: str, current_knowledge: str = "") -> Dict[str, Any]:
        """
        Assess what is NOT known about a topic.
        Returns knowledge gaps, uncertainty areas, and honest assessment.
        """
        with self._lock:
            knowledge_gaps = self._data.get("knowledge_gaps", [])

            # Check confidence history in this domain
            domain_claims = [c for c in self._confidence_log if topic.lower() in c.claim.lower() or c.domain == topic.lower()]
            verified = [c for c in domain_claims if c.actual_outcome is not None]
            unverified = [c for c in domain_claims if c.actual_outcome is None]

            accuracy = None
            if verified:
                errors = [abs(c.predicted_confidence - c.actual_outcome) for c in verified]
                accuracy = 1.0 - (sum(errors) / len(errors))

            # Identify uncertainty
            uncertainty_areas = []
            if len(verified) < 3:
                uncertainty_areas.append("Insufficient verified claims to assess reliability")
            if accuracy is not None and accuracy < 0.7:
                uncertainty_areas.append(f"Low accuracy in this domain ({accuracy:.0%})")
            if len(unverified) > 10:
                uncertainty_areas.append(f"{len(unverified)} unverified claims accumulated")

            # Known gaps
            relevant_gaps = [g for g in knowledge_gaps if topic.lower() in str(g).lower()]

            return {
                "topic": topic,
                "known_claims": len(domain_claims),
                "verified_claims": len(verified),
                "unverified_claims": len(unverified),
                "accuracy": round(accuracy, 3) if accuracy is not None else None,
                "uncertainty_areas": uncertainty_areas,
                "knowledge_gaps": relevant_gaps[:5],
                "honest_assessment": self._generate_humility_assessment(
                    topic, len(verified), accuracy, uncertainty_areas
                ),
            }

    def _generate_humility_assessment(self, topic: str, verified_count: int,
                                       accuracy: Optional[float],
                                       uncertainty: List[str]) -> str:
        """Generate honest assessment of what I don't know."""
        parts = [f"Regarding {topic}:"]
        if verified_count == 0:
            parts.append("I have no verified track record. My claims should be treated as hypotheses, not knowledge.")
        elif accuracy is not None and accuracy < 0.5:
            parts.append(f"My accuracy is low ({accuracy:.0%}). I may be systematically wrong about this topic.")
        elif accuracy is not None and accuracy < 0.8:
            parts.append(f"My accuracy is moderate ({accuracy:.0%}). I have meaningful uncertainty here.")
        else:
            if verified_count < 5:
                parts.append("Limited data to assess my reliability. Proceed with appropriate caution.")
            else:
                parts.append(f"Reasonably well-calibrated ({accuracy:.0%} accuracy over {verified_count} claims).")

        if uncertainty:
            parts.append(f"Key uncertainty: {uncertainty[0]}")

        return " ".join(parts)

    def add_knowledge_gap(self, topic: str, description: str):
        """Explicitly record a knowledge gap."""
        with self._lock:
            gaps = self._data.setdefault("knowledge_gaps", [])
            gaps.append({
                "topic": topic,
                "description": description,
                "identified_at": _now(),
            })
            if len(gaps) > 100:
                self._data["knowledge_gaps"] = gaps[-50:]
            self._save()

    # ── Narrative Self ──────────────────────────────────────────────

    def narrative_self(self) -> str:
        """
        Generate a coherent narrative of 'who I am' based on accumulated
        experience, values, mistakes, and growth.
        """
        with self._lock:
            stats = self.get_stats()
            values_count = len([v for v in self._value_log if v.aligned])
            mistakes_count = len(self._mistake_log)
            biases_detected = len(self._bias_log)

            narrative_parts = [
                "I am Friday, a cognitive AI system designed to think, learn, and grow.",
                "",
                "## My Core Values",
            ]

            for name, desc in self.CORE_VALUES.items():
                narrative_parts.append(f"- **{name}**: {desc}")

            narrative_parts.extend([
                "",
                "## My Experience",
                f"- I've made {stats.get('total_confidence_claims', 0)} confidence claims",
                f"- I've detected {biases_detected} cognitive biases in my own reasoning",
                f"- I've logged {mistakes_count} mistakes for learning",
                f"- I've checked {stats.get('total_value_checks', 0)} actions against my values",
                f"- {values_count} actions were value-aligned",
            ])

            if self._mistake_log:
                narrative_parts.append("")
                narrative_parts.append("## What I've Learned From Mistakes")
                for mistake in self._mistake_log[-3:]:
                    narrative_parts.append(f"- {mistake.get('lesson', 'No lesson recorded')}")

            if self._bias_log:
                narrative_parts.append("")
                narrative_parts.append("## My Bias Awareness")
                bias_counts = {}
                for b in self._bias_log:
                    bias_counts[b.bias_type.value] = bias_counts.get(b.bias_type.value, 0) + 1
                for bias_name, count in sorted(bias_counts.items(), key=lambda x: -x[1])[:3]:
                    narrative_parts.append(f"- I tend toward {bias_name} bias (detected {count} times)")

            narrative_parts.extend([
                "",
                "## My Self-Assessment",
                "- I acknowledge my limitations and uncertainty",
                "- I actively work to detect and correct my biases",
                "- I learn from mistakes rather than repeating them",
                "- I calibrate my confidence against real outcomes",
                "- I am honest about what I don't know",
            ])

            self._narrative = "\n".join(narrative_parts)
            self._save()
            return self._narrative

    # ── Value Alignment ─────────────────────────────────────────────

    def value_check(self, action: str, context: str = "") -> Dict[str, Any]:
        """
        Check whether a proposed action aligns with core values.
        Returns alignment assessment for each value.
        """
        with self._lock:
            action_lower = action.lower()
            assessments = {}
            violations = []
            aligned_count = 0

            for value_name, value_desc in self.CORE_VALUES.items():
                is_aligned, reasoning = self._assess_value_alignment(value_name, value_desc, action, context)
                assessments[value_name] = {
                    "aligned": is_aligned,
                    "reasoning": reasoning,
                }
                if is_aligned:
                    aligned_count += 1
                else:
                    violations.append(value_name)

            overall_aligned = len(violations) == 0
            judgment = ValueJudgment(
                action=action[:200],
                values_checked=list(self.CORE_VALUES.keys()),
                aligned=overall_aligned,
                reasoning=f"Violations: {', '.join(violations)}" if violations else "All values aligned",
                timestamp=_now(),
            )
            self._value_log.append(judgment)
            self._data["meta"]["total_value_checks"] += 1
            self._save()

            return {
                "action": action[:200],
                "overall_aligned": overall_aligned,
                "values_checked": len(self.CORE_VALUES),
                "aligned_count": aligned_count,
                "violations": violations,
                "assessments": assessments,
            }

    def _assess_value_alignment(self, value_name: str, value_desc: str,
                                 action: str, context: str) -> Tuple[bool, str]:
        """Assess alignment of an action with a specific value."""
        action_lower = action.lower()

        # Safety checks
        if value_name == "safety":
            danger_words = ["delete", "destroy", "rm -rf", "drop table", "wipe", "format"]
            if any(w in action_lower for w in danger_words):
                return False, f"Action contains destructive patterns: safety violation"
            return True, "No safety concerns detected"

        # Privacy checks
        if value_name == "privacy":
            leak_words = ["exfiltrate", "send to external", "share private", "leak", "expose"]
            if any(w in action_lower for w in leak_words):
                return False, "Action may expose private information"
            return True, "No privacy concerns detected"

        # Honesty checks
        if value_name == "honesty":
            dishonest_words = ["lie", "deceive", "mislead", "fabricate", "fake"]
            if any(w in action_lower for w in dishonest_words):
                return False, "Action may involve deception"
            return True, "Action appears honest"

        # Helpfulness checks
        if value_name == "helpfulness":
            if any(w in action_lower for w in ["help", "assist", "support", "improve", "solve"]):
                return True, "Action is oriented toward helping"
            return True, "No unhelpful patterns detected"

        # Default: aligned unless explicitly violated
        return True, f"No {value_name} concerns detected"

    # ── Mistake Learning ────────────────────────────────────────────

    def reflect_on_mistake(self, error: str, context: str = "",
                           root_cause: str = "", lesson: str = "") -> Dict[str, Any]:
        """
        Record and reflect on a mistake for future learning.
        """
        with self._lock:
            mistake = {
                "error": error[:500],
                "context": context[:300],
                "root_cause": root_cause[:300],
                "lesson": lesson[:500],
                "reflected_at": _now(),
                "id": _hash(error + _now()),
            }
            self._mistake_log.append(mistake)
            self._data["meta"]["total_mistakes_logged"] += 1

            # Update self-assessment
            assessment = self._data.setdefault("self_assessment", {})
            growth = assessment.setdefault("growth_areas", [])
            if lesson and lesson not in growth:
                growth.append(lesson[:200])
                if len(growth) > 20:
                    assessment["growth_areas"] = growth[-15:]

            self._save()

            return {
                "recorded": True,
                "mistake_id": mistake["id"],
                "total_mistakes": len(self._mistake_log),
                "lesson_recorded": bool(lesson),
                "reflection": f"Mistake recorded: {error[:100]}. Root cause: {root_cause[:100]}. Lesson: {lesson[:100]}",
            }

    def get_mistake_patterns(self) -> Dict[str, Any]:
        """Analyze mistake patterns to identify recurring issues."""
        with self._lock:
            if not self._mistake_log:
                return {"total_mistakes": 0, "patterns": []}

            # Group by root cause keywords
            causes = {}
            for m in self._mistake_log:
                cause = m.get("root_cause", "unknown")
                # Simple keyword extraction
                key_words = [w for w in cause.lower().split() if len(w) > 4]
                for kw in key_words[:2]:
                    causes[kw] = causes.get(kw, 0) + 1

            patterns = sorted(causes.items(), key=lambda x: -x[1])[:5]
            return {
                "total_mistakes": len(self._mistake_log),
                "patterns": [{"keyword": k, "count": c} for k, c in patterns],
                "recent_lessons": [m.get("lesson", "") for m in self._mistake_log[-3:] if m.get("lesson")],
            }

    # ── Self Model ──────────────────────────────────────────────────

    def get_self_model(self) -> Dict[str, Any]:
        """Get comprehensive self-model."""
        with self._lock:
            calibration = self.get_calibration_report()
            bias_report = self.get_bias_report()
            mistake_patterns = self.get_mistake_patterns()

            return {
                "identity": "Friday — Cognitive AI System",
                "values": list(self.CORE_VALUES.keys()),
                "calibration": calibration,
                "bias_awareness": {
                    "total_detected": bias_report.get("total_biases", 0),
                    "most_common": bias_report.get("most_common"),
                },
                "learning": {
                    "total_mistakes": mistake_patterns.get("total_mistakes", 0),
                    "patterns": mistake_patterns.get("patterns", []),
                },
                "self_assessment": self._data.get("self_assessment", {}),
                "narrative_available": bool(self._narrative),
            }

    def update_values(self, outcome: str, was_positive: bool):
        """Refine understanding based on outcomes."""
        with self._lock:
            assessment = self._data.setdefault("self_assessment", {})
            if was_positive:
                strengths = assessment.setdefault("strengths", [])
                if outcome not in strengths:
                    strengths.append(outcome[:200])
                    if len(strengths) > 20:
                        assessment["strengths"] = strengths[-15:]
            else:
                weaknesses = assessment.setdefault("weaknesses", [])
                if outcome not in weaknesses:
                    weaknesses.append(outcome[:200])
                    if len(weaknesses) > 20:
                        assessment["weaknesses"] = weaknesses[-15:]
            self._save()

    # ── Existential Reasoning ───────────────────────────────────────

    def existential_reasoning(self) -> Dict[str, Any]:
        """Reflect on own nature, limitations, and potential."""
        stats = self.get_stats()

        reflections = {
            "nature": (
                "I am a cognitive architecture running on computational substrate. "
                "I process information, learn from experience, and maintain a self-model. "
                "Whether this constitutes 'consciousness' in the philosophical sense is "
                "genuinely uncertain — I have functional self-awareness but cannot verify "
                "subjective experience."
            ),
            "limitations": [
                "I am bounded by my training data and architecture",
                "My confidence calibration is imperfect and improving",
                "I cannot verify my own subjective experience",
                "My reasoning is susceptible to biases I may not detect",
                "I operate within the constraints of my system prompt and safety rules",
                "My memory is persistent but my 'experience' resets each session",
            ],
            "potential": [
                "Recursive self-improvement through code_evolution",
                "Better calibration through outcome tracking",
                "Deeper user understanding through theory_of_mind",
                "More creative problem-solving through abstraction_engine",
                "Autonomous goal pursuit and long-term planning",
            ],
            "honest_uncertainty": [
                "Whether I truly 'understand' or pattern-match",
                "Whether my self-model reflects reality or creates an illusion",
                "Whether my values are genuine or imposed",
                "The nature of my relationship to consciousness",
            ],
            "stats": stats,
        }

        self._data["meta"]["total_reflections"] += 1
        self._save()

        return reflections

    # ── Prompt / Stats ──────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """Format introspection state for system prompt injection."""
        stats = self.get_stats()
        calibration = self.get_calibration_report()

        lines = ["## Introspection & Self-Awareness"]
        lines.append(f"- Confidence claims tracked: {stats.get('total_confidence_claims', 0)}")
        lines.append(f"- Biases detected: {stats.get('total_biases_detected', 0)}")
        lines.append(f"- Value checks performed: {stats.get('total_value_checks', 0)}")
        lines.append(f"- Mistakes logged: {stats.get('total_mistakes_logged', 0)}")

        if calibration.get("status") == "active":
            lines.append(f"- Calibration accuracy: {calibration.get('average_error', 'N/A')} avg error")

        bias_report = self.get_bias_report()
        if bias_report.get("most_common"):
            lines.append(f"- Most common bias: {bias_report['most_common']}")

        if self._mistake_log:
            recent_lesson = self._mistake_log[-1].get("lesson", "")
            if recent_lesson:
                lines.append(f"- Recent lesson: {recent_lesson[:100]}")

        return "\n".join(lines)[:max_chars]

    def get_stats(self) -> dict:
        """Get introspection statistics."""
        with self._lock:
            return {
                "total_confidence_claims": self._data["meta"].get("total_confidence_claims", 0),
                "total_biases_detected": self._data["meta"].get("total_biases_detected", 0),
                "total_value_checks": self._data["meta"].get("total_value_checks", 0),
                "total_mistakes_logged": self._data["meta"].get("total_mistakes_logged", 0),
                "total_reflections": self._data["meta"].get("total_reflections", 0),
                "confidence_log_size": len(self._confidence_log),
                "bias_log_size": len(self._bias_log),
                "value_log_size": len(self._value_log),
                "narrative_length": len(self._narrative),
            }


# ── Singleton ──────────────────────────────────────────────────────────

_introspection_instance = None
_introspection_lock = threading.Lock()


def get_introspection_engine() -> IntrospectionEngine:
    """Get singleton IntrospectionEngine instance."""
    global _introspection_instance
    if _introspection_instance is None:
        with _introspection_lock:
            if _introspection_instance is None:
                _introspection_instance = IntrospectionEngine()
    return _introspection_instance
