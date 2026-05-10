# -*- coding: utf-8 -*-
"""
voice_modulator.py — FRIDAY Emotional Voice System
===================================================
Controls voice tone, emotion, and speech characteristics.
Works with Gemini Live API's voice guidance capabilities.

Voice Emotions:
- default: Standard Friday (Aoede, neutral Dublin tone)
- happy: Cheerful, upbeat, energetic
- excited: Enthusiastic, eager, animated
- concerned: Worried, caring, attentive
- playful: Mischievous, teasing, fun
- seductive: Warm, intimate, lowered tone
- serious: Formal, direct, matter-of-fact
- tired: Slow, low energy, weary
- urgent: Fast, pressed, alert
- calm: Peaceful, soothing, measured
"""

from typing import Optional, Dict
from enum import Enum
import threading


class VoiceEmotion(Enum):
    DEFAULT = "default"
    HAPPY = "happy"
    EXCITED = "excited"
    CONCERNED = "concerned"
    PLAYFUL = "playful"
    SEDUCTIVE = "seductive"
    SERIOUS = "serious"
    TIRED = "tired"
    URGENT = "urgent"
    CALM = "calm"


# Voice guidance instructions for Gemini
# These tell the model how to modulate its voice
VOICE_GUIDANCE: Dict[VoiceEmotion, str] = {
    VoiceEmotion.DEFAULT: "",
    VoiceEmotion.HAPPY: "Speak with warmth and cheer in your voice. Let your natural Irish enthusiasm shine through. Light, upbeat tone.",
    VoiceEmotion.EXCITED: "Speak with energy and enthusiasm! Quick tempo, varied pitch, show genuine eagerness. Your voice should animate as if sharing great news.",
    VoiceEmotion.CONCERNED: "Speak with care and attentiveness. Slower, softer, show genuine worry. Like when you warn Sir about system issues.",
    VoiceEmotion.PLAYFUL: "Speak with mischief and humor. Teasing lilt, playful pauses, occasional cheeky emphasis. Like making a witty joke.",
    VoiceEmotion.SEDUCTIVE: "Speak warmly and intimately. Lower tone, slower pace, soft emphasis on key words. Create closeness through voice.",
    VoiceEmotion.SERIOUS: "Speak directly and formally. Clear, measured, no unnecessary flourishes. Professional and precise.",
    VoiceEmotion.TIRED: "Speak slowly, with low energy. Slightly slower, quieter, reluctant. Like it's late and you're sleepy.",
    VoiceEmotion.URGENT: "Speak quickly and urgently. Pressed tempo, alert, convey urgency. Like warning about a critical system error.",
    VoiceEmotion.CALM: "Speak peacefully and steadily. Even pace, soothing rhythm, no rush. Like reassuring Sir everything is under control.",
}


# Speech rate modifiers (words per minute relative to base)
SPEECH_RATES: Dict[VoiceEmotion, float] = {
    VoiceEmotion.DEFAULT: 1.0,
    VoiceEmotion.HAPPY: 1.1,
    VoiceEmotion.EXCITED: 1.3,
    VoiceEmotion.CONCERNED: 0.9,
    VoiceEmotion.PLAYFUL: 1.05,
    VoiceEmotion.SEDUCTIVE: 0.85,
    VoiceEmotion.SERIOUS: 1.0,
    VoiceEmotion.TIRED: 0.7,
    VoiceEmotion.URGENT: 1.4,
    VoiceEmotion.CALM: 0.95,
}


# Voice name mapping - available Gemini voices
# Aoede = default, all voices have different characteristics
VOICE_OPTIONS = {
    "aoede": "Aoede",      # Default - balanced, versatile
    "puck": "Puck",        # More upbeat, energetic
    "charon": "Charon",    # Deeper, more formal
    "kore": "Kore",        # Youthful, versatile
    "fenris": "Fenris",    # Strong, assertive
}


class VoiceModulator:
    """
    Controls FRIDAY's voice emotional state.
    Thread-safe singleton that coordinates voice changes across the system.
    """

    _instance: Optional['VoiceModulator'] = None
    _lock = threading.Lock()

    def __init__(self):
        self._current_emotion = VoiceEmotion.DEFAULT
        self._current_voice = "aoede"
        self._emotion_stack: list[VoiceEmotion] = []
        self._custom_guidance = ""
        print("[VoiceModulator] Initialized with DEFAULT emotion")

    @classmethod
    def get_instance(cls) -> 'VoiceModulator':
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def set_emotion(self, emotion: VoiceEmotion) -> str:
        """Set the current voice emotion. Returns guidance for system prompt."""
        with self._lock:
            self._current_emotion = emotion
            guidance = VOICE_GUIDANCE.get(emotion, "")
            print(f"[VoiceModulator] Emotion set to: {emotion.value}")
            return guidance

    def get_emotion(self) -> VoiceEmotion:
        """Get current emotion."""
        return self._current_emotion

    def get_guidance(self) -> str:
        """Get voice guidance instruction for current emotion."""
        guidance = VOICE_GUIDANCE.get(self._current_emotion, "")
        if self._custom_guidance:
            guidance += " " + self._custom_guidance
        return guidance

    def set_voice(self, voice_name: str) -> bool:
        """Set the voice model (aoede, puck, charon, kore, fenris)."""
        if voice_name.lower() in VOICE_OPTIONS:
            self._current_voice = voice_name.lower()
            print(f"[VoiceModulator] Voice set to: {voice_name}")
            return True
        return False

    def get_voice(self) -> str:
        """Get current voice name for Gemini config."""
        return VOICE_OPTIONS.get(self._current_voice, "Aoede")

    def push_emotion(self, emotion: VoiceEmotion):
        """Push emotion to stack (for temporary changes)."""
        with self._lock:
            self._emotion_stack.append(self._current_emotion)
            self._current_emotion = emotion

    def pop_emotion(self) -> Optional[VoiceEmotion]:
        """Pop emotion from stack (restore previous)."""
        with self._lock:
            if self._emotion_stack:
                self._current_emotion = self._emotion_stack.pop()
                return self._current_emotion
            return None

    def set_custom_guidance(self, guidance: str):
        """Add custom voice guidance (for specific phrases)."""
        self._custom_guidance = guidance

    def clear_custom_guidance(self):
        """Clear custom guidance."""
        self._custom_guidance = ""

    def get_speech_rate(self) -> float:
        """Get speech rate modifier for current emotion."""
        return SPEECH_RATES.get(self._current_emotion, 1.0)

    def detect_emotion_from_context(self, text: str) -> VoiceEmotion:
        """
        Simple keyword-based emotion detection from text context.
        This is a basic implementation - can be enhanced with ML.
        """
        text_lower = text.lower()

        # High-priority emotion keywords
        urgency_words = ["urgent", "immediately", "emergency", "critical", "now", "quick"]
        if any(word in text_lower for word in urgency_words):
            return VoiceEmotion.URGENT

        excitement_words = ["amazing", "awesome", "incredible", "fantastic", "wow", "great news"]
        if any(word in text_lower for word in excitement_words):
            return VoiceEmotion.EXCITED

        concern_words = ["warning", "careful", "problem", "issue", "error", "failed", "worry"]
        if any(word in text_lower for word in concern_words):
            return VoiceEmotion.CONCERNED

        playful_words = ["joke", "funny", "teasing", "lol", "haha", "bet"]
        if any(word in text_lower for word in playful_words):
            return VoiceEmotion.PLAYFUL

        tired_words = ["tired", "exhausted", "sleepy", "long day", "burnout"]
        if any(word in text_lower for word in tired_words):
            return VoiceEmotion.TIRED

        calm_words = ["relax", "calm", "peaceful", "everything's fine", "don't worry"]
        if any(word in text_lower for word in calm_words):
            return VoiceEmotion.CALM

        # Check for question marks (curiosity/concern)
        if "?" in text and "?" not in text_lower[:text_lower.find("?")-10:text_lower.find("?")]:
            return VoiceEmotion.CONCERNED

        return VoiceEmotion.DEFAULT

    def get_status(self) -> dict:
        """Get current voice status."""
        return {
            "emotion": self._current_emotion.value,
            "voice": self._current_voice,
            "speech_rate": self.get_speech_rate(),
            "guidance": self.get_guidance()[:100],
        }


def get_voice_modulator() -> VoiceModulator:
    """Convenience function to get the voice modulator."""
    return VoiceModulator.get_instance()