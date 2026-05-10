"""
harness_modes.py — Speed/thoroughness tradeoff modes for FRIDAY cyber pipeline.

Each mode defines: which phases to run, wave size, verification strictness,
time budget, and special behaviors.
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("friday.cyber.harness")


class HarnessMode(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"
    LOOP = "loop"
    CODE = "code"


class VerificationStrictness(str, Enum):
    SKIP = "skip"           # Skip verification entirely
    BASIC = "basic"         # One verification attempt
    STANDARD = "standard"   # Two rounds, must confirm at least one
    STRICT = "strict"       # Three rounds, must confirm twice


@dataclass
class HarnessConfig:
    """Configuration for a single harness mode."""
    name: str
    description: str
    phases: list[str]
    wave_size: int
    max_concurrency: int
    verification_strictness: VerificationStrictness
    time_budget_s: int  # seconds
    confidence_threshold: float  # minimum confidence to proceed
    skip_low_confidence_verification: bool = False
    enable_business_logic_testing: bool = False
    enable_data_flow_analysis: bool = False
    enable_static_dynamic_correlation: bool = False
    loop_max_iterations: int = 1
    loop_findings_target: int = 0  # stop when this many findings reached (0 = no target)
    triage_model: str = "default"  # "default" or "haiku" for fast triage
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "description": self.description,
            "phases": self.phases,
            "wave_size": self.wave_size,
            "max_concurrency": self.max_concurrency,
            "verification_strictness": self.verification_strictness.value,
            "time_budget_s": self.time_budget_s,
            "confidence_threshold": self.confidence_threshold,
            "skip_low_confidence_verification": self.skip_low_confidence_verification,
            "enable_business_logic_testing": self.enable_business_logic_testing,
            "enable_data_flow_analysis": self.enable_data_flow_analysis,
            "enable_static_dynamic_correlation": self.enable_static_dynamic_correlation,
            "loop_max_iterations": self.loop_max_iterations,
            "loop_findings_target": self.loop_findings_target,
            "triage_model": self.triage_model,
            "extra": self.extra,
        }
        return d


# ── Mode Definitions ──────────────────────────────────────────────

MODES: dict[str, HarnessConfig] = {
    HarnessMode.FAST: HarnessConfig(
        name="fast",
        description=(
            "Quick triage scan. RECON → triage priority scoring → "
            "1 hunter wave → grade (skip verification for low-confidence)."
        ),
        phases=["RECON", "TRIAGE", "HUNT", "GRADE", "REPORT"],
        wave_size=10,
        max_concurrency=1,
        verification_strictness=VerificationStrictness.SKIP,
        time_budget_s=300,  # 5 min
        confidence_threshold=0.3,
        skip_low_confidence_verification=True,
        triage_model="haiku",
    ),

    HarnessMode.STANDARD: HarnessConfig(
        name="standard",
        description=(
            "Full 7-phase pipeline. Balanced speed and thoroughness."
        ),
        phases=["RECON", "HUNT", "CHAIN", "VERIFY", "GRADE", "REPORT"],
        wave_size=5,
        max_concurrency=3,
        verification_strictness=VerificationStrictness.STANDARD,
        time_budget_s=1800,  # 30 min
        confidence_threshold=0.5,
    ),

    HarnessMode.DEEP: HarnessConfig(
        name="deep",
        description=(
            "Full pipeline + 3× wider waves + business logic testing + "
            "data flow analysis. Maximum thoroughness."
        ),
        phases=["RECON", "HUNT", "CHAIN", "VERIFY", "GRADE", "REPORT"],
        wave_size=15,  # 3× standard
        max_concurrency=5,
        verification_strictness=VerificationStrictness.STRICT,
        time_budget_s=7200,  # 2 hours
        confidence_threshold=0.4,
        enable_business_logic_testing=True,
        enable_data_flow_analysis=True,
    ),

    HarnessMode.LOOP: HarnessConfig(
        name="loop",
        description=(
            "Repeat standard pipeline until findings count or time budget hit."
        ),
        phases=["RECON", "HUNT", "CHAIN", "VERIFY", "GRADE", "REPORT"],
        wave_size=5,
        max_concurrency=3,
        verification_strictness=VerificationStrictness.STANDARD,
        time_budget_s=3600,  # 1 hour
        confidence_threshold=0.5,
        loop_max_iterations=5,
        loop_findings_target=20,
    ),

    HarnessMode.CODE: HarnessConfig(
        name="code",
        description=(
            "White-box mode. Static analysis → data flow → "
            "static-dynamic correlation."
        ),
        phases=["RECON", "HUNT", "CHAIN", "VERIFY", "GRADE", "REPORT"],
        wave_size=5,
        max_concurrency=3,
        verification_strictness=VerificationStrictness.STANDARD,
        time_budget_s=2400,  # 40 min
        confidence_threshold=0.4,
        enable_data_flow_analysis=True,
        enable_static_dynamic_correlation=True,
    ),
}


class Harness:
    """Resolves and manages harness mode configurations."""

    def __init__(self, mode: str = "standard"):
        self.mode = self._resolve(mode)
        self.config = MODES[self.mode]

    def _resolve(self, mode: str) -> str:
        """Resolve mode string to canonical name."""
        mode_lower = mode.lower().strip()
        if mode_lower in MODES:
            return mode_lower
        # Aliases
        aliases = {
            "quick": "fast",
            "full": "standard",
            "normal": "standard",
            "thorough": "deep",
            "deep-scan": "deep",
            "repeat": "loop",
            "whitebox": "code",
            "white-box": "code",
            "static": "code",
        }
        if mode_lower in aliases:
            return aliases[mode_lower]
        logger.warning("Unknown mode '%s', falling back to standard", mode)
        return "standard"

    def should_run_phase(self, phase: str) -> bool:
        """Check if a phase should run in this mode."""
        return phase.upper() in [p.upper() for p in self.config.phases]

    def get_phases(self) -> list[str]:
        """Get the ordered list of phases for this mode."""
        return list(self.config.phases)

    def get_wave_size(self) -> int:
        """Get wave size for this mode."""
        return self.config.wave_size

    def get_max_concurrency(self) -> int:
        """Get max concurrent agents for this mode."""
        return self.config.max_concurrency

    def get_verification_strictness(self) -> VerificationStrictness:
        """Get verification strictness level."""
        return self.config.verification_strictness

    def get_time_budget(self) -> int:
        """Get time budget in seconds."""
        return self.config.time_budget_s

    def should_verify(self, confidence: float) -> bool:
        """Determine if a finding should be verified based on mode and confidence."""
        if self.config.verification_strictness == VerificationStrictness.SKIP:
            return False
        if (self.config.skip_low_confidence_verification and
            confidence < self.config.confidence_threshold):
            return False
        return True

    def get_verification_rounds(self) -> int:
        """Get number of verification rounds based on strictness."""
        mapping = {
            VerificationStrictness.SKIP: 0,
            VerificationStrictness.BASIC: 1,
            VerificationStrictness.STANDARD: 2,
            VerificationStrictness.STRICT: 3,
        }
        return mapping.get(self.config.verification_strictness, 2)

    def get_confirmation_threshold(self) -> int:
        """How many rounds must confirm for a finding to be 'confirmed'."""
        mapping = {
            VerificationStrictness.SKIP: 0,
            VerificationStrictness.BASIC: 1,
            VerificationStrictness.STANDARD: 1,
            VerificationStrictness.STRICT: 2,
        }
        return mapping.get(self.config.verification_strictness, 1)

    def is_loop_mode(self) -> bool:
        """Check if this is a loop mode."""
        return self.mode == "loop"

    def get_loop_config(self) -> dict:
        """Get loop-specific configuration."""
        return {
            "max_iterations": self.config.loop_max_iterations,
            "findings_target": self.config.loop_findings_target,
        }

    def get_triage_model(self) -> str:
        """Get the model to use for triage (e.g., 'haiku' for fast mode)."""
        return self.config.triage_model

    def to_dict(self) -> dict:
        """Serialize the full harness config."""
        return {
            "mode": self.mode,
            "config": self.config.to_dict(),
        }


def get_harness(mode: str = "standard") -> Harness:
    """Factory for Harness instances."""
    return Harness(mode)


def list_modes() -> list[dict]:
    """List all available modes with their descriptions."""
    return [
        {
            "name": cfg.name,
            "description": cfg.description,
            "phases": cfg.phases,
            "time_budget_s": cfg.time_budget_s,
            "wave_size": cfg.wave_size,
            "verification": cfg.verification_strictness.value,
        }
        for cfg in MODES.values()
    ]
