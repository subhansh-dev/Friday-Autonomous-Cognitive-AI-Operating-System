from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import PIL.Image
    import PIL.ImageResampling
    _PIL = True
except ImportError:
    try:
        import PIL.Image
        _PIL = True
    except ImportError:
        _PIL = False

from google import genai
from google.genai import types as gtypes


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE        = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"

# [FIX-5] Cached config
_config_cache: dict | None = None


def _load_config() -> dict:
    global _config_cache
    if _config_cache is None:
        try:
            _config_cache = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            _config_cache = {}
    return _config_cache


def _save_config_key(key: str, value) -> None:
    global _config_cache
    try:
        cfg = _load_config()
        cfg[key] = value
        _config_cache = cfg
        _CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"[Vision] ⚠️  Could not save config key '{key}': {e}")


def _get_api_key() -> str:
    key = _load_config().get("gemini_api_key", "")
    if not key:
        raise RuntimeError("gemini_api_key not found in config.")
    return key


# [FIX-5] Cached OS detection
_os_cache: str | None = None


def _get_os() -> str:
    global _os_cache
    if _os_cache is not None:
        return _os_cache
    import platform
    system = platform.system().lower()
    _os_cache = {"darwin": "mac", "windows": "windows", "linux": "linux"}.get(system, "windows")
    return _os_cache


_LIVE_MODEL         = "models/gemini-2.5-flash-native-audio-preview-12-2025"
_CHANNELS           = 1
_RECEIVE_SAMPLE_RATE = 24_000
_CHUNK_SIZE         = 1_024

_IMG_MAX_W = 640
_IMG_MAX_H = 360
_JPEG_Q    = 60

_SYSTEM_PROMPT = (
    "You are FRIDAY, an advanced AI assistant. "
    "Analyze the provided image with precision and intelligence. "
    "Be concise and direct — maximum two sentences unless the user's question "
    "requires more detail. "
    "Address the user respectfully. "
    "IMPORTANT: Only describe and analyze what you see. "
    "Never call tools or take actions — only provide visual analysis and descriptions."
)


# [FIX-6] Pillow resampling compatibility
def _get_resample():
    try:
        return PIL.Image.Resampling.BILINEAR
    except AttributeError:
        return PIL.Image.BILINEAR


def _compress(img_bytes: bytes, source_format: str = "PNG") -> tuple[bytes, str]:
    if not _PIL:
        return img_bytes, f"image/{source_format.lower()}"

    try:
        img = PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), _get_resample())
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
        return buf.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"[Vision] ⚠️  Image compress failed: {e}")
        return img_bytes, f"image/{source_format.lower()}"


def _capture_screen() -> tuple[bytes, str]:
    if not _MSS:
        raise RuntimeError("mss is not installed. Run: pip install mss")

    with mss.mss() as sct:
        monitors = sct.monitors
        # [FIX-10] Use configurable monitor index
        monitor_idx = _load_config().get("screen_monitor", 1)
        if monitor_idx >= len(monitors):
            monitor_idx = 1 if len(monitors) > 1 else 0
        target = monitors[monitor_idx]
        shot   = sct.grab(target)
        png    = mss.tools.to_png(shot.rgb, shot.size)

    return _compress(png, "PNG")


def _cv2_backend() -> int:
    if not _CV2:
        return 0
    os_name = _get_os()
    if os_name == "windows":
        return cv2.CAP_DSHOW
    if os_name == "mac":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_ANY


def _probe_camera(index: int, backend: int, warmup: int = 5) -> bool:
    if not _CV2:
        return False
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return False
    for _ in range(warmup):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return False
    return bool(np.mean(frame) > 8)


def _detect_camera_index() -> int:
    backend = _cv2_backend()
    print("[Vision] 🔍 Auto-detecting camera...")
    for idx in range(6):
        if _probe_camera(idx, backend):
            print(f"[Vision] ✅ Camera found at index {idx}")
            return idx
        print(f"[Vision] ⚠️  Camera index {idx}: no usable frame")

    print("[Vision] ⚠️  No camera found — defaulting to index 0")
    return 0


def _get_camera_index() -> int:
    cfg = _load_config()
    # [FIX-8] Only auto-detect if no config value exists
    if "camera_index" in cfg:
        idx = int(cfg["camera_index"])
        # Validate the configured index still works
        if _probe_camera(idx, _cv2_backend(), warmup=2):
            return idx
        print(f"[Vision] ⚠️  Configured camera index {idx} failed, re-detecting...")

    idx = _detect_camera_index()
    _save_config_key("camera_index", idx)
    return idx


def _capture_camera() -> tuple[bytes, str]:
    if not _CV2:
        raise RuntimeError("OpenCV (cv2) is not installed. Run: pip install opencv-python")

    index   = _get_camera_index()
    backend = _cv2_backend()
    cap     = cv2.VideoCapture(index, backend)

    if not cap.isOpened():
        raise RuntimeError(f"Camera index {index} could not be opened.")

    for _ in range(10):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError("Camera returned no frame.")

    if _PIL:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(rgb)
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), _get_resample())
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q)
        return buf.getvalue(), "image/jpeg"

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_Q])
    return buf.tobytes(), "image/jpeg"


class _VisionSession:
    def __init__(self):
        self._loop:       Optional[asyncio.AbstractEventLoop] = None
        self._thread:     Optional[threading.Thread]          = None
        self._session                                          = None
        self._out_queue:  Optional[asyncio.Queue]             = None
        self._audio_in:   Optional[asyncio.Queue]             = None
        self._ready_evt:  threading.Event                     = threading.Event()
        self._player                                           = None
        self._lock:       threading.Lock                       = threading.Lock()
        self._stopping:   bool                                 = False

    def start(self, player=None, timeout: float = 25.0) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                if player is not None:
                    self._player = player
                # Wait for existing session to be ready
                if not self._ready_evt.wait(timeout=timeout):
                    raise RuntimeError(f"Vision session not ready within {timeout}s.")
                return
            self._stopping = False
            self._player = player
            self._thread = threading.Thread(
                target=self._run_event_loop,
                daemon=True,
                name="VisionSessionThread",
            )
            self._thread.start()

        if not self._ready_evt.wait(timeout=timeout):
            raise RuntimeError(f"Vision session did not connect within {timeout}s.")
        print("[Vision] ✅ Session ready")

    # [FIX-4] Stop method for clean shutdown
    def stop(self) -> None:
        with self._lock:
            self._stopping = True
            self._ready_evt.clear()
            self._session = None
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self._loop = None
        print("[Vision] Session stopped")

    def analyze(self, image_bytes: bytes, mime_type: str, user_text: str) -> None:
        if not self._loop or not self._loop.is_running():
            print("[Vision] ⚠️  Session not started — dropping request")
            return
        if not self._ready_evt.is_set():
            print("[Vision] ⚠️  Session not ready — dropping request")
            return
        asyncio.run_coroutine_threadsafe(
            self._out_queue.put((image_bytes, mime_type, user_text)),
            self._loop,
        )

    def is_ready(self) -> bool:
        return self._session is not None and self._ready_evt.is_set()

    def _run_event_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._session_loop())
        except Exception as e:
            print(f"[Vision] ❌ Event loop terminated: {e}")
        finally:
            self._loop.close()

    async def _session_loop(self) -> None:
        self._out_queue = asyncio.Queue(maxsize=30)
        self._audio_in  = asyncio.Queue()

        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"},
        )
        config = gtypes.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            system_instruction=_SYSTEM_PROMPT,
            speech_config=gtypes.SpeechConfig(
                voice_config=gtypes.VoiceConfig(
                    prebuilt_voice_config=gtypes.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

        backoff = 2.0
        while not self._stopping:
            try:
                print("[Vision] 🔌 Connecting...")
                async with client.aio.live.connect(
                    model=_LIVE_MODEL, config=config
                ) as session:
                    self._session = session
                    self._ready_evt.set()
                    backoff = 2.0
                    print("[Vision] ✅ Connected")

                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._send_loop())
                        tg.create_task(self._recv_loop())
                        tg.create_task(self._play_loop())

            except ExceptionGroup as eg:
                for exc in eg.exceptions:
                    if not self._stopping:
                        print(f"[Vision] ⚠️  Session error: {exc}")
            except Exception as e:
                if not self._stopping:
                    print(f"[Vision] ⚠️  Session error: {e}")
            finally:
                self._session = None
                # [FIX-2] Only clear ready if we're going to reconnect
                # Don't set it again until actually connected
                if self._stopping:
                    self._ready_evt.clear()

            if self._stopping:
                break

            print(f"[Vision] 🔄 Reconnecting in {backoff:.0f}s...")
            # [FIX-2] Keep ready_evt cleared during reconnect
            self._ready_evt.clear()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 1.5, 30.0)
            # [FIX-2] Removed: self._ready_evt.set() — only set when actually connected

    async def _send_loop(self) -> None:
        while not self._stopping:
            try:
                image_bytes, mime_type, user_text = await asyncio.wait_for(
                    self._out_queue.get(), timeout=30.0
                )
            except asyncio.TimeoutError:
                # [FIX-7] No heartbeat — just wait for next request
                continue

            if not self._session:
                print("[Vision] ⚠️  No session — dropping image")
                continue
            try:
                # [FIX-3] Send raw bytes, not base64
                # [FIX-9] Use proper SDK types
                await self._session.send_client_content(
                    turns=gtypes.Content(
                        parts=[
                            gtypes.Part(
                                inline_data=gtypes.Blob(
                                    mime_type=mime_type,
                                    data=image_bytes,
                                )
                            ),
                            gtypes.Part(text=user_text),
                        ]
                    ),
                    turn_complete=True,
                )
                print(f"[Vision] 📤 Sent {len(image_bytes):,} bytes — '{user_text[:60]}'")
            except Exception as e:
                print(f"[Vision] ⚠️  Send error: {e}")

    async def _recv_loop(self) -> None:
        transcript: list[str] = []
        try:
            async for response in self._session.receive():
                if response.data:
                    await self._audio_in.put(response.data)

                sc = response.server_content
                if not sc:
                    continue

                if sc.output_transcription and sc.output_transcription.text:
                    chunk = sc.output_transcription.text.strip()
                    if chunk:
                        transcript.append(chunk)

                if sc.turn_complete:
                    if transcript and self._player:
                        full = re.sub(r"\s+", " ", " ".join(transcript)).strip()
                        if full:
                            self._player.write_log(f"Friday: {full}")
                            print(f"[Vision] 💬 {full}")
                    transcript = []

        except Exception as e:
            print(f"[Vision] ⚠️  Recv error: {e}")
            raise

    async def _play_loop(self) -> None:
        stream = None
        try:
            stream = sd.RawOutputStream(
                samplerate=_RECEIVE_SAMPLE_RATE,
                channels=_CHANNELS,
                dtype="int16",
                blocksize=_CHUNK_SIZE,
            )
            stream.start()
            while not self._stopping:
                chunk = await self._audio_in.get()
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            if not self._stopping:
                print(f"[Vision] ❌ Play error: {e}")
            raise
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass


# Module-level persistent session
_session      = _VisionSession()
_session_lock = threading.Lock()
_session_up   = False


def _ensure_session(player=None) -> None:
    global _session_up
    with _session_lock:
        if not _session_up:
            _session.start(player=player)
            _session_up = True
        elif player is not None:
            _session._player = player


# [FIX-4] Public shutdown for clean exit
def shutdown_session() -> None:
    global _session_up
    with _session_lock:
        if _session_up:
            _session.stop()
            _session_up = False


def screen_process(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
) -> bool:
    params    = parameters or {}
    user_text = (params.get("text") or params.get("user_text") or "").strip()
    angle     = params.get("angle", "screen").lower().strip()

    if not user_text:
        print("[Vision] ⚠️  No question provided — aborting")
        return False

    print(f"[Vision] ▶ angle={angle!r}  question='{user_text[:80]}'")

    try:
        if angle == "camera":
            image_bytes, mime_type = _capture_camera()
            print(f"[Vision] 📷 Camera: {len(image_bytes):,} bytes")
        else:
            image_bytes, mime_type = _capture_screen()
            print(f"[Vision] 🖥️  Screen: {len(image_bytes):,} bytes")
    except Exception as e:
        print(f"[Vision] ❌ Capture error: {e}")
        return False

    # [FIX-1] Use persistent module-level session instead of creating new one
    try:
        _ensure_session(player=player)
    except RuntimeError as e:
        print(f"[Vision] ❌ Session failed: {e}")
        return False

    _session.analyze(image_bytes, mime_type, user_text)
    return True


def warmup_session(player=None) -> None:
    try:
        _ensure_session(player=player)
    except Exception as e:
        print(f"[Vision] ⚠️  Warmup failed: {e}")


if __name__ == "__main__":
    print("[TEST] screen_processor.py")
    print("=" * 52)
    mode = input("angle — screen / camera (default: screen): ").strip().lower() or "screen"
    q    = input("Question (Enter = default): ").strip() or "What do you see? Be brief."

    t0 = time.perf_counter()
    warmup_session()
    print(f"Session ready in {time.perf_counter()-t0:.2f}s\n")

    t1 = time.perf_counter()
    ok = screen_process({"angle": mode, "text": q})
    print(f"Queued in {time.perf_counter()-t1:.3f}s — waiting for audio...")
    time.sleep(10)

    shutdown_session()
    print("Done." if ok else "Failed.")
