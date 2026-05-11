# -*- coding: utf-8 -*-
"""
holo_builder.py — Iron Man Holographic AR Builder (v4.0)
[Q] cycles draw planes (XY/XZ/YZ)
[Tab] toggles AR mode (webcam background)
[Click] select object | [G+drag] move | [S+drag] scale | [Del] delete
AR Gestures: pinch=draw | fist=grab+move | peace=scale | open=release
[FIX] Camera upside-down (texture V coords flipped)
[FIX] Gesture hand dropout tolerance (10-frame grace)
[FIX] OpenCV CAP_DSHOW + warmup + error recovery
[FIX] Gesture confidence lowered to 0.6
[FIX] Alt+drag = move without key (Alt+drag also enables drawing over objects)
[v4.0] Iron Man UI overhaul: radar grid, sci-fi HUD, glow effects, holographic AR
"""
import math
import random
import sys
import time
import threading
import traceback
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from collections import deque

import numpy as np

try:
    import pygame
    from pygame.locals import *
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False

try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    HAS_OPENGL = True
except ImportError:
    HAS_OPENGL = False

try:
    import cv2
    # Suppress OpenCV MSMF grab-frame warnings (they spam the console on camera errors)
    try:
        cv2.setLogLevel(0)  # CV_LOG_LEVEL_SILENT
    except Exception:
        pass
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import mediapipe as mp
    from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode
    from mediapipe.tasks.python.core.base_options import BaseOptions
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False


class SoundFX:
    def __init__(self):
        self.mixer_initialized = False
        self._init_mixer()

    def _init_mixer(self):
        if not HAS_PYGAME:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            self.mixer_initialized = True
        except Exception:
            self.mixer_initialized = False

    def _play_tone(self, freq, duration, volume=0.3):
        if not self.mixer_initialized:
            return
        try:
            import array, math
            sample_rate = 22050
            n_samples = int(sample_rate * duration)
            buf = array.array('h', [int(volume * 32767 * math.sin(2 * math.pi * freq * i / sample_rate))
                                      for i in range(n_samples)])
            sound = pygame.mixer.Sound(buffer=buf)
            sound.set_volume(volume)
            sound.play()
        except Exception:
            pass  # silently swallowed

    def play_power_up(self):
        self._play_tone(440, 0.5, 0.3)
        time.sleep(0.3)
        self._play_tone(880, 0.2, 0.3)

    def play_shutdown(self):
        self._play_tone(880, 0.15, 0.3)
        time.sleep(0.15)
        self._play_tone(440, 0.15, 0.3)

    def play_gesture(self):
        self._play_tone(1200, 0.1, 0.2)

    def play_ready(self):
        self._play_tone(660, 0.2, 0.3)


class ARVisualFX:
    def __init__(self, width=1280, height=720):
        self.width = width
        self.height = height
        self.time_start = time.time()
        self.scan_timer = 0
        self.scan_interval = 5.0
        self.active_streams = []
        self.active_circuits = []
        self._init_streams()
        self._init_circuits()

    def _init_streams(self):
        for _ in range(8):
            side = random.choice([-1, 1])
            x = self.width // 2 + side * (self.width // 4 + random.randint(-50, 50))
            speed = random.uniform(0.5, 1.5)
            self.active_streams.append({'x': x, 'speed': speed, 'amplitude': random.uniform(2, 8)})

    def _init_circuits(self):
        for _ in range(12):
            region = random.choice(['top', 'bottom'])
            y = 50 if region == 'top' else self.height - 50
            x = random.randint(100, self.width - 100)
            self.active_circuits.append({'x': x, 'y': y, 'region': region, 'phase': random.random() * math.pi * 2})

    def update(self):
        now = time.time() - self.time_start
        if now - self.scan_timer >= self.scan_interval:
            self.scan_timer = now
        for s in self.active_streams:
            s['y'] = s.get('y', 0) + s['speed']
            if s['y'] > self.height:
                s['y'] = 0

    def draw(self, width, height):
        self.width = width
        self.height = height
        t = time.time() - self.time_start
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        self._draw_data_streams(t)
        self._draw_circuit_lines(t)
        self._draw_waveforms(t)
        self._draw_reticle(t)
        if t - self.scan_timer < 1.0:
            self._draw_scan_line(t - self.scan_timer)
        # Restore GL state
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_LIGHTING)

    def _draw_data_streams(self, t):
        glColor4f(0.0, 0.83, 1.0, 0.15)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        for s in self.active_streams:
            y = s.get('y', 0)
            amp = s.get('amplitude', 5)
            wave = amp * math.sin(t * 2 + s['x'] * 0.01)
            glVertex2f(s['x'] + wave, y)
            glVertex2f(s['x'] + wave * 0.5, y + 80)
        glEnd()

    def _draw_circuit_lines(self, t):
        glColor4f(0.0, 0.4, 1.0, 0.1)
        glLineWidth(0.8)
        glBegin(GL_LINES)
        for c in self.active_circuits:
            pulse = 0.5 + 0.5 * math.sin(t * 1.5 + c['phase'])
            x, y = c['x'], c['y']
            glVertex2f(x - 20, y)
            glVertex2f(x + 20, y)
            glVertex2f(x, y - 10 * pulse)
            glVertex2f(x, y + 10 * pulse)
        glEnd()

    def _draw_waveforms(self, t):
        glColor4f(0.0, 0.83, 1.0, 0.12)
        glLineWidth(1.0)
        glBegin(GL_LINE_STRIP)
        for i in range(100):
            x = self.width * 0.1 + (self.width * 0.8) * i / 100
            amp = 15 * math.sin(t * 3 + i * 0.1) * math.sin(t * 0.5)
            y = self.height - 80 + amp
            glVertex2f(x, y)
        glEnd()

    def _draw_reticle(self, t):
        glColor4f(0.0, 0.83, 1.0, 0.08)
        glLineWidth(1.5)
        cx, cy = self.width // 2, self.height // 2
        r = min(self.width, self.height) * 0.35
        rot = t * 0.2
        glBegin(GL_LINE_LOOP)
        for i in range(4):
            angle = rot + i * math.pi / 2
            a1, a2 = angle, angle + 0.3
            glVertex2f(cx + r * math.cos(a1), cy + r * math.sin(a1))
            glVertex2f(cx + r * math.cos(a2), cy + r * math.sin(a2))
        glEnd()

    def _draw_scan_line(self, progress):
        glColor4f(0.0, 0.83, 1.0, 0.3 * (1 - progress))
        glLineWidth(2.0)
        glBegin(GL_LINES)
        y = self.height * progress
        glVertex2f(0, y)
        glVertex2f(self.width, y)
        glEnd()


# ── Model Path ─────────────────────────────────────────────────────
def _get_base():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

_HAND_MODEL = str(_get_base() / "brain" / "hand_landmarker.task")


# ── Data Structures ───────────────────────────────────────────────────

@dataclass
class StrokePoint:
    x: float
    y: float
    z: float
    pressure: float = 1.0
    timestamp: float = 0.0


@dataclass
class Stroke:
    points: List[StrokePoint] = field(default_factory=list)
    color: Tuple[float, float, float] = (0.0, 1.0, 0.85)
    thickness: float = 3.0
    depth: float = 0.0
    extrude: float = 0.05
    closed: bool = False
    timestamp: float = 0.0

    def add_point(self, x, y, z, pressure=1.0):
        self.points.append(StrokePoint(x, y, z, pressure, time.time()))

    def is_valid(self):
        return len(self.points) >= 2

    def get_vertices(self):
        if not self.points:
            return np.empty((0, 3))
        return np.array([[p.x, p.y, p.z] for p in self.points])

    def get_length(self):
        verts = self.get_vertices()
        if len(verts) < 2:
            return 0.0
        return float(np.sum(np.linalg.norm(np.diff(verts, axis=0), axis=1)))


@dataclass
class HoloObject:
    vertices: np.ndarray
    faces: np.ndarray
    normals: np.ndarray
    color: Tuple[float, float, float, float] = (0.0, 1.0, 0.85, 0.7)
    wireframe_color: Tuple[float, float, float, float] = (0.0, 1.0, 0.85, 1.0)
    name: str = "object"
    created: float = 0.0

    def get_center(self):
        if len(self.vertices) == 0:
            return np.zeros(3)
        return np.mean(self.vertices, axis=0)

    def get_radius(self):
        if len(self.vertices) == 0:
            return 0.0
        center = self.get_center()
        return float(np.max(np.linalg.norm(self.vertices - center, axis=1)))


# ── Stroke → 3D Mesh ─────────────────────────────────────────────────

class StrokeMesher:
    @staticmethod
    def extrude_stroke(stroke, depth=0.05, segments=8):
        pts = stroke.get_vertices()
        if len(pts) < 2:
            return None
        if np.all(pts[:, 2] == pts[0, 2]):
            pts[:, 2] = stroke.depth
        n_pts = len(pts)
        radius = stroke.thickness * 0.002
        verts, normals, faces = [], [], []
        for i in range(n_pts):
            if i == 0:
                tangent = pts[1] - pts[0]
            elif i == n_pts - 1:
                tangent = pts[-1] - pts[-2]
            else:
                tangent = pts[i + 1] - pts[i - 1]
            tangent = tangent / (np.linalg.norm(tangent) + 1e-8)
            up = np.array([0, 0, 1])
            if abs(np.dot(tangent, up)) > 0.99:
                up = np.array([0, 1, 0])
            normal = np.cross(tangent, up)
            normal = normal / (np.linalg.norm(normal) + 1e-8)
            binormal = np.cross(tangent, normal)
            for j in range(segments):
                angle = 2 * math.pi * j / segments
                offset = (normal * math.cos(angle) + binormal * math.sin(angle)) * radius
                verts.append(pts[i] + offset)
                normals.append(normal * math.cos(angle) + binormal * math.sin(angle))
        for i in range(n_pts - 1):
            for j in range(segments):
                jn = (j + 1) % segments
                a, b = i * segments + j, i * segments + jn
                c, d = (i + 1) * segments + j, (i + 1) * segments + jn
                faces.append([a, c, b])
                faces.append([b, c, d])
        cs = np.mean(pts[:1], axis=0)
        ce = np.mean(pts[-1:], axis=0)
        idx_s = len(verts)
        verts.append(cs)
        normals.append(-(pts[1] - pts[0]))
        idx_e = len(verts)
        verts.append(ce)
        normals.append(pts[-1] - pts[-2])
        for j in range(segments):
            jn = (j + 1) % segments
            faces.append([idx_s, jn, j])
            faces.append([idx_e, (n_pts - 1) * segments + j, (n_pts - 1) * segments + jn])
        return HoloObject(
            vertices=np.array(verts, dtype=np.float32),
            faces=np.array(faces, dtype=np.uint32),
            normals=np.array(normals, dtype=np.float32),
            color=(*stroke.color, 0.7),
            wireframe_color=(*stroke.color, 1.0),
            name=f"stroke_{int(stroke.timestamp)}",
            created=time.time(),
        )

    @staticmethod
    def ribbon_stroke(stroke, width=0.02):
        pts = stroke.get_vertices()
        if len(pts) < 2:
            return None
        n = len(pts)
        verts, faces = [], []
        hw = width * stroke.thickness * 0.001
        for i in range(n):
            if i == 0:
                tangent = pts[1] - pts[0]
            elif i == n - 1:
                tangent = pts[-1] - pts[-2]
            else:
                tangent = pts[i + 1] - pts[i - 1]
            t2d = tangent[:2]
            norm = np.linalg.norm(t2d)
            t2d = t2d / norm if norm > 1e-8 else np.array([1.0, 0.0])
            perp = np.array([-t2d[1], t2d[0], 0.0]) * hw
            verts.append(pts[i] + perp)
            verts.append(pts[i] - perp)
        for i in range(n - 1):
            a, b, c, d = i * 2, i * 2 + 1, (i + 1) * 2, (i + 1) * 2 + 1
            faces.append([a, c, b])
            faces.append([b, c, d])
        normals = np.zeros_like(np.array(verts))
        normals[:, 2] = 1.0
        return HoloObject(
            vertices=np.array(verts, dtype=np.float32),
            faces=np.array(faces, dtype=np.uint32),
            normals=normals,
            color=(*stroke.color, 0.5),
            wireframe_color=(*stroke.color, 1.0),
            name=f"ribbon_{int(stroke.timestamp)}",
            created=time.time(),
        )


# ── Camera ────────────────────────────────────────────────────────────

class OrbitCamera:
    def __init__(self):
        self.distance = 3.0
        self.yaw = 45.0
        self.pitch = 25.0
        self.target = np.array([0.0, 0.0, 0.0])
        self.sensitivity = 0.3
        self.zoom_speed = 0.15
        self.pan_speed = 0.005

    def get_eye(self):
        ry = math.radians(self.yaw)
        rp = math.radians(self.pitch)
        return self.target + np.array([
            self.distance * math.cos(rp) * math.sin(ry),
            self.distance * math.cos(rp) * math.cos(ry),
            self.distance * math.sin(rp),
        ])

    def apply(self):
        eye = self.get_eye()
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        gluLookAt(eye[0], eye[1], eye[2],
                  self.target[0], self.target[1], self.target[2], 0, 0, 1)

    def orbit(self, dx, dy):
        self.yaw += dx * self.sensitivity
        self.pitch = max(-89, min(89, self.pitch + dy * self.sensitivity))

    def zoom(self, delta):
        self.distance = max(0.5, min(50, self.distance * (1 - delta * self.zoom_speed)))

    def pan(self, dx, dy):
        ry = math.radians(self.yaw)
        right = np.array([math.cos(ry), -math.sin(ry), 0])
        up = np.array([0, 0, 1])
        self.target += right * dx * self.pan_speed * self.distance
        self.target += up * dy * self.pan_speed * self.distance

    def reset(self):
        self.distance = 3.0
        self.yaw = 45.0
        self.pitch = 25.0
        self.target = np.array([0.0, 0.0, 0.0])


# ── Projector ─────────────────────────────────────────────────────────

class Projector:
    PLANES = ["XY", "XZ", "YZ"]

    def __init__(self, camera):
        self.camera = camera
        self.draw_plane = "XY"

    def next_plane(self):
        idx = self.PLANES.index(self.draw_plane)
        self.draw_plane = self.PLANES[(idx + 1) % len(self.PLANES)]
        return self.draw_plane

    def screen_to_world(self, mx, my, width, height, depth=0.0):
        mv = glGetDoublev(GL_MODELVIEW_MATRIX)
        pj = glGetDoublev(GL_PROJECTION_MATRIX)
        vp = glGetIntegerv(GL_VIEWPORT)
        my_gl = vp[3] - my
        near = np.array(gluUnProject(mx, my_gl, 0.0, mv, pj, vp))
        far = np.array(gluUnProject(mx, my_gl, 1.0, mv, pj, vp))
        d = far - near
        n = np.linalg.norm(d)
        if n < 1e-8:
            return near
        d /= n
        if self.draw_plane == "XY":
            axis = 2
        elif self.draw_plane == "XZ":
            axis = 1
        else:
            axis = 0
        if abs(d[axis]) < 1e-8:
            t = 0.5
        else:
            t = (depth - near[axis]) / d[axis]
        return near + d * max(0, min(t, 100))

    def screen_to_ray(self, mx, my, width, height):
        mv = glGetDoublev(GL_MODELVIEW_MATRIX)
        pj = glGetDoublev(GL_PROJECTION_MATRIX)
        vp = glGetIntegerv(GL_VIEWPORT)
        my_gl = vp[3] - my
        near = np.array(gluUnProject(mx, my_gl, 0.0, mv, pj, vp))
        far = np.array(gluUnProject(mx, my_gl, 1.0, mv, pj, vp))
        d = far - near
        n = np.linalg.norm(d)
        d = d / n if n > 1e-8 else np.array([0, 0, -1])
        return near, d


# ── Gesture Controller (Dual-Hand) — Iron Man Edition ────────────────

class GestureController:
    """Low-level hand landmark detector — tracks up to 2 hands via MediaPipe.

    Iron Man feel:
    - Angle-based finger detection (works with tilted/rotated hands)
    - Spring-physics position smoothing (responsive, no jitter)
    - Velocity tracking for motion prediction
    - Adaptive pinch threshold based on palm size
    - Weighted gesture voting (recent frames dominate)
    - Fast hand-lost recovery (4 frames, not 12)
    """
    NONE = "none"
    OPEN = "open"
    POINT = "point"
    PINCH = "pinch"
    FIST = "fist"
    PEACE = "peace"

    # Spring physics for position smoothing
    _SPRING_STIFFNESS = 18.0    # higher = snappier tracking
    _SPRING_DAMPING = 0.75      # critical damping ratio
    # Smoothing alpha for velocity
    _VEL_ALPHA = 0.4
    # Gesture vote: recent frames weighted exponentially
    _VOTE_DECAY = 0.70          # lower = recent frames dominate more
    # Minimum confidence to allow gesture change
    _CONFIDENCE_THRESHOLD = 0.40

    def __init__(self, num_hands=2):
        self.enabled = False
        self.landmarker = None
        self.num_hands = num_hands
        # Per-hand state (index 0 = primary, 1 = secondary)
        self.hand_positions = [None, None]      # smoothed (nx, ny)
        self.hand_positions_raw = [None, None]   # unsmoothed
        self.hand_velocities = [(0.0, 0.0), (0.0, 0.0)]
        self.gestures = [self.NONE, self.NONE]
        self.prev_gestures = [self.NONE, self.NONE]
        self.gesture_confidence = [0.0, 0.0]
        self.pinch_dists = [1.0, 1.0]
        self.palm_sizes = [0.1, 0.1]
        self.landmarks = [None, None]
        self._gesture_buffers = [deque(maxlen=7), deque(maxlen=7)]
        self._hand_lost_frames = [0, 0]
        self._hand_lost_limit = 6               # ~100ms at 60fps — tolerant but not sticky
        self._last_process_time = [0.0, 0.0]
        # Spring physics state per hand
        self._spring_pos = [None, None]         # current spring position
        self._spring_vel = [(0.0, 0.0), (0.0, 0.0)]
        # Backward-compat single-hand properties
        self.hand_pos = None
        self.gesture = self.NONE
        self.prev_gesture = self.NONE
        self.pinch_dist = 1.0
        self._last_lm = None

        if not HAS_MEDIAPIPE:
            print("[HOLO] MediaPipe not installed — gestures disabled")
            print("[HOLO] Install with: pip install mediapipe")
            return
        if not Path(_HAND_MODEL).exists():
            print(f"[HOLO] Hand model not found: {_HAND_MODEL}")
            print("[HOLO] Download hand_landmarker.task to brain/ folder")
            return
        try:
            opts = HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=_HAND_MODEL),
                running_mode=RunningMode.VIDEO,
                num_hands=num_hands,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.4,
                min_tracking_confidence=0.4,
            )
            self.landmarker = HandLandmarker.create_from_options(opts)
            self.enabled = True
            print(f"[HOLO] Gesture controller ready ({num_hands}-hand mode)")
        except Exception as e:
            err_str = str(e)
            if "WinError 193" in err_str or "not a valid Win32" in err_str:
                print(f"[HOLO] Gestures unavailable: MediaPipe native DLL failed to load")
                print(f"[HOLO] This is a known MediaPipe issue on some Python/Windows combos.")
                print(f"[HOLO] Fix options:")
                print(f"[HOLO]   1. Reinstall MediaPipe: pip uninstall mediapipe && pip install mediapipe")
                print(f"[HOLO]   2. If that fails, downgrade Python to 3.12 (won't affect Friday)")
                print(f"[HOLO]   3. Or try: pip install mediapipe==0.10.18 (last stable for your setup)")
            else:
                print(f"[HOLO] Gestures unavailable: {e}")

    @staticmethod
    def _palm_size(lm):
        """Estimate palm size from wrist-to-middle-finger-base distance."""
        wx, wy = lm[0].x, lm[0].y
        mx, my = lm[9].x, lm[9].y
        return math.hypot(mx - wx, my - wy)

    @staticmethod
    def _finger_angle(lm, tip_idx, pip_idx, mcp_idx):
        """Compute angle at PIP joint — robust to hand tilt/rotation.

        Returns angle in radians. 0 = fully extended, pi = fully curled.
        """
        # Vector from PIP to MCP (towards wrist)
        v1_x = lm[mcp_idx].x - lm[pip_idx].x
        v1_y = lm[mcp_idx].y - lm[pip_idx].y
        v1_z = lm[mcp_idx].z - lm[pip_idx].z
        # Vector from PIP to tip (towards fingertip)
        v2_x = lm[tip_idx].x - lm[pip_idx].x
        v2_y = lm[tip_idx].y - lm[pip_idx].y
        v2_z = lm[tip_idx].z - lm[pip_idx].z
        # Dot product → cos(angle)
        dot = v1_x * v2_x + v1_y * v2_y + v1_z * v2_z
        mag1 = math.sqrt(v1_x**2 + v1_y**2 + v1_z**2)
        mag2 = math.sqrt(v2_x**2 + v2_y**2 + v2_z**2)
        if mag1 < 1e-6 or mag2 < 1e-6:
            return math.pi  # assume curled if degenerate
        cos_a = max(-1.0, min(1.0, dot / (mag1 * mag2)))
        return math.acos(cos_a)

    @classmethod
    def _classify(cls, lm, palm_size=0.1):
        """Classify a single hand's gesture from landmarks.

        Uses angle-based finger detection — works with tilted/rotated hands.
        """
        # Finger angles: 0 = extended, ~pi = curled
        # Landmark indices: tip=8, PIP=6, MCP=5 for index finger
        index_angle = cls._finger_angle(lm, 8, 6, 5)
        middle_angle = cls._finger_angle(lm, 12, 10, 9)
        ring_angle = cls._finger_angle(lm, 16, 14, 13)
        pinky_angle = cls._finger_angle(lm, 20, 18, 17)

        # Threshold: < 1.2 rad (~69°) = extended, > 1.5 rad (~86°) = curled
        _EXT = 1.2
        _CURL = 1.5
        index_up = index_angle < _EXT
        middle_up = middle_angle < _EXT
        ring_up = ring_angle < _EXT
        pinky_up = pinky_angle < _EXT
        ext = sum([index_up, middle_up, ring_up, pinky_up])

        # Thumb: use distance from tip to index MCP (more robust than angle)
        pinch_dist = math.hypot(lm[4].x - lm[8].x, lm[4].y - lm[8].y,
                                lm[4].z - lm[8].z)

        # Adaptive pinch threshold
        pinch_threshold = 0.07 * (palm_size / 0.15)
        pinch_threshold = max(0.04, min(0.12, pinch_threshold))

        if ext == 0:
            return "fist", pinch_dist
        elif pinch_dist < pinch_threshold and ext >= 1:
            return "pinch", pinch_dist
        elif index_up and middle_up and not ring_up and not pinky_up:
            return "peace", pinch_dist
        elif index_up and not middle_up and not ring_up and not pinky_up:
            return "point", pinch_dist
        elif ext == 2:
            # Any other 2-finger combo (not peace) — treat as point-ish select
            return "point", pinch_dist
        elif ext >= 3:
            return "open", pinch_dist
        return "open", pinch_dist

    def _smooth_position(self, idx, raw_x, raw_y):
        """Spring-physics position smoothing — Iron Man feel.

        Uses a damped spring system: responsive on fast movements,
        smooth on slow movements, no jitter.
        """
        now = time.time()
        dt = max(0.001, now - self._last_process_time[idx])
        self._last_process_time[idx] = now

        if self._spring_pos[idx] is None:
            # First frame — snap to position
            self._spring_pos[idx] = (raw_x, raw_y)
            self._spring_vel[idx] = (0.0, 0.0)
            self.hand_velocities[idx] = (0.0, 0.0)
            return raw_x, raw_y

        sx, sy = self._spring_pos[idx]
        vx, vy = self._spring_vel[idx]

        # Spring force: F = -k * (pos - target) - c * velocity
        k = self._SPRING_STIFFNESS
        c = 2.0 * self._SPRING_DAMPING * math.sqrt(k)  # critical damping

        fx = -k * (sx - raw_x) - c * vx
        fy = -k * (sy - raw_y) - c * vy

        # Semi-implicit Euler integration
        vx_new = vx + fx * dt
        vy_new = vy + fy * dt
        sx_new = sx + vx_new * dt
        sy_new = sy + vy_new * dt

        self._spring_pos[idx] = (sx_new, sy_new)
        self._spring_vel[idx] = (vx_new, vy_new)

        # Track velocity for prediction (smoothed)
        raw_vx = (raw_x - sx) / dt if dt > 0 else 0.0
        raw_vy = (raw_y - sy) / dt if dt > 0 else 0.0
        va = self._VEL_ALPHA
        ovx, ovy = self.hand_velocities[idx]
        self.hand_velocities[idx] = (
            ovx + va * (raw_vx - ovx),
            ovy + va * (raw_vy - ovy),
        )

        return sx_new, sy_new

    def _weighted_vote(self, idx):
        """Weighted gesture voting — recent frames count more.

        Returns (gesture, confidence).
        """
        buf = list(self._gesture_buffers[idx])
        if not buf:
            return self.NONE, 0.0

        scores = {}
        n = len(buf)
        for i, g in enumerate(buf):
            weight = self._VOTE_DECAY ** (n - 1 - i)
            scores[g] = scores.get(g, 0.0) + weight

        best = max(scores, key=scores.get)
        total = sum(scores.values())
        confidence = scores[best] / total if total > 0 else 0.0
        return best, confidence

    def process(self, rgb_frame):
        if not self.enabled or self.landmarker is None:
            return
        try:
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            ts_ms = int(time.monotonic_ns() // 1_000_000)
            result = self.landmarker.detect_for_video(mp_img, ts_ms)

            detected = set()
            if result.hand_landmarks:
                for idx, lm in enumerate(result.hand_landmarks):
                    if idx >= self.num_hands:
                        break
                    detected.add(idx)
                    self._hand_lost_frames[idx] = 0
                    self.landmarks[idx] = lm

                    # Raw anchor (index finger tip)
                    raw_x, raw_y = lm[8].x, lm[8].y
                    self.hand_positions_raw[idx] = (raw_x, raw_y)

                    # Spring-physics smoothed position
                    sx, sy = self._smooth_position(idx, raw_x, raw_y)
                    self.hand_positions[idx] = (sx, sy)

                    # Palm size for adaptive thresholds
                    ps = self._palm_size(lm)
                    self.palm_sizes[idx] = ps

                    # Classify gesture with angle-based detection
                    raw_gesture, pd = self._classify(lm, ps)
                    self.pinch_dists[idx] = pd
                    self._gesture_buffers[idx].append(raw_gesture)

                    # Weighted vote
                    voted, confidence = self._weighted_vote(idx)
                    self.gesture_confidence[idx] = confidence

                    # Update gesture with confidence gating
                    self.prev_gestures[idx] = self.gestures[idx]
                    if confidence >= self._CONFIDENCE_THRESHOLD:
                        if voted != self.gestures[idx]:
                            self.gestures[idx] = voted

            # Handle lost hands — fast recovery (4 frames)
            for idx in range(self.num_hands):
                if idx not in detected:
                    self._hand_lost_frames[idx] += 1
                    if self._hand_lost_frames[idx] >= self._hand_lost_limit:
                        self.prev_gestures[idx] = self.gestures[idx]
                        self.gestures[idx] = self.NONE
                        self.hand_positions[idx] = None
                        self.hand_positions_raw[idx] = None
                        self.landmarks[idx] = None
                        self._gesture_buffers[idx].clear()
                        self.hand_velocities[idx] = (0.0, 0.0)
                        self._spring_pos[idx] = None
                        self._spring_vel[idx] = (0.0, 0.0)

            # Backward-compat: primary hand = index 0
            self.hand_pos = self.hand_positions[0]
            self.prev_gesture = self.gesture
            self.gesture = self.gestures[0]
            self.pinch_dist = self.pinch_dists[0]
            self._last_lm = self.landmarks[0]
        except Exception as e:
            if not hasattr(self, '_process_err_count'):
                self._process_err_count = 0
            self._process_err_count += 1
            if self._process_err_count <= 3:
                print(f"[HOLO] Gesture process error: {e}")
            elif self._process_err_count == 4:
                print("[HOLO] Gesture errors suppressed (too many)")

    def predict_position(self, idx, dt=0.033):
        """Predict hand position dt seconds ahead using velocity."""
        pos = self.hand_positions[idx]
        vel = self.hand_velocities[idx]
        if pos is None:
            return None
        return (pos[0] + vel[0] * dt, pos[1] + vel[1] * dt)

    @property
    def just_changed(self):
        return self.gesture != self.prev_gesture

    @property
    def both_hands_detected(self):
        return (self.hand_positions[0] is not None and
                self.hand_positions[1] is not None)

    def cleanup(self):
        if self.landmarker:
            try:
                self.landmarker.close()
            except Exception:
                pass
            self.landmarker = None
        self.enabled = False


# ── Dual-Hand Gesture Manager — Iron Man Edition ─────────────────────

class DualHandGestureManager:
    """State machine for two-hand spatial interactions — Iron Man feel.

    States:
        IDLE        — no dual-hand interaction
        SCALE       — spreading/closing hands (distance-based) — zoom hologram
        ROTATE      — rotating hand pair (angle-based) — spin 3D model
        REPOSITION  — both fists moving together — pan the scene

    Gesture pairs (Iron Man mapping):
        Both fists           → REPOSITION (grab & move scene)
        Both open/pinch      → SCALE (spread = zoom in, close = zoom out)
        Both point           → ROTATE (twist to spin model)
        One fist + one open  → ROTATE (asymmetric grab & twist)
    """

    STATE_IDLE = "idle"
    STATE_SCALE = "scale"
    STATE_ROTATE = "rotate"
    STATE_REPOSITION = "reposition"

    # Thresholds — tuned for Iron Man responsiveness
    _SCALE_THRESHOLD = 0.006
    _ROTATE_THRESHOLD = 0.02     # ~1.1 degrees
    _MOVE_THRESHOLD = 0.004
    _DEBOUNCE_FRAMES = 2         # fast transitions
    _SMOOTH_ALPHA = 0.45         # less smoothing = more responsive
    _CONFIDENCE_WINDOW = 4
    _CONFIDENCE_MIN = 2          # only 2 of 4 frames need to agree

    def __init__(self):
        self.state = self.STATE_IDLE
        self._prev_state = self.STATE_IDLE
        self._debounce_counter = 0
        self._debounce_target = self.STATE_IDLE

        # Anchors (normalised screen positions)
        self._anchor_l = None
        self._anchor_r = None
        self._prev_anchor_l = None
        self._prev_anchor_r = None

        # Baseline measurements captured at gesture start
        self._baseline_dist = 0.0
        self._baseline_angle = 0.0
        self._baseline_mid = None

        # Smoothed outputs
        self.scale_factor = 1.0
        self.rotate_delta = 0.0
        self.move_delta = np.array([0.0, 0.0])

        # Velocity stabilisation
        self._scale_velocity = 0.0
        self._rotate_velocity = 0.0
        self._move_velocity = np.array([0.0, 0.0])

        # Per-hand confidence tracking
        self._gesture_history = [deque(maxlen=self._CONFIDENCE_WINDOW),
                                 deque(maxlen=self._CONFIDENCE_WINDOW)]

        # Frame-level state
        self.active = False
        self._frame_count = 0

    def update(self, gc: GestureController):
        """Process one frame of gesture data. Call every frame."""
        self._frame_count += 1
        h0 = gc.hand_positions[0]
        h1 = gc.hand_positions[1]
        g0 = gc.gestures[0]
        g1 = gc.gestures[1]

        self._gesture_history[0].append(g0)
        self._gesture_history[1].append(g1)

        if h0 is None or h1 is None:
            self._end_interaction()
            return

        # Enforce hand ordering: left = lower x, right = higher x
        if h0[0] <= h1[0]:
            left_pos, right_pos = h0, h1
            left_g, right_g = g0, g1
        else:
            left_pos, right_pos = h1, h0
            left_g, right_g = g1, g0

        intended = self._classify_pair(left_g, right_g)
        if intended is None:
            self._end_interaction()
            return

        if not self._check_confidence():
            self._end_interaction()
            return

        # Debounce state transitions — fast for Iron Man feel
        if intended != self.state:
            if self._debounce_counter == 0:
                self._debounce_target = intended
                self._debounce_counter = 1
            elif self._debounce_target == intended:
                self._debounce_counter += 1
            else:
                self._debounce_target = intended
                self._debounce_counter = 1

            if self._debounce_counter >= self._DEBOUNCE_FRAMES:
                self._transition_to(intended, left_pos, right_pos)
            else:
                return
        else:
            self._debounce_counter = 0

        if self.state == self.STATE_SCALE:
            self._apply_scale(left_pos, right_pos)
        elif self.state == self.STATE_ROTATE:
            self._apply_rotate(left_pos, right_pos)
        elif self.state == self.STATE_REPOSITION:
            self._apply_reposition(left_pos, right_pos)

        self._prev_anchor_l = left_pos
        self._prev_anchor_r = right_pos
        self.active = self.state != self.STATE_IDLE

    def _classify_pair(self, left_g, right_g):
        """Determine interaction type from a pair of gestures.

        Iron Man mapping:
        - Both fists → reposition (grab & move)
        - Both open/pinch → scale (spread/close)
        - Both point → rotate
        - Fist + open/pinch → rotate (asymmetric twist)
        """
        if left_g == "fist" and right_g == "fist":
            return self.STATE_REPOSITION
        if left_g in ("open", "pinch") and right_g in ("open", "pinch"):
            return self.STATE_SCALE
        if left_g == "point" and right_g == "point":
            return self.STATE_ROTATE
        if (left_g == "fist" and right_g in ("open", "pinch")) or \
           (right_g == "fist" and left_g in ("open", "pinch")):
            return self.STATE_ROTATE
        return None

    def _check_confidence(self):
        """Require consistent gestures — but be fast about it."""
        for hand_idx in range(2):
            buf = list(self._gesture_history[hand_idx])
            if len(buf) < self._CONFIDENCE_MIN:
                return False
            recent = buf[-self._CONFIDENCE_WINDOW:]
            valid = sum(1 for g in recent if g not in ("none",))
            if valid < self._CONFIDENCE_MIN:
                return False
        return True

    def _transition_to(self, new_state, left_pos, right_pos):
        """Transition to a new state, capturing baseline measurements."""
        self._prev_state = self.state
        self.state = new_state
        self._debounce_counter = 0

        dx = right_pos[0] - left_pos[0]
        dy = right_pos[1] - left_pos[1]
        self._baseline_dist = math.hypot(dx, dy)
        self._baseline_angle = math.atan2(dy, dx)
        self._baseline_mid = ((left_pos[0] + right_pos[0]) / 2,
                              (left_pos[1] + right_pos[1]) / 2)

        self.scale_factor = 1.0
        self.rotate_delta = 0.0
        self.move_delta = np.array([0.0, 0.0])
        self._scale_velocity = 0.0
        self._rotate_velocity = 0.0
        self._move_velocity = np.array([0.0, 0.0])

    def _end_interaction(self):
        """Return to idle when hands are lost or gestures are invalid."""
        if self.state != self.STATE_IDLE:
            self._prev_state = self.state
            self.state = self.STATE_IDLE
            self.active = False
            self.scale_factor = 1.0
            self.rotate_delta = 0.0
            self.move_delta = np.array([0.0, 0.0])
            self._debounce_counter = 0

    # ── Interaction math (smoothed, no dead zone) ─────────────────────

    def _apply_scale(self, left_pos, right_pos):
        """Compute scale factor from hand distance delta — zoom hologram."""
        dx = right_pos[0] - left_pos[0]
        dy = right_pos[1] - left_pos[1]
        current_dist = math.hypot(dx, dy)
        if self._baseline_dist < 1e-6:
            self._baseline_dist = current_dist
            return
        raw = current_dist / self._baseline_dist
        # Smooth but responsive
        self._scale_velocity = (self._SMOOTH_ALPHA * (raw - self.scale_factor) +
                                (1 - self._SMOOTH_ALPHA) * self._scale_velocity)
        self.scale_factor += self._scale_velocity
        self.scale_factor = max(0.05, min(20.0, self.scale_factor))

    def _apply_rotate(self, left_pos, right_pos):
        """Compute rotation angle from hand pair angle delta — spin model."""
        dx = right_pos[0] - left_pos[0]
        dy = right_pos[1] - left_pos[1]
        current_angle = math.atan2(dy, dx)
        delta = current_angle - self._baseline_angle
        while delta > math.pi:
            delta -= 2 * math.pi
        while delta < -math.pi:
            delta += 2 * math.pi
        self._rotate_velocity = (self._SMOOTH_ALPHA * (delta - self.rotate_delta) +
                                 (1 - self._SMOOTH_ALPHA) * self._rotate_velocity)
        self.rotate_delta += self._rotate_velocity
        self.rotate_delta = max(-math.pi, min(math.pi, self.rotate_delta))

    def _apply_reposition(self, left_pos, right_pos):
        """Compute movement delta from midpoint shift — pan scene."""
        mid = ((left_pos[0] + right_pos[0]) / 2,
               (left_pos[1] + right_pos[1]) / 2)
        if self._baseline_mid is None:
            self._baseline_mid = mid
            return
        raw_dx = mid[0] - self._baseline_mid[0]
        raw_dy = mid[1] - self._baseline_mid[1]
        raw = np.array([raw_dx, raw_dy])
        self._move_velocity = (self._SMOOTH_ALPHA * (raw - self.move_delta) +
                               (1 - self._SMOOTH_ALPHA) * self._move_velocity)
        self.move_delta += self._move_velocity


# ── Ray helpers ───────────────────────────────────────────────────────

def _ray_sphere(origin, direction, center, radius):
    oc = origin - center
    a = np.dot(direction, direction)
    b = 2 * np.dot(oc, direction)
    c = np.dot(oc, oc) - radius * radius
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    sq = math.sqrt(disc)
    t = (-b - sq) / (2 * a)
    if t < 0:
        t = (-b + sq) / (2 * a)
    return t if t >= 0 else None


# ── Interaction FX (Tony Stark feel) ─────────────────────────────────

class InteractionFX:
    """Cinematic interaction feedback system.

    Effects:
    - Object materialization: expanding rings + particle burst on creation
    - Selection pulse: glow aura that breathes on the selected object
    - Gesture transition: colour flash when gesture state changes
    - Hand trail: fading ghost trail of hand positions
    - Ambient energy: subtle floating wisps in the scene
    """

    def __init__(self):
        # Materialization effects (per-object)
        self._spawn_effects = []   # list of {center, t0, color, radius}
        # Selection pulse
        self._sel_pulse = 0.0
        # Gesture transition flash
        self._gesture_flash = 0.0
        self._gesture_flash_color = (0, 1, 0.85)
        # Hand trail (ring buffer of recent positions)
        self._trail = deque(maxlen=30)
        # Ambient wisps
        self._wisps = []
        for _ in range(20):
            self._wisps.append({
                'x': random.uniform(-3, 3), 'y': random.uniform(-3, 3),
                'z': random.uniform(-1, 2),
                'vx': random.uniform(-0.01, 0.01),
                'vy': random.uniform(-0.01, 0.01),
                'vz': random.uniform(-0.005, 0.005),
                'phase': random.uniform(0, math.pi * 2),
                'size': random.uniform(1.5, 4.0),
            })

    def trigger_spawn(self, center, color):
        """Call when a new object is created."""
        self._spawn_effects.append({
            'center': np.array(center, dtype=np.float32),
            't0': time.time(),
            'color': color,
            'radius': 0.0,
        })

    def trigger_gesture_change(self, gesture):
        """Call when gesture state changes."""
        colors = {
            'pinch': (1.0, 0.2, 0.4),
            'fist':  (1.0, 0.7, 0.0),
            'peace': (0.0, 1.0, 0.5),
            'open':  (0.0, 0.83, 1.0),
            'point': (0.0, 0.83, 1.0),
        }
        self._gesture_flash_color = colors.get(gesture, (0, 1, 0.85))
        self._gesture_flash = 1.0

    def add_trail_point(self, pos):
        """Add a hand position to the trail."""
        if pos is not None:
            self._trail.append((time.time(), pos))

    def update(self, dt):
        """Update all effects.  Call once per frame."""
        # Decay gesture flash
        self._gesture_flash = max(0, self._gesture_flash - dt * 4)
        # Selection pulse (continuous sine)
        self._sel_pulse = (self._sel_pulse + dt * 3) % (math.pi * 2)
        # Update wisps
        for w in self._wisps:
            w['x'] += w['vx']
            w['y'] += w['vy']
            w['z'] += w['vz']
            # Bounce
            for axis, lim in [('x', 3), ('y', 3), ('z', 2)]:
                if abs(w[axis]) > lim:
                    w['v' + axis] *= -1
        # Prune old spawn effects
        now = time.time()
        self._spawn_effects = [e for e in self._spawn_effects
                               if now - e['t0'] < 2.0]

    def draw_scene(self, selected_obj=None):
        """Draw 3D scene effects (call inside the GL scene, after objects)."""
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)

        t = time.time()

        # ── Spawn materialization rings ──────────────────────────────
        for e in self._spawn_effects:
            age = t - e['t0']
            if age > 2.0:
                continue
            progress = age / 2.0
            cx, cy, cz = e['center']
            c = e['color']

            # Expanding rings (3 concentric)
            for ring_i in range(3):
                ring_age = age - ring_i * 0.15
                if ring_age < 0:
                    continue
                rp = ring_age / 1.5
                if rp > 1:
                    continue
                r = rp * 0.5
                alpha = (1 - rp) * 0.6
                glColor4f(c[0], c[1], c[2], alpha)
                glLineWidth(2.0 - ring_i * 0.5)
                glBegin(GL_LINE_LOOP)
                for i in range(32):
                    a = 2 * math.pi * i / 32
                    glVertex3f(cx + r * math.cos(a),
                               cy + r * math.sin(a), cz)
                glEnd()

            # Particle burst (use points)
            n_burst = 12
            for i in range(n_burst):
                a = 2 * math.pi * i / n_burst + age * 2
                dist = age * 0.4
                px = cx + dist * math.cos(a)
                py = cy + dist * math.sin(a)
                pz = cz + 0.1 * math.sin(age * 5 + i)
                alpha = max(0, 1 - progress) * 0.7
                glColor4f(c[0], c[1], c[2], alpha)
                glPointSize(3.0 * (1 - progress))
                glBegin(GL_POINTS)
                glVertex3f(px, py, pz)
                glEnd()

        # ── Selection aura ───────────────────────────────────────────
        if selected_obj and len(selected_obj.vertices) > 0:
            center = selected_obj.get_center()
            r = selected_obj.get_radius() * 1.8
            pulse = 0.3 + 0.15 * math.sin(self._sel_pulse)
            # Outer aura ring
            glColor4f(0.0, 0.83, 1.0, pulse * 0.15)
            glLineWidth(1.0)
            glBegin(GL_LINE_LOOP)
            for i in range(48):
                a = 2 * math.pi * i / 48
                glVertex3f(center[0] + r * math.cos(a),
                           center[1] + r * math.sin(a), center[2])
            glEnd()
            # Inner breathing ring
            r2 = r * (0.7 + 0.1 * math.sin(self._sel_pulse * 1.5))
            glColor4f(0.0, 1.0, 0.85, pulse * 0.3)
            glLineWidth(1.5)
            glBegin(GL_LINE_LOOP)
            for i in range(36):
                a = 2 * math.pi * i / 36
                glVertex3f(center[0] + r2 * math.cos(a),
                           center[1] + r2 * math.sin(a), center[2])
            glEnd()

        # ── Ambient energy wisps ─────────────────────────────────────
        for w in self._wisps:
            pulse = 0.4 + 0.3 * math.sin(t * 1.5 + w['phase'])
            alpha = 0.08 * pulse
            glColor4f(0.0, 0.6, 0.8, alpha)
            glPointSize(w['size'])
            glBegin(GL_POINTS)
            glVertex3f(w['x'], w['y'], w['z'])
            glEnd()
            # Glow halo
            glColor4f(0.0, 0.4, 0.6, alpha * 0.3)
            glPointSize(w['size'] * 3)
            glBegin(GL_POINTS)
            glVertex3f(w['x'], w['y'], w['z'])
            glEnd()

        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_LIGHTING)

    def draw_overlay(self, width, height):
        """Draw 2D screen-space effects (gesture flash, hand trail)."""
        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)

        t = time.time()

        # ── Gesture transition flash ─────────────────────────────────
        if self._gesture_flash > 0.01:
            c = self._gesture_flash_color
            alpha = self._gesture_flash * 0.08
            glColor4f(c[0], c[1], c[2], alpha)
            glBegin(GL_QUADS)
            glVertex2f(0, 0)
            glVertex2f(width, 0)
            glVertex2f(width, height)
            glVertex2f(0, height)
            glEnd()
            # Edge glow (top + bottom lines)
            glColor4f(c[0], c[1], c[2], self._gesture_flash * 0.3)
            glLineWidth(2.0)
            glBegin(GL_LINES)
            glVertex2f(0, 2); glVertex2f(width, 2)
            glVertex2f(0, height - 2); glVertex2f(width, height - 2)
            glEnd()

        # ── Hand trail ───────────────────────────────────────────────
        if len(self._trail) > 1:
            n = len(self._trail)
            for i in range(1, n):
                age = t - self._trail[i][0]
                if age > 0.5:
                    continue
                alpha = max(0, (0.5 - age) / 0.5) * 0.3
                px = self._trail[i][1][0] * width
                py = self._trail[i][1][1] * height
                glColor4f(0.0, 0.83, 1.0, alpha)
                glPointSize(3.0)
                glBegin(GL_POINTS)
                glVertex2f(px, py)
                glEnd()

        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)


# ── Sci-Fi UI Panels ─────────────────────────────────────────────────

class HoloUIPanels:
    """Advanced holographic UI overlay system.

    Draws floating panels, circular HUDs, animated bars, data streams,
    and object info cards.  All 2D screen-space, additive blended.
    Call draw() once per frame after the main scene.
    """

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self._t0 = time.time()
        # Animated values (lerped each frame)
        self._fps_smooth = 60.0
        self._obj_count_smooth = 0.0
        # Data stream state
        self._streams = []
        for _ in range(6):
            self._streams.append({
                'x': random.uniform(0.05, 0.95),
                'speed': random.uniform(40, 120),
                'offset': random.uniform(0, 1000),
                'alpha': random.uniform(0.04, 0.1),
            })

    def draw(self, fps=60, obj_count=0, selected_name=None,
             draw_mode="TUBE", draw_color=(0, 1, 0.85),
             plane="XY", input_state="idle", dual_state=None):
        """Render all UI panels.  Call once per frame."""
        t = time.time() - self._t0
        w, h = self.width, self.height

        # Smooth animated values
        self._fps_smooth += (fps - self._fps_smooth) * 0.1
        self._obj_count_smooth += (obj_count - self._obj_count_smooth) * 0.1

        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)

        # ── Data streams (background) ────────────────────────────────
        self._draw_data_streams(t)

        # ── Left sidebar: system vitals ──────────────────────────────
        self._draw_system_vitals(t, fps, obj_count)

        # ── Right sidebar: state & selection ─────────────────────────
        self._draw_state_panel(t, selected_name, draw_mode, plane,
                               input_state, dual_state)

        # ── Bottom bar: tool & color info ────────────────────────────
        self._draw_tool_bar(t, draw_color, draw_mode)

        # ── Circular radar HUD (bottom-left) ─────────────────────────
        self._draw_radar_hud(t, obj_count)

        # ── Top status arc ───────────────────────────────────────────
        self._draw_top_arc(t, fps)

        # ── Object info card (if selected) ───────────────────────────
        if selected_name:
            self._draw_object_card(t, selected_name)

        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

    # ── Data streams ──────────────────────────────────────────────────

    def _draw_data_streams(self, t):
        """Vertical data lines cascading down the screen."""
        for s in self._streams:
            x = s['x'] * self.width
            speed = s['speed']
            offset = s['offset']
            # Multiple segments per stream
            for seg in range(3):
                y_base = ((t * speed + offset + seg * 300) % (self.height + 200)) - 100
                seg_len = random.uniform(40, 100) if seg == 0 else 30
                alpha = s['alpha'] * (1 - seg * 0.3)
                glColor4f(0.0, 0.6, 0.8, alpha)
                glLineWidth(1.0)
                glBegin(GL_LINES)
                glVertex2f(x, y_base)
                glVertex2f(x, y_base + seg_len)
                glEnd()
                # Bright head
                if seg == 0:
                    glColor4f(0.0, 0.9, 1.0, alpha * 2)
                    glPointSize(2.0)
                    glBegin(GL_POINTS)
                    glVertex2f(x, y_base)
                    glEnd()

    # ── System vitals (left side) ─────────────────────────────────────

    def _draw_system_vitals(self, t, fps, obj_count):
        """Animated vertical bars showing FPS, objects, etc."""
        x0 = 20
        y0 = self.height * 0.3
        bar_w = 6
        bar_h = 120
        gap = 24

        vitals = [
            ("FPS", fps / 120.0, (0, 1, 0.85)),
            ("OBJ", min(obj_count / 50.0, 1.0), (0, 0.8, 1.0)),
            ("MEM", 0.4 + 0.1 * math.sin(t * 0.5), (0.3, 0.5, 1.0)),
        ]

        for i, (label, fill, color) in enumerate(vitals):
            x = x0 + i * (bar_w + gap)
            fill = max(0, min(1, fill))

            # Background track
            glColor4f(0.05, 0.1, 0.15, 0.3)
            glBegin(GL_QUADS)
            glVertex2f(x, y0)
            glVertex2f(x + bar_w, y0)
            glVertex2f(x + bar_w, y0 + bar_h)
            glVertex2f(x, y0 + bar_h)
            glEnd()

            # Fill bar (animated)
            fill_h = bar_h * fill
            pulse = 0.8 + 0.2 * math.sin(t * 3 + i)
            glColor4f(color[0] * pulse, color[1] * pulse, color[2] * pulse, 0.6)
            glBegin(GL_QUADS)
            glVertex2f(x, y0 + bar_h - fill_h)
            glVertex2f(x + bar_w, y0 + bar_h - fill_h)
            glVertex2f(x + bar_w, y0 + bar_h)
            glVertex2f(x, y0 + bar_h)
            glEnd()

            # Top cap glow
            glColor4f(color[0], color[1], color[2], 0.9)
            glPointSize(3.0)
            glBegin(GL_POINTS)
            glVertex2f(x + bar_w / 2, y0 + bar_h - fill_h)
            glEnd()

            # Tick marks
            glColor4f(0.0, 0.4, 0.5, 0.2)
            glLineWidth(1.0)
            glBegin(GL_LINES)
            for tk in range(5):
                ty = y0 + bar_h * tk / 4
                glVertex2f(x - 2, ty)
                glVertex2f(x + bar_w + 2, ty)
            glEnd()

    # ── State panel (right side) ──────────────────────────────────────

    def _draw_state_panel(self, t, selected_name, draw_mode, plane,
                          input_state, dual_state):
        """Right-side floating state display."""
        x0 = self.width - 180
        y0 = self.height * 0.25
        line_h = 22
        c = (0, 0.83, 1.0)

        # Panel background (very subtle)
        glColor4f(0.0, 0.05, 0.1, 0.15)
        glBegin(GL_QUADS)
        glVertex2f(x0 - 10, y0 - 10)
        glVertex2f(self.width - 10, y0 - 10)
        glVertex2f(self.width - 10, y0 + line_h * 7 + 10)
        glVertex2f(x0 - 10, y0 + line_h * 7 + 10)
        glEnd()

        # Panel border
        pulse = 0.4 + 0.15 * math.sin(t * 1.5)
        glColor4f(c[0], c[1], c[2], pulse)
        glLineWidth(1.0)
        glBegin(GL_LINE_LOOP)
        glVertex2f(x0 - 10, y0 - 10)
        glVertex2f(self.width - 10, y0 - 10)
        glVertex2f(self.width - 10, y0 + line_h * 7 + 10)
        glVertex2f(x0 - 10, y0 + line_h * 7 + 10)
        glEnd()

        # Animated scan line inside panel
        scan_y = y0 + (t * 40) % (line_h * 7)
        glColor4f(c[0], c[1], c[2], 0.08)
        glBegin(GL_LINES)
        glVertex2f(x0 - 8, scan_y)
        glVertex2f(self.width - 12, scan_y)
        glEnd()

        # Text fields
        fields = [
            ("PLANE", plane, c),
            ("DRAW", draw_mode, c),
            ("STATE", input_state.upper(), c),
            ("SELECT", (selected_name or "NONE").upper(), c),
            ("SYS", "ONLINE", (0, 1, 0)),
        ]
        if dual_state:
            fields.append(("DUAL", dual_state.upper(), (1, 0.8, 0)))

        for i, (label, value, color) in enumerate(fields):
            y = y0 + i * line_h
            # Label
            glColor4f(0.3, 0.5, 0.6, 0.5)
            glLineWidth(1.0)
            glBegin(GL_LINES)
            glVertex2f(x0, y + 8)
            glVertex2f(x0 + 40, y + 8)
            glEnd()
            # Value — brighter
            glColor4f(color[0], color[1], color[2], 0.8)
            glPointSize(2.0)
            glBegin(GL_POINTS)
            glVertex2f(x0 + 50, y + 5)
            glEnd()

    # ── Bottom tool bar ───────────────────────────────────────────────

    def _draw_tool_bar(self, t, draw_color, draw_mode):
        """Bottom bar with color swatch and mode indicator."""
        y0 = self.height - 45
        x0 = 50

        # Separator line
        glColor4f(0.0, 0.4, 0.5, 0.2)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        glVertex2f(30, y0 - 5)
        glVertex2f(self.width - 30, y0 - 5)
        glEnd()

        # Color swatch (animated glow)
        pulse = 0.8 + 0.2 * math.sin(t * 2)
        glColor4f(draw_color[0] * pulse, draw_color[1] * pulse,
                  draw_color[2] * pulse, 0.8)
        glBegin(GL_QUADS)
        glVertex2f(x0, y0 + 5)
        glVertex2f(x0 + 18, y0 + 5)
        glVertex2f(x0 + 18, y0 + 23)
        glVertex2f(x0, y0 + 23)
        glEnd()
        # Swatch border
        glColor4f(draw_color[0], draw_color[1], draw_color[2], 0.4)
        glLineWidth(1.0)
        glBegin(GL_LINE_LOOP)
        glVertex2f(x0, y0 + 5)
        glVertex2f(x0 + 18, y0 + 5)
        glVertex2f(x0 + 18, y0 + 23)
        glVertex2f(x0, y0 + 23)
        glEnd()

        # Mode dots (showing draw mode options)
        modes = ["TUBE", "RIBBON"]
        for i, mode in enumerate(modes):
            dx = x0 + 40 + i * 20
            active = (mode == draw_mode)
            if active:
                glColor4f(0.0, 1.0, 0.85, 0.9)
                glPointSize(5.0)
            else:
                glColor4f(0.0, 0.4, 0.5, 0.3)
                glPointSize(3.0)
            glBegin(GL_POINTS)
            glVertex2f(dx, y0 + 14)
            glEnd()

    # ── Circular radar HUD ────────────────────────────────────────────

    def _draw_radar_hud(self, t, obj_count):
        """Small rotating radar in bottom-left corner."""
        cx = 80
        cy = self.height - 100
        r = 40
        rot = t * 0.5

        # Outer ring
        glColor4f(0.0, 0.6, 0.8, 0.15)
        glLineWidth(1.0)
        glBegin(GL_LINE_LOOP)
        for i in range(48):
            a = 2 * math.pi * i / 48
            glVertex2f(cx + r * math.cos(a), cy + r * math.sin(a))
        glEnd()

        # Inner ring
        glColor4f(0.0, 0.6, 0.8, 0.08)
        glBegin(GL_LINE_LOOP)
        for i in range(48):
            a = 2 * math.pi * i / 48
            glVertex2f(cx + r * 0.5 * math.cos(a), cy + r * 0.5 * math.sin(a))
        glEnd()

        # Cross-hairs
        glColor4f(0.0, 0.6, 0.8, 0.2)
        glBegin(GL_LINES)
        glVertex2f(cx - r, cy)
        glVertex2f(cx + r, cy)
        glVertex2f(cx, cy - r)
        glVertex2f(cx, cy + r)
        glEnd()

        # Rotating sweep line
        sweep_a = rot
        glColor4f(0.0, 1.0, 0.85, 0.4)
        glLineWidth(1.5)
        glBegin(GL_LINES)
        glVertex2f(cx, cy)
        glVertex2f(cx + r * math.cos(sweep_a), cy + r * math.sin(sweep_a))
        glEnd()

        # Sweep trail (fade arc)
        for i in range(8):
            trail_a = sweep_a - i * 0.08
            alpha = 0.15 * (1 - i / 8)
            glColor4f(0.0, 0.8, 0.7, alpha)
            glLineWidth(1.0)
            glBegin(GL_LINES)
            glVertex2f(cx, cy)
            glVertex2f(cx + r * math.cos(trail_a), cy + r * math.sin(trail_a))
            glEnd()

        # Object blips
        n_blips = min(obj_count, 12)
        for i in range(n_blips):
            blip_a = rot * 1.3 + i * 0.8
            blip_r = r * (0.3 + 0.5 * ((i * 7 + 3) % 11) / 11.0)
            bx = cx + blip_r * math.cos(blip_a)
            by = cy + blip_r * math.sin(blip_a)
            pulse = 0.5 + 0.5 * math.sin(t * 3 + i)
            glColor4f(0.0, 1.0, 0.85, pulse * 0.7)
            glPointSize(3.0)
            glBegin(GL_POINTS)
            glVertex2f(bx, by)
            glEnd()

    # ── Top arc (FPS & system) ────────────────────────────────────────

    def _draw_top_arc(self, t, fps):
        """Curved progress arc at top-center showing FPS."""
        cx = self.width // 2
        cy = 35
        r = 60
        arc_start = math.radians(200)
        arc_end = math.radians(340)
        fill = min(1.0, fps / 120.0)

        # Background arc
        glColor4f(0.0, 0.2, 0.3, 0.15)
        glLineWidth(3.0)
        glBegin(GL_LINE_STRIP)
        n = 40
        for i in range(n + 1):
            a = arc_start + (arc_end - arc_start) * i / n
            glVertex2f(cx + r * math.cos(a), cy + r * math.sin(a))
        glEnd()

        # Fill arc
        pulse = 0.8 + 0.2 * math.sin(t * 2)
        n_fill = int(40 * fill)
        if n_fill > 0:
            # Color based on FPS: green > 50, yellow > 30, red < 30
            if fps > 50:
                col = (0.0, 1.0, 0.85)
            elif fps > 30:
                col = (1.0, 0.8, 0.0)
            else:
                col = (1.0, 0.2, 0.2)
            glColor4f(col[0] * pulse, col[1] * pulse, col[2] * pulse, 0.7)
            glLineWidth(3.0)
            glBegin(GL_LINE_STRIP)
            for i in range(n_fill + 1):
                a = arc_start + (arc_end - arc_start) * i / 40
                glVertex2f(cx + r * math.cos(a), cy + r * math.sin(a))
            glEnd()
            # End cap glow
            end_a = arc_start + (arc_end - arc_start) * fill
            glColor4f(col[0], col[1], col[2], 0.9)
            glPointSize(4.0)
            glBegin(GL_POINTS)
            glVertex2f(cx + r * math.cos(end_a), cy + r * math.sin(end_a))
            glEnd()

        # Tick marks
        glColor4f(0.0, 0.4, 0.5, 0.2)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        for i in range(0, 41, 10):
            a = arc_start + (arc_end - arc_start) * i / 40
            glVertex2f(cx + (r - 4) * math.cos(a), cy + (r - 4) * math.sin(a))
            glVertex2f(cx + (r + 4) * math.cos(a), cy + (r + 4) * math.sin(a))
        glEnd()

    # ── Object info card ──────────────────────────────────────────────

    def _draw_object_card(self, t, name):
        """Floating card showing selected object info."""
        x0 = self.width - 200
        y0 = self.height * 0.65
        w, h = 160, 80
        pulse = 0.5 + 0.1 * math.sin(t * 2)

        # Card background
        glColor4f(0.0, 0.05, 0.1, 0.2)
        glBegin(GL_QUADS)
        glVertex2f(x0, y0)
        glVertex2f(x0 + w, y0)
        glVertex2f(x0 + w, y0 + h)
        glVertex2f(x0, y0 + h)
        glEnd()

        # Card border (animated)
        glColor4f(0.0, 0.83, 1.0, pulse)
        glLineWidth(1.5)
        glBegin(GL_LINE_LOOP)
        glVertex2f(x0, y0)
        glVertex2f(x0 + w, y0)
        glVertex2f(x0 + w, y0 + h)
        glVertex2f(x0, y0 + h)
        glEnd()

        # Corner accents
        arm = 12
        glColor4f(0.0, 1.0, 0.85, 0.8)
        glLineWidth(2.0)
        glBegin(GL_LINES)
        # Top-left
        glVertex2f(x0, y0 + arm); glVertex2f(x0, y0); glVertex2f(x0 + arm, y0)
        # Top-right
        glVertex2f(x0 + w - arm, y0); glVertex2f(x0 + w, y0); glVertex2f(x0 + w, y0 + arm)
        # Bottom-right
        glVertex2f(x0 + w, y0 + h - arm); glVertex2f(x0 + w, y0 + h); glVertex2f(x0 + w - arm, y0 + h)
        # Bottom-left
        glVertex2f(x0 + arm, y0 + h); glVertex2f(x0, y0 + h); glVertex2f(x0, y0 + h - arm)
        glEnd()

        # Animated scan line inside card
        scan_y = y0 + (t * 30) % h
        glColor4f(0.0, 0.83, 1.0, 0.06)
        glBegin(GL_LINES)
        glVertex2f(x0 + 2, scan_y)
        glVertex2f(x0 + w - 2, scan_y)
        glEnd()

        # Status indicator (pulsing dot)
        glColor4f(0.0, 1.0, 0.5, 0.9)
        glPointSize(4.0)
        glBegin(GL_POINTS)
        glVertex2f(x0 + 12, y0 + 15)
        glEnd()
        # Dot glow
        glColor4f(0.0, 1.0, 0.5, 0.2)
        glPointSize(10.0)
        glBegin(GL_POINTS)
        glVertex2f(x0 + 12, y0 + 15)
        glEnd()


# ── Renderer ──────────────────────────────────────────────────────────

class HoloRenderer:
    def __init__(self, width=1280, height=720):
        self.width = width
        self.height = height
        self.camera = OrbitCamera()
        self.projector = Projector(self.camera)
        self.objects: List[HoloObject] = []
        self.active_stroke: Optional[Stroke] = None
        self.strokes: List[Stroke] = []
        self.draw_mode = "tube"
        self.show_wireframe = True
        self.show_grid = True
        self.grid_size = 5.0
        self.grid_divisions = 20
        self.bg_color = (0.01, 0.04, 0.07)
        self.hud_color = (0.0, 0.83, 1.0)
        self.time_start = time.time()
        self.selected: Optional[HoloObject] = None
        self.ar_mode = False
        self.fps = 0
        self.frame_count = 0
        self.fps_timer = time.time()
        self.input = None  # Set by HoloBuilder after construction

    def init_gl(self):
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_LINE_SMOOTH)
        glHint(GL_LINE_SMOOTH_HINT, GL_NICEST)
        try:
            glEnable(GL_MULTISAMPLE)
        except Exception:
            pass  # silently swallowed
        glClearColor(*self.bg_color, 1.0)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glLightfv(GL_LIGHT0, GL_POSITION, [5, 5, 10, 1])
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.15, 0.15, 0.2])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.8, 0.8, 0.9])
        glEnable(GL_FOG)
        glFogi(GL_FOG_MODE, GL_LINEAR)
        glFogfv(GL_FOG_COLOR, [*self.bg_color, 1.0])
        glFogf(GL_FOG_START, 8.0)
        glFogf(GL_FOG_END, 25.0)

    def resize(self, w, h):
        self.width = max(w, 1)
        self.height = max(h, 1)
        glViewport(0, 0, w, h)
        self._setup_proj()

    def _setup_proj(self):
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(50, self.width / self.height, 0.1, 100)
        glMatrixMode(GL_MODELVIEW)

    def render(self, clear_color=True):
        now = time.time()
        self.frame_count += 1
        if now - self.fps_timer >= 1.0:
            self.fps = self.frame_count
            self.frame_count = 0
            self.fps_timer = now
        
        if clear_color:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        else:
            glClear(GL_DEPTH_BUFFER_BIT)
        self.camera.apply()
        if self.show_grid:
            self._draw_grid()
        self._draw_objects()
        self._draw_active_stroke()
        self._draw_hud()

    def _draw_grid(self):
        # Grid disabled (radar/sweep removed) — skip entirely
        return

    def _draw_objects(self):
        for obj in self.objects:
            self._draw_holo_object(obj, selected=(obj is self.selected))

    def _draw_holo_object(self, obj, selected=False):
        if len(obj.vertices) == 0 or len(obj.faces) == 0:
            return

        t = time.time()
        pulse = 0.85 + 0.15 * math.sin(t * 2 + id(obj) * 0.01)

        # ── Pass 1: Depth shell (slightly expanded, dark) ────────────
        # Gives the object a sense of volume / outer boundary.
        glDisable(GL_LIGHTING)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        center = obj.get_center()
        scale_exp = 1.03  # 3% expansion
        glColor4f(obj.color[0] * 0.15, obj.color[1] * 0.15,
                  obj.color[2] * 0.15, 0.12)
        glBegin(GL_TRIANGLES)
        for face in obj.faces:
            for idx in face:
                if idx < len(obj.vertices):
                    v = obj.vertices[idx]
                    dv = (v - center) * scale_exp + center
                    glVertex3f(dv[0], dv[1], dv[2])
        glEnd()

        # ── Pass 2: Solid body (lit) ─────────────────────────────────
        glEnable(GL_LIGHTING)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        c = obj.color
        glColor4f(c[0] * pulse, c[1] * pulse, c[2] * pulse, c[3])
        glBegin(GL_TRIANGLES)
        for face in obj.faces:
            for idx in face:
                if idx < len(obj.normals):
                    glNormal3f(*obj.normals[idx])
                if idx < len(obj.vertices):
                    glVertex3f(*obj.vertices[idx])
        glEnd()

        if self.show_wireframe:
            glDisable(GL_LIGHTING)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE)
            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
            # ── Pass 3: Edge glow (wide, additive) ──────────────────
            wc = obj.wireframe_color
            glColor4f(wc[0] * 0.3, wc[1] * 0.3, wc[2] * 0.3, 0.15)
            glLineWidth(3.0)
            glBegin(GL_TRIANGLES)
            for face in obj.faces:
                for idx in face:
                    if idx < len(obj.vertices):
                        glVertex3f(*obj.vertices[idx])
            glEnd()
            # ── Pass 4: Edge core (thin, bright) ────────────────────
            glColor4f(wc[0], wc[1], wc[2], 0.8 * pulse)
            glLineWidth(1.2)
            glBegin(GL_TRIANGLES)
            for face in obj.faces:
                for idx in face:
                    if idx < len(obj.vertices):
                        glVertex3f(*obj.vertices[idx])
            glEnd()
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glEnable(GL_LIGHTING)

        if selected:
            glDisable(GL_LIGHTING)
            center = obj.get_center()
            r = obj.get_radius() * 1.5
            t = time.time()
            pulse = 0.5 + 0.3 * math.sin(t * 3)
            glColor4f(0.0, 0.83, 1.0, pulse * 0.6)
            glLineWidth(2.0)
            torus_segs = 48
            # XY ring — single batched call
            glBegin(GL_LINE_LOOP)
            for i in range(torus_segs):
                a = 2 * math.pi * i / torus_segs
                glVertex3f(center[0] + r * math.cos(a),
                           center[1] + r * math.sin(a), center[2])
            glEnd()
            # XZ ring — single batched call
            glBegin(GL_LINE_LOOP)
            for i in range(torus_segs):
                a = 2 * math.pi * i / torus_segs
                glVertex3f(center[0], center[1] + r * math.sin(a),
                           center[2] + r * math.cos(a))
            glEnd()
            glEnable(GL_LIGHTING)

    def _draw_active_stroke(self):
        if not self.active_stroke or not self.active_stroke.points:
            return
        glDisable(GL_LIGHTING)
        pts = self.active_stroke.points
        if not pts:
            return
        t = time.time()
        thickness = self.active_stroke.thickness

        # ── Outer glow (wide, additive, soft) ────────────────────────
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        # Glow layer 1 — very wide halo
        glColor4f(0.0, 0.6, 0.8, 0.08)
        glLineWidth(thickness * 6)
        glBegin(GL_LINE_STRIP)
        for p in pts:
            glVertex3f(p.x, p.y, p.z)
        glEnd()
        # Glow layer 2 — medium halo
        glColor4f(0.0, 0.85, 1.0, 0.15)
        glLineWidth(thickness * 3)
        glBegin(GL_LINE_STRIP)
        for p in pts:
            glVertex3f(p.x, p.y, p.z)
        glEnd()
        # Glow layer 3 — inner halo
        glColor4f(0.0, 1.0, 0.9, 0.3)
        glLineWidth(thickness * 1.8)
        glBegin(GL_LINE_STRIP)
        for p in pts:
            glVertex3f(p.x, p.y, p.z)
        glEnd()

        # ── Core line (sharp, bright) ────────────────────────────────
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(0.3, 1.0, 0.95, 1.0)
        glLineWidth(thickness)
        glBegin(GL_LINE_STRIP)
        for p in pts:
            glVertex3f(p.x, p.y, p.z)
        glEnd()

        # ── Bright centre core (thin white) ──────────────────────────
        glColor4f(0.8, 1.0, 1.0, 0.7)
        glLineWidth(max(1, thickness * 0.4))
        glBegin(GL_LINE_STRIP)
        for p in pts:
            glVertex3f(p.x, p.y, p.z)
        glEnd()

        # ── Trailing energy particles ────────────────────────────────
        n_trail = min(16, len(pts))
        for i in range(n_trail):
            idx = len(pts) - 1 - i
            if idx < 0:
                break
            p = pts[idx]
            alpha = (1 - i / n_trail) ** 1.5 * 0.6
            sz = max(2, 8 - i * 0.35)
            # Glow halo per particle
            glColor4f(0.0, 0.6, 0.8, alpha * 0.3)
            glPointSize(sz * 2.5)
            glBegin(GL_POINTS)
            glVertex3f(p.x, p.y, p.z)
            glEnd()
            # Core per particle
            glColor4f(0.0, 0.9, 1.0, alpha)
            glPointSize(sz)
            glBegin(GL_POINTS)
            glVertex3f(p.x, p.y, p.z)
            glEnd()

        # ── Energy tip at last point ─────────────────────────────────
        if pts:
            last = pts[-1]
            rot = t * 3
            pulse = 0.7 + 0.3 * math.sin(t * 6)
            r = 12 * pulse

            # Outer glow ring
            glBlendFunc(GL_SRC_ALPHA, GL_ONE)
            glColor4f(0.0, 0.6, 0.8, 0.2 * pulse)
            glPointSize(18.0)
            glBegin(GL_POINTS)
            glVertex3f(last.x, last.y, last.z)
            glEnd()

            # Bright core point
            glColor4f(1.0, 1.0, 1.0, 0.95)
            glPointSize(8.0)
            glBegin(GL_POINTS)
            glVertex3f(last.x, last.y, last.z)
            glEnd()

            # Hexagonal scanner ring
            glColor4f(0.0, 0.83, 1.0, 0.7 * pulse)
            glLineWidth(1.5)
            glBegin(GL_LINE_LOOP)
            for i in range(6):
                a = rot + 2 * math.pi * i / 6
                glVertex3f(last.x + r * math.cos(a),
                           last.y + r * math.sin(a), last.z)
            glEnd()

            # Inner rotating triangle
            glColor4f(0.0, 1.0, 0.85, 0.4 * pulse)
            glLineWidth(1.0)
            glBegin(GL_LINE_LOOP)
            for i in range(3):
                a = -rot * 0.7 + 2 * math.pi * i / 3
                glVertex3f(last.x + r * 0.5 * math.cos(a),
                           last.y + r * 0.5 * math.sin(a), last.z)
            glEnd()

            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glEnable(GL_LIGHTING)

    def _draw_hud(self):
        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width, self.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        t = time.time() - self.time_start
        cx, cy = self.width // 2, self.height // 2
        c = self.hud_color

        self._draw_vignette()
        self._draw_corner_brackets(c, t)
        self._draw_scan_line(c, t)
        self._draw_center_reticle(c, t, cx, cy)
        self._draw_top_left_panel(c, t)
        self._draw_top_right_panel(c, t)
        self._draw_bottom_bar(c, t)
        if not self.ar_mode:
            self._draw_ar_prompt(c, t)

        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

    def _draw_vignette(self):
        # Pre-computed once, cached as a display list for the current resolution.
        if not hasattr(self, '_vignette_list') or \
           getattr(self, '_vignette_size', None) != (self.width, self.height):
            self._vignette_size = (self.width, self.height)
            if hasattr(self, '_vignette_list') and self._vignette_list:
                glDeleteLists(self._vignette_list, 1)
            self._vignette_list = glGenLists(1)
            glNewList(self._vignette_list, GL_COMPILE)
            steps = 20  # was 40 — halved, still smooth enough
            cx, cy = self.width // 2, self.height // 2
            sx, sy = self.width / 2, self.height / 2
            for i in range(steps, 0, -1):
                alpha = ((steps - i) / steps) ** 2 * 0.5
                r = i / steps
                glColor4f(0.01, 0.02, 0.04, alpha)
                glLineWidth(1.0)
                glBegin(GL_LINE_LOOP)
                for j in range(36):  # was 72 — halved
                    angle = 2 * math.pi * j / 36
                    glVertex2f(cx + sx * r * math.cos(angle),
                               cy + sy * r * math.sin(angle))
                glEnd()
            glEndList()
        glCallList(self._vignette_list)

    def _draw_corner_brackets(self, c, t):
        margin = 30
        arm = 60
        gap = 15
        pulse = 0.5 + 0.15 * math.sin(t * 1.5)
        glColor4f(c[0], c[1], c[2], pulse)
        glLineWidth(2.0)
        glBegin(GL_LINES)

        glVertex2f(margin, margin + arm)
        glVertex2f(margin, margin + gap)
        glVertex2f(margin, margin)
        glVertex2f(margin + arm, margin)

        glVertex2f(self.width - margin, margin + arm)
        glVertex2f(self.width - margin, margin + gap)
        glVertex2f(self.width - margin, margin)
        glVertex2f(self.width - margin - arm, margin)

        glVertex2f(margin, self.height - margin - arm)
        glVertex2f(margin, self.height - margin - gap)
        glVertex2f(margin, self.height - margin)
        glVertex2f(margin + arm, self.height - margin)

        glVertex2f(self.width - margin, self.height - margin - arm)
        glVertex2f(self.width - margin, self.height - margin - gap)
        glVertex2f(self.width - margin, self.height - margin)
        glVertex2f(self.width - margin - arm, self.height - margin)

        glEnd()

    def _draw_scan_line(self, c, t):
        scan_y = ((t * 60) % self.height)
        glColor4f(c[0], c[1], c[2], 0.15)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        glVertex2f(0, scan_y)
        glVertex2f(self.width, scan_y)
        glEnd()
        glColor4f(c[0], c[1], c[2], 0.08)
        glBegin(GL_LINES)
        glVertex2f(0, scan_y - 2)
        glVertex2f(self.width, scan_y - 2)
        glVertex2f(0, scan_y + 2)
        glVertex2f(self.width, scan_y + 2)
        glEnd()

    def _draw_center_reticle(self, c, t, cx, cy):
        outer_r = 25
        inner_r = 8
        rot = t * 0.3

        glColor4f(c[0], c[1], c[2], 0.25)
        glLineWidth(1.0)
        glBegin(GL_LINE_LOOP)
        for i in range(36):
            angle = 2 * math.pi * i / 36
            glVertex2f(cx + outer_r * math.cos(angle), cy + outer_r * math.sin(angle))
        glEnd()

        glColor4f(c[0], c[1], c[2], 0.6)
        glLineWidth(1.5)
        glBegin(GL_LINES)
        glVertex2f(cx - inner_r, cy)
        glVertex2f(cx + inner_r, cy)
        glVertex2f(cx, cy - inner_r)
        glVertex2f(cx, cy + inner_r)
        glEnd()

        glColor4f(c[0], c[1], c[2], 0.4)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        for i in range(4):
            angle = rot + math.pi / 2 * i
            sx = cx + (outer_r + 5) * math.cos(angle)
            sy = cy + (outer_r + 5) * math.sin(angle)
            ex = cx + (outer_r + 12) * math.cos(angle)
            ey = cy + (outer_r + 12) * math.sin(angle)
            glVertex2f(sx, sy)
            glVertex2f(ex, ey)
        glEnd()

    def _draw_top_left_panel(self, c, t):
        font_x = 50
        font_y = 55
        line_h = 20
        glColor4f(c[0], c[1], c[2], 0.5)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        glVertex2f(40, font_y + 8)
        glVertex2f(40, self.height - 40)
        glEnd()

        mode_str = "AR" if self.ar_mode else "3D"
        objs = len(self.objects)
        fps = self.fps
        plane = self.projector.draw_plane

        self._draw_text_2d(font_x, font_y, "[ FRIDAY.HOLO ]", c, 0.7)
        self._draw_text_2d(font_x, font_y + line_h, f"MODE: {mode_str}", c, 0.5)
        self._draw_text_2d(font_x, font_y + line_h * 2, f"FPS: {fps}", c, 0.5)
        self._draw_text_2d(font_x, font_y + line_h * 3, f"OBJ: {objs}", c, 0.5)
        self._draw_text_2d(font_x, font_y + line_h * 4, f"PLANE: {plane}", c, 0.5)

    def _draw_top_right_panel(self, c, t):
        rx = self.width - 50
        ry = 55
        line_h = 20
        glColor4f(c[0], c[1], c[2], 0.5)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        glVertex2f(self.width - 40, ry + 8)
        glVertex2f(self.width - 40, self.height - 40)
        glEnd()

        mode_str = "AR" if self.ar_mode else "3D"
        plane = self.projector.draw_plane
        obj_sel = self.selected.name if self.selected else "NONE"

        self._draw_text_2d(rx, ry, f"[ {plane} ]", c, 0.7)
        state_str = self.input.state.upper() if self.input else "IDLE"
        self._draw_text_2d(rx, ry + line_h, f"STATE: {state_str}", c, 0.5)
        self._draw_text_2d(rx, ry + line_h * 2, f"SELECT: {obj_sel}", c, 0.5)
        self._draw_text_2d(rx, ry + line_h * 3, "SYS: ONLINE", c, 0.5)

    def _draw_bottom_bar(self, c, t):
        bx = 50
        by = self.height - 50
        swatch_size = 16
        bar_w = 120
        bar_h = 10

        color_names = {
            (0.0, 1.0, 0.85): "CYAN",
            (1.0, 0.2, 0.5): "PINK",
            (0.3, 0.8, 1.0): "BLUE",
            (1.0, 0.8, 0.0): "GOLD",
            (0.5, 1.0, 0.3): "LIME",
            (1.0, 0.4, 0.1): "ORANGE",
            (0.8, 0.3, 1.0): "PURPLE",
        }
        dc = self.input.draw_color if self.input else (0.0, 1.0, 0.85)
        cname = color_names.get(dc, "CUSTOM")

        glColor4f(c[0], c[1], c[2], 0.4)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        glVertex2f(40, by + 20)
        glVertex2f(self.width - 40, by + 20)
        glEnd()

        self._draw_text_2d(bx, by, f"COLOR: {cname}", dc, 0.6)

        glColor4f(dc[0], dc[1], dc[2], 0.8)
        glBegin(GL_QUADS)
        glVertex2f(bx + 110, by - 12)
        glVertex2f(bx + 110 + swatch_size, by - 12)
        glVertex2f(bx + 110 + swatch_size, by - 12 + swatch_size)
        glVertex2f(bx + 110, by - 12 + swatch_size)
        glEnd()

        depth = self.input.draw_depth if self.input else 0.0
        thick = self.input.draw_thickness if self.input else 3.0
        self._draw_text_2d(bx + 160, by, f"D:{depth:.2f} T:{thick:.1f}", c, 0.5)

        mode = (self.input.draw_mode if self.input else "tube").upper()
        self._draw_text_2d(self.width - 160, by, f"DRAW: {mode}", c, 0.5)

    def _draw_ar_prompt(self, c, t):
        """Draw 'TAB to switch to AR mode' prompt centered on screen."""
        prompt = "TAB to switch to AR mode"
        char_w = 8
        text_w = len(prompt) * char_w
        px = (self.width - text_w) // 2
        py = self.height // 2 + 80

        # Pulsing background box
        pulse = 0.5 + 0.2 * math.sin(t * 2)
        box_pad = 16
        glColor4f(0.0, 0.05, 0.1, 0.25 * pulse)
        glBegin(GL_QUADS)
        glVertex2f(px - box_pad, py - box_pad)
        glVertex2f(px + text_w + box_pad, py - box_pad)
        glVertex2f(px + text_w + box_pad, py + 20 + box_pad)
        glVertex2f(px - box_pad, py + 20 + box_pad)
        glEnd()

        # Border
        glColor4f(c[0], c[1], c[2], 0.3 * pulse)
        glLineWidth(1.0)
        glBegin(GL_LINE_LOOP)
        glVertex2f(px - box_pad, py - box_pad)
        glVertex2f(px + text_w + box_pad, py - box_pad)
        glVertex2f(px + text_w + box_pad, py + 20 + box_pad)
        glVertex2f(px - box_pad, py + 20 + box_pad)
        glEnd()

        # Text
        self._draw_text_2d(px, py + 2, prompt, c, 0.5 * pulse)

    def _draw_text_2d(self, x, y, text, color, alpha=0.6, scale=1.0):
        char_w = 8 * scale
        char_h = 14 * scale
        glColor4f(color[0], color[1], color[2], alpha)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        for i, ch in enumerate(text):
            cx = x + i * char_w
            cy = y
            cw = char_w * 0.6
            ch = ch.upper()
            if ch == " ":
                continue
            elif ch == ".":
                glVertex2f(cx + cw * 0.5, cy)
                glVertex2f(cx + cw * 0.5, cy)
                glVertex2f(cx + cw * 0.4, cy)
                glVertex2f(cx + cw * 0.6, cy)
                continue
            elif ch == ":":
                glVertex2f(cx + cw * 0.5, cy + char_h * 0.35)
                glVertex2f(cx + cw * 0.5, cy + char_h * 0.35)
                glVertex2f(cx + cw * 0.5, cy + char_h * 0.65)
                glVertex2f(cx + cw * 0.5, cy + char_h * 0.65)
                continue
            elif ch == "-":
                glVertex2f(cx, cy + char_h * 0.5)
                glVertex2f(cx + cw, cy + char_h * 0.5)
                continue
            elif ch == "]":
                glVertex2f(cx, cy)
                glVertex2f(cx, cy + char_h)
                glVertex2f(cx, cy)
                glVertex2f(cx + cw * 0.3, cy)
                glVertex2f(cx, cy + char_h)
                glVertex2f(cx + cw * 0.3, cy + char_h)
                continue
            elif ch == "[":
                glVertex2f(cx + cw * 0.3, cy)
                glVertex2f(cx + cw * 0.3, cy + char_h)
                glVertex2f(cx + cw * 0.3, cy)
                glVertex2f(cx + cw, cy)
                glVertex2f(cx + cw * 0.3, cy + char_h)
                glVertex2f(cx + cw, cy + char_h)
                continue

            glyph = {
                "0": ["L", "T", "R", "B", "L", "B", "R", "T"],
                "1": ["T", "1", "3"],
                "2": ["T", "R", "M", "L", "B", "R"],
                "3": ["T", "R", "M", "R", "B", "L"],
                "4": ["T", "L", "M", "R", "3"],
                "5": ["T", "L", "M", "R", "B"],
                "6": ["T", "L", "B", "R", "M"],
                "7": ["T", "R", "3"],
                "8": ["T", "R", "M", "L", "B", "R", "M", "L"],
                "9": ["T", "R", "L", "M", "3"],
                "A": ["L", "T", "R", "L", "3"],
                "B": ["L", "T", "R", "M", "L", "B"],
                "C": ["L", "T", "R", "B"],
                "D": ["L", "T", "R", "B", "L"],
                "E": ["R", "T", "L", "M", "L", "B", "R"],
                "F": ["L", "T", "L", "M", "L"],
                "G": ["L", "T", "R", "B", "M", "R"],
                "H": ["L", "T", "M", "R", "B"],
                "I": ["T", "1", "3", "1"],
                "J": ["B", "L", "T", "R"],
                "K": ["L", "T", "M", "L", "B", "4"],
                "L": ["L", "T", "L", "B"],
                "M": ["L", "T", "R", "L", "B"],
                "N": ["L", "T", "R", "B", "L"],
                "O": ["L", "T", "R", "B", "L"],
                "P": ["L", "T", "R", "M", "L"],
                "Q": ["L", "T", "R", "B", "L", "4"],
                "R": ["L", "T", "R", "M", "L", "4"],
                "S": ["T", "R", "M", "L", "B"],
                "T": ["T", "1", "3"],
                "U": ["L", "B", "R", "T"],
                "V": ["L", "B", "R", "B"],
                "W": ["L", "B", "R", "T", "L", "B"],
                "X": ["L", "T", "R", "B"],
                "Y": ["L", "T", "R", "M"],
                "Z": ["T", "R", "L", "B"],
                " ": [],
                ".": ["1"],
                ":": ["5"],
                "-": ["M"],
                "[": ["R", "T", "L", "B", "R"],
                "]": ["L", "T", "R", "B", "L"],
                "_": ["B"],
                "#": ["T", "R", "M", "L", "B", "T", "B"],
            }

            segments = glyph.get(ch, ["M"])
            seg_defs = {
                "T": (cx, cy, cx + cw, cy),
                "B": (cx, cy + char_h, cx + cw, cy + char_h),
                "L": (cx, cy, cx, cy + char_h),
                "R": (cx + cw, cy, cx + cw, cy + char_h),
                "M": (cx, cy + char_h * 0.5, cx + cw, cy + char_h * 0.5),
                "1": (cx + cw * 0.5, cy, cx + cw * 0.5, cy + char_h),
                "3": (cx + cw * 0.5, cy + char_h * 0.5, cx + cw, cy + char_h * 0.5),
                "4": (cx + cw, cy, cx, cy + char_h * 0.5),
                "5": (cx + cw * 0.5, cy + char_h * 0.35, cx + cw * 0.5, cy + char_h * 0.65),
            }
            for seg in segments:
                if seg in seg_defs:
                    x1, y1, x2, y2 = seg_defs[seg]
                    glVertex2f(x1, y1)
                    glVertex2f(x2, y2)
        glEnd()


# ── AR Overlay ────────────────────────────────────────────────────────

class AROverlay:
    def __init__(self):
        self.cap = None
        self.active = False
        self.frame = None
        self.frame_tex_id = None
        self.enabled = HAS_CV2
        self._consecutive_failures = 0
        self._failure_suppress_count = 0

    def start(self):
        if not self.enabled:
            print("[HOLO] OpenCV not installed — AR disabled")
            return False
        self.stop()
        _cap_api = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        for idx in range(3):
            try:
                cap = cv2.VideoCapture(idx, _cap_api)
                if not cap.isOpened():
                    cap.release()
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                for _ in range(5):
                    ret, test = cap.read()
                    if ret and test is not None:
                        h, w = test.shape[:2]
                        if w > 0 and h > 0:
                            self.cap = cap
                            self.active = True
                            print(f"[HOLO] Camera opened (index {idx}, {w}x{h})")
                            return True
                cap.release()
            except Exception:
                try:
                    cap.release()
                except Exception:
                    pass  # silently swallowed
        print("[HOLO] No working camera found")
        return False

    def stop(self):
        self.active = False
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass  # silently swallowed
            self.cap = None
        self.frame = None
        if self.frame_tex_id is not None:
            try:
                glDeleteTextures([self.frame_tex_id])
            except Exception:
                pass  # silently swallowed
            self.frame_tex_id = None

    def grab_frame(self):
        if not self.active or self.cap is None:
            return False
        try:
            ret, frame = self.cap.read()
            if not ret or frame is None or frame.size == 0:
                self._consecutive_failures += 1
                if self._consecutive_failures <= 3:
                    print(f"[HOLO] Camera grab failed (attempt {self._consecutive_failures})")
                elif self._consecutive_failures == 4:
                    print("[HOLO] Camera grab failures suppressed (too many)")
                # After 60 consecutive failures (~1s at 60fps), try reopening
                if self._consecutive_failures >= 60:
                    self._try_reopen_camera()
                return False
            h, w = frame.shape[:2]
            if w < 1 or h < 1:
                return False
            # Reset failure count on success
            if self._consecutive_failures > 0:
                print(f"[HOLO] Camera recovered after {self._consecutive_failures} failures")
                self._consecutive_failures = 0
            frame = cv2.flip(frame, 1)
            self.frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return True
        except cv2.error:
            self._consecutive_failures += 1
            return False
        except Exception:
            self._consecutive_failures += 1
            return False

    def _try_reopen_camera(self):
        """Attempt to reopen the camera after sustained failures."""
        self._consecutive_failures = 0
        print("[HOLO] Attempting camera reopen...")
        try:
            if self.cap is not None:
                self.cap.release()
        except Exception:
            pass
        _cap_api = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        for idx in range(3):
            try:
                cap = cv2.VideoCapture(idx, _cap_api)
                if not cap.isOpened():
                    cap.release()
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                ret, test = cap.read()
                if ret and test is not None:
                    self.cap = cap
                    print(f"[HOLO] Camera reopened (index {idx})")
                    return
                cap.release()
            except Exception:
                try:
                    cap.release()
                except Exception:
                    pass
        print("[HOLO] Camera reopen failed — disabling AR")
        self.active = False
        self.frame = None  # Clear stale frame so gesture processing stops

    def upload_texture(self):
        if self.frame is None:
            return
        h, w, _ = self.frame.shape
        if self.frame_tex_id is None:
            self.frame_tex_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.frame_tex_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, w, h, 0,
                     GL_RGB, GL_UNSIGNED_BYTE, self.frame)

    def draw_background(self, width, height):
        """Draw webcam as fullscreen quad with holographic overlay."""
        if self.frame is None:
            return
        self.upload_texture()

        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_FOG)

        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.frame_tex_id)
        glColor4f(0.95, 0.97, 1.0, 1.0)

        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, 1, 0, 1, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glBegin(GL_QUADS)
        glTexCoord2f(0, 1); glVertex2f(0, 0)
        glTexCoord2f(1, 1); glVertex2f(1, 0)
        glTexCoord2f(1, 0); glVertex2f(1, 1)
        glTexCoord2f(0, 0); glVertex2f(0, 1)
        glEnd()

        self._draw_holo_overlay(width, height)

        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()

        glDisable(GL_TEXTURE_2D)
        glEnable(GL_FOG)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

    def _draw_holo_overlay(self, width, height):
        t = time.time()

        glDisable(GL_TEXTURE_2D)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glColor4f(0.0, 0.15, 0.3, 0.12)
        glBegin(GL_QUADS)
        glVertex2f(0, 0)
        glVertex2f(1, 0)
        glVertex2f(1, 1)
        glVertex2f(0, 1)
        glEnd()

        glColor4f(0.0, 0.83, 1.0, 0.04)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        sy = (t * 30) % height
        glVertex2f(0, sy)
        glVertex2f(width, sy)
        glVertex2f(0, sy - 3)
        glVertex2f(width, sy - 3)
        glEnd()

        glColor4f(0.0, 0.83, 1.0, 0.03)
        glBegin(GL_LINES)
        for y in range(0, int(height), 3):
            glVertex2f(0, y)
            glVertex2f(width, y)
        glEnd()

        self._draw_chromatic_aberration(width, height)

    def _draw_chromatic_aberration(self, width, height):
        pass


# ── Input Handler ─────────────────────────────────────────────────────

class InputHandler:
    STATE_IDLE = "idle"
    STATE_DRAWING = "drawing"
    STATE_ORBIT = "orbit"
    STATE_PAN = "pan"
    STATE_MOVE = "move"
    STATE_SCALE = "scale"

    def __init__(self, renderer, ar_overlay, gesture_ctrl, dual_hand_mgr=None):
        self.renderer = renderer
        self.ar = ar_overlay
        self.gesture_ctrl = gesture_ctrl
        self.dual_hand = dual_hand_mgr
        self.state = self.STATE_IDLE

        self.draw_depth = 0.0
        self.draw_color = (0.0, 1.0, 0.85)
        self.draw_thickness = 3.0
        self.extrude_depth = 0.05
        self.draw_mode = "tube"

        self.mouse_x = 0
        self.mouse_y = 0
        self.last_mx = 0
        self.last_my = 0
        self.mouse_left = False
        self.mouse_right = False
        self.mouse_middle = False
        self.shift = False
        self.ctrl = False
        self.alt = False
        self.undo_stack: List[HoloObject] = []
        self._gesture_prev_pos = None
        # Dual-hand transform snapshot (for undo/commit)
        self._dual_obj_snapshot = None

    def handle_event(self, event):
        if event.type == MOUSEMOTION:
            self.mouse_x, self.mouse_y = event.pos
            dx = self.mouse_x - self.last_mx
            dy = self.mouse_y - self.last_my
            r = self._handle_motion(dx, dy)
            self.last_mx = self.mouse_x
            self.last_my = self.mouse_y
            return r
        elif event.type == MOUSEBUTTONDOWN:
            return self._handle_button_down(event.button, event.pos)
        elif event.type == MOUSEBUTTONUP:
            return self._handle_button_up(event.button)
        elif event.type == MOUSEWHEEL:
            self.renderer.camera.zoom(event.y)
            return None
        elif event.type == KEYDOWN:
            return self._handle_key_down(event)
        elif event.type == KEYUP:
            self._handle_key_up(event)
        return None

    def _handle_motion(self, dx, dy):
        if self.state == self.STATE_ORBIT:
            self.renderer.camera.orbit(dx, -dy)
        elif self.state == self.STATE_PAN:
            self.renderer.camera.pan(-dx, dy)
        elif self.state == self.STATE_DRAWING:
            self._add_draw_point()
        elif self.state == self.STATE_MOVE:
            self._do_move(dx, dy)
        elif self.state == self.STATE_SCALE:
            self._do_scale(dy)
        return None

    def _handle_button_down(self, button, pos):
        self.last_mx, self.last_my = pos
        if button == 1:
            self.mouse_left = True
            # Flag to force drawing even if an existing object is under the cursor
            intent_draw = not (self.shift or self.ctrl or self.alt)
            if self.shift:
                self.state = self.STATE_ORBIT
            elif self.ctrl:
                self.state = self.STATE_PAN
            elif self.alt:
                self.state = self.STATE_MOVE
                self._gesture_prev_pos = pos
                obj = self._pick_object(pos[0], pos[1])
                if obj is not None:
                    self.renderer.selected = obj
                    return "move_started"
            else:
                # Normal left‑click: if an object is under the cursor and the user
                # is not intending to draw, select it. Otherwise start a new stroke.
                obj = self._pick_object(pos[0], pos[1])
                if obj is not None and not intent_draw:
                    self.renderer.selected = obj
                    return "object_selected"
                self.renderer.selected = None
                self._start_drawing()
        elif button == 3:
            self.mouse_right = True
            self.state = self.STATE_ORBIT
        elif button == 2:
            self.mouse_middle = True
            self.state = self.STATE_PAN
        return None

    def _handle_button_up(self, button):
        if button == 1:
            self.mouse_left = False
            if self.state == self.STATE_DRAWING:
                return self._finish_drawing()
            elif self.state in (self.STATE_MOVE, self.STATE_SCALE):
                self.state = self.STATE_IDLE
                return "manipulation_done"
        elif button == 3:
            self.mouse_right = False
        elif button == 2:
            self.mouse_middle = False
        if not any([self.mouse_left, self.mouse_right, self.mouse_middle]):
            self.state = self.STATE_IDLE
        return None

    def _handle_key_down(self, event):
        k = event.key
        if k in (K_LSHIFT, K_RSHIFT):
            self.shift = True
            return None
        if k in (K_LCTRL, K_RCTRL):
            self.ctrl = True
            return None
        if k in (K_LALT, K_RALT):
            self.alt = True
            return None
        if k == K_TAB:
            return "toggle_ar"
        if k == K_z and self.ctrl:
            return "undo"
        if k == K_q:
            self.renderer.projector.next_plane()
            return "plane_changed"
        if k == K_g and self.renderer.selected:
            self.state = self.STATE_MOVE
            self._gesture_prev_pos = (self.mouse_x, self.mouse_y)
            return "move_started"
        if k == K_s and not self.shift and self.renderer.selected:
            self.state = self.STATE_SCALE
            self._gesture_prev_pos = (self.mouse_x, self.mouse_y)
            return "scale_started"
        if k == K_c:
            colors = [
                (0.0, 1.0, 0.85), (1.0, 0.2, 0.5), (0.3, 0.8, 1.0),
                (1.0, 0.8, 0.0), (0.5, 1.0, 0.3), (1.0, 0.4, 0.1),
                (0.8, 0.3, 1.0),
            ]
            try:
                idx = colors.index(self.draw_color)
                self.draw_color = colors[(idx + 1) % len(colors)]
            except ValueError:
                self.draw_color = colors[0]
            return "color_changed"
        if k == K_m:
            self.draw_mode = "ribbon" if self.draw_mode == "tube" else "tube"
            return "mode_changed"
        if k == K_w:
            self.renderer.show_wireframe = not self.renderer.show_wireframe
        if k == K_r and not self.ctrl:
            self.renderer.camera.reset()
            return "camera_reset"
        if k == K_UP:
            self.draw_depth += 0.02
            return "depth_changed"
        if k == K_DOWN:
            self.draw_depth -= 0.02
            return "depth_changed"
        if k == K_RIGHT:
            self.extrude_depth += 0.01
            return "extrude_changed"
        if k == K_LEFT:
            self.extrude_depth = max(0.005, self.extrude_depth - 0.01)
            return "extrude_changed"
        if k in (K_EQUALS, K_PLUS):
            self.draw_thickness = min(10, self.draw_thickness + 0.5)
        if k == K_MINUS:
            self.draw_thickness = max(1, self.draw_thickness - 0.5)
        if k == K_DELETE:
            if self.renderer.selected:
                obj = self.renderer.selected
                if obj in self.renderer.objects:
                    self.renderer.objects.remove(obj)
                self.renderer.selected = None
                return "object_deleted"
            return "clear_all"
        if k == K_ESCAPE:
            return "quit"
        return None

    def _handle_key_up(self, event):
        if event.key in (K_LSHIFT, K_RSHIFT):
            self.shift = False
        elif event.key in (K_LCTRL, K_RCTRL):
            self.ctrl = False
        elif event.key in (K_LALT, K_RALT):
            self.alt = False

    def _pick_object(self, mx, my):
        origin, direction = self.renderer.projector.screen_to_ray(
            mx, my, self.renderer.width, self.renderer.height)
        best_obj = None
        best_t = float('inf')
        for obj in self.renderer.objects:
            center = obj.get_center()
            radius = obj.get_radius() * 2.0
            t = _ray_sphere(origin, direction, center, radius)
            if t is not None and t < best_t:
                best_t = t
                best_obj = obj
        return best_obj

    def _do_move(self, dx, dy, speed=0.003):
        obj = self.renderer.selected
        if obj is None:
            return
        plane = self.renderer.projector.draw_plane
        s = speed * self.renderer.camera.distance
        if plane == "XY":
            delta = np.array([dx * s, -dy * s, 0])
        elif plane == "XZ":
            delta = np.array([dx * s, 0, -dy * s])
        else:
            delta = np.array([0, dx * s, -dy * s])
        obj.vertices += delta.astype(np.float32)

    def _do_scale(self, dy):
        obj = self.renderer.selected
        if obj is None:
            return
        factor = max(0.1, min(10, 1.0 + dy * 0.005))
        center = obj.get_center()
        obj.vertices = (center + (obj.vertices - center) * factor).astype(np.float32)

    def _start_drawing(self):
        self.state = self.STATE_DRAWING
        wp = self.renderer.projector.screen_to_world(
            self.mouse_x, self.mouse_y,
            self.renderer.width, self.renderer.height,
            depth=self.draw_depth,
        )
        stroke = Stroke(
            color=self.draw_color,
            thickness=self.draw_thickness,
            depth=self.draw_depth,
            extrude=self.extrude_depth,
            timestamp=time.time(),
        )
        stroke.add_point(wp[0], wp[1], wp[2])
        self.renderer.active_stroke = stroke

    def _add_draw_point(self):
        if not self.renderer.active_stroke:
            return
        wp = self.renderer.projector.screen_to_world(
            self.mouse_x, self.mouse_y,
            self.renderer.width, self.renderer.height,
            depth=self.draw_depth,
        )
        self.renderer.active_stroke.add_point(wp[0], wp[1], wp[2])

    def _finish_drawing(self):
        stroke = self.renderer.active_stroke
        self.renderer.active_stroke = None
        if not stroke or not stroke.is_valid():
            return None
        self.renderer.strokes.append(stroke)
        if self.draw_mode == "tube":
            obj = StrokeMesher.extrude_stroke(stroke, depth=self.extrude_depth)
        else:
            obj = StrokeMesher.ribbon_stroke(stroke)
        if obj:
            self.renderer.objects.append(obj)
            self.undo_stack.append(obj)
            return "object_created"
        return None

    def update_gesture(self):
        """Process gesture input — single-hand AND dual-hand.

        Iron Man feel: gestures are immediate, no first-frame kill.
        Gesture changes seamlessly transition between states.
        """
        g = self.gesture_ctrl
        dh = self.dual_hand
        if not g.enabled:
            return

        # ── Dual-hand path ────────────────────────────────────────────
        if dh is not None and g.both_hands_detected:
            # If we were in a single-hand state, end it first
            if self.state in (self.STATE_DRAWING, self.STATE_MOVE, self.STATE_SCALE):
                self._end_gesture_action()
            self._apply_dual_hand(dh)
            return

        # ── Single-hand path ─────────────────────────────────────────
        # If dual-hand was active and just ended, commit the transform
        if dh is not None and dh.state != DualHandGestureManager.STATE_IDLE:
            self._commit_dual_transform()

        if g.hand_pos is None and g.gesture == GestureController.NONE:
            self._end_gesture_action()
            return

        if g.hand_pos is None:
            return

        nx, ny = g.hand_pos
        mx = int(nx * self.renderer.width)
        my = int(ny * self.renderer.height)
        self.mouse_x, self.mouse_y = mx, my

        gesture = g.gesture

        # On gesture change: end the OLD action, then IMMEDIATELY start the new one.
        # No wasted frame — Iron Man feel.
        if g.just_changed:
            if self.state == self.STATE_DRAWING and gesture != GestureController.PINCH:
                self._finish_drawing()
            elif self.state in (self.STATE_MOVE, self.STATE_SCALE):
                self.state = self.STATE_IDLE
            self._gesture_prev_pos = None
            self._dual_obj_snapshot = None

        if gesture == GestureController.PINCH:
            if self.state != self.STATE_DRAWING:
                self._start_drawing()
            else:
                self._add_draw_point()

        elif gesture == GestureController.FIST:
            prev = self._gesture_prev_pos
            self._gesture_prev_pos = (mx, my)

            if self.state != self.STATE_MOVE:
                obj = self._pick_object(mx, my)
                if obj is not None:
                    self.renderer.selected = obj
                    self.state = self.STATE_MOVE
                else:
                    self.state = self.STATE_MOVE
                    self.renderer.selected = None
            else:
                if self.renderer.selected is None:
                    obj = self._pick_object(mx, my)
                    if obj is not None:
                        self.renderer.selected = obj

                if self.renderer.selected is not None and prev is not None:
                    dx = mx - prev[0]
                    dy = my - prev[1]
                    self._do_move(dx, dy, speed=0.006)

        elif gesture == GestureController.POINT:
            # Precision select — like Tony pointing at UI elements
            obj = self._pick_object(mx, my)
            if obj is not None:
                self.renderer.selected = obj

        elif gesture == GestureController.PEACE:
            if self.state != self.STATE_SCALE:
                if self.renderer.selected:
                    self.state = self.STATE_SCALE
                    self._gesture_prev_pos = (mx, my)
                else:
                    obj = self._pick_object(mx, my)
                    if obj is not None:
                        self.renderer.selected = obj
                        self.state = self.STATE_SCALE
                        self._gesture_prev_pos = (mx, my)
            else:
                if self._gesture_prev_pos is not None:
                    dy = self._gesture_prev_pos[1] - my
                    self._do_scale(dy * 0.6)
                self._gesture_prev_pos = (mx, my)

        elif gesture == GestureController.OPEN:
            obj = self._pick_object(mx, my)
            if obj is not None and obj is not self.renderer.selected:
                self.renderer.selected = obj

    def _apply_dual_hand(self, dh: DualHandGestureManager):
        """Apply dual-hand transform to the selected object."""
        obj = self.renderer.selected
        if obj is None:
            # Auto-select nearest object using midpoint of both hands
            g = self.gesture_ctrl
            if g.hand_positions[0] and g.hand_positions[1]:
                mx = int((g.hand_positions[0][0] + g.hand_positions[1][0]) / 2 * self.renderer.width)
                my = int((g.hand_positions[0][1] + g.hand_positions[1][1]) / 2 * self.renderer.height)
                obj = self._pick_object(mx, my)
                if obj is not None:
                    self.renderer.selected = obj
            if obj is None:
                return

        # Snapshot vertices before first dual-hand frame (for clean reset)
        if self._dual_obj_snapshot is None:
            self._dual_obj_snapshot = obj.vertices.copy()

        center = obj.get_center()

        if dh.state == DualHandGestureManager.STATE_SCALE:
            factor = dh.scale_factor
            obj.vertices = (center + (obj.vertices - center) * factor).astype(np.float32)
            # Reset baseline each frame so scale is incremental
            dh.scale_factor = 1.0

        elif dh.state == DualHandGestureManager.STATE_ROTATE:
            angle = dh.rotate_delta
            if abs(angle) > 1e-4:
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                # Rotate around Z-axis through object center
                rel = obj.vertices - center
                rot_x = rel[:, 0] * cos_a - rel[:, 1] * sin_a
                rot_y = rel[:, 0] * sin_a + rel[:, 1] * cos_a
                obj.vertices[:, 0] = rot_x + center[0]
                obj.vertices[:, 1] = rot_y + center[1]
                obj.vertices = obj.vertices.astype(np.float32)
                # Reset baseline
                dh.rotate_delta = 0.0

        elif dh.state == DualHandGestureManager.STATE_REPOSITION:
            delta = dh.move_delta
            if np.linalg.norm(delta) > 1e-6:
                # Convert normalised screen delta to world delta
                speed = 0.15 * self.renderer.camera.distance
                plane = self.renderer.projector.draw_plane
                if plane == "XY":
                    world_delta = np.array([delta[0] * speed, -delta[1] * speed, 0])
                elif plane == "XZ":
                    world_delta = np.array([delta[0] * speed, 0, -delta[1] * speed])
                else:
                    world_delta = np.array([0, delta[0] * speed, -delta[1] * speed])
                obj.vertices += world_delta.astype(np.float32)
                # Reset baseline
                dh.move_delta = np.array([0.0, 0.0])

    def _commit_dual_transform(self):
        """Snapshot the dual-hand result so it's visible in the undo stack."""
        self._dual_obj_snapshot = None
        # The object is already modified in-place; nothing else to do.

    def _end_gesture_action(self):
        if self.state == self.STATE_DRAWING:
            self._finish_drawing()
        elif self.state in (self.STATE_MOVE, self.STATE_SCALE):
            self.state = self.STATE_IDLE
        self._gesture_prev_pos = None
        self._dual_obj_snapshot = None
        # Don't clear selected here — let OPEN gesture handle re-selection

    def undo(self):
        if self.undo_stack:
            obj = self.undo_stack.pop()
            if obj in self.renderer.objects:
                self.renderer.objects.remove(obj)
            if obj is self.renderer.selected:
                self.renderer.selected = None
            return True
        return False

    def clear_all(self):
        self.renderer.objects.clear()
        self.renderer.strokes.clear()
        self.undo_stack.clear()
        self.renderer.selected = None


# ── Cinematic Boot Sequence ───────────────────────────────────────────

class CinematicBoot:
    """7-phase holographic boot animation.

    Phases (total ~7 s):
        0  0.0–0.8s  Energy pulse — expanding ring from centre
        1  0.8–2.0s  Grid activation — holographic grid lines materialise
        2  2.0–3.5s  Rotating rings — concentric rings spin up
        3  3.5–5.0s  Data streams — vertical data lines cascade
        4  5.0–6.0s  UI materialisation — HUD panels fade in
        5  6.0–7.0s  Stabilisation — subtle pulse, system ready
    """

    DURATION = 7.0

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.active = True
        # Pre-computed ring geometry (48 segments)
        self._ring_segs = 48
        # Particle sparks for phase 0
        self._sparks = []
        for _ in range(40):
            angle = math.radians(random.uniform(0, 360))
            speed = random.uniform(120, 400)
            self._sparks.append({'angle': angle, 'speed': speed, 'life': random.uniform(0.3, 0.8)})

    def _ease(self, t):
        """Smooth ease-in-out."""
        return t * t * (3 - 2 * t)

    def _clamp01(self, t):
        return max(0.0, min(1.0, t))

    def _phase_progress(self, elapsed, start, end):
        """Return 0-1 progress within a phase window."""
        if elapsed < start:
            return 0.0
        if elapsed > end:
            return 1.0
        return self._clamp01((elapsed - start) / (end - start))

    def render(self, elapsed):
        """Draw one frame of the boot sequence."""
        if elapsed >= self.DURATION:
            self.active = False
            return

        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)

        cx, cy = self.width // 2, self.height // 2

        # ── Phase 0: Energy pulse ─────────────────────────────────────
        p0 = self._phase_progress(elapsed, 0.0, 0.8)
        if p0 > 0:
            ep = self._ease(p0)
            # Expanding ring
            max_r = max(self.width, self.height) * 0.6
            r = ep * max_r
            alpha = (1 - p0) * 0.9
            glColor4f(0.0, 0.83, 1.0, alpha)
            glLineWidth(3.0)
            glBegin(GL_LINE_LOOP)
            for i in range(64):
                a = 2 * math.pi * i / 64
                glVertex2f(cx + r * math.cos(a), cy + r * math.sin(a))
            glEnd()
            # Inner glow ring
            glColor4f(0.0, 1.0, 0.9, alpha * 0.4)
            glLineWidth(8.0)
            glBegin(GL_LINE_LOOP)
            for i in range(64):
                a = 2 * math.pi * i / 64
                glVertex2f(cx + r * 0.7 * math.cos(a), cy + r * 0.7 * math.sin(a))
            glEnd()
            # Spark particles
            for s in self._sparks:
                sr = s['speed'] * elapsed * ep
                sx = cx + sr * math.cos(s['angle'])
                sy = cy + sr * math.sin(s['angle'])
                sa = max(0, s['life'] - elapsed) * 0.8
                if sa > 0:
                    glColor4f(0.0, 0.9, 1.0, sa)
                    glPointSize(3.0)
                    glBegin(GL_POINTS)
                    glVertex2f(sx, sy)
                    glEnd()
            # Central bright point
            glColor4f(1.0, 1.0, 1.0, (1 - p0) * 0.95)
            glPointSize(8.0)
            glBegin(GL_POINTS)
            glVertex2f(cx, cy)
            glEnd()

        # ── Phase 1: Grid activation ──────────────────────────────────
        p1 = self._phase_progress(elapsed, 0.8, 2.0)
        if p1 > 0:
            gp = self._ease(p1)
            alpha = gp * 0.15
            glColor4f(0.0, 0.6, 0.8, alpha)
            glLineWidth(1.0)
            # Horizontal lines
            n_h = 20
            for i in range(n_h):
                frac = i / n_h
                y = self.height * frac
                # Lines sweep from centre outward
                line_p = self._clamp01((gp - frac * 0.5) * 2)
                if line_p > 0:
                    half_w = (self.width / 2) * line_p
                    glBegin(GL_LINES)
                    glVertex2f(cx - half_w, y)
                    glVertex2f(cx + half_w, y)
                    glEnd()
            # Vertical lines
            n_v = 30
            for i in range(n_v):
                frac = i / n_v
                x = self.width * frac
                line_p = self._clamp01((gp - frac * 0.5) * 2)
                if line_p > 0:
                    half_h = (self.height / 2) * line_p
                    glBegin(GL_LINES)
                    glVertex2f(x, cy - half_h)
                    glVertex2f(x, cy + half_h)
                    glEnd()
            # Bright cross at centre
            glColor4f(0.0, 0.83, 1.0, gp * 0.5)
            glLineWidth(2.0)
            glBegin(GL_LINES)
            glVertex2f(cx - 30 * gp, cy)
            glVertex2f(cx + 30 * gp, cy)
            glVertex2f(cx, cy - 30 * gp)
            glVertex2f(cx, cy + 30 * gp)
            glEnd()

        # ── Phase 2: Rotating rings ───────────────────────────────────
        p2 = self._phase_progress(elapsed, 2.0, 3.5)
        if p2 > 0:
            rp = self._ease(p2)
            t = elapsed
            for ring_idx in range(3):
                r = 60 + ring_idx * 45
                rot_speed = (1.5 - ring_idx * 0.3) * (1 if ring_idx % 2 == 0 else -1)
                rot = t * rot_speed
                alpha = rp * (0.5 - ring_idx * 0.12)
                # Colour varies per ring
                if ring_idx == 0:
                    glColor4f(0.0, 1.0, 0.85, alpha)
                elif ring_idx == 1:
                    glColor4f(0.0, 0.6, 1.0, alpha)
                else:
                    glColor4f(0.3, 0.4, 1.0, alpha)
                glLineWidth(2.0 - ring_idx * 0.3)
                glBegin(GL_LINE_LOOP)
                for i in range(self._ring_segs):
                    a = rot + 2 * math.pi * i / self._ring_segs
                    glVertex2f(cx + r * math.cos(a), cy + r * math.sin(a))
                glEnd()
            # Tick marks on outer ring
            glColor4f(0.0, 0.83, 1.0, rp * 0.3)
            glLineWidth(1.0)
            outer_r = 150
            rot = t * 1.5
            glBegin(GL_LINES)
            for i in range(0, 360, 15):
                a = rot + math.radians(i)
                glVertex2f(cx + (outer_r - 6) * math.cos(a), cy + (outer_r - 6) * math.sin(a))
                glVertex2f(cx + (outer_r + 6) * math.cos(a), cy + (outer_r + 6) * math.sin(a))
            glEnd()

        # ── Phase 3: Data streams ─────────────────────────────────────
        p3 = self._phase_progress(elapsed, 3.5, 5.0)
        if p3 > 0:
            dp = self._ease(p3)
            # Vertical data lines from top
            n_streams = 12
            for i in range(n_streams):
                x = self.width * (0.1 + 0.8 * i / n_streams)
                stream_len = dp * self.height * 0.6
                alpha = dp * 0.2
                glColor4f(0.0, 0.83, 1.0, alpha)
                glLineWidth(1.0)
                glBegin(GL_LINES)
                glVertex2f(x, 0)
                glVertex2f(x, stream_len)
                glEnd()
                # Bright head
                if dp < 1.0:
                    glColor4f(0.0, 1.0, 1.0, dp * 0.6)
                    glPointSize(4.0)
                    glBegin(GL_POINTS)
                    glVertex2f(x, stream_len)
                    glEnd()
            # Horizontal scan sweep
            scan_y = dp * self.height
            glColor4f(0.0, 0.83, 1.0, 0.2 * (1 - dp * 0.5))
            glLineWidth(2.0)
            glBegin(GL_LINES)
            glVertex2f(0, scan_y)
            glVertex2f(self.width, scan_y)
            glEnd()

        # ── Phase 4: UI materialisation ───────────────────────────────
        p4 = self._phase_progress(elapsed, 5.0, 6.0)
        if p4 > 0:
            up = self._ease(p4)
            # Top-left bracket
            margin = 30
            arm = int(60 * up)
            glColor4f(0.0, 0.83, 1.0, up * 0.6)
            glLineWidth(2.0)
            glBegin(GL_LINES)
            glVertex2f(margin, margin + arm)
            glVertex2f(margin, margin)
            glVertex2f(margin, margin)
            glVertex2f(margin + arm, margin)
            glEnd()
            # Top-right bracket
            glBegin(GL_LINES)
            glVertex2f(self.width - margin, margin + arm)
            glVertex2f(self.width - margin, margin)
            glVertex2f(self.width - margin, margin)
            glVertex2f(self.width - margin - arm, margin)
            glEnd()
            # Bottom-left bracket
            glBegin(GL_LINES)
            glVertex2f(margin, self.height - margin - arm)
            glVertex2f(margin, self.height - margin)
            glVertex2f(margin, self.height - margin)
            glVertex2f(margin + arm, self.height - margin)
            glEnd()
            # Bottom-right bracket
            glBegin(GL_LINES)
            glVertex2f(self.width - margin, self.height - margin - arm)
            glVertex2f(self.width - margin, self.height - margin)
            glVertex2f(self.width - margin, self.height - margin)
            glVertex2f(self.width - margin - arm, self.height - margin)
            glEnd()
            # Centre text: "SYSTEM ONLINE"
            if up > 0.5:
                text_alpha = (up - 0.5) * 2
                self._draw_boot_text(cx - 80, cy - 8, "SYSTEM ONLINE", text_alpha)
                self._draw_boot_text(cx - 60, cy + 14, "INITIALIZING", text_alpha * 0.6)

        # ── Phase 5: Stabilisation ────────────────────────────────────
        p5 = self._phase_progress(elapsed, 6.0, 7.0)
        if p5 > 0:
            # Final pulse — everything fades to workspace
            fade = 1 - p5
            if fade > 0.01:
                pulse = 0.3 + 0.2 * math.sin(elapsed * 8)
                glColor4f(0.0, 0.83, 1.0, fade * pulse * 0.15)
                glBegin(GL_QUADS)
                glVertex2f(0, 0)
                glVertex2f(self.width, 0)
                glVertex2f(self.width, self.height)
                glVertex2f(0, self.height)
                glEnd()

        # Restore GL state
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

    def _draw_boot_text(self, x, y, text, alpha):
        """Minimal segment-style text for boot overlay."""
        char_w = 10
        glColor4f(0.0, 0.83, 1.0, alpha)
        glLineWidth(1.5)
        glBegin(GL_LINES)
        for i, ch in enumerate(text):
            cx = x + i * char_w
            # Simple line segments per character (just enough to read)
            glyph = {
                "S": [(cx, y, cx+6, y), (cx, y, cx, y+5), (cx, y+5, cx+6, y+5),
                      (cx+6, y+5, cx+6, y+10), (cx, y+10, cx+6, y+10)],
                "Y": [(cx, y, cx+3, y+5), (cx+6, y, cx+3, y+5), (cx+3, y+5, cx+3, y+10)],
                "S": [(cx, y, cx+6, y), (cx, y, cx, y+5), (cx, y+5, cx+6, y+5),
                      (cx+6, y+5, cx+6, y+10), (cx, y+10, cx+6, y+10)],
                "T": [(cx, y, cx+6, y), (cx+3, y, cx+3, y+10)],
                "E": [(cx, y, cx, y+10), (cx, y, cx+6, y), (cx, y+5, cx+4, y+5), (cx, y+10, cx+6, y+10)],
                "M": [(cx, y+10, cx, y), (cx, y, cx+3, y+4), (cx+3, y+4, cx+6, y), (cx+6, y, cx+6, y+10)],
                "O": [(cx, y, cx+6, y), (cx+6, y, cx+6, y+10), (cx+6, y+10, cx, y+10), (cx, y+10, cx, y)],
                "N": [(cx, y+10, cx, y), (cx, y, cx+6, y+10), (cx+6, y+10, cx+6, y)],
                "L": [(cx, y, cx, y+10), (cx, y+10, cx+6, y+10)],
                "I": [(cx+3, y, cx+3, y+10)],
                " ": [],
            }
            segments = glyph.get(ch.upper(), [])
            for seg in segments:
                glVertex2f(seg[0], seg[1])
                glVertex2f(seg[2], seg[3])
        glEnd()


# ── Main Application ──────────────────────────────────────────────────

class HoloBuilder:
    def __init__(self, width=1280, height=720):
        self.width = width
        self.height = height
        self.running = False
        self.screen = None
        self.renderer = HoloRenderer(width, height)
        self.ar = AROverlay()
        self.gesture_ctrl = GestureController(num_hands=2)
        self.dual_hand = DualHandGestureManager()
        self.input = InputHandler(self.renderer, self.ar, self.gesture_ctrl, self.dual_hand)
        self.renderer.input = self.input
        self.ar_mode = False
        self.power_up_active = False
        self.power_up_start = 0
        self.power_up_duration = 3.0
        self.sound_fx = SoundFX()
        self.visual_fx = ARVisualFX(self.width, self.height)
        self.ui_panels = HoloUIPanels(self.width, self.height)
        self.interaction_fx = InteractionFX()
        self.clock = None
        self.fps = 0
        self.frame_count = 0
        self.fps_timer = 0

    def run(self):
        if not HAS_PYGAME:
            print("[HOLO] pygame not installed")
            return
        if not HAS_OPENGL:
            print("[HOLO] PyOpenGL not installed")
            return
        try:
            self._init_window()
            self._init_gl()
            self.running = True
            self.clock = pygame.time.Clock()
            self.fps_timer = time.time()
            # Trigger cinematic boot sequence
            self.power_up_active = True
            self.power_up_start = time.time()
            self._boot_seq = CinematicBoot(self.width, self.height)
            print("[HOLO] Holo Builder v4.0 - Iron Man Edition online")
            print("[HOLO] ==============================================")
            print("  L-Click drag     - DRAW")
            print("  R-Click drag     - ORBIT CAMERA")
            print("  M-Click drag     - PAN CAMERA")
            print("  Scroll wheel     - ZOOM")
            print("  Q                - CYCLE PLANE (XY/XZ/YZ)")
            print("  Tab              - TOGGLE AR MODE")
            print("  C / M / W        - COLOR / MODE / WIREFRAME")
            print("  Click object     - SELECT")
            print("  G + drag         - MOVE SELECTED")
            print("  S + drag         - SCALE SELECTED")
            print("  Alt + drag       - MOVE (no key)")
            print("  Delete           - DELETE / CLEAR ALL")
            print("  Ctrl+Z           - UNDO")
            print("  Esc              - QUIT")
            if self.gesture_ctrl.enabled:
                print("[HOLO] === GESTURE CONTROLS (AR mode) ===")
                print("  Pinch (thumb+index) - Draw")
                print("  Fist (all closed)   - Grab & move selected")
                print("  Peace (2 fingers)   - Scale selected")
                print("  Open hand           - Release / navigate")
            while self.running:
                self._handle_events()
                if not self.running:
                    break
                self._update()
                self._render()
                self.clock.tick(60)
        except Exception as e:
            print(f"[HOLO] Crashed: {e}")
            traceback.print_exc()
        finally:
            self._cleanup()

    def stop(self):
        self.running = False
        # Wait for the run thread to actually finish (with timeout)
        if hasattr(self, '_run_thread') and self._run_thread is not None:
            self._run_thread.join(timeout=3.0)
        # Explicitly clean up gesture controller to stop MediaPipe
        self.gesture_ctrl.cleanup()

    def _init_window(self):
        pygame.init()
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)
        pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
        pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)
        try:
            info = pygame.display.Info()
            self.width = info.current_w
            self.height = info.current_h
            self.screen = pygame.display.set_mode(
                (self.width, self.height), DOUBLEBUF | OPENGL | RESIZABLE)
        except Exception:
            self.screen = pygame.display.set_mode(
                (self.width, self.height), DOUBLEBUF | OPENGL | RESIZABLE)
        pygame.display.set_caption("FRIDAY — Holo Builder")

    def _init_gl(self):
        self.renderer.init_gl()
        self.renderer.resize(self.width, self.height)

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == QUIT:
                self.running = False
                return
            if event.type == VIDEORESIZE:
                self.width, self.height = event.w, event.h
                self.screen = pygame.display.set_mode(
                    (self.width, self.height), DOUBLEBUF | OPENGL | RESIZABLE)
                self.renderer.resize(self.width, self.height)
                if hasattr(self, 'ui_panels'):
                    self.ui_panels = HoloUIPanels(self.width, self.height)
                if hasattr(self, '_boot_seq') and self._boot_seq.active:
                    self._boot_seq = CinematicBoot(self.width, self.height)
                continue
            action = self.input.handle_event(event)
            if action:
                self._process_action(action)

    def _process_action(self, action):
        if action == "quit":
            self.running = False
        elif action == "toggle_ar":
            self._toggle_ar()
        elif action == "undo":
            self.input.undo()
        elif action == "clear_all":
            self.input.clear_all()
        elif action == "object_created":
            obj = self.renderer.objects[-1] if self.renderer.objects else None
            if obj and hasattr(self, 'interaction_fx'):
                self.interaction_fx.trigger_spawn(obj.get_center(), obj.color[:3])
            print(f"[HOLO] Object created ({len(self.renderer.objects)} total)")
        elif action == "plane_changed":
            print(f"[HOLO] Draw plane: {self.renderer.projector.draw_plane}")
        elif action == "object_selected":
            n = self.renderer.selected.name if self.renderer.selected else "?"
            print(f"[HOLO] Selected: {n}")
        elif action == "object_deleted":
            print(f"[HOLO] Deleted ({len(self.renderer.objects)} remaining)")
        elif action == "move_started":
            print("[HOLO] Move mode — drag to move")
        elif action == "scale_started":
            print("[HOLO] Scale mode — drag up/down")

    def _toggle_ar(self):
        if not self.ar.enabled:
            print("[HOLO] AR requires opencv-python")
            return
        if not self.ar_mode:
            if self.ar.start():
                self.ar_mode = True
                self.power_up_active = True
                self.power_up_start = time.time()
                self._gesture_warned = False  # reset so warning can fire again
                if hasattr(self, 'sound_fx'):
                    pass # self.sound_fx.play_power_up()  # disabled per user request
                self.renderer.bg_color = (0.0, 0.0, 0.0)
                glClearColor(0, 0, 0, 0)
                print("[HOLO] AR mode ON — gestures active")
            else:
                print("[HOLO] Could not open webcam")
        else:
            self.ar.stop()
            self.ar_mode = False
            self.renderer.bg_color = (0.02, 0.02, 0.05)
            glClearColor(*self.renderer.bg_color, 1.0)
            print("[HOLO] AR mode OFF")

    def _update(self):
        if not self.running:
            return
        self.frame_count += 1
        now = time.time()
        dt = now - getattr(self, '_last_update_time', now)
        self._last_update_time = now
        if now - self.fps_timer >= 1.0:
            self.fps = self.frame_count
            self.frame_count = 0
            self.fps_timer = now

        # Update interaction FX
        if hasattr(self, 'interaction_fx'):
            self.interaction_fx.update(dt)
            # Track hand position for trail
            if self.gesture_ctrl.hand_pos:
                self.interaction_fx.add_trail_point(self.gesture_ctrl.hand_pos)

        if self.ar_mode:
            self.ar.grab_frame()
            if self.gesture_ctrl.enabled and self.ar.frame is not None:
                prev_gesture = self.gesture_ctrl.gesture
                self.gesture_ctrl.process(self.ar.frame)
                self.dual_hand.update(self.gesture_ctrl)
                self.input.update_gesture()
                # Trigger gesture change effect
                if self.gesture_ctrl.gesture != prev_gesture:
                    self.interaction_fx.trigger_gesture_change(
                        self.gesture_ctrl.gesture)
            elif not self.gesture_ctrl.enabled:
                if not hasattr(self, '_gesture_warned'):
                    print("[HOLO] AR mode active but gestures DISABLED (MediaPipe/model issue)")
                    self._gesture_warned = True
        else:
            # In non-AR mode, reset gesture state so it doesn't leak into keyboard/mouse input
            if self.gesture_ctrl.enabled and self.gesture_ctrl.gesture != GestureController.NONE:
                self.gesture_ctrl.gesture = GestureController.NONE
                self.gesture_ctrl.hand_pos = None
                self.gesture_ctrl.hand_positions = [None, None]

    def _render(self):
        if self.ar_mode and self.ar.frame is not None:
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            self.ar.draw_background(self.width, self.height)
            self.renderer.render(clear_color=False)
        else:
            self.renderer.render(clear_color=True)

        # 3D interaction effects (spawn rings, selection aura, wisps)
        if hasattr(self, 'interaction_fx'):
            self.interaction_fx.draw_scene(selected_obj=self.renderer.selected)

        if self.ar_mode:
            self._draw_gesture_cursor()
            if hasattr(self, 'visual_fx'):
                self.visual_fx.update()
                self.visual_fx.draw(self.width, self.height)

        # 2D overlay effects (gesture flash, hand trail)
        if hasattr(self, 'interaction_fx'):
            self.interaction_fx.draw_overlay(self.width, self.height)

        # Sci-fi UI panels overlay
        if hasattr(self, 'ui_panels'):
            self.ui_panels.draw(
                fps=self.fps,
                obj_count=len(self.renderer.objects),
                selected_name=self.renderer.selected.name if self.renderer.selected else None,
                draw_mode=self.input.draw_mode.upper(),
                draw_color=self.input.draw_color,
                plane=self.renderer.projector.draw_plane,
                input_state=self.input.state,
                dual_state=self.dual_hand.state if self.dual_hand.active else None,
            )

        # Boot animation — drawn LAST so it overlays everything
        if self.power_up_active:
            self._draw_power_up(time.time())

        self._draw_fps()
        pygame.display.flip()

    def _draw_gesture_cursor(self):
        g = self.gesture_ctrl
        if not g.enabled or g.hand_pos is None:
            return

        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width, self.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        hx = int(g.hand_pos[0] * self.width)
        hy = int(g.hand_pos[1] * self.height)
        gesture = g.gesture
        t = time.time()
        pulse = 0.7 + 0.2 * math.sin(t * 4)

        # Track gesture duration for animated effects
        if not hasattr(self, '_gesture_cursor_state'):
            self._gesture_cursor_state = {
                'last_gesture': GestureController.NONE,
                'gesture_start': t,
                'ripples': [],       # expanding ring ripples
                'particles': [],     # burst particles
                'beam_end': None,    # laser beam endpoint
            }
        gs = self._gesture_cursor_state
        if gesture != gs['last_gesture']:
            # Gesture changed — spawn transition particles
            for i in range(12):
                angle = random.uniform(0, math.pi * 2)
                speed = random.uniform(80, 250)
                gs['particles'].append({
                    'x': hx, 'y': hy,
                    'vx': speed * math.cos(angle),
                    'vy': speed * math.sin(angle),
                    't0': t, 'life': random.uniform(0.3, 0.7),
                    'color': self._gesture_fx_color(gesture),
                })
            gs['last_gesture'] = gesture
            gs['gesture_start'] = t
        g_elapsed = t - gs['gesture_start']

        if gesture == GestureController.PINCH:
            # ── Pinch: drawing mode — ink ripple + energy particles ───
            # Spawn periodic ripples while drawing
            if not gs['ripples'] or t - gs['ripples'][-1]['t0'] > 0.15:
                gs['ripples'].append({'t0': t, 'x': hx, 'y': hy})
            gs['ripples'] = [r for r in gs['ripples'] if t - r['t0'] < 0.8]

            # Expanding ripple rings
            for r in gs['ripples']:
                age = t - r['t0']
                prog = age / 0.8
                radius = prog * 35
                alpha = (1 - prog) * 0.6
                glColor4f(1.0, 0.2, 0.4, alpha)
                glLineWidth(2.0 * (1 - prog))
                glBegin(GL_LINE_LOOP)
                for i in range(24):
                    a = 2 * math.pi * i / 24
                    glVertex2f(r['x'] + radius * math.cos(a),
                               r['y'] + radius * math.sin(a))
                glEnd()

            # Central bright core with glow layers
            glColor4f(1.0, 0.0, 0.4, 0.15 * pulse)
            glPointSize(28.0)
            glBegin(GL_POINTS)
            glVertex2f(hx, hy)
            glEnd()
            glColor4f(1.0, 0.1, 0.5, 0.4 * pulse)
            glPointSize(14.0)
            glBegin(GL_POINTS)
            glVertex2f(hx, hy)
            glEnd()
            glColor4f(1.0, 0.4, 0.6, 0.9)
            glPointSize(7.0)
            glBegin(GL_POINTS)
            glVertex2f(hx, hy)
            glEnd()

            # Hexagonal scanner ring rotating
            rot = t * 4
            s = 14 + 3 * math.sin(t * 6)
            glColor4f(1.0, 0.2, 0.4, pulse * 0.7)
            glLineWidth(1.5)
            glBegin(GL_LINE_LOOP)
            for i in range(6):
                a = rot + 2 * math.pi * i / 6
                glVertex2f(hx + s * math.cos(a), hy + s * math.sin(a))
            glEnd()

            # Outer energy ring
            glColor4f(1.0, 0.0, 0.4, pulse * 0.25)
            glLineWidth(1.0)
            glBegin(GL_LINE_LOOP)
            for i in range(36):
                a = 2 * math.pi * i / 36
                glVertex2f(hx + (s + 8) * math.cos(a), hy + (s + 8) * math.sin(a))
            glEnd()

        elif gesture == GestureController.FIST:
            # ── Fist: grab mode — shockwave corners + grip field ──────
            # Shockwave on initial grab
            if g_elapsed < 0.5:
                sw_prog = g_elapsed / 0.5
                sw_r = sw_prog * 60
                sw_alpha = (1 - sw_prog) * 0.7
                glColor4f(1.0, 0.7, 0.0, sw_alpha)
                glLineWidth(2.5 * (1 - sw_prog))
                glBegin(GL_LINE_LOOP)
                for i in range(32):
                    a = 2 * math.pi * i / 32
                    glVertex2f(hx + sw_r * math.cos(a), hy + sw_r * math.sin(a))
                glEnd()

            # Corner brackets with animated pulse
            arm = 20 + 4 * math.sin(t * 5)
            gap = 8
            glColor4f(1.0, 0.7, 0.0, pulse)
            glLineWidth(2.5)
            glBegin(GL_LINES)
            # Top-left
            glVertex2f(hx - arm, hy - arm); glVertex2f(hx - gap, hy - arm)
            glVertex2f(hx - arm, hy - arm); glVertex2f(hx - arm, hy - gap)
            # Top-right
            glVertex2f(hx + arm, hy - arm); glVertex2f(hx + gap, hy - arm)
            glVertex2f(hx + arm, hy - arm); glVertex2f(hx + arm, hy - gap)
            # Bottom-left
            glVertex2f(hx - arm, hy + arm); glVertex2f(hx - gap, hy + arm)
            glVertex2f(hx - arm, hy + arm); glVertex2f(hx - arm, hy + gap)
            # Bottom-right
            glVertex2f(hx + arm, hy + arm); glVertex2f(hx + gap, hy + arm)
            glVertex2f(hx + arm, hy + arm); glVertex2f(hx + arm, hy + gap)
            glEnd()

            # Rotating inner square (energy field)
            rot = t * 2.5
            inner = 10 + 3 * math.sin(t * 3)
            glColor4f(1.0, 0.7, 0.0, pulse * 0.5)
            glLineWidth(1.5)
            glBegin(GL_LINE_LOOP)
            for i in range(4):
                a = rot + math.pi / 2 * i + math.pi / 4
                glVertex2f(hx + inner * math.cos(a), hy + inner * math.sin(a))
            glEnd()

            # Central grip point
            glColor4f(1.0, 0.8, 0.2, 0.8)
            glPointSize(5.0)
            glBegin(GL_POINTS)
            glVertex2f(hx, hy)
            glEnd()

            # Pulsing outer ring
            outer_r = arm + 8 + 4 * math.sin(t * 4)
            glColor4f(1.0, 0.7, 0.0, pulse * 0.2)
            glLineWidth(1.0)
            glBegin(GL_LINE_LOOP)
            for i in range(36):
                a = 2 * math.pi * i / 36
                glVertex2f(hx + outer_r * math.cos(a), hy + outer_r * math.sin(a))
            glEnd()

        elif gesture == GestureController.PEACE:
            # ── Peace: scale mode — V-beam + target scanning ──────────
            # Laser beams from each finger
            beam_len = 80 + 20 * math.sin(t * 3)
            glColor4f(0.0, 1.0, 0.5, pulse * 0.6)
            glLineWidth(2.0)
            glBegin(GL_LINES)
            # Left beam
            glVertex2f(hx, hy)
            glVertex2f(hx - beam_len * 0.3, hy - beam_len)
            # Right beam
            glVertex2f(hx, hy)
            glVertex2f(hx + beam_len * 0.3, hy - beam_len)
            glEnd()

            # Beam glow
            glColor4f(0.0, 1.0, 0.5, pulse * 0.15)
            glLineWidth(8.0)
            glBegin(GL_LINES)
            glVertex2f(hx, hy)
            glVertex2f(hx - beam_len * 0.3, hy - beam_len)
            glVertex2f(hx, hy)
            glVertex2f(hx + beam_len * 0.3, hy - beam_len)
            glEnd()

            # Scanning target reticle at beam tips
            for bx, by in [(hx - beam_len * 0.3, hy - beam_len),
                           (hx + beam_len * 0.3, hy - beam_len)]:
                r = 8 + 3 * math.sin(t * 5)
                glColor4f(0.0, 1.0, 0.5, pulse * 0.5)
                glLineWidth(1.5)
                glBegin(GL_LINE_LOOP)
                for i in range(16):
                    a = 2 * math.pi * i / 16
                    glVertex2f(bx + r * math.cos(a), by + r * math.sin(a))
                glEnd()
                # Cross-hairs
                glColor4f(0.0, 1.0, 0.5, pulse * 0.3)
                glLineWidth(1.0)
                glBegin(GL_LINES)
                glVertex2f(bx - r * 0.6, by); glVertex2f(bx + r * 0.6, by)
                glVertex2f(bx, by - r * 0.6); glVertex2f(bx, by + r * 0.6)
                glEnd()

            # Central V-sign marker
            s = 20
            glColor4f(0.0, 1.0, 0.5, pulse)
            glLineWidth(2.5)
            glBegin(GL_LINES)
            glVertex2f(hx, hy - s); glVertex2f(hx - 6, hy - s + 12)
            glVertex2f(hx, hy - s); glVertex2f(hx + 6, hy - s + 12)
            glVertex2f(hx, hy - s); glVertex2f(hx, hy + s - 8)
            glEnd()

            # Outer scanning ring (rotating segments)
            rot = t * 1.5
            outer = s + 12
            glColor4f(0.0, 1.0, 0.5, pulse * 0.3)
            glLineWidth(1.5)
            glBegin(GL_LINES)
            for i in range(4):
                a = rot + math.pi / 2 * i
                a2 = a + 0.4
                glVertex2f(hx + outer * math.cos(a), hy + outer * math.sin(a))
                glVertex2f(hx + outer * math.cos(a2), hy + outer * math.sin(a2))
            glEnd()

        elif gesture == GestureController.OPEN:
            # ── Open: release mode — energy field + scanning cross ────
            r = 22 + 4 * math.sin(t * 3)

            # Pulsing energy aura (multiple layers)
            for layer in range(3):
                lr = r + layer * 8
                la = 0.25 - layer * 0.07
                glColor4f(0.0, 0.83, 1.0, la * pulse)
                glPointSize(2.0 + layer * 1.5)
                glBegin(GL_POINTS)
                for i in range(12):
                    a = t * (1.5 - layer * 0.3) + 2 * math.pi * i / 12
                    glVertex2f(hx + lr * math.cos(a), hy + lr * math.sin(a))
                glEnd()

            # Main circle
            glColor4f(0.0, 0.83, 1.0, pulse * 0.8)
            glLineWidth(1.5)
            glBegin(GL_LINE_LOOP)
            for i in range(36):
                a = 2 * math.pi * i / 36
                glVertex2f(hx + r * math.cos(a), hy + r * math.sin(a))
            glEnd()

            # Scanning cross-hair (rotating)
            rot = t * 0.8
            glColor4f(0.0, 0.83, 1.0, pulse)
            glLineWidth(2.0)
            glBegin(GL_LINES)
            glVertex2f(hx - r * 0.7, hy); glVertex2f(hx + r * 0.7, hy)
            glVertex2f(hx, hy - r * 0.7); glVertex2f(hx, hy + r * 0.7)
            glEnd()

            # Diagonal cross (rotating)
            glColor4f(0.0, 0.83, 1.0, pulse * 0.5)
            glLineWidth(1.0)
            glBegin(GL_LINES)
            d = r * 0.5
            glVertex2f(hx - d * math.cos(rot), hy - d * math.sin(rot))
            glVertex2f(hx + d * math.cos(rot), hy + d * math.sin(rot))
            glVertex2f(hx + d * math.sin(rot), hy - d * math.cos(rot))
            glVertex2f(hx - d * math.sin(rot), hy + d * math.cos(rot))
            glEnd()

            # Outer ring
            glColor4f(0.0, 0.83, 1.0, pulse * 0.2)
            glLineWidth(1.0)
            glBegin(GL_LINE_LOOP)
            for i in range(36):
                a = 2 * math.pi * i / 36
                glVertex2f(hx + (r + 10) * math.cos(a), hy + (r + 10) * math.sin(a))
            glEnd()

            # Corner tick marks
            glColor4f(0.0, 0.83, 1.0, pulse * 0.4)
            glLineWidth(1.5)
            tick_r = r + 5
            glBegin(GL_LINES)
            for i in range(4):
                a = rot + math.pi / 2 * i
                glVertex2f(hx + (tick_r - 4) * math.cos(a), hy + (tick_r - 4) * math.sin(a))
                glVertex2f(hx + (tick_r + 4) * math.cos(a), hy + (tick_r + 4) * math.sin(a))
            glEnd()

        elif gesture == GestureController.POINT:
            # ── Point: precision select — laser beam + target lock ────
            # Laser beam extending from hand
            beam_len = 120
            # Beam direction: slight downward angle
            bx = hx
            by = hy - beam_len

            # Wide beam glow
            glColor4f(0.0, 0.83, 1.0, 0.08)
            glLineWidth(12.0)
            glBegin(GL_LINES)
            glVertex2f(hx, hy)
            glVertex2f(bx, by)
            glEnd()

            # Medium beam
            glColor4f(0.0, 0.83, 1.0, 0.2)
            glLineWidth(4.0)
            glBegin(GL_LINES)
            glVertex2f(hx, hy)
            glVertex2f(bx, by)
            glEnd()

            # Core beam
            glColor4f(0.5, 1.0, 1.0, 0.7)
            glLineWidth(1.5)
            glBegin(GL_LINES)
            glVertex2f(hx, hy)
            glVertex2f(bx, by)
            glEnd()

            # Target lock circle at beam end
            lock_r = 14 + 3 * math.sin(t * 4)
            glColor4f(0.0, 0.83, 1.0, pulse * 0.7)
            glLineWidth(2.0)
            # Segmented circle (4 arcs)
            for seg in range(4):
                a_start = t * 2 + seg * math.pi / 2
                glBegin(GL_LINE_STRIP)
                for j in range(6):
                    a = a_start + j * (math.pi / 2) / 5
                    glVertex2f(bx + lock_r * math.cos(a), by + lock_r * math.sin(a))
                glEnd()

            # Cross-hair at target
            glColor4f(0.0, 0.83, 1.0, pulse * 0.5)
            glLineWidth(1.0)
            ch = 8
            glBegin(GL_LINES)
            glVertex2f(bx - ch, by); glVertex2f(bx + ch, by)
            glVertex2f(bx, by - ch); glVertex2f(bx, by + ch)
            glEnd()

            # Dot at beam origin
            glColor4f(0.0, 0.83, 1.0, 0.9)
            glPointSize(6.0)
            glBegin(GL_POINTS)
            glVertex2f(hx, hy)
            glEnd()

            # Small dot at target
            glColor4f(1.0, 1.0, 1.0, 0.8)
            glPointSize(3.0)
            glBegin(GL_POINTS)
            glVertex2f(bx, by)
            glEnd()

        # ── Gesture transition particles ─────────────────────────────
        gs['particles'] = [p for p in gs['particles'] if t - p['t0'] < p['life']]
        for p in gs['particles']:
            age = t - p['t0']
            prog = age / p['life']
            px = p['x'] + p['vx'] * age
            py = p['y'] + p['vy'] * age
            alpha = (1 - prog) * 0.8
            sz = 3.0 * (1 - prog * 0.5)
            c = p['color']
            glColor4f(c[0], c[1], c[2], alpha)
            glPointSize(sz)
            glBegin(GL_POINTS)
            glVertex2f(px, py)
            glEnd()

        # ── Dual-hand overlay ─────────────────────────────────────────
        dh = self.dual_hand
        if dh is not None and dh.active and g.both_hands_detected:
            self._draw_dual_hand_overlay(dh, t, pulse)

        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

    @staticmethod
    def _gesture_fx_color(gesture):
        """Return color tuple for a gesture type."""
        return {
            GestureController.PINCH: (1.0, 0.2, 0.4),
            GestureController.FIST:  (1.0, 0.7, 0.0),
            GestureController.PEACE: (0.0, 1.0, 0.5),
            GestureController.OPEN:  (0.0, 0.83, 1.0),
            GestureController.POINT: (0.0, 0.83, 1.0),
        }.get(gesture, (0.0, 1.0, 0.85))

    def _draw_dual_hand_overlay(self, dh: DualHandGestureManager, t, pulse):
        """Draw connection lines, anchor points, and state indicator for dual-hand."""
        g = self.gesture_ctrl
        lx = int(g.hand_positions[0][0] * self.width)
        ly = int(g.hand_positions[0][1] * self.height)
        rx = int(g.hand_positions[1][0] * self.width)
        ry = int(g.hand_positions[1][1] * self.height)
        mid_x = (lx + rx) // 2
        mid_y = (ly + ry) // 2

        # Connection line between hands
        if dh.state == DualHandGestureManager.STATE_SCALE:
            line_color = (0.0, 1.0, 0.5)    # green
        elif dh.state == DualHandGestureManager.STATE_ROTATE:
            line_color = (1.0, 0.7, 0.0)    # gold
        elif dh.state == DualHandGestureManager.STATE_REPOSITION:
            line_color = (0.0, 0.83, 1.0)   # cyan
        else:
            line_color = (0.4, 0.4, 0.4)

        glColor4f(*line_color, pulse * 0.6)
        glLineWidth(2.0)
        glBegin(GL_LINES)
        glVertex2f(lx, ly)
        glVertex2f(rx, ry)
        glEnd()

        # Dashed midpoint indicator
        glColor4f(*line_color, pulse * 0.4)
        glLineWidth(1.0)
        glPointSize(4.0)
        glBegin(GL_POINTS)
        glVertex2f(mid_x, mid_y)
        glEnd()

        # Anchor circles on each hand
        for hx, hy in [(lx, ly), (rx, ry)]:
            glColor4f(*line_color, pulse * 0.8)
            glLineWidth(2.0)
            glBegin(GL_LINE_LOOP)
            for i in range(16):
                a = 2 * math.pi * i / 16
                glVertex2f(hx + 14 * math.cos(a), hy + 14 * math.sin(a))
            glEnd()
            glColor4f(*line_color, pulse * 0.3)
            glPointSize(8.0)
            glBegin(GL_POINTS)
            glVertex2f(hx, hy)
            glEnd()

        # State label above midpoint
        state_label = dh.state.upper()
        label_x = mid_x - len(state_label) * 4
        label_y = mid_y - 30
        glColor4f(*line_color, pulse * 0.9)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        # Simple text: just draw a bracket-style indicator
        glVertex2f(label_x - 5, label_y)
        glVertex2f(label_x + len(state_label) * 8 + 5, label_y)
        glEnd()

    def _draw_power_up(self, t):
        """Legacy hook — delegates to the cinematic boot sequence."""
        if not self.power_up_active:
            return
        if not hasattr(self, '_boot_seq'):
            self._boot_seq = CinematicBoot(self.width, self.height)
        if not self._boot_seq.active:
            self.power_up_active = False
            return
        self._boot_seq.render(t - self.power_up_start)

    def _draw_fps(self):
        if self.frame_count % 30 != 0:
            return
        mode = "AR" if self.ar_mode else "3D"
        n = len(self.renderer.objects)
        plane = self.renderer.projector.draw_plane
        cn = {
            (0.0, 1.0, 0.85): "CYAN",
            (1.0, 0.2, 0.5): "PINK",
            (0.3, 0.8, 1.0): "BLUE",
            (1.0, 0.8, 0.0): "GOLD",
            (0.5, 1.0, 0.3): "LIME",
            (1.0, 0.4, 0.1): "ORANGE",
            (0.8, 0.3, 1.0): "PURPLE",
        }.get(self.input.draw_color, "CUSTOM")
        sel = ""
        if self.renderer.selected:
            sel = f" | SEL:{self.renderer.selected.name.upper()}"
        gs = ""
        if self.gesture_ctrl.enabled and self.ar_mode:
            gs = f" | {self.gesture_ctrl.gesture.upper()}"
            dh = self.dual_hand
            if dh and dh.active:
                gs += f" | DUAL:{dh.state.upper()}"
        pygame.display.set_caption(
            f"[FRIDAY.HOLO.BUILD] | {mode} | {plane} | OBJ:{n} | "
            f"{cn} | T:{self.input.draw_thickness:.0f} | D:{self.input.draw_depth:.2f}"
            f"{sel}{gs}")

    def _cleanup(self):
        self.gesture_ctrl.cleanup()
        self.ar.stop()
        pygame.quit()
        print("[HOLO] Holo Builder closed")


# ── Public API ────────────────────────────────────────────────────────

_builder_instance: Optional[HoloBuilder] = None


def holo_builder(parameters=None, player=None, **kwargs):
    """Launch / stop / query the Holo Builder.

    Parameters:
        parameters: dict with 'action' key (start/stop/status).
        player: accepted for API compatibility with main.py tool dispatch
                but not used — this module manages its own pygame window.
        **kwargs: catch-all so future callers don't crash on extra args.
    """
    global _builder_instance
    params = parameters or {}
    action = params.get("action", "start").lower()

    if action == "start":
        if _builder_instance and _builder_instance.running:
            return "Holo Builder is already running."
        _builder_instance = HoloBuilder()
        _builder_instance._run_thread = threading.Thread(target=_builder_instance.run, daemon=True)
        _builder_instance._run_thread.start()
        return (
            "FRIDAY Holo Builder v4.0 — Iron Man Edition online.\n"
            "L-Click=draw | R-Click=orbit | M-Click=pan | Scroll=zoom\n"
            "Q=plane | Tab=AR mode | Alt+drag=move | G/S=move/scale\n"
            "AR Gestures: pinch=draw | fist=move | peace=scale | open=navigate"
        )

    elif action == "stop":
        if _builder_instance:
            _builder_instance.stop()
            _builder_instance = None
            return "Holo Builder stopped."
        return "Holo Builder is not running."

    elif action == "status":
        if _builder_instance and _builder_instance.running:
            n = len(_builder_instance.renderer.objects)
            m = "AR" if _builder_instance.ar_mode else "3D"
            p = _builder_instance.renderer.projector.draw_plane
            return f"Holo Builder ({m}, plane {p}, {n} objects)."
        return "Holo Builder is not running."

    return f"Unknown action: {action}"


if __name__ == "__main__":
    builder = HoloBuilder()
    builder.run()
