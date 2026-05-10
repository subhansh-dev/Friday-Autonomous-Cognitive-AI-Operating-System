"""
skills/engine/skill_registry.py — Centralized Skill Registry
Replaces hardcoded TOOL_DECLARATIONS in main.py.
Follows Mythos-Skills P1-P8 principles.
"""

from pathlib import Path
from typing import Optional

SKILLS_DIR = Path(__file__).resolve().parent.parent / "definitions"


class SkillDefinition:
    """A single skill definition following Mythos-Skills format."""

    def __init__(self, name: str, trigger: str, freedom: str = "medium",
                 gotchas: list = None, description: str = "",
                 parameters: dict = None):
        self.name = name
        self.trigger = trigger
        self.freedom = freedom
        self.gotchas = gotchas or []
        self.description = description
        self.parameters = parameters or {}

    def to_tool_declaration(self) -> dict:
        return {
            "name": self.name,
            "description": self.trigger,
            "parameters": self.parameters,
        }

    def to_compact_metadata(self) -> str:
        lines = [f"**{self.name}**: {self.trigger}"]
        if self.gotchas:
            lines.append(f"  Gotchas: {'; '.join(self.gotchas[:2])}")
        return "\n".join(lines)


class SkillRegistry:
    """Central registry of all Friday skills."""

    def __init__(self):
        self.skills: dict = {}
        self._load_builtin_skills()

    def _load_builtin_skills(self):
        builtin_skills = [
            SkillDefinition(
                name="security_tools",
                trigger="When the user asks about security scanning, vulnerability analysis, penetration testing, bug bounty, or cybersecurity",
                freedom="low",
                gotchas=["Requires target path to exist", "Large codebases may timeout", "WSL Kali tools must be installed separately"],
                parameters={"type": "object", "properties": {"target": {"type": "string"}, "scan_type": {"type": "string", "enum": ["full", "quick", "recon", "secrets"]}}, "required": ["target"]},
            ),
            SkillDefinition(
                name="browser_control",
                trigger="When the user wants to navigate websites, fill forms, take screenshots of web pages, or automate browser actions",
                freedom="medium",
                gotchas=["Playwright must be installed", "Some sites block automation"],
                parameters={"type": "object", "properties": {"action": {"type": "string"}, "url": {"type": "string"}}, "required": ["action"]},
            ),
            SkillDefinition(
                name="code_helper",
                trigger="When the user wants to write, edit, run, or debug code",
                freedom="high",
                gotchas=["Code execution is sandboxed", "Long-running scripts may timeout"],
                parameters={"type": "object", "properties": {"action": {"type": "string", "enum": ["write", "edit", "run", "debug"]}, "code": {"type": "string"}}, "required": ["action"]},
            ),
            SkillDefinition(
                name="computer_control",
                trigger="When the user wants to control mouse, keyboard, take screenshots, or interact with the desktop",
                freedom="medium",
                gotchas=["pyautogui must be installed", "Screen resolution affects coordinates"],
                parameters={"type": "object", "properties": {"action": {"type": "string"}, "target": {"type": "string"}}, "required": ["action"]},
            ),
            SkillDefinition(
                name="computer_settings",
                trigger="When the user wants to adjust volume, brightness, WiFi, power settings, or system shortcuts",
                freedom="low",
                gotchas=["Windows-only (pycaw, pywinauto)", "Some settings require admin"],
                parameters={"type": "object", "properties": {"setting": {"type": "string"}, "value": {"type": "string"}}, "required": ["setting"]},
            ),
            SkillDefinition(
                name="file_controller",
                trigger="When the user wants to create, read, delete, search, or manage files and directories",
                freedom="medium",
                gotchas=["Deletions are permanent", "Large file searches may be slow"],
                parameters={"type": "object", "properties": {"action": {"type": "string"}, "path": {"type": "string"}}, "required": ["action", "path"]},
            ),
            SkillDefinition(
                name="web_search",
                trigger="When the user wants to search the web for information",
                freedom="high",
                gotchas=["Results depend on DuckDuckGo availability"],
                parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            ),
            SkillDefinition(
                name="weather_report",
                trigger="When the user asks about weather conditions or forecast",
                freedom="high",
                gotchas=["Uses DuckDuckGo — may not always have current data"],
                parameters={"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]},
            ),
            SkillDefinition(
                name="youtube_video",
                trigger="When the user wants to search, play, or summarize YouTube videos",
                freedom="medium",
                gotchas=["Requires yt-dlp for playback", "Age-restricted videos may fail"],
                parameters={"type": "object", "properties": {"action": {"type": "string"}, "query": {"type": "string"}}, "required": ["action", "query"]},
            ),
            SkillDefinition(
                name="open_app",
                trigger="When the user wants to open or launch an application",
                freedom="medium",
                gotchas=["App must be installed", "Some apps require full path"],
                parameters={"type": "object", "properties": {"app_name": {"type": "string"}}, "required": ["app_name"]},
            ),
            SkillDefinition(
                name="send_message",
                trigger="When the user wants to send a message via WhatsApp or Telegram",
                freedom="low",
                gotchas=["Requires valid contacts", "Message text is sent as-is"],
                parameters={"type": "object", "properties": {"platform": {"type": "string"}, "contact": {"type": "string"}, "message": {"type": "string"}}, "required": ["platform", "contact", "message"]},
            ),
            SkillDefinition(
                name="reminder",
                trigger="When the user wants to set a reminder or schedule a task",
                freedom="medium",
                gotchas=["Uses Windows Task Scheduler", "Reminder time must be in the future"],
                parameters={"type": "object", "properties": {"message": {"type": "string"}, "time": {"type": "string"}}, "required": ["message", "time"]},
            ),
            SkillDefinition(
                name="flight_finder",
                trigger="When the user wants to search for flights",
                freedom="medium",
                gotchas=["Uses Google Flights — results depend on availability"],
                parameters={"type": "object", "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}, "date": {"type": "string"}}, "required": ["origin", "destination"]},
            ),
            SkillDefinition(
                name="desktop",
                trigger="When the user wants to change wallpaper, organize desktop, or get desktop stats",
                freedom="medium",
                gotchas=["Wallpaper path must exist", "Organize moves files"],
                parameters={"type": "object", "properties": {"action": {"type": "string"}}, "required": ["action"]},
            ),
            SkillDefinition(
                name="screen_process",
                trigger="When the user wants to capture the screen or camera and analyze it with vision",
                freedom="medium",
                gotchas=["Camera index must be configured", "Spawns daemon thread"],
                parameters={"type": "object", "properties": {"source": {"type": "string", "enum": ["screen", "camera"]}}, "required": ["source"]},
            ),
            SkillDefinition(
                name="game_updater",
                trigger="When the user wants to check or manage game updates on Steam or Epic Games",
                freedom="medium",
                gotchas=["Requires Steam/Epic to be installed"],
                parameters={"type": "object", "properties": {"platform": {"type": "string"}, "action": {"type": "string"}}, "required": ["platform"]},
            ),
            SkillDefinition(
                name="dev_agent",
                trigger="When the user wants to build a multi-file project from a description",
                freedom="high",
                gotchas=["Complex projects may need multiple iterations"],
                parameters={"type": "object", "properties": {"description": {"type": "string"}, "language": {"type": "string"}}, "required": ["description"]},
            ),
            SkillDefinition(
                name="ai_pipeline",
                trigger="When the user wants to run an AI analysis pipeline on data",
                freedom="high",
                gotchas=["Large datasets may take time"],
                parameters={"type": "object", "properties": {"pipeline_type": {"type": "string"}, "data": {"type": "string"}}, "required": ["pipeline_type"]},
            ),
            SkillDefinition(
                name="web_research",
                trigger="When the user wants deep research on a topic using multiple web sources",
                freedom="high",
                gotchas=["Results depend on web availability"],
                parameters={"type": "object", "properties": {"topic": {"type": "string"}, "depth": {"type": "string"}}, "required": ["topic"]},
            ),
            SkillDefinition(
                name="ac_controller",
                trigger="When the user wants to control the air conditioner",
                freedom="low",
                gotchas=["Requires AC brand config", "Broadlink must be on same network"],
                parameters={"type": "object", "properties": {"action": {"type": "string"}, "temperature": {"type": "number"}}, "required": ["action"]},
            ),
            SkillDefinition(
                name="agency_agent",
                trigger="When the user wants a specialized agent to handle a complex sub-task",
                freedom="high",
                gotchas=["Agent spawns sub-session"],
                parameters={"type": "object", "properties": {"task": {"type": "string"}, "agent_type": {"type": "string"}}, "required": ["task"]},
            ),
            SkillDefinition(
                name="verification",
                trigger="When the user wants to verify the result of a previous action",
                freedom="medium",
                gotchas=["Checks file existence, output correctness"],
                parameters={"type": "object", "properties": {"action_id": {"type": "string"}}, "required": ["action_id"]},
            ),
            SkillDefinition(
                name="holographic_map",
                trigger="When the user wants to view or interact with a holographic map visualization",
                freedom="medium",
                gotchas=["Requires display"],
                parameters={"type": "object", "properties": {"action": {"type": "string"}, "location": {"type": "string"}}, "required": ["action"]},
            ),
            SkillDefinition(
                name="holo_earth",
                trigger="When the user wants to open Google Earth with gesture control, or use the holo earth globe",
                freedom="medium",
                gotchas=["Requires webcam, Edge browser, and MediaPipe hand model"],
                parameters={"type": "object", "properties": {"action": {"type": "string"}}, "required": ["action"]},
            ),
            SkillDefinition(
                name="holo_builder",
                trigger="When the user wants to build or modify holographic 3D models",
                freedom="high",
                gotchas=["Complex models may take time"],
                parameters={"type": "object", "properties": {"action": {"type": "string"}, "model_type": {"type": "string"}}, "required": ["action"]},
            ),
        ]

        for skill in builtin_skills:
            self.skills[skill.name] = skill

    def register(self, skill: SkillDefinition):
        self.skills[skill.name] = skill

    def get(self, name: str) -> Optional[SkillDefinition]:
        return self.skills.get(name)

    def get_all(self) -> list:
        return list(self.skills.values())

    def get_tool_declarations(self) -> list:
        return [skill.to_tool_declaration() for skill in self.skills.values()]

    def get_compact_metadata(self) -> str:
        return "\n".join(skill.to_compact_metadata() for skill in self.skills.values())

    def load_from_files(self):
        if not SKILLS_DIR.exists():
            return

        for md_file in SKILLS_DIR.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                skill = self._parse_skill_md(md_file.stem, content)
                if skill:
                    self.skills[skill.name] = skill
            except Exception:
                continue

    def _parse_skill_md(self, name: str, content: str) -> Optional[SkillDefinition]:
        if not content.startswith("---"):
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        frontmatter = parts[1].strip()
        body = parts[2].strip()

        fields = {}
        for line in frontmatter.split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                fields[key.strip()] = value.strip()

        gotchas = []
        if "gotchas" in fields:
            gotchas_text = fields["gotchas"]
            if gotchas_text.startswith("["):
                gotchas = [g.strip().strip('"').strip("'")
                           for g in gotchas_text.strip("[]").split(",")]

        return SkillDefinition(
            name=fields.get("name", name),
            trigger=fields.get("trigger", body.split("\n")[0] if body else ""),
            freedom=fields.get("freedom", "medium"),
            gotchas=gotchas,
            description=body,
        )


_registry_instance: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = SkillRegistry()
        _registry_instance.load_from_files()
    return _registry_instance
