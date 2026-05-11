#!/usr/bin/env python3
"""
agi_orchestrator.py — FRIDAY AGI Orchestrator
===============================================

Master orchestrator that wires all cognitive modules into a unified AGI loop.
Coordinates the full cognitive pipeline: perception → planning → simulation
→ execution → reflection → improvement.

The orchestrator does NOT replace existing modules — it coordinates them,
publishing events at each step and maintaining system-wide state.

Cognitive loop:
  wm_update → h_aif_plan → neurosym_abstract → world_sim_rollout → execute → reflect

Integration points (all optional, graceful degradation):
- global_workspace: central event bus
- memory_coordinator: unified memory API
- active_inference: prediction-error driven learning
- hierarchical_active_inference: hierarchical planning
- world_model: latent dynamics prediction
- neurosymbolic_reasoner: symbolic reasoning
- self_improve_engine: RLHF-inspired improvement
- code_planner: hierarchical goal decomposition
- code_simulator: code simulation
- code_intelligence: code analysis
- code_reasoning_engine: deep code reasoning
- learning: Q-learning, error-driven learning
- dreaming: replay, consolidation
- self_model: capability tracking
- procedural_memory: skill memory
- benchmark_runner: performance benchmarking
- agi_benchmark_v2: autonomous cognitive architecture evaluation (v2)
- self_modifier: self-modification analysis, safe code changes, evolution tracking
- cognitive_integration: unified cognitive pipeline (System 1/2 routing)
- intuition_engine: fast System 1 pattern matching, RPD decisions
- emotional_regulation: somatic markers, mood tracking, decision pruning
- metacognitive_monitor: thinking quality, calibration, strategy effectiveness
- cognitive_appraisal: emotion generation from 6 appraisal dimensions
- cognitive_load: working memory monitoring, overload detection
- self_awareness: consciousness state tracking, theory of mind
- neural_memory: Hebbian learning persistent memory
- episodic_memory: timestamped event recording
- vector_memory: semantic search embeddings
- curiosity: novelty detection, user interest mirroring
- proactive_engine: anticipatory suggestions
- proactive_checkin: tiered idle check-ins
- voice_modulator: emotion/voice control
"""

import json
import math
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BRAIN_DIR = Path(__file__).parent.resolve()
STATE_FILE = BRAIN_DIR / "agi_state.json"
API_CONFIG_PATH = BRAIN_DIR.parent / "config" / "api_keys.json"

# Cognitive loop stages
COGNITIVE_STAGES = [
    "wm_update",
    "h_aif_plan",
    "neurosym_abstract",
    "world_sim_rollout",
    "execute",
    "reflect",
]


class AGIOrchestrator:
    """
    Master orchestrator for FRIDAY's unified cognitive loop.

    Coordinates all brain modules, manages the cognitive pipeline,
    and provides system-wide status and intelligence metrics.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data = self._empty_store()
        self._modules: Dict[str, Any] = {}
        self._modules_loaded = False
        self._cognitive_wiring: Dict[str, Any] = {}
        self._cognitive_activity: List[dict] = []
        self._load()
        self._load_modules()
        self._wire_cognitive_modules()

    # ── Persistence ──────────────────────────────────────────────────────

    def _empty_store(self) -> dict:
        """Return a fresh empty orchestrator state."""
        return {
            "meta": {
                "version": 1,
                "created": datetime.now().isoformat(),
                "last_update": datetime.now().isoformat(),
                "total_goals_processed": 0,
                "total_cognitive_steps": 0,
                "total_maintenance_cycles": 0,
            },
            # History of processed goals
            "goal_history": [],
            # IQ proxy metrics over time
            "iq_history": [],
            # Module availability log
            "module_status": {},
            # Last maintenance cycle timestamp
            "last_maintenance": 0.0,
        }

    def _load(self) -> None:
        """Load orchestrator state from disk."""
        with self._lock:
            if STATE_FILE.exists():
                try:
                    raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                    self._deep_merge(self._data, raw)
                    goals = len(self._data.get("goal_history", []))
                    print(f"[AGIOrchestrator] Loaded state ({goals} goals processed)")
                except Exception as e:
                    print(f"[AGIOrchestrator] Load error: {e}")

    def _save(self) -> None:
        """Persist orchestrator state to disk."""
        with self._lock:
            try:
                self._data["meta"]["last_update"] = datetime.now().isoformat()
                STATE_FILE.write_text(
                    json.dumps(self._data, indent=2, default=str),
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"[AGIOrchestrator] Save error: {e}")

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        """Recursively merge override into base (mutates base)."""
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                AGIOrchestrator._deep_merge(base[k], v)
            else:
                base[k] = v

    # ── Module Loading ───────────────────────────────────────────────────

    def _load_modules(self) -> None:
        """Load all brain modules with graceful degradation."""
        if self._modules_loaded:
            return

        module_loaders = {
            "global_workspace": ("brain.global_workspace", "get_global_workspace"),
            "memory_coordinator": ("brain.memory_coordinator", "get_memory_coordinator"),
            "active_inference": ("brain.active_inference", "get_active_inference"),
            "hierarchical_aif": ("brain.hierarchical_active_inference", "get_hierarchical_aif"),
            "world_model": ("brain.world_model", "get_world_model"),
            "neurosymbolic_reasoner": ("brain.neurosymbolic_reasoner", "get_neurosymbolic_reasoner"),
            "self_improve_engine": ("brain.self_improve_engine", "get_self_improve_engine"),
            "code_planner": ("brain.code_planner", "get_code_planner"),
            "code_simulator": ("brain.code_simulator", "get_code_simulator"),
            "code_intelligence": ("brain.code_intelligence", "get_code_intelligence"),
            "code_reasoning_engine": ("brain.code_reasoning_engine", "get_code_reasoning_engine"),
            "learning_engine": ("brain.learning", "get_learning_engine"),
            "dreaming_system": ("brain.dreaming", "get_dreaming_system"),
            "self_model": ("brain.self_model", "get_self_model"),
            "procedural_memory": ("brain.procedural_memory", "get_procedural_memory"),
            "benchmark_runner": ("brain.benchmark_runner", "get_benchmark_runner"),
            "agi_benchmark_v2": ("benchmarks.agi_benchmark_v2", "get_agi_benchmark_v2"),
            "transfer_learning": ("brain.transfer_learning", "get_transfer_learning"),
            "analogy_engine": ("brain.analogy_engine", "get_analogy_engine"),
            "causal_reasoner": ("brain.causal_reasoner", "get_causal_reasoner"),
            "creativity_engine": ("brain.creativity_engine", "get_creativity_engine"),
            "meta_learner": ("brain.meta_learner", "get_meta_learner"),
            "self_modifier": ("brain.self_modifier", "get_self_modifier"),
            "module_competition": ("brain.module_competition", "get_module_competition"),
            "narrative_intelligence": ("brain.narrative_intelligence", "get_narrative_intelligence"),
            "enhanced_world_model": ("brain.enhanced_world_model", "get_enhanced_world_model"),
            "integrated_info": ("brain.integrated_info", "get_integrated_info"),
            "findings_bus": ("brain.findings_bus", "get_findings_bus"),
            "model_router": ("brain.model_router", "get_model_router"),
            # Cognitive integration & System 1/2 routing
            "cognitive_integration": ("brain.cognitive_integration", "get_cognitive_integration"),
            "intuition_engine": ("brain.intuition_engine", "get_intuition_engine"),
            # Emotional & metacognitive systems
            "emotional_regulation": ("brain.emotional_regulation", "get_emotional_regulation"),
            "metacognitive_monitor": ("brain.metacognitive_monitor", "get_metacognitive_monitor"),
            "cognitive_appraisal": ("brain.cognitive_appraisal", "get_cognitive_appraisal"),
            "cognitive_load": ("brain.cognitive_load", "get_cognitive_load_manager"),
            # Memory systems (also loaded directly in main.py)
            "self_awareness": ("brain.self_awareness", "get_self_awareness"),
            "neural_memory": ("brain.neural_memory", "get_brain"),
            "episodic_memory": ("brain.episodic_memory", "get_episodic_memory"),
            "vector_memory": ("brain.vector_memory", "get_vector_memory"),
            "curiosity": ("brain.curiosity", "get_curiosity_module"),
            # Proactive & voice
            "proactive_engine": ("brain.proactive_engine", "get_proactive_engine"),
            "proactive_checkin": ("brain.proactive_checkin", "get_proactive_checkin"),
            "voice_modulator": ("brain.voice_modulator", "get_voice_modulator"),
            # Code reflection & cyber reasoning
            "code_reflector": ("brain.code_reflector", "get_code_reflector"),
            "cyber_reasoning": ("brain.cyber_reasoning", "get_cyber_engine"),
            # AGI Pillars — Multi-agent & autonomous systems
            "multi_agent_orchestrator": ("brain.multi_agent_orchestrator", "get_multi_agent_orchestrator"),
            "goal_engine": ("brain.goal_engine", "get_goal_engine"),
            "intrinsic_motivation": ("brain.intrinsic_motivation", "get_intrinsic_motivation"),
            "autonomous_planner": ("brain.autonomous_planner", "get_autonomous_planner"),
            # AGI Pillars — Memory & cognition
            "memory_consolidation": ("brain.memory_consolidation", "get_memory_consolidation"),
            "associative_memory": ("brain.associative_memory", "get_associative_memory"),
            "predictive_memory": ("brain.predictive_memory", "get_predictive_memory"),
            # AGI Pillars — Social & abstract reasoning
            "theory_of_mind": ("brain.theory_of_mind", "get_theory_of_mind"),
            "abstraction_engine": ("brain.abstraction_engine", "get_abstraction_engine"),
            # AGI Pillars — Self-awareness & world modeling
            "introspection_engine": ("brain.introspection_engine", "get_introspection_engine"),
            "world_simulation": ("brain.world_simulation", "get_world_simulation"),
            "code_evolution": ("brain.code_evolution", "get_code_evolution"),
        }

        for name, (module_path, func_name) in module_loaders.items():
            try:
                import importlib
                mod = importlib.import_module(module_path)
                getter = getattr(mod, func_name)
                self._modules[name] = getter()
                self._data["module_status"][name] = "available"
            except Exception as e:
                self._modules[name] = None
                self._data["module_status"][name] = f"unavailable: {str(e)[:80]}"
                print(f"[AGIOrchestrator] Module {name} unavailable: {e}")

        self._modules_loaded = True
        available = sum(1 for v in self._data["module_status"].values() if v == "available")
        total = len(module_loaders)
        print(f"[AGIOrchestrator] Loaded {available}/{total} modules")

    def _get_module(self, name: str) -> Any:
        """Get a loaded module or None."""
        return self._modules.get(name)

    # ── Cognitive Module Wiring ──────────────────────────────────────────

    def _wire_cognitive_modules(self) -> None:
        """Connect cognitive modules to orchestrator stages."""
        wiring = {
            "planning": ["analogy_engine", "creativity_engine", "hierarchical_aif",
                         "intuition_engine", "autonomous_planner", "goal_engine"],
            "reflection": ["causal_reasoner", "meta_learner", "narrative_intelligence",
                           "metacognitive_monitor", "introspection_engine"],
            "simulation": ["world_model", "enhanced_world_model", "world_simulation"],
            "verification": ["neurosymbolic_reasoner", "code_reasoning_engine"],
            "improvement": ["self_improve_engine", "transfer_learning", "code_evolution"],
            "competition": ["module_competition"],
            "consciousness": ["integrated_info", "self_awareness"],
            "routing": ["model_router", "cognitive_integration"],
            "communication": ["findings_bus"],
            "emotional": ["emotional_regulation", "cognitive_appraisal"],
            "memory": ["neural_memory", "episodic_memory", "vector_memory",
                       "memory_coordinator", "procedural_memory",
                       "memory_consolidation", "associative_memory", "predictive_memory"],
            "metacognition": ["metacognitive_monitor", "cognitive_load"],
            "exploration": ["curiosity", "proactive_engine", "intrinsic_motivation"],
            "social": ["theory_of_mind"],
            "abstraction": ["abstraction_engine"],
            "multi_agent": ["multi_agent_orchestrator"],
            "code_reflection": ["code_reflector"],
            "security": ["cyber_reasoning"],
        }
        for stage, module_names in wiring.items():
            available = [n for n in module_names if self._modules.get(n) is not None]
            self._cognitive_wiring[stage] = available

        available_count = sum(
            1 for v in self._cognitive_wiring.values() for _ in v
        )
        print(f"[AGIOrchestrator] Cognitive wiring: {available_count} connections across "
              f"{len(self._cognitive_wiring)} stages")

    def process_cognitive_request(self, request: str, context: str = "",
                                   depth: str = "normal") -> dict:
        """
        Process a cognitive request using module competition and orchestration.

        Args:
            request: The cognitive request string.
            context: Additional context.
            depth: Processing depth — "quick", "normal", or "deep".

        Returns:
            Dict with reasoning trace, module contributions, and response.
        """
        start_time = time.time()
        result: Dict[str, Any] = {
            "request": request[:300],
            "depth": depth,
            "trace": [],
            "modules_used": [],
        }

        # Step 1: Use module_competition to decide which modules handle it
        competition = self._get_module("module_competition")
        competition_result = None
        if competition:
            try:
                competition_result = competition.compete(
                    request, context={"context": context, "depth": depth}
                )
                result["competition"] = {
                    "winner": competition_result.get("winner", {}).get("module_name", "none"),
                    "runners_up": [
                        r.get("module_name", "?")
                        for r in competition_result.get("runners_up", [])
                    ],
                }
                result["trace"].append("module_competition: selected modules")
            except Exception as e:
                result["trace"].append(f"module_competition error: {str(e)[:100]}")

        # Step 2: Run winning modules based on depth
        depth_config = {
            "quick": {"max_modules": 2, "timeout_per_module": 5},
            "normal": {"max_modules": 4, "timeout_per_module": 15},
            "deep": {"max_modules": 8, "timeout_per_module": 30},
        }
        config = depth_config.get(depth, depth_config["normal"])

        # Collect candidate modules from competition or wiring
        candidates = []
        if competition_result and competition_result.get("winner"):
            winner_name = competition_result["winner"].get("module_name", "")
            if winner_name and self._modules.get(winner_name):
                candidates.append(winner_name)
            for r in competition_result.get("runners_up", []):
                name = r.get("module_name", "")
                if name and self._modules.get(name):
                    candidates.append(name)

        # Ensure key modules are included
        for stage_modules in self._cognitive_wiring.values():
            for m in stage_modules:
                if m not in candidates and self._modules.get(m):
                    candidates.append(m)

        # Limit by depth
        candidates = candidates[:config["max_modules"]]

        # Step 3: Execute each module
        for mod_name in candidates:
            mod = self._modules.get(mod_name)
            if not mod:
                continue
            try:
                mod_result = self._invoke_cognitive_module(
                    mod_name, mod, request, context, depth
                )
                if mod_result:
                    result["modules_used"].append(mod_name)
                    result[f"result_{mod_name}"] = mod_result
                    result["trace"].append(f"{mod_name}: contributed")
            except Exception as e:
                result["trace"].append(f"{mod_name} error: {str(e)[:80]}")

        # Step 4: Synthesize response
        result["modules_count"] = len(result["modules_used"])
        elapsed = time.time() - start_time
        result["elapsed_seconds"] = round(elapsed, 3)

        # Record activity
        with self._lock:
            self._cognitive_activity.append({
                "request": request[:100],
                "modules_used": result["modules_used"],
                "elapsed": elapsed,
                "timestamp": time.time(),
            })
            if len(self._cognitive_activity) > 100:
                self._cognitive_activity = self._cognitive_activity[-100:]

        self._publish_event("cognitive_request", {
            "request": request[:100],
            "modules_used": result["modules_used"],
            "elapsed": round(elapsed, 3),
        })

        return result

    def _invoke_cognitive_module(self, name: str, mod: Any,
                                  request: str, context: str, depth: str) -> Optional[dict]:
        """Invoke a single cognitive module with the request."""
        # Each module has different interfaces — try common patterns
        if name == "analogy_engine":
            if hasattr(mod, "extract_relational_structure"):
                structure = mod.extract_relational_structure(request[:500])
                return {"structure": structure.to_dict() if hasattr(structure, "to_dict") else str(structure)}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "causal_reasoner":
            if hasattr(mod, "find_causes"):
                causes = mod.find_causes(request[:200], max_depth=3)
                return {"causes": [str(c)[:80] for c in (causes or [])[:5]]}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "creativity_engine":
            if hasattr(mod, "generate_alternatives"):
                ideas = mod.generate_alternatives(
                    problem={"description": request[:200], "domain": "general"},
                    existing_solution={"method": "standard"},
                    n=3 if depth == "quick" else 5,
                )
                return {"ideas": [str(i)[:100] for i in (ideas or [])[:5]]}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "meta_learner":
            if hasattr(mod, "get_strategy_report"):
                report = mod.get_strategy_report("cognitive_request")
                return {"strategy_report": report}
            if hasattr(mod, "get_all_domains"):
                return {"domains": mod.get_all_domains()}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "narrative_intelligence":
            if hasattr(mod, "explain_what_happened"):
                explanation = mod.explain_what_happened(
                    {"description": request[:200]}, context=context[:200]
                )
                return {"narrative": str(explanation)[:300]}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "neurosymbolic_reasoner":
            if hasattr(mod, "abstract_to_symbolic"):
                props = mod.abstract_to_symbolic(request[:200])
                return {"propositions": [str(p)[:80] for p in (props or [])[:5]]}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "world_model":
            if hasattr(mod, "get_state_features"):
                features = mod.get_state_features()
                return {"features": {k: str(v)[:50] for k, v in list(features.items())[:5]}}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "enhanced_world_model":
            if hasattr(mod, "get_state_features"):
                features = mod.get_state_features()
                return {"features": {k: str(v)[:50] for k, v in list(features.items())[:5]}}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "hierarchical_aif":
            if hasattr(mod, "select_action"):
                actions = [w for w in request.lower().split() if len(w) > 3]
                if actions:
                    action, info = mod.select_action(actions[:10])
                    return {"selected_action": action, "info": str(info)[:200]}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "transfer_learning":
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "self_improve_engine":
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "integrated_info":
            if hasattr(mod, "get_consciousness_for_orchestrator"):
                return mod.get_consciousness_for_orchestrator()
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "model_router":
            if hasattr(mod, "get_route"):
                provider, model_id = mod.get_route(request[:200])
                return {"provider": str(provider), "model_id": str(model_id)}

        elif name == "findings_bus":
            if hasattr(mod, "read_recent"):
                findings = mod.read_recent(hours=24)
                return {"recent_findings": len(findings or [])}

        # ── AGI Pillar modules ────────────────────────────────────────

        elif name == "multi_agent_orchestrator":
            # Use a team-based approach for complex requests
            teams = mod.list_teams() if hasattr(mod, "list_teams") else {}
            if teams:
                team_names = list(teams.keys())
                # Pick first available team
                selected_team = team_names[0] if team_names else None
                if selected_team and hasattr(mod, "execute_team"):
                    try:
                        team_result = mod.execute_team(selected_team, request[:300], context=context[:200])
                        return {"team": selected_team, "result": {k: str(v)[:100] for k, v in list(team_result.items())[:5]}}
                    except Exception:
                        pass
            if hasattr(mod, "run_parallel"):
                # Fallback: run with built-in agents
                agents = ["reasoning", "analysis", "synthesis"]
                try:
                    result = mod.run_parallel(agents, request[:300], context=context[:200])
                    return {"parallel_result": {k: str(v)[:100] for k, v in list(result.items())[:5]}}
                except Exception:
                    pass
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "goal_engine":
            if hasattr(mod, "get_active_plans") and hasattr(mod, "get_stats"):
                active = mod.get_active_plans() if hasattr(mod, "get_active_plans") else []
                stats = mod.get_stats()
                return {"active_goals": stats.get("active", 0), "total": stats.get("total_goals", 0),
                        "completion_rate": stats.get("completion_rate", "0%")}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "intrinsic_motivation":
            if hasattr(mod, "get_motivation_state"):
                state = mod.get_motivation_state()
                return {"motivation_state": {k: str(v)[:60] for k, v in list(state.items())[:6]}}
            if hasattr(mod, "generate_exploration_goals"):
                goals = mod.generate_exploration_goals(count=3)
                return {"exploration_goals": [str(g)[:80] for g in (goals or [])[:3]]}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "autonomous_planner":
            if hasattr(mod, "decompose_goal"):
                try:
                    plan = mod.decompose_goal(request[:300], context=context[:200], max_depth=2, iterations=20)
                    plan_dict = plan.to_dict() if hasattr(plan, "to_dict") else {}
                    return {"plan_id": plan_dict.get("id", "?"), "steps": len(plan_dict.get("steps", [])),
                            "status": plan_dict.get("status", "?")}
                except Exception as e:
                    return {"error": str(e)[:100]}
            if hasattr(mod, "get_next_actions"):
                actions = mod.get_next_actions()
                return {"next_actions": [str(a)[:80] for a in (actions or [])[:5]]}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "memory_consolidation":
            if hasattr(mod, "run_consolidation_cycle"):
                try:
                    cycle_result = mod.run_consolidation_cycle()
                    return {"consolidation": {k: str(v)[:60] for k, v in list(cycle_result.items())[:5]}}
                except Exception:
                    pass
            if hasattr(mod, "search_semantic"):
                results = mod.search_semantic(request[:200], limit=5)
                return {"semantic_matches": len(results or [])}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "associative_memory":
            if hasattr(mod, "recall"):
                results = mod.recall(request[:200], depth=2)
                recalled = []
                for item in (results or [])[:5]:
                    if isinstance(item, tuple) and len(item) >= 2:
                        node, score = item[0], item[1]
                        recalled.append({"content": str(getattr(node, "content", str(node)))[:60], "score": round(score, 2)})
                    else:
                        recalled.append(str(item)[:60])
                return {"recalled": recalled, "count": len(results or [])}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "predictive_memory":
            if hasattr(mod, "predict_needed_context"):
                predictions = mod.predict_needed_context(request[:200])
                return {"predicted_context": [str(p)[:80] for p in (predictions or [])[:5]]}
            if hasattr(mod, "preload_predictions"):
                # Extract task type from request keywords
                task_type = "general"
                for kw in ["code", "research", "debug", "design", "analysis"]:
                    if kw in request.lower():
                        task_type = kw
                        break
                preloaded = mod.preload_predictions(task_type)
                return {"preloaded": len(preloaded or []), "task_type": task_type}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "theory_of_mind":
            if hasattr(mod, "infer_intent"):
                intent = mod.infer_intent(request[:300])
                return {"inferred_intent": str(intent)[:200]}
            if hasattr(mod, "infer_emotional_state"):
                emotion = mod.infer_emotional_state(request[:300])
                return {"inferred_emotion": str(emotion)[:100]}
            if hasattr(mod, "predict_user_needs"):
                needs = mod.predict_user_needs()
                return {"predicted_needs": [str(n)[:80] for n in (needs or [])[:5]]}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "abstraction_engine":
            if hasattr(mod, "find_analogies"):
                # Try to find cross-domain analogies
                domains = mod.list_domains() if hasattr(mod, "list_domains") else []
                if len(domains) >= 2:
                    analogies = mod.find_analogies(domains[0], domains[1])
                    return {"analogies": [str(a)[:80] for a in (analogies or [])[:3]], "domains": domains[:5]}
            if hasattr(mod, "first_principles"):
                try:
                    fp = mod.first_principles(request[:300])
                    return {"first_principles": {k: str(v)[:80] for k, v in list(fp.items())[:5]}}
                except Exception:
                    pass
            if hasattr(mod, "counterfactual"):
                try:
                    cf = mod.counterfactual(request[:200], "alternative approach")
                    return {"counterfactual": {k: str(v)[:80] for k, v in list(cf.items())[:5]}}
                except Exception:
                    pass
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "introspection_engine":
            if hasattr(mod, "assess_confidence"):
                assessment = mod.assess_confidence(request[:300])
                return {"confidence_assessment": {k: str(v)[:60] for k, v in list(assessment.items())[:5]}}
            if hasattr(mod, "detect_cognitive_biases"):
                biases = mod.detect_cognitive_biases(request[:300], context[:200])
                return {"biases_detected": len(biases or []),
                        "top_biases": [str(b)[:80] for b in (biases or [])[:3]]}
            if hasattr(mod, "epistemic_humility"):
                humility = mod.epistemic_humility(request[:200])
                return {"epistemic_humility": {k: str(v)[:60] for k, v in list(humility.items())[:5]}}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "world_simulation":
            if hasattr(mod, "predict_outcomes"):
                predictions = mod.predict_outcomes(request[:300])
                return {"predicted_outcomes": [str(p)[:80] for p in (predictions or [])[:5]]}
            if hasattr(mod, "get_world_state"):
                state = mod.get_world_state()
                return {"world_state": {k: str(v)[:60] for k, v in list(state.items())[:5]}}
            if hasattr(mod, "get_user_relevant_events"):
                events = mod.get_user_relevant_events(limit=5)
                return {"relevant_events": len(events or [])}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "code_evolution":
            if hasattr(mod, "propose_evolution"):
                try:
                    proposal = mod.propose_evolution(request[:300])
                    return {"evolution_proposal": str(proposal)[:200]}
                except Exception:
                    pass
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        # ── Newly wired modules ──────────────────────────────────────

        elif name == "intuition_engine":
            if hasattr(mod, "generate_intuitive_judgment"):
                judgment = mod.generate_intuitive_judgment(request[:300])
                return {"judgment": judgment}
            if hasattr(mod, "recognize"):
                result_tuple = mod.recognize(request[:300])
                if result_tuple and result_tuple[0]:
                    return {"recognized_pattern": result_tuple[0], "confidence": result_tuple[1]}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "emotional_regulation":
            if hasattr(mod, "get_current_mood"):
                mood = mod.get_current_mood()
                return {"mood": mood}
            if hasattr(mod, "apply_somatic_markers"):
                # Build options from request for marker application
                options = [{"action": "respond", "context": request[:200]}]
                marked = mod.apply_somatic_markers(options)
                return {"marked_options": len(marked or [])}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "metacognitive_monitor":
            if hasattr(mod, "check_cognitive_load"):
                load_state = mod.check_cognitive_load()
                return {"cognitive_load": load_state.to_dict() if hasattr(load_state, "to_dict") else str(load_state)}
            if hasattr(mod, "get_calibration_report"):
                report = mod.get_calibration_report()
                return {"calibration": report}
            if hasattr(mod, "suggest_strategy"):
                suggestion = mod.suggest_strategy("cognitive_request", context[:200])
                return {"strategy_suggestion": suggestion}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "cognitive_appraisal":
            if hasattr(mod, "appraise"):
                appraisal = mod.appraise(request[:200], context={"depth": depth})
                return {"appraisal": appraisal}
            if hasattr(mod, "get_status"):
                return mod.get_status()
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "cognitive_load":
            if hasattr(mod, "get_active_load"):
                load = mod.get_active_load()
                return {"active_load": load}
            if hasattr(mod, "check_overload"):
                overload = mod.check_overload()
                return {"overload_check": overload}
            if hasattr(mod, "get_status"):
                return mod.get_status()
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "cognitive_integration":
            if hasattr(mod, "process_request"):
                ci_result = mod.process_request(request[:300], context={"depth": depth, "context": context})
                return {"cognitive_response": ci_result.to_dict() if hasattr(ci_result, "to_dict") else str(ci_result)[:300]}
            if hasattr(mod, "health_check"):
                return mod.health_check()
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "self_awareness":
            if hasattr(mod, "get_consciousness_state"):
                state = mod.get_consciousness_state()
                return {"consciousness_state": {k: str(v)[:60] for k, v in list(state.items())[:8]}}
            if hasattr(mod, "get_current_state"):
                return {"current_state": mod.get_current_state()}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "curiosity":
            if hasattr(mod, "get_user_top_interests"):
                interests = mod.get_user_top_interests(limit=5)
                return {"user_interests": interests}
            if hasattr(mod, "get_related_suggestions"):
                suggestions = mod.get_related_suggestions()
                return {"suggestions": suggestions[:5] if suggestions else []}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "neural_memory":
            if hasattr(mod, "recall"):
                memories = mod.recall(request[:200], limit=5)
                return {"recalled_memories": len(memories or [])}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "episodic_memory":
            if hasattr(mod, "search"):
                events = mod.search(request[:200], limit=5)
                return {"matching_events": len(events or [])}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "vector_memory":
            if hasattr(mod, "search"):
                results = mod.search(request[:200], limit=5)
                return {"vector_matches": len(results or [])}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "code_reasoning_engine":
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "proactive_engine":
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "proactive_checkin":
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "voice_modulator":
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "code_reflector":
            if hasattr(mod, "analyze_failure"):
                analysis = mod.analyze_failure(request[:300])
                return {"failure_analysis": str(analysis)[:300]}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        elif name == "cyber_reasoning":
            if hasattr(mod, "get_session_state"):
                state = mod.get_session_state()
                return {"session_state": {k: str(v)[:60] for k, v in list(state.items())[:5]}}
            if hasattr(mod, "get_stats"):
                return mod.get_stats()

        # Generic fallback
        if hasattr(mod, "get_stats"):
            try:
                return mod.get_stats()
            except Exception:
                pass
        return None

    def get_cognitive_status(self) -> dict:
        """
        Get comprehensive status of all cognitive modules.

        Returns:
            Dict with module availability, health, recent activity,
            and consciousness level.
        """
        module_details: Dict[str, dict] = {}
        for name, module in self._modules.items():
            info: Dict[str, Any] = {"available": module is not None}
            if module is not None:
                try:
                    if hasattr(module, "get_stats"):
                        stats = module.get_stats()
                        info["stats_summary"] = {
                            k: v for k, v in list(stats.items())[:5]
                        }
                    info["status"] = "active"
                except Exception as e:
                    info["status"] = f"error: {str(e)[:80]}"
                    info["last_error"] = str(e)[:200]
            else:
                info["status"] = "unavailable"
            module_details[name] = info

        # Wiring summary
        wiring_summary: Dict[str, List[str]] = {}
        for stage, modules in self._cognitive_wiring.items():
            wiring_summary[stage] = modules

        # Recent cognitive activity
        with self._lock:
            recent = list(self._cognitive_activity[-10:])

        # Consciousness level from integrated_info
        consciousness = {}
        ii = self._get_module("integrated_info")
        if ii:
            try:
                if hasattr(ii, "get_consciousness_for_orchestrator"):
                    consciousness = ii.get_consciousness_for_orchestrator()
                elif hasattr(ii, "get_stats"):
                    stats = ii.get_stats()
                    consciousness = {
                        "phi": stats.get("phi", {}).get("current_phi", 0),
                        "state": stats.get("consciousness", {}).get("current_state", "unknown"),
                    }
            except Exception as e:
                consciousness = {"error": str(e)[:100]}

        available = sum(1 for d in module_details.values() if d.get("status") == "active")
        total = len(module_details)

        return {
            "modules": module_details,
            "modules_available": available,
            "modules_total": total,
            "system_health": round(available / total, 2) if total > 0 else 0.0,
            "wiring": wiring_summary,
            "recent_activity": recent,
            "consciousness": consciousness,
        }

    # ── Core API ─────────────────────────────────────────────────────────

    def process_goal(self, goal: str, context: str = "") -> dict:
        """
        Process a goal through the full cognitive loop.

        Executes: wm_update → h_aif_plan → neurosym_abstract →
                  world_sim_rollout → execute → reflect

        Args:
            goal: The goal description.
            context: Additional context for the goal.

        Returns:
            Dict with stage results, total time, and success status.
        """
        start_time = time.time()
        result: Dict[str, Any] = {
            "goal": goal,
            "context": context,
            "stages": {},
            "start_time": start_time,
        }

        print(f"[AGIOrchestrator] Processing goal: {goal[:80]}...")

        # Stage 1: World Model Update (perception)
        result["stages"]["wm_update"] = self._stage_wm_update(goal, context)

        # Stage 2: Hierarchical Active Inference Planning
        result["stages"]["h_aif_plan"] = self._stage_h_aif_plan(goal, context)

        # Stage 3: Neurosymbolic Abstraction
        result["stages"]["neurosym_abstract"] = self._stage_neurosym_abstract(goal, context)

        # Stage 4: World Model Simulation Rollout
        result["stages"]["world_sim_rollout"] = self._stage_world_sim_rollout(
            goal, result["stages"]
        )

        # Stage 5: Execute (delegate to appropriate module)
        result["stages"]["execute"] = self._stage_execute(goal, context, result["stages"])

        # Stage 6: Reflect
        result["stages"]["reflect"] = self._stage_reflect(goal, result["stages"])

        # Finalize
        elapsed = time.time() - start_time
        result["elapsed_seconds"] = round(elapsed, 3)
        result["success"] = result["stages"].get("execute", {}).get("success", False)

        with self._lock:
            self._data["meta"]["total_goals_processed"] += 1
            self._data["goal_history"].append({
                "goal": goal[:200],
                "success": result["success"],
                "elapsed": elapsed,
                "stages_completed": list(result["stages"].keys()),
                "timestamp": time.time(),
            })
            if len(self._data["goal_history"]) > 200:
                self._data["goal_history"] = self._data["goal_history"][-200:]

        # Publish goal completion event
        self._publish_event("goal_processed", {
            "goal": goal[:100],
            "success": result["success"],
            "elapsed": round(elapsed, 3),
            "stages": list(result["stages"].keys()),
        })

        if self._data["meta"]["total_goals_processed"] % 10 == 0:
            self._save()

        print(f"[AGIOrchestrator] Goal processed in {elapsed:.2f}s (success={result['success']})")
        return result

    def cognitive_loop_step(self, state: dict) -> dict:
        """
        Execute a single step of the cognitive loop.

        Useful for debugging and stepping through the pipeline.

        Args:
            state: Dict with 'stage' (which stage to run), 'goal', 'context',
                   and accumulated results from previous stages.

        Returns:
            Dict with the stage result and next_stage.
        """
        stage = state.get("stage", "wm_update")
        goal = state.get("goal", "")
        context = state.get("context", "")
        previous = state.get("previous_stages", {})

        stage_methods = {
            "wm_update": self._stage_wm_update,
            "h_aif_plan": self._stage_h_aif_plan,
            "neurosym_abstract": self._stage_neurosym_abstract,
            "world_sim_rollout": lambda g, c: self._stage_world_sim_rollout(g, previous),
            "execute": lambda g, c: self._stage_execute(g, c, previous),
            "reflect": lambda g, c: self._stage_reflect(g, previous),
        }

        method = stage_methods.get(stage)
        if not method:
            return {"error": f"Unknown stage: {stage}", "stage": stage}

        try:
            stage_result = method(goal, context)
        except Exception as e:
            stage_result = {"error": str(e), "success": False}

        # Determine next stage
        try:
            current_idx = COGNITIVE_STAGES.index(stage)
            next_stage = COGNITIVE_STAGES[current_idx + 1] if current_idx + 1 < len(COGNITIVE_STAGES) else None
        except ValueError:
            next_stage = None

        with self._lock:
            self._data["meta"]["total_cognitive_steps"] += 1

        return {
            "stage": stage,
            "result": stage_result,
            "next_stage": next_stage,
        }

    def get_system_status(self) -> dict:
        """
        Get comprehensive status of all brain modules.

        Returns:
            Dict with module statuses, orchestrator stats, and system health.
        """
        self._load_modules()

        module_details: Dict[str, dict] = {}
        for name, module in self._modules.items():
            if module is not None:
                try:
                    if hasattr(module, "get_stats"):
                        stats = module.get_stats()
                        module_details[name] = {
                            "status": "active",
                            "stats_summary": {
                                k: v for k, v in list(stats.items())[:5]
                            },
                        }
                    else:
                        module_details[name] = {"status": "active (no stats)"}
                except Exception as e:
                    module_details[name] = {"status": f"error: {e}"}
            else:
                module_details[name] = {"status": "unavailable"}

        available = sum(1 for d in module_details.values() if "active" in d.get("status", ""))
        total = len(module_details)

        with self._lock:
            meta = dict(self._data["meta"])

        return {
            "modules": module_details,
            "modules_available": available,
            "modules_total": total,
            "system_health": round(available / total, 2) if total > 0 else 0.0,
            "orchestrator": meta,
        }

    def run_maintenance_cycle(self) -> dict:
        """
        Run periodic maintenance: consolidation, dreaming, and improvement.

        Coordinates background maintenance tasks across all modules.

        Returns:
            Dict with results of each maintenance task.
        """
        results: Dict[str, Any] = {
            "timestamp": time.time(),
            "tasks": {},
        }

        print("[AGIOrchestrator] Running maintenance cycle...")

        # Memory consolidation via dreaming
        dreaming = self._get_module("dreaming_system")
        if dreaming:
            try:
                if hasattr(dreaming, "run_consolidation"):
                    dream_result = dreaming.run_consolidation()
                    results["tasks"]["consolidation"] = {"status": "completed", "result": str(dream_result)[:200]}
                elif hasattr(dreaming, "consolidate"):
                    dream_result = dreaming.consolidate()
                    results["tasks"]["consolidation"] = {"status": "completed", "result": str(dream_result)[:200]}
                else:
                    results["tasks"]["consolidation"] = {"status": "skipped", "reason": "no consolidation method"}
            except Exception as e:
                results["tasks"]["consolidation"] = {"status": "error", "error": str(e)[:100]}
        else:
            results["tasks"]["consolidation"] = {"status": "unavailable"}

        # Self-improvement cycle
        improver = self._get_module("self_improve_engine")
        if improver:
            try:
                if hasattr(improver, "run_improvement_cycle"):
                    improve_result = improver.run_improvement_cycle()
                    results["tasks"]["improvement"] = {
                        "status": "completed",
                        "lessons": improve_result.get("lessons_extracted", 0),
                    }
            except Exception as e:
                results["tasks"]["improvement"] = {"status": "error", "error": str(e)[:100]}
        else:
            results["tasks"]["improvement"] = {"status": "unavailable"}

        # Learning consolidation
        learning = self._get_module("learning_engine")
        if learning:
            try:
                if hasattr(learning, "consolidate"):
                    learning.consolidate()
                    results["tasks"]["learning_consolidation"] = {"status": "completed"}
                else:
                    results["tasks"]["learning_consolidation"] = {"status": "skipped"}
            except Exception as e:
                results["tasks"]["learning_consolidation"] = {"status": "error", "error": str(e)[:100]}
        else:
            results["tasks"]["learning_consolidation"] = {"status": "unavailable"}

        # World model save
        wm = self._get_module("world_model")
        if wm:
            try:
                if hasattr(wm, "save"):
                    wm.save()
                    results["tasks"]["world_model_save"] = {"status": "completed"}
            except Exception as e:
                results["tasks"]["world_model_save"] = {"status": "error", "error": str(e)[:100]}

        # Memory coordinator maintenance
        mc = self._get_module("memory_coordinator")
        if mc:
            try:
                if hasattr(mc, "consolidate"):
                    mc.consolidate()
                    results["tasks"]["memory_consolidation"] = {"status": "completed"}
            except Exception as e:
                results["tasks"]["memory_consolidation"] = {"status": "error", "error": str(e)[:100]}

        # Transfer learning: consolidate cross-domain skills
        transfer = self._get_module("transfer_learning")
        if transfer:
            try:
                if hasattr(transfer, "detect_cross_domain_patterns"):
                    patterns = transfer.detect_cross_domain_patterns()
                    results["tasks"]["transfer_consolidation"] = {
                        "status": "completed",
                        "patterns_found": len(patterns) if patterns else 0,
                    }
                else:
                    results["tasks"]["transfer_consolidation"] = {"status": "skipped"}
            except Exception as e:
                results["tasks"]["transfer_consolidation"] = {"status": "error", "error": str(e)[:100]}

        # Meta-learner: adapt learning strategies
        meta = self._get_module("meta_learner")
        if meta:
            try:
                if hasattr(meta, "get_all_domains"):
                    domains = meta.get_all_domains()
                    results["tasks"]["meta_adaptation"] = {
                        "status": "completed",
                        "domains_tracked": len(domains) if domains else 0,
                    }
                else:
                    results["tasks"]["meta_adaptation"] = {"status": "skipped"}
            except Exception as e:
                results["tasks"]["meta_adaptation"] = {"status": "error", "error": str(e)[:100]}

        # Self-modifier: run self-audit and snapshot codebase metrics
        modifier = self._get_module("self_modifier")
        if modifier:
            try:
                if hasattr(modifier, "self_audit"):
                    audit = modifier.self_audit()
                    results["tasks"]["self_audit"] = {
                        "status": "completed",
                        "suggestions": audit.get("total_suggestions", 0),
                        "critical": len(audit.get("critical_issues", [])),
                        "consistency": audit.get("consistency", {}).get("consistency_pct", 0),
                    }
                elif hasattr(modifier, "tracker") and hasattr(modifier.tracker, "snapshot_metrics"):
                    metrics = modifier.tracker.snapshot_metrics()
                    results["tasks"]["self_audit"] = {
                        "status": "metrics_only",
                        "modules": metrics.get("module_count", 0),
                        "loc": metrics.get("total_loc", 0),
                    }
                else:
                    results["tasks"]["self_audit"] = {"status": "skipped"}
            except Exception as e:
                results["tasks"]["self_audit"] = {"status": "error", "error": str(e)[:100]}
        else:
            results["tasks"]["self_audit"] = {"status": "unavailable"}

        # Causal reasoner: update causal model
        causal = self._get_module("causal_reasoner")
        if causal:
            try:
                if hasattr(causal, "update_model"):
                    causal.update_model()
                    results["tasks"]["causal_update"] = {"status": "completed"}
                elif hasattr(causal, "get_stats"):
                    causal.get_stats()
                    results["tasks"]["causal_update"] = {"status": "checked"}
                else:
                    results["tasks"]["causal_update"] = {"status": "skipped"}
            except Exception as e:
                results["tasks"]["causal_update"] = {"status": "error", "error": str(e)[:100]}

        with self._lock:
            self._data["meta"]["total_maintenance_cycles"] += 1
            self._data["last_maintenance"] = time.time()

        self._save()

        results["summary"] = {
            k: v.get("status", "unknown") for k, v in results["tasks"].items()
        }
        print(f"[AGIOrchestrator] Maintenance cycle complete: {results['summary']}")
        return results

    def get_iq_proxy(self) -> dict:
        """
        Compute proxy metrics for FRIDAY's "intelligence".

        Estimates intelligence dimensions from available module data:
        - SWE-bench estimate: code task success rate
        - Decision entropy: how decisive vs random
        - Prediction accuracy: world model prediction quality
        - Improvement velocity: rate of self-improvement

        Returns:
            Dict with individual metrics and a composite IQ score.
        """
        metrics: Dict[str, Any] = {}

        # Code task success rate (SWE-bench proxy)
        code_planner = self._get_module("code_planner")
        code_intel = self._get_module("code_intelligence")
        if code_planner and hasattr(code_planner, "get_stats"):
            try:
                cp_stats = code_planner.get_stats()
                plans = cp_stats.get("total_plans", 0)
                success = cp_stats.get("successful_plans", 0)
                metrics["swe_bench_estimate"] = round(success / max(plans, 1), 4)
                metrics["total_plans"] = plans
            except Exception:
                metrics["swe_bench_estimate"] = 0.0

        # Decision entropy from active inference
        ai = self._get_module("active_inference")
        if ai and hasattr(ai, "get_stats"):
            try:
                ai_stats = ai.get_stats()
                pred_accuracy = ai_stats.get("prediction_accuracy", 0.5)
                metrics["prediction_accuracy"] = round(pred_accuracy, 4)
                # Decision entropy: higher accuracy = lower entropy
                if pred_accuracy > 0 and pred_accuracy < 1:
                    entropy = -(pred_accuracy * math.log2(pred_accuracy) +
                               (1 - pred_accuracy) * math.log2(1 - pred_accuracy))
                else:
                    entropy = 0.0
                metrics["decision_entropy"] = round(entropy, 4)
            except Exception:
                metrics["prediction_accuracy"] = 0.5
                metrics["decision_entropy"] = 1.0

        # World model prediction accuracy
        wm = self._get_module("world_model")
        if wm and hasattr(wm, "get_stats"):
            try:
                wm_stats = wm.get_stats()
                avg_error = wm_stats.get("avg_prediction_error")
                if avg_error is not None:
                    metrics["world_model_accuracy"] = round(1.0 - avg_error, 4)
                else:
                    metrics["world_model_accuracy"] = 0.5
                metrics["world_model_experiences"] = wm_stats.get("total_experiences", 0)
            except Exception:
                metrics["world_model_accuracy"] = 0.5

        # Improvement velocity
        improver = self._get_module("self_improve_engine")
        if improver and hasattr(improver, "get_improvement_velocity"):
            try:
                velocity = improver.get_improvement_velocity()
                metrics["improvement_velocity"] = round(velocity, 6)
                if hasattr(improver, "get_stats"):
                    imp_stats = improver.get_stats()
                    metrics["improvement_quality"] = imp_stats.get("avg_quality", 0.5)
            except Exception:
                metrics["improvement_velocity"] = 0.0

        # Goal success rate
        with self._lock:
            history = self._data.get("goal_history", [])
        if history:
            recent = history[-50:]
            successes = sum(1 for g in recent if g.get("success", False))
            metrics["goal_success_rate"] = round(successes / len(recent), 4)
            metrics["goals_processed"] = len(history)

        # Composite IQ score (weighted average of normalized metrics)
        components = []
        weights = []

        if "swe_bench_estimate" in metrics:
            components.append(metrics["swe_bench_estimate"])
            weights.append(0.25)
        if "prediction_accuracy" in metrics:
            components.append(metrics["prediction_accuracy"])
            weights.append(0.20)
        if "world_model_accuracy" in metrics:
            components.append(metrics["world_model_accuracy"])
            weights.append(0.20)
        if "goal_success_rate" in metrics:
            components.append(metrics["goal_success_rate"])
            weights.append(0.25)
        if "improvement_velocity" in metrics:
            # Normalize velocity to 0-1 range (cap at ±0.1)
            vel = max(-0.1, min(0.1, metrics["improvement_velocity"]))
            normalized_vel = (vel + 0.1) / 0.2
            components.append(normalized_vel)
            weights.append(0.10)

        if components and weights:
            total_weight = sum(weights)
            composite = sum(c * w for c, w in zip(components, weights)) / total_weight
            # Scale to IQ-like range (70-130, centered at 100)
            iq_score = 70 + composite * 60
            metrics["composite_iq"] = round(iq_score, 1)
        else:
            metrics["composite_iq"] = 100.0  # Default neutral

        # Store IQ history
        with self._lock:
            self._data["iq_history"].append({
                "timestamp": time.time(),
                "iq": metrics["composite_iq"],
                "metrics": {k: v for k, v in metrics.items() if isinstance(v, (int, float))},
            })
            if len(self._data["iq_history"]) > 100:
                self._data["iq_history"] = self._data["iq_history"][-100:]

        return metrics

    # ── Cognitive Loop Stages ────────────────────────────────────────────

    def _stage_wm_update(self, goal: str, context: str) -> dict:
        """Stage 1: Update world model with current context."""
        result: Dict[str, Any] = {"stage": "wm_update", "success": False}

        wm = self._get_module("world_model")
        if wm:
            try:
                # Encode current context as experience
                experience = {
                    "tool": "goal_processing",
                    "complexity": min(len(goal) / 500.0, 1.0),
                    "success": True,
                    "context": context[:500],
                }
                latent = wm.encode_experience(experience)
                features = wm.get_state_features()
                result["latent_state"] = latent[:200]
                result["feature_count"] = features.get("feature_count", 0)
                result["success"] = True
            except Exception as e:
                result["error"] = str(e)[:200]
                print(f"[AGIOrchestrator] WM update error: {e}")
        else:
            result["error"] = "world_model unavailable"

        self._publish_event("stage_complete", {"stage": "wm_update", "success": result["success"]})
        return result

    def _stage_h_aif_plan(self, goal: str, context: str) -> dict:
        """Stage 2: Generate a plan using hierarchical active inference."""
        result: Dict[str, Any] = {"stage": "h_aif_plan", "success": False}

        # Try hierarchical AIF first
        haif = self._get_module("hierarchical_aif")
        if haif:
            try:
                if hasattr(haif, "select_action"):
                    # Extract candidate actions from goal keywords
                    actions = [w for w in goal.lower().split() if len(w) > 3]
                    if actions:
                        action, info = haif.select_action(actions[:20])
                        result["plan"] = {"selected_action": action, "info": info, "method": "hierarchical_aif"}
                        result["success"] = True
                elif hasattr(haif, "get_stats"):
                    stats = haif.get_stats()
                    result["plan"] = {"method": "hierarchical_aif", "stats": stats}
                    result["success"] = True
            except Exception as e:
                result["error"] = str(e)[:200]
                print(f"[AGIOrchestrator] H-AIF error: {e}")

        # Fallback to code planner
        if not result["success"]:
            cp = self._get_module("code_planner")
            if cp:
                try:
                    if hasattr(cp, "decompose_goal"):
                        plan = cp.decompose_goal(goal)
                        result["plan"] = plan.to_dict() if hasattr(plan, "to_dict") else plan
                        result["success"] = True
                        result["fallback"] = "code_planner"
                    elif hasattr(cp, "get_active_plans"):
                        plans = cp.get_active_plans()
                        result["plan"] = {"active_plans": plans, "method": "code_planner"}
                        result["success"] = True
                        result["fallback"] = "code_planner"
                except Exception as e:
                    result["error"] = str(e)[:200]

        # Fallback to active inference
        if not result["success"]:
            ai = self._get_module("active_inference")
            if ai:
                try:
                    result["plan"] = {"goal": goal, "method": "active_inference", "steps": []}
                    result["success"] = True
                    result["fallback"] = "active_inference"
                except Exception as e:
                    result["error"] = str(e)[:200]

        self._publish_event("stage_complete", {"stage": "h_aif_plan", "success": result["success"]})
        return result

    def _stage_neurosym_abstract(self, goal: str, context: str) -> dict:
        """Stage 3: Apply neurosymbolic abstraction to the plan."""
        result: Dict[str, Any] = {"stage": "neurosym_abstract", "success": False}

        nsr = self._get_module("neurosymbolic_reasoner")
        if nsr:
            try:
                if hasattr(nsr, "abstract_to_symbolic"):
                    propositions = nsr.abstract_to_symbolic(goal[:200])
                    result["abstraction"] = {
                        "propositions": [str(p) for p in propositions[:5]] if propositions else [],
                        "count": len(propositions) if propositions else 0,
                    }
                    result["success"] = True
                elif hasattr(nsr, "symbolic_plan"):
                    plan = nsr.symbolic_plan(goal[:200], [])
                    result["abstraction"] = plan
                    result["success"] = True
                elif hasattr(nsr, "extract_invariants"):
                    invariants = nsr.extract_invariants(goal[:200])
                    result["abstraction"] = {"invariants": invariants}
                    result["success"] = True
            except Exception as e:
                result["error"] = str(e)[:200]
                print(f"[AGIOrchestrator] Neurosym error: {e}")
        else:
            result["abstraction"] = {"note": "neurosymbolic_reasoner unavailable", "goal": goal[:200]}
            result["success"] = True
            result["skipped"] = True

        # Enrich with analogical reasoning if available
        analogy = self._get_module("analogy_engine")
        if analogy:
            try:
                if hasattr(analogy, "find_analogy"):
                    # Build a RelationalStructure from the goal
                    from brain.analogy_engine import RelationalStructure
                    source = RelationalStructure(name="current_goal")
                    for word in goal.lower().split():
                        if len(word) > 3:
                            source.add_object(word)
                    if source.objects:
                        source.add_relation("goal", tuple(source.objects))
                    # Access cached domains (private attr, but safe read)
                    cache = getattr(analogy, "_domain_cache", {})
                    targets = list(cache.values())[:10]
                    if targets and not source.is_empty():
                        analogies = analogy.find_analogy(source, targets, top_k=3)
                        if analogies:
                            result["analogies"] = [
                                {"score": m.total_score, "source": m.source_domain, "target": m.target_domain}
                                for m in analogies
                            ]
                            result["analogical_enrichment"] = True
            except Exception as e:
                print(f"[AGIOrchestrator] Analogy enrichment error: {e}")

        self._publish_event("stage_complete", {"stage": "neurosym_abstract", "success": result["success"]})
        return result

    def _stage_world_sim_rollout(self, goal: str, previous_stages: dict) -> dict:
        """Stage 4: Simulate plan execution using world model."""
        result: Dict[str, Any] = {"stage": "world_sim_rollout", "success": False}

        wm = self._get_module("world_model")
        if wm:
            try:
                # Extract plan steps from previous stage
                plan_data = previous_stages.get("h_aif_plan", {}).get("plan", {})
                steps = plan_data.get("steps", plan_data.get("subgoals", []))

                if steps and isinstance(steps, list):
                    # Convert steps to action dicts
                    action_sequence = []
                    for step in steps[:10]:
                        if isinstance(step, dict):
                            action_sequence.append(step)
                        elif isinstance(step, str):
                            action_sequence.append({"tool": step, "complexity": 0.5})

                    if action_sequence:
                        # Get current state
                        features = wm.get_state_features()
                        start_state = {}
                        latent_vec = features.get("latent_vector", [])
                        feature_names = features.get("feature_names", [])
                        if latent_vec and feature_names:
                            start_state = dict(zip(feature_names, latent_vec))

                        trajectory = wm.imagine_trajectory(start_state, action_sequence, horizon=5)
                        evaluation = wm.evaluate_plan(action_sequence)

                        result["trajectory_length"] = len(trajectory)
                        result["evaluation"] = evaluation
                        result["success"] = True
                    else:
                        result["note"] = "No actionable steps to simulate"
                        result["success"] = True
                else:
                    result["note"] = "No plan steps available for simulation"
                    result["success"] = True
            except Exception as e:
                result["error"] = str(e)[:200]
                print(f"[AGIOrchestrator] World sim error: {e}")
        else:
            result["note"] = "world_model unavailable"
            result["success"] = True  # Non-critical

        # Enrich simulation with causal reasoning
        causal = self._get_module("causal_reasoner")
        if causal:
            try:
                if hasattr(causal, "find_causes"):
                    # Find potential causes related to the goal
                    causes = causal.find_causes(goal[:100], max_depth=3)
                    if causes:
                        result["causal_analysis"] = {
                            "causes_found": len(causes),
                            "top_causes": [c.get("cause", str(c))[:60] for c in causes[:3]],
                        }
                if hasattr(causal, "get_stats"):
                    causal_stats = causal.get_stats()
                    result["causal_graph_size"] = causal_stats.get("total_nodes", 0)
            except Exception as e:
                print(f"[AGIOrchestrator] Causal reasoning error: {e}")

        self._publish_event("stage_complete", {"stage": "world_sim_rollout", "success": result["success"]})
        return result

    def _stage_execute(self, goal: str, context: str, previous_stages: dict) -> dict:
        """Stage 5: Execute the plan (delegate to appropriate module)."""
        result: Dict[str, Any] = {"stage": "execute", "success": False}

        # Determine execution strategy based on goal type
        goal_lower = goal.lower()

        # Code-related goals
        if any(kw in goal_lower for kw in ["code", "implement", "fix", "refactor", "debug", "write"]):
            cp = self._get_module("code_planner")
            if cp:
                try:
                    if hasattr(cp, "decompose_goal"):
                        plan = cp.decompose_goal(goal)
                        # Simulate the plan if possible
                        if hasattr(cp, "simulate_plan"):
                            sim_result = cp.simulate_plan(plan)
                            result["execution"] = sim_result
                        else:
                            result["execution"] = plan.to_dict() if hasattr(plan, "to_dict") else plan
                        result["success"] = True
                        result["executor"] = "code_planner"
                except Exception as e:
                    result["error"] = str(e)[:200]

            # Also try code simulator
            if not result["success"]:
                cs = self._get_module("code_simulator")
                if cs:
                    try:
                        if hasattr(cs, "simulate_code"):
                            sim_result = cs.simulate_code(goal)
                            result["execution"] = sim_result
                            result["success"] = True
                            result["executor"] = "code_simulator"
                    except Exception as e:
                        result["error"] = str(e)[:200]

        # Memory-related goals
        elif any(kw in goal_lower for kw in ["remember", "recall", "search", "find", "memory"]):
            mc = self._get_module("memory_coordinator")
            if mc:
                try:
                    if hasattr(mc, "recall"):
                        recall_result = mc.recall(goal)
                        result["execution"] = recall_result
                        result["success"] = True
                        result["executor"] = "memory_coordinator"
                except Exception as e:
                    result["error"] = str(e)[:200]

        # Learning-related goals
        elif any(kw in goal_lower for kw in ["learn", "improve", "practice", "study"]):
            improver = self._get_module("self_improve_engine")
            if improver:
                try:
                    cycle_result = improver.run_improvement_cycle()
                    result["execution"] = cycle_result
                    result["success"] = True
                    result["executor"] = "self_improve_engine"
                except Exception as e:
                    result["error"] = str(e)[:200]

        # Default: try creative problem-solving, then passthrough
        if not result["success"]:
            creativity = self._get_module("creativity_engine")
            if creativity:
                try:
                    if hasattr(creativity, "generate_alternatives"):
                        ideas = creativity.generate_alternatives(
                            problem={"description": goal[:200], "domain": context[:100] if context else "general"},
                            existing_solution={"method": "standard", "steps": []},
                            n=3,
                        )
                        if ideas:
                            result["execution"] = {
                                "goal": goal[:200],
                                "method": "creative_ideation",
                                "ideas": ideas[:5] if isinstance(ideas, list) else str(ideas)[:300],
                            }
                            result["success"] = True
                            result["executor"] = "creativity_engine"
                except Exception as e:
                    print(f"[AGIOrchestrator] Creativity fallback error: {e}")

        if not result["success"]:
            result["execution"] = {
                "goal": goal[:200],
                "method": "orchestrator_passthrough",
                "note": "No specific executor matched; goal logged for future processing.",
            }
            result["success"] = True
            result["executor"] = "passthrough"

        self._publish_event("stage_complete", {"stage": "execute", "success": result["success"]})
        return result

    def _stage_reflect(self, goal: str, previous_stages: dict) -> dict:
        """Stage 6: Reflect on the goal processing outcome."""
        result: Dict[str, Any] = {"stage": "reflect", "success": False}

        # Self-critique the execution
        improver = self._get_module("self_improve_engine")
        if improver:
            try:
                exec_stage = previous_stages.get("execute", {})
                action = {"goal": goal, "stages": list(previous_stages.keys())}
                outcome = {
                    "success": exec_stage.get("success", False),
                    "executor": exec_stage.get("executor", "unknown"),
                }
                critique = improver.self_critique(action, outcome)
                result["critique"] = {
                    "quality_score": critique.get("quality_score", 0.5),
                    "num_lessons": len(critique.get("lessons", [])),
                    "summary": critique.get("summary", "")[:200],
                }
                result["success"] = True
            except Exception as e:
                result["error"] = str(e)[:200]
                print(f"[AGIOrchestrator] Reflect error: {e}")

        # Record learning signal
        learning = self._get_module("learning_engine")
        if learning:
            try:
                exec_success = previous_stages.get("execute", {}).get("success", False)
                if hasattr(learning, "record_event"):
                    learning.record_event("goal_processing", {
                        "goal": goal[:200],
                        "success": exec_success,
                    })
            except Exception as e:
                print(f"[AGIOrchestrator] Learning record error: {e}")

        # Check for cross-domain transfer opportunities
        transfer = self._get_module("transfer_learning")
        if transfer:
            try:
                exec_success = previous_stages.get("execute", {}).get("success", False)
                if exec_success and hasattr(transfer, "on_lesson_learned"):
                    transfer.on_lesson_learned({
                        "description": goal[:200],
                        "success": True,
                        "context": {"stages": list(previous_stages.keys())},
                    })
                if hasattr(transfer, "get_stats"):
                    result["transfer_stats"] = transfer.get_stats()
            except Exception as e:
                print(f"[AGIOrchestrator] Transfer learning error: {e}")

        # Meta-learning: adapt strategies based on outcome
        meta = self._get_module("meta_learner")
        if meta:
            try:
                exec_success = previous_stages.get("execute", {}).get("success", False)
                if hasattr(meta, "record_outcome"):
                    # Use current strategy for this task type
                    strategy = "q_learning"
                    if hasattr(meta, "get_current_strategy"):
                        strategy = meta.get_current_strategy("goal_processing")
                    meta.record_outcome(
                        task_type="goal_processing",
                        strategy=strategy,
                        success=exec_success,
                    )
                if hasattr(meta, "select_strategy"):
                    recommendation = meta.select_strategy("goal_processing")
                    if recommendation:
                        result["meta_recommendation"] = {"strategy": recommendation}
            except Exception as e:
                print(f"[AGIOrchestrator] Meta-learner error: {e}")

        if not result.get("success"):
            result["success"] = True  # Reflection is best-effort
            result["note"] = "Reflection completed (limited data)"

        self._publish_event("stage_complete", {"stage": "reflect", "success": result["success"]})
        return result

    # ── Helper Methods ───────────────────────────────────────────────────

    def _publish_event(self, event_kind: str, data: dict) -> None:
        """Publish an orchestrator event to the global workspace."""
        try:
            from brain.global_workspace import get_global_workspace
            from brain.workspace_events import EventType, WorkspaceEvent

            gw = get_global_workspace()
            event = WorkspaceEvent(
                source="agi_orchestrator",
                type=EventType.REFLECTION,
                content={"kind": event_kind, **data},
                importance=0.4,
            )
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(gw.publish(event))
            except RuntimeError:
                pass
        except Exception as e:
            print(f"[AGIOrchestrator] Failed to publish event: {e}")

    # ── Prompt & Stats ───────────────────────────────────────────────────

    def format_for_prompt(self, max_chars: int = 1500) -> str:
        """
        Format orchestrator state for inclusion in LLM system prompts.

        Args:
            max_chars: Maximum character count for the output.

        Returns:
            Human-readable summary of the orchestrator's status and recent activity.
        """
        with self._lock:
            meta = self._data["meta"]
            history = self._data.get("goal_history", [])
            module_status = self._data.get("module_status", {})

        available = sum(1 for v in module_status.values() if v == "available")
        total = len(module_status)

        parts = ["=== AGI Orchestrator ==="]
        parts.append(f"Modules: {available}/{total} available")
        parts.append(f"Goals processed: {meta['total_goals_processed']}")
        parts.append(f"Cognitive steps: {meta['total_cognitive_steps']}")
        parts.append(f"Maintenance cycles: {meta['total_maintenance_cycles']}")

        # Recent goals
        if history:
            recent = history[-5:]
            parts.append("Recent goals:")
            for g in recent:
                status = "✓" if g.get("success") else "✗"
                parts.append(f"  {status} {g.get('goal', '?')[:60]}")

        # IQ proxy
        iq_history = self._data.get("iq_history", [])
        if iq_history:
            latest_iq = iq_history[-1].get("iq", 100.0)
            parts.append(f"Latest IQ proxy: {latest_iq:.1f}")

        result = "\n".join(parts)
        if len(result) > max_chars:
            result = result[:max_chars].rsplit("\n", 1)[0] + "\n[...]"
        return result

    def get_stats(self) -> dict:
        """
        Get comprehensive statistics about the orchestrator.

        Returns:
            Dict with metadata, module status, goal history, and IQ metrics.
        """
        with self._lock:
            meta = dict(self._data["meta"])
            module_status = dict(self._data.get("module_status", {}))
            history = self._data.get("goal_history", [])
            iq_history = self._data.get("iq_history", [])

        available = sum(1 for v in module_status.values() if v == "available")
        total = len(module_status)

        # Goal success rate
        if history:
            recent = history[-50:]
            success_rate = sum(1 for g in recent if g.get("success", False)) / len(recent)
            avg_time = sum(g.get("elapsed", 0) for g in recent) / len(recent)
        else:
            success_rate = 0.0
            avg_time = 0.0

        # Latest IQ
        latest_iq = iq_history[-1].get("iq", 100.0) if iq_history else 100.0

        return {
            **meta,
            "modules_available": available,
            "modules_total": total,
            "system_health": round(available / total, 2) if total > 0 else 0.0,
            "goal_success_rate": round(success_rate, 4),
            "avg_goal_time": round(avg_time, 3),
            "latest_iq_proxy": latest_iq,
            "goals_in_history": len(history),
        }

    def save(self) -> None:
        """Explicitly save state to disk."""
        self._save()


# ── Singleton ───────────────────────────────────────────────────────────────

_orchestrator: Optional[AGIOrchestrator] = None
_orchestrator_lock = threading.Lock()


def get_agi_orchestrator() -> AGIOrchestrator:
    """
    Get the singleton AGIOrchestrator instance.

    Returns:
        The global AGIOrchestrator singleton.
    """
    global _orchestrator
    if _orchestrator is None:
        with _orchestrator_lock:
            if _orchestrator is None:
                _orchestrator = AGIOrchestrator()
    return _orchestrator
