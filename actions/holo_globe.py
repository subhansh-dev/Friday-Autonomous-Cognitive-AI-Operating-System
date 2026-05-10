# -*- coding: utf-8 -*-
"""
holo_globe.py - FRIDAY Holographic Globe Map v5
Rebuilt from scratch with minimal OpenGL. Each part tested before adding the next.
"""
import os, math, time, threading, traceback, queue, random
os.environ.setdefault("SDL_VIDEODRIVER", "windows")
from pathlib import Path
from collections import deque
import urllib.request

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GLOG_minloglevel'] = '2'

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
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

WIN_W, WIN_H = 1280, 720
GLOBE_RADIUS = 1.5
GLOBE_TILT = math.radians(23.5)


class HoloGlobe:
    def __init__(self):
        self.screen = None
        self.clock = None
        self.running = False
        self.width = WIN_W
        self.height = WIN_H
        self.rot_y = 0.0
        self.rot_x = 0.0
        self.rot_vel_y = 0.3
        self.rot_vel_x = 0.0
        self.zoom = 3.5
        self.gl_tex = None
        self.quadric = None
        self.show_webcam = False
        self.webcam = None
        self.webcam_surface = None
        self.mouse_down = False
        self.mouse_last = (0, 0)
        self.drag_mode = None

    def init(self):
        if not HAVE_PYGAME or not HAVE_PYOPENGL:
            print("[HOLO] pygame or PyOpenGL not available")
            return False

        pygame.init()
        pygame.display.set_mode((WIN_W, WIN_H), DOUBLEBUF | OPENGL | RESIZABLE)
        pygame.display.set_caption("FRIDAY - HoloGlobe")
        self.screen = pygame.display.get_surface()
        self.clock = pygame.time.Clock()

        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glClearColor(0.02, 0.02, 0.08, 1.0)

        self._make_globe_texture()
        print("[HOLO] Display initialized")
        return True

    def _make_globe_texture(self):
        """Create a procedural Earth-like texture using raw RGBA."""
        w, h = 512, 256
        arr = np.zeros((h, w, 4), dtype=np.uint8)
        ocean = np.array([15, 30, 60, 255])
        land = np.array([30, 80, 40, 255])
        ice = np.array([220, 230, 240, 255])

        rng = np.random.default_rng(42)
        for y in range(h):
            lat = (y / h) * 180 - 90
            for x in range(w):
                t = rng.random()
                if abs(lat) > 75:
                    arr[y, x] = ice
                elif abs(lat) > 65:
                    arr[y, x] = land if t > 0.6 else ocean
                elif abs(lat) < 25:
                    arr[y, x] = land if t > 0.65 else ocean
                else:
                    arr[y, x] = land if t > 0.7 else ocean

        self.gl_tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.gl_tex)
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, arr.tobytes())
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

        self.quadric = gluNewQuadric()
        if self.quadric:
            gluQuadricTexture(self.quadric, GL_TRUE)
            gluQuadricNormals(self.quadric, GL_SMOOTH)
        print(f"[HOLO] Texture: {w}x{h}, tex_id={self.gl_tex}")

    def run(self):
        self.running = True
        while self.running:
            self._handle_events()
            self._update()
            self._render()
            self.clock.tick(60)
        pygame.quit()

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == QUIT:
                self.running = False
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    self.running = False
                elif event.key == K_r:
                    self.rot_y = 0
                    self.rot_x = 0
            elif event.type == MOUSEBUTTONDOWN:
                self.mouse_down = True
                self.mouse_last = event.pos
            elif event.type == MOUSEBUTTONUP:
                self.mouse_down = False
                self.drag_mode = None
            elif event.type == MOUSEMOTION and self.mouse_down:
                dx = event.pos[0] - self.mouse_last[0]
                dy = event.pos[1] - self.mouse_last[1]
                if pygame.key.get_pressed()[K_LSHIFT]:
                    self.rot_x += dy * 0.3
                    self.rot_x = max(-89, min(89, self.rot_x))
                else:
                    self.rot_y += dx * 0.5
                    self.rot_x += dy * 0.3
                    self.rot_x = max(-89, min(89, self.rot_x))
                self.mouse_last = event.pos
            elif event.type == VIDEORESIZE:
                self.width, self.height = event.w, event.h
                pygame.display.set_mode((self.width, self.height), DOUBLEBUF | OPENGL | RESIZABLE)

    def _update(self):
        if not self.mouse_down:
            self.rot_y += self.rot_vel_y
        self.rot_vel_y *= 0.99

    def _render(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, self.width / self.height, 0.1, 100)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        gluLookAt(0, 0, self.zoom, 0, 0, 0, 0, 1, 0)
        glRotated(GLOBE_TILT, 1, 0, 0)
        glRotated(self.rot_y, 0, 1, 0)
        glRotated(self.rot_x, 1, 0, 0)

        self._draw_globe()
        self._draw_hud()

        pygame.display.flip()

    def _draw_globe(self):
        if self.gl_tex and self.quadric:
            glDisable(GL_LIGHTING)
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, self.gl_tex)
            glColor4f(1, 1, 1, 1)
            gluSphere(self.quadric, GLOBE_RADIUS, 64, 32)
            glDisable(GL_TEXTURE_2D)
        else:
            glColor3f(0.0, 0.8, 0.8)
            quad = gluNewQuadric()
            gluSphere(quad, GLOBE_RADIUS, 32, 32)

    def _draw_hud(self):
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)

        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width, self.height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        t = time.time()
        pulse = 0.5 + 0.3 * math.sin(t * 2)

        glColor4f(0, 1, 1, pulse * 0.3)
        glLineWidth(2.0)
        glBegin(GL_LINE_LOOP)
        for i in range(36):
            a = 2 * math.pi * i / 36
            glVertex2f(self.width//2 + 40*math.cos(a), self.height//2 + 40*math.sin(a))
        glEnd()

        glColor4f(0, 1, 1, 0.8)
        glLineWidth(1.5)
        glBegin(GL_LINES)
        glVertex2f(self.width//2 - 15, self.height//2)
        glVertex2f(self.width//2 + 15, self.height//2)
        glVertex2f(self.width//2, self.height//2 - 15)
        glVertex2f(self.width//2, self.height//2 + 15)
        glEnd()

        for i in range(0, self.height, 4):
            if i % 8 == 0:
                glColor4f(0, 0.3, 0.3, 0.1)
                glBegin(GL_LINES)
                glVertex2f(0, i)
                glVertex2f(self.width, i)
                glEnd()

        glColor4f(0, 1, 1, 0.15)
        scan_y = int((t * 50) % self.height)
        glBegin(GL_LINES)
        glVertex2f(0, scan_y)
        glVertex2f(self.width, scan_y)
        glEnd()

        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)


def holo_globe(action="open", parameters=None, player=None):
    if isinstance(action, dict):
        parameters = action
        action = parameters.get("action", "open") if parameters else "open"
    elif parameters is None:
        parameters = {}

    if action == "open":
        app = HoloGlobe()
        if app.init():
            app.run()
        return True
    elif action == "close":
        return True
    return False


if __name__ == "__main__":
    holo_globe("open")
