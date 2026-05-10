"""
actions.py — FRIDAY Gesture Music Controller
Global media key control with debouncing and DJ features.
"""

import time
import pyautogui
import subprocess
import sys


# ── Debounce / Cooldown ────────────────────────────────────────────

_DEBOUNCE_SECONDS = 0.5    # [#1] Prevent spam — minimum gap between same action
_last_action_time: dict[str, float] = {}


def _can_fire(action: str) -> bool:
    """Debounce check — prevents spamming the same action rapidly."""
    now = time.monotonic()
    last = _last_action_time.get(action, 0.0)
    if now - last < _DEBOUNCE_SECONDS:
        return False
    _last_action_time[action] = now
    return True


# ── Media Controller ───────────────────────────────────────────────

class MusicController:
    def __init__(self):
        self._playing = False       # [#2] Track state internally
        self._volume = 50           # 0-100 scale
        self._muted = False
        self._bass_boost = False
        # Disable pyautogui failsafe pause (speed) but keep failsafe
        pyautogui.PAUSE = 0.05
        print("[Music] Global Media Controller initialized")

    # ── Playback ───────────────────────────────────────────────────

    def play(self):
        """Play — only fires if not already playing."""  # [#3]
        if not _can_fire("play"):
            return
        if not self._playing:
            pyautogui.press("playpause")
            self._playing = True
            print("[Music] ▶ Play")
        else:
            print("[Music] ▶ Already playing — skipped")

    def pause(self):
        """Pause — only fires if currently playing."""  # [#3]
        if not _can_fire("pause"):
            return
        if self._playing:
            pyautogui.press("playpause")
            self._playing = False
            print("[Music] ⏸ Pause")
        else:
            print("[Music] ⏸ Already paused — skipped")

    def toggle_play_pause(self):
        """Explicit toggle — use when you actually want to flip state."""
        if not _can_fire("toggle"):
            return
        pyautogui.press("playpause")
        self._playing = not self._playing
        state = "playing" if self._playing else "paused"
        print(f"[Music] ⏯ Toggled → {state}")

    def stop(self):
        if not _can_fire("stop"):
            return
        pyautogui.press("stop")
        self._playing = False
        print("[Music] ⏹ Stop")

    # ── Track Navigation ───────────────────────────────────────────

    def next_track(self):
        if not _can_fire("next"):
            return
        pyautogui.press("nexttrack")
        self._playing = True  # [#4] Next track auto-plays
        print("[Music] ⏭ Next Track")

    def prev_track(self):
        if not _can_fire("prev"):
            return
        pyautogui.press("prevtrack")
        self._playing = True
        print("[Music] ⏮ Previous Track")

    # ── Volume ─────────────────────────────────────────────────────

    def volume_up(self, steps: int = 1):
        if not _can_fire("vol_up"):
            return
        for _ in range(min(steps, 10)):  # [#5] Cap at 10 steps per call
            pyautogui.press("volumeup")
        self._volume = min(100, self._volume + steps * 5)
        self._muted = False
        print(f"[Music] 🔊 Volume Up → {self._volume}%")

    def volume_down(self, steps: int = 1):
        if not _can_fire("vol_down"):
            return
        for _ in range(min(steps, 10)):
            pyautogui.press("volumedown")
        self._volume = max(0, self._volume - steps * 5)
        print(f"[Music] 🔉 Volume Down → {self._volume}%")

    def set_volume_percent(self, percent: int):
        """Set volume to a specific percentage (0-100)."""
        percent = max(0, min(100, percent))
        if not _can_fire("set_vol"):
            return
        # [#6] Calculate direction and steps needed
        diff = percent - self._volume
        if abs(diff) < 3:
            return  # Close enough, don't spam keys
        steps = abs(diff) // 5
        direction = "volumeup" if diff > 0 else "volumedown"
        for _ in range(min(steps, 20)):
            pyautogui.press(direction)
        self._volume = percent
        self._muted = False
        print(f"[Music] 🔊 Volume set → {self._volume}%")

    def toggle_mute(self):
        if not _can_fire("mute"):
            return
        pyautogui.press("volumemute")
        self._muted = not self._muted
        state = "muted" if self._muted else "unmuted"
        print(f"[Music] 🔇 {state}")

    # ── DJ Features ────────────────────────────────────────────────

    def fast_forward(self, seconds: int = 5):
        """Skip forward in current track."""  # [#7]
        if not _can_fire("ffwd"):
            return
        for _ in range(seconds):
            pyautogui.press("right")  # Works in most media players
        print(f"[Music] ⏩ +{seconds}s")

    def rewind(self, seconds: int = 5):
        """Skip backward in current track."""
        if not _can_fire("rewind"):
            return
        for _ in range(seconds):
            pyautogui.press("left")
        print(f"[Music] ⏪ -{seconds}s")

    def seek_to_percent(self, percent: int):
        """Seek to position in track (0=start, 100=end)."""
        if not _can_fire("seek"):
            return
        percent = max(0, min(100, percent))
        # [#8] Use click on progress bar — platform-specific
        # For now, use keyboard scrub as approximation
        if percent < 50:
            for _ in range(10):
                pyautogui.press("left")
        else:
            for _ in range(10):
                pyautogui.press("right")
        print(f"[Music] ⏩ Seek → ~{percent}%")

    def bass_boost_toggle(self):
        """Toggle bass boost via Windows audio enhancements."""  # [#9]
        if not _can_fire("bass"):
            return
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            
            bass_boost = volume.GetBassBoost()
            new_bass = 0 if bass_boost > 0 else 100
            volume.SetBassBoost(new_bass)
            volume.CommitConfig()
            
            self._bass_boost = new_bass > 0
            state = "ON" if self._bass_boost else "OFF"
            print(f"[Music] 🎵 Bass boost {state}")
        except Exception as e:
            print(f"[Music] ⚠️ Bass boost not supported: {e}")

    def crossfade_hint(self, direction: str):
        """Visual hint for crossfade — actual crossfade needs DJ software."""
        if not _can_fire("xfade"):
            return
        if direction == "left":
            print("[Music] 🎚 Crossfade ← (shift to previous)")
            pyautogui.press("prevtrack")
        elif direction == "right":
            print("[Music] 🎚 Crossfade → (shift to next)")
            pyautogui.press("nexttrack")

    def shuffle_toggle(self):
        if not _can_fire("shuffle"):
            return
        # Most platforms: Ctrl+S or media key
        pyautogui.hotkey("ctrl", "s")
        print("[Music] 🔀 Shuffle toggled")

    def repeat_toggle(self):
        if not _can_fire("repeat"):
            return
        pyautogui.hotkey("ctrl", "r")
        print("[Music] 🔁 Repeat toggled")

    # ── State ──────────────────────────────────────────────────────

    def get_state(self) -> dict:
        return {
            "playing": self._playing,
            "volume": self._volume,
            "muted": self._muted,
            "bass_boost": self._bass_boost,
        }


# ── Action Router ──────────────────────────────────────────────────

# [#10] All available actions mapped — used by gesture system
ACTION_MAP = {
    "PLAY":           lambda c: c.play(),
    "PAUSE":          lambda c: c.pause(),
    "TOGGLE":         lambda c: c.toggle_play_pause(),
    "STOP":           lambda c: c.stop(),
    "NEXT":           lambda c: c.next_track(),
    "PREV":           lambda c: c.prev_track(),
    "VOLUME_UP":      lambda c: c.volume_up(),
    "VOLUME_DOWN":    lambda c: c.volume_down(),
    "MUTE":           lambda c: c.toggle_mute(),
    "FAST_FORWARD":   lambda c: c.fast_forward(),
    "REWIND":         lambda c: c.rewind(),
    "SHUFFLE":        lambda c: c.shuffle_toggle(),
    "REPEAT":         lambda c: c.repeat_toggle(),
    "CROSSFADE_LEFT": lambda c: c.crossfade_hint("left"),
    "CROSSFADE_RIGHT":lambda c: c.crossfade_hint("right"),
}


def execute_action(action_name: str, controller: MusicController):
    """Execute a named action on the controller."""
    action = ACTION_MAP.get(action_name.upper())
    if action:
        action(controller)
    else:
        print(f"[Music] Unknown action: {action_name}")


def get_available_actions() -> list[str]:
    """Return list of all available action names."""
    return list(ACTION_MAP.keys())
