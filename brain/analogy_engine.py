#!/usr/bin/env python3
"""
analogy_engine.py — FRIDAY Analogical Reasoning Engine
=======================================================

Implements Gentner's Structure Mapping Theory for fluid intelligence.
Analogical reasoning is the #1 predictor of ARC-AGI benchmark performance.

Core concepts:
  - RelationalStructure: domain representation (objects, attributes, relations)
  - StructureMapping: source→target correspondence with systematicity scoring
  - AnalogyEngine: find, score, transfer, and learn from analogies

Integrations:
  - brain.procedural_memory — successful analogies create reusable procedures
  - brain.curiosity — novel analogies boost exploration curiosity
"""

import json
import math
import re
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

BRAIN_DIR = Path(__file__).parent.resolve()
ANALOGY_FILE = BRAIN_DIR / "analogy_data.json"

# Configuration
MAX_LIBRARY_SIZE = 200
MIN_ANALOGY_SUCCESS = 0.3
DECAY_DAYS = 120
MAX_CANDIDATES = 50
SYSTEMATICITY_WEIGHT = 0.45
STRUCTURAL_WEIGHT = 0.35
SEMANTIC_WEIGHT = 0.20


# ═══════════════════════════════════════════════════════════════════════
# Data Structures
# ═══════════════════════════════════════════════════════════════════════

class RelationalStructure:
    """
    Represents a domain as a structured graph:
      - objects: named entities in the domain
      - attributes: object → set of properties (surface features)
      - relations: list of (relation_name, (obj1, obj2, ...), strength)
    """

    def __init__(self, name: str = ""):
        self.name = name
        self.objects: Set[str] = set()
        self.attributes: Dict[str, Set[str]] = defaultdict(set)
        self.relations: List[Tuple[str, Tuple[str, ...], float]] = []

    def add_object(self, obj: str, attrs: Optional[Set[str]] = None):
        self.objects.add(obj)
        if attrs:
            self.attributes[obj].update(attrs)

    def add_relation(self, relation_name: str, objects: Tuple[str, ...],
                     strength: float = 1.0):
        for o in objects:
            self.objects.add(o)
        self.relations.append((relation_name, objects, strength))

    def get_relation_graph(self) -> Dict[str, List[Tuple[str, ...]]]:
        """Build adjacency: relation_name → list of object tuples."""
        graph: Dict[str, List[Tuple[str, ...]]] = defaultdict(list)
        for rel_name, objs, _ in self.relations:
            graph[rel_name].append(objs)
        return dict(graph)

    def object_relations(self, obj: str) -> List[Tuple[str, Tuple[str, ...], float]]:
        """All relations involving a specific object."""
        return [(n, o, s) for n, o, s in self.relations if obj in o]

    def is_empty(self) -> bool:
        return len(self.objects) == 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "objects": list(self.objects),
            "attributes": {k: list(v) for k, v in self.attributes.items()},
            "relations": [
                {"name": n, "objects": list(o), "strength": s}
                for n, o, s in self.relations
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RelationalStructure":
        rs = cls(name=data.get("name", ""))
        rs.objects = set(data.get("objects", []))
        rs.attributes = defaultdict(set)
        for k, v in data.get("attributes", {}).items():
            rs.attributes[k] = set(v)
        for r in data.get("relations", []):
            rs.relations.append((r["name"], tuple(r["objects"]), r.get("strength", 1.0)))
        return rs

    def __repr__(self):
        return (f"RelationalStructure(name={self.name!r}, "
                f"objects={len(self.objects)}, relations={len(self.relations)})")


class StructureMapping:
    """
    A mapping from source domain to target domain.
    Encodes object correspondences, relation correspondences, and quality scores.
    """

    def __init__(self, source_name: str = "", target_name: str = ""):
        self.source_name = source_name
        self.target_name = target_name
        self.object_mappings: Dict[str, str] = {}
        self.relation_mappings: List[Tuple[Tuple, Tuple, float]] = []
        # (source_relation_tuple, target_relation_tuple, score)
        self.systematicity_score: float = 0.0
        self.structural_match_score: float = 0.0
        self.semantic_bonus: float = 0.0
        self.total_score: float = 0.0
        self.metadata: Dict[str, Any] = {}

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "target_name": self.target_name,
            "object_mappings": self.object_mappings,
            "relation_mappings": [
                {"source": list(s), "target": list(t), "score": sc}
                for s, t, sc in self.relation_mappings
            ],
            "systematicity_score": self.systematicity_score,
            "structural_match_score": self.structural_match_score,
            "semantic_bonus": self.semantic_bonus,
            "total_score": self.total_score,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StructureMapping":
        sm = cls(
            source_name=data.get("source_name", ""),
            target_name=data.get("target_name", ""),
        )
        sm.object_mappings = data.get("object_mappings", {})
        for rm in data.get("relation_mappings", []):
            sm.relation_mappings.append((
                tuple(rm["source"]), tuple(rm["target"]), rm["score"]
            ))
        sm.systematicity_score = data.get("systematicity_score", 0.0)
        sm.structural_match_score = data.get("structural_match_score", 0.0)
        sm.semantic_bonus = data.get("semantic_bonus", 0.0)
        sm.total_score = data.get("total_score", 0.0)
        sm.metadata = data.get("metadata", {})
        return sm

    def __repr__(self):
        return (f"StructureMapping({self.source_name!r}→{self.target_name!r}, "
                f"score={self.total_score:.3f})")


class AnalogyTemplate:
    """A stored analogy for reuse — the library entry."""

    def __init__(self, template_id: str, source: RelationalStructure,
                 target: RelationalStructure, mapping: StructureMapping,
                 outcome: str = ""):
        self.template_id = template_id
        self.source = source
        self.target = target
        self.mapping = mapping
        self.outcome = outcome
        self.created = datetime.now().isoformat()
        self.last_used = self.created
        self.success_count = 0
        self.failure_count = 0
        self.total_uses = 0

    @property
    def success_rate(self) -> float:
        return self.success_count / self.total_uses if self.total_uses > 0 else 0.0

    def record_use(self, success: bool):
        self.total_uses += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        self.last_used = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "mapping": self.mapping.to_dict(),
            "outcome": self.outcome,
            "created": self.created,
            "last_used": self.last_used,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_uses": self.total_uses,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnalogyTemplate":
        tmpl = cls(
            template_id=data["template_id"],
            source=RelationalStructure.from_dict(data["source"]),
            target=RelationalStructure.from_dict(data["target"]),
            mapping=StructureMapping.from_dict(data["mapping"]),
            outcome=data.get("outcome", ""),
        )
        tmpl.created = data.get("created", tmpl.created)
        tmpl.last_used = data.get("last_used", tmpl.last_used)
        tmpl.success_count = data.get("success_count", 0)
        tmpl.failure_count = data.get("failure_count", 0)
        tmpl.total_uses = data.get("total_uses", 0)
        return tmpl


# ═══════════════════════════════════════════════════════════════════════
# Analogy Engine
# ═══════════════════════════════════════════════════════════════════════

class AnalogyEngine:
    """
    Analogical reasoning engine implementing Gentner's Structure Mapping Theory.

    Core workflow:
      1. Extract relational structure from experience (via LLM or rules)
      2. Find best structural match across known domains
      3. Score using systematicity, structural consistency, semantic similarity
      4. Transfer inference: apply source knowledge to target
      5. Learn from outcome: store successful analogies as templates
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._analogy_library: Dict[str, AnalogyTemplate] = {}
        self._domain_cache: Dict[str, RelationalStructure] = {}
        self._stats = {
            "total_analogies_found": 0,
            "total_transfers": 0,
            "total_learned": 0,
            "total_extractions": 0,
            "total_abstractions": 0,
        }
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": datetime.now().isoformat(),
                "last_update": "",
            },
            "analogy_library": {},
            "domain_cache": {},
            "stats": dict(self._stats),
        }

    def _load(self):
        if not ANALOGY_FILE.exists():
            self._save()
            return
        try:
            raw = ANALOGY_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            # Load analogy library
            for tid, tdata in data.get("analogy_library", {}).items():
                try:
                    self._analogy_library[tid] = AnalogyTemplate.from_dict(tdata)
                except Exception as e:
                    print(f"[AnalogyEngine] Skipping corrupt template {tid}: {e}")
            # Load domain cache
            for dname, ddata in data.get("domain_cache", {}).items():
                try:
                    self._domain_cache[dname] = RelationalStructure.from_dict(ddata)
                except Exception:
                    pass
            # Load stats
            for k, v in data.get("stats", {}).items():
                if k in self._stats:
                    self._stats[k] = v
            print(f"[AnalogyEngine] Loaded {len(self._analogy_library)} templates, "
                  f"{len(self._domain_cache)} cached domains")
        except (json.JSONDecodeError, IOError) as e:
            print(f"[AnalogyEngine] Load error: {e}")
            self._save()

    def _save(self):
        try:
            BRAIN_DIR.mkdir(parents=True, exist_ok=True)
            with self._lock:
                self._stats_snapshot = dict(self._stats)
                data = {
                    "meta": {
                        "version": 1,
                        "created": datetime.now().isoformat(),
                        "last_update": datetime.now().isoformat(),
                    },
                    "analogy_library": {
                        tid: t.to_dict() for tid, t in self._analogy_library.items()
                    },
                    "domain_cache": {
                        d: s.to_dict() for d, s in self._domain_cache.items()
                    },
                    "stats": dict(self._stats),
                }
            ANALOGY_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[AnalogyEngine] Save error: {e}")

    # ── Core: Find Best Analogy ─────────────────────────────────────────

    def find_analogy(self, source: RelationalStructure,
                     target_domains: List[RelationalStructure],
                     top_k: int = 3) -> List[StructureMapping]:
        """
        Find the best structural match for source across candidate target domains.

        Returns top_k mappings sorted by total_score descending.
        Returns empty list if source is empty or no targets provided.
        """
        if source.is_empty() or not target_domains:
            return []

        candidates = target_domains[:MAX_CANDIDATES]
        mappings: List[StructureMapping] = []

        for target in candidates:
            if target.is_empty():
                continue
            mapping = self._compute_mapping(source, target)
            if mapping.total_score > 0.01:  # threshold to avoid noise
                mappings.append(mapping)

        # Sort by total score
        mappings.sort(key=lambda m: m.total_score, reverse=True)

        with self._lock:
            self._stats["total_analogies_found"] += len(mappings)

        return mappings[:top_k]

    def _compute_mapping(self, source: RelationalStructure,
                         target: RelationalStructure) -> StructureMapping:
        """Compute full structure mapping between source and target."""
        mapping = StructureMapping(source.name, target.name)

        # Step 1: Object alignment via attribute similarity
        obj_map = self._align_objects(source, target)
        mapping.object_mappings = obj_map

        # Step 2: Relation alignment using object correspondences
        rel_map, structural_score = self._align_relations(source, target, obj_map)
        mapping.relation_mappings = rel_map
        mapping.structural_match_score = structural_score

        # Step 3: Systematicity — depth of connected relation chains
        mapping.systematicity_score = self._compute_systematicity(rel_map, source)

        # Step 4: Semantic bonus from attribute overlap
        mapping.semantic_bonus = self._compute_semantic_bonus(
            source, target, obj_map
        )

        # Final score: weighted combination
        mapping.total_score = (
            SYSTEMATICITY_WEIGHT * mapping.systematicity_score +
            STRUCTURAL_WEIGHT * mapping.structural_match_score +
            SEMANTIC_WEIGHT * mapping.semantic_bonus
        )
        mapping.total_score = max(0.0, min(1.0, mapping.total_score))

        return mapping

    def _align_objects(self, source: RelationalStructure,
                       target: RelationalStructure) -> Dict[str, str]:
        """
        Align objects between domains using attribute similarity.
        Greedy best-match: each source object maps to at most one target object.
        """
        if not source.objects or not target.objects:
            return {}

        # Compute pairwise attribute similarity
        candidates: List[Tuple[float, str, str]] = []
        for s_obj in source.objects:
            s_attrs = source.attributes.get(s_obj, set())
            for t_obj in target.objects:
                t_attrs = target.attributes.get(t_obj, set())
                sim = self._jaccard(s_attrs, t_attrs)
                # Also consider name similarity (helps with identical names)
                name_sim = 1.0 if s_obj.lower() == t_obj.lower() else 0.0
                combined = sim * 0.7 + name_sim * 0.3
                if combined > 0.0:
                    candidates.append((combined, s_obj, t_obj))

        # Greedy assignment (Hungarian-lite — good enough for typical domain sizes)
        candidates.sort(key=lambda x: x[0], reverse=True)
        obj_map: Dict[str, str] = {}
        used_source: Set[str] = set()
        used_target: Set[str] = set()

        for score, s_obj, t_obj in candidates:
            if s_obj not in used_source and t_obj not in used_target:
                obj_map[s_obj] = t_obj
                used_source.add(s_obj)
                used_target.add(t_obj)

        return obj_map

    def _align_relations(self, source: RelationalStructure,
                         target: RelationalStructure,
                         obj_map: Dict[str, str]
                         ) -> Tuple[List[Tuple[Tuple, Tuple, float]], float]:
        """
        Align relations using the object mapping.
        Two relations match if they have the same name and their objects correspond.
        """
        if not obj_map or not source.relations or not target.relations:
            return [], 0.0

        # Build target relation index: (name, mapped_objects) → relation tuple
        target_index: Dict[Tuple, List] = defaultdict(list)
        for t_name, t_objs, t_str in target.relations:
            key = (t_name, t_objs)
            target_index[key].append((t_name, t_objs, t_str))

        relation_mappings = []
        matched_source = 0

        for s_name, s_objs, s_str in source.relations:
            # Map source objects to target objects
            mapped_objs = tuple(obj_map.get(o) for o in s_objs)

            # If any object doesn't map, skip
            if None in mapped_objs:
                continue

            # Look for matching relation in target
            key = (s_name, mapped_objs)
            if key in target_index:
                # Exact structural match
                for t_name, t_objs, t_str in target_index[key]:
                    score = min(s_str, t_str)  # weaker strength limits the match
                    relation_mappings.append((
                        (s_name, s_objs, s_str),
                        (t_name, t_objs, t_str),
                        score,
                    ))
                    matched_source += 1
                    break  # one match per source relation
            else:
                # Fuzzy: check for same relation name with different objects
                for t_name, t_objs, t_str in target.relations:
                    if t_name == s_name:
                        # Partial match — objects don't align perfectly
                        overlap = len(set(mapped_objs) & set(t_objs))
                        if overlap > 0:
                            partial = overlap / max(len(mapped_objs), len(t_objs))
                            score = partial * min(s_str, t_str)
                            relation_mappings.append((
                                (s_name, s_objs, s_str),
                                (t_name, t_objs, t_str),
                                score,
                            ))
                            matched_source += 1
                            break

        # Structural score: fraction of source relations that matched
        structural_score = (matched_source / len(source.relations)
                            if source.relations else 0.0)

        return relation_mappings, structural_score

    def _compute_systematicity(self, relation_mappings: List[Tuple],
                               source: RelationalStructure) -> float:
        """
        Systematicity: prefer mappings where relations form connected systems.
        Deep, interconnected mappings score higher than shallow, isolated ones.

        Measures the fraction of mapped relations that participate in at least
        one shared object with another mapped relation.
        """
        if len(relation_mappings) <= 1:
            # Single or no relation — systematicity is the individual strength
            if relation_mappings:
                return relation_mappings[0][2]
            return 0.0

        # Build object co-occurrence graph among mapped relations
        mapped_objects_per_relation: List[Set[str]] = []
        for src_rel, tgt_rel, score in relation_mappings:
            _, src_objs, _ = src_rel
            mapped_objects_per_relation.append(set(src_objs))

        # Count relations that share objects with at least one other relation
        connected = 0
        for i, objs_i in enumerate(mapped_objects_per_relation):
            for j, objs_j in enumerate(mapped_objects_per_relation):
                if i != j and objs_i & objs_j:
                    connected += 1
                    break

        connectivity = connected / len(relation_mappings) if relation_mappings else 0.0

        # Also factor in average relation strength
        avg_strength = (sum(s for _, _, s in relation_mappings) /
                        len(relation_mappings) if relation_mappings else 0.0)

        # Depth bonus: longer chains of connected relations score higher
        chain_length = self._longest_chain(mapped_objects_per_relation)
        depth_bonus = min(1.0, chain_length / max(2, len(relation_mappings)))

        return (connectivity * 0.5 + avg_strength * 0.25 + depth_bonus * 0.25)

    def _longest_chain(self, obj_sets: List[Set[str]]) -> int:
        """Find the longest chain of relations sharing objects."""
        if not obj_sets:
            return 0
        n = len(obj_sets)
        if n == 1:
            return 1

        # Build adjacency: relation i ↔ relation j if they share an object
        adj: Dict[int, List[int]] = defaultdict(list)
        for i in range(n):
            for j in range(i + 1, n):
                if obj_sets[i] & obj_sets[j]:
                    adj[i].append(j)
                    adj[j].append(i)

        # BFS from each node to find longest chain
        best = 1
        for start in range(n):
            visited = {start}
            queue = [(start, 1)]
            while queue:
                node, depth = queue.pop(0)
                best = max(best, depth)
                for neighbor in adj[node]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, depth + 1))
        return best

    def _compute_semantic_bonus(self, source: RelationalStructure,
                                target: RelationalStructure,
                                obj_map: Dict[str, str]) -> float:
        """
        Semantic similarity bonus: reward matching attributes between
        corresponding objects.
        """
        if not obj_map:
            return 0.0

        total_sim = 0.0
        count = 0
        for s_obj, t_obj in obj_map.items():
            s_attrs = source.attributes.get(s_obj, set())
            t_attrs = target.attributes.get(t_obj, set())
            if s_attrs or t_attrs:
                total_sim += self._jaccard(s_attrs, t_attrs)
                count += 1

        return total_sim / count if count > 0 else 0.0

    @staticmethod
    def _jaccard(a: Set[str], b: Set[str]) -> float:
        if not a and not b:
            return 0.0
        intersection = len(a & b)
        union = len(a | b)
        return intersection / union if union > 0 else 0.0

    # ── Score Analogy (Gentner's Criteria) ──────────────────────────────

    def score_analogy(self, mapping: StructureMapping) -> dict:
        """
        Compute detailed analogy score using Gentner's criteria:
          - Structural consistency (1-1 correspondence quality)
          - Systematicity (depth of connected mappings)
          - Semantic similarity (attribute overlap bonus)

        Returns breakdown dict with component scores and total.
        """
        # Structural consistency: are mappings 1-1?
        consistency = self._structural_consistency(mapping)

        # Systematicity already computed
        systematicity = mapping.systematicity_score

        # Semantic bonus already computed
        semantic = mapping.semantic_bonus

        total = (
            SYSTEMATICITY_WEIGHT * systematicity +
            STRUCTURAL_WEIGHT * consistency +
            SEMANTIC_WEIGHT * semantic
        )
        total = max(0.0, min(1.0, total))

        return {
            "structural_consistency": round(consistency, 4),
            "systematicity": round(systematicity, 4),
            "semantic_similarity": round(semantic, 4),
            "total_score": round(total, 4),
            "num_object_mappings": len(mapping.object_mappings),
            "num_relation_mappings": len(mapping.relation_mappings),
        }

    def _structural_consistency(self, mapping: StructureMapping) -> float:
        """
        How well does the mapping preserve relational structure?
        Checks:
          1. Injectivity: each target object mapped to at most one source
          2. Completeness: fraction of source objects that mapped
          3. Relation preservation: fraction of mapped relations with matching targets
        """
        # Injectivity: no two source objects map to same target
        target_objs = list(mapping.object_mappings.values())
        unique_targets = len(set(target_objs))
        injectivity = unique_targets / len(target_objs) if target_objs else 0.0

        # Completeness would need source object count — approximate from relation data
        if mapping.relation_mappings:
            relation_match_rate = mapping.structural_match_score
        else:
            relation_match_rate = 0.0

        return (injectivity * 0.4 + relation_match_rate * 0.6)

    # ── Transfer Inference ──────────────────────────────────────────────

    def transfer_inference(self, mapping: StructureMapping,
                           source_facts: List[str]) -> List[dict]:
        """
        Apply source-domain knowledge to the target domain.

        For each source fact, substitute source objects with their target
        correspondences to generate target-domain inferences.

        Returns list of {"source_fact": str, "target_inference": str, "confidence": float}
        """
        if not mapping.object_mappings or not source_facts:
            return []

        inferences = []
        for fact in source_facts:
            target_fact = fact
            # Apply all object substitutions
            # Sort by length descending to avoid partial replacements
            sorted_mappings = sorted(
                mapping.object_mappings.items(),
                key=lambda kv: len(kv[0]),
                reverse=True,
            )
            for src_obj, tgt_obj in sorted_mappings:
                # Case-insensitive replacement preserving original case
                pattern = re.compile(re.escape(src_obj), re.IGNORECASE)
                target_fact = pattern.sub(tgt_obj, target_fact)

            if target_fact != fact:
                # Confidence based on mapping quality and how much was substituted
                substitution_ratio = sum(
                    1 for s, t in mapping.object_mappings.items() if s in fact
                ) / max(1, len(mapping.object_mappings))
                confidence = mapping.total_score * (0.5 + 0.5 * substitution_ratio)
                inferences.append({
                    "source_fact": fact,
                    "target_inference": target_fact,
                    "confidence": round(min(1.0, confidence), 3),
                    "mapping_score": round(mapping.total_score, 3),
                })

        with self._lock:
            self._stats["total_transfers"] += len(inferences)

        return inferences

    # ── Learn from Analogy ──────────────────────────────────────────────

    def learn_from_analogy(self, mapping: StructureMapping,
                           outcome: str,
                           source: Optional[RelationalStructure] = None,
                           target: Optional[RelationalStructure] = None,
                           success: bool = True) -> str:
        """
        Store a successful analogy as a reusable template.
        Integrates with procedural_memory to create a new procedure.
        Integrates with curiosity to boost exploration of novel patterns.
        """
        template_id = f"analogy_{uuid.uuid4().hex[:8]}"

        # Use empty structures if not provided
        src = source or RelationalStructure(mapping.source_name)
        tgt = target or RelationalStructure(mapping.target_name)

        template = AnalogyTemplate(
            template_id=template_id,
            source=src,
            target=tgt,
            mapping=mapping,
            outcome=outcome,
        )
        template.record_use(success)

        with self._lock:
            self._analogy_library[template_id] = template
            self._stats["total_learned"] += 1
            self._prune_library()

        # Integration: create procedure from analogy
        self._create_procedure_from_analogy(mapping, outcome)

        # Integration: boost curiosity for novel patterns
        self._boost_curiosity(mapping)

        self._save()
        print(f"[AnalogyEngine] Learned analogy: {template_id} "
              f"({mapping.source_name}→{mapping.target_name}, "
              f"score={mapping.total_score:.3f})")
        return template_id

    def _create_procedure_from_analogy(self, mapping: StructureMapping,
                                       outcome: str):
        """Create a procedural memory entry from a successful analogy."""
        try:
            from brain.procedural_memory import get_procedural_memory
            pm = get_procedural_memory()
            goal = (f"analogy: {mapping.source_name} → {mapping.target_name} "
                    f"(score={mapping.total_score:.2f})")
            obj_preview = ", ".join(
                f"{s}→{t}" for s, t in list(mapping.object_mappings.items())[:3]
            )
            steps = [
                {
                    "tool": "analogy_engine",
                    "description": f"Map {obj_preview}",
                    "params_pattern": {
                        "source": mapping.source_name,
                        "target": mapping.target_name,
                        "object_mappings": mapping.object_mappings,
                    },
                },
            ]
            pm.learn_procedure(
                goal=goal,
                steps=steps,
                context={"type": "analogy", "outcome": outcome},
            )
        except ImportError:
            pass  # procedural_memory not available
        except Exception as e:
            print(f"[AnalogyEngine] Procedure creation error: {e}")

    def _boost_curiosity(self, mapping: StructureMapping):
        """Boost curiosity for novel analogical patterns."""
        try:
            from brain.curiosity import get_curiosity_module
            cm = get_curiosity_module()
            # Register the analogy concept for novelty tracking
            concept = f"analogy:{mapping.source_name}→{mapping.target_name}"
            cm.encounter(concept)
            # If it's a novel analogy (high score, few prior encounters),
            # register a surprise to encourage further exploration
            if mapping.total_score > 0.7:
                cm.record_surprise(
                    tool_name="analogy_engine",
                    what=f"Strong analogy found: {mapping.source_name} "
                         f"→ {mapping.target_name} (score={mapping.total_score:.2f})",
                    severity="low",
                )
        except ImportError:
            pass  # curiosity module not available
        except Exception as e:
            print(f"[AnalogyEngine] Curiosity boost error: {e}")

    def _prune_library(self):
        """Remove low-performing or old templates."""
        if len(self._analogy_library) <= MAX_LIBRARY_SIZE:
            return

        now = datetime.now()
        to_remove = []

        for tid, tmpl in self._analogy_library.items():
            if tmpl.total_uses >= 3 and tmpl.success_rate < MIN_ANALOGY_SUCCESS:
                to_remove.append(tid)
                continue
            try:
                last = datetime.fromisoformat(tmpl.last_used)
                if (now - last).days > DECAY_DAYS:
                    to_remove.append(tid)
            except (ValueError, TypeError):
                pass

        # Remove oldest first, keep up to MAX_LIBRARY_SIZE
        to_remove.sort(key=lambda tid: self._analogy_library[tid].last_used)
        for tid in to_remove[:len(self._analogy_library) - MAX_LIBRARY_SIZE]:
            del self._analogy_library[tid]

    # ── Retrieve from Library ───────────────────────────────────────────

    def find_similar_analogy(self, source: RelationalStructure,
                             top_k: int = 3) -> List[dict]:
        """
        Search the analogy library for templates with similar source domains.
        Returns list of template summaries.
        """
        with self._lock:
            if not self._analogy_library:
                return []

            scored = []
            for tid, tmpl in self._analogy_library.items():
                # Compare source structures
                obj_sim = self._jaccard(source.objects, tmpl.source.objects)
                # Compare relation names
                src_rels = set(r[0] for r in source.relations)
                tmpl_rels = set(r[0] for r in tmpl.source.relations)
                rel_sim = self._jaccard(src_rels, tmpl_rels)
                combined = obj_sim * 0.4 + rel_sim * 0.6

                if combined > 0.1:
                    scored.append({
                        "template_id": tid,
                        "source_name": tmpl.source.name,
                        "target_name": tmpl.target.name,
                        "similarity": round(combined, 3),
                        "success_rate": round(tmpl.success_rate, 3),
                        "total_uses": tmpl.total_uses,
                        "outcome": tmpl.outcome,
                        "mapping_score": round(tmpl.mapping.total_score, 3),
                    })

            scored.sort(key=lambda x: x["similarity"] * x["success_rate"],
                        reverse=True)
            return scored[:top_k]

    # ── Extract Relational Structure (LLM-powered) ──────────────────────

    def extract_relational_structure(self, text: str) -> RelationalStructure:
        """
        Extract a relational structure from natural language text.
        Uses LLM if available, falls back to heuristic parsing.
        """
        with self._lock:
            self._stats["total_extractions"] += 1

        # Try LLM extraction first
        llm_result = self._extract_via_llm(text)
        if llm_result and not llm_result.is_empty():
            return llm_result

        # Fallback: heuristic extraction
        return self._extract_heuristic(text)

    def _extract_via_llm(self, text: str) -> Optional[RelationalStructure]:
        """Use LLM to extract structured domain representation."""
        try:
            from brain._agi_imports import get_llm
            llm = get_llm()
            if llm is None:
                return None

            prompt = (
                "Extract a relational structure from this text. "
                "Return JSON with:\n"
                '  "name": "domain name",\n'
                '  "objects": ["obj1", "obj2", ...],\n'
                '  "attributes": {"obj1": ["attr1", "attr2"]},\n'
                '  "relations": [{"name": "rel_name", "objects": ["obj1", "obj2"], '
                '"strength": 0.8}]\n\n'
                f"Text:\n{text[:2000]}"
            )

            response = llm(prompt, max_tokens=500, temperature=0.1)
            if not response:
                return None

            # Parse JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                return None

            data = json.loads(json_match.group())
            return RelationalStructure.from_dict(data)

        except (ImportError, json.JSONDecodeError, Exception) as e:
            print(f"[AnalogyEngine] LLM extraction failed: {e}")
            return None

    def _extract_heuristic(self, text: str) -> RelationalStructure:
        """
        Heuristic extraction: find nouns as objects, adjectives as attributes,
        verb phrases as relations.
        """
        rs = RelationalStructure(name=text[:50].strip())

        # Simple noun extraction (capitalized words, quoted terms)
        nouns = set()
        # Capitalized words (likely proper nouns / entities)
        for match in re.finditer(r'\b[A-Z][a-z]{2,}\b', text):
            nouns.add(match.group())
        # Quoted terms
        for match in re.finditer(r'"([^"]+)"', text):
            nouns.add(match.group(1))

        # Limit to reasonable number
        nouns = set(list(nouns)[:20])
        for noun in nouns:
            rs.add_object(noun)

        # Simple relation extraction: look for "X verb Y" patterns
        relation_patterns = [
            (r'(\w+)\s+(is|are|was|were)\s+(\w+)', "is_a"),
            (r'(\w+)\s+(has|have|had)\s+(\w+)', "has"),
            (r'(\w+)\s+(causes|leads to|results in)\s+(\w+)', "causes"),
            (r'(\w+)\s+(contains|includes|holds)\s+(\w+)', "contains"),
            (r'(\w+)\s+(larger|bigger|greater|more)\s+than\s+(\w+)', "greater_than"),
            (r'(\w+)\s+(smaller|less|fewer)\s+than\s+(\w+)', "less_than"),
            (r'(\w+)\s+(near|close to|adjacent to)\s+(\w+)', "near"),
            (r'(\w+)\s+(above|over|on top of)\s+(\w+)', "above"),
            (r'(\w+)\s+(below|under|beneath)\s+(\w+)', "below"),
            (r'(\w+)\s+(left of|to the left)\s+(\w+)', "left_of"),
            (r'(\w+)\s+(right of|to the right)\s+(\w+)', "right_of"),
        ]

        for pattern, rel_name in relation_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                o1, o2 = match.group(1), match.group(3)
                if o1 in nouns and o2 in nouns:
                    rs.add_relation(rel_name, (o1, o2), 0.7)

        # Attribute extraction: adjectives before nouns
        for noun in nouns:
            attr_pattern = re.compile(
                rf'\b(big|small|red|blue|green|dark|light|fast|slow|hot|cold|'
                rf'round|square|tall|short|wide|narrow|thick|thin|'
                rf'new|old|young|heavy|light)\s+{re.escape(noun)}\b',
                re.IGNORECASE,
            )
            for match in attr_pattern.finditer(text):
                rs.attributes[noun].add(match.group(1).lower())

        return rs

    # ── Abstract Domain from Experiences ────────────────────────────────

    def abstract_domain(self, experiences: List[RelationalStructure],
                        domain_name: str = "abstract") -> RelationalStructure:
        """
        Generalize from multiple specific experiences to an abstract
        relational structure. Keeps patterns common across experiences.
        """
        with self._lock:
            self._stats["total_abstractions"] += 1

        if not experiences:
            return RelationalStructure(domain_name)

        if len(experiences) == 1:
            # Single experience — return it as-is with the abstract name
            abstract = experiences[0]
            abstract.name = domain_name
            return abstract

        # Find common relation names (appear in majority of experiences)
        rel_counts: Dict[str, int] = defaultdict(int)
        obj_counts: Dict[str, int] = defaultdict(int)
        attr_counts: Dict[Tuple[str, str], int] = defaultdict(int)

        for exp in experiences:
            seen_rels = set()
            for rel_name, objs, _ in exp.relations:
                if rel_name not in seen_rels:
                    rel_counts[rel_name] += 1
                    seen_rels.add(rel_name)
            for obj in exp.objects:
                obj_counts[obj] += 1
            for obj, attrs in exp.attributes.items():
                for attr in attrs:
                    attr_counts[(obj, attr)] += 1

        threshold = len(experiences) * 0.5  # majority

        abstract = RelationalStructure(domain_name)

        # Keep common objects
        for obj, count in obj_counts.items():
            if count >= threshold:
                abstract.add_object(obj)

        # Keep common attributes
        for (obj, attr), count in attr_counts.items():
            if count >= threshold and obj in abstract.objects:
                abstract.attributes[obj].add(attr)

        # Keep common relations with averaged strength
        for exp in experiences:
            for rel_name, objs, strength in exp.relations:
                if rel_counts[rel_name] >= threshold:
                    # Check that objects are in abstract domain
                    if all(o in abstract.objects for o in objs):
                        # Avoid duplicate identical relations
                        exists = any(
                            r[0] == rel_name and r[1] == objs
                            for r in abstract.relations
                        )
                        if not exists:
                            # Average strength across experiences that have it
                            avg_strength = strength * (rel_counts[rel_name] /
                                                       len(experiences))
                            abstract.add_relation(rel_name, objs, avg_strength)

        # Cache the abstract domain
        with self._lock:
            self._domain_cache[domain_name] = abstract

        print(f"[AnalogyEngine] Abstracted domain '{domain_name}' from "
              f"{len(experiences)} experiences: "
              f"{len(abstract.objects)} objects, {len(abstract.relations)} relations")
        return abstract

    # ── Format for Prompt ───────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """Format analogy library and recent mappings for system prompt."""
        with self._lock:
            if not self._analogy_library:
                return ""

            # Get top templates by usage and success
            top = sorted(
                self._analogy_library.values(),
                key=lambda t: t.success_rate * t.total_uses,
                reverse=True,
            )[:5]

            parts = ["[ANALOGY ENGINE — Learned analogical patterns]"]
            for tmpl in top:
                obj_map_str = ", ".join(
                    f"{s}→{t}" for s, t in list(tmpl.mapping.object_mappings.items())[:3]
                )
                parts.append(
                    f"  [{tmpl.success_rate:.0%} success, {tmpl.total_uses}x] "
                    f"{tmpl.source.name} → {tmpl.target.name} "
                    f"({obj_map_str}) "
                    f"score={tmpl.mapping.total_score:.2f}"
                )

            result = "\n".join(parts)
            if len(result) > max_chars:
                result = result[:max_chars] + "[...]"
            return result

    # ── Stats ───────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        with self._lock:
            library_size = len(self._analogy_library)
            cache_size = len(self._domain_cache)
            if library_size > 0:
                avg_success = sum(
                    t.success_rate for t in self._analogy_library.values()
                ) / library_size
                avg_score = sum(
                    t.mapping.total_score for t in self._analogy_library.values()
                ) / library_size
            else:
                avg_success = 0.0
                avg_score = 0.0

            return {
                "library_size": library_size,
                "cached_domains": cache_size,
                "avg_success_rate": round(avg_success, 3),
                "avg_mapping_score": round(avg_score, 3),
                **self._stats,
            }


# ═══════════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════════

_analogy_engine = None
_analogy_lock = threading.Lock()


def get_analogy_engine() -> AnalogyEngine:
    global _analogy_engine
    if _analogy_engine is None:
        with _analogy_lock:
            if _analogy_engine is None:
                _analogy_engine = AnalogyEngine()
    return _analogy_engine
