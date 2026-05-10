---
name: desktop
trigger: When the user wants to change wallpaper, organize desktop, or get desktop stats
freedom: medium
gotchas:
  - Wallpaper path must exist and be valid image format
  - Organize moves files — hard to undo
  - Requires proper permissions on the desktop folder
---

action: "set_wallpaper", "organize", "stats", "screenshot"
For set_wallpaper: provide full path to image
For organize: groups files by type into folders
For stats: returns file count, folder count, total size