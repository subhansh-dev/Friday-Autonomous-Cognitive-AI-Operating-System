# -*- coding: utf-8 -*-
"""
FRIDAY Holo Earth — Gesture-Controlled Google Earth
=====================================================
Replaces the broken CesiumJS localhost globe with Google Earth in Edge app mode.
Gestures are GLOBAL — they control whatever window is focused.

Architecture:
  Webcam → MediaPipe (hand landmarks) → Gesture Classifier → pyautogui → Google Earth

Gesture Map:
  palm_open    → Stop / cancel drag (release mouse)
  fist         → Zoom in (scroll up at globe center)
  point        → Rotate/drag camera (left-click drag from center)
  peace        → Zoom out (scroll down at globe center)
  pinch        → Tilt down (right-click drag down)
  spread       → Tilt up (right-click drag up)
  swipe_left   → Rotate left (right-click drag left)
  swipe_right  → Rotate right (right-click drag right)
  swipe_up     → Pitch up (scroll up + tilt)
  swipe_down   → Pitch down (scroll down + tilt)
  stop         → Pause gesture input (toggle)

HUD overlay is a transparent tkinter window pinned on top.

NOTE: Google Earth web ONLY responds to mouse interactions at the globe
position. Keyboard shortcuts (Ctrl+Left, arrows, etc.) do NOT work.
All actions use mouse move/drag/scroll at screen center where the globe is.
"""

import os
import time
import math
import threading
import subprocess
import webbrowser
from pathlib import Path
from collections import deque, Counter
from typing import Optional

# ── Suppress TF/MediaPipe noise ───────────────────────────────────────
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '2'

# ── Paths ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
HAND_MODEL = str(BASE_DIR / "brain" / "hand_landmarker.task")
FACE_MODEL = str(BASE_DIR / "brain" / "face_landmarker.task")

# ── Config ────────────────────────────────────────────────────────────
CAM_INDEX = 0
CAM_W, CAM_H = 640, 480
GESTURE_COOLDOWN = 0.6        # seconds between gesture actions
STABLE_REQUIRED = 4           # consecutive matching frames before action
SMOOTHING_ALPHA = 0.45        # hand position smoothing (higher = more responsive)
DRAG_SENSITIVITY = 3.5        # multiplier for drag movement (pixels per hand delta)
SCROLL_AMOUNT = 3             # scroll ticks per gesture
DRAG_STEP_PX = 120            # pixels per drag step for rotation/tilt

# Eye tracking config
GAZE_SMOOTHING = 0.35         # gaze position smoothing (lower = smoother)
GAZE_DEAD_ZONE = 0.04         # ignore gaze drift below this threshold
BLINK_CLICK_THRESHOLD = 0.25  # seconds of sustained close = intentional blink click
BLINK_COOLDOWN = 1.0          # seconds between blink clicks
EYE_ENABLED = True            # enable/disable eye tracking

# ── Colors for terminal ───────────────────────────────────────────────
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_DIM = "\033[90m"
C_BOLD = "\033[1m"
C_RESET = "\033[0m"


def _log(msg, color=C_CYAN):
    ts = time.strftime("%H:%M:%S")
    print(f"{C_DIM}[{ts}]{C_RESET} {color}{C_BOLD}FRIDAY{C_RESET} ▸ {msg}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GESTURE CLASSIFIER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class GestureClassifier:
    """Classifies hand gestures from MediaPipe hand landmarks."""

    GESTURES = ("open", "fist", "point", "peace", "pinch", "spread", "none")

    def __init__(self, buffer_size=5):
        self._buffer = deque(maxlen=buffer_size)

    def classify(self, landmarks) -> str:
        if not landmarks or len(landmarks) < 21:
            return "none"

        lm = landmarks
        tips = [4, 8, 12, 16, 20]
        mcps = [1, 5, 9, 13, 17]

        # Thumb: compare x (right hand assumption)
        ext = [lm[tips[0]].x > lm[mcps[0]].x]
        # Other fingers: tip above MCP (lower y = higher on screen)
        for t, m in zip(tips[1:], mcps[1:]):
            ext.append(lm[t].y < lm[m].y)

        # Pinch distance: thumb tip to index tip
        pinch_dist = math.hypot(lm[4].x - lm[8].x, lm[4].y - lm[8].y)

        # Classify
        if pinch_dist < 0.055 and ext[1]:
            raw = "pinch"
        elif pinch_dist > 0.15 and ext[0] and ext[1] and not ext[2] and not ext[3]:
            raw = "spread"
        elif all(ext):
            raw = "open"
        elif not any(ext):
            raw = "fist"
        elif ext[1] and ext[2] and not ext[0] and not ext[3] and not ext[4]:
            raw = "peace"
        elif ext[1] and not ext[2] and not ext[3] and not ext[4]:
            raw = "point"
        else:
            raw = "open"

        self._buffer.append(raw)
        if self._buffer:
            return Counter(self._buffer).most_common(1)[0][0]
        return raw


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SWIPE DETECTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class SwipeDetector:
    """Detects swipe gestures from hand position history."""

    def __init__(self, min_distance=0.10, max_time=0.5):
        self._positions = deque(maxlen=15)
        self._min_distance = min_distance
        self._max_time = max_time

    def add_position(self, x: float, y: float):
        self._positions.append((x, y, time.monotonic()))

    def detect(self) -> Optional[str]:
        if len(self._positions) < 4:
            return None

        recent = list(self._positions)
        now = time.monotonic()
        recent = [(x, y, t) for x, y, t in recent if now - t < self._max_time]
        if len(recent) < 3:
            return None

        start_x, start_y, _ = recent[0]
        end_x, end_y, _ = recent[-1]
        dx = end_x - start_x
        dy = end_y - start_y
        dist = math.hypot(dx, dy)

        if dist < self._min_distance:
            return None

        if abs(dx) > abs(dy):
            return "right" if dx > 0 else "left"
        else:
            return "down" if dy > 0 else "up"

    def clear(self):
        self._positions.clear()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EYE TRACKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class EyeTracker:
    """
    Tracks eye state (open/closed) and gaze direction from face landmarks.

    Uses MediaPipe face landmarker (478 landmarks).
    Key landmarks:
      133 = left eye inner corner
      362 = right eye inner corner
      1   = nose tip (gaze anchor)
      159 = left eye top lid
      145 = left eye bottom lid
      386 = right eye top lid
      374 = right eye bottom lid
    """

    def __init__(self):
        self.eyes_open = True
        self.gaze = (0.5, 0.5)
        self.blink = False
        self._closed_start = 0.0
        self._blink_threshold = BLINK_CLICK_THRESHOLD

    def update(self, face_landmarks):
        """Update eye state from face landmarks."""
        if not face_landmarks or len(face_landmarks) < 478:
            self.eyes_open = True
            self.blink = False
            return

        lm = face_landmarks

        # Eye open: top lid above bottom lid
        left_open = lm[159].y < lm[145].y
        right_open = lm[386].y < lm[374].y
        self.eyes_open = left_open and right_open

        # Gaze: average of inner eye corners + nose bridge
        ax = (lm[133].x + lm[362].x + lm[1].x) / 3
        ay = (lm[133].y + lm[362].y + lm[1].y) / 3
        self.gaze = (ax, ay)

        # Sustained blink detection — must keep eyes closed for threshold
        now = time.monotonic()
        if not self.eyes_open:
            if self._closed_start == 0:
                self._closed_start = now
            elif now - self._closed_start >= self._blink_threshold:
                self.blink = True
        else:
            self._closed_start = 0
            self.blink = False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EYE CONTROLLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class EyeController:
    """
    Maps eye gaze to cursor movement and blink to click.

    Gaze coordinates from MediaPipe are normalized (0-1).
    We map them to screen pixels with smoothing and dead zone.
    Webcam is mirrored (cv2.flip), so we invert X.
    """

    def __init__(self):
        self._pyag = None
        self._smoothed_gaze = None
        self._last_blink_time = 0.0
        self._last_gaze_action = ""

    def _ensure_pyautogui(self):
        if self._pyag is None:
            import pyautogui
            pyautogui.PAUSE = 0.02
            pyautogui.FAILSAFE = True
            self._pyag = pyautogui

    def process_gaze(self, gaze: tuple, blink: bool):
        """
        Process gaze position and blink state.
        Moves cursor toward gaze position. Blink = click at cursor.
        """
        self._ensure_pyautogui()

        # Webcam is mirrored — invert X
        raw_x = 1.0 - gaze[0]
        raw_y = gaze[1]

        # Smooth the gaze position
        if self._smoothed_gaze is None:
            self._smoothed_gaze = (raw_x, raw_y)
        else:
            sx = GAZE_SMOOTHING * raw_x + (1 - GAZE_SMOOTHING) * self._smoothed_gaze[0]
            sy = GAZE_SMOOTHING * raw_y + (1 - GAZE_SMOOTHING) * self._smoothed_gaze[1]
            self._smoothed_gaze = (sx, sy)

        # Apply dead zone — ignore small drift
        # (We still update smoothed_gaze, just don't move cursor)
        screen_w, screen_h = self._pyag.size()
        target_x = int(self._smoothed_gaze[0] * screen_w)
        target_y = int(self._smoothed_gaze[1] * screen_h)

        # Move cursor toward gaze position (smooth, not instant)
        current_x, current_y = self._pyag.position()
        dx = target_x - current_x
        dy = target_y - current_y

        # Only move if delta is significant (dead zone in pixels)
        dead_px = int(GAZE_DEAD_ZONE * min(screen_w, screen_h))
        if abs(dx) > dead_px or abs(dy) > dead_px:
            # Move 30% of the way toward target (smooth follow)
            move_x = current_x + int(dx * 0.3)
            move_y = current_y + int(dy * 0.3)
            self._pyag.moveTo(move_x, move_y, _pause=False)

        # Handle blink → click
        if blink:
            now = time.monotonic()
            if now - self._last_blink_time > BLINK_COOLDOWN:
                self._pyag.click(target_x, target_y)
                self._last_blink_time = now
                self._last_gaze_action = "blink_click"
                _log(f"👁 Blink click at ({target_x}, {target_y})")

    def cleanup(self):
        """Reset state."""
        self._smoothed_gaze = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GOOGLE EARTH CONTROLLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class EarthController:
    """
    Translates gestures to mouse inputs for Google Earth.

    Google Earth web ONLY responds to mouse interactions at the globe:
    - Left-click drag = orbit/rotate
    - Scroll at globe = zoom
    - Right-click drag = tilt/rotate camera
    - Shift + scroll = tilt

    Keyboard shortcuts (Ctrl+Left, arrows, etc.) do NOT work.
    All actions move the mouse to screen center first (where the globe is).
    """

    def __init__(self):
        self._pyag = None
        self._dragging = False
        self._right_dragging = False
        self._paused = False
        self._last_action = ""
        self._last_action_time = 0.0
        self._last_release_time = 0.0

    def _ensure_pyautogui(self):
        """Lazy import of pyautogui."""
        if self._pyag is None:
            import pyautogui
            pyautogui.PAUSE = 0.02
            pyautogui.FAILSAFE = True
            self._pyag = pyautogui

    def _screen_center(self):
        """Get screen center coordinates (where the globe should be)."""
        w, h = self._pyag.size()
        return w // 2, h // 2

    def _move_to_center(self):
        """Move mouse to screen center."""
        cx, cy = self._screen_center()
        self._pyag.moveTo(cx, cy, _pause=False)

    @property
    def paused(self):
        return self._paused

    def toggle_pause(self):
        self._paused = not self._paused
        state = "PAUSED" if self._paused else "ACTIVE"
        _log(f"Gesture input: {state}", C_YELLOW if self._paused else C_GREEN)
        return self._paused

    def _can_act(self, action: str) -> bool:
        now = time.monotonic()
        if now - self._last_action_time < GESTURE_COOLDOWN:
            return False
        self._last_action = action
        self._last_action_time = now
        return True

    def stop_action(self):
        """Release any held mouse buttons, cancel drag."""
        if not self._dragging and not self._right_dragging:
            return
        self._ensure_pyautogui()
        now = time.monotonic()
        if now - self._last_release_time < 0.3:
            return
        if self._dragging:
            self._pyag.mouseUp(button='left')
            self._dragging = False
        if self._right_dragging:
            self._pyag.mouseUp(button='right')
            self._right_dragging = False
        self._last_release_time = now
        _log("✋ Released drag")

    def zoom_in(self):
        """Zoom in — scroll up at screen center where globe is."""
        if not self._can_act("zoom_in"):
            return
        self._ensure_pyautogui()
        self._move_to_center()
        self._pyag.scroll(SCROLL_AMOUNT)
        _log("🔍 Zoom IN")

    def zoom_out(self):
        """Zoom out — scroll down at screen center where globe is."""
        if not self._can_act("zoom_out"):
            return
        self._ensure_pyautogui()
        self._move_to_center()
        self._pyag.scroll(-SCROLL_AMOUNT)
        _log("🔎 Zoom OUT")

    def start_drag(self):
        """Start left-click drag at screen center for orbit/rotate."""
        self._ensure_pyautogui()
        if not self._dragging:
            self._move_to_center()
            self._pyag.mouseDown(button='left')
            self._dragging = True
            _log("👆 Drag started (orbit)")

    def drag_move(self, dx: float, dy: float):
        """Move mouse while dragging for orbit/rotate."""
        if not self._dragging:
            return
        self._ensure_pyautogui()
        screen_dx = int(dx * DRAG_SENSITIVITY * 1000)
        screen_dy = int(dy * DRAG_SENSITIVITY * 1000)
        screen_dx = max(-200, min(200, screen_dx))
        screen_dy = max(-200, min(200, screen_dy))
        if abs(screen_dx) > 2 or abs(screen_dy) > 2:
            self._pyag.moveRel(screen_dx, screen_dy, _pause=False)

    def _right_drag(self, dx: int, dy: int):
        """
        Right-click drag at screen center.
        Google Earth: right-drag = tilt/rotate camera.
        """
        self._ensure_pyautogui()
        self._move_to_center()
        self._pyag.mouseDown(button='right')
        self._pyag.moveRel(dx, dy, _pause=False)
        time.sleep(0.05)
        self._pyag.mouseUp(button='right')
        _log(f"🖱 Right-drag ({dx}, {dy})")

    def tilt_up(self):
        """Tilt up — right-click drag upward at screen center."""
        if not self._can_act("tilt_up"):
            return
        self._right_drag(0, -DRAG_STEP_PX)
        _log("⬆ Tilt UP")

    def tilt_down(self):
        """Tilt down — right-click drag downward at screen center."""
        if not self._can_act("tilt_down"):
            return
        self._right_drag(0, DRAG_STEP_PX)
        _log("⬇ Tilt DOWN")

    def rotate_left(self):
        """Rotate left — right-click drag left at screen center."""
        if not self._can_act("rot_left"):
            return
        self._right_drag(-DRAG_STEP_PX, 0)
        _log("⬅ Rotate LEFT")

    def rotate_right(self):
        """Rotate right — right-click drag right at screen center."""
        if not self._can_act("rot_right"):
            return
        self._right_drag(DRAG_STEP_PX, 0)
        _log("➡ Rotate RIGHT")

    def pitch_up(self):
        """Pitch up — scroll up + slight tilt at screen center."""
        if not self._can_act("pitch_up"):
            return
        self._ensure_pyautogui()
        self._move_to_center()
        self._pyag.scroll(2)
        _log("⤴ Pitch UP")

    def pitch_down(self):
        """Pitch down — scroll down + slight tilt at screen center."""
        if not self._can_act("pitch_down"):
            return
        self._ensure_pyautogui()
        self._move_to_center()
        self._pyag.scroll(-2)
        _log("⤵ Pitch DOWN")

    def cleanup(self):
        """Release any held keys/buttons."""
        if self._dragging and self._pyag:
            try:
                self._pyag.mouseUp(button='left')
            except Exception:
                pass
            self._dragging = False
        if self._right_dragging and self._pyag:
            try:
                self._pyag.mouseUp(button='right')
            except Exception:
                pass
            self._right_dragging = False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HUD OVERLAY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class HudOverlay:
    """Transparent HUD overlay showing gesture state and status."""

    def __init__(self):
        self._root = None
        self._labels = {}
        self._running = False
        self._update_queue = deque(maxlen=20)

    def start(self):
        self._running = True
        self._init_tk()

    def _init_tk(self):
        try:
            import tkinter as tk
        except ImportError:
            _log("tkinter not available — HUD disabled", C_YELLOW)
            return

        self._root = tk.Tk()
        self._root.title("FRIDAY Holo HUD")
        self._root.attributes('-topmost', True)
        self._root.attributes('-alpha', 0.85)
        self._root.overrideredirect(True)

        screen_w = self._root.winfo_screenwidth()
        win_w, win_h = 280, 180
        self._root.geometry(f"{win_w}x{win_h}+{screen_w - win_w - 20}+20")
        self._root.configure(bg='#0a0a0f')

        try:
            self._root.wm_attributes('-type', 'dock')
        except Exception:
            pass

        frame = tk.Frame(self._root, bg='#0a0a0f', highlightbackground='#00d4ff',
                         highlightthickness=1)
        frame.pack(fill='both', expand=True, padx=2, pady=2)

        tk.Label(frame, text="FRIDAY HOLO EARTH", font=('Consolas', 11, 'bold'),
                 fg='#00d4ff', bg='#0a0a0f').pack(pady=(6, 2))

        labels = [
            ("gesture", "Gesture: --"),
            ("action", "Action: --"),
            ("eye", "Eye: --"),
            ("fps", "FPS: --"),
            ("status", "Status: INITIALIZING"),
        ]
        for key, text in labels:
            lbl = tk.Label(frame, text=text, font=('Consolas', 9),
                           fg='#88cccc', bg='#0a0a0f', anchor='w')
            lbl.pack(fill='x', padx=10, pady=1)
            self._labels[key] = lbl

        self._poll_updates()

    def _poll_updates(self):
        if not self._running or not self._root:
            return
        try:
            while self._update_queue:
                key, value, color = self._update_queue.popleft()
                if key in self._labels:
                    self._labels[key].config(text=f"{key}: {value}", fg=color)
        except Exception:
            pass
        try:
            self._root.after(50, self._poll_updates)
        except Exception:
            pass

    def update(self, key: str, value: str, color: str = '#88cccc'):
        self._update_queue.append((key, value, color))

    def process_events(self):
        if self._root:
            try:
                self._root.update_idletasks()
                self._root.update()
            except Exception:
                pass

    def stop(self):
        self._running = False
        if self._root:
            try:
                self._root.quit()
                self._root.destroy()
            except Exception:
                pass
            self._root = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN GESTURE LOOP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class HoloEarthSystem:
    """Main system: webcam → MediaPipe → gestures → Google Earth."""

    def __init__(self):
        self._stop_event = threading.Event()
        self._gesture_classifier = GestureClassifier()
        self._swipe_detector = SwipeDetector()
        self._eye_tracker = EyeTracker()
        self._eye_controller = EyeController()
        self._earth = EarthController()
        self._hud = HudOverlay()

        # MediaPipe
        self._hand_landmarker = None
        self._face_landmarker = None
        self._hand_ok = False
        self._face_ok = False

        # Webcam
        self._cap = None
        self._capture_thread = None

        # State
        self._prev_hand_pos = None
        self._current_gesture = "none"
        self._stable_gesture = None
        self._stable_count = 0
        self._fps_counter = 0
        self._fps_time = 0
        self._fps = 0

        self._shutting_down = False

    def _init_mediapipe(self):
        try:
            import mediapipe as mp
            from mediapipe.tasks.python.vision import (
                HandLandmarker, HandLandmarkerOptions,
                FaceLandmarker, FaceLandmarkerOptions, RunningMode
            )
            from mediapipe.tasks.python.core.base_options import BaseOptions

            if not Path(HAND_MODEL).exists():
                _log(f"Hand model not found: {HAND_MODEL}", C_RED)
                _log("Download from: https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task", C_YELLOW)
                return False

            # Hand landmarker
            opts = HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=HAND_MODEL),
                running_mode=RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=0.6,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._hand_landmarker = HandLandmarker.create_from_options(opts)
            self._hand_ok = True
            _log("Hand tracking loaded", C_GREEN)

            # Face landmarker (for eye tracking)
            if EYE_ENABLED and Path(FACE_MODEL).exists():
                try:
                    face_opts = FaceLandmarkerOptions(
                        base_options=BaseOptions(model_asset_path=FACE_MODEL),
                        running_mode=RunningMode.VIDEO,
                        num_faces=1,
                        min_face_detection_confidence=0.5,
                        min_face_presence_confidence=0.5,
                        min_tracking_confidence=0.5,
                    )
                    self._face_landmarker = FaceLandmarker.create_from_options(face_opts)
                    self._face_ok = True
                    _log("Eye tracking loaded", C_GREEN)
                except Exception as e:
                    _log(f"Eye tracking unavailable: {e}", C_YELLOW)
            elif EYE_ENABLED:
                _log(f"Face model not found: {FACE_MODEL} — eye tracking disabled", C_YELLOW)

            return True
        except Exception as e:
            _log(f"MediaPipe init error: {e}", C_RED)
            return False

    def _init_webcam(self):
        try:
            import cv2
            self._cap = cv2.VideoCapture(CAM_INDEX)
            if not self._cap.isOpened():
                _log("No webcam detected", C_RED)
                return False
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_W)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
            for _ in range(5):
                self._cap.read()
            _log(f"Webcam online ({CAM_W}×{CAM_H})", C_GREEN)
            return True
        except Exception as e:
            _log(f"Webcam error: {e}", C_RED)
            return False

    def _process_frame(self, frame_rgb):
        import mediapipe as mp

        ts_ms = int(time.monotonic_ns() // 1_000_000)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

        # ── Eye tracking (face landmarks) ──
        if self._face_landmarker:
            try:
                face_res = self._face_landmarker.detect_for_video(mp_img, ts_ms)
                if face_res.face_landmarks and len(face_res.face_landmarks) > 0:
                    self._eye_tracker.update(face_res.face_landmarks[0])
                    # Process gaze → cursor movement + blink → click
                    self._eye_controller.process_gaze(
                        self._eye_tracker.gaze,
                        self._eye_tracker.blink
                    )
                else:
                    self._eye_tracker.update(None)
            except Exception:
                pass

        # ── Hand gesture tracking ──
        try:
            res = self._hand_landmarker.detect_for_video(mp_img, ts_ms)
        except Exception:
            return

        if not res.hand_landmarks or len(res.hand_landmarks) == 0:
            if self._current_gesture != "none":
                self._current_gesture = "none"
                self._stable_gesture = None
                self._stable_count = 0
                self._swipe_detector.clear()
                self._prev_hand_pos = None
                self._earth.stop_action()
            return

        lm = res.hand_landmarks[0]
        gesture = self._gesture_classifier.classify(lm)

        center_x = sum(p.x for p in lm) / len(lm)
        center_y = sum(p.y for p in lm) / len(lm)
        self._swipe_detector.add_position(center_x, center_y)

        if self._prev_hand_pos is not None:
            sx = SMOOTHING_ALPHA * center_x + (1 - SMOOTHING_ALPHA) * self._prev_hand_pos[0]
            sy = SMOOTHING_ALPHA * center_y + (1 - SMOOTHING_ALPHA) * self._prev_hand_pos[1]
            smoothed = (sx, sy)
        else:
            smoothed = (center_x, center_y)

        if self._prev_hand_pos is not None:
            dx = smoothed[0] - self._prev_hand_pos[0]
            dy = smoothed[1] - self._prev_hand_pos[1]
        else:
            dx, dy = 0, 0
        self._prev_hand_pos = smoothed

        # Check for swipe first (overrides static gesture, but not during drag)
        swipe = self._swipe_detector.detect()
        if swipe and not self._earth._dragging:
            self._execute_swipe(swipe)
            self._swipe_detector.clear()
            return

        if gesture == self._stable_gesture:
            self._stable_count += 1
        else:
            self._stable_gesture = gesture
            self._stable_count = 1

        if self._stable_count >= STABLE_REQUIRED:
            self._execute_gesture(gesture, dx, dy)

        self._current_gesture = gesture

    def _execute_gesture(self, gesture: str, dx: float, dy: float):
        if self._earth.paused and gesture != "stop":
            return

        if gesture == "open":
            self._earth.stop_action()
        elif gesture == "fist":
            self._earth.zoom_in()
        elif gesture == "point":
            self._earth.start_drag()
            self._earth.drag_move(dx, dy)
        elif gesture == "peace":
            self._earth.zoom_out()
        elif gesture == "pinch":
            self._earth.tilt_down()
        elif gesture == "spread":
            self._earth.tilt_up()
        elif gesture == "stop":
            self._earth.toggle_pause()

        self._stable_count = 0
        self._stable_gesture = None

    def _execute_swipe(self, direction: str):
        if self._earth.paused:
            return

        if direction == "left":
            self._earth.rotate_left()
        elif direction == "right":
            self._earth.rotate_right()
        elif direction == "up":
            self._earth.pitch_up()
        elif direction == "down":
            self._earth.pitch_down()

        self._stable_count = 0
        self._stable_gesture = None

    def _capture_loop(self):
        """Main capture and processing loop (runs in daemon thread)."""
        import cv2

        while not self._stop_event.is_set():
            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            self._process_frame_safe(rgb)

            # FPS counter + HUD updates
            self._fps_counter += 1
            now = time.time()
            if now - self._fps_time >= 1.0:
                self._fps = self._fps_counter
                self._fps_counter = 0
                self._fps_time = now

                self._hud.update("gesture", self._current_gesture, '#00ffcc')
                action = self._earth._last_action or "--"
                self._hud.update("action", action, '#ffcc00')
                # Eye state
                eye_state = "OPEN" if self._eye_tracker.eyes_open else "CLOSED"
                if self._eye_tracker.blink:
                    eye_state = "BLINK 👁"
                gx, gy = self._eye_tracker.gaze
                self._hud.update("eye", f"{eye_state} ({gx:.2f},{gy:.2f})", '#ff88ff')
                self._hud.update("fps", f"{self._fps}", '#88cccc')
                status = "PAUSED" if self._earth.paused else "ACTIVE"
                status_color = '#ff6666' if self._earth.paused else '#66ff66'
                self._hud.update("status", status, status_color)

            self._stop_event.wait(timeout=0.033)

        self._release_capture()
        _log("Capture thread exited", C_DIM)

    def _process_frame_safe(self, frame_rgb):
        if self._stop_event.is_set():
            return
        try:
            self._process_frame(frame_rgb)
        except Exception:
            pass

    def _release_capture(self):
        """Release webcam and MediaPipe — idempotent, safe to call multiple times."""
        if self._cap:
            try:
                self._cap.release()
                _log("Webcam released", C_DIM)
            except Exception:
                pass
            self._cap = None

        if self._hand_landmarker:
            try:
                self._hand_landmarker.close()
                _log("Hand landmarker closed", C_DIM)
            except Exception:
                pass
            self._hand_landmarker = None

        if self._face_landmarker:
            try:
                self._face_landmarker.close()
                _log("Face landmarker closed", C_DIM)
            except Exception:
                pass
            self._face_landmarker = None

    def start(self):
        """Start the holo earth system. Blocks until stopped."""
        print()
        print(f"{C_CYAN}{C_BOLD}{'═' * 56}{C_RESET}")
        print(f"{C_CYAN}{C_BOLD}  FRIDAY HOLO EARTH{C_RESET}")
        print(f"{C_CYAN}{C_BOLD}  Gesture-Controlled Google Earth{C_RESET}")
        print(f"{C_CYAN}{C_BOLD}{'═' * 56}{C_RESET}")
        print()

        _log("Initializing systems...")

        missing = []
        for name, pkg in [("mediapipe", "mediapipe"), ("opencv-python", "cv2"),
                           ("pyautogui", "pyautogui"), ("numpy", "numpy")]:
            try:
                __import__(pkg)
            except ImportError:
                missing.append(name)
        if missing:
            _log(f"Missing packages: {', '.join(missing)}", C_RED)
            _log(f"Install: pip install {' '.join(missing)}", C_YELLOW)
            return False

        if not self._init_mediapipe():
            return False

        if not self._init_webcam():
            return False

        print()

        _log("Starting HUD overlay...")
        self._hud.start()

        _log("Launching Google Earth in Edge app mode...")
        _launch_google_earth()

        # Give Edge time to open and load
        _log("Waiting 5s for Google Earth to load...")
        time.sleep(5)

        # Focus the Edge window
        _focus_edge()

        print()
        _log(f"Gesture:  {C_BOLD}ACTIVE{C_RESET} (hand: {'ON' if self._hand_ok else 'OFF'}, eye: {'ON' if self._face_ok else 'OFF'})")
        _log(f"HUD:      {C_BOLD}TOP-RIGHT CORNER{C_RESET}")
        _log(f"Controls: Fist=Zoom, Point=Drag/Orbit, Peace=Zoom Out")
        _log(f"          Pinch=Tilt Down, Spread=Tilt Up")
        _log(f"          Swipe L/R=Rotate, Swipe U/D=Pitch")
        _log(f"          Gaze=Cursor, Blink=Click, Stop gesture=Toggle Pause")
        _log(f"Say 'close holo earth' or Ctrl+C to shutdown")
        print()

        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

        try:
            while not self._stop_event.is_set():
                self._hud.process_events()
                self._stop_event.wait(timeout=0.05)
        except KeyboardInterrupt:
            print()
            _log("Shutdown signal received...", C_YELLOW)
        finally:
            self.stop()

        return True

    def stop(self):
        """Stop everything — idempotent, safe to call multiple times."""
        if self._shutting_down:
            return
        self._shutting_down = True

        _log("Shutting down...", C_YELLOW)

        self._stop_event.set()

        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=3.0)
            if self._capture_thread.is_alive():
                _log("Capture thread still alive after 3s — force releasing", C_YELLOW)

        self._release_capture()
        self._earth.cleanup()
        self._eye_controller.cleanup()
        self._hud.stop()

        _log("All systems offline", C_GREEN)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EDGE / GOOGLE EARTH LAUNCHER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _launch_google_earth() -> bool:
    """Launch Google Earth in Edge app mode (no address bar, no tabs)."""
    earth_url = "https://earth.google.com/web/"

    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        "/usr/bin/microsoft-edge",
        "/usr/bin/microsoft-edge-stable",
        "/opt/microsoft/msedge/msedge",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]

    for path in edge_paths:
        if os.path.isfile(path):
            try:
                subprocess.Popen(
                    [path, f"--app={earth_url}", "--no-first-run",
                     "--disable-features=msEdgeSidebarV2"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                _log(f"Google Earth launched in Edge app mode", C_GREEN)
                _log(f"URL: {earth_url}", C_DIM)
                return True
            except Exception as e:
                _log(f"Edge launch failed: {e}", C_YELLOW)

    try:
        subprocess.Popen(
            ["msedge", f"--app={earth_url}", "--no-first-run"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        _log(f"Google Earth launched (msedge command)", C_GREEN)
        return True
    except FileNotFoundError:
        pass

    _log("Edge not found — opening in default browser", C_YELLOW)
    webbrowser.open(earth_url)
    return False


def _focus_edge():
    """Try to bring the Edge window to focus so gestures go to it."""
    try:
        import pyautogui
        # On Windows, Alt+Tab or click to focus
        # Simple approach: move mouse to center and click
        w, h = pyautogui.size()
        pyautogui.click(w // 2, h // 2)
        _log("Focused Edge window (clicked center)", C_DIM)
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MODULE ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_system: Optional[HoloEarthSystem] = None
_system_lock = threading.Lock()


def holo_earth(action="open", parameters=None, player=None, **kwargs):
    """Main entry point — compatible with FRIDAY's action system."""
    global _system

    if isinstance(action, dict):
        parameters = action
        action = parameters.get("action", "open") if parameters else "open"
    elif parameters is None:
        parameters = {}

    if action == "open":
        with _system_lock:
            if _system and not _system._stop_event.is_set():
                _log("Already running", C_YELLOW)
                return {"status": "already_running"}
            _system = HoloEarthSystem()

        success = _system.start()
        return {"status": "started" if success else "error"}

    elif action == "close":
        with _system_lock:
            if _system:
                _system.stop()
                _system = None
        return {"status": "stopped"}

    elif action == "status":
        running = _system and not _system._stop_event.is_set() if _system else False
        return {
            "status": "running" if running else "stopped",
            "gesture": _system._current_gesture if running else None,
            "fps": _system._fps if running else 0,
        }

    return {"status": "unknown_action"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    holo_earth("open")
