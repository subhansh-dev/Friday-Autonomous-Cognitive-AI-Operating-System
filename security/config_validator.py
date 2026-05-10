import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any, Optional


REQUIRED_SECRETS = {
    "gemini_api_key": r"^[A-Za-z0-9_-]{20,}$",
}

ACCEPTED_OS_VALUES = {"windows", "mac", "linux"}


class ConfigValidationError(Exception):
    pass


class ConfigValidator:
    def __init__(self):
        self._config: dict = {}
        self._loaded = False

    def load(self, path: Optional[Path] = None) -> dict:
        if path is None:
            base = self._get_base_dir()
            path = base / "config" / "api_keys.json"

        if not path.exists():
            raise ConfigValidationError(f"Config file not found: {path}")

        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ConfigValidationError(f"Invalid JSON in config: {e}")
        except IOError as e:
            raise ConfigValidationError(f"Cannot read config: {e}")

        self._config = data
        self._loaded = True
        return data

    def validate(self, data: Optional[dict] = None) -> list[str]:
        errors = []
        cfg = data or self._config

        for key, pattern in REQUIRED_SECRETS.items():
            val = cfg.get(key, "")
            if not val:
                errors.append(f"Missing required secret: {key}")
            elif key in ("gemini_api_key",) and not re.match(pattern, str(val)):
                errors.append(f"{key} has invalid format (expected alphanumeric, 20+ chars)")

        os_val = cfg.get("os_system", "").lower()
        if os_val and os_val not in ACCEPTED_OS_VALUES:
            errors.append(f"Invalid os_system '{os_val}'. Must be one of: {', '.join(sorted(ACCEPTED_OS_VALUES))}")

        self._check_exposed_secrets(cfg, errors)

        return errors

    def validate_or_fail(self, data: Optional[dict] = None):
        errors = self.validate(data)
        if errors:
            msg = "\n".join(errors)
            raise ConfigValidationError(f"Config validation failed:\n{msg}")

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def get_api_key(self) -> str:
        key = self.get("gemini_api_key", "")
        if not key:
            raise ConfigValidationError("gemini_api_key not loaded. Call load() first.")
        return key

    def get_os(self) -> str:
        return self.get("os_system", "windows").lower()

    def get_safe_config(self) -> dict:
        safe = {}
        for k, v in self._config.items():
            if k in REQUIRED_SECRETS or "key" in k.lower() or "token" in k.lower() or "password" in k.lower() or "secret" in k.lower():
                safe[k] = "***REDACTED***"
            else:
                safe[k] = v
        return safe

    @staticmethod
    def _get_base_dir() -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent
        return Path(__file__).resolve().parent.parent

    @staticmethod
    def _check_exposed_secrets(cfg: dict, errors: list[str]):
        val = cfg.get("gemini_api_key", "")
        if val and len(val) > 10:
            for k, v in cfg.items():
                if k == "gemini_api_key":
                    continue
                if isinstance(v, str) and val in v:
                    errors.append(f"Secret gemini_api_key appears in field '{k}' — potential exposure")

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def config(self) -> dict:
        return dict(self._config)


_validator: Optional[ConfigValidator] = None
_validator_lock = threading.Lock()



def get_config_validator() -> ConfigValidator:
    global _validator, _validator_lock
    if _validator is None:
        with _validator_lock:
            if _validator is None:
                _validator = ConfigValidator()
    return _validator
