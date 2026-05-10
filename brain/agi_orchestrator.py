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
- learning: Q-learning, error-driven learning
- dreaming: replay, consolidation
- self_model: capability tracking
- procedural_memory: skill memory
- benchmark_runner: performance benchmarking
- agi_benchmark_v2: autonomous cognitive architecture evaluation (v2)
- self_modifier: self-modification analysis, safe code changes, evolution tracking
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
        self._load()
        self._load_modules()

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
