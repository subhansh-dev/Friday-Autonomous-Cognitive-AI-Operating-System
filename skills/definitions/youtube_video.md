---
name: youtube_video
trigger: When the user wants to search, play, or summarize YouTube videos
freedom: medium
gotchas:
  - Requires yt-dlp for playback: pip install yt-dlp
  - Age-restricted videos may fail
  - Music may trigger copyright detection
---

Actions: search, play, download, summarize
For search: returns top 5 results with title, duration, channel
For summarize: uses AI to extract key points from video transcript