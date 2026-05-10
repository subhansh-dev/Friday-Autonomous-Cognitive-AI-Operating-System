# -*- coding: utf-8 -*-
"""
utils.py — FRIDAY Gesture Utilities
Landmark processing, smoothing, velocity, and gesture helpers.
"""

import numpy as np
from typing import Optional
from collections import deque


# ── Configuration ──────────────────────────────────────────────────

LANDMARKS_PER_HAND = 21
COORDS_PER_LANDMARK = 3  # x, y, z
MAX_HANDS = 2
TOTAL_FEATURES = LANDMARKS_PER_HAND * COORDS_PER_LANDMARK * MAX_HANDS  # 126


class GestureUtils:
    """Utility functions for gesture landmark processing."""

    # ── Normalization ──────────────────────────────────────────────

    @staticmethod
    def normalize_landmarks(
        landmarks,
        image_width: int = 1,
        image_height: int = 1,
    ) -> np.ndarray:
        """
        Normalize landmarks relative to wrist position.

        MediaPipe returns raw x,y,z in [0,1] range.
        Normalizing relative to wrist makes detection
        position-independent — works anywhere in frame. [#1]
        """
        if landmarks is None or len(landmarks) == 0:
            return np.zeros(TOTAL_FEATURES)

        data = []
        for lm in landmarks:
            # [#2] Include z (depth) for 3D gesture detection
            data.extend([lm.x, lm.y, lm.z])

        # Normalize relative to wrist (first landmark)
        return GestureUtils._wrist_normalize(data)

    @staticmethod
    def normalize_two_hands(
        hand_landmarks_list: list,
    ) -> np.ndarray:
        """
        Normalize landmarks for up to 2 hands.
        Sorts hands by x-position for consistency. [#3]
        """
        if not hand_landmarks_list:
            return np.zeros(TOTAL_FEATURES)

        # Sort hands by average x-position (left hand first)
        hands_data = []
        for hand_lms in hand_landmarks_list:
            avg_x = np.mean([lm.x for lm in hand_lms.landmark])
            raw = []
            for lm in hand_lms.landmark:
                raw.extend([lm.x, lm.y, lm.z])
            hands_data.append((avg_x, raw))

        hands_data.sort(key=lambda h: h[0])

        # Normalize each hand independently
        all_data = []
        for _, raw in hands_data[:MAX_HANDS]:
            normalized = GestureUtils._wrist_normalize(raw)
            all_data.extend(normalized)

        # Pad if fewer than MAX_HANDS
        if len(all_data) < TOTAL_FEATURES:
            all_data.extend([0.0] * (TOTAL_FEATURES - len(all_data)))

        return np.array(all_data[:TOTAL_FEATURES], dtype=np.float32)

    @staticmethod
    def _wrist_normalize(data: list) -> list:
        """Normalize landmark data relative to wrist (index 0)."""
        if len(data) < 3:
            return data + [0.0] * (TOTAL_FEATURES // MAX_HANDS - len(data))

        wrist_x, wrist_y, wrist_z = data[0], data[1], data[2]
        normalized = []
        for i in range(0, len(data), 3):
            if i + 2 < len(data):
                normalized.append(data[i] - wrist_x)
                normalized.append(data[i + 1] - wrist_y)
                normalized.append(data[i + 2] - wrist_z)
            else:
                normalized.append(0.0)
        return normalized

    # ── Smoothing ──────────────────────────────────────────────────

    @staticmethod
    def smooth_sequence(
        buffer: list,
        window_size: int = 3,
    ) -> np.ndarray:
        """
        Apply exponential moving average smoothing. [#4]
        Lower latency than simple moving average — better for real-time.
        """
        if not buffer:
            return np.array([])

        if len(buffer) == 1:
            return np.array(buffer[0])

        # Use smaller window for less latency
        window_size = min(window_size, len(buffer))

        # Exponential moving average — recent frames weighted more
        alpha = 2.0 / (window_size + 1)  # EMA smoothing factor
        smoothed = np.array(buffer[0], dtype=np.float32)

        for i in range(1, len(buffer)):
            frame = np.array(buffer[i], dtype=np.float32)
            smoothed = alpha * frame + (1 - alpha) * smoothed

        return smoothed

    @staticmethod
    def smooth_value(
        current: float,
        previous: float,
        alpha: float = 0.4,
    ) -> float:
        """Smooth a single value (e.g., confidence, distance)."""
        return alpha * current + (1 - alpha) * previous

    # ── Velocity & Movement ────────────────────────────────────────

    @staticmethod
    def calculate_velocity(
        prev_pos: np.ndarray,
        curr_pos: np.ndarray,
        dt: float = 1.0,
    ) -> float:
        """
        Compute movement velocity between two frames.
        Returns pixels-per-frame (or per dt).
        """
        prev = np.array(prev_pos, dtype=np.float32)
        curr = np.array(curr_pos, dtype=np.float32)
        if prev.shape != curr.shape:
            return 0.0
        return float(np.linalg.norm(curr - prev) / max(dt, 0.001))

    @staticmethod
    def calculate_velocity_vector(
        prev_pos: np.ndarray,
        curr_pos: np.ndarray,
    ) -> np.ndarray:
        """Get velocity as a direction vector (for swipe detection)."""
        prev = np.array(prev_pos, dtype=np.float32)
        curr = np.array(curr_pos, dtype=np.float32)
        if prev.shape != curr.shape:
            return np.zeros_like(curr)
        return curr - prev

    @staticmethod
    def calculate_distance(
        point_a: np.ndarray,
        point_b: np.ndarray,
    ) -> float:
        """Euclidean distance between two points."""  # [#5]
        a = np.array(point_a, dtype=np.float32)
        b = np.array(point_b, dtype=np.float32)
        return float(np.linalg.norm(a - b))

    # ── Finger State Detection ─────────────────────────────────────

    @staticmethod
    def get_finger_states(landmarks) -> dict:
        """
        Detect which fingers are extended. [#6]
        Critical for distinguishing gestures like fist vs palm.

        MediaPipe landmark indices:
          Thumb:  1(CMC), 2(MCP), 3(IP), 4(TIP)
          Index:  5(MCP), 6(PIP), 7(DIP), 8(TIP)
          Middle: 9(MCP), 10(PIP), 11(DIP), 12(TIP)
          Ring:   13(MCP), 14(PIP), 15(DIP), 16(TIP)
          Pinky:  17(MCP), 18(PIP), 19(DIP), 20(TIP)
        """
        if landmarks is None or len(landmarks) < 21:
            return {
                "thumb": False, "index": False, "middle": False,
                "ring": False, "pinky": False, "count": 0,
            }

        lm = landmarks

        # Finger is extended if TIP is above PIP (lower y = higher in frame)
        # Thumb uses x-axis comparison (special case)
        thumb_extended = lm[4].x < lm[3].x  # Right hand
        # [#7] Detect hand orientation for thumb
        wrist_to_mcp = lm[5].x - lm[0].x
        if wrist_to_mcp > 0:
            thumb_extended = lm[4].x > lm[3].x  # Left hand

        index_extended = lm[8].y < lm[6].y
        middle_extended = lm[12].y < lm[10].y
        ring_extended = lm[16].y < lm[14].y
        pinky_extended = lm[20].y < lm[18].y

        fingers = {
            "thumb": thumb_extended,
            "index": index_extended,
            "middle": middle_extended,
            "ring": ring_extended,
            "pinky": pinky_extended,
            "count": sum([
                thumb_extended, index_extended, middle_extended,
                ring_extended, pinky_extended,
            ]),
        }
        return fingers

    # ── Gesture Detection Helpers ──────────────────────────────────

    @staticmethod
    def detect_swipe(
        positions: list,
        min_distance: float = 0.15,
        max_frames: int = 10,
    ) -> Optional[str]:
        """
        Detect swipe direction from a buffer of hand positions.
        Returns 'left', 'right', 'up', 'down', or None. [#8]
        """
        if len(positions) < 3:
            return None

        # Use last N positions
        recent = positions[-max_frames:]
        start = np.array(recent[0], dtype=np.float32)
        end = np.array(recent[-1], dtype=np.float32)
        delta = end - start

        distance = np.linalg.norm(delta)
        if distance < min_distance:
            return None

        # Determine dominant direction
        dx, dy = delta[0], delta[1]

        if abs(dx) > abs(dy):
            return "right" if dx > 0 else "left"
        else:
            return "down" if dy > 0 else "up"

    @staticmethod
    def detect_pinch_spread(
        positions: list,
        threshold: float = 0.03,
    ) -> Optional[str]:
        """
        Detect pinch (fingers closing) or spread (fingers opening).
        Uses distance between thumb tip and index tip over time. [#9]
        """
        if len(positions) < 5:
            return None

        recent = positions[-5:]
        distances = []
        for pos in recent:
            if isinstance(pos, dict):
                thumb_tip = pos.get("thumb_tip")
                index_tip = pos.get("index_tip")
                if thumb_tip is not None and index_tip is not None:
                    d = np.linalg.norm(
                        np.array(thumb_tip) - np.array(index_tip))
                    distances.append(d)

        if len(distances) < 3:
            return None

        trend = distances[-1] - distances[0]

        if trend < -threshold:
            return "pinch"
        elif trend > threshold:
            return "spread"
        return None

    @staticmethod
    def get_hand_center(landmarks) -> Optional[np.ndarray]:
        """Get the center point of a hand (average of all landmarks)."""
        if landmarks is None or len(landmarks) == 0:
            return None
        xs = [lm.x for lm in landmarks]
        ys = [lm.y for lm in landmarks]
        return np.array([np.mean(xs), np.mean(ys)], dtype=np.float32)

    @staticmethod
    def get_palm_size(landmarks) -> float:
        """
        Get palm size (wrist to middle finger MCP distance).
        Used to normalize gesture distances regardless of
        hand distance from camera. [#10]
        """
        if landmarks is None or len(landmarks) < 10:
            return 0.1  # Default fallback

        wrist = np.array([landmarks[0].x, landmarks[0].y])
        mcp = np.array([landmarks[9].x, landmarks[9].y])
        return max(float(np.linalg.norm(mcp - wrist)), 0.01)

    # ── Gesture Confidence ─────────────────────────────────────────

    @staticmethod
    def gesture_confidence(
        predictions: list,
        min_agreement: int = 5,
    ) -> tuple:
        """
        Determine gesture from multiple consecutive predictions.
        Returns (gesture_name, confidence). [#11]

        Requires `min_agreement` out of last N predictions to match.
        Prevents single-frame misclassifications from triggering actions.
        """
        if not predictions:
            return None, 0.0

        recent = predictions[-min_agreement * 2:]
        if len(recent) < min_agreement:
            return None, 0.0

        # Count votes
        counts = {}
        for pred in recent:
            gesture = pred if isinstance(pred, str) else str(pred)
            counts[gesture] = counts.get(gesture, 0) + 1

        # Find winner
        winner = max(counts, key=counts.get)
        votes = counts[winner]
        confidence = votes / len(recent)

        if votes >= min_agreement and confidence >= 0.6:
            return winner, confidence

        return None, confidence

    # ── Volume Mapping ─────────────────────────────────────────────

    @staticmethod
    def hand_distance_to_volume(
        distance: float,
        min_dist: float = 0.05,
        max_dist: float = 0.5,
    ) -> int:
        """
        Map hand distance from camera to volume percentage (0-100).
        Closer hand = higher volume. [#12]
        """
        distance = max(min_dist, min(max_dist, distance))
        # Invert: closer = louder
        normalized = 1.0 - (distance - min_dist) / (max_dist - min_dist)
        return int(normalized * 100)

    @staticmethod
    def horizontal_to_pan(
        x_position: float,
        dead_zone: float = 0.1,
    ) -> float:
        """
        Map horizontal hand position to stereo pan (-1.0 to 1.0).
        Center = 0.0, full left = -1.0, full right = 1.0. [#13]
        """
        # x_position is 0.0 (left) to 1.0 (right)
        centered = (x_position - 0.5) * 2.0  # -1.0 to 1.0
        if abs(centered) < dead_zone:
            return 0.0
        return max(-1.0, min(1.0, centered))
