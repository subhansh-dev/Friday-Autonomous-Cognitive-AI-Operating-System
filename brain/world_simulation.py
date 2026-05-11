#!/usr/bin/env python3
"""
world_simulation.py — FRIDAY World Simulation Engine (Pillar 8)
================================================================

Real-time world model with predictive capabilities.

Maintains a dynamic internal representation of the external world:
  - Ingests events from multiple domains (tech, economy, politics, science, etc.)
  - Tracks trends and patterns over time
  - Predicts outcomes based on historical event chains
  - Simulates counterfactual scenarios ("what if X had been different?")
  - Filters events by user relevance (interests, projects, goals)
  - Provides context-aware world state summaries for reasoning

This module gives FRIDAY situational awareness — the ability to understand
not just what happened, but what it means and what might happen next.
"""

import json
import math
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


BRAIN_DIR = Path(__file__).parent.resolve()
WORLD_STATE_FILE = BRAIN_DIR / "world_state.json"

# ── Configuration ───────────────────────────────────────────────────────────

MAX_EVENTS_PER_DOMAIN = 500
MAX_TOTAL_EVENTS = 5000
MAX_TRENDS = 200
EVENT_RELEVANCE_DECAY_DAYS = 30.       # relevance halves every 30 days
TREND_MIN_EVENTS = 3                   # minimum events to detect a trend
TREND_TIME_WINDOW_DAYS = 90            # look-back window for trend detection
COUNTERFACTUAL_DEPTH = 5               # max causal chain depth
PREDICTION_HORIZON_DAYS = 30           # how far ahead to predict
HIGH_IMPACT_THRESHOLD = 0.7            # above this = high impact event


# ── Helpers ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().isoformat()


def _timestamp() -> float:
    return time.time()


# ── Data Classes ────────────────────────────────────────────────────────────

@dataclass
class WorldEvent:
    """A single observed event in the external world."""
    event_type: str                     # domain: "tech", "economy", "science", etc.
    description: str                    # what happened
    impact: float                       # 0.0 (negligible) → 1.0 (transformative)
    timestamp: str = field(default_factory=_now)
    source: str = ""                    # where this info came from
    relevance_score: float = 0.5        # how relevant to the user (0.0–1.0)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    entities: List[str] = field(default_factory=list)     # people, orgs, places involved
    causal_links: List[str] = field(default_factory=list) # IDs of events this relates to
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WorldEvent":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Trend:
    """An identified pattern or trajectory in a domain."""
    domain: str
    direction: str                      # "rising", "declining", "stable", "volatile"
    description: str
    strength: float                     # 0.0–1.0 how strong the trend is
    event_count: int = 0
    first_seen: str = field(default_factory=_now)
    last_seen: str = field(default_factory=_now)
    trend_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Trend":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── World Simulation Engine ─────────────────────────────────────────────────

class WorldSimulation:
    """
    Real-time world model — FRIDAY's situational awareness engine.

    Maintains an evolving internal model of the external world,
    tracks trends, predicts outcomes, and filters for relevance.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._events: Dict[str, List[WorldEvent]] = defaultdict(list)  # domain → events
        self._trends: Dict[str, List[Trend]] = defaultdict(list)       # domain → trends
        self._user_interests: Dict[str, float] = {}                    # topic → weight
        self._domain_activity: Dict[str, Dict[str, Any]] = {}          # domain → stats
        self._prediction_history: List[dict] = []
        self._data: Dict[str, Any] = {}
        self._session_ingested = 0
        self._session_predictions = 0
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": _now(),
                "last_update": _now(),
                "total_events_ingested": 0,
                "total_predictions": 0,
                "total_counterfactuals": 0,
            },
            "events": {},               # domain → [event_dicts]
            "trends": {},               # domain → [trend_dicts]
            "user_interests": {},       # topic → weight
            "domain_activity": {},
            "prediction_history": [],
        }

    def _load(self):
        if not WORLD_STATE_FILE.exists():
            self._data = self._empty_store()
            self._save()
            return
        try:
            raw = WORLD_STATE_FILE.read_text(encoding="utf-8")
            self._data = json.loads(raw)
            # Rebuild objects
            for domain, e_list in self._data.get("events", {}).items():
                self._events[domain] = [WorldEvent.from_dict(e) for e in e_list]
            for domain, t_list in self._data.get("trends", {}).items():
                self._trends[domain] = [Trend.from_dict(t) for t in t_list]
            self._user_interests = self._data.get("user_interests", {})
            self._domain_activity = self._data.get("domain_activity", {})
            self._prediction_history = self._data.get("prediction_history", [])
        except (json.JSONDecodeError, IOError):
            self._data = self._empty_store()
            self._save()

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._data["events"] = {
                domain: [e.to_dict() for e in e_list]
                for domain, e_list in self._events.items()
            }
            self._data["trends"] = {
                domain: [t.to_dict() for t in t_list]
                for domain, t_list in self._trends.items()
            }
            self._data["user_interests"] = self._user_interests
            self._data["domain_activity"] = self._domain_activity
            self._data["prediction_history"] = self._prediction_history[-100:]
            self._data["meta"]["last_update"] = _now()
            WORLD_STATE_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ── Event Ingestion ─────────────────────────────────────────────────

    def ingest_event(self, event_type: str, data: Dict[str, Any]) -> WorldEvent:
        """
        Process a new world event.

        Args:
            event_type: Domain/category (e.g., "tech", "economy", "science")
            data: Event details — must include "description".
                  Optional: impact, source, entities, metadata

        Returns:
            The created WorldEvent
        """
        event = WorldEvent(
            event_type=event_type,
            description=data.get("description", ""),
            impact=min(1.0, max(0.0, float(data.get("impact", 0.5)))),
            source=data.get("source", ""),
            relevance_score=self._compute_relevance(event_type, data),
            entities=data.get("entities", []),
            metadata=data.get("metadata", {}),
        )

        with self._lock:
            self._events[event_type].append(event)
            self._session_ingested += 1
            self._data["meta"]["total_events_ingested"] += 1

            # Enforce capacity
            if len(self._events[event_type]) > MAX_EVENTS_PER_DOMAIN:
                # Keep newest, drop oldest low-impact
                self._events[event_type].sort(
                    key=lambda e: (e.impact, e.timestamp), reverse=True
                )
                self._events[event_type] = self._events[event_type][:MAX_EVENTS_PER_DOMAIN]

            total = sum(len(el) for el in self._events.values())
            if total > MAX_TOTAL_EVENTS:
                self._prune_lowest_impact()

            # Update domain activity
            self._update_domain_activity(event_type)
            self._save()

        return event

    def _compute_relevance(self, event_type: str, data: Dict[str, Any]) -> float:
        """Compute how relevant an event is to the user based on their interests."""
        base = 0.5
        # Boost if domain matches user interests
        domain_weight = self._user_interests.get(event_type, 0.0)
        # Check entity overlap
        entities = set(data.get("entities", []))
        interest_entities = {k for k, v in self._user_interests.items() if v > 0.6}
        entity_overlap = len(entities & interest_entities)

        relevance = base + domain_weight * 0.3 + entity_overlap * 0.1
        return min(1.0, max(0.0, relevance))

    def _update_domain_activity(self, domain: str):
        """Update activity stats for a domain."""
        events = self._events.get(domain, [])
        if not events:
            return
        impacts = [e.impact for e in events]
        self._domain_activity[domain] = {
            "event_count": len(events),
            "avg_impact": round(sum(impacts) / len(impacts), 3),
            "max_impact": round(max(impacts), 3),
            "last_event": events[-1].timestamp,
            "updated": _now(),
        }

    def _prune_lowest_impact(self):
        """Remove lowest-impact events across all domains to stay under total cap."""
        all_events: List[Tuple[str, WorldEvent]] = []
        for domain, elist in self._events.items():
            for e in elist:
                all_events.append((domain, e))
        all_events.sort(key=lambda x: x[1].impact)

        excess = sum(len(el) for el in self._events.values()) - MAX_TOTAL_EVENTS
        if excess <= 0:
            return
        to_remove = set()
        for i in range(min(excess, len(all_events))):
            to_remove.add((all_events[i][0], all_events[i][1].event_id))

        for domain in list(self._events.keys()):
            self._events[domain] = [
                e for e in self._events[domain]
                if (domain, e.event_id) not in to_remove
            ]

    # ── Prediction ──────────────────────────────────────────────────────

    def predict_outcomes(self, scenario: str) -> List[dict]:
        """
        Predict what will happen next based on current world state and a scenario.

        Uses causal chain analysis: finds events similar to the scenario,
        traces their historical outcomes, and projects likely results.

        Args:
            scenario: Description of the situation to predict outcomes for

        Returns:
            List of predicted outcomes with probabilities and reasoning
        """
        with self._lock:
            self._session_predictions += 1
            self._data["meta"]["total_predictions"] += 1

        # Find relevant events across domains
        scenario_lower = scenario.lower()
        relevant: List[WorldEvent] = []
        for domain, elist in self._events.items():
            for event in elist:
                # Keyword overlap scoring
                event_words = set(event.description.lower().split())
                scenario_words = set(scenario_lower.split())
                overlap = len(event_words & scenario_words)
                if overlap >= 2 or any(
                    entity.lower() in scenario_lower
                    for entity in event.entities
                ):
                    relevant.append(event)

        # Sort by relevance and impact
        relevant.sort(key=lambda e: e.relevance_score * e.impact, reverse=True)
        relevant = relevant[:20]

        if not relevant:
            predictions = [{
                "outcome": "insufficient_data",
                "probability": 0.0,
                "reasoning": "No similar historical events found to base predictions on.",
                "confidence": "low",
            }]
        else:
            predictions = self._generate_predictions(scenario, relevant)

        # Record prediction
        record = {
            "scenario": scenario[:200],
            "predictions": predictions,
            "events_analyzed": len(relevant),
            "timestamp": _now(),
        }
        with self._lock:
            self._prediction_history.append(record)

        self._save()
        return predictions

    def _generate_predictions(self, scenario: str,
                               events: List[WorldEvent]) -> List[dict]:
        """Generate predictions from relevant historical events."""
        predictions = []

        # Group by impact level
        high_impact = [e for e in events if e.impact >= HIGH_IMPACT_THRESHOLD]
        recent = [e for e in events if self._days_since(e.timestamp) < 30]

        # Prediction 1: Based on high-impact events
        if high_impact:
            top = high_impact[0]
            predictions.append({
                "outcome": f"Similar trajectory to: {top.description[:100]}",
                "probability": min(0.8, top.impact * 0.7 + top.relevance_score * 0.3),
                "reasoning": f"Pattern match with high-impact {top.event_type} event "
                             f"(impact={top.impact:.2f})",
                "confidence": "medium" if len(high_impact) >= 3 else "low",
                "based_on": top.event_id,
            })

        # Prediction 2: Based on recent momentum
        if recent:
            avg_recent_impact = sum(e.impact for e in recent) / len(recent)
            direction = "accelerating" if avg_recent_impact > 0.6 else "stabilizing"
            predictions.append({
                "outcome": f"Domain momentum is {direction}",
                "probability": min(0.7, avg_recent_impact),
                "reasoning": f"{len(recent)} recent events with avg impact "
                             f"{avg_recent_impact:.2f}",
                "confidence": "medium",
            })

        # Prediction 3: Causal chain projection
        chain_events = [e for e in events if e.causal_links]
        if chain_events:
            predictions.append({
                "outcome": "Causal chain continuation likely",
                "probability": 0.5,
                "reasoning": f"{len(chain_events)} events have established causal links, "
                             f"suggesting predictable follow-on effects",
                "confidence": "low",
            })

        # Default if nothing specific
        if not predictions:
            predictions.append({
                "outcome": "No clear trajectory — novel situation",
                "probability": 0.3,
                "reasoning": "Insufficient pattern overlap for confident prediction",
                "confidence": "low",
            })

        return predictions

    def _days_since(self, timestamp_str: str) -> float:
        """Calculate days elapsed since a timestamp."""
        try:
            dt = datetime.fromisoformat(timestamp_str)
            return (datetime.now() - dt).total_seconds() / 86400.0
        except (ValueError, TypeError):
            return 999.0

    # ── Trend Detection ─────────────────────────────────────────────────

    def detect_trends(self, domain: str) -> List[Trend]:
        """
        Identify patterns and trajectories in a domain over time.

        Analyzes event frequency, impact trajectories, and entity
        co-occurrence to detect emerging trends.

        Args:
            domain: The domain to analyze (e.g., "tech", "economy")

        Returns:
            List of detected Trend objects
        """
        with self._lock:
            events = self._events.get(domain, [])
            if len(events) < TREND_MIN_EVENTS:
                return []

            # Filter to recent window
            cutoff = datetime.now() - timedelta(days=TREND_TIME_WINDOW_DAYS)
            recent = []
            for e in events:
                try:
                    if datetime.fromisoformat(e.timestamp) >= cutoff:
                        recent.append(e)
                except (ValueError, TypeError):
                    continue

            if len(recent) < TREND_MIN_EVENTS:
                return []

            # Sort by timestamp
            recent.sort(key=lambda e: e.timestamp)

            trends = self._analyze_trend_signals(domain, recent)

            # Store detected trends
            self._trends[domain] = trends[:10]  # keep top 10 per domain
            self._save()

            return trends

    def _analyze_trend_signals(self, domain: str,
                                events: List[WorldEvent]) -> List[Trend]:
        """Analyze event signals to identify trends."""
        trends = []
        now = _now()

        # Trend 1: Impact trajectory
        half = len(events) // 2
        first_half_impact = sum(e.impact for e in events[:half]) / max(half, 1)
        second_half_impact = sum(e.impact for e in events[half:]) / max(len(events) - half, 1)

        if second_half_impact > first_half_impact * 1.3:
            trends.append(Trend(
                domain=domain,
                direction="rising",
                description=f"Impact levels rising in {domain} "
                            f"({first_half_impact:.2f} → {second_half_impact:.2f})",
                strength=min(1.0, (second_half_impact - first_half_impact) / 0.5),
                event_count=len(events),
                first_seen=events[0].timestamp,
                last_seen=events[-1].timestamp,
            ))
        elif first_half_impact > second_half_impact * 1.3:
            trends.append(Trend(
                domain=domain,
                direction="declining",
                description=f"Impact levels declining in {domain} "
                            f"({first_half_impact:.2f} → {second_half_impact:.2f})",
                strength=min(1.0, (first_half_impact - second_half_impact) / 0.5),
                event_count=len(events),
                first_seen=events[0].timestamp,
                last_seen=events[-1].timestamp,
            ))

        # Trend 2: Frequency acceleration
        time_span = self._days_since(events[0].timestamp)
        if time_span > 7:
            recent_7d = sum(1 for e in events if self._days_since(e.timestamp) < 7)
            older_7d = sum(1 for e in events
                          if 7 <= self._days_since(e.timestamp) < 14)
            if older_7d > 0 and recent_7d > older_7d * 1.5:
                trends.append(Trend(
                    domain=domain,
                    direction="accelerating",
                    description=f"Event frequency accelerating in {domain} "
                                f"({older_7d}/week → {recent_7d}/week)",
                    strength=min(1.0, recent_7d / max(older_7d, 1) / 3),
                    event_count=len(events),
                    first_seen=events[0].timestamp,
                    last_seen=events[-1].timestamp,
                ))

        # Trend 3: Entity clustering (recurring topics)
        entity_freq: Dict[str, int] = defaultdict(int)
        for e in events:
            for entity in e.entities:
                entity_freq[entity] += 1

        hot_entities = [
            (entity, count) for entity, count in entity_freq.items()
            if count >= TREND_MIN_EVENTS
        ]
        hot_entities.sort(key=lambda x: x[1], reverse=True)

        for entity, count in hot_entities[:3]:
            trends.append(Trend(
                domain=domain,
                direction="rising",
                description=f"'{entity}' is a recurring focus in {domain} "
                            f"({count} mentions)",
                strength=min(1.0, count / len(events)),
                event_count=count,
                first_seen=events[0].timestamp,
                last_seen=events[-1].timestamp,
            ))

        # Trend 4: Volatility detection
        if len(events) >= 5:
            impacts = [e.impact for e in events]
            mean_impact = sum(impacts) / len(impacts)
            variance = sum((i - mean_impact) ** 2 for i in impacts) / len(impacts)
            if variance > 0.1:
                trends.append(Trend(
                    domain=domain,
                    direction="volatile",
                    description=f"High impact variance in {domain} "
                                f"(σ²={variance:.3f}) — unstable landscape",
                    strength=min(1.0, variance * 3),
                    event_count=len(events),
                    first_seen=events[0].timestamp,
                    last_seen=events[-1].timestamp,
                ))

        # Sort by strength
        trends.sort(key=lambda t: t.strength, reverse=True)
        return trends

    # ── User Relevance ──────────────────────────────────────────────────

    def get_user_relevant_events(self, limit: int = 20) -> List[WorldEvent]:
        """
        Get events most relevant to the user based on their interests.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of WorldEvent objects sorted by relevance
        """
        with self._lock:
            all_events: List[WorldEvent] = []
            for elist in self._events.values():
                all_events.extend(elist)

            # Apply time decay to relevance
            for event in all_events:
                days = self._days_since(event.timestamp)
                decay = math.pow(2, -days / EVENT_RELEVANCE_DECAY_DAYS)
                event.relevance_score = event.relevance_score * decay

            # Sort by relevance × impact
            all_events.sort(
                key=lambda e: e.relevance_score * (0.5 + 0.5 * e.impact),
                reverse=True,
            )
            return all_events[:limit]

    def update_user_world_model(self, interests: Dict[str, float]):
        """
        Update the model of what world events the user cares about.

        Args:
            interests: Dict mapping topic/domain to importance weight (0.0–1.0)
                       e.g., {"tech": 0.9, "ai": 0.8, "finance": 0.3}
        """
        with self._lock:
            for topic, weight in interests.items():
                self._user_interests[topic.lower()] = min(1.0, max(0.0, weight))

            # Update relevance scores for existing events
            for domain, elist in self._events.items():
                for event in elist:
                    event.relevance_score = self._compute_relevance(
                        domain,
                        {"entities": event.entities},
                    )

            self._save()

    # ── Counterfactual Simulation ───────────────────────────────────────

    def simulate_counterfactual(self, change: str) -> dict:
        """
        Simulate "what if the world was different?"

        Given a hypothetical change, traces causal chains to estimate
        how the world state would differ from reality.

        Args:
            change: Description of the hypothetical change
                    e.g., "What if the Fed had not raised rates?"

        Returns:
            Dict with simulated alternate world state
        """
        with self._lock:
            self._data["meta"]["total_counterfactuals"] = (
                self._data["meta"].get("total_counterfactuals", 0) + 1
            )

        change_lower = change.lower()

        # Find events that would be affected
        affected_events: List[WorldEvent] = []
        unaffected_events: List[WorldEvent] = []

        for domain, elist in self._events.items():
            for event in elist:
                # Check if event is causally related to the change
                relevance = 0.0
                event_words = set(event.description.lower().split())
                change_words = set(change_lower.split())
                overlap = len(event_words & change_words)
                if overlap >= 2:
                    relevance += 0.3
                if any(entity.lower() in change_lower for entity in event.entities):
                    relevance += 0.4
                if event.event_type.lower() in change_lower:
                    relevance += 0.2

                if relevance >= 0.3:
                    affected_events.append(event)
                else:
                    unaffected_events.append(event)

        # Compute alternate world metrics
        if affected_events:
            original_avg_impact = (
                sum(e.impact for e in affected_events) / len(affected_events)
            )
            # In counterfactual: affected events would have different impact
            altered_avg_impact = original_avg_impact * 0.6  # dampened
            impact_delta = altered_avg_impact - original_avg_impact
        else:
            original_avg_impact = 0.0
            altered_avg_impact = 0.0
            impact_delta = 0.0

        result = {
            "counterfactual": change,
            "affected_domains": list(set(e.event_type for e in affected_events)),
            "events_affected": len(affected_events),
            "events_unaffected": len(unaffected_events),
            "original_world": {
                "avg_impact_affected": round(original_avg_impact, 3),
                "total_events": len(affected_events) + len(unaffected_events),
            },
            "counterfactual_world": {
                "avg_impact_affected": round(altered_avg_impact, 3),
                "impact_delta": round(impact_delta, 3),
                "description": self._describe_counterfactual(change, affected_events),
            },
            "confidence": "low" if len(affected_events) < 3 else "medium",
            "timestamp": _now(),
        }

        self._save()
        return result

    def _describe_counterfactual(self, change: str,
                                  affected: List[WorldEvent]) -> str:
        """Generate a human-readable description of the counterfactual world."""
        if not affected:
            return (f"If '{change}' were true, minimal impact detected — "
                    f"few existing events would be directly affected.")

        domains = set(e.event_type for e in affected)
        high_impact_affected = [e for e in affected if e.impact >= HIGH_IMPACT_THRESHOLD]

        parts = [f"If '{change}' were true:"]
        if high_impact_affected:
            parts.append(
                f"  - {len(high_impact_affected)} high-impact events in "
                f"{', '.join(domains)} would likely be altered"
            )
        parts.append(
            f"  - {len(affected)} total events across {len(domains)} domains "
            f"would be affected"
        )
        parts.append(
            "  - Downstream causal chains suggest ripple effects would "
            "modify subsequent events"
        )
        return "\n".join(parts)

    # ── World State ─────────────────────────────────────────────────────

    def get_world_state(self) -> dict:
        """
        Get current understanding of the world.

        Returns a comprehensive snapshot of the world model including
        active domains, recent high-impact events, and trend summary.
        """
        with self._lock:
            # Gather high-impact recent events
            high_impact: List[WorldEvent] = []
            for elist in self._events.values():
                for e in elist:
                    if e.impact >= HIGH_IMPACT_THRESHOLD:
                        high_impact.append(e)
            high_impact.sort(key=lambda e: e.impact, reverse=True)

            # Gather active trends
            all_trends: List[Trend] = []
            for tlist in self._trends.values():
                all_trends.extend(tlist)
            all_trends.sort(key=lambda t: t.strength, reverse=True)

            return {
                "total_events": sum(len(el) for el in self._events.values()),
                "active_domains": list(self._events.keys()),
                "total_trends": sum(len(tl) for tl in self._trends.values()),
                "high_impact_events": [
                    {
                        "description": e.description[:100],
                        "domain": e.event_type,
                        "impact": e.impact,
                        "timestamp": e.timestamp,
                    }
                    for e in high_impact[:5]
                ],
                "active_trends": [
                    {
                        "domain": t.domain,
                        "direction": t.direction,
                        "description": t.description[:100],
                        "strength": t.strength,
                    }
                    for t in all_trends[:5]
                ],
                "user_interests": dict(self._user_interests),
                "domains_tracked": len(self._events),
                "last_update": self._data["meta"].get("last_update", _now()),
            }

    # ── Statistics ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get overall world simulation statistics."""
        with self._lock:
            total_events = sum(len(el) for el in self._events.values())
            total_trends = sum(len(tl) for tl in self._trends.values())
            total_predictions = self._data["meta"].get("total_predictions", 0)
            total_counterfactuals = self._data["meta"].get("total_counterfactuals", 0)

            domain_summary = {}
            for domain, stats in self._domain_activity.items():
                domain_summary[domain] = {
                    "events": stats.get("event_count", 0),
                    "avg_impact": stats.get("avg_impact", 0.0),
                }

            return {
                "total_events": total_events,
                "total_trends": total_trends,
                "domains_tracked": len(self._events),
                "total_predictions": total_predictions,
                "total_counterfactuals": total_counterfactuals,
                "user_interests_count": len(self._user_interests),
                "session_ingested": self._session_ingested,
                "session_predictions": self._session_predictions,
                "domain_summary": domain_summary,
            }

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """Format world state awareness for system prompt injection."""
        stats = self.get_stats()
        state = self.get_world_state()

        parts = [
            "[WORLD SIMULATION — Situational awareness]",
            f"Tracking {stats['total_events']} events across "
            f"{stats['domains_tracked']} domains | "
            f"{stats['total_trends']} active trends",
        ]

        # Top high-impact events
        if state["high_impact_events"]:
            parts.append("High-impact events:")
            for e in state["high_impact_events"][:3]:
                parts.append(
                    f"  • [{e['domain']}] {e['description']} "
                    f"(impact={e['impact']:.2f})"
                )

        # Active trends
        if state["active_trends"]:
            parts.append("Active trends:")
            for t in state["active_trends"][:3]:
                parts.append(
                    f"  • {t['domain']}: {t['direction']} — {t['description']}"
                )

        # User interests
        if state["user_interests"]:
            top_interests = sorted(
                state["user_interests"].items(),
                key=lambda x: x[1], reverse=True,
            )[:5]
            interest_str = ", ".join(
                f"{k}({v:.1f})" for k, v in top_interests
            )
            parts.append(f"User focus: {interest_str}")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "[...]"
        return result


# ── Singleton ───────────────────────────────────────────────────────────────

_world_simulation = None
_world_simulation_lock = threading.Lock()


def get_world_simulation() -> WorldSimulation:
    """Get singleton WorldSimulation instance."""
    global _world_simulation
    if _world_simulation is None:
        with _world_simulation_lock:
            if _world_simulation is None:
                _world_simulation = WorldSimulation()
    return _world_simulation
