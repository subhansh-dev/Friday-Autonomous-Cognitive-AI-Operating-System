"""
brain/transfer_learning.py — Transfer Learning System for FRIDAY

Enables learning in domain A and applying that knowledge in domain B.
Distills domain-independent abstract skills from specific experiences,
matches them to new contexts, and tracks transfer success rates.

Integrates with brain.learning, brain.procedural_memory, and
brain.analogy_engine (when available).
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ─── Constants ───────────────────────────────────────────────────────────────

DATA_FILE = Path(__file__).parent / "transfer_data.json"
BACKUP_SUFFIX = ".backup"

# Domain-specific stopwords stripped during abstraction.
# These words are too concrete to survive domain transfer.
_DOMAIN_STOPWORDS = {
    "coding": {"python", "javascript", "function", "variable", "class", "module",
               "import", "compile", "runtime", "syntax", "bug", "code", "script",
               "npm", "pip", "git", "commit", "repo", "branch", "merge"},
    "security": {"vulnerability", "cve", "cvss", "exploit", "penetration", "firewall",
                 "malware", "trojan", "phishing", "encryption", "hash", "token",
                 "oauth", "jwt", "ssl", "tls", "xss", "sqli", "injection"},
    "communication": {"email", "message", "chat", "reply", "draft", "tone",
                      "greeting", "signature", "subject", "inbox", "notification"},
    "research": {"paper", "hypothesis", "experiment", "dataset", "model", "training",
                 "accuracy", "benchmark", "citation", "abstract", "journal", "peer"},
    "system": {"server", "container", "docker", "kubernetes", "process", "daemon",
               "memory", "cpu", "disk", "network", "port", "socket", "logs", "syslog"},
    "writing": {"essay", "paragraph", "thesis", "draft", "edit", "proofread",
                "narrative", "tone", "voice", "audience", "publish"},
    "data": {"csv", "json", "database", "query", "table", "row", "column",
             "pandas", "sql", "schema", "index", "migration"},
}

# Relation words that survive abstraction — they encode *structure*.
_RELATION_WORDS = {
    "if", "then", "else", "before", "after", "during", "because", "so",
    "and", "or", "not", "but", "while", "when", "where", "how", "why",
    "first", "next", "finally", "always", "never", "sometimes",
    "check", "validate", "verify", "ensure", "retry", "fallback",
    "repeat", "loop", "break", "skip", "aggregate", "split", "merge",
    "filter", "transform", "map", "reduce", "compare", "match",
    "optimize", "minimize", "maximize", "prioritize", "sequence",
    "parallel", "sequential", "incremental", "batch", "stream",
}


# ─── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class AbstractSkill:
    """A domain-independent strategy extracted from specific learnings."""
    name: str
    pattern: str                          # abstract description of the strategy
    preconditions: List[str]              # when this skill applies
    steps: List[str]                      # abstract step sequence
    source_domain: str                    # where it was learned
    success_rate: float = 1.0             # how well it works (0-1)
    transfer_count: int = 0              # times successfully transferred
    total_transfers: int = 0             # total transfer attempts
    created_at: str = ""
    skill_id: str = ""
    keywords: List[str] = field(default_factory=list)  # abstracted keywords

    def __post_init__(self):
        if not self.skill_id:
            self.skill_id = f"skill_{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = _now_iso()

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "pattern": self.pattern,
            "preconditions": self.preconditions,
            "steps": self.steps,
            "source_domain": self.source_domain,
            "success_rate": self.success_rate,
            "transfer_count": self.transfer_count,
            "total_transfers": self.total_transfers,
            "created_at": self.created_at,
            "keywords": self.keywords,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AbstractSkill":
        return cls(
            skill_id=d.get("skill_id", ""),
            name=d.get("name", ""),
            pattern=d.get("pattern", ""),
            preconditions=d.get("preconditions", []),
            steps=d.get("steps", []),
            source_domain=d.get("source_domain", "unknown"),
            success_rate=d.get("success_rate", 1.0),
            transfer_count=d.get("transfer_count", 0),
            total_transfers=d.get("total_transfers", 0),
            created_at=d.get("created_at", ""),
            keywords=d.get("keywords", []),
        )


@dataclass
class TransferRecord:
    """Record of a single transfer attempt."""
    skill_id: str
    source_domain: str
    target_domain: str
    success: bool
    timestamp: str = ""
    details: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = _now_iso()

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "source_domain": self.source_domain,
            "target_domain": self.target_domain,
            "success": self.success,
            "timestamp": self.timestamp,
            "details": self.details,
        }


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z_]{3,}", text.lower())


def _abstract_keywords(text: str, domain: str = "") -> List[str]:
    """Remove domain-specific stopwords, keep relational / structural words."""
    tokens = _tokenize(text)
    domain_sw = _DOMAIN_STOPWORDS.get(domain, set())
    all_sw = domain_sw | {w for d, words in _DOMAIN_STOPWORDS.items()
                          if d != domain for w in words}
    kept = [t for t in tokens if t not in all_sw or t in _RELATION_WORDS]
    # Deduplicate while preserving order
    seen = set()
    result = []
    for w in kept:
        if w not in seen:
            seen.add(w)
            result.append(w)
    return result


def _keyword_similarity(a: List[str], b: List[str]) -> float:
    """Jaccard-like overlap between two keyword lists."""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    inter = sa & sb
    union = sa | sb
    return len(inter) / len(union) if union else 0.0


# ─── Domain Classifier ──────────────────────────────────────────────────────

class DomainClassifier:
    """Categorize experiences into domains."""

    # Keyword → domain mapping, ordered by specificity
    _DOMAIN_SIGNALS: Dict[str, List[str]] = {
        "coding": ["function", "class", "import", "variable", "compile", "runtime",
                    "bug", "syntax", "script", "module", "api", "endpoint", "code",
                    "python", "javascript", "typescript", "rust", "java", "git",
                    "commit", "merge", "refactor", "debug", "test", "unittest"],
        "security": ["vulnerability", "exploit", "cve", "cvss", "malware", "attack",
                     "firewall", "encryption", "auth", "token", "injection", "xss",
                     "csrf", "penetration", "audit", "threat", "risk", "compliance",
                     "scan", "hardening", "privilege", "escalation"],
        "communication": ["email", "message", "reply", "chat", "tone", "audience",
                          "greeting", "draft", "notification", "slack", "discord",
                          "meeting", "presentation", "feedback", "conversation"],
        "research": ["paper", "hypothesis", "experiment", "dataset", "model",
                     "training", "accuracy", "benchmark", "citation", "abstract",
                     "analysis", "statistics", "correlation", "regression"],
        "system": ["server", "docker", "container", "process", "daemon", "memory",
                   "cpu", "disk", "network", "port", "socket", "logs", "deploy",
                   "infrastructure", "monitoring", "cron", "systemd", "nginx"],
        "writing": ["essay", "paragraph", "narrative", "story", "tone", "voice",
                    "proofread", "edit", "draft", "publish", "blog", "article",
                    "copywriting", "content"],
        "data": ["csv", "json", "database", "query", "table", "schema", "pandas",
                 "sql", "migration", "etl", "pipeline", "warehouse", "analytics"],
    }

    @classmethod
    def classify(cls, text: str) -> str:
        """Classify text into the most likely domain."""
        tokens = set(_tokenize(text))
        scores: Dict[str, int] = defaultdict(int)
        for domain, signals in cls._DOMAIN_SIGNALS.items():
            for sig in signals:
                if sig in tokens:
                    scores[domain] += 1
        if not scores:
            return "general"
        return max(scores, key=scores.get)

    @classmethod
    def classify_multi(cls, text: str, threshold: float = 0.5) -> List[str]:
        """Return all domains above threshold (0-1 normalized)."""
        tokens = set(_tokenize(text))
        scores: Dict[str, int] = defaultdict(int)
        for domain, signals in cls._DOMAIN_SIGNALS.items():
            for sig in signals:
                if sig in tokens:
                    scores[domain] += 1
        if not scores:
            return ["general"]
        max_score = max(scores.values()) or 1
        return [d for d, s in scores.items() if s / max_score >= threshold]


# ─── Transfer Learning Engine ───────────────────────────────────────────────

class TransferLearningEngine:
    """
    Core engine for cross-domain transfer learning.

    Distills abstract skills from domain experiences, matches them to new
    contexts, and tracks what transfers well.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._skills: Dict[str, AbstractSkill] = {}
        self._transfer_log: List[TransferRecord] = []
        self._domain_graph: Dict[str, Dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )  # source → target → success_rate
        self._load()
        print(f"[TransferLearning] Initialized ({len(self._skills)} skills, "
              f"{len(self._transfer_log)} transfer records)")

    # ── Persistence ──────────────────────────────────────────────────────

    def _load(self):
        if not DATA_FILE.exists():
            return
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            for s in data.get("skills", []):
                skill = AbstractSkill.from_dict(s)
                self._skills[skill.skill_id] = skill
            for r in data.get("transfer_log", []):
                self._transfer_log.append(TransferRecord(**r))
            for src, targets in data.get("domain_graph", {}).items():
                for tgt, rate in targets.items():
                    self._domain_graph[src][tgt] = rate
        except (json.JSONDecodeError, TypeError) as exc:
            print(f"[TransferLearning] Corrupted data file, starting fresh: {exc}")

    def _save(self):
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "skills": [s.to_dict() for s in self._skills.values()],
            "transfer_log": [r.to_dict() for r in self._transfer_log[-500:]],
            "domain_graph": {s: dict(t) for s, t in self._domain_graph.items()},
        }
        try:
            DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
        except Exception as exc:
            print(f"[TransferLearning] Save failed: {exc}")

    # ── Core: Extract Abstract Skill ─────────────────────────────────────

    def extract_abstract_skill(self, domain_experience: dict) -> Optional[AbstractSkill]:
        """
        Distill a domain-independent strategy from a specific experience.

        Args:
            domain_experience: dict with keys like:
                - description: what was done
                - goal: what was trying to be achieved
                - steps: list of step descriptions
                - domain: (optional) domain tag
                - success: whether it worked
                - context: (optional) additional context

        Returns:
            AbstractSkill if extraction succeeded, None otherwise.
        """
        description = domain_experience.get("description", "")
        goal = domain_experience.get("goal", "")
        steps = domain_experience.get("steps", [])
        domain = domain_experience.get("domain", DomainClassifier.classify(description))

        if not description and not goal:
            return None

        # Abstract the goal into a pattern
        pattern_kw = _abstract_keywords(f"{goal} {description}", domain)
        if len(pattern_kw) < 2:
            pattern_kw = _abstract_keywords(goal, "")  # fallback: no domain filter

        pattern = " ".join(pattern_kw[:12]) if pattern_kw else goal[:80]

        # Abstract preconditions from context
        context = domain_experience.get("context", {})
        preconditions = []
        if isinstance(context, dict):
            for k, v in context.items():
                abs_kw = _abstract_keywords(f"{k} {v}", domain)
                if abs_kw:
                    preconditions.append(" ".join(abs_kw[:6]))
        elif isinstance(context, str):
            abs_kw = _abstract_keywords(context, domain)
            if abs_kw:
                preconditions.append(" ".join(abs_kw[:8]))

        if not preconditions:
            preconditions.append(f"when goal matches: {pattern}")

        # Abstract steps: strip domain jargon, keep relational structure
        abstract_steps = []
        for step in steps:
            if isinstance(step, dict):
                step_text = step.get("description", step.get("action", str(step)))
            else:
                step_text = str(step)
            abs_kw = _abstract_keywords(step_text, domain)
            abstract_steps.append(" ".join(abs_kw[:10]) if abs_kw else step_text[:60])

        if not abstract_steps:
            abstract_steps = ["assess situation", "select strategy", "execute", "verify"]

        skill = AbstractSkill(
            name=f"transfer_{domain}_{uuid.uuid4().hex[:6]}",
            pattern=pattern,
            preconditions=preconditions,
            steps=abstract_steps,
            source_domain=domain,
            keywords=pattern_kw,
        )

        with self._lock:
            self._skills[skill.skill_id] = skill
            self._save()

        print(f"[TransferLearning] Extracted skill '{skill.skill_id}' from "
              f"domain '{domain}': {pattern[:60]}...")

        # Auto-check cross-domain applicability
        self._check_cross_domain_applicability(skill)

        return skill

    # ── Core: Find Transferable Skills ───────────────────────────────────

    def find_transferable_skills(self, target_domain: str,
                                  context: str = "",
                                  top_k: int = 5) -> List[Tuple[AbstractSkill, float]]:
        """
        Match abstract skills to a target domain.

        Returns list of (skill, relevance_score) sorted by relevance.
        """
        target_kw = _abstract_keywords(context, target_domain) if context else []

        with self._lock:
            candidates = []
            for skill in self._skills.values():
                if skill.source_domain == target_domain:
                    continue  # same domain, not a transfer

                # Precondition overlap
                precond_text = " ".join(skill.preconditions)
                precond_kw = _abstract_keywords(precond_text, skill.source_domain)
                precond_sim = _keyword_similarity(precond_kw, target_kw) if target_kw else 0.3

                # Keyword similarity
                kw_sim = _keyword_similarity(skill.keywords, target_kw) if target_kw else 0.0

                # Domain graph bonus: has this source→target worked before?
                graph_bonus = self._domain_graph.get(skill.source_domain, {}).get(
                    target_domain, 0.0) * 0.3

                # Success rate weight
                sr_weight = skill.success_rate * 0.2

                # Composite score
                score = (precond_sim * 0.4 + kw_sim * 0.3 + graph_bonus + sr_weight)
                score = min(score, 1.0)

                if score > 0.05:
                    candidates.append((skill, round(score, 4)))

            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[:top_k]

    # ── Core: Apply Transfer ─────────────────────────────────────────────

    def apply_transfer(self, skill: AbstractSkill,
                       target_context: dict) -> dict:
        """
        Adapt a skill to a new domain, mapping abstract steps to concrete actions.

        Args:
            skill: the abstract skill to transfer
            target_context: dict with keys:
                - domain: target domain name
                - goal: concrete goal in target domain
                - available_tools: list of tool names (optional)
                - constraints: list of constraints (optional)

        Returns:
            dict with:
                - adapted_steps: concrete steps for the target domain
                - mapping: abstract→concrete term mapping
                - confidence: transfer confidence (0-1)
        """
        target_domain = target_context.get("domain", "general")
        target_goal = target_context.get("goal", "")
        available_tools = target_context.get("available_tools", [])
        constraints = target_context.get("constraints", [])

        # Build a mapping from abstract terms to target-domain terms
        target_kw = _abstract_keywords(target_goal, target_domain)
        abstract_kw = skill.keywords

        # Simple mapping: find overlap and extend with domain vocabulary
        mapping: Dict[str, str] = {}
        for ak in abstract_kw:
            # Check if any target keyword is semantically close
            for tk in target_kw:
                if ak == tk or (len(ak) > 3 and len(tk) > 3 and
                                (ak.startswith(tk[:4]) or tk.startswith(ak[:4]))):
                    mapping[ak] = tk
                    break
            if ak not in mapping:
                mapping[ak] = ak  # keep as-is if no match

        # Adapt steps to target domain
        adapted_steps = []
        for step in skill.steps:
            adapted = step
            for abs_term, concrete_term in mapping.items():
                adapted = adapted.replace(abs_term, concrete_term)
            # Add domain prefix if step is too generic
            if len(adapted.split()) < 3:
                adapted = f"{target_domain}: {adapted}"
            adapted_steps.append(adapted)

        # Confidence based on keyword overlap and historical success
        kw_overlap = _keyword_similarity(abstract_kw, target_kw)
        historical = self._domain_graph.get(skill.source_domain, {}).get(
            target_domain, 0.5)
        confidence = round(kw_overlap * 0.6 + historical * 0.3 + skill.success_rate * 0.1, 3)
        confidence = max(0.1, min(confidence, 0.95))

        # Record the attempt
        with self._lock:
            skill.total_transfers += 1

        result = {
            "skill_id": skill.skill_id,
            "adapted_steps": adapted_steps,
            "mapping": mapping,
            "confidence": confidence,
            "source_domain": skill.source_domain,
            "target_domain": target_domain,
            "constraints": constraints,
        }

        print(f"[TransferLearning] Applied '{skill.skill_id}' "
              f"({skill.source_domain} → {target_domain}), confidence={confidence}")

        return result

    # ── Core: Record Transfer Outcome ────────────────────────────────────

    def record_transfer_outcome(self, skill_id: str, target_domain: str,
                                 success: bool, details: str = ""):
        """Track whether a transfer succeeded or failed."""
        with self._lock:
            skill = self._skills.get(skill_id)
            if not skill:
                print(f"[TransferLearning] Unknown skill: {skill_id}")
                return

            if success:
                skill.transfer_count += 1

            # Update success rate (exponential moving average)
            alpha = 0.3
            skill.success_rate = (
                alpha * (1.0 if success else 0.0) +
                (1 - alpha) * skill.success_rate
            )

            # Update domain graph
            src = skill.source_domain
            tgt = target_domain
            old_rate = self._domain_graph[src][tgt]
            n = sum(1 for r in self._transfer_log
                    if r.source_domain == src and r.target_domain == tgt)
            self._domain_graph[src][tgt] = (
                (old_rate * n + (1.0 if success else 0.0)) / (n + 1)
            )

            record = TransferRecord(
                skill_id=skill_id,
                source_domain=src,
                target_domain=tgt,
                success=success,
                details=details,
            )
            self._transfer_log.append(record)
            self._save()

        status = "✓" if success else "✗"
        print(f"[TransferLearning] {status} Transfer {skill_id} → {target_domain} "
              f"(rate: {skill.success_rate:.2f})")

        # If successful, create a procedure in procedural memory
        if success:
            self._promote_to_procedure(skill, target_domain)

    # ── Curriculum Learning ──────────────────────────────────────────────

    def curriculum_learning(self, skill_type: str = "") -> List[dict]:
        """
        Sequence learning tasks for maximum transfer: easy→hard, similar→dissimilar.

        Returns a curriculum (ordered list of task dicts).
        """
        with self._lock:
            skills = list(self._skills.values())

        if skill_type:
            skills = [s for s in skills if skill_type in s.name or
                      skill_type in s.pattern]

        if not skills:
            return []

        # Sort by: source domain diversity, then by success rate (easy first)
        domain_groups: Dict[str, List[AbstractSkill]] = defaultdict(list)
        for s in skills:
            domain_groups[s.source_domain].append(s)

        curriculum = []
        # Phase 1: Easy (high success rate, well-understood skills)
        easy = sorted(skills, key=lambda s: s.success_rate, reverse=True)
        for s in easy[:5]:
            curriculum.append({
                "phase": "foundation",
                "skill_id": s.skill_id,
                "name": s.name,
                "domain": s.source_domain,
                "difficulty": "easy",
                "success_rate": s.success_rate,
                "reason": "High success rate — build confidence",
            })

        # Phase 2: Medium (moderate success, cross-domain targets)
        for src, tgt_pairs in self._domain_graph.items():
            for tgt, rate in sorted(tgt_pairs.items(), key=lambda x: x[1], reverse=True):
                if 0.3 <= rate <= 0.7:
                    curriculum.append({
                        "phase": "transfer",
                        "source_domain": src,
                        "target_domain": tgt,
                        "difficulty": "medium",
                        "historical_rate": rate,
                        "reason": f"Moderate transfer ({src}→{tgt}), room to improve",
                    })

        # Phase 3: Hard (low success or unexplored domain pairs)
        all_domains = set(d for s in skills for d in [s.source_domain])
        for src in all_domains:
            for tgt in all_domains:
                if src == tgt:
                    continue
                rate = self._domain_graph.get(src, {}).get(tgt, None)
                if rate is None or rate < 0.3:
                    curriculum.append({
                        "phase": "challenge",
                        "source_domain": src,
                        "target_domain": tgt,
                        "difficulty": "hard",
                        "historical_rate": rate or 0.0,
                        "reason": "Unexplored or difficult transfer path",
                    })

        print(f"[TransferLearning] Generated curriculum with {len(curriculum)} tasks")
        return curriculum

    # ── Cross-Domain Pattern Detection ───────────────────────────────────

    def _check_cross_domain_applicability(self, skill: AbstractSkill):
        """When a skill is learned, check if it applies to other domains."""
        all_domains = set(_DOMAIN_STOPWORDS.keys()) | {"general"}
        candidates = [d for d in all_domains if d != skill.source_domain]

        for target in candidates:
            # Use keyword overlap as a proxy for applicability
            target_vocab = _DOMAIN_STOPWORDS.get(target, set())
            overlap = set(skill.keywords) & target_vocab
            # If the abstract skill has *few* domain-specific remnants,
            # it's likely transferable
            domain_specific = set(skill.keywords) & _DOMAIN_STOPWORDS.get(
                skill.source_domain, set())
            abstraction_ratio = 1.0 - (len(domain_specific) / max(len(skill.keywords), 1))

            if abstraction_ratio > 0.6:
                print(f"[TransferLearning] Skill '{skill.skill_id}' may transfer "
                      f"to '{target}' (abstraction: {abstraction_ratio:.0%})")

    def detect_cross_domain_patterns(self) -> List[dict]:
        """
        Analyze all transfer logs to find cross-domain patterns.

        Returns list of patterns like:
        - "skills from coding transfer well to system (80%)"
        - "security skills rarely transfer to writing (10%)"
        """
        with self._lock:
            patterns = []
            for src, targets in self._domain_graph.items():
                for tgt, rate in targets.items():
                    count = sum(1 for r in self._transfer_log
                                if r.source_domain == src and r.target_domain == tgt)
                    if count < 2:
                        continue
                    if rate >= 0.6:
                        patterns.append({
                            "type": "strong_transfer",
                            "source": src,
                            "target": tgt,
                            "rate": round(rate, 2),
                            "count": count,
                            "insight": f"{src} skills transfer well to {tgt}",
                        })
                    elif rate <= 0.2:
                        patterns.append({
                            "type": "weak_transfer",
                            "source": src,
                            "target": tgt,
                            "rate": round(rate, 2),
                            "count": count,
                            "insight": f"{src} skills rarely transfer to {tgt}",
                        })

            patterns.sort(key=lambda p: p["rate"], reverse=True)
            return patterns

    # ── Integration: Promote to Procedural Memory ────────────────────────

    def _promote_to_procedure(self, skill: AbstractSkill, target_domain: str):
        """When a transfer succeeds, create a procedure in procedural memory."""
        try:
            from brain.procedural_memory import get_procedural_memory
            pm = get_procedural_memory()
            steps = [{"tool": "transfer", "description": step,
                       "params_pattern": {"domain": target_domain}}
                      for step in skill.steps]
            proc_id = pm.learn_procedure(
                goal=f"[transfer:{skill.source_domain}→{target_domain}] {skill.pattern}",
                steps=steps,
                context={"transfer_skill_id": skill.skill_id,
                          "source_domain": skill.source_domain,
                          "target_domain": target_domain},
            )
            if proc_id:
                print(f"[TransferLearning] Promoted skill '{skill.skill_id}' "
                      f"to procedure '{proc_id}'")
        except ImportError:
            pass  # procedural_memory not available
        except Exception as exc:
            print(f"[TransferLearning] Procedure promotion failed: {exc}")

    # ── Integration: Hook into Learning Engine ───────────────────────────

    def on_lesson_learned(self, lesson: dict):
        """
        Hook: called when brain.learning extracts a new lesson.
        Auto-checks for cross-domain transferability.
        """
        domain = lesson.get("domain", DomainClassifier.classify(
            json.dumps(lesson, default=str)))
        description = lesson.get("description", lesson.get("insight", ""))

        if not description:
            return

        experience = {
            "description": description,
            "goal": lesson.get("recommendation", description),
            "steps": lesson.get("steps", [description]),
            "domain": domain,
            "context": lesson.get("context", {}),
            "success": lesson.get("success", True),
        }
        self.extract_abstract_skill(experience)

    # ── Integration: Analogy Engine ──────────────────────────────────────

    def _try_analogical_mapping(self, skill: AbstractSkill,
                                 target_domain: str) -> Optional[dict]:
        """Use analogy_engine for richer cross-domain mapping if available."""
        try:
            from brain.analogy_engine import AnalogyEngine  # type: ignore
            engine = AnalogyEngine()
            source_desc = f"{skill.pattern}: {' → '.join(skill.steps)}"
            mapping = engine.find_analogy(
                source=source_desc,
                source_domain=skill.source_domain,
                target_domain=target_domain,
            )
            return mapping
        except (ImportError, AttributeError):
            return None
        except Exception as exc:
            print(f"[TransferLearning] Analogy mapping failed: {exc}")
            return None

    # ── Stats & Formatting ───────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return transfer learning statistics."""
        with self._lock:
            total_skills = len(self._skills)
            total_transfers = len(self._transfer_log)
            successful = sum(1 for r in self._transfer_log if r.success)
            domains = set(s.source_domain for s in self._skills.values())

            # Top transfer paths
            paths = []
            for src, targets in self._domain_graph.items():
                for tgt, rate in targets.items():
                    cnt = sum(1 for r in self._transfer_log
                              if r.source_domain == src and r.target_domain == tgt)
                    paths.append({
                        "source": src, "target": tgt,
                        "rate": round(rate, 2), "count": cnt,
                    })
            paths.sort(key=lambda p: p["rate"], reverse=True)

            # Most transferable skills
            top_skills = sorted(self._skills.values(),
                                key=lambda s: s.transfer_count, reverse=True)[:5]

            return {
                "total_skills": total_skills,
                "total_transfer_attempts": total_transfers,
                "successful_transfers": successful,
                "overall_success_rate": round(successful / max(total_transfers, 1), 3),
                "domains_covered": sorted(domains),
                "top_transfer_paths": paths[:10],
                "most_transferred_skills": [
                    {"id": s.skill_id, "name": s.name,
                     "transfers": s.transfer_count, "rate": round(s.success_rate, 2)}
                    for s in top_skills
                ],
            }

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """Format transfer learning insights for system prompt injection."""
        stats = self.get_stats()
        if stats["total_skills"] == 0:
            return ""

        parts = [
            "[TRANSFER LEARNING — Cross-domain skill library]",
            f"Skills: {stats['total_skills']} | "
            f"Transfers: {stats['successful_transfers']}/{stats['total_transfer_attempts']} "
            f"({stats['overall_success_rate']:.0%})",
        ]

        # Top transfer paths
        if stats["top_transfer_paths"]:
            parts.append("Best transfer paths:")
            for p in stats["top_transfer_paths"][:3]:
                parts.append(f"  {p['source']} → {p['target']}: "
                             f"{p['rate']:.0%} ({p['count']} attempts)")

        # Top skills
        if stats["most_transferred_skills"]:
            parts.append("Most reusable skills:")
            for s in stats["most_transferred_skills"][:3]:
                parts.append(f"  [{s['rate']:.0%}] {s['name']} "
                             f"({s['transfers']} transfers)")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "[...]"
        return result

    def get_skill(self, skill_id: str) -> Optional[AbstractSkill]:
        """Retrieve a skill by ID."""
        with self._lock:
            return self._skills.get(skill_id)

    def list_skills(self, domain: str = "") -> List[AbstractSkill]:
        """List all skills, optionally filtered by source domain."""
        with self._lock:
            if domain:
                return [s for s in self._skills.values()
                        if s.source_domain == domain]
            return list(self._skills.values())


# ─── Singleton ───────────────────────────────────────────────────────────────

_transfer_engine: Optional[TransferLearningEngine] = None
_transfer_lock = threading.Lock()


def get_transfer_learning() -> TransferLearningEngine:
    """Get the singleton transfer learning engine instance."""
    global _transfer_engine
    if _transfer_engine is None:
        with _transfer_lock:
            if _transfer_engine is None:
                _transfer_engine = TransferLearningEngine()
    return _transfer_engine


# ─── Quick test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    engine = get_transfer_learning()

    # Simulate extracting a skill from coding domain
    skill = engine.extract_abstract_skill({
        "description": "When a function fails, retry with exponential backoff",
        "goal": "handle transient failures gracefully",
        "steps": [
            "detect failure condition",
            "wait with exponential backoff",
            "retry the operation",
            "if max retries exceeded, use fallback",
            "log the outcome",
        ],
        "domain": "coding",
        "context": {"trigger": "API call timeout", "max_retries": 3},
    })
    print(f"\nExtracted: {skill.skill_id if skill else 'None'}")

    # Find transferable skills for security domain
    matches = engine.find_transferable_skills(
        "security",
        context="handle authentication failures and retry secure connections",
    )
    print(f"\nMatches for security: {len(matches)}")
    for s, score in matches:
        print(f"  {s.skill_id}: {s.pattern[:50]} (score: {score})")

    # Apply transfer
    if skill:
        result = engine.apply_transfer(skill, {
            "domain": "security",
            "goal": "handle failed authentication attempts",
            "available_tools": ["retry", "block_ip", "alert"],
        })
        print(f"\nTransfer result: {json.dumps(result, indent=2)}")

        # Record outcome
        engine.record_transfer_outcome(skill.skill_id, "security", True,
                                        "Successfully adapted retry pattern")

    # Show stats
    print(f"\nStats: {json.dumps(engine.get_stats(), indent=2)}")
    print(f"\nPrompt:\n{engine.format_for_prompt()}")
