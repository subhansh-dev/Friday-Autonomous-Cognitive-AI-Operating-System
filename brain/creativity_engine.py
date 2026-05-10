#!/usr/bin/env python3
"""
creativity_engine.py — FRIDAY Computational Creativity Engine
==============================================================

Implements multiple creativity techniques for novel idea generation:

  [CE-1] ConceptualBlender — merge features from different concepts
  [CE-2] ConstraintRelaxation — explore assumption violations systematically
  [CE-3] Bisociation — connect unrelated frames of reference (Koestler)
  [CE-4] NoveltyEvaluator — score ideas by distance, surprise, usefulness
  [CE-5] creative_dream() — creative memory recombination during dreaming
  [CE-6] generate_alternatives() — multi-technique idea generation
  [CE-7] creative_critique() — evaluate creativity of an idea
  [CE-8] creativity_journal — persistent idea storage with outcomes
  [CE-9] Integration hooks for dreaming, curiosity, world_model
"""

import json
import math
import random
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional, List, Dict, Any, Tuple


BRAIN_DIR = Path(__file__).parent.resolve()
DATA_FILE = BRAIN_DIR / "creativity_data.json"

# ── Configuration ───────────────────────────────────────────────────────────

MAX_JOURNAL_ENTRIES = 500       # Max creative ideas stored
NOVELTY_DISTANCE_THRESHOLD = 0.3  # Min distance to count as novel
BLEND_COMPATIBILITY_THRESHOLD = 0.4  # Feature compatibility for blending
RELAXATION_MAX_DEPTH = 5        # Max assumptions to relax simultaneously
BISECTION_MAX_CONNECTIONS = 10  # Max cross-domain connections per bisociation
CREATIVE_DREAM_COUNT = 5        # Ideas per dream cycle
IDEA_DECAY_DAYS = 30.           # Unreviewed ideas lose relevance
MIN_FEASIBILITY_FOR_RANKING = 0.1  # Minimum feasibility to keep


def _timestamp() -> str:
    return datetime.now().isoformat()


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-max(-10, min(10, x))))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _feature_distance(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Distance between two feature dicts (0 = identical, 1 = maximally different)."""
    all_keys = set(a.keys()) | set(b.keys())
    if not all_keys:
        return 1.0
    sum_sq = 0.0
    for k in all_keys:
        va = a.get(k, 0.0)
        vb = b.get(k, 0.0)
        sum_sq += (va - vb) ** 2
    return min(1.0, math.sqrt(sum_sq / len(all_keys)))


# ═══════════════════════════════════════════════════════════════════════════
# 1. ConceptualBlender — merge features from different concepts
# ═══════════════════════════════════════════════════════════════════════════

class ConceptualBlender:
    """
    Merges features from two different concepts into a novel blend.

    Each concept is a dict with:
      - name: str
      - features: Dict[str, float]  (feature_name → value in [0,1])
      - constraints: List[str]       (inviolable rules)
      - category: str                (domain/category tag)
    """

    def __init__(self):
        self._blend_history: List[Dict[str, Any]] = []

    def blend(self, concept_a: Dict[str, Any], concept_b: Dict[str, Any]) -> Dict[str, Any]:
        """
        Blend two concepts into a novel combination.

        Returns a new concept dict with:
          - name, features, conflicts, novel_combinations, source, blend_score
        """
        feat_a = concept_a.get("features", {})
        feat_b = concept_b.get("features", {})
        constraints_a = set(concept_a.get("constraints", []))
        constraints_b = set(concept_b.get("constraints", []))

        blended_features = {}
        conflicts = []
        novel_combos = []

        # Merge compatible features
        all_keys = set(feat_a.keys()) | set(feat_b.keys())
        for key in all_keys:
            va = feat_a.get(key)
            vb = feat_b.get(key)

            if va is not None and vb is not None:
                # Both have this feature — check compatibility
                diff = abs(va - vb)
                if diff < BLEND_COMPATIBILITY_THRESHOLD:
                    # Compatible: weighted average biased toward higher value
                    blended_features[key] = (va + vb) / 2.0
                else:
                    # Conflict: record it, take a creative midpoint
                    conflicts.append({
                        "feature": key,
                        "value_a": va,
                        "value_b": vb,
                        "resolution": "creative_midpoint"
                    })
                    # Non-obvious blend: geometric mean biases toward interesting middle
                    blended_features[key] = math.sqrt(va * vb)
            elif va is not None:
                blended_features[key] = va
            else:
                blended_features[key] = vb

        # Generate novel combinations: features that interact in unexpected ways
        feat_keys = list(blended_features.keys())
        for i in range(len(feat_keys)):
            for j in range(i + 1, len(feat_keys)):
                k1, k2 = feat_keys[i], feat_keys[j]
                v1, v2 = blended_features[k1], blended_features[k2]
                # Novel if neither source had both features at these values
                in_a = k1 in feat_a and k2 in feat_a
                in_b = k1 in feat_b and k2 in feat_b
                if not in_a and not in_b:
                    novel_combos.append({
                        "features": (k1, k2),
                        "values": (v1, v2),
                        "interaction": v1 * v2  # simple interaction score
                    })

        # Check constraint conflicts
        constraint_conflicts = constraints_a.symmetric_difference(constraints_b)
        for cc in constraint_conflicts:
            conflicts.append({
                "feature": "__constraint__",
                "detail": cc,
                "resolution": "flagged"
            })

        blend_score = max(0.0, 1.0 - len(conflicts) * 0.1) * (
            1.0 + len(novel_combos) * 0.05
        )

        result = {
            "name": f"blend({concept_a.get('name', '?')}, {concept_b.get('name', '?')})",
            "features": blended_features,
            "conflicts": conflicts,
            "novel_combinations": novel_combos,
            "source": [concept_a.get("name", ""), concept_b.get("name", "")],
            "blend_score": round(blend_score, 4),
            "timestamp": _timestamp(),
        }

        self._blend_history.append(result)
        if len(self._blend_history) > 100:
            self._blend_history = self._blend_history[-100:]

        return result


# ═══════════════════════════════════════════════════════════════════════════
# 2. ConstraintRelaxation — systematically explore assumption violations
# ═══════════════════════════════════════════════════════════════════════════

class ConstraintRelaxation:
    """
    Systematically explores what happens when assumptions are relaxed.

    Each assumption is a dict with:
      - name: str
      - description: str
      - relax_modes: List[str]  (ways to relax: "remove", "invert", "weaken", "generalize")
    """

    def __init__(self):
        self._relaxation_history: List[Dict[str, Any]] = []

    def relax_constraints(
        self,
        problem: Dict[str, Any],
        assumptions: List[Dict[str, Any]],
        max_depth: int = RELAXATION_MAX_DEPTH,
    ) -> List[Dict[str, Any]]:
        """
        Generate relaxed problem variants by toggling/modifying assumptions.

        Returns list of variants, each scored by constraint_satisfaction + novelty.
        """
        variants = []
        depth = min(len(assumptions), max_depth)

        # Single-assumption relaxations (most creative)
        for assumption in assumptions[:depth]:
            for mode in assumption.get("relax_modes", ["remove"]):
                variant = self._apply_relaxation(problem, assumption, mode)
                variant["relaxation_depth"] = 1
                variant["score"] = self._score_variant(variant, problem)
                variants.append(variant)

        # Pairwise relaxations (higher novelty potential)
        for i in range(min(depth, 4)):
            for j in range(i + 1, min(depth, 4)):
                a1, a2 = assumptions[i], assumptions[j]
                # Pick most interesting mode for each
                mode1 = random.choice(a1.get("relax_modes", ["remove"]))
                mode2 = random.choice(a2.get("relax_modes", ["remove"]))
                variant = self._apply_relaxation(problem, a1, mode1)
                variant = self._apply_relaxation(variant, a2, mode2)
                variant["relaxation_depth"] = 2
                variant["score"] = self._score_variant(variant, problem)
                variants.append(variant)

        # Sort by score descending
        variants.sort(key=lambda v: v["score"], reverse=True)

        self._relaxation_history.extend(variants[:5])
        if len(self._relaxation_history) > 100:
            self._relaxation_history = self._relaxation_history[-100:]

        return variants

    def _apply_relaxation(
        self, problem: Dict[str, Any], assumption: Dict[str, Any], mode: str
    ) -> Dict[str, Any]:
        """Apply a single relaxation to a problem."""
        variant = {
            "original_problem": problem.get("name", problem.get("description", "unknown")),
            "relaxed_assumption": assumption["name"],
            "relaxation_mode": mode,
            "description": "",
            "modified_constraints": dict(problem.get("constraints", {})),
            "modified_parameters": dict(problem.get("parameters", {})),
        }

        a_name = assumption["name"]

        if mode == "remove":
            variant["description"] = f"What if we don't require '{a_name}'?"
            variant["modified_constraints"].pop(a_name, None)
        elif mode == "invert":
            variant["description"] = f"What if '{a_name}' were reversed?"
            if a_name in variant["modified_constraints"]:
                val = variant["modified_constraints"][a_name]
                if isinstance(val, (int, float)):
                    variant["modified_constraints"][a_name] = -val
                elif isinstance(val, bool):
                    variant["modified_constraints"][a_name] = not val
                else:
                    variant["modified_constraints"][a_name] = f"NOT({val})"
        elif mode == "weaken":
            variant["description"] = f"What if '{a_name}' were less strict?"
            if a_name in variant["modified_constraints"]:
                val = variant["modified_constraints"][a_name]
                if isinstance(val, (int, float)):
                    variant["modified_constraints"][a_name] = val * 0.5
        elif mode == "generalize":
            variant["description"] = f"What if '{a_name}' applied more broadly?"
            variant["modified_constraints"][a_name] = "__generalized__"

        return variant

    def _score_variant(self, variant: Dict[str, Any], original: Dict[str, Any]) -> float:
        """Score a relaxed variant: balance feasibility with novelty."""
        # Constraint satisfaction: how many original constraints still met
        orig_constraints = original.get("constraints", {})
        var_constraints = variant.get("modified_constraints", {})
        if orig_constraints:
            satisfied = sum(
                1 for k in orig_constraints if k in var_constraints
            )
            satisfaction = satisfied / len(orig_constraints)
        else:
            satisfaction = 0.5

        # Novelty: more relaxed = more novel
        novelty = 0.3 + variant.get("relaxation_depth", 1) * 0.2
        # Extra novelty for inversion and generalization
        mode = variant.get("relaxation_mode", "")
        if mode in ("invert", "generalize"):
            novelty += 0.15

        return round(0.4 * satisfaction + 0.6 * novelty, 4)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Bisociation — connect two unrelated frames of reference
# ═══════════════════════════════════════════════════════════════════════════

class Bisociation:
    """
    Koestler's bisociation: connecting two self-consistent but unrelated
    matrices of thought to produce creative insight.

    Each frame is a dict with:
      - name: str
      - domain: str
      - structure: Dict[str, Any]  (relational structure: entities + relationships)
      - patterns: List[str]        (recurring patterns/templates)
    """

    def __init__(self):
        self._bisociation_history: List[Dict[str, Any]] = []

    def bisociate(
        self, frame_a: Dict[str, Any], frame_b: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Find unexpected structural connections between two unrelated frames.

        Returns list of connections, each with:
          - structural_parallel: what maps between frames
          - insight: the creative connection
          - surprise_score: how unexpected the connection is
        """
        connections = []

        struct_a = frame_a.get("structure", {})
        struct_b = frame_b.get("structure", {})
        patterns_a = frame_a.get("patterns", [])
        patterns_b = frame_b.get("patterns", [])

        # Find structural parallels: similar relational patterns
        for rel_a, desc_a in struct_a.items():
            for rel_b, desc_b in struct_b.items():
                similarity = self._structural_similarity(desc_a, desc_b)
                if 0.3 < similarity < 0.9:  # Not trivially similar, not completely different
                    connections.append({
                        "type": "structural_parallel",
                        "frame_a_element": rel_a,
                        "frame_b_element": rel_b,
                        "similarity": round(similarity, 4),
                        "insight": (
                            f"'{rel_a}' in {frame_a.get('name', 'A')} "
                            f"mirrors '{rel_b}' in {frame_b.get('name', 'B')} — "
                            f"what works in one domain might transfer to the other"
                        ),
                    })

        # Find pattern inversions: same pattern, opposite domain
        for pat_a in patterns_a:
            for pat_b in patterns_b:
                if self._are_inverted_patterns(pat_a, pat_b):
                    connections.append({
                        "type": "pattern_inversion",
                        "pattern_a": pat_a,
                        "pattern_b": pat_b,
                        "insight": (
                            f"Pattern '{pat_a}' and '{pat_b}' are inversions — "
                            f"combining them creates tension that may spark novelty"
                        ),
                        "surprise_score": 0.8,
                    })

        # Find cross-domain mappings via shared abstract structure
        shared_abstractions = self._find_shared_abstractions(struct_a, struct_b)
        for abstraction in shared_abstractions:
            connections.append({
                "type": "cross_domain_mapping",
                "abstraction": abstraction,
                "insight": (
                    f"Both frames share abstract structure '{abstraction}' — "
                    f"transfer insights from {frame_a.get('name', 'A')} "
                    f"to {frame_b.get('name', 'B')} via this bridge"
                ),
                "surprise_score": 0.7,
            })

        # Score and rank connections
        for conn in connections:
            conn["surprise_score"] = conn.get("surprise_score", 0.5)
            conn["overall_score"] = round(
                conn["surprise_score"] * 0.6 +
                conn.get("similarity", 0.5) * 0.4, 4
            )

        connections.sort(key=lambda c: c.get("overall_score", 0), reverse=True)
        top = connections[:BISECTION_MAX_CONNECTIONS]

        self._bisociation_history.extend(top)
        if len(self._bisociation_history) > 100:
            self._bisociation_history = self._bisociation_history[-100:]

        return top

    def _structural_similarity(self, desc_a: Any, desc_b: Any) -> float:
        """Compute similarity between two structural descriptions."""
        if isinstance(desc_a, str) and isinstance(desc_b, str):
            words_a = set(desc_a.lower().split())
            words_b = set(desc_b.lower().split())
            if not words_a or not words_b:
                return 0.0
            intersection = words_a & words_b
            union = words_a | words_b
            return len(intersection) / len(union) if union else 0.0
        elif isinstance(desc_a, (int, float)) and isinstance(desc_b, (int, float)):
            return 1.0 / (1.0 + abs(desc_a - desc_b))
        return 0.0

    def _are_inverted_patterns(self, pat_a: str, pat_b: str) -> bool:
        """Check if two patterns are inversions of each other."""
        inversions = {
            "growth": "decay", "expand": "contract", "build": "destroy",
            "connect": "separate", "attract": "repel", "heat": "cool",
            "accelerate": "decelerate", "amplify": "dampen", "open": "close",
        }
        a_lower = pat_a.lower()
        b_lower = pat_b.lower()
        for fwd, rev in inversions.items():
            if (fwd in a_lower and rev in b_lower) or (rev in a_lower and fwd in b_lower):
                return True
        return False

    def _find_shared_abstractions(
        self, struct_a: Dict[str, Any], struct_b: Dict[str, Any]
    ) -> List[str]:
        """Find abstract structural patterns shared between two frames."""
        abstractions = []

        # Check for common relational patterns
        a_rels = set(struct_a.keys())
        b_rels = set(struct_b.keys())

        # Structural isomorphism: same number of elements, similar connectivity
        if len(a_rels) == len(b_rels) and len(a_rels) > 1:
            abstractions.append(f"isomorphic_{len(a_rels)}-element_structure")

        # Hub pattern: one element connected to many
        for rel_set, name in [(a_rels, "A"), (b_rels, "B")]:
            pass  # Already captured in structural parallels

        # Feedback loops: cyclic references
        a_str = json.dumps(struct_a, sort_keys=True)
        b_str = json.dumps(struct_b, sort_keys=True)
        if "feedback" in a_str.lower() and "feedback" in b_str.lower():
            abstractions.append("shared_feedback_dynamics")

        return abstractions


# ═══════════════════════════════════════════════════════════════════════════
# 4. NoveltyEvaluator — score how novel an idea is
# ═══════════════════════════════════════════════════════════════════════════

class NoveltyEvaluator:
    """
    Evaluates how novel, surprising, and useful an idea is relative to
    a library of existing ideas.
    """

    def __init__(self):
        self._existing_ideas: List[Dict[str, Any]] = []

    def register_idea(self, idea: Dict[str, Any]):
        """Register an existing idea to compare against."""
        self._existing_ideas.append(idea)
        if len(self._existing_ideas) > 500:
            self._existing_ideas = self._existing_ideas[-500:]

    def evaluate(
        self,
        idea: Dict[str, Any],
        problem_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, float]:
        """
        Evaluate an idea on three dimensions:
          - novelty: distance from existing ideas in feature space (0-1)
          - surprise: how unexpected given prior knowledge (0-1)
          - usefulness: estimated problem-solving value (0-1)

        Returns dict with novelty, surprise, usefulness, overall_score.
        """
        idea_features = idea.get("features", {})

        # 1. Novelty: minimum distance from any existing idea
        if self._existing_ideas and idea_features:
            distances = [
                _feature_distance(idea_features, existing.get("features", {}))
                for existing in self._existing_ideas
            ]
            novelty = min(1.0, max(distances) if distances else 1.0)
        else:
            novelty = 0.7  # Default moderate novelty if no comparison set

        # 2. Surprise: how many features are atypical
        if self._existing_ideas and idea_features:
            feature_means = defaultdict(float)
            feature_counts = defaultdict(int)
            for existing in self._existing_ideas:
                for k, v in existing.get("features", {}).items():
                    feature_means[k] += v
                    feature_counts[k] += 1
            for k in feature_means:
                feature_means[k] /= max(1, feature_counts[k])

            surprise_sum = 0.0
            surprise_count = 0
            for k, v in idea_features.items():
                if k in feature_means:
                    surprise_sum += abs(v - feature_means[k])
                    surprise_count += 1
            surprise = min(1.0, surprise_sum / max(1, surprise_count) * 2)
        else:
            surprise = 0.5

        # 3. Usefulness: coherence with problem context + feature coverage
        usefulness = 0.5
        if problem_context:
            ctx_features = problem_context.get("relevant_features", set())
            if ctx_features and idea_features:
                coverage = sum(1 for k in idea_features if k in ctx_features)
                usefulness = min(1.0, coverage / max(1, len(ctx_features)))

            # Bonus for ideas that address stated constraints
            constraints = problem_context.get("constraints", {})
            if constraints and idea.get("addresses_constraints"):
                usefulness += 0.2

        overall = round(0.4 * novelty + 0.3 * surprise + 0.3 * usefulness, 4)

        return {
            "novelty": round(novelty, 4),
            "surprise": round(surprise, 4),
            "usefulness": round(usefulness, 4),
            "overall_score": overall,
        }


# ═══════════════════════════════════════════════════════════════════════════
# CreativityEngine — orchestrator tying all techniques together
# ═══════════════════════════════════════════════════════════════════════════

class CreativityEngine:
    """
    Central creativity engine for FRIDAY.

    Orchestrates conceptual blending, constraint relaxation, bisociation,
    novelty evaluation, creative dreaming, and persistent idea journaling.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self.blender = ConceptualBlender()
        self.relaxer = ConstraintRelaxation()
        self.bisociator = Bisociation()
        self.evaluator = NoveltyEvaluator()
        self._journal: List[Dict[str, Any]] = []
        self._stats = {
            "ideas_generated": 0,
            "ideas_evaluated": 0,
            "dream_cycles_used": 0,
            "alternatives_generated": 0,
            "blends_performed": 0,
            "relaxations_performed": 0,
            "bisociations_performed": 0,
        }
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _load(self):
        with self._lock:
            if DATA_FILE.exists():
                try:
                    raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                    self._journal = raw.get("journal", [])
                    self._stats.update(raw.get("stats", {}))
                    # Restore evaluator with existing ideas
                    for entry in self._journal:
                        if entry.get("features"):
                            self.evaluator.register_idea(entry)
                    print(f"[CreativityEngine] Loaded {len(self._journal)} journal entries")
                except Exception as e:
                    print(f"[CreativityEngine] Load error: {e}")

    def _save(self):
        with self._lock:
            try:
                payload = {
                    "version": 1,
                    "updated": _timestamp(),
                    "journal": self._journal[-MAX_JOURNAL_ENTRIES:],
                    "stats": self._stats,
                }
                DATA_FILE.write_text(
                    json.dumps(payload, indent=2, default=str),
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"[CreativityEngine] Save error: {e}")

    # ── 6. generate_alternatives ────────────────────────────────────────

    def generate_alternatives(
        self,
        problem: Dict[str, Any],
        existing_solution: Dict[str, Any],
        n: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Produce N creative alternatives using each creativity technique.

        Uses blending, constraint relaxation, and bisociation, then ranks
        by novelty × feasibility.
        """
        with self._lock:
            alternatives = []

            # Technique 1: Conceptual blending — blend existing solution with
            # random concepts from the journal
            candidates = random.sample(
                self._journal, min(3, len(self._journal))
            ) if self._journal else []
            for cand in candidates:
                blend = self.blender.blend(existing_solution, cand)
                alternatives.append({
                    "technique": "blend",
                    "idea": blend,
                    "feasibility": 0.6,
                })
                self._stats["blends_performed"] += 1

            # Technique 2: Constraint relaxation
            assumptions = problem.get("assumptions", [
                {"name": a, "relax_modes": ["remove", "invert"]}
                for a in problem.get("constraints", {}).keys()
            ])
            if assumptions:
                relaxed = self.relaxer.relax_constraints(problem, assumptions)
                for variant in relaxed[:3]:
                    alternatives.append({
                        "technique": "constraint_relaxation",
                        "idea": variant,
                        "feasibility": max(0.2, 1.0 - variant.get("relaxation_depth", 1) * 0.2),
                    })
                    self._stats["relaxations_performed"] += 1

            # Technique 3: Bisociation with random journal entries
            if len(self._journal) >= 2:
                other = random.choice(self._journal)
                connections = self.bisociator.bisociate(existing_solution, other)
                for conn in connections[:2]:
                    alternatives.append({
                        "technique": "bisociation",
                        "idea": conn,
                        "feasibility": 0.4,
                    })
                    self._stats["bisociations_performed"] += 1

            # Evaluate and rank
            for alt in alternatives:
                idea = alt["idea"]
                eval_result = self.evaluator.evaluate(idea, problem)
                alt["novelty"] = eval_result["novelty"]
                alt["surprise"] = eval_result["surprise"]
                alt["rank_score"] = round(
                    eval_result["novelty"] * alt["feasibility"], 4
                )

            alternatives.sort(key=lambda a: a["rank_score"], reverse=True)
            top_n = alternatives[:n]

            # Journal the top results
            for alt in top_n:
                self._journal_entry(alt["idea"], alt["technique"], alt["rank_score"])

            self._stats["alternatives_generated"] += len(top_n)
            self._stats["ideas_generated"] += len(top_n)
            self._save()

            print(f"[CreativityEngine] Generated {len(top_n)} alternatives "
                  f"from {len(alternatives)} candidates")

            return top_n

    # ── 7. creative_critique ────────────────────────────────────────────

    def creative_critique(self, idea: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate an idea's creativity across three dimensions:
          novelty + value + surprise

        Returns a critique dict with scores and textual feedback.
        """
        with self._lock:
            eval_result = self.evaluator.evaluate(idea)
            self._stats["ideas_evaluated"] += 1

            novelty = eval_result["novelty"]
            surprise = eval_result["surprise"]
            usefulness = eval_result["usefulness"]

            # Generate textual critique
            strengths = []
            weaknesses = []

            if novelty > 0.7:
                strengths.append("Highly novel — far from existing ideas")
            elif novelty > 0.4:
                strengths.append("Moderately novel — fresh perspective")
            else:
                weaknesses.append("Low novelty — similar to existing ideas")

            if surprise > 0.6:
                strengths.append("Surprising — unexpected combination")
            else:
                weaknesses.append("Predictable — follows expected patterns")

            if usefulness > 0.6:
                strengths.append("Practical — addresses the problem well")
            elif usefulness > 0.3:
                strengths.append("Potentially useful with refinement")
            else:
                weaknesses.append("Unclear practical value")

            creativity_score = round(
                0.35 * novelty + 0.35 * surprise + 0.30 * usefulness, 4
            )

            if creativity_score > 0.7:
                verdict = "highly_creative"
            elif creativity_score > 0.5:
                verdict = "moderately_creative"
            elif creativity_score > 0.3:
                verdict = "mildly_creative"
            else:
                verdict = "conventional"

            critique = {
                "creativity_score": creativity_score,
                "verdict": verdict,
                "dimensions": eval_result,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "suggestion": self._improvement_suggestion(eval_result),
                "timestamp": _timestamp(),
            }

            self._save()
            return critique

    def _improvement_suggestion(self, eval_result: Dict[str, float]) -> str:
        """Suggest how to make an idea more creative."""
        novelty = eval_result["novelty"]
        surprise = eval_result["surprise"]
        usefulness = eval_result["usefulness"]

        if novelty < surprise and novelty < usefulness:
            return "Try combining with more distant concepts to increase novelty"
        elif surprise < novelty and surprise < usefulness:
            return "Look for unexpected structural parallels or inversions"
        elif usefulness < novelty and usefulness < surprise:
            return "Ground the idea in concrete problem constraints"
        else:
            return "Refine by relaxing an assumption and re-evaluating"

    # ── 5. creative_dream ───────────────────────────────────────────────

    def creative_dream(self, memories: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        Creative dreaming: deliberately combine memories from different categories.

        Hook into the dreaming system for creative memory recombination.
        Score dream outputs by novelty + coherence.
        """
        with self._lock:
            if not memories:
                memories = self._journal

            if len(memories) < 2:
                print("[CreativityEngine] Not enough memories for creative dream")
                return []

            # Group memories by category for cross-category blending
            by_category: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for mem in memories:
                cat = mem.get("category", mem.get("technique", "unknown"))
                by_category[cat].append(mem)

            categories = list(by_category.keys())
            dream_ideas = []

            for _ in range(CREATIVE_DREAM_COUNT):
                if len(categories) < 2:
                    break

                # Pick two different categories
                cat_a, cat_b = random.sample(categories, 2)
                mem_a = random.choice(by_category[cat_a])
                mem_b = random.choice(by_category[cat_b])

                # Blend them
                blend = self.blender.blend(mem_a, mem_b)
                eval_result = self.evaluator.evaluate(blend)

                # Coherence: how internally consistent is the blend?
                conflict_penalty = len(blend.get("conflicts", [])) * 0.1
                coherence = max(0.0, 1.0 - conflict_penalty)

                dream_score = round(
                    eval_result["novelty"] * 0.5 + coherence * 0.5, 4
                )

                dream_ideas.append({
                    "type": "creative_dream",
                    "source_categories": [cat_a, cat_b],
                    "idea": blend,
                    "novelty": eval_result["novelty"],
                    "coherence": coherence,
                    "dream_score": dream_score,
                    "timestamp": _timestamp(),
                })

            # Journal dream results
            for dream in dream_ideas:
                self._journal_entry(
                    dream["idea"], "creative_dream", dream["dream_score"]
                )

            self._stats["dream_cycles_used"] += 1
            self._stats["ideas_generated"] += len(dream_ideas)
            self._save()

            print(f"[CreativityEngine] Creative dream produced {len(dream_ideas)} ideas")
            return dream_ideas

    # ── Journal ─────────────────────────────────────────────────────────

    def _journal_entry(self, idea: Dict[str, Any], technique: str, score: float):
        """Add an idea to the creativity journal."""
        entry = {
            "id": f"idea_{int(time.time() * 1000)}_{random.randint(1000, 9999)}",
            "technique": technique,
            "features": idea.get("features", {}),
            "description": idea.get("name", idea.get("description", idea.get("insight", ""))),
            "score": score,
            "outcome": None,  # Filled in later when idea is tested
            "created": _timestamp(),
        }
        self._journal.append(entry)
        self.evaluator.register_idea(entry)

        if len(self._journal) > MAX_JOURNAL_ENTRIES:
            self._journal = self._journal[-MAX_JOURNAL_ENTRIES:]

    def record_outcome(self, idea_id: str, outcome: str, success: bool):
        """Record the outcome of a creative idea (for learning)."""
        with self._lock:
            for entry in self._journal:
                if entry.get("id") == idea_id:
                    entry["outcome"] = {
                        "result": outcome,
                        "success": success,
                        "recorded": _timestamp(),
                    }
                    print(f"[CreativityEngine] Recorded outcome for {idea_id}: "
                          f"{'success' if success else 'failure'}")
                    self._save()
                    return
            print(f"[CreativityEngine] Idea {idea_id} not found in journal")

    def get_journal(
        self,
        technique: Optional[str] = None,
        min_score: float = 0.0,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Retrieve journal entries, optionally filtered."""
        with self._lock:
            entries = self._journal
            if technique:
                entries = [e for e in entries if e.get("technique") == technique]
            entries = [e for e in entries if e.get("score", 0) >= min_score]
            return entries[-limit:]

    # ── Integration hooks ───────────────────────────────────────────────

    def dream_integration(self, dream_memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Integration with brain.dreaming — called during dream cycles.

        Takes memories from the dreaming system and produces creative
        recombinations that feed back into the dream journal.
        """
        print(f"[CreativityEngine] Dream integration: processing {len(dream_memories)} memories")
        return self.creative_dream(dream_memories)

    def curiosity_integration(self, curiosity_targets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Integration with brain.curiosity — curiosity drives exploration of
        novel combinations.

        Takes curiosity targets and generates creative alternatives for
        high-curiosity items.
        """
        with self._lock:
            suggestions = []
            for target in curiosity_targets:
                topic = target.get("topic", target.get("name", "unknown"))
                interest = target.get("interest_level", 0.5)

                # Higher curiosity → more aggressive exploration
                if interest > 0.6:
                    problem = {
                        "name": topic,
                        "constraints": {},
                        "assumptions": [
                            {"name": "conventional_approach", "relax_modes": ["invert", "remove"]},
                        ],
                    }
                    existing = {"name": f"standard_{topic}", "features": {}}
                    alts = self.generate_alternatives(problem, existing, n=2)
                    suggestions.extend(alts)

            print(f"[CreativityEngine] Curiosity integration: {len(suggestions)} suggestions")
            return suggestions

    def world_model_integration(
        self, idea: Dict[str, Any], world_model: Any = None
    ) -> Dict[str, Any]:
        """
        Integration with brain.world_model — evaluate creative ideas via simulation.

        Uses the world model to simulate outcomes of a creative idea.
        Falls back to heuristic evaluation if world model unavailable.
        """
        with self._lock:
            if world_model is not None and hasattr(world_model, "evaluate_plan"):
                try:
                    # Convert idea to an action sequence for the world model
                    action_sequence = [{"tool": idea.get("name", "idea"), "complexity": 0.5}]
                    simulation = world_model.evaluate_plan(action_sequence)
                    return {
                        "idea": idea.get("name", "unnamed"),
                        "simulated_outcome": simulation,
                        "evaluation_method": "world_model_simulation",
                    }
                except Exception as e:
                    print(f"[CreativityEngine] World model simulation failed: {e}")

            # Fallback: heuristic evaluation
            critique = self.creative_critique(idea)
            return {
                "idea": idea.get("name", "unnamed"),
                "simulated_outcome": {
                    "feasibility": critique["dimensions"]["usefulness"],
                    "impact": critique["dimensions"]["novelty"],
                },
                "evaluation_method": "heuristic_fallback",
            }

    # ── Prompt formatting ───────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 2000) -> str:
        """Format creativity state for inclusion in LLM prompts."""
        with self._lock:
            lines = ["=== Creativity Engine State ==="]
            lines.append(f"Journal entries: {len(self._journal)}")
            lines.append(f"Ideas generated: {self._stats['ideas_generated']}")
            lines.append(f"Dream cycles used: {self._stats['dream_cycles_used']}")

            # Recent high-scoring ideas
            recent = sorted(self._journal, key=lambda x: x.get("score", 0), reverse=True)[:5]
            if recent:
                lines.append("\nTop ideas:")
                for entry in recent:
                    desc = entry.get("description", "")[:80]
                    score = entry.get("score", 0)
                    tech = entry.get("technique", "?")
                    lines.append(f"  [{tech}] {desc} (score: {score:.2f})")

            # Outcome summary
            with_outcomes = [e for e in self._journal if e.get("outcome")]
            if with_outcomes:
                successes = sum(1 for e in with_outcomes if e["outcome"].get("success"))
                lines.append(f"\nOutcomes: {successes}/{len(with_outcomes)} successful")

            result = "\n".join(lines)
            if len(result) > max_chars:
                result = result[:max_chars - 3] + "..."
            return result

    # ── Stats ───────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return engine statistics."""
        with self._lock:
            journal_by_technique = defaultdict(int)
            for entry in self._journal:
                journal_by_technique[entry.get("technique", "unknown")] += 1

            outcomes = [e for e in self._journal if e.get("outcome")]
            success_rate = (
                sum(1 for e in outcomes if e["outcome"].get("success")) / max(1, len(outcomes))
            )

            return {
                **self._stats,
                "journal_size": len(self._journal),
                "journal_by_technique": dict(journal_by_technique),
                "success_rate": round(success_rate, 4),
                "existing_ideas_for_novelty": len(self.evaluator._existing_ideas),
            }


# ── Singleton ───────────────────────────────────────────────────────────────

_creativity_engine_instance: Optional[CreativityEngine] = None
_creativity_engine_lock = threading.Lock()


def get_creativity_engine() -> CreativityEngine:
    """Get or create the singleton CreativityEngine instance."""
    global _creativity_engine_instance
    if _creativity_engine_instance is None:
        with _creativity_engine_lock:
            if _creativity_engine_instance is None:
                _creativity_engine_instance = CreativityEngine()
                print("[CreativityEngine] Singleton initialized")
    return _creativity_engine_instance
