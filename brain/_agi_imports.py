# ── AGI Module Imports (Phase 1-6) ─────────────────────────────────
# Centralized imports for all AGI-phase brain modules.
# Modules use try/except for graceful degradation if any fail to import.

_brain_benchmark_ok = False
try:
    from brain.benchmark_runner import get_benchmark_runner
    _brain_benchmark_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.benchmark_runner: {e}", flush=True)
    get_benchmark_runner = None

_brain_neurosym_ok = False
try:
    from brain.neurosymbolic_reasoner import get_neurosymbolic_reasoner
    _brain_neurosym_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.neurosymbolic_reasoner: {e}", flush=True)
    get_neurosymbolic_reasoner = None

_brain_haif_ok = False
try:
    from brain.hierarchical_active_inference import get_hierarchical_aif
    _brain_haif_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.hierarchical_active_inference: {e}", flush=True)
    get_hierarchical_aif = None

_brain_agi_orch_ok = False
try:
    from brain.agi_orchestrator import get_agi_orchestrator
    _brain_agi_orch_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.agi_orchestrator: {e}", flush=True)
    get_agi_orchestrator = None

_brain_code_reasoning_ok = False
try:
    from brain.code_reasoning_engine import get_code_reasoning_engine
    _brain_code_reasoning_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.code_reasoning_engine: {e}", flush=True)
    get_code_reasoning_engine = None

_brain_cyber_reasoning_ok = False
try:
    from brain.cyber_reasoning import get_cyber_engine
    _brain_cyber_reasoning_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.cyber_reasoning: {e}", flush=True)
    get_cyber_engine = None

_brain_findings_bus_ok = False
try:
    from brain.findings_bus import get_findings_bus
    _brain_findings_bus_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.findings_bus: {e}", flush=True)
    get_findings_bus = None

_brain_world_model_ok = False
try:
    from brain.world_model import get_world_model
    _brain_world_model_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.world_model: {e}", flush=True)
    get_world_model = None

_brain_self_improve_ok = False
try:
    from brain.self_improve_engine import get_self_improve_engine
    _brain_self_improve_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.self_improve_engine: {e}", flush=True)
    get_self_improve_engine = None

_brain_transfer_ok = False
try:
    from brain.transfer_learning import get_transfer_learning
    _brain_transfer_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.transfer_learning: {e}", flush=True)
    get_transfer_learning = None

_brain_analogy_ok = False
try:
    from brain.analogy_engine import get_analogy_engine
    _brain_analogy_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.analogy_engine: {e}", flush=True)
    get_analogy_engine = None

_brain_causal_ok = False
try:
    from brain.causal_reasoner import get_causal_reasoner
    _brain_causal_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.causal_reasoner: {e}", flush=True)
    get_causal_reasoner = None

_brain_creativity_ok = False
try:
    from brain.creativity_engine import get_creativity_engine
    _brain_creativity_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.creativity_engine: {e}", flush=True)
    get_creativity_engine = None

_brain_meta_learner_ok = False
try:
    from brain.meta_learner import get_meta_learner
    _brain_meta_learner_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.meta_learner: {e}", flush=True)
    get_meta_learner = None

_brain_self_modifier_ok = False
try:
    from brain.self_modifier import get_self_modifier
    _brain_self_modifier_ok = True
except Exception as e:
    print(f"[FRIDAY] brain.self_modifier: {e}", flush=True)
    get_self_modifier = None

_agi_benchmark_v2_ok = False
try:
    from benchmarks.agi_benchmark_v2 import get_agi_benchmark_v2
    _agi_benchmark_v2_ok = True
except Exception as e:
    print(f"[FRIDAY] benchmarks.agi_benchmark_v2 (cognitive benchmark): {e}", flush=True)
    get_agi_benchmark_v2 = None


def get_llm():
    """
    Return a callable LLM function for brain modules that need text generation.

    Usage:
        llm = get_llm()
        if llm:
            response = llm("prompt text", max_tokens=500)

    Returns None if no provider is configured.
    """
    try:
        from brain.model_router import get_model_router, Provider
        router = get_model_router()
        provider = router.get_primary_provider()

        if provider == Provider.GEMINI and router.has_gemini_key():
            from google import genai
            api_key = router.get_gemini_key()
            _, model_config = router.get_route("general")
            client = genai.Client(api_key=api_key)

            def _gemini_llm(prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> str:
                response = client.models.generate_content(
                    model=model_config.model_id,
                    contents=prompt,
                    config={"max_output_tokens": max_tokens, "temperature": temperature},
                )
                return response.text if response and response.text else ""

            return _gemini_llm

        elif provider == Provider.OPENAI and router.has_openai_key():
            import openai
            api_key = router.get_openai_key()
            _, model_config = router.get_route("general")
            client = openai.OpenAI(api_key=api_key)

            def _openai_llm(prompt: str, max_tokens: int = 1024, temperature: float = 0.7) -> str:
                response = client.chat.completions.create(
                    model=model_config.model_id,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return response.choices[0].message.content if response.choices else ""

            return _openai_llm

    except Exception as e:
        print(f"[FRIDAY] get_llm() setup failed: {e}", flush=True)

    return None
