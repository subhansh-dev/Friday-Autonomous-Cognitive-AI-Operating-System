#!/usr/bin/env python3
"""
digital_twin.py — FRIDAY Digital Twin (Writing Style Mimic)
============================================================
Learns the user's writing style from samples and drafts
messages that match their voice using Gemini.
"""

import json
import sys
from pathlib import Path
from typing import Optional, List


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


API_CONFIG_PATH = get_base_dir() / "config" / "api_keys.json"
TWIN_FILE = get_base_dir() / "brain" / "digital_twin.json"


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _generate(prompt: str, system: str = "") -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_get_api_key())
    config = types.GenerateContentConfig(
        system_instruction=system if system else None,
        max_output_tokens=1024,
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=config,
    )
    return response.text.strip()


class DigitalTwin:
    """
    Writing style mimic that learns from user samples
    and drafts messages in their voice.
    """

    PRESET_STYLES = {
        "professional": "Formal, structured, polite. Uses complete sentences and proper grammar.",
        "casual": "Relaxed, friendly, conversational. Uses contractions and informal language.",
        "techy": "Technical, precise, concise. Uses jargon and abbreviations. Direct and to the point.",
        "aggressive": "Urgent, direct, assertive. Uses strong language and action-oriented words.",
        "witty": "Clever, humorous, playful. Uses wordplay, sarcasm, and pop culture references.",
    }

    def __init__(self):
        self._samples: List[str] = []
        self._style_description: str = ""
        self._current_style: str = "professional"
        self._load()

    def _load(self):
        if TWIN_FILE.exists():
            try:
                data = json.loads(TWIN_FILE.read_text(encoding="utf-8"))
                self._samples = data.get("samples", [])
                self._style_description = data.get("style_description", "")
                self._current_style = data.get("current_style", "professional")
            except Exception:
                pass

    def _save(self):
        try:
            TWIN_FILE.parent.mkdir(parents=True, exist_ok=True)
            TWIN_FILE.write_text(json.dumps({
                "samples": self._samples[-20:],  # Keep last 20 samples
                "style_description": self._style_description,
                "current_style": self._current_style,
            }, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def set_style(self, style: str) -> str:
        if style in self.PRESET_STYLES:
            self._current_style = style
            self._style_description = self.PRESET_STYLES[style]
            self._save()
            return f"Style set to {style}: {self.PRESET_STYLES[style]}"
        return f"Unknown style '{style}'. Available: {', '.join(self.PRESET_STYLES.keys())}"

    def analyze_user_style(self, text_samples: List[str]) -> str:
        """Analyze user's writing samples to extract their unique style."""
        if not text_samples:
            return "No samples provided."

        self._samples.extend(text_samples)
        self._samples = self._samples[-20:]  # Keep last 20

        prompt = (
            "Analyze these writing samples and describe the person's writing style in 3-5 sentences. "
            "Cover: tone, formality, vocabulary, sentence structure, personality traits, "
            "common phrases, emoji usage, punctuation habits.\n\n"
            "Samples:\n" + "\n---\n".join(text_samples[:10])
        )

        system = (
            "You are a linguistic analyst. Describe writing styles precisely and objectively. "
            "Focus on patterns that can be replicated."
        )

        try:
            self._style_description = _generate(prompt, system=system)
            self._save()
            return f"Style analyzed: {self._style_description}"
        except Exception as e:
            return f"Style analysis failed: {e}"

    def draft_message(self, prompt: str, target_style: Optional[str] = None) -> str:
        """Draft a message matching the user's style or a preset style."""
        style = target_style or self._current_style

        # Determine style instruction
        if self._style_description:
            style_instruction = self._style_description
        elif style in self.PRESET_STYLES:
            style_instruction = self.PRESET_STYLES[style]
        else:
            style_instruction = "Professional and clear."

        # Build few-shot examples from samples
        examples = ""
        if self._samples:
            examples = "Here are examples of the user's actual writing:\n"
            for s in self._samples[:3]:
                examples += f"- \"{s[:150]}\"\n"

        full_prompt = (
            f"Draft a message about: {prompt}\n\n"
            f"Writing style to match:\n{style_instruction}\n\n"
            f"{examples}\n"
            f"Write the message matching this style exactly. "
            f"Output ONLY the message text, no explanation."
        )

        system = (
            "You are a writing style mimic. Draft messages that perfectly match "
            "the described style. Be authentic — write as if you ARE the person."
        )

        try:
            return _generate(full_prompt, system=system)
        except Exception as e:
            return f"Draft failed: {e}"

    def get_status(self) -> str:
        return (f"Digital Twin: style={self._current_style}, "
                f"samples={len(self._samples)}, "
                f"{'custom style learned' if self._style_description else 'using presets'}")
