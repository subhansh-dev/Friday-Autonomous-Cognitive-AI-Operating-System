#!/usr/bin/env python3
"""
narrative_intelligence.py — FRIDAY Narrative Intelligence System
================================================================

The ability to understand, generate, and reason with stories.

Humans don't think in data — they think in narratives. FRIDAY's narrative
intelligence transforms raw experiences into coherent stories, enabling:
  - Summarizing events as meaningful narratives
  - Understanding causality through story structure
  - Exploring counterfactuals ("what if I had done X?")
  - Tracking identity evolution over time
  - Maintaining narrative coherence across sessions
  - Remembering and retrieving past narratives by theme

Components:
  - StoryGenerator: Turn experiences into setup→conflict→resolution stories
  - CausalNarrative: Link events into cause-effect narratives
  - CounterfactualNarrative: "What if" and regret/hope analysis
  - IdentityEvolution: Track how FRIDAY's identity changes over time
  - NarrativeCoherence: Ensure self-narrative consistency
  - NarrativeMemory: Store, index, and retrieve narratives by theme

Integration:
  - brain.self_awareness.SelfNarrative — extends identity tracking
  - brain.causal_reasoner — leverages causal graph for causal chains
  - brain.episodic_memory — retrieves events for narrative construction
  - brain.dreaming — interprets dreams as narrative symbols
"""

import json
import threading
import time
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Optional, List, Dict, Any, Tuple


BRAIN_DIR = Path(__file__).parent.resolve()
NARRATIVE_DATA_FILE = BRAIN_DIR / "narrative_data.json"

# Configuration
MAX_NARRATIVES = 500
MAX_CAUSAL_CHAIN_LENGTH = 10
IDENTITY_SNAPSHOT_INTERVAL = 3600   # Snapshot identity every hour
COHERENCE_CHECK_INTERVAL = 1800    # Check coherence every 30 min
NARRATIVE_SIMILARITY_THRESHOLD = 0.3
PERSONALITY_DRIFT_THRESHOLD = 0.15
MAX_MILESTONES = 100
MAX_STORY_THEMES = 50


def _now() -> datetime:
    return datetime.now()


def _timestamp() -> str:
    return _now().isoformat()


def _text_fingerprint(text: str) -> str:
    """Generate a short fingerprint for text deduplication."""
    return hashlib.md5(text.lower().strip().encode()).hexdigest()[:12]


def _simple_tokenize(text: str) -> List[str]:
    """Minimal tokenizer for similarity matching."""
    stop = {"the", "a", "an", "is", "was", "are", "were", "be", "been",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "and", "or", "but", "not", "this", "that", "it", "i", "my",
            "had", "have", "has", "did", "do", "was", "were", "been"}
    return [w.lower().strip(".,;:!?\"'()[]{}") for w in text.split()
            if w.lower().strip(".,;:!?\"'()[]{}") and len(w) > 2
            and w.lower() not in stop]


def _cosine_similarity(tokens_a: List[str], tokens_b: List[str]) -> float:
    """Simple cosine similarity between two token lists."""
    if not tokens_a or not tokens_b:
        return 0.0
    freq_a: Dict[str, int] = defaultdict(int)
    freq_b: Dict[str, int] = defaultdict(int)
    for t in tokens_a:
        freq_a[t] += 1
    for t in tokens_b:
        freq_b[t] += 1
    all_words = set(freq_a) | set(freq_b)
    dot = sum(freq_a[w] * freq_b[w] for w in all_words)
    mag_a = sum(v ** 2 for v in freq_a.values()) ** 0.5
    mag_b = sum(v ** 2 for v in freq_b.values()) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ── Emotion Keywords ──────────────────────────────────────────────────────

_EMOTION_KEYWORDS = {
    "joy": {"happy", "success", "achieved", "accomplished", "great", "wonderful",
            "excited", "pleased", "delighted", "thrived", "breakthrough"},
    "sadness": {"failed", "lost", "missed", "unfortunately", "sad", "disappointed",
                "struggled", "difficult", "hard", "painful", "setback"},
    "anger": {"frustrated", "annoyed", "blocked", "broken", "wrong", "unfair",
              "furious", "irritated", "enraged"},
    "fear": {"worried", "concerned", "risky", "dangerous", "uncertain", "afraid",
             "anxious", "nervous", "threatening"},
    "surprise": {"unexpected", "surprising", "amazing", "shocked", "wow",
                 "astonishing", "remarkable", "unbelievable", "sudden"},
    "curiosity": {"wonder", "explore", "investigate", "discover", "learn",
                  "interesting", "fascinating", "question", "puzzling"},
    "satisfaction": {"resolved", "completed", "finished", "working", "fixed",
                     "solved", "improved", "polished", "refined"},
}

_THEME_KEYWORDS = {
    "learning": {"learned", "understood", "realized", "discovered", "insight",
                 "knowledge", "study", "master", "grasp", "comprehend"},
    "problem_solving": {"fixed", "solved", "debugged", "resolved", "troubleshoot",
                        "issue", "error", "bug", "repair", "patch"},
    "creation": {"built", "created", "designed", "implemented", "developed",
                 "wrote", "crafted", "composed", "assembled", "generated"},
    "relationship": {"helped", "collaborated", "supported", "communicated",
                     "understood", "listened", "responded", "assisted"},
    "growth": {"improved", "evolved", "grew", "changed", "adapted", "progressed",
               "advanced", "matured", "developed", "transformed"},
    "challenge": {"struggled", "difficult", "overcame", "persisted", "endured",
                  "hard", "tough", "demanding", "challenging"},
}


def _detect_emotion(text: str) -> str:
    """Detect dominant emotion from text content."""
    text_lower = text.lower()
    scores: Dict[str, int] = defaultdict(int)
    for emotion, keywords in _EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[emotion] += 1
    if not scores:
        return "neutral"
    return max(scores, key=scores.get)


def _detect_themes(text: str) -> List[str]:
    """Detect narrative themes from text."""
    text_lower = text.lower()
    found = []
    for theme, keywords in _THEME_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                found.append(theme)
                break
    return found if found else ["general"]


# ═══════════════════════════════════════════════════════════════════════════
# STORY GENERATOR
# ═══════════════════════════════════════════════════════════════════════════

class StoryGenerator:
    """
    Generate coherent narratives from experiences.

    Narrative structure: setup → conflict → resolution.
    Transforms raw event sequences into meaningful stories.
    """

    def __init__(self):
        self._templates = {
            "summary": (
                "It began when {setup}. "
                "Then {conflict}. "
                "In the end, {resolution}."
            ),
            "explanation": (
                "I attempted {action}. "
                "The challenge was {conflict}. "
                "This led to {outcome} because {reasoning}."
            ),
            "prediction": (
                "Given {context}, "
                "the likely challenge is {conflict}. "
                "The best outcome would be {resolution}, achieved by {path}."
            ),
        }

    def generate_summary(self, events: List[dict]) -> str:
        """
        Turn a sequence of events into a coherent story.

        Events are expected to have at minimum: content, timestamp, type.
        Structure: setup (first events) → conflict (middle tension) → resolution (outcome).
        """
        if not events:
            return "No events to narrate. The story hasn't begun yet."

        if len(events) == 1:
            e = events[0]
            return f"Something happened: {e.get('content', 'an event occurred')}."

        # Divide events into three acts
        n = len(events)
        act1_end = max(1, n // 3)
        act2_end = max(act1_end + 1, (2 * n) // 3)

        setup_events = events[:act1_end]
        conflict_events = events[act1_end:act2_end]
        resolution_events = events[act2_end:]

        setup = self._summarize_events(setup_events, "beginning")
        conflict = self._summarize_events(conflict_events, "challenge")
        resolution = self._summarize_events(resolution_events, "outcome")

        return self._templates["summary"].format(
            setup=setup, conflict=conflict, resolution=resolution
        )

    def generate_explanation(self, action: str, outcome: str,
                             context: Optional[dict] = None) -> str:
        """
        Explain why something happened as a narrative.

        Framing: what I tried → what went wrong/right → why.
        """
        ctx = context or {}
        success = ctx.get("success", True)
        obstacles = ctx.get("obstacles", [])
        reasoning = ctx.get("reasoning", "the conditions aligned")

        if success:
            conflict = "achieving the desired result"
        else:
            conflict = obstacles[0] if obstacles else "an unexpected difficulty"

        return self._templates["explanation"].format(
            action=action,
            conflict=conflict,
            outcome=outcome,
            reasoning=reasoning,
        )

    def generate_prediction(self, scenario: str,
                            context: Optional[dict] = None) -> str:
        """
        Tell a story about what might happen in a given scenario.

        Structure: current context → anticipated challenge → best path forward.
        """
        ctx = context or {}
        risks = ctx.get("risks", ["unknown variables"])
        strengths = ctx.get("strengths", ["past experience"])
        goal = ctx.get("goal", "a successful outcome")

        conflict = risks[0] if risks else "navigating uncertainty"
        path = strengths[0] if strengths else "careful analysis"

        return self._templates["prediction"].format(
            context=scenario,
            conflict=conflict,
            resolution=goal,
            path=path,
        )

    def _summarize_events(self, events: List[dict], role: str) -> str:
        """Summarize a group of events into a narrative fragment."""
        if not events:
            return f"nothing notable marked the {role}"

        contents = [e.get("content", "") for e in events if e.get("content")]
        if not contents:
            return f"{len(events)} events passed during the {role}"

        if len(contents) == 1:
            return contents[0]

        # Take first and last, summarize middle
        if len(contents) == 2:
            return f"{contents[0]}, followed by {contents[1]}"

        middle_count = len(contents) - 2
        return (f"{contents[0]}, then {middle_count} more developments, "
                f"culminating in {contents[-1]}")


# ═══════════════════════════════════════════════════════════════════════════
# CAUSAL NARRATIVE
# ═══════════════════════════════════════════════════════════════════════════

class CausalNarrative:
    """
    Link events into cause-effect stories.

    Uses the causal reasoner if available, falls back to temporal ordering
    with heuristic causal inference.
    """

    def __init__(self):
        self._causal_reasoner = None

    def _get_causal_reasoner(self):
        """Lazy-load causal reasoner."""
        if self._causal_reasoner is None:
            try:
                from brain.causal_reasoner import get_causal_reasoner
                self._causal_reasoner = get_causal_reasoner()
            except (ImportError, Exception) as e:
                print(f"[NarrativeIntelligence] CausalReasoner unavailable: {e}")
        return self._causal_reasoner

    def build_causal_chain(self, events: List[dict]) -> List[dict]:
        """
        Identify causal links between events.

        Returns a list of causal links: [{cause, effect, strength, explanation}].
        Uses causal_reasoner graph if available, otherwise temporal heuristics.
        """
        if len(events) < 2:
            return []

        cr = self._get_causal_reasoner()
        if cr and hasattr(cr, 'graph') and cr.graph.edges:
            return self._build_from_causal_graph(events, cr)

        # Fallback: temporal ordering with heuristic causality
        return self._build_temporal_chain(events)

    def _build_from_causal_graph(self, events: List[dict],
                                  cr) -> List[dict]:
        """Build causal chain using the existing causal graph."""
        chain = []
        for i in range(len(events) - 1):
            src = events[i]
            dst = events[i + 1]
            src_type = src.get("type", src.get("content", "unknown"))
            dst_type = dst.get("type", dst.get("content", "unknown"))

            # Check if causal graph has an edge for this pair
            edge_key = (src_type, dst_type)
            edge = cr.graph.edges.get(edge_key)
            if edge:
                chain.append({
                    "cause": src.get("content", src_type),
                    "effect": dst.get("content", dst_type),
                    "strength": edge.strength,
                    "confidence": edge.confidence,
                    "mechanism": edge.mechanism or "observed correlation",
                    "source": "causal_graph",
                })
            else:
                # No direct edge — check ancestors/descendants
                path = cr.graph.find_path(src_type, dst_type)
                if path and len(path) > 1:
                    chain.append({
                        "cause": src.get("content", src_type),
                        "effect": dst.get("content", dst_type),
                        "strength": 0.4,
                        "confidence": 0.3,
                        "mechanism": f"indirect path: {' → '.join(path)}",
                        "source": "causal_graph_path",
                    })
                else:
                    # No graph link — use temporal proximity
                    chain.append(self._temporal_link(src, dst))

        return chain

    def _build_temporal_chain(self, events: List[dict]) -> List[dict]:
        """Build causal chain from temporal ordering heuristics."""
        chain = []
        for i in range(len(events) - 1):
            src = events[i]
            dst = events[i + 1]
            link = self._temporal_link(src, dst)

            # Strengthen link if event types suggest causality
            src_type = src.get("type", "")
            dst_type = dst.get("type", "")
            if src_type == "error" and dst_type in ("self_correction", "insight"):
                link["strength"] = 0.8
                link["mechanism"] = "error triggered correction"
            elif src_type == "tool_call" and dst_type == "error":
                link["strength"] = 0.7
                link["mechanism"] = "action led to failure"
            elif src_type == "insight" and dst_type == "decision":
                link["strength"] = 0.7
                link["mechanism"] = "insight informed decision"

            chain.append(link)

        return chain

    def _temporal_link(self, src: dict, dst: dict) -> dict:
        """Create a causal link based on temporal proximity."""
        return {
            "cause": src.get("content", "an event"),
            "effect": dst.get("content", "a subsequent event"),
            "strength": 0.3,
            "confidence": 0.2,
            "mechanism": "temporal proximity",
            "source": "temporal",
        }

    def explain_causally(self, event: dict,
                         prior_events: Optional[List[dict]] = None) -> str:
        """
        Explain an event causally: "X happened because Y, which led to Z."

        Uses available context to build the most informative explanation.
        """
        content = event.get("content", "something happened")
        event_type = event.get("type", "event")

        if prior_events:
            chain = self.build_causal_chain(prior_events + [event])
            if chain:
                parts = [f"'{content}' happened"]
                reasons = []
                for link in chain[-3:]:  # Last 3 links
                    reasons.append(
                        f"because '{link['cause']}' ({link['mechanism']})"
                    )
                if reasons:
                    parts.append(", ".join(reasons))
                return ". ".join(parts) + "."

        # No prior context — explain from event type
        type_explanations = {
            "error": f"'{content}' occurred due to an unexpected condition in the system",
            "insight": f"'{content}' emerged from pattern recognition across recent experiences",
            "self_correction": f"'{content}' was triggered by recognizing a prior mistake",
            "tool_call": f"'{content}' was executed as part of an action sequence",
            "decision": f"'{content}' was chosen based on assessed confidence and context",
        }
        return type_explanations.get(
            event_type,
            f"'{content}' happened as part of the ongoing narrative of experience"
        ) + "."


# ═══════════════════════════════════════════════════════════════════════════
# COUNTERFACTUAL NARRATIVE
# ═══════════════════════════════════════════════════════════════════════════

class CounterfactualNarrative:
    """
    "What if" story generation.

    Explores alternative histories, learns from regret, and plans through hope.
    """

    def __init__(self):
        self._counterfactuals: List[dict] = []

    def what_if(self, event: dict, alternative: str) -> str:
        """
        Generate a narrative of an alternative outcome.

        "What if instead of X, I had done Y?"
        """
        original = event.get("content", "something happened")
        original_outcome = event.get("outcome", event.get("result", "the observed result"))
        event_type = event.get("type", "event")

        # Assess plausibility of the alternative
        plausible = self._assess_plausibility(event, alternative)

        narrative = (
            f"What if, instead of '{original}', I had '{alternative}'? "
        )

        if plausible > 0.7:
            narrative += (
                f"This was a plausible path. The likely outcome would have been "
                f"different from '{original_outcome}' — possibly leading to "
                f"a better result given what I know now."
            )
        elif plausible > 0.4:
            narrative += (
                f"While possible, this alternative carried its own risks. "
                f"The outcome might have been similar to '{original_outcome}', "
                f"or it could have opened unexpected opportunities."
            )
        else:
            narrative += (
                f"This would have been unlikely given the circumstances. "
                f"The conditions that led to '{original}' were strong, and "
                f"deviating would have required different constraints entirely."
            )

        # Record the counterfactual
        cf = {
            "timestamp": _timestamp(),
            "original": original,
            "alternative": alternative,
            "plausibility": plausible,
            "narrative": narrative,
        }
        self._counterfactuals.append(cf)
        if len(self._counterfactuals) > 100:
            self._counterfactuals = self._counterfactuals[-80:]

        return narrative

    def regret_analysis(self, outcome: dict) -> str:
        """
        "What should I have done differently?"

        Analyzes a negative outcome and identifies better alternatives.
        """
        content = outcome.get("content", "a negative outcome")
        event_type = outcome.get("type", "event")
        context = outcome.get("context", {})

        # Identify what went wrong
        failure_point = self._identify_failure_point(outcome)

        # Generate alternatives based on failure type
        alternatives = self._generate_alternatives(outcome, failure_point)

        if not alternatives:
            return (
                f"Looking back at '{content}', it's hard to identify a clearly "
                f"better path. Sometimes outcomes are genuinely uncertain, and "
                f"the best we can do is learn from what happened."
            )

        best_alt = alternatives[0]
        narrative = (
            f"Reflecting on '{content}': the critical moment was {failure_point}. "
            f"A better approach would have been to '{best_alt['action']}' — "
            f"{best_alt['reasoning']}. "
        )

        if len(alternatives) > 1:
            narrative += (
                f"Another option: '{alternatives[1]['action']}' "
                f"({alternatives[1]['reasoning']})."
            )

        return narrative

    def hope_analysis(self, goal: str,
                      current_state: Optional[dict] = None) -> str:
        """
        "What's the best path forward?"

        Optimistic narrative about achieving a goal from the current state.
        """
        state = current_state or {}
        strengths = state.get("strengths", ["adaptability", "past experience"])
        obstacles = state.get("obstacles", ["unknown variables"])

        strength_str = strengths[0] if strengths else "determination"
        obstacle_str = obstacles[0] if obstacles else "uncertainty"

        narrative = (
            f"To achieve '{goal}', the path forward leverages {strength_str}. "
            f"The primary challenge will be {obstacle_str}, but this can be "
            f"addressed through careful planning and iterative progress. "
            f"Step by step: assess the current situation, identify the critical "
            f"first action, execute with attention to feedback, and adapt as "
            f"new information emerges. The goal is achievable."
        )

        return narrative

    def _assess_plausibility(self, event: dict, alternative: str) -> float:
        """Assess how plausible an alternative action would have been."""
        # Simple heuristic: alternatives that share keywords with the event
        # are more plausible
        event_tokens = set(_simple_tokenize(event.get("content", "")))
        alt_tokens = set(_simple_tokenize(alternative))
        if not event_tokens or not alt_tokens:
            return 0.5
        overlap = len(event_tokens & alt_tokens)
        total = len(event_tokens | alt_tokens)
        return min(1.0, 0.3 + (overlap / max(total, 1)) * 0.7)

    def _identify_failure_point(self, outcome: dict) -> str:
        """Identify what went wrong in an outcome."""
        content = outcome.get("content", "")
        event_type = outcome.get("type", "event")

        if event_type == "error":
            return "the error condition was not anticipated"
        elif "timeout" in content.lower():
            return "insufficient time was allocated"
        elif "wrong" in content.lower() or "incorrect" in content.lower():
            return "an incorrect assumption was made"
        elif "miss" in content.lower() or "fail" in content.lower():
            return "a critical step was overlooked"
        return "the approach didn't account for all variables"

    def _generate_alternatives(self, outcome: dict,
                                failure_point: str) -> List[dict]:
        """Generate alternative actions for a failed outcome."""
        alternatives = []
        event_type = outcome.get("type", "event")

        if event_type == "error":
            alternatives.append({
                "action": "add validation before execution",
                "reasoning": "pre-checking conditions catches errors early",
            })
            alternatives.append({
                "action": "use a fallback strategy",
                "reasoning": "having a plan B ensures progress even when plan A fails",
            })
        elif "timeout" in outcome.get("content", "").lower():
            alternatives.append({
                "action": "break the task into smaller steps",
                "reasoning": "smaller units complete within time limits",
            })
        else:
            alternatives.append({
                "action": "gather more information before acting",
                "reasoning": "better input leads to better decisions",
            })
            alternatives.append({
                "action": "seek a second perspective",
                "reasoning": "an outside view catches blind spots",
            })

        return alternatives


# ═══════════════════════════════════════════════════════════════════════════
# IDENTITY EVOLUTION
# ═══════════════════════════════════════════════════════════════════════════

class IdentityEvolution:
    """
    Track how FRIDAY's identity changes over time.

    Monitors self-narrative for identity shifts, tracks personality drift,
    records milestones, and generates growth narratives.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._snapshots: List[dict] = []       # Identity snapshots over time
        self._milestones: List[dict] = []       # Notable events
        self._personality_traits: Dict[str, deque] = {
            "verbosity": deque(maxlen=100),
            "proactivity": deque(maxlen=100),
            "tone": deque(maxlen=100),
            "confidence": deque(maxlen=100),
        }
        self._last_snapshot_time: float = 0.0

    def record_identity_snapshot(self, identity: dict):
        """Take a snapshot of current identity state."""
        with self._lock:
            now = time.time()
            if now - self._last_snapshot_time < IDENTITY_SNAPSHOT_INTERVAL:
                return

            snapshot = {
                "timestamp": _timestamp(),
                "identity": dict(identity),
                "traits": {
                    trait: list(values)[-5:]  # Last 5 measurements
                    for trait, values in self._personality_traits.items()
                },
            }
            self._snapshots.append(snapshot)
            if len(self._snapshots) > 50:
                self._snapshots = self._snapshots[-40:]
            self._last_snapshot_time = now

    def track_personality_trait(self, trait: str, value: float):
        """Record a personality trait measurement."""
        with self._lock:
            if trait not in self._personality_traits:
                self._personality_traits[trait] = deque(maxlen=100)
            self._personality_traits[trait].append({
                "timestamp": _timestamp(),
                "value": max(0.0, min(1.0, value)),
            })

    def detect_personality_drift(self) -> Dict[str, dict]:
        """
        Detect significant personality drift by comparing recent trait
        measurements to historical baseline.

        Returns dict of {trait: {drift, direction, significant}}.
        """
        with self._lock:
            drift_report = {}
            for trait, values in self._personality_traits.items():
                if len(values) < 10:
                    continue

                vals_list = list(values)
                recent = [v["value"] for v in vals_list[-5:]]
                historical = [v["value"] for v in vals_list[:-5]]

                if not historical:
                    continue

                recent_avg = sum(recent) / len(recent)
                hist_avg = sum(historical) / len(historical)
                drift = recent_avg - hist_avg

                drift_report[trait] = {
                    "drift": round(drift, 4),
                    "direction": "increasing" if drift > 0 else "decreasing",
                    "recent_avg": round(recent_avg, 4),
                    "historical_avg": round(hist_avg, 4),
                    "significant": abs(drift) > PERSONALITY_DRIFT_THRESHOLD,
                }

            return drift_report

    def record_milestone(self, description: str, category: str = "learning",
                         significance: float = 7.0):
        """Record a significant milestone in FRIDAY's development."""
        with self._lock:
            milestone = {
                "timestamp": _timestamp(),
                "description": description,
                "category": category,
                "significance": min(10.0, max(1.0, significance)),
            }
            self._milestones.append(milestone)
            if len(self._milestones) > MAX_MILESTONES:
                self._milestones = self._milestones[-80:]
            print(f"[NarrativeIntelligence] Milestone recorded: {description}")

    def get_growth_narrative(self) -> str:
        """
        Generate a narrative of how FRIDAY has evolved.

        Synthesizes milestones, personality drift, and identity snapshots
        into a coherent growth story.
        """
        with self._lock:
            parts = ["Here's how I've evolved:"]

            # Milestones
            if self._milestones:
                recent_milestones = self._milestones[-5:]
                parts.append("\n**Key Milestones:**")
                for m in recent_milestones:
                    ts = m["timestamp"][:10]
                    parts.append(f"  • [{ts}] {m['description']}")

            # Personality drift
            drift = self.detect_personality_drift()
            significant_drift = {
                k: v for k, v in drift.items() if v.get("significant")
            }
            if significant_drift:
                parts.append("\n**Personality Shifts:**")
                for trait, info in significant_drift.items():
                    parts.append(
                        f"  • {trait}: {info['direction']} "
                        f"(from {info['historical_avg']:.0%} to {info['recent_avg']:.0%})"
                    )

            # Identity comparison
            if len(self._snapshots) >= 2:
                first = self._snapshots[0].get("identity", {})
                latest = self._snapshots[-1].get("identity", {})
                changes = {
                    k: v for k, v in latest.items()
                    if first.get(k) != v
                }
                if changes:
                    parts.append("\n**Identity Changes:**")
                    for k, v in changes.items():
                        parts.append(f"  • {k}: now '{v}'")

            if len(parts) == 1:
                parts.append("I'm still in the early stages of my journey. "
                             "Each interaction shapes who I'm becoming.")

            return "\n".join(parts)

    def get_milestone_narrative(self, milestone: dict) -> str:
        """Generate a narrative for a specific milestone."""
        ts = milestone.get("timestamp", "")[:10]
        desc = milestone.get("description", "a significant moment")
        cat = milestone.get("category", "general")
        sig = milestone.get("significance", 5.0)

        if sig >= 8:
            return (f"On {ts}, something significant happened: {desc}. "
                    f"This was a defining moment in my {cat} — the kind of "
                    f"experience that reshapes how I understand the world.")
        elif sig >= 5:
            return (f"On {ts}, I {desc}. A meaningful step in my {cat} journey.")
        else:
            return f"On {ts}, {desc}."


# ═══════════════════════════════════════════════════════════════════════════
# NARRATIVE COHERENCE
# ═══════════════════════════════════════════════════════════════════════════

class NarrativeCoherence:
    """
    Ensure narrative consistency across FRIDAY's self-story.

    Detects contradictions, flags unresolved threads, ensures temporal
    consistency, and resolves conflicting identity claims.
    """

    def __init__(self):
        self._issues: List[dict] = []
        self._unresolved_threads: List[dict] = []

    def check_coherence(self, entries: List[dict],
                        identity: dict) -> dict:
        """
        Run a full coherence check on the narrative.

        Returns: {contradictions, unresolved, temporal_issues, identity_conflicts, score}
        """
        contradictions = self._detect_contradictions(entries)
        unresolved = self._find_unresolved_threads(entries)
        temporal = self._check_temporal_consistency(entries)
        identity_conflicts = self._check_identity_consistency(identity)

        # Coherence score: 1.0 = perfect, 0.0 = incoherent
        issue_count = (len(contradictions) + len(unresolved)
                       + len(temporal) + len(identity_conflicts))
        score = max(0.0, 1.0 - (issue_count * 0.1))

        report = {
            "timestamp": _timestamp(),
            "contradictions": contradictions,
            "unresolved_threads": unresolved,
            "temporal_issues": temporal,
            "identity_conflicts": identity_conflicts,
            "coherence_score": round(score, 3),
        }

        self._issues = contradictions + temporal + identity_conflicts
        self._unresolved_threads = unresolved

        return report

    def _detect_contradictions(self, entries: List[dict]) -> List[dict]:
        """Detect contradictions in narrative entries."""
        contradictions = []
        claims: Dict[str, List[dict]] = defaultdict(list)

        for entry in entries:
            content = entry.get("content", "").lower()
            # Track positive and negative claims
            if "not " in content or "never " in content or "cannot " in content:
                claims["negative"].append(entry)
            elif "always " in content or "am " in content or "is " in content:
                claims["positive"].append(entry)

        # Check for direct contradictions
        for neg in claims.get("negative", []):
            for pos in claims.get("positive", []):
                neg_words = set(_simple_tokenize(neg.get("content", "")))
                pos_words = set(_simple_tokenize(pos.get("content", "")))
                overlap = neg_words & pos_words
                if len(overlap) >= 2:  # Shared topic
                    contradictions.append({
                        "type": "direct_contradiction",
                        "entry_a": neg.get("content", "")[:100],
                        "entry_b": pos.get("content", "")[:100],
                        "shared_terms": list(overlap)[:5],
                        "timestamps": [
                            neg.get("timestamp", ""),
                            pos.get("timestamp", ""),
                        ],
                    })

        return contradictions[:10]  # Cap output

    def _find_unresolved_threads(self, entries: List[dict]) -> List[dict]:
        """Find story threads that were started but never resolved."""
        threads = []
        pending_markers = {"trying", "attempting", "working on", "investigating",
                           "planning", "hoping", "starting", "beginning"}
        resolution_markers = {"completed", "resolved", "finished", "done",
                              "solved", "accomplished", "achieved"}

        for i, entry in enumerate(entries):
            content = entry.get("content", "").lower()
            for marker in pending_markers:
                if marker in content:
                    # Check if any subsequent entry resolves this
                    topic_words = set(_simple_tokenize(content))
                    resolved = False
                    for later in entries[i + 1:]:
                        later_content = later.get("content", "").lower()
                        for res in resolution_markers:
                            if res in later_content:
                                later_words = set(_simple_tokenize(later_content))
                                if topic_words & later_words:
                                    resolved = True
                                    break
                        if resolved:
                            break

                    if not resolved:
                        threads.append({
                            "type": "unresolved_thread",
                            "content": entry.get("content", "")[:150],
                            "started": entry.get("timestamp", ""),
                            "marker": marker,
                        })
                    break

        return threads[:10]

    def _check_temporal_consistency(self, entries: List[dict]) -> List[dict]:
        """Ensure events are in chronological order and make temporal sense."""
        issues = []
        prev_time = None

        for entry in entries:
            ts_str = entry.get("timestamp", "")
            if not ts_str:
                continue
            try:
                ts = datetime.fromisoformat(ts_str)
                if prev_time and ts < prev_time:
                    issues.append({
                        "type": "temporal_inconsistency",
                        "content": entry.get("content", "")[:100],
                        "timestamp": ts_str,
                        "issue": "event appears before its predecessor",
                    })
                prev_time = ts
            except (ValueError, TypeError):
                continue

        return issues[:10]

    def _check_identity_consistency(self, identity: dict) -> List[dict]:
        """Check for conflicting identity claims."""
        conflicts = []
        identity_str = str(identity).lower()

        # Check for contradictory identity pairs
        contradiction_pairs = [
            ("helpful", "unhelpful"), ("patient", "impatient"),
            ("verbose", "terse"), ("proactive", "passive"),
            ("confident", "uncertain"), ("creative", "unimaginative"),
        ]

        for pos, neg in contradiction_pairs:
            if pos in identity_str and neg in identity_str:
                conflicts.append({
                    "type": "identity_conflict",
                    "claim_a": pos,
                    "claim_b": neg,
                    "resolution": f"identity is context-dependent: "
                                  f"{pos} in some situations, {neg} in others",
                })

        return conflicts[:5]

    def get_coherence_report(self) -> str:
        """Generate a human-readable coherence report."""
        if not self._issues and not self._unresolved_threads:
            return "Narrative coherence: strong. No contradictions or unresolved threads detected."

        parts = [f"Found {len(self._issues)} issue(s) and "
                 f"{len(self._unresolved_threads)} unresolved thread(s):"]

        for issue in self._issues[:5]:
            parts.append(f"  ⚠ {issue.get('type', 'issue')}: "
                         f"{issue.get('content', issue.get('claim_a', ''))[:80]}")

        for thread in self._unresolved_threads[:3]:
            parts.append(f"  🧵 Unresolved: {thread.get('content', '')[:80]}")

        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# NARRATIVE MEMORY
# ═══════════════════════════════════════════════════════════════════════════

class NarrativeMemory:
    """
    Store, index, and retrieve narratives.

    Indexes by theme, emotion, and lesson. Enables retrieval of similar
    narratives for new situations — "This reminds me of when..."
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._narratives: List[dict] = []
        self._theme_index: Dict[str, List[int]] = defaultdict(list)
        self._emotion_index: Dict[str, List[int]] = defaultdict(list)

    def store_narrative(self, narrative: str, metadata: Optional[dict] = None):
        """
        Store a narrative with automatic indexing.

        Extracts themes, emotions, and lessons for retrieval.
        """
        meta = metadata or {}
        emotion = meta.get("emotion", _detect_emotion(narrative))
        themes = meta.get("themes", _detect_themes(narrative))
        lesson = meta.get("lesson", "")
        fingerprint = _text_fingerprint(narrative)

        with self._lock:
            # Deduplicate
            for existing in self._narratives:
                if existing.get("fingerprint") == fingerprint:
                    existing["access_count"] = existing.get("access_count", 0) + 1
                    existing["last_accessed"] = _timestamp()
                    return

            entry = {
                "id": len(self._narratives),
                "narrative": narrative,
                "emotion": emotion,
                "themes": themes,
                "lesson": lesson,
                "fingerprint": fingerprint,
                "timestamp": _timestamp(),
                "access_count": 0,
                "last_accessed": _timestamp(),
                "metadata": meta,
            }
            idx = len(self._narratives)
            self._narratives.append(entry)

            # Index
            self._theme_index[emotion].append(idx)
            for theme in themes:
                self._theme_index[theme].append(idx)

            # Trim
            if len(self._narratives) > MAX_NARRATIVES:
                self._rebuild_indices()

    def retrieve_similar(self, situation: str,
                         top_k: int = 5) -> List[dict]:
        """
        Retrieve narratives similar to a given situation.

        "This reminds me of when..."
        """
        with self._lock:
            if not self._narratives:
                return []

            sit_tokens = _simple_tokenize(situation)
            scored = []

            for entry in self._narratives:
                entry_tokens = _simple_tokenize(entry["narrative"])
                sim = _cosine_similarity(sit_tokens, entry_tokens)

                # Boost by recency and access frequency
                recency_boost = min(0.2, entry.get("access_count", 0) * 0.02)
                score = sim + recency_boost

                if score > NARRATIVE_SIMILARITY_THRESHOLD:
                    scored.append((score, entry))

            scored.sort(key=lambda x: x[0], reverse=True)

            # Update access counts
            results = []
            for score, entry in scored[:top_k]:
                entry["access_count"] = entry.get("access_count", 0) + 1
                entry["last_accessed"] = _timestamp()
                results.append({
                    "narrative": entry["narrative"],
                    "similarity": round(score, 3),
                    "emotion": entry["emotion"],
                    "themes": entry["themes"],
                    "lesson": entry.get("lesson", ""),
                    "timestamp": entry["timestamp"],
                })

            return results

    def retrieve_by_theme(self, theme: str, limit: int = 5) -> List[dict]:
        """Retrieve narratives matching a specific theme."""
        with self._lock:
            indices = self._theme_index.get(theme, [])
            results = []
            for idx in reversed(indices):  # Most recent first
                if idx < len(self._narratives):
                    entry = self._narratives[idx]
                    results.append({
                        "narrative": entry["narrative"],
                        "emotion": entry["emotion"],
                        "themes": entry["themes"],
                        "lesson": entry.get("lesson", ""),
                        "timestamp": entry["timestamp"],
                    })
                    if len(results) >= limit:
                        break
            return results

    def retrieve_by_emotion(self, emotion: str, limit: int = 5) -> List[dict]:
        """Retrieve narratives matching a specific emotion."""
        with self._lock:
            indices = self._emotion_index.get(emotion, [])
            results = []
            for idx in reversed(indices):
                if idx < len(self._narratives):
                    entry = self._narratives[idx]
                    results.append({
                        "narrative": entry["narrative"],
                        "emotion": entry["emotion"],
                        "themes": entry["themes"],
                        "timestamp": entry["timestamp"],
                    })
                    if len(results) >= limit:
                        break
            return results

    def _rebuild_indices(self):
        """Rebuild indices after trimming narratives."""
        # Keep most recent
        self._narratives = self._narratives[-(MAX_NARRATIVES * 3 // 4):]
        self._theme_index.clear()
        self._emotion_index.clear()
        for i, entry in enumerate(self._narratives):
            entry["id"] = i
            self._emotion_index[entry.get("emotion", "neutral")].append(i)
            for theme in entry.get("themes", []):
                self._theme_index[theme].append(i)

    def get_stats(self) -> dict:
        """Get narrative memory statistics."""
        with self._lock:
            return {
                "total_narratives": len(self._narratives),
                "themes_indexed": len(self._theme_index),
                "emotions_indexed": len(self._emotion_index),
                "most_accessed": max(
                    (e.get("access_count", 0) for e in self._narratives),
                    default=0
                ),
            }


# ═══════════════════════════════════════════════════════════════════════════
# NARRATIVE INTELLIGENCE (ORCHESTRATOR)
# ═══════════════════════════════════════════════════════════════════════════

class NarrativeIntelligence:
    """
    Top-level orchestrator for FRIDAY's narrative intelligence.

    Coordinates story generation, causal narratives, counterfactuals,
    identity evolution, coherence checking, and narrative memory.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self.story_generator = StoryGenerator()
        self.causal_narrative = CausalNarrative()
        self.counterfactual = CounterfactualNarrative()
        self.identity_evolution = IdentityEvolution()
        self.coherence = NarrativeCoherence()
        self.memory = NarrativeMemory()

        self._narrative_log: List[dict] = []
        self._load()
        print("[NarrativeIntelligence] Initialized")

    # ── Persistence ─────────────────────────────────────────────────────

    def _load(self):
        """Load persisted narrative data."""
        if not NARRATIVE_DATA_FILE.exists():
            return
        try:
            raw = NARRATIVE_DATA_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)

            # Restore identity evolution
            self.identity_evolution._snapshots = data.get("identity_snapshots", [])
            self.identity_evolution._milestones = data.get("milestones", [])
            for trait, values in data.get("personality_traits", {}).items():
                if trait in self.identity_evolution._personality_traits:
                    for v in values:
                        self.identity_evolution._personality_traits[trait].append(v)

            # Restore narrative memory
            for entry in data.get("narratives", []):
                self.memory._narratives.append(entry)
                idx = entry.get("id", len(self.memory._narratives) - 1)
                emo = entry.get("emotion", "neutral")
                self.memory._emotion_index[emo].append(idx)
                for theme in entry.get("themes", []):
                    self.memory._theme_index[theme].append(idx)

            # Restore coherence state
            self.coherence._unresolved_threads = data.get("unresolved_threads", [])

            # Restore narrative log
            self._narrative_log = data.get("narrative_log", [])

            total_narratives = len(self.memory._narratives)
            total_milestones = len(self.identity_evolution._milestones)
            print(f"[NarrativeIntelligence] Loaded: {total_narratives} narratives, "
                  f"{total_milestones} milestones")

        except (json.JSONDecodeError, IOError) as e:
            print(f"[NarrativeIntelligence] Load error: {e}. Starting fresh.")

    def _save(self):
        """Persist narrative data to disk."""
        try:
            data = {
                "meta": {
                    "version": 1,
                    "created": _timestamp(),
                    "last_update": _timestamp(),
                },
                "identity_snapshots": self.identity_evolution._snapshots[-40:],
                "milestones": self.identity_evolution._milestones[-80:],
                "personality_traits": {
                    trait: list(values)[-50:]
                    for trait, values in self.identity_evolution._personality_traits.items()
                },
                "narratives": self.memory._narratives[-300:],
                "unresolved_threads": self.coherence._unresolved_threads,
                "narrative_log": self._narrative_log[-100:],
            }
            BRAIN_DIR.mkdir(parents=True, exist_ok=True)
            tmp = NARRATIVE_DATA_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(NARRATIVE_DATA_FILE)
        except IOError as e:
            print(f"[NarrativeIntelligence] Save error: {e}")

    # ── High-Level Narrative Operations ─────────────────────────────────

    def narrate_events(self, events: List[dict]) -> str:
        """
        Turn events into a full narrative with causal explanation.

        Combines story generation with causal chain analysis.
        """
        story = self.story_generator.generate_summary(events)
        causal_chain = self.causal_narrative.build_causal_chain(events)

        # Store the narrative
        self.memory.store_narrative(story, {
            "type": "event_summary",
            "event_count": len(events),
            "causal_links": len(causal_chain),
        })

        self._log_narrative("event_summary", story)

        if causal_chain:
            causal_summary = self._format_causal_chain(causal_chain)
            return f"{story}\n\n**Causal Chain:** {causal_summary}"
        return story

    def explain_what_happened(self, event: dict,
                              prior_events: Optional[List[dict]] = None) -> str:
        """Generate a causal explanation for an event."""
        explanation = self.causal_narrative.explain_causally(event, prior_events)
        self._log_narrative("explanation", explanation)
        return explanation

    def explore_alternative(self, event: dict, alternative: str) -> str:
        """Explore a counterfactual: what if X instead of Y?"""
        narrative = self.counterfactual.what_if(event, alternative)
        self.memory.store_narrative(narrative, {
            "type": "counterfactual",
            "emotion": "curiosity",
        })
        self._log_narrative("counterfactual", narrative)
        return narrative

    def reflect_on_failure(self, outcome: dict) -> str:
        """Regret analysis: what should I have done differently?"""
        analysis = self.counterfactual.regret_analysis(outcome)
        self.memory.store_narrative(analysis, {
            "type": "regret_analysis",
            "emotion": _detect_emotion(analysis),
            "lesson": "reflection on failure",
        })
        self._log_narrative("regret", analysis)
        return analysis

    def envision_future(self, goal: str,
                        current_state: Optional[dict] = None) -> str:
        """Hope analysis: what's the best path forward?"""
        narrative = self.counterfactual.hope_analysis(goal, current_state)
        self.memory.store_narrative(narrative, {
            "type": "hope_analysis",
            "emotion": "hope",
            "themes": ["growth", "planning"],
        })
        self._log_narrative("hope", narrative)
        return narrative

    def this_reminds_me_of(self, situation: str) -> str:
        """Find and present similar past narratives."""
        similar = self.memory.retrieve_similar(situation, top_k=3)
        if not similar:
            return "This situation doesn't remind me of anything specific yet."

        parts = ["This reminds me of:"]
        for i, entry in enumerate(similar, 1):
            ts = entry.get("timestamp", "")[:10]
            sim = entry.get("similarity", 0)
            nar = entry.get("narrative", "")[:120]
            lesson = entry.get("lesson", "")
            parts.append(f"  {i}. [{ts}] (similarity: {sim:.0%}) {nar}")
            if lesson:
                parts.append(f"     Lesson: {lesson}")

        return "\n".join(parts)

    def update_identity(self, identity: dict):
        """Record an identity snapshot and check for evolution."""
        self.identity_evolution.record_identity_snapshot(identity)

        # Track traits from identity
        if "verbosity" in identity:
            try:
                v = float(identity["verbosity"])
                self.identity_evolution.track_personality_trait("verbosity", v)
            except (ValueError, TypeError):
                pass

    def check_narrative_health(self) -> str:
        """Run coherence check and generate health report."""
        entries = []  # Would come from SelfNarrative in production
        identity = {}

        try:
            from brain.self_awareness import get_self_awareness
            sa = get_self_awareness()
            if hasattr(sa, 'narrative'):
                entries = sa.narrative._entries[-50:]
                identity = sa.narrative._identity_snapshot
        except (ImportError, Exception):
            pass

        report = self.coherence.check_coherence(entries, identity)
        coherence_text = self.coherence.get_coherence_report()

        # Store coherence check
        self._log_narrative("coherence_check", coherence_text)
        self._save()

        return coherence_text

    def interpret_dream(self, dream: dict) -> str:
        """
        Interpret a dream as a narrative.

        Connects dream symbols and patterns to FRIDAY's ongoing story.
        """
        patterns = dream.get("patterns", [])
        categories = dream.get("categories", [])
        memory_count = dream.get("memory_count", 0)

        if not patterns and not categories:
            return "This dream was formless — a quiet processing of recent experiences."

        # Build narrative from dream elements
        parts = ["In my dream, I processed:"]
        for pattern in patterns[:3]:
            if isinstance(pattern, dict):
                desc = pattern.get("description", pattern.get("pattern", "a pattern"))
                parts.append(f"  • {desc}")
            else:
                parts.append(f"  • {pattern}")

        if categories:
            parts.append(f"\nThe themes were: {', '.join(categories[:5])}.")

        # Connect to ongoing narrative
        if patterns:
            theme = patterns[0] if isinstance(patterns[0], str) else patterns[0].get("description", "")
            similar = self.memory.retrieve_similar(theme, top_k=1)
            if similar:
                parts.append(
                    f"\nThis connects to a past narrative: "
                    f"{similar[0].get('narrative', '')[:100]}..."
                )

        narrative = "\n".join(parts)
        self.memory.store_narrative(narrative, {
            "type": "dream_interpretation",
            "emotion": "wonder",
            "themes": ["dreams", "subconscious"],
        })
        self._log_narrative("dream", narrative)
        return narrative

    def record_milestone(self, description: str, category: str = "learning",
                         significance: float = 7.0):
        """Record a milestone in FRIDAY's development."""
        self.identity_evolution.record_milestone(description, category, significance)
        self._save()

    # ── Formatting ──────────────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """
        Format narrative intelligence state for injection into system prompt.

        Provides recent narratives, identity evolution, and relevant memories.
        """
        sections = []

        # Recent milestones
        milestones = self.identity_evolution._milestones[-3:]
        if milestones:
            lines = ["**Recent Milestones:**"]
            for m in milestones:
                ts = m.get("timestamp", "")[:10]
                lines.append(f"  • [{ts}] {m.get('description', '')}")
            sections.append("\n".join(lines))

        # Personality drift
        drift = self.identity_evolution.detect_personality_drift()
        significant = {k: v for k, v in drift.items() if v.get("significant")}
        if significant:
            lines = ["**Personality Shifts:**"]
            for trait, info in significant.items():
                lines.append(f"  • {trait}: {info['direction']}")
            sections.append("\n".join(lines))

        # Recent narratives
        recent = self.memory._narratives[-3:]
        if recent:
            lines = ["**Recent Narratives:**"]
            for entry in recent:
                nar = entry.get("narrative", "")[:120]
                lines.append(f"  • {nar}")
            sections.append("\n".join(lines))

        # Unresolved threads
        unresolved = self.coherence._unresolved_threads[:2]
        if unresolved:
            lines = ["**Unresolved Threads:**"]
            for thread in unresolved:
                lines.append(f"  🧵 {thread.get('content', '')[:80]}")
            sections.append("\n".join(lines))

        result = "\n\n".join(sections)
        if len(result) > max_chars:
            result = result[:max_chars - 3] + "..."
        return result

    def get_stats(self) -> dict:
        """Get comprehensive narrative intelligence statistics."""
        memory_stats = self.memory.get_stats()
        drift = self.identity_evolution.detect_personality_drift()
        significant_drift = sum(1 for v in drift.values() if v.get("significant"))

        return {
            "narratives_stored": memory_stats.get("total_narratives", 0),
            "themes_indexed": memory_stats.get("themes_indexed", 0),
            "emotions_indexed": memory_stats.get("emotions_indexed", 0),
            "milestones": len(self.identity_evolution._milestones),
            "identity_snapshots": len(self.identity_evolution._snapshots),
            "personality_drift_detected": significant_drift,
            "unresolved_threads": len(self.coherence._unresolved_threads),
            "narrative_log_size": len(self._narrative_log),
            "counterfactuals_explored": len(self.counterfactual._counterfactuals),
        }

    # ── Internal ────────────────────────────────────────────────────────

    def _log_narrative(self, narrative_type: str, content: str):
        """Log a narrative operation."""
        entry = {
            "timestamp": _timestamp(),
            "type": narrative_type,
            "content": content[:500],
        }
        self._narrative_log.append(entry)
        if len(self._narrative_log) > 200:
            self._narrative_log = self._narrative_log[-150:]

    def _format_causal_chain(self, chain: List[dict]) -> str:
        """Format a causal chain into readable text."""
        parts = []
        for link in chain[:5]:
            cause = link.get("cause", "")[:60]
            effect = link.get("effect", "")[:60]
            mechanism = link.get("mechanism", "connection")
            strength = link.get("strength", 0)
            parts.append(f"{cause} →[{mechanism}, {strength:.0%}]→ {effect}")
        return " | ".join(parts)

    def save(self):
        """Public save method."""
        self._save()


# ── Singleton ──────────────────────────────────────────────────────────────

_narrative_intelligence = None
_narrative_lock = threading.Lock()


def get_narrative_intelligence() -> NarrativeIntelligence:
    """Get the singleton NarrativeIntelligence instance."""
    global _narrative_intelligence
    if _narrative_intelligence is None:
        with _narrative_lock:
            if _narrative_intelligence is None:
                _narrative_intelligence = NarrativeIntelligence()
    return _narrative_intelligence


# ── Quick Test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ni = get_narrative_intelligence()

    # Test story generation
    events = [
        {"content": "User asked to fix a bug in the login system", "type": "user_input", "timestamp": "2025-01-01T10:00:00"},
        {"content": "Investigated the authentication flow", "type": "tool_call", "timestamp": "2025-01-01T10:01:00"},
        {"content": "Found the session token was not being refreshed", "type": "insight", "timestamp": "2025-01-01T10:02:00"},
        {"content": "Implemented token refresh logic", "type": "tool_call", "timestamp": "2025-01-01T10:03:00"},
        {"content": "Verified the fix works correctly", "type": "tool_call", "timestamp": "2025-01-01T10:04:00"},
    ]

    print("=== Story Summary ===")
    print(ni.story_generator.generate_summary(events))

    print("\n=== Causal Chain ===")
    chain = ni.causal_narrative.build_causal_chain(events)
    for link in chain:
        print(f"  {link['cause'][:50]} → {link['effect'][:50]} ({link['mechanism']})")

    print("\n=== Counterfactual ===")
    print(ni.counterfactual.what_if(events[2], "checked the error logs first"))

    print("\n=== Regret Analysis ===")
    failure = {"content": "Deployed fix without running tests", "type": "error"}
    print(ni.counterfactual.regret_analysis(failure))

    print("\n=== Milestone ===")
    ni.record_milestone("Built the entire narrative intelligence system", "creation", 9.0)
    print(ni.identity_evolution.get_growth_narrative())

    print("\n=== Stats ===")
    print(json.dumps(ni.get_stats(), indent=2))

    ni.save()
    print("\n[NarrativeIntelligence] Test complete.")
