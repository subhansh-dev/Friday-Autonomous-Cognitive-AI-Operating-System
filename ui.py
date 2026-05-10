import os, json, time, math, random, threading, platform
import tkinter as tk
from collections import deque
from PIL import Image, ImageTk, ImageDraw, ImageEnhance
import sys
from pathlib import Path
import queue

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

SYSTEM_NAME = "F.R.I.D.A.Y"
MODEL_BADGE = "KAIRO"
DEVELOPER   = "SUBHANSH"
STUDIO      = "NEARX STUDIOS"

def _load_user_name():
    try:
        api_file = get_base_dir() / "config" / "api_keys.json"
        data = json.loads(api_file.read_text(encoding="utf-8"))
        return data.get("user_name", "OPERATOR").upper()
    except Exception:
        return "OPERATOR"

YOUR_NAME = _load_user_name()

# --- Holographic HUD Palette (Ultra Sci-Fi Neon) ---
C_BG       = "#02040a"
C_BG2      = "#050a15"
C_PRI      = "#00f2ff"
C_MAG      = "#7000ff"
C_PURP     = "#0080ff"
C_PURP2    = "#1a0033"
C_SILVER   = "#e6ffff"
C_SILVER2  = "#2d4a6b"
C_DIM      = "#001020"
C_TEXT     = "#b0eaff"
C_GREEN    = "#00ffcc"
C_RED      = "#ff0055"
C_YELLOW   = "#f9ff21"
C_PANEL    = "#000c14"
C_GLOW_C   = "#00ffff"
C_GLOW_M   = "#0055ff"

def hex_points(cx, cy, r, rotation=0):
    pts = []
    for i in range(6):
        a = math.radians(60 * i + rotation)
        pts.append(cx + r * math.cos(a))
        pts.append(cy + r * math.sin(a))
    return pts

def diamond_points(cx, cy, w, h):
    return [cx, cy - h, cx + w, cy, cx, cy + h, cx - w, cy]

CODE_LINES = [
    "neural.matrix.init()",
    "kairo.sync(user='SUBHANSH')",
    "∴ gemini_2_5.stream()",
    "∴ voice.pipeline.start()",
    "mem.recall(depth='infinite')",
    "∵ threat_scan = NONE",
    "clap.detect.armed = True",
    "telegram.bridge.uplink()",
    "∴ tools.manifest.load()",
    "encrypt(mode='AES-512')",
    "cloud.sync.active()",
    "∵ vision.camera.active",
    "∴ screen.capture.ready()",
    "id.status = VERIFIED",
    "∵ response.latency = 42ms",
    "uptime.tick(interval=1)",
    "∴ persona.kairo.v9.1()",
    "∵ memory.persist.write()",
    "action.queue.flush()",
    "∴ status = NOMINAL",
]

GLITCH_CHARS = "!@#$%^&*()_+-=[]{};:<>,.?/\\|"


class FridayUI:
    def __init__(self, face_path, size=None):
        self.root = tk.Tk()
        self.root.title("F.R.I.D.A.Y - KAIRO v9.1")
        self.root.resizable(False, False)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        W  = min(sw, 1100)
        H  = min(sh, 800)
        self.root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        self.root.configure(bg=C_BG)

        self.W = W
        self.H = H

        self.ORB_ZONE_W = int(W * 0.35)
        self.DATA_ZONE_X = self.ORB_ZONE_W
        self.DATA_ZONE_W = W - self.ORB_ZONE_W

        self.FACE_SZ = min(int(H * 0.38), 290)
        self.FCX     = self.ORB_ZONE_W // 2
        self.FCY     = int(H * 0.42)

        # State
        self.speaking      = False
        self.muted         = False
        self.scale         = 1.0
        self.target_scale  = 1.0
        self.halo_a        = 90.0
        self.target_halo   = 90.0
        self.last_t        = time.time()
        self.tick          = 0
        self.scan_angle    = 0.0
        self.scan2_angle   = 180.0
        self.scan3_angle   = 90.0
        self.pulse_r       = [0.0, self.FACE_SZ * 0.3, self.FACE_SZ * 0.6]
        self.status_text   = "INITIALISING"
        self.status_blink  = True
        self._friday_state = "INITIALISING"
        self.typing_queue  = deque()
        self.is_typing     = False
        self.on_text_command = None
        self.on_focus_mode_toggle = None
        self.on_think_mode_toggle  = None
        self.on_deep_dive_toggle   = None
        self.focus_mode    = False
        self._think_mode   = False
        self._face_pil     = None
        self._has_face     = False
        self._face_scale_cache = None

        self._start_time  = time.time()
        self._mem_used    = random.uniform(2.1, 3.8)
        self._cpu_load    = random.uniform(12, 35)
        self._cpu_history = deque(maxlen=60)
        self._net_ping    = random.randint(18, 64)
        self._code_offset = 0
        self._glitch_timer = 0
        self._glitch_active = False
        self._glitch_text   = ""

        # --- Ring system ---
        self._rings = [
            (0.56, 1.8,  140, 40, 4, 0,  0.0),
            (0.52, -1.2, 90,  50, 2, 1, 45.0),
            (0.46, 2.4,  45,  30, 2, 0, 90.0),
            (0.40, -1.8, 60,  40, 1, 2, 135.0),
            (0.34, 3.2,  30,  20, 1, 0, 180.0),
            (0.28, -2.5, 20,  15, 1, 3, 225.0),
            (0.62, 0.6,  10,  170, 1, 1, 0.0),
        ]
        self._energy_dots = [
            (random.uniform(0, 360), random.uniform(0.26, 0.52),
             random.uniform(1.2, 3.2), random.randint(0, 2))
            for _ in range(32)
        ]
        self._data_arcs = [(i * 60.0, random.uniform(0.4, 0.9), i % 3) for i in range(6)]
        self._inner_spin = [i * 45.0 for i in range(8)]
        self._hex_ring   = [i * 60.0 for i in range(6)]

        # --- Enhanced background elements (more particles) ---
        random.seed(42)
        self._bg_particles = [
            (random.randint(0, 1100), random.randint(0, 800),
             random.uniform(0.5, 3.0), random.randint(0, 3),
             random.uniform(0, math.pi * 2))
            for _ in range(120)   # increased from 60
        ]
        self._bg_hexagons = [
            (random.randint(0, 1100), random.randint(0, 800),
             random.randint(12, 55), random.randint(0, 2),
             random.uniform(0, math.pi * 2))
            for _ in range(28)    # increased from 18
        ]
        self._bg_lines = [
            (random.randint(0, 1100), random.randint(0, 800),
             random.uniform(0, math.pi * 2), random.randint(30, 150),
             random.randint(0, 3))
            for _ in range(36)    # increased from 24
        ]
        self._bg_circles = [
            (random.randint(0, 1100), random.randint(0, 800),
             random.randint(8, 50), random.randint(0, 3))
            for _ in range(30)    # increased from 20
        ]
        self._bg_spin = 0.0
        random.seed()
        self._diamond_spin = 0.0
        self._tri_spin    = [0.0, 120.0, 240.0]

        # --- Neural network for background threads (more nodes) ---
        self.neural_nodes = []
        self.neural_edges = []
        self._build_neural_network(120, self.ORB_ZONE_W, self.H)  # more nodes
        self.neural_state_color = (0, 200, 255)   # default cyan (listening)

        self._load_face(face_path)

        self.bg = tk.Canvas(self.root, width=W, height=H, bg=C_BG, highlightthickness=0)
        self.bg.place(x=0, y=0)

        # --- Right panel: log + input ---
        LOG_X = self.DATA_ZONE_X + 20
        LOG_W = self.DATA_ZONE_W - 40
        LOG_Y = int(H * 0.13)
        LOG_H = int(H * 0.48)

        self.log_frame = tk.Frame(self.root, bg=C_PANEL, highlightbackground=C_PURP2, highlightthickness=1)
        self.log_frame.place(x=LOG_X, y=LOG_Y, width=LOG_W, height=LOG_H)

        self._log_header = tk.Canvas(self.log_frame, width=LOG_W-2, height=22,
                                     bg=C_PANEL, highlightthickness=0)
        self._log_header.pack(side="top", fill="x")
        self._log_header.create_rectangle(0,0,LOG_W,22, fill="#000000", outline="")
        self._log_header.create_text(10, 11, text="◈ HOLOGRAPHIC COMM LINK",
                                     fill=C_PURP, font=("Courier",8,"bold"), anchor="w")
        self._log_header.create_text(LOG_W-10, 11, text="ENCRYPTED",
                                     fill=C_SILVER2, font=("Courier",7), anchor="e")

        self.log_text = tk.Text(self.log_frame, fg=C_TEXT, bg=C_PANEL,
                                insertbackground=C_PRI, borderwidth=0,
                                wrap="word", font=("Courier",9), padx=10, pady=6)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")
        self.log_text.tag_config("you", foreground=C_SILVER)
        self.log_text.tag_config("ai",  foreground=C_PRI)
        self.log_text.tag_config("sys", foreground=C_PURP)
        self.log_text.tag_config("err", foreground=C_RED)

        # --- CPU Graph (only graph, no metric bars) ---
        GRAPH_H = 100   # taller to fill space
        self.graph_canvas = tk.Canvas(self.root, width=LOG_W, height=GRAPH_H,
                                      bg=C_BG, highlightbackground=C_PURP2,
                                      highlightthickness=1)
        self.graph_canvas.place(x=LOG_X, y=LOG_Y + LOG_H + 10)

        INPUT_Y = LOG_Y + LOG_H + GRAPH_H + 20
        self._build_input_bar(LOG_W, LOG_X, INPUT_Y)

        self._build_button_panel()
        self._build_bottom_bar()

        # --- Waveform (voice activity) ---
        self.waveform_canvas = tk.Canvas(self.root, width=200, height=40,
                                         bg=C_BG, highlightthickness=0)
        self.waveform_canvas.place(x=self.FCX - 100, y=self.H - 120)
        self.amplitude_queue = queue.Queue()
        self._check_amplitude()

        # --- Toast notifications ---
        self.toast_canvas = None
        self.toast_timer = None

        self.root.bind("<F4>", lambda e: self._toggle_mute())

        self._api_key_ready = self._api_keys_exist()
        if not self._api_key_ready:
            self._show_setup_ui()

        self._scroll_code()
        self._update_metrics()   # still updates CPU load and graph
        self._animate()
        self.root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))

    # ---------- Neural network for background ----------
    def _build_neural_network(self, num_nodes, max_x, max_y):
        nodes = []
        for _ in range(num_nodes):
            nodes.append({
                'x': random.uniform(0, max_x),
                'y': random.uniform(0, max_y),
                'activation': random.uniform(0, 0.2),
                'target': 0
            })
        edges = []
        for i, a in enumerate(nodes):
            for j, b in enumerate(nodes[i+1:]):
                dx = a['x'] - b['x']
                dy = a['y'] - b['y']
                dist = math.hypot(dx, dy)
                if dist < 85:
                    edges.append((a, b))
        self.neural_nodes = nodes
        self.neural_edges = edges

    def _update_neural_network(self):
        # Determine base activation according to state
        if self.speaking:
            core_intensity = 0.9
            state_color = (255, 0, 200)    # magenta
        elif self._friday_state == "THINKING":
            core_intensity = 0.85
            state_color = (255, 200, 0)    # yellow
        elif self.focus_mode:
            core_intensity = 0.7
            state_color = (0, 255, 150)    # green
        elif self.muted:
            core_intensity = 0.2
            state_color = (180, 50, 50)    # dim red
        else:
            core_intensity = 0.4
            state_color = (0, 200, 255)    # listening cyan

        # Influence from orb centre
        for node in self.neural_nodes:
            dx = node['x'] - self.FCX
            dy = node['y'] - self.FCY
            dist = math.hypot(dx, dy)
            influence = max(0, 1 - dist / 250) * core_intensity
            node['target'] = influence
            node['activation'] = node['activation'] * 0.92 + node['target'] * 0.08

        self.neural_state_color = state_color

    def _draw_neural_network(self):
        if not self.neural_edges:
            return
        c = self.bg
        cols = self.neural_state_color
        # Draw all connections
        for n1, n2 in self.neural_edges:
            act = (n1['activation'] + n2['activation']) / 2
            if act < 0.02:
                continue
            width = max(1, int(act * 6))
            alpha = int(act * 200)
            r = int(cols[0] * act)
            g = int(cols[1] * act)
            b = int(cols[2] * act)
            color = self._ac(r, g, b, alpha)
            c.create_line(n1['x'], n1['y'], n2['x'], n2['y'],
                          fill=color, width=width, tags="neural")
        # Draw nodes as glowing circles
        for node in self.neural_nodes:
            act = node['activation']
            if act < 0.05:
                continue
            rad = max(2, int(act * 8))
            alpha = int(act * 220)
            r = int(cols[0] * act)
            g = int(cols[1] * act)
            b = int(cols[2] * act)
            col = self._ac(r, g, b, alpha)
            c.create_oval(node['x']-rad, node['y']-rad,
                          node['x']+rad, node['y']+rad,
                          fill=col, outline="", tags="neural")

    # ---------- Public API ----------
    def toggle_mute(self):
        self._toggle_mute()

    def set_state(self, state: str):
        self._friday_state = state
        lut = {
            "MUTED":      ("MUTED",      False),
            "SPEAKING":   ("SPEAKING",   True),
            "THINKING":   ("THINKING",   False),
            "LISTENING":  ("LISTENING",  False),
            "PROCESSING": ("PROCESSING", False),
        }
        txt, spk = lut.get(state, ("ONLINE", False))
        self.status_text = txt
        self.speaking    = spk

    def write_log(self, text: str):
        self.typing_queue.append(text)
        tl = text.lower()
        if tl.startswith("you:"):
            self.set_state("PROCESSING")
        elif tl.startswith("friday:") or tl.startswith("ai:"):
            self.set_state("SPEAKING")
        if not self.is_typing:
            self._start_typing()

    def start_speaking(self):
        self.set_state("SPEAKING")
    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")

    def wait_for_api_key(self):
        while not self._api_key_ready:
            time.sleep(0.1)

    # ---------- Toast ----------
    def show_toast(self, message, duration=2.5):
        if self.toast_timer:
            self.root.after_cancel(self.toast_timer)
            if self.toast_canvas:
                self.toast_canvas.destroy()
        self.toast_canvas = tk.Canvas(self.root, width=300, height=40,
                                      bg="#000000", highlightthickness=0)
        self.toast_canvas.create_rectangle(0,0,300,40, fill="#000000", outline=C_PURP2)
        self.toast_canvas.create_text(150,20, text=message, fill=C_PRI,
                                      font=("Courier",9,"bold"))
        self.toast_canvas.place(x=self.W//2-150, y=self.H-100)
        self.toast_timer = self.root.after(int(duration*1000),
                                           lambda: self.toast_canvas.destroy() if self.toast_canvas else None)

    # ---------- Voice amplitude ----------
    def feed_amplitude(self, amplitude):
        self.amplitude_queue.put(amplitude)

    def _check_amplitude(self):
        amps = []
        while not self.amplitude_queue.empty():
            amps.append(self.amplitude_queue.get())
        if amps:
            avg = sum(amps) / len(amps)
            self._draw_waveform(avg)
        self.root.after(50, self._check_amplitude)

    def _draw_waveform(self, amplitude):
        c = self.waveform_canvas
        c.delete("wave")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10:
            return
        bars = 20
        bar_w = w / bars
        max_h = h * 0.8
        norm = min(1.0, amplitude / 2000.0)
        height = max_h * norm
        for i in range(bars):
            x = i * bar_w
            bar_h = height * random.uniform(0.7, 1.2)
            c.create_rectangle(x, h-bar_h, x+bar_w-1, h, fill=C_PRI, outline="", tags="wave")

    # ---------- Graphics helpers ----------
    @staticmethod
    def _ac(r, g, b, a):
        a = max(0, min(255, int(a)))
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))
        f = a / 255.0
        return f"#{int(r*f):02x}{int(g*f):02x}{int(b*f):02x}"

    def _ring_color(self, mode, alpha, bright=1.0):
        a = max(0, min(255, int(alpha * bright)))
        if self.muted:
            return self._ac(255, 30, 30, a)
        if mode == 0: return self._ac(0, 240, 255, a)
        if mode == 1: return self._ac(0, 120, 255, a)
        if mode == 2: return self._ac(0, 255, 160, a)
        return self._ac(220, 248, 255, a)

    # ---------- CPU Graph ----------
    def _update_cpu_graph(self):
        c = self.graph_canvas
        c.delete("graph")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10 or len(self._cpu_history) < 2:
            return
        step = w / (len(self._cpu_history)-1)
        points = []
        for i, val in enumerate(self._cpu_history):
            x = i * step
            y = h - (val / 100) * h
            points.append((x, y))
        for i in range(len(points)-1):
            c.create_line(points[i][0], points[i][1], points[i+1][0], points[i+1][1],
                          fill=C_PRI, width=2, tags="graph")
        c.create_polygon([(0, h)] + points + [(w, h)], fill=self._ac(0,200,255,40),
                         outline="", tags="graph")

    def _update_metrics(self):
        # Only update CPU load and graph – no metric bars
        self._cpu_load = max(5, min(95, self._cpu_load + random.uniform(-2, 2)))
        self._cpu_history.append(self._cpu_load)
        self._mem_used = max(1.0, min(8.0, self._mem_used + random.uniform(-0.04, 0.04)))
        self._net_ping = max(8, min(200, self._net_ping + random.randint(-3, 3)))
        self._update_cpu_graph()
        self.root.after(800, self._update_metrics)

    # ---------- Button panel with hover effects ----------
    def _build_button_panel(self):
        btn_w = 85
        btn_h = 30
        gap = 5
        panel_w = btn_w * 4 + gap * 3
        x0 = int((self.ORB_ZONE_W - panel_w) / 2)
        y0 = self.H - 80
        self._btn_w = btn_w
        self._btn_h = btn_h
        self._btn_gap = gap

        # Focus button
        self._focus_canvas = tk.Canvas(self.root, width=btn_w, height=btn_h,
                                       bg=C_BG, highlightthickness=0, cursor="hand2")
        self._focus_canvas.place(x=x0, y=y0)
        self._focus_canvas.bind("<Button-1>", lambda e: self._toggle_focus_mode())
        self._focus_canvas.bind("<Enter>", lambda e: self._draw_button_box(self._focus_canvas, C_GREEN, "#003300", "FOCUS", C_GREEN, hover=True))
        self._focus_canvas.bind("<Leave>", lambda e: self._draw_focus_button())
        self._draw_focus_button()

        # Mute button
        self._mute_canvas = tk.Canvas(self.root, width=btn_w, height=btn_h,
                                      bg=C_BG, highlightthickness=0, cursor="hand2")
        self._mute_canvas.place(x=x0 + btn_w + gap, y=y0)
        self._mute_canvas.bind("<Button-1>", lambda e: self._toggle_mute())
        self._mute_canvas.bind("<Enter>", lambda e: self._draw_button_box(self._mute_canvas, C_MAG, "#200030", "MIC", C_MAG, hover=True))
        self._mute_canvas.bind("<Leave>", lambda e: self._draw_mute_button())
        self._draw_mute_button()

        # Think button
        self._think_canvas = tk.Canvas(self.root, width=btn_w, height=btn_h,
                                       bg=C_BG, highlightthickness=0, cursor="hand2")
        self._think_canvas.place(x=x0 + (btn_w+gap)*2, y=y0)
        self._think_canvas.bind("<Button-1>", lambda e: self._toggle_think_mode())
        self._think_canvas.bind("<Enter>", lambda e: self._draw_button_box(self._think_canvas, C_YELLOW, "#303000", "THINK", C_YELLOW, hover=True))
        self._think_canvas.bind("<Leave>", lambda e: self._draw_think_button())
        self._draw_think_button()

        # Deep Dive button
        self._deep_dive_active = False
        self._deep_dive_canvas = tk.Canvas(self.root, width=btn_w, height=btn_h,
                                           bg=C_BG, highlightthickness=0, cursor="hand2")
        self._deep_dive_canvas.place(x=x0 + (btn_w+gap)*3, y=y0)
        self._deep_dive_canvas.bind("<Button-1>", lambda e: self._toggle_deep_dive())
        self._deep_dive_canvas.bind("<Enter>", lambda e: self._draw_button_box(self._deep_dive_canvas, C_PURP, "#200030", "DIVE", C_PURP, hover=True))
        self._deep_dive_canvas.bind("<Leave>", lambda e: self._draw_deep_dive_button())
        self._draw_deep_dive_button()

    def _draw_button_box(self, c, border, fill, label, fg, hover=False):
        c.delete("all")
        bw, bh = self._btn_w, self._btn_h
        width = 2 if hover else 1
        c.create_rectangle(0, 0, bw, bh, outline=border, fill=fill, width=width)
        for bx, by, dx, dy in [(0,0,8,0),(0,0,0,8),(bw-8,0,bw,0),(bw,0,bw,8),
                               (0,bh-8,0,bh),(0,bh,8,bh),(bw-8,bh,bw,bh),(bw,bh-8,bw,bh)]:
            c.create_line(bx, by, dx, dy, fill=border, width=1)
        c.create_text(bw//2, bh//2, text=label, fill=fg, font=("Courier",9,"bold"))

    def _draw_mute_button(self):
        if self.muted:
            self._draw_button_box(self._mute_canvas, C_RED, "#1a0010", "⊘ MUTE", C_RED)
        else:
            self._draw_button_box(self._mute_canvas, C_MAG, "#100020", "◉ MIC", C_MAG)

    def _draw_focus_button(self):
        if self.focus_mode:
            self._draw_button_box(self._focus_canvas, C_GREEN, "#001a00", "◉ FOCUS", C_GREEN)
        else:
            self._draw_button_box(self._focus_canvas, C_SILVER2, "#000c14", "○ FOCUS", C_SILVER2)

    def _draw_think_button(self):
        if self._think_mode:
            self._draw_button_box(self._think_canvas, C_YELLOW, "#1a1a00", "◆ THINK", C_YELLOW)
        else:
            self._draw_button_box(self._think_canvas, C_SILVER2, "#000c14", "◇ THINK", C_SILVER2)

    def _toggle_mute(self):
        self.muted = not self.muted
        self._draw_mute_button()
        self._play_button_sound(600 if self.muted else 900)
        if self.muted:
            self.set_state("MUTED")
            self.write_log("SYS: Microphone muted.")
            self.show_toast("MICROPHONE MUTED", 1.5)
        else:
            self.set_state("LISTENING")
            self.write_log("SYS: Microphone active.")
            self.show_toast("MICROPHONE ACTIVE", 1.5)

    def _toggle_focus_mode(self):
        self.focus_mode = not self.focus_mode
        self._draw_focus_button()
        self._play_button_sound(700 if self.focus_mode else 500)
        if self.on_focus_mode_toggle:
            self.on_focus_mode_toggle(self.focus_mode)
        if self.focus_mode:
            self.write_log("SYS: Focus Mode activated.")
            self.show_toast("FOCUS MODE ON", 1.5)
        else:
            self.write_log("SYS: Focus Mode deactivated.")
            self.show_toast("FOCUS MODE OFF", 1.5)

    def _toggle_deep_dive(self):
        self._deep_dive_active = not self._deep_dive_active
        self._draw_deep_dive_button()
        self._play_button_sound(750)
        if self.on_deep_dive_toggle:
            self.on_deep_dive_toggle(self._deep_dive_active)
        if self._deep_dive_active:
            self.write_log("SYS: Deep Dive mode activated.")
            self.show_toast("DEEP DIVE ON", 1.5)
        else:
            self.write_log("SYS: Deep Dive mode deactivated.")
            self.show_toast("DEEP DIVE OFF", 1.5)

    def _draw_deep_dive_button(self):
        if self._deep_dive_active:
            self._draw_button_box(self._deep_dive_canvas, C_PURP, "#200030", "DIVE", C_PURP)
        else:
            self._draw_button_box(self._deep_dive_canvas, C_SILVER2, "#000c14", "DIVE", C_SILVER2)

    def _toggle_think_mode(self):
        self._think_mode = not self._think_mode
        self._draw_think_button()
        self._play_button_sound(800 if self._think_mode else 400)
        if self.on_think_mode_toggle:
            self.on_think_mode_toggle(self._think_mode)
        if self._think_mode:
            self.write_log("SYS: Think Mode activated.")
            self.show_toast("THINK MODE ON", 1.5)
        else:
            self.write_log("SYS: Think Mode deactivated.")
            self.show_toast("THINK MODE OFF", 1.5)

    def _play_button_sound(self, freq=600):
        try:
            import winsound
            winsound.Beep(freq, 120)
        except:
            pass

    def _build_input_bar(self, lw, x0, y):
        BTN_W = 90
        INP_W = lw - BTN_W - 6
        self._input_var = tk.StringVar()
        self._input_entry = tk.Entry(self.root, textvariable=self._input_var,
                                     fg=C_TEXT, bg="#000000", insertbackground=C_MAG,
                                     borderwidth=0, font=("Courier",10),
                                     highlightthickness=1, highlightbackground=C_PURP2,
                                     highlightcolor=C_MAG)
        self._input_entry.place(x=x0, y=y, width=INP_W, height=30)
        self._input_entry.bind("<Return>", self._on_input_submit)

        self._send_btn = tk.Button(self.root, text="▶ EXEC", command=self._on_input_submit,
                                   fg=C_BG, bg=C_MAG, activeforeground=C_BG,
                                   activebackground=C_PRI, font=("Courier",9,"bold"),
                                   borderwidth=0, cursor="hand2")
        self._send_btn.place(x=x0+INP_W+6, y=y, width=BTN_W, height=30)

    def _on_input_submit(self, event=None):
        text = self._input_var.get().strip()
        if not text:
            return
        self._input_var.set("")
        self.write_log(f"You: {text}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(text,), daemon=True).start()

    def _scroll_code(self):
        self._code_offset = (self._code_offset + 1) % len(CODE_LINES)
        self.root.after(500, self._scroll_code)

    def _load_face(self, path):
        FW = self.FACE_SZ
        try:
            img = Image.open(path).convert("RGBA").resize((FW, FW), Image.LANCZOS)
            mask = Image.new("L", (FW, FW), 0)
            ImageDraw.Draw(mask).ellipse((2, 2, FW-2, FW-2), fill=255)
            img.putalpha(mask)
            self._face_pil = img
            self._has_face = True
        except:
            self._has_face = False

    def _build_bottom_bar(self):
        BAR_H = 36
        BAR_Y = self.H - BAR_H
        self._bottom = tk.Canvas(self.root, width=self.W, height=BAR_H,
                                 bg="#000000", highlightthickness=0)
        self._bottom.place(x=0, y=BAR_Y)
        self._bottom.create_line(0, 0, self.W, 0, fill=C_PURP2, width=1)
        items = [
            ("◈ KAIRO v9.1", C_PURP),
            (self._get_provider_badge(), C_SILVER2),
            ("[F4] MUTE", C_SILVER2),
            (f"DEV: {DEVELOPER}  ·  {STUDIO}", C_SILVER2),
        ]
        spacing = self.W // (len(items) + 1)
        for i, (label, col) in enumerate(items):
            self._bottom.create_text((i+1)*spacing, BAR_H//2, text=label, fill=col, font=("Courier",8))

    def _get_provider_badge(self) -> str:
        try:
            from brain.model_router import get_model_router
            router = get_model_router()
            return router.get_provider_display_name()
        except Exception:
            return "GEMINI 2.5 FLASH"

    # ---------- Large animation and drawing ----------
    def _animate(self):
        self.tick += 1
        now = time.time()

        if now - self.last_t > (0.12 if self.speaking else 0.5):
            if self.speaking:
                self.target_scale = random.uniform(1.04, 1.10)
                self.target_halo  = random.uniform(140, 190)
            elif self.muted:
                self.target_scale = random.uniform(0.998, 1.001)
                self.target_halo  = random.uniform(18, 30)
            else:
                self.target_scale = random.uniform(1.001, 1.006)
                self.target_halo  = random.uniform(52, 72)
            self.last_t = now

        sp = 0.35 if self.speaking else 0.16
        if self.focus_mode:
            sp = 0.45 if self.speaking else 0.28
        self.scale  += (self.target_scale - self.scale) * sp
        self.halo_a += (self.target_halo  - self.halo_a) * sp

        spd = 1.8 if self.speaking else 0.85
        if self.focus_mode:
            spd *= 1.3
        self.scan_angle  = (self.scan_angle  + spd * 1.6) % 360
        self.scan2_angle = (self.scan2_angle - spd * 1.0) % 360
        self.scan3_angle = (self.scan3_angle + spd * 2.2) % 360

        pspd = 4.0 if self.speaking else 1.9
        if self.focus_mode:
            pspd *= 1.4
        limit = self.FACE_SZ * 0.74
        new_p = [r + pspd for r in self.pulse_r if r + pspd < limit]
        if len(new_p) < 3 and random.random() < (0.07 if self.speaking else 0.025):
            new_p.append(0.0)
        self.pulse_r = new_p

        if self.tick % 38 == 0:
            self.status_blink = not self.status_blink

        ring_spd_factor = 1.0 if (self.speaking or self.focus_mode) else 0.5
        self._rings = [(rf, sp2, al, g, w, cm, (ph + sp2 * spd * ring_spd_factor) % 360) for rf, sp2, al, g, w, cm, ph in self._rings]
        self._inner_spin = [(a + (2.8 * ring_spd_factor)) % 360 for a in self._inner_spin]
        self._data_arcs = [((a + (1.6 * ring_spd_factor)) % 360, v, cm) for a, v, cm in self._data_arcs]
        self._energy_dots = [((a + random.uniform(0.2, 0.9) * ring_spd_factor) % 360, r, s, cm) for a, r, s, cm in self._energy_dots]

        self._hex_ring = [(a + (0.8 if self.speaking else 0.35)) % 360 for a in self._hex_ring]
        self._diamond_spin = (self._diamond_spin + (1.5 if self.speaking else 0.6)) % 360
        self._bg_spin = (self._bg_spin + 0.15) % 360
        self._tri_spin = [(a + (2.2 if self.speaking else 0.9)) % 360 for a in self._tri_spin]

        self._glitch_timer += 1
        if self._glitch_timer > random.randint(120, 300):
            self._glitch_active = True
            self._glitch_text = "".join(random.choice(GLITCH_CHARS) for _ in range(8))
            self._glitch_timer = 0
        elif self._glitch_active and self._glitch_timer > 6:
            self._glitch_active = False

        # Update neural network activation
        self._update_neural_network()

        # Draw (with exception handling for window close)
        try:
            self._draw()
        except tk.TclError:
            return
        self.root.after(16, self._animate)

    def _draw(self):
        c = self.bg
        if not c.winfo_exists():
            return

        W, H = self.W, self.H
        t = self.tick
        FCX = self.FCX
        FCY = self.FCY
        FW = self.FACE_SZ
        OZW = self.ORB_ZONE_W
        DZX = self.DATA_ZONE_X
        c.delete("all")

        # ----- NEURAL BACKGROUND (drawn first) -----
        self._draw_neural_network()

        # Deep space background
        c.create_rectangle(0, 0, W, H, fill=C_BG, outline="")

        # Glow colors for particles
        glow_colors = [
            lambda a: self._ac(0, 240, 255, a),
            lambda a: self._ac(0, 120, 255, a),
            lambda a: self._ac(0, 255, 160, a),
            lambda a: self._ac(220, 248, 255, a),
        ]

        speaking_boost = 1.0 if self.speaking else 0.0
        bg_spin_r = math.radians(self._bg_spin)

        # Background particles (enhanced)
        for i, (px, py, sz, cm, phase) in enumerate(self._bg_particles):
            pulse = abs(math.sin(t * 0.03 + phase + i * 0.3))
            a = int(25 + 75 * pulse * (1 + speaking_boost * 0.6))
            col = glow_colors[cm % len(glow_colors)](a)
            c.create_oval(px - sz, py - sz, px + sz, py + sz, fill=col, outline='')
            a2 = max(5, int(a * 0.4))
            col2 = glow_colors[cm % len(glow_colors)](a2)
            c.create_oval(px - sz * 2.5, py - sz * 2.5, px + sz * 2.5, py + sz * 2.5, outline=col2, width=1)

        # Extra floating orbs (new)
        for i in range(30):
            off = t * 0.02
            x = 100 + 300 * math.sin(off + i)
            y = 200 + 150 * math.cos(off * 1.3 + i*2)
            sz = 3 + math.sin(off*3 + i)*2
            col = self._ac(0, 200, 255, 80)
            c.create_oval(x-sz, y-sz, x+sz, y+sz, fill=col, outline="")

        # Drifting hex grid (more, with state-based color)
        grid_off = (t * 0.15) % 80
        hex_col = self._ac(100, 150, 255, 60 + 40 * math.sin(t*0.05))
        for x in range(-20, OZW + 20, 44):
            for y in range(-20, H + 20, 44):
                off_x = x + grid_off
                off_y = y + grid_off * 0.5
                if 0 < off_x < OZW and 0 < off_y < H:
                    pts = hex_points(off_x, off_y, 14, rotation=t * 0.06)
                    c.create_polygon(pts, outline=hex_col, fill="", width=1)

        # Scrolling code lines (unchanged)
        code_cols = [DZX + 20, DZX + self.DATA_ZONE_W // 2]
        for col_x in code_cols:
            for row in range(15):
                idx = (self._code_offset + row + int(col_x)) % len(CODE_LINES)
                cy2 = 60 + 30 + row * 26
                alpha = max(20, 80 - row * 5)
                tc = self._ac(80, 150, 250, alpha)
                c.create_text(col_x, cy2, text=CODE_LINES[idx][:28],
                              fill=tc, font=("Courier", 7, "bold"), anchor="w")

        # Header (unchanged)
        HDR = 60
        c.create_rectangle(0, 0, W, HDR, fill="#000000", outline="")
        c.create_line(0, HDR, W, HDR, fill=C_PURP2, width=1)
        glow_h = int(180 + 100 * math.sin(t * 0.05))
        for i, col in enumerate([self._ac(255, 0, 200, int(glow_h * 0.3)),
                                 self._ac(255, 0, 200, int(glow_h * 0.6)),
                                 self._ac(255, 0, 200, glow_h)]):
            c.create_line(0, i, W, i, fill=col, width=1)

        dash_off = (t * 4) % 80
        for dx in range(int(dash_off), W, 80):
            c.create_line(dx, 3, dx + 40, 3, fill=self._ac(0, 200, 255, 100), width=1)

        title_col = C_RED if self.muted else C_PRI
        c.create_text(OZW // 2, 20, text=SYSTEM_NAME,
                      fill=title_col, font=("Courier", 26, "bold"))
        if self._glitch_active:
            c.create_text(OZW // 2 + random.randint(-4, 4), 20,
                          text=self._glitch_text[:6],
                          fill=self._ac(255, 0, 200, 190), font=("Courier", 26, "bold"))

        c.create_text(OZW // 2, 46,
                      text="≠ AI‑powered · AI‑possessed",
                      fill=C_PURP, font=("Courier", 9))

        c.create_text(DZX + 16, 20, text=f"◈ {MODEL_BADGE}",
                      fill=C_MAG, font=("Courier", 15, "bold"), anchor="w")
        c.create_text(DZX + 16, 40, text="NEURAL INFERENCE ENGINE",
                      fill=C_SILVER2, font=("Courier", 9), anchor="w")
        c.create_text(W - 16, 20, text=time.strftime("%H:%M:%S"),
                      fill=C_PRI, font=("Courier", 22, "bold"), anchor="e")
        c.create_text(W - 16, 44, text=time.strftime("%d · %b · %Y"),
                      fill=C_SILVER2, font=("Courier", 9), anchor="e")

        # System info (unchanged)
        INFO_Y = HDR + 12
        info_items = [
            ("CPU", f"{self._cpu_load:.1f}%"),
            ("MEM", f"{self._mem_used:.1f}GB"),
            ("PING", f"{self._net_ping}ms"),
            ("OS", platform.system().upper()),
            ("VER", "9.1.0"),
        ]
        ix = DZX + 20
        for label, val in info_items:
            c.create_text(ix, INFO_Y + 4, text=label, fill=C_SILVER2, font=("Courier", 8), anchor="w")
            c.create_text(ix, INFO_Y + 16, text=val, fill=C_SILVER, font=("Courier", 9, "bold"), anchor="w")
            ix += (self.DATA_ZONE_W - 40) // len(info_items)

        # ----- ORB ZONE (unchanged from original, but we have removed metric bars) -----
        # Outer hex frame
        for hr, lw2 in [(FW * 0.76, 1), (FW * 0.73, 1)]:
            pts = hex_points(FCX, FCY, int(hr), rotation=self._hex_ring[0] * 0.07)
            c.create_polygon(pts, outline=C_SILVER2, fill="", width=lw2)

        # Atmospheric radiance
        atm_r = int(FW * 0.74)
        for i in range(32, 0, -1):
            r2 = int(atm_r * i / 32)
            frac = (i / 32) ** 2
            ga = max(0, min(255, int(self.halo_a * 0.08 * frac)))
            if self.muted:
                col = self._ac(255, 40, 50, ga)
            else:
                if i % 3 == 0: col = self._ac(0, 200, 255, ga)
                elif i % 3 == 1: col = self._ac(130, 0, 255, ga)
                else: col = self._ac(0, 160, 255, ga)
            c.create_oval(FCX - r2, FCY - r2, FCX + r2, FCY + r2, fill=col, outline="")

        # All rings
        for r_frac, spd2, arc_l, gap, w_ring, cm, phase in self._rings:
            ring_r = int(FW * r_frac)
            tilt = 0.045 * math.sin(math.radians(phase * 0.85))
            rx = ring_r
            ry = ring_r * (1 - abs(tilt))
            offy = ring_r * tilt * 0.5
            dyn_w = max(1, int(w_ring * (1 + 0.65 * abs(tilt))))
            a_base = max(0, min(255, int(self.halo_a * 1.3)))
            step = arc_l + gap
            for s in range(360 // max(1, step) + 1):
                start = (phase + s * step) % 360
                col = self._ring_color(cm, a_base)
                c.create_arc(FCX - rx, FCY - ry + offy,
                             FCX + rx, FCY + ry + offy,
                             start=start, extent=arc_l,
                             outline=col, width=dyn_w, style="arc")
            for s in range(360 // max(1, step) + 1):
                start = (phase + s * step + arc_l) % 360
                col = self._ring_color(cm, int(a_base * 0.12))
                c.create_arc(FCX - rx, FCY - ry + offy,
                             FCX + rx, FCY + ry + offy,
                             start=start, extent=gap,
                             outline=col, width=1, style="arc")

        # Energy dots
        for angle, r_frac, dot_sz, cm in self._energy_dots:
            ring_r = int(FW * r_frac)
            rad = math.radians(angle)
            dx = FCX + ring_r * math.cos(rad)
            dy = FCY - ring_r * math.sin(rad)
            a_val = max(0, min(255, int(self.halo_a * 2.4)))
            col = self._ring_color(cm, a_val, 1.4)
            sr = dot_sz * (0.7 + 0.3 * math.sin(t * 0.12 + angle))
            c.create_oval(dx - sr, dy - sr, dx + sr, dy + sr, fill=col, outline="")

        # Data arcs
        data_r = int(FW * 0.59)
        for angle, intensity, cm in self._data_arcs:
            a_val = max(0, min(255, int(self.halo_a * 2.0 * intensity)))
            col = self._ring_color(cm, a_val)
            c.create_arc(FCX - data_r, FCY - data_r, FCX + data_r, FCY + data_r,
                         start=angle, extent=25, outline=col, width=7, style="arc")

        # Triple scanner
        for sr_frac, sang, ext, w_s, am, cm in [
                (0.57, self.scan_angle, 1.3, 4, 1.6, 0),
                (0.53, self.scan2_angle, 0.9, 2, 1.1, 1),
                (0.61, self.scan3_angle, 0.7, 1, 0.7, 2)]:
            sr = int(FW * sr_frac)
            arc_e = int((85 if self.speaking else 55) * ext)
            a_val = min(255, int(self.halo_a * am))
            col = self._ring_color(cm, a_val)
            c.create_arc(FCX - sr, FCY - sr, FCX + sr, FCY + sr,
                         start=sang, extent=arc_e, outline=col, width=w_s, style="arc")

        # Tick marks
        t_out = int(FW * 0.57)
        t_in = int(FW * 0.54)
        for deg in range(0, 360, 4):
            rad = math.radians(deg)
            inn = t_in if deg % 20 == 0 else t_in + 2
            ww = 2 if deg % 20 == 0 else 1
            if deg % 20 == 0:
                col = self._ac(0, 220, 255, 220) if not self.muted else self._ac(255, 40, 50, 220)
            elif deg % 10 == 0:
                col = self._ac(128, 0, 255, 160) if not self.muted else self._ac(255, 40, 50, 120)
            else:
                col = self._ac(100, 100, 200, 90)
            c.create_line(FCX + t_out * math.cos(rad), FCY - t_out * math.sin(rad),
                          FCX + inn * math.cos(rad), FCY - inn * math.sin(rad),
                          fill=col, width=ww)

        # Rotating diamonds
        diam_r = int(FW * 0.60)
        da = math.radians(self._diamond_spin)
        for off in [0, 90, 180, 270]:
            ang = da + math.radians(off)
            dx = FCX + diam_r * math.cos(ang)
            dy = FCY - diam_r * math.sin(ang)
            dm_a = max(0, min(255, int(self.halo_a * 0.85)))
            col = self._ac(255, 100, 0, dm_a) if not self.muted else self._ac(255, 80, 80, dm_a)
            c.create_rectangle(dx - 5, dy - 5, dx + 5, dy + 5, fill=col, outline="")

        # Rotating triangles
        for i, t_ang in enumerate(self._tri_spin):
            tri_r = int(FW * [0.56, 0.51, 0.47][i])
            pts = []
            for v in range(3):
                a2 = math.radians(t_ang + v * 120)
                pts.extend([FCX + tri_r * math.cos(a2), FCY - tri_r * math.sin(a2)])
            t_a = max(0, min(255, int(self.halo_a * 0.3)))
            col = self._ring_color(i, t_a)
            c.create_polygon(pts, outline=col, fill="", width=2)

        # Crosshair
        ch_r = int(FW * 0.59)
        gap = int(FW * 0.15)
        ch_a = self._ac(0, 240, 255, int(self.halo_a * 0.7)) if not self.muted else self._ac(255, 60, 70, int(self.halo_a * 0.7))
        for x1, y1, x2, y2 in [(FCX - ch_r, FCY, FCX - gap, FCY),
                               (FCX + gap, FCY, FCX + ch_r, FCY),
                               (FCX, FCY - ch_r, FCX, FCY - gap),
                               (FCX, FCY + gap, FCX, FCY + ch_r)]:
            c.create_line(x1, y1, x2, y2, fill=ch_a, width=2)
        for nx, ny in [(FCX - ch_r, FCY), (FCX + ch_r, FCY), (FCX, FCY - ch_r), (FCX, FCY + ch_r)]:
            pts = diamond_points(nx, ny, 6, 6)
            c.create_polygon(pts, fill=ch_a, outline="")

        # Corner brackets
        blen = 32
        bc = self._ac(0, 200, 255, 250) if not self.muted else self._ac(255, 60, 60, 250)
        bc2 = self._ac(128, 0, 255, 220)
        hl, hr2 = FCX - FW // 2, FCX + FW // 2
        ht, hb = FCY - FW // 2, FCY + FW // 2
        for bx, by, sdx, sdy in [(hl, ht, 1, 1), (hr2, ht, -1, 1), (hl, hb, 1, -1), (hr2, hb, -1, -1)]:
            c.create_line(bx, by, bx + sdx * blen, by, fill=bc, width=3)
            c.create_line(bx, by, bx, by + sdy * blen, fill=bc, width=3)
            pts = diamond_points(bx, by, 6, 6)
            c.create_polygon(pts, fill=bc2, outline="")

        # Face image
        if self._has_face and self._face_pil:
            fw = int(FW * self.scale)
            if (self._face_scale_cache is None or abs(self._face_scale_cache[0] - self.scale) > 0.004):
                scaled = self._face_pil.resize((fw, fw), Image.BILINEAR)
                if self.muted:
                    r2, g2, b2, a2 = scaled.split()
                    g2 = ImageEnhance.Brightness(g2).enhance(0.2)
                    b2 = ImageEnhance.Brightness(b2).enhance(0.3)
                    scaled = Image.merge("RGBA", (r2, g2, b2, a2))
                self._face_scale_cache = (self.scale, ImageTk.PhotoImage(scaled))
            c.create_image(FCX, FCY, image=self._face_scale_cache[1])
        else:
            txt_col = C_RED if self.muted else C_PRI
            c.create_text(FCX, FCY, text=SYSTEM_NAME, fill=txt_col, font=("Courier", 15, "bold"))

        # Status row (unchanged)
        sy = FCY + FW // 2 + 30
        if self.muted:
            stat, sc = "⊘ SYSTEM MUTED", C_RED
        elif self.speaking:
            stat, sc = "◉ SPEAKING", C_MAG
        elif self._friday_state == "THINKING":
            sym = "▶▶▶" if self.status_blink else "———"
            stat, sc = f"{sym} THINKING", C_YELLOW
        elif self._friday_state == "PROCESSING":
            sym = "▶▶▶" if self.status_blink else "———"
            stat, sc = f"{sym} PROCESSING", C_PURP
        elif self._friday_state == "LISTENING":
            sym = "◉" if self.status_blink else "○"
            stat, sc = f"{sym} LISTENING", C_GREEN
        else:
            sym = "◈" if self.status_blink else "◇"
            stat, sc = f"{sym} {self.status_text}", C_PRI

        sw2 = 210
        c.create_rectangle(FCX - sw2 // 2 - 4, sy - 10, FCX + sw2 // 2 + 4, sy + 12,
                           fill="#000000", outline=C_PURP2)
        c.create_text(FCX, sy, text=stat, fill=sc, font=("Courier", 11, "bold"))

        # Waveform (visualiser)
        wy = sy + 30
        N = 52
        BH = 24
        bw = int(OZW * 0.85 / N)
        wx0 = (OZW - N * bw) // 2
        for i in range(N):
            if self.muted:
                hb = int(2 + 2 * math.sin(t * 0.04 + i * 0.25))
                col = C_RED
            elif self.speaking:
                hb = random.randint(4, BH)
                col = [C_PRI, C_MAG, C_PURP][i % 3]
            else:
                hb = int(3 + 4 * math.sin(t * 0.09 + i * 0.5))
                col = C_PURP2
            bx = wx0 + i * bw
            c.create_rectangle(bx, wy + BH - hb, bx + bw - 1, wy + BH, fill=col, outline="")

        # Left sidebar stats (unchanged)
        uptime = int(time.time() - self._start_time)
        stats_l = [
            ("UPTIME", f"{uptime // 3600:02d}:{(uptime % 3600) // 60:02d}:{uptime % 60:02d}"),
            ("STATUS", self._friday_state[:10]),
            ("NET", "ONLINE"),
            ("ENC", "AES-512"),
            ("TOOLS", "18 ACTIVE"),
            ("TG", "BRIDGED"),
        ]
        sy3 = HDR + 10
        for label, val in stats_l:
            c.create_text(8, sy3 + 4, text=label, fill=C_SILVER2, font=("Courier", 8), anchor="w")
            c.create_text(OZW - 8, sy3 + 4, text=val, fill=C_SILVER, font=("Courier", 8, "bold"), anchor="e")
            c.create_line(8, sy3 + 12, OZW - 8, sy3 + 12, fill=C_DIM, width=1)
            sy3 += 18

    # ---------- Typing, API setup (unchanged) ----------
    def _start_typing(self):
        if not self.typing_queue:
            self.is_typing = False
            if not self.speaking and not self.muted:
                self.set_state("LISTENING")
            return
        self.is_typing = True
        text = self.typing_queue.popleft()
        tl = text.lower()
        if tl.startswith("you:"):
            tag = "you"
        elif tl.startswith("friday:") or tl.startswith("ai:"):
            tag = "ai"
        elif tl.startswith("err:") or "error" in tl:
            tag = "err"
        else:
            tag = "sys"
        self.log_text.configure(state="normal")
        self._type_char(text, 0, tag)

    def _type_char(self, text, i, tag):
        if i < len(text):
            self.log_text.insert(tk.END, text[i], tag)
            self.log_text.see(tk.END)
            self.root.after(7, self._type_char, text, i+1, tag)
        else:
            self.log_text.insert(tk.END, "\n")
            self.log_text.configure(state="disabled")
            self.root.after(20, self._start_typing)

    def _api_keys_exist(self) -> bool:
        if not API_FILE.exists():
            return False
        try:
            data = json.loads(API_FILE.read_text(encoding="utf-8"))
            has_gemini = bool(data.get("gemini_api_key"))
            has_os = bool(data.get("os_system"))
            return has_gemini and has_os
        except:
            return False

    @staticmethod
    def _detect_os() -> str:
        s = platform.system().lower()
        return "mac" if s == "darwin" else "windows" if s == "windows" else "linux"

    def _show_setup_ui(self):
        detected = self._detect_os()
        self._selected_os = tk.StringVar(value=detected)

        # ── Outer container with layered border effect ──
        self.setup_frame = tk.Frame(self.root, bg="#0a0a12")
        self.setup_frame.place(relx=0.5, rely=0.5, anchor="center")

        # Inner card
        card = tk.Frame(self.setup_frame, bg="#0d0d18",
                        highlightbackground="#2a1a4e", highlightthickness=2)
        card.pack(padx=3, pady=3)

        # ── Header area ──
        header = tk.Frame(card, bg="#0d0d18")
        header.pack(fill="x", padx=32, pady=(28, 0))

        tk.Label(header, text="F R I D A Y", fg="#8a6dff", bg="#0d0d18",
                 font=("Consolas", 22, "bold")).pack()
        tk.Label(header, text="Autonomous Cognitive AI", fg="#4a4a6a", bg="#0d0d18",
                 font=("Consolas", 10)).pack(pady=(2, 0))
        tk.Label(header, text="v10.7  •  FIRST BOOT SETUP", fg="#2a2a4a", bg="#0d0d18",
                 font=("Consolas", 8)).pack(pady=(4, 0))

        # Accent line
        tk.Frame(card, bg="#8a6dff", height=2).pack(fill="x", padx=32, pady=(20, 24))

        # ── API Key field ──
        field_frame = tk.Frame(card, bg="#0d0d18")
        field_frame.pack(fill="x", padx=32)

        tk.Label(field_frame, text="GEMINI  API  KEY", fg="#6a6a8a", bg="#0d0d18",
                 font=("Consolas", 9, "bold"), anchor="w").pack(fill="x")
        self.gemini_entry = tk.Entry(field_frame, width=48, fg="#c0c0e0", bg="#08080f",
                                     insertbackground="#8a6dff", borderwidth=0,
                                     font=("Consolas", 11), show="•",
                                     highlightthickness=1, highlightbackground="#1a1a2e",
                                     highlightcolor="#8a6dff")
        self.gemini_entry.pack(fill="x", pady=(6, 0))

        # ── Name field ──
        name_frame = tk.Frame(card, bg="#0d0d18")
        name_frame.pack(fill="x", padx=32, pady=(18, 0))

        tk.Label(name_frame, text="CALLSIGN", fg="#6a6a8a", bg="#0d0d18",
                 font=("Consolas", 9, "bold"), anchor="w").pack(fill="x")
        self.name_entry = tk.Entry(name_frame, width=48, fg="#c0c0e0", bg="#08080f",
                                   insertbackground="#8a6dff", borderwidth=0,
                                   font=("Consolas", 11),
                                   highlightthickness=1, highlightbackground="#1a1a2e",
                                   highlightcolor="#8a6dff")
        self.name_entry.insert(0, "OPERATOR")
        self.name_entry.pack(fill="x", pady=(6, 0))

        # ── OS Selection ──
        os_frame = tk.Frame(card, bg="#0d0d18")
        os_frame.pack(fill="x", padx=32, pady=(24, 0))

        detect_label = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}.get(detected, detected)
        tk.Label(os_frame, text=f"SYSTEM  •  AUTO-DETECTED: {detect_label.upper()}",
                 fg="#4a4a6a", bg="#0d0d18",
                 font=("Consolas", 8, "bold"), anchor="w").pack(fill="x", pady=(0, 8))

        os_btn_frame = tk.Frame(os_frame, bg="#0d0d18")
        os_btn_frame.pack(fill="x")
        self._os_buttons = {}
        for os_key, os_label in [("windows", "WINDOWS"), ("mac", "macOS"), ("linux", "LINUX")]:
            btn = tk.Button(os_btn_frame, text=os_label, width=14,
                            font=("Consolas", 9, "bold"), borderwidth=0,
                            cursor="hand2", pady=6,
                            activebackground="#1a1a2e", activeforeground="#8a6dff",
                            command=lambda k=os_key: self._select_os(k))
            btn.pack(side="left", padx=(0, 6), fill="x", expand=True)
            self._os_buttons[os_key] = btn
        self._select_os(detected)

        # ── Activate button ──
        tk.Frame(card, bg="#8a6dff", height=1).pack(fill="x", padx=32, pady=(28, 20))

        btn_frame = tk.Frame(card, bg="#0d0d18")
        btn_frame.pack(fill="x", padx=32, pady=(0, 28))

        activate_btn = tk.Button(btn_frame, text="▶  ACTIVATE  FRIDAY",
                                 command=self._save_api_keys,
                                 bg="#8a6dff", fg="#ffffff",
                                 activebackground="#6a4ddf",
                                 activeforeground="#ffffff",
                                 font=("Consolas", 12, "bold"),
                                 borderwidth=0, pady=11, cursor="hand2")
        activate_btn.pack(fill="x")

    def _select_os(self, os_key: str):
        self._selected_os.set(os_key)
        for key, btn in self._os_buttons.items():
            if key == os_key:
                btn.configure(fg="#ffffff", bg="#8a6dff")
            else:
                btn.configure(fg="#4a4a6a", bg="#12121e")

    def _save_api_keys(self):
        gemini = self.gemini_entry.get().strip()

        if not gemini:
            self.gemini_entry.configure(highlightbackground=C_RED, highlightcolor=C_RED)
            return

        os_system = self._selected_os.get()
        user_name = getattr(self, 'name_entry', None)
        user_name = user_name.get().strip().upper() if user_name else "OPERATOR"
        if not user_name:
            user_name = "OPERATOR"
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(API_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "gemini_api_key": gemini,
                "openai_api_key": "",
                "primary_provider": "gemini",
                "os_system": os_system,
                "camera_index": 0,
                "user_name": user_name
            }, f, indent=4)
        global YOUR_NAME
        YOUR_NAME = user_name

        from brain import model_router as mr_module
        mr_module._router_instance = None

        self.setup_frame.destroy()
        self._api_key_ready = True
        self.set_state("LISTENING")
        self.write_log(f"SYS: KAIRO online. Provider: GEMINI 2.5 FLASH. OS: {os_system.upper()}. Welcome, {user_name}.🎉")


