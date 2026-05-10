---
name: dev_agent
trigger: When the user wants to build a multi-file project from a description
freedom: high
gotchas:
  - Complex projects may need multiple iterations
  - Generated code should be reviewed before running
  - Dependencies must be installed manually
---

description: string — what to build
language: string — optional, e.g., "python", "javascript", "rust"
Uses AI to generate project structure, multiple files, and README.
Creates files in current directory or specified path.