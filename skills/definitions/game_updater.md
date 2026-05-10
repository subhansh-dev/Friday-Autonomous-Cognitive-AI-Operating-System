---
name: game_updater
trigger: When the user wants to check or manage game updates on Steam or Epic Games
freedom: medium
gotchas:
  - Requires Steam/Epic to be installed and logged in
  - Some games run background downloaders
  - Epic web API may be rate-limited
---

platform: "steam" or "epic"
action: "check_updates", "update_all", "check_running"
For Steam: uses Steam API via steam module or registry
For Epic: scrapes Epic Games launcher page