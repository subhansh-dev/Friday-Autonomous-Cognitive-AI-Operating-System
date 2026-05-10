---
name: code_helper
trigger: When the user wants to write, edit, run, or debug code
freedom: high
gotchas:
  - Code execution is sandboxed — no system calls, file I/O restricted
  - Long-running scripts may timeout — use timeout=30s max
  - Debug requires full context — provide file paths for best results
---

Actions: write, edit, run, debug, explain, refactor
For write: provide filename, language, code content
For run: captures stdout/stderr, returns exit code
For debug: parse error messages, suggest fixes