# -*- coding: utf-8 -*-
"""
main.py — FRIDAY Gesture Music Control System
Real-time hand gesture recognition for music control.
Supports both ML model and heuristic fallback.
"""

import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_DIR = Path(__file__).resolve().parent
_sys_path = str(PROJECT_DIR)
if _sys_path not in sys.path:
    sys.path.insert(0, _sys_path)

import json
import cv2
import mediapipe as mp
from mediapipe.tasks.python.vision import (
    HandLandmarker, HandLandmarkerOptions, RunningMode,
)
from mediapipe.tasks.python.core.base_options import BaseOptions
import numpy as np
import time
from collections import deque

from gesture_music_system.actions import MusicController, execute_action, ACTION_MAP
from gesture_music_system.utils import GestureUtils


# ── Configuration ──────────────────────────────────────────────────

MODEL_DIR = PROJECT_DIR.parent / "brain"
HAND_MODEL = MODEL_DIR / "hand_landmarker.task"

GESTURE_MODEL_PATH = PROJECT_DIR / "gesture_model.keras"
GESTURE_LABELS_PATH = PROJECT_DIR / "gesture_labels.json"

SEQUENCE_LENGTH = 20
FEATURES_PER_FRAME = 126       # [#1] 21 landmarks × 3 coords × 2 hands
CONFIDENCE_THRESHOLD = 0.65
COOLDOWN_SECONDS = 1.2
STABLE_REQUIRED = 5            # Consecutive matching frames before action
PREDICTION_BUFFER_SIZE = 7     # [#2] Voting window size
MIN_AGREEMENT = 4              # Min votes for a gesture to count

HEADLESS = True                # [#3] No camera window — set False for debugging

# Default gesture list — overridden by gesture_labels.json if available
DEFAULT_GESTURES = [
    "palm_open", "fist", "wave", "swipe_left", "swipe_right",
    "stop", "point", "peace", "pinch", "spread",
]


# ── Model Loading ──────────────────────────────────────────────────

def _load_gesture_model():
    """Load TF gesture model with error handling."""
    try:
        from gesture_music_system.model import load_model
        model = load_model(str(GESTURE_MODEL_PATH))
        print(f"[GestureMusic] Model loaded from {GESTURE_MODEL_PATH.name}")
        return model
    except FileNotFoundError:
        print("[GestureMusic] No trained model found — using heuristic mode")
        return None
    except Exception as e:
        print(f"[GestureMusic] Model load error: {e} — using heuristic mode")
        return None


def _load_gesture_labels() -> list:
    """Load gesture label mapping from JSON file."""  # [#4]
    if GESTURE_LABELS_PATH.exists():
        try:
            data = json.loads(GESTURE_LABELS_PATH.read_text(encoding="utf-8"))
            # Format: {"0": "fist", "1": "palm_open", ...}
            labels = [data[str(i)] for i in range(len(data))]
            print(f"[GestureMusic] Loaded labels: {labels}")
            return labels
        except Exception as e:
            print(f"[GestureMusic] Label load error: {e}")
    return DEFAULT_GESTURES


# ── Gesture Music System ───────────────────────────────────────────

class GestureMusicSystem:
    def __init__(self):
        self.model = _load_gesture_model()
        self.gesture_labels = _load_gesture_labels()

        # MediaPipe hand landmarker
        self.hand_landmarker = None
        self._init_hand_landmarker()

        # State
        self._last_landmarks = None
        self._last_detection_time = 0.0
        self._hand_present = False       # [#5] Track hand presence explicitly

        # Music controller
        self.music = MusicController()

        # Buffers
        self.buffer = deque(maxlen=SEQUENCE_LENGTH)
        self.prediction_buffer = deque(maxlen=PREDICTION_BUFFER_SIZE)
        self.position_buffer = deque(maxlen=30)  # [#6] For swipe/pinch detection

        # Timing
        self.last_action_time = 0.0
        self.cooldown = COOLDOWN_SECONDS

        # Stability
        self._stable_gesture = None
        self._stable_count = 0
        self._stable_required = STABLE_REQUIRED

        # Error tracking
        self._tf_errored = False

        # Camera
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            print("[GestureMusic] ERROR: Cannot open camera")
            sys.exit(1)

        # [#7] Lower resolution for performance (gesture doesn't need 1080p)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        self._running = True

        # DJ mode state [#8]
        self._dj_mode = False
        self._last_hand_center = None
        self._volume_mode = False

    def _init_hand_landmarker(self):
        """Initialize MediaPipe HandLandmarker."""
        if not HAND_MODEL.exists():
            print(f"[GestureMusic] WARNING: Hand model not found: {HAND_MODEL}")
            print("[GestureMusic] Download from: https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task")
            return

        try:
            hand_opts = HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(HAND_MODEL)),
                running_mode=RunningMode.LIVE_STREAM,
                num_hands=2,
                result_callback=self._hand_callback,
                min_hand_detection_confidence=0.6,
                min_hand_presence_confidence=0.6,   # [#9]
                min_tracking_confidence=0.5,
            )
            self.hand_landmarker = HandLandmarker.create_from_options(hand_opts)
            print("[GestureMusic] HandLandmarker initialized")
        except Exception as e:
            print(f"[GestureMusic] HandLandmarker error: {e}")

    def _hand_callback(self, result, output_image, timestamp_ms):
        """MediaPipe async callback — updates landmark state."""
        if result.hand_landmarks and len(result.hand_landmarks) > 0:
            self._last_landmarks = result.hand_landmarks
            self._hand_present = True
            self._last_detection_time = time.monotonic()
        else:
            # [#10] CRITICAL FIX: Clear stale landmarks when no hand detected
            self._hand_present = False
            self._last_landmarks = None

    def _is_hand_present(self) -> bool:
        """Check if hand is currently present (with grace period)."""
        if not self._hand_present or self._last_landmarks is None:
            return False
        # [#11] Grace period: 0.3s — prevents flicker when hand briefly occluded
        elapsed = time.monotonic() - self._last_detection_time
        return elapsed < 0.3

    def _extract_frame_data(self) -> list:
        """
        Extract landmark data from current frame.
        Returns list of FEATURES_PER_FRAME (126) floats. [#1]
        """
        if not self._is_hand_present() or self._last_landmarks is None:
            return []

        frame_data = []

        # Sort hands by x-position for consistency
        hands_with_x = []
        for hand_lms in self._last_landmarks:
            avg_x = np.mean([lm.x for lm in hand_lms])
            hands_with_x.append((avg_x, hand_lms))
        hands_with_x.sort(key=lambda h: h[0])

        for _, hand_lms in hands_with_x[:2]:
            # [#1] Include z-coordinate: 21 landmarks × 3 coords = 63 per hand
            hand_data = []
            for lm in hand_lms:
                hand_data.extend([lm.x, lm.y, lm.z])

            # Normalize relative to wrist
            normalized = GestureUtils._wrist_normalize(hand_data)
            frame_data.extend(normalized)

        # Pad to FEATURES_PER_FRAME
        if len(frame_data) < FEATURES_PER_FRAME:
            frame_data.extend([0.0] * (FEATURES_PER_FRAME - len(frame_data)))
        elif len(frame_data) > FEATURES_PER_FRAME:
            frame_data = frame_data[:FEATURES_PER_FRAME]

        return frame_data

    def _classify_basic(self) -> str | None:
        """
        Heuristic fallback when TF model is unavailable.
        Uses finger state detection for robustness. [#12]
        """
        if not self._is_hand_present() or self._last_landmarks is None:
            return None

        # Use the first hand
        hand_lms = self._last_landmarks[0]
        if len(hand_lms) < 21:
            return None

        fingers = GestureUtils.get_finger_states(hand_lms)

        # Get hand center for swipe detection
        center = GestureUtils.get_hand_center(hand_lms)
        if center is not None:
            self.position_buffer.append(center)

        # ── Swipe detection (independent of finger state) ───────────
        if len(self.position_buffer) >= 5:
            swipe = GestureUtils.detect_swipe(
                list(self.position_buffer), min_distance=0.12)
            if swipe == "left":
                return "swipe_left"
            elif swipe == "right":
                return "swipe_right"

        # ── Gesture classification ─────────────────────────────────

        # All 5 fingers open → palm_open (play)
        if fingers["count"] >= 4:
            return "palm_open"

        # No fingers → fist (pause)
        if fingers["count"] == 0:
            return "fist"

        # Single finger extended
        if fingers["count"] == 1:
            if fingers["thumb"] and not fingers["index"]:
                return "thumbs_up"
            # Only index extended → point (volume up)
            if fingers["index"] and not fingers["thumb"]:
                return "point"
            return "fist"

        # Two fingers extended
        if fingers["count"] == 2:
            # Peace sign (index + middle extended, others down)
            if fingers["index"] and fingers["middle"] and not fingers["ring"] and not fingers["pinky"]:
                return "peace"
            # Pinch detection (thumb + index close together)
            if fingers["thumb"] and fingers["index"]:
                thumb_tip = np.array([hand_lms[4].x, hand_lms[4].y])
                index_tip = np.array([hand_lms[8].x, hand_lms[8].y])
                dist = np.linalg.norm(thumb_tip - index_tip)
                if dist < 0.05:
                    return "pinch"
                else:
                    return "spread"

        # Three fingers → stop
        if fingers["count"] == 3:
            return "stop"

        return None

    def _get_stable_gesture(self, gesture: str | None) -> str | None:
        """
        Stability filter — only returns gesture after N consecutive
        matching predictions. Prevents single-frame false triggers. [#13]
        """
        if gesture is None:
            self._stable_gesture = None
            self._stable_count = 0
            return None

        if gesture == self._stable_gesture:
            self._stable_count += 1
        else:
            self._stable_gesture = gesture
            self._stable_count = 1

        if self._stable_count >= self._stable_required:
            return gesture

        return None

    def _vote_gesture(self, gesture: str) -> str | None:
        """
        Majority voting over prediction buffer. [#14]
        Requires MIN_AGREEMENT matching predictions.
        """
        self.prediction_buffer.append(gesture)

        if len(self.prediction_buffer) < MIN_AGREEMENT:
            return None

        # Count votes
        counts = {}
        for g in self.prediction_buffer:
            counts[g] = counts.get(g, 0) + 1

        winner = max(counts, key=counts.get)
        if counts[winner] >= MIN_AGREEMENT:
            return winner

        return None

    def process_frame(self):
        """Main per-frame processing loop."""
        ret, frame = self.cap.read()
        if not ret:
            return

        frame = cv2.flip(frame, 1)

        # ── Hand detection ─────────────────────────────────────────
        if self.hand_landmarker:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            ts = int(time.time() * 1000)
            try:
                self.hand_landmarker.detect_async(mp_img, ts)
            except Exception:
                pass  # Async — errors handled in callback

        # ── No hand → reset state ─────────────────────────────────
        if not self._is_hand_present():
            # [#15] Clear all state when hand leaves — prevents stale triggers
            if self._stable_gesture is not None:
                self._stable_gesture = None
                self._stable_count = 0
                self.prediction_buffer.clear()
                self.position_buffer.clear()
                self.buffer.clear()
            # Show frame only if not headless
            if not HEADLESS:
                cv2.putText(frame, "No hand detected",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            (0, 0, 255), 2)
                cv2.imshow("FRIDAY Gesture Control", frame)
                cv2.waitKey(1)
            return

        # ── Extract features ───────────────────────────────────────
        frame_data = self._extract_frame_data()
        if not frame_data:
            return

        self.buffer.append(frame_data)

        # ── Need full sequence ─────────────────────────────────────
        if len(self.buffer) < SEQUENCE_LENGTH:
            if not HEADLESS:
                cv2.putText(frame, f"Buffering... {len(self.buffer)}/{SEQUENCE_LENGTH}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            (0, 255, 255), 2)
                cv2.imshow("FRIDAY Gesture Control", frame)
                cv2.waitKey(1)
            return

        # ── Classify gesture ───────────────────────────────────────
        gesture = None
        confidence = 0.0

        if self.model is not None and not self._tf_errored:
            try:
                # [#16] Proper input shape: (1, 20, 126)
                seq = np.array(list(self.buffer), dtype=np.float32)
                seq = seq.reshape(1, SEQUENCE_LENGTH, FEATURES_PER_FRAME)

                pred = self.model.predict(seq, verbose=0)[0]
                class_idx = int(np.argmax(pred))
                confidence = float(pred[class_idx])

                if confidence >= CONFIDENCE_THRESHOLD:
                    if class_idx < len(self.gesture_labels):
                        gesture = self.gesture_labels[class_idx]

            except Exception as e:
                if not self._tf_errored:
                    print(f"[GestureMusic] TF error: {e} — switching to heuristic")
                    self._tf_errored = True

        # Fallback to heuristic
        if gesture is None:
            gesture = self._classify_basic()
            confidence = 0.9 if gesture else 0.0

        # ── Stability + voting ─────────────────────────────────────
        stable = self._get_stable_gesture(gesture)
        if stable:
            voted = self._vote_gesture(stable)
            if voted:
                self._execute_gesture(voted, confidence)

        # ── Display (debug only) ───────────────────────────────────
        if not HEADLESS:
            h, w = frame.shape[:2]

            # Draw landmarks minimally
            if self._last_landmarks:
                for hand_lms in self._last_landmarks:
                    for lm in hand_lms:
                        cx, cy = int(lm.x * w), int(lm.y * h)
                        cv2.circle(frame, (cx, cy), 2, (0, 255, 0), -1)

            gesture_text = gesture or "..."
            cv2.putText(frame, f"{gesture_text} ({confidence:.2f})",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (0, 255, 0), 2)

            # DJ mode indicator
            if self._dj_mode:
                cv2.putText(frame, "DJ MODE",
                            (w - 150, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            (0, 200, 255), 2)

            cv2.imshow("FRIDAY Gesture Control", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC
                self._running = False
            elif key == ord('d'):  # Toggle DJ mode
                self._dj_mode = not self._dj_mode
                print(f"[GestureMusic] DJ Mode: {'ON' if self._dj_mode else 'OFF'}")
        else:
            # [#17] Headless: still need waitKey for OpenCV to process events
            cv2.waitKey(1)

    def _execute_gesture(self, gesture: str, confidence: float):
        """Execute the mapped action for a recognized gesture."""
        now = time.time()
        if now - self.last_action_time < self.cooldown:
            return

        # ── DJ Mode mappings [#18] ─────────────────────────────────
        if self._dj_mode:
            dj_mapping = {
                "palm_open":    "TOGGLE",           # Play/pause
                "fist":         "STOP",              # Stop
                "wave":         "SHUFFLE",           # Toggle shuffle
                "swipe_left":   "CROSSFADE_LEFT",    # Crossfade left
                "swipe_right":  "CROSSFADE_RIGHT",   # Crossfade right
                "point":        "VOLUME_UP",         # Volume up (index pointing)
                "peace":        "FAST_FORWARD",      # Skip forward
                "pinch":        "REWIND",            # Skip back
                "spread":       "REPEAT",            # Toggle repeat
                "stop":         "MUTE",              # Mute
            }
            mapping = dj_mapping
            mode_label = "DJ"
        else:
            # Standard mode
            mapping = {
                "palm_open":    "PLAY",
                "fist":         "PAUSE",
                "wave":         "NEXT",
                "swipe_left":   "PREV",
                "swipe_right":  "NEXT",
                "point":        "VOLUME_UP",         # Point up for volume
                "peace":        "VOLUME_DOWN",      # Peace for volume down
                "pinch":        "MUTE",
                "spread":       "FAST_FORWARD",
                "stop":         "PAUSE",
            }
            mode_label = "STD"

        action = mapping.get(gesture)
        if action:
            print(f"[GestureMusic] [{mode_label}] {gesture} → {action} "
                  f"(conf: {confidence:.2f})")
            execute_action(action, self.music)
            self.last_action_time = now

            # [#19] Clear buffers after action to prevent retriggering
            self.prediction_buffer.clear()
            self._stable_count = 0

    def activate_gesture_mode(self):
        """Startup message."""
        print("=" * 50)
        print("[GestureMusic] FRIDAY Gesture Music Control")
        print(f"  Mode:     {'Headless' if HEADLESS else 'Debug (camera window)'}")
        print(f"  Model:    {'TF LSTM' if self.model else 'Heuristic fallback'}")
        print(f"  Gestures: {len(self.gesture_labels)}")
        print(f"  Cooldown: {self.cooldown}s")
        print(f"  Stable:   {self._stable_required} frames")
        if not HEADLESS:
            print("  Controls: ESC=Quit, D=Toggle DJ Mode")
        print("=" * 50)

    def run(self):
        """Main loop."""
        self.activate_gesture_mode()

        try:
            while self._running:
                self.process_frame()
        except KeyboardInterrupt:
            print("\n[GestureMusic] Interrupted")
        finally:
            self.cleanup()

    def cleanup(self):
        """Release resources."""
        self._running = False
        if self.hand_landmarker:
            try:
                self.hand_landmarker.close()
            except Exception:
                pass
        self.cap.release()
        cv2.destroyAllWindows()
        print("[GestureMusic] Shutdown complete")


# ── Entry Point ────────────────────────────────────────────────────

if __name__ == "__main__":
    system = GestureMusicSystem()
    system.run()
