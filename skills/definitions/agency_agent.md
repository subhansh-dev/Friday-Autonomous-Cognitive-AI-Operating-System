---
name: agency_agent
trigger: When the user wants a specialized agent to handle a complex sub-task
freedom: high
gotchas:
  - Agent spawns sub-session — uses additional API calls
  - May take time for complex tasks
  - Parent agent monitors but doesn't micro-manage
---

task: string — what the sub-agent should do
agent_type: "developer", "researcher", "writer", "security", "planner"
Spawns specialized agent with domain-specific context.
Results flow back to parent agent for synthesis.