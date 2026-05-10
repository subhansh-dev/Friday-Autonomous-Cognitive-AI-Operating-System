"""
skills/engine/skill_loader.py — Progressive Disclosure Skill Loader
Loads compact metadata first, full details on demand.
Mythos-Skills P1 (Concise is Key) + P2 (Progressive Disclosure).
"""

from pathlib import Path
from typing import Optional

from skills.engine.skill_registry import get_skill_registry, SkillDefinition


class SkillLoader:
    """Loads skill metadata with progressive disclosure."""

    def __init__(self):
        self.registry = get_skill_registry()

    def get_compact_declarations(self) -> list:
        """Get compact tool declarations for the Gemini session.
        Only includes name + trigger — full details loaded on demand."""
        declarations = []
        for skill in self.registry.get_all():
            declarations.append({
                "name": skill.name,
                "description": skill.trigger,
                "parameters": skill.parameters,
            })
        return declarations

    def get_full_skill(self, name: str) -> Optional[str]:
        """Get full skill details when a tool is actually invoked."""
        skill = self.registry.get(name)
        if not skill:
            return None

        lines = [f"# {skill.name}", "", skill.trigger, ""]
        if skill.gotchas:
            lines.append("## Gotchas")
            for g in skill.gotchas:
                lines.append(f"- {g}")
            lines.append("")
        if skill.description:
            lines.append("## Details")
            lines.append(skill.description)
        return "\n".join(lines)

    def get_skill_for_prompt(self) -> str:
        """Get all skills formatted for system prompt injection."""
        metadata = self.registry.get_compact_metadata()
        return f"Available tools:\n{metadata}"


_loader_instance: Optional[SkillLoader] = None


def get_skill_loader() -> SkillLoader:
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = SkillLoader()
    return _loader_instance
