"""
brain/model_router.py — Cross-Model Intelligent Routing
Routes tasks to the best model based on content analysis.
Supports Gemini (primary) and OpenAI (secondary) providers.
Inspired by nicv1990/mythos-agent multi-model architecture.
"""

import json
from enum import Enum
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


class TaskType(Enum):
    VOICE = "voice"
    SECURITY = "security"
    CODE = "code"
    PLANNING = "planning"
    QUICK = "quick"
    GENERAL = "general"


class ModelConfig:
    def __init__(self, provider: str, model_id: str, task_type: TaskType,
                 extended_thinking: bool = False):
        self.provider = provider
        self.model_id = model_id
        self.task_type = task_type
        self.extended_thinking = extended_thinking


class Provider(Enum):
    GEMINI = "gemini"
    OPENAI = "openai"


SECURITY_KEYWORDS = [
    "security", "vulnerability", "exploit", "pentest", "penetration",
    "scan", "recon", "enumerate", "subdomain", "port scan", "nmap",
    "sqlmap", "nuclei", "ffuf", "gobuster", "bug bounty", "cve",
    "injection", "xss", "csrf", "ssrf", "rce", "lfi", "rfi",
    "malware", "forensic", "incident", "threat", "attack",
    "red team", "blue team", "soc", "siem", "ids", "ips",
]

CODE_KEYWORDS = [
    "code", "write", "implement", "function", "class", "method",
    "debug", "fix", "error", "bug", "refactor", "optimize",
    "script", "program", "build", "create", "develop", "module",
    "html", "css", "javascript", "python", "rust", "go", "java",
    "api", "endpoint", "server", "database", "sql", "query",
    "test", "unittest", "pytest", "assert", "mock",
]

PLANNING_KEYWORDS = [
    "plan", "design", "architect", "strategy", "roadmap",
    "think", "reason", "analyze", "evaluate", "assess",
    "pros and cons", "trade-off", "compare", "decide",
    "step by step", "break down", "decompose", "approach",
    "how should", "what approach", "best way",
]

SIMPLE_KEYWORDS = [
    "what time", "what's the time", "weather", "play ", "open ",
    "volume", "mute", "unmute", "pause", "stop", "yes", "no",
    "thanks", "thank you", "ok", "okay", "got it", "sure",
    "hello", "hi", "hey", "morning", "good night", "what is",
]


class ModelRouter:
    """Routes requests to the best model based on content analysis."""

    def __init__(self):
        self.config = self._load_config()
        self.routing_config = self.config.get("model_routing", {})
        self._primary_provider = self._get_primary_provider()

    def _get_primary_provider(self) -> Provider:
        provider_str = self.config.get("primary_provider", "gemini").lower()
        try:
            return Provider(provider_str)
        except ValueError:
            return Provider.GEMINI

    def _load_config(self) -> dict:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def get_primary_provider(self) -> Provider:
        return self._primary_provider

    def get_provider_display_name(self) -> str:
        if self._primary_provider == Provider.OPENAI:
            return "OPENAI GPT-4"
        return "GEMINI 2.5 FLASH"

    def classify(self, request: str) -> TaskType:
        request_lower = request.lower()

        if any(kw in request_lower for kw in SIMPLE_KEYWORDS):
            return TaskType.QUICK

        security_score = sum(1 for kw in SECURITY_KEYWORDS if kw in request_lower)
        code_score = sum(1 for kw in CODE_KEYWORDS if kw in request_lower)
        planning_score = sum(1 for kw in PLANNING_KEYWORDS if kw in request_lower)

        scores = {
            TaskType.SECURITY: security_score,
            TaskType.CODE: code_score,
            TaskType.PLANNING: planning_score,
        }

        best = max(scores, key=scores.get)
        if scores[best] > 0:
            return best

        return TaskType.GENERAL

    def select_model(self, task_type: TaskType) -> ModelConfig:
        routing = self.routing_config
        provider = self._primary_provider

        if provider == Provider.OPENAI:
            model_map = {
                TaskType.VOICE: ModelConfig(
                    provider="openai",
                    model_id=routing.get("voice", "gpt-4o"),
                    task_type=TaskType.VOICE,
                ),
                TaskType.SECURITY: ModelConfig(
                    provider="openai",
                    model_id=routing.get("security", "gpt-4o"),
                    task_type=TaskType.SECURITY,
                    extended_thinking=False,
                ),
                TaskType.CODE: ModelConfig(
                    provider="openai",
                    model_id=routing.get("code", "gpt-4o"),
                    task_type=TaskType.CODE,
                ),
                TaskType.PLANNING: ModelConfig(
                    provider="openai",
                    model_id=routing.get("planning", "gpt-4o"),
                    task_type=TaskType.PLANNING,
                    extended_thinking=False,
                ),
                TaskType.QUICK: ModelConfig(
                    provider="openai",
                    model_id=routing.get("quick", "gpt-4o-mini"),
                    task_type=TaskType.QUICK,
                ),
                TaskType.GENERAL: ModelConfig(
                    provider="openai",
                    model_id=routing.get("quick", "gpt-4o-mini"),
                    task_type=TaskType.GENERAL,
                ),
            }
        else:
            model_map = {
                TaskType.VOICE: ModelConfig(
                    provider="gemini",
                    model_id=routing.get("voice", "gemini-live"),
                    task_type=TaskType.VOICE,
                ),
                TaskType.SECURITY: ModelConfig(
                    provider="anthropic",
                    model_id=routing.get("security", "claude-opus-4-7"),
                    task_type=TaskType.SECURITY,
                    extended_thinking=True,
                ),
                TaskType.CODE: ModelConfig(
                    provider="anthropic",
                    model_id=routing.get("code", "claude-sonnet-4-6"),
                    task_type=TaskType.CODE,
                ),
                TaskType.PLANNING: ModelConfig(
                    provider="anthropic",
                    model_id=routing.get("planning", "claude-opus-4-7"),
                    task_type=TaskType.PLANNING,
                    extended_thinking=True,
                ),
                TaskType.QUICK: ModelConfig(
                    provider="gemini",
                    model_id=routing.get("quick", "gemini-2.5-flash-lite"),
                    task_type=TaskType.QUICK,
                ),
                TaskType.GENERAL: ModelConfig(
                    provider="gemini",
                    model_id=routing.get("quick", "gemini-2.5-flash-lite"),
                    task_type=TaskType.GENERAL,
                ),
            }

        return model_map.get(task_type, model_map[TaskType.GENERAL])

    def get_route(self, request: str) -> tuple:
        task_type = self.classify(request)
        model_config = self.select_model(task_type)
        return task_type, model_config

    def has_anthropic_key(self) -> bool:
        return bool(self.config.get("anthropic_api_key"))

    def has_openai_key(self) -> bool:
        return bool(self.config.get("openai_api_key"))

    def has_gemini_key(self) -> bool:
        return bool(self.config.get("gemini_api_key"))

    def get_anthropic_key(self) -> Optional[str]:
        return self.config.get("anthropic_api_key")

    def get_gemini_key(self) -> Optional[str]:
        return self.config.get("gemini_api_key")

    def get_openai_key(self) -> Optional[str]:
        return self.config.get("openai_api_key")

    def is_openai_primary(self) -> bool:
        return self._primary_provider == Provider.OPENAI


_router_instance: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = ModelRouter()
    return _router_instance
