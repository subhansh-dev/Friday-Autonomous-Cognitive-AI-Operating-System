# -*- coding: utf-8 -*-
"""
model.py — FRIDAY Gesture Recognition Model
LSTM-based sequence classifier for hand gesture recognition.
"""

import tensorflow as tf
from tensorflow.keras import layers, models, callbacks
import numpy as np
from pathlib import Path
from typing import Optional


# ── Configuration ──────────────────────────────────────────────────

MODEL_DIR = Path(__file__).parent.resolve()
DEFAULT_MODEL_PATH = MODEL_DIR / "gesture_model.keras"  # [#1] .keras format
LEGACY_MODEL_PATH = MODEL_DIR / "gesture_model.h5"

# Input dimensions — must match collect_data.py
SEQUENCE_LENGTH = 20
FEATURES_PER_FRAME = 126  # [#2] 21 landmarks × 3 coords × 2 hands


def build_model(
    num_classes: int,
    sequence_length: int = SEQUENCE_LENGTH,
    features: int = FEATURES_PER_FRAME,
    learning_rate: float = 0.001,
) -> tf.keras.Model:
    """
    Build gesture recognition LSTM model.

    Architecture:
    - Bidirectional LSTM for forward + backward temporal patterns
    - Dropout for regularization (critical with small datasets)
    - Batch normalization for training stability
    """
    model = models.Sequential([
        layers.Input(shape=(sequence_length, features)),

        # [#3] Bidirectional LSTM — captures patterns in both directions
        layers.Bidirectional(layers.LSTM(
            128,
            return_sequences=True,
            activation="tanh",           # [#4] tanh, not relu
            recurrent_activation="sigmoid",
            dropout=0.2,                 # [#5] Input dropout
            recurrent_dropout=0.1,       # Recurrent dropout
        )),
        layers.BatchNormalization(),     # [#6] Stabilize training

        layers.Bidirectional(layers.LSTM(
            64,
            return_sequences=False,
            activation="tanh",
            recurrent_activation="sigmoid",
            dropout=0.2,
            recurrent_dropout=0.1,
        )),
        layers.BatchNormalization(),

        # Dense head
        layers.Dense(64, activation="relu"),
        layers.Dropout(0.3),            # [#5] Prevent overfitting
        layers.BatchNormalization(),

        layers.Dense(32, activation="relu"),
        layers.Dropout(0.2),

        layers.Dense(num_classes, activation="softmax"),
    ])

    # [#7] Adam with explicit learning rate for tuning
    optimizer = tf.keras.optimizers.Adam(learning_rate=learning_rate)

    model.compile(
        optimizer=optimizer,
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )

    return model


def get_training_callbacks(
    model_path: Optional[str] = None,
) -> list:
    """Get standard training callbacks."""
    cb = [
        # [#8] Stop early if validation loss stops improving
        callbacks.EarlyStopping(
            monitor="val_loss",
            patience=15,
            restore_best_weights=True,
            verbose=1,
        ),
        # [#8] Reduce learning rate on plateau
        callbacks.ReduceLROnPlateau(
            monitor="val_loss",
            factor=0.5,
            patience=5,
            min_lr=1e-6,
            verbose=1,
        ),
    ]

    if model_path:
        cb.append(
            callbacks.ModelCheckpoint(
                filepath=str(model_path),
                monitor="val_accuracy",
                save_best_only=True,
                verbose=1,
            )
        )

    return cb


def augment_sequence(sequence: np.ndarray) -> np.ndarray:
    """
    Data augmentation for gesture sequences. [#9]
    Critical when you only have ~30 samples per gesture.
    """
    augmented = sequence.copy()

    # Time warping — slight speed variation
    if np.random.random() > 0.5:
        stretch = np.random.uniform(0.9, 1.1)
        indices = np.linspace(0, len(augmented) - 1,
                              int(len(augmented) * stretch))
        indices = np.clip(indices, 0, len(augmented) - 1).astype(int)
        augmented = augmented[indices]
        # Pad or trim back to original length
        if len(augmented) < len(sequence):
            pad_len = len(sequence) - len(augmented)
            augmented = np.vstack([
                augmented,
                np.zeros((pad_len, augmented.shape[1])),
            ])
        elif len(augmented) > len(sequence):
            augmented = augmented[:len(sequence)]

    # Add Gaussian noise
    noise = np.random.normal(0, 0.005, augmented.shape)
    augmented = augmented + noise

    # Random scaling (simulates different hand sizes / distances)
    scale = np.random.uniform(0.95, 1.05)
    augmented = augmented * scale

    # Random frame dropout — simulate missed detections
    if np.random.random() > 0.7:
        drop_idx = np.random.randint(0, len(augmented))
        augmented[drop_idx] = augmented[max(0, drop_idx - 1)]

    return augmented.astype(np.float32)


def generate_augmented_dataset(
    X: np.ndarray,
    y: np.ndarray,
    augment_factor: int = 5,
) -> tuple:
    """
    Generate augmented copies of the training data. [#9]
    30 samples × 5 augmentations = 150 effective samples per gesture.
    """
    X_aug = [X]
    y_aug = [y]

    for i in range(augment_factor):
        X_copy = np.array([
            augment_sequence(seq) for seq in X
        ])
        X_aug.append(X_copy)
        y_aug.append(y)

    return np.concatenate(X_aug), np.concatenate(y_aug)


def save_model(model: tf.keras.Model, path: Optional[str] = None):
    """Save model in .keras format (with .h5 fallback)."""
    save_path = Path(path) if path else DEFAULT_MODEL_PATH
    save_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(save_path))
    print(f"[Model] Saved to {save_path} "
          f"({save_path.stat().st_size / 1024:.0f} KB)")


def load_model(path: Optional[str] = None) -> tf.keras.Model:
    """
    Load model — tries .keras first, falls back to .h5. [#1]
    """
    if path:
        return tf.keras.models.load_model(path)

    # Try new format first
    if DEFAULT_MODEL_PATH.exists():
        print(f"[Model] Loading {DEFAULT_MODEL_PATH}")
        return tf.keras.models.load_model(str(DEFAULT_MODEL_PATH))

    # Fall back to legacy .h5
    if LEGACY_MODEL_PATH.exists():
        print(f"[Model] Loading legacy {LEGACY_MODEL_PATH}")
        return tf.keras.models.load_model(str(LEGACY_MODEL_PATH))

    raise FileNotFoundError(
        f"No model found at {DEFAULT_MODEL_PATH} or {LEGACY_MODEL_PATH}"
    )


def get_model_summary(num_classes: int) -> str:
    """Get a string model summary (for logging)."""
    model = build_model(num_classes)
    lines = []
    model.summary(print_fn=lambda x: lines.append(x))
    return "\n".join(lines)
