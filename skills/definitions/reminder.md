---
name: reminder
trigger: When the user wants to set a reminder or schedule a task
freedom: medium
gotchas:
  - Uses Windows Task Scheduler (schtasks) or at command
  - Reminder time must be in the future
  - Requires proper datetime parsing
---

message: string — what to remind about
time: string — "2026-05-08 14:30" or "in 30 minutes" or "tomorrow 9am"
Creates scheduled task that launches a notification script.
Use python-dateutil for flexible parsing.