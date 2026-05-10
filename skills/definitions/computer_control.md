---
name: computer_control
trigger: When the user wants to control mouse, keyboard, take screenshots, or interact with the desktop
freedom: medium
gotchas:
  - pyautogui must be installed: pip install pyautogui
  - Screen resolution affects coordinates — use pyautogui.size() to calibrate
  - Move mouse safely: always call pyautogui.moveTo with pauses to avoid losing focus
---

Actions: click, double_click, right_click, drag, type, press, hotkey, screenshot, locate_image
Coordinates are (x, y) from top-left. Use pyautogui.position() to get current mouse position.
For screenshot: saves to temp file, returns path.