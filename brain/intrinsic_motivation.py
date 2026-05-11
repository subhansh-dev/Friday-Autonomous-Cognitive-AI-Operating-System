#!/usr/bin/env python3
"""
intrinsic_motivation.py — FRIDAY Intrinsic Motivation Engine
==============================================================

Implements intrinsic motivation based on Self-Determination Theory (SDT),
enabling Friday to pursue curiosity-driven exploration, mastery goals,
and autonomous learning without external rewards.

Inspired by:

  [IM-1] Self-Determination Theory (Deci & Ryan, 1985, 2000)
         — Three innate psychological needs drive intrinsic motivation:
           * Autonomy:  feeling of volition and self-direction
           * Competence: feeling of effectiveness and mastery
           * Relatedness: feeling of connection and belonging

  [IM-2] Flow Theory (Csikszentmihalyi, 1990)
         — Optimal experience occurs when challenge matches skill level.
           Too easy → boredom. Too hard → anxiety. The "flow zone" is
           where learning and engagement peak.

  [IM-3] Curiosity-Driven Exploration (Schmidhuber, 2010; Pathak et al., 2017)
         — Agents are motivated by prediction error: things that surprise
           them are worth exploring. Curiosity = information gain.

  [IM-4] Competence-Based Intrinsic Motivation (White, 1959; Harter, 1978)
         — Organisms are motivated to feel effective. Activities that
           build competence are inherently rewarding.

Key behaviors:
  - Novelty detection drives curiosity exploration
  - Difficulty assessment ensures tasks stay in the flow zone
  - Autonomy score tracks self-initiated vs. directed actions
  - Mastery tracking across domains
  - Exploration goal generation from motivational state
"""

import json
import math
import random
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Constants ──────────────────────────────────────────────────────────────

BRAIN_DIR = Path(__file__).resolve().parent
BASE_DIR = BRAIN_DIR.parent
MOTIVATION_FILE = BRAIN_DIR / "motivation_state.json"

# Self-Determination Theory components
AUTONOMY_WEIGHT = 0.35
COMPETENCE_WEIGHT = 0.40
RELATEDNESS_WEIGHT = 0.25

# Flow zone thresholds (challenge-to-skill ratio)
FLOW_ZONE_LOW = 0.8         # below this = too easy (boredom)
FLOW_ZONE_HIGH = 1.4        # above this = too hard (anxiety)
FLOW_ZONE_OPTIMAL = 1.1     # sweet spot

# Novelty
NOVELTY_MEMORY_WINDOW = 200   # recent experiences to check against
NOVELTY_THRESHOLD = 0.3       # above this = novel
SIMILARITY_DECAY = 0.95       # how fast novelty fades with repeated exposure

# Mastery
MASTERY_LEVELS = {
    0: "novice",
    10: "beginner",
    25: "competent",
    50: "proficient",
    100: "expert",
    200: "master",
}
MASTERY_PER_EXPOSURE = 1.0
MASTERY_PER_SUCCESS = 3.0
MASTERY_DECAY_RATE = 0.001     # per day

# Curiosity
CURIOSITY_BASE = 0.5
CURIOSITY_BOOST_NOVELTY = 0.3
CURIOSITY_BOOST_GAP = 0.2      # knowledge gap
CURIOSITY_DECAY_RATE = 0.05    # per hour without exploration

# Persistence
MAX_EXPERIENCE_LOG = 500
MAX_EXPLORATION_HISTORY = 100


# ── Data Classes ───────────────────────────────────────────────────────────

class MotivationDrive:
    """
    Tracks the three SDT motivation drives: autonomy, competence, relatedness.

    Each drive is a float from 0.0 to 1.0 representing how well that
    psychological need is currently being satisfied.
    """

    def __init__(self, autonomy: float = 0.5, competence: float = 0.5,
                 relatedness: float = 0.5):
        self.autonomy = max(0.0, min(1.0, autonomy))
        self.competence = max(0.0, min(1.0, competence))
        self.relatedness = max(0.0, min(1.0, relatedness))
        self._history: List[Dict[str, float]] = []

    def overall(self) -> float:
        """Weighted overall motivation score."""
        return (
            self.autonomy * AUTONOMY_WEIGHT
            + self.competence * COMPETENCE_WEIGHT
            + self.relatedness * RELATEDNESS_WEIGHT
        )

    def snapshot(self) -> Dict[str, float]:
        """Take a snapshot of current drive state."""
        return {
            "autonomy": round(self.autonomy, 3),
            "competence": round(self.competence, 3),
            "relatedness": round(self.relatedness, 3),
            "overall": round(self.overall(), 3),
            "timestamp": datetime.now().isoformat(),
        }

    def to_dict(self) -> dict:
        return {
            "autonomy": self.autonomy,
            "competence": self.competence,
            "relatedness": self.relatedness,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MotivationDrive":
        return cls(
            autonomy=data.get("autonomy", 0.5),
            competence=data.get("competence", 0.5),
            relatedness=data.get("relatedness", 0.5),
        )


# ── Intrinsic Motivation Engine ───────────────────────────────────────────

class IntrinsicMotivation:
    """
    Intrinsic motivation engine based on Self-Determination Theory.

    Tracks autonomy, competence, and relatedness drives. Generates
    curiosity-driven exploration goals and assesses task difficulty
    to maintain flow-state engagement.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data = self._load()

        # Restore state
        self._drive = MotivationDrive.from_dict(
            self._data.get("drive", {})
        )
        self._domain_mastery: Dict[str, float] = (
            self._data.get("domain_mastery", {})
        )
        self._experience_log: List[Dict] = (
            self._data.get("experience_log", [])
        )
        self._exploration_history: List[Dict] = (
            self._data.get("exploration_history", [])
        )
        self._novelty_cache: Dict[str, float] = (
            self._data.get("novelty_cache", {})
        )
        self._curiosity_level: float = (
            self._data.get("curiosity_level", CURIOSITY_BASE)
        )
        self._last_exploration: Optional[str] = (
            self._data.get("last_exploration")
        )

    # ── Persistence ────────────────────────────────────────────────────

    def _load(self) -> dict:
        """Load motivation state from disk."""
        if MOTIVATION_FILE.exists():
            try:
                return json.loads(MOTIVATION_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "meta": {"version": 1},
            "drive": {},
            "domain_mastery": {},
            "experience_log": [],
            "exploration_history": [],
            "novelty_cache": {},
            "curiosity_level": CURIOSITY_BASE,
            "last_exploration": None,
        }

    def _save(self):
        """Persist motivation state to disk."""
        with self._lock:
            self._data["drive"] = self._drive.to_dict()
            self._data["domain_mastery"] = self._domain_mastery
            self._data["experience_log"] = self._experience_log[-MAX_EXPERIENCE_LOG:]
            self._data["exploration_history"] = (
                self._exploration_history[-MAX_EXPLORATION_HISTORY:]
            )
            self._data["novelty_cache"] = self._novelty_cache
            self._data["curiosity_level"] = self._curiosity_level
            self._data["last_exploration"] = self._last_exploration
            self._data["meta"]["last_update"] = datetime.now().isoformat()

        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        MOTIVATION_FILE.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )

    # ── Novelty Assessment ─────────────────────────────────────────────

    def assess_novelty(self, description: str, domain: str = "general") -> float:
        """
        Assess how novel/interesting something is.

        Uses a simple fingerprint-based approach: hash key features and
        compare against recent experience cache. Returns 0.0 (familiar)
        to 1.0 (completely novel).
        """
        # Create a fingerprint from key features
        words = set(description.lower().split())
        key_features = frozenset(
            w for w in words
            if len(w) > 3 and w not in {
                "the", "and", "for", "this", "that", "with", "from",
                "have", "been", "will", "would", "could", "should",
                "your", "they", "their", "about", "which", "when",
            }
        )

        if not key_features:
            return 0.5  # can't determine

        fingerprint = f"{domain}:{':'.join(sorted(key_features))}"

        with self._lock:
            # Check against cached novelty scores
            if fingerprint in self._novelty_cache:
                # Decay novelty with repeated exposure
                current = self._novelty_cache[fingerprint]
                self._novelty_cache[fingerprint] = current * SIMILARITY_DECAY
                return self._novelty_cache[fingerprint]

            # Check recent experiences for partial overlap
            max_overlap = 0.0
            for exp in self._experience_log[-NOVELTY_MEMORY_WINDOW:]:
                exp_words = set(exp.get("description", "").lower().split())
                if exp_words and key_features:
                    overlap = len(key_features & exp_words) / len(key_features)
                    max_overlap = max(max_overlap, overlap)

            novelty = max(0.0, 1.0 - max_overlap)

            # Domain-specific adjustment
            domain_exp = self._domain_mastery.get(domain, 0)
            # Experts find less novelty in their domain
            expertise_damping = max(0.3, 1.0 - domain_exp / 300.0)
            novelty *= expertise_damping

            # Cache
            self._novelty_cache[fingerprint] = novelty
            # Prune cache
            if len(self._novelty_cache) > 1000:
                # Keep most recent 500
                items = sorted(
                    self._novelty_cache.items(),
                    key=lambda x: x[1], reverse=True
                )
                self._novelty_cache = dict(items[:500])

        self._save()
        return round(novelty, 3)

    # ── Difficulty Assessment ───────────────────────────────────────────

    def assess_difficulty(self, task_description: str,
                          domain: str = "general") -> Dict[str, Any]:
        """
        Assess task difficulty relative to current mastery level.

        Returns a dict with difficulty score, flow zone assessment,
        and whether the task is in the optimal challenge range.
        """
        with self._lock:
            mastery = self._domain_mastery.get(domain, 0.0)

        # Simple heuristic difficulty estimation
        # In production, this could use an LLM call
        difficulty_indicators = {
            "easy": ["simple", "basic", "trivial", "routine", "standard"],
            "medium": ["moderate", "typical", "normal", "standard"],
            "hard": ["complex", "advanced", "challenging", "difficult"],
            "expert": ["expert", "novel", "research", "cutting-edge", "unprecedented"],
        }

        desc_lower = task_description.lower()
        difficulty_score = 0.5  # default medium

        for level, keywords in difficulty_indicators.items():
            for kw in keywords:
                if kw in desc_lower:
                    if level == "easy":
                        difficulty_score = 0.2
                    elif level == "medium":
                        difficulty_score = 0.5
                    elif level == "hard":
                        difficulty_score = 0.8
                    elif level == "expert":
                        difficulty_score = 1.0
                    break

        # Normalize mastery to 0-1 scale (cap at 200 for "master")
        normalized_mastery = min(1.0, mastery / 200.0)

        # Challenge-to-skill ratio
        if normalized_mastery > 0:
            ratio = difficulty_score / normalized_mastery
        else:
            ratio = difficulty_score * 2  # everything is hard for a novice

        # Flow zone assessment
        if ratio < FLOW_ZONE_LOW:
            zone = "boredom"
            in_flow = False
        elif ratio > FLOW_ZONE_HIGH:
            zone = "anxiety"
            in_flow = False
        else:
            zone = "flow"
            in_flow = True

        # Distance from optimal
        distance = abs(ratio - FLOW_ZONE_OPTIMAL)

        return {
            "difficulty": round(difficulty_score, 3),
            "mastery": round(normalized_mastery, 3),
            "challenge_skill_ratio": round(ratio, 3),
            "zone": zone,
            "in_flow_zone": in_flow,
            "distance_from_optimal": round(distance, 3),
            "recommendation": self._flow_recommendation(zone, ratio),
        }

    def _flow_recommendation(self, zone: str, ratio: float) -> str:
        """Generate a recommendation based on flow zone assessment."""
        if zone == "boredom":
            return ("Task may be too easy. Consider adding constraints, "
                    "time pressure, or pursuing a harder variant.")
        elif zone == "anxiety":
            return ("Task may be too hard. Consider breaking it into smaller "
                    "subtasks, seeking help, or building prerequisite skills first.")
        else:
            return ("Task is in the optimal flow zone. Proceed with full engagement.")

    # ── Mastery Tracking ───────────────────────────────────────────────

    def record_experience(self, domain: str, description: str,
                          success: bool = True, time_spent: float = 0.0):
        """Record an experience and update mastery."""
        with self._lock:
            # Update domain mastery
            current = self._domain_mastery.get(domain, 0.0)
            if success:
                current += MASTERY_PER_SUCCESS
            else:
                current += MASTERY_PER_EXPOSURE * 0.5  # learn from failures too
            self._domain_mastery[domain] = current

            # Log experience
            entry = {
                "domain": domain,
                "description": description[:500],
                "success": success,
                "time_spent": time_spent,
                "timestamp": datetime.now().isoformat(),
                "mastery_after": current,
            }
            self._experience_log.append(entry)

            # Update competence drive based on mastery
            avg_mastery = (
                sum(self._domain_mastery.values()) / len(self._domain_mastery)
                if self._domain_mastery else 0.0
            )
            self._drive.competence = min(1.0, avg_mastery / 100.0)

            # Update autonomy drive (self-initiated actions boost it)
            self._drive.autonomy = min(1.0, self._drive.autonomy + 0.01)

        self._save()

    def get_mastery_level(self, domain: str) -> str:
        """Get the mastery level name for a domain."""
        with self._lock:
            mastery = self._domain_mastery.get(domain, 0)

        level_name = "novice"
        for threshold, name in sorted(MASTERY_LEVELS.items()):
            if mastery >= threshold:
                level_name = name
        return level_name

    def get_domain_mastery(self) -> Dict[str, Dict[str, Any]]:
        """Get mastery details for all domains."""
        with self._lock:
            result = {}
            for domain, mastery in self._domain_mastery.items():
                level = "novice"
                for threshold, name in sorted(MASTERY_LEVELS.items()):
                    if mastery >= threshold:
                        level = name
                result[domain] = {
                    "score": round(mastery, 1),
                    "level": level,
                    "next_level_at": self._next_level_threshold(mastery),
                }
            return result

    def _next_level_threshold(self, current: float) -> Optional[int]:
        """Get the threshold for the next mastery level."""
        for threshold in sorted(MASTERY_LEVELS.keys()):
            if threshold > current:
                return threshold
        return None

    # ── Curiosity & Exploration ────────────────────────────────────────

    def get_curiosity_level(self) -> float:
        """Get current curiosity level, decaying over time."""
        with self._lock:
            if self._last_exploration:
                try:
                    last = datetime.fromisoformat(self._last_exploration)
                    hours_since = (datetime.now() - last).total_seconds() / 3600
                    decay = CURIOSITY_DECAY_RATE * hours_since
                    self._curiosity_level = max(
                        CURIOSITY_BASE,
                        self._curiosity_level - decay
                    )
                except (ValueError, TypeError):
                    pass
            return round(self._curiosity_level, 3)

    def boost_curiosity(self, amount: float = 0.1):
        """Boost curiosity level (e.g., after encountering something novel)."""
        with self._lock:
            self._curiosity_level = min(1.0, self._curiosity_level + amount)
        self._save()

    def generate_exploration_goals(self, current_domains: Optional[List[str]] = None,
                                   count: int = 3) -> List[Dict[str, Any]]:
        """
        Generate exploration goals based on motivational state.

        Prioritizes:
          1. Knowledge gaps (low mastery domains)
          2. Novel domains not yet explored
          3. Domains where curiosity is highest
        """
        goals = []
        with self._lock:
            all_domains = set(self._domain_mastery.keys())
            if current_domains:
                all_domains.update(current_domains)

            # Add some default domains if we have few
            if len(all_domains) < 5:
                default_domains = [
                    "algorithms", "systems_design", "security",
                    "data_science", "web_development", "devops",
                    "machine_learning", "databases", "networking",
                    "mobile_development", "cloud_computing", "ui_ux",
                ]
                all_domains.update(default_domains)

            # Sort by mastery (lowest first = biggest knowledge gaps)
            domain_scores = []
            for domain in all_domains:
                mastery = self._domain_mastery.get(domain, 0.0)
                novelty = self._novelty_cache.get(f"{domain}:", 0.5)
                # Prioritize low mastery + high novelty
                priority = (1.0 - min(1.0, mastery / 100.0)) * 0.6 + novelty * 0.4
                domain_scores.append((priority, domain, mastery))

            domain_scores.sort(reverse=True)

            for priority, domain, mastery in domain_scores[:count]:
                level = "novice"
                for threshold, name in sorted(MASTERY_LEVELS.items()):
                    if mastery >= threshold:
                        level = name

                goals.append({
                    "domain": domain,
                    "current_mastery": round(mastery, 1),
                    "current_level": level,
                    "exploration_priority": round(priority, 3),
                    "suggested_focus": self._suggest_focus(domain, mastery),
                    "estimated_flow_challenge": round(
                        min(1.0, FLOW_ZONE_OPTIMAL * (mastery / 100.0 + 0.1)), 2
                    ),
                })

        # Log exploration generation
        with self._lock:
            self._exploration_history.append({
                "timestamp": datetime.now().isoformat(),
                "goals_generated": len(goals),
                "curiosity_level": self._curiosity_level,
            })
            self._last_exploration = datetime.now().isoformat()
            # Curiosity satisfied by generating goals
            self._curiosity_level = max(
                CURIOSITY_BASE, self._curiosity_level - 0.05
            )

        self._save()
        return goals

    def _suggest_focus(self, domain: str, mastery: float) -> str:
        """Suggest what to focus on in a domain."""
        if mastery < 10:
            return f"Learn fundamentals of {domain}"
        elif mastery < 50:
            return f"Practice core {domain} skills with real projects"
        elif mastery < 100:
            return f"Deep dive into advanced {domain} topics"
        else:
            return f"Explore cutting-edge {domain} research and contribute"

    # ── Motivation State ───────────────────────────────────────────────

    def get_motivation_state(self) -> Dict[str, Any]:
        """Get the complete motivation state."""
        with self._lock:
            curiosity = self.get_curiosity_level()
            return {
                "drives": {
                    "autonomy": round(self._drive.autonomy, 3),
                    "competence": round(self._drive.competence, 3),
                    "relatedness": round(self._drive.relatedness, 3),
                    "overall": round(self._drive.overall(), 3),
                },
                "curiosity_level": curiosity,
                "domains_tracked": len(self._domain_mastery),
                "total_experiences": len(self._experience_log),
                "exploration_sessions": len(self._exploration_history),
                "top_domains": self._top_domains(5),
                "motivation_status": self._motivation_status(),
            }

    def _top_domains(self, n: int = 5) -> List[Dict[str, Any]]:
        """Get top N domains by mastery."""
        sorted_domains = sorted(
            self._domain_mastery.items(),
            key=lambda x: x[1],
            reverse=True
        )[:n]
        return [
            {
                "domain": d,
                "mastery": round(m, 1),
                "level": self.get_mastery_level(d),
            }
            for d, m in sorted_domains
        ]

    def _motivation_status(self) -> str:
        """Get a human-readable motivation status."""
        overall = self._drive.overall()
        curiosity = self._curiosity_level

        if overall > 0.8 and curiosity > 0.7:
            return "highly_motivated"
        elif overall > 0.6:
            return "motivated"
        elif overall > 0.4:
            return "moderate"
        elif overall > 0.2:
            return "low"
        else:
            return "demotivated"

    def update_drive(self, autonomy_delta: float = 0.0,
                     competence_delta: float = 0.0,
                     relatedness_delta: float = 0.0):
        """Directly update motivation drives."""
        with self._lock:
            self._drive.autonomy = max(0.0, min(1.0,
                self._drive.autonomy + autonomy_delta))
            self._drive.competence = max(0.0, min(1.0,
                self._drive.competence + competence_delta))
            self._drive.relatedness = max(0.0, min(1.0,
                self._drive.relatedness + relatedness_delta))
        self._save()

    # ── Formatting ─────────────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """Format motivation state for system prompt injection."""
        state = self.get_motivation_state()
        drives = state["drives"]

        parts = ["## Motivation State"]
        parts.append(f"- Overall motivation: {drives['overall']:.0%} "
                     f"({state['motivation_status']})")
        parts.append(f"- Autonomy: {drives['autonomy']:.0%} | "
                     f"Competence: {drives['competence']:.0%} | "
                     f"Relatedness: {drives['relatedness']:.0%}")
        parts.append(f"- Curiosity level: {state['curiosity_level']:.0%}")
        parts.append(f"- Domains tracked: {state['domains_tracked']}")
        parts.append(f"- Total experiences: {state['total_experiences']}")

        if state["top_domains"]:
            parts.append("- Top domains:")
            for d in state["top_domains"]:
                parts.append(f"  • {d['domain']}: {d['level']} ({d['mastery']:.0f})")

        result = "\n".join(parts)
        return result[:max_chars] if len(result) > max_chars else result

    def get_stats(self) -> dict:
        """Get motivation engine statistics."""
        state = self.get_motivation_state()
        return {
            "overall_motivation": state["drives"]["overall"],
            "curiosity": state["curiosity_level"],
            "domains": state["domains_tracked"],
            "experiences": state["total_experiences"],
            "status": state["motivation_status"],
        }


# ── Singleton ─────────────────────────────────────────────────────────────

_intrinsic_motivation_instance = None
_intrinsic_motivation_lock = threading.Lock()


def get_intrinsic_motivation() -> IntrinsicMotivation:
    """Get singleton IntrinsicMotivation instance."""
    global _intrinsic_motivation_instance
    if _intrinsic_motivation_instance is None:
        with _intrinsic_motivation_lock:
            if _intrinsic_motivation_instance is None:
                _intrinsic_motivation_instance = IntrinsicMotivation()
    return _intrinsic_motivation_instance
