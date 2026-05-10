# -*- coding: utf-8 -*-
"""
api_server.py — FRIDAY REST API Server
Provides remote control, status monitoring, and memory access via HTTP.
"""
import sys
import json
import time
import threading
from pathlib import Path
from typing import Optional, Any

_HAVE_FASTAPI = False
try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
    import uvicorn
    _HAVE_FASTAPI = True
except ImportError:
    pass

def _get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


# ── Request models (only defined if FastAPI available) ────────────────

if _HAVE_FASTAPI:
    class MemorySaveRequest(BaseModel):
        category: str = Field(default="notes",
                              description="Memory category")
        key:      str = Field(..., min_length=1,
                              description="Memory key")
        value:    str = Field(..., min_length=1,
                              description="Memory value")


class FridayAPIServer:
    """REST API server for FRIDAY — remote control, status, and data queries."""

    def __init__(self):
        self.app: Optional[Any] = None
        self._server: Optional[Any] = None          # [#1] track uvicorn
        self._server_thread: Optional[threading.Thread] = None
        self._running = False
        self._port = 8899
        self._host = "127.0.0.1"
        self._start_time = 0.0                       # [#2]

        if not _HAVE_FASTAPI:
            return

        self.app = FastAPI(title="Friday API", version="1.0.0")
        self._add_cors()                             # [#3]
        self._add_security_middleware()
        self._register_routes()

    # ── CORS ──────────────────────────────────────────────────────────

    def _add_cors(self):                             # [#3]
        if not self.app:
            return
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:*", "http://127.0.0.1:*"],
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    # ── Security middleware ───────────────────────────────────────────

    def _add_security_middleware(self):
        if not self.app:
            return

        @self.app.middleware("http")
        async def audit_middleware(request: Request, call_next):
            t0 = time.time()
            response = await call_next(request)
            elapsed = time.time() - t0

            try:                                     # [#4]
                from security.audit_logger import get_audit_logger
                audit = get_audit_logger()
                audit.log(
                    action=f"api_{request.method}",
                    status="ok" if response.status_code < 400 else "error",
                    source="api",
                    tool_name=request.url.path,
                    reason=f"HTTP {response.status_code}",
                    duration_ms=round(elapsed * 1000, 1),
                )
            except Exception:
                pass  # audit failure shouldn't break API

            return response

    # ── Routes ────────────────────────────────────────────────────────

    def _register_routes(self):
        if not self.app:
            return

        @self.app.get("/")
        async def root():
            uptime = round(time.time() - self._start_time) if self._start_time else 0
            return {
                "status": "online",
                "name":   "Friday",
                "uptime": f"{uptime}s",
            }

        @self.app.get("/health")                     # [#5]
        async def health():
            return {
                "status": "healthy",
                "uptime": round(time.time() - self._start_time) if self._start_time else 0,
            }

        @self.app.get("/status")
        async def status():
            try:
                import psutil
                return {
                    "cpu":    psutil.cpu_percent(interval=0.3),
                    "memory": psutil.virtual_memory().percent,
                    "disk":   psutil.disk_usage("/").percent,
                    "status": "active",
                }
            except ImportError:
                return {
                    "status": "online",
                    "note":   "psutil not installed — limited info",
                }

        @self.app.get("/memory/stats")
        async def memory_stats():
            try:
                from brain.neural_memory import get_brain
                b = get_brain()
                return b.get_stats()
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/memory/recall/{category}/{key}")
        async def recall_memory(category: str, key: str):
            try:
                from brain.neural_memory import get_brain
                b = get_brain()
                result = b.recall_by_key(category, key)
                if result and result.get("value"):
                    return result
                raise HTTPException(status_code=404,
                                    detail="Memory not found")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/memory/save")
        async def save_memory(data: MemorySaveRequest):  # [#6]
            try:
                from brain.neural_memory import get_brain
                b = get_brain()
                b.encode(data.category, data.key, data.value)
                return {"saved": True, "id": f"{data.category}:{data.key}"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/memory/search")
        async def search_memory(q: str = "", limit: int = 10):  # [#7]
            try:
                from brain.neural_memory import get_brain
                b = get_brain()
                matches = b.search_memory(q, top_k=min(limit, 50))
                return {"query": q, "results": matches, "count": len(matches)}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/system/info")
        async def system_info():
            try:
                from brain.integrations import (
                    get_system_dashboard, get_windows_system_info)
                return {
                    "dashboard": get_system_dashboard(),
                    "system":    get_windows_system_info(),
                }
            except Exception as e:
                return {"error": str(e)}

        @self.app.get("/extensions")
        async def extensions():
            try:
                from brain.integrations import integration_status
                return {"extensions": integration_status()}
            except Exception as e:
                return {"error": str(e)}

        @self.app.get("/tasks")                      # [#8]
        async def list_tasks():
            try:
                from agent.task_queue import get_queue
                q = get_queue()
                return {
                    "tasks":   q.get_all_statuses(),
                    "metrics": q.get_metrics(),
                }
            except Exception as e:
                return {"error": str(e)}

        @self.app.get("/tasks/{task_id}")
        async def get_task(task_id: str):
            try:
                from agent.task_queue import get_queue
                q = get_queue()
                status = q.get_status(task_id)
                if status:
                    return status
                raise HTTPException(status_code=404,
                                    detail="Task not found")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/tasks/cancel/{task_id}")
        async def cancel_task(task_id: str):
            try:
                from agent.task_queue import get_queue
                q = get_queue()
                cancelled = q.cancel(task_id)
                if cancelled:
                    return {"cancelled": True, "task_id": task_id}
                raise HTTPException(
                    status_code=404,
                    detail="Task not found or already finished")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self, port: int = 8899, host: str = "127.0.0.1"):
        if not _HAVE_FASTAPI:
            print("[API] ⚠️ FastAPI not installed — server disabled")
            return
        if self._running:
            print("[API] Already running")
            return

        self._port = port
        self._host = host
        self._running = True
        self._start_time = time.time()

        config = uvicorn.Config(                     # [#9]
            self.app,
            host=host,
            port=port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)

        self._server_thread = threading.Thread(
            target=self._run_server,
            daemon=True,
            name="FridayAPI",
        )
        self._server_thread.start()
        print(f"[API] Friday API server running at http://{host}:{port}")

    def _run_server(self):                           # [#9]
        try:
            self._server.run()
        except Exception as e:
            print(f"[API] ❌ Server crashed: {e}")
            self._running = False

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self._server:                             # [#1]
            self._server.should_exit = True
        print("[API] 🔴 Server stopping")

    @property
    def available(self) -> bool:
        return _HAVE_FASTAPI

    @property
    def is_running(self) -> bool:                    # [#10]
        return self._running


# ── Singleton ─────────────────────────────────────────────────────────

_api_server: Optional[FridayAPIServer] = None
_server_lock = threading.Lock()


def get_api_server() -> FridayAPIServer:             # [#11]
    global _api_server
    with _server_lock:
        if _api_server is None:
            _api_server = FridayAPIServer()
        return _api_server
