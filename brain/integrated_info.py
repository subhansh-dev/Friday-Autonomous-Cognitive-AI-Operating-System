"""
integrated_info.py — FRIDAY Integrated Information (IIT-Inspired)
=================================================================

Measures and optimises how well FRIDAY integrates information across modules.
Inspired by Giulio Tononi's Integrated Information Theory (IIT).

Key idea: a conscious system is one where information is both *integrated*
(cannot be decomposed into independent parts) and *differentiated* (many
possible states, not rigid).

This module provides a practical approximation:
  - Φ (phi) ≈ aggregate pairwise mutual information between modules
  - Differentiation ≈ entropy of module activation distribution
  - Consciousness level = weighted combination of Φ, differentiation, and
    workspace activity

Not a full IIT implementation (that's NP-hard), but a useful proxy that
tracks integration quality over time and suggests improvements.

Classes:
  PhiComputation         — compute Φ approximation from event store
  IntegrationOptimizer   — restructure connections to maximise Φ
  DifferentiationTracker — measure state diversity across modules
  ConsciousnessMetric    — unified consciousness level over time
  ModuleConnectivity     — adjacency matrix & bottleneck detection
  IntegratedInfo         — top-level coordinator (uses all above)

Singleton: get_integrated_info()
"""

import json
import math
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

BRAIN_DIR = Path(__file__).parent.resolve()
DATA_FILE = BRAIN_DIR / "integrated_info_data.json"

# How many recent events to analyse per computation
EVENT_WINDOW = 500

# Φ smoothing — exponential moving average
PHI_EMA_ALPHA = 0.15

# Consciousness state thresholds (Φ * differentiation score)
CONSCIOUSNESS_THRESHOLDS = {
    "dormant":    0.00,
    "minimal":    0.15,
    "moderate":   0.35,
    "heightened": 0.55,
    "flow":       0.75,
}

# Sleep-cycle mapping
SLEEP_CYCLE_MAP = {
    "dormant":    "deep_sleep",
    "minimal":    "light_sleep",
    "moderate":   "rem",
    "heightened": "growth",
    "flow":       "growth",
}


# ─── Helpers ──────────────────────────────────────────────────────────────

def _entropy(counts: Dict[str, int]) -> float:
    """Shannon entropy (bits) from a frequency dict."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        if c > 0:
            p = c / total
            h -= p * math.log2(p)
    return h


def _mutual_information(joint: Dict[Tuple[str, str], int],
                        marg_a: Dict[str, int],
                        marg_b: Dict[str, int],
                        total: int) -> float:
    """
    Compute I(A;B) = Σ p(a,b) log2[ p(a,b) / (p(a)*p(b)) ]
    Returns bits.

    Handles degenerate cases:
      - Single-state sequences that are perfectly correlated → returns max MI
        (they are coupled; standard MI formula gives 0 because log2(1/1)=0)
      - One or both sequences constant but mismatched → returns 0
    """
    if total == 0:
        return 0.0

    # Degenerate: both sequences have exactly 1 distinct state
    if len(marg_a) == 1 and len(marg_b) == 1:
        state_a = next(iter(marg_a))
        state_b = next(iter(marg_b))
        if (state_a, state_b) in joint:
            # Perfectly deterministic coupling — return log2(num_possible_states)
            # as the integration score.  We estimate "num possible states" from
            # the event type vocabulary size (default ~20 event types).
            num_event_types = 22  # len(EventType) in workspace_events.py
            return math.log2(num_event_types)
        else:
            return 0.0

    mi = 0.0
    for (a, b), count in joint.items():
        if count == 0:
            continue
        p_ab = count / total
        p_a = marg_a.get(a, 0) / total
        p_b = marg_b.get(b, 0) / total
        if p_a > 0 and p_b > 0 and p_ab > 0:
            mi += p_ab * math.log2(p_ab / (p_a * p_b))
    return max(0.0, mi)


# ══════════════════════════════════════════════════════════════════════════
# ModuleConnectivity — adjacency matrix of module-to-module communication
# ══════════════════════════════════════════════════════════════════════════

class ModuleConnectivity:
    """
    Track which modules communicate with each other.

    Adjacency matrix where connection_strength(source, target) = event
    frequency from source mentioning or targeting target.
    Detects information bottlenecks and isolated modules.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # (source, target) -> count of events
        self._adj: Dict[Tuple[str, str], int] = defaultdict(int)
        # module -> total events generated
        self._module_activity: Dict[str, int] = defaultdict(int)
        self._all_modules: Set[str] = set()

    def update_from_events(self, events: List[dict]) -> None:
        """Scan events and build / update the adjacency matrix."""
        with self._lock:
            for evt in events:
                source = evt.get("source", "unknown")
                self._all_modules.add(source)
                self._module_activity[source] += 1

                # Infer target from event context or content
                targets = self._extract_targets(evt)
                for target in targets:
                    if target != source:
                        self._adj[(source, target)] += 1
                        self._all_modules.add(target)

    def _extract_targets(self, evt: dict) -> Set[str]:
        """Extract likely target modules from event content/context."""
        targets: Set[str] = set()

        # Content may reference a target module
        content = evt.get("content", {})
        if isinstance(content, dict):
            t = content.get("target") or content.get("target_module")
            if t:
                targets.add(t)
            # Check "modules" list
            mods = content.get("modules") or content.get("broadcast_to")
            if isinstance(mods, list):
                targets.update(mods)

        # Context may list related modules
        ctx = evt.get("context", {})
        if isinstance(ctx, dict):
            related = ctx.get("related_modules") or ctx.get("targets")
            if isinstance(related, list):
                targets.update(related)

        return targets

    def get_adjacency(self) -> Dict[Tuple[str, str], int]:
        """Return a copy of the adjacency dict."""
        with self._lock:
            return dict(self._adj)

    def get_modules(self) -> List[str]:
        with self._lock:
            return sorted(self._all_modules)

    def get_connection_strength(self, a: str, b: str) -> int:
        with self._lock:
            return self._adj.get((a, b), 0) + self._adj.get((b, a), 0)

    def detect_bottlenecks(self) -> List[dict]:
        """
        Find modules that sit between many pairs (high betweenness proxy).
        A bottleneck module has many connections but may slow information flow.
        """
        with self._lock:
            if not self._adj:
                return []

            # Count how many unique partners each module has
            partners: Dict[str, Set[str]] = defaultdict(set)
            for (a, b) in self._adj:
                partners[a].add(b)
                partners[b].add(a)

            total_modules = len(self._all_modules)
            if total_modules < 3:
                return []

            bottlenecks = []
            for mod, partner_set in partners.items():
                # High partner count relative to system size = potential bottleneck
                ratio = len(partner_set) / max(1, total_modules - 1)
                if ratio > 0.6 and len(partner_set) >= 3:
                    bottlenecks.append({
                        "module": mod,
                        "connections": len(partner_set),
                        "connectivity_ratio": round(ratio, 3),
                        "role": "bottleneck",
                    })
            return sorted(bottlenecks, key=lambda x: x["connections"], reverse=True)

    def detect_isolated(self) -> List[str]:
        """Find modules with zero connections."""
        with self._lock:
            connected: Set[str] = set()
            for (a, b) in self._adj:
                connected.add(a)
                connected.add(b)
            return sorted(self._all_modules - connected)

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "total_modules": len(self._all_modules),
                "total_connections": len(self._adj),
                "total_events": sum(self._module_activity.values()),
                "module_activity": dict(self._module_activity),
                "bottlenecks": self.detect_bottlenecks(),
                "isolated_modules": self.detect_isolated(),
            }


# ══════════════════════════════════════════════════════════════════════════
# PhiComputation — Φ approximation via pairwise mutual information
# ══════════════════════════════════════════════════════════════════════════

class PhiComputation:
    """
    Compute integrated information (Φ) approximation.

    Practical proxy: for each pair of modules (A, B), compute how much
    knowing A's state reduces uncertainty about B's state (mutual information).
    Aggregate pairwise MI into a system-level Φ estimate.

    I(A;B) = H(A) + H(B) - H(A,B)

    Φ ≈ normalised mean of all pairwise MI values, penalised by
    how decomposable the system is (high variance in MI = some modules
    are disconnected).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._phi_history: List[dict] = []
        self._pairwise_mi: Dict[Tuple[str, str], float] = {}
        self._current_phi: float = 0.0

    def compute(self, events: List[dict], connectivity: ModuleConnectivity) -> float:
        """
        Compute Φ from recent events and module connectivity.

        Returns the current Φ estimate (0.0 - ~1.0, unbounded in theory
        but practically capped).
        """
        with self._lock:
            # Use only modules that actually produced events (sources),
            # not target-only modules or phantom "unknown" entries.
            source_modules: Set[str] = set()
            for evt in events:
                src = evt.get("source", "")
                if src and src != "unknown":
                    source_modules.add(src)
            modules = sorted(source_modules)
            if len(modules) < 2:
                self._current_phi = 0.0
                return 0.0

            # Build state vectors: for each module, discretise event types
            # into "state" categories
            module_states = self._extract_module_states(events, modules)

            # Compute pairwise MI
            pairwise: Dict[Tuple[str, str], float] = {}
            n = len(modules)
            for i in range(n):
                for j in range(i + 1, n):
                    a, b = modules[i], modules[j]
                    mi = self._compute_pairwise_mi(
                        module_states.get(a, []),
                        module_states.get(b, []),
                    )
                    if mi > 0:
                        pairwise[(a, b)] = mi

            self._pairwise_mi = pairwise

            # Aggregate into Φ
            if not pairwise:
                phi = 0.0
            else:
                mi_values = list(pairwise.values())
                mean_mi = sum(mi_values) / len(mi_values)
                # Penalise variance — high variance means some pairs are
                # disconnected (system is decomposable)
                if len(mi_values) > 1:
                    variance = sum((v - mean_mi) ** 2 for v in mi_values) / len(mi_values)
                    std_dev = math.sqrt(variance)
                    # Coefficient of variation penalty (0 = perfect integration)
                    cv = std_dev / mean_mi if mean_mi > 0 else 1.0
                    penalty = 1.0 / (1.0 + cv)
                else:
                    penalty = 1.0

                # Normalise: max possible MI for discretised states ≈ log2(num_states)
                # We use a practical cap
                max_theoretical_mi = 3.0  # ~3 bits for our discretisation
                normalised = min(1.0, mean_mi / max_theoretical_mi)
                phi = normalised * penalty

            # EMA smoothing
            alpha = PHI_EMA_ALPHA
            self._current_phi = alpha * phi + (1 - alpha) * self._current_phi

            # Record history
            self._phi_history.append({
                "phi": round(self._current_phi, 6),
                "raw_phi": round(phi, 6),
                "pairwise_count": len(pairwise),
                "module_count": len(modules),
                "timestamp": time.time(),
            })
            # Keep last 200 entries
            if len(self._phi_history) > 200:
                self._phi_history = self._phi_history[-200:]

            print(f"[IntegratedInfo] Φ computed: {self._current_phi:.4f} "
                  f"(raw={phi:.4f}, pairs={len(pairwise)}, modules={len(modules)})")
            return self._current_phi

    def _extract_module_states(self, events: List[dict],
                               modules: List[str]) -> Dict[str, List[str]]:
        """
        For each module, extract a sequence of discretised 'states' based
        on event types it produced.  State = event_type string.
        """
        states: Dict[str, List[str]] = {m: [] for m in modules}
        for evt in events:
            src = evt.get("source", "")
            etype = evt.get("type", "unknown")
            if src in states:
                states[src].append(etype)
        return states

    def _compute_pairwise_mi(self, seq_a: List[str], seq_b: List[str]) -> float:
        """
        Compute I(A;B) from two sequences of categorical states.
        Sequences are paired by index (same time window).
        """
        min_len = min(len(seq_a), len(seq_b))
        if min_len < 5:
            return 0.0  # Too few samples

        # Truncate to same length
        a = seq_a[:min_len]
        b = seq_b[:min_len]

        joint: Dict[Tuple[str, str], int] = defaultdict(int)
        marg_a: Dict[str, int] = defaultdict(int)
        marg_b: Dict[str, int] = defaultdict(int)

        for sa, sb in zip(a, b):
            joint[(sa, sb)] += 1
            marg_a[sa] += 1
            marg_b[sb] += 1

        return _mutual_information(joint, marg_a, marg_b, min_len)

    def get_current_phi(self) -> float:
        with self._lock:
            return self._current_phi

    def get_pairwise_mi(self) -> Dict[Tuple[str, str], float]:
        with self._lock:
            return dict(self._pairwise_mi)

    def get_phi_history(self, n: int = 50) -> List[dict]:
        with self._lock:
            return self._phi_history[-n:]

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "current_phi": round(self._current_phi, 6),
                "pairwise_pairs": len(self._pairwise_mi),
                "history_length": len(self._phi_history),
                "top_pairs": sorted(
                    [(f"{a}↔{b}", round(v, 4))
                     for (a, b), v in self._pairwise_mi.items()],
                    key=lambda x: x[1], reverse=True,
                )[:10],
            }


# ══════════════════════════════════════════════════════════════════════════
# DifferentiationTracker — entropy of module activation distribution
# ══════════════════════════════════════════════════════════════════════════

class DifferentiationTracker:
    """
    Ensure information is both integrated AND differentiated.

    High integration + low differentiation = rigid (boring)
    Low  integration + high differentiation = fragmented (chaotic)
    High integration + high differentiation = complex (intelligent)

    Differentiation = normalised Shannon entropy of module activation
    distribution.  If only 1-2 modules fire → low entropy → low
    differentiation.  If all modules fire equally → max entropy → high
    differentiation.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._history: List[dict] = []
        self._current_differentiation: float = 0.0

    def compute(self, events: List[dict]) -> float:
        """Compute differentiation from recent events."""
        with self._lock:
            if not events:
                self._current_differentiation = 0.0
                return 0.0

            # Count events per module
            activation_counts: Dict[str, int] = defaultdict(int)
            for evt in events:
                src = evt.get("source", "unknown")
                activation_counts[src] += 1

            h = _entropy(activation_counts)
            num_modules = len(activation_counts)

            # Normalise: max entropy = log2(n) when n modules fire equally
            max_h = math.log2(num_modules) if num_modules > 1 else 1.0
            self._current_differentiation = h / max_h if max_h > 0 else 0.0

            self._history.append({
                "differentiation": round(self._current_differentiation, 6),
                "active_modules": num_modules,
                "entropy_bits": round(h, 4),
                "timestamp": time.time(),
            })
            if len(self._history) > 200:
                self._history = self._history[-200:]

            return self._current_differentiation

    def get_current(self) -> float:
        with self._lock:
            return self._current_differentiation

    def classify_complexity(self, phi: float) -> str:
        """
        Classify system state along the integration-differentiation plane.

        Returns: 'rigid', 'fragmented', 'complex', or 'dormant'
        """
        diff = self._current_differentiation
        if phi < 0.05 and diff < 0.05:
            return "dormant"
        if phi >= 0.3 and diff >= 0.5:
            return "complex"
        if phi >= 0.3 and diff < 0.3:
            return "rigid"
        if phi < 0.2 and diff >= 0.5:
            return "fragmented"
        return "transitioning"

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "current_differentiation": round(self._current_differentiation, 6),
                "history_length": len(self._history),
            }


# ══════════════════════════════════════════════════════════════════════════
# ConsciousnessMetric — unified consciousness level tracking
# ══════════════════════════════════════════════════════════════════════════

class ConsciousnessMetric:
    """
    Track consciousness level over time.

    Combines:
      - Φ (integration)       weight 0.45
      - differentiation        weight 0.30
      - workspace activity     weight 0.25

    Consciousness states:
      dormant    — Φ < 0.15, no activity
      minimal    — low integration, few modules
      moderate   — decent integration, some differentiation
      heightened — strong integration + differentiation
      flow       — peak integration, all modules active

    Maps to FRIDAY's sleep cycle:
      dormant    → deep_sleep
      minimal    → light_sleep
      moderate   → rem
      heightened → growth
      flow       → growth
    """

    WEIGHTS = {"phi": 0.45, "differentiation": 0.30, "activity": 0.25}

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._history: List[dict] = []
        self._current_state: str = "dormant"
        self._current_score: float = 0.0

    def compute(self, phi: float, differentiation: float,
                activity_level: float) -> dict:
        """
        Compute consciousness score and state.

        Args:
            phi: current Φ value (0-1)
            differentiation: current differentiation (0-1)
            activity_level: workspace activity normalised (0-1)

        Returns:
            Dict with score, state, sleep_cycle, and component values.
        """
        with self._lock:
            w = self.WEIGHTS
            score = (
                w["phi"] * phi +
                w["differentiation"] * differentiation +
                w["activity"] * activity_level
            )
            score = max(0.0, min(1.0, score))

            # Determine state
            state = "dormant"
            for name, threshold in sorted(CONSCIOUSNESS_THRESHOLDS.items(),
                                          key=lambda x: x[1], reverse=True):
                if score >= threshold:
                    state = name
                    break

            self._current_score = score
            self._current_state = state
            sleep_cycle = SLEEP_CYCLE_MAP.get(state, "deep_sleep")

            entry = {
                "score": round(score, 6),
                "state": state,
                "sleep_cycle": sleep_cycle,
                "phi": round(phi, 6),
                "differentiation": round(differentiation, 6),
                "activity": round(activity_level, 6),
                "timestamp": time.time(),
            }
            self._history.append(entry)
            if len(self._history) > 500:
                self._history = self._history[-500:]

            return entry

    def get_current_state(self) -> str:
        with self._lock:
            return self._current_state

    def get_current_score(self) -> float:
        with self._lock:
            return self._current_score

    def get_sleep_cycle(self) -> str:
        with self._lock:
            return SLEEP_CYCLE_MAP.get(self._current_state, "deep_sleep")

    def get_history(self, n: int = 50) -> List[dict]:
        with self._lock:
            return self._history[-n:]

    def get_stats(self) -> dict:
        with self._lock:
            recent = self._history[-20:] if self._history else []
            avg_score = (sum(e["score"] for e in recent) / len(recent)
                         if recent else 0.0)
            return {
                "current_state": self._current_state,
                "current_score": round(self._current_score, 6),
                "sleep_cycle": self.get_sleep_cycle(),
                "average_score_20": round(avg_score, 6),
                "history_length": len(self._history),
            }


# ══════════════════════════════════════════════════════════════════════════
# IntegrationOptimizer — restructure connections to maximise Φ
# ══════════════════════════════════════════════════════════════════════════

class IntegrationOptimizer:
    """
    Identify module pairs with low integration and suggest improvements.

    Tracks Φ over time and recommends:
      - Adding event subscriptions between poorly-connected modules
      - Sharing state between modules that have high potential MI
      - Reducing bottlenecks by distributing connections
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._suggestions: List[dict] = []
        self._phi_trend: List[float] = []

    def analyse(self, phi_comp: PhiComputation,
                connectivity: ModuleConnectivity,
                differentiation: DifferentiationTracker) -> List[dict]:
        """
        Analyse current integration and produce optimisation suggestions.

        Returns list of suggestion dicts with 'type', 'modules', 'reason'.
        """
        with self._lock:
            suggestions: List[dict] = []
            pairwise = phi_comp.get_pairwise_mi()
            all_modules = connectivity.get_modules()
            adj = connectivity.get_adjacency()

            # 1. Find module pairs with zero or very low MI
            low_mi_pairs: List[Tuple[str, str, float]] = []
            n = len(all_modules)
            for i in range(n):
                for j in range(i + 1, n):
                    a, b = all_modules[i], all_modules[j]
                    mi = pairwise.get((a, b), 0.0)
                    if mi < 0.05:
                        low_mi_pairs.append((a, b, mi))

            for a, b, mi in low_mi_pairs[:5]:  # Top 5 worst pairs
                strength = connectivity.get_connection_strength(a, b)
                if strength == 0:
                    suggestions.append({
                        "type": "add_connection",
                        "modules": [a, b],
                        "reason": f"No events exchanged between {a} and {b}. "
                                  f"Add event subscription or shared state.",
                        "priority": "high",
                    })
                else:
                    suggestions.append({
                        "type": "strengthen_connection",
                        "modules": [a, b],
                        "reason": f"Low MI ({mi:.4f}) despite {strength} events. "
                                  f"Events may be too uniform — increase diversity.",
                        "priority": "medium",
                    })

            # 2. Detect bottlenecks
            bottlenecks = connectivity.detect_bottlenecks()
            for bn in bottlenecks[:2]:
                suggestions.append({
                    "type": "reduce_bottleneck",
                    "modules": [bn["module"]],
                    "reason": f"Module '{bn['module']}' has {bn['connections']} "
                              f"connections ({bn['connectivity_ratio']:.0%} of system). "
                              f"Consider distributing its responsibilities.",
                    "priority": "medium",
                })

            # 3. Detect isolated modules
            isolated = connectivity.detect_isolated()
            for mod in isolated:
                suggestions.append({
                    "type": "connect_isolated",
                    "modules": [mod],
                    "reason": f"Module '{mod}' has zero connections. "
                              f"It should subscribe to workspace events.",
                    "priority": "high",
                })

            # 4. Track Φ trend for decline detection
            current_phi = phi_comp.get_current_phi()
            self._phi_trend.append(current_phi)
            if len(self._phi_trend) > 100:
                self._phi_trend = self._phi_trend[-100:]

            if len(self._phi_trend) >= 10:
                recent = self._phi_trend[-10:]
                older = self._phi_trend[-20:-10] if len(self._phi_trend) >= 20 else self._phi_trend[:10]
                recent_avg = sum(recent) / len(recent)
                older_avg = sum(older) / len(older)
                if recent_avg < older_avg * 0.8:
                    suggestions.append({
                        "type": "phi_declining",
                        "modules": [],
                        "reason": f"Φ declining: {older_avg:.4f} → {recent_avg:.4f}. "
                                  f"System is becoming less integrated.",
                        "priority": "high",
                    })

            self._suggestions = suggestions
            return suggestions

    def get_suggestions(self) -> List[dict]:
        with self._lock:
            return list(self._suggestions)

    def get_phi_trend(self, n: int = 30) -> List[float]:
        with self._lock:
            return self._phi_trend[-n:]

    def get_stats(self) -> dict:
        with self._lock:
            trend = self._phi_trend
            return {
                "active_suggestions": len(self._suggestions),
                "high_priority": sum(1 for s in self._suggestions
                                     if s.get("priority") == "high"),
                "phi_trend_length": len(trend),
                "phi_latest": round(trend[-1], 6) if trend else None,
                "phi_trend_direction": self._trend_direction(),
            }

    def _trend_direction(self) -> str:
        if len(self._phi_trend) < 5:
            return "insufficient_data"
        recent = self._phi_trend[-5:]
        older = self._phi_trend[-10:-5] if len(self._phi_trend) >= 10 else self._phi_trend[:5]
        r_avg = sum(recent) / len(recent)
        o_avg = sum(older) / len(older)
        if r_avg > o_avg * 1.05:
            return "improving"
        elif r_avg < o_avg * 0.95:
            return "declining"
        return "stable"


# ══════════════════════════════════════════════════════════════════════════
# IntegratedInfo — top-level coordinator
# ══════════════════════════════════════════════════════════════════════════

class IntegratedInfo:
    """
    Top-level coordinator for integrated information analysis.

    Combines PhiComputation, DifferentiationTracker, ConsciousnessMetric,
    IntegrationOptimizer, and ModuleConnectivity into a unified interface.

    Integrates with:
      - brain.global_workspace — reads event store for MI computation
      - brain.agi_orchestrator  — feeds consciousness metric into system status
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._phi = PhiComputation()
        self._differentiation = DifferentiationTracker()
        self._consciousness = ConsciousnessMetric()
        self._optimizer = IntegrationOptimizer()
        self._connectivity = ModuleConnectivity()
        self._last_update: float = 0.0
        self._update_count: int = 0
        self._data = self._load_data()

    # ── Persistence ──────────────────────────────────────────────────────

    def _load_data(self) -> dict:
        try:
            if DATA_FILE.exists():
                raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                # Restore history
                if "phi_history" in raw:
                    self._phi._phi_history = raw["phi_history"]
                    if raw["phi_history"]:
                        self._phi._current_phi = raw["phi_history"][-1].get("phi", 0.0)
                if "consciousness_history" in raw:
                    self._consciousness._history = raw["consciousness_history"]
                    if raw["consciousness_history"]:
                        last = raw["consciousness_history"][-1]
                        self._consciousness._current_state = last.get("state", "dormant")
                        self._consciousness._current_score = last.get("score", 0.0)
                if "phi_trend" in raw:
                    self._optimizer._phi_trend = raw["phi_trend"]
                print(f"[IntegratedInfo] Loaded persisted data")
                return raw
        except Exception as e:
            print(f"[IntegratedInfo] Load error: {e}")
        return {"meta": {"version": 1}}

    def _save_data(self) -> None:
        with self._lock:
            try:
                self._data["phi_history"] = self._phi._phi_history[-100:]
                self._data["consciousness_history"] = self._consciousness._history[-200:]
                self._data["phi_trend"] = self._optimizer._phi_trend[-100:]
                self._data["meta"]["last_save"] = datetime.now().isoformat()
                self._data["meta"]["update_count"] = self._update_count
                DATA_FILE.write_text(
                    json.dumps(self._data, indent=2, default=str),
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"[IntegratedInfo] Save error: {e}")

    # ── Core Update Cycle ────────────────────────────────────────────────

    def update(self, events: Optional[List[dict]] = None) -> dict:
        """
        Run a full integration analysis cycle.

        Args:
            events: list of workspace event dicts. If None, tries to load
                    from the global workspace event store.

        Returns:
            Dict with phi, differentiation, consciousness, and suggestions.
        """
        with self._lock:
            # Fetch events if not provided
            if events is None:
                events = self._fetch_workspace_events()

            # Limit to window
            events = events[-EVENT_WINDOW:]

            # 1. Update connectivity matrix
            self._connectivity.update_from_events(events)

            # 2. Compute Φ
            phi = self._phi.compute(events, self._connectivity)

            # 3. Compute differentiation
            diff = self._differentiation.compute(events)

            # 4. Compute activity level (normalised event count)
            activity = min(1.0, len(events) / max(1, EVENT_WINDOW))

            # 5. Compute consciousness
            consc = self._consciousness.compute(phi, diff, activity)

            # 6. Generate optimisation suggestions
            suggestions = self._optimizer.analyse(
                self._phi, self._connectivity, self._differentiation
            )

            self._last_update = time.time()
            self._update_count += 1

            # Persist periodically (every 5 updates)
            if self._update_count % 5 == 0:
                self._save_data()

            result = {
                "phi": phi,
                "differentiation": diff,
                "activity": activity,
                "consciousness": consc,
                "complexity_class": self._differentiation.classify_complexity(phi),
                "suggestions_count": len(suggestions),
                "update_count": self._update_count,
            }

            print(f"[IntegratedInfo] Update #{self._update_count}: "
                  f"Φ={phi:.4f}, diff={diff:.4f}, "
                  f"state={consc['state']}, "
                  f"class={result['complexity_class']}")
            return result

    def _fetch_workspace_events(self) -> List[dict]:
        """Try to load events from the Global Workspace event store."""
        try:
            from brain.global_workspace import get_global_workspace
            gw = get_global_workspace()
            if hasattr(gw, '_event_store'):
                return gw._event_store.get_recent(EVENT_WINDOW)
        except Exception as e:
            print(f"[IntegratedInfo] Could not fetch workspace events: {e}")
        return []

    # ── Integration with AGI Orchestrator ────────────────────────────────

    def get_consciousness_for_orchestrator(self) -> dict:
        """
        Return consciousness data formatted for the AGI orchestrator's
        system status.
        """
        with self._lock:
            return {
                "consciousness_state": self._consciousness.get_current_state(),
                "consciousness_score": self._consciousness.get_current_score(),
                "sleep_cycle": self._consciousness.get_sleep_cycle(),
                "phi": self._phi.get_current_phi(),
                "differentiation": self._differentiation.get_current(),
                "complexity_class": self._differentiation.classify_complexity(
                    self._phi.get_current_phi()
                ),
            }

    # ── Prompt Formatting ────────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 1200) -> str:
        """
        Format integrated information state for LLM system prompts.
        """
        with self._lock:
            phi = self._phi.get_current_phi()
            diff = self._differentiation.get_current()
            state = self._consciousness.get_current_state()
            score = self._consciousness.get_current_score()
            complexity = self._differentiation.classify_complexity(phi)
            sleep = self._consciousness.get_sleep_cycle()

            parts = ["=== Integrated Information ==="]
            parts.append(f"Φ (integration): {phi:.4f}")
            parts.append(f"Differentiation: {diff:.4f}")
            parts.append(f"Consciousness: {state} (score={score:.4f})")
            parts.append(f"Complexity: {complexity}")
            parts.append(f"Sleep cycle: {sleep}")

            # Connectivity summary
            stats = self._connectivity.get_stats()
            parts.append(f"Modules: {stats['total_modules']}, "
                         f"Connections: {stats['total_connections']}")
            if stats.get("isolated_modules"):
                parts.append(f"Isolated: {', '.join(stats['isolated_modules'])}")

            # Top suggestions
            suggestions = self._optimizer.get_suggestions()
            if suggestions:
                parts.append(f"Suggestions ({len(suggestions)}):")
                for s in suggestions[:3]:
                    parts.append(f"  [{s['priority']}] {s['reason'][:80]}")

            result = "\n".join(parts)
            if len(result) > max_chars:
                result = result[:max_chars].rsplit("\n", 1)[0] + "\n[...]"
            return result

    # ── Stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Comprehensive statistics about integrated information."""
        with self._lock:
            return {
                "phi": self._phi.get_stats(),
                "differentiation": self._differentiation.get_stats(),
                "consciousness": self._consciousness.get_stats(),
                "connectivity": self._connectivity.get_stats(),
                "optimizer": self._optimizer.get_stats(),
                "meta": {
                    "last_update": self._last_update,
                    "update_count": self._update_count,
                    "event_window": EVENT_WINDOW,
                },
            }

    def save(self) -> None:
        """Explicitly persist state."""
        self._save_data()


# ══════════════════════════════════════════════════════════════════════════
# Singleton
# ══════════════════════════════════════════════════════════════════════════

_integrated_info: Optional[IntegratedInfo] = None
_integrated_info_lock = threading.Lock()


def get_integrated_info() -> IntegratedInfo:
    """
    Get the singleton IntegratedInfo instance.

    Returns:
        The global IntegratedInfo singleton.
    """
    global _integrated_info
    if _integrated_info is None:
        with _integrated_info_lock:
            if _integrated_info is None:
                _integrated_info = IntegratedInfo()
    return _integrated_info
