---
name: file_controller
trigger: When the user wants to create, read, delete, search, or manage files and directories
freedom: medium
gotchas:
  - Deletions are permanent — no trash recovery
  - Large file searches may be slow — use max_depth limit
  - Permission errors common on system folders
---

Actions: read, write, delete, move, copy, list, search, mkdir
Paths support ~ for home directory expansion.
For search: glob patterns like *.py, **/*.js for recursive.
Returns file metadata: size, created, modified timestamps.