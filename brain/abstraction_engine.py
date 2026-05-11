#!/usr/bin/env python3
"""
abstraction_engine.py — FRIDAY Abstraction Engine (Pillar 6)
================================================================

Cross-domain reasoning and abstraction for creative problem-solving.

Implements cognitive capabilities for:

  [AE-1] Analogical reasoning across domains
         — Finding structural similarities between disparate fields
           (Gentner, 1983; Structure-Mapping Theory)

  [AE-2] First-principles decomposition
         — Breaking problems down to fundamental components,
           stripping away assumptions (Aristotelian method,
           popularized by Elon Musk's reasoning framework)

  [AE-3] Counterfactual reasoning
         — Exploring "what if X had been different?" scenarios
           to understand causal dependencies and alternatives
           (Pearl, 2000; Lewis, 1973)

  [AE-4] Causal chain tracing
         — Following cause-effect chains across domains
           to find root causes and downstream effects

  [AE-5] Cross-domain transfer
         — Applying solutions from known domains to novel problems
           (Holyoak & Thagard, 1995)

  [AE-6] Emergent insight generation
         — Combining unrelated concepts to produce novel ideas
           through conceptual blending (Fauconnier & Turner, 2002)

  [AE-7] Abstract pattern recognition
         — Finding common structural patterns across diverse instances

This module enhances FRIDAY's ability to think laterally, transfer
knowledge across domains, and generate creative solutions by
abstracting away surface details to reveal deep structure.
"""

import hashlib
import json
import math
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


BRAIN_DIR = Path(__file__).parent.resolve()
ABSTRACTION_FILE = BRAIN_DIR / "abstraction_state.json"

# ── Configuration ───────────────────────────────────────────────────────────

MAX_DOMAINS = 100
MAX_ANALOGIES = 500
MAX_PATTERNS = 300
MAX_CAUSAL_CHAINS = 200
MAX_INSIGHTS = 200
MAX_CROSS_TRANSFERS = 200

# Similarity
STRUCTURAL_SIMILARITY_THRESHOLD = 0.3
ANALOGY_MIN_RELATIONS = 2

# Causal chain
DEFAULT_CHAIN_DEPTH = 5
MAX_CHAIN_DEPTH = 10

# Persistence
MAX_HISTORY = 500


def _now() -> str:
    return datetime.now().isoformat()


def _timestamp() -> float:
    return time.time()


def _hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


# ── Data Structures ─────────────────────────────────────────────────────────

class Domain:
    """Represents a knowledge domain with its concepts and relations."""

    __slots__ = [
        "name", "concepts", "relations", "properties",
        "created_at", "last_used_at",
    ]

    def __init__(self, name: str):
        self.name = name
        self.concepts: Dict[str, Dict[str, Any]] = {}  # concept_name → attributes
        self.relations: List[Tuple[str, str, str]] = []  # (subject, relation, object)
        self.properties: Dict[str, Any] = {}
        self.created_at = _now()
        self.last_used_at = _now()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "concepts": self.concepts,
            "relations": self.relations,
            "properties": self.properties,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Domain":
        dom = cls(d.get("name", "unknown"))
        dom.concepts = d.get("concepts", {})
        dom.relations = [tuple(r) for r in d.get("relations", [])]
        dom.properties = d.get("properties", {})
        dom.created_at = d.get("created_at", _now())
        dom.last_used_at = d.get("last_used_at", _now())
        return dom


class Analogy:
    """A structural analogy between two domains."""

    __slots__ = [
        "analogy_id", "source_domain", "target_domain",
        "mapping", "structural_similarity", "relations_mapped",
        "created_at", "use_count", "success_count",
    ]

    def __init__(self, source_domain: str, target_domain: str,
                 mapping: Dict[str, str], structural_similarity: float,
                 relations_mapped: int):
        self.analogy_id = _hash(f"{source_domain}:{target_domain}:{_now()}")
        self.source_domain = source_domain
        self.target_domain = target_domain
        self.mapping = mapping  # source_concept → target_concept
        self.structural_similarity = round(structural_similarity, 4)
        self.relations_mapped = relations_mapped
        self.created_at = _now()
        self.use_count = 0
        self.success_count = 0

    def to_dict(self) -> dict:
        return {
            "analogy_id": self.analogy_id,
            "source_domain": self.source_domain,
            "target_domain": self.target_domain,
            "mapping": self.mapping,
            "structural_similarity": self.structural_similarity,
            "relations_mapped": self.relations_mapped,
            "created_at": self.created_at,
            "use_count": self.use_count,
            "success_count": self.success_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Analogy":
        a = cls(
            source_domain=d.get("source_domain", ""),
            target_domain=d.get("target_domain", ""),
            mapping=d.get("mapping", {}),
            structural_similarity=d.get("structural_similarity", 0.0),
            relations_mapped=d.get("relations_mapped", 0),
        )
        a.analogy_id = d.get("analogy_id", a.analogy_id)
        a.created_at = d.get("created_at", _now())
        a.use_count = d.get("use_count", 0)
        a.success_count = d.get("success_count", 0)
        return a


class CausalLink:
    """A single cause-effect link in a causal chain."""

    __slots__ = ["cause", "effect", "domain", "strength", "mechanism"]

    def __init__(self, cause: str, effect: str, domain: str = "general",
                 strength: float = 0.7, mechanism: str = ""):
        self.cause = cause
        self.effect = effect
        self.domain = domain
        self.strength = min(1.0, max(0.0, strength))
        self.mechanism = mechanism

    def to_dict(self) -> dict:
        return {
            "cause": self.cause,
            "effect": self.effect,
            "domain": self.domain,
            "strength": self.strength,
            "mechanism": self.mechanism,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CausalLink":
        return cls(
            cause=d.get("cause", ""),
            effect=d.get("effect", ""),
            domain=d.get("domain", "general"),
            strength=d.get("strength", 0.7),
            mechanism=d.get("mechanism", ""),
        )


# ── Abstraction Engine ──────────────────────────────────────────────────────

class AbstractionEngine:
    """
    Cross-domain reasoning and abstraction for creative problem-solving.

    Finds structural similarities between domains, decomposes problems
    to first principles, explores counterfactuals, traces causal chains,
    transfers solutions across fields, and generates emergent insights
    by combining unrelated concepts.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._domains: Dict[str, Domain] = {}
        self._analogies: List[Analogy] = []
        self._causal_links: List[CausalLink] = []
        self._patterns: List[dict] = []
        self._insights: List[dict] = []
        self._transfers: List[dict] = []
        self._counterfactuals: List[dict] = []
        self._first_principles: List[dict] = []
        self._meta: Dict[str, Any] = {
            "version": 1,
            "created": _now(),
            "last_update": _now(),
            "total_analogies": 0,
            "total_causal_chains": 0,
            "total_insights": 0,
            "total_transfers": 0,
            "total_counterfactuals": 0,
            "total_first_principles": 0,
        }
        self._session_ops = 0
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _load(self):
        if not ABSTRACTION_FILE.exists():
            self._save()
            return
        try:
            raw = ABSTRACTION_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            self._meta = data.get("meta", self._meta)

            for name, d_dict in data.get("domains", {}).items():
                self._domains[name] = Domain.from_dict(d_dict)

            self._analogies = [Analogy.from_dict(a) for a in data.get("analogies", [])]
            self._causal_links = [CausalLink.from_dict(c) for c in data.get("causal_links", [])]
            self._patterns = data.get("patterns", [])
            self._insights = data.get("insights", [])
            self._transfers = data.get("transfers", [])
            self._counterfactuals = data.get("counterfactuals", [])
            self._first_principles = data.get("first_principles", [])
        except (json.JSONDecodeError, IOError):
            self._save()

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            data = {
                "meta": self._meta,
                "domains": {name: d.to_dict() for name, d in self._domains.items()},
                "analogies": [a.to_dict() for a in self._analogies[-MAX_ANALOGIES:]],
                "causal_links": [c.to_dict() for c in self._causal_links[-MAX_CAUSAL_CHAINS:]],
                "patterns": self._patterns[-MAX_PATTERNS:],
                "insights": self._insights[-MAX_INSIGHTS:],
                "transfers": self._transfers[-MAX_CROSS_TRANSFERS:],
                "counterfactuals": self._counterfactuals[-MAX_HISTORY:],
                "first_principles": self._first_principles[-MAX_HISTORY:],
            }
            data["meta"]["last_update"] = _now()
            ABSTRACTION_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ── Domain Management ───────────────────────────────────────────────

    def register_domain(self, name: str, concepts: Dict[str, Any] = None,
                        relations: List[Tuple[str, str, str]] = None,
                        properties: Dict[str, Any] = None) -> Domain:
        """Register or update a knowledge domain."""
        with self._lock:
            if name not in self._domains:
                self._domains[name] = Domain(name)
            dom = self._domains[name]
            if concepts:
                dom.concepts.update(concepts)
            if relations:
                dom.relations.extend(relations)
            if properties:
                dom.properties.update(properties)
            dom.last_used_at = _now()
            self._save()
            return dom

    def get_domain(self, name: str) -> Optional[Domain]:
        """Get a registered domain by name."""
        with self._lock:
            dom = self._domains.get(name)
            if dom:
                dom.last_used_at = _now()
            return dom

    def list_domains(self) -> List[str]:
        """List all registered domain names."""
        with self._lock:
            return list(self._domains.keys())

    # ── Core: Find Analogies ────────────────────────────────────────────

    def find_analogies(self, source_domain: str,
                       target_domain: str) -> List[dict]:
        """
        Find structural similarities between two domains.

        Uses structure-mapping: identifies shared relational structures
        between the source and target domain, even when surface features
        differ completely.

        Args:
            source_domain: Name of the source domain
            target_domain: Name of the target domain

        Returns:
            List of analogy dicts with mapping, similarity, and explanation
        """
        with self._lock:
            self._session_ops += 1
            source = self._domains.get(source_domain)
            target = self._domains.get(target_domain)

            if not source or not target:
                return []

            # Extract relational predicates from both domains
            source_relations = set()
            for subj, rel, obj in source.relations:
                source_relations.add(rel)

            target_relations = set()
            for subj, rel, obj in target.relations:
                target_relations.add(rel)

            # Find shared relation types
            shared_relations = source_relations & target_relations
            if len(shared_relations) < ANALOGY_MIN_RELATIONS:
                # Fall back to concept attribute similarity
                shared_relations = self._find_attribute_overlaps(source, target)

            # Build mapping based on relational role correspondence
            mapping = self._build_structural_mapping(source, target, shared_relations)

            # Compute structural similarity
            total_relations = len(source_relations | target_relations)
            structural_sim = len(shared_relations) / max(total_relations, 1)

            # Adjust for mapping coherence
            if mapping:
                mapping_coverage = len(mapping) / max(len(source.concepts), 1)
                structural_sim = (structural_sim * 0.6 + mapping_coverage * 0.4)

            results = []
            if structural_sim >= STRUCTURAL_SIMILARITY_THRESHOLD:
                analogy = Analogy(
                    source_domain=source_domain,
                    target_domain=target_domain,
                    mapping=mapping,
                    structural_similarity=structural_sim,
                    relations_mapped=len(shared_relations),
                )
                self._analogies.append(analogy)
                self._meta["total_analogies"] += 1

                explanation = self._generate_analogy_explanation(
                    source, target, mapping, shared_relations
                )

                results.append({
                    "analogy_id": analogy.analogy_id,
                    "source": source_domain,
                    "target": target_domain,
                    "mapping": mapping,
                    "structural_similarity": analogy.structural_similarity,
                    "relations_mapped": analogy.relations_mapped,
                    "shared_relations": list(shared_relations),
                    "explanation": explanation,
                })

            self._save()
            return results

    def _find_attribute_overlaps(self, source: Domain,
                                  target: Domain) -> Set[str]:
        """Find overlapping concept attributes between domains."""
        source_attrs = set()
        for c_name, attrs in source.concepts.items():
            if isinstance(attrs, dict):
                source_attrs.update(attrs.keys())

        target_attrs = set()
        for c_name, attrs in target.concepts.items():
            if isinstance(attrs, dict):
                target_attrs.update(attrs.keys())

        return source_attrs & target_attrs

    def _build_structural_mapping(self, source: Domain, target: Domain,
                                   shared_relations: Set[str]) -> Dict[str, str]:
        """Build concept mapping based on structural role correspondence."""
        mapping = {}

        # For each shared relation, map concepts playing similar roles
        for rel in shared_relations:
            source_actors = set()
            for subj, r, obj in source.relations:
                if r == rel:
                    source_actors.add(subj)
                    source_actors.add(obj)

            target_actors = set()
            for subj, r, obj in target.relations:
                if r == rel:
                    target_actors.add(subj)
                    target_actors.add(target_actors)

            # Greedy mapping: match by attribute similarity
            for s_actor in source_actors:
                best_match = None
                best_score = 0.0
                s_attrs = source.concepts.get(s_actor, {})
                for t_actor in target_actors:
                    if t_actor in mapping.values():
                        continue
                    t_attrs = target.concepts.get(t_actor, {})
                    score = self._concept_similarity(s_attrs, t_attrs)
                    if score > best_score:
                        best_score = score
                        best_match = t_actor
                if best_match and best_score > 0.2:
                    mapping[s_actor] = best_match

        return mapping

    def _concept_similarity(self, attrs_a: Dict[str, Any],
                             attrs_b: Dict[str, Any]) -> float:
        """Compute similarity between two concept attribute dicts."""
        if not attrs_a or not attrs_b:
            return 0.0
        shared_keys = set(attrs_a.keys()) & set(attrs_b.keys())
        all_keys = set(attrs_a.keys()) | set(attrs_b.keys())
        if not all_keys:
            return 0.0

        matches = 0
        for k in shared_keys:
            if attrs_a[k] == attrs_b[k]:
                matches += 1
        return matches / len(all_keys)

    def _generate_analogy_explanation(self, source: Domain, target: Domain,
                                       mapping: Dict[str, str],
                                       shared_relations: Set[str]) -> str:
        """Generate human-readable explanation of an analogy."""
        parts = [
            f"Structural analogy between '{source.name}' and '{target.name}':",
        ]

        if mapping:
            for s_concept, t_concept in list(mapping.items())[:5]:
                parts.append(f"  {s_concept} ↔ {t_concept}")

        if shared_relations:
            parts.append(f"Shared relational structure: {', '.join(list(shared_relations)[:5])}")

        return "\n".join(parts)

    # ── Core: First Principles ──────────────────────────────────────────

    def first_principles(self, problem: str) -> dict:
        """
        Decompose a problem to its fundamental components.

        Strips away assumptions, conventions, and inherited wisdom
        to identify the irreducible truths at the foundation of a problem.

        Args:
            problem: Description of the problem to decompose

        Returns:
            Dict with fundamental truths, assumptions identified,
            decomposition tree, and rebuilt solution space
        """
        with self._lock:
            self._session_ops += 1

            # Step 1: Identify assumptions embedded in problem statement
            assumptions = self._extract_assumptions(problem)

            # Step 2: Identify fundamental constraints
            constraints = self._identify_constraints(problem)

            # Step 3: Decompose into irreducible components
            components = self._decompose_to_components(problem)

            # Step 4: Identify what is known vs unknown
            knowns = [c for c in components if c.get("confidence", 0) > 0.6]
            unknowns = [c for c in components if c.get("confidence", 0) <= 0.6]

            # Step 5: Rebuild solution space from fundamentals
            solution_space = self._rebuild_from_fundamentals(
                components, constraints, assumptions
            )

            result = {
                "problem": problem,
                "assumptions": assumptions,
                "constraints": constraints,
                "components": components,
                "knowns": knowns,
                "unknowns": unknowns,
                "solution_space": solution_space,
                "timestamp": _now(),
            }

            self._first_principles.append({
                "problem": problem[:200],
                "num_assumptions": len(assumptions),
                "num_components": len(components),
                "timestamp": _now(),
            })
            self._meta["total_first_principles"] += 1
            self._save()

            return result

    def _extract_assumptions(self, problem: str) -> List[dict]:
        """Extract hidden assumptions from problem description."""
        assumptions = []
        words = problem.lower().split()

        # Detect assumption-laden phrases
        assumption_markers = [
            ("everyone knows", "common_belief"),
            ("obviously", "unexamined_premise"),
            ("always", "overgeneralization"),
            ("never", "overgeneralization"),
            ("impossible", "limiting_belief"),
            ("can't", "limiting_belief"),
            ("should", "normative_assumption"),
            ("must", "normative_assumption"),
            ("have to", "normative_assumption"),
            ("because", "causal_assumption"),
            ("is the only", "exclusivity_assumption"),
        ]

        problem_lower = problem.lower()
        for marker, atype in assumption_markers:
            if marker in problem_lower:
                idx = problem_lower.index(marker)
                context = problem[max(0, idx - 30):idx + len(marker) + 50]
                assumptions.append({
                    "type": atype,
                    "marker": marker,
                    "context": context.strip(),
                    "question": f"What if {marker} isn't true?",
                })

        return assumptions

    def _identify_constraints(self, problem: str) -> List[dict]:
        """Identify fundamental constraints (physical, logical, resource)."""
        constraints = []
        problem_lower = problem.lower()

        constraint_patterns = [
            ("time", "temporal"),
            ("money", "financial"),
            ("resource", "resource"),
            ("memory", "computational"),
            ("bandwidth", "computational"),
            ("energy", "physical"),
            ("speed", "physical"),
            ("law", "legal"),
            ("regulation", "regulatory"),
            ("physics", "physical"),
            ("gravity", "physical"),
            ("thermodynamic", "physical"),
            ("entropy", "physical"),
        ]

        for keyword, ctype in constraint_patterns:
            if keyword in problem_lower:
                constraints.append({
                    "type": ctype,
                    "keyword": keyword,
                    "description": f"Constraint related to: {keyword}",
                })

        return constraints

    def _decompose_to_components(self, problem: str) -> List[dict]:
        """Decompose problem into irreducible sub-components."""
        components = []
        sentences = [s.strip() for s in problem.replace("?", ".").split(".") if s.strip()]

        for i, sentence in enumerate(sentences):
            words = sentence.split()
            # Each sentence/concept becomes a component
            component = {
                "id": f"c{i}",
                "statement": sentence,
                "word_count": len(words),
                "complexity": "high" if len(words) > 15 else "medium" if len(words) > 7 else "low",
                "confidence": 0.8 if len(words) > 3 else 0.4,
                "dependencies": [],
            }

            # Check for dependencies on other components
            for j, other in enumerate(sentences):
                if i != j:
                    shared = set(sentence.lower().split()) & set(other.lower().split())
                    if len(shared) >= 2:
                        component["dependencies"].append(f"c{j}")

            components.append(component)

        return components

    def _rebuild_from_fundamentals(self, components: List[dict],
                                    constraints: List[dict],
                                    assumptions: List[dict]) -> List[dict]:
        """Rebuild solution space from fundamental components."""
        solutions = []

        # Strategy 1: Remove each assumption and see what opens up
        for assumption in assumptions[:3]:
            solutions.append({
                "strategy": "assumption_removal",
                "removed_assumption": assumption.get("marker", ""),
                "new_possibility": f"If we reject '{assumption.get('marker', '')}', "
                                   f"we could explore: {assumption.get('question', '')}",
                "novelty": 0.7,
            })

        # Strategy 2: Relax constraints
        for constraint in constraints[:2]:
            solutions.append({
                "strategy": "constraint_relaxation",
                "relaxed_constraint": constraint.get("keyword", ""),
                "new_possibility": f"What if {constraint.get('keyword', '')} were not a limitation?",
                "novelty": 0.6,
            })

        # Strategy 3: Recombine components
        if len(components) >= 2:
            for i in range(min(3, len(components) - 1)):
                solutions.append({
                    "strategy": "recombination",
                    "components": [components[i]["id"], components[i + 1]["id"]],
                    "new_possibility": f"Combine: '{components[i]['statement'][:50]}' "
                                       f"with '{components[i+1]['statement'][:50]}'",
                    "novelty": 0.5,
                })

        return solutions

    # ── Core: Counterfactual ────────────────────────────────────────────

    def counterfactual(self, scenario: str, change: str) -> dict:
        """
        Explore "what if X had been different?" reasoning.

        Models the effects of a hypothetical change on a scenario,
        tracing downstream consequences through known causal links.

        Args:
            scenario: Description of the current/referenced scenario
            change: The hypothetical change to introduce

        Returns:
            Dict with original scenario, change, predicted effects,
            divergence points, and plausibility assessment
        """
        with self._lock:
            self._session_ops += 1

            # Identify what the change directly affects
            direct_effects = self._trace_direct_effects(change)

            # Trace downstream effects through causal links
            downstream = self._trace_downstream_effects(direct_effects)

            # Identify divergence points from the original scenario
            divergences = self._identify_divergences(scenario, change, direct_effects)

            # Assess plausibility based on causal coherence
            plausibility = self._assess_counterfactual_plausibility(
                scenario, change, direct_effects, downstream
            )

            # Generate alternative outcomes
            alternatives = self._generate_alternative_outcomes(
                scenario, change, downstream
            )

            result = {
                "original_scenario": scenario,
                "hypothetical_change": change,
                "direct_effects": direct_effects,
                "downstream_effects": downstream,
                "divergence_points": divergences,
                "plausibility": plausibility,
                "alternative_outcomes": alternatives,
                "timestamp": _now(),
            }

            self._counterfactuals.append({
                "scenario": scenario[:200],
                "change": change[:200],
                "num_effects": len(direct_effects) + len(downstream),
                "plausibility": plausibility,
                "timestamp": _now(),
            })
            self._meta["total_counterfactuals"] += 1
            self._save()

            return result

    def _trace_direct_effects(self, change: str) -> List[dict]:
        """Find effects directly caused by the hypothetical change."""
        effects = []
        change_lower = change.lower()

        for link in self._causal_links:
            cause_lower = link.cause.lower()
            # Simple keyword overlap check
            change_words = set(change_lower.split())
            cause_words = set(cause_lower.split())
            overlap = change_words & cause_words
            if len(overlap) >= max(1, min(len(change_words), len(cause_words)) // 3):
                effects.append({
                    "effect": link.effect,
                    "domain": link.domain,
                    "strength": link.strength,
                    "mechanism": link.mechanism,
                    "confidence": min(1.0, len(overlap) / max(len(change_words), 1) + 0.3),
                })

        return effects

    def _trace_downstream_effects(self, direct_effects: List[dict],
                                   depth: int = 3) -> List[dict]:
        """Trace cascading effects through causal chain."""
        downstream = []
        visited = set()

        frontier = [e["effect"] for e in direct_effects]
        for d in range(depth):
            next_frontier = []
            for effect_name in frontier:
                if effect_name in visited:
                    continue
                visited.add(effect_name)

                for link in self._causal_links:
                    if link.cause.lower() == effect_name.lower():
                        downstream.append({
                            "cause": link.cause,
                            "effect": link.effect,
                            "depth": d + 1,
                            "strength": link.strength * (0.8 ** d),  # attenuate with depth
                            "domain": link.domain,
                        })
                        next_frontier.append(link.effect)

            frontier = next_frontier

        return downstream

    def _identify_divergences(self, scenario: str, change: str,
                               direct_effects: List[dict]) -> List[dict]:
        """Identify key divergence points from original trajectory."""
        divergences = []

        # Each direct effect is a divergence point
        for i, effect in enumerate(direct_effects[:5]):
            divergences.append({
                "point": f"After '{change[:50]}', {effect['effect'][:50]}",
                "magnitude": effect.get("strength", 0.5),
                "reversibility": 1.0 - effect.get("strength", 0.5),
                "order": i + 1,
            })

        return divergences

    def _assess_counterfactual_plausibility(self, scenario: str, change: str,
                                             direct: List[dict],
                                             downstream: List[dict]) -> float:
        """Assess how plausible the counterfactual scenario is."""
        if not direct:
            return 0.3  # Low plausibility if no causal connections found

        # Factor 1: Number of causal connections
        connection_score = min(1.0, len(direct) / 3.0)

        # Factor 2: Average strength of causal links
        avg_strength = sum(e.get("strength", 0) for e in direct) / max(len(direct), 1)

        # Factor 3: Coherence (do downstream effects form consistent picture?)
        coherence = 1.0 if len(downstream) > 0 else 0.5

        # Factor 4: Attenuation (effects should attenuate, not amplify unboundedly)
        if downstream:
            strengths = [e.get("strength", 0) for e in downstream]
            attenuation_ok = all(s <= 1.0 for s in strengths)
            attenuation_score = 1.0 if attenuation_ok else 0.6
        else:
            attenuation_score = 0.7

        plausibility = (
            connection_score * 0.3 +
            avg_strength * 0.3 +
            coherence * 0.2 +
            attenuation_score * 0.2
        )

        return round(min(1.0, plausibility), 3)

    def _generate_alternative_outcomes(self, scenario: str, change: str,
                                        downstream: List[dict]) -> List[dict]:
        """Generate alternative outcomes based on downstream effects."""
        alternatives = []

        if downstream:
            # Outcome 1: Following the strongest causal path
            strongest = max(downstream, key=lambda e: e.get("strength", 0))
            alternatives.append({
                "description": f"Most likely path: leads to '{strongest['effect']}'",
                "probability": strongest.get("strength", 0.5),
                "path": "strongest_causal",
            })

            # Outcome 2: Weakest link breaks (butterfly effect)
            weakest = min(downstream, key=lambda e: e.get("strength", 0))
            alternatives.append({
                "description": f"Butterfly effect: small change at '{weakest['cause']}' "
                               f"amplifies to '{weakest['effect']}'",
                "probability": weakest.get("strength", 0.3),
                "path": "butterfly",
            })

        return alternatives

    # ── Core: Causal Chain ──────────────────────────────────────────────

    def causal_chain(self, event: str,
                     depth: int = DEFAULT_CHAIN_DEPTH) -> dict:
        """
        Trace cause-effect chains from an event across domains.

        Follows causal links both upstream (causes) and downstream
        (effects) to build a complete picture of causal structure.

        Args:
            event: The event to trace from
            depth: Maximum chain depth (default 5, max 10)

        Returns:
            Dict with upstream causes, downstream effects, and chain visualization
        """
        depth = min(depth, MAX_CHAIN_DEPTH)

        with self._lock:
            self._session_ops += 1

            # Trace upstream (what caused this event?)
            upstream = self._trace_upstream(event, depth)

            # Trace downstream (what does this event cause?)
            downstream = self._trace_downstream(event, depth)

            # Find cross-domain links
            cross_domain = self._find_cross_domain_links(event)

            # Identify root causes
            root_causes = self._identify_root_causes(upstream)

            # Identify ultimate effects
            ultimate_effects = self._identify_ultimate_effects(downstream)

            result = {
                "event": event,
                "upstream_chain": upstream,
                "downstream_chain": downstream,
                "cross_domain_links": cross_domain,
                "root_causes": root_causes,
                "ultimate_effects": ultimate_effects,
                "chain_depth_up": max((u.get("depth", 0) for u in upstream), default=0),
                "chain_depth_down": max((d.get("depth", 0) for d in downstream), default=0),
                "timestamp": _now(),
            }

            self._meta["total_causal_chains"] += 1
            self._save()

            return result

    def _trace_upstream(self, event: str, depth: int) -> List[dict]:
        """Trace causes leading to an event."""
        chain = []
        visited = set()
        frontier = [event]

        for d in range(depth):
            next_frontier = []
            for current in frontier:
                if current in visited:
                    continue
                visited.add(current)

                for link in self._causal_links:
                    if link.effect.lower() == current.lower() or \
                       current.lower() in link.effect.lower():
                        chain.append({
                            "cause": link.cause,
                            "effect": link.effect,
                            "depth": d + 1,
                            "direction": "upstream",
                            "strength": link.strength,
                            "domain": link.domain,
                            "mechanism": link.mechanism,
                        })
                        next_frontier.append(link.cause)

            frontier = next_frontier

        return chain

    def _trace_downstream(self, event: str, depth: int) -> List[dict]:
        """Trace effects caused by an event."""
        chain = []
        visited = set()
        frontier = [event]

        for d in range(depth):
            next_frontier = []
            for current in frontier:
                if current in visited:
                    continue
                visited.add(current)

                for link in self._causal_links:
                    if link.cause.lower() == current.lower() or \
                       current.lower() in link.cause.lower():
                        chain.append({
                            "cause": link.cause,
                            "effect": link.effect,
                            "depth": d + 1,
                            "direction": "downstream",
                            "strength": link.strength,
                            "domain": link.domain,
                            "mechanism": link.mechanism,
                        })
                        next_frontier.append(link.effect)

            frontier = next_frontier

        return chain

    def _find_cross_domain_links(self, event: str) -> List[dict]:
        """Find causal links that cross domain boundaries."""
        cross = []
        event_lower = event.lower()

        # Group links by domain
        domain_links: Dict[str, List[CausalLink]] = defaultdict(list)
        for link in self._causal_links:
            domain_links[link.domain].append(link)

        # Find links where cause or effect matches event across domains
        domains_involved = set()
        for link in self._causal_links:
            if event_lower in link.cause.lower() or event_lower in link.effect.lower():
                domains_involved.add(link.domain)

        if len(domains_involved) > 1:
            for domain in domains_involved:
                for link in domain_links[domain]:
                    if event_lower in link.cause.lower() or event_lower in link.effect.lower():
                        cross.append({
                            "cause": link.cause,
                            "effect": link.effect,
                            "domain": link.domain,
                            "strength": link.strength,
                        })

        return cross

    def _identify_root_causes(self, upstream: List[dict]) -> List[str]:
        """Identify root causes (causes with no further upstream)."""
        if not upstream:
            return []

        all_effects = {u["effect"] for u in upstream}
        all_causes = {u["cause"] for u in upstream}

        # Root causes are causes that aren't effects of anything else in the chain
        root_causes = all_causes - all_effects
        return list(root_causes)[:10]

    def _identify_ultimate_effects(self, downstream: List[dict]) -> List[str]:
        """Identify ultimate effects (effects with no further downstream)."""
        if not downstream:
            return []

        all_causes = {d["cause"] for d in downstream}
        all_effects = {d["effect"] for d in downstream}

        # Ultimate effects are effects that aren't causes of anything else
        ultimate = all_effects - all_causes
        return list(ultimate)[:10]

    # ── Core: Cross-Domain Transfer ─────────────────────────────────────

    def cross_domain_transfer(self, problem: str,
                               known_domains: List[str]) -> List[dict]:
        """
        Apply solutions from known domains to a novel problem.

        Identifies which known domains have structural similarities
        to the problem space, then transfers solution patterns.

        Args:
            problem: Description of the problem to solve
            known_domains: List of domain names with known solutions

        Returns:
            List of transfer suggestions with source domain, pattern,
            applicability score, and adaptation guidance
        """
        with self._lock:
            self._session_ops += 1

            transfers = []
            problem_features = self._extract_problem_features(problem)

            for domain_name in known_domains:
                domain = self._domains.get(domain_name)
                if not domain:
                    continue

                # Assess structural match between problem and domain
                match_score = self._domain_problem_match(problem_features, domain)

                if match_score < STRUCTURAL_SIMILARITY_THRESHOLD:
                    continue

                # Extract transferable patterns from domain
                patterns = self._extract_transferable_patterns(domain, problem_features)

                for pattern in patterns:
                    applicability = match_score * pattern.get("relevance", 0.5)
                    transfer = {
                        "source_domain": domain_name,
                        "pattern": pattern["description"],
                        "applicability": round(applicability, 3),
                        "adaptation_guidance": self._generate_adaptation_guidance(
                            domain_name, problem, pattern
                        ),
                        "confidence": round(min(1.0, applicability + 0.1), 3),
                    }
                    transfers.append(transfer)

            # Sort by applicability
            transfers.sort(key=lambda t: t["applicability"], reverse=True)

            # Record
            self._transfers.extend([{
                "problem": problem[:200],
                "domain": t["source_domain"],
                "applicability": t["applicability"],
                "timestamp": _now(),
            } for t in transfers[:5]])
            self._meta["total_transfers"] += len(transfers)
            self._save()

            return transfers[:10]

    def _extract_problem_features(self, problem: str) -> Dict[str, Any]:
        """Extract abstract features from a problem description."""
        words = problem.lower().split()
        return {
            "word_count": len(words),
            "unique_words": len(set(words)),
            "has_constraints": any(w in problem.lower() for w in
                                   ["limit", "constraint", "must", "cannot", "only"]),
            "has_optimization": any(w in problem.lower() for w in
                                    ["maximize", "minimize", "optimize", "best", "fastest"]),
            "has_sequence": any(w in problem.lower() for w in
                                ["then", "after", "before", "first", "next", "step"]),
            "has_tradeoff": any(w in problem.lower() for w in
                                ["but", "however", "tradeoff", "versus", "vs"]),
            "keywords": set(words),
        }

    def _domain_problem_match(self, problem_features: Dict[str, Any],
                               domain: Domain) -> float:
        """Score how well a domain matches a problem's structure."""
        score = 0.0
        factors = 0

        # Check keyword overlap with domain concepts
        problem_words = problem_features.get("keywords", set())
        domain_words = set()
        for concept in domain.concepts:
            domain_words.update(concept.lower().split())
        for rel in domain.relations:
            domain_words.update(rel[0].lower().split())
            domain_words.update(rel[2].lower().split())

        if problem_words and domain_words:
            overlap = len(problem_words & domain_words)
            score += overlap / max(len(problem_words), 1)
            factors += 1

        # Check structural similarity (number of relations)
        if domain.relations:
            structural_richness = min(1.0, len(domain.relations) / 10.0)
            score += structural_richness
            factors += 1

        return score / max(factors, 1)

    def _extract_transferable_patterns(self, domain: Domain,
                                        problem_features: Dict[str, Any]) -> List[dict]:
        """Extract patterns from a domain that could transfer to the problem."""
        patterns = []

        # Each relation in the domain is a potentially transferable pattern
        for subj, rel, obj in domain.relations:
            relevance = 0.5
            # Boost relevance if keywords match
            problem_words = problem_features.get("keywords", set())
            if subj.lower() in problem_words or obj.lower() in problem_words:
                relevance = 0.8

            patterns.append({
                "description": f"In {domain.name}: {subj} --[{rel}]--> {obj}",
                "relation": rel,
                "relevance": relevance,
            })

        return patterns[:5]

    def _generate_adaptation_guidance(self, source_domain: str,
                                       problem: str,
                                       pattern: dict) -> str:
        """Generate guidance for adapting a pattern to the problem."""
        return (
            f"Adapt '{pattern.get('description', 'pattern')}' from {source_domain} "
            f"by mapping the relational structure to your problem context. "
            f"Preserve the {pattern.get('relation', 'core')} relationship while "
            f"replacing domain-specific entities."
        )

    # ── Core: Emergent Insight ──────────────────────────────────────────

    def emergent_insight(self, concepts: List[str]) -> dict:
        """
        Combine unrelated concepts to generate novel insights.

        Uses conceptual blending: finds unexpected connections between
        disparate ideas to produce emergent meaning that neither
        concept contains alone.

        Args:
            concepts: List of concept strings to combine

        Returns:
            Dict with blended concepts, novel connections,
            emergent properties, and insight statement
        """
        with self._lock:
            self._session_ops += 1

            if len(concepts) < 2:
                return {
                    "concepts": concepts,
                    "insight": "Need at least 2 concepts for blending.",
                    "novelty": 0.0,
                }

            # Find existing connections between concepts
            connections = self._find_concept_connections(concepts)

            # Find gaps (missing connections)
            gaps = self._find_connection_gaps(concepts, connections)

            # Generate emergent properties from combination
            emergent_props = self._identify_emergent_properties(concepts, connections)

            # Synthesize insight statement
            insight_statement = self._synthesize_insight(
                concepts, connections, emergent_props
            )

            # Assess novelty
            novelty = self._assess_novelty(concepts, connections)

            result = {
                "concepts": concepts,
                "connections_found": connections,
                "gaps": gaps,
                "emergent_properties": emergent_props,
                "insight": insight_statement,
                "novelty": round(novelty, 3),
                "timestamp": _now(),
            }

            self._insights.append({
                "concepts": concepts,
                "novelty": novelty,
                "insight": insight_statement[:200],
                "timestamp": _now(),
            })
            self._meta["total_insights"] += 1
            self._save()

            return result

    def _find_concept_connections(self, concepts: List[str]) -> List[dict]:
        """Find existing connections between concepts in stored knowledge."""
        connections = []

        for i, c1 in enumerate(concepts):
            for j, c2 in enumerate(concepts):
                if i >= j:
                    continue

                # Check causal links
                for link in self._causal_links:
                    c1_match = c1.lower() in link.cause.lower() or c1.lower() in link.effect.lower()
                    c2_match = c2.lower() in link.cause.lower() or c2.lower() in link.effect.lower()
                    if c1_match and c2_match:
                        connections.append({
                            "concepts": [c1, c2],
                            "type": "causal",
                            "detail": f"{link.cause} → {link.effect}",
                            "strength": link.strength,
                        })

                # Check domain co-occurrence
                for domain in self._domains.values():
                    c1_in = c1.lower() in [k.lower() for k in domain.concepts]
                    c2_in = c2.lower() in [k.lower() for k in domain.concepts]
                    if c1_in and c2_in:
                        connections.append({
                            "concepts": [c1, c2],
                            "type": "co_occurrence",
                            "detail": f"Both in domain '{domain.name}'",
                            "strength": 0.5,
                        })

        return connections

    def _find_connection_gaps(self, concepts: List[str],
                               connections: List[dict]) -> List[dict]:
        """Identify gaps where concepts lack connections."""
        connected_pairs = set()
        for conn in connections:
            pair = tuple(sorted(conn["concepts"]))
            connected_pairs.add(pair)

        gaps = []
        for i, c1 in enumerate(concepts):
            for j, c2 in enumerate(concepts):
                if i >= j:
                    continue
                pair = tuple(sorted([c1, c2]))
                if pair not in connected_pairs:
                    gaps.append({
                        "concepts": list(pair),
                        "opportunity": f"Bridge between '{c1}' and '{c2}' "
                                       f"could yield novel insight",
                    })

        return gaps

    def _identify_emergent_properties(self, concepts: List[str],
                                       connections: List[dict]) -> List[str]:
        """Identify properties that emerge from concept combination."""
        props = []

        # If concepts span multiple domains, cross-pollination is possible
        domains_involved = set()
        for concept in concepts:
            for domain in self._domains.values():
                if concept.lower() in [k.lower() for k in domain.concepts]:
                    domains_involved.add(domain.name)

        if len(domains_involved) > 1:
            props.append(
                f"Cross-domain synthesis: concepts span {', '.join(domains_involved)} — "
                f"combining frameworks from different fields may produce novel approaches"
            )

        # If there are gaps, those are emergent opportunities
        if len(concepts) >= 3:
            props.append(
                f"Ternary blend: {len(concepts)}-way combination increases "
                f"combinatorial novelty exponentially"
            )

        # Strong connections suggest deep structural resonance
        strong = [c for c in connections if c.get("strength", 0) > 0.7]
        if strong:
            props.append(
                f"Strong resonance: {len(strong)} high-strength connections suggest "
                f"deep structural similarity worth exploiting"
            )

        return props

    def _synthesize_insight(self, concepts: List[str],
                            connections: List[dict],
                            emergent_props: List[str]) -> str:
        """Synthesize a human-readable insight statement."""
        parts = [f"Blending concepts: {', '.join(concepts[:5])}"]

        if connections:
            strongest = max(connections, key=lambda c: c.get("strength", 0))
            parts.append(
                f"Strongest bridge: {strongest['concepts'][0]} ↔ "
                f"{strongest['concepts'][1]} ({strongest['type']})"
            )

        if emergent_props:
            parts.append(f"Emergent: {emergent_props[0][:100]}")

        if not connections and not emergent_props:
            parts.append(
                "No existing connections found — this combination is highly novel "
                "and may require creative bridging to unlock value"
            )

        return " | ".join(parts)

    def _assess_novelty(self, concepts: List[str],
                        connections: List[dict]) -> float:
        """Assess how novel this concept combination is."""
        # More connections = less novel (already explored)
        # Fewer connections = more novel
        connection_factor = 1.0 - min(1.0, len(connections) / (len(concepts) * (len(concepts) - 1) / 2))

        # More concepts = potentially more novel
        combination_factor = min(1.0, len(concepts) / 5.0)

        # Cross-domain combinations are more novel
        domains = set()
        for concept in concepts:
            for domain in self._domains.values():
                if concept.lower() in [k.lower() for k in domain.concepts]:
                    domains.add(domain.name)
        domain_factor = min(1.0, len(domains) / max(len(concepts), 1))

        novelty = (
            connection_factor * 0.5 +
            combination_factor * 0.2 +
            domain_factor * 0.3
        )

        return min(1.0, novelty)

    # ── Core: Abstract Pattern ──────────────────────────────────────────

    def abstract_pattern(self, instances: List[str]) -> dict:
        """
        Find common patterns across diverse instances.

        Identifies the abstract structure shared by a set of
        specific instances, stripping away surface details.

        Args:
            instances: List of instance descriptions to find patterns in

        Returns:
            Dict with common structure, variations, abstraction level,
            and the generalized pattern description
        """
        with self._lock:
            self._session_ops += 1

            if len(instances) < 2:
                return {
                    "instances": instances,
                    "pattern": "Need at least 2 instances to abstract.",
                    "abstraction_level": 0.0,
                }

            # Extract features from each instance
            instance_features = []
            for inst in instances:
                features = {
                    "words": set(inst.lower().split()),
                    "length": len(inst.split()),
                    "has_numbers": any(c.isdigit() for c in inst),
                    "has_negation": any(w in inst.lower() for w in
                                        ["not", "no", "never", "without", "fail"]),
                    "has_question": "?" in inst,
                }
                instance_features.append(features)

            # Find common words (potential shared structure)
            common_words = instance_features[0]["words"].copy()
            for feats in instance_features[1:]:
                common_words &= feats["words"]

            # Remove stop words
            stop_words = {"the", "a", "an", "is", "are", "was", "were", "be",
                          "been", "being", "have", "has", "had", "do", "does",
                          "did", "will", "would", "could", "should", "may",
                          "might", "can", "shall", "to", "of", "in", "for",
                          "on", "with", "at", "by", "from", "it", "this",
                          "that", "and", "or", "but", "if", "as", "into"}
            structural_words = common_words - stop_words

            # Find common structural features
            common_structural = {
                "has_numbers": all(f["has_numbers"] for f in instance_features),
                "has_negation": all(f["has_negation"] for f in instance_features),
                "has_question": all(f["has_question"] for f in instance_features),
                "avg_length": sum(f["length"] for f in instance_features) / len(instance_features),
            }

            # Identify variations (what differs)
            variations = []
            for i, inst in enumerate(instances):
                unique_words = instance_features[i]["words"] - common_words
                if unique_words:
                    variations.append({
                        "instance_index": i,
                        "unique_elements": list(unique_words)[:10],
                        "text": inst[:100],
                    })

            # Compute abstraction level
            if structural_words:
                abstraction = 1.0 - (len(structural_words) /
                                     max(sum(f["length"] for f in instance_features) / len(instance_features), 1))
            else:
                abstraction = 0.8  # High abstraction when no common words

            # Generate pattern description
            pattern_desc = self._describe_abstract_pattern(
                instances, structural_words, common_structural
            )

            result = {
                "instances": [i[:200] for i in instances],
                "common_structure": list(structural_words)[:20],
                "common_features": common_structural,
                "variations": variations[:5],
                "abstraction_level": round(max(0, abstraction), 3),
                "pattern_description": pattern_desc,
                "timestamp": _now(),
            }

            self._patterns.append({
                "num_instances": len(instances),
                "common_count": len(structural_words),
                "abstraction_level": result["abstraction_level"],
                "timestamp": _now(),
            })
            self._save()

            return result

    def _describe_abstract_pattern(self, instances: List[str],
                                    common_words: Set[str],
                                    structural: dict) -> str:
        """Generate a description of the abstract pattern."""
        parts = []

        if common_words:
            parts.append(f"Shared vocabulary: {', '.join(list(common_words)[:8])}")

        if structural.get("has_numbers"):
            parts.append("All instances involve numerical/quantitative elements")
        if structural.get("has_negation"):
            parts.append("All instances involve negation/constraints")
        if structural.get("has_question"):
            parts.append("All instances are interrogative")

        avg_len = structural.get("avg_length", 0)
        if avg_len > 20:
            parts.append("Pattern involves complex, detailed descriptions")
        elif avg_len < 5:
            parts.append("Pattern involves terse, concentrated expressions")

        return " | ".join(parts) if parts else "No strong abstract pattern detected"

    # ── Causal Link Registration ────────────────────────────────────────

    def add_causal_link(self, cause: str, effect: str,
                        domain: str = "general",
                        strength: float = 0.7,
                        mechanism: str = ""):
        """Register a cause-effect link for causal chain reasoning."""
        with self._lock:
            link = CausalLink(cause=cause, effect=effect, domain=domain,
                              strength=strength, mechanism=mechanism)
            self._causal_links.append(link)
            if len(self._causal_links) > MAX_CAUSAL_CHAINS:
                self._causal_links = self._causal_links[-MAX_CAUSAL_CHAINS:]
            self._save()

    # ── Format & Stats ──────────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """Format abstraction engine state for system prompt injection."""
        stats = self.get_stats()

        parts = [
            "[ABSTRACTION ENGINE — Cross-domain reasoning]",
            f"Domains: {stats['domains']} | Analogies: {stats['total_analogies']} | "
            f"Causal links: {stats['causal_links']}",
            f"Insights generated: {stats['total_insights']} | "
            f"Cross-transfers: {stats['total_transfers']}",
            f"First-principles analyses: {stats['total_first_principles']} | "
            f"Counterfactuals: {stats['total_counterfactuals']}",
        ]

        domain_list = self.list_domains()
        if domain_list:
            parts.append(f"Known domains: {', '.join(domain_list[:8])}")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "[...]"
        return result

    def get_stats(self) -> dict:
        """Get abstraction engine statistics."""
        with self._lock:
            return {
                "domains": len(self._domains),
                "total_analogies": self._meta.get("total_analogies", 0),
                "causal_links": len(self._causal_links),
                "total_insights": self._meta.get("total_insights", 0),
                "total_transfers": self._meta.get("total_transfers", 0),
                "total_counterfactuals": self._meta.get("total_counterfactuals", 0),
                "total_first_principles": self._meta.get("total_first_principles", 0),
                "total_patterns": len(self._patterns),
                "session_operations": self._session_ops,
            }


# ── Singleton ───────────────────────────────────────────────────────────────

_abstraction_engine = None
_abstraction_lock = threading.Lock()


def get_abstraction_engine() -> AbstractionEngine:
    """Get singleton AbstractionEngine instance."""
    global _abstraction_engine
    if _abstraction_engine is None:
        with _abstraction_lock:
            if _abstraction_engine is None:
                _abstraction_engine = AbstractionEngine()
    return _abstraction_engine
