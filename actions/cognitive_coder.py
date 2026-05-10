#!/usr/bin/env python3
"""
cognitive_coder.py — FRIDAY Cognitive Coding Orchestrator
==========================================================

The master orchestrator that wires together all cognitive coding modules
into a unified coding intelligence system. This is what makes FRIDAY
think like an expert programmer.

Pipeline:
  User Goal → [Perceive] → [Plan] → [Simulate] → [Execute] → [Debug] → [Reflect]
            → [Learn] → [Consolidate]

Each stage uses the appropriate brain module:
- Perceive: code_intelligence (codebase graph + chunk memory)
- Plan: code_planner (hierarchical decomposition + EFE)
- Simulate: code_simulator (predictive execution + anomaly detection)
- Execute: code_helper/dev_agent (actual code writing/running)
- Debug: code_reflector (root cause analysis + fix strategies)
- Reflect: learning engine (procedural memory update)
"""

import json
import re
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional



BASE_DIR = Path(__file__).resolve().parent.parent
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _resolve_path(target: str) -> Path:
    """Resolve a target path with cross-platform normalization."""
    from actions.resilience import normalize_path
    path, _err = normalize_path(target)
    return path
COGNITIVE_MODEL = "gemini-2.5-flash"

# Maximum iterations for the cognitive loop
MAX_ITERATIONS = 5
# Maximum time for the entire cognitive process (seconds)
MAX_COGNITIVE_TIME = 300


class CognitiveState:
    """Tracks the state of a cognitive coding session."""

    def __init__(self, goal: str, language: str = "python", project_dir: str = ""):
        self.goal = goal
        self.language = language
        self.project_dir = project_dir
        self.start_time = time.time()
        self.iteration = 0
        self.status = "starting"
        self.plan = None
        self.simulation = None
        self.execution_result = None
        self.debug_analysis = None
        self.lessons = []
        self.code_intelligence_context = ""
        self.history: List[dict] = []

    def elapsed(self) -> float:
        return time.time() - self.start_time

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "language": self.language,
            "iteration": self.iteration,
            "status": self.status,
            "elapsed": round(self.elapsed(), 1),
            "lessons_count": len(self.lessons),
            "history": self.history[-10:],
        }


def _get_api_key() -> str:
    try:
        data = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        return data.get("gemini_api_key", data.get("GOOGLE_API_KEY", ""))
    except Exception:
        return ""


def _generate(prompt: str, system: str = "") -> str:
    from google import genai
    from google.genai import types as genai_types
    from actions.resilience import api_retry

    api_key = _get_api_key()
    if not api_key:
        return "Error: No API key configured."

    def _call():
        client = genai.Client(api_key=api_key)
        config = genai_types.GenerateContentConfig(
            system_instruction=system if system else None,
            max_output_tokens=4096,
        )
        response = client.models.generate_content(
            model=COGNITIVE_MODEL,
            contents=prompt,
            config=config,
        )
        return response.text.strip()

    try:
        return api_retry(
            _call,
            max_retries=3,
            base_delay=2.0,
            max_delay=60.0,
            on_retry=lambda attempt, delay, err: print(
                f"[CogCoder] API retry {attempt}/3, waiting {delay:.1f}s: {err}"
            ),
        )
    except Exception as e:
        return f"Error: {e}"


# ── The Cognitive Coding Pipeline ───────────────────────────────────────

def cognitive_code(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    """
    Main entry point for the Cognitive Coding Engine.

    Actions:
    - build: Full cognitive pipeline (plan → simulate → execute → debug → reflect)
    - analyze: Analyze codebase and build semantic graph
    - plan: Generate execution plan without executing
    - simulate: Simulate code before writing
    - debug: Debug a failure with root-cause analysis
    - refactor: Analyze and suggest refactoring
    - review: Deep code review with anomaly detection
    - explain: Explain code with cognitive context
    - status: Get cognitive system status
    """
    p = parameters or {}
    action = p.get("action", "build").lower().strip()
    description = p.get("description", "").strip()
    language = p.get("language", "python").strip()
    code = p.get("code", "").strip()
    file_path = p.get("file_path", "").strip()
    project_dir = p.get("project_dir", "").strip()
    error_output = p.get("error_output", "").strip()

    # Load cognitive modules (lazy)
    try:
        from brain.code_intelligence import get_code_intelligence
        ci = get_code_intelligence()
    except Exception as e:
        ci = None
        print(f"[CogCoder] code_intelligence unavailable: {e}")

    try:
        from brain.code_planner import get_code_planner
        cp = get_code_planner()
    except Exception as e:
        cp = None
        print(f"[CogCoder] code_planner unavailable: {e}")

    try:
        from brain.code_simulator import get_code_simulator
        cs = get_code_simulator()
    except Exception as e:
        cs = None
        print(f"[CogCoder] code_simulator unavailable: {e}")

    try:
        from brain.code_reflector import get_code_reflector
        cr = get_code_reflector()
    except Exception as e:
        cr = None
        print(f"[CogCoder] code_reflector unavailable: {e}")

    try:
        from brain.code_reasoning_engine import get_code_reasoning_engine
        re = get_code_reasoning_engine()
    except Exception as e:
        re = None
        print(f"[CogCoder] code_reasoning_engine unavailable: {e}")

    if action == "build":
        return _action_build(description, language, project_dir, ci, cp, cs, cr, re, player, speak)
    elif action == "build_typed":
        return _action_build_typed(description, language, project_dir, ci, re, player, speak)
    elif action == "analyze":
        return _action_analyze(project_dir or file_path, ci, player)
    elif action == "plan":
        return _action_plan(description, language, project_dir, ci, cp, player)
    elif action == "simulate":
        return _action_simulate(code or file_path, language, cs, player)
    elif action == "debug":
        return _action_debug(error_output, code or file_path, language, cr, cs, player)
    elif action == "refactor":
        return _action_refactor(code or file_path, language, ci, cs, player)
    elif action == "review":
        return _action_review(code or file_path, language, ci, cs, cr, player)
    elif action == "explain":
        return _action_explain(code or file_path, language, ci, player)
    elif action == "reason":
        return _action_reason(description, language, project_dir, re, player)
    elif action == "pattern":
        return _action_select_pattern(description, re, player)
    elif action == "impact":
        return _action_impact(file_path, description, project_dir, re, player)
    elif action == "status":
        return _action_status(ci, cp, cs, cr, re)
    else:
        return f"Unknown cognitive action: {action}. Use: build, build_typed, analyze, plan, simulate, debug, refactor, review, explain, reason, pattern, impact, status"


def _action_build(description: str, language: str, project_dir: str,
                  ci, cp, cs, cr, re_engine, player, speak) -> str:
    """
    Full cognitive coding pipeline with Opus-level reasoning:
    1. Reason: deep chain-of-thought analysis
    2. Perceive: understand the codebase
    3. Design: select architecture/patterns
    4. Plan: decompose into subgoals
    5. Simulate: predict outcomes
    6. Execute with self-correction: write → test → fix loop
    7. Debug: fix remaining failures
    8. Reflect: learn from the process
    """
    if not description:
        return "Please describe what you want to build."

    state = CognitiveState(description, language, project_dir)

    def log(msg):
        print(f"[CogCoder] {msg}")
        if player:
            player.write_log(f"[CogCoder] {msg}")

    log("🧠 Cognitive build started (Opus-level reasoning)")

    # ── Stage 0: Deep Reasoning ─────────────────────────────────────────
    reasoning_context = ""
    if re_engine:
        try:
            log("Stage 0: Deep reasoning about task...")
            reasoning = re_engine.reason_about_task(description, "", language)
            reasoning_context = reasoning.get("recommended_approach", "")
            pitfalls = reasoning.get("potential_pitfalls", [])
            if reasoning_context:
                log(f"  Approach: {reasoning_context[:100]}")
            if pitfalls:
                log(f"  Pitfalls: {', '.join(pitfalls[:3])}")

            # Select design pattern if applicable
            pattern_result = re_engine.select_design_pattern(description, language=language)
            if pattern_result.get("recommended"):
                pattern = pattern_result["recommended"]["pattern"]
                log(f"  Pattern: {pattern} (score={pattern_result['recommended']['score']:.2f})")
                reasoning_context += f"\nRecommended pattern: {pattern}"
        except Exception as e:
            log(f"  Reasoning failed: {e}")

    # ── Stage 1: Perceive ───────────────────────────────────────────────
    log("Stage 1: Perceiving codebase...")
    codebase_context = ""
    project_files: dict = {}
    if ci and project_dir:
        try:
            from pathlib import Path
            pdir = _resolve_path(project_dir)
            if pdir.exists():
                files = [str(f) for f in pdir.rglob("*.py") if "__pycache__" not in str(f)]
                if files:
                    graph_result = ci.build_graph(str(pdir), files[:50])
                    codebase_context = ci.format_for_prompt(max_chars=1000)
                    log(f"  Graph: {graph_result['nodes_added']} nodes, {graph_result['edges_added']} edges")

                    # Load file contents for multi-file reasoning
                    for fp in files[:20]:
                        try:
                            project_files[fp] = Path(fp).read_text(encoding="utf-8")
                        except Exception:
                            pass
        except Exception as e:
            log(f"  Graph build failed: {e}")

    # ── Stage 2: Plan ───────────────────────────────────────────────────
    log("Stage 2: Planning decomposition...")
    plan = None
    plan_context = codebase_context
    if reasoning_context:
        plan_context += f"\n\nReasoning:\n{reasoning_context[:500]}"

    if cp:
        try:
            plan = cp.decompose_goal(description, plan_context, language)
            state.plan = plan
            log(f"  Plan: {len(plan.subgoals)} subgoals, EFE={plan.total_efe:.3f}")

            for gid in plan.execution_order:
                sg = plan.subgoals.get(gid)
                if sg:
                    log(f"  → {gid}: {sg.description[:60]} (EFE={sg.efe_score:.3f})")
        except Exception as e:
            log(f"  Planning failed: {e}")

    # ── Stage 3: Simulate ───────────────────────────────────────────────
    log("Stage 3: Simulating plan...")
    simulation = None
    if cs and plan:
        try:
            simulation = cp.simulate_plan(plan, codebase_context)
            state.simulation = simulation
            log(f"  Confidence: {simulation.get('overall_confidence', 0):.0%}")
            log(f"  Est. time: {simulation.get('estimated_time_seconds', 0)}s")

            high_risk = simulation.get("high_risk_steps", [])
            if high_risk:
                log(f"  ⚠️ {len(high_risk)} high-risk steps identified")
        except Exception as e:
            log(f"  Simulation failed: {e}")

    # ── Stage 4: Execute with Self-Correction ───────────────────────────
    log("Stage 4: Executing with self-correction...")
    execution_result = ""

    if re_engine:
        try:
            # Use the reasoning engine's self-correction loop
            correction_result = re_engine.generate_with_correction(
                goal=description,
                language=language,
                context=codebase_context[:2000],
                max_iterations=3,
            )
            execution_result = correction_result.get("final_code", "")
            corrections = correction_result.get("corrections", 0)
            status = correction_result.get("status", "unknown")
            log(f"  Self-correction: {corrections} corrections, status={status}")

            if correction_result.get("iterations"):
                for it in correction_result["iterations"]:
                    if it.get("corrections"):
                        log(f"    Iteration {it['iteration']}: {it['corrections']}")
        except Exception as e:
            log(f"  Self-correction failed: {e}")

    if not execution_result:
        execution_result = _execute_with_cognition(description, language, project_dir, plan, player, speak)

    state.execution_result = execution_result
    state.history.append({"stage": "execute", "result": execution_result[:200], "time": state.elapsed()})

    # ── Stage 5: Debug (if errors) ──────────────────────────────────────
    if _has_error(execution_result):
        log("Stage 5: Debugging failures...")
        if cr:
            try:
                analysis = cr.analyze_failure(execution_result, description, language)
                state.debug_analysis = analysis

                root_causes = analysis.get("root_causes", [])
                if root_causes:
                    top = root_causes[0]
                    log(f"  Root cause: {top.get('cause', '?')[:80]} (p={top.get('probability', 0):.0%})")

                fix = cr.select_fix_strategy(analysis, description, language)
                log(f"  Strategy: {fix.get('strategy', '?')} (conf={fix.get('confidence', 0):.0%})")

                if fix.get("confidence", 0) > 0.4:
                    fix_result = _execute_with_cognition(
                        f"{description}\n\nFix hint: {fix.get('fix', '')}",
                        language, project_dir, None, player, speak
                    )
                    if not _has_error(fix_result):
                        log("  ✅ Fix successful!")
                        execution_result = fix_result
                        state.lessons.append(f"Fixed: {top.get('cause', '?')[:100]}")
                    else:
                        log("  ❌ Fix failed — manual review needed")
            except Exception as e:
                log(f"  Debug failed: {e}")
    else:
        log("Stage 5: No errors — skipping debug")

    # ── Stage 6: Multi-File Impact Check ────────────────────────────────
    if re_engine and project_files and project_dir:
        try:
            log("Stage 6: Checking multi-file impact...")
            impact = re_engine.reason_about_changes(
                target_file="new_code",
                change_description=description,
                project_files=project_files,
            )
            affected = impact.get("affected_files", [])
            if affected:
                log(f"  Impact: {len(affected)} files affected")
                risk = impact.get("risk_assessment", "unknown")
                log(f"  Risk: {risk}")
        except Exception as e:
            log(f"  Impact analysis failed: {e}")

    # ── Stage 7: Reflect ────────────────────────────────────────────────
    log("Stage 7: Reflecting...")
    if cr:
        try:
            success = not _has_error(execution_result)
            ref_id = cr.learn_from_session(
                error_output=execution_result if not success else "",
                code=description,
                fix_applied=description,
                success=success,
                language=language,
                lessons=state.lessons,
            )
            log(f"  Reflection saved: {ref_id}")
        except Exception as e:
            log(f"  Reflection failed: {e}")

    # ── Stage 8: Consolidate ────────────────────────────────────────────
    log("Stage 8: Consolidating...")
    try:
        from brain.learning import get_learning_engine
        le = get_learning_engine()
        if le:
            le.consolidate()
    except Exception:
        pass

    if ci:
        try:
            ci.learn_chunk(
                pattern_type="generated",
                name=description[:50],
                description=description,
                code_template=execution_result[:500] if execution_result else "",
                language=language,
                tags=[language, "generated"],
            )
        except Exception:
            pass

    state.status = "completed" if not _has_error(execution_result) else "completed_with_errors"
    log(f"✅ Cognitive build done ({state.elapsed():.1f}s)")

    return execution_result


def _execute_with_cognition(description: str, language: str, project_dir: str,
                            plan, player, speak) -> str:
    """Execute code writing using the existing code_helper/dev_agent with plan context."""
    try:
        if project_dir:
            from actions.dev_agent import dev_agent
            result = dev_agent(
                parameters={"description": description, "language": language, "project_name": Path(project_dir).name},
                player=player,
                speak=speak,
            )
        else:
            from actions.code_helper import code_helper
            result = code_helper(
                parameters={"action": "build", "description": description, "language": language},
                player=player,
                speak=speak,
            )
        return result if result else "No result from execution"
    except Exception as e:
        return f"Execution error: {e}"


def _action_analyze(target: str, ci, player) -> str:
    """Analyze a codebase and build semantic graph."""
    if not ci:
        return "Code intelligence module not available."

    if not target:
        return "Please provide a project directory or file path."

    path = _resolve_path(target)
    if not path.exists():
        return f"Path not found: {target}"

    if path.is_dir():
        files = [str(f) for f in path.rglob("*.py") if "__pycache__" not in str(f)]
        if not files:
            return f"No Python files found in {target}"

        result = ci.build_graph(str(path), files[:100])
        summary = ci.get_graph_summary()

        return (
            f"Codebase analysis complete.\n"
            f"Files parsed: {result['files_parsed']}\n"
            f"Nodes: {result['nodes_added']} added ({summary['total_nodes']} total)\n"
            f"Edges: {result['edges_added']} added\n"
            f"By type: {json.dumps(summary.get('by_type', {}))}\n"
            f"Avg complexity: {summary.get('avg_complexity', 0)}"
        )
    else:
        # Single file analysis
        parsed = ci.parse_file(str(path))
        if "error" in parsed:
            return f"Parse error: {parsed['error']}"

        anomalies = ci.extract_patterns_from_code(
            path.read_text(encoding="utf-8"), language=path.suffix.lstrip(".")
        )

        return (
            f"File: {path.name}\n"
            f"Lines: {parsed['lines']}\n"
            f"Classes: {len(parsed['classes'])} — {', '.join(c['name'] for c in parsed['classes']) or 'none'}\n"
            f"Functions: {len(parsed['functions'])} — {', '.join(f['name'] for f in parsed['functions'][:10]) or 'none'}\n"
            f"Imports: {len(parsed['imports'])}\n"
            f"Complexity: {parsed['complexity']}\n"
            f"Patterns: {json.dumps(anomalies[:3]) if anomalies else 'none detected'}"
        )


def _action_plan(description: str, language: str, project_dir: str,
                 ci, cp, player) -> str:
    """Generate an execution plan without executing."""
    if not cp:
        return "Code planner module not available."

    if not description:
        return "Please describe what you want to build."

    codebase_context = ""
    if ci and project_dir:
        try:
            ci.build_graph(project_dir)
            codebase_context = ci.format_for_prompt(max_chars=800)
        except Exception:
            pass  # silently swallowed

    plan = cp.decompose_goal(description, codebase_context, language)

    lines = [f"📋 Execution Plan for: {description[:60]}"]
    lines.append(f"Total EFE: {plan.total_efe:.3f}")
    lines.append(f"Subgoals: {len(plan.subgoals)}")
    lines.append("")

    for i, gid in enumerate(plan.execution_order, 1):
        sg = plan.subgoals.get(gid)
        if sg:
            risk = sg.context.get("risk", "medium")
            risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk, "⚪")
            lines.append(f"{i}. {risk_emoji} [{gid}] {sg.description}")
            lines.append(f"   EFE: {sg.efe_score:.3f} | Risk: {risk} | Steps: {len(sg.steps)}")
            for step in sg.steps[:3]:
                lines.append(f"   → {step.get('tool', '?')}: {step.get('description', '?')[:50]}")

    if plan.context.get("risks"):
        lines.append(f"\n⚠️ Risks: {', '.join(plan.context['risks'][:3])}")

    return "\n".join(lines)


def _action_simulate(target: str, language: str, cs, player) -> str:
    """Simulate code before writing/running."""
    if not cs:
        return "Code simulator module not available."

    code = target
    if _resolve_path(target).exists():
        try:
            code = _resolve_path(target).read_text(encoding="utf-8")
        except Exception as e:
            return f"Could not read file: {e}"

    if not code:
        return "Please provide code or a file path to simulate."

    result = cs.simulate_code(code, language)

    lines = ["🔮 Simulation Results:"]
    lines.append(f"Would run: {'✅' if result.get('would_run') else '❌'}")
    lines.append(f"Confidence: {result.get('confidence', 0):.0%}")

    if result.get("anomalies_detected"):
        lines.append(f"\n🐛 Anomalies: {result['anomaly_count']}")
        for a in result["anomalies_detected"][:5]:
            lines.append(f"  [{a['severity']}] {a['description']} (line {a['line']})")
            if a.get("suggestion"):
                lines.append(f"    → {a['suggestion']}")

    if result.get("likely_errors"):
        lines.append(f"\n⚠️ Likely errors:")
        for e in result["likely_errors"][:3]:
            lines.append(f"  {e.get('type', '?')}: {e.get('reason', '?')[:80]}")

    if result.get("performance"):
        perf = result["performance"]
        lines.append(f"\n📊 Performance:")
        if perf.get("time_complexity"):
            lines.append(f"  Time: {perf['time_complexity']}")
        if perf.get("space_complexity"):
            lines.append(f"  Space: {perf['space_complexity']}")
        if perf.get("bottleneck"):
            lines.append(f"  Bottleneck: {perf['bottleneck']}")

    if result.get("edge_cases"):
        lines.append(f"\n🎯 Edge cases: {', '.join(result['edge_cases'][:3])}")

    return "\n".join(lines)


def _action_debug(error_output: str, code_or_path: str, language: str,
                  cr, cs, player) -> str:
    """Debug a failure with root-cause analysis."""
    if not cr:
        return "Code reflector module not available."

    if not error_output:
        return "Please provide the error output to debug."

    code = code_or_path
    if Path(code_or_path).expanduser().exists():
        try:
            code = Path(code_or_path).expanduser().read_text(encoding="utf-8")
        except Exception:
            pass  # silently swallowed

    # Root cause analysis
    analysis = cr.analyze_failure(error_output, code, language)

    lines = ["🔍 Debug Analysis:"]

    # Error type
    lines.append(f"Error type: {analysis.get('error_type', 'unknown')}")

    # Root causes
    root_causes = analysis.get("root_causes", [])
    if root_causes:
        lines.append(f"\n🎯 Root Causes (ranked):")
        for i, rc in enumerate(root_causes[:3], 1):
            lines.append(f"  {i}. {rc.get('cause', '?')[:80]} (p={rc.get('probability', 0):.0%})")
            if rc.get("evidence"):
                lines.append(f"     Evidence: {rc['evidence'][:60]}")

    # Fix strategies
    fix = cr.select_fix_strategy(analysis, code, language)
    lines.append(f"\n🔧 Recommended fix ({fix.get('strategy', '?')}):")
    lines.append(f"  {fix.get('fix', 'No fix available')[:200]}")
    lines.append(f"  Confidence: {fix.get('confidence', 0):.0%}")
    if fix.get("steps"):
        for step in fix["steps"][:3]:
            lines.append(f"  → {step}")

    # Known patterns
    if analysis.get("known_patterns"):
        lines.append(f"\n📚 Known patterns matched:")
        for p in analysis["known_patterns"][:2]:
            lines.append(f"  {p['error_type']}: {p['fix_strategy'][:60]} (success={p['fix_success_rate']:.0%})")

    # Debugging approach
    if analysis.get("debugging_approach"):
        lines.append(f"\n💡 Suggested approach: {analysis['debugging_approach']}")

    return "\n".join(lines)


def _action_refactor(target: str, language: str, ci, cs, player) -> str:
    """Analyze code and suggest refactoring."""
    code = target
    if _resolve_path(target).exists():
        try:
            code = _resolve_path(target).read_text(encoding="utf-8")
        except Exception as e:
            return f"Could not read file: {e}"

    if not code:
        return "Please provide code or a file path."

    lines = ["♻️ Refactoring Analysis:"]

    # Complexity analysis
    if ci:
        complexity = ci.analyze_complexity(code, language)
        if "error" not in complexity:
            lines.append(f"Complexity: {complexity['rating']} (cognitive={complexity['cognitive']}, cyclomatic={complexity['cyclomatic']})")
            lines.append(f"LOC: {complexity['loc']} | Classes: {complexity['classes']} | Functions: {complexity['functions']}")
            if complexity.get("suggestions"):
                for s in complexity["suggestions"]:
                    lines.append(f"  💡 {s}")

    # Anomaly detection
    if cs:
        anomalies = cs.detect_anomalies(code, language=language)
        if anomalies:
            lines.append(f"\n🐛 Issues found: {len(anomalies)}")
            for a in anomalies[:5]:
                lines.append(f"  [{a['severity']}] {a['description']} (line {a['line']})")

    # Pattern recognition
    if ci:
        patterns = ci.extract_patterns_from_code(code, language)
        if patterns:
            lines.append(f"\n🏗️ Patterns detected:")
            for p in patterns[:3]:
                lines.append(f"  {p['pattern']} (confidence={p['confidence']:.0%})")

    return "\n".join(lines)


def _action_review(target: str, language: str, ci, cs, cr, player) -> str:
    """Deep code review combining all cognitive modules."""
    code = target
    file_path = ""
    if _resolve_path(target).exists():
        try:
            code = _resolve_path(target).read_text(encoding="utf-8")
            file_path = target
        except Exception as e:
            return f"Could not read file: {e}"

    if not code:
        return "Please provide code or a file path."

    lines = ["📋 Cognitive Code Review:"]
    if file_path:
        lines.append(f"File: {file_path}")

    # 1. Complexity
    if ci:
        complexity = ci.analyze_complexity(code, language)
        if "error" not in complexity:
            lines.append(f"\n--- Complexity ---")
            lines.append(f"Rating: {complexity['rating']}")
            lines.append(f"Cognitive: {complexity['cognitive']} | Cyclomatic: {complexity['cyclomatic']}")
            lines.append(f"Max nesting: {complexity['max_nesting']} | Max params: {complexity['max_params']}")

    # 2. Anomalies
    if cs:
        anomalies = cs.detect_anomalies(code, file_path=file_path, language=language)
        if anomalies:
            critical = [a for a in anomalies if a["severity"] == "critical"]
            high = [a for a in anomalies if a["severity"] == "high"]
            lines.append(f"\n--- Security & Bugs ---")
            lines.append(f"Total: {len(anomalies)} (🔴 critical={len(critical)}, 🟠 high={len(high)})")
            for a in anomalies[:5]:
                lines.append(f"  [{a['severity']}] {a['description']} (line {a['line']})")

    # 3. Patterns
    if ci:
        patterns = ci.extract_patterns_from_code(code, language)
        if patterns:
            lines.append(f"\n--- Patterns ---")
            for p in patterns:
                lines.append(f"  {p['pattern']} ({p['confidence']:.0%})")

    # 4. Simulation
    if cs:
        sim = cs.simulate_code(code, language)
        lines.append(f"\n--- Simulation ---")
        lines.append(f"Would run: {'Yes' if sim.get('would_run') else 'No'} (conf={sim.get('confidence', 0):.0%})")
        if sim.get("performance"):
            perf = sim["performance"]
            if perf.get("time_complexity"):
                lines.append(f"Time complexity: {perf['time_complexity']}")

    return "\n".join(lines)


def _action_explain(target: str, language: str, ci, player) -> str:
    """Explain code with cognitive context."""
    code = target
    if _resolve_path(target).exists():
        try:
            code = _resolve_path(target).read_text(encoding="utf-8")
        except Exception as e:
            return f"Could not read file: {e}"

    if not code:
        return "Please provide code or a file path."

    lines = ["📖 Code Explanation:"]

    # Parse structure
    if ci:
        parsed = ci.parse_file("", code)  # Pass code directly
        if "error" not in parsed:
            if parsed["classes"]:
                lines.append(f"\nClasses: {', '.join(c['name'] for c in parsed['classes'])}")
                for cls in parsed["classes"][:3]:
                    lines.append(f"  {cls['name']}: {len(cls['methods'])} methods")
            if parsed["functions"]:
                lines.append(f"\nFunctions: {', '.join(f['name'] for f in parsed['functions'][:10])}")
            lines.append(f"Imports: {len(parsed['imports'])}")
            lines.append(f"Complexity: {parsed['complexity']}")

    # Patterns
    if ci:
        patterns = ci.extract_patterns_from_code(code, language)
        if patterns:
            lines.append(f"\nPatterns used:")
            for p in patterns[:3]:
                lines.append(f"  {p['pattern']} ({p['confidence']:.0%})")

    return "\n".join(lines)


def _action_status(ci, cp, cs, cr, re_engine=None) -> str:
    """Get cognitive coding system status."""
    lines = ["🧠 Cognitive Coding Engine Status (Opus-level):"]

    if ci:
        graph = ci.get_graph_summary()
        lines.append(f"\n📊 Code Intelligence:")
        lines.append(f"  Graph nodes: {graph['total_nodes']}")
        lines.append(f"  Chunks learned: {graph['total_chunks']}")
        lines.append(f"  Avg complexity: {graph.get('avg_complexity', 0)}")

    if cp:
        stats = cp.get_plan_stats()
        lines.append(f"\n📋 Code Planner:")
        lines.append(f"  Plans: {stats['total_plans']} ({stats['completed']} completed)")
        lines.append(f"  Avg prediction error: {stats['avg_prediction_error']:.3f}")

    if cs:
        stats = cs.get_anomaly_stats()
        lines.append(f"\n🔮 Code Simulator:")
        lines.append(f"  Anomalies tracked: {stats['total_anomalies']}")
        lines.append(f"  Unresolved: {stats['unresolved']}")

    if cr:
        stats = cr.get_stats()
        lines.append(f"\n🔍 Code Reflector:")
        lines.append(f"  Failure patterns: {stats['total_patterns']}")
        lines.append(f"  Fix rate: {stats['fix_rate']:.0%}")
        lines.append(f"  Reflections: {stats['total_reflections']}")

    if re_engine:
        stats = re_engine.get_stats()
        lines.append(f"\n🧩 Code Reasoning Engine:")
        lines.append(f"  Sessions: {stats['total_sessions']}")
        lines.append(f"  Corrections: {stats['successful_corrections']}/{stats['total_corrections']}")
        lines.append(f"  Correction rate: {stats['correction_success_rate']:.0%}")
        lines.append(f"  Design patterns: {stats['design_patterns_available']}")

    return "\n".join(lines)


def _action_build_typed(description: str, language: str, project_dir: str,
                        ci, re_engine, player, speak) -> str:
    """
    Build code with strong type awareness.
    Uses existing codebase types to ensure compatibility.
    """
    if not description:
        return "Please describe what you want to build."

    def log(msg):
        print(f"[CogCoder] {msg}")
        if player:
            player.write_log(f"[CogCoder] {msg}")

    log("🧩 Typed build started")

    # Gather existing types from codebase
    existing_types = {}
    if ci and project_dir:
        try:
            from pathlib import Path
            pdir = _resolve_path(project_dir)
            if pdir.exists():
                files = [str(f) for f in pdir.rglob("*.py") if "__pycache__" not in str(f)]
                for fp in files[:10]:
                    try:
                        content = Path(fp).read_text(encoding="utf-8")
                        from brain.code_reasoning_engine import infer_types_from_ast
                        ctx = infer_types_from_ast(content)
                        for name, ti in ctx.variables.items():
                            existing_types[name] = ti.type_str
                        for func_name, params in ctx.functions.items():
                            for param_name, ti in params.items():
                                existing_types[f"{func_name}.{param_name}"] = ti.type_str
                    except Exception:
                        pass
        except Exception as e:
            log(f"  Type extraction failed: {e}")

    if not re_engine:
        return "Code reasoning engine not available for typed build."

    try:
        result = re_engine.generate_with_types(
            goal=description,
            existing_types=existing_types,
            language=language,
        )
        code = result.get("code", "")
        type_coverage = result.get("type_coverage", 0)
        types_used = result.get("types_used", [])

        log(f"  Type coverage: {type_coverage:.0%}")
        log(f"  Types used: {', '.join(types_used[:5])}")

        return code if code else "Failed to generate typed code."
    except Exception as e:
        return f"Typed build error: {e}"


def _action_reason(description: str, language: str, project_dir: str,
                   re_engine, player) -> str:
    """Deep reasoning about a coding task without writing code."""
    if not description:
        return "Please describe the task to reason about."

    if not re_engine:
        return "Code reasoning engine not available."

    try:
        reasoning = re_engine.reason_about_task(description, "", language)

        lines = ["🧩 Deep Reasoning Analysis:"]
        lines.append(f"\n📝 Problem Understanding:")
        lines.append(f"  {reasoning.get('problem_understanding', '?')}")

        decomposition = reasoning.get("decomposition", [])
        if decomposition:
            lines.append(f"\n🔍 Decomposition:")
            for i, item in enumerate(decomposition, 1):
                lines.append(f"  {i}. {item}")

        decisions = reasoning.get("architecture_decisions", [])
        if decisions:
            lines.append(f"\n🏗️ Architecture Decisions:")
            for d in decisions:
                lines.append(f"  • {d.get('decision', '?')}")
                lines.append(f"    Choice: {d.get('choice', '?')} — {d.get('reasoning', '')}")

        pitfalls = reasoning.get("potential_pitfalls", [])
        if pitfalls:
            lines.append(f"\n⚠️ Potential Pitfalls:")
            for p in pitfalls:
                lines.append(f"  • {p}")

        lines.append(f"\n📋 Recommended Approach:")
        lines.append(f"  {reasoning.get('recommended_approach', '?')}")

        complexity = reasoning.get("complexity_estimate", {})
        if complexity:
            lines.append(f"\n📊 Complexity: {complexity}")

        return "\n".join(lines)
    except Exception as e:
        return f"Reasoning error: {e}"


def _action_select_pattern(requirements: str, re_engine, player) -> str:
    """Select the best design pattern for given requirements."""
    if not requirements:
        return "Please describe the requirements."

    if not re_engine:
        return "Code reasoning engine not available."

    try:
        result = re_engine.select_design_pattern(requirements)

        lines = ["🏗️ Design Pattern Recommendation:"]

        recommended = result.get("recommended")
        if recommended:
            lines.append(f"\n✅ Recommended: {recommended['pattern']}")
            lines.append(f"  Score: {recommended['score']:.2f}")
            lines.append(f"  Structure: {recommended['structure']}")
            lines.append(f"  Testability: {recommended['testability']}")
            lines.append(f"  Pros: {', '.join(recommended['pros'])}")
            lines.append(f"  Cons: {', '.join(recommended['cons'])}")
            lines.append(f"  When to use: {', '.join(recommended['when'])}")

        alternatives = result.get("alternatives", [])
        if alternatives:
            lines.append(f"\n🔄 Alternatives:")
            for alt in alternatives:
                lines.append(f"  • {alt['pattern']} (score={alt['score']:.2f})")

        return "\n".join(lines)
    except Exception as e:
        return f"Pattern selection error: {e}"


def _action_impact(target_file: str, change_description: str, project_dir: str,
                   re_engine, player) -> str:
    """Analyze the impact of changes across the codebase."""
    if not target_file or not change_description:
        return "Please provide a file path and change description."

    if not re_engine:
        return "Code reasoning engine not available."

    try:
        from pathlib import Path
        project_files = {}
        pdir = _resolve_path(project_dir) if project_dir else Path(target_file).expanduser().parent

        if pdir.exists():
            for fp in pdir.rglob("*.py"):
                if "__pycache__" not in str(fp):
                    try:
                        project_files[str(fp)] = fp.read_text(encoding="utf-8")
                    except Exception:
                        pass

        if not project_files:
            return f"No Python files found in {pdir}"

        result = re_engine.reason_about_changes(
            target_file=target_file,
            change_description=change_description,
            project_files=project_files,
        )

        lines = ["📊 Impact Analysis:"]
        lines.append(f"\nTarget: {target_file}")
        lines.append(f"Change: {change_description}")
        lines.append(f"Risk: {result.get('risk_assessment', 'unknown')}")

        affected = result.get("affected_files", [])
        if affected:
            lines.append(f"\n📁 Affected files ({len(affected)}):")
            for f in affected:
                lines.append(f"  • {f}")

        changes = result.get("required_changes", [])
        if changes:
            lines.append(f"\n🔧 Required changes:")
            for c in changes:
                lines.append(f"  • {c.get('file', '?')}: {c.get('change', '?')}")

        order = result.get("recommended_order", [])
        if order:
            lines.append(f"\n📋 Recommended order:")
            for i, f in enumerate(order, 1):
                lines.append(f"  {i}. {f}")

        return "\n".join(lines)
    except Exception as e:
        return f"Impact analysis error: {e}"


# ── Error Detection Helper ──────────────────────────────────────────────

def _has_error(output: str) -> bool:
    """Check if output indicates an error."""
    if not output:
        return False
    low = output.lower()
    error_signals = [
        "traceback", "error:", "exception", "failed", "syntaxerror",
        "nameerror", "typeerror", "attributeerror", "valueerror",
        "keyerror", "indexerror", "modulenotfounderror",
    ]
    return any(s in low for s in error_signals)
