# -*- coding: utf-8 -*-
"""
collect_data.py — FRIDAY Gesture Data Collection
Records hand landmark sequences for training the gesture model.
"""

import cv2
import mediapipe as mp
from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode
from mediapipe.tasks.python.core.base_options import BaseOptions
import numpy as np
import os
import sys
import time
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()  # [#1] Use script dir, not CWD
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = SCRIPT_DIR / "gesture_data"
HAND_MODEL = PROJECT_DIR / "brain" / "hand_landmarker.task"

GESTURES = [
    "palm_open",
    "fist",
    "wave",
    "swipe_left",
    "swipe_right",
    "stop",
    # DJ gestures [#2]
    "thumbs_up",
    "peace",
    "pinch",
    "spread",
]

SEQUENCE_LENGTH = 20        # Frames per sequence
SAMPLES_PER_GESTURE = 30    # Sequences per gesture
MIN_HAND_CONFIDENCE = 0.6   # Min detection confidence
MIN_VALID_FRAMES = 15       # [#3] Min frames with valid hand data per sequence
CAMERA_INDEX = 0
TARGET_FPS = 20             # [#4] Target frame rate for sampling
FRAME_INTERVAL = 1.0 / TARGET_FPS

# Landmark dimensions
LANDMARKS_PER_HAND = 21     # MediaPipe hand landmarks
COORDS_PER_LANDMARK = 3     # x, y, z [#5] Include depth
VALUES_PER_HAND = LANDMARKS_PER_HAND * COORDS_PER_LANDMARK  # 63
MAX_HANDS = 2
TOTAL_VALUES = VALUES_PER_HAND * MAX_HANDS  # 126


def _normalize_landmarks(landmarks: list) -> list:
    """
    Normalize landmarks relative to wrist (landmark 0).
    Makes detection position-independent. [#6]
    """
    if len(landmarks) < 3:
        return landmarks

    # Wrist is the first landmark (index 0)
    wrist_x, wrist_y, wrist_z = landmarks[0], landmarks[1], landmarks[2]

    normalized = []
    for i in range(0, len(landmarks), 3):
        if i + 2 < len(landmarks):
            normalized.append(landmarks[i] - wrist_x)      # relative x
            normalized.append(landmarks[i + 1] - wrist_y)  # relative y
            normalized.append(landmarks[i + 2] - wrist_z)  # relative z
        else:
            normalized.append(0.0)
    return normalized


def _extract_hand_data(hand_landmarks) -> list:
    """Extract all coordinates from a single hand."""
    data = []
    for lm in hand_landmarks.landmark:
        data.extend([lm.x, lm.y, lm.z])
    return data


def _extract_frame_data(results) -> tuple:
    """
    Extract and normalize landmark data from MediaPipe results.
    Returns (data_list, valid_frame_count_increment).

    Output: list of TOTAL_VALUES (126) floats.
    """
    frame_data = []

    if results.hand_landmarks:
        # Sort hands consistently by x-position (left hand first) [#7]
        hands_with_x = []
        for hand_lms in results.hand_landmarks:
            avg_x = np.mean([lm.x for lm in hand_lms.landmark])
            hands_with_x.append((avg_x, hand_lms))
        hands_with_x.sort(key=lambda h: h[0])

        for _, hand_lms in hands_with_x[:MAX_HANDS]:
            raw = _extract_hand_data(hand_lms)
            normalized = _normalize_landmarks(raw)
            frame_data.extend(normalized)

    # Pad if fewer than MAX_HANDS detected
    if len(frame_data) < TOTAL_VALUES:
        frame_data.extend([0.0] * (TOTAL_VALUES - len(frame_data)))
    elif len(frame_data) > TOTAL_VALUES:
        frame_data = frame_data[:TOTAL_VALUES]

    is_valid = len(results.hand_landmarks) > 0 if results.hand_landmarks else False
    return frame_data, is_valid


def collect_data():
    """Main data collection loop."""
    print(f"[Collect] Saving to: {DATA_DIR}")
    print(f"[Collect] Gestures: {', '.join(GESTURES)}")
    print(f"[Collect] {SAMPLES_PER_GESTURE} samples per gesture, "
          f"{SEQUENCE_LENGTH} frames each")
    print(f"[Collect] Landmark dims: {TOTAL_VALUES} "
          f"({LANDMARKS_PER_HAND} landmarks × {COORDS_PER_LANDMARK} coords × {MAX_HANDS} hands)")
    print()
    print("Controls:")
    print("  R — Record next sequence")
    print("  D — Delete last recorded sequence for current gesture")
    print("  S — Skip to next gesture")
    print("  ESC — Quit")
    print()

    if not HAND_MODEL.exists():
        print(f"[Collect] ERROR: Hand model not found: {HAND_MODEL}")
        print("[Collect] Download from: https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task")
        sys.exit(1)

    hands = HandLandmarker.create_from_options(HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(HAND_MODEL)),
        running_mode=RunningMode.VIDEO,
        num_hands=MAX_HANDS,
        min_hand_detection_confidence=MIN_HAND_CONFIDENCE,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    ))

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("[Collect] ERROR: Cannot open camera")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    for gesture in GESTURES:
        gesture_path = DATA_DIR / gesture
        gesture_path.mkdir(parents=True, exist_ok=True)

        # [#9] Count existing samples to avoid overwriting
        existing = list(gesture_path.glob("seq_*.npy"))
        collected = len(existing)
        if collected > 0:
            print(f"[Collect] '{gesture}' already has {collected} samples")

        print(f"\n[Collect] === {gesture.upper()} === "
              f"({collected}/{SAMPLES_PER_GESTURE} collected)")
        print(f"[Collect] Show the gesture and press 'R' to record")

        while collected < SAMPLES_PER_GESTURE:
            frame_start = time.monotonic()  # [#4]

            ret, frame = cap.read()
            if not ret:
                print("[Collect] Camera read failed")
                break

            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            results = hands.detect_for_video(mp_img, int(time.time() * 1000))

            # ── HUD overlay ────────────────────────────────────────
            h, w = frame.shape[:2]

            # Gesture info
            cv2.putText(frame, f"Gesture: {gesture}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (0, 255, 0), 2)
            cv2.putText(frame, f"Samples: {collected}/{SAMPLES_PER_GESTURE}",
                        (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 255, 255), 2)

            # Hand detection indicator
            n_hands = len(results.hand_landmarks) if results.hand_landmarks else 0
            color = (0, 255, 0) if n_hands > 0 else (0, 0, 255)
            cv2.putText(frame, f"Hands: {n_hands}",
                        (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        color, 2)

            # Draw landmarks (minimal — just dots, no connections) [#10]
            if results.hand_landmarks:
                for hand_lms in results.hand_landmarks:
                    for lm in hand_lms.landmark:
                        cx, cy = int(lm.x * w), int(lm.y * h)
                        cv2.circle(frame, (cx, cy), 3, (0, 255, 0), -1)

            # Instructions
            cv2.putText(frame, "R=Record  D=Delete  S=Skip  ESC=Quit",
                        (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (200, 200, 200), 1)

            cv2.imshow("FRIDAY Gesture Collection", frame)

            # ── Key handling ───────────────────────────────────────
            key = cv2.waitKey(1) & 0xFF

            if key == 27:  # ESC
                print("[Collect] Quitting")
                hands.close()
                cap.release()
                cv2.destroyAllWindows()
                return

            elif key == ord('s'):  # Skip gesture
                print(f"[Collect] Skipping '{gesture}'")
                break

            elif key == ord('d'):  # Delete last sample
                if collected > 0:
                    collected -= 1
                    del_path = gesture_path / f"seq_{collected}.npy"
                    if del_path.exists():
                        del_path.unlink()
                    print(f"[Collect] Deleted last sample ({collected}/{SAMPLES_PER_GESTURE})")

            elif key == ord('r'):  # Record sequence
                if n_hands == 0:  # [#11]
                    print("[Collect] No hand detected! Show your hand first.")
                    continue

                print(f"[Collect] Recording {collected + 1}/{SAMPLES_PER_GESTURE}...")

                sequence = []
                valid_frames = 0
                countdown_start = time.monotonic()

                for frame_idx in range(SEQUENCE_LENGTH):
                    ret, f = cap.read()
                    if not ret:
                        break
                    f = cv2.flip(f, 1)
                    rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
                    mp_img_r = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    res = hands.detect_for_video(mp_img_r, int(time.time() * 1000))

                    frame_data, is_valid = _extract_frame_data(res)
                    if is_valid:
                        valid_frames += 1

                    sequence.append(frame_data)

                    # Show recording progress on frame
                    progress = (frame_idx + 1) / SEQUENCE_LENGTH
                    bar_w = int(200 * progress)
                    cv2.rectangle(f, (10, h - 60), (10 + bar_w, h - 45),
                                  (0, 255, 0), -1)
                    cv2.rectangle(f, (10, h - 60), (210, h - 45),
                                  (200, 200, 200), 1)
                    cv2.putText(f, f"Recording {frame_idx + 1}/{SEQUENCE_LENGTH}",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                (0, 0, 255), 2)
                    cv2.imshow("FRIDAY Gesture Collection", f)
                    cv2.waitKey(1)

                    # [#12] Frame-rate controlled sampling
                    elapsed = time.monotonic() - frame_start
                    sleep_time = FRAME_INTERVAL - (elapsed % FRAME_INTERVAL)
                    if sleep_time > 0:
                        time.sleep(sleep_time)

                # ── Validate and save ──────────────────────────────
                if valid_frames < MIN_VALID_FRAMES:  # [#3]
                    print(f"[Collect] REJECTED: Only {valid_frames}/{SEQUENCE_LENGTH} "
                          f"frames had valid hand data (need {MIN_VALID_FRAMES})")
                    continue

                seq_array = np.array(sequence, dtype=np.float32)

                # [#13] Sanity check shape
                expected_shape = (SEQUENCE_LENGTH, TOTAL_VALUES)
                if seq_array.shape != expected_shape:
                    print(f"[Collect] Shape mismatch: {seq_array.shape} "
                          f"vs expected {expected_shape}")
                    continue

                # Save
                save_path = gesture_path / f"seq_{collected}.npy"
                np.save(str(save_path), seq_array)
                collected += 1
                print(f"[Collect] ✓ Saved {save_path.name} "
                      f"({valid_frames}/{SEQUENCE_LENGTH} valid frames)")

            # Frame rate control for display loop
            elapsed = time.monotonic() - frame_start
            sleep_time = FRAME_INTERVAL - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        else:
            print(f"[Collect] ✓ '{gesture}' complete: {collected} samples")

    hands.close()
    cap.release()
    cv2.destroyAllWindows()

    # ── Summary ────────────────────────────────────────────────────
    print("\n" + "=" * 50)
    print("[Collect] Collection complete!")
    total = 0
    for gesture in GESTURES:
        g_path = DATA_DIR / gesture
        count = len(list(g_path.glob("seq_*.npy"))) if g_path.exists() else 0
        total += count
        status = "✓" if count >= SAMPLES_PER_GESTURE else "⚠"
        print(f"  {status} {gesture}: {count} samples")
    print(f"\n  Total: {total} samples across {len(GESTURES)} gestures")
    print("=" * 50)


if __name__ == "__main__":
    collect_data()
