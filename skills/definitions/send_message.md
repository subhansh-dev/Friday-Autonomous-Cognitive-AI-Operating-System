---
name: send_message
trigger: When the user wants to send a message via WhatsApp or Telegram
freedom: low
gotchas:
  - Requires valid contacts — must be in your contact list
  - Message text is sent as-is — no undo
  - WhatsApp Web must be logged in and not logged out
---

platform: "whatsapp" or "telegram"
contact: string — phone number or username
message: string — text content, max 4000 chars
For WhatsApp: opens web interface and sends via browser automation.
For Telegram: uses Telegram Bot API with bot_token.