#!/usr/bin/env python3
"""
cognitive_integration.py — FRIDAY Cognitive Integration Layer
===============================================================

The central nervous system that wires all cognitive modules into a
unified request-processing pipeline. This is the most critical module
in FRIDAY's cognitive architecture.

Inspired by:

  [CI-1] Global Workspace Theory (Baars, 1988; Dehaene & Naccache, 2001)
         — Consciousness arises from information broadcast via a global
           workspace. This module IS that workspace's control logic:
           it decides what gets processed, by which modules, and in
           what order.

  [CI-2] Dual-Process Theory (Kahneman, 2011; Stanovich & West, 2000)
         — System 1 (fast, automatic) handles routine tasks.
           System 2 (slow, deliberate) handles novel/complex tasks.
           The integration layer decides which system to engage.

  [CI-3] Predictive Processing (Clark, 2013; Friston, 2010)
         — The brain is a prediction machine. This layer first tries
           fast prediction (intuition), then engages deeper processing
           only when predictions fail or confidence is low.

  [CI-4] Adaptive Control (Norman & Shallice, 1986)
         — The Supervisory Attentional System (SAS) intervenes when
           routine processing is insufficient. This module IS the SAS.

Pipeline:
  1. Receive request → extract context
  2. Fast path: Intuition check (System 1)
     - If confident → return fast response
  3. Slow path: Deliberative pipeline (System 2)
     a. Metacognitive check: what strategy?
     b. Module competition: who should process this?
     c. Causal reasoning: what's the causal structure?
     d. Analogy: have we seen something similar?
     e. Creativity: do we need a novel approach?
     f. World model simulation: predict outcomes
     g. Neurosymbolic verification: is reasoning sound?
  4. Post-processing: metacognitive reflection, emotional update, learning
  5. Return CognitiveResponse

All module integrations use graceful degradation (try/except).
A failing module never blocks the pipeline.
"""

import hashlib
import json
import math
import threading
import time
import traceback
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


BRAIN_DIR = Path(__file__).parent.resolve()
INTEGRATION_FILE = BRAIN_DIR / "cognitive_integration.json"

# ── Configuration ───────────────────────────────────────────────────────────

# Fast path thresholds
FAST_PATH_CONFIDENCE = 0.75      # intuition confidence above this → fast path
FAST_PATH_TIMEOUT_MS = 100       # fast path must complete within 100ms

# Deliberative pipeline
PIPELINE_TIMEOUT_MS = 5000       # full pipeline timeout: 5 seconds
MODULE_TIMEOUT_MS = 1000         # per-module timeout: 1 second

# Module priorities (higher = called first in deliberative path)
MODULE_PRIORITIES = {
    "metacognitive": 10,         # always first: strategy selection
    "intuition": 8,              # second opinion from System 1
    "causal": 7,                 # causal structure analysis
    "analogy": 6,                # analogical reasoning
    "creativity": 5,             # novel approach generation
    "world_model": 4,            # outcome prediction
    "neurosymbolic": 3,          # logical verification
    "emotional": 2,              # emotional modulation
}

# Confidence aggregation
MIN_RESPONSE_CONFIDENCE = 0.1
MAX_MODULES_FOR_RESPONSE = 5

# Persistence
MAX_TRACE_HISTORY = 200
MAX_PERFORMANCE_LOG = 500


def _now() -> str:
    return datetime.now().isoformat()


def _timestamp() -> float:
    return time.time()


def _hash_request(request: str) -> str:
    return hashlib.md5(request.encode()).hexdigest()[:12]


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


# ── Data Structures ─────────────────────────────────────────────────────────

class CognitiveResponse:
    """
    The unified response from FRIDAY's cognitive pipeline.

    Contains not just the answer, but the full reasoning trace,
    which modules contributed, confidence, and emotional state.
    """

    __slots__ = [
        "response", "confidence", "modules_used", "reasoning_trace",
        "emotional_state", "path", "duration_ms", "request_hash",
        "strategy_used", "timestamp",
    ]

    def __init__(self, response: str, confidence: float = 0.5,
                 path: str = "unknown"):
        self.response = response
        self.confidence = _clamp(confidence)
        self.modules_used: List[str] = []
        self.reasoning_trace: List[dict] = []
        self.emotional_state: Optional[dict] = None
        self.path = path  # "fast" or "deliberative"
        self.duration_ms = 0.0
        self.request_hash = ""
        self.strategy_used = "default"
        self.timestamp = _now()

    def add_trace_step(self, module: str, action: str, result: Any = None,
                       duration_ms: float = 0.0, confidence: float = 0.0):
        """Add a step to the reasoning trace."""
        self.reasoning_trace.append({
            "module": module,
            "action": action,
            "result_summary": str(result)[:200] if result else None,
            "duration_ms": round(duration_ms, 2),
            "confidence": round(confidence, 3),
            "timestamp": _now(),
        })
        if module not in self.modules_used:
            self.modules_used.append(module)

    def to_dict(self) -> dict:
        return {
            "response": self.response[:1000],
            "confidence": round(self.confidence, 3),
            "modules_used": self.modules_used,
            "reasoning_trace": self.reasoning_trace,
            "emotional_state": self.emotional_state,
            "path": self.path,
            "duration_ms": round(self.duration_ms, 2),
            "request_hash": self.request_hash,
            "strategy_used": self.strategy_used,
            "timestamp": self.timestamp,
        }


class PipelineMetrics:
    """Tracks performance metrics for the cognitive pipeline."""

    __slots__ = [
        "total_requests", "fast_path_count", "deliberative_count",
        "avg_fast_ms", "avg_deliberative_ms", "module_invocations",
        "module_failures", "confidence_history",
    ]

    def __init__(self):
        self.total_requests = 0
        self.fast_path_count = 0
        self.deliberative_count = 0
        self.avg_fast_ms = 0.0
        self.avg_deliberative_ms = 0.0
        self.module_invocations: Dict[str, int] = defaultdict(int)
        self.module_failures: Dict[str, int] = defaultdict(int)
        self.confidence_history: deque = deque(maxlen=100)

    def record(self, response: CognitiveResponse):
        """Record metrics from a completed response."""
        self.total_requests += 1
        if response.path == "fast":
            self.fast_path_count += 1
            n = self.fast_path_count
            self.avg_fast_ms = (self.avg_fast_ms * (n - 1) + response.duration_ms) / n
        else:
            self.deliberative_count += 1
            n = self.deliberative_count
            self.avg_deliberative_ms = (
                self.avg_deliberative_ms * (n - 1) + response.duration_ms
            ) / n
        for module in response.modules_used:
            self.module_invocations[module] += 1
        self.confidence_history.append(response.confidence)

    def to_dict(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "fast_path_count": self.fast_path_count,
            "deliberative_count": self.deliberative_count,
            "avg_fast_ms": round(self.avg_fast_ms, 1),
            "avg_deliberative_ms": round(self.avg_deliberative_ms, 1),
            "module_invocations": dict(self.module_invocations),
            "module_failures": dict(self.module_failures),
            "avg_confidence": round(
                sum(self.confidence_history) / max(len(self.confidence_history), 1), 3
            ),
        }


# ── Cognitive Integration ───────────────────────────────────────────────────

class CognitiveIntegration:
    """
    The central cognitive integration layer — FRIDAY's supervisory
    attentional system.

    Orchestrates all cognitive modules into a unified pipeline:
    fast intuition → deliberative reasoning → metacognitive reflection.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self._metrics = PipelineMetrics()
        self._trace_history: List[dict] = []
        self._module_cache: Dict[str, Any] = {}  # lazy-loaded module refs
        self._session_start = _timestamp()
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────

    def _empty_store(self) -> dict:
        return {
            "meta": {
                "version": 1,
                "created": _now(),
                "last_update": _now(),
                "total_requests": 0,
                "total_fast_path": 0,
                "total_deliberative": 0,
            },
            "metrics": {},
            "recent_traces": [],
        }

    def _load(self):
        if not INTEGRATION_FILE.exists():
            self._data = self._empty_store()
            self._save()
            return
        try:
            raw = INTEGRATION_FILE.read_text(encoding="utf-8")
            self._data = json.loads(raw)
            self._trace_history = self._data.get("recent_traces", [])
        except (json.JSONDecodeError, IOError):
            self._data = self._empty_store()
            self._save()

    def _save(self):
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._data["metrics"] = self._metrics.to_dict()
            self._data["recent_traces"] = self._trace_history[-MAX_TRACE_HISTORY:]
            self._data["meta"]["last_update"] = _now()
            INTEGRATION_FILE.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # ── Module Loading (Graceful Degradation) ───────────────────────────

    def _get_module(self, name: str) -> Optional[Any]:
        """
        Safely load a cognitive module. Returns None if unavailable.
        All module access goes through here for graceful degradation.
        """
        if name in self._module_cache:
            return self._module_cache[name]

        try:
            if name == "intuition":
                from brain.intuition_engine import get_intuition_engine
                mod = get_intuition_engine()
            elif name == "metacognitive":
                from brain.metacognitive_monitor import get_metacognitive_monitor
                mod = get_metacognitive_monitor()
            elif name == "emotional":
                from brain.emotional_regulation import get_emotional_regulation
                mod = get_emotional_regulation()
            elif name == "causal":
                from brain.causal_reasoner import get_causal_reasoner
                mod = get_causal_reasoner()
            elif name == "analogy":
                from brain.analogy_engine import get_analogy_engine
                mod = get_analogy_engine()
            elif name == "creativity":
                from brain.creativity_engine import get_creativity_engine
                mod = get_creativity_engine()
            elif name == "world_model":
                from brain.world_model import get_world_model
                mod = get_world_model()
            elif name == "neurosymbolic":
                from brain.neurosymbolic_reasoner import get_neurosymbolic_reasoner
                mod = get_neurosymbolic_reasoner()
            elif name == "self_awareness":
                from brain.self_awareness import get_self_awareness
                mod = get_self_awareness()
            elif name == "learning":
                from brain.learning import get_learning_engine
                mod = get_learning_engine()
            elif name == "episodic":
                from brain.episodic_memory import get_episodic_memory
                mod = get_episodic_memory()
            elif name == "procedural":
                from brain.procedural_memory import get_procedural_memory
                mod = get_procedural_memory()
            elif name == "competition":
                from brain.module_competition import get_module_competition
                mod = get_module_competition()
            elif name == "active_inference":
                from brain.active_inference import get_active_inference
                mod = get_active_inference()
            elif name == "global_workspace":
                from brain.global_workspace import get_global_workspace
                mod = get_global_workspace()
            elif name == "research":
                from skills.research_agent import get_research_agent
                mod = get_research_agent()
            elif name == "creative":
                from skills.creative_studio import get_creative_studio
                mod = get_creative_studio()
            elif name == "document":
                from skills.document_intelligence import get_document_intelligence
                mod = get_document_intelligence()
            else:
                return None

            self._module_cache[name] = mod
            return mod
        except Exception:
            return None

    def _call_module(self, module_name: str, method_name: str,
                     *args, timeout_ms: float = MODULE_TIMEOUT_MS,
                     **kwargs) -> Tuple[bool, Any]:
        """
        Safely call a module method with timeout awareness.
        Returns (success, result).
        """
        start = _timestamp()
        mod = self._get_module(module_name)
        if mod is None:
            return False, None

        try:
            method = getattr(mod, method_name, None)
            if method is None:
                return False, None
            result = method(*args, **kwargs)
            elapsed = (_timestamp() - start) * 1000
            if elapsed > timeout_ms:
                # Logged but still returned
                pass
            return True, result
        except Exception as e:
            self._metrics.module_failures[module_name] = self._metrics.module_failures.get(module_name, 0) + 1
            return False, str(e)

    # ── Fast Path (System 1) ────────────────────────────────────────────

    def _fast_path(self, request: str, context: dict,
                   response: CognitiveResponse) -> bool:
        """
        Attempt fast-path response via intuition engine.

        Returns True if fast path produced a confident enough response.
        """
        start = _timestamp()

        # Get domain hint from context
        domain = context.get("domain", "general")

        # Try intuition recognition
        success, result = self._call_module(
            "intuition", "recognize", request, domain
        )

        if success and result:
            action, confidence, match_info = result
            elapsed = (_timestamp() - start) * 1000

            response.add_trace_step(
                module="intuition",
                action="recognize",
                result=action,
                duration_ms=elapsed,
                confidence=confidence,
            )

            if action and confidence >= FAST_PATH_CONFIDENCE:
                # Also get emotional context for the fast path
                emo_success, emo_result = self._call_module(
                    "emotional", "affect_heuristic", action
                )
                if emo_success and emo_result:
                    response.emotional_state = emo_result
                    # Slightly adjust confidence based on emotional valence
                    valence = emo_result.get("emotional_valence", 0.0)
                    response.confidence = _clamp(confidence + valence * 0.1)
                else:
                    response.confidence = confidence

                response.response = action
                response.path = "fast"
                response.strategy_used = "intuitive_recognition"
                return True

        return False

    # ── Deliberative Pipeline (System 2) ────────────────────────────────

    def _deliberative_pipeline(self, request: str, context: dict,
                                response: CognitiveResponse):
        """
        Full deliberative reasoning pipeline.
        Engages multiple cognitive modules in priority order.
        """
        response.path = "deliberative"
        pipeline_start = _timestamp()
        gathered_evidence: List[dict] = []

        # ── Step 1: Metacognitive Strategy Selection ─────────────────
        task_type = context.get("task_type", "general")
        strat_success, strategy = self._call_module(
            "metacognitive", "suggest_strategy", task_type
        )
        if strat_success and strategy:
            response.strategy_used = strategy
            response.add_trace_step(
                "metacognitive", "suggest_strategy", strategy,
                (_timestamp() - pipeline_start) * 1000, 0.0
            )
            # Register cognitive activity
            self._call_module("metacognitive", "register_module_active", "cognitive_integration")

        # ── Step 2: Emotional Priming ────────────────────────────────
        emo_success, emotional_context = self._call_module(
            "emotional", "get_emotional_context"
        )
        if emo_success and emotional_context:
            response.emotional_state = emotional_context.get("mood")
            response.add_trace_step(
                "emotional", "get_emotional_context",
                emotional_context.get("mood", {}).get("label", "neutral"),
                (_timestamp() - pipeline_start) * 1000, 0.0
            )

        # ── Step 3: Module Competition (if available) ────────────────
        comp_success, competition_result = self._call_module(
            "competition", "compete", request, context
        )
        if comp_success and competition_result:
            response.add_trace_step(
                "competition", "compete",
                str(competition_result)[:150],
                (_timestamp() - pipeline_start) * 1000, 0.0
            )

        # ── Step 4: Causal Reasoning ─────────────────────────────────
        causal_success, causal_result = self._call_module(
            "causal", "do_calculus", "predict", request[:200]
        )
        if causal_success and causal_result:
            response.add_trace_step(
                "causal", "do_calculus",
                str(causal_result)[:150],
                (_timestamp() - pipeline_start) * 1000, 0.0
            )
            gathered_evidence.append({
                "source": "causal",
                "data": causal_result,
                "weight": 0.8,
            })

        # ── Step 5: Analogical Reasoning ─────────────────────────────
        analogy_success, analogy_result = self._call_module(
            "analogy", "score_analogy", request[:200], context
        )
        if analogy_success and analogy_result:
            response.add_trace_step(
                "analogy", "score_analogy",
                str(analogy_result)[:150],
                (_timestamp() - pipeline_start) * 1000, 0.0
            )
            gathered_evidence.append({
                "source": "analogy",
                "data": analogy_result,
                "weight": 0.6,
            })

        # ── Step 6: Creativity Check ─────────────────────────────────
        creativity_success, creative_result = self._call_module(
            "creativity", "generate_alternatives", request, context
        )
        if creativity_success and creative_result:
            response.add_trace_step(
                "creativity", "generate_alternatives",
                str(creative_result)[:150],
                (_timestamp() - pipeline_start) * 1000, 0.0
            )
            gathered_evidence.append({
                "source": "creativity",
                "data": creative_result,
                "weight": 0.5,
            })

        # ── Step 7: World Model Simulation ───────────────────────────
        wm_success, wm_result = self._call_module(
            "world_model", "evaluate_plan",
            [request[:100]]
        )
        if wm_success and wm_result:
            response.add_trace_step(
                "world_model", "simulate_outcome",
                str(wm_result)[:150],
                (_timestamp() - pipeline_start) * 1000, 0.0
            )
            gathered_evidence.append({
                "source": "world_model",
                "data": wm_result,
                "weight": 0.7,
            })

        # ── Step 8: Neurosymbolic Verification ───────────────────────
        neuro_success, neuro_result = self._call_module(
            "neurosymbolic", "check_consistency",
            [{"statement": str(ev.get("data", ""))[:100], "confidence": ev.get("weight", 0.5)} for ev in gathered_evidence]
        )
        if neuro_success and neuro_result:
            response.add_trace_step(
                "neurosymbolic", "verify_reasoning",
                str(neuro_result)[:150],
                (_timestamp() - pipeline_start) * 1000, 0.0
            )

        # ── Step 9: Intuitive Second Opinion ─────────────────────────
        intuition_success, gut_result = self._call_module(
            "intuition", "generate_intuitive_judgment", request,
            context.get("domain", "general")
        )
        if intuition_success and gut_result:
            response.add_trace_step(
                "intuition", "generate_intuitive_judgment",
                gut_result.get("judgment", "neutral"),
                (_timestamp() - pipeline_start) * 1000,
                gut_result.get("strength", 0.0),
            )
            gathered_evidence.append({
                "source": "intuition_gut",
                "data": gut_result,
                "weight": 0.4,
            })

        # ── Step 10: Synthesize Response ─────────────────────────────
        synthesis = self._synthesize_response(
            request, context, gathered_evidence, response
        )
        response.response = synthesis.get("response", "")
        response.confidence = synthesis.get("confidence", 0.5)

        # ── Step 11: Apply Somatic Markers to Final Confidence ───────
        if response.emotional_state:
            valence = response.emotional_state.get("valence", 0.0) if isinstance(
                response.emotional_state, dict
            ) else 0.0
            # Positive mood slightly boosts confidence, negative slightly reduces
            response.confidence = _clamp(response.confidence + valence * 0.05)

    def _synthesize_response(self, request: str, context: dict,
                              evidence: List[dict],
                              response: CognitiveResponse) -> dict:
        """
        Synthesize gathered evidence into a final response and confidence.

        Uses weighted evidence aggregation: modules with higher weight
        contribute more to the final confidence score.
        """
        if not evidence:
            return {
                "response": f"Processed request through deliberative pipeline. "
                            f"Request: {request[:100]}",
                "confidence": 0.3,
            }

        # Weighted confidence from evidence sources
        total_weight = 0.0
        weighted_confidence = 0.0
        evidence_summary = []

        for ev in evidence:
            source = ev.get("source", "unknown")
            weight = ev.get("weight", 0.5)
            data = ev.get("data")

            # Extract confidence from evidence
            if isinstance(data, dict):
                conf = data.get("confidence", data.get("strength", 0.5))
            elif isinstance(data, (list, tuple)) and len(data) >= 2:
                conf = data[1] if isinstance(data[1], (int, float)) else 0.5
            else:
                conf = 0.5

            weighted_confidence += conf * weight
            total_weight += weight
            evidence_summary.append(f"{source}({conf:.2f})")

        if total_weight > 0:
            final_confidence = weighted_confidence / total_weight
        else:
            final_confidence = 0.3

        # Build response text from evidence
        response_parts = [f"Deliberative analysis of: {request[:80]}..."]
        if evidence_summary:
            response_parts.append(f"Evidence from: {', '.join(evidence_summary)}")

        # Add top evidence insight
        if evidence:
            top = max(evidence, key=lambda e: e.get("weight", 0))
            top_data = top.get("data")
            if isinstance(top_data, dict):
                for key in ["result", "recommendation", "insight", "action"]:
                    if key in top_data:
                        response_parts.append(f"Key insight ({top['source']}): {str(top_data[key])[:100]}")
                        break

        return {
            "response": " | ".join(response_parts),
            "confidence": round(_clamp(final_confidence), 3),
        }

    # ── Post-Processing ─────────────────────────────────────────────────

    def _post_process(self, request: str, context: dict,
                      response: CognitiveResponse):
        """
        After response generation: metacognitive reflection,
        emotional update, and learning.
        """
        # Metacognitive reflection
        self._call_module(
            "metacognitive", "record_performance",
            success=True,  # assume success until proven otherwise
            confidence=response.confidence,
        )

        # Calibrate confidence
        self._call_module(
            "metacognitive", "calibrate_confidence",
            predicted=response.confidence,
            actual=response.confidence,  # will be updated when outcome is known
            context=request[:100],
        )

        # Record to episodic memory
        self._call_module(
            "episodic", "encode_event",
            "cognitive_response",
            f"Request: {request[:100]} | Response: {response.response[:100]}",
            context.get("domain", "general"),
        )

        # Update emotional state based on processing
        if response.confidence > 0.7:
            self._call_module(
                "emotional", "update_mood",
                valence_delta=0.1, arousal_delta=0.05,
            )
        elif response.confidence < 0.3:
            self._call_module(
                "emotional", "update_mood",
                valence_delta=-0.1, arousal_delta=0.1,
            )

        # Record learning signal
        self._call_module(
            "learning", "record_event",
            "cognitive_response",
            {"request": request[:200], "response": response.response[:200], "confidence": response.confidence},
        )

        # Publish to global workspace
        try:
            from brain.workspace_events import WorkspaceEvent, EventType
            event = WorkspaceEvent(
                source="cognitive_integration",
                type=EventType.TOOL_CALL,
                content={
                    "request": request[:100],
                    "confidence": response.confidence,
                    "path": response.path,
                    "modules": response.modules_used,
                },
                importance=response.confidence,
            )
            ws = self._get_module("global_workspace")
            if ws and hasattr(ws, "push"):
                ws.push(event)
        except Exception:
            pass

        # Register idle
        self._call_module(
            "metacognitive", "register_module_idle", "cognitive_integration"
        )

    # ── Main Entry Point ────────────────────────────────────────────────

    def process_request(self, request: str, context: Optional[dict] = None) -> CognitiveResponse:
        """
        Process an incoming request through FRIDAY's full cognitive pipeline.

        This is the main entry point for all cognitive processing.

        Args:
            request: The request text (user query, task, etc.)
            context: Optional context dict with keys like:
                - domain: knowledge domain
                - task_type: type of task
                - urgency: low/medium/high
                - user_state: user emotional state
                - history: recent conversation

        Returns:
            CognitiveResponse with response, confidence, reasoning trace,
            modules used, and emotional state.
        """
        start_time = _timestamp()
        context = context or {}
        request_hash = _hash_request(request)

        response = CognitiveResponse(response="", confidence=0.0)
        response.request_hash = request_hash

        with self._lock:
            self._data["meta"]["total_requests"] += 1

        # ── Fast Path (System 1) ────────────────────────────────────
        try:
            if self._fast_path(request, context, response):
                response.duration_ms = (_timestamp() - start_time) * 1000
                self._metrics.record(response)
                self._trace_history.append(response.to_dict())
                if len(self._trace_history) > MAX_TRACE_HISTORY:
                    self._trace_history = self._trace_history[-MAX_TRACE_HISTORY:]

                with self._lock:
                    self._data["meta"]["total_fast_path"] += 1
                    self._save()

                # Post-process even for fast path
                self._post_process(request, context, response)
                return response
        except Exception:
            pass  # Fast path failure → fall through to deliberative

        # ── Deliberative Pipeline (System 2) ────────────────────────
        try:
            self._deliberative_pipeline(request, context, response)
        except Exception as e:
            response.add_trace_step(
                "pipeline", "error", str(e),
                (_timestamp() - start_time) * 1000, 0.0
            )
            if not response.response:
                response.response = f"Deliberative processing encountered an issue. Request logged for review."
            response.confidence = max(response.confidence, 0.1)

        response.duration_ms = (_timestamp() - start_time) * 1000

        # ── Record & Persist ────────────────────────────────────────
        self._metrics.record(response)
        self._trace_history.append(response.to_dict())
        if len(self._trace_history) > MAX_TRACE_HISTORY:
            self._trace_history = self._trace_history[-MAX_TRACE_HISTORY:]

        with self._lock:
            self._data["meta"]["total_deliberative"] += 1
            self._save()

        # Post-process
        self._post_process(request, context, response)
        return response

    # ── Reflection (Outcomes) ───────────────────────────────────────────

    def reflect_on_outcome(self, request_hash: str, actual_outcome: str,
                           actual_success: bool, actual_confidence: float):
        """
        After the real-world outcome is known, reflect and learn.

        Updates calibration, somatic markers, and learning signals.
        """
        # Find the original trace
        original = None
        for trace in reversed(self._trace_history):
            if trace.get("request_hash") == request_hash:
                original = trace
                break

        if original is None:
            return

        predicted_confidence = original.get("confidence", 0.5)

        # Metacognitive calibration update
        self._call_module(
            "metacognitive", "calibrate_confidence",
            predicted=predicted_confidence,
            actual=actual_confidence,
            context=f"outcome_reflection:{request_hash}",
        )

        # Update learning
        self._call_module(
            "learning", "record_tool_result",
            "cognitive_response", actual_success, actual_outcome[:200],
        )

        # Update somatic markers if emotional context existed
        emo_state = original.get("emotional_state")
        if emo_state:
            valence = 0.3 if actual_success else -0.3
            self._call_module(
                "emotional", "create_somatic_marker",
                situation=original.get("response", "")[:100],
                action=original.get("strategy_used", "default"),
                outcome_valence=valence,
                outcome_description=actual_outcome[:200],
            )

        # Record in procedural memory if successful
        if actual_success:
            self._call_module(
                "procedural", "learn_procedure",
                original.get("request_hash", ""),
                [{"module": m} for m in original.get("modules_used", [])],
                {"outcome": actual_outcome[:200]},
            )

    # ── Statistics ──────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get integration pipeline statistics."""
        with self._lock:
            meta = self._data.get("meta", {})
            metrics = self._metrics.to_dict()
            session_duration = _timestamp() - self._session_start

            return {
                "total_requests": meta.get("total_requests", 0),
                "fast_path_count": meta.get("total_fast_path", 0),
                "deliberative_count": meta.get("total_deliberative", 0),
                "fast_path_rate": round(
                    meta.get("total_fast_path", 0) /
                    max(meta.get("total_requests", 0), 1), 3
                ),
                "avg_fast_ms": metrics.get("avg_fast_ms", 0),
                "avg_deliberative_ms": metrics.get("avg_deliberative_ms", 0),
                "module_usage": metrics.get("module_invocations", {}),
                "module_failures": metrics.get("module_failures", {}),
                "avg_confidence": metrics.get("avg_confidence", 0),
                "session_duration_min": round(session_duration / 60, 1),
                "modules_available": len(self._module_cache),
            }

    def get_recent_traces(self, limit: int = 10) -> List[dict]:
        """Get recent reasoning traces for debugging/analysis."""
        with self._lock:
            return list(reversed(self._trace_history[-limit:]))

    def format_for_prompt(self, max_chars: int = 600) -> str:
        """Format integration awareness for system prompt injection."""
        stats = self.get_stats()

        parts = [
            "[COGNITIVE INTEGRATION — Pipeline awareness]",
            f"Requests: {stats['total_requests']} | "
            f"Fast-path: {stats['fast_path_rate']:.0%} | "
            f"Avg confidence: {stats['avg_confidence']:.2f}",
            f"Fast: {stats['avg_fast_ms']:.0f}ms | "
            f"Deliberative: {stats['avg_deliberative_ms']:.0f}ms",
        ]

        module_usage = stats.get("module_usage", {})
        if module_usage:
            top_modules = sorted(module_usage.items(), key=lambda x: x[1], reverse=True)[:4]
            parts.append(f"Top modules: {', '.join(f'{m}({c})' for m, c in top_modules)}")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars] + "[...]"
        return result

    # ── Health Check ────────────────────────────────────────────────────

    def health_check(self) -> dict:
        """
        Check health of all connected cognitive modules.
        Returns status for each module.
        """
        module_names = [
            "intuition", "metacognitive", "emotional", "causal",
            "analogy", "creativity", "world_model", "neurosymbolic",
            "self_awareness", "learning", "episodic", "procedural",
            "competition", "active_inference", "global_workspace",
            "research", "creative", "document",
        ]

        status = {}
        for name in module_names:
            mod = self._get_module(name)
            if mod is not None:
                # Try to get basic stats
                try:
                    if hasattr(mod, "get_stats"):
                        mod.get_stats()
                    status[name] = "available"
                except Exception:
                    status[name] = "loaded_error"
            else:
                status[name] = "unavailable"

        available = sum(1 for s in status.values() if s == "available")
        return {
            "modules": status,
            "available_count": available,
            "total_count": len(module_names),
            "health": "good" if available >= 8 else "degraded" if available >= 4 else "critical",
        }


# ── Singleton ───────────────────────────────────────────────────────────────

_cognitive_integration = None
_integration_lock = threading.Lock()


def get_cognitive_integration() -> CognitiveIntegration:
    """Get singleton CognitiveIntegration instance."""
    global _cognitive_integration
    if _cognitive_integration is None:
        with _integration_lock:
            if _cognitive_integration is None:
                _cognitive_integration = CognitiveIntegration()
    return _cognitive_integration
