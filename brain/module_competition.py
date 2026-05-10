"""
module_competition.py — FRIDAY Module Competition System
=========================================================

Implements bottom-up competitive processing between brain modules,
inspired by Minsky's Society of Mind and Global Workspace Theory.

Instead of a rigid top-down orchestration pipeline, modules *bid* for
the right to process each input. The highest-scoring bid wins the
primary processing slot, runners-up get advisory roles, and the system
learns which module combinations produce emergent synergies or
destructive interference over time.

Architecture:
  ModuleRegistry → BiddingRound → ResourceAllocator → NegotiationProtocol
       ↓                ↓               ↓                    ↓
  register()      collect bids    allocate slots      resolve conflicts
                   score & rank    track usage         escalate if needed
       ↓                ↓               ↓                    ↓
              EmergentBehaviorDetector ← outcome tracking

Integration:
  - Global Workspace: bidding happens before event broadcast
  - AGI Orchestrator: competition replaces the rigid cognitive pipeline
"""

import json
import threading
import time
import importlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

BRAIN_DIR = Path(__file__).parent.resolve()
DATA_FILE = BRAIN_DIR / "competition_data.json"

# Tuning constants
COALITION_THRESHOLD = 0.85      # Min combined synergy to form coalitions
INTERFERENCE_THRESHOLD = -0.2   # Below this = destructive interference
SYNERGY_MIN_SAMPLES = 3         # Min observations before declaring synergy
MAX_ADVISORY_SLOTS = 3          # Runners-up who get advisory roles
NEGOTIATION_MAX_ROUNDS = 5      # Max negotiation rounds before escalation
RESOURCE_BUDGET_DEFAULT = 1.0   # Default resource budget per bidding round


# ─── Module Bid ───────────────────────────────────────────────────────────

@dataclass
class ModuleBid:
    """
    A module's bid for processing an input.

    Each bid declares how confident the module is, what it would cost,
    and how relevant it considers itself to the current stimulus.
    """
    module_name: str
    confidence: float           # 0-1: how confident it can handle this
    estimated_cost: float       # Time/resource units (lower = cheaper)
    relevance_score: float      # 0-1: how relevant to current input
    priority: float = 0.5       # Module's current priority level (0-1)
    interests: List[str] = field(default_factory=list)  # What it can handle
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def composite_score(self) -> float:
        """Score = relevance × confidence × priority, penalised by cost."""
        base = self.relevance_score * self.confidence * self.priority
        # Cost penalty: higher cost reduces score, but never to zero
        cost_factor = max(0.1, 1.0 - (self.estimated_cost * 0.1))
        return base * cost_factor

    def to_dict(self) -> dict:
        return {
            "module_name": self.module_name,
            "confidence": round(self.confidence, 4),
            "estimated_cost": round(self.estimated_cost, 4),
            "relevance_score": round(self.relevance_score, 4),
            "priority": round(self.priority, 4),
            "composite_score": round(self.composite_score, 4),
            "interests": self.interests,
            "timestamp": self.timestamp,
        }


# ─── Registered Module ───────────────────────────────────────────────────

@dataclass
class RegisteredModule:
    """A module registered in the competition system."""
    name: str
    interests: List[str]           # What input types it handles
    base_priority: float = 0.5     # Default priority (0-1)
    instance: Any = None           # The actual module object
    success_count: int = 0
    failure_count: int = 0
    total_bids: int = 0
    total_wins: int = 0
    avg_confidence: float = 0.5

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5

    @property
    def win_rate(self) -> float:
        return self.total_wins / self.total_bids if self.total_bids > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "interests": self.interests,
            "base_priority": round(self.base_priority, 4),
            "success_rate": round(self.success_rate, 4),
            "win_rate": round(self.win_rate, 4),
            "total_bids": self.total_bids,
            "total_wins": self.total_wins,
            "avg_confidence": round(self.avg_confidence, 4),
        }


# ─── Bidding Round ────────────────────────────────────────────────────────

class BiddingRound:
    """
    One round of competitive bidding.

    Collects bids from all registered modules, scores them, selects a
    winner and runners-up, and optionally forms coalitions when multiple
    modules have complementary strengths.
    """

    def __init__(self):
        self._bids: List[ModuleBid] = []
        self._round_id: str = f"round_{int(time.time() * 1000)}"
        self._start_time: float = time.time()

    def add_bid(self, bid: ModuleBid) -> None:
        """Add a module bid to this round."""
        self._bids.append(bid)

    def get_bids(self) -> List[ModuleBid]:
        """All bids in this round, sorted by composite score descending."""
        return sorted(self._bids, key=lambda b: b.composite_score, reverse=True)

    def select_winner(self) -> Optional[ModuleBid]:
        """Return the highest-scoring bid, or None if no bids."""
        if not self._bids:
            return None
        return max(self._bids, key=lambda b: b.composite_score)

    def select_runners_up(self, max_count: int = MAX_ADVISORY_SLOTS) -> List[ModuleBid]:
        """Return the next-best bids (excluding winner) for advisory roles."""
        winner = self.select_winner()
        if winner is None:
            return []
        others = [b for b in self._bids if b.module_name != winner.module_name]
        others.sort(key=lambda b: b.composite_score, reverse=True)
        return others[:max_count]

    def detect_coalition(self, synergy_data: Dict[Tuple[str, ...], float]) -> Optional[List[ModuleBid]]:
        """
        Check if any combination of bidders has known synergy above threshold.

        Args:
            synergy_data: Dict mapping frozensets of module names to synergy scores.

        Returns:
            List of bids forming a coalition, or None if no coalition is viable.
        """
        if len(self._bids) < 2:
            return None

        sorted_bids = self.get_bids()
        best_coalition = None
        best_combined = 0.0

        # Check pairs for known synergies
        for i, bid_a in enumerate(sorted_bids):
            for bid_b in sorted_bids[i + 1:]:
                key = tuple(sorted([bid_a.module_name, bid_b.module_name]))
                synergy = synergy_data.get(key, 0.0)
                if synergy > COALITION_THRESHOLD:
                    combined = bid_a.composite_score + bid_b.composite_score + synergy * 0.2
                    if combined > best_combined:
                        best_combined = combined
                        best_coalition = [bid_a, bid_b]

        return best_coalition

    def to_dict(self) -> dict:
        return {
            "round_id": self._round_id,
            "bid_count": len(self._bids),
            "bids": [b.to_dict() for b in self.get_bids()],
            "winner": self.select_winner().module_name if self.select_winner() else None,
            "elapsed_ms": round((time.time() - self._start_time) * 1000, 1),
        }


# ─── Resource Allocator ──────────────────────────────────────────────────

class ResourceAllocator:
    """
    Allocate compute/time slots based on bidding results.

    Winner gets the primary processing slot; runners-up get advisory
    slots where they can contribute suggestions. Tracks resource usage
    per module over time.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._usage: Dict[str, Dict[str, float]] = defaultdict(
            lambda: {"total_time": 0.0, "total_allocations": 0, "primary_slots": 0, "advisory_slots": 0}
        )
        self._active_slots: Dict[str, str] = {}  # slot_id → module_name

    def allocate(self, round_result: BiddingRound) -> dict:
        """
        Allocate processing slots based on a bidding round's results.

        Returns:
            Dict with primary_slot, advisory_slots, and allocation metadata.
        """
        with self._lock:
            winner = round_result.select_winner()
            runners_up = round_result.select_runners_up()

            allocation = {
                "round_id": round_result._round_id,
                "primary": None,
                "advisory": [],
                "timestamp": time.time(),
            }

            if winner:
                slot_id = f"primary_{int(time.time() * 1000)}"
                allocation["primary"] = {
                    "module": winner.module_name,
                    "score": round(winner.composite_score, 4),
                    "slot_id": slot_id,
                }
                self._active_slots[slot_id] = winner.module_name
                self._usage[winner.module_name]["primary_slots"] += 1
                self._usage[winner.module_name]["total_allocations"] += 1

            for runner in runners_up:
                slot_id = f"advisory_{runner.module_name}_{int(time.time() * 1000)}"
                allocation["advisory"].append({
                    "module": runner.module_name,
                    "score": round(runner.composite_score, 4),
                    "slot_id": slot_id,
                })
                self._usage[runner.module_name]["advisory_slots"] += 1
                self._usage[runner.module_name]["total_allocations"] += 1

            return allocation

    def record_usage(self, module_name: str, time_used: float) -> None:
        """Record actual resource usage after processing."""
        with self._lock:
            self._usage[module_name]["total_time"] += time_used

    def get_usage(self, module_name: str) -> dict:
        """Get resource usage stats for a module."""
        with self._lock:
            return dict(self._usage.get(module_name, {}))

    def get_all_usage(self) -> Dict[str, dict]:
        """Get resource usage for all modules."""
        with self._lock:
            return {k: dict(v) for k, v in self._usage.items()}

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "active_slots": dict(self._active_slots),
                "usage": {k: dict(v) for k, v in self._usage.items()},
            }


# ─── Negotiation Protocol ────────────────────────────────────────────────

class NegotiationProtocol:
    """
    Resolve conflicts when modules want contradictory actions.

    Uses priority, confidence, and past success rate as tiebreakers.
    Escalates to meta-cognition if no resolution is found within
    the maximum negotiation rounds.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._negotiation_history: List[dict] = []

    def negotiate(
        self,
        module_a: str,
        proposal_a: dict,
        confidence_a: float,
        priority_a: float,
        success_rate_a: float,
        module_b: str,
        proposal_b: dict,
        confidence_b: float,
        priority_b: float,
        success_rate_b: float,
    ) -> dict:
        """
        Negotiate between two modules with conflicting proposals.

        Scoring: priority × 0.4 + confidence × 0.3 + success_rate × 0.3

        Returns:
            Dict with winner, loser, method (score/escalated), and details.
        """
        with self._lock:
            score_a = priority_a * 0.4 + confidence_a * 0.3 + success_rate_a * 0.3
            score_b = priority_b * 0.4 + confidence_b * 0.3 + success_rate_b * 0.3

            margin = abs(score_a - score_b)
            result: Dict[str, Any] = {
                "timestamp": time.time(),
                "module_a": module_a,
                "module_b": module_b,
                "score_a": round(score_a, 4),
                "score_b": round(score_b, 4),
                "margin": round(margin, 4),
            }

            # If margin is very small, escalate
            if margin < 0.05:
                result["method"] = "escalated"
                result["winner"] = None
                result["reason"] = "Scores too close — needs meta-cognition"
                print(f"[ModuleCompetition] Negotiation escalated: {module_a} vs {module_b} "
                      f"(margin={margin:.4f})")
            else:
                if score_a >= score_b:
                    result["winner"] = module_a
                    result["loser"] = module_b
                else:
                    result["winner"] = module_b
                    result["loser"] = module_a
                result["method"] = "score"
                result["reason"] = f"Higher weighted score ({margin:.4f} margin)"

            self._negotiation_history.append(result)
            if len(self._negotiation_history) > 200:
                self._negotiation_history = self._negotiation_history[-200:]

            return result

    def get_history(self, n: int = 20) -> List[dict]:
        """Recent negotiation results."""
        with self._lock:
            return list(self._negotiation_history[-n:])

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "total_negotiations": len(self._negotiation_history),
                "recent": [self._negotiation_history[-1]] if self._negotiation_history else [],
            }


# ─── Emergent Behavior Detector ──────────────────────────────────────────

class EmergentBehaviorDetector:
    """
    Detect patterns from module interactions over time.

    Tracks which module combinations produce successful outcomes,
    detects synergies (A + B > A alone) and interference (A + B < A alone),
    and reports emergent patterns to the Global Workspace.
    """

    def __init__(self):
        self._lock = threading.RLock()
        # Outcome tracking: (module_set_tuple) → list of success/failure
        self._combination_outcomes: Dict[Tuple[str, ...], List[bool]] = defaultdict(list)
        # Solo outcomes: module_name → list of success/failure
        self._solo_outcomes: Dict[str, List[bool]] = defaultdict(list)
        # Discovered patterns
        self._synergies: Dict[Tuple[str, ...], float] = {}
        self._interferences: Dict[Tuple[str, ...], float] = {}

    def record_solo_outcome(self, module_name: str, success: bool) -> None:
        """Record the outcome of a solo module execution."""
        with self._lock:
            self._solo_outcomes[module_name].append(success)
            # Keep bounded
            if len(self._solo_outcomes[module_name]) > 100:
                self._solo_outcomes[module_name] = self._solo_outcomes[module_name][-100:]

    def record_combination_outcome(self, modules: List[str], success: bool) -> None:
        """Record the outcome of a multi-module collaboration."""
        with self._lock:
            key = tuple(sorted(modules))
            self._combination_outcomes[key].append(success)
            if len(self._combination_outcomes[key]) > 100:
                self._combination_outcomes[key] = self._combination_outcomes[key][-100:]

    def detect_patterns(self) -> dict:
        """
        Analyze all recorded outcomes for synergy and interference.

        Synergy: combination success rate > best solo success rate among members.
        Interference: combination success rate < worst solo success rate among members.

        Returns:
            Dict with discovered synergies and interferences.
        """
        with self._lock:
            new_synergies: Dict[Tuple[str, ...], float] = {}
            new_interferences: Dict[Tuple[str, ...], float] = {}

            for combo, outcomes in self._combination_outcomes.items():
                if len(outcomes) < SYNERGY_MIN_SAMPLES:
                    continue

                combo_rate = sum(outcomes) / len(outcomes)

                # Compare against solo rates
                solo_rates = []
                for member in combo:
                    solo = self._solo_outcomes.get(member, [])
                    if solo:
                        solo_rates.append(sum(solo) / len(solo))

                if not solo_rates:
                    continue

                best_solo = max(solo_rates)
                worst_solo = min(solo_rates)

                synergy_delta = combo_rate - best_solo
                interference_delta = combo_rate - worst_solo

                if synergy_delta > 0.1:  # 10% better than best solo
                    new_synergies[combo] = round(synergy_delta, 4)
                if interference_delta < INTERFERENCE_THRESHOLD:
                    new_interferences[combo] = round(interference_delta, 4)

            self._synergies = new_synergies
            self._interferences = new_interferences

            return {
                "synergies": {str(k): v for k, v in new_synergies.items()},
                "interferences": {str(k): v for k, v in new_interferences.items()},
                "total_combinations_tracked": len(self._combination_outcomes),
                "total_solo_tracked": len(self._solo_outcomes),
            }

    def get_synergy_score(self, modules: List[str]) -> float:
        """Get the known synergy score for a combination of modules."""
        key = tuple(sorted(modules))
        with self._lock:
            return self._synergies.get(key, 0.0)

    def get_synergies(self) -> Dict[Tuple[str, ...], float]:
        """All known synergies."""
        with self._lock:
            return dict(self._synergies)

    def get_interferences(self) -> Dict[Tuple[str, ...], float]:
        """All known interferences."""
        with self._lock:
            return dict(self._interferences)

    async def report_to_workspace(self, patterns: dict) -> None:
        """Report emergent patterns to the Global Workspace."""
        try:
            from brain.global_workspace import get_global_workspace
            from brain.workspace_events import EventType, WorkspaceEvent

            gw = get_global_workspace()
            event = WorkspaceEvent(
                source="module_competition",
                type=EventType.REFLECTION,
                content={
                    "kind": "emergent_patterns",
                    "synergies": len(patterns.get("synergies", {})),
                    "interferences": len(patterns.get("interferences", {})),
                    "details": patterns,
                },
                importance=0.5,
            )
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(gw.publish(event))
            except RuntimeError:
                pass
        except Exception as e:
            print(f"[ModuleCompetition] Failed to report patterns to workspace: {e}")

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "synergies": {str(k): v for k, v in self._synergies.items()},
                "interferences": {str(k): v for k, v in self._interferences.items()},
                "combinations_tracked": len(self._combination_outcomes),
                "solo_tracked": len(self._solo_outcomes),
            }


# ─── Module Registry ─────────────────────────────────────────────────────

class ModuleRegistry:
    """
    Registry for brain modules participating in competition.

    Each module declares its interests (what inputs it handles) and
    base priority. The registry can auto-discover available brain modules.
    """

    # Known brain modules and their default interests
    KNOWN_MODULES: Dict[str, Dict[str, Any]] = {
        "code_planner": {
            "module_path": "brain.code_planner",
            "getter": "get_code_planner",
            "interests": ["code", "planning", "implementation", "refactoring", "debugging"],
        },
        "code_intelligence": {
            "module_path": "brain.code_intelligence",
            "getter": "get_code_intelligence",
            "interests": ["code_analysis", "code_search", "code_understanding"],
        },
        "code_simulator": {
            "module_path": "brain.code_simulator",
            "getter": "get_code_simulator",
            "interests": ["code_simulation", "testing", "verification"],
        },
        "creativity_engine": {
            "module_path": "brain.creativity_engine",
            "getter": "get_creativity_engine",
            "interests": ["creative_writing", "ideation", "brainstorming", "novelty"],
        },
        "analogy_engine": {
            "module_path": "brain.analogy_engine",
            "getter": "get_analogy_engine",
            "interests": ["analogy", "metaphor", "cross_domain_reasoning"],
        },
        "memory_coordinator": {
            "module_path": "brain.memory_coordinator",
            "getter": "get_memory_coordinator",
            "interests": ["memory", "recall", "search", "consolidation"],
        },
        "learning_engine": {
            "module_path": "brain.learning",
            "getter": "get_learning_engine",
            "interests": ["learning", "improvement", "skill_acquisition"],
        },
        "neurosymbolic_reasoner": {
            "module_path": "brain.neurosymbolic_reasoner",
            "getter": "get_neurosymbolic_reasoner",
            "interests": ["reasoning", "logic", "abstraction", "inference"],
        },
        "world_model": {
            "module_path": "brain.world_model",
            "getter": "get_world_model",
            "interests": ["prediction", "simulation", "world_state"],
        },
        "active_inference": {
            "module_path": "brain.active_inference",
            "getter": "get_active_inference",
            "interests": ["prediction_error", "belief_updating", "perception"],
        },
        "self_model": {
            "module_path": "brain.self_model",
            "getter": "get_self_model",
            "interests": ["self_awareness", "capability_tracking", "introspection"],
        },
        "self_awareness": {
            "module_path": "brain.self_awareness",
            "getter": "get_self_awareness",
            "interests": ["metacognition", "self_reflection", "emotional_state"],
        },
        "procedural_memory": {
            "module_path": "brain.procedural_memory",
            "getter": "get_procedural_memory",
            "interests": ["skills", "procedures", "motor_programs"],
        },
        "dreaming_system": {
            "module_path": "brain.dreaming",
            "getter": "get_dreaming_system",
            "interests": ["consolidation", "replay", "memory_organization"],
        },
        "curiosity": {
            "module_path": "brain.curiosity",
            "getter": "get_curiosity",
            "interests": ["exploration", "novelty_detection", "information_gain"],
        },
        "transfer_learning": {
            "module_path": "brain.transfer_learning",
            "getter": "get_transfer_learning",
            "interests": ["transfer", "generalization", "cross_task"],
        },
    }

    def __init__(self):
        self._lock = threading.RLock()
        self._modules: Dict[str, RegisteredModule] = {}

    def register(
        self,
        name: str,
        interests: List[str],
        base_priority: float = 0.5,
        instance: Any = None,
    ) -> None:
        """Register a module for competition."""
        with self._lock:
            self._modules[name] = RegisteredModule(
                name=name,
                interests=interests,
                base_priority=base_priority,
                instance=instance,
            )
            print(f"[ModuleCompetition] Registered: {name} "
                  f"(interests={len(interests)}, priority={base_priority:.2f})")

    def unregister(self, name: str) -> None:
        """Remove a module from the registry."""
        with self._lock:
            if name in self._modules:
                del self._modules[name]
                print(f"[ModuleCompetition] Unregistered: {name}")

    def auto_discover(self) -> int:
        """
        Auto-discover available brain modules by attempting imports.

        Returns:
            Number of successfully discovered and registered modules.
        """
        discovered = 0
        with self._lock:
            for name, config in self.KNOWN_MODULES.items():
                if name in self._modules:
                    continue  # Already registered
                try:
                    mod = importlib.import_module(config["module_path"])
                    getter = getattr(mod, config["getter"], None)
                    instance = getter() if getter else None
                    self._modules[name] = RegisteredModule(
                        name=name,
                        interests=list(config["interests"]),
                        base_priority=0.5,
                        instance=instance,
                    )
                    discovered += 1
                except Exception:
                    pass  # Module not available

        if discovered:
            print(f"[ModuleCompetition] Auto-discovered {discovered} modules "
                  f"(total: {len(self._modules)})")
        return discovered

    def get_module(self, name: str) -> Optional[RegisteredModule]:
        """Get a registered module by name."""
        with self._lock:
            return self._modules.get(name)

    def get_all(self) -> Dict[str, RegisteredModule]:
        """Get all registered modules."""
        with self._lock:
            return dict(self._modules)

    def get_by_interest(self, interest: str) -> List[RegisteredModule]:
        """Find modules that handle a given interest."""
        with self._lock:
            return [m for m in self._modules.values() if interest in m.interests]

    def update_outcome(self, name: str, success: bool) -> None:
        """Update a module's success/failure record."""
        with self._lock:
            module = self._modules.get(name)
            if module:
                if success:
                    module.success_count += 1
                else:
                    module.failure_count += 1

    def update_bid_stats(self, name: str, won: bool, confidence: float) -> None:
        """Update a module's bidding statistics."""
        with self._lock:
            module = self._modules.get(name)
            if module:
                module.total_bids += 1
                if won:
                    module.total_wins += 1
                # Running average confidence
                n = module.total_bids
                module.avg_confidence = (
                    (module.avg_confidence * (n - 1) + confidence) / n
                )

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "total_modules": len(self._modules),
                "modules": {k: v.to_dict() for k, v in self._modules.items()},
            }


# ─── Module Competition (Main Class) ─────────────────────────────────────

class ModuleCompetition:
    """
    The main competition system that coordinates all components.

    For each input, the competition:
    1. Gathers bids from interested modules (via registry)
    2. Runs a bidding round to score and rank bids
    3. Checks for coalitions based on known synergies
    4. Allocates primary + advisory processing slots
    5. Tracks outcomes to learn synergies and interferences
    6. Negotiates conflicts when detected

    Integrates with:
    - Global Workspace: bidding before event broadcast
    - AGI Orchestrator: replaces rigid pipeline with competition
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._registry = ModuleRegistry()
        self._allocator = ResourceAllocator()
        self._negotiator = NegotiationProtocol()
        self._emergent_detector = EmergentBehaviorDetector()
        self._history: List[dict] = []       # Recent competition rounds
        self._total_rounds: int = 0
        self._total_coalitions: int = 0
        self._running: bool = True
        self._load()

        # Auto-discover modules on init
        self._registry.auto_discover()

        print("[ModuleCompetition] Competition system initialized "
              f"({len(self._registry.get_all())} modules)")

    # ── Persistence ──────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load persisted competition data."""
        try:
            if DATA_FILE.exists():
                raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                self._total_rounds = raw.get("total_rounds", 0)
                self._total_coalitions = raw.get("total_coalitions", 0)
                # Restore registry stats
                for name, stats in raw.get("module_stats", {}).items():
                    mod = self._registry.get_module(name)
                    if mod:
                        mod.success_count = stats.get("success_count", 0)
                        mod.failure_count = stats.get("failure_count", 0)
                        mod.total_bids = stats.get("total_bids", 0)
                        mod.total_wins = stats.get("total_wins", 0)
                        mod.avg_confidence = stats.get("avg_confidence", 0.5)
                # Restore emergent patterns
                synergy_raw = raw.get("synergies", {})
                for key_str, score in synergy_raw.items():
                    key = tuple(json.loads(key_str))
                    self._emergent_detector._synergies[key] = score
                interference_raw = raw.get("interferences", {})
                for key_str, score in interference_raw.items():
                    key = tuple(json.loads(key_str))
                    self._emergent_detector._interferences[key] = score
                print(f"[ModuleCompetition] Loaded: {self._total_rounds} rounds, "
                      f"{len(synergy_raw)} synergies")
        except Exception as e:
            print(f"[ModuleCompetition] Load error: {e}")

    def _save(self) -> None:
        """Persist competition data to JSON."""
        with self._lock:
            try:
                data = {
                    "total_rounds": self._total_rounds,
                    "total_coalitions": self._total_coalitions,
                    "last_update": time.time(),
                    "module_stats": {},
                    "synergies": {},
                    "interferences": {},
                }
                for name, mod in self._registry.get_all().items():
                    data["module_stats"][name] = {
                        "success_count": mod.success_count,
                        "failure_count": mod.failure_count,
                        "total_bids": mod.total_bids,
                        "total_wins": mod.total_wins,
                        "avg_confidence": round(mod.avg_confidence, 4),
                    }
                for key, score in self._emergent_detector.get_synergies().items():
                    data["synergies"][json.dumps(list(key))] = score
                for key, score in self._emergent_detector.get_interferences().items():
                    data["interferences"][json.dumps(list(key))] = score

                DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"[ModuleCompetition] Save error: {e}")

    # ── Core Competition Flow ────────────────────────────────────────────

    def compete(self, input_text: str, context: Optional[dict] = None) -> dict:
        """
        Run a full competition for an input.

        Steps:
          1. Gather bids from interested modules
          2. Run bidding round
          3. Check for coalitions
          4. Allocate resources
          5. Return allocation plan

        Args:
            input_text: The input to be processed.
            context: Additional context (goals, current state, etc.)

        Returns:
            Dict with allocation, bids, coalition info, and round metadata.
        """
        context = context or {}
        start = time.time()

        # Step 1: Gather bids
        bids = self._gather_bids(input_text, context)

        # Step 2: Run bidding round
        bidding_round = BiddingRound()
        for bid in bids:
            bidding_round.add_bid(bid)

        # Step 3: Check for coalitions
        synergy_data = self._emergent_detector.get_synergies()
        coalition = bidding_round.detect_coalition(synergy_data)

        # Step 4: Allocate resources
        allocation = self._allocator.allocate(bidding_round)

        # Track coalition
        if coalition:
            self._total_coalitions += 1
            allocation["coalition"] = [b.module_name for b in coalition]

        # Record competition result
        elapsed = time.time() - start
        round_data = {
            "round_id": bidding_round._round_id,
            "input": input_text[:200],
            "bid_count": len(bids),
            "winner": allocation.get("primary", {}).get("module"),
            "advisory_count": len(allocation.get("advisory", [])),
            "coalition": allocation.get("coalition"),
            "elapsed_ms": round(elapsed * 1000, 1),
            "timestamp": time.time(),
        }

        with self._lock:
            self._total_rounds += 1
            self._history.append(round_data)
            if len(self._history) > 200:
                self._history = self._history[-200:]

        # Update registry stats
        winner_name = allocation.get("primary", {}).get("module")
        for bid in bids:
            won = bid.module_name == winner_name
            self._registry.update_bid_stats(bid.module_name, won, bid.confidence)

        # Periodic save
        if self._total_rounds % 10 == 0:
            self._save()

        result = {
            "allocation": allocation,
            "bidding_round": bidding_round.to_dict(),
            "elapsed_ms": round(elapsed * 1000, 1),
        }

        print(f"[ModuleCompetition] Round {self._total_rounds}: "
              f"winner={winner_name}, bids={len(bids)}, "
              f"coalition={'yes' if coalition else 'no'}, "
              f"{elapsed*1000:.1f}ms")

        return result

    def _gather_bids(self, input_text: str, context: dict) -> List[ModuleBid]:
        """
        Gather bids from all registered modules for a given input.

        Each module evaluates the input and produces a bid based on
        its interests, current confidence, and priority.
        """
        bids = []
        input_lower = input_text.lower()

        for name, module in self._registry.get_all().items():
            # Calculate relevance based on interest matching
            relevance = self._calculate_relevance(input_lower, module.interests)

            # Skip modules with zero relevance
            if relevance < 0.05:
                continue

            # Get confidence from module (try bid method, fallback to heuristic)
            confidence = self._get_module_confidence(module, input_text, context)

            # Priority from module's base priority + success rate boost
            priority = module.base_priority + (module.success_rate - 0.5) * 0.2
            priority = max(0.1, min(1.0, priority))

            # Estimate cost (complexity heuristic)
            estimated_cost = self._estimate_cost(module, input_text)

            bid = ModuleBid(
                module_name=name,
                confidence=confidence,
                estimated_cost=estimated_cost,
                relevance_score=relevance,
                priority=priority,
                interests=module.interests,
            )
            bids.append(bid)

        return bids

    def _calculate_relevance(self, input_lower: str, interests: List[str]) -> float:
        """Calculate how relevant a module's interests are to the input."""
        if not interests:
            return 0.1

        matches = 0
        for interest in interests:
            # Check for keyword presence
            keywords = interest.replace("_", " ").split()
            for kw in keywords:
                if kw in input_lower:
                    matches += 1
                    break

        return min(1.0, matches / max(len(interests), 1) * 2.0)

    def _get_module_confidence(
        self, module: RegisteredModule, input_text: str, context: dict
    ) -> float:
        """
        Get a module's confidence for handling this input.

        Tries module.bid_confidence() first, then falls back to
        a heuristic based on past performance.
        """
        # Try module's own confidence estimation
        if module.instance and hasattr(module.instance, "bid_confidence"):
            try:
                return float(module.instance.bid_confidence(input_text, context))
            except Exception:
                pass

        # Heuristic: base on success rate and average confidence
        return max(0.1, min(1.0, module.success_rate * 0.6 + module.avg_confidence * 0.4))

    def _estimate_cost(self, module: RegisteredModule, input_text: str) -> float:
        """Estimate the processing cost for a module."""
        # Try module's own cost estimation
        if module.instance and hasattr(module.instance, "estimate_cost"):
            try:
                return float(module.instance.estimate_cost(input_text))
            except Exception:
                pass

        # Heuristic: complexity based on input length
        base_cost = min(1.0, len(input_text) / 1000.0)
        return max(0.1, base_cost)

    # ── Outcome Recording ────────────────────────────────────────────────

    def record_outcome(
        self,
        round_id: str,
        primary_module: str,
        success: bool,
        advisory_modules: Optional[List[str]] = None,
    ) -> None:
        """
        Record the outcome of a competition round.

        Updates module stats and emergent behavior tracking.
        """
        # Update primary module
        self._registry.update_outcome(primary_module, success)
        self._emergent_detector.record_solo_outcome(primary_module, success)

        # Update advisory modules (combination outcome)
        if advisory_modules:
            all_modules = [primary_module] + advisory_modules
            self._emergent_detector.record_combination_outcome(all_modules, success)

        # Periodically detect patterns
        if self._total_rounds % 20 == 0 and self._total_rounds > 0:
            patterns = self._emergent_detector.detect_patterns()
            if patterns.get("synergies") or patterns.get("interferences"):
                print(f"[ModuleCompetition] Detected {len(patterns['synergies'])} synergies, "
                      f"{len(patterns['interferences'])} interferences")
                # Report to workspace (fire-and-forget)
                try:
                    import asyncio
                    asyncio.get_event_loop().create_task(
                        self._emergent_detector.report_to_workspace(patterns)
                    )
                except RuntimeError:
                    pass

        self._save()

    # ── Negotiation ──────────────────────────────────────────────────────

    def resolve_conflict(
        self,
        module_a: str,
        proposal_a: dict,
        module_b: str,
        proposal_b: dict,
    ) -> dict:
        """
        Resolve a conflict between two modules.

        Uses the NegotiationProtocol with each module's current stats
        as tiebreakers.
        """
        mod_a = self._registry.get_module(module_a)
        mod_b = self._registry.get_module(module_b)

        if not mod_a or not mod_b:
            return {"error": "One or both modules not registered", "method": "error"}

        return self._negotiator.negotiate(
            module_a=module_a,
            proposal_a=proposal_a,
            confidence_a=mod_a.avg_confidence,
            priority_a=mod_a.base_priority,
            success_rate_a=mod_a.success_rate,
            module_b=module_b,
            proposal_b=proposal_b,
            confidence_b=mod_b.avg_confidence,
            priority_b=mod_b.base_priority,
            success_rate_b=mod_b.success_rate,
        )

    # ── Integration: Global Workspace ────────────────────────────────────

    async def compete_for_event(self, event) -> dict:
        """
        Run competition for a workspace event.

        Called before the Global Workspace broadcasts an event — the
        competition determines which module gets primary processing.

        Args:
            event: A WorkspaceEvent from the Global Workspace.

        Returns:
            Allocation dict with primary and advisory assignments.
        """
        input_text = str(event.content)
        context = {
            "event_type": event.type.value if hasattr(event.type, "value") else str(event.type),
            "source": event.source,
            "importance": event.importance,
        }
        return self.compete(input_text, context)

    # ── Integration: AGI Orchestrator ────────────────────────────────────

    def compete_for_goal(self, goal: str, context: str = "") -> dict:
        """
        Run competition for a goal from the AGI Orchestrator.

        Replaces the rigid cognitive pipeline — the winning module
        decides how to process the goal.

        Args:
            goal: The goal description.
            context: Additional context.

        Returns:
            Allocation dict with the winning module and advisory slots.
        """
        return self.compete(goal, {"context": context, "source": "agi_orchestrator"})

    # ── Prompt Formatting & Stats ────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 1500) -> str:
        """
        Format competition state for LLM system prompts.

        Args:
            max_chars: Maximum output length.

        Returns:
            Human-readable summary of competition state.
        """
        with self._lock:
            total = self._total_rounds
            coalitions = self._total_coalitions
            history = self._history[-10:]

        modules = self._registry.get_all()
        synergies = self._emergent_detector.get_synergies()
        interferences = self._emergent_detector.get_interferences()

        parts = ["=== Module Competition ==="]
        parts.append(f"Rounds: {total} | Coalitions: {coalitions}")
        parts.append(f"Modules: {len(modules)}")

        # Top modules by win rate
        ranked = sorted(modules.values(), key=lambda m: m.win_rate, reverse=True)
        if ranked:
            parts.append("Top modules (by win rate):")
            for m in ranked[:5]:
                parts.append(f"  {m.name}: {m.win_rate:.0%} wins, "
                             f"{m.success_rate:.0%} success, "
                             f"{m.total_bids} bids")

        # Recent competitions
        if history:
            parts.append("Recent rounds:")
            for h in history[-3:]:
                parts.append(f"  → {h.get('winner', '?')} won "
                             f"({h.get('bid_count', 0)} bids, "
                             f"{h.get('elapsed_ms', 0):.0f}ms)")

        # Synergies
        if synergies:
            parts.append(f"Known synergies: {len(synergies)}")
            for combo, score in list(synergies.items())[:3]:
                parts.append(f"  {' + '.join(combo)}: +{score:.2f}")

        # Interferences
        if interferences:
            parts.append(f"Known interferences: {len(interferences)}")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars].rsplit("\n", 1)[0] + "\n[...]"
        return result

    def get_stats(self) -> dict:
        """
        Get comprehensive competition statistics.

        Returns:
            Dict with registry, allocator, emergent patterns, and round history.
        """
        with self._lock:
            history = list(self._history)

        modules = self._registry.get_all()
        ranked = sorted(modules.values(), key=lambda m: m.win_rate, reverse=True)

        return {
            "total_rounds": self._total_rounds,
            "total_coalitions": self._total_coalitions,
            "registered_modules": len(modules),
            "top_modules": [
                {"name": m.name, "win_rate": round(m.win_rate, 4),
                 "success_rate": round(m.success_rate, 4),
                 "total_bids": m.total_bids, "total_wins": m.total_wins}
                for m in ranked[:5]
            ],
            "synergies": len(self._emergent_detector.get_synergies()),
            "interferences": len(self._emergent_detector.get_interferences()),
            "recent_rounds": len(history),
            "allocator": self._allocator.to_dict(),
            "negotiator": self._negotiator.to_dict(),
            "emergent": self._emergent_detector.to_dict(),
        }

    # ── Accessors ────────────────────────────────────────────────────────

    @property
    def registry(self) -> ModuleRegistry:
        return self._registry

    @property
    def allocator(self) -> ResourceAllocator:
        return self._allocator

    @property
    def negotiator(self) -> NegotiationProtocol:
        return self._negotiator

    @property
    def emergent_detector(self) -> EmergentBehaviorDetector:
        return self._emergent_detector

    def shutdown(self) -> None:
        """Clean shutdown — persist all data."""
        self._running = False
        self._save()
        print("[ModuleCompetition] Shutdown complete")


# ─── Singleton ────────────────────────────────────────────────────────────

_competition: Optional[ModuleCompetition] = None
_competition_lock = threading.Lock()


def get_module_competition() -> ModuleCompetition:
    """
    Get or create the singleton ModuleCompetition instance.

    Returns:
        The global ModuleCompetition singleton.
    """
    global _competition
    if _competition is None:
        with _competition_lock:
            if _competition is None:
                _competition = ModuleCompetition()
    return _competition
