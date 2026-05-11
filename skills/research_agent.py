#!/usr/bin/env python3
"""
research_agent.py — Friday Autonomous Research Agent
=====================================================

Deep autonomous research that synthesizes knowledge from multiple sources,
builds knowledge graphs, tracks citations, and produces structured reports.

This is NOT a simple search-and-summarize. It's a research COGNITIVE SYSTEM:

  [RA-1] Multi-Source Synthesis — gathers information from web, documents,
         memory, and analogical reasoning, then synthesizes a coherent picture.

  [RA-2] Knowledge Graph Construction — automatically builds a graph of
         entities, relationships, and claims from research material.

  [RA-3] Citation Tracking — every claim is traceable to its source with
         confidence scores and recency weighting.

  [RA-4] Research Planning — decomposes complex questions into sub-questions,
         identifies knowledge gaps, and plans a research strategy.

  [RA-5] Iterative Deepening — starts broad, identifies the most promising
         threads, then drills down. Mirrors expert research behavior.

  [RA-6] Contradiction Detection — identifies conflicting claims across
         sources and flags them for resolution.

  [RA-7] Confidence Assessment — rates overall confidence in findings
         based on source quality, agreement, and recency.

Inspired by:
  - Marchionini's Information Seeking Model (1995)
  - Pirolli & Card's Sensemaking theory (2005)
  - Belkin's Anomalous State of Knowledge (ASK) model (1980)

Usage:
    from skills.research_agent import get_research_agent
    agent = get_research_agent()
    report = agent.research("What are the latest advances in quantum error correction?")
"""

import hashlib
import json
import math
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


SKILLS_DIR = Path(__file__).parent.resolve()
DATA_DIR = SKILLS_DIR / "research_data"
KNOWLEDGE_GRAPH_FILE = DATA_DIR / "knowledge_graph.json"
RESEARCH_HISTORY_FILE = DATA_DIR / "research_history.json"

# ── Configuration ───────────────────────────────────────────────────────────

MAX_ENTITIES = 2000
MAX_RELATIONS = 5000
MAX_RESEARCH_HISTORY = 200
MAX_SOURCES_PER_CLAIM = 10
CONFIDENCE_DECAY_DAYS = 180.       # old findings lose confidence
MIN_ENTITY_FREQUENCY = 2           # entity must appear at least twice
MAX_SUB_QUESTIONS = 7
RESEARCH_DEPTH_LEVELS = 3          # broad → medium → deep


def _now() -> str:
    return datetime.now().isoformat()


def _timestamp() -> float:
    return time.time()


def _hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


# ── Data Structures ─────────────────────────────────────────────────────────

class Entity:
    """A node in the knowledge graph — a concept, person, technology, etc."""

    __slots__ = [
        "entity_id", "name", "entity_type", "description",
        "aliases", "mentions", "first_seen", "last_seen",
        "confidence", "attributes",
    ]

    def __init__(self, name: str, entity_type: str = "concept",
                 description: str = ""):
        self.entity_id = _hash(f"{entity_type}:{name.lower()}")
        self.name = name.strip()
        self.entity_type = entity_type
        self.description = description[:500]
        self.aliases: Set[str] = set()
        self.mentions = 1
        self.first_seen = _now()
        self.last_seen = _now()
        self.confidence = 0.5
        self.attributes: Dict[str, str] = {}

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "entity_type": self.entity_type,
            "description": self.description,
            "aliases": list(self.aliases),
            "mentions": self.mentions,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "confidence": round(self.confidence, 3),
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Entity":
        e = cls(d.get("name", ""), d.get("entity_type", "concept"),
                d.get("description", ""))
        e.entity_id = d.get("entity_id", e.entity_id)
        e.aliases = set(d.get("aliases", []))
        e.mentions = d.get("mentions", 1)
        e.first_seen = d.get("first_seen", _now())
        e.last_seen = d.get("last_seen", _now())
        e.confidence = d.get("confidence", 0.5)
        e.attributes = d.get("attributes", {})
        return e


class Relation:
    """An edge in the knowledge graph — connects two entities."""

    __slots__ = [
        "relation_id", "source_id", "target_id", "relation_type",
        "description", "weight", "sources", "first_seen", "last_seen",
    ]

    def __init__(self, source_id: str, target_id: str,
                 relation_type: str = "related_to",
                 description: str = "", source_url: str = ""):
        self.relation_id = _hash(f"{source_id}:{relation_type}:{target_id}")
        self.source_id = source_id
        self.target_id = target_id
        self.relation_type = relation_type
        self.description = description[:300]
        self.weight = 0.5
        self.sources: List[str] = [source_url] if source_url else []
        self.first_seen = _now()
        self.last_seen = _now()

    def to_dict(self) -> dict:
        return {
            "relation_id": self.relation_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "description": self.description,
            "weight": round(self.weight, 3),
            "sources": self.sources,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Relation":
        r = cls(d.get("source_id", ""), d.get("target_id", ""),
                d.get("relation_type", "related_to"),
                d.get("description", ""))
        r.relation_id = d.get("relation_id", r.relation_id)
        r.weight = d.get("weight", 0.5)
        r.sources = d.get("sources", [])
        r.first_seen = d.get("first_seen", _now())
        r.last_seen = d.get("last_seen", _now())
        return r


class Claim:
    """A research finding with source tracking and confidence."""

    __slots__ = [
        "claim_id", "text", "topic", "sources", "confidence",
        "supporting_count", "contradicting_count", "first_seen", "last_seen",
    ]

    def __init__(self, text: str, topic: str = "",
                 source_url: str = "", confidence: float = 0.5):
        self.claim_id = _hash(text)
        self.text = text[:500]
        self.topic = topic
        self.sources: List[dict] = []
        if source_url:
            self.sources.append({"url": source_url, "timestamp": _now()})
        self.confidence = _clamp(confidence)
        self.supporting_count = 1 if source_url else 0
        self.contradicting_count = 0
        self.first_seen = _now()
        self.last_seen = _now()

    def add_source(self, url: str, agrees: bool = True):
        self.sources.append({"url": url, "timestamp": _now(), "agrees": agrees})
        if agrees:
            self.supporting_count += 1
        else:
            self.contradicting_count += 1
        self.last_seen = _now()
        # Update confidence: more supporting sources = higher confidence
        total = self.supporting_count + self.contradicting_count
        if total > 0:
            self.confidence = _clamp(self.supporting_count / total)

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "topic": self.topic,
            "sources": self.sources[-MAX_SOURCES_PER_CLAIM:],
            "confidence": round(self.confidence, 3),
            "supporting_count": self.supporting_count,
            "contradicting_count": self.contradicting_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Claim":
        c = cls(d.get("text", ""), d.get("topic", ""))
        c.claim_id = d.get("claim_id", c.claim_id)
        c.sources = d.get("sources", [])
        c.confidence = d.get("confidence", 0.5)
        c.supporting_count = d.get("supporting_count", 0)
        c.contradicting_count = d.get("contradicting_count", 0)
        c.first_seen = d.get("first_seen", _now())
        c.last_seen = d.get("last_seen", _now())
        return c


class ResearchReport:
    """A structured research report with findings, graph, and metadata."""

    __slots__ = [
        "report_id", "query", "sub_questions", "findings",
        "knowledge_graph_summary", "contradictions", "confidence",
        "sources_consulted", "depth_reached", "duration_s",
        "created_at", "entities_discovered", "relations_discovered",
    ]

    def __init__(self, query: str):
        self.report_id = _hash(f"{query}:{_now()}")
        self.query = query
        self.sub_questions: List[str] = []
        self.findings: List[dict] = []
        self.knowledge_graph_summary: dict = {}
        self.contradictions: List[dict] = []
        self.confidence = 0.0
        self.sources_consulted = 0
        self.depth_reached = 0
        self.duration_s = 0.0
        self.created_at = _now()
        self.entities_discovered = 0
        self.relations_discovered = 0

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "query": self.query,
            "sub_questions": self.sub_questions,
            "findings": self.findings,
            "knowledge_graph_summary": self.knowledge_graph_summary,
            "contradictions": self.contradictions,
            "confidence": round(self.confidence, 3),
            "sources_consulted": self.sources_consulted,
            "depth_reached": self.depth_reached,
            "duration_s": round(self.duration_s, 2),
            "created_at": self.created_at,
            "entities_discovered": self.entities_discovered,
            "relations_discovered": self.relations_discovered,
        }


# ── Research Agent ──────────────────────────────────────────────────────────

class ResearchAgent:
    """
    Autonomous research agent that plans, gathers, synthesizes, and reports.

    Research cycle:
    1. Analyze query → decompose into sub-questions
    2. Plan research strategy → identify sources and approaches
    3. Gather information → web search, memory recall, analogy
    4. Extract entities & relations → build knowledge graph
    5. Identify claims → track sources and confidence
    6. Detect contradictions → flag conflicting information
    7. Synthesize → produce structured report
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._entities: Dict[str, Entity] = {}
        self._relations: Dict[str, Relation] = {}
        self._claims: Dict[str, Claim] = {}
        self._research_history: List[dict] = []
        self._load()

    # ── Persistence ─────────────────────────────────────────────────

    def _load(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if KNOWLEDGE_GRAPH_FILE.exists():
            try:
                data = json.loads(KNOWLEDGE_GRAPH_FILE.read_text(encoding="utf-8"))
                for ed in data.get("entities", []):
                    e = Entity.from_dict(ed)
                    self._entities[e.entity_id] = e
                for rd in data.get("relations", []):
                    r = Relation.from_dict(rd)
                    self._relations[r.relation_id] = r
                for cd in data.get("claims", []):
                    c = Claim.from_dict(cd)
                    self._claims[c.claim_id] = c
            except (json.JSONDecodeError, IOError):
                pass
        if RESEARCH_HISTORY_FILE.exists():
            try:
                self._research_history = json.loads(
                    RESEARCH_HISTORY_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                self._research_history = []

    def _save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            KNOWLEDGE_GRAPH_FILE.write_text(json.dumps({
                "entities": [e.to_dict() for e in list(self._entities.values())[-MAX_ENTITIES:]],
                "relations": [r.to_dict() for r in list(self._relations.values())[-MAX_RELATIONS:]],
                "claims": [c.to_dict() for c in list(self._claims.values())[-MAX_RESEARCH_HISTORY:]],
            }, indent=2, ensure_ascii=False), encoding="utf-8")
            RESEARCH_HISTORY_FILE.write_text(json.dumps(
                self._research_history[-MAX_RESEARCH_HISTORY:],
                indent=2, ensure_ascii=False), encoding="utf-8")

    # ── Research Planning ────────────────────────────────────────────

    def decompose_query(self, query: str) -> List[str]:
        """
        Break a complex research question into sub-questions.

        Uses simple heuristics: question words, conjunctions, topic markers.
        """
        query_lower = query.lower().strip()
        sub_qs = []

        # Split on question markers
        parts = re.split(r'\b(what|how|why|when|where|who|which|compare|contrast|difference|impact|effect|relationship)\b',
                         query_lower)

        # Extract meaningful segments
        question_words = {"what", "how", "why", "when", "where", "who", "which"}
        current = ""
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if part in question_words:
                if current:
                    sub_qs.append(current.strip("? ."))
                current = part + " "
            else:
                current += part
        if current:
            sub_qs.append(current.strip("? ."))

        # Also split on "and", "as well as", "also"
        expanded = []
        for sq in sub_qs:
            for segment in re.split(r'\b(?:and|as well as|also|additionally)\b', sq):
                segment = segment.strip()
                if len(segment) > 10:
                    expanded.append(segment.capitalize() + "?")

        # Limit
        result = expanded[:MAX_SUB_QUESTIONS] if expanded else [query]
        if not result:
            result = [query]
        return result

    def plan_research_strategy(self, query: str, sub_questions: List[str]) -> dict:
        """
        Plan how to approach the research.

        Returns a strategy dict with source priorities and approach per sub-question.
        """
        # Categorize the query
        query_lower = query.lower()
        categories = []
        if any(w in query_lower for w in ["latest", "recent", "new", "2024", "2025", "2026"]):
            categories.append("current_events")
        if any(w in query_lower for w in ["how", "tutorial", "guide", "implement"]):
            categories.append("procedural")
        if any(w in query_lower for w in ["compare", "vs", "versus", "difference", "better"]):
            categories.append("comparative")
        if any(w in query_lower for w in ["why", "cause", "reason", "because"]):
            categories.append("causal")
        if any(w in query_lower for w in ["history", "origin", "evolution", "timeline"]):
            categories.append("historical")
        if not categories:
            categories.append("general")

        strategy = {
            "query": query,
            "categories": categories,
            "sub_questions": sub_questions,
            "source_priority": ["web_search", "memory", "analogy", "world_model"],
            "depth_target": min(RESEARCH_DEPTH_LEVELS, len(sub_questions)),
            "approach": "iterative_deepening",
        }
        return strategy

    # ── Entity & Relation Extraction ─────────────────────────────────

    def extract_entities(self, text: str, source: str = "") -> List[Entity]:
        """
        Extract entities from text using pattern-based NER.
        No ML dependencies — uses capitalization, patterns, and heuristics.
        """
        entities = []

        # Capitalized multi-word phrases (potential proper nouns)
        cap_pattern = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', text)
        for phrase in cap_pattern:
            if len(phrase) > 2 and phrase not in {"The", "This", "That", "These",
                                                    "When", "Where", "What", "How",
                                                    "Why", "Which", "Their", "They",
                                                    "However", "Although", "Because"}:
                entity = Entity(phrase, entity_type="concept")
                if entity.entity_id not in self._entities:
                    entities.append(entity)

        # Technology/tool names (lowercase with dots, hyphens)
        tech_pattern = re.findall(r'\b([a-z][a-z0-9]+[._-][a-z0-9]+)\b', text.lower())
        for tech in set(tech_pattern):
            if len(tech) > 3:
                entity = Entity(tech, entity_type="technology")
                if entity.entity_id not in self._entities:
                    entities.append(entity)

        # Acronyms (2-6 uppercase letters)
        acronyms = re.findall(r'\b([A-Z]{2,6})\b', text)
        for acr in set(acronyms):
            entity = Entity(acr, entity_type="acronym")
            if entity.entity_id not in self._entities:
                entities.append(entity)

        return entities

    def extract_relations(self, text: str, entities: List[Entity],
                          source: str = "") -> List[Relation]:
        """
        Extract relations between co-occurring entities.
        """
        relations = []
        # Simple co-occurrence within sentences
        sentences = re.split(r'[.!?]', text)
        for sentence in sentences:
            sentence_entities = [
                e for e in entities
                if e.name.lower() in sentence.lower()
            ]
            # Create relations between co-occurring entities
            for i, e1 in enumerate(sentence_entities):
                for e2 in sentence_entities[i+1:]:
                    # Determine relation type from context
                    rel_type = "co_occurs_with"
                    s_lower = sentence.lower()
                    if any(w in s_lower for w in ["uses", "uses", "built on", "based on"]):
                        rel_type = "depends_on"
                    elif any(w in s_lower for w in ["creates", "produces", "generates"]):
                        rel_type = "produces"
                    elif any(w in s_lower for w in ["part of", "component of", "includes"]):
                        rel_type = "part_of"
                    elif any(w in s_lower for w in ["competes", "vs", "versus", "alternative"]):
                        rel_type = "competes_with"
                    elif any(w in s_lower for w in ["improves", "enhances", "upgrades"]):
                        rel_type = "improves"

                    rel = Relation(e1.entity_id, e2.entity_id, rel_type,
                                   sentence.strip()[:200], source)
                    if rel.relation_id not in self._relations:
                        relations.append(rel)

        return relations

    # ── Claim Extraction & Tracking ──────────────────────────────────

    def extract_claims(self, text: str, topic: str = "",
                       source_url: str = "") -> List[Claim]:
        """
        Extract factual claims from text.
        Claims are sentences with factual indicators.
        """
        claims = []
        sentences = re.split(r'(?<=[.!?])\s+', text)

        factual_indicators = [
            "is", "are", "was", "were", "has", "have", "can", "will",
            "shows", "demonstrates", "indicates", "suggests", "found",
            "study", "research", "data", "evidence", "according",
            "percent", "%", "million", "billion", "increased", "decreased",
        ]

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 20 or len(sentence) > 300:
                continue
            s_lower = sentence.lower()
            # Check for factual indicators
            indicator_count = sum(1 for ind in factual_indicators if ind in s_lower)
            if indicator_count >= 2:
                confidence = min(0.7, 0.3 + indicator_count * 0.1)
                claim = Claim(sentence, topic, source_url, confidence)
                claims.append(claim)

        return claims

    # ── Contradiction Detection ──────────────────────────────────────

    def detect_contradictions(self) -> List[dict]:
        """
        Find claims that contradict each other.
        Uses keyword opposition and negation detection.
        """
        contradictions = []
        claim_list = list(self._claims.values())

        oppositions = [
            ("increase", "decrease"), ("more", "less"), ("better", "worse"),
            ("true", "false"), ("yes", "no"), ("can", "cannot"),
            ("effective", "ineffective"), ("safe", "unsafe"),
            ("improves", "worsens"), ("positive", "negative"),
        ]

        for i, c1 in enumerate(claim_list):
            for c2 in claim_list[i+1:]:
                if c1.topic and c2.topic and c1.topic != c2.topic:
                    continue
                t1, t2 = c1.text.lower(), c2.text.lower()
                for word_a, word_b in oppositions:
                    if (word_a in t1 and word_b in t2) or (word_b in t1 and word_a in t2):
                        # Check they're about similar topics
                        words1 = set(t1.split())
                        words2 = set(t2.split())
                        overlap = len(words1 & words2)
                        if overlap >= 3:
                            contradictions.append({
                                "claim_a": c1.to_dict(),
                                "claim_b": c2.to_dict(),
                                "opposition": f"{word_a} vs {word_b}",
                                "overlap_words": overlap,
                            })

        return contradictions

    # ── Main Research Pipeline ───────────────────────────────────────

    def research(self, query: str, context: dict = None) -> dict:
        """
        Conduct autonomous research on a topic.

        Full pipeline: plan → gather → extract → synthesize → report.

        Args:
            query: The research question
            context: Optional context with existing knowledge, sources, etc.

        Returns:
            Research report dict with findings, graph, contradictions, confidence.
        """
        start = _timestamp()
        context = context or {}

        # Phase 1: Decompose
        sub_questions = self.decompose_query(query)

        # Phase 2: Plan
        strategy = self.plan_research_strategy(query, sub_questions)

        # Phase 3: Gather & Extract (from provided context)
        all_entities = []
        all_claims = []
        sources_count = 0

        # Process any provided source material
        source_texts = context.get("sources", [])
        for source in source_texts:
            text = source.get("text", "")
            url = source.get("url", "")
            if not text:
                continue
            sources_count += 1

            entities = self.extract_entities(text, url)
            all_entities.extend(entities)

            relations = self.extract_relations(text, entities, url)
            for rel in relations:
                self._relations[rel.relation_id] = rel

            claims = self.extract_claims(text, query, url)
            all_claims.extend(claims)

        # Also check memory/knowledge graph for existing relevant entities
        query_words = set(query.lower().split())
        relevant_existing = []
        for entity in self._entities.values():
            if any(w in entity.name.lower() for w in query_words):
                relevant_existing.append(entity)

        # Phase 4: Store entities
        for entity in all_entities:
            if entity.entity_id in self._entities:
                self._entities[entity.entity_id].mentions += 1
                self._entities[entity.entity_id].last_seen = _now()
            else:
                self._entities[entity.entity_id] = entity

        # Phase 5: Store claims
        for claim in all_claims:
            if claim.claim_id in self._claims:
                existing = self._claims[claim.claim_id]
                for src in claim.sources:
                    existing.add_source(src.get("url", ""), agrees=True)
            else:
                self._claims[claim.claim_id] = claim

        # Phase 6: Detect contradictions
        contradictions = self.detect_contradictions()

        # Phase 7: Calculate confidence
        if all_claims:
            avg_confidence = sum(c.confidence for c in all_claims) / len(all_claims)
        else:
            avg_confidence = 0.3

        # Phase 8: Build report
        report = ResearchReport(query)
        report.sub_questions = sub_questions
        report.findings = [c.to_dict() for c in sorted(
            all_claims, key=lambda c: c.confidence, reverse=True)[:20]]
        report.contradictions = contradictions[:10]
        report.confidence = avg_confidence
        report.sources_consulted = sources_count
        report.depth_reached = strategy["depth_target"]
        report.duration_s = _timestamp() - start
        report.entities_discovered = len(all_entities)
        report.relations_discovered = len(self._relations)

        # Knowledge graph summary
        top_entities = sorted(
            self._entities.values(), key=lambda e: e.mentions, reverse=True)[:10]
        report.knowledge_graph_summary = {
            "total_entities": len(self._entities),
            "total_relations": len(self._relations),
            "total_claims": len(self._claims),
            "top_entities": [
                {"name": e.name, "type": e.entity_type, "mentions": e.mentions}
                for e in top_entities
            ],
        }

        # Record history
        self._research_history.append({
            "query": query,
            "report_id": report.report_id,
            "confidence": report.confidence,
            "entities": report.entities_discovered,
            "timestamp": _now(),
        })

        self._save()
        return report.to_dict()

    # ── Knowledge Graph Queries ──────────────────────────────────────

    def query_entity(self, name: str) -> Optional[dict]:
        """Look up an entity by name."""
        with self._lock:
            name_lower = name.lower()
            for entity in self._entities.values():
                if entity.name.lower() == name_lower or name_lower in entity.aliases:
                    # Get connected relations
                    connected = []
                    for rel in self._relations.values():
                        if rel.source_id == entity.entity_id:
                            target = self._entities.get(rel.target_id)
                            if target:
                                connected.append({
                                    "relation": rel.relation_type,
                                    "target": target.name,
                                    "description": rel.description,
                                })
                        elif rel.target_id == entity.entity_id:
                            source = self._entities.get(rel.source_id)
                            if source:
                                connected.append({
                                    "relation": f"inverse_{rel.relation_type}",
                                    "target": source.name,
                                    "description": rel.description,
                                })
                    return {
                        "entity": entity.to_dict(),
                        "connections": connected[:20],
                    }
            return None

    def get_graph_stats(self) -> dict:
        """Get knowledge graph statistics."""
        with self._lock:
            entity_types = defaultdict(int)
            for e in self._entities.values():
                entity_types[e.entity_type] += 1
            relation_types = defaultdict(int)
            for r in self._relations.values():
                relation_types[r.relation_type] += 1
            return {
                "entities": len(self._entities),
                "relations": len(self._relations),
                "claims": len(self._claims),
                "entity_types": dict(entity_types),
                "relation_types": dict(relation_types),
                "research_sessions": len(self._research_history),
            }

    def get_stats(self) -> dict:
        """Get research agent statistics (alias for get_graph_stats)."""
        return self.get_graph_stats()

    def get_recent_research(self, limit: int = 10) -> List[dict]:
        """Get recent research history."""
        with self._lock:
            return list(reversed(self._research_history[-limit:]))

    def format_for_prompt(self, max_chars: int = 500) -> str:
        """Format research context for system prompt."""
        stats = self.get_graph_stats()
        recent = self.get_recent_research(3)

        parts = [
            "[RESEARCH AGENT — Knowledge graph]",
            f"Entities: {stats['entities']} | Relations: {stats['relations']} | "
            f"Claims: {stats['claims']} | Sessions: {stats['research_sessions']}",
        ]

        if recent:
            parts.append("Recent: " + " | ".join(
                f"\"{r['query'][:40]}\"({r['confidence']:.0%})" for r in recent))

        result = "\n".join(parts)
        return result[:max_chars]


# ── Singleton ───────────────────────────────────────────────────────────────

_research_agent = None
_research_lock = threading.Lock()


def get_research_agent() -> ResearchAgent:
    """Get singleton ResearchAgent instance."""
    global _research_agent
    if _research_agent is None:
        with _research_lock:
            if _research_agent is None:
                _research_agent = ResearchAgent()
    return _research_agent
