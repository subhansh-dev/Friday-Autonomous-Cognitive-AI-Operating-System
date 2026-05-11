# -*- coding: utf-8 -*-
"""
FRIDAY Holographic World Map v6 — "NEXUS" Edition
Google Earth in Edge app mode with gesture controls.
Falls back to the built-in OpenGL globe if Playwright/Edge is unavailable.
"""
import os, math, time, threading, json, random, sys
from pathlib import Path
from typing import Optional, Tuple
from collections import deque

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '2'

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
HAND_MODEL = str(BASE_DIR / "brain" / "hand_landmarker.task")

# ── MediaPipe (lazy) ──────────────────────────────────────────────────────────
_mp = None
_HandLandmarker = _HandLandmarkerOptions = None
_RunningMode = _BaseOptions = None

def _load_mediapipe():
    global _mp, _HandLandmarker, _HandLandmarkerOptions, _RunningMode, _BaseOptions
    if _mp is not None:
        return True
    try:
        import mediapipe as mp
        from mediapipe.tasks.python.vision import (
            HandLandmarker, HandLandmarkerOptions, RunningMode)
        from mediapipe.tasks.python.core.base_options import BaseOptions
        _mp = mp; _HandLandmarker = HandLandmarker
        _HandLandmarkerOptions = HandLandmarkerOptions
        _RunningMode = RunningMode; _BaseOptions = BaseOptions
        return True
    except Exception as e:
        print(f"[NEXUS] MediaPipe unavailable: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GESTURE CONTROLLER (shared between Google Earth & OpenGL globe)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class GestureController:
    """Hand gesture detection for map navigation.

    Gestures:
        fist    → grab & pan (drag the globe)
        pinch   → zoom in / rotate
        peace   → zoom out
        point   → precision aim / tilt
        open    → release / idle
        palm    → rotate globe
    """

    def __init__(self, num_hands=1):
        self.landmarker = None
        self.gesture = "none"
        self.prev_gesture = "none"
        self.hand_pos = (0.5, 0.5)
        self.prev_pos = None
        self._buf = deque(maxlen=5)
        self.enabled = False
        self.num_hands = num_hands
        self._hand_lost_frames = 0
        self._hand_lost_limit = 6

    def init(self):
        if not _load_mediapipe() or not Path(HAND_MODEL).exists():
            print(f"[Gesture] Model not found: {HAND_MODEL}")
            return False
        try:
            opts = _HandLandmarkerOptions(
                base_options=_BaseOptions(model_asset_path=HAND_MODEL),
                running_mode=_RunningMode.LIVE_STREAM,
                num_hands=self.num_hands,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.4,
                min_tracking_confidence=0.4,
            )
            self.landmarker = _HandLandmarker.create_from_options(opts)
            self.enabled = True
            print(f"[Gesture] Ready ({self.num_hands}-hand mode)")
            return True
        except Exception as e:
            print(f"[Gesture] {e}")
            return False

    def update(self, frame_rgb, ts):
        if not self.landmarker:
            return
        try:
            import mediapipe as mp
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            res = self.landmarker.detect_for_video(mp_img, int(ts * 1000))
            if res and res.hand_landmarks:
                self._hand_lost_frames = 0
                lm = res.hand_landmarks[0]
                self.prev_pos = self.hand_pos
                self.hand_pos = (lm[9].x, lm[9].y)
                g = self._classify(lm)
                self._buf.append(g)
                from collections import Counter
                self.prev_gesture = self.gesture
                self.gesture = Counter(self._buf).most_common(1)[0][0]
            else:
                self._hand_lost_frames += 1
                if self._hand_lost_frames >= self._hand_lost_limit:
                    self.prev_gesture = self.gesture
                    self.gesture = "none"
                    self.prev_pos = None
        except Exception:
            pass

    @staticmethod
    def _classify(lm):
        """Angle-based finger classification — robust to hand tilt."""
        def finger_angle(tip, pip, mcp):
            v1 = (lm[mcp].x - lm[pip].x, lm[mcp].y - lm[pip].y, lm[mcp].z - lm[pip].z)
            v2 = (lm[tip].x - lm[pip].x, lm[tip].y - lm[pip].y, lm[tip].z - lm[pip].z)
            dot = sum(a*b for a, b in zip(v1, v2))
            mag1 = math.sqrt(sum(a*a for a in v1))
            mag2 = math.sqrt(sum(a*a for a in v2))
            if mag1 < 1e-6 or mag2 < 1e-6:
                return math.pi
            return math.acos(max(-1, min(1, dot / (mag1 * mag2))))

        index_up = finger_angle(8, 6, 5) < 1.2
        middle_up = finger_angle(12, 10, 9) < 1.2
        ring_up = finger_angle(16, 14, 13) < 1.2
        pinky_up = finger_angle(20, 18, 17) < 1.2
        ext = sum([index_up, middle_up, ring_up, pinky_up])

        pinch_dist = math.hypot(lm[4].x - lm[8].x, lm[4].y - lm[8].y,
                                lm[4].z - lm[8].z)

        if ext == 0:
            return "fist"
        elif pinch_dist < 0.08 and ext >= 1:
            return "pinch"
        elif index_up and middle_up and not ring_up and not pinky_up:
            return "peace"
        elif index_up and not middle_up and not ring_up and not pinky_up:
            return "point"
        elif ext >= 3:
            return "open"
        return "open"

    def get_delta(self):
        if self.prev_pos and self.hand_pos:
            dx = self.hand_pos[0] - self.prev_pos[0]
            dy = self.hand_pos[1] - self.prev_pos[1]
            return dx, dy
        return 0, 0

    @property
    def just_changed(self):
        return self.gesture != self.prev_gesture


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GOOGLE EARTH CONTROLLER (Playwright + Edge app mode)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# JavaScript injected into Google Earth for programmatic control
_EARTH_JS = """
window.__friday_earth = {
    // Simulate mouse events for drag/pan/zoom
    _dispatch(type, x, y, dx, dy, button) {
        const el = document.elementFromPoint(x, y) || document.body;
        const opts = {
            clientX: x, clientY: y,
            screenX: x, screenY: y,
            movementX: dx, movementY: dy,
            button: button || 0,
            buttons: type === 'mouseup' ? 0 : 1,
            bubbles: true, cancelable: true
        };
        el.dispatchEvent(new MouseEvent(type, opts));
    },

    // Pan/drag the globe (fist gesture)
    drag(startX, startY, endX, endY, steps) {
        steps = steps || 10;
        this._dispatch('mousedown', startX, startY, 0, 0);
        for (let i = 1; i <= steps; i++) {
            const t = i / steps;
            const x = startX + (endX - startX) * t;
            const y = startY + (endY - startY) * t;
            const dx = (endX - startX) / steps;
            const dy = (endY - startY) / steps;
            this._dispatch('mousemove', x, y, dx, dy);
        }
        this._dispatch('mouseup', endX, endY, 0, 0);
    },

    // Zoom via scroll (pinch/peace gestures)
    zoom(x, y, delta) {
        const el = document.elementFromPoint(x, y) || document.body;
        el.dispatchEvent(new WheelEvent('wheel', {
            clientX: x, clientY: y,
            deltaY: delta,
            bubbles: true, cancelable: true
        }));
    },

    // Tilt via right-drag (point gesture)
    tilt(startX, startY, endX, endY) {
        this._dispatch('mousedown', startX, startY, 0, 0, 2);
        for (let i = 1; i <= 10; i++) {
            const t = i / 10;
            this._dispatch('mousemove',
                startX + (endX - startX) * t,
                startY + (endY - startY) * t,
                (endX - startX) / 10, (endY - startY) / 10);
        }
        this._dispatch('mouseup', endX, endY, 0, 0, 2);
    },

    // Fly to coordinates
    flyTo(lat, lon, altitude) {
        // Use the search bar or URL hash
        window.location.hash = '!a' + lat + 'd' + lon + 'e' + (altitude || 1000000);
    },

    // Get current view center
    getCenter() {
        // Try to extract from the URL hash
        const hash = window.location.hash;
        const match = hash.match(/!a([\\d.-]+)d([\\d.-]+)/);
        if (match) return { lat: parseFloat(match[1]), lon: parseFloat(match[2]) };
        return null;
    }
};
console.log('[FRIDAY] Earth control injected');
"""


class GoogleEarthController:
    """Launches Google Earth in Edge app mode and controls it via gestures."""

    EARTH_URL = "https://earth.google.com/web/"

    def __init__(self):
        self.browser = None
        self.page = None
        self.context = None
        self._pw = None
        self._pw_ctx = None
        self.active = False
        self._gesture_state = "idle"
        self._drag_start = None
        self._zoom_accum = 0.0

    def launch(self) -> bool:
        """Launch Google Earth in Edge app mode."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("[NEXUS] Playwright not installed — cannot launch Google Earth")
            print("[NEXUS] Install with: pip install playwright && playwright install")
            return False

        # Detect browser
        browser_path = self._find_browser()
        if not browser_path:
            print("[NEXUS] No Chromium browser found (Edge/Chrome)")
            return False

        try:
            self._pw_ctx = sync_playwright()
            self._pw = self._pw_ctx.start()

            print(f"[NEXUS] Launching Google Earth in app mode...")
            self.browser = self._pw.chromium.launch(
                headless=False,
                executable_path=browser_path,
                args=[
                    "--app=https://earth.google.com/web/",
                    "--disable-features=TranslateUI",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-session-crashed-bubble",
                    "--start-maximized",
                ],
            )

            self.context = self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                no_viewport=True,
            )
            self.page = self.context.new_page()

            # Navigate to Google Earth
            self.page.goto(self.EARTH_URL, wait_until="domcontentloaded",
                           timeout=30000)

            # Wait for Earth to load (the canvas element)
            try:
                self.page.wait_for_selector("canvas, #earth-container, .earth-view",
                                            timeout=15000)
            except Exception:
                print("[NEXUS] Google Earth may still be loading...")

            # Inject control JS
            try:
                self.page.evaluate(_EARTH_JS)
            except Exception as e:
                print(f"[NEXUS] JS injection warning: {e}")

            self.active = True
            print("[NEXUS] Google Earth ready — gesture controls active")
            return True

        except Exception as e:
            print(f"[NEXUS] Failed to launch Google Earth: {e}")
            self._cleanup()
            return False

    def _find_browser(self) -> Optional[str]:
        """Find a Chromium-based browser."""
        candidates = []
        if sys.platform == "win32":
            prog_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
            prog_files_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
            local_app = os.environ.get("LOCALAPPDATA", "")
            candidates = [
                os.path.join(prog_files, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(prog_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(local_app, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(prog_files, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(prog_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            ]
        elif sys.platform == "darwin":
            candidates = [
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ]
        else:  # Linux
            candidates = [
                "/usr/bin/microsoft-edge-stable",
                "/usr/bin/microsoft-edge",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium",
            ]

        for path in candidates:
            if os.path.isfile(path):
                return path
        return None

    def apply_gesture(self, gesture, hand_pos, prev_pos, dt):
        """Map gesture input to Google Earth controls."""
        if not self.active or not self.page:
            return

        try:
            cx = int(hand_pos[0] * 1920)
            cy = int(hand_pos[1] * 1080)

            if gesture == "fist":
                # Grab & pan — drag the globe
                if self._gesture_state != "dragging":
                    self._gesture_state = "dragging"
                    self._drag_start = (cx, cy)
                elif self._drag_start and prev_pos:
                    px = int(prev_pos[0] * 1920)
                    py = int(prev_pos[1] * 1080)
                    dx = cx - px
                    dy = cy - py
                    if abs(dx) > 2 or abs(dy) > 2:
                        self.page.evaluate(
                            f"window.__friday_earth && window.__friday_earth.drag({px}, {py}, {cx}, {cy}, 3)")

            elif gesture == "pinch":
                # Zoom in — scroll up
                self._zoom_accum += dt * 300
                if self._zoom_accum > 50:
                    self.page.evaluate(
                        f"window.__friday_earth && window.__friday_earth.zoom({cx}, {cy}, -120)")
                    self._zoom_accum = 0
                self._gesture_state = "zoom_in"

            elif gesture == "peace":
                # Zoom out — scroll down
                self._zoom_accum += dt * 300
                if self._zoom_accum > 50:
                    self.page.evaluate(
                        f"window.__friday_earth && window.__friday_earth.zoom({cx}, {cy}, 120)")
                    self._zoom_accum = 0
                self._gesture_state = "zoom_out"

            elif gesture == "point":
                # Tilt/rotate — right-drag
                if self._gesture_state != "tilting":
                    self._gesture_state = "tilting"
                    self._drag_start = (cx, cy)
                elif self._drag_start and prev_pos:
                    px = int(prev_pos[0] * 1920)
                    py = int(prev_pos[1] * 1080)
                    dx = cx - px
                    dy = cy - py
                    if abs(dx) > 2 or abs(dy) > 2:
                        self.page.evaluate(
                            f"window.__friday_earth && window.__friday_earth.tilt({px}, {py}, {cx}, {cy})")

            elif gesture == "open":
                # Release / idle
                self._gesture_state = "idle"
                self._drag_start = None
                self._zoom_accum = 0

            elif gesture == "palm":
                # Rotate — same as drag
                if self._gesture_state != "rotating":
                    self._gesture_state = "rotating"
                    self._drag_start = (cx, cy)
                elif self._drag_start and prev_pos:
                    px = int(prev_pos[0] * 1920)
                    py = int(prev_pos[1] * 1080)
                    self.page.evaluate(
                        f"window.__friday_earth && window.__friday_earth.drag({px}, {py}, {cx}, {cy}, 3)")

        except Exception as e:
            # Page may have been closed
            if "closed" in str(e).lower() or "target" in str(e).lower():
                self.active = False
            else:
                print(f"[NEXUS] Gesture error: {e}")

    def fly_to(self, lat: float, lon: float, altitude: int = 1000000):
        """Fly to a specific location."""
        if not self.active or not self.page:
            return False
        try:
            self.page.evaluate(
                f"window.__friday_earth && window.__friday_earth.flyTo({lat}, {lon}, {altitude})")
            return True
        except Exception:
            return False

    def _cleanup(self):
        """Clean up browser resources."""
        try:
            if self.page:
                self.page.close()
        except Exception:
            pass
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self.page = None
        self.context = None
        self.browser = None
        self._pw = None
        self.active = False

    def shutdown(self):
        self._cleanup()
        print("[NEXUS] Google Earth closed")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FALLBACK: OPENGL GLOBE (original, kept for when Playwright is unavailable)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

try:
    import numpy as np
    import pygame
    from pygame.locals import *
    from OpenGL.GL import *
    from OpenGL.GLU import *
    HAVE_OPENGL_GLOBE = True
except ImportError:
    HAVE_OPENGL_GLOBE = False

if HAVE_OPENGL_GLOBE:
    import io
    import urllib.request
    try:
        from PIL import Image as PILImage
        HAS_PIL = True
    except ImportError:
        HAS_PIL = False

    try:
        import cv2
        HAS_CV2 = True
    except ImportError:
        HAS_CV2 = False

    import queue as _queue

    WIN_W, WIN_H = 1280, 720
    CAM_W, CAM_H = 640, 480
    TILE_SIZE = 256
    GLOBE_RADIUS = 1.5
    GLOBE_TILT = math.radians(23.5)

    C_CYAN   = (0.0, 1.0, 1.0)
    C_GOLD   = (1.0, 0.84, 0.0)
    C_GREEN  = (0.0, 1.0, 0.0)
    C_SILVER = (0.7, 0.7, 0.6)
    C_WHITE  = (0.9, 0.9, 0.9)

    STATUS_COLORS = {
        "ACTIVE": (0, 1, 1), "NOMINAL": (0, 1, 0), "STABLE": (0.7, 0.7, 0.6),
        "GROWING": (0.2, 1, 0.2), "MEGA": (1, 1, 0),
    }
    MAP_STYLES = ["SATELLITE", "TERRAIN", "STREET", "DARK", "HYBRID"]
    TILE_URLS = {
        "SATELLITE": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "TERRAIN":   "https://tile.opentopomap.org/{z}/{x}/{y}.png",
        "STREET":    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "DARK":      "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "HYBRID":    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    }

    TILE_CACHE = BASE_DIR / "assets" / "tile_cache"

    def _c(n, la, lo, co, rg, po, tz, te, aq, we, st, no=""):
        return {"name": n, "lat": la, "lon": lo, "country": co, "region": rg,
                "pop": po, "tz": tz, "temp_c": te, "aqi": aq, "weather": we,
                "status": st, "notable": no}

    CITIES = [
        _c("New York",    40.71,  -74.01, "USA",       "N. America", "8.3M",  "UTC-5",   18,  52, "Partly Cloudy", "Wall St"),
        _c("London",      51.51,   -0.13, "UK",        "Europe",     "8.9M",  "UTC+0",   14,  42, "Overcast",      "Canary Wharf"),
        _c("Tokyo",       35.68,  139.69, "Japan",     "E. Asia",    "14M",   "UTC+9",   20,  42, "Partly Cloudy", "Shibuya"),
        _c("Dubai",       25.20,   55.27, "UAE",       "Middle East","3.4M",  "UTC+4",   38,  95, "Sunny",         "Burj Khalifa"),
        _c("Singapore",    1.35,  103.82, "Singapore", "SE. Asia",   "5.7M",  "UTC+8",   31,  52, "Thunderstorm",  "Marina Bay"),
        _c("Mumbai",      19.08,   72.88, "India",     "S. Asia",    "20.7M", "UTC+5:30",32, 145, "Haze",          "Bollywood"),
        _c("Beijing",     39.90,  116.40, "China",     "E. Asia",    "21.5M", "UTC+8",   19, 120, "Smog",          "Forbidden City"),
        _c("Paris",       48.86,    2.35, "France",    "Europe",     "2.2M",  "UTC+1",   16,  48, "Partly Cloudy", "Eiffel Tower"),
        _c("Sydney",     -33.87,  151.21, "Australia", "Oceania",    "5.3M",  "UTC+10",  16,  35, "Clear",         "Opera House"),
        _c("Sao Paulo",  -23.55,  -46.63, "Brazil",    "S. America", "12.3M", "UTC-3",   20,  65, "Partly Cloudy", "B3 Exchange"),
        _c("Cairo",       30.04,   31.24, "Egypt",     "Africa",     "10.2M", "UTC+2",   32, 110, "Haze",          "Pyramids"),
        _c("Moscow",      55.76,   37.62, "Russia",    "Europe",     "12.5M", "UTC+3",    8,  55, "Overcast",      "Kremlin"),
        _c("Istanbul",    41.01,   28.98, "Turkey",    "Europe",     "15.5M", "UTC+3",   19,  68, "Partly Cloudy", "Bosphorus"),
        _c("Los Angeles", 34.05, -118.24, "USA",       "N. America", "3.9M",  "UTC-8",   24,  78, "Sunny",         "Hollywood"),
        _c("Johannesburg",-26.20,   28.05, "S. Africa", "Africa",     "5.6M",  "UTC+2",   16,  62, "Clear",         "Gold Reef City"),
    ]

    class TileManager:
        def __init__(self, style="SATELLITE", cache_size=1200):
            self.style = style
            self.cache_size = cache_size
            self.ram = {}
            self._q = _queue.Queue()
            self._rq = _queue.Queue()
            self._lock = threading.Lock()
            self._running = True
            self.loaded = 0
            TILE_CACHE.mkdir(parents=True, exist_ok=True)
            self._workers = [threading.Thread(target=self._work, daemon=True) for _ in range(8)]
            for t in self._workers:
                t.start()

        def _work(self):
            while self._running:
                try:
                    z, y, x, key = self._q.get(timeout=0.5)
                except _queue.Empty:
                    continue
                if key is None:
                    break
                surf = self._fetch(z, y, x)
                if surf:
                    self._rq.put((key, surf))

        def _fetch(self, z, y, x):
            cache = TILE_CACHE / f"{self.style}_{z}_{x}_{y}.png"
            if cache.exists():
                try:
                    return pygame.image.load(str(cache)).convert_alpha()
                except Exception:
                    pass
            url = TILE_URLS[self.style].format(z=z, y=y, x=x)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "FRIDAY-NEXUS/6.0"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = r.read()
                if HAS_PIL:
                    img = PILImage.open(io.BytesIO(data)).convert("RGBA")
                    surf = pygame.image.fromstring(img.tobytes(), img.size, "RGBA")
                    img.save(str(cache))
                else:
                    surf = pygame.image.load(io.BytesIO(data)).convert_alpha()
                    pygame.image.save(surf, str(cache))
                self.loaded += 1
                return surf
            except Exception:
                return None

        def request(self, z, y, x):
            key = (z, y, x)
            with self._lock:
                if key in self.ram:
                    return self.ram[key]
            self._q.put((z, y, x, key))
            return None

        def get(self, z, y, x):
            with self._lock:
                return self.ram.get((z, y, x))

        def collect(self):
            new = []
            while True:
                try:
                    key, surf = self._rq.get_nowait()
                    with self._lock:
                        if len(self.ram) >= self.cache_size:
                            del self.ram[next(iter(self.ram))]
                        self.ram[key] = surf
                    new.append((key, surf))
                except _queue.Empty:
                    break
            return new

        def set_style(self, s):
            if s != self.style:
                self.style = s
                with self._lock:
                    self.ram.clear()

        def shutdown(self):
            self._running = False
            for _ in self._workers:
                self._q.put(None)

    class GlobeRenderer:
        def __init__(self):
            self.rot_x = 15.0
            self.rot_y = 0.0
            self.rot_vx = 0.0
            self.rot_vy = 0.15
            self.zoom = 4.5
            self.target_zoom = 4.5
            self.auto_rotate = True
            self.tiles = TileManager()
            self.tex_id = None
            self.tex_w = self.tex_h = 0
            self.tex_dirty = True
            self.tile_phase = 0
            self.last_req = 0
            self.stars = None
            self._init_stars()

        def _init_stars(self):
            n = 1500
            pos = np.random.uniform(-60, 60, (n, 3))
            pos[:, 2] = np.abs(pos[:, 2]) + 15
            self.stars = (pos, np.random.uniform(0.3, 1.0, n))

        def init_display(self):
            pygame.display.set_mode((WIN_W, WIN_H), DOUBLEBUF | OPENGL | RESIZABLE)
            pygame.display.set_caption("FRIDAY NEXUS — Holographic Globe (fallback)")
            glEnable(GL_DEPTH_TEST)
            glEnable(GL_TEXTURE_2D)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glClearColor(0.008, 0.008, 0.035, 1.0)
            glEnable(GL_LIGHTING)
            glEnable(GL_LIGHT0)
            glLightfv(GL_LIGHT0, GL_POSITION, (2, 3, 2, 0))
            glLightfv(GL_LIGHT0, GL_DIFFUSE,  (0.85, 0.85, 0.95, 1))
            glLightfv(GL_LIGHT0, GL_AMBIENT,  (0.25, 0.25, 0.35, 1))
            self.tex_id = glGenTextures(1)
            self._placeholder()
            self._request_z(2)
            print(f"[NEXUS] Fallback globe ready {WIN_W}x{WIN_H}")

        def _placeholder(self):
            w, h = 1024, 512
            a = np.zeros((h, w, 4), dtype=np.uint8)
            a[:, :, 0] = 8; a[:, :, 1] = 14; a[:, :, 2] = 32; a[:, :, 3] = 255
            for i in range(0, w, 64):
                a[:, i, 1] = 50; a[:, i, 2] = 70
            for i in range(0, h, 64):
                a[i, :, 1] = 50; a[i, :, 2] = 70
            self._upload(a, w, h)

        def _upload(self, arr, w, h):
            self.tex_w, self.tex_h = w, h
            glBindTexture(GL_TEXTURE_2D, self.tex_id)
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA,
                         GL_UNSIGNED_BYTE, arr.tobytes())
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            glGenerateMipmap(GL_TEXTURE_2D)
            self.tex_dirty = False

        def _request_z(self, z):
            n = 2 ** z
            for y in range(n):
                for x in range(n):
                    self.tiles.request(z, y, x)

        @staticmethod
        def _ll2xyz(lat, lon, r=GLOBE_RADIUS):
            p = math.radians(90 - lat)
            t = math.radians(lon + 180)
            return r * math.sin(p) * math.cos(t), r * math.cos(p), r * math.sin(p) * math.sin(t)

        def update_tiles(self):
            now = time.time()
            new = self.tiles.collect()
            if new:
                self.tex_dirty = True
            if now - self.last_req > 0.5:
                self.last_req = now
                if self.tile_phase == 0 and sum(1 for k in self.tiles.ram if k[0] == 2) >= 10:
                    self.tile_phase = 1
                    self._request_z(3)
                elif self.tile_phase == 1 and sum(1 for k in self.tiles.ram if k[0] == 3) >= 36:
                    self.tile_phase = 2
                    self._request_z(4)
            if self.tex_dirty:
                self._composite()

        def _composite(self):
            best = 2
            for z in (4, 3, 2):
                if any(k[0] == z for k in self.tiles.ram):
                    best = z
                    break
            w = (2 ** best) * TILE_SIZE
            h = w
            arr = np.zeros((h, w, 4), dtype=np.uint8)
            arr[:, :, 3] = 255
            for z in range(2, best + 1):
                n = 2 ** z
                sc = 2 ** (best - z)
                tw = TILE_SIZE * sc
                for ty in range(n):
                    for tx in range(n):
                        tile = self.tiles.get(z, ty, tx)
                        if tile is None:
                            continue
                        try:
                            td = np.frombuffer(
                                pygame.image.tobytes(tile, "RGBA", True),
                                dtype=np.uint8).reshape(TILE_SIZE, TILE_SIZE, 4)
                        except Exception:
                            continue
                        if sc > 1:
                            td = np.repeat(np.repeat(td, sc, axis=0), sc, axis=1)
                        ys, xs = ty * tw, tx * tw
                        ye = min(ys + tw, h)
                        xe = min(xs + tw, w)
                        arr[ys:ye, xs:xe] = td[:ye - ys, :xe - xs]
            self._upload(arr, w, h)

        def handle_input(self, events):
            for e in events:
                if e.type == KEYDOWN:
                    if e.key == K_SPACE:
                        self.auto_rotate = not self.auto_rotate
                    elif K_1 <= e.key <= K_5:
                        idx = e.key - K_1
                        self.tiles.set_style(MAP_STYLES[idx])
                        self._request_z(2); self.tile_phase = 0
                    elif e.key in (K_PLUS, K_EQUALS):
                        self.target_zoom = max(2.0, self.target_zoom - 0.5)
                    elif e.key == K_MINUS:
                        self.target_zoom = min(12.0, self.target_zoom + 0.5)
                elif e.type == MOUSEBUTTONDOWN:
                    if e.button == 4:
                        self.target_zoom = max(2.0, self.target_zoom - 0.3)
                    elif e.button == 5:
                        self.target_zoom = min(12.0, self.target_zoom + 0.3)
            keys = pygame.key.get_pressed()
            if keys[K_LEFT]:  self.rot_vy -= 0.03
            if keys[K_RIGHT]: self.rot_vy += 0.03
            if keys[K_UP]:    self.rot_vx -= 0.03
            if keys[K_DOWN]:  self.rot_vx += 0.03
            mb = pygame.mouse.get_pressed()
            if mb[0]:
                dx, dy = pygame.mouse.get_rel()
                self.rot_vy += dx * 0.005
                self.rot_vx += dy * 0.005

        def update(self, dt):
            if self.auto_rotate:
                self.rot_vy += 0.0005
            self.rot_vx *= 0.97; self.rot_vy *= 0.97
            self.rot_x += self.rot_vx; self.rot_y += self.rot_vy
            self.rot_x = max(-89, min(89, self.rot_x))
            self.rot_y %= 360
            self.zoom += (self.target_zoom - self.zoom) * 0.12

        def render(self):
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            glMatrixMode(GL_PROJECTION); glLoadIdentity()
            gluPerspective(45, WIN_W / max(WIN_H, 1), 0.1, 200)
            glMatrixMode(GL_MODELVIEW); glLoadIdentity()
            gluLookAt(0, 0, self.zoom, 0, 0, 0, 0, 1, 0)
            self._draw_stars()
            glPushMatrix()
            glRotated(math.degrees(GLOBE_TILT), 1, 0, 0)
            glRotated(self.rot_x, 1, 0, 0)
            glRotated(self.rot_y, 0, 1, 0)
            self._draw_globe()
            self._draw_grid()
            self._draw_markers()
            glPopMatrix()
            self._draw_atmosphere()

        def _draw_globe(self):
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, self.tex_id)
            glColor4f(1, 1, 1, 1)
            glEnable(GL_CULL_FACE); glCullFace(GL_BACK)
            glEnable(GL_LIGHTING)
            glMaterialfv(GL_FRONT, GL_DIFFUSE, (1, 1, 1, 1))
            glMaterialfv(GL_FRONT, GL_AMBIENT, (0.3, 0.3, 0.3, 1))
            q = gluNewQuadric()
            gluQuadricTexture(q, GL_TRUE)
            gluQuadricNormals(q, GL_SMOOTH)
            gluSphere(q, GLOBE_RADIUS, 80, 40)
            gluDeleteQuadric(q)
            glDisable(GL_CULL_FACE)
            glDisable(GL_TEXTURE_2D)
            glDisable(GL_LIGHTING)

        def _draw_atmosphere(self):
            glDisable(GL_DEPTH_TEST)
            glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE)
            glDisable(GL_LIGHTING); glDisable(GL_TEXTURE_2D)
            glEnable(GL_CULL_FACE); glCullFace(GL_FRONT)
            for r, a in ((1.05, 0.07), (1.12, 0.04), (1.22, 0.02)):
                glColor4f(0.0, 0.35, 0.65, a)
                q = gluNewQuadric()
                gluSphere(q, GLOBE_RADIUS * r, 32, 16)
                gluDeleteQuadric(q)
            glCullFace(GL_BACK); glDisable(GL_CULL_FACE)
            glDisable(GL_BLEND); glEnable(GL_DEPTH_TEST)

        def _draw_stars(self):
            if not self.stars:
                return
            pos, bri = self.stars
            glDisable(GL_LIGHTING); glDisable(GL_DEPTH_TEST)
            glEnable(GL_POINT_SMOOTH); glPointSize(2.0)
            t = time.time()
            indices = np.arange(len(bri))
            colours = bri * (0.7 + 0.3 * np.sin(t * 2 + indices * 0.5))
            glBegin(GL_POINTS)
            for i in range(len(pos)):
                c = colours[i]
                glColor3f(c, c, c * 1.1)
                glVertex3f(pos[i, 0], pos[i, 1], pos[i, 2])
            glEnd()
            glDisable(GL_POINT_SMOOTH); glEnable(GL_DEPTH_TEST)

        def _draw_grid(self):
            glDisable(GL_LIGHTING); glDisable(GL_TEXTURE_2D)
            glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            r = GLOBE_RADIUS + 0.002
            glColor4f(0, 0.45, 0.45, 0.12); glLineWidth(1.0)
            for lat in range(-80, 81, 20):
                glBegin(GL_LINE_STRIP)
                for lon in range(0, 361, 5):
                    glVertex3f(*self._ll2xyz(lat, lon, r))
                glEnd()
            for lon in range(0, 360, 20):
                glBegin(GL_LINE_STRIP)
                for lat in range(-90, 91, 5):
                    glVertex3f(*self._ll2xyz(lat, lon, r))
                glEnd()
            glColor4f(0, 0.75, 0.75, 0.25); glLineWidth(1.5)
            glBegin(GL_LINE_STRIP)
            for lon in range(0, 361, 3):
                glVertex3f(*self._ll2xyz(0, lon, r))
            glEnd()
            glDisable(GL_BLEND); glLineWidth(1.0)

        def _draw_markers(self):
            glDisable(GL_LIGHTING); glDisable(GL_TEXTURE_2D)
            glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE)
            t = time.time()
            for c in CITIES:
                x, y, z = self._ll2xyz(c["lat"], c["lon"], GLOBE_RADIUS + 0.01)
                col = STATUS_COLORS.get(c["status"], C_CYAN)
                pulse = 0.6 + 0.4 * math.sin(t * 3 + hash(c["name"]) % 99)
                glPointSize(8 * pulse)
                glBegin(GL_POINTS)
                glColor4f(*col, 0.9); glVertex3f(x, y, z)
                glEnd()
                glPointSize(18 * pulse)
                glBegin(GL_POINTS)
                glColor4f(*col, 0.15); glVertex3f(x, y, z)
                glEnd()
            glDisable(GL_BLEND); glPointSize(1.0)

        def gesture_zoom(self, zoom_in):
            self.target_zoom = max(2.0, min(12.0,
                self.target_zoom + (-0.3 if zoom_in else 0.3)))

        def gesture_rotate(self, dx, dy):
            self.rot_vy += dx * 0.5; self.rot_vx += dy * 0.5

        def shutdown(self):
            self.tiles.shutdown()

    class WebcamHandler:
        def __init__(self):
            self.cap = None
            self.available = False
            self._frame = None
            self._lock = threading.Lock()
            self._running = False

        def init(self):
            if not HAS_CV2:
                return False
            try:
                self.cap = cv2.VideoCapture(0)
                if not self.cap.isOpened():
                    self.cap = None
                    return False
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_W)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
                self.available = True
                self._running = True
                threading.Thread(target=self._loop, daemon=True).start()
                return True
            except Exception:
                return False

        def _loop(self):
            while self._running and self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    with self._lock:
                        self._frame = rgb
                else:
                    time.sleep(0.03)

        def get_frame(self):
            with self._lock:
                return self._frame.copy() if self._frame is not None else None

        def shutdown(self):
            self._running = False
            if self.cap:
                self.cap.release()
            if HAS_CV2:
                try:
                    cv2.destroyAllWindows()
                except Exception:
                    pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def holographic_map(action="open", parameters=None, player=None, **kwargs):
    """Launch the holographic world map.

    Prefers Google Earth in Edge app mode with gesture controls.
    Falls back to the built-in OpenGL satellite globe if unavailable.

    Parameters:
        action: "open" to launch.
        parameters: optional dict.
        player: accepted for API compatibility.
        **kwargs: catch-all.
    """
    if isinstance(action, dict):
        parameters = action
        action = parameters.get("action", "open") if parameters else "open"
    elif parameters is None:
        parameters = {}

    if action == "close":
        return "Holographic map closed."
    if action == "status":
        return "Holographic map: Google Earth mode with gesture controls."

    if action != "open":
        return {"status": "unknown_action"}

    # ── Try Google Earth in Edge app mode first ──────────────────────────
    earth = GoogleEarthController()
    gesture = GestureController(num_hands=1)

    if earth.launch():
        # Initialize gesture controller
        gesture.init()

        # Start webcam for gestures
        webcam = None
        if HAVE_OPENGL_GLOBE:
            webcam = WebcamHandler()
            webcam.init()

        print("[NEXUS] Google Earth running — gesture controls active")
        print("[NEXUS]   Fist=drag | Pinch=zoom in | Peace=zoom out | Point=tilt | Open=idle")

        try:
            last_time = time.time()
            while earth.active:
                now = time.time()
                dt = now - last_time
                last_time = now

                # Process gestures
                if webcam and webcam.available:
                    frame = webcam.get_frame()
                    if frame is not None:
                        gesture.update(frame, now)

                if gesture.gesture != "none":
                    earth.apply_gesture(
                        gesture.gesture,
                        gesture.hand_pos,
                        gesture.prev_pos,
                        dt,
                    )

                time.sleep(0.016)  # ~60fps

        except KeyboardInterrupt:
            pass
        finally:
            earth.shutdown()
            if webcam:
                webcam.shutdown()
            gesture.landmarker = None
        return {"status": "closed"}

    # ── Fallback: OpenGL globe ───────────────────────────────────────────
    print("[NEXUS] Google Earth unavailable — falling back to OpenGL globe")
    if not HAVE_OPENGL_GLOBE:
        print("[NEXUS] Neither Playwright nor pygame/PyOpenGL available")
        return {"status": "error", "msg": "No display backend available"}

    app = OpenGLGlobeApp()
    if app.init():
        app.run()
    return {"status": "closed"}


class OpenGLGlobeApp:
    """Fallback OpenGL globe with gesture controls."""

    def __init__(self):
        self.globe = None
        self.gesture = None
        self.webcam = None
        self.running = False

    def init(self):
        pygame.init()
        pygame.font.init()
        self.globe = GlobeRenderer()
        self.globe.init_display()
        self.gesture = GestureController()
        self.gesture.init()
        self.webcam = WebcamHandler()
        self.webcam.init()
        return True

    def run(self):
        self.running = True
        clock = pygame.time.Clock()
        last = time.time()

        while self.running:
            now = time.time()
            dt = now - last
            last = now

            events = pygame.event.get()
            for e in events:
                if e.type == QUIT or (e.type == KEYDOWN and e.key == K_ESCAPE):
                    self.running = False

            self.globe.handle_input(events)

            # Gesture input
            if self.webcam and self.webcam.available:
                frame = self.webcam.get_frame()
                if frame is not None:
                    self.gesture.update(frame, now)

            g = self.gesture.gesture
            if g == "open":
                self.globe.gesture_zoom(True)
            elif g == "fist":
                self.globe.gesture_zoom(False)
            elif g in ("point", "palm"):
                dx, dy = self.gesture.get_delta()
                self.globe.gesture_rotate(dx * 2, dy * 2)

            self.globe.update(dt)
            self.globe.update_tiles()
            self.globe.render()

            pygame.display.flip()
            clock.tick(60)

        self.shutdown()

    def shutdown(self):
        if self.webcam:
            self.webcam.shutdown()
        if self.globe:
            self.globe.shutdown()
        pygame.quit()


if __name__ == "__main__":
    holographic_map("open")
