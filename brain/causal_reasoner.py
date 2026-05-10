#!/usr/bin/env python3
"""
causal_reasoner.py — FRIDAY Causal Reasoning Engine
=====================================================

Structural Causal Model (SCM) for understanding *why* things happen, not just
*what* happens. Enables interventional and counterfactual reasoning over
observed tool execution sequences and world states.

Core concepts (Judea Pearl's Causal Hierarchy):
  1. Association: P(Y|X) — observing X tells us about Y
  2. Intervention: P(Y|do(X=x)) — forcing X=x changes Y by...
  3. Counterfactual: P(Y_x|X=x', Y=y') — what would Y have been if X had been x?

Architecture:
  CausalGraph (DAG) ← CausalNode + CausalEdge
  StructuralCausalModel ← variables + equations
  CausalReasoner ← graph + SCM + LLM explanations + integration

Integration points:
  - brain.active_inference: causal predictions feed prediction errors
  - brain.world_model: causal structure improves trajectory predictions

Graceful degradation: if Gemini API unavailable, LLM features return
placeholder text instead of crashing.
"""

import json
import math
import random
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


BRAIN_DIR = Path(__file__).parent.resolve()
CAUSAL_FILE = BRAIN_DIR / "causal_data.json"
API_CONFIG_PATH = BRAIN_DIR.parent / "config" / "api_keys.json"

# Granger causality parameters
GRANGER_LAG = 3                # Number of past observations to consider
GRANGER_SIGNIFICANCE = 0.05    # p-value threshold for causal link
MIN_OBSERVATIONS = 5           # Minimum observations to attempt learning
CONFIDENCE_DECAY = 0.98        # Edge confidence decays per consolidation cycle
EDGE_STRENGTH_MIN = 0.05       # Below this, edge is pruned

# LLM config (matches other brain/ modules)
CAUSAL_MODEL = "gemini-2.5-flash"


def _timestamp() -> str:
    return datetime.now().isoformat()


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-max(-10, min(10, x))))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


# ── Data Structures ────────────────────────────────────────────────────────


class CausalNode:
    """A variable in the causal graph with its domain and observations."""

    def __init__(self, name: str, domain: Optional[Set[str]] = None):
        self.name = name
        self.domain: Set[str] = domain or set()
        self.observations: List[dict] = []   # [{timestamp, value, context}]
        self.latent_value: float = 0.0       # Current estimated value

    def observe(self, value: Any, context: str = ""):
        """Record an observation of this variable."""
        self.domain.add(str(value))
        self.observations.append({
            "timestamp": _timestamp(),
            "value": value,
            "context": context,
        })
        # Keep bounded
        if len(self.observations) > 200:
            self.observations = self.observations[-200:]

    def recent_values(self, n: int = 10) -> list:
        """Get last n observed values."""
        return [o["value"] for o in self.observations[-n:]]

    def mean(self) -> float:
        """Mean of numeric observations."""
        nums = []
        for o in self.observations:
            try:
                nums.append(float(o["value"]))
            except (TypeError, ValueError):
                continue
        return sum(nums) / len(nums) if nums else 0.0

    def variance(self) -> float:
        """Variance of numeric observations."""
        nums = []
        for o in self.observations:
            try:
                nums.append(float(o["value"]))
            except (TypeError, ValueError):
                continue
        if len(nums) < 2:
            return 0.0
        m = sum(nums) / len(nums)
        return sum((x - m) ** 2 for x in nums) / (len(nums) - 1)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "domain": list(self.domain),
            "observations": self.observations[-50:],  # Persist last 50
            "latent_value": self.latent_value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CausalNode":
        node = cls(d["name"], set(d.get("domain", [])))
        node.observations = d.get("observations", [])
        node.latent_value = d.get("latent_value", 0.0)
        return node


class CausalEdge:
    """Directed edge: cause → effect with strength, mechanism, confidence."""

    def __init__(self, cause: str, effect: str, strength: float = 0.5,
                 mechanism: str = "", confidence: float = 0.5):
        self.cause = cause
        self.effect = effect
        self.strength = max(0.0, min(1.0, strength))
        self.mechanism = mechanism
        self.confidence = max(0.0, min(1.0, confidence))
        self.created_at = _timestamp()
        self.last_validated = _timestamp()
        self.validation_count = 0
        self.supporting_observations: int = 0

    def to_dict(self) -> dict:
        return {
            "cause": self.cause,
            "effect": self.effect,
            "strength": round(self.strength, 4),
            "mechanism": self.mechanism,
            "confidence": round(self.confidence, 4),
            "created_at": self.created_at,
            "last_validated": self.last_validated,
            "validation_count": self.validation_count,
            "supporting_observations": self.supporting_observations,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CausalEdge":
        edge = cls(d["cause"], d["effect"], d.get("strength", 0.5),
                   d.get("mechanism", ""), d.get("confidence", 0.5))
        edge.created_at = d.get("created_at", _timestamp())
        edge.last_validated = d.get("last_validated", _timestamp())
        edge.validation_count = d.get("validation_count", 0)
        edge.supporting_observations = d.get("supporting_observations", 0)
        return edge


class CausalGraph:
    """
    Directed Acyclic Graph of cause-effect relationships.
    Stored as adjacency list (forward) and reverse adjacency (backward).
    """

    def __init__(self):
        self.nodes: Dict[str, CausalNode] = {}
        self.edges: Dict[Tuple[str, str], CausalEdge] = {}  # (cause, effect) -> edge
        self._forward: Dict[str, Set[str]] = defaultdict(set)   # cause -> {effects}
        self._backward: Dict[str, Set[str]] = defaultdict(set)  # effect -> {causes}

    def add_node(self, node: CausalNode):
        self.nodes[node.name] = node

    def get_or_create_node(self, name: str) -> CausalNode:
        if name not in self.nodes:
            self.nodes[name] = CausalNode(name)
        return self.nodes[name]

    def add_edge(self, edge: CausalEdge):
        """Add edge, checking for cycles."""
        # Temporarily add to check for cycles
        self._forward[edge.cause].add(edge.effect)
        self._backward[edge.effect].add(edge.cause)
        if self._has_cycle():
            # Rollback
            self._forward[edge.cause].discard(edge.effect)
            self._backward[edge.effect].discard(edge.cause)
            print(f"[CausalReasoner] Rejected edge {edge.cause}→{edge.effect}: would create cycle")
            return False
        self.edges[(edge.cause, edge.effect)] = edge
        self.get_or_create_node(edge.cause)
        self.get_or_create_node(edge.effect)
        return True

    def _has_cycle(self) -> bool:
        """Kahn's algorithm to detect cycles."""
        in_degree = defaultdict(int)
        for n in self._forward:
            for m in self._forward[n]:
                in_degree[m] += 1
        queue = deque(n for n in self.nodes if in_degree[n] == 0 and n in self._forward or n in self._backward)
        # Collect all nodes involved
        all_nodes = set(self._forward.keys()) | set(self._backward.keys()) | set(self.nodes.keys())
        for n in all_nodes:
            if in_degree[n] == 0:
                queue.append(n)
        visited = 0
        while queue:
            n = queue.popleft()
            visited += 1
            for m in self._forward.get(n, set()):
                in_degree[m] -= 1
                if in_degree[m] == 0:
                    queue.append(m)
        return visited < len(all_nodes)

    def find_path(self, start: str, end: str) -> Optional[List[str]]:
        """BFS to find shortest path from start to end."""
        if start == end:
            return [start]
        visited = {start}
        queue = deque([(start, [start])])
        while queue:
            node, path = queue.popleft()
            for neighbor in self._forward.get(node, set()):
                if neighbor == end:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return None

    def ancestors(self, node: str) -> Set[str]:
        """All nodes that can reach this node (backward closure)."""
        visited = set()
        queue = deque([node])
        while queue:
            n = queue.popleft()
            for parent in self._backward.get(n, set()):
                if parent not in visited:
                    visited.add(parent)
                    queue.append(parent)
        return visited

    def descendants(self, node: str) -> Set[str]:
        """All nodes reachable from this node (forward closure)."""
        visited = set()
        queue = deque([node])
        while queue:
            n = queue.popleft()
            for child in self._forward.get(n, set()):
                if child not in visited:
                    visited.add(child)
                    queue.append(child)
        return visited

    def to_dict(self) -> dict:
        return {
            "nodes": {n: nd.to_dict() for n, nd in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges.values()],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CausalGraph":
        g = cls()
        for n, nd in d.get("nodes", {}).items():
            g.nodes[n] = CausalNode.from_dict(nd)
        for e in d.get("edges", []):
            edge = CausalEdge.from_dict(e)
            g.edges[(edge.cause, edge.effect)] = edge
            g._forward[edge.cause].add(edge.effect)
            g._backward[edge.effect].add(edge.cause)
        return g


# ── Structural Causal Model ───────────────────────────────────────────────


class StructuralCausalModel:
    """
    Variables + structural equations. Supports simple linear equations
    and LLM-assisted complex mechanisms.
    """

    def __init__(self):
        self.equations: Dict[str, dict] = {}  # effect -> {type, params}
        # Linear: {"type": "linear", "coefficients": {"cause1": 0.5, ...}, "intercept": 0.0}
        # LLM:    {"type": "llm", "prompt_template": "..."}

    def set_linear_equation(self, effect: str, coefficients: Dict[str, float],
                            intercept: float = 0.0):
        """Define a linear structural equation: effect = sum(coeff * cause) + intercept."""
        self.equations[effect] = {
            "type": "linear",
            "coefficients": coefficients,
            "intercept": intercept,
        }

    def predict(self, effect: str, context: Dict[str, float]) -> float:
        """Predict value of effect given context values."""
        eq = self.equations.get(effect)
        if not eq:
            return context.get(effect, 0.0)

        if eq["type"] == "linear":
            result = eq["intercept"]
            for cause, coeff in eq["coefficients"].items():
                result += coeff * context.get(cause, 0.0)
            return result

        return context.get(effect, 0.0)

    def fit_linear(self, effect: str, observations: List[Dict[str, float]]):
        """Simple OLS fit from observations (no numpy dependency)."""
        if len(observations) < 3:
            return

        # Collect all cause variables present in observations
        all_keys = set()
        for obs in observations:
            all_keys.update(obs.keys())
        all_keys.discard(effect)

        causes = sorted(all_keys)
        n = len(observations)
        if not causes or n < len(causes) + 2:
            return

        # Build X matrix and y vector
        y = []
        X = []
        for obs in observations:
            yi = obs.get(effect, 0.0)
            try:
                yi = float(yi)
            except (TypeError, ValueError):
                continue
            y.append(yi)
            row = [1.0]  # intercept
            for c in causes:
                try:
                    row.append(float(obs.get(c, 0.0)))
                except (TypeError, ValueError):
                    row.append(0.0)
            X.append(row)

        if len(X) < len(causes) + 2:
            return

        # Normal equations: (X^T X) beta = X^T y  (small system, direct solve)
        cols = len(causes) + 1
        XtX = [[0.0] * cols for _ in range(cols)]
        Xty = [0.0] * cols

        for i in range(len(X)):
            for j in range(cols):
                Xty[j] += X[i][j] * y[i]
                for k in range(cols):
                    XtX[j][k] += X[i][j] * X[i][k]

        # Gauss-Jordan elimination
        aug = [XtX[j][:] + [Xty[j]] for j in range(cols)]
        for col in range(cols):
            # Pivot
            max_row = col
            for row in range(col + 1, cols):
                if abs(aug[row][col]) > abs(aug[max_row][col]):
                    max_row = row
            aug[col], aug[max_row] = aug[max_row], aug[col]
            if abs(aug[col][col]) < 1e-10:
                continue
            pivot = aug[col][col]
            for j in range(cols + 1):
                aug[col][j] /= pivot
            for row in range(cols):
                if row == col:
                    continue
                factor = aug[row][col]
                for j in range(cols + 1):
                    aug[row][j] -= factor * aug[col][j]

        coefficients = {}
        intercept = aug[0][cols]
        for i, c in enumerate(causes):
            coeff = aug[i + 1][cols]
            if abs(coeff) > 0.01:  # Prune negligible
                coefficients[c] = round(coeff, 4)

        if coefficients:
            self.equations[effect] = {
                "type": "linear",
                "coefficients": coefficients,
                "intercept": round(intercept, 4),
            }

    def to_dict(self) -> dict:
        return {"equations": self.equations}

    @classmethod
    def from_dict(cls, d: dict) -> "StructuralCausalModel":
        scm = cls()
        scm.equations = d.get("equations", {})
        return scm


# ── Main Causal Reasoner ──────────────────────────────────────────────────


class CausalReasoner:
    """
    FRIDAY's causal reasoning engine. Maintains a causal graph, performs
    interventions and counterfactuals, learns structure from observations,
    and integrates with active inference and world model.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self.graph = CausalGraph()
        self.scm = StructuralCausalModel()
        self._intervention_log: List[dict] = []
        self._counterfactual_log: List[dict] = []
        self._load()
        self._start_consolidation_thread()
        print("[CausalReasoner] Initialized")

    # ── Persistence ─────────────────────────────────────────────────────

    def _load(self):
        if not CAUSAL_FILE.exists():
            self._save()
            return
        try:
            raw = CAUSAL_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            self.graph = CausalGraph.from_dict(data.get("graph", {}))
            self.scm = StructuralCausalModel.from_dict(data.get("scm", {}))
            self._intervention_log = data.get("intervention_log", [])
            self._counterfactual_log = data.get("counterfactual_log", [])
            print(f"[CausalReasoner] Loaded: {len(self.graph.nodes)} nodes, "
                  f"{len(self.graph.edges)} edges")
        except (json.JSONDecodeError, IOError) as e:
            print(f"[CausalReasoner] Load failed, starting fresh: {e}")

    def _save(self):
        try:
            data = {
                "meta": {
                    "version": 1,
                    "created": _timestamp(),
                    "last_update": _timestamp(),
                },
                "graph": self.graph.to_dict(),
                "scm": self.scm.to_dict(),
                "intervention_log": self._intervention_log[-100:],
                "counterfactual_log": self._counterfactual_log[-50:],
            }
            CAUSAL_FILE.write_text(json.dumps(data, indent=2, default=str),
                                   encoding="utf-8")
        except IOError as e:
            print(f"[CausalReasoner] Save failed: {e}")

    # ── Consolidation ──────────────────────────────────────────────────

    def _start_consolidation_thread(self):
        def _consolidate_loop():
            while True:
                time.sleep(600)  # Every 10 minutes
                try:
                    self._consolidate()
                except Exception as e:
                    print(f"[CausalReasoner] Consolidation error: {e}")

        t = threading.Thread(target=_consolidate_loop, daemon=True,
                             name="causal-consolidation")
        t.start()

    def _consolidate(self):
        """Periodic maintenance: decay confidence, prune weak edges, re-fit equations."""
        with self._lock:
            pruned = 0
            for key in list(self.graph.edges.keys()):
                edge = self.graph.edges[key]
                edge.confidence *= CONFIDENCE_DECAY
                if edge.confidence < EDGE_STRENGTH_MIN and edge.validation_count < 2:
                    # Remove weak, unvalidated edge
                    del self.graph.edges[key]
                    self.graph._forward[edge.cause].discard(edge.effect)
                    self.graph._backward[edge.effect].discard(edge.cause)
                    pruned += 1

            # Re-fit equations for nodes with enough observations
            for name, node in self.graph.nodes.items():
                if len(node.observations) >= MIN_OBSERVATIONS:
                    # Build observation dicts for fitting
                    obs_dicts = []
                    for obs in node.observations[-50:]:
                        d = {name: obs.get("value", 0)}
                        ctx = obs.get("context", "")
                        if isinstance(ctx, dict):
                            d.update(ctx)
                        obs_dicts.append(d)
                    if obs_dicts:
                        self.scm.fit_linear(name, obs_dicts)

            if pruned:
                print(f"[CausalReasoner] Consolidated: pruned {pruned} weak edges")
            self._save()

    # ── Causal Graph Construction from Sequences ───────────────────────

    def build_graph_from_sequences(self, observations: List[dict]):
        """
        Learn causal structure from tool execution sequences using Granger
        causality: X Granger-causes Y if past X values improve prediction of Y.

        observations: list of {tool, timestamp, success, duration_ms, context}
        """
        if len(observations) < MIN_OBSERVATIONS:
            print(f"[CausalReasoner] Need ≥{MIN_OBSERVATIONS} observations, got {len(observations)}")
            return

        with self._lock:
            # Group by tool name
            tool_series: Dict[str, List[float]] = defaultdict(list)
            for obs in observations:
                tool = obs.get("tool", obs.get("name", "unknown"))
                val = 1.0 if obs.get("success", True) else 0.0
                dur = obs.get("duration_ms", 0)
                # Composite signal: success weighted by inverse duration
                signal = val * (1.0 / (1.0 + dur / 1000.0))
                tool_series[tool].append(signal)

            tools = sorted(tool_series.keys())

            # Ensure all series are same length (use shortest)
            min_len = min(len(v) for v in tool_series.values())
            if min_len < GRANGER_LAG + 2:
                return
            for t in tools:
                tool_series[t] = tool_series[t][-min_len:]

            # Test Granger causality for each pair
            new_edges = 0
            for cause in tools:
                for effect in tools:
                    if cause == effect:
                        continue
                    gc_stat = self._granger_test(
                        tool_series[cause], tool_series[effect])
                    if gc_stat > GRANGER_SIGNIFICANCE:
                        # Causal link detected
                        strength = min(1.0, gc_stat / 2.0)
                        existing = self.graph.edges.get((cause, effect))
                        if existing:
                            existing.strength = max(existing.strength, strength)
                            existing.confidence = min(1.0, existing.confidence + 0.1)
                            existing.supporting_observations += 1
                            existing.last_validated = _timestamp()
                        else:
                            edge = CausalEdge(
                                cause=cause,
                                effect=effect,
                                strength=round(strength, 3),
                                mechanism=f"Granger causality (lag={GRANGER_LAG})",
                                confidence=0.5,
                            )
                            edge.supporting_observations = 1
                            if self.graph.add_edge(edge):
                                new_edges += 1

            # Record observations in nodes
            for obs in observations:
                tool = obs.get("tool", obs.get("name", "unknown"))
                node = self.graph.get_or_create_node(tool)
                node.observe(
                    1.0 if obs.get("success", True) else 0.0,
                    context=obs.get("context", ""),
                )

            if new_edges:
                print(f"[CausalReasoner] Learned {new_edges} new causal edges from "
                      f"{len(observations)} observations")
            self._save()

    def _granger_test(self, x: List[float], y: List[float]) -> float:
        """
        Simplified Granger causality test.
        Returns F-statistic proxy: how much past X improves prediction of Y
        beyond past Y alone. Higher = more likely X→Y.
        """
        n = len(y)
        lag = min(GRANGER_LAG, n // 3)
        if lag < 1:
            return 0.0

        # Restricted model: y_t = a + b*y_{t-1} + ... + b*y_{t-lag}
        # Unrestricted model: y_t = a + b*y_{t-1}... + c*x_{t-1}...
        start = lag
        y_actual = y[start:]

        # Restricted predictions (autoregressive only)
        resid_restricted = []
        for t in range(start, n):
            pred = sum(y[t - l - 1] for l in range(lag)) / lag
            resid_restricted.append((y[t] - pred) ** 2)

        # Unrestricted predictions (add lagged x)
        resid_unrestricted = []
        for t in range(start, n):
            y_part = sum(y[t - l - 1] for l in range(lag)) / lag
            x_part = sum(x[t - l - 1] for l in range(lag)) / lag
            pred = 0.5 * y_part + 0.5 * x_part
            resid_unrestricted.append((y[t] - pred) ** 2)

        rss_r = sum(resid_restricted) + 1e-10
        rss_u = sum(resid_unrestricted) + 1e-10

        # F-statistic proxy
        n_obs = len(y_actual)
        k_r = lag
        k_u = 2 * lag
        if rss_u < 1e-10:
            return 0.0
        f_stat = ((rss_r - rss_u) / (k_u - k_r)) / (rss_u / max(n_obs - k_u, 1))

        # Convert to p-value proxy (higher F → lower p → more significant)
        # We return F as a significance score; threshold caller decides
        return f_stat

    # ── Intervention: do-calculus ───────────────────────────────────────

    def do_calculus(self, action: str, variable: str,
                    value: Any = None) -> dict:
        """
        Compute intervention effect: P(Y | do(X=x)).
        Simulates setting variable to value and propagating effects
        through structural equations.

        Returns: {affected_variables: {name: new_value}, total_impact: float}
        """
        with self._lock:
            if value is None:
                value = action

            # Set the intervened variable
            node = self.graph.get_or_create_node(variable)
            node.observe(value, context={"intervention": True})

            affected = {variable: value}
            total_impact = 0.0

            # Propagate forward through DAG (topological order)
            queue = deque([variable])
            visited = {variable}

            while queue:
                current = queue.popleft()
                current_val = float(affected.get(current, 0))
                try:
                    current_val = float(current_val)
                except (TypeError, ValueError):
                    current_val = 0.0

                for effect_name in self.graph._forward.get(current, set()):
                    if effect_name in visited:
                        continue
                    visited.add(effect_name)

                    edge = self.graph.edges.get((current, effect_name))
                    if not edge:
                        continue

                    # Propagate through SCM equation or edge strength
                    eq = self.scm.equations.get(effect_name)
                    if eq and eq["type"] == "linear":
                        # Re-compute with new value
                        ctx = {v: float(affected.get(v, self.graph.nodes[v].mean()))
                               for v in eq["coefficients"]
                               if v in self.graph.nodes}
                        ctx[current] = current_val
                        new_val = self.scm.predict(effect_name, ctx)
                    else:
                        # Simple propagation: effect = strength * cause_delta
                        base = self.graph.nodes[effect_name].mean()
                        new_val = base + edge.strength * current_val

                    affected[effect_name] = round(new_val, 4)
                    impact = abs(new_val - self.graph.nodes[effect_name].mean())
                    total_impact += impact
                    queue.append(effect_name)

            # Log intervention
            entry = {
                "timestamp": _timestamp(),
                "action": action,
                "variable": variable,
                "value": value,
                "affected": affected,
                "total_impact": round(total_impact, 4),
            }
            self._intervention_log.append(entry)
            self._save()

            print(f"[CausalReasoner] do({variable}={value}) → "
                  f"affected {len(affected)} variables, impact={total_impact:.3f}")
            return {"affected_variables": affected, "total_impact": round(total_impact, 4)}

    # ── Counterfactual Reasoning ───────────────────────────────────────

    def counterfactual(self, observation: dict, intervention: dict) -> dict:
        """
        Counterfactual: "What would have happened if X had been x instead of x'?"

        observation: actual world state {variable: value, ...}
        intervention: hypothetical change {variable: value, ...}

        Returns: {counterfactual_state: {...}, differences: {...}, explanation: str}
        """
        with self._lock:
            # Step 1: Abduction — infer latent variables from observation
            # (simplified: use observation as world state)
            actual_state = dict(observation)

            # Step 2: Action — apply intervention
            cf_state = dict(actual_state)
            for var, val in intervention.items():
                cf_state[var] = val

            # Step 3: Prediction — propagate through structural equations
            for var in intervention:
                queue = deque([var])
                visited = set(intervention.keys())

                while queue:
                    current = queue.popleft()
                    for effect_name in self.graph._forward.get(current, set()):
                        if effect_name in visited:
                            continue
                        visited.add(effect_name)

                        edge = self.graph.edges.get((current, effect_name))
                        if not edge:
                            continue

                        eq = self.scm.equations.get(effect_name)
                        if eq and eq["type"] == "linear":
                            ctx = {v: cf_state.get(v, self.graph.nodes[v].mean())
                                   for v in eq["coefficients"]}
                            new_val = self.scm.predict(effect_name, ctx)
                        else:
                            base = cf_state.get(effect_name,
                                                self.graph.nodes.get(effect_name, CausalNode(effect_name)).mean())
                            cause_delta = cf_state.get(current, 0) - actual_state.get(current, 0)
                            new_val = base + edge.strength * cause_delta

                        cf_state[effect_name] = round(new_val, 4)
                        queue.append(effect_name)

            # Compute differences
            differences = {}
            for var in set(list(actual_state.keys()) + list(cf_state.keys())):
                a = actual_state.get(var)
                c = cf_state.get(var)
                if a != c and c is not None:
                    differences[var] = {"actual": a, "counterfactual": c}

            # Generate explanation
            explanation_parts = []
            for var, val in intervention.items():
                actual_val = actual_state.get(var, "unknown")
                explanation_parts.append(
                    f"If {var} had been {val} (instead of {actual_val})")
            for var, diff in differences.items():
                if var not in intervention:
                    explanation_parts.append(
                        f"then {var} would have been {diff['counterfactual']} "
                        f"(instead of {diff['actual']})")

            explanation = ". ".join(explanation_parts) + "." if explanation_parts else "No difference detected."

            result = {
                "counterfactual_state": cf_state,
                "differences": differences,
                "explanation": explanation,
            }

            self._counterfactual_log.append({
                "timestamp": _timestamp(),
                "observation": observation,
                "intervention": intervention,
                "result": result,
            })
            self._save()

            print(f"[CausalReasoner] Counterfactual: {len(differences)} differences found")
            return result

    # ── Traversal ──────────────────────────────────────────────────────

    def find_causes(self, effect: str, max_depth: int = 5) -> List[dict]:
        """Trace backward to find all causes of an effect."""
        with self._lock:
            causes = []
            visited = set()
            queue = deque([(effect, 0)])

            while queue:
                node, depth = queue.popleft()
                if depth > max_depth or node in visited:
                    continue
                visited.add(node)

                for cause_name in self.graph._backward.get(node, set()):
                    edge = self.graph.edges.get((cause_name, node))
                    if edge:
                        causes.append({
                            "cause": cause_name,
                            "effect": node,
                            "strength": edge.strength,
                            "confidence": edge.confidence,
                            "mechanism": edge.mechanism,
                            "depth": depth + 1,
                        })
                    queue.append((cause_name, depth + 1))

            causes.sort(key=lambda c: c["strength"] * c["confidence"], reverse=True)
            return causes

    def find_effects(self, cause: str, max_depth: int = 5) -> List[dict]:
        """Trace forward to find all effects of a cause."""
        with self._lock:
            effects = []
            visited = set()
            queue = deque([(cause, 0)])

            while queue:
                node, depth = queue.popleft()
                if depth > max_depth or node in visited:
                    continue
                visited.add(node)

                for effect_name in self.graph._forward.get(node, set()):
                    edge = self.graph.edges.get((node, effect_name))
                    if edge:
                        effects.append({
                            "cause": node,
                            "effect": effect_name,
                            "strength": edge.strength,
                            "confidence": edge.confidence,
                            "mechanism": edge.mechanism,
                            "depth": depth + 1,
                        })
                    queue.append((effect_name, depth + 1))

            effects.sort(key=lambda e: e["strength"] * e["confidence"], reverse=True)
            return effects

    # ── LLM Explanations ───────────────────────────────────────────────

    def explain_causal_chain(self, cause: str, effect: str) -> str:
        """Generate natural language explanation of causal chain via LLM."""
        path = self.graph.find_path(cause, effect)
        if not path:
            return f"No known causal path from {cause} to {effect}."

        # Build chain description
        chain_parts = []
        for i in range(len(path) - 1):
            edge = self.graph.edges.get((path[i], path[i + 1]))
            if edge:
                chain_parts.append(
                    f"{path[i]} → {path[i+1]} "
                    f"(strength={edge.strength:.2f}, mechanism='{edge.mechanism}')")
            else:
                chain_parts.append(f"{path[i]} → {path[i+1]}")

        chain_desc = " → ".join(path)

        # Try LLM explanation
        try:
            return self._llm_explain(cause, effect, chain_desc, chain_parts)
        except Exception as e:
            print(f"[CausalReasoner] LLM explanation failed: {e}")
            # Fallback: template-based explanation
            parts = [f"Causal chain from {cause} to {effect}: {chain_desc}"]
            for cp in chain_parts:
                parts.append(f"  • {cp}")
            parts.append(f"Chain length: {len(path)} steps")
            return "\n".join(parts)

    def _llm_explain(self, cause: str, effect: str, chain_desc: str,
                     chain_parts: list) -> str:
        """Call Gemini to generate causal explanation."""
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise RuntimeError("google-genai not installed")

        try:
            api_config = json.loads(API_CONFIG_PATH.read_text())
            api_key = api_config.get("gemini_api_key", api_config.get("gemini", {}).get("api_key", ""))
            if not api_key:
                raise RuntimeError("No Gemini API key")
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            raise RuntimeError("API config unavailable")

        client = genai.Client(api_key=api_key)

        prompt = (
            f"Explain this causal chain in clear, concise natural language.\n\n"
            f"Cause: {cause}\nEffect: {effect}\n"
            f"Chain: {chain_desc}\n"
            f"Details:\n" + "\n".join(f"  - {cp}" for cp in chain_parts) + "\n\n"
            f"Explain WHY this causal relationship exists in 2-3 sentences. "
            f"Be specific about the mechanism."
        )

        resp = client.models.generate_content(model=CAUSAL_MODEL, contents=prompt)
        return resp.text.strip()

    # ── Validation ─────────────────────────────────────────────────────

    def validate_causal_link(self, cause: str, effect: str,
                             interventions: List[dict]) -> dict:
        """
        Test if a causal link holds under intervention.

        interventions: list of {cause_value, observed_effect_value}
        Returns: {valid: bool, confidence: float, evidence: list}
        """
        with self._lock:
            if not interventions:
                return {"valid": False, "confidence": 0.0, "evidence": []}

            predictions_correct = 0
            evidence = []

            for intervention in interventions:
                cause_val = intervention.get("cause_value")
                expected_effect = intervention.get("expected_effect")

                # Predict using SCM
                result = self.do_calculus(str(cause_val), cause, cause_val)
                predicted_effect = result["affected_variables"].get(effect)

                if predicted_effect is not None and expected_effect is not None:
                    # Check if prediction matches (within tolerance)
                    try:
                        diff = abs(float(predicted_effect) - float(expected_effect))
                        correct = diff < 0.3  # tolerance
                    except (TypeError, ValueError):
                        correct = str(predicted_effect) == str(expected_effect)

                    if correct:
                        predictions_correct += 1
                    evidence.append({
                        "cause_value": cause_val,
                        "predicted": predicted_effect,
                        "expected": expected_effect,
                        "match": correct,
                })

            confidence = predictions_correct / len(interventions)
            valid = confidence > 0.5

            # Update edge confidence
            edge = self.graph.edges.get((cause, effect))
            if edge:
                edge.confidence = (edge.confidence + confidence) / 2
                edge.validation_count += 1
                edge.last_validated = _timestamp()
                self._save()

            print(f"[CausalReasoner] Validated {cause}→{effect}: "
                  f"{'VALID' if valid else 'INVALID'} "
                  f"(confidence={confidence:.2f})")
            return {
                "valid": valid,
                "confidence": round(confidence, 3),
                "evidence": evidence,
            }

    # ── Integration: Active Inference ──────────────────────────────────

    def feed_prediction_errors(self):
        """
        Send causal predictions to the active inference engine as
        prediction signals. Integrates with brain.active_inference.
        """
        try:
            from brain.active_inference import get_active_inference
            inference = get_active_inference()

            with self._lock:
                for (cause, effect), edge in self.graph.edges.items():
                    if edge.confidence > 0.5:
                        # Predict effect value based on cause's recent state
                        cause_node = self.graph.nodes.get(cause)
                        if cause_node and cause_node.observations:
                            recent = cause_node.recent_values(5)
                            if recent:
                                predicted_effect = edge.strength * float(recent[-1])
                                # Feed as prediction to active inference
                                # (tool predictions are the main use case)
                                inference.predict_outcome(
                                    effect, context=f"causal:{cause}→{effect}")

            print("[CausalReasoner] Fed predictions to active inference")
        except ImportError:
            pass  # active_inference not available
        except Exception as e:
            print(f"[CausalReasoner] Integration error: {e}")

    # ── Integration: World Model ───────────────────────────────────────

    def get_trajectory_predictions(self, start_state: dict,
                                   action_sequence: list) -> list:
        """
        Use causal structure to improve trajectory predictions.
        Returns predicted states after each action.
        """
        predictions = []
        current_state = dict(start_state)

        for action in action_sequence:
            action_name = action if isinstance(action, str) else action.get("tool", "unknown")

            # Check if this action has known causal effects
            effects = self.find_effects(action_name, max_depth=2)
            predicted_state = dict(current_state)

            for eff in effects:
                effect_name = eff["effect"]
                strength = eff["strength"]
                edge = self.graph.edges.get((action_name, effect_name))
                if edge:
                    # Predict state change
                    current_val = float(current_state.get(effect_name, 0))
                    delta = strength * float(current_state.get(action_name, 0.5))
                    predicted_state[effect_name] = current_val + delta

            predictions.append(predicted_state)
            current_state = predicted_state

        return predictions

    # ── Prompt Formatting ──────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 800) -> str:
        """Format causal knowledge for system prompt injection."""
        with self._lock:
            stats = self.get_stats()
            if stats["total_edges"] == 0:
                return ""

            parts = ["[CAUSAL REASONING — Cause-effect understanding]"]
            parts.append(
                f"  Nodes: {stats['total_nodes']} | "
                f"Edges: {stats['total_edges']} | "
                f"Avg confidence: {stats['avg_confidence']:.0%}")

            # Top causal relationships
            top_edges = sorted(
                self.graph.edges.values(),
                key=lambda e: e.strength * e.confidence,
                reverse=True
            )[:5]

            if top_edges:
                parts.append("  Top causal links:")
                for edge in top_edges:
                    parts.append(
                        f"    {edge.cause} → {edge.effect} "
                        f"(str={edge.strength:.2f} conf={edge.confidence:.2f})")

            result = "\n".join(parts)
            if len(result) > max_chars:
                result = result[:max_chars].rsplit("\n", 1)[0] + "\n  [...]"
            return result

    def get_stats(self) -> dict:
        """Get causal reasoning statistics."""
        with self._lock:
            confidences = [e.confidence for e in self.graph.edges.values()]
            strengths = [e.strength for e in self.graph.edges.values()]

            return {
                "total_nodes": len(self.graph.nodes),
                "total_edges": len(self.graph.edges),
                "total_equations": len(self.scm.equations),
                "avg_confidence": round(
                    sum(confidences) / max(len(confidences), 1), 3),
                "avg_strength": round(
                    sum(strengths) / max(len(strengths), 1), 3),
                "total_interventions": len(self._intervention_log),
                "total_counterfactuals": len(self._counterfactual_log),
                "high_confidence_edges": sum(1 for c in confidences if c > 0.7),
            }


# ── Singleton ──────────────────────────────────────────────────────────────

_causal_reasoner = None
_causal_lock = threading.Lock()


def get_causal_reasoner() -> CausalReasoner:
    """Get singleton causal reasoner instance."""
    global _causal_reasoner
    if _causal_reasoner is None:
        with _causal_lock:
            if _causal_reasoner is None:
                _causal_reasoner = CausalReasoner()
    return _causal_reasoner


# ── Quick test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cr = get_causal_reasoner()

    # Build some test observations
    test_obs = [
        {"tool": "read_file", "success": True, "duration_ms": 50},
        {"tool": "parse_json", "success": True, "duration_ms": 120},
        {"tool": "validate_schema", "success": True, "duration_ms": 200},
        {"tool": "read_file", "success": True, "duration_ms": 45},
        {"tool": "parse_json", "success": False, "duration_ms": 300},
        {"tool": "validate_schema", "success": False, "duration_ms": 100},
        {"tool": "read_file", "success": True, "duration_ms": 55},
        {"tool": "parse_json", "success": True, "duration_ms": 110},
    ]

    cr.build_graph_from_sequences(test_obs)
    print(f"\nStats: {cr.get_stats()}")
    print(f"\nCauses of validate_schema: {cr.find_causes('validate_schema')}")
    print(f"\nEffects of read_file: {cr.find_effects('read_file')}")

    # Test intervention
    result = cr.do_calculus("read_file", "read_file", 1.0)
    print(f"\nIntervention result: {result}")

    # Test counterfactual
    cf = cr.counterfactual(
        {"read_file": 1.0, "parse_json": 1.0, "validate_schema": 1.0},
        {"read_file": 0.0}
    )
    print(f"\nCounterfactual: {cf['explanation']}")

    print(f"\nPrompt format:\n{cr.format_for_prompt()}")
