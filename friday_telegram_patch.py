import asyncio
import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
INBOX    = BASE_DIR / "telegram_inbox.json"
OUTBOX   = BASE_DIR / "telegram_outbox.json"


class TelegramBridge:
    def __init__(self, friday):
        self.friday = friday
        self.pending_response = False
        self.last_command = ""
        print("[Telegram] Bridge watching for inbox messages...")

    def _read_inbox(self):
        """Check if there's a new command from Telegram."""
        if not INBOX.exists():
            return None
        try:
            data = json.loads(INBOX.read_text(encoding="utf-8"))
            if not data.get("processed"):
                return data
        except Exception:
            pass
        return None

    def _mark_processed(self):
        """Mark inbox message as processed."""
        if INBOX.exists():
            try:
                data = json.loads(INBOX.read_text(encoding="utf-8"))
                data["processed"] = True
                tmp = INBOX.with_suffix('.tmp')
                tmp.write_text(json.dumps(data), encoding="utf-8")
                tmp.replace(INBOX)
            except Exception:
                pass

    def write_outbox(self, response: str):
        """Write Friday's response for Telegram bot to pick up."""
        data = {
            "response": response,
            "timestamp": datetime.now().isoformat(),
            "ready": True
        }
        try:
            tmp = OUTBOX.with_suffix('.tmp')
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(OUTBOX)
        except OSError:
            OUTBOX.write_text(json.dumps(data), encoding="utf-8")
        print(f"[Telegram] Response sent: {response[:80]}")

    def send_response(self, text: str):
        """Called by main.py when FRIDAY finishes speaking — writes actual reply."""
        if self.pending_response and text:
            self.write_outbox(text)
            self.pending_response = False
            # Reset action source back to mic after Telegram response
            try:
                self.friday._action_source = "mic"
            except Exception:
                pass

    def _handle_security_command(self, text: str) -> str | None:
        """Handle security commands from Telegram. Returns response if handled."""
        from security import get_lock_state
        lock = get_lock_state()

        if text == "__LOCK_SECURITY__":
            lock.locked = True
            return "🔒 Security lock activated. Mic-triggered actions blocked."
        if text == "__UNLOCK_SECURITY__":
            lock.locked = False
            return "🔓 Security lock deactivated."
        if text == "__SECURITY_STATUS__":
            status = "ENABLED" if lock.locked else "DISABLED"
            from security import get_permission_manager
            pm = get_permission_manager()
            return (
                f"FRIDAY Security Status:\n"
                f"  Lock: {status}\n"
                f"  Strict mode: {pm.policy.strict_mode}\n"
                f"  Tools: {len(pm._risk_overrides) + 23} registered"
            )
        return None

    async def poll(self):
        """Continuously check for incoming Telegram commands."""
        print("[Telegram] Polling for commands...")
        while True:
            se = getattr(self.friday, '_shutdown_event', None)
            if se is not None and se.is_set():
                print("[Telegram] Shutting down poll.")
                return
            try:
                inbox = self._read_inbox()
                if inbox:
                    text = inbox.get("text", "")
                    print(f"[Telegram] Command received: {text}")
                    self._mark_processed()

                    # Handle security commands first
                    sec_response = self._handle_security_command(text)
                    if sec_response:
                        self.write_outbox(sec_response)
                        continue

                    if self.friday.session:
                        # Mark Telegram as the action source for the next tool call
                        self.friday._action_source = "telegram"
                        self.last_command = text
                        self.pending_response = True
                        await self.friday.session.send_client_content(
                            turns={"parts": [{"text": text}]},
                            turn_complete=True
                        )
                        # Non-blocking timeout: wait up to 30s without blocking event loop
                        try:
                            await asyncio.wait_for(
                                self._wait_for_response(), timeout=30)
                        except asyncio.TimeoutError:
                            if self.pending_response:
                                self.pending_response = False
                                self.write_outbox("Friday is still processing your request. Will respond here when done.")
                    else:
                        self.write_outbox("Friday is not connected yet. Try again in a moment.")

            except Exception as e:
                print(f"[Telegram] Poll error: {e}")

            await asyncio.sleep(0.5)

    async def _wait_for_response(self):
        """Wait until pending_response is cleared by send_response()."""
        while self.pending_response:
            await asyncio.sleep(0.5)