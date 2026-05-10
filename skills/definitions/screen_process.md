---
name: screen_process
trigger: When the user wants to capture the screen or camera and analyze it with vision
freedom: medium
gotchas:
  - Camera index must be configured — default is 0
  - Spawns daemon thread — main session stays silent
  - Low light affects camera quality
---

source: "screen" or "camera"
For screen: uses mss for fast capture, PIL for processing
For camera: uses OpenCV, releases resource after capture
Returns: image path, then uses vision model to analyze