# -*- coding: utf-8 -*-
"""
train.py — FRIDAY Gesture Model Training
Loads collected data, augments, trains, and saves the gesture recognition model.
"""

import json
import sys
import numpy as np
import tensorflow as tf
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from collections import Counter

from model import (
    build_model,
    save_model,
    get_training_callbacks,
    generate_augmented_dataset,
    SEQUENCE_LENGTH,
    FEATURES_PER_FRAME,
)


# ── Configuration ──────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()  # [#1]
DATA_DIR = SCRIPT_DIR / "gesture_data"
MODEL_PATH = SCRIPT_DIR / "gesture_model.keras"
LABEL_PATH = SCRIPT_DIR / "gesture_labels.json"  # [#2] Save label mapping
HISTORY_PATH = SCRIPT_DIR / "training_history.json"

# Training params
TEST_SIZE = 0.2
RANDOM_SEED = 42
EPOCHS = 100            # [#3] More epochs, but early stopping prevents overfitting
BATCH_SIZE = 8          # [#4] Small batch for small dataset
AUGMENT_FACTOR = 5      # Generate 5x augmented copies
MIN_SAMPLES = 10        # [#5] Minimum samples required per gesture


def discover_gestures() -> list:
    """Auto-discover gesture classes from data directory."""  # [#6]
    if not DATA_DIR.exists():
        print(f"[Train] ERROR: Data directory not found: {DATA_DIR}")
        sys.exit(1)

    gestures = []
    for d in sorted(DATA_DIR.iterdir()):
        if d.is_dir():
            npy_files = list(d.glob("seq_*.npy"))
            if len(npy_files) >= MIN_SAMPLES:
                gestures.append(d.name)
            else:
                print(f"[Train] Skipping '{d.name}': "
                      f"only {len(npy_files)} samples (need {MIN_SAMPLES})")

    if not gestures:
        print(f"[Train] ERROR: No gestures with enough data in {DATA_DIR}")
        sys.exit(1)

    return gestures


def load_data(gestures: list) -> tuple:
    """Load all gesture sequences and labels."""
    X = []
    y = []
    stats = {}

    for gesture in gestures:
        gesture_path = DATA_DIR / gesture
        files = sorted(gesture_path.glob("seq_*.npy"))
        count = 0

        for f in files:
            try:
                seq = np.load(str(f))

                # [#7] Validate shape
                expected = (SEQUENCE_LENGTH, FEATURES_PER_FRAME)
                if seq.shape != expected:
                    print(f"[Train] WARNING: {f.name} shape {seq.shape} "
                          f"!= expected {expected} — skipping")
                    continue

                # [#8] Check for garbage data (all zeros)
                if np.all(seq == 0):
                    print(f"[Train] WARNING: {f.name} is all zeros — skipping")
                    continue

                # [#8] Check for NaN/Inf
                if np.any(np.isnan(seq)) or np.any(np.isinf(seq)):
                    print(f"[Train] WARNING: {f.name} has NaN/Inf — skipping")
                    continue

                X.append(seq)
                y.append(gesture)
                count += 1

            except Exception as e:
                print(f"[Train] WARNING: Failed to load {f}: {e}")

        stats[gesture] = count
        print(f"[Train] Loaded {count} samples for '{gesture}'")

    if not X:
        print("[Train] ERROR: No valid data loaded")
        sys.exit(1)

    # Print summary
    total = sum(stats.values())
    print(f"\n[Train] Total: {total} samples across {len(stats)} gestures")
    min_g = min(stats, key=stats.get)
    max_g = max(stats, key=stats.get)
    print(f"[Train] Min: '{min_g}' ({stats[min_g]}) | "
          f"Max: '{max_g}' ({stats[max_g]})")

    return np.array(X), np.array(y), stats


def train_gesture_model():
    """Main training pipeline."""
    print("=" * 50)
    print("[Train] FRIDAY Gesture Model Training")
    print("=" * 50)

    # ── Discover and load data ─────────────────────────────────────
    gestures = discover_gestures()
    print(f"\n[Train] Found {len(gestures)} gesture classes: "
          f"{', '.join(gestures)}")

    X, y_raw, stats = load_data(gestures)

    # ── Encode labels ──────────────────────────────────────────────
    le = LabelEncoder()
    le.fit(gestures)  # [#9] Fit on full gesture list, not just loaded labels
    y_encoded = le.transform(y_raw)
    y_categorical = tf.keras.utils.to_categorical(y_encoded)
    num_classes = len(gestures)

    # [#2] Save label encoder mapping — CRITICAL for inference
    label_map = {i: label for i, label in enumerate(le.classes_)}
    LABEL_PATH.write_text(
        json.dumps(label_map, indent=2),
        encoding="utf-8",
    )
    print(f"[Train] Label mapping saved to {LABEL_PATH.name}: {label_map}")

    # ── Split data ─────────────────────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_categorical,
        test_size=TEST_SIZE,
        random_state=RANDOM_SEED,
        stratify=y_encoded,  # [#10] Ensure balanced split
    )

    print(f"\n[Train] Split: {len(X_train)} train, {len(X_test)} test")

    # ── Augment training data ──────────────────────────────────────
    print(f"[Train] Augmenting training data ({AUGMENT_FACTOR}x)...")
    X_train_aug, y_train_aug = generate_augmented_dataset(
        X_train, y_train,
        augment_factor=AUGMENT_FACTOR,
    )
    print(f"[Train] Augmented: {len(X_train)} → {len(X_train_aug)} samples")

    # [#11] Shuffle augmented data
    shuffle_idx = np.random.permutation(len(X_train_aug))
    X_train_aug = X_train_aug[shuffle_idx]
    y_train_aug = y_train_aug[shuffle_idx]

    # ── Build model ────────────────────────────────────────────────
    print(f"\n[Train] Building model: {num_classes} classes, "
          f"input=({SEQUENCE_LENGTH}, {FEATURES_PER_FRAME})")
    model = build_model(num_classes)
    model.summary()

    # ── Train ──────────────────────────────────────────────────────
    print(f"\n[Train] Training for up to {EPOCHS} epochs "
          f"(batch_size={BATCH_SIZE})...")

    # [#12] Class weights — balance gestures with different sample counts
    class_counts = Counter(y_raw)
    total_samples = sum(class_counts.values())
    class_weight = {
        i: total_samples / (num_classes * class_counts.get(label, 1))
        for i, label in enumerate(le.classes_)
    }
    print(f"[Train] Class weights: {class_weight}")

    history = model.fit(
        X_train_aug,
        y_train_aug,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        validation_data=(X_test, y_test),
        callbacks=get_training_callbacks(str(MODEL_PATH)),
        class_weight=class_weight,
        verbose=1,
    )

    # ── Evaluate ───────────────────────────────────────────────────
    print("\n" + "=" * 50)
    print("[Train] Final Evaluation:")
    loss, accuracy = model.evaluate(X_test, y_test, verbose=0)
    print(f"[Train] Test Loss:     {loss:.4f}")
    print(f"[Train] Test Accuracy: {accuracy:.2%}")

    # Per-class accuracy
    y_pred = model.predict(X_test, verbose=0)
    y_pred_classes = np.argmax(y_pred, axis=1)
    y_true_classes = np.argmax(y_test, axis=1)

    print("\n[Train] Per-class accuracy:")
    for i, gesture in enumerate(le.classes_):
        mask = y_true_classes == i
        if mask.sum() > 0:
            class_acc = (y_pred_classes[mask] == i).mean()
            print(f"  {gesture:20s} {class_acc:.0%} "
                  f"({mask.sum()} test samples)")
        else:
            print(f"  {gesture:20s} no test samples")

    # ── Save ───────────────────────────────────────────────────────
    save_model(model, str(MODEL_PATH))

    # [#13] Save training history
    hist_data = {
        "final_accuracy": float(accuracy),
        "final_loss": float(loss),
        "epochs_trained": len(history.history["loss"]),
        "gestures": gestures,
        "label_map": label_map,
        "train_samples": int(len(X_train_aug)),
        "test_samples": int(len(X_test)),
        "augment_factor": AUGMENT_FACTOR,
    }
    HISTORY_PATH.write_text(
        json.dumps(hist_data, indent=2),
        encoding="utf-8",
    )
    print(f"\n[Train] Training history saved to {HISTORY_PATH.name}")

    print("\n" + "=" * 50)
    print("[Train] Training complete!")
    print(f"  Model: {MODEL_PATH.name}")
    print(f"  Labels: {LABEL_PATH.name}")
    print(f"  Accuracy: {accuracy:.2%}")
    print("=" * 50)


if __name__ == "__main__":
    np.random.seed(RANDOM_SEED)  # [#14] Reproducibility
    tf.random.set_seed(RANDOM_SEED)
    train_gesture_model()
