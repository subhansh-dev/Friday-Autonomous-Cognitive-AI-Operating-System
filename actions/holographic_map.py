# -*- coding: utf-8 -*-
"""
FRIDAY Holographic World Map v5 — "NEXUS" Edition
Real satellite imagery on a 3D globe with sci-fi aesthetics,
progressive tile loading, atmospheric glow, and gesture controls.
"""
import os, math, time, threading, queue, random, io
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from collections import deque
import urllib.request

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '2'
os.environ.pop("SDL_VIDEODRIVER", None)
os.environ["PYOPENGL_PLATFORM"] = ""

import numpy as np

try:
    import pygame
    from pygame.locals import *
    HAVE_PYGAME = True
except ImportError:
    HAVE_PYGAME = False

try:
    from OpenGL.GL import *
    from OpenGL.GLU import *
    HAVE_PYOPENGL = True
except ImportError:
    HAVE_PYOPENGL = False

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

# ── MediaPipe (lazy) ──────────────────────────────────────────────────────────
_mp = None
_HandLandmarker = _HandLandmarkerOptions = None
_FaceLandmarker = _FaceLandmarkerOptions = None
_RunningMode = _BaseOptions = None

def _load_mediapipe():
    global _mp, _HandLandmarker, _HandLandmarkerOptions
    global _FaceLandmarker, _FaceLandmarkerOptions, _RunningMode, _BaseOptions
    if _mp is not None:
        return True
    try:
        import mediapipe as mp
        from mediapipe.tasks.python.vision import (
            HandLandmarker, HandLandmarkerOptions,
            FaceLandmarker, FaceLandmarkerOptions, RunningMode)
        from mediapipe.tasks.python.core.base_options import BaseOptions
        _mp = mp; _HandLandmarker = HandLandmarker
        _HandLandmarkerOptions = HandLandmarkerOptions
        _FaceLandmarker = FaceLandmarker
        _FaceLandmarkerOptions = FaceLandmarkerOptions
        _RunningMode = RunningMode; _BaseOptions = BaseOptions
        return True
    except Exception as e:
        print(f"[NEXUS] MediaPipe unavailable: {e}")
        return False

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
TILE_CACHE = BASE_DIR / "assets" / "tile_cache"
HAND_MODEL = str(BASE_DIR / "brain" / "hand_landmarker.task")
FACE_MODEL = str(BASE_DIR / "brain" / "face_landmarker.task")

# ── Constants ─────────────────────────────────────────────────────────────────
WIN_W, WIN_H = 1280, 720
CAM_W, CAM_H = 640, 480
TILE_SIZE = 256
GLOBE_RADIUS = 1.5
GLOBE_TILT = math.radians(23.5)
MAX_ZOOM_LEVEL = 4

C_CYAN   = (0.0, 1.0, 1.0)
C_GOLD   = (1.0, 0.84, 0.0)
C_GREEN  = (0.0, 1.0, 0.0)
C_RED    = (1.0, 0.2, 0.2)
C_WHITE  = (0.9, 0.9, 0.9)
C_SILVER = (0.7, 0.7, 0.6)
C_DIM    = (0.15, 0.15, 0.12)

STATUS_COLORS = {
    "ACTIVE": (0, 1, 1), "NOMINAL": (0, 1, 0), "STABLE": (0.7, 0.7, 0.6),
    "GROWING": (0.2, 1, 0.2), "MEGA": (1, 1, 0),
}
ADVISORY_COLORS = {"LOW": (0, 1, 0), "MEDIUM": (1, 0.7, 0), "HIGH": (1, 0.2, 0.2)}

MAP_STYLES = ["SATELLITE", "TERRAIN", "STREET", "DARK", "HYBRID"]
TILE_URLS = {
    "SATELLITE": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "TERRAIN":   "https://tile.opentopomap.org/{z}/{x}/{y}.png",
    "STREET":    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "DARK":      "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
    "HYBRID":    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
}

# ── City data ─────────────────────────────────────────────────────────────────
def _c(n, la, lo, co, rg, po, tz, te, aq, we, st, no, hi="", cu="", ta="LOW"):
    return {"name": n, "lat": la, "lon": lo, "country": co, "region": rg,
            "pop": po, "tz": tz, "temp_c": te, "aqi": aq, "weather": we,
            "status": st, "notable": no, "historical": hi, "cultural": cu,
            "travel_advisory": ta}

CITIES = [
    _c("New York",    40.71,  -74.01, "USA",       "N. America", "8.3M",  "UTC-5",   18,  52, "Partly Cloudy", "ACTIVE",  "Wall St, UN HQ"),
    _c("London",      51.51,   -0.13, "UK",        "Europe",     "8.9M",  "UTC+0",   14,  42, "Overcast",      "ACTIVE",  "Canary Wharf"),
    _c("Tokyo",       35.68,  139.69, "Japan",     "E. Asia",    "14M",   "UTC+9",   20,  42, "Partly Cloudy", "NOMINAL", "Shibuya, Akihabara"),
    _c("Dubai",       25.20,   55.27, "UAE",       "Middle East","3.4M",  "UTC+4",   38,  95, "Sunny",         "GROWING", "Burj Khalifa"),
    _c("Singapore",    1.35,  103.82, "Singapore", "SE. Asia",   "5.7M",  "UTC+8",   31,  52, "Thunderstorm",  "ACTIVE",  "Marina Bay"),
    _c("Mumbai",      19.08,   72.88, "India",     "S. Asia",    "20.7M", "UTC+5:30",32, 145, "Haze",          "GROWING", "Bollywood"),
    _c("Beijing",     39.90,  116.40, "China",     "E. Asia",    "21.5M", "UTC+8",   19, 120, "Smog",          "MEGA",    "Forbidden City"),
    _c("Paris",       48.86,    2.35, "France",    "Europe",     "2.2M",  "UTC+1",   16,  48, "Partly Cloudy", "ACTIVE",  "Eiffel Tower"),
    _c("Sydney",     -33.87,  151.21, "Australia", "Oceania",    "5.3M",  "UTC+10",  16,  35, "Clear",         "STABLE",  "Opera House"),
    _c("Sao Paulo",  -23.55,  -46.63, "Brazil",    "S. America", "12.3M", "UTC-3",   20,  65, "Partly Cloudy", "STABLE",  "B3 Exchange"),
    _c("Cairo",       30.04,   31.24, "Egypt",     "Africa",     "10.2M", "UTC+2",   32, 110, "Haze",          "GROWING", "Pyramids"),
    _c("Moscow",      55.76,   37.62, "Russia",    "Europe",     "12.5M", "UTC+3",    8,  55, "Overcast",      "NOMINAL", "Kremlin"),
    _c("Istanbul",    41.01,   28.98, "Turkey",    "Europe",     "15.5M", "UTC+3",   19,  68, "Partly Cloudy", "GROWING", "Bosphorus"),
    _c("Los Angeles", 34.05, -118.24, "USA",       "N. America", "3.9M",  "UTC-8",   24,  78, "Sunny",         "ACTIVE",  "Hollywood"),
    _c("Johannesburg",-26.20,   28.05, "S. Africa", "Africa",     "5.6M",  "UTC+2",   16,  62, "Clear",         "STABLE",  "Gold Reef City"),
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  TILE MANAGER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TileManager:
    def __init__(self, style="SATELLITE", cache_size=1200):
        self.style = style
        self.cache_size = cache_size
        self.ram: Dict[Tuple, pygame.Surface] = {}
        self._q = queue.Queue()
        self._rq = queue.Queue()
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
            except queue.Empty:
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
            req = urllib.request.Request(url, headers={"User-Agent": "FRIDAY-NEXUS/5.0"})
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
            except queue.Empty:
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


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GLOBE RENDERER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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
        self.buildings = {}
        self._gen_buildings()

    def _gen_buildings(self):
        rng = random.Random(42)
        for c in CITIES:
            b = [(rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25),
                  rng.uniform(0.01, 0.06)) for _ in range(15)]
            self.buildings[c["name"]] = b

    def init_display(self):
        pygame.display.set_mode((WIN_W, WIN_H), DOUBLEBUF | OPENGL | RESIZABLE)
        pygame.display.set_caption("FRIDAY NEXUS — Holographic World Map v5")
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
        self._init_stars()
        self._request_z(2)
        print(f"[NEXUS] Display ready {WIN_W}x{WIN_H}")

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

    def _init_stars(self):
        n = 1500  # was 3000 — halved, still dense enough
        pos = np.random.uniform(-60, 60, (n, 3))
        pos[:, 2] = np.abs(pos[:, 2]) + 15
        self.stars = (pos, np.random.uniform(0.3, 1.0, n))

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

    # ── tile compositing ──────────────────────────────────────────────────────

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
                print("[NEXUS] Loading zoom 3…")
            elif self.tile_phase == 1 and sum(1 for k in self.tiles.ram if k[0] == 3) >= 36:
                self.tile_phase = 2
                self._request_z(4)
                print("[NEXUS] Loading zoom 4…")

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
        print(f"[NEXUS] Texture → {w}×{h} (z{best})")

    # ── input ─────────────────────────────────────────────────────────────────

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

    # ── update ────────────────────────────────────────────────────────────────

    def update(self, dt):
        if self.auto_rotate:
            self.rot_vy += 0.0005
        self.rot_vx *= 0.97; self.rot_vy *= 0.97
        self.rot_x += self.rot_vx; self.rot_y += self.rot_vy
        self.rot_x = max(-89, min(89, self.rot_x))
        self.rot_y %= 360
        self.zoom += (self.target_zoom - self.zoom) * 0.12

    # ── render ────────────────────────────────────────────────────────────────

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
        if self.zoom < 5.5:
            self._draw_buildings()
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
        # Vectorised twinkle: compute all brightnesses at once
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

    def _draw_buildings(self):
        glDisable(GL_LIGHTING); glDisable(GL_TEXTURE_2D)
        glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        t = time.time()
        for c in CITIES:
            for dlat, dlon, h in self.buildings.get(c["name"], []):
                bx, by, bz = self._ll2xyz(c["lat"] + dlat, c["lon"] + dlon,
                                           GLOBE_RADIUS + 0.005)
                tx, ty, tz = self._ll2xyz(c["lat"] + dlat, c["lon"] + dlon,
                                           GLOBE_RADIUS + 0.005 + h * 0.25)
                pulse = 0.5 + 0.5 * math.sin(t * 2 + dlat * 10)
                glColor4f(0, 0.6, 0.85, 0.35 * pulse); glLineWidth(2)
                glBegin(GL_LINES)
                glVertex3f(bx, by, bz); glVertex3f(tx, ty, tz)
                glEnd()
                glPointSize(4)
                glBegin(GL_POINTS)
                glColor4f(0, 0.9, 1, 0.5 * pulse); glVertex3f(tx, ty, tz)
                glEnd()
        glDisable(GL_BLEND); glLineWidth(1.0)

    def gesture_zoom(self, zoom_in):
        self.target_zoom = max(2.0, min(12.0,
            self.target_zoom + (-0.3 if zoom_in else 0.3)))

    def gesture_rotate(self, dx, dy):
        self.rot_vy += dx * 0.5; self.rot_vx += dy * 0.5

    def shutdown(self):
        self.tiles.shutdown()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EYE TRACKER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class EyeTracker:
    def __init__(self):
        self.landmarker = None
        self.eyes_open = True
        self.gaze = (0, 0)
        self.enabled = False

    def init(self):
        if not _load_mediapipe() or not Path(FACE_MODEL).exists():
            print(f"[EyeTracker] Model not found: {FACE_MODEL}")
            return False
        try:
            opts = _FaceLandmarkerOptions(
                base_options=_BaseOptions(model_asset_path=FACE_MODEL),
                running_mode=_RunningMode.LIVE_STREAM)
            self.landmarker = _FaceLandmarker.create_from_options(opts)
            self.enabled = True
            print("[EyeTracker] Ready")
            return True
        except Exception as e:
            print(f"[EyeTracker] {e}")
            return False

    def update(self, frame_rgb, ts):
        if not self.landmarker:
            return
        try:
            import mediapipe as mp
            h, w = frame_rgb.shape[:2]
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            res = self.landmarker.detect_for_video(mp_img, int(ts * 1000))
            if res and res.face_landmarks:
                lm = res.face_landmarks[0]
                self.eyes_open = lm[159].y < lm[145].y and lm[386].y < lm[374].y
                ax = (lm[33].x + lm[263].x + lm[1].x) / 3
                ay = (lm[33].y + lm[263].y + lm[1].y) / 3
                self.gaze = (ax - 0.5, ay - 0.5)
        except Exception:
            pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GESTURE CONTROLLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class GestureController:
    def __init__(self):
        self.landmarker = None
        self.gesture = "none"
        self.hand_pos = (0, 0)
        self._buf = deque(maxlen=5)
        self.enabled = False
        self.prev_pos = None

    def init(self):
        if not _load_mediapipe() or not Path(HAND_MODEL).exists():
            print(f"[Gesture] Model not found: {HAND_MODEL}")
            return False
        try:
            opts = _HandLandmarkerOptions(
                base_options=_BaseOptions(model_asset_path=HAND_MODEL),
                running_mode=_RunningMode.LIVE_STREAM, num_hands=1)
            self.landmarker = _HandLandmarker.create_from_options(opts)
            self.enabled = True
            print("[Gesture] Ready")
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
                lm = res.hand_landmarks[0]
                self.prev_pos = self.hand_pos
                self.hand_pos = (lm[9].x, lm[9].y)
                g = self._classify(lm)
                self._buf.append(g)
                if self._buf:
                    from collections import Counter
                    self.gesture = Counter(self._buf).most_common(1)[0][0]
            else:
                self.gesture = "none"
                self.prev_pos = None
        except Exception:
            pass

    @staticmethod
    def _classify(lm):
        tips = [4, 8, 12, 16, 20]
        mcps = [1, 5, 9, 13, 17]
        ext = [lm[t].y < lm[m].y for t, m in zip(tips, mcps)]
        if ext[1] and ext[2] and not ext[0] and not ext[3] and not ext[4]:
            return "peace"
        if all(ext):
            return "open"
        if not any(ext):
            return "fist"
        if ext[0] and not any(ext[1:]):
            return "point"
        if not ext[0] and all(ext[1:]):
            return "palm"
        return "pinch"

    def get_delta(self):
        if self.prev_pos and self.hand_pos:
            dx = self.hand_pos[0] - self.prev_pos[0]
            dy = self.hand_pos[1] - self.prev_pos[1]
            return dx, dy
        return 0, 0

    def get_input(self):
        return {"gesture": self.gesture, "position": self.hand_pos}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HYBRID SELECTOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class HybridSelector:
    def __init__(self):
        self.eye = EyeTracker()
        self.hand = GestureController()
        self._frame = None

    def init(self):
        e = self.eye.init()
        h = self.hand.init()
        print(f"[Hybrid] Eye={e} Hand={h}")

    def update(self, frame_rgb, ts):
        if self.eye.enabled:
            self.eye.update(frame_rgb, ts)
        if self.hand.enabled:
            self.hand.update(frame_rgb, ts)

    def get_selection(self):
        if self.eye.enabled and self.eye.eyes_open:
            gx, gy = self.eye.gaze
            if abs(gx) > 0.05 or abs(gy) > 0.05:
                return {"source": "eye", "gaze": self.eye.gaze}
        if self.hand.enabled and self.hand.gesture in ("palm", "point", "open", "fist"):
            return {"source": "hand", "gesture": self.hand.gesture,
                    "pos": self.hand.hand_pos, "delta": self.hand.get_delta()}
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  INFO PANEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class InfoPanel:
    def __init__(self):
        self.surf = None
        self.w, self.h = 310, 520
        self.phase = 0.0
        self.scan_y = 0
        self.city = None
        self.fps = 0
        self.zoom_level = 0
        self.tiles_loaded = 0
        self.map_style = "SATELLITE"
        self.eye_status = "OFFLINE"
        self.hand_status = "STANDBY"
        self.current_gesture = "none"

    def init(self):
        pygame.font.init()
        self.surf = pygame.Surface((self.w, self.h), SRCALPHA)

    def render(self, screen):
        if not self.surf:
            return
        self.phase += 0.05
        self.scan_y = (self.scan_y + 3) % self.h
        s = self.surf
        s.fill((0, 0, 0, 0))

        a = 200
        pygame.draw.rect(s, (4, 12, 22, a), (0, 0, self.w, self.h))
        glow = int(50 + 30 * math.sin(self.phase))
        pygame.draw.rect(s, (0, glow, glow, 200), (0, 0, self.w, self.h), 2)
        pygame.draw.rect(s, (0, glow, glow, 40), (0, 0, self.w, 3))
        pygame.draw.rect(s, (0, glow, glow, 40), (0, self.h - 3, self.w, 3))

        for i in range(0, self.h, 4):
            if i % 16 == 0:
                pygame.draw.line(s, (0, 60, 60, 25), (0, i), (self.w, i))
        pygame.draw.line(s, (0, 255, 255, 80), (0, self.scan_y), (self.w, self.scan_y), 2)

        ft = pygame.font.SysFont("Consolas", 20, bold=True)
        fs = pygame.font.SysFont("Consolas", 11)
        fl = pygame.font.SysFont("Consolas", 10)
        fv = pygame.font.SysFont("Consolas", 12, bold=True)

        s.blit(ft.render("FRIDAY // NEXUS", True, (0, 255, 255)), (18, 14))
        s.blit(fs.render("HOLOGRAPHIC MAP v5.0", True, (120, 120, 120)), (18, 38))
        pygame.draw.line(s, (0, 180, 180, 120), (18, 56), (self.w - 18, 56), 1)

        fields = [
            ("SYSTEM",        "NOMINAL",       C_GREEN),
            ("EYE TRACKING",  self.eye_status,  C_CYAN),
            ("HAND GESTURE",  self.hand_status, C_SILVER),
            ("GESTURE",       self.current_gesture.upper(), C_GOLD),
            ("MAP STYLE",     self.map_style,   C_WHITE),
            ("TILE ZOOM",     f"z{self.zoom_level}", C_WHITE),
            ("TILES LOADED",  str(self.tiles_loaded), C_WHITE),
            ("FPS",           str(self.fps),    C_WHITE),
            ("MARKERS",       f"{len(CITIES)} CITIES", C_WHITE),
            ("TIME",          time.strftime("%H:%M:%S"), C_WHITE),
        ]
        y = 68
        for label, val, col in fields:
            s.blit(fl.render(label, True, (90, 110, 120)), (18, y))
            s.blit(fv.render(str(val), True, col), (195, y))
            y += 22

        y += 10
        pygame.draw.line(s, (0, 180, 180, 80), (18, y), (self.w - 18, y), 1)
        y += 10
        hints = ["1-5: Map Style", "SPACE: Auto-Rotate",
                 "SCROLL: Zoom", "ARROWS: Rotate", "V: Webcam", "ESC: Exit"]
        for h in hints:
            s.blit(fl.render(h, True, (70, 90, 100)), (18, y))
            y += 16

        if self.city:
            y += 8
            pygame.draw.line(s, (0, 180, 180, 100), (18, y), (self.w - 18, y), 1)
            y += 10
            s.blit(ft.render(f"> {self.city['name'].upper()}", True, C_CYAN), (18, y))
            y += 24
            details = [
                f"Country: {self.city['country']}",
                f"Region:  {self.city['region']}",
                f"Pop:     {self.city['pop']}",
                f"Timezone:{self.city['tz']}",
                f"Temp:    {self.city['temp_c']}°C",
                f"AQI:     {self.city['aqi']}",
                f"Weather: {self.city['weather']}",
                f"Status:  {self.city['status']}",
                f"Alert:   {self.city['travel_advisory']}",
            ]
            for line in details:
                s.blit(fl.render(line, True, C_SILVER), (18, y))
                y += 16

        screen.blit(s, (WIN_W - self.w - 15, 15))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HOLOGRAPHIC FX
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class HoloFX:
    _MAX_PARTICLES = 120  # hard cap — prevents unbounded growth

    def __init__(self):
        self.particles = []
        self.timer = 0
        self._corner_cache = None  # pre-rendered corner glow surfaces

    def update(self, dt):
        self.timer += dt
        if self.timer > 0.08:
            self.timer = 0
            if len(self.particles) < self._MAX_PARTICLES:
                for _ in range(2):
                    self.particles.append({
                        "x": WIN_W / 2 + random.uniform(-80, 80),
                        "y": WIN_H / 2 + random.uniform(-80, 80),
                        "vx": random.uniform(-1.5, 1.5),
                        "vy": random.uniform(-1.5, 1.5),
                        "life": 1.0, "sz": random.uniform(2, 4)})
        for p in self.particles:
            p["x"] += p["vx"]; p["y"] += p["vy"]; p["life"] -= 0.015
        self.particles = [p for p in self.particles if p["life"] > 0]

    def render(self, screen):
        # Scan lines — draw once into a cached surface, blit each frame
        if not hasattr(self, '_scan_surf') or self._scan_surf is None:
            self._scan_surf = pygame.Surface((WIN_W, WIN_H), SRCALPHA)
            for y in range(0, WIN_H, 8):
                pygame.draw.line(self._scan_surf, (0, 30, 30, 15), (0, y), (WIN_W, y))
        screen.blit(self._scan_surf, (0, 0))

        for p in self.particles:
            r = int(p["sz"] * p["life"])
            if r > 0:
                pygame.draw.circle(screen, (0, 200, 220), (int(p["x"]), int(p["y"])), r)

        # Corner glows — cache the surfaces so we don't recreate every frame
        if self._corner_cache is None:
            self._corner_cache = []
            for _ in range(4):
                layers = []
                for i in range(3):
                    rad = 80 + i * 40
                    alpha = 15 - i * 4
                    if alpha > 0:
                        vs = pygame.Surface((rad * 2, rad * 2), SRCALPHA)
                        pygame.draw.circle(vs, (0, 10, 20, alpha), (rad, rad), rad)
                        layers.append((rad, vs))
                self._corner_cache.append(layers)
        corners = [(0, 0), (WIN_W, 0), (0, WIN_H), (WIN_W, WIN_H)]
        for corner, layers in zip(corners, self._corner_cache):
            for rad, vs in layers:
                screen.blit(vs, (corner[0] - rad, corner[1] - rad))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ZOOM CONTROLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ZoomControls:
    def __init__(self):
        self.btn_size = 40
        self.margin = 20
        x = self.margin
        y = WIN_H - 2 * self.btn_size - 3 * self.margin
        self.btn_in  = pygame.Rect(x, y, self.btn_size, self.btn_size)
        self.btn_out = pygame.Rect(x, y + self.btn_size + 10, self.btn_size, self.btn_size)

    def render(self, screen, zoom):
        font = pygame.font.SysFont("Consolas", 22, bold=True)
        for btn, label in [(self.btn_in, "+"), (self.btn_out, "−")]:
            pygame.draw.rect(screen, (0, 60, 60, 180), btn)
            pygame.draw.rect(screen, (0, 180, 180), btn, 2)
            txt = font.render(label, True, (0, 255, 255))
            screen.blit(txt, (btn.centerx - txt.get_width() // 2,
                              btn.centery - txt.get_height() // 2))
        font_sm = pygame.font.SysFont("Consolas", 11)
        ztxt = font_sm.render(f"ZOOM {zoom:.1f}", True, (0, 200, 200))
        screen.blit(ztxt, (self.margin, self.btn_out.bottom + 8))

    def handle_click(self, pos):
        if self.btn_in.collidepoint(pos):
            return "in"
        if self.btn_out.collidepoint(pos):
            return "out"
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  WEBCAM HANDLER — headless, no OpenCV window
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class WebcamHandler:
    """Reads webcam frames in the background without opening any OpenCV window."""

    def __init__(self):
        self.cap = None
        self.available = False
        self._frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def init(self):
        if not HAS_CV2:
            print("[Webcam] OpenCV not installed")
            return False
        try:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                print("[Webcam] No camera found")
                self.cap = None
                return False
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_W)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
            self.available = True
            self._running = True
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()
            print("[Webcam] Ready (headless)")
            return True
        except Exception as e:
            print(f"[Webcam] {e}")
            return False

    def _capture_loop(self):
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
        # Force close any stray OpenCV windows
        if HAS_CV2:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN APPLICATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class HoloGlobeApp:
    def __init__(self):
        self.globe = None
        self.panel = None
        self.fx = None
        self.hybrid = None
        self.zoom_ui = None
        self.webcam_handler = None
        self.running = False
        self.show_webcam = False
        self._last_city = None
        self._frame_count = 0
        self._fps_time = 0
        self._fps = 0
        self._webcam_surf = None

    def init(self):
        if not HAVE_PYGAME or not HAVE_PYOPENGL:
            print("[NEXUS] Missing pygame or PyOpenGL")
            return False
        pygame.init()
        pygame.font.init()
        self.globe = GlobeRenderer()
        self.globe.init_display()
        self.panel = InfoPanel()
        self.panel.init()
        self.fx = HoloFX()
        self.zoom_ui = ZoomControls()
        self.hybrid = HybridSelector()
        self.hybrid.init()
        self.webcam_handler = WebcamHandler()
        self.webcam_handler.init()
        print("[NEXUS] ✓ Initialized")
        return True

    def run(self):
        self.running = True
        clock = pygame.time.Clock()
        last = time.time()

        while self.running:
            now = time.time()
            dt = now - last
            last = now

            # FPS
            self._frame_count += 1
            if now - self._fps_time >= 1.0:
                self._fps = self._frame_count
                self._frame_count = 0
                self._fps_time = now

            # Events
            events = pygame.event.get()
            for e in events:
                if e.type == QUIT or (e.type == KEYDOWN and e.key == K_ESCAPE):
                    self.running = False
                elif e.type == KEYDOWN and e.key == K_t:
                    idx = (MAP_STYLES.index(self.globe.tiles.style) + 1) % len(MAP_STYLES)
                    self.globe.tiles.set_style(MAP_STYLES[idx])
                    self.globe._request_z(2)
                    self.globe.tile_phase = 0
                elif e.type == KEYDOWN and e.key == K_v:
                    self.show_webcam = not self.show_webcam
                elif e.type == MOUSEBUTTONDOWN and e.button == 1:
                    action = self.zoom_ui.handle_click(e.pos)
                    if action == "in":
                        self.globe.gesture_zoom(True)
                    elif action == "out":
                        self.globe.gesture_zoom(False)

            self.globe.handle_input(events)

            # Gesture + eye tracking (always runs, no OpenCV window)
            if self.webcam_handler and self.webcam_handler.available:
                frame = self.webcam_handler.get_frame()
                if frame is not None:
                    self.hybrid.update(frame, now)

            # Apply gesture/eye input to globe
            sel = self.hybrid.get_selection()
            if sel:
                if sel.get("source") == "eye":
                    gz = sel.get("gaze", (0, 0))
                    if abs(gz[0]) > 0.1:
                        self.globe.gesture_rotate(gz[0] * 0.3, 0)
                elif sel.get("source") == "hand":
                    g = sel.get("gesture")
                    dx, dy = sel.get("delta", (0, 0))
                    if g == "open":
                        self.globe.gesture_zoom(True)
                    elif g == "fist":
                        self.globe.gesture_zoom(False)
                    elif g == "point":
                        self.globe.gesture_rotate(dx * 2, dy * 2)
                    elif g == "palm":
                        self.globe.gesture_rotate(dx * 2, dy * 2)

            # Update
            self.globe.update(dt)
            self.globe.update_tiles()
            self.fx.update(dt)

            # Nearest city
            self._update_selected_city()

            # Panel data
            self.panel.fps = self._fps
            self.panel.zoom_level = self.globe.tile_phase + 2
            self.panel.tiles_loaded = self.globe.tiles.loaded
            self.panel.map_style = self.globe.tiles.style
            self.panel.eye_status = "ACTIVE" if self.hybrid.eye.enabled else "OFFLINE"
            self.panel.hand_status = "ACTIVE" if self.hybrid.hand.enabled else "STANDBY"
            self.panel.current_gesture = self.hybrid.hand.gesture if self.hybrid.hand.enabled else "none"

            # Render
            screen = pygame.display.get_surface()
            self.globe.render()

            # Switch to 2D overlay
            glDisable(GL_DEPTH_TEST)
            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            glOrtho(0, WIN_W, WIN_H, 0, -1, 1)
            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()

            self.fx.render(screen)
            self.panel.render(screen)
            self.zoom_ui.render(screen, self.globe.zoom)

            # Webcam overlay (drawn on pygame surface, NOT OpenCV window)
            if self.show_webcam and self.webcam_handler.available:
                self._draw_webcam_overlay(screen)

            pygame.display.flip()
            clock.tick(60)

        self.shutdown()

    def _draw_webcam_overlay(self, screen):
        frame = self.webcam_handler.get_frame()
        if frame is None:
            return
        # Convert numpy RGB to pygame surface
        surf = pygame.surfarray.make_surface(np.rot90(frame))
        surf = pygame.transform.flip(surf, True, False)
        scaled = pygame.transform.scale(surf, (CAM_W // 2, CAM_H // 2))
        x, y = 20, WIN_H - CAM_H // 2 - 20
        # Border
        border = pygame.Rect(x - 2, y - 2, CAM_W // 2 + 4, CAM_H // 2 + 4)
        pygame.draw.rect(screen, (0, 180, 180), border, 2)
        screen.blit(scaled, (x, y))
        # Label
        font = pygame.font.SysFont("Consolas", 10)
        lbl = font.render("WEBCAM", True, (0, 200, 200))
        screen.blit(lbl, (x + 4, y + 4))

    def _update_selected_city(self):
        ry = math.radians(self.globe.rot_y)
        rx = math.radians(self.globe.rot_x)
        best = None
        best_d = 999
        for c in CITIES:
            dlat = c["lat"] - math.degrees(rx)
            dlon = c["lon"] - math.degrees(ry)
            d = dlat * dlat + dlon * dlon
            if d < best_d and d < 400:
                best_d = d
                best = c
        if best != self._last_city:
            self._last_city = best
            self.panel.city = best

    def shutdown(self):
        if self.webcam_handler:
            self.webcam_handler.shutdown()
        if self.globe:
            self.globe.shutdown()
        pygame.quit()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def holographic_map(action="open", parameters=None, player=None, **kwargs):
    """Launch the holographic world map.

    Parameters:
        action: "open" to launch the map.
        parameters: optional dict of extra params (unused for now).
        player: accepted for API compatibility with main.py tool dispatch
                but not used — this module manages its own pygame window.
        **kwargs: catch-all so future callers don't crash on extra args.
    """
    if isinstance(action, dict):
        parameters = action
        action = parameters.get("action", "open") if parameters else "open"
    elif parameters is None:
        parameters = {}

    if action == "open":
        app = HoloGlobeApp()
        if app.init():
            app.run()
        return {"status": "closed"}
    return {"status": "unknown_action"}


if __name__ == "__main__":
    holographic_map("open")
