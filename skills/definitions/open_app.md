---
name: open_app
trigger: When the user wants to open or launch an application
freedom: medium
gotchas:
  - App must be installed on system
  - Some apps require full path, not just name
  - macOS requires osascript for GUI apps
---

app_name: string — application name or path
Uses subprocess.run() with shell=True on Windows, open command on macOS.
Returns: success/failure with process info.