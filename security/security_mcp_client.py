# FRIDAY Cyber Security MCP Client (patched v1.1)
# Changes from v1.0:
#   [FIX-1] stderr drained in background thread — prevents pipe deadlock
#   [FIX-2] Lock released before blocking read — other threads can call during timeout

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional


class CyberMCPClient:
    """Client for the FRIDAY Cyber Security MCP Server.

    Starts the MCP server as a subprocess and communicates via stdin/stdout
    using a simple JSON-RPC protocol.
    """

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._req_id = 0
        self._server_script = Path(__file__).parent.parent / "cyber" / "mcp_server.py"
        self._stderr_lines: list[str] = []
        self._stderr_thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _drain_stderr(self):
        """FIX-1: Continuously read stderr to prevent pipe buffer deadlock."""
        try:
            while self._process and self._process.poll() is None:
                line = self._process.stderr.readline()
                if line:
                    self._stderr_lines.append(line.rstrip())
                    # Keep only last 100 lines
                    if len(self._stderr_lines) > 100:
                        self._stderr_lines = self._stderr_lines[-80:]
                else:
                    break
        except Exception:
            pass

    def start(self) -> str:
        """Start the MCP server subprocess."""
        if self.is_running:
            return "MCP server already running."
        if not self._server_script.exists():
            return f"MCP server script not found: {self._server_script}"
        try:
            self._process = subprocess.Popen(
                [sys.executable, str(self._server_script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            # FIX-1: Start stderr drain thread
            self._stderr_lines = []
            self._stderr_thread = threading.Thread(
                target=self._drain_stderr, daemon=True)
            self._stderr_thread.start()

            # Wait for startup signal with timeout
            result_holder = [None]
            def _read_start():
                try:
                    result_holder[0] = self._process.stdout.readline()
                except Exception:
                    pass
            reader = threading.Thread(target=_read_start, daemon=True)
            reader.start()
            reader.join(timeout=15)

            if reader.is_alive():
                self.stop()
                return "MCP server failed to start (15s timeout)."
            if not result_holder[0]:
                stderr_dump = "\n".join(self._stderr_lines[-5:])
                self.stop()
                return f"MCP server sent no startup signal. Stderr:\n{stderr_dump}"

            data = json.loads(result_holder[0])
            if "result" in data:
                return f"MCP server started: {data['result'].get('status', 'ok')}"
            return f"MCP server started (unexpected: {result_holder[0][:100]})"
        except Exception as e:
            return f"Failed to start MCP server: {e}"

    def stop(self) -> str:
        """Stop the MCP server subprocess."""
        if not self.is_running:
            self._process = None
            return "MCP server not running."
        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=3)
            self._process = None
            return "MCP server stopped."
        except Exception as e:
            self._process = None
            return f"Error stopping MCP server: {e}"

    def call(self, method: str, params: dict = None, timeout: float = 300.0) -> str:
        """Call a method on the MCP server and return the result."""
        if not self.is_running:
            return json.dumps({"error": "MCP server is not running. Call 'start_mcp' first."})

        # FIX-2: Acquire lock only for request ID + write, not for read
        with self._lock:
            self._req_id += 1
            req_id = self._req_id
            request = {
                "id": req_id,
                "method": method,
                "params": params or {},
            }
            try:
                req_str = json.dumps(request) + "\n"
                self._process.stdin.write(req_str)
                self._process.stdin.flush()
            except BrokenPipeError:
                self._process = None
                return json.dumps({"error": "MCP server process died unexpectedly."})
            except Exception as e:
                return json.dumps({"error": f"MCP write failed: {e}"})

        # FIX-2: Read outside lock — other threads can send while we wait
        result_holder = [None]
        error_holder = [None]

        def _read_line():
            try:
                result_holder[0] = self._process.stdout.readline()
            except Exception as e:
                error_holder[0] = e

        reader = threading.Thread(target=_read_line, daemon=True)
        reader.start()
        reader.join(timeout=timeout)

        if reader.is_alive():
            return json.dumps({"error": f"MCP server timed out after {timeout}s"})

        if error_holder[0]:
            return json.dumps({"error": str(error_holder[0])})

        if not result_holder[0]:
            stderr_dump = "\n".join(self._stderr_lines[-3:])
            return json.dumps({
                "error": "MCP server closed connection",
                "stderr": stderr_dump,
            })

        raw = result_holder[0].strip()

        # Unwrap JSON-RPC envelope — return clean result
        try:
            resp = json.loads(raw)
            if "error" in resp:
                err = resp["error"]
                return json.dumps(err if isinstance(err, dict) else {"error": str(err)})
            if "result" in resp:
                return json.dumps(resp["result"])
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        return raw

    def health(self) -> dict:
        """Quick health check."""
        if not self.is_running:
            return {"status": "stopped"}
        try:
            r = self.call("health", timeout=10)
            return json.loads(r)
        except Exception:
            return {"status": "error"}

    def get_stderr(self, lines: int = 10) -> list[str]:
        """Get recent stderr output from the server process."""
        return self._stderr_lines[-lines:]


# Singleton
_client: Optional[CyberMCPClient] = None
_client_lock = threading.Lock()


def get_mcp_client() -> CyberMCPClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = CyberMCPClient()
    return _client
