import asyncio
import json
import os
import sys
import httpx
from pathlib import Path
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
# Load from environment variable or config file — never hardcode secrets
BOT_TOKEN = os.environ.get("FRIDAY_TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER = int(os.environ.get("FRIDAY_TELEGRAM_ALLOWED_USER", "0"))

if not BOT_TOKEN or not ALLOWED_USER:
    # Fallback: try loading from config file
    try:
        base = Path(__file__).resolve().parent
        cfg_path = base / "config" / "api_keys.json"
        if cfg_path.exists():
            import json
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            BOT_TOKEN = cfg.get("telegram_bot_token", "") or BOT_TOKEN
            ALLOWED_USER = int(cfg.get("telegram_allowed_user", "0")) or ALLOWED_USER
    except Exception:
        pass

if not BOT_TOKEN:
    print("[Telegram] " + "=" * 55)
    print("[Telegram]   TELEGRAM BOT NOT CONFIGURED")
    print("[Telegram] " + "=" * 55)
    print("[Telegram]   To enable Telegram remote control:")
    print("[Telegram]     Option A - Environment variables:")
    print("[Telegram]       set FRIDAY_TELEGRAM_BOT_TOKEN=your_bot_token")
    print("[Telegram]       set FRIDAY_TELEGRAM_ALLOWED_USER=your_user_id")
    print("[Telegram]")
    print("[Telegram]     Option B - Config file (config/api_keys.json):")
    print("[Telegram]       Add these fields:")
    print("[Telegram]         \"telegram_bot_token\": \"your_bot_token\"")
    print("[Telegram]         \"telegram_allowed_user\": 123456789")
    print("[Telegram]")
    print("[Telegram]     Get a token from: https://t.me/BotFather")
    print("[Telegram]     Find your user ID at: https://t.me/userinfobot")
    print("[Telegram] " + "=" * 55)
    print("[Telegram] Bot disabled. FRIDAY will run without Telegram.")
    print("[Telegram]")
    sys.exit(0)
# ──────────────────────────────────────────────────────────────────────────────

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
BASE_DIR = Path(__file__).resolve().parent
INBOX    = BASE_DIR / "telegram_inbox.json"
OUTBOX   = BASE_DIR / "telegram_outbox.json"


def write_inbox(text: str):
    data = {
        "text": text,
        "timestamp": datetime.now().isoformat(),
        "processed": False
    }
    try:
        tmp = INBOX.with_suffix('.tmp')
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(INBOX)
    except OSError:
        INBOX.write_text(json.dumps(data), encoding="utf-8")


def read_outbox() -> str | None:
    if not OUTBOX.exists():
        return None
    try:
        data = json.loads(OUTBOX.read_text(encoding="utf-8"))
        if data.get("ready"):
            try:
                OUTBOX.unlink()
            except OSError:
                pass
            return data.get("response", "Done.")
    except (json.JSONDecodeError, OSError):
        pass
    return None


async def send_message(chat_id: int, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(f"{BASE_URL}/sendMessage", json={
            "chat_id": chat_id,
            "text": text
        })


async def wait_for_response(timeout: int = 20) -> str:
    for _ in range(timeout * 10):
        response = read_outbox()
        if response:
            return response
        await asyncio.sleep(0.1)
    return "FRIDAY didn't respond in time!"


async def main():
    print("[Telegram] Bot starting...")
    offset = 0

    # First clear any old pending updates
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.get(f"{BASE_URL}/getUpdates", params={"offset": -1, "limit": 1})
            updates = r.json().get("result", [])
            if updates:
                offset = updates[-1]["update_id"] + 1
                print(f"[Telegram] Cleared old updates, starting from offset {offset}")
        except Exception as e:
            print(f"[Telegram] Could not clear updates: {e}")

    print("[Telegram] Bot is running! Text your bot on Telegram.")

    while True:
        try:
            async with httpx.AsyncClient(timeout=35) as client:
                r = await client.get(f"{BASE_URL}/getUpdates", params={
                    "offset": offset,
                    "timeout": 25,
                    "allowed_updates": ["message"]
                })
                data = r.json()

                if not data.get("ok"):
                    print(f"[Telegram] API error: {data}")
                    await asyncio.sleep(2)
                    continue

                updates = data.get("result", [])

                for update in updates:
                    offset = update["update_id"] + 1
                    message = update.get("message", {})
                    chat_id = message.get("chat", {}).get("id")
                    user_id = message.get("from", {}).get("id")
                    text    = message.get("text", "")

                    if not text:
                        continue

                    print(f"[Telegram] Message from {user_id}: {text}")

                    if user_id != ALLOWED_USER:
                        # Silently ignore unauthorized users — don't confirm bot exists
                        continue

                    if text == "/start":
                        await send_message(chat_id,
                            "FRIDAY is online!\nText me any command and I'll forward it to your laptop.\n\nCommands:\n/lock - Lock mic-triggered actions\n/unlock - Unlock mic-triggered actions\n/status - Check security status")
                        continue

                    if text == "/lock":
                        write_inbox("__LOCK_SECURITY__")
                        await send_message(chat_id, "🔒 Security lock activated. Mic-triggered actions blocked.")
                        continue

                    if text == "/unlock":
                        write_inbox("__UNLOCK_SECURITY__")
                        await send_message(chat_id, "🔓 Security lock deactivated.")
                        continue

                    if text == "/status":
                        write_inbox("__SECURITY_STATUS__")
                        await send_message(chat_id, "⏳ Checking security status...")
                        continue

                    write_inbox(text)
                    await send_message(chat_id, "⚡ Sending to FRIDAY...")

                    response = await wait_for_response(timeout=20)
                    await send_message(chat_id, f"🤖 {response}")
                    print(f"[Telegram] Replied: {response}")

        except httpx.TimeoutException:
            pass  # normal, just means no new messages
        except Exception as e:
            print(f"[Telegram] Error: {e}")
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())